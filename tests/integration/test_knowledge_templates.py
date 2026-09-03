"""새 문서의 틀을 조직이 스스로 관리한다 (문서 개편 7번 · 0027).

## 이 파일이 지키는 계약 하나

**틀을 고치거나 지워도 이미 그 틀로 만든 문서는 안 바뀐다.** 이것이 「템플릿」과 「공유
서식」을 가르는 선이고, 사용자가 명시적으로 요구한 것이다. 지키는 방법은 코드가 아니라
스키마다 — `documents` 에 `template_id` 가 없어서 따라갈 참조 자체가 없다. 그래서 이
시험은 「참조가 없다」를 주장하지 않고 **본문이 안 변했다**를 잰다.

## 「빈 문서」는 표에 없다

그것은 화면의 바탕이지 어휘가 아니다. 표에 넣으면 지울 수 있게 되고, 지워진 날 새 문서
대화상자의 기본값이 없는 틀을 가리킨다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "kt-me@goodmit.co.kr"

_BODY = {
    "type": "doc",
    "content": [
        {"type": "heading", "attrs": {"level": 2},
         "content": [{"type": "text", "text": "점검 항목"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "무엇을 보는지 적습니다."}]},
    ],
}


@pytest.fixture()
def space(db, make_user):
    from app.knowledge.models import KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    make_user(ME, role="admin", display_name="나")
    row = KnowledgeSpace(name="틀 공간", slug="kt-space", owner_kind="organization",
                         org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.commit()
    return row.id


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=ME)}


def _catalog(client, hdr):
    r = client.get("/api/knowledge/templates", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_the_seeded_templates_are_rows_and_blank_is_not(client, login_as, space):
    """0027 이 시드한 셋은 고칠 수 있는 행이고, 「빈 문서」만 상수다."""
    hdr = _hdr(login_as)
    items = _catalog(client, hdr)
    by_name = {i["name"]: i for i in items}
    assert {"빈 문서", "회의록", "요구사항 정의서", "운영 가이드"} <= set(by_name)
    assert by_name["빈 문서"]["builtin"] is True
    assert by_name["회의록"]["builtin"] is False

    # 「빈 문서」는 열 수도 없다 — 404 가 아니라 422 다. 404 는 「고장」으로 읽힌다.
    assert client.get("/api/knowledge/templates/blank", headers=hdr).status_code == 422


def test_add_edit_delete_round_trip(client, login_as, space):
    """목록 · 추가 · 수정 · 삭제 넷이 실제로 도는가 (인수 조건 8)."""
    hdr = _hdr(login_as)

    made = client.post("/api/knowledge/templates", headers=hdr, json={
        "name": "장애 보고서", "help": "무엇이 언제 왜 멈췄는지 적습니다.", "body": _BODY,
    })
    assert made.status_code == 200, made.text
    template_id = made.json()["id"]
    assert made.json()["name"] == "장애 보고서"

    assert "장애 보고서" in {i["name"] for i in _catalog(client, hdr)}

    # 같은 이름을 두 번 만들 수 없다 — 고르는 자리에 같은 이름 둘이 서면 못 고른다.
    dup = client.post("/api/knowledge/templates", headers=hdr, json={"name": "장애 보고서"})
    assert dup.status_code == 409, dup.text

    fetched = client.get(f"/api/knowledge/templates/{template_id}", headers=hdr)
    assert fetched.status_code == 200
    assert fetched.json()["body"]["content"][0]["content"][0]["text"] == "점검 항목"

    edited = client.patch(f"/api/knowledge/templates/{template_id}", headers=hdr,
                          json={"name": "장애 보고서 v2"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "장애 보고서 v2"
    # 이름만 보냈으므로 본문과 설명은 그대로다 — 「안 보냈다」와 「지운다」는 다른 말이다.
    assert edited.json()["help"] == "무엇이 언제 왜 멈췄는지 적습니다."
    assert edited.json()["body"]["content"][0]["content"][0]["text"] == "점검 항목"

    gone = client.delete(f"/api/knowledge/templates/{template_id}", headers=hdr)
    assert gone.status_code == 200, gone.text
    assert "장애 보고서 v2" not in {i["name"] for i in _catalog(client, hdr)}
    assert client.get(f"/api/knowledge/templates/{template_id}", headers=hdr).status_code == 404


def test_editing_or_deleting_a_template_never_touches_documents_made_from_it(
    client, login_as, space
):
    """🔴 이 파일이 있는 이유. 틀은 **출발점**이지 문서의 주인이 아니다.

    참조가 없으니 따라갈 길도 없다는 것을 「본문이 그대로다」로 잰다 — 구조를 주장하지
    않고 사용자가 보는 것을 잰다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/templates", headers=hdr, json={
        "name": "주간 보고", "help": "한 주를 적습니다.", "body": _BODY,
    })
    template_id = made.json()["id"]

    doc = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": space, "title": "9월 첫째 주", "template": template_id,
    })
    assert doc.status_code == 200, doc.text
    document_id = doc.json()["id"]

    def _body_of(doc_id):
        r = client.get(f"/api/knowledge/documents/{doc_id}", headers=hdr)
        assert r.status_code == 200, r.text
        # 본문은 **현재 판**(`current`) 아래 있다 — 문서 행에는 본문 칸이 없다(D-198).
        return r.json()["current"]["body"]

    before = _body_of(document_id)
    assert "점검 항목" in str(before)

    # 틀을 통째로 다른 내용으로 바꾼다.
    client.patch(f"/api/knowledge/templates/{template_id}", headers=hdr, json={
        "name": "주간 보고", "help": "",
        "body": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "완전히 다른 글"}]},
        ]},
    })
    assert _body_of(document_id) == before

    # 그리고 지운다.
    assert client.delete(f"/api/knowledge/templates/{template_id}",
                         headers=hdr).status_code == 200
    assert _body_of(document_id) == before
    assert "완전히 다른 글" not in str(_body_of(document_id))


