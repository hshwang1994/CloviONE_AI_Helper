"""프로젝트가 **선택**이 된 뒤의 계약 (문서 개편 3·4·6·21번).

## 이 파일이 지키는 것 셋

1. **프로젝트를 안 골라도 문서가 만들어진다.** 예전에는 「어느 프로젝트(또는 공간)의
   문서인지 골라 주세요」로 거절했다.
2. 🔴 **그 문서가 아무에게도 안 보이는 자리에 앉으면 안 된다.** 공통 공간의
   `owner_kind` 가 `unset` 이면 `app/authz/visibility.py::_stored_ownership_rules` 의
   어느 갈래에도 안 걸려 전역 조회 권한자 말고는 목록에서도 AI 검색에서도 사라진다 —
   오류 한 줄 없이. 실측에서 문서 110건이 그렇게 사라진 적이 있다.
3. **「프로젝트 미지정」 필터로 그 문서를 다시 찾을 수 있다.** 만들 수만 있고 못 찾으면
   만들지 못하는 것과 같다.

## 「최근 24시간」은 타일과 목록이 같은 수를 말해야 한다

조건을 두 자리에 손으로 적으면 「12」를 눌렀을 때 아홉 줄이 나오고, 그 어긋남은 수를
세어 본 사람만 안다. 그래서 둘 다 `service.recently_updated_since` 하나를 쓴다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration

ME = "kpo-me@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user, make_project):
    from app.core.models_base import utcnow
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    make_user(ME, role="admin", display_name="나")
    # 코드는 **제품의 생성기**가 짓는다(D-282) — 손으로 고르면 `ck_projects_code_shape` 와
    # 갈라지고, 갈라진 사실은 DB 제약이 잡을 때까지 안 보인다.
    project = make_project(name="인천국제공항공사 [클라우드 인프라 고도화]")
    pspace = KnowledgeSpace(name=project.name, slug="icn", owner_kind="project",
                            owner_project_id=project.id, org_id=DEFAULT_ORG_ID)
    db.add(pspace)
    db.flush()
    # 프로젝트 문서 하나 — 「프로젝트 미지정」이 이것을 안 집어 오는지 재려면 필요하다.
    db.add(Document(space_id=pspace.id, title="프로젝트 문서",
                    updated_at=utcnow() - timedelta(days=9)))
    db.commit()
    return {"project": project.id, "pspace": pspace.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=ME)}


def _stamp(db, when, *, only=None) -> None:
    """문서의 `updated_at` 을 **주입된 시계 기준**으로 박는다.

    두 가지 이유로 SQL 이다.

    1. ORM 으로는 못 민다 — `TimestampMixin` 이 `onupdate=utcnow` 라 대입한 값을 flush 가
       **지금**으로 덮는다.
    2. 🔴 그리고 그 「지금」이 시험에서는 **읽는 쪽과 다른 시계**다. 쓰기 경로는
       `utcnow()`(실제 시각)로 찍는데 목록·요약은 주입된 `FakeClock`(2026-07-14 고정)을
       본다. 운영에서는 `SystemClock.now() == utcnow()` 라 둘이 같지만, 시험에서는
       두 달 넘게 벌어져 **모든 문서가 창 안에** 들어온다. 그래서 창을 재는 시험은
       기준 시각을 시계에서 가져와 직접 박는다.
    """
    import sqlalchemy as sa

    sql = "UPDATE documents SET updated_at = :t"
    params = {"t": when}
    if only is not None:
        sql += " WHERE id = :i"
        params["i"] = only
    db.execute(sa.text(sql), params)
    db.commit()


def _list(client, hdr, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get("/api/knowledge/documents" + (f"?{query}" if query else ""), headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ── 프로젝트 없이 만들기 ─────────────────────────────────────────────────────


def test_a_document_can_be_created_with_no_project_at_all(client, login_as, world):
    """인수 조건 5. 예전에는 여기서 422 였다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr,
                       json={"title": "프로젝트 없는 문서"})
    assert made.status_code == 200, made.text
    assert made.json()["title"] == "프로젝트 없는 문서"


def test_the_sentinel_none_means_the_same_thing_as_sending_nothing(client, login_as, world):
    """화면의 「프로젝트 미지정」이 보내는 값도 같은 자리로 온다."""
    hdr = _hdr(login_as)
    a = client.post("/api/knowledge/documents", headers=hdr,
                    json={"title": "센티널 문서", "project_id": "none"})
    assert a.status_code == 200, a.text
    b = client.post("/api/knowledge/documents", headers=hdr, json={"title": "빈 값 문서"})
    detail_a = client.get(f"/api/knowledge/documents/{a.json()['id']}", headers=hdr).json()
    detail_b = client.get(f"/api/knowledge/documents/{b.json()['id']}", headers=hdr).json()
    assert detail_a["space_id"] == detail_b["space_id"]


