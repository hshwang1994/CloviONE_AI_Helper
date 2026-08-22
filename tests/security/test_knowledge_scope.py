"""지식 공간과 문서도 **범위를 지킨다** (S7 · D-193 · D-194).

## 왜 새 도메인마다 이 시험이 필요한가

이 저장소는 같은 실수를 네 번 했다(`scripts/check_scope_gates.py` 서문): 목록에는 범위를
걸고 **같은 모듈의 단건·쓰기에는 안 걸었다.** 지식 도메인은 그 함정이 특히 크다 —
가시성이 문서 자신이 아니라 **공간**에서 오기 때문에(§5.3), 문서 쪽 조회에 조건을
빼먹어도 문서 목록만 보면 정상으로 보인다.

여기서 보는 것 다섯:

1. **공간 목록·상세**에 남의 부서 공간이 안 나온다 (404, 403 이 아니다).
2. **문서 목록·상세**가 공간의 가시성을 물려받는다.
3. **폴더 조회·수정**이 남의 공간을 못 건드린다 — 폴더는 권한 축이 아니지만, 그렇다고
   권한 없는 공간의 폴더를 만질 수 있다는 뜻은 아니다.
4. **`confidential` 공간**은 만든 사람과 `SPACE_ADMIN` 만 본다.
5. **관계 잇기**가 한쪽만 보이는 상태에서 안 통한다 — 통하면 안 보이는 문서의 id 가
   존재한다는 사실이 새 나간다.

## 양쪽을 함께 본다

「안 보인다」만 확인하면 **전부 안 보이는 구현**도 통과한다. 그래서 각 단정에 「우리 것은
보인다」를 함께 둔다.
"""

from __future__ import annotations

import pytest

from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department

pytestmark = pytest.mark.security

