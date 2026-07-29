"""놀이 데이터 접근 (쿼리 전용). 종료(closed_at)된 방은 목록에서 제외(§5.3)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.games.models import GameEvent, GameRoom, GameRoomMember, ROLE_SPECTATOR


def get_room(db: Session, room_id: str) -> GameRoom | None:
    return db.execute(
        select(GameRoom).where(GameRoom.id == room_id, GameRoom.closed_at.is_(None))
    ).scalar_one_or_none()


def list_open_rooms(db: Session) -> list[GameRoom]:
    return list(
        db.execute(
            select(GameRoom).where(GameRoom.closed_at.is_(None)).order_by(GameRoom.created_at.desc())
        ).scalars().all()
    )


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
