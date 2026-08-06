"""DocumentRepository 의 Notion 구현 (§7.1.C).

**문서 쪽에서 Notion 구현 세부가 사는 유일한 모듈**이다(sync 는 예외 — 미러 채우기 자체가
소스 특화 동작이라 같은 허용군이다). 목록·상세 메타 읽기는 이미 있는 로컬 미러 접근
모듈(app/team_docs/repository.py)을 그대로 감싸므로 동작·응답이 1:1로 같다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models_base import utcnow
from app.core.notion_blocks import markdown_to_blocks
from app.team_docs import notion_docs, repository
from app.tickets.repository import BodySaveResult


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

    def save_body(
        self, db: Session, *, page_id: str, body_markdown: str, now: datetime | None = None
    ) -> BodySaveResult:
        """본문 저장. **정본을 먼저 쓰고, 그다음 Notion 블록을 push 한다.**

        순서가 이 함수의 전부다(티켓 쪽 `save_body` 와 같은 판단). 반대로 하면 Notion 이
        죽은 날 사용자가 방금 친 글이 통째로 사라진다. 이 순서라면 push 가 실패해도 우리
        DB 에는 이미 들어가 있다.

        그래서 push 실패를 **예외로 던지지 않는다**: 요청 트랜잭션이 롤백되면 방금 저장한
        본문까지 되돌아가 순서를 지킨 의미가 없어진다. 대신 어긋난 사실을 행에 적어 두고
        (`body_sync_error`) `synced=False` 로 알린다 - 화면이 배너와 재시도를 그린다.

        **보장 범위를 과장하지 않는다.** 여기서 지키는 것은 push 단계의 실패뿐이다. 문서는
        캐시 행이 이미 있어야 편집이 열리므로(범위 판정이 그 행을 읽는다) 티켓처럼 '첫
        저장에서 소스를 먼저 부르는' 경로는 없다.
        """
        stamp = now or utcnow()
        row = repository.get_by_page_id(db, page_id)
        if row is None:
            # 부르는 쪽(service.save_document_body)이 범위 판정으로 이미 행을 읽었다.
            # 여기까지 None 이면 그 사이에 사라진 것이므로 없는 문서로 답한다.
            from app.core.errors import NotFoundError

            raise NotFoundError("문서를 찾을 수 없습니다.")

        # 1) 정본. 여기까지가 "사용자 글은 반드시 살아남는다"의 범위다.
        row.body_markdown = body_markdown
        db.flush()

        # 2) 소스 반영. 어떤 실패도 밖으로 내보내지 않는다.
        try:
            notion_docs.replace_page_body(
                self._outbound, self._settings,
                page_id=page_id, blocks=markdown_to_blocks(body_markdown),
            )
        except Exception as exc:  # noqa: BLE001 — 위 1)을 롤백시키지 않는 것이 이 except 의 목적
            message = getattr(exc, "message", None) or f"Notion 반영 실패: {type(exc).__name__}"
            row.body_sync_error = message
            row.body_synced_at = None
            db.flush()
            return BodySaveResult(
                uid=row.id, body_markdown=body_markdown, synced=False, sync_error=message
            )

        row.body_sync_error = None
        row.body_synced_at = stamp
        db.flush()
        return BodySaveResult(uid=row.id, body_markdown=body_markdown, synced=True)
