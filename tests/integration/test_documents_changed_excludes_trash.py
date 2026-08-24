"""UA-09: readers.documents_changed_between() filtered on `archived` only, while its
sibling readers.recent_documents() already excludes trashed documents too (fixed earlier
for exactly this reason — see that function's docstring: "지운 문서로 가는 살아있는
링크"). A trashed-but-not-yet-archived document was double counted by the weekly digest
and rendered as a clickable link in AssistantPanel.jsx that 404'd.

S14: 두 형제 함수 모두 정본(`documents`)을 읽는다. 휴지통은 아직 옛 page id 로 담기므로
`legacy_page_id` 로 맞춰 본다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.home import readers
from app.trash.models import TRASH_DOCUMENT, TrashItem

pytestmark = pytest.mark.integration

SINCE = "2026-08-02T15:00:00"
UNTIL = "2026-08-09T15:00:00"


def test_a_trashed_document_is_excluded_from_the_weekly_changed_count(
    db, make_user, make_space, make_knowledge_document
):
    user = make_user(email="ua09@goodmit.co.kr")
    space = make_space(name="UA09 공간", slug="ua09", org_wide=True)
    live = make_knowledge_document(
        space=space, title="살아있는 문서", doc_type="회의록",
        updated_at=datetime(2026, 8, 3, 2, 0, 0),
    )
    make_knowledge_document(
        space=space, title="지운 문서", doc_type="회의록", legacy_page_id="doc-trashed",
        updated_at=datetime(2026, 8, 4, 2, 0, 0),
    )
    db.add(TrashItem(
        item_type=TRASH_DOCUMENT, notion_page_id="doc-trashed", title="지운 문서",
        url=None, deleted_by_user_id=user.id,
        deleted_by_name="테스트", deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.commit()

    result = readers.documents_changed_between(db, SINCE, UNTIL)
    titles = {item["title"] for item in result["items"]}
    assert "살아있는 문서" in titles
    assert "지운 문서" not in titles, "휴지통 문서가 이번 주 변경 목록에 남아 있다 — 클릭하면 404"
    assert {item["id"] for item in result["items"]} == {live.id}
    assert result["count"] == 1
