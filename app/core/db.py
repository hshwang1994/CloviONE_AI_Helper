"""Database engine and session factories — **PostgreSQL** (D-187).

System of Record 는 PostgreSQL 16 이다. SQLite 전용 장치(PRAGMA·`check_same_thread`·
명시적 `BEGIN`·`isolation_level=None`)는 전부 걷어냈다 — psycopg 가 트랜잭션을 관리하고
격리는 서버가 정한다.

모든 timestamp 는 naive UTC 로 저장한다(§7.1 계약 유지). Asia/Seoul 은 cron 평가와
표시에만 쓴다.

**손잡이는 인자로 받는다.** 예전에 이 함수 안에 상수로 박혀 있던 값들이다. 사람이 1000명
규모로 늘 때 가장 먼저 만지는 것이 풀 크기라, 값을 바꾸려고 코드를 고쳐 배포하지 않게
`EngineOptions` 로 뺀다.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

# 풀 기본값. SQLite 시절에는 None(SQLAlchemy 기본)이 맞았지만 PG 에서는 실제 값을 정해야
# 한다 — `--workers` 를 올리면(D-192) 프로세스마다 이 풀이 하나씩 생기므로, 워커 수 ×
# (pool_size + max_overflow) 가 서버의 `max_connections` 안에 들어와야 한다.
#
# 기본 5+10 은 web 프로세스 하나가 최대 15 커넥션을 쓴다는 뜻이다. 워커 4개로 올려도
# 60 이라 PG 기본 `max_connections=100` 안에 들어온다. 그 이상으로 올릴 때 함께 올려야
# 하는 값이 무엇인지 설치 문서가 아니라 여기에 적어 둔다.
DEFAULT_POOL_SIZE = 5
DEFAULT_MAX_OVERFLOW = 10
# 커넥션을 얼마나 오래 재사용할지. PG 는 유휴 커넥션을 끊지 않지만 그 앞에 놓이는
# 것들(방화벽·프록시)은 끊는다. 30분마다 갈아 끼우면 "어제부터 죽어 있던 커넥션"을
# 오늘 처음 만나는 일이 없다.
DEFAULT_POOL_RECYCLE_SECONDS = 1800


@dataclass(frozen=True)
class EngineOptions:
    """엔진 손잡이 한 묶음."""

    pool_size: int = DEFAULT_POOL_SIZE
    max_overflow: int = DEFAULT_MAX_OVERFLOW
    pool_recycle_seconds: int = DEFAULT_POOL_RECYCLE_SECONDS
    pool_pre_ping: bool = True
    # 서버가 이 세션을 무엇으로 부를지. `pg_stat_activity` 에서 web/worker/scheduler 를
    # 구분하는 유일한 수단이라, 잠금 경합을 조사할 때 이 값이 없으면 어느 프로세스가
    # 무엇을 들고 있는지 알 수 없다.
    application_name: str = "clovirassist"
    # 잠금을 기다리는 상한(ms). 0 은 '무한정 기다린다'다. 무한정은 위험하다 — 한 트랜잭션이
    # 잠금을 놓지 않으면 그 뒤로 오는 요청이 전부 그 자리에 쌓이고, 앱은 아무 오류도 안 낸다.
    # 상한을 걸면 `55P03 lock_not_available` 로 나오고 그것은 재시도 대상이다
    # (`is_serialization_conflict`).
    lock_timeout_ms: int = 10_000
    # 한 문장이 돌 수 있는 상한(ms). 폭주한 질의 하나가 커넥션을 영원히 붙들지 않게 한다.
    # nginx 의 `proxy_read_timeout 180s` 보다 짧게 잡아, 서버가 먼저 포기하고 이유가
    # 남게 한다.
    statement_timeout_ms: int = 120_000

    def session_options(self) -> dict[str, str]:
        """연결마다 서버에 걸 세션 설정. psycopg 의 `options` 로 한 번에 넘긴다."""
        return {
            "application_name": self.application_name,
            "lock_timeout": f"{self.lock_timeout_ms}ms",
            "statement_timeout": f"{self.statement_timeout_ms}ms",
        }


DEFAULT_ENGINE_OPTIONS = EngineOptions()

# psycopg3 다이얼렉트. `postgresql://` 로만 적으면 SQLAlchemy 가 psycopg2 를 찾는다 —
# 우리는 psycopg3 만 설치하므로 URL 을 정규화해 준다. 설정 파일이 어느 쪽으로 적혀 있어도
# 같은 드라이버로 붙게 하는 것이 목적이다.
_PG_SCHEME_PREFIXES = ("postgresql://", "postgres://")
PG_DRIVER_SCHEME = "postgresql+psycopg://"


class UnsupportedDatabaseError(RuntimeError):
    """PostgreSQL 이 아닌 `database_url` 이다.

    조용히 SQLite 로 떨어지지 않게 한다 — 떨어지면 앱은 뜨지만 System of Record 가
    파일 하나가 되고, 그 사실을 아무도 모른 채 며칠이 지난다(D-187).
    """


def normalize_database_url(database_url: str) -> str:
    """`postgresql://`·`postgres://` 를 psycopg3 다이얼렉트로 맞춘다.

    PostgreSQL 이 아니면 여기서 막는다. SQLite URL 을 넘기면 예전 코드는 그냥 동작했고,
    그래서 "설정을 안 넣었다"와 "SQLite 로 돌고 있다"가 구별되지 않았다.
    """
    url = (database_url or "").strip()
    if not url:
        raise UnsupportedDatabaseError(
            "database_url 이 비어 있습니다. PostgreSQL 주소를 설정해 주세요."
        )
    for prefix in _PG_SCHEME_PREFIXES:
        if url.startswith(prefix):
            return PG_DRIVER_SCHEME + url[len(prefix) :]
    if url.startswith(PG_DRIVER_SCHEME):
        return url
    scheme = url.split("://", 1)[0]
    raise UnsupportedDatabaseError(
        f"PostgreSQL 주소만 쓸 수 있습니다(받은 스킴: {scheme!r}). "
        "이 제품의 System of Record 는 PostgreSQL 입니다."
    )


def make_engine(database_url: str, options: EngineOptions | None = None) -> Engine:
    opts = options or DEFAULT_ENGINE_OPTIONS
    url = normalize_database_url(database_url)

    # psycopg 는 `-c key=value` 를 이어 붙인 문자열로 세션 설정을 받는다. 값에 공백이
    # 없으므로(전부 이 모듈이 만든 리터럴) 따옴표가 필요 없다.
    server_settings = " ".join(
        f"-c {key}={value}" for key, value in opts.session_options().items()
    )

    return create_engine(
        url,
        connect_args={"options": server_settings},
        pool_size=opts.pool_size,
        max_overflow=opts.max_overflow,
        pool_recycle=opts.pool_recycle_seconds,
        pool_pre_ping=opts.pool_pre_ping,
    )


def make_session_factory(bind) -> sessionmaker[Session]:
    """세션 팩토리. `bind` 는 보통 `Engine` 이지만 **살아 있는 `Connection`** 일 수도 있다.

    커넥션에 직접 묶는 경우 `join_transaction_mode="create_savepoint"` 를 켠다. 그 커넥션은
    이미 트랜잭션을 열어 둔 상태이고, 세션이 그 위에서 `commit()` 을 부르면 **그 바깥
    트랜잭션을 커밋해 버린다** — SAVEPOINT 로 합류시키면 세션의 커밋/롤백이 자기 구간에만
    작용한다.

    시험 하네스가 이 모양을 쓴다(D-190): 시험마다 트랜잭션 하나를 열고, 앱을 그 커넥션
    위에서 띄우고, 끝나면 통째로 되감는다. 제품 경로는 `Engine` 을 넘기므로 아무것도
    달라지지 않는다.
    """
    kwargs: dict = {"bind": bind, "autoflush": False, "expire_on_commit": False}
    if isinstance(bind, Connection):
        kwargs["join_transaction_mode"] = "create_savepoint"
    return sessionmaker(**kwargs)


# ── 충돌 분류 (D-191) ─────────────────────────────────────────────────────────
#
# 예전 `is_write_conflict()` 는 **모든 `IntegrityError` 를 재시도 대상**으로 봤다.
# SQLite 에서는 대체로 맞았다 — `database is locked` 가 진짜 일시적 상태였기 때문이다.
#
# PG 에서는 다르다. 그대로 두면 **진짜 제약 위반(FK 위반·NOT NULL·CHECK)이 10회 재시도
# 후 503 「다시 시도」로 나간다.** 데이터 버그가 일시적 오류로 위장하고 로그에는 재시도만
# 남는다. 조용히 틀리는 종류의 실패다.
#
# 그래서 둘로 쪼갠다. 이름이 곧 "호출부가 무엇을 뜻했는가"다:
#   * `is_serialization_conflict` — "지금은 안 됐다, 다시 하면 된다" → 트랜잭션 재시도
#   * `is_unique_violation`       — "이미 있다"                     → 호출부가 국소 처리
# 둘 중 어디에도 안 걸리는 예외는 **그대로 올라간다.** 그것이 이 분류의 요점이다.

# 재시도해야 하는 SQLSTATE.
#   40001 serialization_failure  — 직렬화 실패
#   40P01 deadlock_detected      — 교착. PG 가 한쪽을 죽인다
#   55P03 lock_not_available     — `lock_timeout` 초과, `NOWAIT` 거절
SERIALIZATION_SQLSTATES = frozenset({"40001", "40P01", "55P03"})

# "이미 있다".
UNIQUE_VIOLATION_SQLSTATE = "23505"

# 재시도하면 **안 되는** 것들. 목록으로 두는 이유는 진단 때문이다 — 이 중 하나가 재시도
# 루프 안에서 나왔다면 그것은 데이터 버그이지 경합이 아니다.
#   23503 foreign_key_violation · 23502 not_null_violation · 23514 check_violation
#   23P01 exclusion_violation
CONSTRAINT_VIOLATION_SQLSTATES = frozenset({"23503", "23502", "23514", "23P01"})


def sqlstate_of(exc: BaseException) -> str | None:
    """이 예외가 들고 있는 PostgreSQL SQLSTATE. 없으면 None.

    psycopg3 는 `exc.orig.sqlstate` 에 담는다. SQLAlchemy 가 감싸면 `orig` 를 한 번
    벗겨야 한다. 테스트 목이나 다른 드라이버가 `pgcode` 로 주는 경우도 함께 본다.
    """
    orig = getattr(exc, "orig", None) or exc
    for attr in ("sqlstate", "pgcode"):
        code = getattr(orig, attr, None)
        if code:
            return str(code)
    diag = getattr(orig, "diag", None)
    code = getattr(diag, "sqlstate", None)
    return str(code) if code else None


def is_serialization_conflict(exc: BaseException) -> bool:
    """**재시도해야 하는** 경합인가 — 직렬화 실패·교착·잠금 대기 초과.

    호출부 관용구:

        except (OperationalError, DBAPIError) as exc:
            if not is_serialization_conflict(exc) or attempt == budget - 1:
                raise
            db.rollback()
            time.sleep(write_conflict_backoff(attempt))

    `IntegrityError` 는 여기 해당하지 않는다 — 제약 위반은 다시 해도 같은 결과다.
    """
    return sqlstate_of(exc) in SERIALIZATION_SQLSTATES


def is_unique_violation(exc: BaseException, *, constraint: str | None = None) -> bool:
    """**"이미 있다"** 인가 — 유니크(또는 PK) 제약 위반.

    `constraint` 를 주면 그 이름의 제약일 때만 참이다. 이름을 대는 쪽이 훨씬 정확하다:
    한 테이블에 유니크가 둘 이상이면 "내가 예상한 그 경합"과 "전혀 다른 열의 충돌"이
    구별되지 않는데, 후자를 삼키면 그 버그는 영영 안 보인다.

    이름 비교는 부분 일치다 — PG 가 돌려주는 이름이 인덱스 이름(`uq_...`)이고 호출부가
    아는 이름과 같지만, 스키마 접두가 붙는 경우를 위해 느슨하게 본다.
    """
    if sqlstate_of(exc) != UNIQUE_VIOLATION_SQLSTATE:
        return False
    if constraint is None:
        return True
    orig = getattr(exc, "orig", None) or exc
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) or ""
    if name:
        return constraint in str(name)
    # 진단 필드가 없는 드라이버/목이면 메시지로 내려간다.
    return constraint in str(orig)


def is_insert_race(exc: BaseException, *, constraint: str | None = None) -> bool:
    """**"넣어 보고 지면 남의 행을 읽는다"** 관용구가 삼켜도 되는 예외인가.

    이 관용구(`db.begin_nested()` + INSERT, 실패하면 승자 행 재조회)는 두 얼굴을 만난다:
    보통은 유니크 위반이고, 잠금이 얽히면 직렬화 실패로도 온다. 둘 다 답은 같다 —
    "남이 먼저 넣었으니 그 행을 읽는다".

    **FK 위반·NOT NULL·CHECK 는 여기 안 들어온다.** 예전 `is_write_conflict()` 가
    모든 `IntegrityError` 를 참으로 봐서 그것들까지 삼켰고, 그래서 데이터 버그가
    "경합이 잦다"로 보였다(D-191).
    """
    return is_unique_violation(exc, constraint=constraint) or is_serialization_conflict(exc)


# PA-RC-0008: 재시도 관용구가 각자 다른 예산/지터로 손으로 따로 쓰여 있었다 — 가장 약한
# 곳(`app/prompts/service.py::new_version_from`, 예산 5·지터 없음)이 8-way 경합에서 40%
# 확률로 재시도를 소진해 처리 안 된 오류를 그대로 500으로 흘렸다. `app/auth/router.py` 의
# 로그인 재시도가 **실측으로 검증된** 유일한 값이다(10-way 동시 로그인 스트레스 시험 —
# 지터 없이 10회 재시도로도 5번 중 1번은 여전히 실패했다). 그 값을 여기 한 곳으로 승격해
# 새 호출부의 기본값으로 삼는다 — 다르게 써야 하면(예: `approvals`/`team_chat` 은 관측된
# 경합이 더 잦아 12) 그 이유를 호출부 주석에 남긴다.
#
# 승격하지 않는 것: 재시도 **루프 구조 자체**(SAVEPOINT 후 실패 시 `db.commit()` 으로
# 스냅샷을 새로 뜨는지, `db.rollback()`+재조회인지, `db.refresh()` 로 특정 컬럼만 새로
# 읽는지)는 호출부마다 무엇을 다시 계산해야 하는지가 달라 하나로 묶을 수 없다.
# `app/core/sessions.py::_commit_best_effort`(예산 2, 실패해도 조용히 넘어감)는 순수
# 부수효과 커밋이라 의도적으로 이 기본값을 안 쓴다.
DEFAULT_WRITE_CONFLICT_RETRIES = 10


def write_conflict_backoff(attempt: int) -> float:
    """`attempt`번째 재시도 전에 잘 시간(초). `auth/router.py` 가 실측으로 정한 지터
    공식 그대로다 — 여러 스레드가 지터 없이 즉시 재시도만 하면 서로 계속 다시 부딪힌다.
    """
    return random.uniform(0.01, 0.05) * (attempt + 1)


# PA-RC-0008 regression_risk: 예산을 늘리고 sleep 을 넣으면 경합 시 응답 지연이 늘어난다
# — 상한을 명시적으로 계산해 둔다. 예산 N이면 마지막 시도 전까지 (N-1)번 쉬고, 매번 최악
# `write_conflict_backoff` 의 상한 `0.05*(attempt+1)` 를 쓴다고 가정하면 최대 누적 대기는
# `0.05 * N*(N-1)/2` 초다. 기본값 N=10 → 최대 2.25초. `approvals`/`team_chat` 처럼 일부러
# 12를 쓰는 곳은 최대 3.3초. 둘 다 `deploy/nginx/*.conf` 의 `proxy_read_timeout 180s` 에
# 비하면 무시할 수준(<2%)이라 별도 타임아웃 조정은 필요 없다.


# PostgreSQL 은 한 문장에 바인딩할 수 있는 파라미터를 **65535개**로 제한한다(프로토콜의
# int16 필드). `id IN (...)` 은 id 하나마다 파라미터 하나를 쓰므로, 충분히 큰 id 집합은
# 그 상한을 넘겨 처리되지 않은 오류가 된다. SQLite 시절 상한(기본 32766, 옛 빌드 999)보다
# 넉넉해졌지만 상한 자체는 그대로 있다.
#
# 500 을 유지하는 이유는 상한이 아니라 **계획(plan) 품질**이다 — `IN` 목록이 길어지면
# PG 가 인덱스 스캔 대신 순차 스캔을 고르는 지점이 오고, 그 전환은 상한보다 훨씬 일찍
# 온다. app/core/retention.py 가 같은 헬퍼를 따로 갖고 있었고(UA-24/UB-28) 다른 호출부도
# 필요해져서 여기로 올렸다.
ID_BATCH_SIZE = 500

# 참고용 상수 — 위 주석의 "65535" 를 코드에서도 확인할 수 있게 둔다.
PG_MAX_BIND_PARAMS = 65535


def batched(items: Sequence[str], size: int = ID_BATCH_SIZE) -> Iterator[Sequence[str]]:
    """Yield ``items`` in chunks of at most ``size`` — use before any SQL
    ``IN``/``NOT IN`` clause built from a caller-controlled id list."""
    for start in range(0, len(items), size):
        yield items[start : start + size]
