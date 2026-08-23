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

"""qa-contract-change: 문서 생성 완료 알림 절이 S11 과 함께 사라졌고, AI 쿼터 소진 알림의 소비 경로를 문서 생성에서 채팅으로 옮겼다. 그 김에 시험이 더 정확해졌다 — 채팅은 워커가 답을 만든 뒤에 기록하므로 「보낸 즉시」가 아니라 「처리된 뒤」 소진을 본다."""

import pytest

from app.core.models_base import join_names
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

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


def _me_id(client) -> str:
    return client.get("/api/me").json()["user"]["id"]


def _rows(app, kind: str) -> list:
    from app.notifications.models import Notification

    with app.state.session_factory() as session:
        return list(session.query(Notification).filter(Notification.type == kind).all())


# ── 1. 문서 생성 성공 ─────────────────────────────────────────────────────────
#
# S11 이 n8n 기반 문서 생성을 걷어냈다. 그 절이 지키던 「요청한 사람이 결과를 안다」는
# 지금 채팅이 진다 — 답변이든 「근거가 없다」든 그 사람의 대화에 바로 남는다
# (tests/integration/test_chat_answers_from_retrieval.py).


# ── 2. 오프보딩 후임자 ────────────────────────────────────────────────────────

@pytest.fixture()
def tickets(db, make_project):
    """퇴사자가 들고 있는 두 건. S14 이후 티켓의 정본은 자체 DB(`tickets`)다.

    통보 시험이라고 티켓을 흉내만 내면 안 된다 — 실제로 옮겨진 건수가 알림 문구와 발송
    여부를 정하기 때문에, 넘어갈 티켓이 없으면 「안 보냈다」가 저절로 참이 된다.
    """
    project = make_project(name="알파", external_id="proj-1")
    for page_id, tid, title, due in (
        ("page-1", 101, "혼자 담당 A", "2026-09-01"),
        ("page-2", 102, "혼자 담당 B", "2026-09-02"),
    ):
        db.add(TicketCache(
            notion_page_id=page_id, org_id=DEFAULT_ORG_ID, notion_ticket_number=tid,
            title=title, status="진행", due_date=due,
            project_ids=join_names(["proj-1"]), project_uid=project.id,
            project_link=PROJECT_LINK_OK, project_names=join_names([project.name]),
            assignee_notion_ids=join_names([LEAVER_NID]),
        ))
    db.commit()
    return project


@pytest.fixture()
def people(db, make_user) -> dict[str, str]:
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


def test_the_successor_is_told_what_they_inherited(client, app, admin, people, tickets):
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
    client, app, admin, people, tickets
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


def test_no_successor_means_no_handover_notification(client, app, admin, people, tickets):
    """후임 없이 미할당으로 보내는 경우 - 받을 사람이 없으면 아무에게도 안 보낸다."""
    response = client.post(
        f"/api/admin/offboarding/run/{people['leaver']}",
        json={"ticket_page_ids": ["page-1"], "deactivate": False, "archive": False},
        headers={"X-CSRF-Token": admin},
    )

    # 옮긴 것이 실제로 있어야 「안 보냈다」가 의미를 갖는다 - 0건이면 저절로 참이 된다.
    assert response.json()["run"]["ticket_moved"] == 1, response.text
    assert _rows(app, "offboarding_handover") == [], "받을 사람이 없는데 알림이 생겼다"


