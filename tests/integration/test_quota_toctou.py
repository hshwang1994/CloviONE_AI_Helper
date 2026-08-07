"""AI 쿼터 TOCTOU — 동시 요청이 상한을 **함께** 통과하지 못한다 (Z15).

## 무엇이 잘못됐나

판정은 두 걸음이었다: `enforce()` 로 지금까지 쓴 수를 **세고**, 나중에 `record_call()` 로
**늘린다.** 그 사이는 잠기지 않은 창이다.

    A: used=9 < 10  -> 통과          B: used=9 < 10  -> 통과
    A: 호출 -> 10                     B: 호출 -> 11      <- 상한 10 인데 11회

두 갈래로 새는데 증상은 같다("숫자가 상한을 넘어 있다"):

1. **동기 경로**(문서 생성, 도우미 문장) — 확인과 기록이 한 요청 안이지만 그 사이에
   AI 호출(수 초)이 들어간다. 그동안 같은 사람의 다른 요청이 같은 숫자를 읽는다.
2. **큐 경로**(AI 도우미 채팅) — 기록은 **워커가** 잡을 끝낸 뒤에 한다. 확인과 기록 사이에
   큐가 통째로 들어 있어서, 큐에 든 호출은 아무 데도 세어지지 않는다. 연속으로 보내면
   상한이 1인 사람도 원하는 만큼 보낼 수 있다.

## 이 테스트가 왜 스레드를 쓰나(그리고 왜 하나는 안 쓰나)

큐 경로는 **스레드 없이** 재현된다 — 잡을 큐에 넣기만 하고 워커를 안 돌리면 그게 바로
"확인과 기록 사이"다. 값이 실제로 달라진다: 고치기 전 202, 고친 뒤 429.

동기 경로는 두 요청이 **같은 숫자를 읽는 순간**이 사건이라 스레드가 필요하다. 잠들기로
맞추면 느리고 흔들리므로 `Barrier` 로 "둘 다 세기에 도달" 을 못박는다 — 잠금이 있으면
둘째가 첫째를 기다리느라 그 barrier 에 못 오고, 그 사실 자체가 잠금이 걸렸다는 증거다.
"""

from __future__ import annotations

import threading
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 3, 9, 0, 0)


@pytest.fixture()
def capped(db, make_user):
    """하루 1회 상한이 걸린 사용자."""
    from app.quotas.models import AiQuota

    user = make_user("toctou@goodmit.co.kr", role="user", display_name="상한사용자")
    db.add(AiQuota(
        scope_type="user", user_id=user.id, period="day", max_calls=1,
        created_at=NOW, updated_at=NOW,
    ))
    db.commit()
    return user


# ── 1) 큐 경로: 큐에 든 호출도 이미 쓴 것이다 ────────────────────────────────


_seq = iter(range(1, 10_000))


def _send(client, csrf, conv_id):
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "안녕", "client_message_id": f"toctou-{next(_seq):04d}"},
        headers={"X-CSRF-Token": csrf},
    )


def test_a_queued_call_already_counts_against_the_cap(client, login_as, db, capped):
    """하루 1회인 사람이 워커가 돌기 전에 두 번째를 보내면 막혀야 한다."""
    from app.quotas.service import EVENT_AI_CALL, used
    from app.observability.models import UsageEvent
    from sqlalchemy import func, select

    csrf = login_as("user", email="toctou@goodmit.co.kr")
    conv_id = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
    ).json()["conversation"]["id"]

    first = _send(client, csrf, conv_id)
    assert first.status_code == 202, f"첫 번째가 막혔다: {first.status_code} {first.text}"

    # 아직 아무것도 기록되지 않았다 — 이것이 바로 창이 열려 있는 상태다.
    recorded = db.execute(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.event == EVENT_AI_CALL)
    ).scalar_one()
    assert recorded == 0, "표본이 사건을 재현하지 못한다(이미 기록돼 있으면 창이 없다)"
    assert used(db, user_id=capped.id, period="day", now=NOW) == 0

    second = _send(client, csrf, conv_id)
    assert second.status_code == 429, (
        f"상한 1회인데 큐에 든 호출을 세지 않아 두 번째가 그대로 나갔다: "
        f"{second.status_code} {second.text}"
    )
    # 폭주 차단(초 단위)이 아니라 **상한**에 걸려야 한다. 버스트 20건이라 여기 걸릴 리 없지만,
    # 이유가 다른 429 로 초록불이 나면 이 테스트는 아무것도 증명하지 못한다.
    assert "상한" in second.json()["error"]["message"], (
        f"429 이긴 한데 상한 때문이 아니다: {second.text}"
    )


