"""Schedule management API (spec §18, §23.6)."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.jobs import repository as jobs_repo
from app.schedules import cron
from app.schedules.models import (
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    TARGET_SYSTEM,
    TARGET_WORKFLOW,
    TYPE_CRON,
    TYPE_ONCE,
    Schedule,
    ScheduleRun,
)
from app.schedules.scheduler import (
    _has_active_run,
    advance_next_run,
    create_run_and_enqueue,
)
from app.workflows.models import Workflow

router = APIRouter(
    prefix="/api/admin/schedules",
    tags=["admin-schedules"],
    dependencies=[Depends(require_csrf)],
)


SYSTEM_TARGETS = frozenset({"noop"})


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    schedule_type: str = TYPE_CRON
    cron_expression: str | None = Field(default=None, max_length=120)
    preset: str | None = None  # daily | weekly | monthly → cron_expression
    run_at: str | None = None  # ISO, for once type
    timezone: str = "Asia/Seoul"
    target_type: str
    target_ref: str = Field(min_length=1, max_length=64)
    payload_template: dict = Field(default_factory=dict)
    retry_policy: dict = Field(default_factory=dict)
    misfire_policy: str = "skip"
    concurrency_policy: str = "skip"
    timeout_seconds: int = Field(default=180, ge=1, le=3600)
    start_at: str | None = None
    end_at: str | None = None

    @field_validator("schedule_type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in {TYPE_CRON, TYPE_ONCE}:
            raise ValueError("schedule_type은 cron 또는 once여야 합니다.")
        return v

    @field_validator("misfire_policy", mode="before")
    @classmethod
    def _misfire_default(cls, v):
        # 관리자 콘솔 select가 미선택 상태를 명시적 null로 보낼 수 있다 — 필드엔
        # 기본값이 있으므로 null은 그 기본값(skip)으로 본다(payload_template과 동일 패턴).
        return "skip" if v is None else v

    @field_validator("misfire_policy")
    @classmethod
    def _misfire_known(cls, v: str) -> str:
        if v not in {"skip", "run_once"}:
            raise ValueError("misfire_policy는 skip 또는 run_once여야 합니다.")
        return v

    @field_validator("concurrency_policy", mode="before")
    @classmethod
    def _concurrency_default(cls, v):
        return "skip" if v is None else v

    @field_validator("concurrency_policy")
    @classmethod
    def _concurrency_known(cls, v: str) -> str:
        if v not in {"skip", "allow"}:
            raise ValueError("concurrency_policy는 skip 또는 allow여야 합니다.")
        return v

    @field_validator("target_type")
    @classmethod
    def _target_known(cls, v: str) -> str:
        if v not in {TARGET_WORKFLOW, TARGET_SYSTEM}:
            raise ValueError("target_type은 workflow 또는 system이어야 합니다.")
        return v

    @field_validator("payload_template", "retry_policy", mode="before")
    @classmethod
    def _serializable(cls, v):
        # 관리자 콘솔의 빈 JSON 입력은 null로 온다 — 선택 필드이므로 빈 객체로 본다(round16 스윕 B2).
        if v is None:
            return {}
        if isinstance(v, dict):
            json.dumps(v)
        return v


def _parse_iso(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationAppError(f"{field} 형식이 올바르지 않습니다 (ISO 8601).") from None
    if parsed.tzinfo is not None:
        from datetime import timezone as _tz

        parsed = parsed.astimezone(_tz.utc).replace(tzinfo=None)
    return parsed


def _view(row: Schedule) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "schedule_type": row.schedule_type,
        "cron_expression": row.cron_expression,
        "timezone": row.timezone,
        "owner_user_id": row.owner_user_id,
        "target_type": row.target_type,
        "target_ref": row.target_ref,
        "payload_template": json.loads(row.payload_template_json),
        "retry_policy": json.loads(row.retry_policy_json),
        "misfire_policy": row.misfire_policy,
        "concurrency_policy": row.concurrency_policy,
        "timeout_seconds": row.timeout_seconds,
        "enabled": row.enabled,
        "start_at": row.start_at.isoformat() if row.start_at else None,
        "end_at": row.end_at.isoformat() if row.end_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        # once 스케줄은 편집 시 run_at 입력을 다시 채워야 한다 — 편집 폼이 비어 있으면
        # FormModal이 빈 필드를 생략해 PUT에 run_at이 빠지고 서버가 422로 거부한다. 저장된
        # 실행 시각(next_run_at)을 run_at으로 되돌려줘서 편집 왕복을 성립시킨다.
        "run_at": (
            row.next_run_at.isoformat()
            if row.schedule_type == TYPE_ONCE and row.next_run_at
            else None
        ),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "created_at": row.created_at.isoformat(),
    }


def _run_view(run: ScheduleRun) -> dict:
    return {
        "id": run.id,
        "schedule_id": run.schedule_id,
        "scheduled_at": run.scheduled_at.isoformat(),
        "status": run.status,
        "request_payload": json.loads(run.request_payload_json or "{}"),
        "response_summary": run.response_summary,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error_message": run.error_message,
        "retry_count": run.retry_count,
        "created_at": run.created_at.isoformat(),
    }


def _get_or_404(db: Session, schedule_id: str) -> Schedule:
    row = db.get(Schedule, schedule_id)
    if row is None:
        raise NotFoundError("Schedule을 찾을 수 없습니다.")
    return row


def _require_execution_gate(row: Schedule) -> None:
    """승인 게이트(schedule.enable)가 지키는 것은 '이 정의로 실제 실행하는 것'이다.

    수동 실행이든 실패한 실행의 재시도든 같은 문을 지나야 한다. 아직 활성화되지 않은
    정의는 승인을 받은 적이 없으므로 어떤 경로로도 돌릴 수 없다 (spec §20). 실행을
    시작하는 모든 경로가 이 함수를 부르게 해서 한쪽만 검사가 빠지는 일을 막는다.
    """
    if not row.enabled:
        raise ConflictError(
            "비활성 스케줄은 실행할 수 없습니다. 먼저 활성화(승인)하세요."
        )


def _validate_and_normalize(db: Session, payload: ScheduleRequest, now: datetime) -> dict:
    cron.validate_timezone(payload.timezone)
    cron_expression = payload.cron_expression
    run_at = _parse_iso(payload.run_at, "run_at")

    if payload.schedule_type == TYPE_CRON:
        if payload.preset:
            if payload.preset not in cron.PRESETS:
                raise ValidationAppError(
                    f"preset은 {sorted(cron.PRESETS)} 중 하나여야 합니다."
                )
            cron_expression = cron.PRESETS[payload.preset]
        if not cron_expression:
            raise ValidationAppError("cron 스케줄에는 cron_expression 또는 preset이 필요합니다.")
        cron.validate_cron(cron_expression)
        # 폼은 cron/once 필드를 동시에 보여준다(프런트에 조건부 표시가 없다) — schedule_type을
        # 나중에 once→cron으로 바꾼 편집 요청이 이전 run_at을 그대로 실어 보내면, 그 값이
        # 여기서 안 지워질 경우 DB에 죽은 run_at이 남아 다음 조회/판단을 오염시킨다. 이 타입에
        # 안 쓰는 필드는 정의 시점에 확실히 비운다.
        run_at = None
    else:  # once
        if run_at is None:
            raise ValidationAppError("once 스케줄에는 run_at이 필요합니다.")
        if run_at <= now:
            raise ValidationAppError("run_at은 미래 시각이어야 합니다.")
        # 위와 대칭: cron→once로 바꾼 편집이 이전 cron_expression/preset을 그대로 실어 보내도
        # once 스케줄에는 안 쓰는 값이므로 여기서 비운다.
        cron_expression = None

    if payload.target_type == TARGET_WORKFLOW:
        workflow = db.get(Workflow, payload.target_ref)
        if workflow is None:
            raise ValidationAppError("target_ref에 해당하는 Workflow가 없습니다.")
        # 스케줄(cron/once) 실행은 승인 응답을 채울 사람이 없어 payload.approved가 항상 False다.
        # write + approval_required workflow를 대상으로 하면 app/jobs/handlers/schedule_run.py가
        # 매번 PermanentJobError로 실패한다 — 절대 성공할 수 없는 조합이므로 정의 시점에 막는다.
        if workflow.operation_mode == "write" and workflow.approval_required:
            raise ValidationAppError(
                "승인이 필요한 쓰기(write) Workflow는 스케줄로 자동 실행할 수 없습니다"
                "(실행마다 승인이 필요해 예약 실행이 매번 실패합니다). 승인 필요 없음으로 설정하거나"
                " 다른 워크플로를 선택하세요."
            )
    else:
        if payload.target_ref not in SYSTEM_TARGETS:
            raise ValidationAppError(
                f"system target은 {sorted(SYSTEM_TARGETS)} 중 하나여야 합니다."
            )

    start_at = _parse_iso(payload.start_at, "start_at")
    end_at = _parse_iso(payload.end_at, "end_at")
    if start_at and end_at and end_at <= start_at:
        raise ValidationAppError("end_at은 start_at 이후여야 합니다.")
    # run_at이 start_at보다 빠르면 once 스케줄이 활성화된 뒤 매 tick마다 start_at 게이트에
    # 막혀 재평가만 반복하다 결국 misfire로 흘러간다. 정의 시점에 막는다(once/ start_at 둘 다
    # 있을 때만 — cron은 run_at이 없다).
    if run_at is not None and start_at is not None and run_at < start_at:
        raise ValidationAppError(
            "run_at은 start_at 이후여야 합니다 (once 스케줄의 실행 시각이 시작 시각보다 빠릅니다)."
        )

    return {
        "cron_expression": cron_expression,
        "run_at": run_at,
        "start_at": start_at,
        "end_at": end_at,
    }


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_schedules(db: Session = Depends(get_db)):
    rows = db.execute(select(Schedule).order_by(Schedule.name)).scalars().all()
    return {"items": [_view(r) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_schedule(request: Request, payload: ScheduleRequest, db: Session = Depends(get_db)):
    now = request.app.state.clock.now()
    normalized = _validate_and_normalize(db, payload, now)
    if db.execute(
        select(Schedule).where(Schedule.name == payload.name)
    ).scalar_one_or_none() is not None:
        raise ConflictError(f"이미 존재하는 Schedule 이름입니다: {payload.name}")

    row = Schedule(
        name=payload.name,
        description=payload.description,
        schedule_type=payload.schedule_type,
        cron_expression=normalized["cron_expression"],
        timezone=payload.timezone,
        owner_user_id=request.state.user.id,
        target_type=payload.target_type,
        target_ref=payload.target_ref,
        payload_template_json=json.dumps(payload.payload_template, ensure_ascii=False),
        retry_policy_json=json.dumps(payload.retry_policy, ensure_ascii=False),
        misfire_policy=payload.misfire_policy,
        concurrency_policy=payload.concurrency_policy,
        timeout_seconds=payload.timeout_seconds,
        enabled=False,
        start_at=normalized["start_at"],
        end_at=normalized["end_at"],
        next_run_at=normalized["run_at"],  # once형은 여기 저장; cron형은 enable 시 계산
    )
    db.add(row)
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.create", object_type="schedule",
        object_id=row.id, after=_view(row),
    )
    return {"schedule": _view(row)}


@router.get("/{schedule_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_schedule(schedule_id: str, db: Session = Depends(get_db)):
    return {"schedule": _view(_get_or_404(db, schedule_id))}


@router.put("/{schedule_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_schedule(
    request: Request,
    schedule_id: str,
    payload: ScheduleRequest,
    db: Session = Depends(get_db),
):
    from app.approvals.service import needs_approval
    from app.schedules.service import definition_snapshot

    row = _get_or_404(db, schedule_id)
    now = request.app.state.clock.now()
    normalized = _validate_and_normalize(db, payload, now)
    if payload.name != row.name:
        clash = db.execute(
            select(Schedule).where(Schedule.name == payload.name, Schedule.id != row.id)
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError(f"이미 존재하는 Schedule 이름입니다: {payload.name}")
    before = _view(row)
    approved_definition = definition_snapshot(row)

    row.name = payload.name
    row.description = payload.description
    row.schedule_type = payload.schedule_type
    row.cron_expression = normalized["cron_expression"]
    row.timezone = payload.timezone
    row.target_type = payload.target_type
    row.target_ref = payload.target_ref
    row.payload_template_json = json.dumps(payload.payload_template, ensure_ascii=False)
    row.retry_policy_json = json.dumps(payload.retry_policy, ensure_ascii=False)
    row.misfire_policy = payload.misfire_policy
    row.concurrency_policy = payload.concurrency_policy
    row.timeout_seconds = payload.timeout_seconds
    row.start_at = normalized["start_at"]
    row.end_at = normalized["end_at"]
    # enabled의 뜻은 '이 정의가 승인 게이트를 통과했다'이다. 승인이 필요한 사용자가
    # 활성 스케줄의 정의를 바꾸면 그 뜻이 깨진다 — 승인받은 적 없는 정의가 계속 돌고,
    # run_now도 enabled만 보므로 게이트가 통째로 우회된다. 활성 상태를 내려 다시
    # 승인을 받게 한다 (승인 대기 중 변조를 막는 stale 검사와 같은 불변식).
    if (
        row.enabled
        and definition_snapshot(row) != approved_definition
        and needs_approval(request.state.user)
    ):
        row.enabled = False
        row.next_run_at = None
    elif row.enabled:
        # Re-anchor the next occurrence under the new definition.
        if row.schedule_type == TYPE_ONCE:
            row.next_run_at = normalized["run_at"]
        else:
            row.next_run_at = cron.next_after(row.cron_expression, row.timezone, now)
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.update", object_type="schedule",
        object_id=row.id, before=before, after=_view(row),
    )
    return {"schedule": _view(row)}


@router.post("/{schedule_id}/enable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def enable_schedule(request: Request, schedule_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, schedule_id)
    now = request.app.state.clock.now()

    # Spec §20: Schedule 활성화는 승인 대상 — system_admin만 즉시 적용.
    from app.approvals.service import approval_view, create_approval, needs_approval

    if needs_approval(request.state.user):
        from app.schedules.service import definition_snapshot

        approval = create_approval(
            db,
            request_type="schedule.enable",
            object_type="schedule",
            object_id=row.id,
            requested_by=request.state.user,
            # 승인자는 object_id가 아니라 '이 정의'를 승인한다. 스냅샷이 승인 화면의
            # 표시 근거이자, 실행 직전 정의 변조(TOCTOU) 판정 기준이 된다.
            payload={"definition": definition_snapshot(row)},
            now=now,
        )
        record_audit_from_request(
            request, db, action="schedule.enable_requested", object_type="schedule",
            object_id=row.id, after={"approval_id": approval.id},
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=202,
            content={"status": "approval_pending", "approval": approval_view(approval)},
        )

    if row.schedule_type == TYPE_ONCE:
        if row.next_run_at is None or row.next_run_at <= now:
            raise ConflictError("once 스케줄의 실행 시각이 이미 지났습니다.")
        # 활성화 시점에도 run_at < start_at을 거부한다 — 정의는 create/update에서 막지만,
        # start_at만 나중에 바뀌는 등으로 어긋난 상태가 게이트를 통과하지 못하게 한다.
        if row.start_at is not None and row.next_run_at < row.start_at:
            raise ValidationAppError(
                "run_at은 start_at 이후여야 합니다 (once 스케줄의 실행 시각이 시작 시각보다 빠릅니다)."
            )
    else:
        anchor = max(now, row.start_at) if row.start_at else now
        row.next_run_at = cron.next_after(row.cron_expression, row.timezone, anchor)
    row.enabled = True
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.enable", object_type="schedule",
        object_id=row.id, after={"next_run_at": row.next_run_at.isoformat()},
    )
    return {"schedule": _view(row)}


@router.post("/{schedule_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_schedule(request: Request, schedule_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, schedule_id)
    row.enabled = False
    # next_run_at은 '이 시각에 실행될 예정'이라는 뜻이다 — enabled만 내리고 이 값을
    # 남겨 두면 '다음 실행' 열이 여전히 (때로는 미래의) 실제 시각을 보여줘, 활성 배지를
    # 함께 보지 않는 한 '이건 이제 안 돈다'는 사실을 놓치기 쉽다. 비활성화는 예정된
    # 실행이 없다는 뜻이므로 함께 지운다(재활성화 시 enable_schedule이 다시 계산한다).
    row.next_run_at = None
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.disable", object_type="schedule", object_id=row.id,
    )
    return {"schedule": _view(row)}


@router.post("/{schedule_id}/dry-run", dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))])
def dry_run(request: Request, schedule_id: str, db: Session = Depends(get_db)):
    """Payload preview + next fire times — no execution (spec §18.6)."""
    row = _get_or_404(db, schedule_id)
    now = request.app.state.clock.now()
    fire_times: list[str] = []
    if row.schedule_type == TYPE_ONCE:
        if row.next_run_at:
            fire_times = [row.next_run_at.isoformat()]
    else:
        cursor = now
        for _ in range(3):
            cursor = cron.next_after(row.cron_expression, row.timezone, cursor)
            fire_times.append(cursor.isoformat())
    return {
        "payload_preview": json.loads(row.payload_template_json),
        "target_type": row.target_type,
        "target_ref": row.target_ref,
        "next_fire_times_utc": fire_times,
    }


async def _optional_json_body(request: Request) -> dict:
    """run_now의 본문은 선택적이다(빈 본문이면 {}). sync 핸들러(§2 불변 규칙 1)에서는
    `await request.json()`을 할 수 없으므로 본문 읽기를 async 의존성으로 분리한다."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


