"""문서의 소속은 프로젝트다 — 공간은 그 다리일 뿐이다 (재검수 묶음2 §11.4·§14).

## 여기서 보는 것

  1. `project_id` 로 새 문서를 만들면 그 프로젝트의 공간을 **찾거나 만든다**(§14.2) —
     화면이 "공간"을 몰라도 된다.
  2. 두 번째 문서가 같은 프로젝트를 고르면 **같은 공간을 재사용한다**(공간이 두 개
     생기지 않는다).
  3. `GET /documents?project_id=` 가 그 프로젝트 공간의 문서로 좁힌다.
  4. 목록·상세 응답의 `project` 가 `{id, code, name}` — 공통 공간 문서는 `null`.
  5. `POST /documents/{id}/move` 에 `project_id` 를 주면 공간이 바뀌고, 옛 폴더 참조는
     버려진다(다른 공간의 폴더를 가리킬 수 없다).
  6. `tags`(다중)는 **AND** — 고른 태그를 전부 가진 문서만 남는다.
"""

from __future__ import annotations

import pytest

from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project

pytestmark = pytest.mark.integration

ME = "kproj-me@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    me = make_user(ME, role="admin", display_name="나")
    me.admin_scope = "global"

    # 코드는 `ck_projects_code_shape` 를 지켜야 한다 — I·L·O·숫자 없는 대문자 6글자.
    alpha = Project(name="알파 프로젝트", code="AAAAAA", org_id=DEFAULT_ORG_ID)
    beta = Project(name="베타 프로젝트", code="BBBBBB", org_id=DEFAULT_ORG_ID)
    db.add_all([alpha, beta])
    db.flush()

    common = KnowledgeSpace(
        name="팀 문서", slug="kproj-common", owner_kind="organization", org_id=DEFAULT_ORG_ID,
    )
    db.add(common)
    db.flush()
    loose = Document(space_id=common.id, title="공통 문서", created_by=me.id)
    db.add(loose)
    db.commit()
    return {"alpha": alpha.id, "beta": beta.id, "common_space": common.id, "loose": loose.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=ME)}


def test_creating_with_project_id_makes_the_space_on_first_use(client, login_as, world, db):
    hdr = _hdr(login_as)
    before = db.query(KnowledgeSpace).filter(
        KnowledgeSpace.owner_project_id == world["alpha"]
    ).count()
    assert before == 0

    r = client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"project_id": world["alpha"], "title": "알파 문서 1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["space_id"], "project_id 만 줬는데 공간이 안 정해졌다"

    after = db.query(KnowledgeSpace).filter(
        KnowledgeSpace.owner_project_id == world["alpha"]
    ).all()
    assert len(after) == 1, "같은 프로젝트에 공간이 두 개 생겼다"
    assert after[0].id == body["space_id"]

    # 상세(GET)는 목록과 같은 계약으로 project 를 낸다(§11.4) — extras 를 통해서다.
    detail = client.get(f"/api/knowledge/documents/{body['id']}", headers=hdr)
    assert detail.json()["project"] == {
        "id": world["alpha"], "code": "AAAAAA", "name": "알파 프로젝트",
    }

    r2 = client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"project_id": world["alpha"], "title": "알파 문서 2"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["space_id"] == body["space_id"], "두 번째 문서가 같은 공간을 안 썼다"


def test_project_id_filter_narrows_the_list(client, login_as, world):
    hdr = _hdr(login_as)
    client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"project_id": world["beta"], "title": "베타 문서"},
    )

    r = client.get(f"/api/knowledge/documents?project_id={world['beta']}", headers=hdr)
    assert r.status_code == 200, r.text
    titles = [d["title"] for d in r.json()["items"]]
    assert titles == ["베타 문서"]

    # 공통 공간 문서는 project_id 필터에 안 걸린다.
    r_all = client.get("/api/knowledge/documents", headers=hdr)
    all_titles = {d["title"] for d in r_all.json()["items"]}
    assert "공통 문서" in all_titles


def test_common_space_documents_have_no_project(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.get(f"/api/knowledge/documents/{world['loose']}", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["project"] is None


def test_move_with_project_id_switches_space_and_drops_stale_folder(
    client, login_as, world, db,
):
    hdr = _hdr(login_as)
    made = client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"space_id": world["common_space"], "title": "옮길 문서"},
    )
    doc_id = made.json()["id"]
    folder = client.post(
        "/api/knowledge/folders", headers=hdr,
        json={"space_id": world["common_space"], "name": "임시 폴더"},
    )
    client.post(
        f"/api/knowledge/documents/{doc_id}/move", headers=hdr,
        json={"folder_id": folder.json()["id"]},
    )

    moved = client.post(
        f"/api/knowledge/documents/{doc_id}/move", headers=hdr,
        json={"project_id": world["alpha"]},
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["space_id"] != world["common_space"]
    assert body["folder_id"] is None, "옛 공간의 폴더를 그대로 가리키고 있다"

    new_space = db.get(KnowledgeSpace, body["space_id"])
    assert new_space.owner_project_id == world["alpha"]


def test_tags_filter_is_and_not_or(client, login_as, world):
    hdr = _hdr(login_as)
    a = client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"space_id": world["common_space"], "title": "Docker 문서",
              "tag_names": ["Docker"]},
    ).json()
    both = client.post(
        "/api/knowledge/documents", headers=hdr,
        json={"space_id": world["common_space"], "title": "Docker+K8s 문서",
              "tag_names": ["Docker", "Kubernetes"]},
    ).json()

    r = client.get(
        "/api/knowledge/documents?tags=Docker&tags=Kubernetes", headers=hdr,
    )
    ids = {d["id"] for d in r.json()["items"]}
    assert ids == {both["id"]}, "AND 가 아니라 OR 로 좁혀졌다"
    assert a["id"] not in ids


def test_project_none_lists_only_common_documents(client, login_as, world):
    """🔴 `project_id=none` 은 「어느 프로젝트에도 속하지 않은 문서만」이다.

    이 센티널이 없으면 분할이 안 닫힌다 — 각 프로젝트 필터로는 프로젝트 문서만 잡히고,
    공통 문서는 「전체」에서 눈으로 골라내는 수밖에 없었다. 각 프로젝트 + 공통 = 전체.
    """
    made = client.post(
        "/api/knowledge/documents",
        json={"title": "알파 문서", "project_id": world["alpha"]},
        headers=_hdr(login_as),
    )
    assert made.status_code == 200, made.text

    body = client.get(
        "/api/knowledge/documents?project_id=none", headers=_hdr(login_as)
    ).json()
    titles = {d["title"] for d in body["items"]}
    assert "공통 문서" in titles, titles
    assert "알파 문서" not in titles, titles

    # 반례 — 기존 프로젝트 필터와 임의 uuid 는 그대로다.
    scoped = client.get(
        f"/api/knowledge/documents?project_id={world['alpha']}", headers=_hdr(login_as)
    ).json()
    assert {d["title"] for d in scoped["items"]} == {"알파 문서"}
    ghost = client.get(
        "/api/knowledge/documents?project_id=00000000-0000-0000-0000-000000000000",
        headers=_hdr(login_as),
    ).json()
    assert ghost["items"] == []
