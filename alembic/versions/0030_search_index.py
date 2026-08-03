"""통합 검색 — search_documents(일반 표) + search_index(FTS5 external content) (PLAN Phase 5)

Revision ID: 0030
Revises: 0026
Create Date: 2026-08-03

## 왜 표가 둘인가

FTS5 는 검색만 잘하는 표다. 정렬 키·권한 판정에 필요한 값(org, 담당자 집합, 라우트)을 그
안에 넣으면 인덱스가 뚱뚱해지고, 무엇보다 **권한을 검색 인덱스 안에서 판정하게 된다** —
그건 인덱스를 다시 만들 때마다 권한이 흔들린다는 뜻이다. 그래서 사실은 일반 표
(`search_documents`)에 두고, FTS5 는 `content=` 로 그 표를 가리키는 **external content**
인덱스로만 쓴다. 인덱스가 깨져도 `search_documents` 만 있으면 LIKE 로 답할 수 있다.

## 토크나이저는 trigram 이다 (unicode61 이 아니다)

실험으로 확정했다:
  * `unicode61` 은 한국어에 **못 쓴다**. 공백으로만 자르므로 `회의` 가 `회의록` 에 안 걸린다.
    한국어에서 어절 중간 일치는 예외가 아니라 기본이다.
  * `trigram` 은 3글자 창을 훑으므로 `"린트 회"` 가 `스프린트 회의록 정리` 에 걸린다.
    **단 3자 이상이 필요하다** — 1~2자 질의는 FTS 가 아무것도 못 돌려준다.
1~2자는 애플리케이션이 `LIKE` 로 답한다(app/search/query.py). 코퍼스가 작아서 충분하고,
"두 글자를 치면 조용히 0건" 이 되는 편이 훨씬 나쁘다.

## 인덱스 유지는 트리거로 한다

external content FTS5 는 원본 표가 바뀌어도 **자동으로 따라오지 않는다**. 애플리케이션
코드에서 두 번 쓰게 하면 언젠가 한쪽만 쓰는 경로가 생기고, 그때 검색은 조용히 옛 내용을
돌려준다(가장 알아채기 어려운 종류의 결함이다). SQLite 트리거로 묶어 두면 어떤 경로로
써도 인덱스가 같이 움직인다.

## 채팅은 인덱싱하지 않는다 (v1 범위: 티켓·문서·게시판·사용자)

방별 ACL 을 인덱스 안에 넣어야 하고, 1:1 DM 을 공용 인덱스에 넣는 것은 그 자체로 유출
경로다. 이 표에 채팅이 절대 들어오지 않는다는 것은
`tests/security/test_search_no_chat.py` 가 보안 테스트로 못박는다.

타임스탬프는 만들지 않는다 — 새 표 둘뿐이고 백필이 없어서 SQLite `STRFTIME('%f')` 함정
(CLAUDE.md §8)에 걸릴 값 자체가 없다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
# 리비전 번호는 예약 라벨일 뿐이고 `down_revision` 은 **머지 시점의 실제 head** 다
# (PLAN '알렘빅 다중 헤드 규칙'). 착수 시점 head 는 0026 이었으나 작업 중 다른 레인이
# 0029(chat_member_last_seen_nullable, down=0026)를 머지했다. 나중에 머지하는 레인이
# 리베이스한다는 규칙에 따라 0029 뒤에 붙인다 — 둘 다 0026 을 가리키면 head 가 둘이 되고
# `alembic upgrade head` 가 "Multiple head revisions are present" 로 거절해 배포가 죽는다.
down_revision = "0029"
branch_labels = None
depends_on = None


# FTS5 인덱스와 원본 표를 묶는 트리거 3개. 이름을 한곳에 모아 downgrade 가 빠뜨리지 못하게 한다.
_TRIGGERS = ("search_documents_ai", "search_documents_ad", "search_documents_au")


def upgrade() -> None:
    op.create_table(
        "search_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        # 'ticket' | 'document' | 'board' | 'user'. **'chat' 은 없다**(모듈 docstring).
        sa.Column("kind", sa.String(16), nullable=False),
        # 그 유형의 세계에서 이 항목을 가리키는 id. 티켓·문서는 Notion page id,
        # 게시판·사용자는 자체 UUID — 화면 딥링크가 이미 그 값을 키로 쓴다.
        sa.Column("ref_id", sa.String(64), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=True),
        # 이 항목을 '가진' 앱 사용자 id 들, 콤마로 감싸 이어 붙인다(",a,b,").
        # 부서 범위 판정이 이 집합으로만 이뤄진다(app/core/scope.py::any_assignee_visible) —
        # 스칼라 부서 하나로 정하면 두 부서가 함께 맡은 티켓이 한쪽에서 통째로 사라진다.
        sa.Column("owner_user_ids", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        # 결과 줄에 제목 밑에 붙는 한 줄(상태·부서·카테고리 등). 검색 대상은 아니다.
        sa.Column("subtitle", sa.String(300), nullable=True),
        # SPA 해시 라우트("/tickets/<id>"). 결과를 눌렀을 때 갈 곳을 인덱스가 들고 있어야
        # 화면이 유형별 if 문을 갖지 않는다.
        sa.Column("route", sa.String(300), nullable=False, server_default=""),
        # 원본(Notion 등) 바깥 링크. 없으면 NULL.
        sa.Column("url", sa.String(1000), nullable=True),
        # 동점일 때의 정렬 키(ISO 문자열). 최신 것이 위로 온다.
        sa.Column("sort_key", sa.String(40), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
    )
    # 같은 대상이 두 줄로 들어오면 검색 결과가 중복된다. DB 가 막는다.
    op.create_index(
        "ux_search_documents_kind_ref", "search_documents", ["kind", "ref_id"], unique=True
    )
    op.create_index("ix_search_documents_kind", "search_documents", ["kind"])
    op.create_index("ix_search_documents_org_id", "search_documents", ["org_id"])

    # external content FTS5. content_rowid 는 기본값('rowid')이라 적지 않는다.
    op.execute(
        "CREATE VIRTUAL TABLE search_index USING fts5("
        "  title, body,"
        "  content='search_documents',"
        "  tokenize='trigram'"
        ")"
    )

    op.execute(
        "CREATE TRIGGER search_documents_ai AFTER INSERT ON search_documents BEGIN"
        "  INSERT INTO search_index(rowid, title, body)"
        "  VALUES (new.rowid, new.title, new.body);"
        "END"
    )
    op.execute(
        "CREATE TRIGGER search_documents_ad AFTER DELETE ON search_documents BEGIN"
        "  INSERT INTO search_index(search_index, rowid, title, body)"
        "  VALUES ('delete', old.rowid, old.title, old.body);"
        "END"
    )
    op.execute(
        "CREATE TRIGGER search_documents_au AFTER UPDATE ON search_documents BEGIN"
        "  INSERT INTO search_index(search_index, rowid, title, body)"
        "  VALUES ('delete', old.rowid, old.title, old.body);"
        "  INSERT INTO search_index(rowid, title, body)"
        "  VALUES (new.rowid, new.title, new.body);"
        "END"
    )


def downgrade() -> None:
    for name in _TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS search_index")
    op.drop_index("ix_search_documents_org_id", table_name="search_documents")
    op.drop_index("ix_search_documents_kind", table_name="search_documents")
    op.drop_index("ux_search_documents_kind_ref", table_name="search_documents")
    op.drop_table("search_documents")
