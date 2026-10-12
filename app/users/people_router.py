"""관리 콘솔의 **사람 찾기** — 읽기 전용 후보 목록 (FP-D).

## 왜 이 엔드포인트가 있는가

승인·승인 위임·감사 로그·대리 접속·AI 쿼터 화면은 「사람」 필터와 선택 상자를 채우려고
`GET /api/admin/users` 를 불렀다. 그 경로는 `USER_MANAGE`(admin 이상) 뒤에 있다. 그래서
운영자와 감사자가 그 다섯 화면을 열 때마다 403 이 한 번씩 났고, 사람 필터는 빈 채로
남았다 — 화면은 열리는데 사람을 고를 수 없는 상태였다. 권한 게이트를 낮추면 사용자 관리
전체가 열리므로 그쪽을 건드릴 수는 없다. 필요한 것은 「이 사람이 누구인지 고를 수 있을
만큼」의 목록 하나다.

## 왜 `/api/admin/users` 보다 일부러 좁은가

* **읽기만 있다.** 역할 게이트는 `CONSOLE_READ_ROLES` 다 — 운영자·감사자가 볼 수 있고,
  쓰기 경로는 하나도 없다. 사람을 바꾸는 일은 여전히 `/api/admin/users` 만 할 수 있다.
* **신원 조각만 싣는다.** id·이름·이메일·활성·보관·부서명이 전부다. 역할·잠금·마지막
  로그인·비밀번호 변경 여부·관리 범위 같은 관리 정보는 싣지 않는다 — 운영자가 이 경로로
  상위 권한 계정을 정찰할 수 있으면 사용자 관리 게이트가 반쪽이 된다.
* **범위는 사용자 목록과 같은 규칙을 쓴다.** `apply_user_scope(principal.management)` 를
  그대로 지나므로 부서 관리자는 자기 서브트리만, 운영자·감사자는 자기 조직만, 전역 관리자는
  전부를 본다. 목록에서 가린 사람이 여기서 새면 가린 의미가 없다(IDOR).
* **보관된 사람도 기본으로 싣는다.** 감사 로그와 승인 이력은 퇴사한 사람을 계속 가리킨다.
  그 사람을 목록에서 빼면 옛 기록의 행위자를 고를 수 없어 필터가 거짓말한다. 화면이
  `archived` 를 보고 표시를 구분한다.

## 두 축을 따로 끈다 — 보관과 비활성

「고를 수 있는 사람」의 정의는 화면마다 다르다. 감사 로그의 행위자 필터는 **퇴사자까지**
필요하고, AI 상한·승인 위임처럼 **새로 지정하는** 폼은 그 반대다 — 서버가 거절할 사람을
후보로 세우면 폼은 반드시 실패하는 선택지를 권한 셈이 된다(`registry/shared.js` 가 보관
계정을 후보에서 뺀 이유가 그것이다). 비활성 계정도 같은 부류다: 상한을 걸면 422 이고
(`app/quotas/router.py::_ensure_target_accepts_a_new_quota`), 그 사실을 후보 목록만
모르고 있었다. 그래서 `include_archived` 옆에 `include_inactive` 를 둔다 — 거절 규칙과
후보 규칙이 같은 축을 쓴다.

## 잘렸으면 잘렸다고 말한다

상한(`PEOPLE_LIMIT_MAX`)에서 자르고 그 사실을 응답에 안 적으면, 501번째 사람은 화면에서
**존재하지 않는 사람**이 된다 — 오류도 빈 목록도 아니고 그냥 이름이 없다. 고를 수 없는
이유를 화면이 말할 수 없으므로 응답이 말한다: `truncated`·`total`·`limit`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import CONSOLE_READ_ROLES
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.scope import Principal, apply_user_scope
from app.core.search_text import contains_folded
from app.users.models import User

# 화면의 선택 상자가 한 번에 받는 상한. 사용자 수가 1000명 규모라 500 이면 한 조직이
# 한 번에 들어오고, 그보다 크면 `q` 로 좁혀서 다시 부른다.
PEOPLE_LIMIT_MAX = 500

router = APIRouter(
    prefix="/api/admin/people",
    tags=["admin-people"],
    # GET 뿐이라 `require_csrf` 는 지금 아무것도 막지 않는다(안전한 메서드는 통과한다).
    # 그래도 다른 관리 라우터와 같은 모양으로 둔다 — 나중에 쓰기 경로가 하나 생겨도
    # CSRF 가 저절로 걸린다(tests/security/test_csrf_coverage.py 가 그 사실을 본다).
    dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES)), Depends(require_csrf)],
)


def _person_row(user: User) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "active": user.active,
        "archived": user.archived_at is not None,
        # `department` 는 명부 관계에서 이름을 읽는 프로퍼티다(`lazy="joined"` 라 추가 질의가
        # 없다). 동명이인을 화면이 구분하려면 이름 옆에 부서가 있어야 한다(app/core/people.py).
        "department_name": user.department,
    }


def _person_rows(db, users) -> list[dict]:
    """후보 줄마다 얼굴 두 칸(`avatar_url` · `avatar_default_key`)을 한 번의 질의로 싣는다(D-556).

    선택 상자의 줄이 `UserAvatar` 로 그려지는데 두 칸이 없으면 id 로 배정한 기본 그림이 서서
    같은 사람이 프로필 화면과 다른 얼굴을 갖는다.
    """
    from app.core.people import avatar_map

    rows = [_person_row(u) for u in users]
    amap = avatar_map(db, [r["id"] for r in rows])
    for r in rows:
        a = amap.get(r["id"]) or {}
        r["avatar_url"] = a.get("url")
        r["avatar_default_key"] = a.get("default_key")
    return rows


@router.get("")
def list_people(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=PEOPLE_LIMIT_MAX, ge=1, le=PEOPLE_LIMIT_MAX),
    include_archived: bool = Query(
        default=True,
        description="false 면 보관된 계정을 뺀다. 기본(true)은 옛 기록의 행위자도 고를 수 있게 싣는다.",
    ),
    include_inactive: bool = Query(
        default=True,
        description=(
            "false 면 비활성 계정을 뺀다. AI 상한이나 승인 위임처럼 새로 지정하는 폼이 쓴다. "
            "서버가 거절할 사람을 후보로 세우지 않기 위해서다."
        ),
    ),
) -> dict:
    """후보 목록 한 페이지. **잘렸으면 잘렸다고 말한다.**"""
    stmt = apply_user_scope(select(User), principal.management)
    if not include_archived:
        stmt = stmt.where(User.archived_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(User.active.is_(True))
    # 이름·이메일 검색. 대조는 공용 접기 규칙이다(`app/core/search_text.py`) — 「김 지혜」로
    # 「김지혜」를 찾고, `%`·`_` 는 글자로 본다. 접은 뒤 빈 검색어는 조건이 아니다.
    search_clause = contains_folded((User.display_name, User.email), q)
    if search_clause is not None:
        stmt = stmt.where(search_clause)
    # 상한보다 **한 행 더** 읽는다 — 잘렸는지는 그 한 행이 있는지로 안다(추가 질의 없이).
    rows = (
        db.execute(
            stmt.order_by(User.display_name.asc(), User.email.asc()).limit(limit + 1)
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > limit
    rows = rows[:limit]
    # 총원은 **잘렸을 때만** 센다. 안 잘렸으면 지금 실은 것이 전부라 셀 이유가 없고,
    # 잘렸으면 화면이 「몇 명 중 몇 명을 보고 있는가」를 말할 수 있어야 한다.
    total = (
        db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        if truncated
        else len(rows)
    )
    return {
        "items": _person_rows(db, rows),
        # 화면은 이 셋으로 「이름을 더 적어 좁혀 주세요」를 말한다. 없으면 없는 사람과
        # 못 실은 사람이 화면에서 똑같아진다.
        "truncated": truncated,
        "total": total,
        "limit": limit,
    }
