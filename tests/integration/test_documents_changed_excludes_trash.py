"""UA-09: readers.documents_changed_between() filtered on `archived` only, while its
sibling readers.recent_documents() already excludes trashed documents too (fixed earlier
for exactly this reason — see that function's docstring: "지운 문서로 가는 살아있는
링크"). A trashed-but-not-yet-archived document was double counted by the weekly digest
and rendered as a clickable link in AssistantPanel.jsx that 404'd.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.home import readers
from app.team_docs.models import DocumentCache
from app.trash.models import TRASH_DOCUMENT, TrashItem
from app.users.models import User

pytestmark = pytest.mark.integration

SINCE = "2026-08-02T15:00:00"
UNTIL = "2026-08-09T15:00:00"


def test_a_trashed_document_is_excluded_from_the_weekly_changed_count(db, make_user):
    user = make_user(email="ua09@goodmit.co.kr")
    db.add_all([
        DocumentCache(notion_page_id="doc-live", title="살아있는 문서", document_type="회의록",
                      owner="나", last_edited="2026-08-03T02:00:00.000Z",
                      synced_at=datetime(2026, 8, 3, 2, 0, 0)),
        DocumentCache(notion_page_id="doc-trashed", title="지운 문서", document_type="회의록",
                      owner="나", last_edited="2026-08-04T02:00:00.000Z",
                      synced_at=datetime(2026, 8, 4, 2, 0, 0)),
    ])
    db.add(TrashItem(
        item_type=TRASH_DOCUMENT, notion_page_id="doc-trashed", title="지운 문서",
        url="https://notion/doc-trashed", deleted_by_user_id=user.id,
        deleted_by_name="테스트", deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.commit()

    result = readers.documents_changed_between(db, SINCE, UNTIL)
    ids = {item["id"] for item in result["items"]}
    assert "doc-live" in ids
    assert "doc-trashed" not in ids, "휴지통 문서가 이번 주 변경 목록에 남아 있다 — 클릭하면 404"
    assert result["count"] == 1
