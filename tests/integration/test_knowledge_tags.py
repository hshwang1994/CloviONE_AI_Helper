"""태그를 사람이 관리한다 (지시 22-5 개정).

## 무엇이 없었나

태그는 지금까지 **문서를 저장할 때 곁다리로** 생겼다(`tags.ensure`). 그래서 오타로 만든
태그를 고칠 방법이 없었고, 안 쓰는 태그를 치울 방법도 없었다 — 목록은 늘기만 했다.
운영에는 태그 19개가 있고 그중 여덟이 고객사 이름이라, 계약이 끝나거나 이름이 바뀌면
누군가는 그것을 고쳐야 한다.

## 여기서 보는 것

  1. **이름을 고치면 slug 도 함께 고쳐진다.** 안 그러면 다음 사람이 새 이름을 적었을 때
     옛 slug 를 못 찾아 같은 뜻의 태그가 하나 더 생긴다.
  2. **같은 뜻의 태그는 둘이 될 수 없다.** 추가와 이름 고치기 둘 다에서 막는다.
  3. **지우면 연결만 끊긴다** — 문서는 그대로다. 몇 건에서 떼어졌는지 말한다.
  4. 사용 수는 **내가 볼 수 있는 문서 안에서만** 센다. 수 하나도 남의 공간에 무엇이
     있는지 말해 준다.
  5. 이름을 고치고 지우는 것은 남의 문서에 영향을 주는 동작이라 문서 삭제와 같은 문이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "ktag-me@goodmit.co.kr"
OPS = "ktag-ops@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, DocumentTag, KnowledgeSpace, Tag
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="태그팀", org_id=DEFAULT_ORG_ID)
    other = Department(name="남의 태그팀", org_id=DEFAULT_ORG_ID)
    db.add_all([dept, other])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    me.department_id = dept.id
    ops = make_user(OPS, role="operator", display_name="운영자")
    ops.department_id = dept.id

    ours = KnowledgeSpace(name="우리 공간", slug="ktag-ours", owner_kind="department",
                          owner_dept_id=dept.id, org_id=DEFAULT_ORG_ID)
    theirs = KnowledgeSpace(name="남의 공간", slug="ktag-theirs", owner_kind="department",
                            owner_dept_id=other.id, org_id=DEFAULT_ORG_ID)
    db.add_all([ours, theirs])
    db.flush()

    shared = Tag(org_id=DEFAULT_ORG_ID, name="인프라", slug="인프라")
    hidden_only = Tag(org_id=DEFAULT_ORG_ID, name="남의태그", slug="남의태그")
    db.add_all([shared, hidden_only])
    db.flush()

    mine = Document(space_id=ours.id, title="우리 문서", created_by=me.id)
    theirs_doc = Document(space_id=theirs.id, title="남의 문서")
    db.add_all([mine, theirs_doc])
    db.flush()
    db.add_all([
        DocumentTag(document_id=mine.id, tag_id=shared.id),
        DocumentTag(document_id=theirs_doc.id, tag_id=shared.id),
        DocumentTag(document_id=theirs_doc.id, tag_id=hidden_only.id),
    ])
    db.commit()
    return {"shared": shared.id, "hidden_only": hidden_only.id, "doc": mine.id}


def _hdr(login_as, email=ME, role="user"):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _tags(client, hdr):
    r = client.get("/api/knowledge/tags", headers=hdr)
    assert r.status_code == 200, r.text
    return {t["name"]: t for t in r.json()["items"]}


# ── 목록과 사용 수 ───────────────────────────────────────────────────────────


def test_the_usage_count_only_sees_documents_i_can_see(client, login_as, world):
    """🔴 「인프라」는 문서 둘에 붙어 있지만 내가 볼 수 있는 것은 하나다."""
    rows = _tags(client, _hdr(login_as))
    assert rows["인프라"]["documents"] == 1
    # 남의 공간 문서에만 붙은 태그는 어휘로는 보이되 **사용 수는 0** 이다.
    assert rows["남의태그"]["documents"] == 0


# ── 추가 ─────────────────────────────────────────────────────────────────────


def test_a_tag_can_be_added_by_anyone_who_can_edit_documents(client, login_as, world):
    """문서를 저장하면서 태그가 이미 만들어진다 — 관리 화면의 추가에 더 좁은 문을 두면
    같은 일이 두 규칙을 갖는다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/tags", headers=hdr, json={"name": "배포 관리"})
    assert made.status_code == 200, made.text
    assert made.json()["documents"] == 0
    assert "배포 관리" in _tags(client, hdr)


