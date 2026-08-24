"""사용자 셀프서비스 티켓 수동 편집(쓰기) 유닛 테스트.

## 무엇이 달라졌고 무엇이 그대로인가 (S14)

예전에는 이 파일이 가짜 Notion 서버를 세워 두고 **PATCH 페이로드**를 검사했다. 티켓의
정본이 이 서버의 `tickets` 표로 옮겨 왔으므로, 이제는 표본을 그 표에 심고 **저장된 행**을
검사한다. 판정 대상만 옮겼을 뿐 이 파일이 지키는 것은 그대로다: 소유권(남의 티켓은 못
고친다·운영자는 우회한다·미할당은 누구나), 값 검증(모르는 상태·빈 제목·프로젝트 분리),
담당자 해석과 **외부 담당자 보존**, 그리고 편집 가능한 필드가 하나도 빠짐없이 실제로
저장되는가.

마지막 항목이 특히 중요하다. 예전에는 노션 속성 별칭표에 이름이 빠지면 화면에서는 저장된
것처럼 보이고 값만 사라졌다. 지금은 그 자리가 저장소의 도메인 키 분기이고, 증상은 그때와
똑같다 — 그래서 API 가 받는 필드 전부를 한 건씩 저장해 보고 행이 실제로 바뀌는지 본다.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import ForbiddenError, TicketNotFoundError, ValidationAppError
from app.core.models_base import join_names
from app.notion_mapping.models import STATUS_UNMAPPED, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets import service
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.tickets.schemas import TicketUpdate

pytestmark = pytest.mark.unit

PAGE_ID = "page-1"


@pytest.fixture()
def project(make_project):
    """이 파일의 모든 티켓이 붙어 있는 Portal 프로젝트(조직 공통).

    0060 부터 티켓의 조직 소속은 프로젝트가 정한다 — 프로젝트가 없으면 그 티켓은
    어느 범위에도 안 잡히는 유령이라 쓰기 경로가 404 로 막는다. 이 파일이 검사하려는
    것은 그 게이트가 아니라 편집 동작이므로, 정상 소속을 미리 만들어 둔다.
    """
    return make_project(name="알파", external_id="px-1")


def _seed(db, project, *, people=None, tid=42, title="샘플", status="진행",
          due="2026-09-01", est=2.0, diff="보통", prio="보통") -> TicketCache:
    """편집 대상 티켓 한 건을 자체 DB 표에 심는다."""
    row = TicketCache(
        notion_page_id=PAGE_ID,
        org_id=project.org_id,
        notion_ticket_number=tid,
        url=f"https://example.invalid/{PAGE_ID}",
        title=title,
        status=status,
        due_date=date.fromisoformat(due) if due else None,
        est_wd=est,
        difficulty=diff,
        priority=prio,
        project_ids=join_names(["px-1"]),
        project_names=join_names([project.name]),
        project_uid=project.id,
        project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names(people or []),
    )
    db.add(row)
    db.commit()
    return row


def _map(db, user, notion_id, status=STATUS_VERIFIED):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=status))
    db.commit()


def _edit(db, settings, user, changes, *, page_id=PAGE_ID):
    """자체 DB 저장소는 `outbound` 를 쓰지 않으므로 넘기지 않는다."""
    return service.update_ticket(db, None, settings, user, page_id=page_id, changes=changes)


def _row(db) -> TicketCache:
    db.expire_all()
    return service.ticket_row_for(db, PAGE_ID)


# ── 소유권 ──────────────────────────────────────────────────────────────────

def test_update_forbidden_when_not_owner(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-other"])  # 남의 티켓
    with pytest.raises(ForbiddenError):
        _edit(db, settings, me, {"est_wd": 3.0})
    assert _row(db).est_wd == 2.0  # 쓰기까지 못 감


def test_update_allowed_for_owner(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    out = _edit(db, settings, me, {"est_wd": 5.0})
    assert _row(db).est_wd == 5.0
    assert out["before"]["est_wd"] == 2.0


def test_update_allowed_for_unassigned(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")  # 매핑 없어도 됨
    _seed(db, project, people=[])
    _edit(db, settings, me, {"priority": "높음"})
    assert _row(db).priority == "높음"


def test_bypass_role_can_edit_others(db, settings, make_user, project):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    _seed(db, project, people=["notion-other"])
    _edit(db, settings, op, {"status": "완료"})
    assert _row(db).status == "완료"


# ── 값 검증 ─────────────────────────────────────────────────────────────────

def test_no_changes_rejected(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, me, {})


def test_invalid_status_rejected(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, me, {"status": "없는상태"})
    assert _row(db).status == "진행"


def test_empty_status_rejected(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, me, {"status": ""})
    assert _row(db).status == "진행"


def test_due_date_clear_stores_null(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    _edit(db, settings, me, {"due_date": ""})
    assert _row(db).due_date is None


def test_difficulty_clear_stores_null(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    _edit(db, settings, me, {"difficulty": ""})
    assert _row(db).difficulty is None


def test_ticket_not_found(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    with pytest.raises(TicketNotFoundError):
        _edit(db, settings, me, {"est_wd": 1.0}, page_id="nope")


# ── 담당자 해석·보존 ─────────────────────────────────────────────────────────

def test_assignee_resolved_and_external_preserved(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    mate = make_user(email="mate@goodmit.co.kr", display_name="동료", role="user")
    _map(db, me, "notion-me")
    _map(db, mate, "notion-mate")
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")  # 우회
    # 현재 담당자: 외부 미연결 + 동료(앱 사용자). 나에게 재배정 → 동료는 빠지고 외부는 보존.
    _seed(db, project, people=["ext-unmapped", "notion-mate"])
    _edit(db, settings, op, {"assignee_user_ids": [me.id]})
    assert _row(db).assignee_notion_ids == join_names(["ext-unmapped", "notion-me"])


def test_assignee_clear_keeps_external(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    _seed(db, project, people=["ext-unmapped", "notion-me"])
    _edit(db, settings, op, {"assignee_user_ids": []})
    # 앱 사용자만 비우고 외부는 유지
    assert _row(db).assignee_notion_ids == join_names(["ext-unmapped"])


def test_assignee_unknown_user_rejected(db, settings, make_user, project):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    _seed(db, project, people=[])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, op, {"assignee_user_ids": ["no-such-user"]})


def test_assignee_unverified_user_rejected(db, settings, make_user, project):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ghost = make_user(email="ghost@goodmit.co.kr", display_name="유령", role="user")
    _map(db, ghost, "notion-ghost", status=STATUS_UNMAPPED)  # 미검증 → 후보 아님
    _seed(db, project, people=[])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, op, {"assignee_user_ids": [ghost.id]})


# ── claim ───────────────────────────────────────────────────────────────────

def test_claim_requires_mapping(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")  # 매핑 없음
    _seed(db, project, people=[])
    with pytest.raises(ValidationAppError):
        service.claim_ticket(db, None, settings, me, page_id=PAGE_ID)


def test_claim_assigns_me(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=[])
    out = service.claim_ticket(db, None, settings, me, page_id=PAGE_ID)
    assert _row(db).assignee_notion_ids == join_names(["notion-me"])
    assert me.id in out["ticket"]["assignee_user_ids"]


def test_claim_forbidden_on_others_ticket(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-other"])  # 남이 이미 담당
    with pytest.raises(ForbiddenError):
        service.claim_ticket(db, None, settings, me, page_id=PAGE_ID)


# ── meta ────────────────────────────────────────────────────────────────────

def test_meta_statuses_are_the_products_vocabulary(db, settings, project):
    """진행상태의 정본은 제품(`app/work/workflow.py`)이다.

    예전에는 이 목록이 노션 스키마의 select 옵션이었다 — 워크스페이스에서 옵션 하나가
    사라지면 포털의 드롭다운도 조용히 달라졌다. 우선순위·난이도는 아직 제품 어휘가
    없어서 지금 데이터에 실제로 쓰인 값에서 나온다.
    """
    _seed(db, project, prio="높음", diff="어려움")
    meta = service.ticket_meta(None, settings, db)
    assert meta["statuses"] == ["계획", "이슈", "진행", "검증", "완료", "취소"]
    assert meta["priorities"] == ["높음"]
    assert meta["difficulties"] == ["어려움"]


# ── 제품화: 편집 가능한 속성을 전부 포털에서 고친다 (2026-08-04 지시) ──────────────
#
# 예전에는 제목·프로젝트·실제 WD·시작일·대분류가 쓰기 계약에 아예 없었다. 그중 하나만
# 고치려 해도 노션을 열어야 했고, 그게 "DB 에 접근하지 않아도 업무를 관리한다"를 막고 있었다.
# 지금 그 자리는 저장소의 도메인 키 분기다. 이름이 하나 어긋나면 저장소가 그 키를 조용히
# 건너뛰고, 화면에서는 저장된 것처럼 보인다 — 증상이 그때와 똑같으므로 같은 방식으로 막는다.

#: API 필드 → (보낼 값, 저장 뒤 행에서 확인할 컬럼, 기대값). `assignee_user_ids` 와
#: `project_id` 는 값이 시험 안에서 만들어지므로 아래 함수가 따로 넣는다.
_FIELD_CASES = {
    "title": ("고친 제목", "title", "고친 제목"),
    "est_wd": (7.5, "est_wd", 7.5),
    "act_wd": (3.5, "act_wd", 3.5),
    "difficulty": ("어려움", "difficulty", "어려움"),
    "priority": ("높음", "priority", "높음"),
    "status": ("완료", "status", "완료"),
    "due_date": ("2026-10-01", "due_date", date(2026, 10, 1)),
    "start_date": ("2026-09-01", "start_date", date(2026, 9, 1)),
    "category": ("인프라", "category", "인프라"),
}


def test_every_editable_field_actually_reaches_the_row(db, settings, make_user, make_project,
                                                       project):
    """API 가 받는 편집 필드가 **하나도 빠짐없이** 행까지 도달하는지 본다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    target = make_project(name="베타", external_id="px-2")
    _seed(db, project, people=["notion-me"])

    # 계약에 있는 필드와 여기서 확인하는 필드가 어긋나면 먼저 그것부터 알려 준다.
    covered = set(_FIELD_CASES) | {"assignee_user_ids", "project_id"}
    assert set(TicketUpdate.model_fields) == covered, (
        "편집 계약이 바뀌었다 — 이 시험이 확인하는 필드 목록을 함께 고쳐라: "
        f"{sorted(set(TicketUpdate.model_fields) ^ covered)}"
    )

    for field, (sent, column, expected) in _FIELD_CASES.items():
        _edit(db, settings, me, {field: sent})
        assert getattr(_row(db), column) == expected, f"{field} 가 저장되지 않았다"

    _edit(db, settings, me, {"assignee_user_ids": [me.id]})
    assert _row(db).assignee_notion_ids == join_names(["notion-me"])

    _edit(db, settings, me, {"project_id": target.id})
    row = _row(db)
    assert row.project_uid == target.id, "Portal 프로젝트 id 가 소속으로 옮겨지지 않았다"
    assert row.project_ids == join_names(["px-2"])


def test_title_cannot_be_emptied(db, settings, make_user, project):
    """제목을 비우면 목록에서 그 티켓이 '(제목 없음)'이 된다 — 실수지 뜻이 아니다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    _seed(db, project, people=["notion-me"])
    with pytest.raises(ValidationAppError):
        _edit(db, settings, me, {"title": "  "})
    assert _row(db).title == "샘플"


def test_project_can_be_moved_but_never_detached(db, settings, make_user, make_project, project):
    """프로젝트는 **옮길 수는 있어도 뗄 수는 없다** (0060).

    예전에는 빈 값이 '연결 해제' 였다. 티켓의 조직 소속을 프로젝트가 정하는 이상 그건
    그 티켓을 어느 범위에도 안 잡히는 유령으로 만드는 동작이라 막는다 — 소속을 지우는
    것과 옮기는 것은 다른 일이다.
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    make_project(name="베타", external_id="px-2")
    _seed(db, project, people=["notion-me"])

    with pytest.raises(ValidationAppError):
        _edit(db, settings, me, {"project_id": ""})
    assert _row(db).project_uid == project.id
