"""판 · 차이 · 되돌리기 — **S7 의 Exit 조건**을 실제 요청으로 확인한다 (D-198).

MASTER_PLAN §9.1 의 S7 Exit 는 「Version diff/restore 동작」이다. 여기서 보는 것은
그 한 줄이 실제로 무슨 뜻인가다:

1. 저장할 때마다 판이 쌓이고, **안 바뀌었으면 안 쌓인다**
2. 차이가 **블록 단위**로 나온다 — 줄바꿈만 바뀐 판이 전면 수정으로 안 보인다
3. 되돌리기가 **이력을 지우지 않고 새 판을 쌓는다**
4. 되돌리기가 **남의 저장을 조용히 덮지 않는다** (낙관적 잠금, D-240)

## 그리고 옛 상한이 정말 사라졌는지 본다

옛 코드는 본문 100줄·한 줄 1900자를 넘으면 저장 자체를 거절했다. 그 두 수는 Notion API
한 번 요청의 상한이지 이 제품의 규칙이 아니었다 — 회의록 하나가 그 줄 수를 넘으면
저장이 안 됐다. D-198 이 그것을 없애라고 했고, 없앴는지는 **실제 요청**으로만 알 수 있다.
"""

from __future__ import annotations

import pytest

from app.core.notion_blocks import MAX_BLOCKS, MAX_LINE_CHARS

pytestmark = pytest.mark.integration

AUTHOR = "knowledge-versions@goodmit.co.kr"


def _doc(*paragraphs):
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            for text in paragraphs
        ],
    }


@pytest.fixture()
def api(client, login_as):
    """`admin` 은 `SPACE_ADMIN` 을 갖는다(0002 시드) — 공간을 만들 수 있다."""
    token = login_as("admin", email=AUTHOR)
    headers = {"X-CSRF-Token": token}

    class Api:
        def get(self, path, **kw):
            return client.get(path, headers=headers, **kw)

        def post(self, path, json=None):
            return client.post(path, json=json or {}, headers=headers)

        def put(self, path, json=None):
            return client.put(path, json=json or {}, headers=headers)

    return Api()


@pytest.fixture()
def document(api):
    space = api.post("/api/knowledge/spaces", {
        "name": "설계", "slug": "design", "owner_kind": "organization",
    })
    assert space.status_code == 200, space.text
    made = api.post("/api/knowledge/documents", {
        "space_id": space.json()["id"], "title": "회의록", "body": _doc("가", "나"),
    })
    assert made.status_code == 200, made.text
    return made.json()


# ── 판이 쌓인다 ──────────────────────────────────────────────────────────────


def test_creating_a_document_makes_the_first_version(api, document):
    body = api.get(f"/api/knowledge/documents/{document['id']}/versions").json()
    assert [v["version_no"] for v in body["items"]] == [1]
    assert body["current_version_no"] == 1


def test_saving_new_body_stacks_a_version(api, document):
    r = api.put(f"/api/knowledge/documents/{document['id']}", {
        "body": _doc("가", "나 고침"), "change_reason": "오타 수정",
    })
    assert r.status_code == 200, r.text
    assert r.json()["created_version"] is True

    body = api.get(f"/api/knowledge/documents/{document['id']}/versions").json()
    assert [v["version_no"] for v in body["items"]] == [2, 1]
    assert body["items"][0]["change_reason"] == "오타 수정"


def test_saving_the_same_body_does_not_stack_a_version(api, document):
    """편집기는 커서만 움직여도 저장을 부른다. 그때마다 판이 쌓이면 이력 화면이
    「변경 없음」 수백 줄이 되고, 그 안에서 실제 변경을 못 찾는다."""
    r = api.put(f"/api/knowledge/documents/{document['id']}", {"body": _doc("가", "나")})
    assert r.status_code == 200, r.text
    assert r.json()["created_version"] is False

    body = api.get(f"/api/knowledge/documents/{document['id']}/versions").json()
    assert [v["version_no"] for v in body["items"]] == [1]


