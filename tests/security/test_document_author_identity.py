"""문서 삭제 권한을 **이름이 아니라 id 로** 판정한다 (X2).

`users.display_name` 에는 유일 제약이 없다(바로 위 `email` 에는 있다). 그래서 이름으로
판정하면 두 가지가 동시에 일어난다:

  * **개명하면 자기 문서를 못 지운다** — 이름이 안 맞으니 403.
  * **동명이인은 남의 문서를 지운다** — 이름이 맞으니 통과.

같은 저장소의 `app/core/people.py` 가 "display_name 에 유일 제약이 없다" 고 **이미 경고**해
놓았는데 이 판정만 그 이름을 신뢰하고 있었다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError

pytestmark = pytest.mark.security

NID_ME = "notion-doc-me"


@pytest.fixture()
def doc_world(db, make_user):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.team_docs.models import DocumentCache

    me = make_user("doc-me@goodmit.co.kr", role="user", display_name="김하나")
    twin = make_user("doc-twin@goodmit.co.kr", role="user", display_name="김하나")  # 동명이인
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_ME, status=STATUS_VERIFIED))
    doc = DocumentCache(notion_page_id="doc-1", title="내 문서",
                        author_names="김하나", author_notion_ids=NID_ME)
    db.add(doc)
    db.commit()
    return me, twin, doc


def test_the_author_can_delete_their_own_document(db, doc_world):
    from app.team_docs.service import ensure_can_delete_doc

    me, _, doc = doc_world
    ensure_can_delete_doc(doc, me, db)   # 예외가 없으면 통과


def test_a_namesake_cannot_delete_someone_elses_document(db, doc_world):
    """**같은 이름이라는 이유로 남의 문서를 지울 수 있었다.**"""
    from app.team_docs.service import ensure_can_delete_doc

    _, twin, doc = doc_world
    with pytest.raises(ForbiddenError):
        ensure_can_delete_doc(doc, twin, db)


def test_renaming_yourself_does_not_lock_you_out(db, doc_world):
    """**개명하면 자기 문서를 못 지웠다.** id 는 안 바뀌므로 그대로 지울 수 있어야 한다."""
    from app.team_docs.service import ensure_can_delete_doc

    me, _, doc = doc_world
    me.display_name = "김하나(개명)"
    db.commit()
    ensure_can_delete_doc(doc, me, db)


def test_rows_without_ids_still_fall_back_to_names(db, doc_world):
    """아직 동기화가 id 를 안 채운 행. 폴백이 없으면 **재동기화 전까지 아무도 자기 문서를
    못 지운다** — 고치려던 것보다 나쁜 상태가 된다."""
    from app.team_docs.service import ensure_can_delete_doc

    me, _, doc = doc_world
    doc.author_notion_ids = ""
    db.commit()
    ensure_can_delete_doc(doc, me, db)
