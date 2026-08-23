"""`ABCDEF-37` 은 **영원히 같은 티켓으로 간다** (D-282 · MASTER_PLAN §9.1 S6 Exit).

qa-contract-change: 앞 판은 세 층(canonical → legacy → alias)이 옛 `GIT-142` 링크를 지키는지를 봤다. 그 두 층이 사라졌으므로(D-282 · D-283) 같은 형태의 시험은 대상이 없다 — 못박는 성질을 「옛 이름이 계속 열린다」에서 「지금 이름이 절대 안 움직인다」로 옮겼고, 움직일 수 있었던 경로(코드 변경·코드 재사용)가 실제로 없어졌는지를 반례로 확인한다.

## 무엇이 걸려 있는가

티켓 이름은 문서·대화·메일·커밋 메시지에 뿌려진다. 그 이름이 한 번이라도 움직이면
그때까지 뿌린 링크가 전부 죽고, 이 전환은 사람들에게 「기록이 사라진 사건」이 된다.

앞 정책은 그 위험을 **별칭**으로 막았다 — 이름이 바뀌면 옛 이름을 남겼다. 새 정책은
더 앞에서 막는다: **이름이 안 바뀐다.** 코드는 서버가 짓고 아무도 못 고치며, 번호는
한 번 받으면 안 움직인다.

그래서 이 파일이 보는 것은 「옛 이름이 열리는가」가 아니라 **「이름을 움직일 수 있는
경로가 정말로 없는가」**다.

## 순서가 계약이다

`canonical_key` → `uuid`. 「찾았다」뿐 아니라 **어느 층이 답했는지**까지 본다 — 찾기만
확인하면 순서가 뒤집혀도 통과한다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes, numbering
from app.work.resolve import BY_CANONICAL, BY_UUID, resolve

pytestmark = pytest.mark.regression


@pytest.fixture()
def project(db):
    """제품이 짓는 방식 그대로 코드를 받은 프로젝트.

    문자열을 시험이 고르지 않는 이유: 고르면 그 문자열이 정책과 갈라질 수 있고, 갈라진
    시험은 「제품이 만들 수 없는 값」 위에서 초록을 찍는다.
    """
    row = Project(
        name="SK하이닉스 용인", org_id=DEFAULT_ORG_ID, notion_page_id="proj-page-1",
    )
    codes.insert_with_code(db, row)
    db.flush()
    assert codes.is_valid(row.code)
    return row


@pytest.fixture()
def ticket(db, project):
    """아직 번호를 못 받은 티켓 하나 — 적재 직후의 상태다."""
    row = Ticket(
        title="용인 클러스터 대비", project_uid=project.id, project_link=PROJECT_LINK_OK,
        notion_page_id="page-142", notion_ticket_number=142,
        org_id=DEFAULT_ORG_ID, source="notion",
    )
    db.add(row)
    db.flush()
    return row


def test_a_ticket_without_a_number_has_no_name(db, ticket):
    """번호가 없으면 부를 이름도 없다 — **uuid 를 이름 자리에 넣지 않는다.**

    넣으면 「이름이 없다」는 사실이 화면에서 감춰지고, 사용자는 읽을 수 없는 문자열을
    티켓 번호로 믿는다.
    """
    from app.work.resolve import display_key

    assert ticket.canonical_key is None
    assert display_key(ticket) is None


def test_numbering_gives_the_ticket_its_name(db, project, ticket):
    """`<CODE>-<SEQ>`. **코드는 프로젝트가, 번호는 카운터가, 이름은 트리거가** 만든다."""
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    db.refresh(ticket)
    assert ticket.canonical_key == f"{project.code}-1"

    found = resolve(db, ticket.canonical_key)
    assert found is not None and found.ticket.id == ticket.id
    assert found.matched_by == BY_CANONICAL and found.is_current_name


def test_renaming_the_project_moves_no_name(db, project, ticket):
    """**이름 변경은 코드와 티켓 이름에 영향을 주지 않는다** — 정책의 한 줄 그대로.

    앞 정책에서는 코드가 이름에서 나왔기 때문에 이 성질이 성립하지 않았다(옛 D-278 이
    실제로 그 사고를 기록한다: 소스가 접두사를 뺀 날 확정 20건이 전부 «못 찾음» 이 됐다).
    """
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    db.refresh(ticket)
    before_code, before_key = project.code, ticket.canonical_key

    project.name = "완전히 다른 이름으로 바꾼다"
    db.flush()
    db.refresh(project)
    db.refresh(ticket)

    assert project.code == before_code
    assert ticket.canonical_key == before_key
    assert resolve(db, before_key).ticket.id == ticket.id


def test_two_projects_never_share_a_code(db):
    """**전역 유일이다.** 조직이 달라도 같은 코드를 못 쓴다.

    앞 정책의 유니크는 `(org_id, code)` 였고 `org_id` 가 NULL 인 행끼리는 서로 다른
    값이라 사실상 아무것도 막지 않았다. 티켓 이름은 조직을 지고 다니지 않으므로
    유일성도 조직을 지면 안 된다.
    """
    from sqlalchemy.exc import IntegrityError

    first = Project(name="가", org_id=DEFAULT_ORG_ID)
    codes.insert_with_code(db, first)
    db.flush()

    second = Project(name="나", org_id="other-org")
    second.code = first.code
    db.add(second)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_database_refuses_a_code_the_generator_cannot_make(db):
    """**반례** — 앱을 안 거치는 쓰기도 막힌다 (`ck_projects_code_shape`).

    이관·수동 SQL·되감기는 앱을 안 지난다. 그쪽으로 옛 정책의 `SKH` 가 들어오면 티켓
    이름이 두 규칙에서 나오게 되고, 그 상태는 아무 오류도 안 낸다.
    """
    from sqlalchemy.exc import IntegrityError

    for bad in ("SKH", "ABCDEI", "ABCDE", "ABCDEFG", "abcdef", "ABCD12"):
        row = Project(name=f"틀린 코드 {bad}", org_id=DEFAULT_ORG_ID)
        row.code = bad
        db.add(row)
        with pytest.raises(IntegrityError, match="ck_projects_code_shape"):
            db.flush()
        db.rollback()


def test_a_project_without_a_code_gets_no_number(db):
    """코드가 없으면 번호를 안 준다 — 주면 「번호는 있는데 이름이 없는 티켓」이 생긴다."""
    from app.core.errors import ConflictError

    row = Project(name="코드 없는 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.flush()
    with pytest.raises(ConflictError):
        numbering.allocate(db, row.id)


def test_resolution_is_case_insensitive_for_codes(db, project, ticket):
    """`abcdef-1` 도 같은 티켓이다. 저장형은 대문자 하나뿐이다."""
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    db.refresh(ticket)
    found = resolve(db, ticket.canonical_key.lower())
    assert found is not None and found.ticket.id == ticket.id


def test_the_uuid_layer_still_answers(db, ticket):
    """두 번째 층. 「어느 층이 답했는가」를 함께 본다 — 순서가 계약이다."""
    found = resolve(db, ticket.id)
    assert found is not None and found.ticket.id == ticket.id
    assert found.matched_by == BY_UUID


def test_unknown_tokens_resolve_to_nothing(db, project, ticket):
    """**반례** — 없는 이름은 못 찾아야 한다.

    옛 정책의 이름(`GIT-142`·`SKH-1`)이 여기 있는 것이 중요하다. 그 둘이 무언가로
    해석되면 옛 코드를 폐기했다는 말이 거짓이 된다(D-283).
    """
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    for token in (
        "GIT-142", "SKH-1", "ZZZZZZ-1", f"{project.code}-999",
        "", None, "not-a-uuid", f"{project.code}-",
    ):
        assert resolve(db, token) is None, f"«{token}» 이 무언가로 해석됐다"


def test_canonical_cannot_be_written_by_the_application(db, project, ticket):
    """앱이 `canonical_key` 에 무엇을 적든 **트리거가 덮어쓴다** (D-282).

    이 성질이 「어긋날 수 없다」의 근거다. 주석으로 약속하는 대신 DB 가 강제한다.
    """
    ticket.seq = numbering.allocate(db, project.id)
    ticket.canonical_key = "WRONG-999"
    db.flush()
    db.refresh(ticket)
    assert ticket.canonical_key == f"{project.code}-1"
