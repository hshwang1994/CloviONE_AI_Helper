"""검색 대조를 질의와 대상 **양쪽**에 — `search_fold()` 와 접힌 생성 열 셋 (D-495).

Revision ID: 0030_search_fold
Revises: 0029_sprint_team_owner
Create Date: 2026-09-21

앱 코드를 import 하지 않는다. 0002~0029 가 적어 둔 이유 그대로다 — 마이그레이션은 **그
시점 스키마의 얼어붙은 스냅숏**이라, 앱 상수를 참조하면 나중에 그 상수를 고치는 날 이
파일의 뜻이 소리 없이 함께 바뀐다. 접기 규칙도 여기에 글자로 얼려 둔다.

## 무엇이 문제였나

「현황 제외」라는 제목을 「현황제외」로 치면 아무것도 안 나왔다. 질의는 앞뒤 공백을 걷었지만
대상 쪽 공백을 걷는 곳이 없었고, 대소문자는 `ILIKE` 가 맞췄지만 전각 표기·NFD 한글·제로폭
공백은 어느 쪽도 맞추지 않았다. 규칙은 이제 `app/core/search_text.py::fold` 하나이고, 이
마이그레이션이 **대상 쪽 짝**을 DB 안에 세운다.

## 무엇을 하는가

1. `search_fold(text)` — IMMUTABLE · PARALLEL SAFE · `pg_catalog` 내장만 쓴다. STRICT 도 SET
   절도 안 붙인다. 둘 중 하나라도 붙으면 플래너가 이 함수를 질의 안에 펼치지(inline) 못하고
   행마다 함수 호출로 남는다. 내장만 쓰므로 `search_path` 가 비어 있는 복원(pg_restore)에서도
   생성 열을 다시 계산할 수 있다. PG 정규식의 `\\s` 는 로케일에 따라 답이 달라서 지울
   코드포인트를 글자로 적는다.
2. **자기 점검** — 알려진 입력 하나를 접어 기대값과 다르면 중단한다. 서버의 유니코드 표나
   `lower()` 가 파이썬 쪽과 다르면 그 차이는 오류가 아니라 「검색이 조금 덜 찾는다」로만
   드러나기 때문이다. 트랜잭션 하나라 중단하면 아무것도 남지 않는다.
3. 원문 위 트라이그램 인덱스 셋을 지운다. 질의가 접혀 오므로 받을 조건이 없다. 생성 열을
   더하면 표를 다시 쓰면서 인덱스를 전부 다시 짓는데, 곧 지울 인덱스까지 짓지 않도록 먼저
   지운다(`document_chunks` 의 원문 GIN 이 그중 가장 비싸다).
4. 파생 표 둘에 **STORED 생성 열** 셋과 그 위 GIN 트라이그램 인덱스 셋을 만든다
   (`search_documents.title_fold`·`body_fold`, `document_chunks.text_fold`).
   `ix_chunk_text_fts` 는 그대로 둔다 — FTS 레인은 어절 경계를 보므로 원문 위에 서야 한다.

작은 표(티켓·프로젝트·사용자 등)에는 열을 더하지 않는다. 질의 때 `search_fold(col)` 을
계산하고, 운영 규모에서 10~60ms 다. 파생 표 둘은 색인이 행마다 트라이그램을 들고 있어야
해서 저장해 둔다.

## CONCURRENTLY 가 없는 이유

`alembic/env.py` 가 마이그레이션 전체를 트랜잭션 하나로 감싸고, `CREATE INDEX CONCURRENTLY`
는 트랜잭션 안에서 못 돈다. 두 표는 파생 데이터라 크지 않고(색인 수천 행), 잠금은 이
트랜잭션이 끝날 때까지다.

## 서비스가 떠 있는 채 돈다

`install.sh` 9단계는 서비스를 멈추지 않고 이 파일을 돌린다. 옛 코드와 양립한다: 생성 열은
옛 INSERT 가 이름을 부르지 않으므로 보이지 않고, 옛 `ILIKE` 질의는 인덱스 없이 전량 스캔으로
같은 답을 낸다. 새 코드로 다시 뜨면 접힌 열과 새 인덱스를 쓴다.

## 되돌리기

새 인덱스 → 생성 열 → 옛 원문 인덱스 셋 복원(`0001`·`0008` 이 만든 모양 그대로) → 함수 순으로
지운다. 생성 열이 함수에 기대고 있어 함수를 먼저 지울 수 없다. 지우는 것은 전부 파생 값이라
잃는 데이터가 없다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_search_fold"
down_revision = "0029_sprint_team_owner"
branch_labels = None
depends_on = None

#: 접기 규칙 판 1. 정본은 `app/core/search_text.py` 이고, 두 곳이 같은 값을 내는지는
#: `tests/unit/test_search_fold.py` 가 공용 말뭉치로 잰다. **이 글자는 고치지 않는다** —
#: 규칙이 바뀌면 새 마이그레이션이 새 판을 만든다.
_FOLD_SQL = r"""
CREATE OR REPLACE FUNCTION search_fold(src text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fold$
  SELECT regexp_replace(replace(lower(replace(
    CASE WHEN src IS NFKC NORMALIZED THEN src ELSE normalize(src, NFKC) END, U&'\0130', 'i')),
    U&'\03C2', U&'\03C3'),
    '[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u00AD\u1680\u2028\u2029\u200B-\u200F\u2060\uFEFF]+', '', 'g')
$fold$
"""

_FOLD_COMMENT_SQL = (
    "COMMENT ON FUNCTION search_fold(text) IS "
    "'search_fold v1 - 검색 대조 규칙(D-495). app/core/search_text.py 의 fold 와 같은 값을 낸다.'"
)

#: 자기 점검 입력 — 앞뒤 공백 · 전각 라틴 · 대소문자 · 전각 공백(U+3000)을 한 줄에 담았다.
_PROBE = "  \uff23\uff4c\uff4f\uff56\uff49\uff52\uff2f\uff2e\uff25 현황\u3000제외 "
_EXPECTED = "clovirone현황제외"

#: 0030 이 지우는 원문 트라이그램 인덱스. 되돌리기가 `0001`·`0008` 의 모양 그대로 다시 만든다.
_RAW_TRGM_INDEXES = (
    ("ix_search_documents_title_trgm", "search_documents", "title"),
    ("ix_search_documents_body_trgm", "search_documents", "body"),
    ("ix_chunk_text_trgm", "document_chunks", "text"),
)

#: 0030 이 더하는 접힌 생성 열과 그 인덱스 — (표, 열, 원문 열, 인덱스).
_FOLDED_COLUMNS = (
    ("search_documents", "title_fold", "title", "ix_search_documents_title_fold_trgm"),
    ("search_documents", "body_fold", "body", "ix_search_documents_body_fold_trgm"),
    ("document_chunks", "text_fold", "text", "ix_chunk_text_fold_trgm"),
)


def _tables() -> tuple[str, ...]:
    """열을 더할 표. 같은 표의 열은 ALTER 한 번에 묶는다 — 표 재작성이 한 번으로 끝난다."""
    seen: list[str] = []
    for table, *_ in _FOLDED_COLUMNS:
        if table not in seen:
            seen.append(table)
    return tuple(seen)


def upgrade() -> None:
    op.execute(_FOLD_SQL)
    op.execute(_FOLD_COMMENT_SQL)

    conn = op.get_bind()
    folded = conn.execute(sa.text("SELECT search_fold(:probe)"), {"probe": _PROBE}).scalar()
    if folded != _EXPECTED:
        # 그대로 진행하면 저장된 사본과 파이썬이 접은 질의가 조용히 어긋난다.
        raise RuntimeError(
            "0030 중단 — 이 서버의 search_fold() 가 기대와 다른 값을 냅니다"
            f"(받은 값 {folded!r}, 기대 {_EXPECTED!r}). 서버 인코딩이 UTF8 인지, 유니코드 "
            "정규화를 지원하는 PostgreSQL 13 이상인지 확인하세요."
        )

    for name, _table, _column in _RAW_TRGM_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

    for table in _tables():
        clauses = ", ".join(
            f"ADD COLUMN {column} text GENERATED ALWAYS AS (search_fold({source})) STORED NOT NULL"
            for owner, column, source, _index in _FOLDED_COLUMNS
            if owner == table
        )
        op.execute(f"ALTER TABLE {table} {clauses}")

    for table, column, _source, index in _FOLDED_COLUMNS:
        op.execute(f"CREATE INDEX {index} ON {table} USING gin ({column} gin_trgm_ops)")


def downgrade() -> None:
    for _table, _column, _source, index in _FOLDED_COLUMNS:
        op.execute(f"DROP INDEX IF EXISTS {index}")

    for table in _tables():
        clauses = ", ".join(
            f"DROP COLUMN IF EXISTS {column}"
            for owner, column, _source, _index in _FOLDED_COLUMNS
            if owner == table
        )
        op.execute(f"ALTER TABLE {table} {clauses}")

    for name, table, column in _RAW_TRGM_INDEXES:
        op.execute(f"CREATE INDEX {name} ON {table} USING gin ({column} gin_trgm_ops)")

    op.execute("DROP FUNCTION IF EXISTS search_fold(text)")
