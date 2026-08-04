"""팀 채팅 비즈니스 규칙 — 방 생성(그룹/1:1) + append-only 메시지 로그 + 폴링 커서.

놀이(games)의 seq 할당기를 그대로 옮겼다: begin_nested 안에서 seq=event_seq+1 로 넣고, 유니크
(room_id, seq) 충돌은 SAVEPOINT로 흡수하고 재시도한다. 전체 채팅 방은 동시 전송이 몰려 seq 경쟁이
심하므로 재시도 횟수를 넉넉히 둔다. 1:1 방은 dm_key(정렬된 두 uid)로 유일하게 만들고, 동시 생성
경쟁은 유니크 위반을 잡아 승자를 다시 읽어 돌려준다. 외부 호출 없음(순수 내부 DB).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import people
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.presence import PRESENCE_THROTTLE_SECONDS, should_touch
from app.notifications.service import notify_user
from app.team_chat import repository
from app.team_chat.mentions import find_mentioned, mention_preview
from app.team_chat.models import (
    MSG_IMAGE,
    MSG_SYSTEM,
    MSG_TEXT,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROOM_DIRECT,
    ROOM_GROUP,
    ChatMessage,
    ChatMessageImage,
    ChatReadCursor,
    ChatRoom,
    ChatRoomMember,
)
from app.users.models import User

MAX_BODY = 2000
MAX_TITLE = 200
MAX_MEMBERS = 50  # 그룹 방 정원(스키마 제한이 아니라 화면·알림 팬아웃의 상한)
_SEQ_RETRIES = 12  # 전체 채팅은 seq 경쟁이 잦다 — 놀이(5)보다 넉넉히

# 초대 알림 유형 — 프런트 TYPE_KO / RELATED_DESTINATIONS 와 짝이다.
NOTI_CHAT_INVITED = "chat_invited"
NOTI_CHAT_MENTIONED = "chat_mentioned"
RELATED_CHAT_ROOM = "chat_room"
RELATED_CHAT_MENTION = "chat_mention"

# 온라인 점의 임계값. **presence 쓰기 스로틀(30초)보다 반드시 크게 잡는다** —
# app/core/presence.py 가 그 이유를 길게 적어 뒀다: 임계값이 스로틀에 가까우면 실제로 붙어
# 있는 사람이 '갱신 직전' 구간마다 오프라인으로 깜빡인다. 120초면 그 창 안에 최소 세 번은
# 찍힌다. 두 값의 관계(≥ 스로틀의 2배)는 테스트가 고정한다 — 여기서 import 한
# PRESENCE_THROTTLE_SECONDS 가 그 테스트가 보는 값이다.
ONLINE_SECONDS = 120.0
MIN_ONLINE_SECONDS = PRESENCE_THROTTLE_SECONDS * 2


def dm_key(a: str, b: str) -> str:
    return ":".join(sorted([a, b]))


def _append_message(db: Session, room: ChatRoom, *, kind: str, sender_id: str | None, body: str,
                    client_message_id: str | None, now: datetime) -> ChatMessage:
    for _ in range(_SEQ_RETRIES):
        seq = room.event_seq + 1
        msg = ChatMessage(
            room_id=room.id, seq=seq, sender_user_id=sender_id, kind=kind,
            body=body, client_message_id=client_message_id, created_at=now,
        )
        try:
            with db.begin_nested():
                db.add(msg)
                db.flush()
            room.event_seq = seq
            room.updated_at = now
            db.flush()
            return msg
        except IntegrityError:
            db.refresh(room)  # 다른 요청이 먼저 seq를 붙였다 — 다시 계산
    raise ConflictError("메시지를 보내지 못했습니다. 잠시 후 다시 시도해 주세요.")


def create_group(db: Session, user: User, *, title: str, member_user_ids: list[str], now: datetime) -> ChatRoom:
    title = (title or "").strip()
    if not title:
        raise ValidationAppError("방 이름을 입력하세요.")
    room = ChatRoom(kind=ROOM_GROUP, title=title[:200], created_by_user_id=user.id,
                    is_global=False, event_seq=0, created_at=now, updated_at=now)
    db.add(room)
    db.flush()
    # 만든 사람 = 방장, 지정한 사람들 = 멤버(중복·본인 제거).
    ids = {user.id, *[m for m in (member_user_ids or []) if m]}
    valid = set(repository.users_by_ids(db, list(ids)).keys())
    for uid in ids:
        if uid not in valid:
            continue
        db.add(ChatRoomMember(room_id=room.id, user_id=uid,
                              role=ROLE_OWNER if uid == user.id else ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=None))
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 채팅방을 만들었습니다.", client_message_id=None, now=now)
    _notify_invited(db, user, room, [uid for uid in ids if uid != user.id and uid in valid], now=now)
    return room


def _notify_invited(db: Session, inviter: User, room: ChatRoom, user_ids: list[str], *, now: datetime) -> None:
    """초대된 사람에게만 알림 — 초대한 본인은 제외한다(자기가 만든 방을 알림으로 다시 알릴 이유가 없다).

    related=("chat_room", room_id) 는 알림 벨의 딥링크 표(app/notifications/destinations.py)가
    `#/chat-rooms/<id>` 로 푸는 좌표다.
    """
    label = room.title.strip() if room.title else ""
    for uid in user_ids:
        notify_user(
            db,
            uid,
            type_=NOTI_CHAT_INVITED,
            title=f"{inviter.display_name}님이 대화에 초대했습니다.",
            body=(f"채팅방: {label}" if label else None),
            related=(RELATED_CHAT_ROOM, room.id),
            now=now,
        )


def _mention_candidates(db: Session, room: ChatRoom, sender: User) -> dict[str, str]:
    """이 방에서 `@이름` 으로 부를 수 있는 사람들(표시 이름 → user_id). 보낸 사람은 뺀다.

    전체 채팅 방은 멤버십 행이 없다 — 거기서 멘션을 못 쓰게 하면 정작 가장 필요한 자리에서
    빠진다. 그래서 그 방만 활성 사용자 디렉터리로 후보를 만든다(방 접근이 이미 전원 공개라
    새로 새는 정보가 없다). 멤버가 있는 방은 **멤버로 한정**한다 — 방 밖 사람을 부를 수 있으면
    그 사람은 열 수도 없는 방의 알림을 받는다.

    ## 동명이인 (2026-08-04 사용자 지시로 고쳤다)

    예전에는 표시 이름이 겹치면 **두 사람 다 후보에서 뺐다**. 임의로 한 명을 고르면 '누가
    받았는지 모르는 알림'이 되기 때문인데, 그 결과 동명이인은 **아무도 부를 수 없었다** —
    그것도 조용히. 부르는 쪽은 `@김하나` 라고 쳤는데 알림이 안 갔다는 사실조차 몰랐다.

    이제는 겹치는 이름만 소속을 붙여 갈라 놓는다: `김하나(플랫폼팀 선임)`, `김하나(인프라팀 선임)`.
    find_mentioned 가 **가장 긴 이름부터** 맞춰 보므로(mentions.py) 이 형태가 먼저 걸리고,
    괄호 없는 `@김하나` 는 어느 쪽에도 안 걸린다 — 애매한 채로 아무에게나 보내지 않는다는
    원래 원칙은 그대로다. 달라진 것은 **정확히 지목할 방법이 생겼다**는 것뿐이다.

    소속까지 같으면 이메일 아이디로 가른다(email 은 유일하므로 여기서 반드시 갈린다).
    """
    if room.is_global:
        users = repository.directory(db, sender.id)
    else:
        member_ids = [m.user_id for m in repository.members(db, room.id) if m.user_id != sender.id]
        users = list(repository.users_by_ids(db, member_ids).values())

    named: dict[str, list] = {}
    for u in users:
        name = (u.display_name or "").strip()
        if name:
            named.setdefault(name, []).append(u)

    out: dict[str, str] = {}
    for name, group in named.items():
        if len(group) == 1:
            out[name] = group[0].id
            continue
        by_label: dict[str, list] = {}
        for u in group:
            by_label.setdefault(people.affiliation(people.identity(u)) or "", []).append(u)
        for label, same in by_label.items():
            for u in same:
                tag = label if (label and len(same) == 1) else (u.email or "").split("@")[0]
                if not tag:
                    continue  # 가를 방법이 아예 없으면 부를 수 없는 채로 둔다(예전 동작)
                out[f"{name}({tag})"] = u.id
    return out


def notify_mentions(db: Session, room: ChatRoom, sender: User, msg: ChatMessage, *, now: datetime) -> list[str]:
    """본문에서 불린 사람에게 알림. 반환값은 실제로 알린 user_id 들(테스트·감사용).

    `@` 가 없으면 **쿼리 자체를 하지 않는다** — 전송은 폴링만큼 뜨겁지는 않지만, 멘션이 없는
    평범한 메시지가 사용자 목록 조회를 끌고 다닐 이유가 없다.
    """
    body = msg.body or ""
    if "@" not in body:
        return []
    targets = find_mentioned(body, _mention_candidates(db, room, sender))
    if not targets:
        return []
    label = _room_label(room)
    for uid in targets:
        notify_user(
            db,
            uid,
            type_=NOTI_CHAT_MENTIONED,
            title=f"{sender.display_name}님이 회원님을 언급했습니다.",
            body=(f"{label}: {mention_preview(body)}" if label else mention_preview(body)),
            # 목적지는 서버 표(app/notifications/destinations.py)가 계산한다 — 프런트에 if 를 늘리지 않는다.
            related=(RELATED_CHAT_MENTION, room.id),
            now=now,
        )
    return targets


def _room_label(room: ChatRoom) -> str:
    """알림 본문에 쓰는 방 이름. 1:1 은 제목이 비어 있어(상대 이름은 보는 사람마다 다르다)
    고정 문구를 쓴다 — 여기서 상대 이름을 넣으면 알림 저장 시점에 '누구 기준'인지가 굳어 버린다."""
    if room.is_global:
        return room.title.strip() or "전체 채팅"
    if room.kind == ROOM_DIRECT:
        return "1:1 대화"
    return room.title.strip() or "채팅방"


def create_or_get_direct(db: Session, user: User, *, other_user_id: str, now: datetime) -> ChatRoom:
    if not other_user_id or other_user_id == user.id:
        raise ValidationAppError("대화 상대를 선택하세요.")
    umap = repository.users_by_ids(db, [other_user_id])
    if other_user_id not in umap:
        raise ValidationAppError("대화 상대를 찾을 수 없습니다.")
    key = dm_key(user.id, other_user_id)
    existing = repository.get_direct_by_key(db, key)
    if existing is not None:
        # 내가 숨겨 뒀던 대화를 다시 열면 숨김을 푼다 — 그렇지 않으면 "1:1 대화 시작"이
        # 200을 돌려주는데 목록에는 아무것도 안 나타나는 유령 상태가 된다.
        unhide_room(db, existing, user)
        return existing
    room = ChatRoom(kind=ROOM_DIRECT, title="", created_by_user_id=user.id, is_global=False,
                    dm_key=key, event_seq=0, created_at=now, updated_at=now)
    try:
        with db.begin_nested():
            db.add(room)
            db.flush()
    except IntegrityError:
        # 동시 생성 경쟁에서 졌다 — 먼저 만들어진 방을 돌려준다.
        won = repository.get_direct_by_key(db, key)
        if won is not None:
            unhide_room(db, won, user)
            return won
        raise
    for uid in (user.id, other_user_id):
        db.add(ChatRoomMember(room_id=room.id, user_id=uid, role=ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=None))
    db.flush()
    _notify_invited(db, user, room, [other_user_id], now=now)
    return room


def ensure_access(db: Session, room: ChatRoom, user: User) -> ChatRoomMember | None:
    """방을 볼/쓸 수 있는지. 전체 채팅 방은 멤버십 없이 누구나(멤버 None 반환). 그 외는 멤버여야 한다."""
    if room.is_global:
        return None
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    return member


def send_message(db: Session, room: ChatRoom, user: User, *, body: str,
                 client_message_id: str | None, now: datetime) -> ChatMessage:
    body = (body or "").strip()
    if not body:
        raise ValidationAppError("메시지를 입력하세요.")
    if client_message_id:
        dup = repository.find_by_client_id(db, room.id, client_message_id[:64])
        if dup is not None:
            return dup  # 낙관적 전송 재시도 중복 제거 — 멘션 알림도 다시 보내지 않는다
    msg = _append_message(db, room, kind=MSG_TEXT, sender_id=user.id, body=body[:MAX_BODY],
                          client_message_id=(client_message_id or None), now=now)
    notify_mentions(db, room, user, msg, now=now)
    return msg


def delete_message(db: Session, room: ChatRoom, user: User, *, seq: int, now: datetime) -> ChatMessage:
    """**내** 메시지 지우기(soft delete) + 툼스톤 시스템 메시지로 `event_seq` 를 올린다.

    seq 를 올리는 것이 이 기능의 핵심이다. 행에 `deleted_at` 만 찍으면 이미 화면을 띄워 둔
    클라이언트는 다음 폴링에서 '새 이벤트 없음'(seq 그대로)을 받고 **지워진 말풍선을 계속
    보여 준다** — 그 사람에게는 삭제가 일어나지 않은 것과 같다. 새 시스템 메시지가 seq 를
    올려야 `since=<옛 seq>` 폴링이 변경을 받아 다시 읽는다.
    (tests/integration/test_team_chat_message_delete.py 가 이 성질을 고정한다.)

    툼스톤은 '지워진 자리'가 아니라 로그 끝에 붙는다 — 이 방의 메시지는 append-only 이고
    seq 는 곧 순서다. 이미 나간 seq 를 고쳐 쓰면 그 seq 를 받은 클라이언트마다 다른 내용을
    갖게 된다.
    """
    msg = repository.get_message_by_seq(db, room.id, seq)
    if msg is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    if msg.kind == MSG_SYSTEM:
        raise ConflictError("시스템 메시지는 삭제할 수 없습니다.")
    if msg.sender_user_id != user.id:
        # 존재는 이미 아는 사람(같은 방)이라 403 이 정보를 새로 흘리지 않는다.
        raise ForbiddenError("자기가 보낸 메시지만 삭제할 수 있습니다.")
    if msg.deleted_at is not None:
        return msg  # 멱등 — 재시도가 툼스톤을 두 개 만들지 않는다
    msg.deleted_at = now
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 메시지를 삭제했습니다.",
                    client_message_id=None, now=now)
    return msg


def send_image_message(db: Session, room: ChatRoom, user: User, *, filename: str,
                       stored_name: str, media_type: str, size_bytes: int,
                       client_message_id: str | None, now: datetime) -> tuple[ChatMessage, ChatMessageImage]:
    """붙여넣은 이미지 한 장 = 메시지 한 개(kind='image') + 이미지 행 한 개.

    본문(body)에는 새니타이즈된 표시용 파일명을 남긴다 — 그림을 못 그리는 자리(스크린리더
    alt, 감사, 나중의 검색)에서 무엇이 왔는지 남는 유일한 흔적이다. 목록 미리보기는 이 값을
    쓰지 않는다(붙여넣기 파일명은 'paste.png' 라 목록이 파일 탐색기처럼 읽힌다 —
    router._last_preview 가 '사진'으로 바꾼다).
    """
    if client_message_id:
        dup = repository.find_by_client_id(db, room.id, client_message_id[:64])
        if dup is not None:
            existing = repository.images_for_messages(db, [dup.id]).get(dup.id) or []
            if existing:
                return dup, existing[0]  # 낙관적 전송 재시도 중복 제거
    msg = _append_message(db, room, kind=MSG_IMAGE, sender_id=user.id,
                          body=filename[:MAX_BODY], client_message_id=(client_message_id or None), now=now)
    image = ChatMessageImage(
        message_id=msg.id, room_id=room.id, filename=filename, stored_name=stored_name,
        media_type=media_type, size_bytes=size_bytes, created_at=now,
    )
    db.add(image)
    db.flush()
    return msg, image


def unread_for(room: ChatRoom, member: ChatRoomMember | None, cursor: ChatReadCursor | None) -> int:
    """방 하나의 안읽음 — 멤버 방은 멤버 행이, 전체 채팅 방은 읽음 커서가 기준이다.

    커서가 아예 없으면(그 사용자가 전체 채팅을 한 번도 읽지 않았다) event_seq 전부가 안읽음이다.
    0으로 뭉개면 '새 메시지가 와도 영영 배지가 안 뜨는' 상태가 되므로 그렇게 하지 않는다.
    """
    return max(0, room.event_seq - read_seq_for(member, cursor))


def read_seq_for(member: ChatRoomMember | None, cursor: ChatReadCursor | None) -> int:
    """그 사람이 '어디까지 읽었는가'. 멤버 행이 있으면 그것이, 없으면(전체 채팅) 커서가 기준이다.

    **멤버 행이 있으면 커서를 보지 않는다.** 둘의 최댓값을 쓰면 안 된다: `hide_room` 이
    1:1 '나에게만 숨김'을 기록할 때 커서의 `last_read_seq` 에 그 시점 event_seq 를 박기 때문에,
    최댓값을 쓰면 **상대가 대화를 숨겼을 뿐인데 '읽음'으로 표시된다**(읽지 않은 것을 읽었다고
    말하는 것이라 읽음 표시 전체가 못 믿을 값이 된다).
    """
    if member is not None:
        return member.last_read_seq
    return cursor.last_read_seq if cursor is not None else 0


def is_online(last_seen: datetime | None, now: datetime) -> bool:
    """온라인 점 — `last_seen` 이 ONLINE_SECONDS 안이면 이 방을 보는 중으로 본다.

    여기서 말하는 '접속'은 **이 방을 열어 두고 폴링 중**이라는 뜻이다(다른 화면에 있는 사람은
    이 방의 last_seen 을 갱신하지 않는다). 방 참여자 목록의 점이라 그 뜻이 맞다.

    `last_seen` 이 NULL 이면 **아직 한 번도 열어 보지 않은 사람**이라 꺼진 점이다(0029).
    예전엔 멤버 행을 만들 때 joined_at 을 넣어서, 방금 초대된 사람이 초대된 줄도 모르는 채로
    2분 동안 '보는 중'으로 켜져 있었다. 한쪽으로 틀릴 수밖에 없다면 **꺼진 쪽으로** 튼다.

    미래 시각(시계 역행)은 온라인으로 본다 — 오프라인으로 보면 시계가 정상으로 돌아올 때까지
    붙어 있는 사람이 계속 꺼져 보인다.
    """
    if last_seen is None:
        return False
    elapsed = (now - last_seen).total_seconds()
    return elapsed < ONLINE_SECONDS


def mark_read(db: Session, room: ChatRoom, user: User, *, seq: int, now: datetime) -> None:
    """**읽을 때만** 쓴다. 폴링(GET messages)은 이 경로를 부르지 않는다.

    이미 그 seq 까지 읽은 상태면 아무것도 쓰지 않는다 — 프런트가 방을 열어 둔 채로 같은
    seq 로 반복 호출해도 UPDATE 가 나가지 않아야 한다(SQLite 쓰기 경합).
    """
    seq = min(max(0, seq), room.event_seq)
    member = repository.get_member(db, room.id, user.id)
    if member is not None:
        if seq > member.last_read_seq:
            member.last_read_seq = seq
            db.flush()
        return
    # 멤버십 행이 없는 방(전체 채팅) — 여기서 ChatRoomMember 를 게으르게 만들면
    # member_count 의 뜻이 '멤버 수'에서 '한 번이라도 연 사람 수'로 바뀐다. 커서만 쓴다.
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is None:
        if seq <= 0:
            return  # 읽을 게 없었다 — 빈 행을 만들지 않는다
        db.add(ChatReadCursor(room_id=room.id, user_id=user.id, last_read_seq=seq,
                              hidden_at=None, updated_at=now))
        db.flush()
        return
    if seq > cursor.last_read_seq:
        cursor.last_read_seq = seq
        cursor.updated_at = now
        db.flush()


def hide_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """1:1 '나에게만 숨김' — 방을 지우지 않고 내 목록에서만 감춘다.

    1:1 은 파할 수 없다(disband_room 주석 참고). 대신 지금 event_seq 를 커서에 박아 두고
    숨긴다 — 상대가 새 메시지를 보내면 event_seq 가 그보다 커져 목록에 다시 나타난다.
    """
    if room.is_global:
        raise ConflictError("전체 채팅방은 숨길 수 없습니다.")
    ensure_access(db, room, user)
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is None:
        cursor = ChatReadCursor(room_id=room.id, user_id=user.id, last_read_seq=room.event_seq,
                                hidden_at=now, updated_at=now)
        db.add(cursor)
    else:
        cursor.last_read_seq = room.event_seq
        cursor.hidden_at = now
        cursor.updated_at = now
    db.flush()


def unhide_room(db: Session, room: ChatRoom, user: User) -> None:
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is not None and cursor.hidden_at is not None:
        cursor.hidden_at = None
        db.flush()


def is_hidden_for(room: ChatRoom, cursor: ChatReadCursor | None) -> bool:
    """숨김은 '그때까지의 대화'에만 걸린다 — 새 메시지가 오면 방이 다시 보인다."""
    return cursor is not None and cursor.hidden_at is not None and room.event_seq <= cursor.last_read_seq


def disband_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """방 파하기(soft delete) — 방장만. 전체 채팅과 1:1 은 409.

    1:1 을 파하면 안 되는 이유(실제로 500을 만든다): `chat_rooms.dm_key` 는 unique 이고
    모든 조회가 `deleted_at IS NULL` 로 거른다. soft-delete 한 DM 은 조회에서 사라지지만
    유니크 인덱스에는 그대로 남는다 → 같은 상대와 다시 대화를 시작하면
    `create_or_get_direct` 가 방을 못 찾아 INSERT 하고, dm_key 충돌로 IntegrityError,
    except 절이 다시 읽어도 여전히 None → raise → **다음 1:1 이 500**.
    그래서 1:1 은 hide_room('나에게만 숨김')으로 보낸다. 정말 파하기를 지원하려면
    같은 트랜잭션에서 dm_key 를 NULL 로 만들어야 한다.
    """
    if room.is_global:
        raise ConflictError("전체 채팅방은 파할 수 없습니다.")
    if room.kind == ROOM_DIRECT:
        raise ConflictError("1:1 대화는 파할 수 없습니다. 내 목록에서 숨기기를 사용하세요.")
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    if member.role != ROLE_OWNER:
        raise ForbiddenError("방장만 채팅방을 파할 수 있습니다.")
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 채팅방을 파했습니다.", client_message_id=None, now=now)
    room.deleted_at = now
    db.flush()


def leave_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """방 나가기. 방장이 나가면 **주인 없는 방이 남지 않게** 승계하거나 방을 파한다.

    예전엔 멤버 행만 지웠다. 방장이 나가면 그 방은 이름을 바꿀 수도, 사람을 부를 수도, 파할
    수도 없는 채로 영원히 남았다(모든 관리 동작이 `role == owner` 를 요구한다). 남은 사람이
    할 수 있는 일은 자기도 나가는 것뿐이고, 그러면 아무도 없는 방이 목록에서만 사라진 채
    DB 에 남는다.

    규칙: 방장이 나가면 **가장 먼저 들어온 남은 멤버**가 방장이 된다(들어온 순서는 방에 대한
    맥락을 가장 많이 가진 순서다). 남은 멤버가 없으면 방을 파한다 — 아무도 없는 방을 살려 둘
    이유가 없고, 되살릴 경로도 없다.
    """
    if room.is_global:
        raise ConflictError("전체 채팅방은 나갈 수 없습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        return
    was_owner = member.role == ROLE_OWNER
    db.delete(member)
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 나갔습니다.", client_message_id=None, now=now)
    if not was_owner:
        return
    rest = sorted(repository.members(db, room.id), key=lambda m: (m.joined_at, m.id))
    if not rest:
        room.deleted_at = now  # 아무도 없는 방은 남기지 않는다
        db.flush()
        return
    heir = rest[0]
    heir.role = ROLE_OWNER
    db.flush()
    names = repository.users_by_ids(db, [heir.user_id])
    heir_name = names[heir.user_id].display_name if heir.user_id in names else "새 방장"
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{heir_name}님이 새 방장이 되었습니다.", client_message_id=None, now=now)


# ── 그룹 관리(방장 전용) ─────────────────────────────────────────────────────
#
# 권한 규칙은 한 곳(_require_owner)에서만 판단한다. 이름 변경·초대·내보내기·방장 넘기기가
# 각자 조건을 다시 쓰면 언젠가 하나만 고쳐지고, 그 순간 '보이는데 누르면 403'이 된다.
#
# 관리 대상은 **그룹 방뿐**이다:
#   * 전체 채팅 — 이름이 제품의 일부이고 멤버십 자체가 없다;
#   * 1:1 — 멤버가 정의상 둘이고, 이름은 보는 사람마다 상대 이름으로 계산된다.
# 둘 다 409 로 막는다(403 이 아니다 — 권한 문제가 아니라 그 방에는 없는 개념이다).

def _require_group(room: ChatRoom) -> None:
    if room.is_global:
        raise ConflictError("전체 채팅방은 관리할 수 없습니다.")
    if room.kind == ROOM_DIRECT:
        raise ConflictError("1:1 대화는 관리할 수 없습니다.")


def _require_owner(db: Session, room: ChatRoom, user: User) -> ChatRoomMember:
    _require_group(room)
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    if member.role != ROLE_OWNER:
        raise ForbiddenError("방장만 채팅방을 관리할 수 있습니다.")
    return member


def rename_room(db: Session, room: ChatRoom, user: User, *, title: str, now: datetime) -> ChatRoom:
    _require_owner(db, room, user)
    title = (title or "").strip()
    if not title:
        raise ValidationAppError("방 이름을 입력하세요.")
    title = title[:MAX_TITLE]
    if title == room.title:
        return room  # 같은 이름으로 저장해도 시스템 메시지를 만들지 않는다
    before = room.title
    room.title = title
    room.updated_at = now
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 방 이름을 ‘{before}’에서 ‘{title}’(으)로 바꿨습니다.",
                    client_message_id=None, now=now)
    return room


def add_members(db: Session, room: ChatRoom, user: User, *, user_ids: list[str], now: datetime) -> list[str]:
    """멤버 초대. 반환값은 **실제로 새로 들어온** user_id 들(이미 있던 사람은 조용히 건너뛴다).

    이미 멤버인 사람을 오류로 만들지 않는 이유: 초대 화면은 목록을 폴링하지 않으므로 두 사람이
    동시에 같은 사람을 부르는 일이 실제로 생긴다. 그때 요청 전체가 실패하면 함께 고른 다른
    사람들까지 못 들어온다.
    """
    _require_owner(db, room, user)
    wanted = [uid for uid in (user_ids or []) if uid]
    if not wanted:
        raise ValidationAppError("초대할 사람을 선택하세요.")
    existing = {m.user_id for m in repository.members(db, room.id)}
    valid = repository.users_by_ids(db, wanted)
    fresh = [uid for uid in dict.fromkeys(wanted) if uid in valid and uid not in existing]
    if len(existing) + len(fresh) > MAX_MEMBERS:
        raise ConflictError(f"한 방에는 최대 {MAX_MEMBERS}명까지 참여할 수 있습니다.")
    if not fresh:
        return []
    for uid in fresh:
        db.add(ChatRoomMember(room_id=room.id, user_id=uid, role=ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=None))
    db.flush()
    names = repository.users_by_ids(db, fresh)
    joined = ", ".join(names[uid].display_name for uid in fresh if uid in names)
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 {joined}님을 초대했습니다.",
                    client_message_id=None, now=now)
    _notify_invited(db, user, room, fresh, now=now)
    return fresh


def remove_member(db: Session, room: ChatRoom, user: User, *, user_id: str, now: datetime) -> None:
    """멤버 내보내기(방장 전용).

    **방장은 자기 자신을 내보낼 수 없다.** 그 경로를 열면 방장 없는 방이 만들어진다 — 남은
    사람은 이름 변경도, 초대도, 파하기도 못 한다(전부 방장 권한이다). 방장이 빠지고 싶으면
    `transfer_owner` 로 넘기거나, `leave_room`(자동 승계·마지막이면 파하기) 또는
    `disband_room` 을 쓴다.
    """
    _require_owner(db, room, user)
    if user_id == user.id:
        raise ConflictError("방장은 스스로 내보낼 수 없습니다. 방장을 넘기거나 방을 나가세요.")
    target = repository.get_member(db, room.id, user_id)
    if target is None:
        raise NotFoundError("그 사람은 이 채팅방의 참여자가 아닙니다.")
    names = repository.users_by_ids(db, [user_id])
    label = names[user_id].display_name if user_id in names else "참여자"
    db.delete(target)
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 {label}님을 내보냈습니다.",
                    client_message_id=None, now=now)


def transfer_owner(db: Session, room: ChatRoom, user: User, *, user_id: str, now: datetime) -> None:
    """방장 넘기기 — 넘긴 사람은 일반 멤버가 된다.

    '자기 자신을 방장에서 내리는' 유일한 정상 경로다. 방장 자리는 **항상 정확히 한 명**이어야
    하므로 내려놓기만 하는 동작은 없다(그건 주인 없는 방을 만든다).
    """
    me = _require_owner(db, room, user)
    if user_id == user.id:
        raise ConflictError("이미 방장입니다.")
    target = repository.get_member(db, room.id, user_id)
    if target is None:
        raise NotFoundError("그 사람은 이 채팅방의 참여자가 아닙니다.")
    target.role = ROLE_OWNER
    me.role = ROLE_MEMBER
    db.flush()
    names = repository.users_by_ids(db, [user_id])
    label = names[user_id].display_name if user_id in names else "참여자"
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 {label}님에게 방장을 넘겼습니다.",
                    client_message_id=None, now=now)


def touch_presence(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """실제 멤버만 last_seen 갱신. 전체 채팅 방은 멤버십이 없어 아무 것도 쓰지 않는다
    (모든 페이지에서 폴링하는 위젯이 매 조회마다 쓰기를 만들지 않게).

    스로틀은 2초에서 **30초**로 올렸다(app/core/presence.py). 2초는 폴링 주기와 거의 같아
    사실상 스로틀이 아니었고, 읽기 폴링이 그대로 쓰기 부하가 됐다 — SQLite writer 는 하나라
    사람이 늘수록 아무도 아무것도 안 하는 동안에도 쓰기 큐가 찬다.
    온라인 점의 임계값(계획 F)은 2분 이상으로 잡는다 — 30초면 그 창 안에 네 번은 찍혀서
    실제로 붙어 있는 사람이 깜빡이지 않는다."""
    if room.is_global:
        return
    member = repository.get_member(db, room.id, user.id)
    if member is not None and should_touch(member.last_seen, now):
        member.last_seen = now
        db.flush()
