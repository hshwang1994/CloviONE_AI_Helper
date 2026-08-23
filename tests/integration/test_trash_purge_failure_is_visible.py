"""휴지통 영구삭제 실패가 **보여야** 한다 (H5).

## 무엇이 문제였나

만료 항목을 지울 때 소스 호출이 실패하면 `failed += 1` 만 하고 넘어갔다. 로그도 없고,
어느 항목이 왜 실패했는지도 남지 않았다.

원본이 Notion 에서 이미 지워졌거나 토큰 권한이 빠진 항목은 **매 주기 똑같이 실패**한다.
그 항목은 휴지통에 영원히 남고, 화면에는 "N건 실패" 만 뜬다. N 이 줄지 않는 이유를
아무도 모르고, 조사할 단서도 없다. 조용한 실패 중에서도 **영구히 반복되는** 부류다.

## 무엇을 싣고 무엇을 안 싣는가

오류 **종류**(예외 클래스 이름)는 싣는다 - 원인이 그것으로 갈린다.
오류 **메시지**는 안 싣는다 - 소스가 준 문자열이라 무엇이 들었는지 보장할 수 없는데,
이 값은 운영 화면까지 그대로 나간다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 6, 9, 0, 0)


@pytest.fixture()
def expired_items(db, make_user):
    """보관 기간이 지난 휴지통 항목 둘."""
    from app.trash.models import TRASH_TICKET, TrashItem

    owner = make_user("purge@goodmit.co.kr", role="user", display_name="버린사람")
    old = NOW - timedelta(days=400)
    db.add_all([
        TrashItem(item_type=TRASH_TICKET, notion_page_id="page-fails",
                  title="지워지지 않는 것", deleted_by_user_id=owner.id, deleted_at=old),
        TrashItem(item_type=TRASH_TICKET, notion_page_id="page-ok",
                  title="정상", deleted_by_user_id=owner.id, deleted_at=old),
    ])
    db.commit()
    return owner


def _purge(db, settings, *, failing_page: str | None):
    """`page-fails` 만 터지게 하고 정리를 돌린다."""
    from app.trash import service

    class _Boom(RuntimeError):
        pass

    original = service._archive_source

    def _fake(db, item, *, outbound, settings):
        if failing_page and item.notion_page_id == failing_page:
            raise _Boom("소스가 거절했다")
        return None

    service._archive_source = _fake
    try:
        return service.purge_expired(
            db, outbound=None, settings=settings, retention_days=30, now=NOW
        )
    finally:
        service._archive_source = original


def test_the_sample_actually_has_one_failure_and_one_success(db, settings, expired_items):
    """오탐 방지 - 둘 다 성공하거나 둘 다 실패하면 아래 검사가 아무것도 못 가른다."""
    result = _purge(db, settings, failing_page="page-fails")
    assert result["purged"] == 1, result
    assert result["failed"] == 1, result


def test_a_failure_says_which_item_and_why(db, settings, expired_items):
    """🔴 숫자만으로는 조사할 수 없다. 어느 항목이 어떤 종류로 실패했는지 나와야 한다."""
    result = _purge(db, settings, failing_page="page-fails")
    failures = result.get("failures")
    assert failures, f"실패 내역이 없다 - 숫자만 남았다: {result}"
    assert len(failures) == 1, failures
    assert failures[0]["reason"], f"실패 이유(종류)가 비었다: {failures[0]}"
    assert result["failure_reasons"] == [failures[0]["reason"]], result


def test_the_failure_message_from_the_source_is_not_leaked(db, settings, expired_items):
    """소스가 준 문자열은 무엇이 들었는지 보장할 수 없다 - 종류만 낸다."""
    result = _purge(db, settings, failing_page="page-fails")
    blob = str(result)
    assert "소스가 거절했다" not in blob, f"소스 메시지가 그대로 실렸다: {blob}"


def test_the_failure_is_written_to_the_log(db, settings, expired_items, caplog):
    """로그가 없으면 화면을 안 보는 사이에 일어난 실패는 흔적이 없다."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.trash"):
        _purge(db, settings, failing_page="page-fails")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "휴지통 영구삭제 실패" in text, f"실패가 로그에 안 남았다: {text!r}"
    assert "page-fails" not in text, "로그에 소스 page id 를 그대로 적을 이유가 없다"


def test_the_failed_item_stays_for_the_next_round(db, settings, expired_items):
    """실패한 항목을 지워 버리면 원본이 남은 채 기록만 사라진다 - 되돌릴 수 없다."""
    from sqlalchemy import select

    from app.trash.models import TrashItem

    _purge(db, settings, failing_page="page-fails")
    db.expire_all()
    left = db.execute(select(TrashItem)).scalars().all()
    assert [i.notion_page_id for i in left] == ["page-fails"], (
        f"실패한 항목이 남지 않았거나 성공분이 안 지워졌다: {[i.notion_page_id for i in left]}"
    )


def test_nothing_is_reported_when_nothing_fails(db, settings, expired_items):
    """오탐 방지 - 아무 문제 없을 때 실패 목록이 비어야 한다."""
    result = _purge(db, settings, failing_page=None)
    assert result["failed"] == 0, result
    assert result["failures"] == [], result
    assert result["failure_reasons"] == [], result
