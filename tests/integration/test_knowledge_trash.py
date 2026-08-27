"""문서 휴지통 — 버린 문서를 **되살릴 수 있는가** (지시 22.7).

## 무엇이 없었나

문서 삭제는 `documents.archived` 를 세우는 일이고 그것 자체는 옳다 — 행을 지우면 판·멘션·
관계가 CASCADE 로 함께 사라진다. 문제는 그 뒤였다: 보관된 문서를 보여 주는 화면도, 다시
내리는 API 도 없었다. 화면의 「휴지통」 버튼은 옛 Notion 미러의 것이라 Native 문서는 애초에
거기 안 들어간다. 즉 **문서 삭제는 되돌릴 수 없었고, 사용자에게는 그냥 사라진 것이었다.**

## 여기서 보는 것

  1. 버린 문서가 **공용 휴지통 목록에** 뜬다 (티켓과 한 목록).
  2. 되살리면 목록으로 돌아오고 휴지통에서 빠진다. 판·태그가 그대로다.
  3. 되살리기가 **색인을 다시 건다** — 보관 중에는 검색·AI 후보에서 빠져 있었다.
  4. 영구 삭제는 **휴지통에 있는 문서만** 지난다.
  5. 남의 문서를 남이 되살리지 못한다 — 공용 휴지통과 같은 규칙이다.
  6. 범위 밖 문서는 휴지통에도 안 보이고 id 로도 못 건드린다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "kt-me@goodmit.co.kr"
MATE = "kt-mate@goodmit.co.kr"
OUTSIDER = "kt-out@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="휴지통팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의 휴지통팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    # 문서를 버릴 수 있는 사람은 운영자군뿐이다(`DOCUMENT_DELETE` = MODERATOR_ROLES).
    # 관리자는 **자기 부서로 좁힌다** — 안 좁히면 「범위 밖은 404」를 이 시험이 못 본다.
    me = make_user(ME, role="admin", display_name="나")
    me.admin_scope = "dept"
    me.scope_dept_id = mine.id
    # 같은 부서의 일반 사용자. 문서는 보이지만 버릴 수는 없다.
    mate = make_user(MATE, role="user", display_name="동료")
    outsider = make_user(OUTSIDER, role="admin", display_name="남")
    outsider.admin_scope = "dept"
    outsider.scope_dept_id = theirs.id
    me.department_id = mine.id
    mate.department_id = mine.id
    outsider.department_id = theirs.id

    ours = KnowledgeSpace(name="우리 공간", slug="kt-ours", owner_kind="department",
                          owner_dept_id=mine.id, org_id=DEFAULT_ORG_ID)
    others = KnowledgeSpace(name="남의 공간", slug="kt-theirs", owner_kind="department",
                            owner_dept_id=theirs.id, org_id=DEFAULT_ORG_ID)
    db.add_all([ours, others])
    db.flush()

    one = Document(space_id=ours.id, title="버릴 문서", created_by=me.id)
    keep = Document(space_id=ours.id, title="남길 문서", created_by=me.id)
    hidden = Document(space_id=others.id, title="남의 문서", created_by=outsider.id)
    db.add_all([one, keep, hidden])
    db.commit()
    return {"space": ours.id, "one": one.id, "keep": keep.id, "hidden": hidden.id}


def _hdr(login_as, email=ME, role="admin"):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _titles(client, hdr):
    r = client.get("/api/knowledge/documents", headers=hdr)
    assert r.status_code == 200, r.text
    return [d["title"] for d in r.json()["items"]]


def _trash(client, hdr):
    r = client.get("/api/trash", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ── 버리고 되살리기 ──────────────────────────────────────────────────────────


def test_a_deleted_document_shows_up_in_the_shared_trash(client, login_as, world):
    """🔴 예전에는 여기가 비어 있었다 — 버린 문서를 찾을 자리가 없었다."""
    hdr = _hdr(login_as)
    assert client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr).status_code == 200

    rows = [r for r in _trash(client, hdr) if r["title"] == "버릴 문서"]
    assert len(rows) == 1, "버린 문서가 휴지통에 없다"
    row = rows[0]
    assert row["item_type"] == "document"
    assert row["source"] == "knowledge", "옛 미러 항목과 구별되지 않는다"
    assert row["deleted_by"] == "나", "누가 버렸는지 안 적혀 있다"
    assert row["deleted_at"], "언제 버렸는지 안 적혀 있다"
    assert row["purge_after"] > row["deleted_at"], "삭제 예정이 삭제일보다 앞이다"
    assert row["space"] == "우리 공간", "어느 공간의 문서인지 안 보인다"
    assert row["can_manage"] is True


def test_restoring_brings_the_document_back_with_its_history(client, login_as, world, db):
    """되살리기는 새 문서를 만드는 것이 아니다 — **같은 문서**가 돌아온다."""
    from app.knowledge.models import Document, DocumentVersion
    from sqlalchemy import func, select

    hdr = _hdr(login_as)
    save = client.put(
        f"/api/knowledge/documents/{world['one']}",
        headers=hdr,
        json={"body": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "본문 한 줄"}]}]}},
    )
    assert save.status_code == 200, save.text
    before = db.execute(
        select(func.count()).select_from(DocumentVersion)
        .where(DocumentVersion.document_id == world["one"])
    ).scalar_one()

    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)
    assert "버릴 문서" not in _titles(client, hdr)

    back = client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=hdr)
    assert back.status_code == 200, back.text
    assert back.json()["archived"] is False

    assert "버릴 문서" in _titles(client, hdr)
    assert [r for r in _trash(client, hdr) if r["title"] == "버릴 문서"] == []

    db.expire_all()
    document = db.get(Document, world["one"])
    assert document.archived_at is None and document.archived_by is None, (
        "되살린 문서에 옛 삭제 흔적이 남았다 — 다음에 그 값을 읽는 코드가 「버려졌다」로 읽는다"
    )
    after = db.execute(
        select(func.count()).select_from(DocumentVersion)
        .where(DocumentVersion.document_id == world["one"])
    ).scalar_one()
    assert after == before, "되살리면서 판이 늘거나 줄었다"


def test_restoring_queues_the_document_for_indexing(client, login_as, world, db):
    """🔴 보관 중에는 검색과 AI 후보에서 빠져 있었다(`indexer._document_rows` ·
    `ai/retrieval/service`). 되살리면서 신호를 안 걸면 그 문서는 **되살아난 뒤에도 안
    찾아진다** — 화면에는 멀쩡히 있는데 검색만 모른다."""
    from app.ai.models import STATE_PENDING, AiIndexState
    from sqlalchemy import select

    hdr = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)
    # 보관 상태에서 색인이 끝난 척해 둔다 — 그래야 되살리기가 다시 걸었는지 보인다.
    state = db.execute(
        select(AiIndexState).where(AiIndexState.document_id == world["one"])
    ).scalar_one_or_none()
    if state is None:
        state = AiIndexState(document_id=world["one"], status="ok")
        db.add(state)
    else:
        state.status = "ok"
    db.commit()

    client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=hdr)
    db.expire_all()
    again = db.execute(
        select(AiIndexState).where(AiIndexState.document_id == world["one"])
    ).scalar_one()
    assert again.status == STATE_PENDING, "되살린 문서를 다시 색인하라는 신호가 없다"


def test_restoring_twice_is_not_an_error(client, login_as, world):
    """목록을 열어 둔 사이에 누가 먼저 되살렸을 수 있다. 그것을 오류로 만들면 화면은
    「실패했습니다」라고 말하는데 사용자가 원한 상태는 이미 돼 있다."""
    hdr = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)
    first = client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=hdr)
    second = client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=hdr)
    assert first.status_code == second.status_code == 200


def test_the_trash_can_restore_a_document_through_its_own_route(client, login_as, world):
    """화면은 휴지통 하나만 보므로 그 화면의 버튼도 휴지통 주소로 간다.

    id 앞머리(`doc:`)로 갈라져 문서 도메인의 같은 함수를 지난다 — 쓰기 절차가 두 벌이 되면
    한쪽만 색인을 다시 걸게 된다.
    """
    hdr = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)
    row = next(r for r in _trash(client, hdr) if r["title"] == "버릴 문서")
    assert row["id"] == f"doc:{world['one']}"

    done = client.post(f"/api/trash/{row['id']}/restore", headers=hdr)
    assert done.status_code == 200, done.text
    assert "버릴 문서" in _titles(client, hdr)


# ── 영구 삭제 ────────────────────────────────────────────────────────────────


def test_a_live_document_cannot_be_purged(client, login_as, world):
    """🔴 영구 삭제는 **휴지통을 거쳐야** 한다.

    살아 있는 문서를 이 문으로 지울 수 있으면 「삭제」 한 번의 실수가 판·관계·댓글까지
    되돌릴 수 없이 지운다.
    """
    hdr = _hdr(login_as)
    r = client.post(f"/api/knowledge/documents/{world['keep']}/purge", headers=hdr)
    assert r.status_code == 422, r.text
    assert "휴지통" in r.json()["error"]["message"], "왜 막혔는지 화면이 말할 수 없다"


def test_purging_removes_the_row_and_everything_hanging_off_it(client, login_as, world, db):
    """영구 삭제는 행을 지운다 — 그래서 판도 함께 사라진다(CASCADE). 첨부의 **파일 자체**는
    남는다(지시 22.3): 지우는 것은 문서와 파일을 잇는 줄뿐이다."""
    from app.knowledge.models import Document, DocumentVersion
    from sqlalchemy import func, select

    hdr = _hdr(login_as)
    client.put(f"/api/knowledge/documents/{world['one']}", headers=hdr,
               json={"body": {"type": "doc", "content": [
                   {"type": "paragraph", "content": [{"type": "text", "text": "한 줄"}]}]}})
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)

    gone = client.post(f"/api/knowledge/documents/{world['one']}/purge", headers=hdr)
    assert gone.status_code == 200, gone.text

    db.expire_all()
    assert db.get(Document, world["one"]) is None
    left = db.execute(
        select(func.count()).select_from(DocumentVersion)
        .where(DocumentVersion.document_id == world["one"])
    ).scalar_one()
    assert left == 0, "문서를 지웠는데 판이 남았다"
    assert client.get(f"/api/knowledge/documents/{world['one']}", headers=hdr).status_code == 404


# ── 권한과 범위 ──────────────────────────────────────────────────────────────


def test_someone_who_cannot_delete_cannot_restore_either(client, login_as, world):
    """되살리기와 버리기는 **한 쌍**이라 같은 권한을 쓴다 (`DOCUMENT_DELETE`).

    되살리기를 더 넓게 열면 버릴 수 없는 사람이 남이 버린 문서를 되돌릴 수 있다 —
    그것은 「보이지 않게 해 달라」는 결정을 남이 뒤집는 일이다. 이 사람은 같은 부서라
    문서 자체는 보인다: 막히는 것은 **동작**이지 범위가 아니다.
    """
    mine = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=mine)

    plain = _hdr(login_as, email=MATE, role="user")
    assert client.get(
        f"/api/knowledge/documents/{world['keep']}", headers=plain
    ).status_code == 200, "같은 부서 문서를 못 보고 있다 — 이 시험의 전제가 깨졌다"
    denied = client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=plain)
    assert denied.status_code == 403, denied.text
    purge = client.post(f"/api/knowledge/documents/{world['one']}/purge", headers=plain)
    assert purge.status_code == 403, purge.text
    # 휴지통 주소로 우회해도 같다 — 문이 둘이면 하나만 잠그는 실수가 난다.
    assert client.post(
        f"/api/trash/doc:{world['one']}/restore", headers=plain
    ).status_code == 403


def test_a_moderator_can_manage_what_anyone_threw_away(client, login_as, world):
    """정리 권한이다 — 버린 사람이 자리를 비운 사이에도 휴지통이 관리돼야 한다."""
    mine = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=mine)

    ops = _hdr(login_as, email="kt-ops@goodmit.co.kr", role="operator")
    back = client.post(f"/api/knowledge/documents/{world['one']}/restore", headers=ops)
    assert back.status_code == 200, back.text


def test_a_document_outside_my_scope_is_not_in_my_trash(client, login_as, world, db):
    """🔴 휴지통이 자기 규칙을 가지면 목록에서 가린 문서가 여기서 보인다.

    범위 밖은 **404** 다 — 403 은 그 문서가 존재한다는 사실을 알려 준다.
    """
    from app.knowledge.models import Document

    document = db.get(Document, world["hidden"])
    document.archived = True
    db.commit()

    hdr = _hdr(login_as)
    assert [r for r in _trash(client, hdr) if r["title"] == "남의 문서"] == []
    r = client.post(f"/api/knowledge/documents/{world['hidden']}/restore", headers=hdr)
    assert r.status_code == 404, r.text
    assert client.post(
        f"/api/trash/doc:{world['hidden']}/restore", headers=hdr
    ).status_code == 404


def test_the_trash_still_lists_tickets(client, login_as, world):
    """문서를 얹으면서 티켓이 밀려나면 안 된다 — 지시는 「공통 목록」이라고 적었다.

    티켓이 하나도 없는 설치에서도 이 시험은 뜻이 있다: 응답 모양(`total`·`items`)이 그대로인지
    본다. 문서 몫을 더하면서 두 수가 어긋나면 화면의 「몇 건 중 어디쯤」이 조용히 틀린다.
    """
    hdr = _hdr(login_as)
    client.delete(f"/api/knowledge/documents/{world['one']}", headers=hdr)
    body = client.get("/api/trash", headers=hdr).json()
    assert body["total"] >= len(body["items"])
    assert body["retention_days"] >= 1
    assert all({"id", "item_type", "title", "can_manage"} <= set(r) for r in body["items"])
