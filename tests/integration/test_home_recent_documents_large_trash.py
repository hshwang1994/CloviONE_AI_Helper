"""UA-24: recent_documents() fed the *entire* trashed-page-id set into a single SQL
NOT IN(...) clause. SQLite caps host variables per statement (999 on older builds,
32766 on newer ones) — once a long-lived install's trash crosses that count, this
query (and therefore the whole home page, since every user hits it) raised an
unhandled OperationalError instead of degrading gracefully. Trash only grows over
time, so "it fits today" was never a safe assumption.

Fixed by chunking the exclusion list via app/core/db.py::batched() and AND-ing the
NOT IN clauses together (semantically identical to one big NOT IN — `x NOT IN A AND
x NOT IN B` == `x NOT IN (A ∪ B)`).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.db import ID_BATCH_SIZE
from app.home import readers
from app.team_docs.models import DocumentCache
from app.trash.models import TRASH_DOCUMENT, TrashItem

pytestmark = pytest.mark.integration


def test_recent_documents_does_not_crash_when_trash_exceeds_one_sql_batch(db, make_user):
    user = make_user(email="ua24@goodmit.co.kr")
    # ID_BATCH_SIZE(500)를 넘겨 반드시 2개 이상의 NOT IN 청크가 필요하게 만든다.
    trash_count = ID_BATCH_SIZE + 50
    db.add_all([
        DocumentCache(
            notion_page_id=f"doc-trashed-{i}", title=f"지운 문서 {i}",
            last_edited="2026-08-01T00:00:00.000Z", synced_at=datetime(2026, 8, 1),
        )
        for i in range(trash_count)
    ])
    db.add_all([
        TrashItem(
            item_type=TRASH_DOCUMENT, notion_page_id=f"doc-trashed-{i}", title=f"지운 문서 {i}",
            url=None, deleted_by_user_id=user.id, deleted_by_name="테스트",
            deleted_at=datetime(2026, 8, 1),
        )
        for i in range(trash_count)
    ])
    db.add(DocumentCache(
        notion_page_id="doc-live", title="살아있는 문서",
        last_edited="2026-08-05T00:00:00.000Z", synced_at=datetime(2026, 8, 5),
    ))
    db.commit()

    # 예전 코드라면 여기서 sqlite3.OperationalError("too many SQL variables")가 처리 안
    # 된 채 그대로 샜다.
    items = readers.recent_documents(db)

    ids = {item["id"] for item in items}
    assert "doc-live" in ids
    assert not any(i.startswith("doc-trashed-") for i in ids), (
        "휴지통 문서가 청크 경계를 넘는 규모에서 새어 나왔다"
    )
