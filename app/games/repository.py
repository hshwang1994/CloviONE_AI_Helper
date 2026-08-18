"""놀이 데이터 접근 (쿼리 전용). 종료(closed_at)된 방은 목록에서 제외(§5.3)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.games.models import GameEvent, GameRoom, GameRoomMember, ROLE_SPECTATOR
from app.users.models import User


def users_by_ids(db: Session, ids: list[str]) -> dict[str, User]:
    """참여자 표시에 쓸 사용자(부서·직책 포함)를 한 번에 읽어 {user_id: User}로 돌려준다."""
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(list(ids)))).scalars().all()
    return {u.id: u for u in rows}


def get_room(db: Session, room_id: str, *, org_id: str | None = None) -> GameRoom | None:
    """열린 방 하나. `org_id` 를 주면 **그 조직 방만** 돌려준다(0060).

    `GameRoom.org_id` 는 0024 부터 채워지고 있었는데 **읽는 접근 제어가 없었다** — 컬럼만
    있고 아무도 안 봤다. 놀이는 부서로 좁히지 않는다(같은 회사 사람끼리 노는 곳이다) —
    조직 경계 하나만 지킨다.
    """
    stmt = select(GameRoom).where(GameRoom.id == room_id, GameRoom.closed_at.is_(None))
    if org_id:
        stmt = stmt.where(GameRoom.org_id == org_id)
    return db.execute(stmt).scalar_one_or_none()


def list_open_rooms(db: Session, *, org_id: str | None = None) -> list[GameRoom]:
    """열린 방 목록. 조건은 단건(`get_room`)과 **같은 것**이다 — 갈라지면 목록에 없는데
    id 로 들어가지는 방이 생긴다."""
    stmt = select(GameRoom).where(GameRoom.closed_at.is_(None))
    if org_id:
        stmt = stmt.where(GameRoom.org_id == org_id)
    return list(db.execute(stmt.order_by(GameRoom.created_at.desc())).scalars().all())


def last_seen_by_room(db: Session) -> dict:
    """열린 방마다 마지막으로 폴링한 시각(참여자 last_seen 중 최댓값)을 돌려준다. 유휴 방 정리용."""
    rows = db.execute(
        select(GameRoomMember.room_id, func.max(GameRoomMember.last_seen)).group_by(GameRoomMember.room_id)
    ).all()
    return {room_id: last for room_id, last in rows}


def members(db: Session, room_id: str) -> list[GameRoomMember]:
    return list(
        db.execute(
            select(GameRoomMember)
            .where(GameRoomMember.room_id == room_id)
            .order_by(GameRoomMember.joined_at.asc())
        ).scalars().all()
    )


def get_member(db: Session, room_id: str, user_id: str) -> GameRoomMember | None:
    return db.execute(
        select(GameRoomMember).where(
            GameRoomMember.room_id == room_id, GameRoomMember.user_id == user_id
        )
    ).scalar_one_or_none()


def player_count(db: Session, room_id: str) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(GameRoomMember).where(
                GameRoomMember.room_id == room_id,
                GameRoomMember.role != ROLE_SPECTATOR,
                GameRoomMember.active.is_(True),
            )
        ).scalar_one()
    )


def member_count(db: Session, room_id: str) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(GameRoomMember).where(
                GameRoomMember.room_id == room_id, GameRoomMember.active.is_(True)
            )
        ).scalar_one()
    )


def events_since(db: Session, room_id: str, since: int) -> list[GameEvent]:
    return list(
        db.execute(
            select(GameEvent)
            .where(GameEvent.room_id == room_id, GameEvent.seq > since)
            .order_by(GameEvent.seq.asc())
        ).scalars().all()
    )