def test_an_admin_who_hands_over_to_themselves_gets_nothing(
    client, app, make_user, db, tickets
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

    csrf = client.post(
        "/login", json={"email": "boss2@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    ).json()["csrf_token"]
    response = client.post(
        f"/api/admin/offboarding/run/{leaver.id}",
        json={"ticket_page_ids": ["page-1"], "successor_user_id": boss.id,
              "deactivate": False, "archive": False},
        headers={"X-CSRF-Token": csrf},
    )

    # 위와 같은 이유 - 넘어간 티켓이 있어야 「나에게는 안 왔다」가 시험이 된다.
    assert response.json()["run"]["ticket_moved"] == 1, response.text
    assert _count(app, boss.id, "offboarding_handover") == 0, (
        "내가 나에게 넘긴 일이 나에게 알림으로 왔다"
    )


# ── 3. AI 쿼터 소진 ───────────────────────────────────────────────────────────
#
# 상한을 소비하는 경로가 S11 로 하나 줄었다(문서 생성). 남은 것은 채팅이고, 그 경로는
# **워커가 답을 만든 뒤에** 기록한다 — 그래서 「보낸 즉시 소진」이 아니라 「처리된 뒤 소진」이다.


def _set_quota(client, csrf, user_id: str, max_calls: int):
    return client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": user_id, "period": "day",
              "max_calls": max_calls},
        headers={"X-CSRF-Token": csrf},
    )


class _AlwaysAnswers:
    name = "scripted"
    model = "scripted-model"
    dim = 384

    def __init__(self, cap):
        self._cap = cap

    def capability(self):
        from app.ai.gateway import contract

        return contract.available(self._cap, model=self.model)

    def embed(self, texts, *, kind=None):
        from app.ai.gateway import contract

        one = tuple([1.0] + [0.0] * 383)
        return contract.EmbedResult(status=contract.STATUS_OK, model=self.model,
                                    dim=384, vectors=tuple(one for _ in texts))

    def generate(self, *, system, user):
        from app.ai.gateway import contract

        return contract.GenerateResult(status=contract.STATUS_OK, model=self.model,
                                       text="답변입니다.")


@pytest.fixture()
def chat_quota_world(client, app, login_as, db, settings, fake_clock):
    """상한이 걸린 사용자 + 근거가 될 문서 하나 + 그 답을 만드는 워커."""
    from app.ai.gateway import contract
    from app.ai.index import service as index_service
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.worker import Worker, WorkerContext
    from app.knowledge import versions
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    gateway = contract.Gateway(
        enabled=True,
        embed_adapter=_AlwaysAnswers(contract.CAP_EMBED),
        generate_adapter=_AlwaysAnswers(contract.CAP_GENERATE),
    )
    app.state.ai_gateway = gateway

    space = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="규정", slug="rules",
                           owner_kind="organization")
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="연차 규정", archived=False)
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "연차는 15일이다."}]}
    ]}, author_id=None)
    db.flush()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()

    ctx = WorkerContext(settings=settings, clock=fake_clock,
                        outbound_client=app.state.outbound_client,
                        extras={"ai_gateway": gateway})
    worker = Worker(app.state.session_factory, fake_clock,
                    {"chat_message": handle_chat_message}, ctx, poll_interval=0.01)
    return worker


_msg = iter(range(1000, 9999))


def _ask(client, csrf, conv_id):
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "연차 며칠인가요", "client_message_id": f"quota{next(_msg)}" + "0" * 24},
        headers={"X-CSRF-Token": csrf},
    )


def test_the_user_hears_about_the_quota_when_it_runs_out(
    client, app, login_as, db, chat_quota_world
):
    """상한에 **닿는 순간** 알린다. 다음에 쓰려다 429 를 보고 아는 것은 너무 늦다."""
    admin_csrf = login_as("system_admin", email="quota-admin@goodmit.co.kr")
    csrf = login_as("user", email="quota-user@goodmit.co.kr")
    me = _me_id(client)
    admin_csrf = login_as("system_admin", email="quota-admin@goodmit.co.kr")
    assert _set_quota(client, admin_csrf, me, 2).status_code == 201

    csrf = login_as("user", email="quota-user@goodmit.co.kr")
    conv = client.post("/api/conversations", json={},
                       headers={"X-CSRF-Token": csrf}).json()["conversation"]["id"]

    assert _ask(client, csrf, conv).status_code == 202
    chat_quota_world.run_once()
    assert _count(app, me, "ai_quota_exhausted") == 0, "아직 한 번 남았는데 소진을 알렸다"

    assert _ask(client, csrf, conv).status_code == 202
    chat_quota_world.run_once()
    assert _count(app, me, "ai_quota_exhausted") == 1, "상한에 닿았는데 알림이 없다"


def test_the_quota_notice_is_sent_once_not_on_every_rejected_call(
    client, app, login_as, db, chat_quota_world
):
    """상한에 걸린 뒤에도 계속 시도한다. 시도마다 알리면 배지가 그 사람만 폭주한다."""
    csrf = login_as("user", email="quota-user2@goodmit.co.kr")
    me = _me_id(client)
    admin_csrf = login_as("system_admin", email="quota-admin2@goodmit.co.kr")
    assert _set_quota(client, admin_csrf, me, 1).status_code == 201

    csrf = login_as("user", email="quota-user2@goodmit.co.kr")
    conv = client.post("/api/conversations", json={},
                       headers={"X-CSRF-Token": csrf}).json()["conversation"]["id"]

    assert _ask(client, csrf, conv).status_code == 202
    chat_quota_world.run_once()
    for _ in range(2):
        assert _ask(client, csrf, conv).status_code == 429

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


def test_a_successful_backup_says_nothing(app, settings, make_user, stub_pg_dump):
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


