"""문서 작업공간이 화면에 답하는 것들 (지시 22.4 · 22.5).

## 요약 넷은 **누르면 좁혀지는 수**다

「전체 268」 같은 수를 장식으로 두면 아무 행동으로도 이어지지 않는다. 그래서 각 수는 아래
목록의 조건 하나와 **같은 판정**을 쓴다 — 여기서 갈라지면 「최근 수정 3」을 눌렀는데 두
줄이 나오는 화면이 되고, 그때 사용자가 믿는 것은 목록이 아니라 아무것도 아니게 된다.

## 목록 한 줄이 그리는 것

작성자 · 미리보기 · 공간/폴더 · 첨부와 댓글 수. 문서마다 물으면 한 화면이 문서 수의 몇
배만큼 질의가 되므로 **쪽 단위로 한 번에** 모은다. 여기서 보는 것은 그 값들이 실제로
실려 나가는가다 — 안 실리면 화면이 조용히 빈 칸을 그린다.

## 「내 초안」은 지어낸 상태가 아니다

이 제품의 문서에는 상태 칸이 없고 만들지도 않았다. `version` 은 만들 때 1 이고 저장할
때마다 오르므로, 「아직 한 번도 고치지 않은 내 문서」는 이미 있는 사실을 읽은 것이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "kw-me@goodmit.co.kr"
MATE = "kw-mate@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, Folder, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="작업공간팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    mate = make_user(MATE, role="user", display_name="동료")
    me.department_id = dept.id
    mate.department_id = dept.id

    space = KnowledgeSpace(name="우리 공간", slug="kw-space", owner_kind="department",
                           owner_dept_id=dept.id, org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    # `sort_order` 는 not-null 이고 `path`·`depth` 는 트리거가 쓴다(D-244) — 값을 손으로
    # 적지 않고 자리만 준다.
    parent = Folder(space_id=space.id, name="01. 기획", sort_order=1)
    db.add(parent)
    db.flush()
    child = Folder(space_id=space.id, name="1-1. 요구사항", parent_id=parent.id, sort_order=1)
    db.add(child)
    db.flush()

    mine_draft = Document(space_id=space.id, title="내 초안", created_by=me.id,
                          folder_id=child.id)
    mine_edited = Document(space_id=space.id, title="내가 고친 문서", created_by=me.id,
                           version=3)
    theirs = Document(space_id=space.id, title="동료 문서", created_by=mate.id, version=2)
    db.add_all([mine_draft, mine_edited, theirs])
    db.commit()
    return {
        "space": space.id, "folder": child.id, "parent": parent.id,
        "draft": mine_draft.id, "edited": mine_edited.id, "theirs": theirs.id,
    }


def _hdr(login_as, email=ME):
    return {"X-CSRF-Token": login_as("user", email=email)}


def _list(client, hdr, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get("/api/knowledge/documents" + (f"?{query}" if query else ""), headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ── 요약 ─────────────────────────────────────────────────────────────────────


def test_the_summary_counts_match_the_lists_they_open(client, login_as, world):
    """🔴 요약과 목록이 **같은 판정**을 쓰는가.

    다르면 「내 초안 1」을 눌렀을 때 두 줄이 나오거나 한 줄도 안 나오고, 그 어긋남은 아무
    오류도 안 낸다.
    """
    hdr = _hdr(login_as)
    summary = client.get("/api/knowledge/summary", headers=hdr)
    assert summary.status_code == 200, summary.text
    body = summary.json()

    assert body["total"] == _list(client, hdr)["total"]
    assert body["drafts"] == _list(client, hdr, mine="true", drafts="true")["total"]
    assert body["favorites"] == _list(client, hdr, favorites="true")["total"]


def test_the_draft_count_is_only_mine_and_only_untouched(client, login_as, world):
    """「내 초안」의 뜻 둘 — 내가 만들었고, 아직 고치지 않았다."""
    hdr = _hdr(login_as)
    assert client.get("/api/knowledge/summary", headers=hdr).json()["drafts"] == 1
    rows = _list(client, hdr, mine="true", drafts="true")["items"]
    assert [d["title"] for d in rows] == ["내 초안"]


def test_the_summary_never_counts_a_document_i_cannot_see(client, login_as, world, db):
    """가시성은 요약에도 걸린다 — 수만 새어 나가도 남의 공간에 무엇이 있는지 알려 준다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other = Department(name="남의 작업공간팀", org_id=DEFAULT_ORG_ID)
    db.add(other)
    db.flush()
    space = KnowledgeSpace(name="남의 공간", slug="kw-other", owner_kind="department",
                           owner_dept_id=other.id, org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    db.add(Document(space_id=space.id, title="남의 문서"))
    db.commit()

    hdr = _hdr(login_as)
    assert client.get("/api/knowledge/summary", headers=hdr).json()["total"] == 3


# ── 목록 한 줄 ───────────────────────────────────────────────────────────────


def test_a_row_carries_who_wrote_it_and_where_it_lives(client, login_as, world):
    """화면이 그리는 것을 서버가 실어야 한다 — 없으면 목록이 조용히 빈 칸이 된다."""
    hdr = _hdr(login_as)
    rows = {d["title"]: d for d in _list(client, hdr)["items"]}
    draft = rows["내 초안"]
    assert draft["author"]["display_name"] == "나"
    assert draft["space_name"] == "우리 공간"
    # 폴더는 **조상까지** 적는다. 「1-1. 요구사항」만 보여 주면 같은 이름의 폴더가 두 곳에
    # 있을 때 구별이 안 된다.
    assert draft["folder_path"] == "01. 기획 > 1-1. 요구사항"
    assert draft["counts"] == {"attachments": 0, "comments": 0, "relations": 0}


def test_a_row_carries_a_preview_of_the_body(client, login_as, world):
    """제목만으로는 무슨 문서인지 모른다. 미리보기는 **현재 판의 파생 텍스트**에서 온다."""
    hdr = _hdr(login_as)
    save = client.put(
        f"/api/knowledge/documents/{world['draft']}", headers=hdr,
        json={"body": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "이 문서는 요구사항을 정리합니다."}]}]}},
    )
    assert save.status_code == 200, save.text
    rows = {d["title"]: d for d in _list(client, hdr)["items"]}
    assert rows["내 초안"]["excerpt"] == "이 문서는 요구사항을 정리합니다."


