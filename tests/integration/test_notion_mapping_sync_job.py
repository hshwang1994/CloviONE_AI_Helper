"""Notion 매핑 동기화를 작업 큐로 돌린다.

사용자 제안: "워크플로를 별도로 배치해서 Notion 매핑 페이지에 접근해 동기화 버튼을 한 번
누르면 그 워크플로가 동작하도록 하면 안 되는거야? 동작이 끝나면 정보가 나오도록 하고."

맞는 구조다. 지금까지는 사용자당 '검증'이 n8n을 **동기로** 불렀고, 그 워크플로는 Notion의
작업·프로젝트 DB를 통째로 읽어 9~13초가 걸린다(프로덕션 실측). 12명이면 브라우저를 2분
붙잡으면서 같은 조회를 12번 반복한다. 한 번 읽어 전원에게 나눠 주는 것이 맞다.
"""

import json

import pytest

from app.jobs.exceptions import PermanentJobError
from app.jobs.handlers.notion_mapping_sync import handle_notion_mapping_sync
from app.jobs.models import Job
from app.jobs.worker import WorkerContext

pytestmark = pytest.mark.integration

_PEOPLE = [
    {"notion_user_id": "2b5d872b-594c-8128-896b-000230e4e13c",
     "notion_email": "kimjh@goodmit.co.kr", "name": "김지혜"},
    {"notion_user_id": "239d872b-594c-81cb-a8a9-0002e17e2738",
     "notion_email": "donghyunkim@goodmit.co.kr", "name": "김동현"},
]


