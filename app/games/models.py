"""팀 공간 > 놀이 모델 (§5·§6·§13·§20).

서버 확정·이벤트 시퀀스 상태 모델(§13.1): 방 상태와 채팅·반응·게임 이벤트를 하나의 append-only
이벤트 로그(GameEvent)로 흘려보내고, 클라이언트는 GET /rooms/{id}/state?since=<seq> 폴링으로
따라온다(불변 §1 sync 유지 — WebSocket 없이). 결과는 언제나 서버가 확정한다.

내부 전용 기능 — 외부 호출(n8n/Notion/Claude) 없음. 게임 히스토리는 남기지 않는다(§16.1):
방이 끝나고 정리 시간이 지나면 방·이벤트를 지운다(retention에서 처리, 여기선 스키마만).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

# 게임 종류(§8). 방/이벤트/폴링 인프라는 전부 공유하고, 종류별 규칙만 service에서 분기한다.
#   random_draw — 방장이 시작하면 서버가 참여자 중 당첨자를 즉시 확정.
#   quick_vote  — 방장이 선택지를 열고, 참여자가 투표한 뒤, 방장이 종료하면 서버가 집계·확정.
#   team_split  — 방장이 시작하면 서버가 참여자를 N개 팀으로 공정하게 나눠 즉시 확정.
#   number      — 숫자 눈치. 참여자가 몰래 숫자를 고르고(진행 중엔 남의 선택 비공개), 방장이
#                 종료하면 서버가 공개해 '가장 낮은 유일 숫자'를 고른 사람이 승리한다.
#   ladder      — 사다리타기. 방장이 시작하면 서버가 참여자 각각에 결과(도착지)를 무작위로
#                 1:1 배정해 즉시 확정한다(결과가 참여자보다 적으면 '꽝'으로 채운다).
#   rps         — 가위바위보. 참여자가 몰래 가위/바위/보를 내고(진행 중 비공개), 방장이 공개하면
#                 서버가 판정한다. 정확히 두 종류만 나오면 이기는 쪽이 승리, 아니면 무승부.
#   quiz        — 실시간 퀴즈. 방장이 문제를 미리 넣고, 라운드마다 참여자가 몰래 답하고(비공개)
#                 방장이 정답을 공개(채점)한 뒤 다음 문제로 넘어간다. 마지막에 누적 점수판을 확정.
GAME_RANDOM_DRAW = "random_draw"
GAME_QUICK_VOTE = "quick_vote"
GAME_TEAM_SPLIT = "team_split"
GAME_NUMBER = "number"
GAME_LADDER = "ladder"
GAME_RPS = "rps"
GAME_QUIZ = "quiz"
GAME_TYPES: frozenset[str] = frozenset(
    {GAME_RANDOM_DRAW, GAME_QUICK_VOTE, GAME_TEAM_SPLIT, GAME_NUMBER, GAME_LADDER, GAME_RPS, GAME_QUIZ}
)

# 방 상태(§5.3).
ROOM_WAITING = "waiting"
ROOM_PLAYING = "playing"
ROOM_FINISHED = "finished"

# 참여 역할·상태(§6.1·§6.4).
ROLE_HOST = "host"
ROLE_PLAYER = "player"
ROLE_SPECTATOR = "spectator"

# 이벤트 종류.
EV_JOIN = "join"
EV_LEAVE = "leave"
EV_READY = "ready"
EV_START = "start"
EV_VOTE = "vote"
EV_PICK = "pick"
EV_RESULT = "result"
EV_RESET = "reset"
EV_CHAT = "chat"
EV_REACTION = "reaction"
EV_SYSTEM = "system"


class GameRoom(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "game_rooms"

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    game_type: Mapped[str] = mapped_column(String(32), nullable=False)
    host_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ROOM_WAITING, index=True)
    max_players: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    allow_spectators: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 이벤트 순번 카운터 — 방에 이벤트를 붙일 때마다 +1. 폴링 커서로 쓴다.
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class GameRoomMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "game_room_members"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("game_rooms.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_PLAYER)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 재접속 감지
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_game_member"),
    )


class GameEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "game_events"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("game_rooms.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("room_id", "seq", name="uq_game_event_seq"),
    )