def test_an_unknown_template_still_creates_the_document(client, login_as, space):
    """모르는 틀 이름은 **거절하지 않는다.**

    거절하면 틀을 하나 지운 날, 그 이름을 들고 온 요청이 문서 생성 자체를 못 하게 되고
    사용자는 자기가 쓴 제목까지 잃는다. 빈 문서로 시작하는 것은 잃는 것이 없다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/documents", headers=hdr, json={
        "space_id": space, "title": "이름 없는 틀", "template": "no-such-template-id",
    })
    assert made.status_code == 200, made.text


def test_the_template_body_goes_through_the_document_block_check(client, login_as, space):
    """본문은 문서와 **같은 함수**로 검사된다 — 이 표가 저장 XSS 의 입구가 되지 않게.

    `blocks.normalize` 는 모르는 노드를 **지우지 않고 거절한다.** 조용히 지우면 사용자는
    자기가 넣은 것이 왜 없어졌는지 모르고, 그 침묵은 「통과했다」와 구별되지 않는다.
    거절은 422 다 — 500 이면 화면에 「알 수 없는 오류」만 뜬다.
    """
    hdr = _hdr(login_as)
    made = client.post("/api/knowledge/templates", headers=hdr, json={
        "name": "정규화 검사",
        "body": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "정상"}]},
            {"type": "script", "content": [{"type": "text", "text": "alert(1)"}]},
        ]},
    })
    assert made.status_code == 422, made.text
    assert "정규화 검사" not in {i["name"] for i in _catalog(client, hdr)}

    # 고칠 때도 같은 문을 지난다 — 만들 때만 검사하면 두 번째 저장이 우회로가 된다.
    ok = client.post("/api/knowledge/templates", headers=hdr,
                     json={"name": "정규화 검사", "body": _BODY})
    assert ok.status_code == 200, ok.text
    bad = client.patch(f"/api/knowledge/templates/{ok.json()['id']}", headers=hdr, json={
        "body": {"type": "doc", "content": [{"type": "script"}]},
    })
    assert bad.status_code == 422, bad.text
