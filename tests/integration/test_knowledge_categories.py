"""카테고리를 사람이 관리한다 (0026).

## 무엇이 없었나

`documents.doc_type` 은 CRUD 도 필터도 없는 자유 문자열이라, 분류 어휘가 Notion 이관
시점에 얼어붙어 있었다. 회사마다 문서를 다르게 가르므로 어휘는 제품이 아니라 관리
화면이 만든다 — 태그와 같은 계약(추가는 편집 가능자 전부, 이름 고치기와 삭제는
운영자군)으로 세운다.

## 여기서 보는 것

  1. 태그와 같은 정규화 — 「회의록」과 「 회의록 」은 같은 카테고리다.
  2. 이름을 고치면 slug 도 함께 고쳐진다. 다른 카테고리와 겹치면 거절한다.
  3. 지우면 문서는 **미분류로 돌아온다** — 몇 건이 돌아왔는지 말한다.
  4. 사용 수는 내가 볼 수 있는 문서 안에서만 센다.
  5. 목록 필터 `category_id` 는 서버가 걸고, 검색·태그와 AND 로 겹친다.
  6. 저장(PUT)에서 「안 보냈다」와 「해제한다(null)」는 다른 요청이다 — 카테고리를
     모르는 호출자가 저장할 때마다 분류가 지워지면 안 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "kcat-me@goodmit.co.kr"
OPS = "kcat-ops@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, DocumentCategory, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="분류팀", org_id=DEFAULT_ORG_ID)
    other = Department(name="남의 분류팀", org_id=DEFAULT_ORG_ID)
    db.add_all([dept, other])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    me.department_id = dept.id
    ops = make_user(OPS, role="operator", display_name="운영자")
    ops.department_id = dept.id

    ours = KnowledgeSpace(name="우리 공간", slug="kcat-ours", owner_kind="department",
                          owner_dept_id=dept.id, org_id=DEFAULT_ORG_ID)
    theirs = KnowledgeSpace(name="남의 공간", slug="kcat-theirs", owner_kind="department",
                            owner_dept_id=other.id, org_id=DEFAULT_ORG_ID)
    db.add_all([ours, theirs])
    db.flush()

    meeting = DocumentCategory(org_id=DEFAULT_ORG_ID, name="회의록", slug="회의록",
                               sort_order=1024)
    hidden_only = DocumentCategory(org_id=DEFAULT_ORG_ID, name="남의분류", slug="남의분류",
                                   sort_order=2048)
    db.add_all([meeting, hidden_only])
    db.flush()

    mine = Document(space_id=ours.id, title="우리 회의록", created_by=me.id,
                    category_id=meeting.id)
    plain = Document(space_id=ours.id, title="분류 없는 문서", created_by=me.id)
    theirs_doc = Document(space_id=theirs.id, title="남의 문서", category_id=meeting.id)
    theirs_hidden = Document(space_id=theirs.id, title="남의 분류 문서",
                             category_id=hidden_only.id)
    db.add_all([mine, plain, theirs_doc, theirs_hidden])
    db.commit()
    return {
        "meeting": meeting.id, "hidden_only": hidden_only.id,
        "doc": mine.id, "plain": plain.id, "space": ours.id,
    }


def _hdr(login_as, email=ME, role="user"):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _categories(client, hdr):
    r = client.get("/api/knowledge/categories", headers=hdr)
    assert r.status_code == 200, r.text
    return {c["name"]: c for c in r.json()["items"]}


# ── 목록과 사용 수 ───────────────────────────────────────────────────────────


def test_the_usage_count_only_sees_documents_i_can_see(client, login_as, world):
    """「회의록」은 문서 둘에 붙어 있지만 내가 볼 수 있는 것은 하나다."""
    rows = _categories(client, _hdr(login_as))
    assert rows["회의록"]["document_count"] == 1
    assert rows["남의분류"]["document_count"] == 0


def test_the_list_is_ordered_by_sort_order(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.get("/api/knowledge/categories", headers=hdr)
    names = [c["name"] for c in r.json()["items"]]
    assert names == ["회의록", "남의분류"]


# ── 추가 ─────────────────────────────────────────────────────────────────────


def test_a_category_can_be_added_by_anyone_who_can_edit_documents(client, login_as, world):
    """태그의 추가와 같은 문이다 — 어휘가 두 개라고 규칙이 두 벌이 되면 안 된다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/categories", headers=hdr, json={"name": "기술 문서"})
    assert made.status_code == 200, made.text
    assert made.json()["document_count"] == 0
    assert "기술 문서" in _categories(client, hdr)


