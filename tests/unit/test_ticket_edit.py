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
        "시작일": {"type": "date"},
        "대분류": {"type": "rich_text"},
        "프로젝트": {"type": "relation", "relation": {"database_id": "proj-db"}},
    }
}


@pytest.fixture(autouse=True)
def portal_project(make_project):
    """이 파일의 모든 티켓이 붙어 있는 Portal 프로젝트(조직 공통).

    0060 부터 티켓의 조직 소속은 프로젝트가 정한다 — 프로젝트가 없으면 그 티켓은
    어느 범위에도 안 잡히는 유령이라 쓰기 경로가 404 로 막는다. 이 파일이 검사하려는
    것은 그 게이트가 아니라 편집 동작이므로, 정상 소속을 미리 만들어 둔다.
    """
    return make_project(name="알파", external_id="px-1")


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
            "시작일": {"date": None},
            "대분류": {"rich_text": []},
            "프로젝트": {"relation": [{"id": "px-1"}]},
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


# ── 제품화: 작업 DB 의 편집 가능한 속성을 전부 포털에서 고친다 (2026-08-04 지시) ──────────
#
# 예전에는 제목·프로젝트·실제 WD·시작일·대분류가 PATCH 계약에 아예 없었다. 그중 하나만
# 고치려 해도 노션을 열어야 했고, 그게 "DB 에 접근하지 않아도 업무를 관리한다"를 막고 있었다.
# 아래 테스트들은 **각 필드가 실제로 Notion PATCH 페이로드까지 도달하는지**를 못박는다 —
# 스키마에 필드를 더해 놓고 저장소가 흘려버리면 화면에서는 저장된 것처럼 보인다.

def test_title_reaches_notion(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"title": "고친 제목"})
    assert ob.last_patch["properties"]["제목"]["title"][0]["text"]["content"] == "고친 제목"


def test_title_cannot_be_emptied(db, settings, make_user):
    """제목을 비우면 목록에서 그 티켓이 '(제목 없음)'이 된다 — 실수지 뜻이 아니다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"title": "  "})
    assert ob.last_patch is None


def test_actual_wd_reaches_notion(db, settings, make_user):
    """티켓을 닫을 때 실제 공수를 적는다 — 이게 없어서 완료 처리에 노션이 필요했다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"act_wd": 3.5})
    assert ob.last_patch["properties"]["실제 WD"] == {"number": 3.5}


def test_start_date_reaches_notion_and_clears(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1",
                          changes={"start_date": "2026-09-01"})
    assert ob.last_patch["properties"]["시작일"] == {"date": {"start": "2026-09-01"}}
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"start_date": ""})
    assert ob.last_patch["properties"]["시작일"] == {"date": None}


def test_category_reaches_notion(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))
    service.update_ticket(db, ob, settings, me, page_id="page-1", changes={"category": "인프라"})
    assert ob.last_patch["properties"]["대분류"]["rich_text"][0]["text"]["content"] == "인프라"


def test_project_can_be_moved_but_never_detached(db, settings, make_user, make_project):
    """프로젝트는 **옮길 수는 있어도 뗄 수는 없다** (0060).

    예전에는 빈 값이 '연결 해제' 였다. 티켓의 조직 소속을 프로젝트가 정하는 이상 그건
    그 티켓을 어느 범위에도 안 잡히는 유령으로 만드는 동작이라 막는다 — 소속을 지우는
    것과 옮기는 것은 다른 일이다.

    옮기는 대상도 **내가 쓸 수 있는 프로젝트**여야 한다. 아니면 내 티켓을 남의 부서로
    밀어 넣을 수 있고, 밀어 넣은 순간 내 범위에서 사라져 되돌릴 수도 없다.
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    target = make_project(name="베타", external_id="px-2")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))

    service.update_ticket(db, ob, settings, me, page_id="page-1",
                          changes={"project_id": target.id})
    assert ob.last_patch["properties"]["프로젝트"] == {"relation": [{"id": "px-2"}]}, (
        "Portal 프로젝트 id 가 외부 relation id 로 번역되지 않았다"
    )

    with pytest.raises(ValidationAppError):
        service.update_ticket(db, ob, settings, me, page_id="page-1",
                              changes={"project_id": ""})


def test_every_editable_schema_property_has_an_alias(db, settings):
    """작업 DB 의 **편집 가능한** 속성이 전부 EDIT_PROP_ALIASES 에 있는지 본다.

    새 속성이 노션에 생겼는데 여기 없으면 그 값을 고치려고 노션을 열게 된다 — 그것이 곧
    제품화가 깨진 상태다. 관계형 넷(상위/하위/선행/후속 작업)은 별도 UI 가 필요해 아직
    범위 밖이며, 이 목록이 그 사실을 명시적으로 기록한다.
    """
    from app.tickets.notion_write import EDIT_PROP_ALIASES

    computed = {"티켓 ID", "생성 일시"}          # 노션이 계산한다 — 쓸 수 없다
    our_own = {"파일과 미디어"}                   # 첨부는 우리 표로 옮겼다(ticket_attachments)
    not_used = {"다중 선택", "텍스트"}            # 실제 데이터 1,000건에서 사용률 0%
    out_of_scope = {"상위 작업", "하위 작업", "티켓 선택(선행 작업)", "티켓 선택(후속 작업)"}

    editable = set(_SCHEMA["properties"]) - computed - our_own - not_used - out_of_scope
    aliased = {names[0] for names in EDIT_PROP_ALIASES.values()}
    assert editable <= aliased, f"별칭이 없는 편집 가능 속성: {sorted(editable - aliased)}"
