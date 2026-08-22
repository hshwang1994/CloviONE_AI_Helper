"""Knowledge Domain 표 (S7). 공간 · 폴더 트리 · 문서 · 버전 · 태그 · 관계 · 멘션.

## 이 파일이 지키는 것 셋

**1. 본문의 정본은 Block JSON 하나다** (D-198). `document_versions.body` 가 그것이고
Markdown 과 Plain Text 는 **파생**이다. 파생을 손으로 적을 수 있으면 언젠가 갈라지고,
갈라진 뒤에는 인용이 가리키는 문장과 화면이 보여 주는 문장이 달라진다. 그래서 파생
컬럼은 `app/knowledge/blocks.py` 하나만 만든다(`check_domain_single_source.py`).

**2. 폴더의 `path` 와 `depth` 는 앱이 쓰지 않는다.** S6 이 `canonical_key` 에서 쓴 방법
그대로다(D-236) — BEFORE 트리거가 부모에서 파생시키고, 옮기면 AFTER 트리거가 자손을
따라 고친다. 순환도 그 트리거가 막는다. 「조심해서 쓰자」로 막을 수 있는 성질이 아니다.

**3. 권한은 공간이 정하고, 폴더는 정하지 않는다** (§5.3). 문서를 다른 폴더로 옮기는 것은
**정리**이고 다른 사람이 볼 수 있게 되는 일이 아니다. 그래서 문서에는 소속 컬럼이 없다 —
`knowledge_spaces` 가 그것을 들고, 문서는 자기 공간의 가시성을 그대로 물려받는다.
문서 자신이 갖는 것은 좁히는 축(`confidential`)과 직접 부여뿐이다.

## 낙관적 잠금은 S6 이 정한 규약 그대로다

`version` 은 정수이고 이름이 `Ticket`·`Project`·`DocumentCache` 와 같다(D-240). 화면이
같은 충돌을 자원마다 다른 필드 이름으로 다루면 프런트가 여러 벌의 처리를 갖게 되고,
그중 하나가 빠진 화면에서 덮어쓰기가 조용히 일어난다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)
from app.core.ownership import (
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)

# ── 공간의 소속 종류 ─────────────────────────────────────────────────────────
#
# 어휘의 정본은 `app/core/ownership.py` 다. 공간이 실제로 저장하는 넷만 다시 노출한다 —
# `document_cache.owner_kind` 와 **같은 값 집합**이라 `effective_visibility_clause` 의
# 소속 갈래(`_stored_ownership_rules`)를 그대로 쓸 수 있다.
SPACE_OWNER_KINDS: tuple[str, ...] = (
    OWNER_PROJECT, OWNER_DEPARTMENT, OWNER_ORGANIZATION, OWNER_UNSET,
)

# ── 문서 출처 (§5.3) ─────────────────────────────────────────────────────────
#
# 「누가 이 문서를 만들었는가」가 아니라 「무엇이 만들었는가」다. AI 가 만든 문서를
# 사람이 쓴 문서와 구별할 수 없으면, 나중에 「이 문장 근거가 뭐죠」에 답할 수 없다.
SOURCE_USER = "USER"
SOURCE_AI = "AI"
SOURCE_MIGRATION = "MIGRATION"
SOURCE_TYPES: tuple[str, ...] = (SOURCE_USER, SOURCE_AI, SOURCE_MIGRATION)

# ── 버전이 생긴 이유 ─────────────────────────────────────────────────────────
#
# `RESTORE` 를 따로 두는 이유: 되돌리기는 **새 버전을 쌓는 것**이지 이력을 지우는 것이
# 아니다(아래 `DocumentVersion` docstring). 사유를 안 남기면 「왜 3판이 1판과 같지」에
# 아무도 답할 수 없다.
VSRC_USER = "USER"
VSRC_AI = "AI"
VSRC_MIGRATION = "MIGRATION"
VSRC_RESTORE = "RESTORE"
VERSION_SOURCES: tuple[str, ...] = (VSRC_USER, VSRC_AI, VSRC_MIGRATION, VSRC_RESTORE)

# ── 문서 관계 종류 ───────────────────────────────────────────────────────────
#
# S6 의 `ticket_relations` 와 **같은 모양**이다: 방향 있는 것 둘, 없는 것 하나. 방향
# 없는 관계를 두 행으로 저장하면 한쪽만 지워지는 날이 오므로 한 행으로 저장하고
# 순서를 제약이 고정한다(`from < to`).
DREL_SUPERSEDES = "supersedes"    # 이 문서가 저 문서를 대체한다
DREL_REFERENCES = "references"    # 이 문서가 저 문서를 근거로 든다
DREL_RELATES_TO = "relates_to"    # 방향 없음
DREL_KINDS: tuple[str, ...] = (DREL_SUPERSEDES, DREL_REFERENCES, DREL_RELATES_TO)

# ── 멘션 대상 ────────────────────────────────────────────────────────────────
MENTION_USER = "user"
MENTION_DOCUMENT = "document"
MENTION_TICKET = "ticket"
MENTION_KINDS: tuple[str, ...] = (MENTION_USER, MENTION_DOCUMENT, MENTION_TICKET)

# 폴더 순서. S6 의 `backlog_rank` 와 같은 수다 — 정밀도 없는 `numeric` 이라 두 이웃
# 사이에 언제나 중점이 있고, 한 폴더를 옮길 때 형제 전부를 다시 매기지 않는다.
# 자리수 재조정은 `app/work/rank.py` 가 그대로 담당한다(같은 문제라 두 벌로 만들지 않는다).
FOLDER_SORT_TYPE = Numeric()
FOLDER_SORT_STEP = Decimal(1024)

# 트리 깊이 상한. 무한 깊이를 허용하면 `path` 가 무한히 길어지고, 그보다 먼저
# 사람이 못 쓰는 화면이 된다. 트리거가 이 값을 강제한다.
MAX_FOLDER_DEPTH = 16


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a','b')` — CHECK 제약을 상수 튜플에서 만든다.

    `app/work/models.py` 와 같은 이유다: 손으로 다시 적으면 상수를 늘린 날 제약만 옛
    목록에 남고, 새 값이 조용히 거절된다.
    """
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class KnowledgeSpace(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """지식 공간 — **권한의 단위**다.

    문서를 담는 상자가 아니라 「누가 볼 수 있는가」의 경계다. 폴더가 그 일을 하지 않는
    이유가 §5.3 에 한 줄로 적혀 있다: **폴더 이동이 권한을 바꾸지 않는다.** 정리하다가
    문서가 다른 부서에 보이기 시작하는 일은 아무도 눈치채지 못한다.

    소속 컬럼 셋(`owner_kind`·`owner_dept_id`·`owner_project_id`)은 `document_cache` 와
    **같은 이름의 같은 뜻**이다. 같은 이름이어야 `effective_visibility_clause` 의
    소속 갈래를 자원마다 다시 쓰지 않는다(D-194).
    """

    __tablename__ = "knowledge_spaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 주소에 나가는 이름. 조직 안에서 유일하다 — 두 공간이 같은 slug 면 링크가 어느
    # 쪽을 여는지 요청마다 달라진다.
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    owner_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OWNER_UNSET,
        server_default=OWNER_UNSET, index=True,
    )
    owner_dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id"), nullable=True, index=True
    )
    owner_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )

    # 좁히는 축은 이 하나뿐이다 (D-193). 소유자 + 명시 부여자 + `SPACE_ADMIN` 만 본다.
    confidential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __table_args__ = (
        CheckConstraint(_in_list("owner_kind", SPACE_OWNER_KINDS), name="ck_kspace_owner_kind"),
        # 소속 종류와 그 대상은 함께 있거나 함께 없다. 「부서 소유인데 부서가 없다」는
        # 행은 어느 갈래에도 안 걸려 전역 관리자만 보게 되는데, 화면에는 그 사실이
        # 안 나온다 — 만든 사람이 자기 공간을 못 찾는다.
        CheckConstraint(
            "(owner_kind = 'department') = (owner_dept_id IS NOT NULL)",
            name="ck_kspace_dept_pair",
        ),
        CheckConstraint(
            "(owner_kind = 'project') = (owner_project_id IS NOT NULL)",
            name="ck_kspace_project_pair",
        ),
        Index("uq_kspace_slug", "org_id", "slug", unique=True),
        Index("ix_kspace_owner", "org_id", "owner_kind", "archived"),
    )