def test_adding_a_category_that_already_means_the_same_thing_is_refused(client, login_as, world):
    """「회의록」과 「 회의록 」은 같은 카테고리다(slug 가 같다)."""
    hdr = _hdr(login_as)
    again = client.post("/api/knowledge/categories", headers=hdr, json={"name": " 회의록 "})
    assert again.status_code == 409, again.text
    assert "이미" in again.json()["error"]["message"]


# ── 이름 고치기 ──────────────────────────────────────────────────────────────


def test_renaming_moves_the_slug_too(client, login_as, world, db):
    """이름만 바꾸면 다음 사람이 새 이름을 적었을 때 같은 뜻의 카테고리가 하나 더 생긴다."""
    from app.knowledge.models import DocumentCategory

    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.patch(f"/api/knowledge/categories/{world['meeting']}", headers=hdr,
                     json={"name": "회의 기록"})
    assert r.status_code == 200, r.text

    db.expire_all()
    category = db.get(DocumentCategory, world["meeting"])
    assert category.name == "회의 기록"
    assert category.slug == "회의 기록"

    # 문서의 분류는 그대로다 — 이름만 바뀌었다.
    detail = client.get(f"/api/knowledge/documents/{world['doc']}", headers=hdr).json()
    assert detail["category"] == {"id": world["meeting"], "name": "회의 기록"}


def test_renaming_into_an_existing_category_is_refused(client, login_as, world):
    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.patch(f"/api/knowledge/categories/{world['meeting']}", headers=hdr,
                     json={"name": "남의분류"})
    assert r.status_code == 409, r.text


def test_an_ordinary_user_cannot_rename_or_delete(client, login_as, world):
    """이름을 고치면 그 분류를 쓰는 모든 문서의 표기가 바뀐다 — 문서 삭제와 같은 선이다."""
    hdr = _hdr(login_as)
    assert client.patch(f"/api/knowledge/categories/{world['meeting']}", headers=hdr,
                        json={"name": "아무거나"}).status_code == 403
    assert client.delete(f"/api/knowledge/categories/{world['meeting']}",
                         headers=hdr).status_code == 403


# ── 삭제 ─────────────────────────────────────────────────────────────────────


