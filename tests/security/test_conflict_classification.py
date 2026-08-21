"""충돌 분류가 **진짜 제약 위반을 재시도로 감추지 않는가** (D-191 · R1).

## 왜 보안 시험인가

이것은 성능 문제가 아니라 **틀린 것을 못 보게 만드는** 문제다. 예전 `is_write_conflict()` 는
모든 `IntegrityError` 를 재시도 대상으로 봤다. SQLite 에서는 대체로 맞았다 —
`database is locked` 가 진짜 일시적 상태였기 때문이다.

PG 에서는 다르다. 그대로 두면 **FK 위반·NOT NULL 위반 같은 진짜 데이터 버그가 10회 재시도 후
503 「잠시 후 다시 시도해 주세요」로 나간다.** 사용자는 다시 시도하고, 로그에는 재시도만
남고, 진짜 원인은 아무 데도 안 적힌다. 데이터 무결성 결함이 «서버가 좀 바쁜가 보다» 로
보이는 것 — 그게 이 파일이 막는 것이다.

MASTER_PLAN §9.1 이 S2 의 Exit 로 요구한 «음성 테스트» 가 이것이다:
**명백한 제약 위반이 재시도 없이 즉시 도메인 오류로 나오는가.**

## 두 층으로 본다

1. **분류 함수 자체** — SQLSTATE 별로 어느 통에 들어가는가. 가짜 예외로 빠르게 본다.
2. **진짜 DB 로** — 실제 FK 위반을 만들어, 재시도 관용구가 그것을 삼키지 않는지 본다.
   1번만으로는 «호출부가 그 함수를 실제로 쓰는가» 를 증명하지 못한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.db import (
    is_insert_race,
    is_serialization_conflict,
    is_unique_violation,
    sqlstate_of,
)
from tests.fakes import pgerrors

pytestmark = pytest.mark.security


# ── 1. 분류 함수 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "make, code",
    [
        (pgerrors.serialization_failure, "40001"),
        (pgerrors.deadlock_detected, "40P01"),
        (pgerrors.lock_not_available, "55P03"),
    ],
)
def test_transient_conflicts_are_retryable(make, code):
    """이 셋만 재시도 대상이다 — 다시 하면 결과가 달라질 수 있는 것들."""
    exc = make()
    assert sqlstate_of(exc) == code
    assert is_serialization_conflict(exc) is True
    assert is_insert_race(exc) is True


def test_a_unique_violation_is_not_a_transient_conflict():
    """유니크 충돌은 **다시 해도 같은 결과**다. 재시도 통에 넣으면 예산만 태운다."""
    exc = pgerrors.unique_violation()
    assert is_serialization_conflict(exc) is False
    assert is_unique_violation(exc) is True
    # 다만 "넣어 보고 지면 남의 행을 읽는다" 관용구는 이것을 삼켜도 된다.
    assert is_insert_race(exc) is True


@pytest.mark.parametrize(
    "make", [pgerrors.foreign_key_violation, pgerrors.not_null_violation]
)
def test_real_constraint_violations_are_in_no_bucket_at_all(make):
    """**이 파일의 핵심이다.** FK·NOT NULL 위반은 어느 통에도 안 들어간다.

    들어가는 순간 그 데이터 버그는 재시도 뒤 503 으로 나가고, 원인은 로그에서 사라진다.
    """
    exc = make()
    assert is_serialization_conflict(exc) is False
    assert is_unique_violation(exc) is False
    assert is_insert_race(exc) is False, (
        "진짜 제약 위반이 insert-race 로 분류됐다 — 호출부가 이것을 삼킨다"
    )


def test_an_error_with_no_sqlstate_is_in_no_bucket():
    """정체를 모르는 예외를 «경합» 으로 추정하지 않는다.

    옛 구현은 `isinstance(exc, IntegrityError)` 하나로 판정해서, SQLSTATE 가 없는
    예외까지 전부 재시도 대상으로 봤다.
    """
    exc = IntegrityError("INSERT ...", {}, Exception("무슨 일인지 모르겠다"))
    assert sqlstate_of(exc) is None
    assert is_serialization_conflict(exc) is False
    assert is_insert_race(exc) is False


def test_an_unrelated_operational_error_is_not_a_conflict():
    """디스크 오류가 «잠시 후 다시 시도» 로 위장하면 진짜 고장을 아무도 안 본다."""
    exc = pgerrors.io_error()
    assert is_serialization_conflict(exc) is False
    assert is_insert_race(exc) is False


# ── 2. 제약 이름으로 좁히기 ──────────────────────────────────────────────────


def test_naming_the_constraint_narrows_what_gets_swallowed():
    """한 표에 유니크가 둘 이상이면 «내가 예상한 그 경합» 과 «전혀 다른 열의 충돌» 이
    구별되지 않는다. 후자를 삼키면 그 버그는 영영 안 보인다."""
    exc = pgerrors.unique_violation(constraint="uq_projects_org_code")
    assert is_unique_violation(exc, constraint="uq_projects_org_code") is True
    assert is_unique_violation(exc, constraint="uq_trash_item") is False


# ── 3. 진짜 DB 로 — 호출부가 실제로 그 함수를 쓰는가 ─────────────────────────


def test_a_real_foreign_key_violation_is_not_swallowed_by_a_retry_site(db, make_user):
    """**진짜 FK 위반**을 만들어, 재시도 관용구가 그것을 통과시키지 않는지 본다.

    분류 함수만 시험하면 「호출부가 그 함수를 실제로 쓰는가」는 증명되지 않는다.
    여기서는 실제 PG 가 낸 `23503` 을 재시도 판정에 그대로 먹여 본다.
    """
    from app.trash.models import TrashItem
    from datetime import datetime

    user = make_user("fk-violation@goodmit.co.kr")
    # 없는 조직을 가리키는 행 — PG 가 `23503` 으로 거부한다.
    db.add(
        TrashItem(
            item_type="ticket", notion_page_id="fk-check", title="고아",
            deleted_by_user_id=user.id, deleted_by_name="지운사람",
            deleted_at=datetime(2026, 8, 21, 9, 0, 0), org_id="no-such-org",
        )
    )
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    db.rollback()

    exc = caught.value
    assert sqlstate_of(exc) == "23503", f"기대한 FK 위반이 아니다: {sqlstate_of(exc)}"
    assert is_insert_race(exc) is False, (
        "진짜 FK 위반이 insert-race 로 분류된다 — 호출부가 재시도로 감춘다"
    )
    assert is_serialization_conflict(exc) is False


def test_a_real_unique_violation_carries_the_constraint_name(db):
    """제약 이름을 실제로 읽을 수 있는가 — 못 읽으면 `constraint=` 좁히기가 헛돈다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    db.add(Department(name="이름중복확인", org_id=DEFAULT_ORG_ID))
    db.flush()
    db.add(Department(name="이름중복확인", org_id=DEFAULT_ORG_ID))
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    db.rollback()

    exc = caught.value
    assert sqlstate_of(exc) == "23505"
    assert is_unique_violation(exc) is True
    # 이름이 실려 오면 호출부가 «어느 유니크인가» 로 좁힐 수 있다.
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    assert getattr(diag, "constraint_name", None), (
        "PG 가 준 제약 이름을 못 읽는다 — `is_unique_violation(constraint=…)` 이 무의미해진다"
    )


def test_the_outer_request_commit_only_retries_transient_conflicts():
    """요청 끝 커밋(`get_db`)이 **유니크 위반을 503 으로 포장하지 않는다**.

    그 자리는 「이 요청은 지금 못 쓴다, 다시 해 보라」를 뜻하는 503 을 낸다. 유니크 위반은
    다시 해도 같은 결과이고, 그 라우트가 같은 행을 두 번 만들려 했다는 뜻이다 —
    포장하면 사용자는 계속 재시도하고 로그에는 진짜 원인이 안 남는다.
    """
    import inspect

    from app.core import deps

    source = inspect.getsource(deps.get_db)
    assert "is_serialization_conflict" in source
    assert "is_insert_race" not in source, (
        "요청 끝 커밋이 insert-race 를 삼킨다 — 유니크 위반이 503 으로 나간다"
    )
