"""사람 한 명을 화면에서 **구분**하기 위한 최소 신원 — 단일 정의.

## 왜 이 파일이 필요한가

사용자 지시(2026-08-04): *"채팅 및 대화 및 댓글 작성 등을 할 때도 동명이인 등을 고려해
어떤 조직의 어떤 부서인지 나와야 한다."*

그동안 사람이 나오는 자리마다 각자 다른 조각을 실었다:
  - `/api/team-chat/directory` — 이름 + 부서 + 직책 (유일하게 구분됨)
  - 방 멤버 목록, 메시지 발신자, 댓글 작성자, 티켓 담당자 선택, 게임방 — **이름만**
  - 오프보딩 후임자 선택 — 이름 + 이메일 + 부서

같은 질문("이 사람이 누구냐")에 화면마다 다르게 답하고 있었고, 대부분은 표시 이름 하나로
답하고 있었다. `users.display_name` 에는 유일성 제약이 **없다**(`app/users/models.py`) —
동명이인은 스키마상 정상 상태다. 실제로 `app/team_chat/service.py::_mention_candidates` 는
표시 이름이 겹치면 **두 사람 다 멘션 후보에서 조용히 뺀다**. 이름만으로는 못 고르기 때문이다.

그래서 신원 조각을 만드는 자리를 여기 하나로 모은다. 새 화면이 사람을 보여줄 때
`identity()` 를 쓰면 부서·직책·조직이 자동으로 따라온다 — 다음 화면에서 또 새어 나가지 않는다.

## 왜 조직까지 넣는가

지금은 조직이 한 행뿐이라 화면에 늘 그리면 잡음이다. 그래서 **응답에는 항상 싣고, 그릴지는
화면이 정한다**(조직이 둘 이상일 때만). 제품화되면 다른 조직의 동명이인이 실제로 생기는데,
그때 payload 부터 고치기 시작하면 이 파일이 없던 시절로 돌아간다.

## 비용

`User.department_ref`/`title_ref` 는 이미 `lazy="joined"` 라(`app/users/models.py`) 부서·직책은
**추가 질의 없이** 읽힌다. 조직 이름만 `org_name_map()` 으로 한 번 읽어 넘긴다 —
조직 표는 행이 몇 개뿐이라 요청당 한 번이면 충분하다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.org.models import Organization


def org_name_map(db: Session) -> dict[str, str]:
    """{org_id: 조직명}. 조직 표는 작아서 통째로 읽는다."""
    rows = db.execute(select(Organization.id, Organization.name)).all()
    return {oid: name for oid, name in rows}


def name_map(db: Session, user_ids) -> dict[str, dict[str, str]]:
    """{user_id: {display_name, email}} — **한 번의 질의로** (E-4 UUID 노출).

    ## 왜 여기 있나

    관리자 상세 패널이 사람 자리를 전부 UUID 로 채우고 있었다. 운영자는
    `9f2c…-…` 를 보고 "이게 누구냐" 를 알 수 없어, 사용자 화면을 따로 열어 id 를 검색해야
    했다. 그런데 이름을 붙이는 코드는 이미 있었다 — 승인(approvals)과 대리 접속
    (impersonation)이 **각자 한 벌씩** 들고 있었다. 세 번째 사본을 만들지 않으려고
    여기로 올린다.

    건별 조회를 하지 않는 이유는 `avatar_map` 과 같다: 목록 응답에 실려 나가는 값이라
    N+1 이면 목록 화면이 그대로 느려진다.
    """
    ids = {i for i in (user_ids or ()) if i}
    if not ids:
        return {}
    from app.users.models import User

    rows = db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(tuple(ids)))
    ).all()
    return {r[0]: {"display_name": r[1], "email": r[2]} for r in rows}


def identity(
    user, org_names: dict[str, str] | None = None, avatars: dict[str, str] | None = None
) -> dict:
    """사람 한 명의 신원 조각.

    `user` 가 None 이면(삭제된 사용자를 참조하는 옛 레코드) 빈 신원을 돌려준다 —
    호출부마다 None 검사를 다시 쓰지 않게 하려는 것이다.
    """
    if user is None:
        return {
            "user_id": None, "display_name": "", "dept": "", "title": "", "org": "",
            "archived": False, "avatar_url": None,
        }
    org_id = getattr(user, "org_id", None)
    return {
        "user_id": user.id,
        "display_name": user.display_name or "",
        # `department`/`title` 은 관계에서 이름을 꺼내는 프로퍼티다(users/models.py).
        "dept": user.department or "",
        "title": user.title or "",
        "org": (org_names or {}).get(org_id, "") if org_id else "",
        # **사람이 없어졌다는 사실**을 신원에 싣는다 (N3). 이 값을 안 보내면 퇴사자가 영원히
        # 참여자·발신자로 살아 있고, 보는 사람은 답이 안 오는 대화를 며칠 기다린다 —
        # 시스템에서 가장 비싼 침묵이다. `archived_at` 은 관리자 API 에만 실려 있었다.
        "archived": getattr(user, "archived_at", None) is not None
        or not getattr(user, "active", True),
        # 사진은 **있으면 싣고 없으면 None** 이다 (X13). 호출부가 `avatars` 를 안 주면 예전과
        # 똑같이 동작한다 — 배치 조회가 필요한 값이라 모든 호출부에 강제하지 않는다.
        "avatar_url": (avatars or {}).get(user.id),
    }


def affiliation(person: dict, *, with_org: bool = False) -> str:
    """'개발본부 팀장' 처럼 소속을 한 줄로. 비어 있는 조각은 건너뛴다.

    구분자로 가운뎃점(·)을 쓰지 않는다 — 이 제품에서 그 문자를 화면에 쓰지 않기로 했다.
    """
    parts: list[str] = []
    if with_org and person.get("org"):
        parts.append(person["org"])
    if person.get("dept"):
        parts.append(person["dept"])
    if person.get("title"):
        parts.append(person["title"])
    return " ".join(parts)


def avatar_map(db, user_ids) -> dict[str, str]:
    """{user_id: 아바타 URL} — **한 번의 질의로** (X13).

    서빙 경로(`/api/profile/avatar/{user_id}`)는 **이미 전 직원 대상**이다. 빠져 있던 것은
    "남의 아바타 주소를 알려 주는 payload" 하나뿐이라, 사진 기능이 있는데 **자기 우상단에만**
    보였다. 채팅·게시판·댓글 어디에도 남의 아바타 자리가 없었다 — 채팅이 먼저 메웠고,
    게시글·댓글은 `app/board/router.py::_people_of` 가 같은 것을 쓴다.

    건별 조회를 하지 않는다 — `people` payload 는 메시지 묶음·게시글 상세·목록마다 실려
    나가므로 N+1 이면 가장 뜨거운 경로가 바로 느려진다(H4 가 지적한 그 모양).

    지문(`?v=`)을 붙이는 이유는 `profiles/router._avatar_url` 과 같다: 없으면 사진을 바꿔도
    캐시 때문에 5분 동안 옛 사진이 보이고 사용자는 업로드가 실패한 줄 안다.
    """
    ids = [i for i in set(user_ids or ()) if i]
    if not ids:
        return {}
    from sqlalchemy import select

    from app.profiles.models import UserPreference

    rows = db.execute(
        select(UserPreference).where(
            UserPreference.user_id.in_(ids),
            UserPreference.avatar_stored_name.is_not(None),
        )
    ).scalars().all()
    out: dict[str, str] = {}
    for r in rows:
        stamp = int(r.avatar_updated_at.timestamp()) if r.avatar_updated_at else 0
        out[r.user_id] = f"/api/profile/avatar/{r.user_id}?v={stamp}"
    return out