def test_deleting_a_category_returns_documents_to_unclassified(client, login_as, world, db):
    """카테고리를 지우면서 문서가 사라지면 그것은 다른 사고다 — 미분류로 돌아올 뿐이다."""
    from app.knowledge.models import Document

    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.delete(f"/api/knowledge/categories/{world['meeting']}", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["detached"] == 2, "미분류로 돌아간 문서 수를 안 말한다"

    db.expire_all()
    doc = db.get(Document, world["doc"])
    assert doc is not None, "문서가 함께 사라졌다"
    assert doc.category_id is None, "분류가 안 풀렸다"

    detail = client.get(f"/api/knowledge/documents/{world['doc']}", headers=hdr).json()
    assert detail["category"] is None


def test_a_category_from_another_organisation_is_not_found(client, login_as, world, db, two_orgs):
    """다른 조직의 카테고리는 **없는 것**이다(404) — 403 은 존재를 알려 준다."""
    from app.knowledge.models import DocumentCategory

    alien = DocumentCategory(org_id=two_orgs.org_b_id, name="남의조직", slug="남의조직")
    db.add(alien)
    db.commit()

    hdr = _hdr(login_as, email=OPS, role="operator")
    assert client.patch(f"/api/knowledge/categories/{alien.id}", headers=hdr,
                        json={"name": "고침"}).status_code == 404
    assert client.delete(f"/api/knowledge/categories/{alien.id}", headers=hdr).status_code == 404


# ── 목록 필터 ────────────────────────────────────────────────────────────────


def test_the_list_filter_narrows_to_that_category(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.get("/api/knowledge/documents",
                   params={"category_id": world["meeting"]}, headers=hdr)
    assert r.status_code == 200, r.text
    titles = [d["title"] for d in r.json()["items"]]
    # 남의 공간의 「회의록」 문서는 가시성이 거른다 — 필터가 새는 문이 되면 안 된다.
    assert titles == ["우리 회의록"]
    assert r.json()["total"] == 1


def test_the_category_filter_stacks_with_search(client, login_as, world):
    """필터는 좁히는 축이다 — 검색과 AND 로 겹친다."""
    hdr = _hdr(login_as)
    r = client.get("/api/knowledge/documents",
                   params={"category_id": world["meeting"], "q": "없는 낱말"}, headers=hdr)
    assert r.json()["total"] == 0
    r = client.get("/api/knowledge/documents",
                   params={"category_id": world["meeting"], "q": "회의록"}, headers=hdr)
    assert r.json()["total"] == 1


def test_list_rows_carry_the_category(client, login_as, world):
    """목록 행이 분류를 실어야 화면이 문서마다 다시 묻지 않는다."""
    hdr = _hdr(login_as)
    r = client.get("/api/knowledge/documents", headers=hdr)
    by_title = {d["title"]: d for d in r.json()["items"]}
    assert by_title["우리 회의록"]["category"] == {"id": world["meeting"], "name": "회의록"}
    assert by_title["분류 없는 문서"]["category"] is None


# ── 만들기와 저장 ────────────────────────────────────────────────────────────


def test_creating_a_document_with_a_category(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": world["space"], "title": "분류 달린 새 문서",
        "category_id": world["meeting"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["category"] == {"id": world["meeting"], "name": "회의록"}


def test_creating_with_an_alien_category_is_not_found(client, login_as, world, db, two_orgs):
    from app.knowledge.models import DocumentCategory

    alien = DocumentCategory(org_id=two_orgs.org_b_id, name="남의조직분류", slug="남의조직분류")
    db.add(alien)
    db.commit()

    hdr = _hdr(login_as)
    r = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": world["space"], "title": "남의 분류를 단 문서", "category_id": alien.id,
    })
    assert r.status_code == 404, r.text


def test_saving_without_the_field_keeps_the_category(client, login_as, world):
    """카테고리를 모르는 호출자(제목만 고치는 저장)가 분류를 지우면 안 된다."""
    hdr = _hdr(login_as)
    r = client.put(f"/api/knowledge/documents/{world['doc']}", headers=hdr,
                   json={"title": "제목만 고침"})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == {"id": world["meeting"], "name": "회의록"}


def test_saving_null_clears_the_category(client, login_as, world):
    """`category_id: null` 은 「해제한다」다 — 「안 보냈다」와 다른 요청이다."""
    hdr = _hdr(login_as)
    r = client.put(f"/api/knowledge/documents/{world['doc']}", headers=hdr,
                   json={"category_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["category"] is None


def test_saving_a_category_sets_it(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.put(f"/api/knowledge/documents/{world['plain']}", headers=hdr,
                   json={"category_id": world["meeting"]})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == {"id": world["meeting"], "name": "회의록"}


# ── 감사 로그 ────────────────────────────────────────────────────────────────


def test_rename_and_delete_are_audited(client, login_as, world, db):
    from sqlalchemy import select

    from app.audit.models import AuditLog

    hdr = _hdr(login_as, email=OPS, role="operator")
    client.patch(f"/api/knowledge/categories/{world['meeting']}", headers=hdr,
                 json={"name": "회의 기록"})
    client.delete(f"/api/knowledge/categories/{world['meeting']}", headers=hdr)
    db.expire_all()
    actions = set(db.execute(
        select(AuditLog.action).where(AuditLog.object_id == world["meeting"])
    ).scalars().all())
    assert "knowledge.category_rename" in actions
    assert "knowledge.category_delete" in actions