def test_the_comment_count_is_visible_in_the_list(client, login_as, world):
    """「댓글 2」는 목록에서 문서를 고르는 근거다 — 열어 봐야 아는 값이면 못 고른다."""
    hdr = _hdr(login_as)
    r = client.post(f"/api/knowledge/documents/{world['edited']}/comments",
                    headers=hdr, json={"body": "질문 하나 남깁니다."})
    assert r.status_code in (200, 201), r.text
    rows = {d["title"]: d for d in _list(client, hdr)["items"]}
    assert rows["내가 고친 문서"]["counts"]["comments"] == 1
    assert rows["내 초안"]["counts"]["comments"] == 0


# ── 좁히기와 정렬 ────────────────────────────────────────────────────────────


def test_search_looks_at_the_body_not_only_the_title(client, login_as, world):
    """지시 22.4 는 「제목/본문 검색」이라고 적었다. 제목만 보면 내용을 기억하는 사람이
    자기 문서를 못 찾는다."""
    hdr = _hdr(login_as)
    client.put(f"/api/knowledge/documents/{world['edited']}", headers=hdr,
               json={"body": {"type": "doc", "content": [
                   {"type": "paragraph", "content": [
                       {"type": "text", "text": "결제 모듈 이관 계획"}]}]}})
    found = _list(client, hdr, q="결제")
    assert [d["title"] for d in found["items"]] == ["내가 고친 문서"]


def test_the_author_filter_narrows_to_one_person(client, login_as, world):
    hdr = _hdr(login_as)
    rows = _list(client, hdr, mine="true")["items"]
    assert sorted(d["title"] for d in rows) == ["내 초안", "내가 고친 문서"]


def test_sorting_by_title_is_a_total_order(client, login_as, world):
    """정렬 축 이름은 **허용 목록**을 지난다. 모르는 값은 기본 정렬로 떨어진다 —
    거절하면 옛 주소를 들고 온 사람의 목록이 통째로 깨진다."""
    hdr = _hdr(login_as)
    titles = [d["title"] for d in _list(client, hdr, sort="title")["items"]]
    assert titles == sorted(titles)
    fallback = _list(client, hdr, sort="아무거나")
    assert fallback["total"] == 3


# ── 새 문서의 틀 ─────────────────────────────────────────────────────────────


