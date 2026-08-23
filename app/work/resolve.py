"""티켓 이름 → 티켓. **순서가 계약이다** (D-282).

`canonical_key` → `uuid`.

## 층이 넷이었고 둘이 됐다

앞 정책에서는 `canonical_key` → `legacy_key` → `ticket_key_aliases.alias` → `uuid`
넷이었다. 두 층이 사라진 이유는 서로 다르다.

* **`legacy_key`(`GIT-142`)** — 옛 코드를 이관하지 않기로 했다(D-283). 들어올 값이 없는
  층은 「찾아보고 없다」를 매번 한 번 더 하는 것 말고 하는 일이 없다.
* **`ticket_key_aliases`** — 옛 canonical 이 별칭으로 밀려나는 것은 프로젝트 코드를 **바꿀
  때**만 일어났다. 이제 코드가 안 바뀌므로(D-282) 그 표에 행이 생길 경로가 없다.

남은 두 층에는 겹침이 없다. `<CODE>-<SEQ>` 는 대문자와 하이픈과 숫자이고 uuid 는
소문자 16진수와 하이픈이라, 한 문자열이 둘 다일 수 없다. 그래도 순서를 고정해 두는
이유는 **읽는 사람이 순서를 물을 필요가 없어야** 하기 때문이다.

## 왜 page_id 는 여기 없는가

Notion page id 는 **미러의 축**이지 도메인 이름이 아니다. 여기 넣으면 계약이 조용히
세 단계가 되고, 미러를 걷어낼 때 그 세 번째가 어디서 쓰이는지 아무도 모른다.
"""

from __future__ import annotations

import re
import uuid as uuid_mod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tickets.models import Ticket

# `<CODE>-<SEQ>` 모양. 앞은 Project Code 의 문자 집합
# (`app/work/codes.py::CODE_ALPHABET`)과 같고 길이도 여섯으로 같다.
#
# 여기서 다시 느슨하게 받지 않는 이유: 느슨하면 `SKH-1` 처럼 **옛 정책의 이름**이 이
# 갈래로 들어와 canonical 조회를 한 번 태우고 `None` 을 받는다. 그 답은 「없는 티켓」과
# 구별되지 않아서, 옛 링크를 든 사람이 무엇이 잘못됐는지 알 수 없다.
KEY_TOKEN_RE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ]{6}-[0-9]{1,9}$")

# 결과에 「어느 층이 답했는가」를 함께 싣는다. 시험이 순서를 실제로 검증할 수 있다.
BY_CANONICAL = "canonical"
BY_UUID = "uuid"
LOOKUP_ORDER: tuple[str, ...] = (BY_CANONICAL, BY_UUID)


@dataclass(frozen=True, slots=True)
class Resolution:
    """찾은 티켓과 **어느 층이 답했는가**."""

    ticket: Ticket
    matched_by: str
    token: str

    @property
    def is_current_name(self) -> bool:
        """지금 쓰는 이름으로 왔는가.

        두 층뿐인 지금은 언제나 참이다. 그래도 이 성질을 지우지 않는 이유는 화면이
        이것을 읽고 있고, 「옛 이름으로 오셨습니다」 안내가 이 값 하나로 켜지고 꺼지기
        때문이다. 남겨 두면 층이 늘어나는 날 화면을 안 고쳐도 된다.
        """
        return self.matched_by in LOOKUP_ORDER


def normalize_token(raw: str | None) -> str:
    """사람이 친 값 → 조회형.

    `<CODE>-<SEQ>` 모양이면 위로 맞춘다 — 코드는 대문자가 정본이라 `abcdef-37` 도 같은
    티켓이어야 한다. uuid 는 손대지 않는다(그쪽은 소문자 16진수 규약이다).
    """
    token = (raw or "").strip()
    upper = token.upper()
    if KEY_TOKEN_RE.match(upper):
        return upper
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
    """지금 이 티켓을 부르는 이름. 아직 번호를 못 받았으면 `None`.

    여기서 uuid 를 돌려주지 않는 이유: uuid 는 사람이 읽고 말하는 값이 아니라서
    「티켓 이름」 자리에 넣으면 오히려 이름이 없다는 사실을 감춘다. 화면은 이름이
    없으면 제목을 쓴다.
    """
    return ticket.canonical_key
