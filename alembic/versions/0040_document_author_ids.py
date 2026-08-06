"""문서 작성자를 **이름이 아니라 id 로** 판정한다 (X2).

`ensure_can_delete_doc` 이 `display_name` 문자열을 비교했다:

    name in authors or name == doc.owner

`users.display_name` 에는 **유일 제약이 없다**(바로 위 `email` 에는 있다 — `users/models.py`).
그래서 두 가지가 동시에 일어난다:

  * **개명하면 자기 문서를 못 지운다** — 이름이 안 맞으니 403.
  * **동명이인은 남의 문서를 지운다** — 이름이 맞으니 통과.

같은 저장소의 `app/core/people.py` 가 "display_name 에 유일 제약이 없다" 고 **이미 경고**해
놓았는데 이 판정만 그 이름을 신뢰하고 있었다.

## 왜 컬럼을 새로 두는가

Notion 응답의 person 객체에는 `id` 가 들어 있는데 파서가 **이름만 남기고 버리고 있었다**
(`notion_docs._person_names`). 그 id 를 같이 저장하면 매핑(`user_notion_mappings`)을 통해
앱 사용자로 해석할 수 있다 — 이름을 거치지 않는다.

## 백필하지 않는다

기존 행의 작성자 id 는 **Notion 을 다시 읽어야만** 알 수 있다(이름에서 역산하면 지금 고치려는
그 동명이인 문제를 그대로 되풀이한다). 다음 동기화가 채운다. 그 사이에는 판정이 **이름으로
폴백**한다 — 안 그러면 재동기화 전까지 아무도 자기 문서를 못 지운다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("document_cache")}
    if "author_notion_ids" not in cols:
        op.add_column(
            "document_cache",
            sa.Column("author_notion_ids", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("document_cache")}
    if "author_notion_ids" in cols:
        op.drop_column("document_cache", "author_notion_ids")
