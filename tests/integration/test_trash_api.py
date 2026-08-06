"""휴지통 — 이동/복원/권한/만료정리 + API 목록·복원.

노션 호출(archive)은 만료 정리에서만 나므로 그 부분은 _archive_notion 을 모킹해 격리한다.
이동/복원/권한/필터는 순수 로컬 DB 로직이라 노션 없이 검증한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConflictError, ForbiddenError
from app.trash import repository, service
from app.trash.models import TRASH_DOCUMENT, TRASH_TICKET
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def test_move_restore_and_duplicate(db, make_user):
    u = make_user(email="tr1@goodmit.co.kr", display_name="휴지하나")
    now = datetime(2026, 7, 29, 0, 0, 0)
    item = service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="pg-1",
                                 title="티켓제목", url="https://notion/x", user=u, now=now)
    assert repository.get_by_page(db, TRASH_TICKET, "pg-1") is not None
    assert repository.trashed_page_ids(db, TRASH_TICKET) == {"pg-1"}
    # 같은 페이지 두 번 넣기 → 충돌.
    with pytest.raises(ConflictError):
        service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="pg-1",
                              title="티켓제목", url=None, user=u, now=now)
    # 복원 → 목록에서 사라진다(노션 무손상이라 원래 목록으로 복귀).
    service.restore(db, item, u)
    assert repository.get_by_page(db, TRASH_TICKET, "pg-1") is None


def test_manage_permission(db, make_user):
    owner = make_user(email="own@goodmit.co.kr", display_name="주인", role="user")
    other = make_user(email="oth@goodmit.co.kr", display_name="남", role="user")
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    item = service.move_to_trash(db, item_type=TRASH_DOCUMENT, notion_page_id="d-1",
                                 title="문서", url=None, user=owner, now=datetime(2026, 7, 29))
    # 셋 다 부서가 없다 → 범위는 안 좁혀진다(폴백). 여기서 보는 것은 **권한 축**이다.
    service.ensure_can_manage(db, owner, item)  # 버린 본인 OK
    service.ensure_can_manage(db, op, item)     # 운영자 OK
    with pytest.raises(ForbiddenError):
        service.ensure_can_manage(db, other, item)  # 남은 불가


def test_purge_expired_skips_recent(db, make_user, monkeypatch):
    archived: list[str] = []
    monkeypatch.setattr(service, "_archive_notion",
                        lambda item, *, outbound, settings: archived.append(item.notion_page_id))
    u = make_user(email="pex@goodmit.co.kr", display_name="정리")
    base = datetime(2026, 7, 29, 0, 0, 0)
    service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="old",
                          title="오래됨", url=None, user=u, now=base - timedelta(days=10))
    service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="fresh",
                          title="최근", url=None, user=u, now=base - timedelta(days=1))
    res = service.purge_expired(db, now=base, retention_days=7, outbound=object(), settings=object())
    assert res["purged"] == 1 and archived == ["old"]  # 10일 지난 것만 보관처리·삭제
    assert repository.get_by_page(db, TRASH_TICKET, "old") is None
    assert repository.get_by_page(db, TRASH_TICKET, "fresh") is not None  # 1일 된 것은 유지


def test_purge_expired_isolates_notion_failure(db, make_user, monkeypatch):
    def boom(item, *, outbound, settings):
        raise RuntimeError("notion down")

    monkeypatch.setattr(service, "_archive_notion", boom)
    u = make_user(email="pfail@goodmit.co.kr", display_name="실패")
    base = datetime(2026, 7, 29)
    service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="x",
                          title="t", url=None, user=u, now=base - timedelta(days=30))
    res = service.purge_expired(db, now=base, retention_days=7, outbound=object(), settings=object())
    # 노션 실패는 격리 — 행은 남아 다음 주기에 재시도(무한 손실 방지).
    assert res["failed"] == 1 and res["purged"] == 0
    assert repository.get_by_page(db, TRASH_TICKET, "x") is not None


def test_bulk_trash_documents(db, make_user):
    """문서 일괄 삭제 — 존재하는 것은 휴지통으로, 없는 것은 실패로 분리(부분 성공)."""
    from app.team_docs import service as docsvc
    from app.team_docs.models import DocumentCache

    op = make_user(email="bulkop@goodmit.co.kr", display_name="운영자", role="operator")
    db.add(DocumentCache(notion_page_id="bd-1", title="문서1"))
    db.add(DocumentCache(notion_page_id="bd-2", title="문서2"))
    db.flush()
    res = docsvc.trash_documents_bulk(db, user=op, page_ids=["bd-1", "bd-2", "missing"],
                                      now=datetime(2026, 7, 29))
    assert len(res["trashed"]) == 2 and len(res["failed"]) == 1  # 없는 것은 실패로
    assert repository.trashed_page_ids(db, TRASH_DOCUMENT) == {"bd-1", "bd-2"}


def test_bulk_restore_and_purge(db, make_user, monkeypatch):
    """일괄 복원/영구삭제 — 복원은 노션 무손상, 영구삭제는 노션 보관처리 후 제거. 없는 id는 실패로."""
    archived: list[str] = []
    monkeypatch.setattr(service, "_archive_notion",
                        lambda item, *, outbound, settings: archived.append(item.notion_page_id))
    u = make_user(email="tbulk@goodmit.co.kr", display_name="벌크")
    now = datetime(2026, 7, 29)
    a = service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="a", title="A", url=None, user=u, now=now)
    b = service.move_to_trash(db, item_type=TRASH_DOCUMENT, notion_page_id="b", title="B", url=None, user=u, now=now)
    res = service.restore_bulk(db, [a.id, "missing"], u)
    assert len(res["restored"]) == 1 and len(res["failed"]) == 1
    assert repository.get_by_page(db, TRASH_TICKET, "a") is None
    res2 = service.purge_bulk(db, [b.id], u, outbound=object(), settings=object())
    assert len(res2["purged"]) == 1 and archived == ["b"]
    assert repository.get_by_page(db, TRASH_DOCUMENT, "b") is None


def _login(app, email):
    make = TestClient(app, raise_server_exceptions=False)
    make.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return make, make.get("/api/me").json()["csrf_token"]


def test_trash_list_and_restore_api(app, db, make_user):
    """API: 휴지통 목록에 종류·삭제자·제목이 나오고, 버린 본인이 복원하면 사라진다."""
    u = make_user(email="apiu@goodmit.co.kr", display_name="API유저")
    service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="t-api",
                          title="API 티켓", url="https://notion/t", user=u, now=datetime(2026, 7, 29))
    db.commit()
    c, csrf = _login(app, "apiu@goodmit.co.kr")
    with c:
        body = c.get("/api/trash").json()
        assert body["retention_days"] == 7
        items = body["items"]
        assert len(items) == 1
        it = items[0]
        assert it["item_type"] == "ticket" and it["type_label"] == "티켓"
        assert it["title"] == "API 티켓" and it["deleted_by"] == "API유저" and it["can_manage"] is True
        assert it["deleted_at"] and it["purge_after"]
        # 복원.
        assert c.post(f"/api/trash/{it['id']}/restore", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert c.get("/api/trash").json()["items"] == []


def test_trash_restore_requires_permission(app, db, make_user):
    owner = make_user(email="towner@goodmit.co.kr", display_name="주인")
    make_user(email="tnobody@goodmit.co.kr", display_name="무권한")
    item = service.move_to_trash(db, item_type=TRASH_DOCUMENT, notion_page_id="d-perm",
                                 title="문서", url=None, user=owner, now=datetime(2026, 7, 29))
    db.commit()
    c, csrf = _login(app, "tnobody@goodmit.co.kr")
    with c:
        # 남이 버린 항목은 일반 사용자가 복원 못 한다(403).
        assert c.post(f"/api/trash/{item.id}/restore", headers={"X-CSRF-Token": csrf}).status_code == 403