@router.post("/{schedule_id}/run-now", dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))])
def run_now(
    request: Request,
    schedule_id: str,
    body: dict = Depends(_optional_json_body),
    db: Session = Depends(get_db),
):
    # sync 핸들러(§2 불변 규칙 1): 동기 SQLAlchemy·enqueue가 이벤트 루프를 막지 않는다.
    row = _get_or_404(db, schedule_id)
    now = request.app.state.clock.now()
    if body.get("dry_run"):
        return dry_run(request, schedule_id, db)

    _require_execution_gate(row)

    # 더블클릭·연타로 인한 중복 실행 방지. 이미 대기·실행 중인 run이 있으면 새 run을
    # 만들지 않고 그 run을 돌려준다(scheduler의 동시 실행 방지와 같은 불변식). 그리고
    # idempotency 키는 마이크로초가 아니라 초 단위로 — 같은 초 안의 연타는 UNIQUE 제약이
    # 흡수하고, 그 이후의 연타는 아래 active-run 가드가 막는다.
    if _has_active_run(db, row.id):
        active_run = (
            db.execute(
                select(ScheduleRun)
                .where(
                    ScheduleRun.schedule_id == row.id,
                    ScheduleRun.status.in_([RUN_QUEUED, RUN_RUNNING]),
                )
                .order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
            )
            .scalars()
            .first()
        )
        return {
            "ok": True,
            "run": _run_view(active_run) if active_run else None,
            "deduplicated": True,
        }

    key = f"manual:{row.id}:{now.strftime('%Y%m%d%H%M%S')}"
    run = create_run_and_enqueue(
        db, row, scheduled_at=now, now=now, key=key, manual=True
    )
    # The scheduler's automatic tick (scheduler.py:_process) sets
    # schedule.last_run_at, but this manual '지금 실행' path never did — a
    # schedule run only ever via run-now (e.g. every 'once' schedule started
    # manually, or an admin always clicking run-now instead of waiting) shows
    # '마지막 실행' as permanently blank even though it has, in fact, run.
    if run is not None:
        row.last_run_at = now
    record_audit_from_request(
        request, db, action="schedule.run_now", object_type="schedule",
        object_id=row.id, after={"run_id": run.id if run else None},
    )
    return {"ok": True, "run": _run_view(run) if run else None}