class Folder(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """공간 안의 폴더 트리. **`path` 와 `depth` 는 앱이 안 쓴다.**

    ## 왜 트리거인가

    자료구조가 두 벌이기 때문이다: 부모를 가리키는 `parent_id` 와, 조상을 한 줄에 담은
    `path`. 둘이 어긋나면 「이 폴더 아래 전부」가 틀린 답을 내는데, 그 틀림은 조용하다 —
    목록에 한 건이 덜 나오는 것으로 보인다. `parent_id` 만 두고 매번 재귀 질의를 하면
    안 어긋나지만, 문서 목록이 폴더마다 재귀를 돌게 된다.

    그래서 S6 이 `canonical_key` 에서 쓴 방법을 그대로 쓴다(D-236): **파생을 트리거가
    만든다.** 앱이 무엇을 적든 BEFORE 트리거가 덮어쓰고, 폴더를 옮기면 AFTER 트리거가
    자손의 `path` 를 따라 고친다. 어긋날 자리가 없다.

    순환도 같은 트리거가 막는다 — 새 부모의 `path` 안에 자기 id 가 있으면 거절한다.
    앱에서만 막으면 「한 곳만 빠뜨린 날」에 트리가 통째로 안 열린다(무한 재귀).

    ## `path` 의 모양

    `/<조상id>/…/<자기id>/` — 양끝에 구분자를 둔다. 그래야 `path LIKE '/a/%'` 가
    토큰 경계를 정확히 잡는다(`NAMES_SEP` 을 sentinel 로 감싸는 것과 같은 이유다).
    """

    __tablename__ = "folders"

    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 폴더를 지우면 그 아래 폴더도 함께 지운다. 문서는 안 지운다 — `documents.folder_id`
    # 가 `SET NULL` 이라 공간 뿌리로 올라온다(아래 `Document` docstring).
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("folders.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 트리거가 만든다. 앱이 쓰면 `check_domain_single_source.py` 가 잡는다.
    path: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    depth: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    sort_order: Mapped[Decimal] = mapped_column(FOLDER_SORT_TYPE, nullable=False)

    __table_args__ = (
        CheckConstraint("id <> parent_id", name="ck_folder_not_self"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_folder_name_nonempty"),
        CheckConstraint(f"depth <= {MAX_FOLDER_DEPTH}", name="ck_folder_depth"),
        # 같은 부모 아래 같은 이름은 없다. PG 에서 NULL 은 서로 다르므로 뿌리 폴더는
        # 부분 유니크로 따로 잡는다 — 안 그러면 뿌리에만 같은 이름이 여럿 생긴다.
        Index(
            "uq_folder_sibling_name", "space_id", "parent_id", "name", unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
        Index(
            "uq_folder_root_name", "space_id", "name", unique=True,
            postgresql_where=text("parent_id IS NULL"),
        ),
        Index("ix_folder_sibling_order", "space_id", "parent_id", "sort_order"),
        # 「이 폴더 아래 전부」의 인덱스. `path LIKE '/a/%'` 는 접두 검색이라
        # `text_pattern_ops` 여야 인덱스를 탄다(기본 연산자 클래스는 로캘 정렬이다).
        Index(
            "ix_folder_subtree", "path",
            postgresql_ops={"path": "text_pattern_ops"},
        ),
    )


class Document(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """문서 한 건. **본문은 여기 없다** — `document_versions` 가 든다.

    본문을 이 표에 두면 「지금 본문」과 「이력」이 두 벌이 되고, 되돌리기가 둘을 함께
    고쳐야 하는 일이 된다. 여기는 **어느 판이 지금인가**(`current_version_id`)만 든다.

    ## 소속 컬럼이 없는 것은 빠뜨린 것이 아니다

    문서의 가시성은 **자기 공간의 가시성**이다(§5.3). 문서마다 소속을 또 두면 공간을
    옮길 때 둘이 어긋나고, 어긋난 문서는 「목록에는 없는데 링크로는 열린다」가 된다.
    문서 자신이 갖는 것은 좁히는 축(`confidential`)과 직접 부여뿐이다.

    ## `legacy_page_id` 는 S13 이 쓸 다리다

    지금은 전부 NULL 이다. Notion 미러(`document_cache.notion_page_id`)에서 옮겨 올 때
    그 값을 여기 적어 두면 **옛 링크가 계속 열린다** — S6 이 `GIT-142` 에 한 것과 같은
    성질이고, 같은 이유로 유일해야 한다(둘이 같은 옛 페이지를 주장하면 링크가 어느
    쪽을 여는지 요청마다 달라진다).
    """

    __tablename__ = "documents"

    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 폴더를 지워도 문서는 안 지운다 — 공간 뿌리로 올라온다. CASCADE 로 두면 폴더
    # 하나를 잘못 지운 날 그 아래 문서가 전부 사라지고, 문서는 재계산으로 안 돌아온다.
    folder_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("folders.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    doc_type: Mapped[str | None] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SOURCE_USER, server_default=SOURCE_USER,
        index=True,
    )
    # 지금 보여 주는 판. 두 표가 서로를 가리켜 생성 순서를 정할 수 없으므로 `use_alter`
    # 로 **나중에** 거는 FK 다 — 마이그레이션도 두 표가 다 선 다음에 `ALTER TABLE` 로
    # 같은 이름의 제약을 건다. 이름을 명시하는 이유: 이름이 없으면 autogenerate 가
    # 모델과 DB 를 대조할 때 이 제약을 「없는 것」으로 보고 매번 삭제 diff 를 낸다.
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "document_versions.id", ondelete="SET NULL", use_alter=True,
            name="documents_current_version_id_fkey",
        ),
    )
    confidential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    # 낙관적 잠금 (D-240). 티켓·프로젝트·미러와 **같은 이름의 같은 규약**이다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # S13 이 채운다. 지금은 전부 NULL 이고 그것이 정상이다.
    legacy_page_id: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(_in_list("source_type", SOURCE_TYPES), name="ck_document_source_type"),
        # NULL 이 여럿이어야 하므로 부분 유니크다. 「아직 옮겨 오지 않았다」가 흔한 값이고
        # 그것들끼리 부딪히면 안 된다.
        Index(
            "uq_document_legacy_page", "legacy_page_id", unique=True,
            postgresql_where=text("legacy_page_id IS NOT NULL"),
        ),
        Index("ix_document_space_folder", "space_id", "folder_id", "archived"),
        Index("ix_document_updated", "space_id", "updated_at"),
    )


class DocumentVersion(Base):
    """한 판. **정본은 `body`(Block JSON) 이고 나머지 둘은 파생이다** (D-198).

    ## 왜 파생을 저장하는가

    Markdown 과 Plain Text 를 매번 다시 만들 수도 있다. 그런데 검색 색인(pg_trgm ·
    FTS · 임베딩)이 Plain Text 를 읽고, 그것을 질의 시각에 만들면 색인을 만들 수가 없다.
    그래서 저장하되 **만드는 자리를 하나로 묶는다** — `app/knowledge/blocks.py` 다.
    두 곳에서 만들면 같은 판이 화면과 검색에서 다른 글이 된다.

    ## 이력은 지우지 않는다

    되돌리기는 **새 판을 쌓는 것**이다(`source = 'RESTORE'`). 3판에서 1판으로 되돌리면
    1판과 같은 본문의 **4판**이 생긴다. 이력을 잘라 내면 「누가 언제 무엇을 되돌렸는가」가
    사라지고, 그 질문은 사고가 난 다음에만 나온다.

    `prev_version_id` 는 앞판을 가리킨다. `version_no - 1` 로 찾으면 될 것 같지만,
    그것은 「번호가 연속이다」를 전제한다 — 되돌리기·병합이 생기면 전제가 깨진다.
    """

    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── 정본 ────────────────────────────────────────────────────────────────
    # ProseMirror 노드 트리. `JsonText` 가 아니라 진짜 `JSONB` 다 — 이 값은 문자열로
    # 다루지 않고 블록 단위로 읽는다(diff · 인용 앵커 · 멘션 추출).
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ── 파생 (`app/knowledge/blocks.py` 만 만든다) ──────────────────────────
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    author_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    change_reason: Mapped[str | None] = mapped_column(String(500))
    # 이 판을 만드는 데 AI 를 썼는가. 「AI 가 만든 문서」(`documents.source_type`)와
    # 다른 질문이다 — 사람이 쓴 문서의 한 문단만 AI 로 다듬은 판이 있다.
    ai_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VSRC_USER, server_default=VSRC_USER
    )
    prev_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        CheckConstraint(_in_list("source", VERSION_SOURCES), name="ck_dver_source"),
        CheckConstraint("version_no >= 1", name="ck_dver_no_positive"),
        Index("uq_dver_document_no", "document_id", "version_no", unique=True),
        Index("ix_dver_history", "document_id", "version_no"),
    )