def test_the_common_space_is_never_owner_kind_unset(client, login_as, world, db):
    """🔴 이 파일에서 가장 중요한 시험.

    `unset` 이면 그 문서는 만든 사람 눈에도 안 보인다 — 목록에서도, AI 검색에서도.
    """
    from app.knowledge.models import Document, KnowledgeSpace

    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr, json={"title": "소유 검사"})
    assert made.status_code == 200, made.text

    db.expire_all()
    document = db.get(Document, made.json()["id"])
    space = db.get(KnowledgeSpace, document.space_id)
    assert space.owner_kind == "organization", f"공통 공간의 소유가 {space.owner_kind} 다"
    assert space.org_id, "공통 공간에 조직이 없다 — 그것도 아무에게도 안 보이는 상태다"
    # 조직 전체에 `unset` 공간이 하나도 없어야 한다.
    stray = [s.slug for s in db.query(KnowledgeSpace).filter(
        KnowledgeSpace.owner_kind == "unset").all()]
    assert stray == [], f"소유가 없는 공간이 남아 있다: {stray}"


def test_the_project_space_and_the_common_space_are_not_the_same_row(client, login_as, world):
    """프로젝트를 고르면 그 프로젝트 공간으로 간다 — 공통으로 새지 않는다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr,
                       json={"title": "프로젝트 있는 문서", "project_id": world["project"]})
    assert made.status_code == 200, made.text
    detail = client.get(f"/api/knowledge/documents/{made.json()['id']}", headers=hdr).json()
    assert detail["space_id"] == world["pspace"]


def test_the_migration_default_space_is_the_same_space_the_product_uses(world):
    """이관·Import 가 넣는 공통 공간과 화면이 만드는 공통 공간은 **같은 행**이어야 한다.

    두 벌로 적어 두면 「프로젝트 미지정」 필터가 절반만 돌려주고, 그 절반은 아무도 안 센다.
    """
    from app.knowledge import service
    from app.migration import load

    assert load.DEFAULT_SPACE_SLUG == service.COMMON_SPACE_SLUG
    assert load.DEFAULT_SPACE_NAME == service.COMMON_SPACE_NAME


# ── 프로젝트 미지정 필터 ─────────────────────────────────────────────────────


def test_the_unassigned_filter_finds_exactly_the_project_less_documents(client, login_as, world):
    """인수 조건 6. 그리고 프로젝트 문서는 안 끼어 온다."""
    hdr = _hdr(login_as)
    client.post("/api/knowledge/documents", headers=hdr, json={"title": "미지정 A"})
    client.post("/api/knowledge/documents", headers=hdr, json={"title": "미지정 B"})
    client.post("/api/knowledge/documents", headers=hdr,
                json={"title": "프로젝트 C", "project_id": world["project"]})

    titles = {d["title"] for d in _list(client, hdr, project_id="none")["items"]}
    assert {"미지정 A", "미지정 B"} <= titles
    assert "프로젝트 C" not in titles
    assert "프로젝트 문서" not in titles


def test_project_less_documents_are_not_missing_from_the_full_list_or_search(
    client, login_as, world
):
    """인수 조건 4의 나머지 절반 — 프로젝트가 없다는 이유로 **빠지면 안 된다.**"""
    hdr = _hdr(login_as)
    client.post("/api/knowledge/documents", headers=hdr, json={"title": "찾아야 하는 문서"})

    assert "찾아야 하는 문서" in {d["title"] for d in _list(client, hdr)["items"]}
    found = _list(client, hdr, q="찾아야")["items"]
    assert [d["title"] for d in found] == ["찾아야 하는 문서"]


def test_a_document_can_be_moved_back_to_unassigned(client, login_as, world):
    """이동 대화상자의 「프로젝트 미지정」.

    🔴 예전 설계는 이 값을 `allLabel` 로 그리려 했는데, 그것은 **빈 값**의 이름만 바꾼다 —
    센티널이 서버에 안 오고 이동이 조용히 아무것도 안 한다. 값이 실제로 도는지 잰다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr,
                       json={"title": "옮길 문서", "project_id": world["project"]})
    document_id = made.json()["id"]
    assert client.get(f"/api/knowledge/documents/{document_id}",
                      headers=hdr).json()["space_id"] == world["pspace"]

    moved = client.post(f"/api/knowledge/documents/{document_id}/move", headers=hdr,
                        json={"project_id": "none"})
    assert moved.status_code == 200, moved.text
    after = client.get(f"/api/knowledge/documents/{document_id}", headers=hdr).json()
    assert after["space_id"] != world["pspace"]
    assert "옮길 문서" in {d["title"] for d in _list(client, hdr, project_id="none")["items"]}


# ── 최근 24시간 ──────────────────────────────────────────────────────────────


def test_the_24h_tile_and_the_24h_list_say_the_same_number(
    client, login_as, world, db, fake_clock
):
    """인수 조건 7의 「최근 24시간」. 타일과 목록이 **같은 술어**를 쓰는가."""
    hdr = _hdr(login_as)
    fresh = client.post("/api/knowledge/documents", headers=hdr, json={"title": "방금 고친 문서"})
    assert fresh.status_code == 200, fresh.text
    client.post("/api/knowledge/documents", headers=hdr, json={"title": "오래된 문서"})

    now = fake_clock.now()
    # 전부 창 밖으로 밀고(30시간 전), 하나만 창 안으로 되돌린다. 그래야 「창이 실제로
    # 좁히는가」를 재고, fixture 가 만든 문서까지 결과에 섞이지 않는다.
    _stamp(db, now - timedelta(hours=30))
    _stamp(db, now, only=fresh.json()["id"])

    summary = client.get("/api/knowledge/summary", headers=hdr).json()
    listed = _list(client, hdr, updated_within_hours=24)
    assert summary["recent"] == listed["total"]

    titles = {d["title"] for d in listed["items"]}
    assert titles == {"방금 고친 문서"}, f"창 안에 다른 것이 들어왔다: {titles}"


