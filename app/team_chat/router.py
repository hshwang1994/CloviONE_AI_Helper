"""팀 채팅 API — 방 목록/생성(그룹·1:1)/메시지 폴링/전송/읽음/나가기/파하기 + 이미지 + 디렉터리.

순수 내부 기능(외부 호출 없음). 조회는 인증만, 상태변경은 CSRF. IDOR 차단: 1:1·그룹 방은 멤버만
접근(전체 채팅 방만 예외로 누구나). 폴링은 GET .../messages?since=<seq> 로 놀이와 같은 커서를 쓴다.

**이미지 서빙은 이 라우터에만 있다.** 게시판의 `GET /api/board/attachments/{id}` 는 로그인한
사람 누구에게나 첨부를 내준다(게시판은 조직 전체 공개라 맞는 설계다). 그 라우트를 채팅이
재사용하면 1:1 DM 이미지가 전사 공개가 된다 — 그래서 방 접근 검사를 먼저 하는 별도
라우트(`GET /messages/{message_id}/images/{image_id}`)를 두고, 접근 불가는 403이 아니라
**404**로 답한다(방/이미지의 존재 자체를 알려주지 않는다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import people, uploads
from app.core.audit import record_audit_from_request
from app.core.deps import AuthContext, get_current_auth, get_current_user, get_db, require_csrf
from app.core.errors import ForbiddenError, NotFoundError, RateLimitedError
from app.core.etag import etag_json_response
from app.core.feature_flags import load_feature_flags
from app.team_chat import repository, service
from app.team_chat.models import MSG_IMAGE, ROLE_OWNER, ROOM_DIRECT
from app.team_chat.schemas import (
    DirectCreate,
    GroupCreate,
    MemberInput,
    MembersInput,
    MessageCreate,
    ReadInput,
    RenameInput,
)
from app.users.models import User
from app.settings.gate import block_if_maintenance


def require_team_chat_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("team_chat_enabled", True):
        raise NotFoundError("팀 채팅 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/team-chat",
    tags=["team-chat"],
    dependencies=[Depends(require_team_chat_enabled), Depends(block_if_maintenance)],
)


def _room_title(room, members, names, me_id) -> str:
    if room.is_global:
        return room.title or "전체 채팅"
    if room.kind == ROOM_DIRECT:
        other = next((m.user_id for m in members if m.user_id != me_id), None)
        u = names.get(other)
        return (u.display_name if u else "대화") if other else "대화"
    return room.title or "채팅방"


def _last_preview(last) -> str:
    """목록 한 줄 미리보기. 이미지 메시지의 body 는 저장 파일명이라(붙여넣기는 'paste.png')
    그대로 내보내면 목록이 파일 탐색기처럼 읽힌다 — 무엇이 왔는지만 말한다."""
    if last is None:
        return ""
    if last.kind == MSG_IMAGE:
        return "사진"
    return last.body[:80]


def _room_summary(room, me_id, names, cursor, mem, last) -> dict:
    """목록 한 줄. **참여자와 마지막 메시지를 인자로 받는다** — 여기서 직접 조회하면
    방 하나당 질의 두 개가 붙어 목록이 곧 3N+3 이 된다(H4). 그 둘은 호출자가 방 전체를
    한 번에 읽어 넘긴다(repository.members_for_rooms / last_messages_for_rooms)."""
    my = next((m for m in mem if m.user_id == me_id), None)
    return {
        "id": room.id,
        "kind": room.kind,
        "is_global": room.is_global,
        # 팀 방은 그룹 방과 kind 가 같다(0039) — 화면이 "내 팀" 태그를 붙이려면 이 값이 필요하다.
        "department_id": getattr(room, "department_id", None),
        "title": _room_title(room, mem, names, me_id),
        "member_count": len(mem),
        "last_preview": _last_preview(last),
        "last_at": last.created_at.isoformat() if last else None,
        "seq": room.event_seq,
        # 전체 채팅 방은 멤버십 행이 없어 예전엔 항상 0이었다 — 이제 개인별 읽음 커서로 센다.
        "unread": service.unread_for(room, my, cursor),
    }


@router.get("/rooms")
def list_rooms(request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    # 내 팀 방을 보장한다(Q6) — 부서가 있으면 그 부서의 방이 늘 있고 나는 그 멤버다.
    # 목록을 여는 이 길목에서 하는 이유는 `service.ensure_team_room` 주석 참조.
    team = service.ensure_team_room(db, me, now=request.app.state.clock.now())
    rooms = repository.rooms_for_user(db, me.id)
    glob = repository.get_global_room(db)
    cursors = repository.cursors_for_user(db, me.id)
    # '나에게만 숨김'한 1:1 은 새 메시지가 오기 전까지 내 목록에서 뺀다(방은 그대로 남는다 —
    # dm_key 가 unique 라 soft-delete 하면 그 사람과 다시 대화를 시작할 수 없다).
    rooms = [r for r in rooms if not service.is_hidden_for(r, cursors.get(r.id))]

    # 아래 두 줄이 이 응답의 비용을 방 개수와 떼어 놓는다 (H4).
    # 이 목록은 **모든 화면에서** 주기적으로 돈다(사이드바 안 읽음 배지). 예전에는 방마다
    # 참여자와 마지막 메시지를 따로 물어 방이 늘수록 질의가 3배씩 늘었다 — SQLite 는
    # writer 가 하나라 사람이 늘면 이 경로가 먼저 막힌다. 이제 방 전체를 한 번에 읽는다.
    shown = [r for r in rooms if team is None or r.id != team.id]
    extra = [r for r in (team, glob) if r is not None]
    all_ids = [r.id for r in shown] + [r.id for r in extra]
    members_by_room = repository.members_for_rooms(db, all_ids)
    last_by_room = repository.last_messages_for_rooms(db, all_ids)
    # 상대 이름 해석을 위해 모든 방의 멤버 user_id 를 한 번에 읽는다.
    all_uids = {m.user_id for mem in members_by_room.values() for m in mem}
    names = repository.users_by_ids(db, list(all_uids))

    def summary(room):
        return _room_summary(
            room, me.id, names, cursors.get(room.id),
            members_by_room.get(room.id, []), last_by_room.get(room.id),
        )

    # 팀 방은 `items` 에서 뺀다 — 전체 채팅처럼 **따로 실어** 화면이 맨 위에 고정으로
    # 그린다. 목록 안에 섞이면 마지막 대화 시각 순으로 밀려 내려가고, "기본 방" 이라는
    # 성격이 사라진다.
    items = [summary(r) for r in shown]
    result = {"items": items}
    unread_total = sum(x["unread"] for x in items)
    if team is not None:
        result["team"] = summary(team)
        unread_total += result["team"]["unread"]
    if glob is not None:
        result["global"] = summary(glob)
        unread_total += result["global"]["unread"]
    # 사이드바 '채팅방' 항목의 합계 배지 — 새 폴링을 만들지 않고 이미 도는 이 응답에 실어 준다.
    result["unread_total"] = unread_total
    # 이 목록은 로그인한 사용자 전원의 브라우저가 60초마다 깨워 부른다 — 제품 전체에서
    # fanout 이 가장 큰 폴링이다. payload 는 이미 사용자별(멤버십·읽음 커서)로 다르므로
    # ETag 도 요청자마다 자연히 갈린다 - 공용 캐시가 아니다(app/core/etag.py 참고).
    return etag_json_response(request, result)


@router.post("/rooms", dependencies=[Depends(require_csrf)])
def create_group(request: Request, payload: GroupCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = service.create_group(db, me, title=payload.title, member_user_ids=payload.member_user_ids,
                                now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.create_group", object_type="chat_room",
                              object_id=room.id, after={"title": room.title})
    return {"room": {"id": room.id, "kind": room.kind, "title": room.title}}


@router.post("/rooms/direct", dependencies=[Depends(require_csrf)])
def create_direct(request: Request, payload: DirectCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = service.create_or_get_direct(db, me, other_user_id=payload.user_id, now=request.app.state.clock.now())
    return {"room": {"id": room.id, "kind": room.kind}}


def _get_room_or_404(db, room_id):
    room = repository.get_room(db, room_id)
    if room is None:
        raise NotFoundError("채팅방을 찾을 수 없습니다.")
    return room


def _image_view(img) -> dict:
    return {
        "id": img.id,
        # 인증·방 접근 검사를 하는 전용 서빙 경로. 게시판 첨부 URL을 절대 쓰지 않는다.
        "url": f"/api/team-chat/messages/{img.message_id}/images/{img.id}",
        "filename": img.filename,
        "media_type": img.media_type,
        "size_bytes": img.size_bytes,
    }


def _member_view(m, names, cursor, now, org_names=None, dnd_ids=frozenset()) -> dict:
    """참여자 한 줄 — 이름·소속·역할 + **읽음 위치**와 **접속 여부**.

    `last_read_seq` 는 1:1 읽음 표시가 쓰는 값이다(내 메시지의 seq 가 상대의 이 값 이하면
    '읽음'). 방 멤버만 이 응답을 받으므로 대화 상대끼리만 서로의 읽음 위치를 본다.

    `online` 은 이 방의 `last_seen` 기준이다 — '이 방을 열어 두고 있다'는 뜻이지 '앱에
    접속해 있다'가 아니다. 방 참여자 목록의 점이라 그 뜻이 맞다.

    `dept`/`title`/`org` 는 2026-08-04 지시로 추가했다. 방을 만들 때 쓰는 디렉터리
    (`/directory`)는 부서를 주는데 정작 **만들어진 방의 참여자 목록은 이름만** 줬다 —
    같은 이름 두 사람을 초대한 방에서 누가 누구인지 구분할 방법이 없었다.

    `archived` 도 `person` 에서 그대로 옮긴다 (N3, 교차 화면 감사). 이 함수는 `people.identity()`
    를 이미 부르면서 `archived` 를 계산해 놓고 응답에는 담지 않았다 — 그래서 같은 응답의
    `people`(말풍선이 읽는다, `_msg_view` 아래)에는 퇴사자가 "(보관됨)"으로 나오는데, 정확히
    같은 사람이 참여자 목록(`MemberStrip`/`ManageRoomModal`, `frontend/ChatRoomMembers.jsx`)
    에는 여전히 살아 있는 사람처럼 보였다. 답이 안 오는 대화를 며칠 기다리게 하는 그 침묵이다.
    """
    u = names.get(m.user_id)
    person = people.identity(u, org_names)
    return {
        "user_id": m.user_id,
        # `name` 은 기존 계약이라 유지한다(프런트 여러 곳이 이 키를 읽는다).
        "name": person["display_name"],
        "dept": person["dept"],
        "title": person["title"],
        "org": person["org"],
        "archived": person["archived"],
        "role": m.role,
        "last_read_seq": service.read_seq_for(m, cursor),
        # `online` 은 기존 계약이라 그대로 둔다(프런트 여러 곳이 읽는다).
        "online": service.is_online(m.last_seen, now),
        # `presence` 는 세 상태다 (X3). 방해금지를 켠 사람을 **오프라인으로 그리지 않는다** -
        # 그건 거짓말이고 거는 사람이 "자리에 없구나" 로 잘못 읽는다.
        "presence": service.presence_for(
            m.last_seen, now, dnd=m.user_id in dnd_ids
        ),
    }


def _msg_view(m, names, images=None, *, me=None) -> dict:
    """말풍선 한 개.

    `mentions_me` 를 **서버가** 판정하는 이유: 전체 채팅 방에서 프런트는 자기 표시 이름을
    모른다(참여자 목록이 없고 디렉터리는 본인을 뺀다). 그리고 멘션 규칙(경계·최장 일치)이
    양쪽에 따로 구현돼 있으면 '알림은 갔는데 화면엔 표시가 없는' 상태가 생긴다 —
    알림을 만드는 쪽과 같은 함수로 답한다. `@` 가 없으면 문자열 검사조차 하지 않는다.
    """
    u = names.get(m.sender_user_id) if m.sender_user_id else None
    body = m.body or ""
    mentions_me = bool(
        me is not None
        and m.sender_user_id != me.id
        and "@" in body
        and service.find_mentioned(body, {me.display_name: me.id})
    )
    return {
        "seq": m.seq, "kind": m.kind, "sender_user_id": m.sender_user_id,
        "sender_name": u.display_name if u else "",
        "body": m.body, "created_at": m.created_at.isoformat(),
        "mentions_me": mentions_me,
        "images": [_image_view(i) for i in (images or [])],
    }


@router.get("/rooms/{room_id}/messages")
def room_messages(request: Request, room_id: str, since: int = Query(default=0, ge=0),
                  idle: bool = Query(default=False),
                  db: Session = Depends(get_db), me: User = Depends(get_current_user),
                  auth: AuthContext = Depends(get_current_auth)):
    """`idle` 은 브라우저가 붙이는 신호다 (X12).

    참이면 폴링은 여전히 오지만 **접속 표시를 갱신하지 않는다** — 모니터만 끄고 간 사람의
    탭이 밤새 초록 점을 켜 두던 것이 그 때문이었다. 기본값은 거짓이라 이 파라미터를 안
    붙이는 옛 클라이언트는 예전과 똑같이 동작한다.

    이 값으로 **더 보여 주거나 덜 보여 주지 않는다.** 접근 판정은 아래 `ensure_access` 가
    그대로 한다 — 클라이언트가 보낸 말이 권한 결정에 끼어들면 그건 다른 종류의 결함이다.
    """
    room = _get_room_or_404(db, room_id)
    member = service.ensure_access(db, room, me)  # 멤버 아니면 403(전체 채팅만 예외)
    now = request.app.state.clock.now()
    # GET 이라 공용 임퍼소네이션 쓰기 차단을 안 지난다 — 여기서 안 막으면 관리자의 폴링이
    # 대상 사용자를 '접속 중'으로 켠다(team_docs record_view 와 같은 종류의 새는 구멍).
    if not auth.impersonating:
        service.touch_presence(db, room, me, now=now, idle=idle)
    msgs = repository.messages_since(db, room.id, since)
    mem = repository.members(db, room.id)
    names = repository.users_by_ids(db, list({m.sender_user_id for m in msgs if m.sender_user_id} | {m.user_id for m in mem}))
    # 이미지 메시지가 하나도 없으면 쿼리 자체를 건너뛴다(폴링이 매초 도는 경로다).
    img_ids = [m.id for m in msgs if m.kind == MSG_IMAGE]
    images = repository.images_for_messages(db, img_ids)
    # 멤버십 행이 없는 방(전체 채팅)의 읽음 위치는 커서에 있다 — 이 값이 0으로 고정돼 있으면
    # 프런트가 방을 열어 둔 내내 같은 seq 로 읽음 POST 를 반복한다(폴링마다 쓰기).
    # 방 전체 커서를 한 번에 읽는다(N+1 회피). 멤버가 있는 방은 커서가 대개 비어 있어 공짜다.
    cursors = repository.cursors_for_room(db, room.id)
    last_read = service.read_seq_for(member, cursors.get(me.id))
    is_owner = member is not None and member.role == ROLE_OWNER
    is_group = not room.is_global and room.kind != ROOM_DIRECT
    org_names = people.org_name_map(db)
    # 발신자 신원 맵 — 말풍선마다 부서를 실으면 같은 사람이 200번 반복된다(폴링 경로다).
    # 등장하는 사람 한 명당 한 줄만 보내고, 말풍선은 sender_user_id 로 여기서 찾아 쓴다.
    avatars = people.avatar_map(db, names.keys())
    # 방해금지도 한 번에 읽는다 - 참여자마다 질의하면 폴링 경로가 N+1 이 된다.
    dnd_ids = service.dnd_user_ids(db, [m.user_id for m in mem], now=now)
    return {
        "room": {"id": room.id, "kind": room.kind, "is_global": room.is_global,
                 # 목록(list_rooms/_room_summary)과 같은 값을 싣는다 — 없으면 화면이 목록에서는
                 # "내 팀" 태그를 붙이고 방 안(ChatRoom.jsx RoomDetailPanel)에서는 "그룹 N"이라
                 # 해, 같은 방인데 들어가는 순간 표식이 바뀌는 자기모순이 난다.
                 "department_id": getattr(room, "department_id", None),
                 "title": _room_title(room, mem, names, me.id), "member_count": len(mem)},
        "members": [_member_view(m, names, cursors.get(m.user_id), now, org_names, dnd_ids)
                    for m in mem],
        # 사진까지 한 번에 — 건별 조회를 하면 이 경로가 바로 N+1 이 된다(X13).
        "people": {
            uid: people.identity(u, org_names, avatars)
            for uid, u in names.items()
        },
        "messages": [_msg_view(m, names, images.get(m.id), me=me) for m in msgs],
        "seq": room.event_seq,
        "you": {"user_id": me.id, "display_name": me.display_name,
                "role": member.role if member else None,
                "last_read_seq": last_read, "is_member": member is not None,
                # 서버가 최종 판단한다 — 프런트 게이팅은 UX 일 뿐이다(파하기는 다시 검사한다).
                "can_disband": is_owner and is_group,
                "can_hide": (not room.is_global and room.kind == ROOM_DIRECT),
                # 이름 변경·초대·내보내기·방장 넘기기를 한 플래그로 묶는다 — 네 규칙이
                # 모두 같은 조건(그룹 방의 방장)이라 프런트가 각각 다시 계산할 이유가 없다.
                "can_manage": is_owner and is_group},
    }


@router.post("/rooms/{room_id}/messages", dependencies=[Depends(require_csrf)])
def send_message(request: Request, room_id: str, payload: MessageCreate,
                 db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    key = f"team-chat:{me.id}"
    if not request.app.state.chat_ratelimiter.allow(key):
        raise RateLimitedError("메시지를 너무 빨리 보냈습니다. 잠시 후 다시 시도하세요.",
                               retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(key))
    msg = service.send_message(db, room, me, body=payload.body,
                               client_message_id=payload.client_message_id, now=request.app.state.clock.now())
    return {"ok": True, "seq": msg.seq}


@router.post("/rooms/{room_id}/messages/{seq}/delete", dependencies=[Depends(require_csrf)])
def delete_message(request: Request, room_id: str, seq: int,
                   db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """내가 보낸 메시지 지우기. 응답의 `seq` 는 **방의 새 event_seq** 다(지운 메시지의 seq 가 아니다).

    POST 인 이유: 이 저장소의 상태변경은 전부 POST + CSRF 다(DELETE 는 쓰지 않는다).
    """
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    service.delete_message(db, room, me, seq=seq, now=request.app.state.clock.now())
    return {"ok": True, "seq": room.event_seq}


@router.post("/rooms/{room_id}/read", dependencies=[Depends(require_csrf)])
def mark_read(request: Request, room_id: str, payload: ReadInput,
              db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    service.mark_read(db, room, me, seq=payload.seq, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/leave", dependencies=[Depends(require_csrf)])
def leave(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    service.leave_room(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/disband", dependencies=[Depends(require_csrf)])
def disband(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """방 파하기 — 방장만. 전체 채팅은 409, 1:1 도 409(숨기기로 유도, service 주석 참고)."""
    room = _get_room_or_404(db, room_id)
    service.disband_room(db, room, me, now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.disband", object_type="chat_room",
                              object_id=room.id, after={"title": room.title})
    return {"ok": True}


@router.post("/rooms/{room_id}/hide", dependencies=[Depends(require_csrf)])
def hide(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """1:1 '나에게만 숨김' — 상대에게는 그대로 보이고, 새 메시지가 오면 내 목록에 다시 뜬다."""
    room = _get_room_or_404(db, room_id)
    service.hide_room(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


# ── 그룹 관리 (방장 전용 · 그룹 방만) ────────────────────────────────────────
#
# 네 동작 모두 service.ensure_can_manage_room 한 곳에서 판단한다. 라우터가 조건을 다시 쓰면
# 언젠가 한쪽만 고쳐져 '보이는데 누르면 403'이 된다.
#
# 초대 대상(사람)의 범위는 service.get_scoped_participants_or_404 가 판단한다 — 방 만들기·
# 초대·1:1 열기가 모두 그 함수로 사람을 찾는다. 조직 밖은 **404**(그 계정의 존재를 알려주지
# 않는다), 비멤버·비방장은 **403**(그건 범위가 아니라 권한 문제다).

@router.post("/rooms/{room_id}/rename", dependencies=[Depends(require_csrf)])
def rename_room(request: Request, room_id: str, payload: RenameInput,
                db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    before = room.title
    service.rename_room(db, room, me, title=payload.title, now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.rename", object_type="chat_room",
                              object_id=room.id, before={"title": before}, after={"title": room.title})
    return {"ok": True, "room": {"id": room.id, "title": room.title}}


@router.post("/rooms/{room_id}/members/add", dependencies=[Depends(require_csrf)])
def add_members(request: Request, room_id: str, payload: MembersInput,
                db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    added = service.add_members(db, room, me, user_ids=payload.user_ids,
                                now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.add_members", object_type="chat_room",
                              object_id=room.id, after={"added": len(added)})
    return {"ok": True, "added": len(added)}


@router.post("/rooms/{room_id}/members/remove", dependencies=[Depends(require_csrf)])
def remove_member(request: Request, room_id: str, payload: MemberInput,
                  db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.remove_member(db, room, me, user_id=payload.user_id,
                          now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.remove_member", object_type="chat_room",
                              object_id=room.id, after={"user_id": payload.user_id})
    return {"ok": True}


@router.post("/rooms/{room_id}/owner", dependencies=[Depends(require_csrf)])
def transfer_owner(request: Request, room_id: str, payload: MemberInput,
                   db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """방장 넘기기 — 자기 자신을 방장에서 내리는 유일한 정상 경로(주인 없는 방을 만들지 않는다)."""
    room = _get_room_or_404(db, room_id)
    service.transfer_owner(db, room, me, user_id=payload.user_id,
                           now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.transfer_owner", object_type="chat_room",
                              object_id=room.id, after={"user_id": payload.user_id})
    return {"ok": True}


# ── 이미지 (붙여넣기 업로드 · 접근 검사 후 서빙) ─────────────────────────────
@router.post("/rooms/{room_id}/images", dependencies=[Depends(require_csrf)])
def upload_image(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    file: UploadFile = File(...),
    client_message_id: str = Form(default=""),
):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    key = f"team-chat:{me.id}"
    if not request.app.state.chat_ratelimiter.allow(key):
        raise RateLimitedError("메시지를 너무 빨리 보냈습니다. 잠시 후 다시 시도하세요.",
                               retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(key))
    # sync 핸들러에서는 UploadFile의 내부 파일 객체를 직접 읽는다(await 불필요, 불변 §1).
    content = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    stored_name, media_type, size, display_name = uploads.save_upload(
        request.app.state.settings.data_dir,
        room.id,
        filename=file.filename or "image",
        content=content,
        namespace=uploads.NS_TEAM_CHAT,
        allowed_media_types=uploads.IMAGE_MEDIA_TYPES,  # 채팅 말풍선은 이미지만(PDF 불가)
    )
    msg, image = service.send_image_message(
        db, room, me, filename=display_name, stored_name=stored_name, media_type=media_type,
        size_bytes=size, client_message_id=(client_message_id or None),
        now=request.app.state.clock.now(),
    )
    return {"ok": True, "seq": msg.seq, "image": _image_view(image)}


@router.get("/messages/{message_id}/images/{image_id}")
def serve_image(
    request: Request,
    message_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """방 접근 검사를 통과한 사람에게만 원본 바이트를 준다.

    접근 불가는 403이 아니라 **404**다 — 403은 "그 방에 그런 이미지가 있다"를 확인해 준다.
    """
    msg = repository.get_message(db, message_id)
    image = repository.get_image(db, message_id, image_id) if msg is not None else None
    if msg is None or image is None:
        raise NotFoundError("이미지를 찾을 수 없습니다.")
    room = repository.get_room(db, msg.room_id)
    if room is None:
        raise NotFoundError("이미지를 찾을 수 없습니다.")  # 방이 파해졌으면 더는 서빙하지 않는다
    try:
        service.ensure_access(db, room, me)
    except ForbiddenError:
        raise NotFoundError("이미지를 찾을 수 없습니다.") from None
    path = uploads.attachment_path(
        request.app.state.settings.data_dir, image.room_id, image.stored_name,
        namespace=uploads.NS_TEAM_CHAT,
    )
    if path is None:
        raise NotFoundError("이미지 파일을 찾을 수 없습니다.")
    # nosniff + inline. 서버가 판정·저장한 media_type만 신뢰한다. 실행 불가.
    return FileResponse(
        str(path),
        media_type=image.media_type,
        headers={
            "Content-Disposition": uploads.content_disposition(image.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/directory")
def directory(request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """1:1 상대 고르기용 사용자 목록 — 이름·부서·직책만(이메일·역할·비밀은 절대 안 나감)."""
    users = repository.directory(db, me.id, org_id=getattr(me, "org_id", None))
    return {"users": [{"user_id": u.id, "display_name": u.display_name,
                       "dept": u.department or "", "title": u.title or ""} for u in users]}