def test_adding_a_tag_that_already_means_the_same_thing_is_refused(client, login_as, world):
    """🔴 「인프라」와 「 인프라 」는 같은 태그다(slug 가 같다).

    `ensure` 는 있으면 그것을 쓰지만, 관리 화면에서 「추가」를 누른 사람에게는 「이미
    있습니다」가 정확한 답이다 — 눌렀는데 아무 일도 안 일어나면 사람은 다시 누른다.
    """
    hdr = _hdr(login_as)
    again = client.post("/api/knowledge/tags", headers=hdr, json={"name": " 인프라 "})
    assert again.status_code == 409, again.text
    assert "이미" in again.json()["error"]["message"]


# ── 이름 고치기 ──────────────────────────────────────────────────────────────


def test_renaming_moves_the_slug_too(client, login_as, world, db):
    """🔴 이름만 바꾸면 다음 사람이 새 이름을 적었을 때 **같은 뜻의 태그가 하나 더** 생긴다."""
    from app.knowledge.models import Tag

    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.patch(f"/api/knowledge/tags/{world['shared']}", headers=hdr,
                     json={"name": "인프라 운영"})
    assert r.status_code == 200, r.text

    db.expire_all()
    tag = db.get(Tag, world["shared"])
    assert tag.name == "인프라 운영"
    assert tag.slug == "인프라 운영"

    # 문서의 연결은 그대로다 — 이름만 바뀌었다.
    detail = client.get(f"/api/knowledge/documents/{world['doc']}", headers=hdr).json()
    assert [t["name"] for t in detail["tags"]] == ["인프라 운영"]


def test_renaming_into_an_existing_tag_is_refused(client, login_as, world):
    """합치기는 안 한다 — 두 태그를 하나로 합치는 것은 문서 여럿의 분류를 바꾸는 일이고,
    이름을 고치다 실수로 그 일이 일어나면 되돌릴 방법이 없다."""
    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.patch(f"/api/knowledge/tags/{world['shared']}", headers=hdr,
                     json={"name": "남의태그"})
    assert r.status_code == 409, r.text


def test_an_ordinary_user_cannot_rename_or_delete(client, login_as, world):
    """이름을 고치면 그 태그를 쓰는 **모든 문서**의 표기가 바뀐다 — 문서 삭제와 같은 선이다."""
    hdr = _hdr(login_as)
    assert client.patch(f"/api/knowledge/tags/{world['shared']}", headers=hdr,
                        json={"name": "아무거나"}).status_code == 403
    assert client.delete(f"/api/knowledge/tags/{world['shared']}",
                         headers=hdr).status_code == 403


# ── 삭제 ─────────────────────────────────────────────────────────────────────


def test_deleting_a_tag_detaches_it_without_touching_the_documents(client, login_as, world, db):
    """🔴 태그를 지우면서 문서가 사라지면 그것은 다른 사고다.

    끊긴 건수를 돌려준다 — 화면이 그 수를 그대로 말해야 사용자가 방금 무슨 일이 일어났는지
    안다.
    """
    from sqlalchemy import func, select

    from app.knowledge.models import Document, DocumentTag

    hdr = _hdr(login_as, email=OPS, role="operator")
    r = client.delete(f"/api/knowledge/tags/{world['shared']}", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["detached"] == 2, "떼어진 문서 수를 안 말한다"

    db.expire_all()
    assert db.get(Document, world["doc"]) is not None, "문서가 함께 사라졌다"
    left = db.execute(
        select(func.count()).select_from(DocumentTag)
        .where(DocumentTag.tag_id == world["shared"])
    ).scalar_one()
    assert left == 0, "태그를 지웠는데 연결 행이 남았다 — 고아 데이터다"

    detail = client.get(f"/api/knowledge/documents/{world['doc']}", headers=hdr).json()
    assert detail["tags"] == []


def test_a_tag_from_another_organisation_is_not_found(client, login_as, world, db, two_orgs):
    """다른 조직의 태그는 **없는 것**이다. 403 은 그 조직에 그런 태그가 있다를 알려 준다."""
    from app.knowledge.models import Tag

    alien = Tag(org_id=two_orgs.org_b_id, name="남의조직", slug="남의조직")
    db.add(alien)
    db.commit()

    hdr = _hdr(login_as, email=OPS, role="operator")
    assert client.patch(f"/api/knowledge/tags/{alien.id}", headers=hdr,
                        json={"name": "고침"}).status_code == 404
    assert client.delete(f"/api/knowledge/tags/{alien.id}", headers=hdr).status_code == 404
