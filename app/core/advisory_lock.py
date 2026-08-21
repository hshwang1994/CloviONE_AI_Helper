"""PostgreSQL advisory lock — **프로세스 경계를 넘는** 상호배제 (D-192).

## 무엇이 문제였나

`--workers 1` 이 고정이던 이유의 절반이 이것이다. 티켓 배정 잠금·쿼터 잠금·재색인 잠금·
동기화 잠금·Notion 생성 잠금이 전부 `threading.Lock()` 이었고, 그건 **한 프로세스 안에서만**
성립한다. 워커를 늘리는 순간 잠금이 N벌이 되어 아무것도 막지 못한다.

그리고 그 잠금들은 지금도 이미 새고 있었다: 웹과 **워커는 원래 다른 프로세스**라, 다섯 중
넷이 "워커 틱은 못 막는다"를 자기 주석에 적어 두고 있었다. 알려진 구멍이었지 고쳐진 것이
아니다. advisory lock 은 **DB 가 잠금을 들고 있으므로** 그 구멍까지 함께 닫는다.

## 왜 잠금 전용 연결을 따로 쓰는가

이것이 이 모듈에서 가장 중요한 결정이다.

`pg_advisory_xact_lock` 은 **트랜잭션이 끝나면 풀린다.** 요청 세션에 그대로 걸면, 잠긴
구간 안에서 누가 `db.commit()` 을 부르는 순간 잠금이 조용히 풀린다 — 그리고 이 저장소에는
그런 자리가 실제로 있다(`notion_console/router.py` 는 외부 호출 앞에서 일부러 커밋한다).
잠금이 걸린 줄 알았는데 안 걸린 상태가 되고, 증상은 "가끔 두 개가 만들어진다" 다.

그래서 **잠금만을 위한 세션을 따로 연다.** 잠금의 수명은 `with` 블록 하나이고, 요청 세션이
그 사이에 무엇을 하든 상관없다 — 옛 `threading.Lock()` 과 정확히 같은 수명이다.

블록을 나갈 때 `rollback()` 으로 그 트랜잭션을 끝내 잠금을 놓는다. `pg_advisory_unlock` 을
손으로 부르지 않는 이유: 예외로 빠져나가는 경로에서 빠뜨릴 수 있고, 세션 수준 잠금은
연결이 풀로 돌아가도 **남아 있어서** 다음에 그 연결을 쓰는 요청이 영문 모를 잠금을 물려받는다.
트랜잭션 수명에 매어 두면 그 실수 자체가 불가능하다.

## 키를 두 개로 나누는 이유

`pg_advisory_xact_lock(int4, int4)` 는 잠금 공간을 (namespace, key) 로 나눈다. 하나짜리
`bigint` 로 쓰면 티켓 id 의 해시와 사용자 id 의 해시가 **같은 값이 되는 날** 서로 관계없는
두 요청이 서로를 막는다. 그 사고는 재현이 거의 불가능하고 로그에 아무 단서도 안 남는다.
namespace 를 분리하면 그 충돌 자체가 생기지 않는다.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import is_serialization_conflict

logger = logging.getLogger("app.lock")

# 잠금 네임스페이스. **값을 재사용하지 않는다** — 새 잠금 용도가 생기면 새 번호를 준다.
NS_TICKET_CLAIM = 1      # 티켓 배정 (page id 단위)
NS_QUOTA = 2             # AI 쿼터 확인→소비 (user id 단위)
NS_SEARCH_REINDEX = 3    # 수동 재색인 (전역 하나)
NS_TICKET_SYNC = 4       # 티켓 동기화 트리거 (전역 하나)
NS_NOTION_CREATE = 5     # Notion DB 생성 (전역 하나)

# 대상이 하나뿐인 잠금의 키. namespace 가 이미 용도를 구분하므로 0 이면 충분하다.
GLOBAL_KEY = 0


@contextmanager
def _lock_session(db: Session):
    """잠금만 들고 있는 **별도 세션** 하나. 나갈 때 롤백해서 잠금을 놓는다.

    `db` 는 **어느 엔진에 붙을지 알아내는 데에만** 쓴다 — 그 세션 자체에는 아무것도 걸지
    않는다. 호출부가 세션 팩토리를 따로 들고 다니지 않아도 되게 하려는 것이고, 잠금이
    요청 트랜잭션과 분리돼야 한다는 성질(모듈 docstring)은 그대로다.
    """
    # **엔진까지 내려가서** 새 커넥션을 받는다. `db.get_bind()` 는 세션이 커넥션에
    # 직접 묶여 있으면(시험 하네스가 그렇게 만든다) 그 커넥션을 그대로 준다 — 그러면
    # 아래 `rollback()` 이 남의 트랜잭션을 되감는다. `Connection.engine` 을 한 번 더
    # 벗겨 두면 제품에서도 시험에서도 언제나 별도 커넥션이다.
    bind = db.get_bind()
    lock_db = Session(bind=getattr(bind, "engine", bind))
    try:
        yield lock_db
    finally:
        # 커밋이 아니라 롤백이다 — 이 세션은 잠금 말고 아무것도 안 쓴다.
        lock_db.rollback()
        lock_db.close()


@contextmanager
def try_lock(db: Session, namespace: int, key: str | None = None):
    """**기다리지 않고** 잠근다. `with` 가 주는 값이 잠갔는지 여부다.

        with try_lock(db, NS_TICKET_SYNC) as got:
            if not got:
                raise ConflictError("이미 진행 중입니다.")
            ...

    `key` 를 주면 그 문자열 단위로, 안 주면 namespace 전체에 하나로 잠근다.
    `hashtext()` 로 int4 를 만든다 — 해시가 충돌해도 결과는 "잠깐 더 기다린다" 이지
    "둘 다 통과한다" 가 아니라 안전한 방향이다.
    """
    with _lock_session(db) as lock_db:
        if key is None:
            sql, params = "SELECT pg_try_advisory_xact_lock(:ns, :key)", {"key": GLOBAL_KEY}
        else:
            sql, params = "SELECT pg_try_advisory_xact_lock(:ns, hashtext(:key))", {"key": str(key)}
        got = bool(lock_db.execute(text(sql), {"ns": namespace, **params}).scalar())
        yield got


@contextmanager
def lock_or_continue(db: Session, namespace: int, key: str, *, wait_seconds: float):
    """잠그되, `wait_seconds` 안에 못 잡으면 **잠금 없이 진행한다**.

    쿼터가 이 모양을 쓴다. 못 잡았다고 409 를 던지면 상한이 남아 있는 사람에게 "안 된다"고
    거짓말을 하게 되고, 무한정 기다리면 사람 하나 때문에 스레드가 잠긴다. 쿼터는 비용 통제
    장치이지 보안 장치가 아니므로, 드물게 한 번 더 쓰는 쪽이 전 사용자 정지보다 낫다.

    `set_config(…, true)` 는 **이 잠금 세션의 트랜잭션에만** 적용되고 끝나면 사라진다 —
    엔진 기본값(`app/core/db.py::EngineOptions.lock_timeout_ms`)을 건드리지 않는다.
    """
    with _lock_session(db) as lock_db:
        got = False
        try:
            # `SET` 은 바인드 파라미터를 못 받는다("syntax error at or near $1").
            # `set_config(..., is_local => true)` 가 같은 일을 하면서 파라미터를 받는다 —
            # 값을 문자열로 이어 붙이지 않아도 된다.
            lock_db.execute(
                text("SELECT set_config('lock_timeout', :t, true)"),
                {"t": f"{int(wait_seconds * 1000)}ms"},
            )
            lock_db.execute(text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
                            {"ns": namespace, "key": str(key)})
            got = True
        except (OperationalError, DBAPIError) as exc:
            if not is_serialization_conflict(exc):
                raise
            # `55P03 lock_not_available` — 기다릴 만큼 기다렸다. 그 예외로 이 잠금 세션이
            # 실패 상태가 되므로 되감고 계속 간다(요청 세션은 건드리지 않았다).
            lock_db.rollback()
            logger.warning(
                "잠금(ns=%s)을 %.0f초 안에 못 잡았다. 이번 판정은 잠금 없이 진행한다 "
                "(동시 요청이 상한을 함께 지날 수 있다)",
                namespace, wait_seconds,
            )
        yield got
