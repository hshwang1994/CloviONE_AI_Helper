"""document_comments (문서 댓글, 사용자 지적 #9)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 stdout 에 찍고, Windows
콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다(0044, 0045 와 같은 이유).

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-06

## 번호가 0046 이 아닌 이유

지시서는 0046 을 지정했지만, 이 작업을 쓰는 사이에 다른 작업이
`0046_document_body_edit.py` 를 먼저 올렸다. 같은 번호로 두 파일을 두면 alembic 의 head 가
둘이 되어 `upgrade head` 가 아예 실패한다. 그래서 0046 뒤에 잇는다.

## 표의 모양은 `ticket_comments`(0028) 를 그대로 옮겼다

`author_user_id` / `body` / `deleted_at`(툼스톤 soft-delete) / `created_at` / `updated_at`.
같은 규약이어야 화면 두 곳에서 '삭제' 가 같은 뜻이다.

## ⚠️ 부모를 가리키는 방법만 다르다 - CASCADE 를 **일부러** 안 걸었다

0028 은 `ticket_comments.ticket_uid` 를 `ticket_cache.id` 에 `ON DELETE CASCADE` 로 걸었다.
이유는 타당했다: 소스에서 사라진 티켓을 `sync._prune` 이 지울 때 자식이 남아 있으면 그
DELETE 가 실패하고(SQLite 는 PRAGMA foreign_keys=ON), sync 는 예외를 통째로 삼키므로
**티켓 미러 전체가 조용히 멈춘다.**

그런데 그 CASCADE 가 사용자 데이터를 지웠다. 티켓이 소스 응답에서 **한 회차** 빠지는 것만으로
(페이지네이션 흔들림, 필터, 일시 권한 문제 - 전부 HTTP 200 이다) prune 이 캐시 행을 지우고
댓글, 첨부가 함께 사라졌다. 재현 기록은 `tests/regression/test_comment_survives_resync.py`,
고친 방법은 0043 의 소프트 프룬(`ticket_cache.notion_missing_at`: 지우는 대신 표시하고,
유예를 넘겨야 진짜로 지운다)이다.

**문서 동기화도 같은 prune 을 한다**(`app/team_docs/sync.py::_prune`). 그리고 문서 쪽에는
0043 같은 표시 컬럼이 **없다** - 지금도 진짜로 지운다. 그러니 여기에 CASCADE 를 걸면 이미
한 번 값을 치르고 배운 함정을 그대로 다시 파는 것이 된다.

세 가지 선택지를 놓고 골랐다:

  1. CASCADE 그대로 + 문서에도 소프트 프룬 도입.
     문서 소프트 프룬은 **그 자체로 옳고 언젠가 해야 한다** (`sync._prune` 이 이미
     `classification_manual` 수동 분류가 prune 한 번에 영구 소실된다고 적어 놨다).
     하지만 그건 목록 질의, 상세, 유예 만료 정리까지 함께 바꾸는 별개 작업이고,
     **댓글을 그 작업의 인질로 잡는다** - 그 전까지는 댓글이 한 회차 깜빡임에 사라진다.
  2. RESTRICT. 캐시 행 DELETE 가 실패하고 sync 가 예외를 삼켜 문서 미러가 조용히 멈춘다.
     0028 이 걱정한 그 상태 그대로다. 안 된다.
  3. **조회 키는 `notion_page_id`, FK 는 `document_id` + ON DELETE SET NULL.** (고른 것)

3번은 이 모듈이 이미 쓰는 관용이다. `document_favorites` / `document_recent_views`(0025)가
정확히 그 모양으로, 유일성과 조회는 `notion_page_id` 가 담당하고 `document_id` 는 미러 행이
있을 때 채워지는 보조 참조다. 그래서 이 표는:

  * 캐시 행이 prune 으로 사라져도 댓글이 **남는다**(문서가 안 보이는 동안에는 댓글 조회도
    404 다 - 조회가 `get_doc_in_scope` 를 지나므로 범위 판정과 같은 답이 나간다);
  * SET NULL 이라 그 DELETE 가 **실패하지 않는다** - 동기화가 멈추지 않는다;
  * 문서가 돌아오면 `_upsert` 가 새 UUID 로 캐시 행을 만드는데, 댓글은 page id 로 붙어 있어
    **그대로 다시 보인다**. 티켓에서 '결정적 UUID' 로도 못 고쳤던 상황이 여기서는 애초에
    생기지 않는다.

티켓이 page id 를 못 쓴 이유(자체 생성 티켓은 page id 가 아예 없다)는 문서에 없다.
`document_cache.notion_page_id` 는 NOT NULL + UNIQUE 이고 문서 API 는 처음부터 page id 로만
말한다. 소스가 자체 DB 로 바뀌는 날 이어 붙일 다리가 `document_id` 다.

고정 테스트: tests/regression/test_document_comment_survives_resync.py.

시드 없음 - 새 표 하나뿐이라 타임스탬프 함정(SQLite STRFTIME '%f' 금지)에 걸릴 일이 없다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_TABLE = "document_comments"
_INDEXES = (
    ("ix_document_comments_notion_page_id", ["notion_page_id"]),
    ("ix_document_comments_document_id", ["document_id"]),
    ("ix_document_comments_author_user_id", ["author_user_id"]),
    ("ix_document_comments_deleted_at", ["deleted_at"]),
)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE in set(insp.get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(36), primary_key=True),
        # 조회 키. FK 가 **아니다** (윗 docstring). 미러 행이 한 회차 사라져도 댓글은 남는다.
        sa.Column("notion_page_id", sa.String(64), nullable=False),
        # 소스 전환을 위한 다리. 미러 행이 없거나 prune 으로 사라지면 NULL 이 정상 상태다.
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("document_cache.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # soft-delete. 목록 API 는 삭제된 댓글도 본문 없는 툼스톤으로 계속 돌려준다 -
        # 이미 목록을 받아 둔 클라이언트가 '사라짐'이 아니라 '삭제됨'을 볼 수 있어야 한다.
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for name, cols in _INDEXES:
        op.create_index(name, _TABLE, cols)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    existing = {i["name"] for i in insp.get_indexes(_TABLE)}
    for name, _cols in _INDEXES:
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
