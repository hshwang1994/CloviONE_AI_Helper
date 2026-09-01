"""신호(`이슈 있음` · `차단됨`)를 켜고 끄는 경로 (D-349).

셋 중 둘은 **사람이 켜는 값**이다(`docs/ui-redesign/PLAN.md` §1). 그래서 이 파일이
지키는 것은 「저장되는가」 하나가 아니라 셋이다:

  * 사유는 **차단이 켜진 뒤의 상태**를 기준으로 남는다 — 요청 안의 키 순서와 무관하게.
  * 차단을 풀면 사유도 함께 사라진다. 지난 이유가 다음 차단에 붙어 나오면 그 말은 이미 틀렸다.
  * 켠 사실이 **감사 스냅샷에 남는다.** 남지 않으면 「누가 언제 이 티켓을 이슈로
    표시했나」에 답할 자리가 제품에 없다.

세 번째가 이 회차에 비어 있던 자리다. `snapshot()` 이 신호 둘을 안 실어서, 이슈를 켠
편집은 감사 로그에 「아무것도 안 바뀐 저장」으로 남았다.
"""

from __future__ import annotations

import pytest

from app.core.models_base import join_names
from app.tickets import service
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.tickets.repository import snapshot
from app.tickets.schemas import TicketUpdate

pytestmark = pytest.mark.unit

PAGE_ID = "sig-page-1"


@pytest.fixture()
def project(make_project):
    return make_project(name="알파", external_id="px-sig")


def _seed(db, project, **extra) -> TicketCache:
    row = TicketCache(
        notion_page_id=PAGE_ID,
        org_id=project.org_id,
        notion_ticket_number=7,
        url=f"https://example.invalid/{PAGE_ID}",
        title="신호 표본",
        status="진행",
        project_ids=join_names(["px-sig"]),
        project_names=join_names([project.name]),
        project_uid=project.id,
        project_link=PROJECT_LINK_OK,
        assignee_notion_ids="",
        **extra,
    )
    db.add(row)
    db.commit()
    return row


def _row(db) -> TicketCache:
    db.expire_all()
    return service.ticket_row_for(db, PAGE_ID)


def _edit(db, settings, user, changes):
    """API 가 받는 모양 그대로 지나간다 — `model_dump(exclude_unset=True)` 까지 같다."""
    payload = TicketUpdate(**changes)
    return service.update_ticket(
        db, None, settings, user, page_id=PAGE_ID,
        changes=payload.model_dump(exclude_unset=True),
    )


@pytest.fixture()
def editor(make_user):
    return make_user(email="sig@goodmit.co.kr", display_name="편집자", role="user")


def test_issue_flag_turns_on_and_off(db, settings, editor, project):
    _seed(db, project)

    _edit(db, settings, editor, {"issue_flag": True})
    assert _row(db).issue_flag is True

    _edit(db, settings, editor, {"issue_flag": False})
    assert _row(db).issue_flag is False


def test_blocked_reason_survives_when_it_precedes_the_flag(db, settings, editor, project):
    """사유가 깃발보다 **먼저** 와도 저장된다.

    저장소는 변경 dict 를 순서대로 훑는다. 사유를 적용할 때 그 순간의 차단 여부를 보므로,
    이 판정이 순서 안에 있으면 「막혔다 + 이유」를 한 번에 보낸 저장에서 이유만 조용히
    사라진다. 지금은 요청 스키마의 필드 순서가 우연히 지켜 주고 있을 뿐이라, 그 우연을
    빼고도 참인지 여기서 직접 잰다.
    """
    _seed(db, project)

    repo = service._repo(settings, None, None)
    repo.update(
        db, page_id=PAGE_ID,
        changes={"blocked_reason": "배포 승인 대기", "blocked_flag": True},
    )
    db.commit()

    row = _row(db)
    assert row.blocked_flag is True
    assert row.blocked_reason == "배포 승인 대기"


def test_unblocking_clears_the_reason(db, settings, editor, project):
    _seed(db, project, blocked_flag=True, blocked_reason="외부 응답 대기")

    _edit(db, settings, editor, {"blocked_flag": False})

    row = _row(db)
    assert row.blocked_flag is False
    assert row.blocked_reason is None, "차단을 풀었는데 지난 이유가 남았다"


def test_reason_without_the_flag_is_not_stored(db, settings, editor, project):
    """차단이 꺼진 채 사유만 보내면 안 남는다 — 어느 화면에도 안 나오는 글이 된다."""
    _seed(db, project)

    _edit(db, settings, editor, {"blocked_reason": "혼자 적어 둔 말"})

    assert _row(db).blocked_reason is None


def test_audit_snapshot_carries_the_signals(db, settings, editor, project):
    """켠 사실이 감사 before/after 에 남는다.

    🔴 안 남았다. `snapshot()` 이 status·due·assignees·est_wd·difficulty·priority 여섯만
    실어서, 이슈를 켠 편집은 before 와 after 가 **완전히 같은** 기록으로 남았다 — 이력
    화면은 「바뀐 것만」 말하므로 그 줄에는 아무 변화도 안 보였다.
    """
    _seed(db, project)

    result = _edit(db, settings, editor, {"issue_flag": True})

    assert result["before"]["issue"] is False
    assert result["after"]["issue"] is True
    # 차단도 같은 자리에 실린다 — 둘 다 사람이 켜는 값이다.
    assert "blocked" in result["before"] and "blocked" in result["after"]


def test_history_reads_the_flags_as_korean(db, settings, editor, project):
    """이력에는 「켜짐 / 꺼짐」으로 나간다. `str(False)` 는 화면에 「False」로 나간다."""
    assert service.HISTORY_FIELDS["issue"] == "이슈 있음"
    assert service.HISTORY_FIELDS["blocked"] == "차단됨"
    assert service._history_value("issue", True, {}) == "켜짐"
    assert service._history_value("issue", False, {}) == "꺼짐"
    assert service._history_value("blocked", False, {}) == "꺼짐"


def test_snapshot_is_a_superset_of_the_history_fields():
    """이력이 이름을 붙인 칸은 **스냅샷에 실제로 실려야** 한다.

    둘이 어긋나면 이력 화면은 그 칸을 영원히 안 보여 주고, 아무 오류도 안 난다.
    `assignees` 는 스냅샷 키 이름이 그대로 이력 키다 — 여기서 함께 잰다.
    """
    from app.tickets.repository import TicketDTO

    keys = set(snapshot(TicketDTO(page_id="x", key="X-1", title="t")))
    missing = set(service.HISTORY_FIELDS) - keys
    assert not missing, "이력이 이름 붙인 칸이 스냅샷에 없다: %s" % sorted(missing)