def test_the_queue_reservation_clears_when_the_job_finishes(client, login_as, db, capped):
    """예약은 잡이 끝나면 사라진다 — 안 그러면 하루 상한이 영원히 한 칸 줄어든다."""
    from app.jobs.models import STATUS_SUCCEEDED, Job

    csrf = login_as("user", email="toctou@goodmit.co.kr")
    conv_id = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
    ).json()["conversation"]["id"]
    assert _send(client, csrf, conv_id).status_code == 202

    from sqlalchemy import select

    job = db.execute(select(Job).where(Job.job_type == "chat_message")).scalars().first()
    assert job is not None
    job.status = STATUS_SUCCEEDED
    db.commit()

    # 잡이 끝났고(예약 해제) 아직 아무것도 기록되지 않았으니 다시 한 칸이 남는다.
    again = _send(client, csrf, conv_id)
    assert again.status_code == 202, (
        f"끝난 잡이 계속 상한을 잡아먹는다: {again.status_code} {again.text}"
    )


# ── 2) 동기 경로: 둘이 같은 마지막 한 칸을 가져가지 못한다 ────────────────────


def test_two_concurrent_calls_cannot_both_take_the_last_slot(app, db, capped, monkeypatch):
    """상한 1회를 두 요청이 동시에 통과하면 안 된다."""
    from app.core.errors import RateLimitedError
    from app.quotas import service as quotas

    real_used = quotas.used
    barrier = threading.Barrier(2)

    def counting_used(*args, **kwargs):
        # 잠금이 없으면 둘 다 여기에 도달해 **같은 숫자**를 읽는다. 잠금이 있으면 둘째는
        # 첫째가 끝날 때까지 여기 못 오고 barrier 는 시간 초과로 깨진다(그 편이 정상이다).
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return real_used(*args, **kwargs)

    monkeypatch.setattr(quotas, "used", counting_used)

    outcomes: list[str] = []
    lock = threading.Lock()

    def worker():
        session = app.state.session_factory()
        try:
            with quotas.consume(
                session, user_id=capped.id, org_id=None,
                kind=quotas.KIND_DOCUMENT_GENERATE, now=NOW,
            ) as slot:
                slot.record()
            session.commit()
            result = "ok"
        except RateLimitedError:
            session.rollback()
            result = "429"
        finally:
            session.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(outcomes) == ["429", "ok"], (
        f"상한 1회를 두 요청이 함께 통과했다: {outcomes}"
    )

    from app.observability.models import UsageEvent
    from sqlalchemy import func, select

    db.expire_all()
    recorded = db.execute(
        select(func.count()).select_from(UsageEvent).where(
            UsageEvent.event == quotas.EVENT_AI_CALL
        )
    ).scalar_one()
    assert recorded == 1, f"상한 1회인데 {recorded}회가 기록됐다"


def test_a_failed_call_does_not_burn_the_slot(app, db, capped):
    """기록은 성공했을 때만 한다 — 러너가 죽은 날 상한까지 잃으면 안 된다."""
    from app.quotas import service as quotas

    session = app.state.session_factory()
    try:
        with quotas.consume(
            session, user_id=capped.id, org_id=None,
            kind=quotas.KIND_DOCUMENT_GENERATE, now=NOW,
        ):
            pass  # slot.record() 를 부르지 않는다 = 호출이 실패했다
        session.commit()
    finally:
        session.close()

    db.expire_all()
    assert quotas.used(db, user_id=capped.id, period="day", now=NOW) == 0, (
        "실패한 호출이 상한을 깎았다"
    )
