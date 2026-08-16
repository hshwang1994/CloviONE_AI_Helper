"""Job queue persistence: atomic claim, retry with backoff, stuck recovery.

The claim is a single UPDATE … RETURNING statement — atomic under SQLite WAL
with busy_timeout, so N workers can never claim the same job twice
(proven by tests/integration/test_job_claim_race.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import Select, or_ as sa_or, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.jobs.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Job,
)

# Backoff: 5s, 10s, 20s, … (base * 2^(attempt-1))
BACKOFF_BASE_SECONDS = 5.0
# Must exceed the longest legitimate handler runtime (scheduler timeout up to
# 3600s) so recovery never requeues a job that is genuinely still running.
DEFAULT_RUNNING_TIMEOUT_SECONDS = 3900


def enqueue(
    db: Session,
    *,
    job_type: str,
    payload: dict,
    now: datetime,
    user_id: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    available_at: datetime | None = None,
) -> Job:
    if idempotency_key is not None:
        existing = get_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return existing

    job = Job(
        job_type=job_type,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status=STATUS_QUEUED,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
        available_at=available_at or now,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        # Another writer inserted the same idempotency key first.
        existing = get_by_idempotency_key(db, idempotency_key) if idempotency_key else None
        if existing is not None:
            return existing
        raise
    return job


def get_by_idempotency_key(db: Session, key: str) -> Job | None:
    return db.execute(
        select(Job).where(Job.idempotency_key == key)
    ).scalar_one_or_none()


# ── 범위 판정 (§0-A 2순위) ────────────────────────────────────────────────────
#
# 목록·상세·재시도·취소가 **이 조건 하나**만 쓴다. 판정을 두 벌로 적으면 한쪽만 고쳐지고
# 증상은 "어떤 사람만 안 된다" 가 된다 — 목록에선 안 보이는데 id 로는 열리는(그 반대도)
# 상태가 정확히 그 모양이다. 단건도 `db.get` 이 아니라 **같은 조건이 붙은 SELECT** 로
# 찾으므로 두 경로가 갈라질 자리가 애초에 없다.


def scope_clause(visible: frozenset[str] | None):
    """범위 안 잡을 고르는 조건. 전역이면 ``None``(= 조건 없음).

    ``None`` 을 돌려주는 규약은 `core/scope.py::scope_filter` 와 같다 — 조건을 빼먹은
    코드와 '전역이라 조건이 없는' 코드를 눈으로 구별하기 위해서다.

    **시스템 잡(`user_id` 없음)은 남긴다.** 보존 정리·동기화 같은 자동 작업에는 소유자가
    없고, 그것까지 가리면 부서 관리자가 자기 범위의 자동 처리 실패를 못 본다(감사 로그와
    같은 규칙). 범위가 비어 있어도 이 갈래는 살아 있다.
    """
    if visible is None:
        return None
    return sa_or(Job.user_id.in_(tuple(sorted(visible))), Job.user_id.is_(None))


def apply_scope(stmt: Select, visible: frozenset[str] | None) -> Select:
    clause = scope_clause(visible)
    return stmt if clause is None else stmt.where(clause)


def get_in_scope(db: Session, job_id: str, visible: frozenset[str] | None) -> Job | None:
    """단건 조회 — 범위 밖이면 **아예 안 나온다**(부르는 쪽이 404 로 만든다).

    `db.get(Job, id)` 로 먼저 꺼내 놓고 나중에 판정하면, 판정을 빠뜨린 새 경로가 조용히
    열린다. 조건을 조회 자체에 붙여 두면 빠뜨릴 자리가 없다.
    """
    return db.execute(
        apply_scope(select(Job).where(Job.id == job_id), visible)
    ).scalar_one_or_none()


def claim_next(db: Session, now: datetime) -> Job | None:
    """Atomically claim the oldest ready job. Commits the claim."""
    # Must match SQLAlchemy's SQLite DATETIME storage format exactly
    # (microseconds always present) — string comparison depends on it.
    now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    row = db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'running',
                started_at = :now,
                attempt_count = attempt_count + 1,
                updated_at = :now
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'queued' AND available_at <= :now
                ORDER BY created_at, id
                LIMIT 1
            )
            RETURNING id
            """
        ),
        {"now": now_str},
    ).fetchone()
    db.commit()
    if row is None:
        return None
    job = db.get(Job, row[0])
    # The raw UPDATE bypassed the ORM — refresh so the instance reflects
    # the claimed state (identity map would otherwise serve stale values).
    db.refresh(job)
    return job


