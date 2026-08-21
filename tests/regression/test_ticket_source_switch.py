"""TICKET_SOURCE 킬 스위치 — 미러를 꺼도 응답이 한 글자도 안 바뀌는지 고정한다.

`ticket_source=notion` 은 운영용 되돌리기 장치다: 로컬 미러가 이상하면 env 한 줄을 바꿔 재시작하는
것만으로 캐시 도입 **이전과 똑같은 실시간 경로**로 돌아가야 한다. 그게 실제로 참인지 확인하지 않으면
그건 장치가 아니라 희망사항이다.

확인 방법 두 겹:
  1. 같은 시드·같은 페이크로 `notion_cache` 와 `notion` 두 앱을 띄워 모든 티켓 읽기 엔드포인트
     응답을 **바이트 단위로** 비교한다.
  2. 그 응답이 커밋된 골든 계약과도 같은지 확인한다 — 두 모드가 똑같이 틀린 경우를 잡는다.

시드/페이크는 골든 계약 모듈에서 그대로 가져온다. 여기서 따로 만들면 '계약'이 두 벌이 된다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes.clock import FakeClock
from tests.fakes.notion import DEFAULT_PROJECTS_DB, DEFAULT_TASKS_DB, FakeNotionTasksDB
from tests.regression.test_api_contract_golden import (
    CONTRACT_NOW,
    CONTRACT_PASSWORD,
    GOLDEN_DIR,
    PROJECT_ROWS,
    TASK_BLOCKS,
    TASK_ROWS,
    TOKEN_REF,
    _canonical,
    _seed_users,
)

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.regression, pytest.mark.real_db]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 골든이 얼려 둔 티켓 읽기 경로 전부. /api/tickets/{id} 상세도 포함한다 — 상세는 늘 실시간이라
# 두 모드가 같아야 하는 것이 당연하지만, '당연한 것'이 깨지는 게 회귀다.
PATHS = [
    ("tickets_mine", "/api/tickets/mine"),
    ("tickets_unassigned", "/api/tickets/unassigned"),
    ("tickets_team_active", "/api/tickets/team?active=true"),
    ("tickets_team_all", "/api/tickets/team?active=false"),
    ("tickets_meta", "/api/tickets/meta"),
    ("tickets_projects", "/api/tickets/projects"),
    ("tickets_detail", "/api/tickets/page-0001"),
    ("sprint_summary", "/api/sprint/summary"),
    ("dev_monthly", "/api/admin/reports/dev-monthly?period=2026-07"),
]


def _run(db_url, tmp_path, ticket_source: str) -> dict[str, str]:
    """주어진 소스 설정으로 앱을 띄워 모든 경로의 정규화된 JSON을 돌려준다."""
    secrets_dir = tmp_path / f"secrets-{ticket_source}"
    secrets_dir.mkdir(exist_ok=True)
    (secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=db_url,
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=PROJECT_ROOT / "config",
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
        ticket_source=ticket_source,
        # 작업 DB id 는 설치처 고유값이라 소스 기본값이 비어 있다(app/core/tenant_config.py).
        # 안 채우면 조회가 '설정 안 됨'으로 먼저 막혀, 두 소스가 **둘 다 빈 응답**으로 같아진다
        # - 킬 스위치가 동작한다는 증거가 아니라 아무것도 시험하지 못한 초록불이다.
        notion_tasks_database_id=DEFAULT_TASKS_DB,
    )
    from tests.fakes.http import FakeHTTP

    fake_http = FakeHTTP()
    FakeNotionTasksDB(
        rows=TASK_ROWS, projects=PROJECT_ROWS, blocks=TASK_BLOCKS,
        projects_db=DEFAULT_PROJECTS_DB, fail_message="계약 테스트용 강제 오류",
    ).install(fake_http)
    app = create_app(settings, clock=FakeClock(CONTRACT_NOW),
                     outbound_transport=fake_http.transport())
    out: dict[str, str] = {}
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/login", json={"email": "contract-admin@goodmit.co.kr",
                                            "password": CONTRACT_PASSWORD})
        assert login.status_code == 200, login.text
        for name, path in PATHS:
            response = client.get(path)
            assert response.status_code == 200, f"{path}: {response.text}"
            out[name] = _canonical(response.json())
    return out


@pytest.fixture()
def seeded_db(db_url, app, db):
    """골든과 같은 사용자·매핑을 심은 DB 파일 경로. ticket_cache 는 일부러 비워 둔다 —
    미러가 비면 notion_cache 모드도 실시간으로 폴백해야 하고, 그게 여기서 비교하는 성질이다."""
    _seed_users(db)
    return db_url


def test_kill_switch_produces_byte_identical_payloads(seeded_db, tmp_path):
    cached = _run(seeded_db, tmp_path, "notion_cache")
    live = _run(seeded_db, tmp_path, "notion")
    for name, _path in PATHS:
        assert cached[name] == live[name], (
            f"{name}: TICKET_SOURCE 를 바꿨더니 응답이 달라졌다 — 킬 스위치가 되돌리기가 아니다.\n"
            f"--- notion_cache ---\n{cached[name]}\n--- notion ---\n{live[name]}"
        )


def test_both_modes_match_the_committed_golden(seeded_db, tmp_path):
    """두 모드가 서로 같기만 하고 둘 다 계약과 다르면 의미가 없다 — 골든과도 맞춘다."""
    for source in ("notion_cache", "notion"):
        payloads = _run(seeded_db, tmp_path, source)
        for name, _path in PATHS:
            golden = (GOLDEN_DIR / f"{name}__ok.json").read_text(encoding="utf-8")
            if name == "dev_monthly":
                # generated_at 은 얼린 시계라 고정이지만, 골든은 그 값을 포함해 저장돼 있다.
                assert json.loads(payloads[name]) == json.loads(golden), name
            else:
                assert payloads[name] == golden, f"{name} ({source}) 가 골든과 다르다"
