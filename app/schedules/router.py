"""Schedule management API (spec §18, §23.6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import people
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.jobs import repository as jobs_repo
from app.jobs.models import STATUS_QUEUED, STATUS_RUNNING, Job
from app.schedules import cron
from app.schedules.models import (
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_SKIPPED,
    TARGET_SYSTEM,
    TARGET_WORKFLOW,
    TYPE_CRON,
    TYPE_ONCE,
    Schedule,
    ScheduleRun,
)
from app.schedules.scheduler import (
    _has_active_run,
    _max_attempts,
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


def _view(row: Schedule, names: dict | None = None, workflow_names: dict | None = None) -> dict:
    """`names` 는 {user_id: {display_name, email}} (app/core/people.py::name_map).
    `workflow_names` 는 {workflow_id: name}(USE-04/SCHD-02 — target_ref가 워크플로 UUID 원문뿐이라
    관리 화면이 그 UUID를 그대로 그렸다. 워크플로 화면은 이미 이름을 안다).

    소유자를 UUID 로만 주면 관리 화면은 그 UUID 를 그대로 그릴 수밖에 없다 — 운영자는
    "이 스케줄이 누구 것이냐" 를 알아내려고 사용자 화면을 따로 열어 id 를 검색해야 했다.
    id 자체는 계속 싣는다: 감사 로그 필터에 붙여 넣는 값이고, 이름이 겹칠 때 최종
    구분자이기도 하다. **이름을 더하는 것이지 id 를 감추는 것이 아니다.**

    `names`/`workflow_names` 를 안 주면 이름은 None 이다(모르는 것을 지어내지 않는다) — 목록
    경로만 배치로 해석하고, 단건 응답은 예전 모양 그대로 둔다.
    """
    owner = (names or {}).get(row.owner_user_id) or {}
    target_name = (
        (workflow_names or {}).get(row.target_ref)
        if row.target_type == TARGET_WORKFLOW
        else None
    )
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "schedule_type": row.schedule_type,
        "cron_expression": row.cron_expression,
        "timezone": row.timezone,
        "owner_user_id": row.owner_user_id,
        "owner_name": owner.get("display_name"),
        "owner_email": owner.get("email"),
        "target_type": row.target_type,
        "target_ref": row.target_ref,
        "target_name": target_name,
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
    # 소유자 이름은 **한 번의 질의로** 모아 온다 — 행마다 조회하면 이 목록이 N+1 이 된다.
    names = people.name_map(db, [r.owner_user_id for r in rows])
    workflow_ids = [r.target_ref for r in rows if r.target_type == TARGET_WORKFLOW]
    workflow_names = dict(
        db.execute(select(Workflow.id, Workflow.name).where(Workflow.id.in_(workflow_ids))).all()
    ) if workflow_ids else {}
    return {"items": [_view(r, names, workflow_names) for r in rows]}


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


# 스케줄러 캘린더 (0033, PLAN Phase 6).
# 정적 경로는 `/{schedule_id}` **앞에** 있어야 한다 — 뒤에 두면 FastAPI 가 등록 순서대로
# 매칭해 "calendar 라는 Schedule 을 찾을 수 없습니다"(404)가 된다.
@router.get("/calendar", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def calendar(
    request: Request,
    db: Session = Depends(get_db),
    start: str = Query(description="조회 구간 시작(ISO 8601). 예: 2026-08-01T00:00:00+09:00"),
    end: str = Query(description="조회 구간 끝(ISO 8601, 미포함)"),
    schedule_id: str | None = Query(default=None, max_length=36),
) -> dict:
    """구간 안의 실행 일정 — **지난 실행(사실)과 앞으로의 예정(계산)을 함께** 돌려준다.

    달력이 예정만 보여 주면 "어제 그 일이 돌긴 했나"에 답하지 못하고, 실행 이력만 보여 주면
    "내일 몇 시에 도는가"에 답하지 못한다. 관리자가 달력을 여는 이유는 대개 둘 중 하나라서
    한 응답에 담는다. `kind` 로 구분한다: `run`(실제 실행) / `planned`(아직 안 온 예정).

    예정은 `cron.next_after` 를 반복해 전개한다. `Schedule.next_run_at` 은 **다음 한 번**만
    들고 있어서 그것만 그리면 달력에 점이 스케줄당 하나씩만 찍힌다.

    상한: 스케줄당 최대 `MAX_OCCURRENCES` 개. 매분 도는 cron 을 한 달치 전개하면 4만 개가
    나와 브라우저가 멈춘다 — 잘렸다는 사실은 `truncated` 로 정직하게 알린다(숨기면 관리자가
    "이 시간엔 아무 일도 없구나"라고 잘못 읽는다).
    """
    MAX_OCCURRENCES = 200
    MAX_RANGE_DAYS = 92

    start_at = _parse_iso(start, "start")
    end_at = _parse_iso(end, "end")
    if start_at is None or end_at is None:
        raise ValidationAppError("start 와 end 는 ISO 8601 형식이어야 합니다.")
    if end_at <= start_at:
        raise ValidationAppError("end 는 start 보다 뒤여야 합니다.")
    if (end_at - start_at).days > MAX_RANGE_DAYS:
        raise ValidationAppError(f"조회 구간은 최대 {MAX_RANGE_DAYS}일입니다.")

    now = request.app.state.clock.now()
    stmt = select(Schedule)
    if schedule_id:
        stmt = stmt.where(Schedule.id == schedule_id)
    schedules = db.execute(stmt.order_by(Schedule.name)).scalars().all()
    by_id = {s.id: s for s in schedules}

    events: list[dict] = []

    # 1) 실제 실행 이력 — 사실이므로 먼저 담는다.
    run_stmt = select(ScheduleRun).where(
        ScheduleRun.scheduled_at >= start_at, ScheduleRun.scheduled_at < end_at
    )
    if schedule_id:
        run_stmt = run_stmt.where(ScheduleRun.schedule_id == schedule_id)
    for run in db.execute(run_stmt.order_by(ScheduleRun.scheduled_at)).scalars().all():
        parent = by_id.get(run.schedule_id)
        events.append({
            "kind": "run",
            "schedule_id": run.schedule_id,
            "schedule_name": parent.name if parent else None,
            "occurs_at": run.scheduled_at.isoformat(),
            "status": run.status,
            "run_id": run.id,
            "error_message": run.error_message,
        })

    # 2) 앞으로의 예정 — 이미 실행 행이 있는 시각은 건너뛴다(같은 점이 두 번 찍히지 않게).
    seen = {(e["schedule_id"], e["occurs_at"]) for e in events}
    truncated = False
    for schedule in schedules:
        if not schedule.enabled:
            continue
        if schedule.schedule_type == TYPE_ONCE:
            if schedule.next_run_at and start_at <= schedule.next_run_at < end_at:
                key = (schedule.id, schedule.next_run_at.isoformat())
                if key not in seen:
                    events.append({
                        "kind": "planned",
                        "schedule_id": schedule.id,
                        "schedule_name": schedule.name,
                        "occurs_at": schedule.next_run_at.isoformat(),
                        "status": None,
                        "run_id": None,
                        "error_message": None,
                    })
            continue
        if not schedule.cron_expression:
            continue
        cursor = max(start_at, now) - timedelta(seconds=1)
        produced = 0
        while produced < MAX_OCCURRENCES:
            try:
                nxt = cron.next_after(schedule.cron_expression, schedule.timezone, cursor)
            except Exception:
                # 표현식 하나가 망가진 스케줄 때문에 달력 전체가 500 이 되면 안 된다.
                break
            if nxt is None or nxt >= end_at:
                break
            if schedule.end_at is not None and nxt >= schedule.end_at:
                break
            cursor = nxt
            produced += 1
            key = (schedule.id, nxt.isoformat())
            if key in seen:
                continue
            events.append({
                "kind": "planned",
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "occurs_at": nxt.isoformat(),
                "status": None,
                "run_id": None,
                "error_message": None,
            })
        if produced >= MAX_OCCURRENCES:
            truncated = True

    events.sort(key=lambda e: (e["occurs_at"], e["schedule_name"] or ""))
    return {
        "items": events,
        "start": start_at.isoformat(),
        "end": end_at.isoformat(),
        "truncated": truncated,
        "schedules": [
            {"id": s.id, "name": s.name, "enabled": s.enabled, "timezone": s.timezone}
            for s in schedules
        ],
    }


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
        # create_run_and_enqueue(스케줄러 tick, run-now)는 스케줄의 retry_policy를
        # 잡의 max_attempts로 싣는다. 여기서 빠뜨리면 jobs_repo.enqueue 기본값(3)이
        # 조용히 대신 쓰여, "재시도 안 함"(max_attempts=1)으로 설정한 스케줄도 운영자가
        # '재시도'를 누르는 순간부터 최대 3회까지 자동 재시도하게 된다.
        max_attempts=_max_attempts(schedule),
    )
    record_audit_from_request(
        request, db, action="schedule.retry_run", object_type="schedule_run",
        object_id=run.id,
    )
    return {"ok": True, "run": _run_view(run)}


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))])
def cancel_run(request: Request, run_id: str, db: Session = Depends(get_db)):
    """실행 이력 화면(달력)이 run_id 만 갖고 있어 취소할 방법이 없다는 지적(M9)에 대한 응답.

    `app/jobs/router.py::cancel` 은 job_id 기준이라 여기서는 못 쓴다 — ScheduleRun 에
    job_id 를 직접 저장하는 컬럼이 없어(잡을 만들 때 payload 에 schedule_run_id 를 실어
    보내는 반대 방향 참조만 있다), payload_json 에서 이 run_id 를 실은 대기/실행 중
    잡을 거꾸로 찾는다. json.dumps 의 기본 구분자(`": "`, `", "`)가 안정적이라 값 앞뒤로
    따옴표를 포함한 부분 문자열 매칭으로 충분하다(그러지 않으면 다른 run_id 의 부분
    문자열과 우연히 겹칠 수 있다 — 값 전체를 따옴표로 감싸 매칭하면 그 위험이 없다)."""
    run = db.get(ScheduleRun, run_id)
    if run is None:
        raise NotFoundError("실행 이력을 찾을 수 없습니다.")
    if run.status not in (RUN_QUEUED, RUN_RUNNING):
        raise ConflictError("대기 또는 실행 중인 실행만 취소할 수 있습니다.")
    now = request.app.state.clock.now()

    needle = f'"schedule_run_id": "{run.id}"'
    job = db.execute(
        select(Job).where(
            Job.job_type == "schedule_run",
            Job.status.in_([STATUS_QUEUED, STATUS_RUNNING]),
            Job.payload_json.like(f"%{needle}%"),
        )
    ).scalars().first()
    if job is not None:
        jobs_repo.cancel_queued(db, job, now=now)

    run.status = RUN_SKIPPED
    run.finished_at = now
    run.error_message = "운영자가 취소했습니다."
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.cancel_run", object_type="schedule_run",
        object_id=run.id, after={"job_cancelled": job is not None},
    )
    return {"ok": True, "run": _run_view(run)}
