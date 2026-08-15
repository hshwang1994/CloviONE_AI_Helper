"""Database engine and session factories.

SQLite runs in WAL mode with busy_timeout and enforced foreign keys
(spec §7.1, §21). All timestamps in the database are naive UTC —
Asia/Seoul is applied only for cron evaluation and display.

**왜 파라미터화했는가 (PLAN Phase 4 — 스케일 심).** 예전에는 PRAGMA 값과 풀 설정이 이 함수
안에 상수로 박혀 있었다. 사람이 1000명 규모로 늘 때 가장 먼저 만지게 되는 손잡이가 바로
이것들인데, 값을 바꾸려면 코드를 고쳐 배포해야 했고 테스트는 다른 값(예: 아주 짧은
busy_timeout)으로 잠금 경합을 재현할 방법이 없었다. 이제 인자로 받되 **기본값은 예전과
정확히 같다** — 아무도 값을 넘기지 않으면 동작이 한 글자도 달라지지 않는다.

기본값을 지금 바꾸지 않는 이유: 이 단계의 목적은 '조절 가능하게 만드는 것'이지 '조절하는 것'이
아니다. 측정 없이 성능 기본값을 바꾸는 것은 되돌리기 어려운 종류의 변경이다.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# 예전에 이 파일에 박혀 있던 값 그대로다. 바꾸려면 EngineOptions 로 넘긴다.
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_JOURNAL_MODE = "WAL"
DEFAULT_SYNCHRONOUS = "NORMAL"


@dataclass(frozen=True)
class EngineOptions:
    """엔진 손잡이 한 묶음. 전부 기본값이 예전 하드코딩 값과 같다."""

    # SQLite writer 는 하나다. 다른 커넥션이 쓰는 중이면 이 시간만큼 기다린 뒤
    # 'database is locked' 를 낸다. 짧게 주면 잠금 경합을 테스트에서 재현할 수 있다.
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    journal_mode: str = DEFAULT_JOURNAL_MODE
    synchronous: str = DEFAULT_SYNCHRONOUS
    # 외래키 강제. **끄는 것은 특수 상황(스키마 정비) 전용**이다 — 앱 런타임에서 끄면
    # 참조 무결성이 조용히 사라진다.
    foreign_keys: bool = True
    # 풀 크기. SQLite 에서는 None(= SQLAlchemy 기본)이 맞다. Postgres 로 옮길 때
    # 이 두 값이 첫 손잡이가 된다.
    pool_size: int | None = None
    max_overflow: int | None = None
    pool_pre_ping: bool = True

    def pragmas(self) -> tuple[tuple[str, str], ...]:
        """연결마다 실행할 PRAGMA. 순서가 의미 있다(journal_mode 를 먼저 잡는다)."""
        return (
            ("journal_mode", self.journal_mode),
            ("busy_timeout", str(self.busy_timeout_ms)),
            ("foreign_keys", "ON" if self.foreign_keys else "OFF"),
            ("synchronous", self.synchronous),
        )


DEFAULT_ENGINE_OPTIONS = EngineOptions()


def make_engine(database_url: str, options: EngineOptions | None = None) -> Engine:
    opts = options or DEFAULT_ENGINE_OPTIONS
    connect_args: dict = {}
    engine_kwargs: dict = {"pool_pre_ping": opts.pool_pre_ping}

    if opts.pool_size is not None:
        engine_kwargs["pool_size"] = opts.pool_size
    if opts.max_overflow is not None:
        engine_kwargs["max_overflow"] = opts.max_overflow

    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # The app serves sync handlers from a threadpool; SQLite connections
        # are pooled and may cross threads. busy_timeout serializes writers.
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    if is_sqlite:
        pragmas = opts.pragmas()

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            # pysqlite 의 레거시 암묵적 트랜잭션 관리를 끈다(SQLAlchemy 공식 권고,
            # "Serializable isolation / Savepoints / Transactional DDL" — SQLite 다이얼렉트
            # 문서). 끄지 않으면 SAVEPOINT(= db.begin_nested(), app/core/versioning.py 등
            # 5곳 + 이 자체가 첫 문장일 때)가 진짜 BEGIN 없이 나가고, pysqlite 는 INSERT 를
            # 보고서야 암묵적 BEGIN 을 시도하는데 SQLite 는 이미 그 SAVEPOINT 가 스스로 연
            # 트랜잭션 안이라 pysqlite 의 BEGIN 이 생략된다 — 그 결과 RELEASE SAVEPOINT 가
            # **커밋과 같아진다.** 실측: 커밋 안 한 SAVEPOINT 행이 다른 커넥션에 즉시
            # 보이고, 그 뒤 `session.rollback()` 을 불러도 그 행이 사라지지 않는다(둘 다
            # `tests/integration/test_zz_scratch_isolation_probe*.py` 로 직접 재현·확인).
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            for name, value in pragmas:
                # PRAGMA 는 파라미터 바인딩을 받지 않는다. 값은 전부 이 모듈이 만든
                # 리터럴이고 사용자 입력이 닿지 않으므로 주입 경로가 없다.
                cursor.execute(f"PRAGMA {name}={value}")
            cursor.close()

        # 정확한 격리가 적용되면 `db.begin_nested()`(SAVEPOINT) 기반 재시도 코드
        # (아래 IS_WRITE_CONFLICT_MESSAGES 사용처 13곳)가 예전에 `IntegrityError`
        # 로만 보던 경합을 이제 `OperationalError`("database is locked")로도 본다 —
        # 세션이 앞서 읽은 스냅샷이 그 사이 다른 세션이 커밋한 값보다 낡으면, 같은
        # 세션의 나중 쓰기는 UNIQUE 제약까지 가지도 못하고 SQLite 자체가 그 쓰기를
        # 거부한다(WAL 스냅샷 격리, `busy_timeout` 으로도 못 구한다 — 그건 "지금 누가
        # 잠갔다"가 아니라 "내가 본 상태가 이미 낡았다"이기 때문이다). 실측:
        # `tests/integration/test_quota_toctou.py`, 여러 `*_race.py` 시험이 격리
        # 수정 직후 이 정확한 이유로 빨간불이 됐다가, 재시도 코드가 이 메시지를
        # 함께 잡도록 고치자 다시 초록불이 됐다.

        @event.listens_for(engine, "begin")
        def _emit_explicit_begin(conn) -> None:
            # 위에서 pysqlite 의 암묵적 BEGIN 을 껐으니, SQLAlchemy 가 트랜잭션을 시작할
            # 때마다 이제는 우리가 직접 BEGIN 을 내야 한다(같은 공식 권고).
            #
            # DEFERRED(평범한 BEGIN, 인자 없음)를 쓴다 — IMMEDIATE 를 먼저 시도했다가
            # 실측으로 되돌렸다. IMMEDIATE 는 **읽기 전용** 세션까지 트랜잭션 시작 순간
            # 전역 쓰기 예약 하나를 잡는다 — 이 저장소의 테스트가 흔히 쓰는 "세션 하나를
            # 테스트 내내 열어 두고 그 사이 client/worker 가 별도 세션으로 쓴다" 패턴과
            # 정면으로 부딪혀서, DEFERRED 에서 23건이던 회귀가 IMMEDIATE 에서 84건으로
            # **늘었다**(전체 회귀 실측, 2026-08-11). DEFERRED 로는 대신 아래 두 가지를
            # 함께 갖춰야 한다:
            #   1. `db.begin_nested()`(SAVEPOINT) 기반 재시도 코드는 `IntegrityError`
            #      (UNIQUE 위반) 뿐 아니라 `OperationalError`("database is locked")도
            #      같은 경합의 다른 얼굴로 잡아야 한다 — 세션이 먼저 읽은 스냅샷이 그 사이
            #      다른 세션의 커밋보다 낡으면, 쓰기 자체가 제약 검사까지 못 가고 여기서
            #      먼저 거부되기 때문이다(`busy_timeout` 으로 못 구한다 — "지금 누가
            #      잠갔다"가 아니라 "내가 본 상태가 이미 낡았다"라서). 아래
            #      `is_write_conflict()` 가 그 판정이고, 13개 호출부가 이미 이 패턴을 쓴다.
            #   2. 세션을 오래 들고 있다가(먼저 읽고) 한참 뒤에 그 세션으로 다시 쓰려는
            #      코드(주로 테스트 픽스처)는 그 사이 `db.commit()`(또는 `rollback()`/
            #      `expire_all()`)으로 스냅샷을 새로 떠야 한다 — 안 그러면 위 1번과 같은
            #      이유로 자기 자신의 쓰기가 거부된다.
            conn.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# SQLite가 쓰기 충돌을 알릴 때 쓰는 문구. 정확한 BEGIN(위 make_engine)이 있어야 이 경합이
# 실제로 여기까지 온다 — 그 전에는 같은 경합이 대부분 조용히 "먼저 쓴 쪽이 이겼다"로
# 뭉개지거나 IntegrityError 하나로만 나타났다. `sqlite_errorcode`(Python 3.11+)가 있으면
# 그걸 우선 쓰고, 없으면(오래된 드라이버·테스트 목) 메시지 문자열로 판정한다.
_SQLITE_WRITE_CONFLICT_MESSAGES = ("database is locked", "database table is locked")


def is_write_conflict(exc: BaseException) -> bool:
    """`db.begin_nested()`(SAVEPOINT) 재시도 코드가 "누군가 먼저 썼다"로 해석해야 하는
    예외인가 — `IntegrityError`(UNIQUE 위반)는 항상 그렇다. 정확한 트랜잭션 격리
    아래서는 같은 경합이 `OperationalError`("database is locked")로도 온다 — 이 세션이
    먼저 읽은 스냅샷이 그 사이 다른 세션의 커밋보다 낡으면, 쓰기 자체가 제약 검사까지
    못 가고 거부되기 때문이다(`make_engine`의 `"begin"` 이벤트 주석 참고). 호출부는
    `except (IntegrityError, OperationalError) as exc: if not is_write_conflict(exc): raise`
    처럼 쓴다 — 관계없는 `OperationalError`(디스크 오류 등)까지 조용히 삼키지 않는다.
    """
    from sqlalchemy.exc import IntegrityError, OperationalError

    if isinstance(exc, IntegrityError):
        return True
    if not isinstance(exc, OperationalError):
        return False
    orig = getattr(exc, "orig", exc)
    code = getattr(orig, "sqlite_errorcode", None)
    if code is not None:
        import sqlite3

        # `sqlite_errorcode`는 SQLite의 "확장 결과 코드"다(예: 517 =
        # SQLITE_BUSY_SNAPSHOT — 스냅샷이 낡아 쓰기가 거부된 실제 사례에서 관측·확인함,
        # 하위 바이트만 SQLITE_BUSY=5와 같다). 하위 8비트로 낮춰 "확장" 변형(BUSY_RECOVERY·
        # BUSY_SNAPSHOT·BUSY_TIMEOUT·LOCKED_SHAREDCACHE 등)을 전부 같은 판정으로 묶는다.
        return (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    message = str(orig).lower()
    return any(m in message for m in _SQLITE_WRITE_CONFLICT_MESSAGES)


# PA-RC-0008: `is_write_conflict()` 재시도 관용(13곳 이상)이 각자 다른 예산/지터로
# 손으로 따로 쓰여 있었다 — 가장 약한 곳(`app/prompts/service.py::new_version_from`,
# 예산 5·지터 없음)이 8-way 경합에서 40% 확률로 재시도를 소진해 처리 안 된
# `OperationalError`를 그대로 500으로 흘렸다. `app/auth/router.py`의 로그인 재시도가
# **실측으로 검증된** 유일한 값이다(10-way 동시 로그인 스트레스 시험 — 지터 없이 10회
# 재시도로도 5번 중 1번은 여전히 실패했다). 그 값을 여기 한 곳으로 승격해 새 호출부의
# 기본값으로 삼는다 — 다르게 써야 하면(예: `approvals`/`team_chat`은 관측된 경합이 더
# 잦아 12) 그 이유를 호출부 주석에 남긴다(§13 완료 기준이 요구하는 "왜 다른가"다).
#
# 승격하지 않는 것: 재시도 **루프 구조 자체**(SAVEPOINT 후 실패 시 `db.commit()`으로
# 스냅샷을 새로 뜨는지, `db.rollback()`+재조회인지, `db.refresh()`로 특정 컬럼만
# 새로 읽는지)는 호출부마다 무엇을 다시 계산해야 하는지가 달라 하나로 묶을 수 없다 —
# 묶으려 하면 SAVEPOINT/outer transaction 경계(§3-10)를 억지로 흐리게 된다. 여기서
# 공용화하는 것은 "몇 번, 얼마나 쉬고" 뿐이다. `app/core/sessions.py::_commit_best_effort`
# (예산 2, 실패해도 조용히 넘어감)는 순수 부수효과 커밋이라 의도적으로 이 기본값을
# 안 쓴다 — Handoff 문서 자체가 "일괄 치환 전에 개별 판단할 것"이라고 못박았다.
DEFAULT_WRITE_CONFLICT_RETRIES = 10


def write_conflict_backoff(attempt: int) -> float:
    """`attempt`번째 재시도 전에 잘 시간(초). `auth/router.py`가 실측으로 정한 지터
    공식 그대로다 — 여러 스레드가 지터 없이 즉시 재시도만 하면 서로 계속 다시 부딪힌다.
    """
    return random.uniform(0.01, 0.05) * (attempt + 1)


# PA-RC-0008 regression_risk: 예산을 늘리고 sleep을 넣으면 경합 시 응답 지연이 늘어난다
# — 상한을 명시적으로 계산해 둔다. 예산 N이면 마지막 시도 전까지 (N-1)번 쉬고, 매번 최악
# `write_conflict_backoff`의 상한 `0.05*(attempt+1)`를 쓴다고 가정하면 최대 누적 대기는
# `0.05 * N*(N-1)/2` 초다. 기본값 N=10 → 최대 2.25초. `approvals`/`team_chat`처럼 일부러
# 12를 쓰는 곳은 최대 3.3초. 둘 다 `deploy/nginx/*.conf`의 `proxy_read_timeout 180s`에
# 비하면 무시할 수준(<2%)이라 별도 타임아웃 조정은 필요 없다.


# SQLite caps host variables (default ~32766, older builds 999); an `id IN (...)`/
# `NOT IN (...)` clause inlines one variable per id, so a large enough id set blows
# the limit and raises an unhandled OperationalError. app/core/retention.py had its
# own private copy of this same chunking helper before other call sites needed it
# too (UA-24/UB-28) — promoted here so nobody has to re-invent it a third time.
ID_BATCH_SIZE = 500


def batched(items: Sequence[str], size: int = ID_BATCH_SIZE) -> Iterator[Sequence[str]]:
    """Yield ``items`` in chunks of at most ``size`` — use before any SQL
    ``IN``/``NOT IN`` clause built from a caller-controlled id list."""
    for start in range(0, len(items), size):
        yield items[start : start + size]
