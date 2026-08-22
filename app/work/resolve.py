"""티켓 이름 → 티켓. **순서가 계약이다** (D-195).

`canonical_key` → `legacy_key` → `ticket_key_aliases.alias` → `uuid`.

이 순서를 바꾸면 `GIT-142` 가 다른 티켓으로 갈 수 있다. 순서가 고정이어야 하는 이유는
겹침이 실제로 생기기 때문이다: Project Key 를 바꾸면 옛 canonical 이 별칭이 되고,
그 뒤에 **다른** 프로젝트가 그 문자열을 canonical 로 만들 수는 없지만(Key 재사용
금지) — 만약 재사용을 허용하는 날이 오면 이 순서만이 옛 링크를 지킨다.

## 왜 page_id 는 여기 없는가

Notion page id 는 **미러의 축**이지 도메인 이름이 아니다. 지금 딥링크가 그 값을 쓰는
것은 사실이고 `app/tickets/router.py` 가 그 경로를 그대로 갖고 있다. 여기 넣으면
계약이 조용히 다섯 단계가 되고, S14 가 Notion 을 걷어 낼 때 그 다섯 번째가 어디서
쓰이는지 아무도 모른다.
"""

from __future__ import annotations

import re
import uuid as uuid_mod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tickets.models import Ticket
from app.work.models import TicketKeyAlias

# `<KEY>-<SEQ>` 모양. Key 규칙(`^[A-Z][A-Z0-9]{1,9}$`)과 같은 문자 집합이다.
KEY_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,9}-[0-9]{1,9}$")

# 결과에 「어느 층이 답했는가」를 함께 싣는다. 화면이 「옛 이름으로 오셨습니다」를
# 보여줄 수 있고, 시험이 순서를 실제로 검증할 수 있다.
BY_CANONICAL = "canonical"
BY_LEGACY = "legacy"
BY_ALIAS = "alias"
BY_UUID = "uuid"
LOOKUP_ORDER: tuple[str, ...] = (BY_CANONICAL, BY_LEGACY, BY_ALIAS, BY_UUID)


@dataclass(frozen=True, slots=True)
class Resolution:
    """찾은 티켓과 **어느 층이 답했는가**."""

    ticket: Ticket
    matched_by: str
    token: str

    @property
    def is_current_name(self) -> bool:
        """지금 쓰는 이름으로 왔는가. 아니면 화면이 새 이름을 안내할 수 있다."""
        return self.matched_by in (BY_CANONICAL, BY_UUID)


def normalize_token(raw: str | None) -> str:
    """사람이 친 값 → 조회형.

    `<KEY>-<SEQ>` 모양이면 위로 맞춘다 — Key 는 대소문자 무관 유일이라 `skh-37` 도
    같은 티켓이어야 한다. uuid 는 손대지 않는다(그쪽은 소문자 16진수 규약이다).
    """
    token = (raw or "").strip()
    if KEY_TOKEN_RE.match(token):
        return token.upper()
    return token


def _looks_like_uuid(token: str) -> bool:
    try:
        uuid_mod.UUID(token)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def resolve(db: Session, raw: str | None) -> Resolution | None:
    """티켓 하나. 못 찾으면 `None` — **범위 판정은 하지 않는다.**

    보이는가는 부르는 쪽이 `app/tickets/service.py::ensure_ticket_visible` 로 묻는다.
    여기서 함께 하면 「없는 티켓」과 「안 보이는 티켓」이 같은 답이 되고, 그 둘을
    구별하지 못하면 관리자가 예외 티켓을 찾을 수 없다.
    """
    token = normalize_token(raw)
    if not token:
        return None

    if KEY_TOKEN_RE.match(token):
        row = db.execute(
            select(Ticket).where(Ticket.canonical_key == token)
        ).scalar_one_or_none()
        if row is not None:
            return Resolution(ticket=row, matched_by=BY_CANONICAL, token=token)

        row = db.execute(
            select(Ticket).where(Ticket.legacy_key == token)
        ).scalar_one_or_none()
        if row is not None:
            return Resolution(ticket=row, matched_by=BY_LEGACY, token=token)

        alias = db.get(TicketKeyAlias, token)
        if alias is not None:
            row = db.get(Ticket, alias.ticket_id)
            if row is not None:
                return Resolution(ticket=row, matched_by=BY_ALIAS, token=token)
        return None

    if _looks_like_uuid(token):
        row = db.get(Ticket, token)
        if row is not None:
            return Resolution(ticket=row, matched_by=BY_UUID, token=token)
    return None


def resolve_id(db: Session, raw: str | None) -> str | None:
    """티켓 id 만 필요할 때. 못 찾으면 `None`."""
    found = resolve(db, raw)
    return found.ticket.id if found is not None else None


def display_key(ticket: Ticket) -> str | None:
    """지금 이 티켓을 부르는 이름.

    canonical 이 있으면 그것이고, 아직 번호를 못 받았으면 옛 이름이다. 둘 다 없으면
    부를 이름이 없다 — 화면은 그때 제목을 쓴다. 여기서 uuid 를 돌려주지 않는 이유:
    uuid 는 사람이 읽고 말하는 값이 아니라서 「티켓 이름」 자리에 넣으면 오히려
    이름이 없다는 사실을 감춘다.
    """
    return ticket.canonical_key or ticket.legacy_key
