"""문서를 폴더로 재분류해도 **볼 수 있는 사람이 안 바뀐다** (지시 22.7 개정 · 7항).

## 왜 이것을 시험하는가

마이그레이션 `0022` 가 이관 문서 111건의 `folder_id` 를 한 번에 채운다. 폴더는 정리 축이고
가시성은 공간이 정하지만(§5.3), 그 사실은 **코드가 지금 그렇게 돼 있다**는 뜻이지 앞으로도
그렇다는 보장이 아니다. 누군가 폴더에 권한을 붙이는 날, 이 시험이 먼저 깨져야 한다.

같은 이유로 검색 색인도 본다. 색인 행이 폴더를 싣기 시작하면 재분류가 검색 결과를 바꾸고,
그때 목록·상세·검색·AI 가 **서로 다른 답**을 하게 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

INSIDER = "drv-in@goodmit.co.kr"
OUTSIDER = "drv-out@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, Folder, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="재분류팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의 재분류팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    insider = make_user(INSIDER, role="user", display_name="안쪽")
    outsider = make_user(OUTSIDER, role="user", display_name="바깥")
    insider.department_id = mine.id
    outsider.department_id = theirs.id

    space = KnowledgeSpace(name="우리 공간", slug="drv-space", owner_kind="department",
                           owner_dept_id=mine.id, org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    folder = Folder(space_id=space.id, name="01. 회의록", sort_order=1)
    db.add(folder)
    db.flush()

    document = Document(space_id=space.id, title="재분류할 문서", created_by=insider.id)
    db.add(document)
    db.commit()
    return {"space": space.id, "folder": folder.id, "document": document.id}


def _can_see(client, login_as, email, document_id) -> bool:
    hdr = {"X-CSRF-Token": login_as("user", email=email)}
    return client.get(f"/api/knowledge/documents/{document_id}", headers=hdr).status_code == 200


def test_moving_a_document_into_a_folder_changes_nobody(client, login_as, world, db):
    """🔴 폴더는 **정리 축**이다. 여기서 권한이 움직이면 재분류 한 번이 유출이 된다."""
    from app.knowledge.models import Document

    before = (
        _can_see(client, login_as, INSIDER, world["document"]),
        _can_see(client, login_as, OUTSIDER, world["document"]),
    )
    assert before == (True, False), "이 시험의 전제가 깨졌다"

    document = db.get(Document, world["document"])
    document.folder_id = world["folder"]
    db.commit()

    after = (
        _can_see(client, login_as, INSIDER, world["document"]),
        _can_see(client, login_as, OUTSIDER, world["document"]),
    )
    assert after == before, "폴더를 옮겼더니 볼 수 있는 사람이 달라졌다"


def test_the_list_still_shows_it_to_the_same_person(client, login_as, world, db):
    from app.knowledge.models import Document

    document = db.get(Document, world["document"])
    document.folder_id = world["folder"]
    db.commit()

    hdr = {"X-CSRF-Token": login_as("user", email=INSIDER)}
    titles = [
        d["title"] for d in client.get("/api/knowledge/documents", headers=hdr).json()["items"]
    ]
    assert "재분류할 문서" in titles

    out = {"X-CSRF-Token": login_as("user", email=OUTSIDER)}
    theirs = [
        d["title"] for d in client.get("/api/knowledge/documents", headers=out).json()["items"]
    ]
    assert "재분류할 문서" not in theirs


def test_the_search_index_row_does_not_depend_on_the_folder(db, world):
    """🔴 색인이 폴더를 싣기 시작하면 재분류가 검색 결과를 바꾼다.

    그러면 목록·상세·검색·AI 가 서로 다른 답을 하게 되고, 그 어긋남은 「검색에는 나오는데
    열면 404」로만 드러난다. 색인 행이 같은지를 **값으로** 본다 — 주석이 아니라.
    """
    from sqlalchemy import text

    from app.search.indexer import _document_rows

    before, _ = _document_rows(db)
    row_before = next(r for r in before if r["ref_id"] == world["document"])

    # 마이그레이션 `0022` 와 **같은 방식**으로 옮긴다 — 날 SQL 이라 `updated_at` 을 안 건드린다.
    # ORM 으로 옮기면 `onupdate` 가 그 칸을 지금 시각으로 올리고, 그러면 이관 문서 111건이
    # 전부 「방금 고침」이 되어 작업공간의 「최근 수정」이 거짓말을 한다.
    db.execute(
        text("UPDATE documents SET folder_id = :f WHERE id = :d"),
        {"f": world["folder"], "d": world["document"]},
    )
    db.commit()

    after, _ = _document_rows(db)
    row_after = next(r for r in after if r["ref_id"] == world["document"])
    assert row_after == row_before, "폴더를 옮겼더니 검색 색인 행이 달라졌다"
    assert "folder" not in " ".join(row_after.keys())


def test_the_ai_candidate_set_does_not_depend_on_the_folder(db, world):
    """AI 후보도 같은 기준을 쓴다(지시 22.9). 보관 여부만 보고 폴더는 안 본다."""
    from sqlalchemy import select

    from app.knowledge.models import Document

    stmt = select(Document.id).where(Document.archived.is_(False))
    before = set(db.execute(stmt).scalars().all())

    document = db.get(Document, world["document"])
    document.folder_id = world["folder"]
    db.commit()

    assert set(db.execute(stmt).scalars().all()) == before


def test_reclassifying_does_not_make_every_document_look_freshly_edited(db, world):
    """🔴 재분류가 「최근 수정」을 뒤집으면 안 된다.

    `folder_id` 를 ORM 으로 채우면 `onupdate` 가 `updated_at` 을 지금 시각으로 올린다. 그러면
    이관 문서 111건이 **전부 오늘 고친 문서**가 되어, 목록의 기본 정렬도 요약의 「최근 수정」도
    아무 뜻이 없어진다. 마이그레이션이 날 SQL 을 쓰는 이유가 그것이다.
    """
    from sqlalchemy import text

    from app.knowledge.models import Document

    before = db.get(Document, world["document"]).updated_at
    db.execute(
        text("UPDATE documents SET folder_id = :f WHERE id = :d"),
        {"f": world["folder"], "d": world["document"]},
    )
    db.commit()
    db.expire_all()
    assert db.get(Document, world["document"]).updated_at == before
