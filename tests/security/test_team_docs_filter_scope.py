"""필터 드롭다운도 범위를 지킨다 (`GET /api/team-docs/filters`).

`GET /api/team-docs` 는 `service.doc_in_scope` 로 행을 거르고 total 까지 보정한다. 그런데
`service.filter_options` 는 `repository.all_active` 로 **문서 캐시 전량**을 훑어 프로젝트와
상태를 모았다 — `viewer` 인자 자체가 없었다.

그래서 목록에서 가린 문서의 **프로젝트 코드명**이 드롭다운으로 그대로 나갔다. 본문을 안 줬으니
괜찮다고 읽으면 안 된다: 프로젝트 코드명은 대개 그 자체가 정보다(고객사명·제품명이 들어간다).
"어느 고객사 일을 하고 있는가" 는 문서를 한 건도 열지 않고 알 수 있고, 옵션 목록은 그걸
정리해서 준다. 상태 어휘도 남의 팀 업무 흐름을 알려 준다.

## ⚠️ 좁히면 **안 되는** 것 두 가지

  * **고정 상수** — 문서 종류·업무 분야·기술 태그는 `classify.py` 에 박힌 공통 어휘라 누구에게나
    같다. 좁히면 "우리 팀에 아직 회의록이 없다" 는 이유로 작성 폼에서 회의록을 못 고르게 되고,
    그때부터 아무도 새 종류의 문서를 못 만든다. 가릴 것도 없는데 기능만 죽는다.
  * **작성자를 해석할 수 없는 문서** — `author_notion_ids` 는 다음 동기화가 채운다. 그걸 범위
    밖으로 치면 드롭다운이 통째로 비고, 목록에는 보이는 문서를 필터로는 못 고르게 된다
    (tests/security/test_document_scope.py 가 목록에 대해 고정한 그 성질과 같다).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-filt-mine", "notion-filt-theirs"

ME = "df-me@goodmit.co.kr"        # 우리팀 일반 사용자(기본 범위가 자기 팀)
OTHER = "df-other@goodmit.co.kr"  # 남의팀 일반 사용자
OP = "df-op@goodmit.co.kr"        # 우리팀만 보는 부서 범위 관리자

PROJ_MINE = "사내포탈 고도화"
PROJ_THEIRS = "한빛은행 차세대 계정계"   # 고객사명이 그대로 들어간 코드명
PROJ_ORPHAN = "미해석 문서 프로젝트"

STATUS_MINE = "진행중"
STATUS_THEIRS = "고객 검수 대기"
STATUS_ORPHAN = "보류"


@pytest.fixture()
def docs(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리팀만 보는 부서 관리자 + 문서 셋(우리팀·남의팀·작성자 미해석)."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.team_docs.models import DocumentCache, join_names

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    other = make_user(OTHER, role="user", display_name="남")
    op = make_user(OP, role="admin", display_name="부서관리자")
    me.department_id = mine.id
    other.department_id = theirs.id
    op.department_id = mine.id
    op.admin_scope = "dept"
    op.scope_dept_id = mine.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    # 소속(0060)은 문서 자신이 든다 — 작성자가 정하지 않는다. 마지막 문서는 작성자를
    # 앱 계정으로 해석할 수 없는 경우인데, 소속이 우리 팀이므로 필터 후보에 남아야 한다.
    db.add_all([
        DocumentCache(
            notion_page_id="fm", title="우리팀 문서", author_notion_ids=NID_MINE,
            owner_kind="department", owner_dept_id=mine.id,
            project_names=join_names([PROJ_MINE]), status=STATUS_MINE,
        ),
        DocumentCache(
            notion_page_id="ft", title="남의팀 문서", author_notion_ids=NID_THEIRS,
            owner_kind="department", owner_dept_id=theirs.id,
            project_names=join_names([PROJ_THEIRS]), status=STATUS_THEIRS,
        ),
        DocumentCache(
            notion_page_id="fn", title="작성자 미해석 문서", author_notion_ids="",
            owner_kind="department", owner_dept_id=mine.id,
            project_names=join_names([PROJ_ORPHAN]), status=STATUS_ORPHAN,
        ),
    ])
    db.commit()


def _filters(client) -> dict:
    r = client.get("/api/team-docs/filters")
    assert r.status_code == 200, f"필터 조회 자체가 실패했다: {r.status_code} {r.text}"
    return r.json()


# ── 가린 문서의 정보는 옵션에도 없다 ─────────────────────────────────────────────

def test_another_teams_project_code_name_is_not_offered(client, login_as, docs):
    """목록에서 가린 문서의 프로젝트 코드명이 드롭다운으로 나가면 안 된다.

    자기 팀 값이 **함께 들어 있는지**도 같은 검사에서 본다 - 옵션이 통째로 비어도 통과하는
    테스트는 아무것도 증명하지 못한다.
    """
    login_as("user", email=ME)
    body = _filters(client)
    assert PROJ_MINE in body["projects"], f"자기 팀 프로젝트까지 사라졌다: {body['projects']}"
    assert PROJ_THEIRS not in body["projects"], (
        f"남의 팀 프로젝트 코드명이 필터 옵션으로 새어 나간다: {body['projects']}"
    )


def test_another_teams_status_vocabulary_is_not_offered(client, login_as, docs):
    """상태 어휘도 캐시에서 뽑는다 - 남의 팀 업무 흐름이 그대로 드러난다."""
    login_as("user", email=ME)
    body = _filters(client)
    assert STATUS_MINE in body["statuses"], f"자기 팀 상태까지 사라졌다: {body['statuses']}"
    assert STATUS_THEIRS not in body["statuses"], (
        f"남의 팀 상태 어휘가 필터 옵션으로 새어 나간다: {body['statuses']}"
    )


def test_a_scoped_admin_sees_only_their_own_departments_projects(client, login_as, docs):
    """부서 범위 관리자도 같다 - 역할이 높다고 범위가 넓어지지는 않는다."""
    login_as("admin", email=OP)
    body = _filters(client)
    assert PROJ_MINE in body["projects"], f"자기 팀 프로젝트가 안 보인다: {body['projects']}"
    assert PROJ_THEIRS not in body["projects"], (
        f"다른 부서 프로젝트 코드명이 부서 관리자에게 새어 나간다: {body['projects']}"
    )


def test_the_other_team_sees_the_mirror_image(client, login_as, docs):
    """방향이 바뀌어도 같아야 한다 - 한쪽만 막혔으면 그건 판정이 아니라 우연이다."""
    login_as("user", email=OTHER)
    body = _filters(client)
    assert PROJ_THEIRS in body["projects"], f"자기 팀 프로젝트가 안 보인다: {body['projects']}"
    assert PROJ_MINE not in body["projects"], (
        f"남의 팀 프로젝트 코드명이 새어 나간다: {body['projects']}"
    )


# ── 오탐 방지 - 좁히면 안 되는 것들 ──────────────────────────────────────────────

def test_the_fixed_constants_are_never_narrowed(client, login_as, docs):
    """**가장 중요한 오탐 검사 1.** 문서 종류·업무 분야·기술 태그는 코드에 박힌 공통 어휘다.
    좁히면 작성 폼에서 고를 수 없게 되고, 아무도 새 종류의 문서를 못 만든다."""
    from app.team_docs.classify import DOC_TYPES, TECH_TAGS, WORK_FIELDS

    login_as("user", email=ME)
    body = _filters(client)
    assert body["doc_types"] == list(DOC_TYPES), f"문서 종류가 좁혀졌다: {body['doc_types']}"
    assert body["work_fields"] == list(WORK_FIELDS), f"업무 분야가 좁혀졌다: {body['work_fields']}"
    assert body["tech_tags"] == list(TECH_TAGS), f"기술 태그가 좁혀졌다: {body['tech_tags']}"


def test_options_from_documents_without_resolvable_authors_survive(client, login_as, docs):
    """**가장 중요한 오탐 검사 2.** `author_notion_ids` 는 다음 동기화가 채우므로 지금 대부분
    비어 있다. 그걸 범위 밖으로 치면 드롭다운이 통째로 비고, 목록에는 보이는 문서를 필터로는
    못 고르게 된다."""
    login_as("user", email=ME)
    body = _filters(client)
    assert PROJ_ORPHAN in body["projects"], (
        f"작성자 미해석 문서의 프로젝트가 사라졌다: {body['projects']}"
    )
    assert STATUS_ORPHAN in body["statuses"], (
        f"작성자 미해석 문서의 상태가 사라졌다: {body['statuses']}"
    )


def test_a_global_admin_still_sees_every_project(client, login_as, docs):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    login_as("system_admin")
    body = _filters(client)
    assert {PROJ_MINE, PROJ_THEIRS, PROJ_ORPHAN} <= set(body["projects"]), body["projects"]
    assert {STATUS_MINE, STATUS_THEIRS, STATUS_ORPHAN} <= set(body["statuses"]), body["statuses"]


def test_the_options_match_what_the_list_actually_shows(client, login_as, docs):
    """옵션과 목록이 갈라지면 고를 수는 있는데 결과가 0건인 필터가 생긴다 - 그 자체로도
    "그 프로젝트가 존재한다" 는 답이다. 판정이 한 함수여야 하는 이유가 이것이다."""
    login_as("user", email=ME)
    listed = client.get("/api/team-docs")
    assert listed.status_code == 200, listed.text
    from_list = {p for item in listed.json()["items"] for p in item["projects"]}
    assert set(_filters(client)["projects"]) == from_list, (
        "필터 옵션과 목록이 서로 다른 문서 집합을 보고 있다"
    )
