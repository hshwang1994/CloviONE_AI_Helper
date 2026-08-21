"""PostgreSQL 오류를 **분류 가능한 모양으로** 만들어 주는 도우미 (D-191).

## 왜 필요한가

재시도 경로를 시험하려면 경합 오류를 손으로 만들어 던져야 한다. SQLite 시절에는
`OperationalError("database is locked")` 면 됐다 — 판정이 **메시지 문자열**이었기 때문이다.

PG 는 다르다. 판정 기준이 **SQLSTATE** 이고(`app/core/db.py::sqlstate_of`), 그건 예외 메시지가
아니라 드라이버가 따로 실어 주는 값이다. 그래서 메시지만 그럴듯한 가짜를 던지면
`is_serialization_conflict()` 가 «분류할 수 없는 예외» 로 보고 **그대로 올린다** —
그리고 그게 맞는 동작이다(D-191: 정체를 모르는 오류를 재시도로 삼키지 않는다).

즉 여기서 SQLSTATE 를 빠뜨리면 시험은 "재시도가 안 된다" 로 실패하는데 원인은 제품이
아니라 가짜 예외에 있다. 그 함정을 한 곳에 가둔다.

## 왜 진짜 psycopg 예외를 안 쓰는가

`psycopg.errors.SerializationFailure` 는 실제 서버 응답 없이 만들기 번거롭고, 만들어도
`diag` 가 비어 있다. 우리가 시험해야 하는 것은 **우리 분류 함수가 SQLSTATE 를 읽는가**
이므로, SQLSTATE 를 들고 있는 최소한의 객체면 충분하다.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError, OperationalError


class _PgError(Exception):
    """psycopg 예외가 SQLSTATE 를 싣는 자리를 흉내 낸다."""

    def __init__(self, sqlstate: str, message: str, constraint: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = _Diag(sqlstate, constraint)


class _Diag:
    def __init__(self, sqlstate: str, constraint: str | None) -> None:
        self.sqlstate = sqlstate
        self.constraint_name = constraint


def serialization_failure(statement: str = "UPDATE ...") -> OperationalError:
    """`40001` — 직렬화 실패. **재시도 대상**이다."""
    return OperationalError(
        statement, {}, _PgError("40001", "could not serialize access due to concurrent update")
    )


def deadlock_detected(statement: str = "UPDATE ...") -> OperationalError:
    """`40P01` — 교착. PG 가 한쪽을 죽인다. 재시도 대상이다."""
    return OperationalError(statement, {}, _PgError("40P01", "deadlock detected"))


def lock_not_available(statement: str = "SELECT ... FOR UPDATE") -> OperationalError:
    """`55P03` — `lock_timeout` 초과. 재시도 대상이다."""
    return OperationalError(
        statement, {}, _PgError("55P03", "canceling statement due to lock timeout")
    )


def unique_violation(
    statement: str = "INSERT ...", constraint: str | None = None
) -> IntegrityError:
    """`23505` — "이미 있다". 재시도가 아니라 **호출부가 국소 처리**할 대상이다."""
    return IntegrityError(
        statement,
        {},
        _PgError("23505", "duplicate key value violates unique constraint", constraint),
    )


def foreign_key_violation(statement: str = "INSERT ...") -> IntegrityError:
    """`23503` — FK 위반. **재시도해서도 삼켜서도 안 되는** 진짜 데이터 버그다.

    D-191 이 막으려는 실패가 이것이다: 예전 `is_write_conflict()` 는 모든
    `IntegrityError` 를 참으로 봐서 이것까지 10회 재시도한 뒤 503 「다시 시도」로 내보냈다.
    """
    return IntegrityError(
        statement, {}, _PgError("23503", "insert or update violates foreign key constraint")
    )


def not_null_violation(statement: str = "INSERT ...") -> IntegrityError:
    """`23502` — NOT NULL 위반. 역시 재시도 대상이 아니다."""
    return IntegrityError(
        statement, {}, _PgError("23502", 'null value in column violates not-null constraint')
    )


def io_error(statement: str = "COMMIT") -> OperationalError:
    """`58030 io_error` — 디스크 오류. **경합이 아니다.**

    재시도 경로가 이것까지 삼키면 진짜 고장이 "잠시 후 다시 시도해 주세요" 로 위장한다.
    분류 함수가 «어느 통에도 안 넣는» 것이 옳은 동작이고, 그 성질을 시험하는 데 쓴다.
    """
    return OperationalError(statement, {}, _PgError("58030", "could not write to file"))
