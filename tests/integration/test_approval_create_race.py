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


# ── 결정 경합 (perm-06) ──────────────────────────────────────────────────────
#
# 생성만 막혀 있었다. 두 관리자가 같은 큐를 동시에 처리하면(화면 둘을 열어 두면 실제로
# 일어난다) 두 트랜잭션이 각자 「아직 대기」를 보고 **각자 실행기를 돌린 뒤** 서로의 status 를
# 덮어썼다 — 원장은 「거절」인데 대상 계정은 admin 이 되고, 요청자는 상반된 통보 둘을 받았다.
# 승인은 권한 부여 실행이라 사후에 되돌릴 방법이 없다.

DECIDERS = 4

#: 이 시험만 쓰는 요청 유형. 실제 실행기(역할 변경 등)를 쓰면 사용자·스케줄 세계를 통째로
#: 세워야 하고, 정작 세려는 것은 「실행기가 몇 번 돌았나」 하나다.
RACE_REQUEST_TYPE = "test.decide_race"


def _seed_pair(url: str) -> tuple[str, str]:
    """요청자(admin) 와 결재자(system_admin) 각각 하나. id 를 돌려준다."""
    from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, User

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            asker = User(
                email="decide-asker@goodmit.co.kr", display_name="요청자",
                password_hash="not-a-real-hash", role=ROLE_ADMIN, active=True,
            )
            decider = User(
                email="decide-boss@goodmit.co.kr", display_name="결재자",
                password_hash="not-a-real-hash", role=ROLE_SYSTEM_ADMIN, active=True,
            )
            db.add_all([asker, decider])
            db.commit()
            return asker.id, decider.id
    finally:
        engine.dispose()


def test_concurrent_decisions_on_one_approval_pick_exactly_one_winner(db_url):
    import app.approvals.service as svc
    from app.approvals.models import Approval
    from app.core.errors import ConflictError
    from app.users.models import User

    now = datetime(2026, 7, 14, 0, 0, 0)
    asker_id, decider_id = _seed_pair(db_url)
    executed: list[str] = []

    def _count_only(_db, approval, _app_state):
        executed.append(approval.id)

    svc.APPROVAL_EXECUTORS[RACE_REQUEST_TYPE] = _count_only
    try:
        engine = make_engine(db_url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                approval = svc.create_approval(
                    db,
                    request_type=RACE_REQUEST_TYPE,
                    object_type="user",
                    object_id="decide-race-target",
                    requested_by=db.get(User, asker_id),
                    payload={"role": "admin"},
                    now=now,
                )
                db.commit()
                approval_id = approval.id
        finally:
            engine.dispose()

        def attempt(_i: int) -> str:
            thread_engine = make_engine(db_url)
            thread_factory = make_session_factory(thread_engine)
            try:
                with thread_factory() as db:
                    try:
                        svc.decide(
                            db,
                            db.get(Approval, approval_id),
                            db.get(User, decider_id),
                            approve=True,
                            comment=None,
                            now=now,
                            self_approval_allowed=False,
                            app_state=None,
                        )
                        db.commit()
                        return "decided"
                    except ConflictError as exc:
                        db.rollback()
                        return f"conflict: {exc.message}"
            finally:
                thread_engine.dispose()

        with ThreadPoolExecutor(max_workers=DECIDERS) as pool:
            outcomes = list(pool.map(attempt, range(DECIDERS)))
    finally:
        del svc.APPROVAL_EXECUTORS[RACE_REQUEST_TYPE]

    assert outcomes.count("decided") == 1, f"한 승인이 여러 번 결정됐다: {outcomes}"
    assert len(executed) == 1, f"실행기가 {len(executed)}번 돌았다 — 정확히 한 번이어야 한다"
    assert all("이미" in o for o in outcomes if o != "decided"), outcomes

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            row = db.get(Approval, approval_id)
            assert row.status == "approved"
            assert row.decided_at is not None
    finally:
        engine.dispose()


# ── 위임 겹침 경합 (xd-02 · perm-07) ─────────────────────────────────────────
#
# 겹침 금지의 목적은 「회수가 거짓말을 하지 않는 것」이다 — 같은 짝의 위임이 두 장 살아 있으면
# 관리자가 한 장을 거두고 권한을 회수했다고 믿는 순간 다른 한 장이 그대로 결재를 허용한다.
# 사전 검사와 INSERT 사이가 열려 있어 동시 4발이 전부 201 이었다.


def _seed_delegation_pair(url: str) -> tuple[str, str]:
    from app.users.models import ROLE_ADMIN, ROLE_OPERATOR, User

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            boss = User(
                email="deleg-race-boss@goodmit.co.kr", display_name="위임자",
                password_hash="not-a-real-hash", role=ROLE_ADMIN, active=True,
            )
            stand_in = User(
                email="deleg-race-standin@goodmit.co.kr", display_name="대리인",
                password_hash="not-a-real-hash", role=ROLE_OPERATOR, active=True,
            )
            db.add_all([boss, stand_in])
            db.commit()
            return boss.id, stand_in.id
    finally:
        engine.dispose()


def test_concurrent_overlapping_delegations_leave_exactly_one_live_row(db_url):
    from datetime import timedelta

    from app.approvals import delegation
    from app.approvals.models import ApprovalDelegation
    from app.core.errors import ConflictError
    from app.users.models import User

    now = datetime(2026, 7, 14, 0, 0, 0)
    starts_at = now + timedelta(days=20)
    ends_at = now + timedelta(days=23)
    boss_id, stand_in_id = _seed_delegation_pair(db_url)

    def attempt(_i: int) -> str:
        engine = make_engine(db_url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                try:
                    delegation.create(
                        db,
                        delegator=db.get(User, boss_id),
                        delegate=db.get(User, stand_in_id),
                        starts_at=starts_at,
                        ends_at=ends_at,
                        reason="경합",
                        created_by=boss_id,
                        now=now,
                        visible=None,
                    )
                    db.commit()
                    return "created"
                except ConflictError:
                    db.rollback()
                    return "conflict"
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        outcomes = list(pool.map(attempt, range(THREADS)))

    assert outcomes.count("created") == 1, f"겹치는 위임이 여러 장 만들어졌다: {outcomes}"

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            live = db.execute(
                select(func.count()).select_from(ApprovalDelegation).where(
                    ApprovalDelegation.delegator_user_id == boss_id,
                    ApprovalDelegation.delegate_user_id == stand_in_id,
                    ApprovalDelegation.revoked_at.is_(None),
                )
            ).scalar_one()
            assert live == 1, (
                f"한 장을 거둬도 권한이 남는 상태다 — 살아 있는 위임이 {live}장이다"
            )
    finally:
        engine.dispose()


def test_a_second_non_overlapping_delegation_is_still_allowed(db_url):
    """오탐 방지 — 겹치지 않는 창은 여러 장 만들 수 있어야 한다(부재가 여러 번 있다)."""
    from datetime import timedelta

    from app.approvals import delegation
    from app.users.models import User

    now = datetime(2026, 7, 14, 0, 0, 0)
    boss_id, stand_in_id = _seed_delegation_pair(db_url)

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            first = delegation.create(
                db, delegator=db.get(User, boss_id), delegate=db.get(User, stand_in_id),
                starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=2),
                reason=None, created_by=boss_id, now=now, visible=None,
            )
            second = delegation.create(
                db, delegator=db.get(User, boss_id), delegate=db.get(User, stand_in_id),
                starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=4),
                reason=None, created_by=boss_id, now=now, visible=None,
            )
            db.commit()
            assert first.id != second.id
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
