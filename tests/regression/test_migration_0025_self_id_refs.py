"""자체 id 다리와 **레거시 키를 지우지 않았다**는 보증 (옛 0025).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

백필 자체(옛 행에 값을 채우는 일)는 새 설치에 대상이 없으므로 여기서 볼 것이 없다 —
그건 S13 Migration Tool 이 운영 데이터를 옮길 때 보는 일이다. 여기서 보는 것은 **구조**다:
다리가 되는 컬럼이 있는가, 그리고 옛 키를 지우지 않았는가.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def test_the_self_id_bridge_columns_exist(db):
    """소스가 자체 DB 로 바뀌는 날 이어 붙일 다리다. 없으면 그날 이어 붙일 곳이 없다."""
    assert "document_id" in _cols(db, "document_favorites")
    assert "document_id" in _cols(db, "document_recent_views")
    assert "target_uid" in _cols(db, "trash_items")


@pytest.mark.parametrize(
    "table", ["document_favorites", "document_recent_views", "trash_items"]
)
def test_the_legacy_notion_page_id_column_is_kept(db, table):
    """「자체 id 가 생겼으니 옛 컬럼은 지워도 되겠지」가 정확히 사고를 만드는 판단이다.

    휴지통의 중복 방지 키(`uq_trash_item`)가 `notion_page_id` 에 걸려 있다. 떼면 같은
    페이지를 두 번 버릴 수 있게 되고 복원 시 목록에 중복 행이 생긴다.
    """
    assert "notion_page_id" in _cols(db, table), f"{table}.notion_page_id 가 사라졌다"


def test_the_trash_dedupe_key_still_rejects_a_second_delete(db, make_user):
    """구조가 아니라 **동작**으로 본다 — 인덱스가 있어도 안 막으면 소용이 없다."""
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from app.trash.models import TrashItem

    now = datetime(2026, 8, 21, 9, 0, 0)
    user = make_user("trash-dup@goodmit.co.kr")
    for _ in range(2):
        db.add(
            TrashItem(
                item_type="ticket",
                notion_page_id="page-dup",
                title="같은 페이지",
                deleted_by_user_id=user.id,
                deleted_by_name="지운사람",
                deleted_at=now,
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_different_item_type_with_the_same_page_is_allowed(db, make_user):
    """중복 키는 `(item_type, notion_page_id)` 다 — 유형까지 묶여야 티켓과 문서가 안 부딪힌다."""
    from datetime import datetime

    from app.trash.models import TrashItem

    now = datetime(2026, 8, 21, 9, 0, 0)
    user = make_user("trash-kinds@goodmit.co.kr")
    for kind in ("ticket", "document"):
        db.add(
            TrashItem(
                item_type=kind,
                notion_page_id="page-shared",
                title="같은 페이지, 다른 유형",
                deleted_by_user_id=user.id,
                deleted_by_name="지운사람",
                deleted_at=now,
            )
        )
    db.flush()  # 예외가 나면 실패다.
