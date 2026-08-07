"""홈 '오늘'이 조합하는 **기존 리더들** — 새 저장소도 새 표도 만들지 않는다.

계획서 Phase 5: *"홈 '오늘' 커맨드 센터: 신규 저장소 없이 기존 리더 조합(GET /api/home/today)"*.
그래서 이 파일에는 SELECT 뿐이고 INSERT/UPDATE 가 한 줄도 없다. 각 함수는 이미 다른 화면이
쓰고 있는 표를 같은 규칙으로 다시 읽을 뿐이다:

  * 알림       → app/notifications/service.unread_count (알림 벨과 같은 값)
  * 채팅       → app/team_chat 의 저장소 + unread_for (채팅방 목록과 같은 규칙: 숨긴 1:1 제외,
                 전체 채팅 방 포함). 안읽음 계산을 여기서 다시 구현하지 않는다 — 두 벌이 되면
                 사이드바 배지와 홈 숫자가 서로 다른 말을 한다.
  * 문서       → team_docs 캐시(archived 제외, last_edited 내림차순) — 문서 목록의 '최근 수정순'과 동일
  * 게시판     → board 저장소 list_posts(sort=recent) — 자유게시판 첫 페이지와 동일

티켓은 여기 없다. 티켓은 반드시 저장소 seam(app/tickets/service + repository)을 통해서만
읽는다 — Notion 구현 모듈을 직접 import 하면 정적 검사가 막는다(scripts/static_checks.sh).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.board import repository as board_repo
from app.board.models import Post
from app.core.feature_flags import load_feature_flags
from app.notifications.service import unread_count
from app.team_docs.models import DocumentCache

# 홈은 '무엇을 볼지 고르는' 화면이라 목록을 길게 싣지 않는다. 전체는 각 화면이 갖고 있다.
RECENT_LIMIT = 5


def notifications_unread(db: Session, user_id: str) -> int:
    """안 읽은 알림 수 — 상단 알림 벨(/api/notifications/unread-count)과 같은 함수를 쓴다."""
    return unread_count(db, user_id)


def chat_unread(db: Session, user, *, config_dir) -> int | None:
    """안 읽은 채팅 수(전체 합계). 기능 플래그가 꺼져 있으면 **0이 아니라 None** 을 준다.

    0 과 None 은 다른 뜻이다: 0 은 '다 읽었다', None 은 '이 설치에는 채팅이 없다'. 꺼진 기능을
    0 으로 그리면 화면에 영영 0 인 칸이 하나 남는다.

    계산 규칙은 GET /api/team-chat/rooms 와 같다 — '나에게만 숨김'한 1:1 은 빼고, 멤버십 행이
    없는 전체 채팅 방은 개인 읽음 커서로 센다. team_chat 모듈은 읽기만 한다(쓰기 없음).
    """
    if not load_feature_flags(config_dir).get("team_chat_enabled", True):
        return None
    from app.team_chat import repository as chat_repo
    from app.team_chat import service as chat_service

    cursors = chat_repo.cursors_for_user(db, user.id)
    rooms = [
        r for r in chat_repo.rooms_for_user(db, user.id)
        if not chat_service.is_hidden_for(r, cursors.get(r.id))
    ]
    # 방마다 get_member 를 따로 물으면 방 개수만큼 질의가 붙는다(M2, H4 와 같은 함정) —
    # 한 번에 읽는다. GET /api/team-chat/rooms 가 이미 같은 방식으로 고쳤다(members_for_rooms).
    members = chat_repo.members_for_rooms_and_user(db, [r.id for r in rooms], user.id)
    total = 0
    for room in rooms:
        total += chat_service.unread_for(room, members.get(room.id), cursors.get(room.id))
    glob = chat_repo.get_global_room(db)
    if glob is not None:
        total += chat_service.unread_for(glob, None, cursors.get(glob.id))
    return total


def recent_documents(db: Session, *, limit: int = RECENT_LIMIT) -> list[dict]:
    """최근 수정된 팀 문서. 문서 목록 화면의 기본 정렬(recent)과 같은 순서를 쓴다.

    last_edited 는 Notion 이 준 ISO 문자열이라 사전순 정렬이 곧 시간순이다(모델 주석 참조).
    """
    rows = db.execute(
        select(DocumentCache)
        .where(DocumentCache.archived.is_(False))
        .order_by(DocumentCache.last_edited.desc().nulls_last(), DocumentCache.title.asc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            # 화면 딥링크(#/team-docs/:id)가 쓰는 키와 같아야 한다 — 문서 API 의 id 는 page id 다.
            "id": r.notion_page_id,
            "title": r.title or "(제목 없음)",
            "document_type": r.document_type,
            "owner": r.owner or "",
            "last_edited": r.last_edited,
        }
        for r in rows
    ]


def recent_board_posts(db: Session, *, limit: int = RECENT_LIMIT) -> list[dict]:
    """자유게시판 최신 글. board 저장소를 그대로 쓴다(고정글 우선 + 최신순 = 게시판 첫 화면)."""
    rows, _total = board_repo.list_posts(
        db, category=None, search=None, sort="recent", offset=0, limit=limit
    )
    names = board_repo.author_names(db, {p.author_user_id for p in rows})
    return [
        {
            "id": p.id,
            "title": p.title,
            "category": p.category,
            "author_name": names.get(p.author_user_id, ""),
            "is_pinned": bool(p.is_pinned),
            "comment_count": board_repo.comment_count(db, p.id),
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


def documents_changed_between(
    db: Session, since_iso: str, until_iso: str, *, limit: int = RECENT_LIMIT
) -> dict:
    """주간 다이제스트용 — 창 안에 **수정된** 문서 {count, items}.

    ## 이 함수가 M4 였다 (인자를 둘로 늘린 이유)

    예전에는 인자가 하나였고 그 값이 'YYYY-MM-DD' 라는 **KST 달력일**이었다. 그런데
    `last_edited` 는 Notion 이 준 **UTC** 문자열이다. 축이 다른 두 값을 그대로 비교하면
    KST 는 UTC+9 라 **월요일 오전 9시 이전에 고친 문서가 통째로 빠진다** — '2026-08-03'
    보다 '2026-08-02T21:00:00.000Z'(KST 월요일 06:00)가 사전순으로 앞이기 때문이다.
    위쪽 경계는 아예 없어서 반대로 **다음 주에 고친 문서가 이번 주에 끼었다**.

    화면에는 그럴듯한 숫자가 떠 있어서 아무도 신고하지 않는다. 그래서 경계를 양쪽 다
    받는다. 경계를 만드는 일은 이 파일이 하지 않고 `home.service.utc_iso_bounds` 한 곳이
    한다 — 변환이 두 벌이 되면 갈라진 쪽이 다시 조용히 틀린다(바로 아래
    `board_posts_between` 이 이미 같은 규약이다).

    `since_iso` / `until_iso` 는 그 함수가 준 naive UTC ISO 문자열이다(예
    '2026-08-02T15:00:00'). 문자열로 자르는 근거는 그 함수의 주석에 적어 뒀다.
    """
    base = (
        DocumentCache.archived.is_(False),
        DocumentCache.last_edited >= since_iso,
        DocumentCache.last_edited < until_iso,
    )
    total = db.execute(
        select(func.count()).select_from(DocumentCache).where(*base)
    ).scalar_one()
    rows = db.execute(
        select(DocumentCache)
        .where(*base)
        .order_by(DocumentCache.last_edited.desc(), DocumentCache.title.asc())
        .limit(limit)
    ).scalars().all()
    return {
        "count": int(total),
        "items": [
            {"id": r.notion_page_id, "title": r.title or "(제목 없음)",
             "document_type": r.document_type, "owner": r.owner or "",
             "last_edited": r.last_edited}
            for r in rows
        ],
    }


def board_posts_between(
    db: Session, since_utc, until_utc, *, limit: int = RECENT_LIMIT
) -> dict:
    """주간 다이제스트용 — 창 안에 **작성된** 게시글 {count, items}.

    경계는 naive UTC 로 받는다(created_at 이 그 형식이다). KST↔UTC 변환은 호출측
    home.service.window_utc_bounds 한 곳에서만 한다.
    """
    base = (
        Post.deleted_at.is_(None),
        Post.created_at >= since_utc,
        Post.created_at < until_utc,
    )
    total = db.execute(select(func.count()).select_from(Post).where(*base)).scalar_one()
    rows = db.execute(
        select(Post).where(*base).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit)
    ).scalars().all()
    names = board_repo.author_names(db, {p.author_user_id for p in rows})
    return {
        "count": int(total),
        "items": [
            {"id": p.id, "title": p.title, "category": p.category,
             "author_name": names.get(p.author_user_id, ""),
             "created_at": p.created_at.isoformat()}
            for p in rows
        ],
    }


def assignee_candidates(db: Session) -> list[dict]:
    """배정 후보 [{user_id, display_name}] — /api/tickets/assignees 와 같은 조건.

    트리아지 '제안'이 쓰는 후보 집합이다. raw Notion id 는 싣지 않는다(§12.3).
    tickets.service.list_assignees 를 그대로 쓰지 않는 이유는 없다 — 그대로 쓴다.
    """
    from app.tickets.service import list_assignees

    return list_assignees(db)
