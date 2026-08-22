"""`GIT-142` 는 **영원히 같은 티켓으로 간다** (D-195 · MASTER_PLAN §9.1 S6 Exit).

## 무엇이 걸려 있는가

옛 티켓 번호는 문서·대화·메일·커밋 메시지에 이미 뿌려져 있다. Project Key 를 새로
정하고 번호를 다시 매기는 순간 그 링크들이 전부 죽으면, 이 전환은 사람들에게
「기록이 사라진 사건」이 된다. 3층 식별자가 있는 이유가 그것 하나다.

## 순서가 계약이다

`canonical_key` → `legacy_key` → `alias` → `uuid`. 순서를 바꾸면 같은 문자열이
다른 티켓으로 갈 수 있다. 그래서 「찾았다」뿐 아니라 **어느 층이 답했는지**까지 본다 —
찾기만 확인하면 순서가 뒤집혀도 통과한다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import keys as keys_mod
from app.work import numbering
from app.work.models import ALIAS_LEGACY, ALIAS_SUPERSEDED, KEY_RETIRED, TicketKeyAlias
from app.work.resolve import BY_ALIAS, BY_CANONICAL, BY_LEGACY, BY_UUID, resolve

pytestmark = pytest.mark.regression


@pytest.fixture()
def project(db):
    row = Project(
        name="SK하이닉스 용인", code=None, org_id=DEFAULT_ORG_ID,
        notion_page_id="proj-page-1",
    )
    db.add(row)
    db.flush()
    keys_mod.claim(db, project_id=row.id, key="SKH")
    db.flush()
    return row


@pytest.fixture()
def ticket(db, project):
    """옛 이름이 `GIT-142` 인 티켓 하나. 아직 번호는 없다 — 이관 전 상태다."""
    row = Ticket(
        title="용인 클러스터 대비", project_uid=project.id, project_link=PROJECT_LINK_OK,
        notion_page_id="page-142", notion_ticket_number=142, legacy_key="GIT-142",
        org_id=DEFAULT_ORG_ID, source="notion",
    )
    db.add(row)
    db.flush()
    db.add(
        TicketKeyAlias(alias="GIT-142", ticket_id=row.id, kind=ALIAS_LEGACY)
    )
    db.flush()
    return row


def test_legacy_key_resolves_before_numbering(db, ticket):
    """번호를 받기 전에도 옛 이름으로 찾을 수 있다."""
    found = resolve(db, "GIT-142")
    assert found is not None
    assert found.ticket.id == ticket.id
    assert found.matched_by == BY_LEGACY
    # 지금 이 티켓을 부르는 이름이 옛 이름이라는 것을 화면이 알아야 한다.
    assert found.is_current_name is False


def test_legacy_key_still_resolves_after_numbering(db, project, ticket):
    """번호가 붙어도 옛 이름은 **그대로 산다.**

    새 canonical 이 생기는 것과 옛 이름이 죽는 것은 다른 일이다. 여기서 갈라지면
    「이관 이후 옛 링크가 안 된다」가 된다.
    """
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    db.refresh(ticket)
    assert ticket.canonical_key == "SKH-1"

    by_new = resolve(db, "SKH-1")
    assert by_new is not None and by_new.ticket.id == ticket.id
    assert by_new.matched_by == BY_CANONICAL and by_new.is_current_name

    by_old = resolve(db, "GIT-142")
    assert by_old is not None and by_old.ticket.id == ticket.id
    assert by_old.matched_by == BY_LEGACY


def test_project_key_change_keeps_every_old_link_alive(db, project, ticket):
    """Key 를 바꿔도 **옛 canonical 과 옛 legacy 가 둘 다 같은 티켓으로 간다** (D-195).

    이것이 `keys.change()` 의 존재 이유다. 별칭 복사 없이 `projects.code` 만 고치면
    옛 `SKH-1` 은 404 도 아니고 **아무 데도 없는 이름**이 된다.
    """
    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    db.refresh(ticket)
    assert ticket.canonical_key == "SKH-1"

    result = keys_mod.change(db, project_id=project.id, key="HYNIX")
    db.flush()
    db.refresh(ticket)

    assert result["changed"] and result["old_key"] == "SKH" and result["new_key"] == "HYNIX"
    assert ticket.canonical_key == "HYNIX-1", "트리거가 새 Key 로 다시 계산해야 한다"

    for token, expected_layer in (
        ("HYNIX-1", BY_CANONICAL),
        ("SKH-1", BY_ALIAS),
        ("GIT-142", BY_LEGACY),
        (ticket.id, BY_UUID),
    ):
        found = resolve(db, token)
        assert found is not None, f"«{token}» 이 아무 데도 닿지 않는다"
        assert found.ticket.id == ticket.id
        assert found.matched_by == expected_layer, (
            f"«{token}» 은 {expected_layer} 층이 답해야 하는데 {found.matched_by} 가 답했다"
        )

    superseded = db.get(TicketKeyAlias, "SKH-1")
    assert superseded is not None and superseded.kind == ALIAS_SUPERSEDED


def test_old_key_is_retired_not_released(db, project, ticket):
    """옛 Key 는 **해제되지 않는다.** 다른 프로젝트가 가져갈 수 없어야 한다 (D-196).

    가져갈 수 있으면 그쪽의 `SKH-1` 이 이쪽의 옛 `SKH-1` 과 같은 문자열이 되고,
    그때 그 링크가 어느 티켓을 가리키는지는 아무도 답할 수 없다.
    """
    from app.core.errors import ConflictError

    ticket.seq = numbering.allocate(db, project.id)
    db.flush()
    keys_mod.change(db, project_id=project.id, key="HYNIX")
    db.flush()

    retired = keys_mod.find(db, "SKH")
    assert retired is not None and retired.state == KEY_RETIRED

    other = Project(name="다른 회사", org_id=DEFAULT_ORG_ID)
    db.add(other)
    db.flush()
    with pytest.raises(ConflictError):
        keys_mod.claim(db, project_id=other.id, key="SKH")


def test_reserved_git_namespace_can_never_be_claimed(db):
    """`GIT` 은 어떤 프로젝트도 못 가져간다 (D-196).

    가져가면 새로 발급한 `GIT-142` 가 옛 `GIT-142` 와 같은 문자열이 되고, 그 순간
    Resolution 순서가 두 티켓 사이에서 조용히 갈린다.
    """
    from app.core.errors import ConflictError

    row = Project(name="깃 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.flush()
    with pytest.raises(ConflictError):
        keys_mod.claim(db, project_id=row.id, key="git")


def test_resolution_is_case_insensitive_for_keys(db, ticket):
    """`git-142` 도 같은 티켓이다. Key 는 **대소문자 무관 유일**이다 (§5.2)."""
    found = resolve(db, "git-142")
    assert found is not None and found.ticket.id == ticket.id


def test_unknown_tokens_resolve_to_nothing(db, ticket):
    """**반례** — 없는 이름은 못 찾아야 한다.

    이것이 없으면 위 시험들이 「무엇을 넣어도 이 티켓이 나오는」 구현에도 초록을 찍는다.
    """
    for token in ("ZZZ-1", "GIT-999", "", None, "not-a-uuid", "SKH-"):
        assert resolve(db, token) is None, f"«{token}» 이 무언가로 해석됐다"


def test_canonical_cannot_be_written_by_the_application(db, project, ticket):
    """앱이 `canonical_key` 에 무엇을 적든 **트리거가 덮어쓴다** (D-195).

    이 성질이 「어긋날 수 없다」의 근거다. 주석으로 약속하는 대신 DB 가 강제한다.
    """
    ticket.seq = numbering.allocate(db, project.id)
    ticket.canonical_key = "WRONG-999"
    db.flush()
    db.refresh(ticket)
    assert ticket.canonical_key == "SKH-1"