def test_the_24h_filter_is_not_just_a_sort(client, login_as, world, db, fake_clock):
    """예전 「최근 수정」 타일은 `sort=recent` 만 걸어 **전체를 정렬만** 했다.

    그래서 「최근 24시간」이라고 적어 놓고 2025년 문서를 첫 줄 아래에 계속 보여 줬다.
    """
    hdr = _hdr(login_as)
    today = client.post("/api/knowledge/documents", headers=hdr, json={"title": "오늘 문서"})
    client.post("/api/knowledge/documents", headers=hdr, json={"title": "지난주 문서"})

    now = fake_clock.now()
    _stamp(db, now - timedelta(hours=200))
    _stamp(db, now, only=today.json()["id"])

    everything = _list(client, hdr, sort="recent")["total"]
    windowed = _list(client, hdr, updated_within_hours=24)["total"]
    assert windowed < everything, "24시간 창이 전체와 같다 — 필터가 안 걸렸다"
    assert {d["title"] for d in _list(client, hdr, updated_within_hours=24)["items"]} == {
        "오늘 문서"
    }


# ── 제목만 바꾼 저장도 AI 색인을 낡게 표시한다 ───────────────────────────────


def test_renaming_a_document_marks_the_ai_index_stale(client, login_as, world, db):
    """🔴 오래 열려 있던 구멍 (문서 개편 21번).

    제목만 고치면 `snapshot()` 이 「본문이 같다」며 `None` 을 돌려주어 색인 신호를 안
    보내고, 훑기의 낡음 조건 넷에도 제목이 없다. 그런데 제목은 **첫 청크 본문에**
    들어가므로 그 문서는 옛 이름으로 계속 검색됐다.
    """
    from app.ai.models import AiIndexState

    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr, json={"title": "옛 이름"})
    document_id = made.json()["id"]

    db.expire_all()
    state = db.query(AiIndexState).filter(AiIndexState.document_id == document_id).one_or_none()
    if state is not None:
        state.status = "ok"
        db.commit()

    saved = client.put(f"/api/knowledge/documents/{document_id}", headers=hdr,
                       json={"title": "새 이름"})
    assert saved.status_code == 200, saved.text
    # 본문은 안 보냈으므로 새 판은 안 생긴다 — 그런데도 색인은 낡았다고 적혀야 한다.
    assert saved.json()["created_version"] is False

    db.expire_all()
    state = db.query(AiIndexState).filter(AiIndexState.document_id == document_id).one_or_none()
    assert state is not None, "제목만 바꾼 저장이 색인 신호를 아예 안 남겼다"
    assert state.status == "pending", f"색인이 여전히 {state.status} 다 — 옛 이름으로 검색된다"


def test_the_trash_calls_a_project_less_document_unassigned_not_by_its_space_name(
    client, login_as, world
):
    """🔴 휴지통의 「프로젝트」 열도 같은 낱말을 쓴다.

    목록과 문서 상세는 프로젝트 없는 문서를 「프로젝트 미지정」이라고 부르는데, 휴지통만
    조직 공통 공간의 **이름**(「팀 문서」)을 그 칸에 넣고 있었다. 그러면 같은 문서가
    화면마다 다른 프로젝트에 있는 것처럼 읽힌다 — 라벨이 내용에 대해 거짓말을 하는 자리다.

    프로젝트 문서 쪽도 함께 잰다. 한쪽만 재면 「전부 미지정으로 적는다」로 고쳐도 초록이다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr,
                       json={"title": "버릴 미지정 문서"})
    assert made.status_code == 200, made.text
    mine = made.json()["id"]
    owned = client.post("/api/knowledge/documents", headers=hdr,
                        json={"title": "버릴 프로젝트 문서", "project_id": world["project"]})
    assert owned.status_code == 200, owned.text

    for doc_id in (mine, owned.json()["id"]):
        assert client.delete(f"/api/knowledge/documents/{doc_id}",
                             headers=hdr).status_code == 200

    rows = client.get("/api/trash", headers=hdr)
    assert rows.status_code == 200, rows.text
    by_title = {r["title"]: r for r in rows.json()["items"]}

    assert by_title["버릴 미지정 문서"]["space"] == "프로젝트 미지정", \
        "휴지통이 공통 공간의 이름을 프로젝트인 것처럼 적었다"
    assert by_title["버릴 프로젝트 문서"]["space"] == \
        "인천국제공항공사 [클라우드 인프라 고도화]", \
        "프로젝트 문서까지 미지정으로 적으면 열이 아무것도 안 말한다"
