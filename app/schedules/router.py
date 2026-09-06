"""Schedule management API (spec §18, §23.6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core import people
from app.core.audit import audit_failure_on_exception, record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.db import is_insert_race
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.core.scope import Principal, require_global_management
from app.core.sort import SortParams, SortSpec, order_by
from app.jobs import repository as jobs_repo
from app.jobs.models import STATUS_QUEUED, STATUS_RUNNING, Job
from app.schedules import cron
from app.schedules.models import (
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_SKIPPED,
    TARGET_SYSTEM,
    TYPE_CRON,
    TYPE_ONCE,
    Schedule,
    ScheduleRun,
)
from app.schedules.scheduler import (
    MAX_ATTEMPTS_CEILING,
    MAX_ATTEMPTS_FLOOR,
    UNREADABLE_RETRY_POLICY_MESSAGE,
    InvalidRetryPolicy,
    _has_active_run,
    _max_attempts,
    advance_next_run,
    create_run_and_enqueue,
)
from app.schedules.service import (
    definition_snapshot,
    definition_version,
    ensure_enablable,
)

router = APIRouter(
    prefix="/api/admin/schedules",
    tags=["admin-schedules"],
    dependencies=[Depends(require_csrf)],
)


SYSTEM_TARGETS = frozenset({"noop"})


class ScheduleRequest(BaseModel):
    # 모르는 필드를 조용히 버리지 않는다. 이 스키마의 이름 대부분이 컬럼 이름과 같아서
    # (`enabled`·`owner_user_id`·`next_run_at`·`last_run_at`) 그 이름을 실어 보낸 쪽은
    # 값이 반영됐다고 믿는다 — 200 만 받고는 아무 일도 없었다는 것을 알 방법이 없다.
    model_config = ConfigDict(extra="forbid")

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
    #: 편집을 시작한 시점의 판(`_view` 의 `base_version` 을 그대로 돌려보낸다). 보내면 그
    #: 사이 다른 사람이 먼저 저장했을 때 409 로 막는다. 안 보내면 예전대로 동작한다 —
    #: 새 계약을 강제해 기존 클라이언트를 깨뜨리지 않는다(app/projects/service.py
    #: ::ensure_not_changed 와 같은 규약).
    base_version: str | None = Field(default=None, max_length=64)

    @field_validator("name", mode="before")
    @classmethod
    def _name_not_blank(cls, v):
        # `min_length=1` 은 공백 문자도 한 자로 센다 — 이름이 공백뿐인 행은 목록에서도
        # 검색에서도 감사 로그에서도 지목할 수 없고, 이름이 유니크 키라 이름 공간까지
        # 차지한다. 부서·직책·사용자 이름이 이미 지키는 규칙과 같은 규칙이다.
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("이름을 입력해야 합니다.")
        return v

    @field_validator("schedule_type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in {TYPE_CRON, TYPE_ONCE}:
            raise ValueError("schedule_type은 cron 또는 once여야 합니다.")
        return v

    # UX-41: misfire_policy/concurrency_policy는 이미 이 null 코어싱을 받고 있었는데
    # (아래), 같은 폼의 timezone/timeout_seconds 두 칸만 빠져 있었다 — 콘솔이 지워진
    # 선택 칸을 명시적 null로 보내면 스키마 기본값 대신 422가 났다(같은 패턴, 같은 이유).
    @field_validator("timezone", mode="before")
    @classmethod
    def _timezone_default(cls, v):
        return "Asia/Seoul" if v is None else v

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _timeout_default(cls, v):
        return 180 if v is None else v

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
        if v != TARGET_SYSTEM:
            # S11 이 n8n 을 걷어내면서 workflow 대상이 사라졌다. 남겨 두면 화면이 고를 수
            # 있는 대상으로 계속 보여 주고 실행은 매번 실패한다.
            raise ValueError("target_type은 system이어야 합니다.")
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

    @field_validator("retry_policy")
    @classmethod
    def _retry_policy_runnable(cls, v):
        """재시도 횟수는 **저장 시점에** 본다 — 실행 시점에 보면 이미 늦다.

        `scheduler._max_attempts` 가 이 값을 정수로 읽어 잡의 최대 시도 횟수로 싣는다.
        문자열·목록·소수가 들어오면 그 일정은 저장되고 활성화까지 되지만 실행은 매번
        터졌다(수동 실행은 500, 자동 실행은 로그 한 줄).

        여기서 보는 것은 **형**뿐이다. 정수가 아닌 값은 어느 경로로도 실행될 수 없어서
        (`_max_attempts` 가 `InvalidRetryPolicy` 로 올린다) 그 값을 그대로 다시 저장하게
        둘 이유가 없다. 반면 **범위**를 벗어난 정수는 이미 저장돼 멀쩡히 돌고 있다
        (`_max_attempts` 가 예전부터 1~10 으로 잘라 왔다). 그 값을 여기서 거절하면 그 행은
        설명 한 줄도 못 고치게 되므로, 범위는 `current` 를 볼 수 있는
        `_validate_and_normalize` 에서 본다 (target_ref·end_at 과 같은 처리다).
        """
        if not isinstance(v, dict) or "max_attempts" not in v:
            return v
        raw = v["max_attempts"]
        # bool 은 int 의 하위형이다 — True 를 1 로 받으면 잘못 적은 값을 삼키게 된다.
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(
                f"재시도 횟수는 {MAX_ATTEMPTS_FLOOR}~{MAX_ATTEMPTS_CEILING} 사이 정수여야 합니다."
            )
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


def _view(row: Schedule, names: dict | None = None) -> dict:
    """`names` 는 {user_id: {display_name, email}} (app/core/people.py::name_map).

    소유자를 UUID 로만 주면 관리 화면은 그 UUID 를 그대로 그릴 수밖에 없다 — 운영자는
    "이 스케줄이 누구 것이냐" 를 알아내려고 사용자 화면을 따로 열어 id 를 검색해야 했다.
    id 자체는 계속 싣는다: 감사 로그 필터에 붙여 넣는 값이고, 이름이 겹칠 때 최종
    구분자이기도 하다. **이름을 더하는 것이지 id 를 감추는 것이 아니다.**

    `names` 를 안 주면 이름은 None 이다(모르는 것을 지어내지 않는다) — 목록 경로만 배치로
    해석하고, 단건 응답은 예전 모양 그대로 둔다.
    """
    owner = (names or {}).get(row.owner_user_id) or {}
    # 대상은 이제 system 하나뿐이고 그 이름은 target_ref 자신이다(SYSTEM_TARGETS).
    target_name = None
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
        # 편집 폼이 그대로 돌려보내면 낙관적 잠금이 된다(_ensure_not_changed).
        "base_version": _version_of(row),
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


def _version_of(row: Schedule) -> str:
    """이 행의 판 — **정의**에서만 만든다(`app/schedules/service.py::definition_version`).

    정수 판 컬럼을 새로 만들지 않는 이유는 그것이 마이그레이션이기 때문이고, `updated_at`
    을 쓰지 않는 이유는 그 값이 사람의 저장 말고 스케줄러의 실행에도 올라가기 때문이다
    (자세한 근거는 `definition_version` 의 설명에 있다).
    """
    return definition_version(row)


def _ensure_not_changed(row: Schedule, base_version: str | None) -> None:
    """편집을 시작한 뒤 다른 사람이 먼저 저장했으면 막는다.

    일정 정의는 주기·페이로드·재시도 정책이 함께 든 한 벌이고 PUT 은 전체 교체다. 두
    관리자가 각자 다른 칸을 고치면 나중 저장이 앞 저장을 통째로 덮는데, 덮인 쪽은 저장
    성공 토스트를 봤기 때문에 사라진 사실을 알아챌 수 없다.

    `base_version` 을 안 보내면 예전대로 동작한다 — 새 계약을 강제해 기존 클라이언트·CLI 를
    깨뜨리지 않는다(`app/projects/service.py::ensure_not_changed` 와 같은 규약).
    """
    if base_version is None:
        return
    if base_version != _version_of(row):
        raise ConflictError(
            "다른 사람이 먼저 저장했습니다. 새로 고쳐 최신 내용을 확인한 뒤 다시 저장해 주세요."
        )


def _require_global_schedule_write(
    request: Request,
    db: Session,
    principal: Principal,
    *,
    action: str,
    object_id: str | None = None,
) -> None:
    """실행 일정을 바꾸려면 관리 범위가 **전역**이어야 한다.

    역할 게이트(`CONSOLE_WRITE_ROLES`)만으로는 부서 범위 관리자가 그대로 지난다. 전사
    야간 배치는 부서로 나눌 수 있는 자원이 아니라서, 그 사람이 남의 부서 일정을 끄면
    범위를 좁힌 의미가 통째로 사라진다. 판정은 공용 헬퍼가 한다
    (`app/core/scope.py::require_global_management` — 공지·정합성·쿼터가 쓰는 그 판정).

    거절도 감사에 남긴다. **거절된 쓰기 시도**는 흔적 없이 사라지면 안 된다(읽기 거절은
    남기지 않는다 — 화면을 열어 본 것까지 원장에 쌓으면 정작 쓰기 시도가 묻힌다).

    ## 어디에 걸고 어디에 안 거는가 — 정의는 전역, 실행은 운영

    이 문은 **정의를 바꾸는 넷**(생성·수정·활성화·비활성화)에만 건다. 실행을 움직이는
    셋(`지금 실행`·`재시도`·`실행 취소`)에는 일부러 걸지 않는다. 이유는 둘이다.

    1. 그 셋은 `console.ops` 다(`app/core/authz.py`). 그 능력의 정의가 "설정을 바꾸지는
       않지만 부수효과가 있는 것"이고 운영자가 거기 들어 있다 — 운영자는 조직 관리자가
       아니라서 `management_scope` 가 `admin_scope` 값과 무관하게 전역을 주지 않는다
       (`app/core/scope.py`, "운영자·감사자는 관리 콘솔 사용자이지 조직 관리자가 아니다").
       그러니 이 문을 그 셋에 걸면 **모든 운영자**가 실행·재시도·취소를 잃는다. 화면이
       그리는 RBAC 매트릭스가 약속한 것과 서버가 하는 일이 정면으로 갈린다.
    2. 실행은 되돌릴 수 있는 한 번이고, 정의는 지금부터 계속이다. 게다가 실행되는 정의는
       이미 이 문을 지나 승인까지 받은 것이다 — `지금 실행`은 승인받은 일을 한 번 앞당길
       뿐, 승인받지 않은 일을 하지 못한다(`_require_execution_gate`).

    그래서 부서 범위 관리자는 전사 일정을 **끄지는 못해도 한 번 돌릴 수는 있다.** 그 사람은
    운영 축에서 최소한 운영자이고, 아래 있는 운영자에게 허용된 것을 위에서 막을 수 없다.
    (`tests/integration/test_schedules_api.py` 가 이 경계를 그대로 못 박는다.)
    """
    with audit_failure_on_exception(
        request, db, action=action, object_type="schedule", object_id=object_id
    ):
        require_global_management(principal, "실행 일정")


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


def _stored_max_attempts(current: Schedule):
    """이 행에 **이미 저장돼 있는** 재시도 횟수. 읽을 수 없으면 None(비교 대상이 없다)."""
    try:
        policy = json.loads(current.retry_policy_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(policy, dict):
        return None
    return policy.get("max_attempts")


def _validate_and_normalize(
    db: Session,
    payload: ScheduleRequest,
    now: datetime,
    current: Schedule | None = None,
) -> dict:
    """정의를 검증하고 저장할 모양으로 되돌린다.

    `current` 는 **수정 중인 행**이다(생성이면 None). 오늘의 규칙으로 어제 저장된 값을
    다시 검사하면, 그 값을 그대로 실어 보내는 수정이 영원히 거절된다 — 관리자가 설명
    한 줄을 고치려면 그 일정이 하는 일을 바꿔야 하는 상태가 된다. 그래서 **값이 바뀌지
    않은 항목은 그대로 통과시키고, 새 값에만 오늘의 규칙을 건다.**
    """
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

    # 대상 어휘는 S11 이 좁혔다(D-267, `system`/`noop` 하나). 그 전에 만들어진 행은 이
    # 검사 때문에 저장 자체가 불가능했다 — 화면이 고를 수 있는 대상에 그 값이 없으므로
    # 「설명 오타 수정」이 「이 일정이 하는 일 바꾸기」가 됐다. 이미 저장된 값을 그대로
    # 다시 보내는 것만 통과시킨다. 새로 고를 수 있는 대상은 여전히 SYSTEM_TARGETS 뿐이다.
    if payload.target_ref not in SYSTEM_TARGETS and (
        current is None or payload.target_ref != current.target_ref
    ):
        raise ValidationAppError(
            "대상은 " + ", ".join(sorted(SYSTEM_TARGETS)) + " 중 하나여야 합니다."
        )

    # 재시도 횟수의 **범위**도 저장된 값을 봐준다. 스키마 층에는 `current` 가 없어서 거기
    # 두면 예외를 둘 수가 없는데, `_max_attempts` 는 범위 밖 정수를 예전부터 잘라 왔다
    # (999 → 10, 0 → 1). 그 행을 지금 거절하면 관리자가 「설명 오타 수정」을 하려고 그
    # 일정의 재시도 정책부터 바꿔야 한다 — 위 target_ref·아래 end_at 과 같은 예외다.
    attempts = payload.retry_policy.get("max_attempts")
    if (
        isinstance(attempts, int)
        and not isinstance(attempts, bool)
        and not MAX_ATTEMPTS_FLOOR <= attempts <= MAX_ATTEMPTS_CEILING
        and (current is None or attempts != _stored_max_attempts(current))
    ):
        raise ValidationAppError(
            f"재시도 횟수는 {MAX_ATTEMPTS_FLOOR}~{MAX_ATTEMPTS_CEILING} 사이 정수여야 합니다."
        )

    start_at = _parse_iso(payload.start_at, "start_at")
    end_at = _parse_iso(payload.end_at, "end_at")
    if start_at and end_at and end_at <= start_at:
        raise ValidationAppError("end_at은 start_at 이후여야 합니다.")
    # 유효 기간이 이미 끝난 일정은 만들 수 없다. 예전에는 201 로 저장되고 활성화까지 돼
    # 목록이 영영 오지 않을 '다음 실행'을 약속했다(once 형이 지난 run_at 을 거절하는 것과
    # 같은 규칙이다). 이미 그런 값을 들고 있는 행의 수정은 막지 않는다 — 그 행을 고치는
    # 유일한 길이 이 요청이기 때문이다.
    if (
        end_at is not None
        and end_at <= now
        and (current is None or end_at != current.end_at)
    ):
        raise ValidationAppError("종료 시각은 현재 시각 이후여야 합니다.")
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
    return {"items": [_view(r, names) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_schedule(
    request: Request,
    payload: ScheduleRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _require_global_schedule_write(request, db, principal, action="schedule.create")
    if payload.base_version is not None:
        # 만들 것에는 앞 판이 없다. 조용히 버리면 보낸 쪽은 잠금이 걸렸다고 믿는다.
        raise ValidationAppError("base_version은 일정을 수정할 때만 보낼 수 있습니다.")
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
    # 위 사전 검사와 이 INSERT 사이는 비어 있지 않다 — 같은 이름으로 두 요청이 동시에 오면
    # 뒤진 쪽의 flush 가 `schedules.name` 유니크를 때리고, 흡수하는 곳이 없어 500 이 됐다.
    # 직렬 경로가 이미 그 답(409)을 갖고 있으므로 경합에서도 같은 답을 준다
    # (`app/org/service.py::create_item`·`app/prompts/service.py` 와 같은 관용구).
    # 재시도 루프를 두지 않는 이유: 이 표의 유니크는 이름 하나뿐이라 같은 이름으로 다시
    # 넣어 봐야 결과가 같다 — 기다렸다 같은 409 를 주는 것은 늦게 주는 것일 뿐이다.
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
        raise ConflictError(f"이미 존재하는 Schedule 이름입니다: {payload.name}") from None
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
    principal: Principal = Depends(get_principal),
):
    from app.approvals.service import needs_approval

    row = _get_or_404(db, schedule_id)
    _require_global_schedule_write(
        request, db, principal, action="schedule.update", object_id=row.id
    )
    _ensure_not_changed(row, payload.base_version)
    now = request.app.state.clock.now()
    normalized = _validate_and_normalize(db, payload, now, current=row)
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
    # 이름 바꾸기도 생성과 같은 모양이다 — 위 중복 검사와 이 flush 사이에 다른 요청이
    # 같은 이름을 차지하면 유니크 위반이 500 으로 샌다. 같은 답(409)으로 흡수한다.
    try:
        with db.begin_nested():
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
        raise ConflictError(f"이미 존재하는 Schedule 이름입니다: {payload.name}") from None
    record_audit_from_request(
        request, db, action="schedule.update", object_type="schedule",
        object_id=row.id, before=before, after=_view(row),
    )
    return {"schedule": _view(row)}


@router.post("/{schedule_id}/enable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def enable_schedule(
    request: Request,
    schedule_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    row = _get_or_404(db, schedule_id)
    _require_global_schedule_write(
        request, db, principal, action="schedule.enable", object_id=row.id
    )
    now = request.app.state.clock.now()

    # 활성화가 성립하는지는 **승인 분기 앞에서** 본다. 뒤에 두면 그 검사를 지나는 사람이
    # system_admin 하나뿐이 된다 — 나머지 관리자는 전부 승인 경로로 빠지고, 승인 실행기는
    # 같은 검사를 갖고 있지 않아 결국 켜진다(`app/schedules/service.py::ensure_enablable`).
    next_run_at = ensure_enablable(row, now)

    # Spec §20: Schedule 활성화는 승인 대상 — system_admin만 즉시 적용.
    from app.approvals.service import approval_view, create_approval, needs_approval

    if needs_approval(request.state.user):
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

    row.next_run_at = next_run_at
    row.enabled = True
    db.flush()
    record_audit_from_request(
        request, db, action="schedule.enable", object_type="schedule",
        object_id=row.id, after={"next_run_at": row.next_run_at.isoformat()},
    )
    return {"schedule": _view(row)}


@router.post("/{schedule_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_schedule(
    request: Request,
    schedule_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    row = _get_or_404(db, schedule_id)
    _require_global_schedule_write(
        request, db, principal, action="schedule.disable", object_id=row.id
    )
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
    # 시작도 못 한 실행은 '마지막 실행'이 아니다. `create_run_and_enqueue` 는 재시도 정책을
    # 읽을 수 없으면 예외 대신 **실패 행**을 남기는데(그래야 실행 이력이 침묵하지 않는다),
    # 그 행까지 마지막 실행으로 찍으면 목록의 '마지막 실행' 칸이 "이 시각에 돌았다"고
    # 거짓말을 한다. 스케줄러 tick 이 세는 기준과 같은 기준으로 본다(scheduler.py 의
    # "시작도 못 한 실행을 세지 않는다"). run 이 None 인 것은 같은 초의 쌍둥이 요청이 그
    # 발생을 이미 가져갔다는 뜻이라 실패가 아니다 — 그쪽이 찍는다.
    started = run is None or run.status == RUN_QUEUED
    if run is not None and started:
        row.last_run_at = now
    record_audit_from_request(
        request, db, action="schedule.run_now", object_type="schedule",
        object_id=row.id, after={"run_id": run.id if run else None, "started": started},
    )
    # `ok` 는 "실행을 시작했는가"다. 실패 행을 돌려주면서 ok 라고 답하면 부르는 쪽에는
    # 시작하지 못했다는 사실을 알 방법이 없다 — 자세한 이유는 `run.status` 와
    # `run.error_message` 에 그대로 실려 있다.
    return {"ok": started, "run": _run_view(run) if run else None}


#: 실행 이력의 정렬 계약. 부모 스케줄 하나에 종속된 목록이라 축이 시간과 결과뿐이다.
_RUN_SORT = SortSpec(
    columns={
        "created_at": ScheduleRun.created_at,
        "scheduled_at": ScheduleRun.scheduled_at,
        "started_at": ScheduleRun.started_at,    # nullable
        "finished_at": ScheduleRun.finished_at,  # nullable
        "status": ScheduleRun.status,
        "retry_count": ScheduleRun.retry_count,
    },
    default="created_at",
    tiebreak=ScheduleRun.id,
    default_order="desc",
)


@router.get("/{schedule_id}/runs", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def run_history(
    schedule_id: str,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=16),
    sort: SortParams = Depends(),
):
    _get_or_404(db, schedule_id)
    stmt = select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id)
    if status:
        stmt = stmt.where(ScheduleRun.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(*order_by(_RUN_SORT, sort))
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
    # 잡에 실을 최대 시도 횟수를 **먼저** 읽는다. 아래 상태를 다 바꾼 뒤에 읽다 터지면
    # 그 예외가 500 이 되고 운영자는 무엇을 고쳐야 하는지 알 수 없다(사람이 누른 경로에는
    # 실행 이력의 실패 행이 아니라 지금 읽을 수 있는 답을 준다).
    try:
        attempts = _max_attempts(schedule)
    except InvalidRetryPolicy as exc:
        raise ValidationAppError(UNREADABLE_RETRY_POLICY_MESSAGE) from exc
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
        max_attempts=attempts,
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

    # 예전에는 `'"schedule_run_id": "…"'` 라는 **문자열 조각**을 payload JSON 본문에서
    # LIKE 로 찾았다. 그 방식은 직렬화 모양(콜론 뒤 공백·키 순서)에 의존한다 — `jsonb` 는
    # 그 모양을 PG 가 정하므로, 문자열로 찾는 코드는 언젠가 조용히 0건을 돌려준다.
    # `->>` 로 키를 직접 뽑으면 모양과 무관하게 정확하다.
    job = db.execute(
        select(Job).where(
            Job.job_type == "schedule_run",
            Job.status.in_([STATUS_QUEUED, STATUS_RUNNING]),
            Job.payload_json["schedule_run_id"].astext == run.id,
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
