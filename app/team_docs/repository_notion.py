"""DocumentRepository 의 Notion 구현 (§7.1.C).

**문서 쪽에서 Notion 구현 세부가 사는 유일한 모듈**이다(sync 는 예외 — 미러 채우기 자체가
소스 특화 동작이라 같은 허용군이다). 목록·상세 메타 읽기는 이미 있는 로컬 미러 접근
모듈(app/team_docs/repository.py)을 그대로 감싸므로 동작·응답이 1:1로 같다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.team_docs import notion_docs, repository


class NotionDocumentRepository:
    def __init__(self, settings, outbound) -> None:
        self._settings = settings
        self._outbound = outbound

    # ── 로컬 미러 읽기(그대로 위임) ──────────────────────────────────────────

    def list_documents(self, db: Session, **filters):
        return repository.list_documents(db, **filters)

    def get(self, db: Session, *, page_id: str):
        return repository.get_by_page_id(db, page_id)

    # ── 소스(Notion) 왕복 ────────────────────────────────────────────────────

    def body_blocks(self, db: Session, *, page_id: str) -> list[dict]:
        return notion_docs.fetch_page_blocks(self._outbound, self._settings, page_id)

    def project_names(self, db: Session) -> list[str]:
        return notion_docs.list_all_project_names(self._outbound, self._settings)

    def create(
        self, db: Session, *, title: str, status, priority, owner, memo, body,
        project_names: list[str], author_id: str | None,
    ) -> dict:
        """새 문서를 만든다. 프로젝트만 Notion relation 으로 기록하고, 문서 종류·업무 분야·기술
        태그는 앱측 택소노미라 여기서 다루지 않는다(캐시에 저장 — service.cache_created_document)."""
        schema = notion_docs.fetch_documents_schema(self._outbound, self._settings)
        project_ids = notion_docs.resolve_names_to_ids(
            self._outbound, self._settings, schema, notion_docs.PROP_PROJECT, project_names
        )
        props = notion_docs.build_create_properties(
            title=title, status=status, priority=priority, owner=owner, memo=memo,
            type_ids=[], category_ids=[], project_ids=project_ids, author_id=author_id,
        )
        children = notion_docs.body_children(body)
        return notion_docs.create_document(
            self._outbound, self._settings, properties=props, children=children
        )

    def archive(self, db: Session | None, *, page_id: str) -> None:
        """소스 원본을 보관처리한다. 문서 캐시 행은 다음 동기화가 정리한다."""
        notion_docs.archive_page(self._outbound, self._settings, page_id=page_id)
