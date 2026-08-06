"""휴지통 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.trash.models import TrashItem


def list_items(db: Session) -> list[TrashItem]:
    """휴지통 전체를 최근 삭제 순으로. **범위를 걸지 않는다** — 보존 정리(worker)가 쓴다.

    화면용 목록은 `list_visible()` 을 쓴다. 두 함수를 나눠 둔 이유: 배경 작업이 화면 범위에
    걸리면 **범위 밖 항목이 영원히 정리되지 않는다**(만료됐는데 아무도 못 지운다).
    """
    return list(
        db.execute(select(TrashItem).order_by(TrashItem.deleted_at.desc())).scalars().all()
    )


def list_visible(db: Session, scope) -> list[TrashItem]:
    """그 사람이 볼 수 있는 휴지통 항목만 (1순위 유출 #6 / Z15).

    `GET /api/trash` 에는 조건이 **하나도 없었다** — 로그인만 하면 남의 팀이 지운 티켓·문서의
    제목과 URL 이 그대로 보였다. 목록 화면에서 가려 둔 것이 휴지통에서 새는 경로다.
    그리고 `trash_items` 는 `OrgScopedMixin` 을 상속한다 — **모델은 범위를 선언하는데 유일한
    조회자가 안 걸고 있었다**(Z15). 두 곳이 다른 의도를 말하고 있었다.

    ## 기준은 '지운 사람'

    휴지통 항목에는 담당자가 없다. 있는 것은 `deleted_by_user_id` 이고 그게 맞는 기준이다 —
    "내 팀이 지운 것" 이 내 팀이 되돌릴 수 있는 것이고, 되돌리기가 이 화면의 목적이다.

    ## 보관된 계정이 지운 것은 남긴다

    `visible_user_ids` 는 **활성 사용자만** 본다. 퇴사자가 지운 항목을 그 이유로 숨기면
    **아무도 되돌릴 수 없게 된다** — 오프보딩 직후가 정확히 "저 사람이 뭘 지웠더라" 를
    확인해야 하는 때다. 그래서 '아는 사람 집합에 없으면 숨긴다' 가 아니라 '**다른 팀 사람이
    지운 것만** 숨긴다' 로 판정한다.
    """
    from app.core.scope import visible_user_ids

    rows = list_items(db)
    if not getattr(scope, "is_dept", False):
        return rows

    visible = visible_user_ids(db, scope)
    # 이 범위 밖 **활성** 사용자들. 이 사람들이 지운 것만 가린다.
    hidden = _active_user_ids(db) - set(visible)
    return [r for r in rows if r.deleted_by_user_id not in hidden]


def _active_user_ids(db: Session) -> set[str]:
    from app.users.models import User

    return {
        uid for (uid,) in db.execute(
            select(User.id).where(User.active.is_(True), User.archived_at.is_(None))
        ).all()
    }


def visible_to(db: Session, item: TrashItem, scope) -> bool:
    """이 항목이 그 사람 범위 안인가 (3순위 IDOR).

    목록은 `list_visible` 로 가렸는데 단건(`복원`·`영구삭제`)은 조건이 없어서, **id 하나로
    남의 팀 휴지통 항목을 영구삭제**할 수 있었다. 목록에서 가린 것이 단건에서 새면 가린
    의미가 없고, 여기서는 그 결과가 **되돌릴 수 없는 삭제**다.

    판정은 `list_visible` 과 **같은 규칙**이어야 한다(두 벌이 되면 한쪽만 고쳐진다):
    다른 팀의 **활성** 사용자가 지운 것만 가린다 — 퇴사자가 지운 것은 남긴다.
    """
    if not getattr(scope, "is_dept", False):
        return True
    from app.core.scope import visible_user_ids

    hidden = _active_user_ids(db) - set(visible_user_ids(db, scope) or set())
    return item.deleted_by_user_id not in hidden


def get(db: Session, trash_id: str) -> TrashItem | None:
    return db.execute(select(TrashItem).where(TrashItem.id == trash_id)).scalar_one_or_none()


def get_by_page(db: Session, item_type: str, notion_page_id: str) -> TrashItem | None:
    return db.execute(
        select(TrashItem).where(TrashItem.item_type == item_type, TrashItem.notion_page_id == notion_page_id)
    ).scalar_one_or_none()


def trashed_page_ids(db: Session, item_type: str) -> set[str]:
    """해당 종류의 휴지통에 들어간 노션 page id 집합 — 목록에서 걸러내는 데 쓴다."""
    rows = db.execute(
        select(TrashItem.notion_page_id).where(TrashItem.item_type == item_type)
    ).scalars().all()
    return set(rows)