@router.get("/{schedule_id}/runs", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def run_history(
    schedule_id: str,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=16),
):
    _get_or_404(db, schedule_id)
    stmt = select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id)
    if status:
        stmt = stmt.where(ScheduleRun.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [_run_view(r) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.post("/runs/{run_id}/retry", dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))])
def retry_run(request: Request, run_id: str, db: Session = Depends(get_db)):
    run = db.get(ScheduleRun, run_id)
    if run is None:
        raise NotFoundError("실행 이력을 찾을 수 없습니다.")
    if run.status != RUN_FAILED:
        raise ConflictError("실패한 실행만 재시도할 수 있습니다.")
    schedule = _get_or_404(db, run.schedule_id)
    _require_execution_gate(schedule)
    now = request.app.state.clock.now()

    run.status = "queued"
    run.error_message = None
    run.finished_at = None
    # 재시도는 새 실행 시도다. started_at을 지우지 않으면 핸들러가 기존 값을 유지해
    # (started_at or now) 소요시간이 이전 실패 시도부터 계산되어 실제보다 길게 보인다.
    run.started_at = None
    # Same '마지막 실행' gap as run_now above: a run-history retry re-enqueues
    # the schedule_run job directly (bypassing scheduler.py:_process, the only
    # other writer of last_run_at), so a schedule whose only executions were
    # retries would never show a last-run timestamp at all.
    schedule.last_run_at = now
    db.flush()
    jobs_repo.enqueue(
        db,
        job_type="schedule_run",
        payload={"schedule_run_id": run.id, "schedule_id": schedule.id, "manual": True},
        now=now,
        idempotency_key=f"schedrun-retry:{run.id}:{now.strftime('%Y%m%d%H%M%S%f')}",
    )
    record_audit_from_request(
        request, db, action="schedule.retry_run", object_type="schedule_run",
        object_id=run.id,
    )
    return {"ok": True, "run": _run_view(run)}
