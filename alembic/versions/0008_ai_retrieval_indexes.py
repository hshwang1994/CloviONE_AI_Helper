"""AI Retrieval — `document_chunks` 의 키워드 인덱스 둘 (S10).

Revision ID: 0008_ai_retrieval
Revises: 0007_ai_index
Create Date: 2026-08-23

앱 코드를 import 하지 않는다. 0002~0007 이 적어 둔 이유 그대로다 — 마이그레이션은
**그 시점 스키마의 얼어붙은 스냅숏**이라 앱 상수를 참조하면 나중에 그 상수를 고치는 날
이 파일의 뜻이 소리 없이 함께 바뀐다.

## S9 는 왜 이 인덱스를 안 만들었나

**그때는 아무도 그 컬럼으로 검색하지 않았다.** 안 쓰는 인덱스를 미리 만들면 chunk 를
넣을 때마다 쓰기만 는다 — 색인 레인이 문서 하나에 chunk 수십 개를 한 번에 넣는
자리라 그 비용이 그대로 색인 시간이 된다. 그 컬럼을 처음 읽는 것이 S10 이므로 여기서
만든다.

## 왜 둘 다 만드는가 (D-209)

한국어에서 **후보 생성(recall)은 `gin_trgm_ops` 하나가 책임진다.** S1 이 실 PG16 에서
쟀다: 어절 내부 부분일치 질의 20건 중 전문검색(`to_tsvector('simple')`)은 **19건이
아무것도 못 찾았고**(recall 0.083) `pg_trgm` GIN 은 **recall 1.000** 이었다.

그런데도 FTS 를 함께 거는 이유는 그것이 **다른 일**을 하기 때문이다. FTS 는 어절
정확일치를 판별한다 — `회의` 를 친 사람에게 `회의록` 과 `회의` 를 같은 점수로 주지
않는다. RRF 는 그 두 순위를 융합하고, FTS 의 몫은 recall 이 아니라 **정밀도**다.
가중치가 그 사실을 그대로 적는다(`app/ai/retrieval/fusion.py`).

## Vector 인덱스는 여기서도 안 만든다 (D-210)

384차원 exact 스캔이 1,169 벡터에 0.88ms · 49,098 벡터에 42ms 다. 임계는 약 1.2만
벡터이고 넘었는지는 `ai_cli status` 의 `vector_index_recommended` 가 말한다. 넘으면
HNSW(`m=32`·`ef_construction=200`)를 **별도 마이그레이션**으로 만든다.
"""
from __future__ import annotations

from alembic import op


revision = '0008_ai_retrieval'
down_revision = '0007_ai_index'
branch_labels = None
depends_on = None

# 어휘를 여기 얼려 둔다. 정본은 `app/ai/catalog.py::FTS_CONFIG` 이고
# `tests/unit/test_ai_domain_seed.py` 가 둘을 맞물려 둔다. `simple` 인 이유는 한국어
# stemmer 가 PG 에 없기 때문이고, 다른 설정을 쓰면 색인과 질의가 서로 다른 토큰을 만든다.
_FTS_CONFIG = "simple"


def upgrade() -> None:
    # 후보 생성의 정본. `text ILIKE '%…%'` 를 이 인덱스가 받는다.
    #
    # ⚠️ **플래너가 항상 이것을 고르지는 않는다.** PG 는 `ILIKE '%…%'` 의 선택도를
    # 추정하지 못해 «거의 다 걸린다»로 본다 — 작은 표에서는 seq scan 이 더 싸고 그것은
    # 틀린 판단이 아니다(D-209 실측: 현 규모에서 seq scan 3ms). 코퍼스가 자란 뒤
    # 검색이 느려지면 인덱스를 의심하지 말고 통계·비용 파라미터를 본다.
    op.execute(
        "CREATE INDEX ix_chunk_text_trgm ON document_chunks "
        "USING gin (text gin_trgm_ops)"
    )
    # 어절 정확일치. `to_tsvector(regconfig, text)` 는 **설정을 명시했을 때만** IMMUTABLE
    # 이라 인덱스에 쓸 수 있다 — 한 인자짜리는 `default_text_search_config` 를 읽어
    # STABLE 이고, 그것으로 인덱스를 만들려 하면 여기서 죽는다.
    op.execute(
        f"CREATE INDEX ix_chunk_text_fts ON document_chunks "
        f"USING gin (to_tsvector('{_FTS_CONFIG}', text))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_text_fts")
    op.execute("DROP INDEX IF EXISTS ix_chunk_text_trgm")
