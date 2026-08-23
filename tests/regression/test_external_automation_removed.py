"""외부 자동화가 **없다**는 것을 시험으로 못 박는다 (S11 · P-21).

qa-contract-replaced-by: tests/integration/test_documents_api.py
qa-contract-replaced-by: tests/integration/test_runners_api.py
qa-contract-replaced-by: tests/integration/test_templates_api.py
qa-contract-replaced-by: tests/integration/test_workflows_api.py
qa-contract-replaced-by: tests/integration/test_notion_mapping_sync_job.py
qa-contract-replaced-by: tests/security/test_document_generation_scope.py
qa-contract-replaced-by: tests/unit/test_document_quality.py
qa-contract-replaced-by: tests/unit/test_runner_circuit.py
qa-contract-replaced-by: tests/unit/test_runner_health_sweep.py
qa-contract-replaced-by: tests/unit/test_chat_runner_context_delete.py
qa-contract-replaced-by: tests/regression/test_notion_mapping_workflow_is_seeded.py
qa-contract-replaced-by: tests/integration/test_handlers_hardening.py
qa-contract-replaced-by: frontend/src/screens/registry-documents-empty-help.test.js
qa-contract-replaced-by: frontend/src/screens/registry/documents-retry-endpoint.test.jsx
qa-contract-replaced-by: frontend/src/screens/runner-maintenance-action.test.jsx
qa-contract-replaced-by: frontend/src/screens/registry-integration-name-label.test.js

## 위 시험들을 왜 이 파일이 대신하는가

그것들이 지키던 계약은 **「이 기능이 이렇게 동작한다」**였다. S11 이 그 기능들을 걷어냈으니
같은 계약을 다른 파일에 다시 쓸 수는 없다. 대신 지켜야 할 계약이 하나 생겼다 —
**「그것들이 돌아오지 않는다」**다. 지운 코드는 되살아나기 쉽다: 누군가 `app/runners` 를
다시 만들거나, 허용 목록에 `127.0.0.1:5678` 을 한 줄 되돌리거나, 옛 설치 스크립트가 여전히
n8n 유닛을 확인하면 그때부터 이 세션이 한 일이 조용히 무효가 된다.

지우는 것으로 끝나면 그 회귀는 **아무 오류도 안 낸다.** 그것이 이 파일의 존재 이유다.

## 무엇을 안 보는가

서버에서 유닛이 실제로 죽었는지는 여기서 못 본다(그건 그 서버의 상태이지 이 저장소의
상태가 아니다). 실측은 [`EVIDENCE/S11/`](../../docs/platform/EVIDENCE/S11/README.md) 이
들고, 여기서는 **저장소가 다시 그것을 부르려 하지 않는지**만 본다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]

#: 사라진 서비스가 듣던 포트. 이 문자열이 제품 코드나 설정에 다시 나타나면 안 된다.
DEAD_PORTS = ("5678", "5679", "8787", "8788", "8789")

#: 사라진 모듈. import 가 되살아나면 그 자체가 회귀다.
DEAD_MODULES = ("app.workflows", "app.runners", "app.documents", "app.templates")

#: 사라진 잡 종류. 워커 레지스트리에 다시 들어오면 부를 핸들러가 없다.
DEAD_JOB_TYPES = ("document_generate", "notion_mapping_sync")


def _tracked(*globs: str) -> list[Path]:
    out: list[Path] = []
    for pattern in globs:
        out.extend(
            p for p in ROOT.glob(pattern)
            if p.is_file() and "__pycache__" not in p.parts and "node_modules" not in p.parts
        )
    return out


# ── 1. 제품 코드가 사라진 것을 안 부른다 ──────────────────────────────────────


def test_no_module_imports_the_removed_packages():
    """`app/**` 어디에서도 지운 네 패키지를 import 하지 않는다.

    빠뜨린 import 하나는 **그 라우트를 실제로 부를 때까지** 안 드러난다 — S2 가 정확히
    그 사고를 겪었다(P-09b). 여기서 정적으로 잡는다.
    """
    pattern = re.compile(
        r"(?:^|\s)(?:from|import)\s+(%s)\b" % "|".join(re.escape(m) for m in DEAD_MODULES)
    )
    offenders = [
        f"{p.relative_to(ROOT).as_posix()}:{i}"
        for p in _tracked("app/**/*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == [], f"지운 패키지를 다시 import 한다: {offenders}"


def test_the_app_builds_without_the_removed_routes(app):
    """FastAPI 앱에 그 화면들의 경로가 하나도 안 남아 있다."""
    paths = {r.path for r in app.routes}
    dead = sorted(
        p for p in paths
        if p.startswith(("/api/admin/workflows", "/api/admin/runners",
                         "/api/admin/documents", "/api/admin/templates"))
        or p.endswith("/notion-mapping/sync")
        or p.endswith("/notion-mapping/{user_id}/verify")
    )
    assert dead == [], f"지운 화면의 라우트가 남아 있다: {dead}"


def test_worker_registers_no_handler_for_the_removed_job_types():
    """워커 핸들러 표에 부를 곳 없는 잡 종류가 없다.

    남겨 두면 큐에 그 종류가 들어왔을 때 **핸들러는 있는데 부를 것이 없는** 상태가 된다.
    """
    from app.worker_main import build_handlers

    handlers = build_handlers()
    leftover = sorted(set(DEAD_JOB_TYPES) & set(handlers))
    assert leftover == [], f"사라진 잡 종류에 핸들러가 붙어 있다: {leftover}"


# ── 2. 허용 목록이 그 포트로 나가지 않는다 ────────────────────────────────────


def test_outbound_allowlists_no_longer_reach_the_dead_ports():
    """SSRF 허용 목록에 죽은 포트가 없다. **이것이 실제 경계다.**

    화면에서 지우는 것은 편의일 뿐이다 — 허용 목록에 한 줄이 남아 있으면 관리자가 연동
    하나를 만들어 그 주소를 다시 부를 수 있다.
    """
    config_dir = ROOT / "config"
    assert (config_dir / "allowed-services.json").exists()
    # 러너·워크플로 전용 목록은 파일 자체가 사라졌다 — 이름만 남으면 다시 채워진다.
    assert not (config_dir / "allowed-runners.json").exists()
    assert not (config_dir / "allowed-workflows.json").exists()

    hosts = json.loads((config_dir / "allowed-services.json").read_text(encoding="utf-8"))["hosts"]
    bad = [h for h in hosts if any(h.endswith(":" + port) for port in DEAD_PORTS)]
    assert bad == [], f"허용 목록이 아직 죽은 포트로 나갈 수 있다: {bad}"


def test_allowlist_registry_has_no_runner_or_workflow_lane():
    """`AllowlistRegistry` 가 아는 이름에 `runners`/`workflows` 가 없다.

    이름이 남아 있으면 `OutboundClient(allowlist="runners")` 가 다시 쓰일 수 있고, 그때
    빈 파일은 «허용 목록이 없다» 가 아니라 «아무것도 허용 안 함» 이라 조용히 실패한다.
    """
    from app.core.allowlist import ALLOWLIST_FILES

    assert "runners" not in ALLOWLIST_FILES
    assert "workflows" not in ALLOWLIST_FILES


# ── 3. 배포·운영 산출물에 n8n 흔적이 없다 (P-21 완료의 정의) ──────────────────


def test_installer_and_ops_scripts_have_no_n8n_trace():
    """설치·백업·검증 스크립트 어디에도 n8n 이 없다.

    특히 `scripts/validate-clovirone-web-assistant.sh` 는 «n8n 이 살아 있다» 를 **성공
    조건으로** 단언하고 있었다 — 그대로 두면 n8n 을 지운 설치에서 검증이 실패한다.
    """
    offenders = []
    for p in _tracked("deploy/**/*", "scripts/*.sh", "config/*.json", ".env.example"):
        # 개발용 자율 러너(`scripts/runner/`)와 사전조사 산출물(실측 기록)은 제품이 아니다.
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("scripts/runner/") or "/artifacts/" in rel:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if "n8n" in low and "s11" not in low:
                offenders.append(f"{rel}:{i}")
            elif any(re.search(r"[:.]%s\b" % port, line) for port in DEAD_PORTS):
                offenders.append(f"{rel}:{i}")
    assert offenders == [], f"배포·운영 산출물에 n8n/러너 흔적이 남아 있다: {offenders}"


def test_the_workflow_export_is_archived_before_the_engine_was_removed():
    """지우기 전에 워크플로를 **보관했다** — S11 실행 순서의 첫 단계다.

    「끄고 나서 옮기지 않는다」가 이 세션의 순서였고(INVENTORY 09), 그 순서를 지켰다는
    증거가 저장소 안에 있어야 한다. 서버는 다시 설치되지만 이 파일은 남는다.
    """
    archive = ROOT / "docs" / "platform" / "EVIDENCE" / "S11" / "n8n-workflows-s11.tar.gz"
    assert archive.exists(), "n8n 워크플로 export 아카이브가 없다"
    assert archive.stat().st_size > 10_000, "아카이브가 비어 있다"


# ── 4. DB 에서도 사라졌다 ─────────────────────────────────────────────────────


def test_the_four_tables_are_gone_from_the_schema(db):
    """실 스키마에 표 넷이 없다. 모델만 지우면 표는 그대로 남는다."""
    from sqlalchemy import text

    rows = db.execute(text(
        "select table_name from information_schema.tables "
        "where table_schema = 'public' and table_name = any(:names)"
    ), {"names": ["workflows", "runners", "automation_templates", "document_generations"]})
    assert sorted(r[0] for r in rows) == []


def test_runner_reference_columns_are_gone(db):
    """`prompts.runner_id` · `schedules.runner_id` 도 함께 내려갔다.

    가리킬 표가 없는 참조 컬럼은 아무것도 안 가리키는 36자 문자열이다.
    """
    from sqlalchemy import text

    rows = db.execute(text(
        "select table_name from information_schema.columns "
        "where table_schema = 'public' and column_name = 'runner_id'"
    ))
    assert sorted(r[0] for r in rows) == []
