"""AI Index 표 둘 — `document_chunks` · `ai_index_state` (D-203).

## 🔴 이 표에 권한 컬럼이 없다. 그것이 설계다.

지금 검색은 **300초 재색인 간격 동안 권한 변경을 못 따라간다** — 권한 판정 결과가 인덱스에
구워져 있기 때문이다. 부서를 옮긴 사람이 5분 동안 옛 부서 문서를 계속 보거나, 방금 받은
권한이 5분 동안 안 붙는다.

그 문제를 「인덱스를 더 자주 다시 만들기」로 풀지 않는다. **권한을 인덱스에 안 넣는다.**
chunk 는 「이 문서의 이 자리에 이런 글이 있다」만 안다. 「누가 볼 수 있는가」는 질의 시각에
`effective_visibility_clause` 가 답한다(D-194 · D-202). 그래서 **Permission 변경은
재임베딩이 아니라 필터 재계산**이고, 재계산은 다음 질의에서 이미 끝나 있다.

`document_id` 가 NOT NULL 인 이유가 이것이다 — 첨부에서 나온 chunk 도 **부모 문서**를
가리킨다. 첨부의 가시성은 부모 문서가 지킨다(D-253). 파일만 가리키면 그 chunk 의 권한을
물을 자리가 없다.

## 파생 데이터다 — 백업 대상이 아니다

`document_chunks` 는 언제든 다시 만들 수 있다(D-203 · D-204). 그래서 백업에서 **일부러
뺀다**. 대신 재생성 경로를 항상 살려 둔다 — `ai_index_state` 를 `pending` 으로 되돌리면
색인 레인이 처음부터 다시 만든다.

## Vector 인덱스를 처음부터 만들지 않는다 (D-210)

384차원에서 exact 스캔이 1,169 벡터에 0.88ms · 49,098 벡터에 42ms 다. Cutover 시점 벡터는
수천 규모라 **인덱스가 필요 없다.** 미리 만들면 빌드 비용·디스크·재색인 복잡도만 지고
얻는 것이 없다. 임계는 **약 1.2만 벡터**이고 그때 HNSW(`m=32`·`ef_construction=200`)를
만든다. 지금 벡터가 몇 개인지는 `ai_cli status` 가 말한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.ai.catalog import FTS_CONFIG, VECTOR_DIM
from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

# ── 색인 대상의 종류 ─────────────────────────────────────────────────────────
#: 문서 본문에서 나온 chunk. 앵커는 블록 id 다(D-198).
SOURCE_DOCUMENT = "document"
#: 문서에 붙은 파일에서 나온 chunk. 앵커는 쪽·슬라이드·절·시트다.
SOURCE_FILE = "file"
SOURCE_KINDS = (SOURCE_DOCUMENT, SOURCE_FILE)

# ── 인용 앵커의 종류 ─────────────────────────────────────────────────────────
# 인용은 「이 문서 어딘가」가 아니라 **「이 자리」**를 가리켜야 한다. 형식마다 그 자리의
# 이름이 다르다 (MASTER_PLAN §5.4).
ANCHOR_BLOCK = "block"      # Document — 블록 id
ANCHOR_PAGE = "page"        # PDF — 쪽 번호
ANCHOR_SLIDE = "slide"      # PPTX — 슬라이드 번호
ANCHOR_SECTION = "section"  # DOCX — 절/문단
ANCHOR_SHEET = "sheet"      # XLSX — 시트 + 범위
ANCHOR_TEXT = "text"        # 평문·마크다운 — 문자 구간
ANCHOR_KINDS = (
    ANCHOR_BLOCK, ANCHOR_PAGE, ANCHOR_SLIDE, ANCHOR_SECTION, ANCHOR_SHEET, ANCHOR_TEXT,
)

# ── 색인 상태 ────────────────────────────────────────────────────────────────
STATE_PENDING = "pending"
#: 성공. `chunk_count` 가 0 이어도 성공이다 — 빈 문서는 결함이 아니다.
STATE_OK = "ok"
#: 실패. `last_error` 에 이유가 있고 `next_attempt_at` 뒤에 다시 본다.
STATE_FAILED = "failed"
STATES = (STATE_PENDING, STATE_OK, STATE_FAILED)

#: D-210 의 임계. 이 위로 가면 HNSW 를 만들 때다. 넘었다는 사실을 `ai_cli status` 가
#: 말한다 — 조용히 느려지는 것이 이 저장소가 가장 싫어하는 종류의 사고다.
VECTOR_INDEX_THRESHOLD = 12000


class Vector(UserDefinedType):
    """pgvector 의 `vector(n)`.

    `pgvector` 파이썬 패키지를 안 쓴다. 우리가 필요한 것은 **고정 차원 실수 배열 하나**
    이고, 그 텍스트 표현(`[1,2,3]`)은 20줄이면 끝난다. 폐쇄망 wheelhouse 에 넣어야 하는
    의존을 그 20줄 때문에 늘리지 않는다 — `JsonText` 와 같은 판단이다.

    텍스트 표현을 쓰는 것의 비용도 적어 둔다: 384차원 한 줄이 대략 5 KB 문자열이다.
    chunk 수천 건 규모에서는 문제가 아니고, 그 규모를 넘으면 D-210 대로 HNSW 를 만들
      때 같이 재본다.
    """

    cache_ok = True

    def __init__(self, dim: int = VECTOR_DIM) -> None:
        self.dim = int(dim)

    def get_col_spec(self, **kw) -> str:  # noqa: ARG002 - SQLAlchemy 계약
        return f"vector({self.dim})"

    def bind_processor(self, dialect):  # noqa: ARG002
        dim = self.dim

        def process(value):
            if value is None:
                return None
            values = [float(v) for v in value]
            if len(values) != dim:
                # 차원이 다른 벡터를 저장하면 PG 가 거절한다. 그 거절은 「어느 행이」를
                # 안 알려 주므로 여기서 먼저 말한다.
                raise ValueError(f"벡터 차원이 {dim} 이어야 합니다(받은 값 {len(values)}).")
            return "[" + ",".join(repr(v) for v in values) + "]"

        return process

    def result_processor(self, dialect, coltype):  # noqa: ARG002
        def process(value):
            if value is None:
                return None
            if isinstance(value, (list, tuple)):
                return tuple(float(v) for v in value)
            body = str(value).strip().lstrip("[").rstrip("]")
            if not body:
                return ()
            return tuple(float(part) for part in body.split(","))

        return process


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    """색인된 글 조각 하나. **파생 데이터다.**

    `updated_at` 이 없다. chunk 는 고쳐지지 않는다 — 문서가 바뀌면 그 문서의 chunk 를
    통째로 지우고 다시 만든다. 부분 갱신은 「무엇이 바뀌었는가」를 chunk 단위로 알아야
    하고, 한 번 어긋나면 그 조각만 영원히 옛 내용으로 남는다(`app/search/indexer.py` 가
    같은 이유로 전체 재구축을 골랐다).
    """

    __tablename__ = "document_chunks"

    source_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    #: 🔴 **권한을 묻는 자리.** 첨부에서 나온 chunk 도 부모 문서를 가리킨다(D-253).
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `source_kind='file'` 일 때만 있다.
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=True, index=True
    )
    #: 어느 판의 본문에서 나왔는가. 판이 바뀌면 낡는다.
    version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    #: 한 대상 안에서의 순서. 인용 문맥을 앞뒤로 넓힐 때 쓴다.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    anchor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 기계가 쓰는 앵커. 블록 id · `"12"` · `"Sheet1!A1:D20"`.
    anchor_ref: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    #: 사람이 읽는 앵커. 「3쪽」·「2번 슬라이드」. 화면이 이것을 그대로 쓴다.
    anchor_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    text_body: Mapped[str] = mapped_column("text", Text, nullable=False)
    #: 같은 글이면 다시 임베딩하지 않는다. 판이 올라도 안 바뀐 chunk 가 대부분이다.
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_estimate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    #: 임베딩이 아직 없으면 NULL 이다. **그 상태가 정상**이다 — 모델이 없는 설치에서도
    #: 파싱과 chunk 는 돌고, 모델이 생기면 그때 채운다(D-201 의 경계).
    embedding: Mapped[tuple | None] = mapped_column(Vector(VECTOR_DIM), nullable=True)

    parser_version: Mapped[str] = mapped_column(String(16), nullable=False)
    embedding_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", server_default=""
    )
    embedding_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default=""
    )

    indexed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("source_kind", SOURCE_KINDS), name="ck_chunk_source_kind"),
        CheckConstraint(_in_list("anchor_kind", ANCHOR_KINDS), name="ck_chunk_anchor_kind"),
        CheckConstraint("length(btrim(text)) > 0", name="ck_chunk_text_nonempty"),
        CheckConstraint("ordinal >= 0", name="ck_chunk_ordinal_nonneg"),
        CheckConstraint("length(text_sha256) = 64", name="ck_chunk_sha_len"),
        # 파일 chunk 에는 파일이 있고, 문서 chunk 에는 없다. 이 짝이 어긋나면 인용이
        # 어디를 가리키는지 알 수 없다.
        CheckConstraint(
            "(source_kind = 'file') = (file_id IS NOT NULL)", name="ck_chunk_file_pair"
        ),
        # 벡터가 있으면 **무엇으로 만들었는지도 있다.** 없으면 그 벡터는 비교할 수
        # 없는 값이다 — 모델을 바꾼 날 어느 벡터가 옛것인지 가릴 수가 없다.
        CheckConstraint(
            "embedding IS NULL OR ("
            "embedded_at IS NOT NULL AND length(btrim(embedding_model)) > 0 "
            "AND length(btrim(embedding_version)) > 0)",
            name="ck_chunk_embedding_provenance",
        ),
        CheckConstraint(
            "(embedding IS NULL) = (embedded_at IS NULL)", name="ck_chunk_embedded_pair"
        ),
        # 한 대상 안에서 순서는 유일하다. `file_id` 가 NULL 인 문서 chunk 와 파일 chunk 를
        # 한 인덱스로 묶으려면 NULL 을 값으로 접어야 한다 — PG 는 NULL 을 서로 다른
        # 값으로 보기 때문에 그냥 두면 중복이 들어온다.
        Index(
            "uq_chunk_unit_ordinal",
            "document_id", text("coalesce(file_id, '')"), "ordinal", unique=True,
        ),
        # 「이 문서의 chunk 를 순서대로」 — 인용 문맥을 넓힐 때의 그 질의다.
        Index("ix_chunk_document_ordinal", "document_id", "ordinal"),
        # 「임베딩이 아직 없는 chunk」 — 모델이 나중에 생긴 설치가 이것으로 따라잡는다.
        Index(
            "ix_chunk_pending_embedding", "document_id",
            postgresql_where=text("embedding IS NULL"),
        ),
        # ── 키워드 두 레인 (S10 · D-209) ──────────────────────────────────────
        #
        # **후보 생성의 정본은 트라이그램이다.** 한국어는 조사·접미가 어절에 붙어서
        # 어절 내부 부분일치가 예외가 아니라 기본이고, PG 의 전문검색은 그것을 못 한다
        # (S1 실측 recall 0.083 대 1.000).
        #
        # FTS 를 함께 거는 것은 recall 때문이 아니라 **어절 정확일치를 판별하기**
        # 위해서다 — 융합 가중치가 그 사실을 그대로 적는다(`app/ai/retrieval/fusion.py`).
        #
        # S9 가 이 둘을 안 만든 이유도 적어 둔다: 그때는 아무도 이 컬럼으로 검색하지
        # 않았고, 안 쓰는 인덱스는 chunk 를 넣을 때마다 쓰기만 늘린다.
        Index(
            "ix_chunk_text_trgm", "text",
            postgresql_using="gin", postgresql_ops={"text": "gin_trgm_ops"},
        ),
        Index(
            "ix_chunk_text_fts",
            text(f"to_tsvector('{FTS_CONFIG}', text)"),
            postgresql_using="gin",
        ),
    )


class AiIndexState(UUIDPrimaryKeyMixin, Base):
    """문서 하나의 색인 상태. **작업 목록이자 결과 기록이다.**

    큐 표를 따로 두지 않는다. 「할 일」은 `status='pending'` 인 행이고, 「끝난 일」은
    같은 행이 `ok` 가 된 것이다. 표를 둘로 나누면 큐에서 사라졌는데 결과가 없는 상태를
    만들 수 있고, 그 상태는 아무 화면에도 안 나온다.

    ## 신호와 훑기를 **둘 다** 쓴다

    문서를 저장할 때 이 행을 `pending` 으로 만든다(신호). 그리고 색인 레인이 주기적으로
    「판이 바뀌었는데 상태가 ok 인 행」을 훑는다(backstop). 신호 하나만 믿으면 신호를
    빠뜨린 문서가 **영원히** 옛 내용으로 남고, 그것이 가장 알아채기 어려운 결함이다.
    """

    __tablename__ = "ai_index_state"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    #: 이 판까지 색인했다. 문서의 `current_version_id` 와 다르면 낡았다.
    indexed_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: 어떤 파서·모델로 만들었는가. 판이 올라가면 같은 본문도 다시 만든다.
    parser_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default=""
    )
    embedding_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", server_default=""
    )
    embedding_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default=""
    )
    #: 첨부 집합의 지문. 파일이 붙거나 떨어지면 바뀐다 — 본문이 그대로여도 낡는다.
    attachment_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: 벡터까지 붙은 chunk 수. `chunk_count` 보다 작으면 모델이 없거나 실패한 것이다.
    embedded_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATE_PENDING, server_default=STATE_PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: 실패 이유 한 줄. **경로와 토큰이 안 섞인 문장만** 넣는다(OPS-05).
    last_error: Mapped[str] = mapped_column(
        String(300), nullable=False, default="", server_default=""
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: 실패한 문서를 곧바로 다시 잡지 않는다. 안 그러면 못 읽는 파일 하나가 레인을
    #: 통째로 돌린다.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("status", STATES), name="ck_index_state_status"),
        CheckConstraint("chunk_count >= 0", name="ck_index_state_chunks_nonneg"),
        CheckConstraint(
            "embedded_count >= 0 AND embedded_count <= chunk_count",
            name="ck_index_state_embedded_range",
        ),
        Index("uq_index_state_document", "document_id", unique=True),
        # 「지금 할 일」 — 색인 레인이 매 tick 에 던지는 그 질의다.
        Index("ix_index_state_queue", "status", "next_attempt_at", "queued_at"),
    )
