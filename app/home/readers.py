"""홈 '오늘'이 조합하는 **기존 리더들** — 새 저장소도 새 표도 만들지 않는다.

계획서 Phase 5: *"홈 '오늘' 커맨드 센터: 신규 저장소 없이 기존 리더 조합(GET /api/home/today)"*.
그래서 이 파일에는 SELECT 뿐이고 INSERT/UPDATE 가 한 줄도 없다. 각 함수는 이미 다른 화면이
쓰고 있는 표를 같은 규칙으로 다시 읽을 뿐이다:

  * 알림       → app/notifications/service.unread_count (알림 벨과 같은 값)
  * 채팅       → app/team_chat 의 저장소 + unread_for (채팅방 목록과 같은 규칙: 숨긴 1:1 제외,
                 전체 채팅 방 포함). 안읽음 계산을 여기서 다시 구현하지 않는다 — 두 벌이 되면
                 사이드바 배지와 홈 숫자가 서로 다른 말을 한다.
  * 문서       → knowledge 정본 documents(archived 제외, updated_at 내림차순) — 문서 목록의
                 기본 정렬과 같다. 옛 미러(document_cache)는 안 읽는다(S14 · D1).
  * 게시판     → board 저장소 list_posts(sort=recent) — 자유게시판 첫 페이지와 동일

티켓은 여기 없다. 티켓은 반드시 저장소 seam(app/tickets/service + repository)을 통해서만
읽는다 — Notion 구현 모듈을 직접 import 하면 정적 검사가 막는다(scripts/static_checks.sh).
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.dates import iso_dt, parse_dt
from app.board import repository as board_repo
from app.board.models import Post
from app.core.db import batched
from app.core.feature_flags import load_feature_flags
from app.notifications.service import unread_count

# 홈은 '무엇을 볼지 고르는' 화면이라 목록을 길게 싣지 않는다. 전체는 각 화면이 갖고 있다.
RECENT_LIMIT = 5


def _display_names(db: Session, user_ids) -> dict[str, str]:
    """`user_id -> 표시 이름` — 질의 한 번. 없는 id 는 그냥 빠진다(빈 이름이 된다)."""
    from app.users.models import User

    wanted = sorted({str(uid) for uid in user_ids if uid})
    if not wanted:
        return {}
    out: dict[str, str] = {}
    for batch in batched(wanted):
        rows = db.execute(
            select(User.id, User.display_name).where(User.id.in_(batch))
        ).all()
        out.update({str(uid): (name or "") for uid, name in rows})
    return out


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


def recent_documents(db: Session, *, limit: int = RECENT_LIMIT, viewer=None) -> list[dict]:
    """최근 수정된 문서. **정본은 `documents` 다** (S14 · D1).

    예전에는 Notion 미러(`document_cache`)를 읽었다. 이관 뒤 그 표는 제목이 110행 전부 빈
    문자열이라, 이 위젯이 「(제목 없음)」 다섯 줄을 그리고 있었다. 정본을 읽으면 그 자리에
    실제 제목이 들어간다.

    정렬 축은 `updated_at` 이고, 문서 목록 화면
    (`app/knowledge/service.py::list_documents`)이 쓰는 것과 같은 축이다. 두 화면이 다른
    축으로 세우면 "목록 맨 위에 있는 문서가 홈에는 없다" 가 된다.

    가시성 판정은 문서가 아니라 **공간**이 한다(D-245). 그래서 `doc_in_scope` 가 아니라
    `RESOURCE_KNOWLEDGE_DOC` 의 가시성 절을 그대로 쓴다 — 목록 API 가 지나는 바로 그
    함수라, 홈만 다른 답을 낼 자리가 없다. 조건이 SQL 이라 상한 **앞에** 걸리고, 예전처럼
    넉넉히 오버페치해 파이썬에서 거를 이유도 사라졌다.

    휴지통은 아직 옛 page id 로 담기므로 `legacy_page_id` 로 맞춰 본다 — 옛 화면에서 지운
    문서가 새 위젯으로 되살아나면 그 카드는 열리지 않는 링크가 된다.
    """
    from app.knowledge.models import Document
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    trashed = trash_repo.trashed_page_ids(db, TRASH_DOCUMENT)
    stmt = (
        select(Document)
        .where(Document.archived.is_(False))
        .order_by(Document.updated_at.desc(), Document.title.asc())
    )
    # UA-24: `trashed`를 통째로 한 NOT IN에 박으면 호스트 변수 상한을 넘는 순간 이 쿼리가,
    # 곧 홈 전체가 처리 안 된 500이 된다 — 오래 쓴 설치일수록 휴지통은 계속 쌓이기만 하므로
    # "지금 안 넘는다"가 안전을 보장하지 않는다. NOT IN 여러 개를 이어 붙이면(.where()를
    # 반복 호출하면 AND로 묶인다) 의미가 그대로 보존된다 —
    # `x NOT IN A AND x NOT IN B` ≡ `x NOT IN (A ∪ B)`.
    for batch in batched(list(trashed)):
        stmt = stmt.where(
            or_(Document.legacy_page_id.is_(None), Document.legacy_page_id.notin_(batch))
        )
    if viewer is not None:
        from app.authz.visibility import (
            RESOURCE_KNOWLEDGE_DOC,
            context_for_user,
            effective_visibility_clause,
        )

        clause = effective_visibility_clause(context_for_user(db, viewer), RESOURCE_KNOWLEDGE_DOC)
        if clause is not None:
            stmt = stmt.where(clause)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    # 옛 미러의 `owner` 는 Notion 이 준 표시 이름 문자열이었다. 자체 DB 에는 만든 사람의
    # 계정 참조(`created_by`)만 있으므로 이름은 여기서 **한 번에** 붙인다 — 행마다 물으면
    # 그대로 N+1 이다.
    owner_names = _display_names(db, [r.created_by for r in rows])
    return [
        {
            # 화면 딥링크(/knowledge/:id)가 쓰는 키와 같아야 한다.
            "id": document.id,
            "title": document.title or "(제목 없음)",
            "document_type": document.doc_type,
            "owner": owner_names.get(document.created_by, ""),
            "last_edited": iso_dt(document.updated_at),
        }
        for document in rows
    ]


def recent_board_posts(db: Session, *, limit: int = RECENT_LIMIT, org_id: str | None = None) -> list[dict]:
    """자유게시판 최신 글. board 저장소를 그대로 쓴다(고정글 우선 + 최신순 = 게시판 첫 화면).

    SEC-12: 게시판의 모든 실제 경로(`board/router.py`)는 `_viewer_org_id(me)`로 조직
    게이트를 지나는데 이 위젯만 `org_id` 없이 불렀다 — `list_posts`가 이미 그 인자를
    받으므로 그대로 전달한다(가려야 할 글이 새 SQL 없이 걸러진다).
    """
    rows, _total = board_repo.list_posts(
        db, category=None, search=None, sort="recent", offset=0, limit=limit, org_id=org_id
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
    db: Session, since_iso: str, until_iso: str, *, limit: int = RECENT_LIMIT, viewer=None
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

    UA-09: `archived`만 보고 휴지통은 안 걸렀다 — `recent_documents`가 정확히 같은 이유로
    이미 고쳐진 자리인데(주석 참조), 여기는 형제 함수라 안 옮겨졌다. 휴지통에 있는 문서가
    "이번 주 바뀐 문서"로 과다 집계되고, `AssistantPanel.jsx`가 그 항목을 클릭 가능한
    링크로 그려서 누르면 404였다. 그 UA-09 수정이 트래시만 옮기고 **똑같이 형제 관계인
    다른 결함(아래)은 안 옮겼다** — 나중에 재감사로 다시 확인됨.

    whole-product 재감사(2026-08-13): `recent_documents`가 이미 막은 SEC-13(부서 범위
    밖 문서 유출)·SEC-10(`restricted` 문서 유출) 판정(`doc_in_scope`)이 이 형제 함수에는
    여전히 없었다 — `GET /api/assistant/weekly-digest`(role 게이트 없음, 로그인만 요구)로
    누구나 회사 전체 이번 주 변경 문서(제한 문서 포함, 타 부서 포함)의 제목·유형·소유자·
    수정 시각을 봤다. `viewer`를 받아 같은 판정을 적용한다.

    `count`는 "상위 N건 미리보기"가 아니라 다이제스트가 그대로 보여주는 **정확한 총
    건수**다. 그래서 세는 질의와 보여 주는 질의가 **같은 조건**에서 갈라져 나온다 —
    조건이 두 벌이 되면 "3건이라는데 목록에는 1건" 이 된다.

    S14: `recent_documents` 와 **같은 이유로** 정본(`documents`)을 읽는다. 형제 함수 둘이
    다른 표를 읽으면 "홈에는 있는데 주간 요약에는 없다" 가 되고, 그 어긋남은 조용하다.
    창 경계도 그 위젯과 같은 축(`updated_at`)에 건다. 가시성은 `RESOURCE_KNOWLEDGE_DOC`
    절이라 SQL 이고, 그래서 `count` 를 세기 전에 이미 걸려 있다 — 파이썬으로 거른 뒤 세던
    예전 관용구가 필요 없어졌다.
    """
    from app.knowledge.models import Document
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    trashed = trash_repo.trashed_page_ids(db, TRASH_DOCUMENT)
    scoped = (
        select(Document)
        .where(
            Document.archived.is_(False),
            # 창 경계는 naive UTC ISO 문자열로 들어온다(`home.service.utc_iso_bounds`).
            Document.updated_at >= parse_dt(since_iso),
            Document.updated_at < parse_dt(until_iso),
        )
    )
    for batch in batched(list(trashed)):
        scoped = scoped.where(
            or_(Document.legacy_page_id.is_(None), Document.legacy_page_id.notin_(batch))
        )
    if viewer is not None:
        from app.authz.visibility import (
            RESOURCE_KNOWLEDGE_DOC,
            context_for_user,
            effective_visibility_clause,
        )

        clause = effective_visibility_clause(context_for_user(db, viewer), RESOURCE_KNOWLEDGE_DOC)
        if clause is not None:
            scoped = scoped.where(clause)
    total = db.execute(
        select(func.count()).select_from(scoped.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(
        scoped.order_by(Document.updated_at.desc(), Document.title.asc()).limit(limit)
    ).scalars().all()
    owner_names = _display_names(db, [r.created_by for r in rows])
    return {
        "count": int(total),
        "items": [
            {"id": r.id, "title": r.title or "(제목 없음)",
             "document_type": r.doc_type, "owner": owner_names.get(r.created_by, ""),
             "last_edited": iso_dt(r.updated_at)}
            for r in rows
        ],
    }


def board_posts_between(
    db: Session, since_utc, until_utc, *, limit: int = RECENT_LIMIT, org_id: str | None = None
) -> dict:
    """주간 다이제스트용 — 창 안에 **작성된** 게시글 {count, items}.

    경계는 naive UTC 로 받는다(created_at 이 그 형식이다). KST↔UTC 변환은 호출측
    home.service.window_utc_bounds 한 곳에서만 한다.

    whole-product 재감사(2026-08-13): 이 함수는 `Post`를 직접 `select`해
    `board_repo.visible_posts`(게시글 가시성 판정이 모이는 단 하나의 자리 — 그 docstring이
    "판정이 두 벌이 되면 한쪽만 고쳐지고... 실제로 그랬다(3순위 IDOR)"고 스스로 경고한다)를
    완전히 건너뛰고 있었다 — `org_id`를 받지도 않았다. `GET /api/assistant/weekly-digest`
    (role 게이트 없음, 로그인만 요구)로 누구나 회사 밖 게시글까지 "이번 주 작성된 글"로
    그대로 봤다(형제 함수 `recent_board_posts`는 SEC-12로 이미 `org_id`를 받는다). 조건을
    다시 적지 않고 `visible_posts(org_id)`를 그대로 기반으로 쓴다.
    """
    time_window = (Post.created_at >= since_utc, Post.created_at < until_utc)
    scoped = board_repo.visible_posts(org_id).where(*time_window)
    total = db.execute(select(func.count()).select_from(scoped.subquery())).scalar_one()
    rows = db.execute(
        scoped.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit)
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


def assignee_candidates(db: Session, *, org_id: str | None = None) -> list[dict]:
    """배정 후보 [{user_id, display_name}] — /api/tickets/assignees 와 같은 조건.

    트리아지 '제안'이 쓰는 후보 집합이다. raw Notion id 는 싣지 않는다(§12.3).
    tickets.service.list_assignees 를 그대로 쓰지 않는 이유는 없다 — 그대로 쓴다.

    whole-product 재감사(2026-08-13): `list_assignees`의 `org_id` 인자는 optional
    (`if org_id:`)이라 여기서 안 넘기면 조용히 전체 조직이 다 나온다 — 실제 배정
    엔드포인트(`/api/tickets/assignees`, `tickets/router.py`)는 이미
    `org_id=getattr(user,"org_id",None)`을 넘기는데 이 형제 소비처(`GET /api/assistant/
    triage`, role 게이트 없음)는 안 넘겨서, 트리아지 제안이 타 조직 실제 재직자 이름/id를
    그대로 후보로 냈다. 호출측(`assistant/facts.py::triage_facts`)에서 넘긴다.
    """
    from app.tickets.service import list_assignees

    return list_assignees(db, org_id=org_id)
