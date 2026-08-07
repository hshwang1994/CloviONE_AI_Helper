"""새 티켓 수동 생성(POST) + 프로젝트 발견 유닛 테스트.

fake outbound 가 스키마 조회(GET db)·페이지 생성(POST pages)·프로젝트 목록(POST projdb/query)을
(method, url) 로 라우팅한다. 제목 필수·기본 상태·프로젝트 필수·담당자 해석·옵션 검증을 검증한다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.tickets import service
from app.tickets.schemas import TicketCreate

_PROJ_DB = "projdb-1"
_SCHEMA = {
    "properties": {
        "제목": {"type": "title"},
        "진행상태": {"type": "status", "status": {"options": [
            {"name": "계획"}, {"name": "진행"}, {"name": "완료"},
        ]}},
        "마감일": {"type": "date"},
        "우선순위": {"type": "select", "select": {"options": [{"name": "높음"}, {"name": "보통"}]}},
        "난이도": {"type": "select", "select": {"options": [{"name": "보통"}, {"name": "어려움"}]}},
        "예상 WD": {"type": "number"},
        "티켓 담당자": {"type": "people"},
        "티켓 ID": {"type": "unique_id"},
        "프로젝트": {"type": "relation", "relation": {"database_id": _PROJ_DB}},
    }
}


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeOutbound:
    def __init__(self, *, schema=_SCHEMA, projects=None):
        self.schema = schema
        self.projects = projects or []
        self.calls = []
        self.created_body = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET" and "/v1/databases/" in url:
            return _Resp(200, self.schema)
        if method == "POST" and url.endswith("/v1/pages"):
            self.created_body = kwargs.get("json")
            props = (self.created_body or {}).get("properties", {})
            title = ""
            tv = props.get("제목", {}).get("title") or []
            if tv:
                title = tv[0]["text"]["content"]
            # 생성 결과를 _parse_row 가 읽을 수 있는 페이지로 되돌린다.
            return _Resp(200, {
                "id": "new-page", "url": "https://notion/new-page",
                "properties": {
                    "제목": {"title": [{"plain_text": title}]},
                    "진행상태": props.get("진행상태", {"status": None}),
                    "마감일": props.get("마감일", {"date": None}),
                    "티켓 담당자": props.get("티켓 담당자", {"people": []}),
                    "예상 WD": props.get("예상 WD", {"number": None}),
                    "난이도": props.get("난이도", {"select": None}),
                    "우선순위": props.get("우선순위", {"select": None}),
                    "티켓 ID": {"unique_id": {"number": 999}},
                },
            })
        if method == "POST" and f"/v1/databases/{_PROJ_DB}/query" in url:
            results = [{"id": p["id"], "properties": {"프로젝트": {"type": "title", "title": [{"plain_text": p["name"]}]}}} for p in self.projects]
            return _Resp(200, {"results": results, "has_more": False})
        raise AssertionError(f"unexpected {method} {url}")


def _map(db, user, notion_id):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=STATUS_VERIFIED))
    db.commit()


def _payload(**kw):
    base = {"title": "테스트 티켓", "project_id": "proj-1"}
    base.update(kw)
    return TicketCreate(**base)


def test_create_builds_title_and_default_status(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    out = service.create_ticket(db, ob, settings, me, payload=_payload())
    props = ob.created_body["properties"]
    assert props["제목"]["title"][0]["text"]["content"] == "테스트 티켓"
    assert props["진행상태"]["status"]["name"] == "계획"  # 기본값
    assert props["프로젝트"]["relation"] == [{"id": "proj-1"}]
    assert out["ticket"]["title"] == "테스트 티켓"


def test_create_requires_project_when_prop_exists(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    with pytest.raises(ValidationAppError):
        service.create_ticket(db, ob, settings, me, payload=_payload(project_id=None))
    assert ob.created_body is None


def test_create_resolves_assignees(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(assignee_user_ids=[me.id]))
    people = ob.created_body["properties"]["티켓 담당자"]["people"]
    assert people == [{"id": "notion-me"}]


def test_create_rejects_invalid_priority(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    with pytest.raises(ValidationAppError):
        service.create_ticket(db, ob, settings, me, payload=_payload(priority="긴급긴급"))
    assert ob.created_body is None


def test_create_with_description_adds_children(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(description="배경 설명입니다"))
    children = ob.created_body.get("children")
    assert children and children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "배경 설명입니다"


def test_create_description_converts_markdown_to_blocks(db, settings, make_user):
    # 설명도 문서 본문처럼 제목/글머리/구분선이 실제 Notion 블록이 되어야 한다(§BodyEditor 짝).
    me = make_user(email="mk@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(description="## 개요\n- 항목1\n---\n일반 문단"))
    kinds = [c["type"] for c in ob.created_body.get("children")]
    assert kinds == ["heading_2", "bulleted_list_item", "divider", "paragraph"]


def test_create_est_wd_and_due(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(est_wd=3.0, due_date="2026-10-01"))
    props = ob.created_body["properties"]
    assert props["예상 WD"] == {"number": 3.0}
    assert props["마감일"] == {"date": {"start": "2026-10-01"}}


def test_list_projects_discovers_relation_db(db, settings):
    ob = _FakeOutbound(projects=[{"id": "p2", "name": "베타"}, {"id": "p1", "name": "알파"}])
    rows = service.list_projects(ob, settings)
    assert [r["name"] for r in rows] == ["베타", "알파"] or [r["name"] for r in rows] == ["알파", "베타"]
    # 이름 기준 정렬(가나다).
    assert rows[0]["name"] == "베타" or rows[0]["name"] == "알파"
    names = [r["name"] for r in rows]
    assert names == sorted(names)


def test_title_required_by_schema():
    with pytest.raises(Exception):
        TicketCreate(title="   ", project_id="p1")


def test_description_over_line_cap_is_rejected_not_truncated():
    """설명은 그대로 노션 블록으로 바뀐다(markdown_to_blocks, app/core/notion_blocks.py).
    그 변환기는 100줄을 넘으면 조용히 잘라내므로, 총 글자 수(4000자)만 보고 통과시키면
    짧은 줄 150개(1300자 남짓, 4000자 밑)도 뒤 50줄이 소리 없이 사라진다. 여기서 거절해야
    한다(TicketBodyUpdate와 같은 규칙)."""
    desc = "\n".join(f"line {i}" for i in range(150))
    assert len(desc) < 4000  # 글자 수 상한은 통과하는 입력이어야 이 테스트의 의미가 있다
    with pytest.raises(Exception):
        TicketCreate(title="t", description=desc)


def test_description_within_line_cap_is_accepted():
    desc = "\n".join(f"line {i}" for i in range(50))
    tc = TicketCreate(title="t", description=desc)
    assert tc.description == desc
