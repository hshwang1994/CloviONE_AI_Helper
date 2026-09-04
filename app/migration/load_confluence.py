"""Confluence 페이지를 ClovirAssist 문서로 넣는다 (문서 개편 14~20번).

## 두 번 돌려도 같은 결과다

다리는 `legacy_mapping(legacy_source='confluence', legacy_source_id=<page id>)` 하나다.
두 번째 회차는 그 표를 먼저 보고 **같은 문서를 다시 만들지 않는다.** 첨부도 같다 —
`<page id>:<attachment id>` 로 적어 두므로 바이트를 두 번 안 받는다.

## 🔴 어느 공간에 앉히는가가 이 파일에서 가장 위험한 줄이다

조직 공통 공간(`service.COMMON_SPACE_SLUG`)이다. `owner_kind` 가 `unset` 인 공간에
넣으면 그 문서는 **전역 조회 권한자 말고는 아무에게도 안 보인다** — 목록에서도, AI
검색에서도, 오류 한 줄 없이. 실측에서 문서 110건이 그렇게 사라진 적이 있다. 그래서
공간은 제품과 **같은 함수**로 얻고, 얻은 뒤 소유를 단언한다.

프로젝트 배정은 여기서 안 한다. 제목과 본문을 보고 정하는 일이라 사람이 검토할 수 있는
별도 단계(`classify.py`)가 맡는다 — 억지로 붙이지 않는 것이 요구다(15번).

## 실패의 단위는 **문서 하나**다

첨부 하나가 3MB 를 넘거나, 형식이 허용 목록 밖이거나, 바이트를 못 받아도 그 문서의
본문·댓글·나머지 첨부는 들어간다(18번). 건너뛴 사실은 보고서의 분류된 예외로 남고
본문에는 사람이 읽는 한 줄이 남는다 — 조용히 사라지는 것이 이 회차가 고치는 결함이다.

## 계층을 폴더로 만들지 않는다

한 페이지 = 한 문서다(14번). 부모 페이지 id 는 `parentId` 로 알지만 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.knowledge import attachments as doc_attachments
from app.knowledge import blocks
from app.knowledge import service as knowledge_service
from app.knowledge import versions
from app.knowledge.models import (
    SOURCE_MIGRATION,
    VSRC_MIGRATION,
    Document,
    DocumentComment,
    KnowledgeSpace,
)
from app.migration.models import (
    SRC_CONFLUENCE,
    T_COMMENT,
    T_DOCUMENT,
    T_FILE,
    LegacyMapping,
)
from app.migration.report import (
    SEVERITY_BLOCKING,
    SEVERITY_CLASSIFIED,
    SEVERITY_NOTE,
    StageResult,
)
from app.migration.transform_confluence import adf_plain_text, adf_to_doc, adf_media_ids
from app.users.models import User

__all__ = ["ConfluenceLoadResult", "ConfluenceLoader"]

#: 본문 이미지의 주소. 라우트의 정본은 `app/knowledge/router.py::serve_attachment` 다.
#: 상대 주소라 호스트가 바뀌어도 안 깨진다.
_ATTACHMENT_URL = "/api/knowledge/attachments/%s/content"

#: 건너뛴 첨부를 본문에 남기는 말. 내부 사유 이름을 사용자에게 보여 주지 않는다.
_SKIPPED_LINE = "원본에만 있는 첨부 파일입니다: %s"

#: 🔴 못 옮긴 **본문 그림**에는 사유를 그대로 적는다.
#:
#: 예전에는 셋 다 「원본에만 있는 이미지입니다」 한 문장이었다. 그런데 셋은 서로 다른
#: 사실이고, 그중 하나에는 그 문장이 **거짓말**이다 — 운영 실측에서 자리표시자 22개 중
#: 18개가 원본에서 이미 지워진 그림이었고(지금 눌러도 Atlassian 이 404 를 준다), 읽는
#: 사람은 그 문장을 보고 원본을 보러 갔다가 거기서도 깨진 그림을 본다.
#:
#: 파일 이름을 함께 적는 이유도 같다. 이름이 없으면 「무엇이 없어졌는지」를 물어볼
#: 방법조차 없다.
_GONE_LINE = "원본에서 이미 지워진 그림입니다: %s"
_TOO_LARGE_LINE = "3MB 를 넘어 옮기지 않은 그림입니다: %s"
_REJECTED_LINE = "옮길 수 없는 형식이라 넘긴 파일입니다: %s"


@dataclass
class ConfluenceLoadResult:
    """이 회차가 무엇을 했는가. **수와 사유만 낸다** — 통과 판정은 보고서가 한다."""

    pages_seen: int = 0
    documents_created: int = 0
    documents_updated: int = 0
    documents_skipped: int = 0
    attachments_attached: int = 0
    attachments_too_large: int = 0
    attachments_rejected: int = 0
    #: 지난 회차가 이미 옮겨 둔 첨부. 🔴 이 칸이 없으면 **두 번째 회차가 실패한다** —
    #: 이미 옮긴 것은 다시 안 붙이므로 `attachments_attached` 가 0 이 되고, 첨부 대조
    #: 게이트가 그것을 「하나도 못 옮겼다」로 읽는다. 회차를 다시 돌리는 것은 이 도구의
    #: 정상 사용법이다(멱등이 설계다).
    attachments_reused: int = 0
    comments_created: int = 0
    comments_without_author: int = 0
    skipped_page_ids: list[str] = field(default_factory=list)
    #: 결과가 정해진 페이지 id. **세는 자리는 여기 하나다.**
    #:
    #: 🔴 예전에는 세 counter 를 더해서 셌는데, 한 페이지가 「만들었다」로 세어진 뒤
    #: 나중에 실패하면 「건너뛰었다」로 한 번 더 세어져 3건이 4건이 됐다. 집합이면
    #: 같은 페이지를 두 번 세는 것이 구조적으로 불가능하다.
    accounted_ids: set = field(default_factory=set)

    @property
    def accounted(self) -> int:
        """설명된 페이지 수. **열거한 수와 같아야 한다**(원본 수 대조 게이트)."""
        return len(self.accounted_ids)

    def account(self, page_id: str) -> bool:
        """이 페이지의 결과를 적는다. 이미 적혀 있으면 `False` — 두 번 안 센다."""
        if page_id in self.accounted_ids:
            return False
        self.accounted_ids.add(page_id)
        return True

    def as_dict(self) -> dict:
        return {
            "pages_seen": self.pages_seen,
            "documents_created": self.documents_created,
            "documents_updated": self.documents_updated,
            "documents_skipped": self.documents_skipped,
            "attachments_attached": self.attachments_attached,
            "attachments_too_large": self.attachments_too_large,
            "attachments_rejected": self.attachments_rejected,
            "attachments_reused": self.attachments_reused,
            "comments_created": self.comments_created,
            "comments_without_author": self.comments_without_author,
            "accounted": self.accounted,
            "skipped_page_ids": list(self.skipped_page_ids),
        }


class ConfluenceLoader:
    """Confluence 한 번 가져오기. 대상에만 쓴다 — 원본은 조회뿐이다."""

    def __init__(self, db: Session, *, report, actor: User, settings=None) -> None:
        self.db = db
        self.report = report
        # 「가져온 사람」. 작성자를 못 푼 문서·댓글이 이 계정으로 앉는다 — 남의 이름을
        # 지어내는 것보다 낫고, 원래 이름은 보고서와 댓글 첫 줄에 남는다.
        self.actor = actor
        self.settings = settings
        self.result = ConfluenceLoadResult()
        self._space: KnowledgeSpace | None = None
        self._users_by_email: dict[str, User] | None = None
        self._provider_ready = False

    # ── 공간 ─────────────────────────────────────────────────────────────────

    def space(self) -> KnowledgeSpace:
        """조직 공통 공간. **제품과 같은 함수로 얻는다** — 위 머리말의 이유."""
        if self._space is None:
            space = knowledge_service.resolve_or_create_common_space(self.db, self.actor)
            # 리졸버가 이미 단언하지만 여기서 한 번 더 본다. 이 줄이 틀리면 가져온
            # 문서 524건이 통째로 안 보이고, 그 사실은 아무 오류도 안 낸다.
            if space.owner_kind != "organization" or not space.org_id:
                raise AppError(
                    f"공통 공간의 소유가 조직이 아닙니다: {space.slug}"
                )
            self._space = space
        return self._space

    def ensure_storage(self) -> None:
        """기본 저장소를 세운다 — **첫 첨부 앞에서 한 번만.**

        🔴 이 줄이 없으면 첨부가 하나도 안 붙는다. `store_bytes` 는 활성 저장소가 없으면
        거절하고, 그 거절은 「형식이 안 맞는다」와 같은 예외로 올라와 **첨부 1,458건이
        전부 「거절됨」으로 분류된 채 회차가 초록으로 끝난다.** 설치 직후나 새 DB 에서
        정확히 그렇게 되고, 그때 아무도 오류를 안 본다.
        """
        if self._provider_ready:
            return
        from app.core.config import Settings
        from app.storage import service as storage_service

        # 🔴 `settings` 가 없으면 여기서 터진다 — 그리고 그 예외는 첨부 하나가 아니라
        # **페이지 하나**를 죽인다. 제품 기본값으로 떨어지는 편이 옳다.
        storage_service.ensure_default_provider(self.db, self.settings or Settings())
        self._provider_ready = True

    # ── 다리 ─────────────────────────────────────────────────────────────────

    def _mapped(self, legacy_id: str, target_type: str) -> str | None:
        return self.db.execute(
            sa.select(LegacyMapping.target_id).where(
                LegacyMapping.legacy_source == SRC_CONFLUENCE,
                LegacyMapping.legacy_source_id == legacy_id,
                LegacyMapping.target_type == target_type,
            )
        ).scalar_one_or_none()

    def _map(self, legacy_id: str, target_type: str, target_id: str) -> None:
        if self._mapped(legacy_id, target_type) is not None:
            return
        self.db.add(LegacyMapping(
            legacy_source=SRC_CONFLUENCE,
            legacy_source_id=legacy_id[:128],
            target_type=target_type,
            target_id=target_id,
        ))

    # ── 사람 ─────────────────────────────────────────────────────────────────

    def _user_for(self, email: str | None) -> User | None:
        """이메일로 우리 사용자를 찾는다. 못 찾으면 `None` — **지어내지 않는다.**

        Atlassian 은 GDPR 설정에 따라 이메일을 안 줄 수 있다. 그때는 못 찾는 것이
        정상이고, 그 사실이 보고서에 수로 남는다.
        """
        key = (email or "").strip().lower()
        if not key:
            return None
        if self._users_by_email is None:
            rows = self.db.execute(sa.select(User)).scalars().all()
            self._users_by_email = {
                (u.email or "").strip().lower(): u for u in rows if u.email
            }
        return self._users_by_email.get(key)

    # ── 문서 하나 ────────────────────────────────────────────────────────────

    def load_page(
        self,
        page: dict,
        body: dict,
        *,
        attachments: list[dict],
        comments: list[dict],
        fetch=None,
        dry_run: bool = False,
    ) -> Document | None:
        """페이지 하나를 문서 하나로. **이 함수 안에서 나는 예외는 그 문서만 죽인다.**

        부르는 쪽(`runner`)이 SAVEPOINT 로 감싸므로 한 페이지가 실패해도 앞의 523건이
        되감기지 않는다.
        """
        page_id = str(page.get("id") or "")
        if not page_id:
            self.result.documents_skipped += 1
            self.report.finding(
                SEVERITY_BLOCKING, "confluence_page_without_id", "documents",
                "id 가 없는 페이지가 있습니다.",
            )
            return None
        self.result.pages_seen += 1

        title = (page.get("title") or body.get("title") or "").strip() or "(제목 없음)"
        existing_id = self._mapped(page_id, T_DOCUMENT)
        document = self.db.get(Document, existing_id) if existing_id else None

        if dry_run:
            self.result.account(page_id)
            if document is None:
                self.result.documents_created += 1
            else:
                self.result.documents_updated += 1
            return None

        if document is None:
            document = Document(
                space_id=self.space().id,
                title=title[:500],
                source_type=SOURCE_MIGRATION,
                created_by=self._page_author(body) or self.actor.id,
            )
            self.db.add(document)
            self.db.flush()
            self._map(page_id, T_DOCUMENT, document.id)
            self.result.documents_created += 1
            title_changed = True
        else:
            title_changed = document.title != title[:500]
            document.title = title[:500]
            self.result.documents_updated += 1
        # 🔴 여기서 세지 않는다. 아래 본문 정규화가 거절하면 이 페이지는 「건너뛴 것」이고,
        # 두 갈래를 다 세면 한 페이지가 둘로 보고된다(대조 게이트가 잡은 결함).

        # 원본이 말한 만든 날과 고친 날. 안 옮기면 524건이 전부 오늘이 되고, 그러면
        # 「최근 24시간」이 가져오기 직후 524를 말한다.
        document.legacy_created_at = _ts(page.get("createdAt") or body.get("createdAt"))
        document.legacy_updated_at = _ts((body.get("version") or {}).get("createdAt"))
        # 보관된 페이지는 보관된 문서로 온다 — 상태를 바꾸지 않는다.
        document.archived = str(page.get("status") or "").lower() == "archived"

        media_urls, skipped, media_notes = self._load_attachments(
            document, page_id, attachments, body, fetch=fetch
        )
        doc_body = adf_to_doc(
            body.get("adf"), media_urls=media_urls, media_notes=media_notes
        )
        for name in skipped:
            doc_body["content"].append({
                "type": "paragraph",
                "content": [{"type": "text", "text": _SKIPPED_LINE % name}],
            })
        try:
            normalized = blocks.normalize(doc_body)
        except blocks.BlockError as exc:
            # 본문 모양이 틀렸으면 **빈 본문으로 넘기지 않는다** — 빈 본문은 「원본이
            # 비어 있었다」와 구별되지 않는다. 사유를 남기고 이 문서만 건너뛴다.
            self.report.finding(
                SEVERITY_BLOCKING, "confluence_body_rejected", "documents",
                f"{title}: {exc}", ref=page_id,
            )
            # 만들었거나 고친 것을 되돌린다 — 이 페이지의 결과는 「건너뜀」 하나다.
            if document.current_version_id is None:
                self.result.documents_created -= 1
            else:
                self.result.documents_updated -= 1
            self.result.documents_skipped += 1
            self.result.skipped_page_ids.append(page_id)
            self.result.account(page_id)
            return None

        made = versions.snapshot(
            self.db, document, normalized,
            author_id=document.created_by or self.actor.id,
            change_reason="Confluence 에서 가져왔습니다.",
            source=VSRC_MIGRATION,
            # 첫 회차의 색인은 훑기가 「상태 행이 없다」로 집어 간다(이관 전용 경로).
            reindex=False,
        )
        if made is None and title_changed:
            # 🔴 두 번째 회차에서 **제목만** 바뀐 자리. 본문이 같으면 `snapshot` 이 `None`
            # 을 주어 신호를 안 보내고, 훑기의 낡음 조건 넷에도 제목이 없다. 그런데 제목은
            # 첫 청크 본문에 들어가므로 그 문서는 **옛 이름으로 계속 검색된다.**
            # (`service.save_document` 이 같은 구멍을 같은 방법으로 막는다.)
            versions.mark_stale(self.db, document.id)
        self._load_comments(document, page_id, comments)
        self.db.flush()
        self.result.account(page_id)
        return document

    def _page_author(self, body: dict) -> str | None:
        """페이지를 만든 사람. Atlassian id 는 우리 계정이 아니므로 이메일이 있을 때만
        푼다 — v2 의 페이지 응답은 이메일을 안 주므로 보통 `None` 이다."""
        user = self._user_for((body.get("_author_email") or ""))
        return user.id if user else None

    # ── 첨부 ─────────────────────────────────────────────────────────────────

    def _load_attachments(
        self, document: Document, page_id: str, rows: list[dict], body: dict, *, fetch
    ) -> tuple[dict[str, str], list[str], dict[str, str]]:
        """첨부를 옮기고 셋을 돌려준다.

        1. **본문의 media id → 우리 주소.**
        2. **본문이 안 부른** 첨부 중 건너뛴 것의 이름. 본문 끝에 한 줄로 적어 「여기
           무언가 있었다」를 남긴다 — 조용히 사라지면 원본보다 짧아진 것을 아무도 모른다.
        3. **본문이 부른** 그림 중 못 옮긴 것의 media id → 사유 문장. 그 자리에 그대로
           선다. 🔴 본문이 부른 그림을 끝줄로 보내면 그림이 있던 자리를 잃는다 —
           읽는 사람은 「어디에 있던 그림인지」를 알아야 한다.
        """
        wanted = set(adf_media_ids(body.get("adf")))
        urls: dict[str, str] = {}
        skipped: list[str] = []
        notes: dict[str, str] = {}
        if not rows:
            return urls, skipped, notes

        def lost(keys: set[str], name: str, line: str) -> None:
            """못 옮긴 사실을 **본문이 부른 자리**나 **끝줄** 중 한 곳에만 적는다."""
            marked = False
            for key in keys:
                if key and key in wanted:
                    notes[key] = line % name
                    marked = True
            if not marked:
                skipped.append(name)
        self.ensure_storage()
        for row in rows:
            name = str(row.get("title") or "첨부")
            att_id = str(row.get("id") or "")
            # 본문이 가리키는 키는 파일 id 이거나 media id 다. 둘 다 후보로 둔다.
            keys = {att_id, str(row.get("fileId") or "")} & (wanted or {att_id})
            legacy_id = f"{page_id}:{att_id}"

            already = self._mapped(legacy_id, T_FILE)
            if already:
                self.result.attachments_reused += 1
                for key in keys or {att_id}:
                    if key:
                        urls[key] = _ATTACHMENT_URL % already
                continue

            size = row.get("fileSize")
            content = None
            if fetch is not None:
                try:
                    content = fetch(
                        row.get("downloadLink") or "",
                        declared_size=int(size) if size is not None else None,
                    )
                except AppError as exc:
                    self.report.finding(
                        SEVERITY_CLASSIFIED, "confluence_attachment_download_failed",
                        "files", f"{name}: {exc}", ref=legacy_id,
                    )
                    lost(keys or {att_id}, name, _GONE_LINE)
                    continue
            if content is None:
                # 상한을 넘었거나 안 받기로 한 회차다. **문서를 실패시키지 않는다.**
                self.result.attachments_too_large += 1
                self.report.finding(
                    SEVERITY_CLASSIFIED, "confluence_attachment_too_large", "files",
                    f"{name}: 3MB 상한을 넘어 안 옮겼습니다.", ref=legacy_id,
                )
                lost(keys or {att_id}, name, _TOO_LARGE_LINE)
                continue
            try:
                with self.db.begin_nested():
                    link, record = doc_attachments.attach(
                        self.db, document, filename=name, content=content,
                        created_by=self.actor.id,
                    )
            except AppError as exc:
                # 형식 허용 목록 밖(zip·hwp·octet-stream 등). 제품 규칙을 이관 때문에
                # 넓히지 않는다 — 건너뛰고 사실을 남긴다.
                self.result.attachments_rejected += 1
                self.report.finding(
                    SEVERITY_CLASSIFIED, "confluence_attachment_rejected", "files",
                    f"{name}: {exc}", ref=legacy_id,
                )
                lost(keys or {att_id}, name, _REJECTED_LINE)
                continue
            self._map(legacy_id, T_FILE, record.id)
            self.result.attachments_attached += 1
            for key in keys or {att_id}:
                if key:
                    urls[key] = _ATTACHMENT_URL % link.id
        return urls, skipped, notes

    # ── 댓글 ─────────────────────────────────────────────────────────────────

    def _load_comments(self, document: Document, page_id: str, rows: list[dict]) -> None:
        """댓글을 **기존 구조**에 넣는다 (19번). 새 댓글 시스템을 만들지 않는다.

        `document_comments.author_user_id` 는 NOT NULL 이다. 작성자를 못 풀면 실행
        계정으로 넣되 **본문 첫 줄에 원 작성자와 시각을 적는다** — 내용을 잃지 않으면서
        남의 이름을 사칭하지도 않는다.
        """
        for row in rows or []:
            comment_id = str(row.get("id") or "")
            if not comment_id:
                continue
            legacy_id = f"{page_id}:c:{comment_id}"
            if self._mapped(legacy_id, T_COMMENT) is not None:
                continue  # 두 번 돌려도 안 늘어난다
            text = _comment_text(row)
            if not text:
                continue
            author_email = ((row.get("version") or {}).get("authorEmail")) or ""
            author = self._user_for(author_email)
            display = _comment_author_label(row)
            when = _ts((row.get("version") or {}).get("createdAt"))
            body = text
            if author is None:
                self.result.comments_without_author += 1
                head = f"{display} 님이 {when:%Y-%m-%d} 에 Confluence 에 남긴 댓글입니다." \
                    if when else f"{display} 님이 Confluence 에 남긴 댓글입니다."
                body = f"{head}\n\n{text}"
            created = DocumentComment(
                document_id=document.id,
                author_user_id=(author.id if author else self.actor.id),
                body=body[:2000],
            )
            if when is not None:
                created.created_at = when
                created.updated_at = when
            self.db.add(created)
            self.db.flush()
            self._map(legacy_id, T_COMMENT, created.id)
            self.result.comments_created += 1

    # ── 대조 게이트 ──────────────────────────────────────────────────────────

    def reconcile(
        self, enumerated: int, *, report=None, attachments_seen: int | None = None
    ) -> StageResult:
        """🔴 「전부 가져왔다」를 **주장이 아니라 증명**으로 만든다 (14번).

        열거한 페이지 수와, 만들었거나 고쳤거나 **명시적으로 건너뛴** 수가 같아야 한다.
        안 맞으면 어딘가에서 페이지가 조용히 사라진 것이고, 그 침묵이 이 회차가 고치는
        결함의 모양이다.

        ## 첨부도 같은 대조를 받는다

        🔴 이 회차에 실제로 일어난 일이다: 524쪽이 전부 들어오고 첨부는 **1,458개 중 0개**가
        들어왔는데 회차는 `CONFLUENCE_IMPORT_OK` 로 끝났다. 페이지 대조만 있었고, 첨부
        실패는 전부 「분류된 예외」라 판정을 안 건드렸기 때문이다.

        원인 둘(리다이렉트·0바이트)은 각각 막았다. 하지만 **그 사고를 잡아 줄 검사**는
        안 생겼었다 — 다음에 다른 이유로 첨부가 통째로 실패하면 운영자는 다시 초록을 본다.
        그래서 여기서 센다: 원본에 첨부가 있었는데 **하나도 못 옮겼으면 실패**다.
        """
        stage = StageResult(name="confluence_reconcile")
        stage.inserted = self.result.documents_created
        stage.updated = self.result.documents_updated
        stage.skipped = self.result.documents_skipped
        # 🔴 이 대조를 **검사**로도 남긴다. Finding 만 남기면 보고서의 자기 판정이
        # 「검사 0건」이 되고, 그때 보고서 마지막 줄은 아무 문제가 없는 회차에도 FAIL 을
        # 찍는다 — 괜찮은데 FAIL 이라고 적힌 원장은 다음 사람이 안 믿는다.
        (report or self.report).check(
            "Confluence 페이지 전수", self.result.accounted == enumerated,
            enumerated, self.result.accounted,
            "열거한 페이지가 전부 설명됐는가. 만들었거나, 고쳤거나, 건너뛰었거나.",
        )
        if self.result.accounted != enumerated:
            self.report.finding(
                SEVERITY_BLOCKING, "confluence_page_count_mismatch", "documents",
                f"열거한 페이지 {enumerated}건 중 {self.result.accounted}건만 "
                "설명됐습니다. 나머지는 오류도 없이 사라진 것입니다.",
            )
        elif self.result.documents_skipped:
            self.report.finding(
                SEVERITY_NOTE, "confluence_pages_skipped", "documents",
                f"페이지 {self.result.documents_skipped}건을 건너뛰었습니다: "
                + ", ".join(self.result.skipped_page_ids[:20]),
            )

        if attachments_seen:
            # 이번에 옮긴 것 + 지난 회차가 이미 옮겨 둔 것. 둘 다 「지금 문서에 붙어 있다」다.
            got = self.result.attachments_attached + self.result.attachments_reused
            # 「하나도 못 옮겼다」가 판정 기준이다. 몇 개를 건너뛰는 것은 정상이고(3MB·형식),
            # 전부를 건너뛰는 것은 규칙이 아니라 고장이다.
            (report or self.report).check(
                "Confluence 첨부가 들어왔는가", got > 0, "1건 이상", f"{got}건",
                f"원본이 가진 첨부 {attachments_seen}건 중 하나라도 옮겼는가. "
                "전부 못 옮긴 회차가 초록으로 끝난 적이 있다.",
            )
            if got == 0:
                self.report.finding(
                    SEVERITY_BLOCKING, "confluence_no_attachment_landed", "files",
                    f"원본에 첨부가 {attachments_seen}건 있는데 문서에 붙은 것이 없습니다. "
                    "본문의 그림이 전부 자리표시자가 됩니다.",
                )
            elif got * 2 < attachments_seen:
                # 절반 넘게 못 옮겼으면 규칙 때문일 수도, 고장일 수도 있다. 판정을 막지는
                # 않되 **사람이 반드시 보게** 남긴다.
                self.report.finding(
                    SEVERITY_BLOCKING, "confluence_most_attachments_missing", "files",
                    f"첨부 {attachments_seen}건 중 {got}건만 들어왔습니다. "
                    "건너뛴 사유를 확인해 주세요.",
                )
        return stage


# ── 값 하나씩 ────────────────────────────────────────────────────────────────


def _ts(value):
    """ISO 8601 → naive UTC. 못 읽으면 `None` — 지어내지 않는다."""
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _comment_text(row: dict) -> str:
    """댓글 본문의 글자. 우리 댓글은 **글자**이므로 서식은 안 옮긴다."""
    body = row.get("body") or {}
    raw = (body.get("atlas_doc_format") or {}).get("value")
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            return adf_plain_text(json.loads(raw)).strip()
        except ValueError:
            return ""
    return str((body.get("storage") or {}).get("value") or "").strip()


def _comment_author_label(row: dict) -> str:
    version = row.get("version") or {}
    return str(
        version.get("authorDisplayName")
        or version.get("authorId")
        or "알 수 없는 사람"
    )
