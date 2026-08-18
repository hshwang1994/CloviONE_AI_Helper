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
        membership: str = "organization",
    ):
        """테스트 사용자 하나.

        `membership` 기본값이 `organization`(조직 직속)인 이유: 픽스처가 만드는 사람은
        "이 회사에서 일하는 보통 사람" 이라, 조직 데이터가 하나도 안 보이는 상태를 기본으로
        두면 거의 모든 테스트가 그 게이트에만 걸려 정작 검사하려던 것을 못 본다.

        **제품의 기본값은 다르다** — `create_user` 는 `unassigned` 로 만든다(0060, fail-closed).
        그 기본값 자체는 `tests/security/test_membership_gate.py` 가 따로 못박는다. 여기서
        바꾸는 것은 픽스처의 편의이지 제품 동작이 아니다.

        부서를 배정하는 테스트는 이 값을 신경 쓸 필요가 없다 — 부서가 있으면 부서가 이긴다
        (`app/core/scope.py::_membership_scope`).
        """
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
        user.membership_kind = membership
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


# ── Resource Ownership (0060) ─────────────────────────────────────────────────
#
# 자원의 소속을 만드는 자리를 여기 하나로 둔다. 예전에는 테스트마다 `TicketCache` 나
# `DocumentCache` 를 손으로 조립했는데, 소속 축이 바뀌자 그 조립이 전부 낡았다 — 그리고
# 낡은 방식은 "권한이 없어서 안 보이는 것" 과 "픽스처가 소속을 안 심어서 안 보이는 것" 을
# 구별할 수 없게 만든다. 소속을 만드는 방법이 한 곳에 있으면 다음에 축이 또 바뀌어도
# 고칠 곳이 하나다.


@pytest.fixture()
def make_project(db):
    """Portal 프로젝트 하나. `dept` 를 주면 그 부서 소유, 안 주면 **조직 공통**이다.

    `external_id`(외부 소스 page id)를 주면 티켓 동기화가 그 프로젝트로 해석할 수 있다 —
    안 주면 포털 전용 프로젝트라 외부 티켓이 붙을 수 없다(실제 제품과 같은 성질).
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project

    def _make(
        *,
        name: str = "테스트 프로젝트",
        dept=None,
        org_id: str | None = None,
        external_id: str | None = None,
        code: str | None = None,
    ):
        dept_id = getattr(dept, "id", dept)
        resolved_org = org_id or getattr(dept, "org_id", None) or DEFAULT_ORG_ID
        project = Project(
            name=name, code=code, dept_id=dept_id, org_id=resolved_org,
            notion_page_id=external_id,
        )
        db.add(project)
        db.flush()
        db.commit()
        return project

    return _make


@pytest.fixture()
def portal_project(make_project):
    """페이크 소스가 매다는 기본 프로젝트(`DEFAULT_PROJECT_PAGE_ID`)의 **Portal 짝**.

    0060 부터 티켓의 소속은 프로젝트가 정한다. Portal 에 짝이 없으면 그 티켓은
    `project_link='unresolved'` 로 남고, 그건 전역 관리자 말고는 아무에게도 안 보인다 —
    티켓을 다루는 시험은 대개 그 상태를 보려는 것이 아니므로 이 픽스처를 함께 쓴다.

    부서를 안 주므로 **조직 공통** 프로젝트다(`dept_id IS NULL` → ORGANIZATION). 조직에
    속한 사람이면 누구나 보이는 상태라, 소속 게이트가 아니라 시험하려던 것이 검사된다.
    부서별 격리를 보려면 `tests/fixtures/org_tree.py` 의 세계를 쓴다.
    """
    from tests.fakes.notion import DEFAULT_PROJECT_PAGE_ID

    return make_project(name="기본 프로젝트", external_id=DEFAULT_PROJECT_PAGE_ID)


@pytest.fixture()
def make_document(db):
    """소속이 심긴 문서 미러 한 건.

    `project` 를 주면 프로젝트 소유, `dept` 를 주면 부서 소유, `org_id` 만 주면 조직 공통,
    아무 것도 안 주면 **미지정**(fail-closed 확인용)이다. 소속을 안 주는 것이 기본값인
    이유는 "안 정하면 닫힌다" 가 이 모델의 핵심 성질이기 때문이다.
    """
    from app.core import ownership
    from app.org.constants import DEFAULT_ORG_ID
    from app.team_docs.models import DocumentCache, join_names

    def _make(
        *,
        page_id: str,
        title: str = "문서",
        project=None,
        dept=None,
        org_id: str | None = None,
        org_wide: bool = False,
        restricted: bool = False,
        author_notion_ids: list[str] | None = None,
        author_names: list[str] | None = None,
        project_names: list[str] | None = None,
        status: str | None = None,
    ):
        dept_id = getattr(dept, "id", dept)
        resolved_org = (
            org_id
            or getattr(project, "org_id", None)
            or getattr(dept, "org_id", None)
            or DEFAULT_ORG_ID
        )
        if project is not None:
            kind, owner_project, owner_dept = ownership.OWNER_PROJECT, project.id, None
        elif dept_id:
            kind, owner_project, owner_dept = ownership.OWNER_DEPARTMENT, None, dept_id
        elif org_wide:
            kind, owner_project, owner_dept = ownership.OWNER_ORGANIZATION, None, None
        else:
            kind, owner_project, owner_dept = ownership.OWNER_UNSET, None, None
        row = DocumentCache(
            notion_page_id=page_id,
            title=title,
            org_id=resolved_org,
            owner_kind=kind,
            owner_project_id=owner_project,
            owner_dept_id=owner_dept,
            restricted=restricted,
            author_notion_ids=join_names(author_notion_ids or []),
            author_names=join_names(author_names or []),
            project_names=join_names(project_names or []),
            project_external_ids=join_names(
                [project.notion_page_id] if project is not None and project.notion_page_id else []
            ),
            status=status,
        )
        db.add(row)
        db.flush()
        db.commit()
        return row

    return _make
