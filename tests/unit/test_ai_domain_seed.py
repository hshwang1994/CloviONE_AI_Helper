"""마이그레이션에 얼려 둔 AI 값이 **코드의 표와 같은가** (S9 · 0006 과 같은 관용).

마이그레이션은 앱 코드를 import 하지 않는다 — 그 시점 스키마의 얼어붙은 스냅숏이어야
하기 때문이다. 그래서 어휘가 두 곳에 적히고, **두 곳에 적힌 값이 어긋나면 조용히 깨진다**:

  * 앵커 종류를 하나 늘리고 CHECK 를 안 고치면 → 그 형식의 chunk 가 DB 에서 거절된다.
    증상은 「그 문서만 색인이 실패한다」이고 오류 문구는 제약 이름뿐이다.
  * 벡터 차원을 바꾸고 컬럼을 안 고치면 → 임베딩이 전부 거절된다. 그런데 chunk 는
    그대로 쌓이므로 **검색이 조용히 키워드 전용이 된다.**

그리고 이 파일은 D-203 의 구조적 성질도 함께 지킨다: **chunk 표에 권한 컬럼이 없다.**
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.ai import catalog
from app.ai.models import ANCHOR_KINDS, SOURCE_KINDS, STATES

pytestmark = pytest.mark.unit

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0007_ai_index.py"
)


def _frozen(name: str) -> tuple[str, ...]:
    """마이그레이션이 얼려 둔 상수 튜플을 **글자로** 읽는다.

    import 하면 안 된다 — import 가 되는 순간 두 곳이 한 곳이 되고, 이 시험이
    아무것도 확인하지 않게 된다(그래도 초록이라 아무도 눈치채지 못한다).
    """
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\s*=\s*\(([^)]*)\)", source, re.M)
    assert match, f"마이그레이션에서 {name} 을 못 찾았다"
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def _frozen_int(name: str) -> int:
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\s*=\s*(\d+)", source, re.M)
    assert match, f"마이그레이션에서 {name} 을 못 찾았다"
    return int(match.group(1))


def test_the_frozen_reader_is_not_vacuous():
    """이 파일의 다른 시험들이 **빈 튜플끼리 비교하며** 통과하지 않는지 먼저 본다."""
    assert len(_frozen("_ANCHOR_KINDS")) == 6


@pytest.mark.parametrize(
    "frozen_name,code_values",
    [
        ("_SOURCE_KINDS", SOURCE_KINDS),
        ("_ANCHOR_KINDS", ANCHOR_KINDS),
        ("_STATES", STATES),
    ],
)
def test_every_frozen_vocabulary_matches_the_code(frozen_name, code_values):
    assert _frozen(frozen_name) == tuple(code_values), (
        f"{frozen_name} 이 코드와 다르다 — 새 값이 DB 에서 조용히 거절된다"
    )


def test_the_frozen_vector_dimension_matches_the_catalog():
    """차원이 갈리면 임베딩이 전부 거절되고 검색이 조용히 키워드 전용이 된다."""
    assert _frozen_int("_VECTOR_DIM") == catalog.VECTOR_DIM == catalog.E5_SMALL.dim


def test_both_ai_tables_stand(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"document_chunks", "ai_index_state"} <= names


def test_the_vector_extension_is_installed(db):
    """`0007` 이 만든다. 없으면 그 자리에서 죽는 것이 맞다 — 「타입이 없다」보다
    「확장이 없다」가 운영자에게 훨씬 가까운 사실이다."""
    installed = db.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()
    assert installed == "vector"


def test_the_embedding_column_has_the_declared_dimension(db):
    kind = db.execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = 'document_chunks'::regclass AND a.attname = 'embedding'"
        )
    ).scalar_one()
    assert kind == f"vector({catalog.VECTOR_DIM})"


# ── 🔴 D-203 의 구조적 성질 ─────────────────────────────────────────────────


def test_the_chunk_table_has_no_permission_column(db):
    """**이것이 설계다.** 권한을 인덱스에 구우면 Permission 변경이 재색인이 되고,
    재색인 간격 동안 부서를 옮긴 사람이 옛 부서 문서를 계속 본다. chunk 는 「이 문서의
    이 자리에 이런 글이 있다」만 알고, 「누가 볼 수 있는가」는 질의 시각에 답한다.
    """
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("document_chunks")}
    forbidden = {
        "visibility", "confidential", "org_id", "owner_kind", "owner_dept_id",
        "owner_project_id", "space_id", "user_id", "role", "permission",
    }
    assert not (columns & forbidden), (
        "chunk 에 권한이 구워지면 Permission 변경이 재임베딩이 된다 (D-203)"
    )


def test_the_chunk_table_points_at_the_document_that_owns_the_permission(db):
    """첨부에서 나온 chunk 도 **부모 문서**를 가리킨다(D-253). 파일만 가리키면
    그 chunk 의 권한을 물을 자리가 없다."""
    columns = {c["name"]: c for c in inspect(db.get_bind()).get_columns("document_chunks")}
    assert columns["document_id"]["nullable"] is False
    assert columns["file_id"]["nullable"] is True


def test_there_is_no_vector_index_yet(db):
    """D-210: 384차원 exact 스캔이 수천 벡터에서 1~9ms 다. 미리 만들면 빌드 비용·
    디스크·재색인 복잡도만 지고 얻는 것이 없다. 임계는 약 1.2만 벡터다."""
    kinds = db.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'document_chunks'"
        )
    ).scalars().all()
    assert not any("hnsw" in d.lower() or "ivfflat" in d.lower() for d in kinds)


# ── S10 — 키워드 두 레인의 인덱스 ────────────────────────────────────────────
#
# `0008` 이 만든 것이 실제로 서 있는가, 그리고 **인덱스 식과 질의 식이 같은가**.
# 둘이 다르면 아무 오류도 안 나고 인덱스만 안 탄다 — 코퍼스가 자란 뒤에야 느려진다.

RETRIEVAL_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "0008_ai_retrieval_indexes.py"
)


def test_the_frozen_fts_config_matches_the_catalog():
    source = RETRIEVAL_MIGRATION.read_text(encoding="utf-8")
    match = re.search(r'^_FTS_CONFIG\s*=\s*"([^"]+)"', source, re.M)
    assert match, "마이그레이션에서 _FTS_CONFIG 를 못 찾았다"
    assert match.group(1) == catalog.FTS_CONFIG


def test_both_keyword_lanes_have_an_index(db):
    defs = {
        name: definition
        for name, definition in db.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'document_chunks'"
            )
        ).all()
    }
    assert "gin_trgm_ops" in defs["ix_chunk_text_trgm"]
    assert "to_tsvector" in defs["ix_chunk_text_fts"]
    assert f"'{catalog.FTS_CONFIG}'" in defs["ix_chunk_text_fts"]


class _Explain(Executable, ClauseElement):
    """`EXPLAIN <select>` — **바인드 파라미터를 그대로 둔 채** 계획을 묻는다.

    SQL 을 문자열로 렌더링해서 묻지 않는다. `literal_binds` 는 `%` 와 escape 문자를
    이스케이프하므로 `ILIKE '%…%' ESCAPE '\'` 가 **문법 오류**가 된다 — 그러면 검사가
    제품이 아니라 렌더링을 시험하게 된다(실제로 한 번 그렇게 빨개졌다).
    """

    inherit_cache = False

    def __init__(self, statement):
        self.statement = statement


@compiles(_Explain, "postgresql")
def _compile_explain(element, compiler, **kw):  # pragma: no cover - 컴파일러 훅
    return "EXPLAIN " + compiler.process(element.statement, **kw)


def _plan_for(db, statement) -> str:
    """이 질의의 계획. `enable_seqscan=off` 로 강제한다.

    현 코퍼스가 작아서 플래너가 seq scan 을 고르는 것은 **맞는 판단**이다(D-209).
    우리가 확인하려는 것은 「지금 쓰는가」가 아니라 **「쓸 수 있는가」**다 — 인덱스 식과
    질의 식이 어긋나면 강제해도 못 쓴다.
    """
    db.execute(text("SET LOCAL enable_seqscan = off"))
    return "\n".join(db.execute(_Explain(statement)).scalars().all())


def test_the_query_expression_is_the_indexed_expression(db):
    """🔴 **글자가 아니라 플래너에게 물어본다.** 「같아 보인다」는 증거가 아니다."""
    from app.ai.retrieval import query as query_mod

    assert "ix_chunk_text_fts" in _plan_for(db, query_mod.fts_lane("연차 규정", limit=5))


def test_the_trigram_lane_can_use_its_index_too(db):
    """`ILIKE '%…%'` 를 `gin_trgm_ops` 가 받는다 (D-209 · S2 원장)."""
    from app.ai.retrieval import query as query_mod

    assert "ix_chunk_text_trgm" in _plan_for(db, query_mod.trgm_lane("연차 규정", limit=5))
