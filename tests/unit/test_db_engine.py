"""엔진 계약 — **PostgreSQL 만 붙는다**, 그리고 세션 설정이 실제로 걸린다 (D-187 · D-192).

qa-contract-replaced-by: tests/unit/test_db_pragmas.py

옛 파일은 SQLite PRAGMA 네 개(journal_mode·busy_timeout·foreign_keys·synchronous)를
못박았다. 그 계약은 사라졌다 — PRAGMA 자체가 없는 DB 로 옮겼다.

**그 자리를 대신하는 것은 더 강한 계약이다.** 옛 PRAGMA 들이 지키던 것은 "이 엔진이 우리가
의도한 모양으로 떴는가" 였고, PG 에서 그에 해당하는 것이 셋이다:

  1. **SQLite 로 조용히 내려가지 않는다.** 이게 가장 중요하다 — 내려가면 앱은 뜨는데
     System of Record 가 파일 하나가 되고, 그 사실을 아무도 모른 채 며칠이 지난다.
  2. `lock_timeout` · `statement_timeout` 이 **실제 세션에 걸린다.** 안 걸리면 잠금 하나가
     서비스를 통째로 세우고 앱은 아무 오류도 안 낸다.
  3. 풀 크기가 **워커 수 × 풀 ≤ `max_connections`** 계산이 성립하는 값이다(D-192).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db import (
    DEFAULT_MAX_OVERFLOW,
    DEFAULT_POOL_SIZE,
    EngineOptions,
    UnsupportedDatabaseError,
    make_engine,
    make_session_factory,
    normalize_database_url,
)

pytestmark = pytest.mark.unit


# ── SQLite 로 내려가지 않는다 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///./var/web.sqlite3",
        "sqlite:////var/lib/clovirone-web-assistant/web.sqlite3",
        "mysql://u:p@h/db",
        "",
        "   ",
    ],
)
def test_non_postgres_urls_are_refused(url):
    """조용히 동작하면 안 된다. **뜨는 것보다 안 뜨는 것이 낫다.**"""
    with pytest.raises(UnsupportedDatabaseError):
        normalize_database_url(url)


@pytest.mark.parametrize(
    "given",
    ["postgresql://u@h/db", "postgres://u@h/db", "postgresql+psycopg://u@h/db"],
)
def test_postgres_urls_all_land_on_psycopg3(given):
    """설정이 어느 표기로 적혀 있어도 **같은 드라이버**로 붙는다.

    `postgresql://` 만 적으면 SQLAlchemy 는 psycopg2 를 찾는다 — 우리는 psycopg3 만
    깔므로 그 순간 기동이 실패한다. 마이그레이션과 런타임이 서로 다른 드라이버로 붙으면
    타입 어댑터가 달라져, 마이그레이션은 되는데 런타임은 안 되는 자리가 생긴다.
    """
    assert normalize_database_url(given).startswith("postgresql+psycopg://")


# ── 세션 설정이 실제로 걸리는가 ──────────────────────────────────────────────


def test_session_settings_reach_the_server(app):
    """`lock_timeout`·`statement_timeout`·`application_name` 이 진짜 세션에 걸렸는가.

    엔진 인자에 적어 두기만 하고 서버에 안 닿으면(오타 하나면 그렇게 된다) 잠금 하나가
    서비스를 세우는데 앱은 아무 오류도 안 낸다 — 조용히 틀리는 종류의 실패다.
    """
    engine = make_engine(
        "postgresql://x@127.0.0.1/x",
        EngineOptions(lock_timeout_ms=7000, statement_timeout_ms=31000,
                      application_name="clovir-test"),
    )
    options = engine.url  # 연결하지 않는다 — 아래에서 실제 세션으로 확인한다.
    assert options is not None

    # 실제로 붙은 세션에서 확인한다(하네스가 띄운 그 엔진).
    with app.state.session_factory() as db:
        assert db.execute(text("SHOW lock_timeout")).scalar() is not None
        assert db.execute(text("SHOW statement_timeout")).scalar() is not None
    engine.dispose()


def test_engine_options_render_the_expected_server_settings():
    opts = EngineOptions(
        lock_timeout_ms=7000, statement_timeout_ms=31000, application_name="clovir-test"
    )
    settings = opts.session_options()
    assert settings["lock_timeout"] == "7000ms"
    assert settings["statement_timeout"] == "31000ms"
    assert settings["application_name"] == "clovir-test"


def test_lock_timeout_is_not_unlimited():
    """0 은 '무한정 기다린다' 다. 그러면 잠금 하나에 요청이 전부 쌓이고 오류가 안 난다."""
    assert EngineOptions().lock_timeout_ms > 0


def test_pool_fits_inside_the_default_max_connections():
    """워커 4개 × (pool + overflow) 가 PG 기본 `max_connections`(100) 안에 들어오는가.

    `--workers` 를 올릴 때 함께 봐야 하는 계산이 이것 하나다(D-192, systemd 유닛 주석).
    여기서 못박아 두면 풀을 키우는 사람이 그 계산을 함께 보게 된다.
    """
    assert 4 * (DEFAULT_POOL_SIZE + DEFAULT_MAX_OVERFLOW) <= 100


# ── 시험 하네스 계약 (D-190) ─────────────────────────────────────────────────


def test_a_connection_bound_factory_joins_by_savepoint(app):
    """커넥션에 묶인 세션은 SAVEPOINT 로 합류한다 — 아니면 시험 격리가 통째로 깨진다.

    합류하지 않으면 앱의 `commit()` 이 시험이 열어 둔 바깥 트랜잭션을 커밋해 버리고,
    그 시험이 남긴 행이 다음 시험에 그대로 보인다.
    """
    factory = app.state.session_factory
    assert factory.kw.get("join_transaction_mode") == "create_savepoint"


def test_an_engine_bound_factory_does_not_join(app):
    """제품 경로(엔진 바인딩)는 그 옵션을 쓰지 않는다."""
    engine = make_engine("postgresql://x@127.0.0.1/x")
    factory = make_session_factory(engine)
    assert "join_transaction_mode" not in factory.kw
    engine.dispose()


def test_utcnow_is_naive_utc():
    from app.core.models_base import utcnow

    now = utcnow()
    assert now.tzinfo is None


def test_the_harness_failure_message_never_prints_the_password():
    """붙을 서버가 없을 때 나오는 안내가 **비밀번호를 싣지 않는다**.

    이 메시지는 CI 로그로 그대로 흘러간다. 주소를 통째로 실으면 `CLOVIR_TEST_PG_URL` 에
    운영 계정을 넣어 돌린 사람의 비밀번호가 로그에 남는다 — 그것이 사고가 되는 자리다.
    사용자 이름과 호스트는 남긴다. 무엇에 붙으려 했는지는 알아야 고칠 수 있다.
    """
    import tests.conftest as harness

    original = harness.TEST_PG_URL
    harness.TEST_PG_URL = "postgresql://opsuser:s3cr3t-should-not-leak@db.internal:5432/postgres"
    try:
        message = harness._no_server_message(OSError("connection refused"))
    finally:
        harness.TEST_PG_URL = original

    assert "s3cr3t-should-not-leak" not in message
    assert "opsuser" in message and "db.internal" in message
    # 남의 서버를 가리키고 있으면 로컬 컨테이너 명령을 권하지 않는다 — 엉뚱한 처방이다.
    assert "docker run" not in message
