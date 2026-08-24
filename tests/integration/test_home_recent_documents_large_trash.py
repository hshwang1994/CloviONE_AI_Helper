"""UA-24: recent_documents() fed the *entire* trashed-page-id set into a single SQL
NOT IN(...) clause. Databases cap host variables per statement — once a long-lived
install's trash crosses that count, this query (and therefore the whole home page,
since every user hits it) raised an unhandled error instead of degrading gracefully.
Trash only grows over time, so "it fits today" was never a safe assumption.

Fixed by chunking the exclusion list via app/core/db.py::batched() and AND-ing the
NOT IN clauses together (semantically identical to one big NOT IN — `x NOT IN A AND
x NOT IN B` == `x NOT IN (A ∪ B)`).

S14: 휴지통은 아직 옛 page id 로 담기고, 정본 문서는 그 값을 `legacy_page_id` 에 들고
있다. 그래서 대조 축이 그 칸으로 옮겨 갔다 — 청크로 자르는 성질은 그대로다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.db import ID_BATCH_SIZE
from app.home import readers
from app.trash.models import TRASH_DOCUMENT, TrashItem

pytestmark = pytest.mark.integration


def test_recent_documents_does_not_crash_when_trash_exceeds_one_sql_batch(
    db, make_user, make_space, make_knowledge_document
):
    user = make_user(email="ua24@goodmit.co.kr")
    space = make_space(name="UA24 공간", slug="ua24", org_wide=True)
    # ID_BATCH_SIZE(500)를 넘겨 반드시 2개 이상의 NOT IN 청크가 필요하게 만든다.
    trash_count = ID_BATCH_SIZE + 50
    for i in range(trash_count):
        make_knowledge_document(
            space=space, title=f"지운 문서 {i}", legacy_page_id=f"doc-trashed-{i}",
            updated_at=datetime(2026, 8, 1),
        )
    db.add_all([
        TrashItem(
            item_type=TRASH_DOCUMENT, notion_page_id=f"doc-trashed-{i}", title=f"지운 문서 {i}",
            url=None, deleted_by_user_id=user.id, deleted_by_name="테스트",
            deleted_at=datetime(2026, 8, 1),
        )
        for i in range(trash_count)
    ])
    live = make_knowledge_document(
        space=space, title="살아있는 문서", updated_at=datetime(2026, 8, 5),
    )
    db.commit()

    # 예전 코드라면 여기서 "too many SQL variables" 가 처리 안 된 채 그대로 샜다.
    items = readers.recent_documents(db)

    titles = {item["title"] for item in items}
    assert "살아있는 문서" in titles
    assert {item["id"] for item in items} == {live.id}, (
        "휴지통 문서가 청크 경계를 넘는 규모에서 새어 나왔다"
    )
