"""관리자 백로그 잔여 API (0033, PLAN Phase 6) — 승인 위임·SLA, 스케줄러 캘린더,
시스템 상태 배너, 공지, AI 쿼터, 기능 플래그, 감사 이상탐지·내보내기·저장 필터,
백업 일정·복구 리허설.

각 테스트는 **화면이 실제로 쓰는 응답**을 본다(내부 함수가 아니라). 그래야 계약이 바뀌면
화면보다 먼저 여기가 빨개진다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration


def _h(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


# ── 공지 배너 ────────────────────────────────────────────────────────────────


def test_announcement_lifecycle_and_dismissal(client, login_as, make_user):
    """관리자가 띄우고, 사용자가 닫으면 다시 안 뜬다 — 그리고 그 사실이 서버에 남는다."""
    csrf = login_as("system_admin")
    created = client.post(
        "/api/admin/announcements",
        json={"title": "정기 점검 안내", "body": "토요일 02:00~04:00", "level": "warning"},
        headers=_h(csrf),
    )
    assert created.status_code == 201, created.text
    announcement_id = created.json()["id"]

    # 관리자 콘솔에서도 보인다.
    mine = client.get("/api/announcements").json()["items"]
    assert [a["id"] for a in mine] == [announcement_id]

    dismissed = client.post(
        f"/api/announcements/{announcement_id}/dismiss", headers=_h(csrf)
    )
    assert dismissed.status_code == 200 and dismissed.json()["dismissed"] is True
    assert client.get("/api/announcements").json()["items"] == []

    # 멱등: 두 번 닫아도 오류가 아니고 행도 늘지 않는다.
    again = client.post(f"/api/announcements/{announcement_id}/dismiss", headers=_h(csrf))
    assert again.status_code == 200 and again.json()["dismissed"] is False


def test_announcement_search_matches_title_or_body(client, login_as):
    """UB-24: 화면 설정에 searchFields/searchPlaceholder가 이미 있었는데 searchable이
    빠져 있어(그래서 백엔드도 q를 몰랐다) 검색창 자체가 안 그려졌다 — 제목으로 배너를
    찾을 방법이 없었다."""
    csrf = login_as("system_admin")
    client.post(
        "/api/admin/announcements",
        json={"title": "정기 점검 안내", "body": "토요일 새벽에 점검합니다", "level": "info"},
        headers=_h(csrf),
    )
    client.post(
        "/api/admin/announcements",
        json={"title": "신규 기능 안내", "body": "게시판 검색이 추가됐습니다", "level": "info"},
        headers=_h(csrf),
    )

    by_title = client.get("/api/admin/announcements?q=점검").json()
    assert [a["title"] for a in by_title["items"]] == ["정기 점검 안내"]

    by_body = client.get("/api/admin/announcements?q=게시판").json()
    assert [a["title"] for a in by_body["items"]] == ["신규 기능 안내"]

    no_match = client.get("/api/admin/announcements?q=존재하지않는단어").json()
    assert no_match["items"] == []


def test_announcement_window_and_audience(client, login_as):
    csrf = login_as("system_admin")
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    client.post(
        "/api/admin/announcements",
        json={"title": "아직 시작 안 함", "starts_at": future},
        headers=_h(csrf),
    )
    client.post(
        "/api/admin/announcements",
        json={"title": "관리자 전용", "audience": "admin"},
        headers=_h(csrf),
    )
    titles = [a["title"] for a in client.get("/api/announcements").json()["items"]]
    assert "아직 시작 안 함" not in titles, "시작 전 공지가 노출됐다"
    assert "관리자 전용" in titles


# UB-06: starts_at >= ends_at 인 창은 in_window()가 항상 False를 내는(=영원히 아무도
# 못 보는) 죽은 공지를 만든다. 서버가 만들 때/고칠 때 둘 다 막아야 한다.


def test_creating_an_announcement_with_a_reversed_window_is_rejected(client, login_as):
    csrf = login_as("system_admin")
    now = datetime.now(timezone.utc)
    starts = now + timedelta(days=2)
    ends = now + timedelta(days=1)  # 시작보다 앞선 종료 — 뒤집힌 창
    r = client.post(
        "/api/admin/announcements",
        json={
            "title": "뒤집힌 창", "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
        },
        headers=_h(csrf),
    )
    assert r.status_code == 422, f"뒤집힌 창이 그대로 통과했다: {r.text}"


def test_equal_starts_and_ends_is_also_rejected(client, login_as):
    """starts_at == ends_at 도 폭이 0인 창이라 in_window()가 항상 False다."""
    csrf = login_as("system_admin")
    same = datetime.now(timezone.utc).isoformat()
    r = client.post(
        "/api/admin/announcements",
        json={"title": "폭 0인 창", "starts_at": same, "ends_at": same},
        headers=_h(csrf),
    )
    assert r.status_code == 422, f"폭 0인 창이 그대로 통과했다: {r.text}"


def test_patching_only_ends_at_past_the_existing_starts_at_is_rejected(client, login_as):
    """한쪽만 고쳐도 이미 저장된 다른 쪽과 뒤집힐 수 있다 — PATCH도 결과 창을 봐야 한다."""
    csrf = login_as("system_admin")
    now = datetime.now(timezone.utc)
    created = client.post(
        "/api/admin/announcements",
        json={
            "title": "정상 창",
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=5)).isoformat(),
        },
        headers=_h(csrf),
    )
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"ends_at": now.isoformat()},  # starts_at(now+1일)보다 앞선 값
        headers=_h(csrf),
    )
    assert r.status_code == 422, f"PATCH가 결과 창이 뒤집히는데도 통과했다: {r.text}"
    # 거부됐으니 저장값은 원래 그대로여야 한다.
    unchanged = client.get("/api/admin/announcements").json()
    row = next(a for a in unchanged["items"] if a["id"] == row_id)
    assert row["ends_at"] is not None and row["ends_at"] != now.isoformat()


def test_a_valid_window_edit_still_works(client, login_as):
    """검증을 추가했다고 정상 창까지 막히면 안 된다."""
    csrf = login_as("system_admin")
    now = datetime.now(timezone.utc)
    created = client.post(
        "/api/admin/announcements",
        json={
            "title": "정상 창 2",
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=5)).isoformat(),
        },
        headers=_h(csrf),
    )
    row_id = created.json()["id"]

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"ends_at": (now + timedelta(days=10)).isoformat()},
        headers=_h(csrf),
    )
    assert r.status_code == 200, f"정상적인 창 연장이 거부됐다: {r.text}"


def test_non_dismissible_announcement_refuses_dismiss(client, login_as):
    csrf = login_as("system_admin")
    row = client.post(
        "/api/admin/announcements",
        json={"title": "필수 공지", "dismissible": False},
        headers=_h(csrf),
    ).json()
    response = client.post(f"/api/announcements/{row['id']}/dismiss", headers=_h(csrf))
    assert response.status_code == 409


def test_regular_user_sees_only_audience_all(client, login_as, make_user):
    admin_csrf = login_as("system_admin")
    client.post(
        "/api/admin/announcements",
        json={"title": "모두에게", "audience": "all"},
        headers=_h(admin_csrf),
    )
    client.post(
        "/api/admin/announcements",
        json={"title": "관리자만", "audience": "admin"},
        headers=_h(admin_csrf),
    )
    client.post("/logout", headers=_h(admin_csrf))
    login_as("user")
    titles = [a["title"] for a in client.get("/api/announcements").json()["items"]]
    assert titles == ["모두에게"]
    # 일반 사용자는 관리 API 에 닿지 못한다.
    assert client.get("/api/admin/announcements").status_code == 403


# ── 승인 위임 + SLA ──────────────────────────────────────────────────────────


def test_approval_gets_due_at_and_reports_overdue(client, login_as, db, fake_clock):
    """기한이 붙고, 지나면 목록이 overdue 로 말한다 — 만료와는 다른 축이다."""
    from app.approvals.models import DEFAULT_SLA_HOURS, Approval
    from app.approvals.service import create_approval
    from app.users.models import User
    from sqlalchemy import select

    csrf = login_as("system_admin")
    actor = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    now = fake_clock.now()
    row = create_approval(
        db, request_type="user.role_change", object_type="user", object_id=actor.id,
        requested_by=actor, payload={"role": "operator"}, now=now,
    )
    db.commit()
    assert row.due_at == now + timedelta(hours=DEFAULT_SLA_HOURS)

    response = client.get("/api/admin/approvals")
    assert response.status_code == 200, response.text
    listed = response.json()["items"][0]
    assert listed["due_at"] is not None and listed["overdue"] is False

    # 기한을 넘긴 상태를 만든다. **시계를 앞으로 돌리지 않는다** — 세션 유휴 만료(30분)에
    # 걸려 다음 요청이 401 이 되고, 그러면 이 테스트가 SLA 가 아니라 세션을 시험하게 된다.
    # 대신 행의 기한을 과거로 옮긴다(만료 시각은 그대로 두어 '만료'와 구분되게).
    stored = db.get(Approval, row.id)
    stored.due_at = now - timedelta(hours=1)
    db.commit()

    listed = client.get("/api/admin/approvals").json()["items"][0]
    assert listed["overdue"] is True, "기한이 지났는데 overdue 가 아니다"
    assert listed["status"] == "pending", "기한 초과가 만료로 오인됐다"
    # 상세도 같은 답을 준다(목록과 상세가 갈리면 관리자가 어느 쪽을 믿을지 모른다).
    detail = client.get(f"/api/admin/approvals/{row.id}").json()["approval"]
    assert detail["overdue"] is True


def test_delegation_lets_a_non_admin_decide_and_records_on_behalf_of(
    client, login_as, make_user, db, fake_clock
):
    from sqlalchemy import select

    from app.approvals.service import create_approval
    from app.users.models import User

    admin_csrf = login_as("system_admin")
    admin = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    operator = make_user(email="stand-in@goodmit.co.kr", role="operator")
    operator_id = operator.id
    admin_id = admin.id

    target = make_user(email="promote-me@goodmit.co.kr", role="user")
    now = fake_clock.now()
    approval = create_approval(
        db, request_type="user.role_change", object_type="user", object_id=target.id,
        requested_by=admin, payload={"role": "operator"}, now=now,
    )
    approval_id = approval.id
    db.commit()

    # 위임 전: 운영자는 결재할 수 없다.
    client.post("/logout", headers=_h(admin_csrf))
    op_csrf = login_as("operator", email="stand-in@goodmit.co.kr")
    denied = client.post(f"/api/admin/approvals/{approval_id}/approve", headers=_h(op_csrf))
    assert denied.status_code == 403, denied.text

    # 관리자가 위임한다.
    client.post("/logout", headers=_h(op_csrf))
    admin_csrf = login_as("system_admin")
    created = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": admin_id,
            "delegate_user_id": operator_id,
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=3)).isoformat(),
            "reason": "휴가",
        },
        headers=_h(admin_csrf),
    )
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "active"
    delegation_id = created.json()["id"]

    # 위임 후: 운영자가 결재할 수 있고, 누구를 대신했는지 남는다.
    client.post("/logout", headers=_h(admin_csrf))
    op_csrf = login_as("operator", email="stand-in@goodmit.co.kr")
    approved = client.post(
        f"/api/admin/approvals/{approval_id}/approve", headers=_h(op_csrf)
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()["approval"]
    assert body["status"] == "approved"
    assert body["decided_on_behalf_of"] == admin_id, "대신한 사람이 기록되지 않았다"
    assert body["approver_id"] == operator_id

    # 위임을 거두면 다시 못 한다.
    client.post("/logout", headers=_h(op_csrf))
    admin_csrf = login_as("system_admin")
    revoked = client.post(
        f"/api/admin/approval-delegations/{delegation_id}/revoke", headers=_h(admin_csrf)
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"


def test_delegation_rejects_self_and_non_approver(client, login_as, make_user, db, fake_clock):
    from sqlalchemy import select

    from app.users.models import User

    csrf = login_as("system_admin")
    admin = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    admin_id = admin.id
    plain = make_user(email="plain@goodmit.co.kr", role="user")
    plain_id = plain.id
    now = fake_clock.now()
    window = {
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(days=1)).isoformat(),
    }
    self_delegation = client.post(
        "/api/admin/approval-delegations",
        json={"delegator_user_id": admin_id, "delegate_user_id": admin_id, **window},
        headers=_h(csrf),
    )
    assert self_delegation.status_code == 422

    not_an_approver = client.post(
        "/api/admin/approval-delegations",
        json={"delegator_user_id": plain_id, "delegate_user_id": admin_id, **window},
        headers=_h(csrf),
    )
    assert not_an_approver.status_code == 422


def test_sla_sweep_notifies_once(client, login_as, db, fake_clock):
    from sqlalchemy import func, select

    from app.approvals.delegation import notify_overdue
    from app.approvals.service import create_approval
    from app.notifications.models import Notification
    from app.users.models import User

    login_as("system_admin")
    actor = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    now = fake_clock.now()
    create_approval(
        db, request_type="user.role_change", object_type="user", object_id=actor.id,
        requested_by=actor, payload={"role": "operator"}, now=now,
    )
    db.commit()

    later = now + timedelta(hours=25)
    assert notify_overdue(db, now=later) == 1
    db.commit()
    # 두 번째 스윕은 아무것도 안 보낸다(sla_notified_at).
    assert notify_overdue(db, now=later + timedelta(hours=1)) == 0
    db.commit()
    count = db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.type == "approval_overdue"
        )
    ).scalar_one()
    assert count == 1


# ── 스케줄러 캘린더 ──────────────────────────────────────────────────────────


def test_schedule_calendar_expands_cron_occurrences(client, login_as, db, fake_clock):
    csrf = login_as("system_admin")
    now = fake_clock.now()
    created = client.post(
        "/api/admin/schedules",
        json={
            "name": "매일 아침 리포트",
            "schedule_type": "cron",
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Seoul",
            "target_type": "system",
            "target_ref": "noop",
        },
        headers=_h(csrf),
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["schedule"]["id"]
    enabled = client.post(f"/api/admin/schedules/{schedule_id}/enable", headers=_h(csrf))
    assert enabled.status_code in (200, 202), enabled.text

    start = now.isoformat()
    end = (now + timedelta(days=7)).isoformat()
    body = client.get(f"/api/admin/schedules/calendar?start={start}&end={end}").json()
    planned = [e for e in body["items"] if e["kind"] == "planned"]
    assert 5 <= len(planned) <= 8, f"7일치 매일 일정이 {len(planned)}개다"
    assert all(e["schedule_id"] == schedule_id for e in planned)
    assert body["truncated"] is False
    assert any(s["id"] == schedule_id for s in body["schedules"])


def test_schedule_calendar_rejects_absurd_ranges(client, login_as):
    login_as("system_admin")
    now = datetime.now(timezone.utc)
    bad = client.get(
        "/api/admin/schedules/calendar"
        f"?start={now.isoformat()}&end={(now + timedelta(days=400)).isoformat()}"
    )
    assert bad.status_code == 422
    reversed_range = client.get(
        "/api/admin/schedules/calendar"
        f"?start={now.isoformat()}&end={(now - timedelta(days=1)).isoformat()}"
    )
    assert reversed_range.status_code == 422


# ── 시스템 상태 배너 ─────────────────────────────────────────────────────────


# `setup_complete` 를 쓰는 이유: 갓 마이그레이션한 세계는 부서도 Notion 토큰도 러너도 없어
# '정상'이 아니다. 이제 그 상태에서는 셋업 배너가 뜨므로(9-3), '정상이면 조용하다'를
# 검사하려면 정상인 세계를 먼저 만들어야 한다(tests/conftest.py::setup_complete).
def test_system_status_is_quiet_when_healthy(client, login_as, setup_complete):
    login_as("user")
    body = client.get("/api/system/status").json()
    assert body["notices"] == []
    assert body["poll_seconds"] > 0
    # 일반 사용자에게는 컴포넌트 내부 정보를 주지 않는다.
    assert "components" not in body


def test_system_status_reports_late_ticket_sync(
    client, login_as, db, fake_clock, setup_complete
):
    from app.observability.models import COMPONENT_TICKETS, SYNC_OK
    from app.observability.service import upsert_sync_status

    now = fake_clock.now()
    upsert_sync_status(
        db, COMPONENT_TICKETS, status=SYNC_OK, now=now - timedelta(hours=2), item_count=10
    )
    db.commit()

    login_as("user")
    body = client.get("/api/system/status").json()
    assert len(body["notices"]) == 1
    notice = body["notices"][0]
    assert notice["id"] == "sync.tickets"
    assert notice["level"] == "critical"
    assert "티켓" in notice["message"]
    # 내부 이름·예외는 사용자 문구에 새지 않는다.
    assert "sync_status" not in notice["message"]
    assert "components" not in body


def test_operators_get_component_detail(client, login_as, db, fake_clock):
    from app.observability.models import COMPONENT_TICKETS, SYNC_OK
    from app.observability.service import upsert_sync_status

    upsert_sync_status(
        db, COMPONENT_TICKETS, status=SYNC_OK, now=fake_clock.now(), item_count=3
    )
    db.commit()
    login_as("operator")
    body = client.get("/api/system/status").json()
    assert any(c["component"] == COMPONENT_TICKETS for c in body["components"])


# ── AI 쿼터 ──────────────────────────────────────────────────────────────────


def test_ai_quota_blocks_document_generation_over_the_limit(
    client, login_as, db, fake_clock, make_user
):
    from sqlalchemy import select

    from app.users.models import User
    from app.workflows.models import Workflow

    csrf = login_as("system_admin")
    admin = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    admin_id = admin.id

    workflow = Workflow(name="문서 워크플로", enabled=True, webhook_url="https://n8n.example/hook")
    db.add(workflow)
    db.flush()
    workflow_id = workflow.id
    db.commit()

    quota = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": admin_id, "period": "day", "max_calls": 1},
        headers=_h(csrf),
    )
    assert quota.status_code == 201, quota.text

    first = client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "mode": "preview_only", "period": "2026-08"},
        headers=_h(csrf),
    )
    assert first.status_code == 202, first.text

    second = client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "mode": "preview_only", "period": "2026-08"},
        headers=_h(csrf),
    )
    assert second.status_code == 429, second.text
    assert "상한" in second.json()["error"]["message"]

    # 목록은 상한과 함께 **현재 소비량**을 준다 — 상한만 보면 위험한지 알 수 없다.
    listed = client.get("/api/admin/ai-quotas").json()
    row = [q for q in listed["items"] if q["user_id"] == admin_id][0]
    assert row["used"] == 1 and row["max_calls"] == 1
    # **정확히 일치**를 유지한다(부분집합으로 느슨하게 하지 않는다) — 이 검사가 막는 것은
    # 화면이 "여기에도 상한이 걸린다" 고 **과장**하는 것이고, 부분집합은 그걸 못 잡는다.
    # `chat_message` 는 X11 로 실제로 상한 안에 들어왔다(전송·재시도 두 경로 + 성공분만 계수).
    assert {e["kind"] for e in listed["enforced_on"]} == {
        "assistant_narrative", "document_generate", "chat_message"
    }


def test_ai_quota_absent_means_no_limit(client, login_as, db):
    """상한 행이 없으면 아무 제한도 없다(fail-open) — 켠 적 없는 기능이 막히면 안 된다."""
    from app.quotas import service

    csrf = login_as("system_admin")
    usage = client.get("/api/admin/ai-quotas/usage").json()
    assert usage["periods"][0]["limit"] is None
    assert service.effective_limits(db, "nobody") == {}


def test_ai_quota_rejects_duplicates_and_unknown_user(client, login_as):
    csrf = login_as("system_admin")
    body = {"scope_type": "global", "period": "day", "max_calls": 100}
    assert client.post("/api/admin/ai-quotas", json=body, headers=_h(csrf)).status_code == 201
    assert client.post("/api/admin/ai-quotas", json=body, headers=_h(csrf)).status_code == 409
    missing = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": "no-such-user", "period": "day", "max_calls": 5},
        headers=_h(csrf),
    )
    assert missing.status_code == 404


def test_ai_quota_patch_rejects_explicit_null_instead_of_silently_ignoring_it(client, login_as):
    """UB-30: max_calls는 DB에서 NOT NULL이고 null로 둘 수 있는 상태가 없다(0="차단",
    무제한을 원하면 행을 지운다). `{"max_calls": null}`을 조용히 무시하면 보낸 사람은
    상한이 바뀐 줄 안다 — 명시적으로 거부해야 한다."""
    csrf = login_as("system_admin")
    created = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "global", "period": "day", "max_calls": 100},
        headers=_h(csrf),
    ).json()["id"]

    r = client.patch(f"/api/admin/ai-quotas/{created}", json={"max_calls": None}, headers=_h(csrf))
    assert r.status_code != 200, f"max_calls: null이 조용히 성공했다: {r.status_code} {r.text}"

    unchanged = client.get("/api/admin/ai-quotas").json()["items"]
    row = next(i for i in unchanged if i["id"] == created)
    assert row["max_calls"] == 100, "거부됐어야 할 요청이 실제로는 값을 건드렸다"


# ── 기능 플래그 UI ───────────────────────────────────────────────────────────


@pytest.fixture()
def flags_file(settings):
    """플래그 파일을 백업했다가 되돌린다 — 테스트가 저장소 파일을 영구히 바꾸면 안 된다."""
    from app.core.feature_flags import flags_path, reset_cache

    path = flags_path(settings.config_dir)
    # **바이트 단위**로 스냅숏한다. read_text/write_text 는 줄바꿈을 변환해서, 내용이 같아도
    # 되돌린 파일이 원본과 다른 바이트가 된다(윈도우에서 실제로 저장소가 더럽혀졌다).
    original = path.read_bytes() if path.exists() else None
    yield path
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(original)
    reset_cache()


def test_feature_flag_list_shows_owner_and_editability(client, login_as):
    login_as("system_admin")
    body = client.get("/api/admin/feature-flags").json()
    by_name = {i["name"]: i for i in body["items"]}
    assert by_name["board_enabled"]["owner"] == "file"
    assert by_name["board_enabled"]["editable_here"] is True
    # DB 소유 플래그는 여기서 못 고친다 — split-brain 을 다시 열지 않는다.
    assert by_name["maintenance_mode"]["owner"] == "db"
    assert by_name["maintenance_mode"]["editable_here"] is False
    # 읽는 코드가 없는 플래그는 그렇다고 말한다.
    assert by_name["limited_service_actions_enabled"]["has_consumer"] is False


def test_feature_flag_toggle_writes_the_file_and_takes_effect(client, login_as, flags_file):
    from app.core.feature_flags import load_feature_flags

    csrf = login_as("system_admin")
    response = client.put(
        "/api/admin/feature-flags/games_enabled", json={"enabled": False}, headers=_h(csrf)
    )
    assert response.status_code == 200, response.text
    assert response.json()["value"] is False

    # 파일을 **다시 읽어** 실제로 반영됐는지 본다(응답만 믿지 않는다).
    on_disk = json.loads(flags_file.read_text(encoding="utf-8"))
    assert on_disk["games_enabled"] is False
    assert load_feature_flags(flags_file.parent)["games_enabled"] is False

    # 화면 목록도 같은 값을 말한다.
    listed = {i["name"]: i for i in client.get("/api/admin/feature-flags").json()["items"]}
    assert listed["games_enabled"]["value"] is False

    # 감사 로그에 남는다.
    logs = client.get("/api/admin/audit?action=feature_flag.update").json()["items"]
    assert logs and logs[0]["object_id"] == "games_enabled"
    assert logs[0]["before"]["value"] is True and logs[0]["after"]["value"] is False


def test_feature_flag_db_owned_is_refused(client, login_as, flags_file):
    csrf = login_as("system_admin")
    response = client.put(
        "/api/admin/feature-flags/maintenance_mode", json={"enabled": True}, headers=_h(csrf)
    )
    assert response.status_code == 409
    assert "설정" in response.json()["error"]["message"]


def test_feature_flag_unknown_is_404(client, login_as, flags_file):
    csrf = login_as("system_admin")
    response = client.put(
        "/api/admin/feature-flags/made_up_flag", json={"enabled": True}, headers=_h(csrf)
    )
    assert response.status_code == 404


# ── 감사 이상탐지 · 내보내기 · 저장 필터 ─────────────────────────────────────


def test_audit_anomalies_flags_failure_bursts_with_evidence(client, login_as, db, fake_clock):
    from app.core.audit import record_audit
    from app.users.models import User
    from sqlalchemy import select

    csrf = login_as("system_admin")
    actor = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    now = fake_clock.now()
    for i in range(6):
        record_audit(
            db, actor_id=actor.id, action="user.update", object_type="user",
            object_id=f"u{i}", result="failure",
        )
    db.commit()

    body = client.get("/api/admin/audit/anomalies").json()
    kinds = {f["kind"] for f in body["findings"]}
    assert "failure_burst" in kinds
    burst = [f for f in body["findings"] if f["kind"] == "failure_burst"][0]
    assert burst["count"] >= 6
    assert burst["threshold"] == body["thresholds"]["failure_burst"]
    assert burst["evidence"], "근거 없이 경보만 내면 아무도 안 믿는다"
    assert burst["actor_name"], "행위자 이름이 해석되지 않았다"


def test_audit_anomalies_flags_critical_actions(client, login_as, make_user):
    csrf = login_as("system_admin")
    target = make_user(email="imp-target@goodmit.co.kr", role="user")
    client.post(
        "/api/admin/impersonation/start",
        json={"user_id": target.id}, headers=_h(csrf),
    )
    client.post("/api/admin/impersonation/stop", headers=_h(csrf))
    findings = client.get("/api/admin/audit/anomalies").json()["findings"]
    critical = [f for f in findings if f["kind"] == "critical_action"]
    assert critical, "임퍼소네이션 시작이 소견에 안 잡혔다"
    assert any("impersonation.start" in e for e in critical[0]["evidence"])


def test_audit_export_csv_matches_the_filtered_query(client, login_as, db):
    from app.core.audit import record_audit
    from sqlalchemy import select

    from app.users.models import User

    csrf = login_as("system_admin")
    actor = db.execute(select(User).where(User.role == "system_admin")).scalars().first()
    record_audit(db, actor_id=actor.id, action="zzz.only", object_type="user", object_id="x")
    db.commit()

    response = client.get("/api/admin/audit/export.csv?action=zzz.only")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["X-Export-Truncated"] == "0"
    text = response.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0].startswith("시각(KST)")
    assert len(lines) == 2, "필터가 무시되고 전체가 나왔다"
    assert "zzz.only" in lines[1]
    # 엑셀이 UTF-8 로 인식하도록 BOM 이 붙어 있어야 한다.
    assert response.content.startswith(b"\xef\xbb\xbf")


# 감사 '저장 필터'는 여기서 시험하지 않는다 — 0032 의 `saved_views` 가 담당하고
# (`DataScreen` 이 감사 화면에도 그 컨트롤을 그린다) 그쪽 테스트가 이미 있다.
# 같은 일을 하는 두 번째 저장소를 만들지 않기로 한 결정은 0033 마이그레이션 docstring 참조.


# ── 백업 일정 + 복구 리허설 ──────────────────────────────────────────────────


def test_backup_schedule_view_is_honest_when_never_rehearsed(client, login_as):
    login_as("system_admin")
    body = client.get("/api/admin/backups/schedule").json()
    assert body["schedule"]["enabled"] is False
    assert body["last_rehearsal"] is None, "한 적 없는 리허설을 있다고 말하면 안 된다"
    rehearsals = client.get("/api/admin/backups/rehearsals").json()
    assert rehearsals["items"] == []
    assert "restore_rehearsal.py" in rehearsals["command"]


def test_backup_schedule_setting_validates_cron(client, login_as):
    csrf = login_as("system_admin")
    bad = client.put(
        "/api/admin/settings/backup_schedule",
        json={"value": {"enabled": True, "cron": "정말 아님", "timezone": "Asia/Seoul", "keep": 7}},
        headers=_h(csrf),
    )
    assert bad.status_code == 422, bad.text
    good = client.put(
        "/api/admin/settings/backup_schedule",
        json={"value": {"enabled": True, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 7}},
        headers=_h(csrf),
    )
    assert good.status_code == 200, good.text
    assert client.get("/api/admin/backups/schedule").json()["schedule"]["enabled"] is True


def test_scheduled_backup_is_due_only_once_per_fire_time(client, login_as, db, fake_clock):
    """멱등 판정 — 워커가 재시작해도 같은 예정 시각에 두 번 돌지 않는다."""
    from app.backups.service import due_for_scheduled_backup, run_scheduled_backup

    config = {"enabled": True, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 3}
    # KST 03:00 = UTC 18:00 전날. 지금을 KST 09:00 으로 잡으면 직전 예정 시각이 오늘 03:00 이다.
    now = datetime(2026, 8, 3, 0, 0)  # UTC 00:00 == KST 09:00
    assert due_for_scheduled_backup(db, config, now=now) is True

    from app.core.config import Settings

    settings = client.app.state.settings
    row = run_scheduled_backup(db, settings, config, now=now)
    db.commit()
    assert row is not None and row.status in ("succeeded", "verified")
    assert due_for_scheduled_backup(db, config, now=now + timedelta(hours=1)) is False
    # 다음 예정 시각이 지나면 다시 돌 차례다.
    assert due_for_scheduled_backup(db, config, now=now + timedelta(days=1)) is True


def test_disabled_schedule_never_runs(db):
    from app.backups.service import due_for_scheduled_backup

    config = {"enabled": False, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 3}
    assert due_for_scheduled_backup(db, config, now=datetime(2026, 8, 3, 0, 0)) is False


# ── 프롬프트 사용 통계 ───────────────────────────────────────────────────────


def test_prompt_usage_stats_marks_unused(client, login_as):
    csrf = login_as("system_admin")
    created = client.post(
        "/api/admin/prompts",
        json={"name": "안 쓰이는 프롬프트", "content": "hello", "purpose": "테스트"},
        headers=_h(csrf),
    )
    assert created.status_code == 201, created.text
    stats = client.get("/api/admin/prompts/usage/stats").json()["items"]
    row = [i for i in stats if i["name"] == "안 쓰이는 프롬프트"][0]
    assert row["versions"] == 1
    assert row["template_refs"] == 0 and row["schedule_refs"] == 0
    assert row["document_runs"] == 0
    assert row["unused"] is True


def test_prompt_usage_stats_counts_beyond_the_old_50_sample_cap(client, login_as, db):
    """UB-11/UB-12: 이름당 버전이 50개를 넘으면 예전엔 `sorted(ids)[:50]`(UUID 사전순 —
    임의 표본)만 세었다. 실제로 쓰이는 버전의 id가 그 표본 밖이면(여기서는 사전순 맨 뒤가
    되도록 일부러 구성) 운영 중인 프롬프트가 '쓰이지 않음'으로 잘못 표시됐다 — 이 화면의
    존재 이유(정리 대상을 고른다)를 정면으로 배신하는 오탐이었다."""
    from app.documents.models import STATUS_PENDING, DocumentGeneration
    from app.prompts.models import Prompt

    name = "51개 버전 프롬프트"
    used_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"  # 사전순 항상 맨 뒤 — 옛 50개 표본 밖
    for v in range(1, 51):
        db.add(Prompt(id=f"00000000-0000-0000-0000-{v:012d}", name=name, version=v, content="x"))
    db.add(Prompt(id=used_id, name=name, version=51, content="x"))
    db.add(DocumentGeneration(
        template_id=None, workflow_id="wf-1", mode="manual",
        idempotency_key="ub11-regression-key", status=STATUS_PENDING,
        config_json=json.dumps({"prompt_id": used_id}),
    ))
    db.commit()

    login_as("system_admin")
    stats = client.get("/api/admin/prompts/usage/stats").json()["items"]
    row = [i for i in stats if i["name"] == name][0]
    assert row["versions"] == 51
    assert row["document_runs"] == 1, "사전순 맨 뒤 버전의 실제 사용이 안 잡혔다"
    assert row["unused"] is False, "실제로 쓰이는 프롬프트가 '쓰이지 않음'으로 오탐됐다"
