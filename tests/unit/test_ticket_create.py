"""새 티켓 수동 생성(POST) + 프로젝트 발견 유닛 테스트.

fake outbound 가 스키마 조회(GET db)·페이지 생성(POST pages)·프로젝트 목록(POST projdb/query)을
(method, url) 로 라우팅한다. 제목 필수·기본 상태·프로젝트 필수·담당자 해석·옵션 검증을 검증한다.
"""

from __future__ import annotations

import pytest

# 이 파일은 **Notion 저장소 구현체**를 시험한다 — 픽스처가 전부 가짜 Notion 서버다.
# 제품 기본 소스는 S14 부터 `native` 이므로 여기서 되돌려 놓는다. 안 되돌리면 이 시험들이
# 빈 결과 위에서 통과하거나(거짓 초록) 엉뚱한 오류로 죽는다.
#
# 이 표는 동시에 **Notion 을 걷어낼 때 다시 쓸 파일의 목록**이다. 여기서 지키는 성질
# (권한·소유·검증·본문 저장 순서)은 소스가 바뀌어도 그대로 지켜야 하는 것이고, 그 확인은
# 자체 DB 구현체 위에서 다시 서야 한다.
pytestmark = pytest.mark.notion_source

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


@pytest.fixture()
def project(make_project):
    """조직 공통 Portal 프로젝트. 외부 짝(`external_id`)이 있어야 티켓을 만들 수 있다.

    0060 부터 티켓 생성은 **Portal 프로젝트 id** 를 받고, 서버가 그것을 외부 relation id 로
    번역한다 — 브라우저가 외부 시스템의 키를 알 이유가 없고, Portal id 여야 그 프로젝트에
    대한 권한을 검증할 수 있다.
    """
    return make_project(name="알파", external_id="proj-1")


@pytest.fixture()
def me(db, make_user):
    """조직 직속 사용자. 부서가 없어도 조직 공통 프로젝트는 볼 수 있어야 한다.

    부서도 조직 직속도 아닌(미지정) 계정은 아무 것도 못 본다 — 그게 0060 의 기본값이고,
    이 파일이 검사하려는 것은 그 게이트가 아니라 생성 동작이다.
    """
    from app.users.models import MEMBERSHIP_ORGANIZATION

    user = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    user.membership_kind = MEMBERSHIP_ORGANIZATION
    db.commit()
    return user


def _payload(project, **kw):
    base = {"title": "테스트 티켓", "project_id": project.id}
    base.update(kw)
    return TicketCreate(**base)


def test_create_builds_title_and_default_status(db, settings, me, project):
    ob = _FakeOutbound()
    out = service.create_ticket(db, ob, settings, me, payload=_payload(project))
    props = ob.created_body["properties"]
    assert props["제목"]["title"][0]["text"]["content"] == "테스트 티켓"
    assert props["진행상태"]["status"]["name"] == "계획"  # 기본값
    assert props["프로젝트"]["relation"] == [{"id": "proj-1"}]
    assert out["ticket"]["title"] == "테스트 티켓"


