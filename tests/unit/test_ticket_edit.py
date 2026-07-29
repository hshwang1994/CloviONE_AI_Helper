"""사용자 셀프서비스 티켓 수동 편집(쓰기) 유닛 테스트.

Notion 호출은 fake outbound 로 대체(httpx 미사용). fetch_ticket(GET page)·fetch_schema(GET db)·
update_ticket_properties(PATCH page) 세 경로를 (method, url) 로 라우팅한다. 소유권/스키마 검증/
담당자 해석·보존/claim 을 검증한다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError, ValidationAppError
from app.notion_mapping.models import STATUS_UNMAPPED, STATUS_VERIFIED, UserNotionMapping
from app.tickets import service
from app.tickets.notion_write import TicketNotFoundError

_SCHEMA = {
    "properties": {
        "제목": {"type": "title"},
        "진행상태": {"type": "status", "status": {"options": [
            {"name": "계획"}, {"name": "진행"}, {"name": "검증"},
            {"name": "이슈"}, {"name": "완료"}, {"name": "취소"},
        ]}},
        "마감일": {"type": "date"},
        "우선순위": {"type": "select", "select": {"options": [
            {"name": "높음"}, {"name": "보통"}, {"name": "낮음"},
        ]}},
        "난이도": {"type": "select", "select": {"options": [
            {"name": "보통"}, {"name": "어려움"},
        ]}},
        "예상 WD": {"type": "number"},
        "실제 WD": {"type": "number"},
        "티켓 담당자": {"type": "people"},
        "티켓 ID": {"type": "unique_id"},
    }
}


def _page(*, pid="page-1", tid=42, title="샘플", status="진행", due="2026-09-01",
          people=None, est=2.0, diff="보통", prio="보통"):
    return {
        "id": pid,
        "url": f"https://notion/{pid}",
        "properties": {
            "제목": {"title": [{"plain_text": title}]},
            "진행상태": {"status": {"name": status}},
            "마감일": {"date": {"start": due} if due else None},
            "티켓 담당자": {"people": [{"id": p} for p in (people or [])]},
            "예상 WD": {"number": est},
            "실제 WD": {"number": None},
            "난이도": {"select": {"name": diff} if diff else None},
            "우선순위": {"select": {"name": prio} if prio else None},
            "티켓 ID": {"unique_id": {"number": tid}},
        },
    }


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeOutbound:
    """(method, url) 로 라우팅. PATCH 바디는 last_patch 에 저장, current 페이지를 갱신해 되돌려준다."""

    def __init__(self, *, page, schema=_SCHEMA, page_status=200):
        self.page = page
        self.schema = schema
        self.page_status = page_status
        self.calls = []
        self.last_patch = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET" and "/v1/databases/" in url:
            return _Resp(200, self.schema)
        if method == "GET" and "/v1/pages/" in url:
            if self.page_status != 200:
                return _Resp(self.page_status, {"message": "not found"})
            return _Resp(200, self.page)
        if method == "PATCH" and "/v1/pages/" in url:
            self.last_patch = kwargs.get("json")
            # 반영된 페이지: 기존 페이지에 patch 속성을 덮어써 되돌려준다(간이).
            merged = {**self.page, "properties": {**self.page["properties"], **(self.last_patch or {}).get("properties", {})}}
            return _Resp(200, merged)
        raise AssertionError(f"unexpected {method} {url}")


def _map(db, user, notion_id, status=STATUS_VERIFIED):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=status))
    db.commit()


# ── 소유권 ──────────────────────────────────────────────────────────────────

def test_update_forbidden_when_not_owner(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-other"]))  # 남의 티켓
    with pytest.raises(ForbiddenError):
        service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"est_wd": 3.0})
    assert ob.last_patch is None  # 쓰기까지 못 감


def test_update_allowed_for_owner(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    out = service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"est_wd": 5.0})
    assert ob.last_patch["properties"]["예상 WD"] == {"number": 5.0}
    assert out["before"]["est_wd"] == 2.0


def test_update_allowed_for_unassigned(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")  # 매핑 없어도 됨
    ob = _FakeOutbound(page=_page(people=[]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"priority": "높음"})
    assert ob.last_patch["properties"]["우선순위"] == {"select": {"name": "높음"}}


def test_bypass_role_can_edit_others(db, settings, make_user):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ob = _FakeOutbound(page=_page(people=["notion-other"]))
    service.update_ticket(db, ob, settings, op, page_id="page-1", changes={"status": "완료"})
    assert ob.last_patch["properties"]["진행상태"] == {"status": {"name": "완료"}}


# ── 스키마/값 검증 ───────────────────────────────────────────────────────────

def test_no_changes_rejected(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, me, page_id="page-1", changes={})


def test_invalid_status_rejected(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"status": "없는상태"})
    assert ob.last_patch is None


def test_empty_status_rejected(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"status": ""})


def test_due_date_clear_sends_null(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"due_date": ""})
    assert ob.last_patch["properties"]["마감일"] == {"date": None}


def test_difficulty_clear_sends_null(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"difficulty": ""})
    assert ob.last_patch["properties"]["난이도"] == {"select": None}


def test_ticket_not_found(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(), page_status=404)
    with pytest.raises(TicketNotFoundError):
        service.update_ticket(db, ob, settings, me, page_id="nope", changes={"est_wd": 1.0})


# ── 담당자 해석·보존 ─────────────────────────────────────────────────────────

def test_assignee_resolved_and_external_preserved(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    mate = make_user(email="mate@goodmit.co.kr", display_name="동료", role="user")
    _map(db, me, "notion-me")
    _map(db, mate, "notion-mate")
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")  # 우회
    # 현재 담당자: 외부 미연결 + 동료(앱 사용자). 나에게 재배정 → 동료는 빠지고 외부는 보존.
    ob = _FakeOutbound(page=_page(people=["ext-unmapped", "notion-mate"]))
    service.update_ticket(db, ob, settings, op, page_id="page-1",
                          changes={"assignee_user_ids": [me.id]})
    ids = [p["id"] for p in ob.last_patch["properties"]["티켓 담당자"]["people"]]
    assert ids == ["ext-unmapped", "notion-me"]


def test_assignee_clear_keeps_external(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ob = _FakeOutbound(page=_page(people=["ext-unmapped", "notion-me"]))
    service.update_ticket(db, ob, settings, op, page_id="page-1",
                          changes={"assignee_user_ids": []})
    ids = [p["id"] for p in ob.last_patch["properties"]["티켓 담당자"]["people"]]
    assert ids == ["ext-unmapped"]  # 앱 사용자만 비우고 외부는 유지


def test_assignee_unknown_user_rejected(db, settings, make_user):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ob = _FakeOutbound(page=_page(people=[]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, op, page_id="page-1",
                              changes={"assignee_user_ids": ["no-such-user"]})


def test_assignee_unverified_user_rejected(db, settings, make_user):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ghost = make_user(email="ghost@goodmit.co.kr", display_name="유령", role="user")
    _map(db, ghost, "notion-ghost", status=STATUS_UNMAPPED)  # 미검증 → 후보 아님
    ob = _FakeOutbound(page=_page(people=[]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, op, page_id="page-1",
                              changes={"assignee_user_ids": [ghost.id]})


# ── claim ───────────────────────────────────────────────────────────────────

def test_claim_requires_mapping(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")  # 매핑 없음
    ob = _FakeOutbound(page=_page(people=[]))
    with pytest.raises(ValidationAppError):
        service.claim_ticket(db, ob, settings, me, page_id="page-1")


def test_claim_assigns_me(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=[]))
    out = service.claim_ticket(db, ob, settings, me, page_id="page-1")
    ids = [p["id"] for p in ob.last_patch["properties"]["티켓 담당자"]["people"]]
    assert ids == ["notion-me"]
    assert me.id in out["ticket"]["assignee_user_ids"] or "notion-me" in out["ticket"]["assignees"]


def test_claim_forbidden_on_others_ticket(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-other"]))  # 남이 이미 담당
    with pytest.raises(ForbiddenError):
        service.claim_ticket(db, ob, settings, me, page_id="page-1")


# ── meta ────────────────────────────────────────────────────────────────────

def test_meta_reads_schema_options(db, settings):
    ob = _FakeOutbound(page=_page())
    meta = service.ticket_meta(ob, settings)
    assert meta["statuses"] == ["계획", "진행", "검증", "이슈", "완료", "취소"]
    assert meta["priorities"] == ["높음", "보통", "낮음"]
    assert meta["difficulties"] == ["보통", "어려움"]
