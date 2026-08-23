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
