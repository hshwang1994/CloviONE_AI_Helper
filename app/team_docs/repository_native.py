"""DocumentRepository 의 자체 DB 구현 (S14). **나가는 호출이 하나도 없다.**

`repository_notion.py` 와 짝을 이루는 두 번째 구현체이고, 두 파일의 차이는 「소스가 어디인가」
하나다. 목록과 상세 메타는 저쪽도 이미 로컬 미러(`app/team_docs/repository.py`)를 읽고 있어서
**같은 함수에 그대로 위임**한다 — 소스를 바꿔도 목록 응답이 한 글자도 달라지지 않아야 하고,
같은 질의를 여기서 다시 적으면 두 벌이 갈라지는 날 그 사실이 목록에서만 조용히 드러난다.

## 이 파일은 `notion_docs` 를 import 하지 않는다

그것이 이 구현체의 존재 이유다. `scripts/static_checks.sh` 의 경계 검사가 이름으로 한 번
막고(`_notion.py` 가 아닌 파일은 Notion 모듈을 못 부른다),
`tests/integration/test_native_document_repository.py` 가 모듈 소스와 실제 호출로 다시 막는다.
정적 검사만 두면 이름을 바꿔 같은 일을 하는 코드를 못 잡고, 시험만 두면 「생각조차 안 한
import」를 못 잡는다.

## 본문의 정본은 둘이 아니라 하나이고, 순서가 그것을 정한다

  1. `document_cache.body_markdown` 이 NULL 이 아니면 **그것이 정본이다.** 포털에서 저장한
     본문이고, 자체 DB 소스에서는 `save_body` 가 오직 이 칸만 쓴다.
  2. NULL 이면 S13 이 옮겨 둔 지식 도메인의 현재 판을 읽는다. 다리는
     `documents.legacy_page_id = document_cache.notion_page_id` 이고, 그 다리를 S13 이
     `app/migration/load.py::load_documents` 에서 놓았다. 이 경로가 없으면 「포털에서 한 번도
     안 고친 문서」의 본문이 Notion 을 걷어내는 순간 화면에서 통째로 사라진다.

NULL 과 빈 문자열을 여기서도 구별한다(`models.py::DocumentCache.body_markdown` 의 그 이유).
둘을 뭉개면 옮겨 온 문서 전부가 빈 본문으로 보인다.

## 파생 컬럼 정적 검사에 이 파일 이름이 아직 없다

`scripts/check_domain_single_source.py` 의 `body_markdown` 규칙은 미러 컬럼을 쓰는 파일을
이름으로 열어 준다(`repository_notion.py`·`router.py`·`service.py`…). 이 파일도 같은 미러
컬럼을 쓰므로 그 목록에 함께 있어야 한다. 목록을 여기서 못 고치는 이유는 티켓 쪽 자체 DB
구현체도 같은 줄을 필요로 해서, 두 작업이 같은 파일을 동시에 고치면 한쪽이 지워지기
때문이다 — S14 배선이 한 번에 넣는다.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.models_base import new_uuid, utcnow
from app.knowledge.models import Document, DocumentVersion
from app.projects.models import Project
from app.team_docs import repository
from app.team_docs.models import DocumentCache
from app.tickets.repository import BodySaveResult


class NativeArchiveNeedsSessionError(RuntimeError):
    """보관처리에 DB 세션이 필요한데 못 받았다.

    휴지통 영구삭제 경로(`app/trash/service.py::_archive_notion`)가 저장소에 `db=None` 을
    넘긴다. 소스가 Notion 이던 동안에는 그것이 옳았다 — 그 자리가 하는 일은 저쪽 페이지를
    보관처리하는 것뿐이고, 우리 캐시 행은 다음 동기화가 정리했다. 자체 DB 소스에는 그
    「다음 동기화」가 없으므로 보관처리 자체가 로컬 쓰기다.

    세션 없이 조용히 통과시키지 않는 이유는 통과시켰을 때 벌어지는 일이다: 휴지통 행은
    지워지고 문서 행은 `archived=False` 로 남아, **사용자가 지운 문서가 목록에 되살아난다**
    (목록은 휴지통에 있는 page id 를 빼서 감추고 있었을 뿐이다). 반대로 여기서 실패하면
    휴지통 행이 그대로 남아 문서는 계속 안 보이고, 실패 사유가 운영 화면에 뜬다. 되살아나는
    쪽이 훨씬 나쁘다.
    """


# ── 본문 렌더 ────────────────────────────────────────────────────────────────
#
# 화면이 받는 본문은 `[{kind, text, ...}]` 축약형이다(프런트 `DocBody`). 저장된 마크다운을
# 그 모양으로 바꾸는 것이 아래 함수들이고, 규칙은 `app/core/notion_blocks.py` 가 정한 것과
# **같은 규칙**이다 — 프런트 편집기 미리보기(BodyEditor)가 그 규칙을 그대로 쓰기 때문에,
# 여기서 다르게 읽으면 사용자가 미리보기에서 본 것과 저장 뒤에 보는 것이 달라진다.
#
# 그 모듈의 `markdown_to_blocks` 를 부르지 않는 이유는 그 함수가 **Notion API 의 상한 둘**을
# 함께 들고 있기 때문이다: 한 번에 100 블록(`MAX_BLOCKS`), 한 줄 1900 자(`MAX_LINE_CHARS`).
# 저쪽에서는 요청 상한이라 맞는 수지만, 자체 DB 에는 본문이 통째로 들어가 있어서 그 수를
# 화면 렌더에 그대로 쓰면 **저장된 글이 101 번째 줄부터 화면에서 사라진다.** 편집기는 정본
# 마크다운을 그대로 열어 전문을 보여 주므로, 사용자에게는 "읽기 화면에서만 글이 잘린다" 로
# 보인다. 규칙이 갈라지지 않는지는 시험이 두 구현의 줄 분류를 맞춰 보며 고정한다.
_DIVIDER_LINES = frozenset({"---", "___", "***"})
_HEADING_PREFIXES: tuple[tuple[str, str], ...] = (
    ("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"),
)
_BULLET_PREFIXES = ("- ", "* ")
_NUMBERED_LINE = re.compile(r"^(\d+)\.\s+(.*)$")


def _line_item(line: str) -> dict:
    """마크다운 한 줄 → 렌더 항목 하나.

    제목·목록은 앞뒤 공백을 떼고 읽지만 문단은 원문 줄을 그대로 싣는다. 들쭉날쭉해 보여도
    `markdown_to_blocks` 가 하는 것과 같아야 한다 — 여기서 문단까지 깎으면 코드 조각을 붙여
    넣은 문단의 들여쓰기가 화면에서만 사라진다.

    비어 있거나 공백뿐인 줄은 글자 없는 문단이다. 그것이 문단 사이의 간격이 되고, 지워
    버리면 문단이 전부 붙어 한 덩어리로 보인다.
    """
    stripped = line.strip()
    if stripped in _DIVIDER_LINES:
        return {"kind": "divider", "text": ""}
    for prefix, kind in _HEADING_PREFIXES:
        if stripped.startswith(prefix):
            text = stripped[len(prefix):]
            return {"kind": kind, "text": text if text.strip() else ""}
    for prefix in _BULLET_PREFIXES:
        if stripped.startswith(prefix):
            text = stripped[len(prefix):]
            return {"kind": "bulleted", "text": text if text.strip() else ""}
    numbered = _NUMBERED_LINE.match(stripped)
    if numbered:
        text = numbered.group(2)
        return {"kind": "numbered", "text": text if text.strip() else ""}
    return {"kind": "paragraph", "text": line if line.strip() else ""}


def markdown_to_items(body_markdown: str | None) -> list[dict]:
    """저장된 마크다운 → 화면이 받는 `[{kind, text}]`.

    `has_children` 를 안 싣는다. 그 값은 Notion 페이지의 접힌 토글·중첩 목록처럼 **한 겹만
    읽어서 화면에 안 실린 자식**이 있다는 경고였는데(H-1), 마크다운 본문에는 못 읽은 자식이라는
    상태 자체가 없다. 없는 경고를 싣는 것은 화면에 거짓을 하나 더 만드는 일이다.
    """
    if not body_markdown:
        return []
    return [_line_item(line) for line in body_markdown.split("\n")]


class NativeDocumentRepository:
    """자체 DB 가 정본인 문서 저장소.

    `settings` 와 `outbound` 를 받는 이유는 선택기(`app/core/source_registry.py`)가 모든
    구현체를 같은 방법으로 만들기 때문이다. **둘 다 붙들지 않는다** — 특히 `outbound` 를
    필드로 두면 "여기서 한 번만 부르면 되는데" 가 언젠가 반드시 생기고, 그러면 이 구현체가
    지키기로 한 성질(나가는 호출이 없다)이 조용히 깨진다. 시험이 그 필드가 없다는 것까지 본다.
    """

    def __init__(self, settings=None, outbound=None) -> None:
        # 받기만 하고 버린다. 붙들지 않는 것이 이 구현체가 지키는 성질이다(위 docstring).
        del settings, outbound

    # ── 로컬 정본 읽기(Notion 구현과 같은 함수에 위임) ───────────────────────

    def list_documents(self, db: Session, **filters):
        return repository.list_documents(db, **filters)

    def get(self, db: Session, *, page_id: str):
        return repository.get_by_page_id(db, page_id)

    # ── 본문 ─────────────────────────────────────────────────────────────────

    def body_blocks(self, db: Session, *, page_id: str) -> list[dict]:
        """본문을 화면 렌더용 축약형으로 돌려준다. **저장된 것만 읽는다.**

        Notion 구현은 이 자리에서 페이지 블록을 실시간으로 읽었고, 그래서 상세 라우터가
        이 호출만 따로 격리한다(실패해도 메타는 보여 준다). 자체 DB 에서는 실패할 외부
        구간이 없어져서 그 격리가 하는 일이 없어지지만, 호출부는 그대로 둔다 — 격리를
        걷어내는 것은 이 구현체의 일이 아니고, 남아 있어도 해가 없다.

        찾는 순서는 모듈 docstring 에 적은 그대로다: 포털 정본 → S13 이 옮긴 판.

        ## 없는 page id 는 빈 본문이 아니라 404 다

        빈 목록으로 답하면 「본문이 없는 문서」와 「없는 문서」가 같은 답이 된다. 그러면
        편집기가 빈 칸으로 열리고 거기서의 저장이 **없는 문서를 만드는 시도**가 된다.
        모르는 것은 모른다고 답해야 호출부가 격리할 수 있다.

        ## 아는 문서인데 본문이 어디에도 없으면 빈 본문이다

        이때는 정말로 본문이 없다. 자체 DB 가 정본이 된 뒤에는 「저쪽에는 있는데 우리가
        못 읽은 것」이라는 상태가 없어서, 빈 본문으로 열고 사용자가 채우게 하는 것이 맞다.
        """
        row = repository.get_by_page_id(db, page_id)
        if row is None:
            raise NotFoundError("문서를 찾을 수 없습니다.")
        if row.body_markdown is not None:
            return markdown_to_items(row.body_markdown)
        return markdown_to_items(self._migrated_body(db, page_id))

    @staticmethod
    def _migrated_body(db: Session, page_id: str) -> str | None:
        """S13 이 옮겨 둔 지식 도메인 본문(마크다운). 다리가 없으면 None.

        정본은 Block JSON 이고 여기서 읽는 `body_markdown` 은 **파생**이다(D-198). 파생을
        읽는 이유는 그 값을 만드는 자리가 `app/knowledge/blocks.py` 하나뿐이라서다 — 여기서
        Block JSON 을 다시 마크다운으로 풀면 같은 판이 지식 화면과 문서 화면에서 다른 글이
        된다. 만드는 곳은 하나, 읽는 곳은 여럿이어야 한다.
        """
        return db.execute(
            select(DocumentVersion.body_markdown)
            .join(Document, Document.current_version_id == DocumentVersion.id)
            .where(Document.legacy_page_id == page_id)
        ).scalar_one_or_none()

    def save_body(
        self, db: Session, *, page_id: str, body_markdown: str, now: datetime | None = None
    ) -> BodySaveResult:
        """본문을 저장한다. 자체 DB 에서는 **쓸 곳이 한 곳뿐이라 순서 문제가 사라진다.**

        Notion 구현의 그 긴 절차 - 정본을 먼저 쓰고, 커밋으로 확정하고, 그다음 push 하고,
        push 실패는 예외로 던지지 않고 행에 적어 둔다 - 는 전부 **정본과 원본이 다른 곳에
        있어서** 필요했다. 순서를 지키지 않으면 Notion 이 죽은 날 사용자가 방금 친 글이
        통째로 사라지고, push 실패를 예외로 던지면 요청 트랜잭션이 롤백되면서 방금 저장한
        본문까지 함께 되돌아간다.

        여기서는 정본이 이 행 하나다. 밀어 넣을 곳이 없으니 실패할 push 도, 그 실패를 담을
        `body_sync_error` 도, 느린 외부 구간을 통과하려고 미리 뜨던 커밋도 필요 없다. 그래서
        `synced=True` 는 낙관이 아니라 사실이다 - 어긋날 상대가 없다.

        그래도 **정본을 먼저 쓴다는 순서 자체는 남긴다.** 지금은 그 뒤에 아무것도 없어서
        지킬 것이 없어 보이지만, 이 함수에 나중에 무엇이 붙든(색인·알림·판 쌓기) 그것들은
        사용자 글이 이미 들어간 다음에 일어나야 한다.

        `body_sync_error` 를 **비운다.** Notion 시절에 어긋난 채로 남은 문서가 있고, 그
        배너는 「원본에 못 밀어 넣었다」는 뜻이다. 원본이 없어진 뒤에도 그 문구를 계속
        띄우면 사용자는 고칠 수 없는 경고를 영원히 보게 된다.
        """
        stamp = now or utcnow()
        row = repository.get_by_page_id(db, page_id)
        if row is None:
            # 부르는 쪽(service.save_document_body)이 범위 판정으로 이미 행을 읽었다.
            # 여기까지 None 이면 그 사이에 사라진 것이므로 없는 문서로 답한다.
            raise NotFoundError("문서를 찾을 수 없습니다.")

        row.body_markdown = body_markdown
        row.body_sync_error = None
        row.body_synced_at = stamp
        # flush 로 충분하다. Notion 구현이 여기서 commit 한 것은 뒤따르는 느린 외부 호출을
        # 통과하는 동안 요청 종료 시점 커밋이 스냅샷 노후화로 거부될 수 있어서였다 - 그
        # 구간이 없어졌으므로 이 앱의 다른 쓰기와 같은 모양으로 요청 트랜잭션에 맡긴다.
        db.flush()
        return BodySaveResult(uid=row.id, body_markdown=body_markdown, synced=True)

    # ── 생성 폼 ──────────────────────────────────────────────────────────────

    def project_names(self, db: Session) -> list[str]:
        """새 문서에 붙일 수 있는 프로젝트 이름 전부.

        Notion 구현이 이 왕복을 하던 이유가 그대로 남는다: 필터 목록은 「문서가 있는
        프로젝트」만 보여 주지만, 새로 쓸 때는 문서가 한 건도 없는 프로젝트도 골라야 한다.

        보관한 프로젝트(`archived_at`)는 뺀다. 그쪽은 소프트 삭제라 행은 남아 있어도 사용자
        눈에는 지워진 프로젝트이고, 지운 프로젝트를 새 문서에 붙일 수 있으면 그 문서는
        만들자마자 아무 데도 안 보이는 자리에 놓인다.

        이름은 유일하지 않으므로 집합으로 모아 정렬한다 - 같은 이름이 두 줄로 보이면
        사용자는 둘이 다른 프로젝트라고 읽고, 어느 쪽을 골라야 하는지 알 방법이 없다.
        """
        rows = db.execute(
            select(Project.name).where(Project.archived_at.is_(None))
        ).scalars().all()
        return sorted({(name or "").strip() for name in rows if (name or "").strip()})

    def create(
        self, db: Session, *, title: str, status, priority, owner, memo, body,
        project_names: list[str], author_id: str | None,
    ) -> dict:
        """새 문서를 만들고 **생성된 페이지 모양의 dict** 를 돌려준다.

        호출부(`app/team_docs/service.py::cache_created_document`)를 그대로 두려고 이 모양을
        지킨다. 그 함수는 소스가 준 페이지에서 `id`·`url`·`created_time`·`last_edited_time`
        넷을 읽고 나머지 칸(분류·소속·작성자)을 자기가 채운다. 자체 DB 라고 그 함수를 건너뛰고
        여기서 전부 쓰면, 「포털에서 만든 문서의 소속은 만든 사람의 자리가 정한다」(0060 §9)
        같은 규칙이 두 곳에 생긴다.

        그래서 여기서 하는 일은 **행을 먼저 만들고 그 넷을 돌려주는 것**이다. 호출부는 같은
        page id 로 그 행을 다시 찾아 나머지를 채운다(`get_by_page_id(...) or DocumentCache(...)`).

        ## 본문은 여기서 쓴다

        `cache_created_document` 는 본문을 안 건드린다 - Notion 시절에는 본문이 저쪽 페이지에
        들어갔기 때문이다. 여기서 안 쓰면 사용자가 작성 폼에 친 본문이 **저장되는 곳이 없다.**
        빈 본문이어도 NULL 이 아니라 빈 문자열로 쓴다: 자체 DB 에서는 이 칸이 정본이라,
        NULL(「포털에서 고친 적이 없다」)은 만들어진 적 없는 상태를 뜻하게 된다.

        ## page id 는 우리가 짓는다

        `document_cache.notion_page_id` 는 문서의 딥링크 키이고 댓글·즐겨찾기·휴지통이 전부
        그 값으로 문서를 가리킨다. 소스가 더 이상 id 를 주지 않으므로 UUID 를 발급한다.

        `url` 은 None 이다. 그 칸은 「바깥 원본으로 가는 링크」이고 화면은 http(s) 만 링크로
        그린다(`safeExternal`). 바깥 원본이 없는 문서에 링크 자리를 만들어 주면 그 자리는
        어디에도 닿지 않는다.

        `project_names` 는 여기서 쓰지 않는다 - 호출부가 이름 목록을 그대로 캐시 행에 적는다
        (Notion 구현만 그 이름들을 relation id 로 해석해야 했다).
        """
        stamp = utcnow()
        page_id = new_uuid()
        row = DocumentCache(
            notion_page_id=page_id,
            title=title or "",
            body_markdown=body or "",
            created_time=stamp,
            last_edited=stamp,
            synced_at=stamp,
        )
        db.add(row)
        db.flush()
        return {
            "id": page_id,
            "url": None,
            # 호출부가 `parse_dt` 로 읽는다. naive UTC 를 ISO 로 적고 Z 를 붙인다 -
            # 저장 계약이 UTC 이고, 오프셋 없는 문자열은 읽는 쪽이 현지 시각으로 오해할 수 있다.
            "created_time": stamp.isoformat() + "Z",
            "last_edited_time": stamp.isoformat() + "Z",
        }

    # ── 보관처리 ─────────────────────────────────────────────────────────────

    def archive(self, db: Session | None, *, page_id: str) -> None:
        """보관처리한다. 자체 DB 에서 그것은 **이 행의 `archived` 를 세우는 일**이다.

        Notion 시절의 뜻은 「저쪽 페이지를 휴지통으로 보낸다」였고, 우리 캐시 행은 다음
        동기화가 정리했다(보관처리된 페이지는 소스 조회 결과에서 빠진다). 자체 DB 에는 그
        동기화가 없으므로 그 정리를 여기서 한다.

        **행을 지우지 않는다.** 지우면 그 문서의 댓글·즐겨찾기·최근 열람이 가리키는 곳이
        사라지고(`document_comments.document_id` 는 `SET NULL` 이라 조용히 끊긴다), 무엇보다
        되돌릴 방법이 없다. `archived=True` 면 목록 질의가 이미 그 행을 빼므로
        (`repository.list_documents`) 사용자에게는 사라진 것과 같다.

        없는 page id 는 조용히 넘어간다. 이 함수를 부르는 곳은 보관기간이 끝난 휴지통 항목을
        치우는 경로이고, 원본이 이미 없는 것은 「할 일이 끝났다」이지 오류가 아니다 - 여기서
        던지면 그 휴지통 행이 매 주기 실패하며 영원히 남는다.
        """
        if db is None:
            raise NativeArchiveNeedsSessionError(
                "자체 DB 소스의 문서 보관처리에는 DB 세션이 필요합니다."
            )
        row = repository.get_by_page_id(db, page_id)
        if row is None:
            return
        row.archived = True
        db.flush()