class _Provider:
    """n8n 자리. 실제 호출 없이 계약만 흉내 낸다."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def invoke(self, workflow, payload, *, timeout):
        self.calls.append(payload)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _run(db, app, monkeypatch, provider_payload, users_seed):
    from app.workflows.service import seed_known_workflows
    import app.jobs.handlers.notion_mapping_sync as mod

    seed_known_workflows(db, allowlists=app.state.allowlists)
    for email, name in users_seed:
        users_seed_user(db, email, name)
    db.flush()

    provider = _Provider(provider_payload)
    monkeypatch.setattr(mod, "N8nWorkflowProvider", lambda outbound: provider)
    job = Job(job_type="notion_mapping_sync", payload_json="{}", available_at=app.state.clock.now())
    db.add(job)
    db.flush()
    ctx = WorkerContext(settings=app.state.settings, clock=app.state.clock, outbound_client=None)
    handle_notion_mapping_sync(db, job, ctx)
    return provider


def users_seed_user(db, email, name):
    from app.users.models import ROLE_USER, User

    db.add(User(email=email, display_name=name, role=ROLE_USER,
                password_hash="x", must_change_password=False))


def _status_of(db, email):
    from sqlalchemy import select
    from app.notion_mapping.models import UserNotionMapping
    from app.users.models import User

    user = db.execute(select(User).where(User.email == email)).scalar_one()
    row = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id == user.id)
    ).scalar_one()
    return row


def test_one_call_maps_everyone(db, app, monkeypatch):
    """n8n을 **한 번** 부르고 그 결과로 전원을 맞춘다 — 사람마다 부르지 않는다."""
    provider = _run(
        db, app, monkeypatch,
        {"users": _PEOPLE, "total": len(_PEOPLE)},
        [("kimjh@goodmit.co.kr", "김지혜"), ("donghyunkim@goodmit.co.kr", "김동현"),
         ("nobody@goodmit.co.kr", "없는사람")],
    )
    assert len(provider.calls) == 1, f"n8n을 {len(provider.calls)}번 불렀다 — 한 번이면 된다"
    assert provider.calls[0] == {"action": "list_users"}

    assert _status_of(db, "kimjh@goodmit.co.kr").status == "verified"
    assert _status_of(db, "kimjh@goodmit.co.kr").notion_user_id == _PEOPLE[0]["notion_user_id"]
    assert _status_of(db, "donghyunkim@goodmit.co.kr").status == "verified"
    # Notion에 없는 사람은 미매핑이다 — 없는 ID를 지어내지 않는다.
    assert _status_of(db, "nobody@goodmit.co.kr").status == "unmapped"
    assert _status_of(db, "nobody@goodmit.co.kr").notion_user_id is None


def test_notion_failure_is_not_reported_as_nobody_found(db, app, monkeypatch):
    """Notion을 못 읽었을 때 '그 사람이 없다'고 답하면 안 된다.

    이게 이 핸들러의 핵심이다. 빈 목록을 '없음'으로 읽으면 사용자는 그 사람이 Notion에
    없다고 믿고, 멀쩡한 매핑을 지우게 된다.
    """
    with pytest.raises(PermanentJobError) as exc:
        _run(db, app, monkeypatch,
             {"error": "Notion 작업 데이터를 읽지 못했습니다.", "matches": []},
             [("kimjh@goodmit.co.kr", "김지혜")])
    assert "읽지 못했" in str(exc.value)


def test_malformed_response_is_permanent_not_silent(db, app, monkeypatch):
    """응답이 계약과 다르면 조용히 넘기지 않는다."""
    with pytest.raises(PermanentJobError):
        _run(db, app, monkeypatch, {"unexpected": True}, [("kimjh@goodmit.co.kr", "김지혜")])


def test_duplicate_emails_become_conflict_not_a_guess(db, app, monkeypatch):
    """같은 이메일이 둘이면 우리가 고르지 않는다 — 관리자가 정한다."""
    dupes = [
        {"notion_user_id": "aaaa1111-1111-1111-1111-111111111111",
         "notion_email": "kimjh@goodmit.co.kr", "name": "김지혜"},
        {"notion_user_id": "bbbb2222-2222-2222-2222-222222222222",
         "notion_email": "kimjh@goodmit.co.kr", "name": "김지혜(중복)"},
    ]
    _run(db, app, monkeypatch, {"users": dupes}, [("kimjh@goodmit.co.kr", "김지혜")])
    row = _status_of(db, "kimjh@goodmit.co.kr")
    assert row.status == "conflict"
    assert row.notion_user_id is None, "충돌인데 하나를 골랐다"
    assert len(json.loads(row.candidates_json)) == 2, "관리자가 고를 후보를 남겨야 한다"


def test_sync_endpoint_returns_202_and_does_not_block(client, login_as):
    """동기화 버튼은 잡을 만들고 바로 돌려준다 — 9~13초를 기다리게 하지 않는다."""
    csrf = login_as("admin")
    r = client.post("/api/admin/notion-mapping/sync", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job_id"]
    assert body["status"] in {"pending", "queued", "ready"}


def test_sync_endpoint_needs_csrf_and_write_role(client, login_as):
    csrf = login_as("admin")
    assert client.post("/api/admin/notion-mapping/sync").status_code == 403
    login_as("operator")
    r = client.post("/api/admin/notion-mapping/sync", headers={"X-CSRF-Token": csrf})
    assert r.status_code in {401, 403}, f"operator가 동기화를 실행했다: {r.status_code}"


def test_double_click_does_not_run_notion_twice(client, login_as):
    """무거운 Notion 조회를 두 번 돌리지 않는다 (같은 분 안의 중복 클릭)."""
    csrf = login_as("admin")
    a = client.post("/api/admin/notion-mapping/sync", headers={"X-CSRF-Token": csrf}).json()
    b = client.post("/api/admin/notion-mapping/sync", headers={"X-CSRF-Token": csrf}).json()
    assert a["job_id"] == b["job_id"], "연달아 누르면 잡이 두 개 생긴다"


def test_idempotency_key_is_deterministic_within_the_same_second():
    """같은 초에 만든 키는 항상 같아야 `jobs_repo.enqueue`의 유니크 제약이 동시 요청의
    경합(진행 중인 잡 조회와 삽입 사이의 틈)을 막아 준다.

    예전엔 키에 ``uuid.uuid4().hex[:8]``를 더 붙여서 호출마다 무조건 달라졌다 - 그러면
    유니크 제약에 절대 안 걸리므로 동시 요청 둘 다 삽입에 성공해 잡이 두 개 생긴다.
    """
    from datetime import datetime

    from app.notion_mapping.router import _sync_idempotency_key

    now = datetime(2026, 7, 14, 9, 30, 0)
    assert _sync_idempotency_key(now) == _sync_idempotency_key(now)

    later = datetime(2026, 7, 14, 9, 30, 1)
    assert _sync_idempotency_key(now) != _sync_idempotency_key(later)


def test_concurrent_sync_requests_do_not_enqueue_two_jobs(db, app, fake_clock):
    """진짜 동시 요청(진행 중인 잡 조회 이후, 삽입 이전에 둘 다 도착)도 잡을 하나만 만든다.

    라우터의 '진행 중인 잡' 조회만으로는 이 틈을 못 막는다 - 그래서 `jobs_repo.enqueue`의
    유니크 idempotency_key가 최후의 안전망이다. 같은 초에 결정되는 키가 아니면 이 안전망은
    작동하지 않는다(위 결정성 테스트가 그 전제를 고정한다).
    """
    from app.jobs import repository as jobs_repo
    from app.notion_mapping.router import _sync_idempotency_key

    now = fake_clock.now()
    key = _sync_idempotency_key(now)

    # 두 '동시' 요청이 이미 진행 중인 잡을 못 보고(active is None) 둘 다 enqueue에 닿았다고
    # 가정한다 - 실제 레이스가 넓어지면 벌어지는 상황을 그대로 흉내 낸다.
    first = jobs_repo.enqueue(
        db, job_type="notion_mapping_sync", payload={}, now=now, idempotency_key=key,
    )
    db.commit()
    second = jobs_repo.enqueue(
        db, job_type="notion_mapping_sync", payload={}, now=now, idempotency_key=key,
    )
    db.commit()

    assert second.id == first.id, "동시 요청이 동기화 잡을 두 개 만들었다"
