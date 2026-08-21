"""Shared pytest fixtures.

## DB 전략은 2계층이다 (D-190)

**기본(거의 모든 시험).** 시험마다 커넥션 하나를 열고 트랜잭션을 시작한 뒤, 앱을 **그
커넥션 위에서** 띄우고, 끝나면 통째로 되감는다. 앱이 부르는 `commit()` 은 SAVEPOINT
릴리스가 되므로(`app/core/db.py::make_session_factory`) 시험 안에서는 커밋된 것처럼
보이지만 DB 에는 아무것도 남지 않는다. 시험 하나당 수 ms 다.

**실 DB 가 필요한 시험 — `@pytest.mark.real_db`.** 커넥션이 여럿이어야 하는 동시성 시험과
별도 프로세스를 띄우는 시험은 위 방식으로 못 한다 — 트랜잭션 하나 안에 갇힌 데이터는 다른
커넥션에 안 보인다. 그런 시험은 `CREATE DATABASE … TEMPLATE` 로 자기 DB 를 받고 끝나면 지운다.

**마커가 필요한 경우 다섯** — 전부 「다른 커넥션이 이 시험의 데이터를 봐야 한다」로 같다:

  1. `db_url` 픽스처를 쓴다(두 번째 엔진·스레드 경합).
  2. `DATABASE_URL` 로 **따로 붙는** 코드를 부른다(CLI, 별도 프로세스).
  3. **`create_app(settings, …)` 을 직접 부른다.** 하네스의 바인드를 안 받으므로 자기 엔진을
     만들고 진짜로 커밋한다 — 공유 DB 에서는 그 커밋이 되감기 밖에 있어 다음 시험으로 샌다.
  4. **스레드·프로세스를 여럿 띄운다.** 공유 계층에서는 그 세션들이 같은 커넥션 하나를
     나눠 쓴다 — 경합이 재현되기는커녕 커넥션이 엉켜 엉뚱한 오류가 난다.
  5. **「요청이 롤백돼도 남는다」를 단언한다.** 제품은 그러려고 별도 세션에서 커밋한다
     (rate limiter, 임퍼소네이션 차단 카운터). 공유 계층에서는 그 세션이 **같은 커넥션의
     SAVEPOINT** 라, 요청 롤백이 그것까지 되감아 «안 남는다» 로 보인다 — 제품이 아니라
     하네스 때문에 빨간불이 되는 자리다.

예전에는 alembic 을 파일 하나에 돌려 놓고 시험마다 `shutil.copy` 했다. **파일 DB 전용
기법**이라 PG 로 그대로 옮길 수 없다.

## 접속 정보

`CLOVIR_TEST_PG_URL` 로 덮어쓸 수 있다. 기본값은 로컬 개발용 컨테이너다.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 시험용 PostgreSQL. 이 주소의 서버에 **DB 를 만들고 지울 수 있어야** 한다.
DEFAULT_TEST_PG_URL = "postgresql://cloviradmin:s2devpw@127.0.0.1:55433/postgres"
TEST_PG_URL = os.environ.get("CLOVIR_TEST_PG_URL", DEFAULT_TEST_PG_URL)

# 마이그레이션을 한 번만 돌려 두는 원본. 시험 DB 는 전부 이것을 복제해 만든다.
#
# **이름에 프로세스 id 를 넣는다.** 안 넣으면 pytest 를 두 개 돌리는 순간(샤딩, 또는 사람이
# 다른 창에서 한 번 더 돌리는 것) 서로의 DB 를 지우고 서로의 커넥션을 끊는다 —
# `_drop_and_create` 가 `pg_terminate_backend` 를 쓰기 때문이다. 그때 나오는 오류는
# `AdminShutdown: terminating connection due to administrator command` 이고, 제품과 아무
# 관계가 없는데 시험이 빨간불이 된다(실제로 이 함정에 걸려 본 뒤 넣었다).
#
# 값은 프로세스마다 다르고, 끝나면 지운다.
_RUN_ID = os.getpid()
TEMPLATE_DB = f"clovir_test_template_{_RUN_ID}"
# 기본 계층(트랜잭션 되감기)이 함께 쓰는 DB. 아무것도 커밋되지 않으므로 공유해도 된다.
SHARED_DB = f"clovir_test_shared_{_RUN_ID}"


def _admin_engine():
    """`CREATE DATABASE` 를 내기 위한 엔진. 그 문장은 트랜잭션 안에서 못 돈다.

    `normalize_database_url` 을 지나게 한다 — 안 그러면 SQLAlchemy 가 `postgresql://` 을
    보고 psycopg2 를 찾는다(우리는 psycopg3 만 깐다).
    """
    from app.core.db import normalize_database_url

    return create_engine(
        normalize_database_url(TEST_PG_URL), isolation_level="AUTOCOMMIT", future=True
    )


def _no_server_message(exc: Exception) -> str:
    """붙을 서버가 없을 때 **무엇을 하면 되는지**까지 말한다.

    그냥 두면 `connection refused` 하나만 나오고, 다음 사람은 하네스가 고장 난 줄 안다.
    실제로 필요한 것은 명령 한 줄이다. 주소를 그대로 싣되 **비밀번호는 가린다** —
    실패 로그가 CI 로 흘러가는 자리다.
    """
    safe = TEST_PG_URL
    if "@" in safe and "://" in safe:
        scheme, rest = safe.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        safe = f"{scheme}://{user}:***@{host}"
    using_default = TEST_PG_URL == DEFAULT_TEST_PG_URL
    lines = [
        f"시험용 PostgreSQL 에 붙지 못했습니다: {safe}",
        f"  원인: {type(exc).__name__}: {str(exc).strip().splitlines()[0]}",
        "",
        "  시험은 DB 를 만들고 지울 수 있는 PostgreSQL 16 이 있어야 돕니다"
        "(하네스가 `CREATE DATABASE … TEMPLATE` 을 씁니다).",
    ]
    if using_default:
        lines += [
            "",
            "  기본 주소를 쓰고 있습니다. 로컬 개발용 컨테이너를 이 명령으로 띄우면 됩니다:",
            "",
            "    docker run -d --name clovir-s2-pg -e POSTGRES_USER=cloviradmin \\",
            "      -e POSTGRES_PASSWORD=s2devpw -e POSTGRES_DB=clovir \\",
            "      -p 55433:5432 postgres:16-alpine",
            "",
            "  다른 서버를 쓰려면 `CLOVIR_TEST_PG_URL` 로 주소를 넘기면 됩니다.",
        ]
    else:
        lines += [
            "",
            "  `CLOVIR_TEST_PG_URL` 로 지정한 주소입니다. 그 서버가 떠 있는지,"
            " 그 계정에 DB 생성 권한이 있는지 확인하면 됩니다.",
        ]
    return "\n".join(lines)


def _url_for(dbname: str) -> str:
    base = TEST_PG_URL.rsplit("/", 1)[0]
    return f"{base}/{dbname}"


def _drop_and_create(conn, dbname: str, *, template: str | None = None) -> None:
    # 복제할 때 원본에 다른 연결이 붙어 있으면 PG 가 거절한다. 시험 프로세스가 남긴
    # 연결이 그 원인이라 먼저 끊는다.
    for target in filter(None, (dbname, template)):
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :d AND pid <> pg_backend_pid()"
            ),
            {"d": target},
        )
    conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
    suffix = f' TEMPLATE "{template}"' if template else ""
    conn.execute(text(f'CREATE DATABASE "{dbname}"{suffix}'))


@pytest.fixture(scope="session")
def migrated_db_template() -> str:
    """마이그레이션이 끝난 원본 DB 이름. 세션당 한 번 만든다.

    alembic 을 **인프로세스로** 돌린다. 예전에는 `subprocess` 였고 그 이유가 인코딩
    함정이었는데(한글이 섞인 마이그레이션 설명을 로케일로 디코드하다 리더 스레드가 죽어
    정작 실패 이유를 못 봤다), 인프로세스면 그 함정 자체가 없다.
    """
    from alembic import command
    from alembic.config import Config

    try:
        conn_ctx = _admin_engine().connect()
    except Exception as exc:  # noqa: BLE001 — 원인을 그대로 실어 다시 던진다
        raise pytest.UsageError(_no_server_message(exc)) from exc

    with conn_ctx as conn:
        _drop_and_create(conn, TEMPLATE_DB)

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _url_for(TEMPLATE_DB)
    try:
        command.upgrade(cfg, "head")
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior
    return TEMPLATE_DB


@pytest.fixture(scope="session")
def _shared_engine(migrated_db_template: str):
    """기본 계층이 쓰는 엔진. 스키마는 원본을 복제해 만든다.

    풀을 크게 잡지 않는다 — 기본 계층은 시험당 커넥션 하나만 쓴다.
    """
    with _admin_engine().connect() as conn:
        _drop_and_create(conn, SHARED_DB, template=migrated_db_template)
    from app.core.db import normalize_database_url

    engine = create_engine(normalize_database_url(_url_for(SHARED_DB)))
    yield engine
    engine.dispose()

    # 이 프로세스가 만든 DB 둘을 지운다. 안 지우면 서버에 `clovir_test_*_<pid>` 가 쌓인다.
    # 실패해도 시험 결과를 바꾸지 않는다 — 정리를 못 한 것이 시험 실패는 아니다.
    try:
        with _admin_engine().connect() as conn:
            for name in (SHARED_DB, TEMPLATE_DB):
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :d AND pid <> pg_backend_pid()"
                    ),
                    {"d": name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    except Exception:  # pragma: no cover - 정리 실패는 조용히 넘긴다
        pass


@pytest.fixture()
def _test_database(request, migrated_db_template):
    """이 시험이 어느 DB 에서 도는가. **두 계층의 갈림길이 여기 하나다.**

    기본은 공유 DB 다 — 트랜잭션 하나를 열고 끝에 되감으므로 아무것도 남지 않는다.
    `@pytest.mark.real_db` 를 단 시험은 **자기 DB** 를 받는다: 커넥션이 여럿이어야 하거나
    (동시성), 별도 프로세스를 띄우거나(CLI·워커), DDL 을 돌리는 시험이다.

    왜 나눠야 하는가: 기본 계층에서 커밋한 것은 그 트랜잭션 **안에만** 있다. 다른 커넥션이
    못 보므로, 경합 시험을 기본 계층에 두면 경합 자체가 일어나지 않는데 통과한다 —
    **거짓 초록**이다(D-190).
    """
    if request.node.get_closest_marker("real_db") is None:
        yield ("shared", _url_for(SHARED_DB))
        return

    name = f"clovir_test_{uuid.uuid4().hex[:12]}"
    admin = _admin_engine()
    with admin.connect() as conn:
        _drop_and_create(conn, name, template=migrated_db_template)
    try:
        yield ("dedicated", _url_for(name))
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :d AND pid <> pg_backend_pid()"
                ),
                {"d": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@pytest.fixture()
def db_url(_test_database) -> str:
    """이 시험 전용 DB 의 주소. **`@pytest.mark.real_db` 가 있어야 한다.**

    없으면 공유 DB 주소를 돌려주게 되는데, 그 DB 에 붙은 두 번째 커넥션은 시험이 아직
    커밋 안 한 것을 못 본다 — 시험은 조용히 아무것도 증명하지 못한 채 통과한다. 그래서
    여기서 막는다.
    """
    kind, url = _test_database
    assert kind == "dedicated", (
        "db_url 을 쓰는 시험에는 `@pytest.mark.real_db` 가 필요하다 — 공유 DB 에서는 "
        "두 번째 커넥션이 이 시험의 데이터를 못 본다"
    )
    return url


@pytest.fixture()
def _bound_connection(_test_database, _shared_engine):
    """앱을 띄울 바인드.

    공유 계층에서는 **트랜잭션을 연 커넥션**을 준다 — 끝에 되감는 것이 격리의 전부다.
    전용 계층에서는 **엔진**을 준다: 진짜로 커밋돼야 다른 커넥션·다른 프로세스가 본다.
    """
    from app.core.db import normalize_database_url

    kind, url = _test_database
    if kind == "shared":
        connection = _shared_engine.connect()
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
            connection.close()
        return

    engine = create_engine(normalize_database_url(url))
    try:
        yield engine
    finally:
        engine.dispose()


# 노션 DB id 는 설치처 고유값이라 소스 기본값이 **비어 있다**(app/core/tenant_config.py).
# 테스트 세계는 '설정을 마친 설치'를 흉내 낸다: 비워 두면 티켓·문서 경로가 '설정 안 됨'으로
# 먼저 막혀, 정작 검증하려던 로직에 닿지도 못한 채 초록불이 나온다(가짜 안전감).
# 값 자체는 아무 문자열이어도 되지만 가짜 노션 서버가 URL 로 알아봐야 하므로
# tests/fakes/notion.py 의 DEFAULT_TASKS_DB 와 같은 값을 쓴다.
# 비어 있을 때의 동작은 tests/unit/test_tenant_defaults.py 가 따로 고정한다.
TEST_DOCS_DB = "docs-db-0001"


@pytest.fixture()
def settings(_bound_connection, _test_database, tmp_path: Path) -> Settings:
    from tests.fakes.notion import DEFAULT_TASKS_DB

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    return Settings(
        _env_file=None,
        app_env="test",
        # 앱은 이 주소로 엔진을 만들지 않는다 — `create_app(bind=…)` 가 시험이 준
        # 바인드를 그대로 받는다. 그래도 **맞는 값이어야 한다**: `Settings` 를 읽어
        # 스스로 붙는 경로(CLI·백업·마이그레이션)가 이 문자열을 쓴다.
        database_url=_test_database[1],
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=PROJECT_ROOT / "config",
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
        notion_tasks_database_id=DEFAULT_TASKS_DB,
        notion_documents_database_id=TEST_DOCS_DB,
    )


@pytest.fixture()
def stub_pg_dump(monkeypatch):
    """백업의 **바깥 도구 호출만** 가짜로 바꾼다 — 서비스 계층 계약은 그대로 검사한다.

    `pg_dump`/`pg_restore` 는 PostgreSQL 서버와 함께 깔린다. 개발 머신(Windows)에는 없고
    배포 대상(Ubuntu)에는 있다. 그 바이너리를 **전 스위트의 전제조건으로 만들지 않는다** —
    백업 행의 상태 전이·알림·장부는 도구 없이도 전부 검사할 수 있고, 그것이 이 시험들이
    실제로 보려는 것이다.

    그러면 **진짜 덤프가 되는지는 누가 보는가**:
      * `tests/unit/test_pg_backup.py` — 도구 없이 판정 가능한 것 전부(URL→libpq 변환,
        체크섬, 이유 코드, **도구가 없을 때 조용히 통과하지 않는가**)
      * `docs/platform/EVIDENCE/S2/pg_backup_roundtrip.txt` — 실 PG 16.15 에서 잰 왕복.
        부분 유니크의 `WHERE`·GIN trgm·jsonb·identity 가 복원 뒤에도 살아 있고, 손상된
        아카이브는 `pg_restore --list` 가 거부한다

    즉 가짜로 바꾸는 것은 **도구 실행 한 걸음**뿐이고, 그 걸음의 진짜 동작은 다른 곳에서
    실측으로 고정돼 있다.
    """
    from app.backups import pg_backup, service

    # 아카이브 안에 담긴 것처럼 보이게 하는 표식. 이것이 없으면 «깨진 파일» 로 본다 —
    # 파일이 덮어써졌는지를 도구 없이도 알아볼 수 있게 하는 최소한의 장치다.
    magic = b"PGDMP fake archive"

    def fake_backup(database_url, dest_path, *, bin_dir=None):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(magic)
        return {
            "path": str(dest_path),
            "size_bytes": dest_path.stat().st_size,
            # **진짜 체크섬이다.** 이 부분은 외부 도구가 필요 없고, 재검증이 손상을
            # 잡아내는지는 바로 이 값에 달려 있다 — 가짜로 두면 그 시험이 헛돈다.
            "checksum": pg_backup.sha256_file(dest_path),
        }

    def fake_verify(backup_path, expected_checksum=None, *, bin_dir=None):
        """체크섬은 **진짜로** 보고, `pg_restore --list` 자리만 가짜다."""
        from pathlib import Path as _Path

        path = _Path(backup_path)
        if not path.exists():
            return {"ok": False, "reason": "file_missing"}
        if expected_checksum is not None and pg_backup.sha256_file(path) != expected_checksum:
            return {"ok": False, "reason": "checksum_mismatch"}
        if path.read_bytes()[: len(magic)] != magic:
            return {"ok": False, "reason": "archive_unreadable: fake"}
        return {"ok": True, "reason": None}

    def fake_restore_test(backup_path, *, database_url=None, bin_dir=None):
        structural = fake_verify(backup_path, bin_dir=bin_dir)
        return structural if not structural["ok"] else {"ok": True, "reason": None}

    monkeypatch.setattr(service, "backup_database", fake_backup)
    monkeypatch.setattr(service, "restore_test", fake_restore_test)
    monkeypatch.setattr(service, "verify_backup", fake_verify)
    return fake_backup


@pytest.fixture()
def fake_clock():
    from tests.fakes.clock import FakeClock

    return FakeClock()


@pytest.fixture()
def fake_http():
    from tests.fakes.http import FakeHTTP

    return FakeHTTP()


@pytest.fixture()
def app(settings: Settings, fake_clock, fake_http, _bound_connection):
    return create_app(
        settings,
        clock=fake_clock,
        outbound_transport=fake_http.transport(),
        # 이 시험의 커넥션 위에서 띄운다 — 세션이 SAVEPOINT 로 합류하므로 앱의
        # `commit()` 이 시험 밖으로 새지 않는다(D-190).
        bind=_bound_connection,
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