# ── 4-R. RSTR-03: 백업이 실패가 아니라 애초에 안 도는 것 ──────────────────────
#
# announce_backup_failure(위 두 시험)는 백업을 "시도했는데 실패했을 때"만 켜진다. 이
# 설치의 실제 문제는 그게 아니었다 — 예약 백업이 기본값(꺼짐)인 채로 20일이 지났는데,
# 시도 자체가 없으니 실패 알림도 한 번도 안 나갔다. /restore-drills 화면을 직접 열어야만
# 보였고 아무도 그 화면을 안 봤다.

def test_disabled_schedule_gets_a_reason(app):
    import app.backups.service as backups_service

    with app.state.session_factory() as session:
        reason = backups_service.backup_health_alert_reason(
            session, {"enabled": False}, now=app.state.clock.now()
        )
    assert reason is not None and "꺼져" in reason


def test_enabled_but_never_run_gets_a_reason(app):
    import app.backups.service as backups_service

    with app.state.session_factory() as session:
        reason = backups_service.backup_health_alert_reason(
            session, {"enabled": True}, now=app.state.clock.now()
        )
    assert reason is not None and "없습니다" in reason


def test_enabled_and_recent_backup_is_healthy(app):
    import app.backups.service as backups_service
    from app.backups.models import STATUS_VERIFIED, Backup

    now = app.state.clock.now()
    with app.state.session_factory() as session:
        session.add(Backup(
            backup_type="manual", path="/tmp/clv-recent.sqlite3",
            status=STATUS_VERIFIED, created_at=now,
        ))
        session.commit()
        reason = backups_service.backup_health_alert_reason(
            session, {"enabled": True}, now=now
        )
    assert reason is None


def test_enabled_but_stale_backup_gets_a_reason(app):
    from datetime import timedelta

    import app.backups.service as backups_service
    from app.backups.models import STATUS_VERIFIED, Backup

    now = app.state.clock.now()
    with app.state.session_factory() as session:
        session.add(Backup(
            backup_type="manual", path="/tmp/clv-stale.sqlite3",
            status=STATUS_VERIFIED,
            created_at=now - timedelta(days=backups_service.BACKUP_STALE_ALERT_DAYS + 1),
        ))
        session.commit()
        reason = backups_service.backup_health_alert_reason(
            session, {"enabled": True}, now=now
        )
    assert reason is not None and "오래됐다면" in reason


def test_a_disabled_schedule_reaches_the_admins_once_a_day_not_every_tick(app, make_user):
    """반복 경보와 같은 원칙 — 나쁜 상태가 계속 참이어도 매 틱(10분)마다 알리면
    관리자 알림함이 도배된다. 하루 한 번으로 눌러 둔다."""
    import app.backups.service as backups_service

    ops = make_user("ops-noti3@goodmit.co.kr", role="admin", display_name="운영자")
    now = app.state.clock.now()
    with app.state.session_factory() as session:
        backups_service.check_backup_health(session, {"enabled": False}, now=now)
        session.commit()
    assert _count(app, ops.id, "backup_failed") == 1

    with app.state.session_factory() as session:
        # 같은 틱이 몇 번 더 돌아도(워커가 재시작하는 등) 쿨다운 안이면 추가로 안 보낸다.
        backups_service.check_backup_health(session, {"enabled": False}, now=now)
        backups_service.check_backup_health(session, {"enabled": False}, now=now)
        session.commit()
    assert _count(app, ops.id, "backup_failed") == 1, "쿨다운 안에서 알림함이 도배됐다"


def test_a_healthy_schedule_says_nothing(app, make_user):
    import app.backups.service as backups_service
    from app.backups.models import STATUS_VERIFIED, Backup

    ops = make_user("ops-noti4@goodmit.co.kr", role="admin", display_name="운영자")
    now = app.state.clock.now()
    with app.state.session_factory() as session:
        session.add(Backup(
            backup_type="manual", path="/tmp/clv-healthy.sqlite3",
            status=STATUS_VERIFIED, created_at=now,
        ))
        session.commit()
        backups_service.check_backup_health(session, {"enabled": True}, now=now)
        session.commit()
    assert _count(app, ops.id, "backup_failed") == 0


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


def test_a_successful_manual_backup_says_nothing(app, client, login_as, make_user, stub_pg_dump):
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
    for kind in ("ticket_assigned", "offboarding_handover",
                 "ai_quota_exhausted", "backup_failed"):
        assert kind in keys, f"{kind} 을(를) 설정 화면에서 끌 수 없다"