def test_saving_only_the_title_still_saves(api, document):
    """본문이 안 바뀌어도 제목은 저장된다 — 「저장했는데 아무 일도 안 일어났다」가 되면 안 된다."""
    r = api.put(f"/api/knowledge/documents/{document['id']}", {"title": "주간 회의록"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "주간 회의록"
    assert r.json()["created_version"] is False


# ── 차이는 블록 단위다 ──────────────────────────────────────────────────────


def test_diff_reports_the_edited_paragraph_only(api, document):
    api.put(f"/api/knowledge/documents/{document['id']}", {"body": _doc("가", "나 고침")})
    body = api.get(
        f"/api/knowledge/documents/{document['id']}/diff?base=1&target=2"
    ).json()
    changes = body["changes"]
    assert [c["change"] for c in changes] == ["changed"], changes
    assert changes[0]["before"] == "나"
    assert changes[0]["after"] == "나 고침"


def test_diff_of_a_version_with_itself_is_empty(api, document):
    body = api.get(
        f"/api/knowledge/documents/{document['id']}/diff?base=1&target=1"
    ).json()
    assert body["changes"] == []


def test_diff_of_a_missing_version_is_404(api, document):
    r = api.get(f"/api/knowledge/documents/{document['id']}/diff?base=1&target=99")
    assert r.status_code == 404, r.text


# ── 되돌리기는 쌓는 것이다 ──────────────────────────────────────────────────


def test_restore_stacks_a_new_version_and_keeps_the_history(api, document):
    doc_id = document["id"]
    api.put(f"/api/knowledge/documents/{doc_id}", {"body": _doc("가", "나 고침")})
    api.put(f"/api/knowledge/documents/{doc_id}", {"body": _doc("가", "나 또 고침")})

    r = api.post(f"/api/knowledge/documents/{doc_id}/versions/1/restore")
    assert r.status_code == 200, r.text

    history = api.get(f"/api/knowledge/documents/{doc_id}/versions").json()
    assert [v["version_no"] for v in history["items"]] == [4, 3, 2, 1], (
        "되돌리기가 이력을 잘라 냈다 — 「누가 언제 무엇을 되돌렸는가」가 사라진다"
    )
    assert history["current_version_no"] == 4
    assert history["items"][0]["source"] == "RESTORE"


def test_restore_actually_brings_the_old_body_back(api, document):
    doc_id = document["id"]
    api.put(f"/api/knowledge/documents/{doc_id}", {"body": _doc("완전히 다른 글")})
    api.post(f"/api/knowledge/documents/{doc_id}/versions/1/restore")

    current = api.get(f"/api/knowledge/documents/{doc_id}").json()["current"]
    texts = [
        node["content"][0]["text"] for node in current["body"]["content"]
    ]
    assert texts == ["가", "나"], f"옛 본문이 안 돌아왔다: {texts}"


def test_restoring_the_version_you_are_already_on_is_a_conflict(api, document):
    r = api.post(f"/api/knowledge/documents/{document['id']}/versions/1/restore")
    assert r.status_code == 409, r.text


def test_restore_refuses_when_someone_saved_after_you_looked(api, document):
    """되돌리기는 남의 편집을 통째로 덮는 동작이라, 「내가 이력을 본 뒤 누군가
    저장했다」를 반드시 잡아야 한다 — 안 잡으면 방금 쓴 문단이 조용히 사라진다."""
    doc_id = document["id"]
    stale = document["version"]
    api.put(f"/api/knowledge/documents/{doc_id}", {"body": _doc("다른 사람이 쓴 글")})

    r = api.post(
        f"/api/knowledge/documents/{doc_id}/versions/1/restore", {"base_version": stale}
    )
    assert r.status_code == 409, r.text


def test_restore_with_the_current_lock_value_succeeds(api, document):
    """반대편 — 여기서 실패하면 위 시험은 「전부 거절하는 구현」도 통과시킨다."""
    doc_id = document["id"]
    saved = api.put(f"/api/knowledge/documents/{doc_id}", {"body": _doc("바뀐 글")}).json()
    r = api.post(
        f"/api/knowledge/documents/{doc_id}/versions/1/restore",
        {"base_version": saved["version"]},
    )
    assert r.status_code == 200, r.text


# ── 옛 길이 상한은 사라졌다 (D-198) ─────────────────────────────────────────


def test_a_body_longer_than_the_old_block_limit_is_accepted(api, document):
    assert MAX_BLOCKS == 100, "옛 상한 값이 바뀌었다 — 이 시험의 전제를 다시 봐야 한다"
    long_body = _doc(*[f"{i}번째 줄" for i in range(MAX_BLOCKS * 3)])
    r = api.put(f"/api/knowledge/documents/{document['id']}", {"body": long_body})
    assert r.status_code == 200, r.text
    current = api.get(f"/api/knowledge/documents/{document['id']}").json()["current"]
    assert len(current["body"]["content"]) == MAX_BLOCKS * 3


def test_a_line_longer_than_the_old_line_limit_is_accepted(api, document):
    assert MAX_LINE_CHARS == 1900, "옛 상한 값이 바뀌었다 — 전제를 다시 봐야 한다"
    long_line = "가" * (MAX_LINE_CHARS * 2)
    r = api.put(f"/api/knowledge/documents/{document['id']}", {"body": _doc(long_line)})
    assert r.status_code == 200, r.text
    current = api.get(f"/api/knowledge/documents/{document['id']}").json()["current"]
    assert current["body"]["content"][0]["content"][0]["text"] == long_line


# ── 모양은 여전히 거절한다 ──────────────────────────────────────────────────


def test_an_unknown_node_type_is_rejected_with_422(api, document):
    """길이는 안 막지만 모양은 막는다. 통과시키면 편집기가 못 그리는 값이 DB 에 들어가고
    그 문서는 열 때마다 빈 화면이 된다."""
    r = api.put(f"/api/knowledge/documents/{document['id']}", {
        "body": {"type": "doc", "content": [{"type": "iframe", "attrs": {"src": "http://x"}}]},
    })
    assert r.status_code == 422, r.text


def test_a_javascript_link_loses_its_mark_but_the_words_stay(api, document):
    r = api.put(f"/api/knowledge/documents/{document['id']}", {
        "body": {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "눌러",
             "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}]},
        ]}]},
    })
    assert r.status_code == 200, r.text
    current = api.get(f"/api/knowledge/documents/{document['id']}").json()["current"]
    node = current["body"]["content"][0]["content"][0]
    assert node["text"] == "눌러"
    assert "marks" not in node, "위험한 링크가 저장됐다"
