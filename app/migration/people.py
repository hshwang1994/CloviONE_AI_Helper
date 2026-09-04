"""원본이 적은 **사람 이름**을 지금 계정에 잇는다.

## 왜 공용인가

Notion 과 Confluence 두 적재기가 같은 문제를 갖는다: 원본은 사람의 이름을 주는데 우리
계정과 잇는 다리(이메일)는 안 준다. 규칙을 두 곳에 적으면 한쪽만 고치는 날이 오고, 그날
「Confluence 문서는 이어지는데 Notion 문서는 안 이어진다」가 된다.

## 세 걸음 중 가운데

적재기의 순서는 이렇다: 이메일 → **이름** → 기본 계정. 이 모듈이 가운데를 맡는다.

  1. 표시 이름이 같다 — 「서윤경」 → `syk@goodmit.co.kr`.
  2. 이메일 앞부분이 같다 — 원본의 표시 이름이 계정 아이디인 경우가 있다
     (실측: 「ujmoon」 39건 → `ujmoon@goodmit.co.kr` 문의진).

🔴 **동명이인은 안 찍는다.** 같은 이름이 둘 이상이면 아무도 안 고른다 — 둘 중 하나를
고르는 것은 추정이 아니라 동전 던지기이고, 그 문서는 기본 계정으로 간다.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.users.models import User

__all__ = ["strip_seat_label", "user_by_name"]

#: 좌석이 없는 계정에 원본이 붙이는 꼬리표. **사람 이름의 일부가 아니다.**
#: 안 떼면 실측 23명 중 15명이 우리 계정과 영영 안 맞는다.
_SEAT_LABELS = ("(Unlicensed)", "(unlicensed)", "(비활성)", "(deactivated)")


def strip_seat_label(name: str | None) -> str:
    """「김동균 (Unlicensed)」 → 「김동균」."""
    clean = (name or "").strip()
    for tail in _SEAT_LABELS:
        if clean.endswith(tail):
            clean = clean[: -len(tail)].strip()
    return clean


def user_by_name(db: Session, name: str | None) -> User | None:
    """이름으로 우리 사용자 하나. 못 찾거나 **여럿이면** `None`."""
    clean = strip_seat_label(name)
    if not clean:
        return None
    rows = list(db.execute(
        sa.select(User).where(sa.func.lower(User.display_name) == clean.lower())
    ).scalars().all())
    if len(rows) == 1:
        return rows[0]
    if rows:
        return None          # 동명이인 — 안 찍는다
    rows = list(db.execute(
        sa.select(User).where(
            sa.func.lower(sa.func.split_part(User.email, "@", 1)) == clean.lower()
        )
    ).scalars().all())
    return rows[0] if len(rows) == 1 else None
