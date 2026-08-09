"""Shared pytest fixtures.

DB strategy: run alembic once per session into a template file, then copy the
file per test — migrations are exercised on every run but tests stay fast.
File-based SQLite only (never :memory:) so WAL and multi-connection behavior
match production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template_dir = tmp_path_factory.mktemp("db-template")
    db_path = template_dir / "template.sqlite3"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        # 인코딩을 안 적으면 로케일(한국어 Windows 에서는 cp949)로 디코드한다. 마이그레이션
        # 설명에 한글이나 특수문자가 하나만 있어도 리더 스레드가 UnicodeDecodeError 로 죽어
        # **stderr 를 못 읽는다** — 즉 마이그레이션이 실패했을 때 정작 그 이유를 못 본다.
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
    assert db_path.exists()
    return db_path


@pytest.fixture()
def db_path(migrated_db_template: Path, tmp_path: Path) -> Path:
    target = tmp_path / "web.sqlite3"
    shutil.copy(migrated_db_template, target)
    return target


# 노션 DB id 는 설치처 고유값이라 소스 기본값이 **비어 있다**(app/core/tenant_config.py).
# 테스트 세계는 '설정을 마친 설치'를 흉내 낸다: 비워 두면 티켓·문서 경로가 '설정 안 됨'으로
# 먼저 막혀, 정작 검증하려던 로직에 닿지도 못한 채 초록불이 나온다(가짜 안전감).
# 값 자체는 아무 문자열이어도 되지만 가짜 노션 서버가 URL 로 알아봐야 하므로
# tests/fakes/notion.py 의 DEFAULT_TASKS_DB 와 같은 값을 쓴다.
# 비어 있을 때의 동작은 tests/unit/test_tenant_defaults.py 가 따로 고정한다.
TEST_DOCS_DB = "docs-db-0001"


@pytest.fixture()
def settings(db_path: Path, tmp_path: Path) -> Settings:
    from tests.fakes.notion import DEFAULT_TASKS_DB

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=PROJECT_ROOT / "config",
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
        notion_tasks_database_id=DEFAULT_TASKS_DB,
        notion_documents_database_id=TEST_DOCS_DB,
    )


@pytest.fixture()
def fake_clock():
    from tests.fakes.clock import FakeClock

    return FakeClock()


@pytest.fixture()
def fake_http():
    from tests.fakes.http import FakeHTTP

    return FakeHTTP()


@pytest.fixture()
def app(settings: Settings, fake_clock, fake_http):
    return create_app(
        settings, clock=fake_clock, outbound_transport=fake_http.transport()
    )


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def db(app):
    factory = app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


DEFAULT_TEST_PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture()
def make_user(db, settings):
    from app.users.service import create_user

    def _make(
        email: str = "user@goodmit.co.kr",
        *,
        password: str = DEFAULT_TEST_PASSWORD,
        role: str = "user",
        active: bool = True,
        must_change_password: bool = False,
        display_name: str = "테스트 사용자",
    ):
        user = create_user(
            db,
            email=email,
            display_name=display_name,
            password=password,
            settings=settings,
            # 테스트 픽스처는 seed_admin.py 와 같은 성격의 부트스트랩이다 - 임의 역할의
            # 테스트 사용자를 자유롭게 만들 수 있어야 하므로 system_admin 으로 self-declare.
            actor_role="system_admin",
            role=role,
            active=active,
            must_change_password=must_change_password,
        )
        db.commit()
        return user

    return _make


@pytest.fixture()
def login_as(client, make_user):
    """Create a user for the given role, log in, and return the CSRF token.

    The client keeps the session cookie automatically.
    """

    def _login(role: str = "user", *, email: str | None = None):
        from app.users.service import get_user_by_email

        email = email or f"{role.replace('_', '-')}@goodmit.co.kr"
        # Tolerate a pre-created user (tests that call make_user then login_as).
        with client.app.state.session_factory() as db:
            existing = get_user_by_email(db, email)
        if existing is None:
            make_user(email=email, role=role)
        response = client.post(
            "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
        )
        assert response.status_code == 200, response.text
        return response.json()["csrf_token"]

    return _login


# ── 두 번째 조직 시드 — org 축을 **검증 가능하게** 만드는 전제 (7단계 #5) ────────
#
# 계획서(PLAN4)가 이렇게 적어 놨다: 조직이 **1개뿐**이라 `WHERE org_id = :org` 는 한 행도
# 안 거른다 — 효과도 없고 **검증도 불가능**하다(걸린 것과 안 건 것이 구별되지 않는다).
# 그 상태로 테스트를 쓰면 `test_scope_idor_matrix.py` 가 `user.admin_scope = scope` 를 손으로
# 대입해 만든 **'가짜 안전감'과 똑같은 실패**를 되풀이한다 — 초록불인데 아무것도 증명하지 못한다.
#
# 그래서 코드를 쓰기 **전에** 두 조직이 실제로 존재하는 세계를 만든다.
#
# `org_id` 를 **명시적으로** 넣는다. 새 행의 org 를 무엇으로 정할지는 아직 코드가 답하지 않는
# 질문이고(신규 행 org 추론), 픽스처가 그걸 몰래 정해 버리면 나중에 결정을 바꿀 때 테스트가
# 먼저 깨진다.

@dataclass(frozen=True)
class OrgWorld:
    """두 조직과 각 조직의 부서·사람 하나씩. 테스트가 읽기 좋게 이름을 붙여 둔다."""

    org_a_id: str
    org_b_id: str
    user_a: object
    user_b: object
    dept_a: object
    dept_b: object


@pytest.fixture()
def two_orgs(db, make_user) -> "OrgWorld":
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department, Organization

    org_b = Organization(slug="org-b", name="두번째조직")
    db.add(org_b)
    db.flush()

    dept_a = Department(name="A팀", org_id=DEFAULT_ORG_ID)
    dept_b = Department(name="B팀", org_id=org_b.id)
    db.add_all([dept_a, dept_b])
    db.flush()

    user_a = make_user("orga@goodmit.co.kr", role="user", display_name="A사람")
    user_b = make_user("orgb@goodmit.co.kr", role="user", display_name="B사람")
    user_a.org_id = DEFAULT_ORG_ID
    user_a.department_id = dept_a.id
    user_b.org_id = org_b.id
    user_b.department_id = dept_b.id
    db.commit()

    return OrgWorld(
        org_a_id=DEFAULT_ORG_ID, org_b_id=org_b.id,
        user_a=user_a, user_b=user_b, dept_a=dept_a, dept_b=dept_b,
    )


# ── 설치가 끝난 세계 (9-3) ────────────────────────────────────────────────────
#
# 기본 테스트 세계는 마이그레이션만 돈 **갓 설치한** 상태다: 부서도 Notion 토큰도 러너도
# 연동도 없다. 그 상태에서 사용자 화면 배너는 이제 "초기 설정이 아직 끝나지 않았습니다" 를
# 말한다(app/setup/checklist.py) - 그게 이 과제가 없애려던 침묵의 반대편이다.
#
# 그래서 "정상이면 배너가 조용하다" 같은 성질을 검사하는 테스트는 **정상인 세계**를 먼저
# 만들어야 한다. 항목마다 손으로 채우면 그 목록이 테스트 파일마다 복사되고, 항목이 하나
# 늘 때 어느 한 곳을 빠뜨려도 아무 테스트가 빨개지지 않는다. 그래서 한 곳에 둔다.


@pytest.fixture()
def setup_complete(db, settings, make_user, fake_clock):
    """셋업 체크리스트가 일반 사용자에게 말할 것이 없는 상태로 만든다.

    사용자에게 보이는 항목(조직, Notion, 매핑, 러너, 연동)만 채운다. 관리자 계정과 TLS 는
    사용자 화면이 비는 이유가 아니라 배너에 쓰이지 않는다(app/setup/steps.py).
    """
    from app.integrations.models import HEALTH_UP, Integration
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.observability.models import COMPONENT_DOCUMENTS, SYNC_OK, SyncStatus
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.runners.models import Runner

    now = fake_clock.now()
    for ref in (settings.notion_report_token_ref, settings.notion_docs_token_ref):
        (settings.secrets_dir / ref).write_text("test-token", encoding="utf-8")

    db.add(Department(name="개발팀", org_id=DEFAULT_ORG_ID))
    # 티켓이 아니라 문서 쪽에 성공 이력을 둔다 - 티켓 동기화 지연을 검사하는 테스트가
    # 자기 값을 따로 심으므로 서로 덮어쓰지 않게 한다.
    db.add(
        SyncStatus(
            component=COMPONENT_DOCUMENTS, status=SYNC_OK, last_success_at=now, item_count=1
        )
    )
    db.add(
        Runner(
            name="setup-runner", provider_type="http_service",
            base_url="http://127.0.0.1:8789", enabled=True, last_health_status=HEALTH_UP,
        )
    )
    db.add(
        Integration(
            name="setup-n8n", provider_type="n8n", base_url="http://127.0.0.1:5678",
            capabilities_json="{}", enabled=True, last_health_status=HEALTH_UP,
        )
    )
    db.flush()
    mapped = make_user("mapped@goodmit.co.kr", role="user", display_name="연결된 사용자")
    db.add(
        UserNotionMapping(
            user_id=mapped.id, notion_user_id="notion-mapped",
            status=STATUS_VERIFIED, last_verified_at=now,
        )
    )
    db.commit()
