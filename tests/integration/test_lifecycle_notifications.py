"""나머지 네 가지 조용한 사건 (§E-6 N2).

감사 확인: 아래 네 사건에 화면 알림이 0건이었다.

  * **문서 생성 성공** - 요청한 문서가 다 만들어져도 화면을 다시 열어 봐야 알았다.
  * **오프보딩 후임자** - 티켓을 넘겨받은 사람이 그 사실을 통보받지 못했다.
  * **AI 쿼터 소진** - 쓰려는 순간에야 상한에 걸린 것을 알았다.
  * **백업 실패** - 메일은 나가는데 앱 안에서는 여전히 조용했다.

공통으로 지키는 것은 티켓 배정 알림과 같다(tests/integration/test_assignment_notification.py):
내가 한 일은 나에게 오지 않고, 알림이 실패해도 본 작업은 남으며, 방해금지는 배지만 끈다.

오프보딩에는 규칙이 하나 더 있다: **티켓 한 건마다 알리지 않는다.** 100건을 넘겨받은 사람에게
알림 100건을 보내면 그건 통보가 아니라 사고다 - 요약 한 건만 보낸다.
"""

from __future__ import annotations

import pytest

from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.integration

TOKEN_REF = "notion_report_token"
DOC_URL = "http://127.0.0.1:5678/webhook/doc-gen"

LEAVER_NID = "notion-leaver"
SUCCESSOR_NID = "notion-successor"


def _count(app, user_id: str, kind: str) -> int:
    from app.notifications.models import Notification

    with app.state.session_factory() as session:
        return (
            session.query(Notification)
            .filter(Notification.user_id == user_id, Notification.type == kind)
            .count()
        )


def _rows(app, kind: str) -> list:
    from app.notifications.models import Notification

    with app.state.session_factory() as session:
        return list(session.query(Notification).filter(Notification.type == kind).all())


# ── 1. 문서 생성 성공 ─────────────────────────────────────────────────────────

@pytest.fixture()
def doc_worker(app, settings, fake_clock):
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.worker import Worker, WorkerContext

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    )


def _workflow(client, csrf, *, approval_required: bool) -> str:
    return client.post(
        "/api/admin/workflows",
        json={"name": "문서 생성", "webhook_url": DOC_URL,
              "operation_mode": "write", "approval_required": approval_required},
        headers={"X-CSRF-Token": csrf},
    ).json()["workflow"]["id"]


def _generate(client, csrf, workflow_id, mode, period="2026-W28"):
    return client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "mode": mode, "period": period,
              "config": {"target_parent_page": "page-123", "template_version": 1,
                         "prompt_template": "weekly"}},
        headers={"X-CSRF-Token": csrf},
    )


def _me_id(client) -> str:
    return client.get("/api/me").json()["user"]["id"]


def test_a_published_document_tells_the_person_who_asked_for_it(
    client, app, login_as, doc_worker, fake_http
):
    csrf = login_as("admin", email="doc-admin@goodmit.co.kr")
    me = _me_id(client)
    fake_http.on(
        DOC_URL,
        json_body={"title": "주간 보고서", "body": "완료된 작업 요약입니다. " * 3,
                   "source_row_count": 4, "published_ref": "https://www.notion.so/pub123"},
    )
    workflow_id = _workflow(client, csrf, approval_required=False)
    response = _generate(client, csrf, workflow_id, "auto_publish")
    assert response.status_code == 202, response.text
    gen_id = response.json()["generation"]["id"]

    # 아직 큐에 있을 뿐이다 - 여기서 알림이 있으면 '요청했다'를 '만들어졌다'로 속인 것이다.
    assert _count(app, me, "document_ready") == 0, "만들어지기도 전에 완료 알림이 갔다"

    doc_worker.run_once()
    assert client.get(f"/api/admin/documents/{gen_id}").json()["generation"]["status"] == "published"
    assert _count(app, me, "document_ready") == 1, "문서가 다 만들어졌는데 요청자가 모른다"


