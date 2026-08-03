"""소스 선택기 — 티켓·문서 저장소 구현체를 설정으로 고른다 (§7.1.C).

**선택 로직은 여기 한 곳뿐이다.** 두 번째 선택기(provider.py 류)를 만들지 않는다 — 소스가
어디서 정해지는지 두 군데가 되면 킬 스위치가 한쪽에만 먹는 사고가 난다.

설정값(app/core/config.py, env 로 바꾸고 재시작):
  * `ticket_source`
      - `notion_cache`(기본) — 로컬 미러 우선, 미러가 비었으면 실시간 폴백.
      - `notion` — **운영 킬 스위치**. 캐시를 아예 보지 않는다. 캐시 도입 전과 똑같은 실시간
        경로라, 미러가 이상하면 이 값 하나만 바꿔 재시작하면 원복된다.
      - `native` — 자체 DB가 정본. 아직 구현체가 없다(문만 열어 둔 상태) → 시작 시 즉시 거절.
  * `document_source` — `notion`(기본) | `notion_cache` | `native`. 문서는 이미 로컬 미러에서
    읽으므로 notion / notion_cache 가 같은 구현체를 가리킨다.

`native` 를 조용히 무시하지 않고 예외로 죽이는 이유: 잘못 설정한 채로 뜨면 '왜 옛날 데이터가
보이지'로 며칠을 태운다. 시작 시 분명한 메시지로 실패하는 편이 싸다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.team_docs.repository_iface import DocumentRepository
from app.team_docs.repository_notion import NotionDocumentRepository
from app.tickets.repository import TicketRepository
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
    if value not in _KNOWN_SOURCES:
        raise UnsupportedSourceError(
            f"{name}='{value}' 는 알 수 없는 값입니다. 가능: {', '.join(_KNOWN_SOURCES)}"
        )
    if value == SOURCE_NATIVE:
        raise UnsupportedSourceError(
            f"{name}='native' 는 아직 구현되지 않았습니다(자체 DB 소스는 defer). "
            f"'{SOURCE_NOTION_CACHE}' 또는 '{SOURCE_NOTION}' 을 쓰세요."
        )
    return value


def build_ticket_repository(settings, outbound) -> TicketRepository:
    source = _check("ticket_source", getattr(settings, "ticket_source", SOURCE_NOTION_CACHE))
    return NotionTicketRepository(settings, outbound, use_cache=(source == SOURCE_NOTION_CACHE))


def build_document_repository(settings, outbound) -> DocumentRepository:
    _check("document_source", getattr(settings, "document_source", SOURCE_NOTION))
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
