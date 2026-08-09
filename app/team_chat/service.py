"""팀 채팅 비즈니스 규칙 — 방 생성(그룹/1:1) + append-only 메시지 로그 + 폴링 커서.

놀이(games)의 seq 할당기를 그대로 옮겼다: begin_nested 안에서 seq=event_seq+1 로 넣고, 유니크
(room_id, seq) 충돌은 SAVEPOINT로 흡수하고 재시도한다. 전체 채팅 방은 동시 전송이 몰려 seq 경쟁이
심하므로 재시도 횟수를 넉넉히 둔다. 1:1 방은 dm_key(정렬된 두 uid)로 유일하게 만들고, 동시 생성
경쟁은 유니크 위반을 잡아 승자를 다시 읽어 돌려준다. 외부 호출 없음(순수 내부 DB).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import people
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.presence import PRESENCE_THROTTLE_SECONDS, should_touch
from app.notifications.service import notify_user
from app.org.models import Department
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


def ensure_team_room(db: Session, user: User, *, now: datetime) -> ChatRoom | None:
    """이 사용자의 **부서 방**을 보장한다. 없으면 만들고, 멤버가 아니면 넣는다.

    사용자 지적 Q6: "홈 및 채팅방에 default 로 만들어진 방은 기본적으로 내 팀임."
    지금까지 기본으로 있던 방은 `전체 채팅` 하나뿐이었다 — 회사 전체는 매일 쓰는 단위가
    아니다. 사람들이 실제로 대화하는 단위는 자기 팀이다.

    **게으르게 만든다.** 마이그레이션이 미리 만들면 그 뒤에 생기는 부서에는 방이 없고,
    부서가 생길 때마다 마이그레이션을 하나씩 더 써야 한다. 방 목록을 여는 길목에서
    보장하면 부서를 언제 만들든 한 번은 지나간다.

    부서가 없는 사용자는 `None` 이다 — 없는 팀의 방을 만들어 주지 않는다.
    """
    dept_id = getattr(user, "department_id", None)
    if not dept_id:
        return None

    room = repository.get_team_room(db, dept_id)
    if room is None:
        dept = db.get(Department, dept_id)
        if dept is None:
            return None  # 지워진 부서를 가리키는 사용자. 방을 만들 근거가 없다.
        room = ChatRoom(
            kind=ROOM_GROUP, title=dept.name[:200], created_by_user_id=None,
            is_global=False, department_id=dept_id, event_seq=0,
            created_at=now, updated_at=now,
        )
        try:
            # 두 사람이 동시에 목록을 열면 둘 다 "없다" 를 보고 각자 만들려 한다.
            # 1:1 방(dm_key)과 같은 관용으로 SAVEPOINT 를 두고, 졌으면 이긴 쪽 방을 쓴다.
            with db.begin_nested():
                db.add(room)
                db.flush()
        except IntegrityError:
            room = repository.get_team_room(db, dept_id)
            if room is None:
                return None
    else:
        # 부서 이름이 바뀌면 방 이름도 따라간다 — 팀 방의 이름은 팀 이름이지 별도 값이 아니다.
        dept = db.get(Department, dept_id)
        if dept is not None and room.title != dept.name[:200]:
            room.title = dept.name[:200]
            room.updated_at = now

    if repository.get_member(db, room.id, user.id) is None:
        db.add(ChatRoomMember(room_id=room.id, user_id=user.id, role=ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=None))
        db.flush()
    return room


def get_scoped_participants_or_404(db: Session, actor: User, user_ids: list[str]) -> dict[str, User]:
    """`user_ids` 중 **actor 가 자기 방에 들일 수 있는** 사람들. 범위 밖은 404.

    방에 사람을 넣는 문은 셋이다 — 방 만들기(`member_user_ids`)·초대(`members/add`)·1:1 열기.
    셋 다 목록(`/directory`)이 아니라 **id 를 그대로** 받는다. 그래서 목록만 조직으로 좁혀
    두면 나머지 문으로 그대로 뚫린다(3순위 IDOR). 실제로 1:1 만 막혀 있었고 **그룹 초대는
    같은 판정을 안 지났다** — 이 저장소가 여러 번 겪은 "목록만 좁히고 쓰기는 그대로" 다.

    그래서 **조회와 판정을 한 함수에 묶는다**: 사람을 찾는 코드가 곧 범위를 거는 코드라
    새 경로가 판정을 빠뜨릴 자리가 없다(`app/jobs/repository.py::scope_clause` 와 같은 관용).

    막아야 하는 이유는 목록이 새는 것보다 무겁다 — 사람을 방에 넣는 **순간** 그 방의 메시지와
    붙여넣기 이미지 전부에 접근권이 생긴다(이미지 서빙이 방 멤버십으로 판정한다).

    **부서로는 좁히지 않는다.** 다른 팀을 못 부르면 그건 기능 축소지 보안이 아니다 —
    맞는 축은 조직이고, `repository.directory` 가 쓰는 축과 같다.

    **403 이 아니라 404** — 403 은 "그 id 는 존재한다" 를 알려 준다(저장소 규칙:
    `get_scoped_user_or_404`, 채팅 이미지 서빙, `core/scope.py` 모듈 docstring).

    한쪽 `org_id` 가 비어 있으면 막지 않는다 — 조직 축이 붙기 전 데이터를 여기서 막으면
    기존 방들이 통째로 멈춘다(`OrgScopedMixin` 이 nullable 인 이유와 같은 판단).
    """
    found = repository.users_by_ids(db, user_ids)
    my_org = getattr(actor, "org_id", None)
    for target in found.values():
        their_org = getattr(target, "org_id", None)
        if my_org and their_org and my_org != their_org:
            raise NotFoundError("대화 상대를 찾을 수 없습니다.")
    return found


def create_group(db: Session, user: User, *, title: str, member_user_ids: list[str], now: datetime) -> ChatRoom:
    title = (title or "").strip()
    if not title:
        raise ValidationAppError("방 이름을 입력하세요.")
    room = ChatRoom(kind=ROOM_GROUP, title=title[:200], created_by_user_id=user.id,
                    is_global=False, event_seq=0, created_at=now, updated_at=now)
    db.add(room)
    db.flush()
    # 만든 사람 = 방장, 지정한 사람들 = 멤버(중복·본인 제거).
    # 초대(`add_members`)와 **같은 함수**로 사람을 찾는다 — 만들 때만 열려 있으면 막은 의미가 없다.
    ids = {user.id, *[m for m in (member_user_ids or []) if m]}
    valid = set(get_scoped_participants_or_404(db, user, list(ids)).keys())
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
    # **조직 밖 사람과는 방을 열지 않는다** (3순위 IDOR) — 판정은 조회에 붙어 있다
    # (`get_scoped_participants_or_404` docstring 에 왜가 적혀 있다). 조직 밖은 404,
    # 아예 없는 사람은 아래 422 — 이 두 갈래는 tests/security/test_org_axis.py 가 고정한다.
    umap = get_scoped_participants_or_404(db, user, [other_user_id])
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


PRESENCE_ONLINE = "online"
PRESENCE_DND = "dnd"
PRESENCE_OFFLINE = "offline"


def dnd_user_ids(db: Session, user_ids, *, now: datetime) -> set[str]:
    """지금 **수동 방해금지**를 켜 둔 사람들 (X3).

    ## 왜 밖에서 보여야 하나

    방해금지는 지금까지 **자기 배지만 조용하게** 했다. 밖에서는 아무 표시가 없어서, 동료는
    초록 점을 보고 말을 걸고 답이 없으면 이상하게 여긴다. 방해금지를 켠 사람은 방해를 받고,
    거는 사람은 무시당했다고 느낀다 - 아무도 원하지 않은 결과다. 방해금지는 원래
    **밖으로 내는 신호**다.

    ## 조용시간(quiet hours)은 왜 안 넣나

    조용시간은 "밤에는 알림 소리를 끄겠다" 는 **개인 일정**이지 "지금 말 걸지 마라" 가 아니다.
    23시에 채팅방을 열어 두고 읽고 있는 사람을 방해금지로 그리면 **사실이 아닌 것을 그리는
    것**이다. 그래서 사용자가 직접 누른 수동 방해금지만 밖으로 낸다.

    ## 왜 한 번에 읽나

    참여자 수만큼 질의하면 방 하나 여는 데 N+1 이 된다. 이 화면은 폴링 대상이라 그 비용이
    매 초 반복된다.
    """
    ids = [uid for uid in set(user_ids or []) if uid]
    if not ids:
        return set()

    from sqlalchemy import select

    from app.profiles.models import UserPreference
    from app.profiles.prefs import evaluate_quiet

    rows = db.execute(
        select(UserPreference).where(UserPreference.user_id.in_(ids))
    ).scalars().all()
    out: set[str] = set()
    for pref in rows:
        state = evaluate_quiet(
            dnd_enabled=pref.dnd_enabled,
            dnd_until=pref.dnd_until,
            # 조용시간을 끄고 부른다 - 위 docstring 의 이유대로다.
            # ⚠️ 다만 **실제로 막고 있는 것은 아래 `reason == "manual"` 검사**다. 이 인자를
            # 되돌려 넣는 사보타주를 걸었는데 테스트가 초록이었고, 그래서 확인했다.
            # 둘 다 남겨 둔다(한쪽이 무너져도 다른 쪽이 잡는다). 다만 "이 인자가 지킨다" 고
            # 적어 두면 다음 사람이 아래 검사를 안심하고 지울 수 있어서, 사실대로 적는다.
            quiet_hours_enabled=False,
            quiet_start=pref.quiet_start,
            quiet_end=pref.quiet_end,
            now=now,
        )
        if state.quiet and state.reason == "manual":
            out.add(pref.user_id)
    return out


def presence_for(last_seen: datetime | None, now: datetime, *, dnd: bool) -> str:
    """참여자 한 명의 표시 상태.

    🔴 **방해금지라고 오프라인으로 그리지 않는다.** 그건 거짓말이고, 거는 사람이 "자리에
    없구나" 로 잘못 읽는다. 있는 그대로 "있지만 지금은 곤란함" 을 말한다.

    반대로 **접속해 있지 않으면 방해금지도 표시하지 않는다** - 어제 켜 두고 퇴근한 사람에게
    방해금지 딱지가 붙어 있으면 그것도 사실이 아니다.
    """
    if not is_online(last_seen, now):
        return PRESENCE_OFFLINE
    return PRESENCE_DND if dnd else PRESENCE_ONLINE


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
# 권한 규칙은 한 곳(ensure_can_manage_room)에서만 판단한다. 이름 변경·초대·내보내기·방장
# 넘기기가 각자 조건을 다시 쓰면 언젠가 하나만 고쳐지고, 그 순간 '보이는데 누르면 403'이 된다.
# 이름을 `ensure_*` 로 두는 것도 규칙이다 — `scripts/check_scope_gates.py` 가 판정을 이 어휘로
# 찾는다. 예전 이름(밑줄로 시작하는 require 형태)은 사람 눈에만 게이트였고 검사에는
# '판정 없음'으로 보여 이 네 경로가 통째로 잡혔다 — 그 소음이 진짜 구멍 하나를 덮고 있었다
# (초대에 조직 판정이 없었다).
#
# 관리 대상은 **그룹 방뿐**이다:
#   * 전체 채팅 — 이름이 제품의 일부이고 멤버십 자체가 없다;
#   * 1:1 — 멤버가 정의상 둘이고, 이름은 보는 사람마다 상대 이름으로 계산된다.
# 둘 다 409 로 막는다(403 이 아니다 — 권한 문제가 아니라 그 방에는 없는 개념이다).
#
# **대상(target)의 범위 판정은 초대에만 붙는다.** 내보내기·방장 넘기기의 대상은 이미 그
# 방의 멤버라 새로 열리는 문이 없고, 거기에 조직 판정을 걸면 구멍이 막히기 전에 들어온
# 사람을 영영 못 빼게 된다(고치려다 가두는 꼴이다).

def _require_group(room: ChatRoom) -> None:
    if room.is_global:
        raise ConflictError("전체 채팅방은 관리할 수 없습니다.")
    if room.kind == ROOM_DIRECT:
        raise ConflictError("1:1 대화는 관리할 수 없습니다.")


def ensure_can_manage_room(db: Session, room: ChatRoom, user: User) -> ChatRoomMember:
    """이 방을 관리할 수 있는가 — 네 경로(이름 변경·초대·내보내기·방장 넘기기)의 유일한 문.

    비멤버·비방장은 **403 이다(404 가 아니다)**. 범위 밖을 404 로 감추는 규칙은 '그런 것이
    있는지도 모르게' 하려는 것인데, 방은 이미 접근 거부를 403 으로 답하기로 정해져 있다
    (tests/security/test_team_chat_images.py: "방 자체는 예전처럼 403이다 — 이미지만 404로
    감추는 것은 의도적이다"). 여기만 404 로 바꾸면 같은 방이 경로마다 다르게 답한다.
    이 모듈에서 404 로 감추는 축은 **사람**이다 — `get_scoped_participants_or_404`.
    """
    _require_group(room)
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    if member.role != ROLE_OWNER:
        raise ForbiddenError("방장만 채팅방을 관리할 수 있습니다.")
    return member


def rename_room(db: Session, room: ChatRoom, user: User, *, title: str, now: datetime) -> ChatRoom:
    ensure_can_manage_room(db, room, user)
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

    **조직 밖 사람은 다르다 — 조용히 건너뛰지 않고 요청 전체를 404 로 세운다.** 건너뛰면
    화면은 성공이라 말하는데 고른 사람이 안 들어온 상태가 되고(스키마 docstring 이 말하는
    "사용자 글자를 말없이 먹는" 실패), 무엇보다 그건 정상 화면에서 일어날 수 없는 요청이다
    — `/directory` 가 이미 조직으로 좁혀져 있어 조직 밖 id 는 손으로 넣어야만 나온다.
    """
    ensure_can_manage_room(db, room, user)
    wanted = [uid for uid in (user_ids or []) if uid]
    if not wanted:
        raise ValidationAppError("초대할 사람을 선택하세요.")
    existing = {m.user_id for m in repository.members(db, room.id)}
    # 방 만들기(`create_group`)·1:1 열기와 **같은 함수**로 사람을 찾는다 — 조직 밖은 404.
    valid = get_scoped_participants_or_404(db, user, wanted)
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
    ensure_can_manage_room(db, room, user)
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
    me = ensure_can_manage_room(db, room, user)
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


def touch_presence(
    db: Session, room: ChatRoom, user: User, *, now: datetime, idle: bool = False
) -> None:
    """실제 멤버만 last_seen 갱신. 전체 채팅 방은 멤버십이 없어 아무 것도 쓰지 않는다
    (모든 페이지에서 폴링하는 위젯이 매 조회마다 쓰기를 만들지 않게).

    스로틀은 2초에서 **30초**로 올렸다(app/core/presence.py). 2초는 폴링 주기와 거의 같아
    사실상 스로틀이 아니었고, 읽기 폴링이 그대로 쓰기 부하가 됐다 — SQLite writer 는 하나라
    사람이 늘수록 아무도 아무것도 안 하는 동안에도 쓰기 큐가 찬다.
    온라인 점의 임계값(계획 F)은 2분 이상으로 잡는다 — 30초면 그 창 안에 네 번은 찍혀서
    실제로 붙어 있는 사람이 깜빡이지 않는다.

    `idle` 은 브라우저가 "폴링은 돌지만 사람은 없다"고 알려 온 값이다 (X12). 판정 규칙은
    `app/core/presence.py` 한 곳에 있다 — 여기서 다시 해석하지 않는다."""
    if room.is_global:
        return
    member = repository.get_member(db, room.id, user.id)
    if member is not None and should_touch(member.last_seen, now, idle=idle):
        member.last_seen = now
        db.flush()


def transfer_owned_rooms(db: Session, *, target: User, successor: User | None = None) -> int:
    """`target` 이 방장인 **그룹** 방의 방장직을 다른 멤버에게 넘긴다. 넘긴 방 수를 돌려준다.

    로그인 불가 계정(비활성화·보관)이 방장으로 남으면 그 방을 **아무도 관리 못 한다** —
    `ensure_can_manage_room` 에 관리자 우회가 없어 system_admin 도 이름 변경·초대·파하기를
    못 한다(X8). 계정을 로그인 못 하게 만드는 자리라면 어디서 그러든 이 함수를 불러야
    한다 — `app/users/service.py::set_user_active`/`archive_user`(직접 비활성화·보관)와
    `app/offboarding/service.py::run_offboarding`(오프보딩 전체 실행) 둘 다.

    이 함수는 원래 오프보딩 전용이었다(app/offboarding/service.py 안의 `_transfer_room_ownership`).
    그런데 오프보딩 마법사를 거치지 않고 `/users`에서 바로 비활성화·보관해도 계정은 로그인을
    못 하게 되는 것은 같다 — 호출부가 오프보딩 실행 한 곳뿐이라 그 경로만 안전했다. 채팅방
    도메인 로직이라 여기(team_chat)로 옮겨 두 호출부가 순환 import 없이 공유한다
    (app/users/service.py 는 app/offboarding/service.py 를 모르고, app/offboarding/service.py
    는 이미 app/users/service.py 를 부른다 — 반대로 옮기면 순환 import 다).

    **누구에게 넘기는가**: 후임(`successor`)이 그 방 멤버면 후임, 아니면 **가장 오래된
    다른 멤버**다. 후임을 방에 억지로 넣지 않는다 — 오프보딩은 티켓을 넘기는 일이지 남의
    대화방에 사람을 밀어 넣는 일이 아니다. 직접 비활성화·보관 경로에는 후임 개념이 없으므로
    `successor=None`으로 부른다(=가장 오래된 멤버에게 넘어간다). 넘길 사람이 아무도
    없으면(혼자 있던 방) 그대로 둔다: 받을 사람이 없는데 방장을 비우면 그때부터는
    **되살릴 방법도 없다.**

    **멤버십은 유지한다.** 지우면 지난 대화의 발신자가 참여자 목록에서 사라져 "이 말을
    누가 했는지" 를 못 읽는다. 계정을 화면에서 지우는 것이 아니라 **보관됨으로 표시**하는
    것이 이 저장소의 방향이다(N3).

    1:1(dm)과 전체 방은 건드리지 않는다 — 방장 개념이 뜻을 갖지 않는다.
    """
    owned = db.execute(
        select(ChatRoomMember)
        .join(ChatRoom, ChatRoom.id == ChatRoomMember.room_id)
        .where(
            ChatRoomMember.user_id == target.id,
            ChatRoomMember.role == ROLE_OWNER,
            ChatRoom.kind == ROOM_GROUP,
            ChatRoom.is_global.is_(False),
        )
    ).scalars().all()

    moved = 0
    for mine in owned:
        candidates = db.execute(
            select(ChatRoomMember)
            .where(
                ChatRoomMember.room_id == mine.room_id,
                ChatRoomMember.user_id != target.id,
            )
            .order_by(ChatRoomMember.joined_at.asc(), ChatRoomMember.id.asc())
        ).scalars().all()
        if not candidates:
            continue
        heir = next(
            (c for c in candidates if successor is not None and c.user_id == successor.id),
            candidates[0],
        )
        heir.role = ROLE_OWNER
        mine.role = ROLE_MEMBER
        moved += 1
    db.flush()
    return moved