def test_a_preview_only_document_also_reports_when_it_is_ready(
    client, app, login_as, doc_worker, fake_http
):
    """미리보기만 만드는 모드도 '요청한 산출물이 준비됐다'는 같은 사건이다."""
    csrf = login_as("admin", email="doc-admin2@goodmit.co.kr")
    me = _me_id(client)
    fake_http.on(
        DOC_URL,
        json_body={"title": "주간 보고서", "body": "완료된 작업 요약입니다. " * 3,
                   "source_row_count": 4},
    )
    workflow_id = _workflow(client, csrf, approval_required=True)
    _generate(client, csrf, workflow_id, "preview_only")
    doc_worker.run_once()

    assert _count(app, me, "document_ready") == 1, "미리보기가 준비됐는데 요청자가 모른다"


def test_a_failed_document_does_not_claim_success(
    client, app, login_as, doc_worker, fake_http
):
    """값이 실제로 달라지는 표본. 품질 게이트에 걸린 문서는 '완료'가 아니다."""
    csrf = login_as("admin", email="doc-admin3@goodmit.co.kr")
    me = _me_id(client)
    fake_http.on(DOC_URL, json_body={"title": "", "body": "짧", "source_row_count": 0})
    workflow_id = _workflow(client, csrf, approval_required=True)
    _generate(client, csrf, workflow_id, "auto_publish")
    doc_worker.run_once()

    assert _count(app, me, "document_ready") == 0, "실패한 문서를 완료로 알렸다"


# ── 2. 오프보딩 후임자 ────────────────────────────────────────────────────────

@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="page-1", tid=101, title="혼자 담당 A", status="진행",
                     due="2026-09-01", people=[LEAVER_NID]),
            task_row(page_id="page-2", tid=102, title="혼자 담당 B", status="진행",
                     due="2026-09-02", people=[LEAVER_NID]),
        ],
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def people(db, make_user, settings, notion) -> dict[str, str]:
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    made: dict[str, str] = {}
    for key, email, nid, name in (
        ("leaver", "leaver@goodmit.co.kr", LEAVER_NID, "퇴사자"),
        ("successor", "successor@goodmit.co.kr", SUCCESSOR_NID, "후임"),
    ):
        user = make_user(email=email, role="user", display_name=name)
        db.add(UserNotionMapping(
            id=f"map-{key}", user_id=user.id, notion_user_id=nid,
            status=STATUS_VERIFIED, source=SOURCE_MANUAL,
        ))
        made[key] = user.id
    db.commit()
    return made


