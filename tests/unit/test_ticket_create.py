"""새 티켓 수동 생성(POST) + 프로젝트 발견 유닛 테스트.

## 판정 대상이 옮겨 갔다 (S14)

예전에는 가짜 Notion 서버가 받은 **생성 페이로드**를 검사했다. 티켓의 정본이 이 서버의
`tickets` 표로 옮겨 왔으므로 이제는 **만들어진 행**을 검사한다. 제목·기본 상태·프로젝트
필수와 범위·담당자 해석·설명 본문은 저장소가 어디든 같아야 하는 것이라 그대로 남는다.

## 사라진 것 하나

우선순위·난이도의 **허용값 검사**가 없어졌다. 그 목록은 노션 스키마의 select 옵션이었고,
지금 두 축에는 제품이 소유한 어휘가 없다 — 있는 데이터에서 뽑은 목록으로 검사하면 첫 새
값이 영원히 못 들어와 목록이 스스로를 잠근다(`app/tickets/repository_native.py::meta`).
대신 제품이 실제로 소유한 어휘인 **진행상태**는 그대로 막히고, 그 확인이 아래 있다.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import ValidationAppError
from app.core.models_base import split_names
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.tickets import service
from app.tickets.models import PROJECT_LINK_OK
from app.tickets.schemas import TicketCreate

pytestmark = pytest.mark.unit


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


def _create(db, settings, user, payload):
    """자체 DB 저장소는 `outbound` 를 쓰지 않으므로 넘기지 않는다."""
    return service.create_ticket(db, None, settings, user, payload=payload)


def _row(db, out):
    db.expire_all()
    return service.ticket_row_for(db, out["ticket"]["id"])


def test_create_builds_title_and_default_status(db, settings, me, project):
    out = _create(db, settings, me, _payload(project))
    row = _row(db, out)
    assert row.title == "테스트 티켓"
    assert row.status == "계획"  # 기본값
    assert split_names(row.project_ids) == ["proj-1"]
    assert row.project_uid == project.id and row.project_link == PROJECT_LINK_OK
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
    from sqlalchemy import func, select

    from app.core.errors import NotFoundError
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets.models import TicketCache

    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    db.add_all([theirs, mine])
    db.flush()
    other_project = make_project(name="남의 프로젝트", dept=theirs, external_id="proj-theirs")
    # 조직 직속이면 조직 전체가 보인다 — 좁혀지는 상태(부서 소속)로 바꿔야 이 시험이 성립한다.
    me.department_id = mine.id
    db.commit()

    with pytest.raises(NotFoundError):
        _create(db, settings, me,
                TicketCreate(title="몰래 만들기", project_id=other_project.id))
    assert db.execute(select(func.count()).select_from(TicketCache)).scalar_one() == 0


def test_create_resolves_assignees(db, settings, me, project):
    _map(db, me, "notion-me")
    out = _create(db, settings, me, _payload(project, assignee_user_ids=[me.id]))
    assert split_names(_row(db, out).assignee_notion_ids) == ["notion-me"]


def test_create_rejects_an_unknown_status(db, settings, me, project):
    """진행상태 어휘는 제품이 소유한다 — 모르는 값은 만들 때부터 막힌다.

    우선순위·난이도에는 같은 검사가 없다. 그 두 축에는 제품이 소유한 목록이 아직 없고,
    지금 데이터에서 뽑은 목록으로 검사하면 첫 새 값이 영원히 못 들어온다(모듈 docstring).
    """
    with pytest.raises(ValidationAppError):
        _create(db, settings, me, _payload(project, status="없는상태"))


def test_create_with_description_stores_the_body(db, settings, me, project):
    out = _create(db, settings, me, _payload(project, description="배경 설명입니다"))
    assert _row(db, out).body_markdown == "배경 설명입니다"


def test_create_description_comes_back_as_blocks(db, settings, me, project):
    """설명도 문서 본문처럼 제목/글머리/구분선이 실제 블록이 되어야 한다(§BodyEditor 짝)."""
    from app.core.source_registry import build_ticket_repository

    out = _create(db, settings, me,
                  _payload(project, description="## 개요\n- 항목1\n---\n일반 문단"))
    repo = build_ticket_repository(settings, None)
    blocks = repo.body_blocks(db, page_id=out["ticket"]["id"])
    assert [b["kind"] for b in blocks] == ["heading_2", "bulleted", "divider", "paragraph"]


def test_create_est_wd_and_due(db, settings, me, project):
    out = _create(db, settings, me, _payload(project, est_wd=3.0, due_date="2026-10-01"))
    row = _row(db, out)
    assert row.est_wd == 3.0
    assert row.due_date == date(2026, 10, 1)


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
    """설명은 그대로 본문 블록으로 바뀐다(markdown_to_blocks, app/core/notion_blocks.py).
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
