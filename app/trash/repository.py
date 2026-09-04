"""휴지통 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.trash.models import TrashItem

# UA-10 확증 — 화면은 15초마다 폴링되는데 이 상한도 total도 없었다("더 보기" 클릭도 조용히
# 무시됐다). app/chat/service.py의 대화 목록(AI-18)과 같은 값 — 그 화면과 같은 이유로 정한
# 상한이다(대부분 이 아래고, 늘려도 한 응답이 과하게 커지지 않는다).
DEFAULT_TRASH_LIST_LIMIT = 100
MAX_TRASH_LIST_LIMIT = 1000


def list_items(db: Session) -> list[TrashItem]:
    """휴지통 전체를 최근 삭제 순으로. **범위를 걸지 않는다** — 보존 정리(worker)가 쓴다.

    화면용 목록은 `list_visible()` 을 쓴다. 두 함수를 나눠 둔 이유: 배경 작업이 화면 범위에
    걸리면 **범위 밖 항목이 영원히 정리되지 않는다**(만료됐는데 아무도 못 지운다).
    """
    return list(
        db.execute(
            # 🔴 `deleted_at` 하나로만 정렬하면 **전순서가 아니다.** 일괄 삭제는 여러 행에
            # 같은 시각을 찍으므로 그 묶음 안의 순서를 DB 가 매번 마음대로 정하고, 상한
            # 경계에 그 묶음이 걸리면 새로고침마다 다른 행이 잘려 나간다 — 사용자에게는
            # 「방금 있던 것이 사라졌다」로 보이고 재현도 안 된다. 문서 쪽(`_order_by`)이
            # 이미 `id` 를 붙여 전순서를 만든다. 두 원천을 합치는 자리라 더 그래야 한다.
            select(TrashItem).order_by(TrashItem.deleted_at.desc(), TrashItem.id.asc())
        ).scalars().all()
    )


def scoped_rows(db: Session, scope) -> list[TrashItem]:
    """범위를 건 뒤의 전량. 목록도 개수도 **이 한 함수**를 지난다.

    두 벌이 되면 한쪽만 고쳐지는 날이 온다 — 이 파일의 `visible_to` 머리말이 같은 이유를
    이미 적어 뒀다. 개수(`counts_visible`)가 목록과 다른 규칙으로 세면 화면의 탭이
    「티켓 7」이라 말하고 눌렀을 때 5줄이 나온다.
    """
    from app.core.scope import visible_user_ids

    rows = list_items(db)
    # RBAC 재감사(2026-08-16)로 발견: `is_dept`일 때만 걸렀던 원래 조건은 org 범위
    # (admin_scope='org') 관리자를 global과 똑같이 취급해 다른 조직이 지운 항목까지
    # 그대로 냈다. 진짜 무제한은 global뿐이므로 그 경우만 건너뛴다.
    if not getattr(scope, "is_global", False):
        visible = visible_user_ids(db, scope)
        # 이 범위 밖 **활성** 사용자들. 이 사람들이 지운 것만 가린다.
        hidden = _active_user_ids(db) - set(visible)
        rows = [r for r in rows if r.deleted_by_user_id not in hidden]
    return rows


def counts_visible(db: Session, scope, *, rows: list[TrashItem] | None = None) -> dict[str, int]:
    """종류별 개수 — **조건과 상한을 적용하기 전** 기준이다.

    화면의 탭이 이 값을 쓴다. 예전에는 화면이 **이미 걸러진 응답**에서 종류를 셌다. 그래서
    문서 화면의 「휴지통」 단추가 `?kind=document` 로 열면 첫 화면부터 「티켓 0」이 떴다 —
    티켓이 수십 건 들어 있어도 그랬다. 세 칸이 서로 다른 말을 하는 조작기는 조작기가 아니다.
    """
    rows = scoped_rows(db, scope) if rows is None else rows
    out: dict[str, int] = {}
    for r in rows:
        out[r.item_type] = out.get(r.item_type, 0) + 1
    return out


#: 휴지통 목록의 정렬 축 → 옛 미러 행에서 그 값을 뽑는 함수.
#:
#: `purge_after` 가 `deleted_at` 과 같은 함수인 것은 눈속임이 아니라 사실이다 — 옛 항목의
#: 삭제 예정일은 `deleted_at + 보관기간` 이고 보관기간은 이 원천 안에서 상수라, 두 축의
#: **순서가 같다.** (문서 원천은 보관기간이 다르지만 그쪽도 자기 안에서는 상수다. 그래서
#: 원천별로 자기 축을 정렬해도 합친 뒤 실제 `purge_after` 로 다시 세우면 결과가 옳다.)
_LEGACY_SORT_KEYS = {
    "deleted_at": lambda r: r.deleted_at,
    "purge_after": lambda r: r.deleted_at,
    # 🔴 `casefold()` 가 아니라 `lower()` 다 — 문서 원천의 SQL 이 `func.lower()` 를 지난다
    # (`knowledge/service.py::_order_by`). 두 원천의 비교 함수가 다르면 각자 잘라 온 앞
    # N 줄이 합친 기준의 앞 N 줄이 아니게 된다.
    "title": lambda r: (r.title or "").lower(),
}


def list_visible(
    db: Session, scope, *, limit: int = DEFAULT_TRASH_LIST_LIMIT, item_type: str | None = None,
    sort: str = "deleted_at", descending: bool = True,
    rows: list[TrashItem] | None = None,
) -> tuple[list[TrashItem], int]:
    """그 사람이 볼 수 있는 휴지통 항목만 (1순위 유출 #6 / Z15).

    반환은 `(상한까지 자른 목록, 범위 안 전체 개수)` 쌍이다(UA-10 확증) — 범위 판정을
    **먼저** 끝낸 뒤에 자른다. 순서를 바꿔 SQL 단계에서 먼저 자르면, 그 뒤 파이썬에서
    범위 밖 행을 걸러내는 이 함수의 방식과 맞물려 실제로는 더 있는데도 상한보다 적게
    돌려주는 조용한 손실이 생긴다.

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
    # `rows` 를 받으면 다시 안 읽는다. 한 요청이 목록·개수·급한 건수 셋을 함께 내는데
    # 그때마다 표를 다시 훑으면 15초 폴링이 같은 일을 세 번 한다.
    rows = scoped_rows(db, scope) if rows is None else rows
    # 종류로 좁히는 것도 **자르기 전에** 한다. 화면에서 거르면 상한 안에 그 종류가 몇 건
    # 들어왔는지에 따라 목록이 달라지고, 「몇 건 중 어디쯤」도 함께 틀린다.
    if item_type:
        rows = [r for r in rows if r.item_type == item_type]
    # 정렬도 **자르기 전에** 한다. 그리고 축은 화면이 고른 것이어야 한다 — 문서 원천이
    # 「제목 오름차순」인데 이쪽만 「삭제일 내림차순」이면, 각자 앞 `limit` 줄을 잘라 합친
    # 목록의 한가운데가 통째로 빈다.
    #
    # 🔴 동점은 **방향과 무관하게 `id` 오름차순**으로 깬다. 튜플 `(값, id)` 를 통째로
    # 뒤집으면 내림차순에서 id 순서까지 뒤집히는데, 문서 원천의 SQL 은 어느 방향에서도
    # `id.asc()` 다(`_order_by`). 두 원천이 동점 묶음을 다른 순서로 자르면 그 경계에서
    # 합친 목록이 어긋난다. 파이썬 정렬은 안정 정렬이라 두 번 세면 그 짝이 만들어진다.
    key = _LEGACY_SORT_KEYS.get(sort) or _LEGACY_SORT_KEYS["deleted_at"]
    rows = sorted(rows, key=lambda r: r.id)
    rows.sort(key=key, reverse=descending)
    return rows[:limit], len(rows)


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
    # RBAC 재감사(2026-08-16)로 발견: `is_dept`가 아니면 무조건 통과시키던 조건은 org 범위
    # 관리자를 global과 똑같이 취급했다 — 여기서는 그 결과가 **되돌릴 수 없는 영구삭제**라
    # list_visible보다 더 심각하다. 진짜 무제한은 global뿐이다.
    if getattr(scope, "is_global", False):
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