def finish(db: Session, job: Job, *, now: datetime) -> None:
    job.status = STATUS_SUCCEEDED
    job.finished_at = now
    job.last_error = None
    db.flush()


def fail(
    db: Session,
    job: Job,
    *,
    error: str,
    now: datetime,
    permanent: bool = False,
) -> None:
    job.last_error = (error or "")[:2000]
    if permanent or job.attempt_count >= job.max_attempts:
        job.status = STATUS_FAILED
        job.finished_at = now
    else:
        job.status = STATUS_QUEUED
        delay = BACKOFF_BASE_SECONDS * (2 ** (job.attempt_count - 1))
        job.available_at = now + timedelta(seconds=delay)
        job.started_at = None
    db.flush()


def retry_failed(db: Session, job: Job, *, now: datetime) -> Job:
    """Manual retry of a failed job (spec §10.2 operator capability)."""
    job.status = STATUS_QUEUED
    job.attempt_count = 0
    job.available_at = now
    job.finished_at = None
    job.started_at = None  # clear the prior run's start so the requeued job is clean
    db.flush()
    return job


def cancel_queued(db: Session, job: Job, *, now: datetime) -> Job:
    """대기(`queued`) 상태의 Job만 취소한다 — `claim_next`와 같은 CAS(compare-and-swap).

    예전에는 `UPDATE ... WHERE id = :id`(상태 조건 없이, ORM 대입으로)만 했다.
    호출부(`router.cancel`)가 먼저 파이썬에서 `job.status == 'queued'`를 확인하지만,
    그 확인과 이 UPDATE가 실제로 커밋되는 시점 사이에는 요청의 남은 처리 시간만큼 창이
    열려 있다(`get_db`가 요청 끝에 한 번만 커밋한다). 그 창에서 워커의 `claim_next`
    (자체 커밋하는 원자적 UPDATE)가 같은 Job을 queued→running으로 먼저 가져가면, 조건
    없는 UPDATE는 그 사실을 모른 채 워커가 실행 중인 running을 도로 cancelled로 덮어써
    버린다 — 워커는 자기 세션에서 핸들러를 계속 실행해 나중에 succeeded/failed로 다시
    덮어쓰므로, 실제로 일어난 일과 어긋나는 'job cancelled by operator' 상태가 연결된
    도메인 레코드(ScheduleRun/DocumentGeneration/Message)에 영구히 남을 수 있었다.

    `claim_next`와 같은 패턴으로 `WHERE status = 'queued'`를 UPDATE 조건에 넣는다. 0행이면
    (이미 다른 상태로 넘어갔으면) 호출부가 `_terminalize_linked_record`로 더 진행하지 않게
    `ConflictError`를 던진다.
    """
    now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    result = db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'cancelled',
                finished_at = :now,
                started_at = NULL,
                updated_at = :now
            WHERE id = :id AND status = 'queued'
            """
        ),
        {"now": now_str, "id": job.id},
    )
    if result.rowcount == 0:
        raise ConflictError("대기 상태의 Job만 취소할 수 있습니다.")
    # 원시 UPDATE는 ORM identity map을 거치지 않는다 — 호출부가 이어서 job.status 등을
    # 읽으므로(응답 직렬화, _terminalize_linked_record) 새로 반영해 둔다.
    db.refresh(job)
    return job


def recover_stuck(
    db: Session,
    *,
    now: datetime,
    running_timeout_seconds: int = DEFAULT_RUNNING_TIMEOUT_SECONDS,
) -> list[Job]:
    """Requeue (or fail) jobs left 'running' by a crashed worker (spec §22).
    Returns the recovered jobs so the caller can fire failure hooks."""
    cutoff = now - timedelta(seconds=running_timeout_seconds)
    stuck = (
        db.execute(
            select(Job).where(Job.status == STATUS_RUNNING, Job.started_at < cutoff)
        )
        .scalars()
        .all()
    )
    for job in stuck:
        fail(db, job, error="worker timeout: stuck job recovered", now=now)
    db.flush()
    return list(stuck)


def queue_stats(db: Session, *, now: datetime, visible: frozenset[str] | None = None) -> dict:
    """SEC-02: 형제인 목록·상세·재시도·취소는 전부 `apply_scope`를 지나는데 이 요약만
    빠져 있었다 — 부서 범위 admin이 전역 큐 깊이·실패 수를 그대로 봤다. `visible=None`
    (전역 권한)이면 예전과 동일하게 전체를 센다."""
    from sqlalchemy import func

    counts = dict(
        db.execute(
            apply_scope(select(Job.status, func.count()), visible).group_by(Job.status)
        ).all()
    )
    ready = db.execute(
        apply_scope(
            select(func.count()).select_from(Job)
            .where(Job.status == STATUS_QUEUED, Job.available_at <= now),
            visible,
        )
    ).scalar_one()
    oldest_queued = db.execute(
        apply_scope(
            select(func.min(Job.created_at)).where(Job.status == STATUS_QUEUED), visible
        )
    ).scalar_one()

    # VIS-120: 대기/실행 중/실행 가능(ready)은 전부 "지금 이 순간의 큐 깊이"뿐이다 — 셋 다
    # 0이면 큐가 건강해 보이지만, 최근에 계속 실패해 왔거나(재시도로 결국 빠져나가 큐에는
    # 안 남는다) 처리가 느려지고 있다는 신호는 이 셋 중 어디에도 없다. 같은 24시간 창으로
    # 두 가지를 더 낸다.
    cutoff = now - timedelta(hours=24)
    recent_failed = db.execute(
        apply_scope(
            select(func.count()).select_from(Job).where(
                Job.status == STATUS_FAILED, Job.finished_at.is_not(None), Job.finished_at >= cutoff,
            ),
            visible,
        )
    ).scalar_one()
    # 평균 처리 시간은 성공한 건만 잰다 — 실패는 재시도 백오프까지 걸린 시간이 섞여
    # "얼마나 걸리는가"가 아니라 "몇 번 재시도했는가"를 재게 된다. SQLite 날짜 함수
    # (julianday 등) 대신 파이썬에서 직접 뺀다 — 이 저장소에 그 함수를 쓴 전례가 없고,
    # 시각 컬럼 하나가 예상과 다른 문자열 표현으로 저장되면 조용히 틀린 값을 낼 수 있어
    # (이 코드베이스가 UTC 저장·시간대 변환에 유난히 조심하는 이유와 같다) 검증된 파이썬
    # datetime 뺄셈이 더 안전하다. 이 요약은 /jobs 화면이 4초마다 폴링하므로(DataScreen의
    # summary.poll) 건수가 많은 설치에서 매번 무제한 행을 끌어오지 않게 최근 200건으로
    # 상한을 둔다 — "최근 추세"가 목적이지 전수 집계가 아니다.
    recent_succeeded = db.execute(
        apply_scope(
            select(Job.started_at, Job.finished_at).where(
                Job.status == STATUS_SUCCEEDED, Job.started_at.is_not(None),
                Job.finished_at.is_not(None), Job.finished_at >= cutoff,
            ),
            visible,
        ).order_by(Job.finished_at.desc()).limit(200)
    ).all()
    avg_processing_seconds = (
        round(
            sum((finished - started).total_seconds() for started, finished in recent_succeeded)
            / len(recent_succeeded),
            1,
        )
        if recent_succeeded else None
    )
    return {
        "queued": counts.get(STATUS_QUEUED, 0),
        "running": counts.get(STATUS_RUNNING, 0),
        "succeeded": counts.get(STATUS_SUCCEEDED, 0),
        "failed": counts.get(STATUS_FAILED, 0),
        "cancelled": counts.get(STATUS_CANCELLED, 0),
        "ready": ready,
        "oldest_queued_at": oldest_queued.isoformat() if oldest_queued else None,
        "recent_failed_24h": recent_failed,
        "avg_processing_seconds_24h": avg_processing_seconds,
    }
