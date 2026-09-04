"""휴지통에 있는 문서는 **읽을 수는 있고 고칠 수는 없다**.

## 무엇이 뚫려 있었나

문서 삭제는 `documents.archived` 를 세우는 일인데 **어떤 쓰기 경로도 그 값을 안 봤다.**
`save_document` 는 범위와 잠금만 보고(`app/knowledge/service.py`), `DOCUMENT_UPDATE` 는
EVERYONE 이다. 그래서 휴지통에서 제목을 눌러 문서를 연 사람이 오타를 고치고 「저장」을
누르면 **성공 안내를 받았다.** 그 문서는 여전히 목록에 없고, 보관기간이 지나면
`purge_expired_documents` 가 판까지 통째로 하드 삭제한다 — 사람은 「저장됐다」고 들었는데
그 글은 곧 사라진다.

티켓과 옛 미러 문서는 이 구멍을 이미 막았다(H2). `app/tickets/service.py::ensure_not_trashed`
의 머리말이 같은 증상을 적고 **「게시판은 제대로 하는데 티켓·문서만 빠져 있었다」**고 썼는데,
그 회차에 티켓만 고치고 문서는 안 고쳤다.

## 읽기를 막지 않는 것이 이 파일의 절반이다

티켓은 상세 조회까지 404 로 막았다. 문서는 그러면 **안 된다** — 휴지통 화면의
「되돌릴 수 없는 영구 삭제 앞에서 무엇을 지우는지 본다」가 그 읽기 위에 서 있다.
그래서 여기서는 「쓰기는 404, 읽기는 200」을 **함께** 잰다. 한쪽만 재면 두 방향 중
어느 쪽으로 고쳐도 초록인 시험이 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "tro-me@goodmit.co.kr"

BODY = {"type": "doc", "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "휴지통에서 고친 줄"}]}]}


@pytest.fixture()
def doc(db, make_user):
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    me = make_user(ME, role="admin", display_name="나")
    space = KnowledgeSpace(name="쓰기 가드 공간", slug="tro-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    live = Document(space_id=space.id, title="살아 있는 문서", created_by=me.id)
    # 관계를 이을 짝. 없는 id 로 재면 「짝이 없다」는 404 와 「휴지통이라 막혔다」는 404 를
    # 구별할 수 없다 — 반례가 뜻을 잃는다.
    mate = Document(space_id=space.id, title="이을 문서", created_by=me.id)
    db.add_all([live, mate])
    db.commit()
    return {"id": live.id, "mate": mate.id, "space": space.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=ME)}


def _trash_it(client, hdr, document_id):
    r = client.delete(f"/api/knowledge/documents/{document_id}", headers=hdr)
    assert r.status_code == 200, r.text


# ── 쓰기는 막힌다 ────────────────────────────────────────────────────────────


def test_saving_a_trashed_document_is_refused(client, login_as, doc):
    """🔴 예전에는 200 과 「저장했습니다」가 나왔다."""
    hdr = _hdr(login_as)
    # 반례의 절반 — 버리기 **전에는** 저장이 된다. 이게 없으면 저장을 통째로 막아도 초록이다.
    before = client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr, json={"body": BODY})
    assert before.status_code == 200, before.text

    _trash_it(client, hdr, doc["id"])

    after = client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr,
                       json={"title": "휴지통에서 바꾼 제목"})
    assert after.status_code == 404, (
        f"휴지통 문서가 저장됐다({after.status_code}) — 그 글은 보관기간이 끝나면 사라진다"
    )


def test_the_refusal_does_not_write_anything(client, login_as, doc, db):
    """거절이 「거절했지만 이미 썼다」면 거절이 아니다."""
    from app.knowledge.models import Document

    hdr = _hdr(login_as)
    _trash_it(client, hdr, doc["id"])
    client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr, json={"title": "바뀐 제목"})

    db.expire_all()
    assert db.get(Document, doc["id"]).title == "살아 있는 문서"


#: 이번 회차가 `get_writable_document_or_404` 로 옮긴 **쓰기 자리 전부**.
#:
#: 표를 이렇게 넓히는 이유는 이 파일 머리말이 이미 적은 것과 같다 — 한 자리만 막으면 그
#: 자리를 안 지나는 경로가 남고, 그 경로는 아무도 안 본다. 셋만 재던 시절에는 판 되돌리기·
#: 이동·첨부 둘·댓글 수정/삭제를 되돌려도 이 파일이 초록이었다.
#: 이 회차가 `get_writable_document_or_404` 로 옮긴 쓰기 자리. `{mate}` 는 관계를 이을 짝이다.
WRITE_ROUTES = [
    ("post", "/api/knowledge/documents/{id}/comments", {"body": "휴지통 댓글"}),
    ("post", "/api/knowledge/documents/{id}/favorite", {"on": True}),
    ("post", "/api/knowledge/documents/{id}/relations",
     {"to_document_id": "{mate}", "kind": "relates_to"}),
    ("post", "/api/knowledge/documents/{id}/versions/1/restore", {}),
    ("post", "/api/knowledge/documents/{id}/move", {"project_id": None}),
]


def _fill(payload, doc):
    return {k: (doc["mate"] if v == "{mate}" else v) for k, v in payload.items()}


@pytest.mark.parametrize("method,path,payload", WRITE_ROUTES)
def test_other_write_paths_are_refused_too(client, login_as, doc, method, path, payload):
    """한 자리만 막으면 그 자리를 안 지나는 경로가 남는다 — 같은 문을 다 지나게 한다."""
    hdr = _hdr(login_as)
    # 판 되돌리기를 재려면 되돌릴 판이 있어야 한다.
    client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr, json={"body": BODY})
    _trash_it(client, hdr, doc["id"])
    r = getattr(client, method)(path.format(id=doc["id"]), headers=hdr, json=_fill(payload, doc))
    assert r.status_code == 404, f"{path} 가 휴지통 문서에 {r.status_code} 를 냈다"


@pytest.mark.parametrize("method,path,payload", WRITE_ROUTES)
def test_the_same_routes_work_before_it_is_trashed(client, login_as, doc, method, path, payload):
    """반례 — **버리기 전에는 404 가 아니다.**

    이것이 없으면 「그 경로들이 원래 404 였다」와 「가드가 막았다」를 구별할 수 없다.
    404 가 아니기만 하면 된다 — 각 경로의 나머지 계약은 각자의 시험이 잰다.
    """
    hdr = _hdr(login_as)
    client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr, json={"body": BODY})
    r = getattr(client, method)(path.format(id=doc["id"]), headers=hdr, json=_fill(payload, doc))
    assert r.status_code != 404, f"{path} 가 살아 있는 문서에도 404 다 — 가드와 무관한 실패다"


def test_attaching_a_file_is_refused_before_the_storage_layer_is_even_asked(
    client, login_as, doc
):
    """첨부 업로드도 같은 문을 지난다 — 그리고 **저장소보다 먼저** 지난다.

    이 시험 환경에는 파일 저장소가 없어서 살아 있는 문서에 올리면 503 이 난다. 그것이
    바로 반례다: 휴지통 문서에서 **404** 가 나온다면 그 404 는 저장소가 아니라 가드가
    낸 것이다. 두 코드가 같았으면 이 시험은 아무것도 증명하지 못한다.
    """
    hdr = _hdr(login_as)
    upload = {"files": {"file": ("메모.txt", b"hello", "text/plain")}}

    live = client.post(f"/api/knowledge/documents/{doc['id']}/attachments", headers=hdr, **upload)
    assert live.status_code != 404, f"살아 있는 문서에서 404 가 났다({live.status_code})"

    _trash_it(client, hdr, doc["id"])
    again = client.post(f"/api/knowledge/documents/{doc['id']}/attachments", headers=hdr, **upload)
    assert again.status_code == 404, (
        f"휴지통 문서의 첨부 업로드가 {again.status_code} 다 — 가드를 안 지났다"
    )


# ── 읽기는 열려 있다 (이 절이 없으면 위 절을 통째 차단으로 고쳐도 초록이다) ───


def test_reading_a_trashed_document_still_works_because_the_trash_preview_needs_it(
    client, login_as, doc
):
    """🔴 휴지통이 「무엇을 지우는지」를 이 읽기 위에 세운다 — 함께 막으면 안 된다."""
    hdr = _hdr(login_as)
    client.put(f"/api/knowledge/documents/{doc['id']}", headers=hdr, json={"body": BODY})
    _trash_it(client, hdr, doc["id"])

    r = client.get(f"/api/knowledge/documents/{doc['id']}", headers=hdr)
    assert r.status_code == 200, "휴지통 문서를 못 읽는다 — 지우기 전에 확인할 방법이 없어진다"
    body = r.json()
    assert body["archived"] is True, "화면이 「휴지통에 있다」고 말하려면 이 값이 필요하다"
    assert body["current"]["body"], "본문이 안 온다 — 제목만으로 영구 삭제를 결정하게 된다"


def test_restore_and_purge_still_work_on_a_trashed_document(client, login_as, doc):
    """복원·영구삭제는 **휴지통 문서에만** 하는 일이다 — 쓰기 가드가 이 둘을 막으면 안 된다."""
    hdr = _hdr(login_as)
    _trash_it(client, hdr, doc["id"])

    back = client.post(f"/api/knowledge/documents/{doc['id']}/restore", headers=hdr)
    assert back.status_code == 200, back.text

    _trash_it(client, hdr, doc["id"])
    gone = client.post(f"/api/knowledge/documents/{doc['id']}/purge", headers=hdr)
    assert gone.status_code == 200, gone.text


# ── 두 번 버려도 시계가 안 밀린다 ────────────────────────────────────────────


def test_deleting_an_already_trashed_document_does_not_reset_the_purge_clock(
    client, login_as, doc, db, fake_clock
):
    """🔴 다시 버리면 `archived_at`·`archived_by` 가 다시 찍혔다.

    그 둘은 장식이 아니다 — `archived_at` 은 **삭제 예정일의 기준**이고 `archived_by` 는
    **누가 되살릴 수 있는가**다. 다시 찍히면 아무도 안 눌렀는데 보관기간이 한 주기 뒤로
    밀리고, 원래 버린 사람이 자기 항목의 복원 권한을 잃는다. `restore_document` 는 이미
    멱등이었다 — 한쪽만 멱등인 짝은 언젠가 어긋난다.
    """
    from app.knowledge.models import Document

    hdr = _hdr(login_as)
    _trash_it(client, hdr, doc["id"])
    db.expire_all()
    first = db.get(Document, doc["id"]).archived_at
    assert first is not None

    fake_clock.advance(600)
    again = client.delete(f"/api/knowledge/documents/{doc['id']}", headers=hdr)
    assert again.status_code == 200, "두 번 버리는 것이 오류가 되면 안 된다 — 결과는 같다"

    db.expire_all()
    assert db.get(Document, doc["id"]).archived_at == first, (
        "보관 시각이 다시 찍혔다 — 그 줄의 삭제 예정일이 통째로 뒤로 밀린다"
    )
