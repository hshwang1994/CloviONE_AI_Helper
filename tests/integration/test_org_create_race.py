"""Proof that concurrent department/job-title/organization creation with the
same name never crashes with a raw 500 — whole-product re-audit finding
(2026-08-15, alongside PA-RC-0008).

`app/org/service.py::create_item` (departments, job titles) and
`app/org/router.py::create_organization` were check-then-insert with no
SAVEPOINT/retry: `Department.(org_id, name)`, `JobTitle.name` (global), and
`Organization.slug` are all real DB UNIQUE constraints, so two concurrent
POSTs with the same name/slug could both pass the pre-insert duplicate
check and the loser's `db.flush()` raised an unhandled
IntegrityError/OperationalError ("database is locked") straight into the
generic 500 handler — the same bug class PA-RC-0008 already fixed at 7
other call sites (e.g. app/projects/service.py's PROJ-01).

Both are now wrapped in the shared `db.begin_nested()` + `is_write_conflict`
retry (app/core/db.py), and raise the *same* clean error on exhaustion that
the synchronous pre-check already used for that call site (ConflictError
for create_item, ValidationAppError for create_organization) — a client
that loses the race gets the same response as one that arrived slightly
later and hit the ordinary duplicate check.

## A second, separate, pre-existing gap this test found and does NOT fix

Writing the real-concurrency test below (8 threads, tight loop, same name)
occasionally surfaced a *different*, broader, pre-existing bug: the
request-scoped outer `db.commit()` in `app/core/deps.py::get_db` (used by
*every* endpoint, not just these two) has no write-conflict retry at all.
`create_item`/`create_organization` only guarantee that *their own*
SAVEPOINT-level insert is retried — the final commit that makes the row
durable happens one layer up, in `get_db`, after the service function has
already returned successfully. Under rare, narrow-window contention that
outer commit can itself raise an unhandled OperationalError. Recovering
from that properly needs the whole request re-run (a naive commit-retry
would `rollback()` the very row SQLAlchemy had already flushed, silently
discarding a "successful" create) — a request-scoped, framework-level
change well beyond this fix's scope. Tracked in `docs/BACKLOG.md` (search
"get_db 바깥 커밋") for separate follow-up. The tests below scope their
hard assertions to what `create_item`/`create_organization` themselves
promise (no data corruption, clean typed error on exhaustion) rather than
to the pre-existing outer-commit gap.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.fakes.pgerrors import unique_violation

from app.core.db import make_engine, make_session_factory
from app.org.constants import DEFAULT_ORG_ID

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

THREADS = 8


def test_concurrent_department_create_never_duplicates(db_url):
    from app.org.models import Department
    from app.org.service import create_item

    url = db_url

    def attempt(_i: int):
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                try:
                    row = create_item(db, Department, name="경합부서", org_id=DEFAULT_ORG_ID)
                    db.commit()
                    return ("ok", row.id)
                except Exception as exc:  # noqa: BLE001 — 어떤 실패든 최소한 데이터는 안 망가졌는지가 관심사
                    db.rollback()
                    return ("error", type(exc).__name__)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, range(THREADS)))

    from app.core.errors import ConflictError

    # create_item 자신의 SAVEPOINT 재시도가 처리 못 한 것으로 새 나가면 안 되는 예외는
    # IntegrityError뿐이다(그게 이 함수가 고치는 대상이다) — OperationalError는 모듈
    # docstring이 설명하는 별개의, 이미 있던, 범위 밖 outer-commit 결함에서 드물게
    # 새 나올 수 있어 여기서는 허용한다(각주 참고).
    leaked_integrity_errors = [r for r in results if r[0] == "error" and r[1] == "IntegrityError"]
    assert not leaked_integrity_errors, (
        f"create_item의 SAVEPOINT 재시도가 IntegrityError를 못 잡았다: {leaked_integrity_errors}"
    )

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(Department).where(
                    Department.org_id == DEFAULT_ORG_ID, Department.name == "경합부서"
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 이름의 부서가 {count}개 남았다"
    finally:
        engine.dispose()


def test_concurrent_job_title_create_never_duplicates(db_url):
    """JobTitle은 이름이 **전역** UNIQUE라 Department와 dedup 판정 자리가 다르다
    (create_item의 dup_org 계산 분기) — 같은 함수의 다른 코드 경로를 실제로 태운다."""
    from app.org.models import JobTitle
    from app.org.service import create_item

    url = db_url

    def attempt(_i: int):
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                try:
                    row = create_item(db, JobTitle, name="경합직책")
                    db.commit()
                    return ("ok", row.id)
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    return ("error", type(exc).__name__)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, range(THREADS)))

    leaked_integrity_errors = [r for r in results if r[0] == "error" and r[1] == "IntegrityError"]
    assert not leaked_integrity_errors, (
        f"create_item의 SAVEPOINT 재시도가 IntegrityError를 못 잡았다: {leaked_integrity_errors}"
    )

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(JobTitle).where(JobTitle.name == "경합직책")
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 이름의 직책이 {count}개 남았다"
    finally:
        engine.dispose()


def test_create_item_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """PA-RC-0008과 같은 계약 — 예산을 다 썼는데도 경합이면 raw 500이 아니라 깨끗한
    409(ConflictError)여야 한다. 실 스레드 대신 `db.add()`가 항상 UNIQUE 위반으로
    실패하게 고정해 결정적으로 예산을 소진시킨다."""
    import app.org.service as svc
    from app.core.errors import ConflictError
    from app.org.models import Department

    attempts = []

    def _add_that_always_conflicts(_instance):
        attempts.append(1)
        raise unique_violation("INSERT INTO departments")

    monkeypatch.setattr(db, "add", _add_that_always_conflicts)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)

    with pytest.raises(ConflictError):
        svc.create_item(db, Department, name="소진부서", org_id=DEFAULT_ORG_ID)
    assert len(attempts) == svc._CREATE_ITEM_RETRIES, f"정확히 예산만큼 시도해야 한다: {attempts}"


def test_create_organization_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """create_organization(라우터 레벨)도 같은 계약 — 예산 소진 시 사전 검사와 같은
    ValidationAppError(422, "이미 있는 식별자입니다")여야 한다."""
    import app.org.router as router_mod
    from app.core.errors import ValidationAppError

    attempts = []

    def _add_that_always_conflicts(_instance):
        attempts.append(1)
        raise unique_violation("INSERT INTO organizations")

    monkeypatch.setattr(db, "add", _add_that_always_conflicts)
    monkeypatch.setattr(router_mod.time, "sleep", lambda _seconds: None)

    from app.core.org_tree import DeptTree
    from app.core.scope import Principal, Scope
    from app.org.router import create_organization
    from app.org.schemas import OrganizationCreateRequest
    from app.users.models import ADMIN_SCOPE_GLOBAL, MEMBERSHIP_ORGANIZATION

    class _FakeRequest:
        headers: dict = {}
        state = type("S", (), {})()

    # 0060: `Principal.scope` 하나가 조회·관리 두 축으로 갈라졌다. 조직 생성은 **관리**
    # 행위라 `management` 가 판정한다 — 둘을 같은 값으로 주면 어느 축이 쓰였는지 이 시험이
    # 말해 주지 못하므로, 여기서는 관리만 전역으로 둔다.
    principal = Principal(
        user_id="admin-1", role="admin", org_id=None, department_id=None,
        membership_kind=MEMBERSHIP_ORGANIZATION,
        visibility=Scope(kind=ADMIN_SCOPE_GLOBAL),
        management=Scope(kind=ADMIN_SCOPE_GLOBAL),
        tree=DeptTree.load(db),
    )

    with pytest.raises(ValidationAppError):
        create_organization(
            _FakeRequest(),
            OrganizationCreateRequest(slug="race-org", name="경합 조직"),
            db,
            principal,
        )
    assert len(attempts) == router_mod._CREATE_ORG_RETRIES, f"정확히 예산만큼 시도해야 한다: {attempts}"