BOSS = "knowledge-scope-boss@goodmit.co.kr"
OUTSIDER = "knowledge-scope-outsider@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 부서 공간 + 각 공간 문서 + **우리 부서만 보는 관리자**."""
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user(BOSS, role="admin", display_name="팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    def _space(name, slug, dept):
        row = KnowledgeSpace(
            org_id=DEFAULT_ORG_ID, name=name, slug=slug,
            owner_kind="department", owner_dept_id=dept.id,
        )
        db.add(row)
        db.flush()
        return row

    ours = _space("우리 공간", "ours", mine)
    theirs_space = _space("남의 공간", "theirs", theirs)

    def _document(space, title):
        row = Document(space_id=space.id, title=title)
        db.add(row)
        db.flush()
        return row

    result = {
        "ours": ours,
        "theirs": theirs_space,
        "ours_doc": _document(ours, "우리 문서"),
        "theirs_doc": _document(theirs_space, "남의 문서"),
        "boss": boss,
    }
    db.commit()
    return result


@pytest.fixture()
def api(client, login_as, world):
    headers = {"X-CSRF-Token": login_as("admin", email=BOSS)}

    class Api:
        def get(self, path):
            return client.get(path, headers=headers)

        def post(self, path, json=None):
            return client.post(path, json=json or {}, headers=headers)

        def patch(self, path, json=None):
            return client.patch(path, json=json or {}, headers=headers)

        def put(self, path, json=None):
            return client.put(path, json=json or {}, headers=headers)

    return Api()


# ── 공간 ─────────────────────────────────────────────────────────────────────


def test_the_space_list_shows_ours_and_not_theirs(api, world):
    slugs = {s["slug"] for s in api.get("/api/knowledge/spaces").json()["items"]}
    assert "ours" in slugs, f"우리 부서 공간이 목록에 없다 — 검사가 헛돈다: {slugs}"
    assert "theirs" not in slugs, f"남의 부서 공간이 목록에 있다: {slugs}"


def test_opening_someone_elses_space_is_404(api, world):
    """**403 이 아니라 404** 다. 403 은 그 공간이 존재한다는 사실을 알려 준다."""
    r = api.get(f"/api/knowledge/spaces/{world['theirs'].id}")
    assert r.status_code == 404, f"남의 공간이 열렸다: {r.status_code} {r.text}"


def test_opening_our_own_space_works(api, world):
    """반대편 — 여기서 실패하면 위 시험은 「전부 막는 구현」도 통과시킨다."""
    assert api.get(f"/api/knowledge/spaces/{world['ours'].id}").status_code == 200


def test_editing_someone_elses_space_is_404(api, world):
    r = api.patch(f"/api/knowledge/spaces/{world['theirs'].id}", {"name": "가로챈 이름"})
    assert r.status_code == 404, r.text


def test_someone_elses_tree_is_404(api, world):
    r = api.get(f"/api/knowledge/spaces/{world['theirs'].id}/tree")
    assert r.status_code == 404, r.text


# ── 문서는 공간의 가시성을 물려받는다 ──────────────────────────────────────


def test_the_document_list_inherits_space_visibility(api, world):
    titles = {d["title"] for d in api.get("/api/knowledge/documents").json()["items"]}
    assert "우리 문서" in titles, f"우리 문서가 목록에 없다 — 검사가 헛돈다: {titles}"
    assert "남의 문서" not in titles, f"남의 공간 문서가 목록에 있다: {titles}"


def test_opening_a_document_in_someone_elses_space_is_404(api, world):
    r = api.get(f"/api/knowledge/documents/{world['theirs_doc'].id}")
    assert r.status_code == 404, r.text


def test_opening_our_own_document_works(api, world):
    assert api.get(f"/api/knowledge/documents/{world['ours_doc'].id}").status_code == 200


def test_saving_a_document_in_someone_elses_space_is_404(api, world):
    r = api.put(f"/api/knowledge/documents/{world['theirs_doc'].id}", {"title": "가로챔"})
    assert r.status_code == 404, r.text


def test_filtering_by_someone_elses_space_returns_nothing(api, world):
    """필터는 좁히기만 한다 — 넓힐 수 있으면 선택기를 안 보여 줘도 API 한 번에 뚫린다."""
    r = api.get(f"/api/knowledge/documents?space_id={world['theirs'].id}")
    assert r.status_code == 404, f"공간 필터로 범위를 넓혔다: {r.status_code} {r.text}"


def test_the_version_history_of_someone_elses_document_is_404(api, world):
    r = api.get(f"/api/knowledge/documents/{world['theirs_doc'].id}/versions")
    assert r.status_code == 404, r.text


def test_the_diff_of_someone_elses_document_is_404(api, world):
    r = api.get(f"/api/knowledge/documents/{world['theirs_doc'].id}/diff?base=1&target=2")
    assert r.status_code == 404, r.text


def test_restoring_a_version_of_someone_elses_document_is_404(api, world):
    r = api.post(f"/api/knowledge/documents/{world['theirs_doc'].id}/versions/1/restore")
    assert r.status_code == 404, r.text


def test_creating_a_document_in_someone_elses_space_is_404(api, world):
    r = api.post("/api/knowledge/documents", {
        "space_id": world["theirs"].id, "title": "몰래 넣기",
    })
    assert r.status_code == 404, r.text


# ── 폴더 ─────────────────────────────────────────────────────────────────────


def test_creating_a_folder_in_someone_elses_space_is_404(api, world):
    r = api.post("/api/knowledge/folders", {
        "space_id": world["theirs"].id, "name": "몰래 만든 폴더",
    })
    assert r.status_code == 404, r.text


def test_editing_a_folder_in_someone_elses_space_is_404(api, world, db):
    from app.knowledge import folders

    folder = folders.create(db, space_id=world["theirs"].id, name="남의 폴더")
    db.commit()
    r = api.patch(f"/api/knowledge/folders/{folder.id}", {"name": "가로챈 이름"})
    assert r.status_code == 404, r.text


def test_editing_a_folder_in_our_space_works(api, world, db):
    from app.knowledge import folders

    folder = folders.create(db, space_id=world["ours"].id, name="우리 폴더")
    db.commit()
    r = api.patch(f"/api/knowledge/folders/{folder.id}", {"name": "새 이름"})
    assert r.status_code == 200, r.text


# ── `confidential` — 유일한 축소 원시연산 (D-193) ───────────────────────────


def test_a_confidential_space_hides_from_someone_without_space_admin(
    client, login_as, world, db, make_user
):
    """소유자 + 명시 부여자 + `SPACE_ADMIN` 만 본다. 여기서 보는 사람은 **셋 다 아니다.**"""
    secret = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="비밀 공간", slug="secret",
        owner_kind="organization", confidential=True,
    )
    db.add(secret)
    db.commit()

    make_user(OUTSIDER, role="user", display_name="일반 사용자")
    headers = {"X-CSRF-Token": login_as("user", email=OUTSIDER)}

    listed = client.get("/api/knowledge/spaces", headers=headers).json()["items"]
    assert "secret" not in {s["slug"] for s in listed}
    r = client.get(f"/api/knowledge/spaces/{secret.id}", headers=headers)
    assert r.status_code == 404, r.text