class DocumentRelation(UUIDPrimaryKeyMixin, Base):
    """문서 사이의 관계. S6 의 `ticket_relations` 와 **같은 모양**이다.

    같은 모양으로 둔 것은 게으름이 아니라 판단이다: 「대체한다」와 「근거로 든다」는
    방향이 있고 「관련 있다」는 없다는 구조가 티켓과 똑같고, 다르게 만들면 화면 둘이
    같은 개념을 다른 방식으로 보여 준다.
    """

    __tablename__ = "document_relations"

    from_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    to_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(_in_list("kind", DREL_KINDS), name="ck_drel_kind"),
        CheckConstraint("from_document_id <> to_document_id", name="ck_drel_not_self"),
        CheckConstraint(
            "kind <> 'relates_to' OR from_document_id < to_document_id",
            name="ck_drel_symmetric_ordered",
        ),
        Index("uq_drel_edge", "from_document_id", "to_document_id", "kind", unique=True),
    )


class Tag(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """태그. **조직 안에서 이름이 하나다.**

    자유 문자열로 두면 「보안」·「보안 」·「Security」가 서로 다른 태그가 되고, 태그로
    거른 목록이 언제나 절반만 나온다. `slug` 는 정규화한 형태(소문자·공백 제거)이고
    유일 제약이 그 위에 걸린다 — `name` 은 사람이 처음 적은 표기를 그대로 둔다.
    """

    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_tag_name_nonempty"),
        Index("uq_tag_slug", "org_id", "slug", unique=True),
    )


