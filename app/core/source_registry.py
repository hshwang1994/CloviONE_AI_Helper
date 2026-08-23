"""소스 선택기 — 티켓·문서 저장소 구현체를 설정으로 고른다 (§7.1.C).

**선택 로직은 여기 한 곳뿐이다.** 두 번째 선택기(provider.py 류)를 만들지 않는다 — 소스가
어디서 정해지는지 두 군데가 되면 킬 스위치가 한쪽에만 먹는 사고가 난다.

설정값(app/core/config.py, env 로 바꾸고 재시작):
  * `ticket_source`
      - `native`(**기본** · S14) — 자체 DB 가 정본이다. 나가는 호출이 하나도 없다.
      - `notion_cache` — 로컬 미러 우선, 미러가 비었으면 실시간 폴백.
      - `notion` — 캐시를 아예 보지 않는 실시간 경로.
  * `document_source` — `native`(**기본**) | `notion` | `notion_cache`. 문서는 미러 경로
    에서 notion 과 notion_cache 가 같은 구현체를 가리킨다.

## 왜 옛 두 값을 안 지웠나

Cutover 는 **서비스 Open 전까지 되돌릴 수 있다**(MASTER_PLAN §7.5). 되돌리면 미러가 다시
정본이 되므로 그 창 안에서는 옛 값이 맞는 값이다. 값을 지워 놓고 되돌려야 하는 날이 오면
기동이 거부되고, 그때 고칠 것은 설정이 아니라 코드가 된다 — 되돌리기가 필요한 순간에
배포부터 해야 하는 상태를 만들지 않는다.

Open 이후에는 쓸 자리가 없고, Notion 구현체를 걷어내는 작업이 이 두 값을 함께 걷는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.team_docs.repository_iface import DocumentRepository
from app.team_docs.repository_native import NativeDocumentRepository
from app.team_docs.repository_notion import NotionDocumentRepository
from app.tickets.repository import TicketRepository
from app.tickets.repository_native import NativeTicketRepository
from app.tickets.repository_notion import NotionTicketRepository

SOURCE_NOTION = "notion"
SOURCE_NOTION_CACHE = "notion_cache"
SOURCE_NATIVE = "native"

_KNOWN_SOURCES = (SOURCE_NOTION, SOURCE_NOTION_CACHE, SOURCE_NATIVE)


class UnsupportedSourceError(RuntimeError):
    """설정된 소스를 만들 수 없다(오타이거나 아직 구현하지 않은 소스)."""


@dataclass(frozen=True)
class Repositories:
    """요청 처리에 쓰는 저장소 묶음. app.state.repositories 로 노출된다."""

    tickets: TicketRepository
    documents: DocumentRepository


def _check(name: str, value: str) -> str:
    """아는 값인가. **모르는 값은 조용히 기본값으로 떨어뜨리지 않는다.**

    떨어뜨리면 오타 하나로 「왜 옛날 데이터가 보이지」에 며칠을 태운다. 시작 시 분명한
    메시지로 실패하는 편이 싸다.
    """
    if value not in _KNOWN_SOURCES:
        raise UnsupportedSourceError(
            f"{name}='{value}' 는 알 수 없는 값입니다. 가능: {', '.join(_KNOWN_SOURCES)}"
        )
    return value


def build_ticket_repository(settings, outbound) -> TicketRepository:
    source = _check("ticket_source", getattr(settings, "ticket_source", SOURCE_NATIVE))
    if source == SOURCE_NATIVE:
        return NativeTicketRepository(settings, outbound)
    return NotionTicketRepository(settings, outbound, use_cache=(source == SOURCE_NOTION_CACHE))


def build_document_repository(settings, outbound) -> DocumentRepository:
    source = _check("document_source", getattr(settings, "document_source", SOURCE_NATIVE))
    if source == SOURCE_NATIVE:
        return NativeDocumentRepository(settings, outbound)
    return NotionDocumentRepository(settings, outbound)


def build_repositories(settings, outbound) -> Repositories:
    return Repositories(
        tickets=build_ticket_repository(settings, outbound),
        documents=build_document_repository(settings, outbound),
    )


def install(app) -> None:
    """앱 기동 시 한 번 배선한다. 저장소는 (settings, outbound) 만 붙든 얇은 객체라 상태가 없다."""
    app.state.repositories = build_repositories(
        app.state.settings, app.state.outbound_client
    )
