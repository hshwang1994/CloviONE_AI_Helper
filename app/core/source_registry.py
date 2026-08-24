"""저장소 배선 — 티켓·문서 저장소 구현체를 한곳에서 만든다 (§7.1.C).

**배선은 여기 한 곳뿐이다.** 두 번째 배선기(provider.py 류)를 만들지 않는다 — 저장소가
어디서 정해지는지 두 군데가 되면 한쪽만 고쳐지고, 그 순간 어느 구현이 도는지 아무도
확신할 수 없게 된다.

## 왜 고를 것이 없어졌나

예전에는 `ticket_source` / `document_source` 설정으로 세 값(`native` · `notion_cache` ·
`notion`) 중 하나를 골랐다. Cutover 를 되돌릴 수 있는 동안에는 그 선택이 뜻을 가졌다 —
되돌리면 노션 미러가 다시 정본이 되기 때문이다.

지금은 자체 DB 가 정본이고 노션을 읽고 쓰는 구현체 자체가 없다. 남은 구현이 하나뿐인데
설정으로 고르게 두면 그것은 **되는 척하는 스위치**다. 값을 바꾼 운영자는 무언가 달라졌다고
믿지만 실제로는 아무 일도 일어나지 않는다. 그래서 설정과 선택 로직을 함께 걷어냈다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.team_docs.repository_iface import DocumentRepository
from app.team_docs.repository_native import NativeDocumentRepository
from app.tickets.repository import TicketRepository
from app.tickets.repository_native import NativeTicketRepository

# 이 설치가 무엇을 읽고 쓰는지 한 단어로 말하는 이름이다. `/healthz` 가 이 값을 그대로
# 싣는다(app/health/router.py) — 운영자가 SSH 없이 확인하는 유일한 자리라 상수로 남긴다.
SOURCE_NATIVE = "native"


@dataclass(frozen=True)
class Repositories:
    """요청 처리에 쓰는 저장소 묶음. app.state.repositories 로 노출된다."""

    tickets: TicketRepository
    documents: DocumentRepository


def build_ticket_repository(settings, outbound) -> TicketRepository:
    return NativeTicketRepository(settings, outbound)


def build_document_repository(settings, outbound) -> DocumentRepository:
    return NativeDocumentRepository(settings, outbound)


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