class DocumentTag(Base):
    """문서 ↔ 태그. 복합 기본키라 같은 태그가 두 번 붙지 않는다."""

    __tablename__ = "document_tags"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        # 「이 태그가 붙은 문서」의 인덱스. 기본키는 `(document_id, tag_id)` 라
        # 반대 방향 조회를 못 탄다.
        Index("ix_dtag_by_tag", "tag_id", "document_id"),
    )


class DocumentMention(UUIDPrimaryKeyMixin, Base):
    """본문이 가리키는 것 — 사람 · 다른 문서 · 티켓.

    ## 왜 표로 두는가

    본문 JSON 안에 이미 있다. 그런데 답해야 하는 질문은 반대 방향이다: **「나를 언급한
    문서가 어디 있나」.** JSON 안을 매번 뒤지면 문서 수만큼 훑게 되고, 그 화면은
    문서가 늘수록 느려진다.

    `block_id` 를 함께 든다 — 인용이 「이 문서 어딘가」가 아니라 **「이 블록」** 을
    가리켜야 하기 때문이다(D-198). 그것이 Block JSON 을 정본으로 고른 이유 자체다.

    ## 현재 판의 것만 있다

    `app/knowledge/mentions.py` 가 판이 바뀔 때마다 다시 만든다. 판마다 쌓아 두면
    「나를 언급한 문서」에 3년 전 지워진 문장이 계속 나온다.
    """

    __tablename__ = "document_mentions"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 본문 안의 위치. 인용 앵커다.
    block_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # FK 를 안 건다 — 대상 표가 셋이라 한 컬럼으로 걸 수 없고, 지워진 대상을 가리키는
    # 멘션은 화면에서 「없는 대상」으로 보이는 것이 맞다(글은 그때 그렇게 쓰여 있었다).
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(_in_list("target_kind", MENTION_KINDS), name="ck_dmention_kind"),
        Index(
            "uq_dmention", "document_id", "block_id", "target_kind", "target_id",
            unique=True,
        ),
        # 역방향 — 「나를 언급한 문서」. 이 표가 존재하는 이유다.
        Index("ix_dmention_target", "target_kind", "target_id"),
    )
