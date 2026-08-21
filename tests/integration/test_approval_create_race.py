"""Proof that concurrent create_approval calls for the same (request_type,
object_id, payload) never produce two PENDING rows — backend-approvals-jobs
audit #1: the check-then-insert dedup in create_approval had a race window
spanning the whole request (commit only happens at the very end, in get_db),
so two near-simultaneous requests (double-click, retried form submit) could
both see "no existing pending" and both insert. A duplicate pending row then
crashed every future create_approval() call for that object with
MultipleResultsFound (500), because the dedup query used
`scalar_one_or_none()`.

Migration 0052 adds a partial unique index
(request_type, object_id, request_payload_json) WHERE status='pending', and
create_approval() now catches the resulting IntegrityError and returns the
winning row — mirroring app/jobs/repository.py::enqueue's idempotency-key
race handling.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from tests.fakes.pgerrors import unique_violation

from app.core.db import make_engine, make_session_factory

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

THREADS = 8


def _seed_requester(url: str) -> str:
    from app.users.models import ROLE_ADMIN, User

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            user = User(
                email="racer@goodmit.co.kr",
                display_name="레이서",
                password_hash="not-a-real-hash",
                role=ROLE_ADMIN,
                active=True,
            )
            db.add(user)
            db.commit()
            return user.id
    finally:
        engine.dispose()


def test_concurrent_create_approval_same_payload_never_duplicates(db_url):
    # Import registers the built-in executors (schedule.enable, etc.) as a
    # module-level side effect of app.approvals.service — required so
    # create_approval() accepts request_type="schedule.enable".
    import app.approvals.service  # noqa: F401
    from app.approvals.service import create_approval
    from app.users.models import User

    url = db_url
    now = datetime(2026, 7, 14, 0, 0, 0)
    user_id = _seed_requester(url)

    payload = {"definition": {"cron_expression": "0 * * * *"}}

    def attempt(_i: int) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                requester = db.get(User, user_id)
                approval = create_approval(
                    db,
                    request_type="schedule.enable",
                    object_type="schedule",
                    object_id="sched-race-1",
                    requested_by=requester,
                    payload=payload,
                    now=now,
                )
                db.commit()
                return approval.id
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        ids = list(pool.map(attempt, range(THREADS)))

    assert len(set(ids)) == 1, f"race created duplicate pending approvals: {ids}"

    # A later call for the same object/payload must not crash even though the
    # race exercised the insert-conflict path (previously: MultipleResultsFound
    # once a duplicate existed).
    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            requester = db.get(User, user_id)
            again = create_approval(
                db,
                request_type="schedule.enable",
                object_type="schedule",
                object_id="sched-race-1",
                requested_by=requester,
                payload=payload,
                now=now,
            )
            assert again.id == ids[0]

            from sqlalchemy import func, select

            from app.approvals.models import Approval

            count = db.execute(
                select(func.count()).select_from(Approval).where(
                    Approval.object_id == "sched-race-1",
                    Approval.status == "pending",
                )
            ).scalar_one()
            assert count == 1
    finally:
        engine.dispose()


def test_create_approval_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """PA-RC-0008 — 예산을 다 쓰고도 승자를 못 찾으면 raw 500(처리 안 된
    IntegrityError)이 아니라 깨끗한 409여야 한다. 실 스레드 경합 대신 `db.add()`가
    항상 (가짜) `IntegrityError`로 실패하게 고정한다 — 실제로는 아무 것도 추가되지
    않으므로 "승자 재조회"도 매번 빈 손으로 끝나 결정적으로 예산을 소진한다.
    """
    import app.approvals.service as svc  # noqa: F401 — request_type 실행기 등록 부수효과
    from app.core.errors import ConflictError
    from app.users.models import ROLE_ADMIN, User

    user = User(
        email="exhaust-racer@goodmit.co.kr",
        display_name="소진 레이서",
        password_hash="not-a-real-hash",
        role=ROLE_ADMIN,
        active=True,
    )
    db.add(user)
    db.commit()

    attempts = []

    def _add_that_always_conflicts(_instance):
        attempts.append(1)
        raise unique_violation("INSERT INTO approvals", constraint="ux_approvals_pending_dedup")

    monkeypatch.setattr(db, "add", _add_that_always_conflicts)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)  # 재시도 횟수/결과만 본다 — 실제로 자면 느려진다

    with pytest.raises(ConflictError):
        svc.create_approval(
            db,
            request_type="schedule.enable",
            object_type="schedule",
            object_id="sched-exhaust-1",
            requested_by=user,
            payload={"definition": {"cron_expression": "0 * * * *"}},
            now=datetime(2026, 8, 15, 0, 0, 0),
        )
    assert len(attempts) == svc._CREATE_RETRIES, f"정확히 예산만큼 시도해야 한다: {attempts}"
