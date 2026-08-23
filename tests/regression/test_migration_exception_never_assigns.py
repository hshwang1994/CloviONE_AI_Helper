"""**임의 배정 0** — 소속을 모르는 티켓에 프로젝트를 골라 주지 않는다 (U11 · D-197).

## 왜 이것이 Exit 조건인가

잘못 배정한 티켓은 남의 부서로 샌다. 그리고 그 사고는 **화면이 정상으로 보이기
때문에 아무도 신고하지 않는다** — 목록에 한 줄이 더 있을 뿐이고, 그게 원래 거기
있어야 하는지는 보는 사람이 모른다.

그래서 「자동으로 고르지 않는다」는 규칙이고, 규칙은 시험이 지킨다.

## 반례를 함께 본다

"아무것도 안 한다" 는 **아무것도 안 하는 구현에서도 통과한다.** 그래서 분류가 실제로
돌았는지(예외가 잡혔는지)와 사람이 지정했을 때는 제대로 번호가 붙는지를 함께 본다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import (
    PROJECT_LINK_AMBIGUOUS,
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    PROJECT_LINK_UNRESOLVED,
    Ticket,
    join_names,
)
from app.work import codes as codes_mod
from app.work import triage
from app.work.models import (
    EXC_AMBIGUOUS,
    EXC_MISSING,
    EXC_SOURCE_MISSING,
    EXC_UNRESOLVED,
    MigrationException,
)

pytestmark = pytest.mark.regression


@pytest.fixture()
def project(db):
    # 코드는 제품의 생성기가 짓는다 (D-282). 시험이 문자열을 직접 고르면 그 값이 정책과
    # 갈라지고, 갈라진 사실은 DB 제약이 잡을 때까지 안 보인다.
    row = Project(name="정상 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-ok")
    codes_mod.insert_with_code(db, row)
    db.flush()
    return row


def _ticket(db, *, page_id, link, project=None, external_ids=(), missing_at=None):
    row = Ticket(
        title=f"티켓 {page_id}", notion_page_id=page_id, project_link=link,
        project_uid=getattr(project, "id", None),
        project_ids=join_names(list(external_ids)),
        notion_missing_at=missing_at, org_id=DEFAULT_ORG_ID, source="notion",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db, project):
    """실측이 말한 네 갈래를 한 줄씩 (D-197): ambiguous · missing · unresolved · 사라짐."""
    from datetime import datetime

    return {
        "ambiguous": _ticket(
            db, page_id="p-amb", link=PROJECT_LINK_AMBIGUOUS,
            external_ids=("ext-a", "ext-b"),
        ),
        "missing": _ticket(db, page_id="p-mis", link=PROJECT_LINK_MISSING),
        "unresolved": _ticket(
            db, page_id="p-unr", link=PROJECT_LINK_UNRESOLVED, external_ids=("ext-x",)
        ),
        "source_missing": _ticket(
            db, page_id="p-gone", link=PROJECT_LINK_OK, project=project,
            missing_at=datetime(2026, 8, 1, 0, 0, 0),
        ),
        "healthy": _ticket(
            db, page_id="p-ok", link=PROJECT_LINK_OK, project=project,
            external_ids=("proj-ok",),
        ),
    }


def test_classify_finds_the_four_kinds(db, world):
    """**검출기가 실제로 잡는가** 부터 본다 (D-213).

    이것이 없으면 아래 「배정하지 않는다」가 「분류 자체가 안 돌았다」와 구별되지 않는다.
    """
    result = triage.classify(db)
    assert result["opened"] == 4, f"네 갈래를 다 잡아야 한다: {result}"

    rows = {
        r.ticket_id: r.reason
        for r in db.query(MigrationException).filter(
            MigrationException.resolved_at.is_(None)
        )
    }
    assert rows[world["ambiguous"].id] == EXC_AMBIGUOUS
    assert rows[world["missing"].id] == EXC_MISSING
    assert rows[world["unresolved"].id] == EXC_UNRESOLVED
    assert rows[world["source_missing"].id] == EXC_SOURCE_MISSING
    assert world["healthy"].id not in rows, "정상 티켓이 예외로 잡혔다"


def test_classify_assigns_no_project_and_no_number(db, world):
    """**이 시험이 S6 Exit 의 「Exception 임의 배정 0」이다.**"""
    triage.classify(db)
    db.flush()

    for name in ("ambiguous", "missing", "unresolved"):
        ticket = world[name]
        db.refresh(ticket)
        assert ticket.project_uid is None, f"{name} 티켓에 프로젝트가 배정됐다"
        assert ticket.seq is None, f"{name} 티켓에 번호가 붙었다"
        assert ticket.canonical_key is None, f"{name} 티켓에 표시 이름이 생겼다"


def test_evidence_is_kept_so_a_person_can_decide(db, world):
    """사유만으로는 결정할 수 없다 — **무엇을 보고 그렇게 판단했는지**가 남아야 한다."""
    import json

    triage.classify(db)
    row = (
        db.query(MigrationException)
        .filter(MigrationException.ticket_id == world["ambiguous"].id)
        .one()
    )
    evidence = json.loads(row.source_evidence)
    assert evidence["source_project_ids"] == ["ext-a", "ext-b"], (
        "모호했던 원본 relation 목록이 남아야 한다"
    )
    assert evidence["project_link"] == PROJECT_LINK_AMBIGUOUS


def test_classify_is_idempotent(db, world):
    """다시 돌려도 줄이 안 쌓인다. 쌓이면 「몇 건 남았나」에 답할 수 없다."""
    triage.classify(db)
    before = triage.open_count(db)
    second = triage.classify(db)
    assert second["opened"] == 0 and triage.open_count(db) == before


def test_resolving_the_link_closes_the_exception(db, world, project):
    """예외가 아니게 되면 **줄이 닫힌다.** 안 닫히면 목록이 영원히 안 줄어든다."""
    triage.classify(db)
    assert triage.open_count(db) == 4

    world["missing"].project_link = PROJECT_LINK_OK
    world["missing"].project_uid = project.id
    db.flush()

    result = triage.classify(db)
    assert result["closed"] == 1
    assert triage.open_count(db) == 3


def test_a_person_assigning_the_project_runs_the_numbering(db, world, project, make_user):
    """관리자가 소속을 정하는 **그 순간** 채번이 돌고 표시 이름이 생긴다 (D-197).

    자동으로 안 하는 일을 사람이 하는 자리다. 여기가 없으면 예외 티켓은 영원히
    이름 없는 상태로 남는다.
    """
    triage.classify(db)
    ticket = world["ambiguous"]
    admin = make_user("triage-admin@goodmit.co.kr", role="admin")

    result = triage.assign(
        db, ticket_id=ticket.id, project_id=project.id, actor_id=admin.id
    )
    db.refresh(ticket)

    # 코드를 서버가 지으므로 기대값도 그 프로젝트가 실제로 받은 코드에서 만든다.
    expected_key = f"{project.code}-1"
    assert result["seq"] == 1 and result["canonical_key"] == expected_key
    assert ticket.project_uid == project.id and ticket.canonical_key == expected_key

    row = (
        db.query(MigrationException)
        .filter(MigrationException.ticket_id == ticket.id)
        .one()
    )
    assert row.resolved_at is not None and row.resolved_by == admin.id
    assert triage.open_count(db) == 3


def test_reason_for_is_a_pure_judgement(db, project):
    """판정은 순수 함수다 — 화면과 분류가 **같은 판정**을 쓴다.

    DB 를 안 보므로 행 하나로 직접 확인할 수 있고, 두 소비자가 갈라질 자리가 없다.
    """
    from datetime import datetime

    healthy = Ticket(
        title="정상", project_link=PROJECT_LINK_OK, project_uid=project.id,
        org_id=DEFAULT_ORG_ID,
    )
    assert triage.reason_for(healthy) is None

    healthy.notion_missing_at = datetime(2026, 8, 1)
    assert triage.reason_for(healthy) == EXC_SOURCE_MISSING

    healthy.project_link = PROJECT_LINK_AMBIGUOUS
    assert triage.reason_for(healthy) == EXC_AMBIGUOUS, (
        "두 이유가 겹치면 **채번을 막는 쪽**이 사유다"
    )
