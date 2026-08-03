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
            cursor = dbapi_connection.cursor()
            for name, value in pragmas:
                # PRAGMA 는 파라미터 바인딩을 받지 않는다. 값은 전부 이 모듈이 만든
                # 리터럴이고 사용자 입력이 닿지 않으므로 주입 경로가 없다.
                cursor.execute(f"PRAGMA {name}={value}")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