def test_an_ordinary_space_is_visible_to_that_same_person(
    client, login_as, world, db, make_user
):
    """반대편 — 위 시험이 「일반 사용자에게는 아무것도 안 보인다」로 통과하면 안 된다."""
    open_space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="열린 공간", slug="open", owner_kind="organization",
    )
    db.add(open_space)
    db.commit()

    make_user(OUTSIDER, role="user", display_name="일반 사용자")
    headers = {"X-CSRF-Token": login_as("user", email=OUTSIDER)}
    listed = client.get("/api/knowledge/spaces", headers=headers).json()["items"]
    assert "open" in {s["slug"] for s in listed}


def test_space_admin_can_see_a_confidential_space(api, db):
    """`SPACE_ADMIN` 이 그것을 여는 권한이다 — `admin` 역할이 그 권한을 갖는다(0002 시드)."""
    secret = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="비밀 공간", slug="secret2",
        owner_kind="organization", confidential=True,
    )
    db.add(secret)
    db.commit()
    assert api.get(f"/api/knowledge/spaces/{secret.id}").status_code == 200


# ── 관계 ─────────────────────────────────────────────────────────────────────


def test_relating_to_a_document_we_cannot_see_is_404(api, world):
    """통하면 **안 보이는 문서의 id 가 존재한다**는 사실이 새 나간다."""
    r = api.post(f"/api/knowledge/documents/{world['ours_doc'].id}/relations", {
        "to_document_id": world["theirs_doc"].id, "kind": "references",
    })
    assert r.status_code == 404, r.text


def test_relating_two_documents_we_can_see_works(api, world, db):
    other = Document(space_id=world["ours"].id, title="우리 두 번째 문서")
    db.add(other)
    db.commit()
    r = api.post(f"/api/knowledge/documents/{world['ours_doc'].id}/relations", {
        "to_document_id": other.id, "kind": "references",
    })
    assert r.status_code == 200, r.text
    assert len(r.json()["relations"]) == 1


# ── 권한 게이트 ─────────────────────────────────────────────────────────────


def test_a_plain_user_cannot_create_a_space(client, login_as, make_user):
    """공간을 만드는 것은 **권한 경계를 만드는 것**이라 `SPACE_ADMIN` 이다.

    `SPACE_WRITE` 와 같은 선에 두면 아무나 자기만 보이는 공간을 만들어 조직의 글을
    그 안으로 옮길 수 있다.
    """
    make_user(OUTSIDER, role="user", display_name="일반 사용자")
    headers = {"X-CSRF-Token": login_as("user", email=OUTSIDER)}
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "내 공간", "slug": "mine", "owner_kind": "organization"},
        headers=headers,
    )
    assert r.status_code == 403, r.text


def test_writing_without_a_csrf_token_is_rejected(client, login_as, world):
    login_as("admin", email=BOSS)
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "토큰 없이", "slug": "no-token", "owner_kind": "organization"},
    )
    assert r.status_code == 403, r.text
