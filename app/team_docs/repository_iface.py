"""문서 저장소 인터페이스 (§7.1.C — 티켓 쪽 app/tickets/repository.py 와 같은 모양).

문서는 이미 로컬 미러(document_cache)에서 읽고 있어서 성능 문제가 없다. 그래도 seam 을 여기
같이 여는 이유는 Notion 호출이 **라우터에 직접 박혀 있었기** 때문이다(본문 블록·생성·프로젝트
목록). 그 상태로는 소스를 바꿀 때 고칠 곳이 흩어진다. 인터페이스를 두고 Notion 세부를 구현체
하나로 모은다.

DTO를 새로 만들지 않고 기존 DocumentCache ORM 행을 그대로 돌려준다 — 문서 화면은 이미 그
모양(_doc_view)으로 응답을 만들고 있어서, 여기서 DTO를 끼우면 얻는 것 없이 응답 계약만 흔들린다.
자체 id 이행(0025)이 올 때 같이 정리한다.
"""

from __future__ import annotations

from typing import Protocol

from app.tickets.repository import BodySaveResult


class DocumentRepository(Protocol):
    """문서를 읽고 쓰는 유일한 통로."""

    # -- 로컬 미러 읽기 --------------------------------------------------------
    def list_documents(self, db, **filters) -> tuple[list, int]:
        """(행 목록, 전체 건수). 필터 인자는 app/team_docs/repository.list_documents 와 같다."""
        ...

    def get(self, db, *, page_id: str): ...

    # -- 소스(Notion) 왕복 -----------------------------------------------------
    def body_blocks(self, db, *, page_id: str) -> list[dict]:
        """본문 블록(실시간). 실패는 호출측이 격리한다 — 메타는 계속 보여줘야 한다."""
        ...

    def project_names(self, db) -> list[str]:
        """생성 폼용 전체 프로젝트 이름."""
        ...

    def create(self, db, *, title, status, priority, owner, memo, body,
               project_names, author_id) -> dict:
        """소스에 새 문서를 만들고 생성된 페이지(dict)를 돌려준다."""
        ...

    def archive(self, db, *, page_id: str) -> None:
        """소스 쪽 원본을 보관처리(휴지통 보관기간 만료 정리)."""
        ...

    def save_body(self, db, *, page_id: str, body_markdown: str, now) -> BodySaveResult:
        """본문 저장. **정본을 먼저 쓰고 그다음 소스에 push** 한다(순서가 계약이다).

        결과 타입은 티켓 것을 그대로 쓴다. 같은 뜻을 가진 모양을 두 벌 두면 필드 이름이
        갈라지고, 그러면 응답 계약도 화면 코드도 두 벌이 된다 - 문서 상세와 티켓 상세는
        이미 같은 본문 렌더러(DocBody)를 공유하고 있다.
        """
        ...
