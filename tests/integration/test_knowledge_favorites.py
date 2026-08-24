"""즐겨찾기와 옛 주소 해석 — 옛 문서 화면에서 정본 문서로 옮겨 온 두 축 (S14 · C2).

## 즐겨찾기

담기·빼기는 멱등이고, 「즐겨찾기만」 필터는 **권한 조건과 나란히** 걸린다. 나란히 안 걸면
남이 담아 둔 문서나 범위 밖 문서가 이 목록으로 새어 나온다.

## 옛 주소

`/team-docs/<page id>` 는 알림 딥링크 · 감사 로그 · 사람들 북마크에 박혀 있다. 그 주소가
죽으면 사용자에게는 「문서가 사라졌다」로 보인다. 다리(`documents.legacy_page_id`)가 그
주소를 지금 문서로 데려가고, **못 찾는 것과 못 보는 것은 같은 404** 다 — 다르면 옛 id
하나로 남의 부서 문서의 존재를 확인할 수 있다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "kf-me@goodmit.co.kr"
MATE = "kf-mate@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="즐겨찾기팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의 즐겨찾기팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    mate = make_user(MATE, role="user", display_name="동료")
    me.department_id = mine.id
    mate.department_id = mine.id

    ours = KnowledgeSpace(name="우리 공간", slug="kf-ours", owner_kind="department",
                          owner_dept_id=mine.id, org_id=DEFAULT_ORG_ID)
    others = KnowledgeSpace(name="남의 공간", slug="kf-theirs", owner_kind="department",
                            owner_dept_id=theirs.id, org_id=DEFAULT_ORG_ID)
    db.add_all([ours, others])
    db.flush()

    one = Document(space_id=ours.id, title="담을 문서", legacy_page_id="legacy-page-1")
    two = Document(space_id=ours.id, title="안 담을 문서")
    hidden = Document(space_id=others.id, title="남의 문서", legacy_page_id="legacy-page-2")
    db.add_all([one, two, hidden])
    db.commit()
    return {"space": ours.id, "one": one.id, "two": two.id, "hidden": hidden.id}


def _hdr(login_as, email=ME):
    return {"X-CSRF-Token": login_as("user", email=email)}


def _list(client, hdr, space, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/knowledge/documents?space_id={space}" + (f"&{query}" if query else "")
    r = client.get(url, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ── 즐겨찾기 ─────────────────────────────────────────────────────────────────


def test_a_document_can_be_starred_and_unstarred(client, login_as, world):
    hdr = _hdr(login_as)
    on = client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true", headers=hdr)
    assert on.status_code == 200, on.text
    assert on.json()["is_favorite"] is True

    only = _list(client, hdr, world["space"], favorites="true")
    assert [d["id"] for d in only["items"]] == [world["one"]]
    assert only["total"] == 1

    off = client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=false", headers=hdr)
    assert off.json()["is_favorite"] is False
    assert _list(client, hdr, world["space"], favorites="true")["total"] == 0


def test_starring_twice_is_idempotent(client, login_as, world):
    """더블클릭이나 재시도가 오류가 되면 안 된다 — 사용자가 원한 상태는 이미 됐다."""
    hdr = _hdr(login_as)
    first = client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true", headers=hdr)
    second = client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true", headers=hdr)
    assert first.status_code == second.status_code == 200
    assert _list(client, hdr, world["space"], favorites="true")["total"] == 1


def test_the_list_says_which_documents_are_starred(client, login_as, world):
    """화면이 별을 그리려면 목록이 그 값을 실어야 한다. 문서마다 한 번씩 묻게 하면
    목록 한 화면이 문서 수만큼의 요청이 된다."""
    hdr = _hdr(login_as)
    client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true", headers=hdr)
    rows = {d["id"]: d["is_favorite"] for d in _list(client, hdr, world["space"])["items"]}
    assert rows[world["one"]] is True
    assert rows[world["two"]] is False


def test_the_list_carries_doc_type_and_tags(client, login_as, world, db):
    """🔴 문서 상세는 태그를 실었는데(`_document_json(..., tags=...)`) 목록은 안 실었다.
    화면의 「분류」 필터로 좁힐 수는 있어도 각 줄에는 아무것도 안 보였다 — 필터만 있고
    줄에는 없으면 이관이 손실처럼 보인다(S14). 문서마다 한 번씩 묻지 않고 한 질의로
    낸다(`tags_mod.of_documents`) — 즐겨찾기와 같은 이유다.
    """
    from app.knowledge import tags
    from app.knowledge.models import Document

    hdr = _hdr(login_as)
    document = db.get(Document, world["one"])
    document.doc_type = "회의록"
    tags.set_for_document(db, document, ["인프라"])
    db.commit()

    rows = {d["id"]: d for d in _list(client, hdr, world["space"])["items"]}
    assert rows[world["one"]]["doc_type"] == "회의록"
    assert [t["name"] for t in rows[world["one"]]["tags"]] == ["인프라"]
    assert rows[world["two"]]["tags"] == []


def test_my_star_is_not_someone_elses(client, login_as, world):
    client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true",
                headers=_hdr(login_as, ME))
    mate_hdr = _hdr(login_as, MATE)
    assert _list(client, mate_hdr, world["space"], favorites="true")["total"] == 0
    rows = {d["id"]: d["is_favorite"] for d in _list(client, mate_hdr, world["space"])["items"]}
    assert rows[world["one"]] is False


def test_starring_a_document_i_cannot_see_is_404(client, login_as, world):
    """범위 밖은 **403 이 아니라 404** — 403 은 그 id 가 존재한다고 알려 준다."""
    r = client.post(f"/api/knowledge/documents/{world['hidden']}/favorite?on=true",
                    headers=_hdr(login_as))
    assert r.status_code == 404, f"범위 밖 문서를 담을 수 있다: {r.status_code} {r.text}"


def test_starring_requires_csrf(client, login_as, world):
    login_as("user", email=ME)
    r = client.post(f"/api/knowledge/documents/{world['one']}/favorite?on=true")
    assert r.status_code == 403


# ── 옛 주소 ──────────────────────────────────────────────────────────────────


def test_an_old_page_id_resolves_to_the_document(client, login_as, world):
    r = client.get("/api/knowledge/documents/by-legacy/legacy-page-1", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    assert r.json() == {"id": world["one"], "title": "담을 문서"}


def test_an_unknown_page_id_and_a_hidden_one_answer_the_same(client, login_as, world):
    """두 답이 다르면 옛 id 를 찍어 보며 존재하는 문서를 열거할 수 있다."""
    hdr = _hdr(login_as)
    missing = client.get("/api/knowledge/documents/by-legacy/no-such-page", headers=hdr)
    hidden = client.get("/api/knowledge/documents/by-legacy/legacy-page-2", headers=hdr)
    assert missing.status_code == hidden.status_code == 404
    assert missing.json()["error"]["message"] == hidden.json()["error"]["message"], (
        f"응답 문구가 달라 존재 여부가 새어 나간다: {missing.text} vs {hidden.text}"
    )


# ── 목록이 몇 건인지 말한다 ──────────────────────────────────────────────────


def test_the_list_reports_the_total_beyond_one_page(client, login_as, db, world):
    """서버는 한 페이지치만 주면서 `total` 을 함께 말해야 한다. 화면이 그 값을 안 보면
    두 번째 페이지의 문서는 **있다는 사실 자체가** 사용자에게 안 보인다 — 운영에서 문서
    110건 중 60건이 정확히 그렇게 가려져 있었다.
    """
    from app.knowledge.models import Document

    for i in range(5):
        db.add(Document(space_id=world["space"], title=f"쪽수 시험 {i}"))
    db.commit()

    hdr = _hdr(login_as)
    first = _list(client, hdr, world["space"], limit=3, offset=0)
    assert len(first["items"]) == 3
    assert first["total"] == 7, f"전체 건수를 안 말한다: {first['total']}"
    assert first["limit"] == 3 and first["offset"] == 0

    second = _list(client, hdr, world["space"], limit=3, offset=3)
    assert len(second["items"]) == 3
    first_ids = {d["id"] for d in first["items"]}
    assert not (first_ids & {d["id"] for d in second["items"]}), "두 쪽이 같은 문서를 보여 준다"