def test_create_requires_a_project(db, settings, me, project):
    """프로젝트 없는 티켓은 **만들 수조차 없다** (0060).

    예전에는 저장소 구현체가 외부 스키마를 보고 거절했다 — 즉 그 관계 속성이 없는 설치에서는
    프로젝트 없는 티켓이 그대로 만들어졌다. 이제 티켓의 조직 소속을 프로젝트가 정하므로
    (`app/core/ownership.py`) 프로젝트 없는 티켓은 **어느 범위에도 안 잡히는 유령**이 된다.
    그래서 계약(스키마) 단계에서 막는다 — 외부 소스의 모양과 무관하게.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TicketCreate(title="테스트 티켓", project_id=None)
    with pytest.raises(ValidationError):
        TicketCreate(title="테스트 티켓", project_id="   ")


def test_create_rejects_a_project_outside_my_scope(db, settings, me, make_project):
    """남의 부서 프로젝트로는 티켓을 만들 수 없다 — 만들 수 있으면 쓰기로 범위를 넘는다.

    **없는 프로젝트와 같은 404** 다. 갈리면 응답만 보고 "그 프로젝트는 존재한다" 를 알 수
    있고, id 를 찍어 보며 조직의 프로젝트 목록을 열거할 수 있다.
    """
    from app.core.errors import NotFoundError
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    db.add_all([theirs, mine])
    db.flush()
    other_project = make_project(name="남의 프로젝트", dept=theirs, external_id="proj-theirs")
    # 조직 직속이면 조직 전체가 보인다 — 좁혀지는 상태(부서 소속)로 바꿔야 이 시험이 성립한다.
    me.department_id = mine.id
    db.commit()

    ob = _FakeOutbound()
    with pytest.raises(NotFoundError):
        service.create_ticket(
            db, ob, settings, me,
            payload=TicketCreate(title="몰래 만들기", project_id=other_project.id),
        )
    assert ob.created_body is None


def test_create_resolves_assignees(db, settings, me, project):
    _map(db, me, "notion-me")
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(project, assignee_user_ids=[me.id]))
    people = ob.created_body["properties"]["티켓 담당자"]["people"]
    assert people == [{"id": "notion-me"}]


def test_create_rejects_invalid_priority(db, settings, me, project):
    ob = _FakeOutbound()
    with pytest.raises(ValidationAppError):
        service.create_ticket(db, ob, settings, me, payload=_payload(project, priority="긴급긴급"))
    assert ob.created_body is None


def test_create_with_description_adds_children(db, settings, me, project):
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(project, description="배경 설명입니다"))
    children = ob.created_body.get("children")
    assert children and children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "배경 설명입니다"


def test_create_description_converts_markdown_to_blocks(db, settings, me, project):
    # 설명도 문서 본문처럼 제목/글머리/구분선이 실제 Notion 블록이 되어야 한다(§BodyEditor 짝).
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(project, description="## 개요\n- 항목1\n---\n일반 문단"))
    kinds = [c["type"] for c in ob.created_body.get("children")]
    assert kinds == ["heading_2", "bulleted_list_item", "divider", "paragraph"]


def test_create_est_wd_and_due(db, settings, me, project):
    ob = _FakeOutbound()
    service.create_ticket(db, ob, settings, me, payload=_payload(project, est_wd=3.0, due_date="2026-10-01"))
    props = ob.created_body["properties"]
    assert props["예상 WD"] == {"number": 3.0}
    assert props["마감일"] == {"date": {"start": "2026-10-01"}}


def test_list_projects_offers_only_portal_projects_i_can_see(db, me, make_project):
    """새 티켓 폼의 프로젝트 후보는 **Portal 프로젝트**이고 범위 안만 나온다 (0060).

    예전에는 외부 소스(Notion)의 relation 목록을 그대로 내려 줬다 — 다른 부서의 프로젝트
    이름이 전부 드롭다운에 떴고, 외부 키가 브라우저로 나갔다(그 id 로는 권한을 검증할 수
    없다). 정렬은 이름순이라 같은 화면을 두 번 열어도 순서가 흔들리지 않는다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    make_project(name="베타", external_id="p-beta")
    make_project(name="알파", external_id="p-alpha")
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    db.add_all([theirs, mine])
    db.flush()
    make_project(name="남의 프로젝트", dept=theirs, external_id="p-theirs")
    # 조직 직속이면 조직 전체가 보인다 — 좁혀지는 상태(부서 소속)여야 이 시험이 성립한다.
    me.department_id = mine.id
    db.commit()

    rows = service.list_projects(db, me)

    names = [r["name"] for r in rows]
    assert names == sorted(names), "이름순 정렬이 아니다"
    assert "남의 프로젝트" not in names, "다른 부서 프로젝트가 드롭다운에 샜다"
    assert {"알파", "베타"} <= set(names), (
        "조직 공통 프로젝트(dept 없음)가 부서 사용자에게 안 보인다 — 그건 소속이 아니라 실종이다"
    )
    assert all(r["can_create_ticket"] for r in rows), "외부 짝이 있는데 생성 불가로 표시됐다"


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
        TicketCreate(title="t", project_id="p1", description=desc)


def test_description_within_line_cap_is_accepted():
    desc = "\n".join(f"line {i}" for i in range(50))
    tc = TicketCreate(title="t", project_id="p1", description=desc)
    assert tc.description == desc