@pytest.fixture()
def admin(client, make_user, db) -> str:
    make_user(email="boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login", json={"email": "boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_the_successor_is_told_what_they_inherited(client, app, admin, people, notion):
    response = client.post(
        f"/api/admin/offboarding/run/{people['leaver']}",
        json={"ticket_page_ids": ["page-1", "page-2"],
              "successor_user_id": people["successor"],
              "deactivate": True, "archive": False},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["ticket_moved"] == 2

    assert _count(app, people["successor"], "offboarding_handover") == 1, (
        "티켓을 넘겨받은 사람이 그 사실을 모른다"
    )


def test_a_handover_is_one_summary_not_one_notification_per_ticket(
    client, app, admin, people, notion
):
    """100건을 넘겨받은 사람에게 알림 100건을 보내면 그건 통보가 아니라 사고다."""
    client.post(
        f"/api/admin/offboarding/run/{people['leaver']}",
        json={"ticket_page_ids": ["page-1", "page-2"],
              "successor_user_id": people["successor"],
              "deactivate": False, "archive": False},
        headers={"X-CSRF-Token": admin},
    )

    assert _count(app, people["successor"], "ticket_assigned") == 0, (
        "오프보딩이 티켓 건마다 배정 알림을 뿌렸다"
    )
    assert _count(app, people["successor"], "offboarding_handover") == 1


def test_no_successor_means_no_handover_notification(client, app, admin, people, notion):
    """후임 없이 미할당으로 보내는 경우 - 받을 사람이 없으면 아무에게도 안 보낸다."""
    client.post(
        f"/api/admin/offboarding/run/{people['leaver']}",
        json={"ticket_page_ids": ["page-1"], "deactivate": False, "archive": False},
        headers={"X-CSRF-Token": admin},
    )

    assert _rows(app, "offboarding_handover") == [], "받을 사람이 없는데 알림이 생겼다"


def test_an_admin_who_hands_over_to_themselves_gets_nothing(
    client, app, make_user, db, settings, notion
):
    """자기 자신을 후임으로 지정한 관리자는 자기가 한 일을 이미 안다."""
    boss = make_user(email="boss2@goodmit.co.kr", role="system_admin", display_name="관리자")
    db.add(UserNotionMapping(
        id="map-boss2", user_id=boss.id, notion_user_id=SUCCESSOR_NID,
        status=STATUS_VERIFIED, source=SOURCE_MANUAL,
    ))
    leaver = make_user(email="leaver2@goodmit.co.kr", role="user", display_name="퇴사자")
    db.add(UserNotionMapping(
        id="map-leaver2", user_id=leaver.id, notion_user_id=LEAVER_NID,
        status=STATUS_VERIFIED, source=SOURCE_MANUAL,
    ))
    db.commit()
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")

    csrf = client.post(
        "/login", json={"email": "boss2@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    ).json()["csrf_token"]
    client.post(
        f"/api/admin/offboarding/run/{leaver.id}",
        json={"ticket_page_ids": ["page-1"], "successor_user_id": boss.id,
              "deactivate": False, "archive": False},
        headers={"X-CSRF-Token": csrf},
    )

    assert _count(app, boss.id, "offboarding_handover") == 0, (
        "내가 나에게 넘긴 일이 나에게 알림으로 왔다"
    )


# ── 3. AI 쿼터 소진 ───────────────────────────────────────────────────────────

def _set_quota(client, csrf, user_id: str, max_calls: int):
    return client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": user_id, "period": "day",
              "max_calls": max_calls},
        headers={"X-CSRF-Token": csrf},
    )


def test_the_user_hears_about_the_quota_when_it_runs_out(
    client, app, login_as, doc_worker, fake_http
):
    """상한에 **닿는 순간** 알린다. 다음에 쓰려다 429 를 보고 아는 것은 너무 늦다."""
    csrf = login_as("admin", email="quota-admin@goodmit.co.kr")
    me = _me_id(client)
    fake_http.on(
        DOC_URL,
        json_body={"title": "보고서", "body": "완료된 작업 요약입니다. " * 3,
                   "source_row_count": 4},
    )
    workflow_id = _workflow(client, csrf, approval_required=True)
    assert _set_quota(client, csrf, me, 2).status_code == 201

    assert _generate(client, csrf, workflow_id, "preview_only", period="2026-W31").status_code == 202
    assert _count(app, me, "ai_quota_exhausted") == 0, "아직 한 번 남았는데 소진을 알렸다"

    assert _generate(client, csrf, workflow_id, "preview_only", period="2026-W32").status_code == 202
    assert _count(app, me, "ai_quota_exhausted") == 1, "상한에 닿았는데 알림이 없다"


def test_the_quota_notice_is_sent_once_not_on_every_rejected_call(
    client, app, login_as, fake_http
):
    """상한에 걸린 뒤에도 계속 시도한다. 시도마다 알리면 배지가 그 사람만 폭주한다."""
    csrf = login_as("admin", email="quota-admin2@goodmit.co.kr")
    me = _me_id(client)
    fake_http.on(
        DOC_URL,
        json_body={"title": "보고서", "body": "완료된 작업 요약입니다. " * 3,
                   "source_row_count": 4},
    )
    workflow_id = _workflow(client, csrf, approval_required=True)
    assert _set_quota(client, csrf, me, 1).status_code == 201

    assert _generate(client, csrf, workflow_id, "preview_only", period="2026-W33").status_code == 202
    for period in ("2026-W34", "2026-W35"):
        assert _generate(client, csrf, workflow_id, "preview_only", period=period).status_code == 429

    assert _count(app, me, "ai_quota_exhausted") == 1, "거절될 때마다 알림이 쌓인다"


# ── 4. 백업 실패 ──────────────────────────────────────────────────────────────

def test_a_failed_scheduled_backup_reaches_the_admins_in_the_app(
    app, settings, make_user
):
    """메일만으로는 부족하다 - 메일함을 안 보는 날 백업이 멈춘 사실은 아무 데도 안 뜬다."""
    import app.backups.service as backups_service

    ops = make_user("ops-noti@goodmit.co.kr", role="admin", display_name="운영자")

    def boom(*_args, **_kwargs):
        raise OSError("디스크에 공간이 없습니다")

    original = backups_service.backup_database
    backups_service.backup_database = boom
    try:
        with app.state.session_factory() as session:
            backups_service.run_scheduled_backup(
                session, settings, {"keep": 3}, now=app.state.clock.now()
            )
            session.commit()
    finally:
        backups_service.backup_database = original

    assert _count(app, ops.id, "backup_failed") == 1, (
        "§E-6: 백업 실패가 여전히 앱 안에서는 조용하다"
    )


def test_a_successful_backup_says_nothing(app, settings, make_user):
    """값이 실제로 달라지는 표본 - 성공한 백업이 실패 알림을 만들면 안 된다."""
    import app.backups.service as backups_service

    make_user("ops-noti2@goodmit.co.kr", role="admin", display_name="운영자")
    with app.state.session_factory() as session:
        row = backups_service.run_scheduled_backup(
            session, settings, {"keep": 3}, now=app.state.clock.now()
        )
        session.commit()
        assert row is not None and row.status != "failed", row.error_message

    assert _rows(app, "backup_failed") == [], "성공한 백업이 실패 알림을 냈다"


def test_a_failed_manual_backup_reaches_the_admins_in_the_app(app, client, login_as, make_user):
    """FN-09 — 예약 백업은 실패를 알리는데, '지금 백업' 버튼(수동 경로)은 실패해도 누른
    사람 말고는 아무도 몰랐다(POST 응답으로만 봄). run_backup 자체는 두 경로가 공유하므로
    (app/backups/service.py) 실패 시뮬레이션 방식은 예약 백업 시험과 같다."""
    import app.backups.service as backups_service

    ops = make_user("ops-noti-manual@goodmit.co.kr", role="admin", display_name="운영자")
    csrf = login_as("system_admin", email="ops-noti-manual-actor@goodmit.co.kr")

    def boom(*_args, **_kwargs):
        raise OSError("디스크에 공간이 없습니다")

    original = backups_service.backup_database
    backups_service.backup_database = boom
    try:
        r = client.post("/api/admin/backups", headers={"X-CSRF-Token": csrf})
    finally:
        backups_service.backup_database = original

    assert r.status_code == 201, r.text
    assert r.json()["backup"]["status"] == "failed"
    assert _count(app, ops.id, "backup_failed") == 1, (
        "FN-09: 수동 백업 실패가 여전히 앱 안에서는 조용하다"
    )


def test_a_successful_manual_backup_says_nothing(app, client, login_as, make_user):
    """값이 실제로 달라지는 표본 — 성공한 수동 백업이 실패 알림을 만들면 안 된다."""
    make_user("ops-noti-manual2@goodmit.co.kr", role="admin", display_name="운영자")
    csrf = login_as("system_admin", email="ops-noti-manual2-actor@goodmit.co.kr")

    r = client.post("/api/admin/backups", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 201, r.text
    assert r.json()["backup"]["status"] != "failed"
    assert _rows(app, "backup_failed") == [], "성공한 수동 백업이 실패 알림을 냈다"


# ── 새 유형은 전부 설정 화면에서 끌 수 있어야 한다 ────────────────────────────

def test_every_new_type_is_in_the_preference_registry(client, login_as):
    """레지스트리에 없는 유형은 사용자가 끌 수 없다 - '왜 이건 못 끄지'가 남는다."""
    login_as("user", email="prefs@goodmit.co.kr")
    catalog = client.get("/api/me/preferences").json()["notifications"]["catalog"]
    keys = {t["key"] for t in catalog}
    for kind in ("ticket_assigned", "document_ready", "offboarding_handover",
                 "ai_quota_exhausted", "backup_failed"):
        assert kind in keys, f"{kind} 을(를) 설정 화면에서 끌 수 없다"
