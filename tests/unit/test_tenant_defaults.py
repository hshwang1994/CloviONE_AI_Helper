"""고객사 고유값이 기본값에 남아 있지 않은지, 비었을 때 무슨 일이 벌어지는지 고정한다.

## 왜 이 테스트가 있는가

`app/core/config.py` 의 **기본값**에 이 워크스페이스의 Notion DB id 두 개와
`allowed_email_domains="goodmit.co.kr"` 가 박혀 있었다. 다른 고객사에 설치하면 아무 설정
없이도 조용히 이 워크스페이스를 가리켰다. 토큰이 없어 데이터가 새지는 않지만,
**동작하지 않는 이유가 어디에도 안 뜬다** - "연결은 됐는데 안 된다" 로 보인다.

그래서 세 가지를 한꺼번에 못 박는다.

1. 기본 설정에 고객 식별자가 없다.
2. 비었을 때의 동작이 **의도한 방향**이다. 이메일 도메인이 비면 "아무나 로그인 가능" 인지
   "아무도 로그인 불가" 인지 틀리면 정반대가 된다 - 아래 도메인 테스트의 docstring 에
   기존 로그인 코드를 읽고 내린 판단과 근거를 적어 뒀다.
3. 진단이 "설정 안 됨" 을 **빈 값과 구분해서** 말한다(§불변 6: 0 과 "없음" 과 "못 잼" 은
   서로 다른 사실이다).

⚠️ 순수 함수만 시험하면 배선을 증명하지 못한다(이 저장소에서 실제로 다섯 번 겪었다).
그래서 `tenant_config_status` 단위 검사와 **HTTP 로 진단 번들을 받아 보는 검사**를 둘 다 둔다.

qa-contract-change: 노션 데이터베이스 id 두 개가 설정에서 사라져 그 키를 이름으로 묻던 단언들이 대상을 잃었고, 빈 id 로 외부 조회가 나가지 않는지 보던 시험은 조회 경로 자체가 없어져 지운다. 대신 기본값 검사를 어느 필드에도 그 값이 없다로 강화하고, 진단이 사라진 키를 되살려 말하지 않는지를 새로 못박는다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 이 워크스페이스를 가리키던 값들. 테스트가 스스로 문자열을 들고 있어야 "기본값에 없다" 를
# 실제로 증명한다(설정 파일을 읽어 비교하면 같이 바뀌어 버려 아무것도 증명하지 못한다).
CUSTOMER_NOTION_TASKS_DB = "262c5c5a568481fa9697ee5691cb558d"
CUSTOMER_NOTION_DOCS_DB = "55efc3c0b58341a5b8d17f31fc2b152c"
CUSTOMER_EMAIL_DOMAIN = "goodmit.co.kr"
# S3 이 정본 호스트를 옮겼다. **둘 다 든다** — 옛 이름은 되살아나는 것을 막고, 새 이름은
# 지금 새는 것을 막는다. 하나만 들면 이름이 바뀔 때마다 검사가 한 칸씩 뒤처진다.
LEGACY_CUSTOMER_HOST = "clovirone-ai.gooddi.lab"
CUSTOMER_HOST = "clovirassist.gooddi.lab"


def _bare_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


# ── 1. 기본 설정에 고객 식별자가 없다 ────────────────────────────────────────


def test_default_settings_have_no_customer_identifiers():
    s = _bare_settings()
    assert s.allowed_email_domains == ""
    assert s.allowed_email_domain_list == []
    # 노션 데이터베이스 id 두 개는 설정 **필드 자체가** 없어졌다(S14). 그래서 이름으로
    # 묻는 대신 **어느 필드에도 그 값이 없다**로 본다 — 필드 이름이 바뀌어 되살아나도
    # 이 검사는 그대로 잡는다.
    values = {str(getattr(s, name)) for name in Settings.model_fields}
    assert CUSTOMER_NOTION_TASKS_DB not in values
    assert CUSTOMER_NOTION_DOCS_DB not in values
    # 기본 base url 은 개발용 루프백이어야 한다. 고객사 호스트가 여기 있으면 메일 링크와
    # 리다이렉트가 남의 서버를 가리킨다. `APP_BASE_URL` 은 설치처 env 가 정한다(S3).
    assert CUSTOMER_HOST not in s.app_base_url
    assert LEGACY_CUSTOMER_HOST not in s.app_base_url


def test_settings_registry_default_domain_list_is_empty():
    """DB 설정 레지스트리의 기본값도 같이 비어야 한다.

    env 기본값만 비우고 레지스트리를 두면, 설치 직후 첫 부팅에서 레지스트리 기본값이
    DB 에 내려앉아 고객 도메인이 되살아난다.
    """
    from app.settings.registry import get_spec

    assert get_spec("allowed_email_domains").default == []


# ── 2. 비었을 때의 동작이 의도한 방향이다 ────────────────────────────────────


def test_empty_domain_list_means_no_restriction_not_lockout():
    """빈 도메인 목록 = "제한 없음". "아무도 못 쓴다" 가 아니다.

    기존 코드를 읽고 내린 판단이다.

      * 로그인(`app/auth/router.py`)은 도메인을 **아예 보지 않는다**. 이 값은
        `app/users/service.py::create_user` 의 **계정 생성** 경로에서만 쓰인다.
        따라서 이 값을 비워도 기존 사용자의 로그인은 영향을 받지 않는다.
      * DB 설정이 있는 경로는 이미 빈 목록을 "제한 없음" 으로 해석한다
        (`create_user` 의 `if configured:` 분기, `registry._email_domains` 의 안내문,
        Settings 화면의 "빈 목록이면 제한 없음" 문구).
      * 계정 생성은 관리자 전용이다(관리 콘솔, 일괄 등록 CSV, CLI, seed 스크립트).
        공개 가입 경로가 없으므로 "제한 없음" 이 곧 아무나 들어온다는 뜻이 아니다.

    그런데 **env 기본값만 쓰는 폴백 경로**(`effective_settings` 를 안 넘기는 CLI 등)는
    빈 목록을 만나면 `domain not in []` 로 **전부 거절**했다. 방향이 정반대인 두 경로가
    한 저장소에 있었다. 여기서 한 방향으로 고정한다.
    """
    from app.users.service import validate_company_email

    s = _bare_settings()
    # 예외가 나면 실패한다. "제한 없음" 이 의도한 방향이다.
    validate_company_email("anyone@some-other-company.example", s)


def test_configured_domain_list_still_rejects_outsiders():
    """비었을 때만 제한이 없다. 값을 넣으면 예전처럼 막아야 한다."""
    from app.core.errors import ValidationAppError
    from app.users.service import validate_company_email

    s = _bare_settings(allowed_email_domains="example.com")
    validate_company_email("ok@example.com", s)
    with pytest.raises(ValidationAppError):
        validate_company_email("nope@other.example", s)


# ── 3. 진단이 "설정 안 됨" 을 구분해 말한다 ──────────────────────────────────


def test_tenant_config_status_marks_unset_items():
    from app.core.tenant_config import tenant_config_status

    status = tenant_config_status(_bare_settings())
    assert status["configured"] is False
    by_key = {item["key"]: item for item in status["items"]}
    assert by_key["allowed_email_domains"]["state"] == "unset"
    # 노션 데이터베이스 id 두 개가 여기 있었다. 설정 자체가 사라졌으므로 목록에도 없어야
    # 한다 — 남아 있으면 진단이 **존재하지 않는 값**을 안 채웠다고 말한다.
    assert "notion_tasks_database_id" not in by_key
    assert "notion_documents_database_id" not in by_key
    # 빈 값이 아니라 "왜 문제인가" 를 사람 문장으로 들고 있어야 화면이 안내를 그릴 수 있다.
    assert by_key["allowed_email_domains"]["when_unset"].strip()


def test_tenant_config_status_marks_set_items():
    from app.core.tenant_config import tenant_config_status

    status = tenant_config_status(
        _bare_settings(allowed_email_domains="example.com")
    )
    assert status["configured"] is True
    assert all(item["state"] == "set" for item in status["items"])
    assert status["unset_count"] == 0


def test_tenant_config_status_reads_db_override_for_domains():
    """도메인은 관리 콘솔에서도 바꾼다. 진단은 실제로 적용 중인 값을 봐야 한다."""
    from app.core.tenant_config import tenant_config_status

    status = tenant_config_status(
        _bare_settings(), effective={"allowed_email_domains": ["example.com"]}
    )
    by_key = {item["key"]: item for item in status["items"]}
    assert by_key["allowed_email_domains"]["state"] == "set"


def test_tenant_config_status_unwraps_effective_settings_envelope():
    """진단이 실제로 넘기는 모양은 값이 아니라 **메타데이터 봉투**다.

    `app/settings/service.py::effective_settings` 는 화면용으로
    `{"value": [], "type": "object", ...}` 를 준다. 봉투를 그대로 보면 항상 비어 있지 않은
    dict 라 **빈 목록이 "설정됨" 으로 보고됐다** - 실제로 이렇게 틀렸고, HTTP 로 두 번 불러
    값이 바뀌는지 본 테스트가 잡았다. 그 모양을 여기서 직접 고정한다.
    """
    from app.core.tenant_config import tenant_config_status

    envelope_empty = {
        "allowed_email_domains": {
            "value": [], "type": "object", "restart_required": False,
            "description": "허용 이메일 도메인", "is_default": True,
        }
    }
    status = tenant_config_status(_bare_settings(), effective=envelope_empty)
    by_key = {item["key"]: item for item in status["items"]}
    assert by_key["allowed_email_domains"]["state"] == "unset"

    envelope_filled = {
        "allowed_email_domains": {
            "value": ["example.com"], "type": "object", "restart_required": False,
            "description": "허용 이메일 도메인", "is_default": False,
        }
    }
    status = tenant_config_status(_bare_settings(), effective=envelope_filled)
    by_key = {item["key"]: item for item in status["items"]}
    assert by_key["allowed_email_domains"]["state"] == "set"


def test_diagnostics_bundle_reports_tenant_config(client, login_as, settings):
    """배선 검사. 순수 함수가 맞아도 번들에 안 실리면 아무도 못 본다.

    ⚠️ **값이 실제로 달라지는 표본**을 쓴다. 한 번만 불러 "unset" 을 확인하면, 진단이 설정을
    읽지 않고 상수를 돌려줘도 초록불이다(이 저장소에서 실제로 겪은 실패 유형이다).
    같은 엔드포인트를 설정이 있는 상태와 없는 상태로 두 번 불러 **응답이 따라 바뀌는지** 본다.
    """
    login_as("system_admin")

    # 1) 갓 설치한 상태. 픽스처는 이메일 도메인을 비워 둔다.
    tenant = client.get("/api/admin/diagnostics/bundle").json()["tenant_config"]
    states = {item["key"]: item["state"] for item in tenant["items"]}
    assert states["allowed_email_domains"] == "unset"
    # 하나라도 비면 '설정 완료'가 아니다.
    assert tenant["configured"] is False
    assert tenant["unset_count"] == 1
    # 화면이 "아직 설정하지 않았습니다"를 그릴 수 있게 안내 문장도 같이 온다.
    assert all(item["when_unset"].strip() for item in tenant["items"])

    # 2) 설정을 마친 설치로 바꾼다. 응답이 따라 바뀌어야 한다.
    client.app.state.settings.allowed_email_domains = "example.com"
    tenant = client.get("/api/admin/diagnostics/bundle").json()["tenant_config"]
    states = {item["key"]: item["state"] for item in tenant["items"]}
    assert states["allowed_email_domains"] == "set"
    assert tenant["configured"] is True
    assert tenant["unset_count"] == 0


# ── 4. 정적 검사가 실제로 돈다 ───────────────────────────────────────────────


def test_check_tenant_defaults_script_passes_on_clean_tree():
    """검사 자신이 헛것이 아닌지는 "되돌려서 실패하는가" 로 본다(작업 노트에 기록).

    여기서는 깨끗한 트리에서 통과하는 것만 고정한다. 통과조차 못 하면 아무도 안 켠다.
    """
    result = subprocess.run(
        [sys.executable, "scripts/check_tenant_defaults.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        # 검사기는 한국어로 실패를 알린다. Windows 기본 cp949 로 읽으면 여기서 터져
        # 실패 내용을 못 본다(검사기 자신이 stdout 을 utf-8 로 재설정하는 것과 같은 이유).
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_tenant_defaults_script_catches_reintroduced_identifier(tmp_path):
    """검사가 눈을 뜨고 있는지 본다. 고객 식별자를 넣은 파일을 주면 실패해야 한다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_tenant_defaults", PROJECT_ROOT / "scripts" / "check_tenant_defaults.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sample = tmp_path / "config.py"
    sample.write_text(
        f'notion_tasks_database_id: str = "{CUSTOMER_NOTION_TASKS_DB}"\n',
        encoding="utf-8",
    )
    hits = module.scan_text(sample.name, sample.read_text(encoding="utf-8"))
    assert hits, "고객 DB id 를 도로 넣었는데 검사가 아무 말도 안 한다"

    # S3 회귀: 정본 호스트가 바뀌면 검사도 따라와야 한다. 옛 이름만 들고 있으면 새 이름을
    # 소스 기본값에 박아도 아무 데서도 안 걸리고, 그것은 검사가 있는데 없는 상태다.
    for host in (CUSTOMER_HOST, LEGACY_CUSTOMER_HOST):
        leaked = tmp_path / "leaked.py"
        leaked.write_text(f'app_base_url: str = "https://{host}"\n', encoding="utf-8")
        assert module.scan_text(leaked.name, leaked.read_text(encoding="utf-8")), (
            f"소스 기본값에 {host} 를 박았는데 검사가 아무 말도 안 한다"
        )
