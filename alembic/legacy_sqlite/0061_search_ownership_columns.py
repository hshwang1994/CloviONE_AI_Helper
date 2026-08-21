"""검색 인덱스에 Ownership 을 싣는다 — 상한 **앞에서** 원본과 같은 규칙으로 거른다 (0060 §25)

## 왜 인덱스가 Ownership 을 들고 있어야 하는가

검색은 `search_documents` 라는 **평평한 사본** 하나만 본다(0030). 사본이라 원본의 ACL 을
조인할 수 없고, 그래서 지금까지는 `owner_user_ids`(담당자 집합)로 범위를 판정했다. 0060 이
티켓 권한을 담당자 축에서 **프로젝트 축**으로 옮기고 문서를 **Portal 소유 Ownership** 으로
옮기면서, 그 판정은 원본과 다른 답을 내는 상태가 됐다:

  * 담당자가 없는(또는 매핑이 안 된) 티켓 → 목록에서는 프로젝트 ACL 로 보이는데 검색에서만
    사라진다.
  * 작성자가 부서를 옮긴 문서 → 목록에서는 그대로인데 검색 결과만 사람을 따라 움직인다.

"검색은 목록과 같은 것을 찾아 준다" 가 깨지면 사용자는 무엇이 맞는지 알 수 없고, 반대
방향으로 틀리면 그건 유출이다. 그래서 색인 시점에 **원본의 Ownership 을 그대로 복사**하고,
검색은 `app/core/ownership.py::stored_ownership_clause` 하나로 판정한다 — 문서 목록이 쓰는
바로 그 함수다.

## 왜 백필하지 않는가

`search_documents` 는 원본에서 언제든 다시 만들 수 있는 파생 표다(`app/search/indexer.py`).
여기서 SQL 로 Ownership 을 흉내 내 채우면 그 계산이 indexer 와 두 벌이 되고, 두 벌은 반드시
갈라진다. 새 컬럼은 `unset` 으로 두고 — `unset` 은 전역 관리자만 통과하는 **fail-closed** 다 —
다음 색인 회차가 실제 값으로 채운다. 배포 직후 한 회차 동안 일반 사용자 검색이 조용히 넓어
지는 것보다 조용히 좁아지는 쪽이 안전하다.

## ALTER 로 붙인다 (batch 아님)

`search_index` 는 이 표를 `content=` 로 가리키는 external content FTS5 이고 트리거 셋이
둘을 묶는다. batch_alter_table 은 표를 다시 만들면서 **그 트리거를 떨어뜨린다** — 그러면
색인이 조용히 멈추고 검색은 LIKE 폴백으로만 동작한다. 세 컬럼 다 nullable 이거나 기본값이
있어서 SQLite 의 `ADD COLUMN` 제약에 걸리지 않는다. FK 는 같은 이유로 걸지 않는다(SQLite 는
`ADD COLUMN` 으로 FK 를 못 붙이고, 파생 표라 참조 무결성을 DB 에 맡길 이유도 없다 —
가리키는 프로젝트가 사라지면 그 행은 다음 색인에서 없어진다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_documents",
        sa.Column(
            "owner_kind", sa.String(length=16), nullable=False, server_default="unset"
        ),
    )
    op.add_column(
        "search_documents", sa.Column("owner_dept_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "search_documents",
        sa.Column("owner_project_id", sa.String(length=36), nullable=True),
    )
    # 판정은 (kind, dept) 와 (kind, project) 두 모양으로만 들어온다.
    op.create_index(
        "ix_search_documents_owner_dept", "search_documents",
        ["owner_kind", "owner_dept_id"],
    )
    op.create_index(
        "ix_search_documents_owner_project", "search_documents",
        ["owner_kind", "owner_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_search_documents_owner_project", table_name="search_documents")
    op.drop_index("ix_search_documents_owner_dept", table_name="search_documents")
    # 되돌릴 때도 batch 를 쓰지 않는다 — 트리거를 지키는 것이 위와 같은 이유다.
    # (SQLite 3.35+ 는 DROP COLUMN 을 지원하고, 이 프로젝트의 최소 버전이 그 위다.)
    op.drop_column("search_documents", "owner_project_id")
    op.drop_column("search_documents", "owner_dept_id")
    op.drop_column("search_documents", "owner_kind")