def test_the_template_list_does_not_ship_the_bodies(client, login_as):
    """고르는 자리에 필요한 것은 이름과 설명뿐이다. 본문까지 실으면 문서를 만들지 않는
    사람에게도 네 벌의 Block JSON 이 나간다."""
    hdr = _hdr(login_as)
    r = client.get("/api/knowledge/templates", headers=hdr)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # 🔴 이름으로 잰다. 틀이 표가 된 뒤(0027) id 는 조직마다 다른 UUID 라 고정 문자열로
    # 재면 시드가 도는 설치에서만 초록이다. 사용자가 보는 것도 이름이다.
    assert {i["name"] for i in items} >= {"빈 문서", "회의록", "요구사항 정의서", "운영 가이드"}
    assert all("body" not in i for i in items)
    blank = next(i for i in items if i["id"] == "blank")
    assert blank["empty"] is True and blank["builtin"] is True
    # 「빈 문서」 말고는 전부 표의 행이다 — 그래야 고치고 지울 수 있다.
    assert all(i["builtin"] is False for i in items if i["id"] != "blank")


def test_creating_with_a_template_fills_the_body(client, login_as, world):
    """틀은 **질문**을 채운다 — 예시 문장을 넣어 두면 그 문장이 지워지지 않은 채 저장된
    문서가 반드시 생긴다."""
    hdr = _hdr(login_as)
    catalog = client.get("/api/knowledge/templates", headers=hdr).json()["items"]
    meeting = next(t["id"] for t in catalog if t["name"] == "회의록")
    made = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": world["space"], "title": "8월 회의록", "template": meeting,
    })
    assert made.status_code == 200, made.text
    detail = client.get(f"/api/knowledge/documents/{made.json()['id']}", headers=hdr).json()
    headings = [
        node["content"][0]["text"]
        for node in detail["current"]["body"]["content"]
        if node["type"] == "heading"
    ]
    assert headings == ["회의 개요", "논의 내용", "정한 것", "할 일"]


def test_an_unknown_template_still_makes_the_document(client, login_as, world):
    """🔴 틀 하나를 없앤 날 그 이름을 들고 온 요청이 문서 생성 자체를 못 하게 되면,
    사용자는 자기가 쓴 제목까지 잃는다. 빈 문서로 시작하는 것은 잃는 것이 없다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": world["space"], "title": "틀 없는 문서", "template": "사라진틀",
    })
    assert made.status_code == 200, made.text
    detail = client.get(f"/api/knowledge/documents/{made.json()['id']}", headers=hdr).json()
    assert detail["current"]["body"]["content"] == []


def test_an_explicit_body_beats_the_template(client, login_as, world):
    """내용을 들고 오는 경로(제안을 문서로 옮기는 자리)가 틀 때문에 그 내용을 잃으면,
    사용자는 자기가 쓴 글이 사라진 것으로 본다."""
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": world["space"], "title": "옮겨 온 글", "template": "meeting",
        "body": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "원래 쓰던 글"}]}]},
    })
    assert made.status_code == 200, made.text
    detail = client.get(f"/api/knowledge/documents/{made.json()['id']}", headers=hdr).json()
    assert detail["current"]["body"]["content"][0]["content"][0]["text"] == "원래 쓰던 글"


# ── 최근 열람 ────────────────────────────────────────────────────────────────


def test_recently_opened_documents_are_mine_and_still_visible(client, login_as, world, db):
    """옛 기록은 남아 있어도 그 사이 권한이 바뀌었을 수 있다. 기록을 근거로 보여 주면
    목록에서 가린 문서를 「최근 열람」이 열어 준다."""
    hdr = _hdr(login_as)
    client.get(f"/api/knowledge/documents/{world['edited']}", headers=hdr)
    r = client.get("/api/knowledge/recent", headers=hdr)
    assert r.status_code == 200, r.text
    assert [d["title"] for d in r.json()["items"]] == ["내가 고친 문서"]

    # 보관한 문서는 「최근 열람」에서도 빠진다 — 휴지통에 있는 것을 최근 목록이 권하면 안 된다.
    from app.knowledge.models import Document

    document = db.get(Document, world["edited"])
    document.archived = True
    db.commit()
    assert client.get("/api/knowledge/recent", headers=hdr).json()["items"] == []
