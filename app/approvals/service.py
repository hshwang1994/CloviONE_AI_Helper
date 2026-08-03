"""Approval workflow (spec §20).

Gate rule: actions on the mandatory list apply immediately when performed by
system_admin; any other authorized role creates a PENDING approval instead.
Approving replays the stored payload through the same service-layer write
path (executor registry) exactly once. Self-approval is banned unless the
self_approval_allowed feature flag is on.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.models import (
    APPROVAL_APPROVED,
    APPROVAL_CANCELLED,
    APPROVAL_EXPIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    DEFAULT_EXPIRY_HOURS,
    Approval,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.notifications.service import notify_admins, notify_user
from app.core.authz import CONSOLE_WRITE_ROLES
from app.users.models import ROLE_SYSTEM_ADMIN, User

# request_type → executor(db, approval, app_state). Registered by modules below.
APPROVAL_EXECUTORS: dict[str, Callable] = {}


def approval_view(
    row: Approval,
    now: datetime | None = None,
    names: dict[str, dict[str, str]] | None = None,
) -> dict:
    # A pending row past its expiry displays as 'expired' immediately, even before
    # the background sweep persists the change (else it looks decidable but isn't).
    status = row.status
    if (
        now is not None
        and status == APPROVAL_PENDING
        and row.expires_at is not None
        and row.expires_at <= now
    ):
        status = APPROVAL_EXPIRED
    # 요청자/결정자는 UUID만 두면 승인 큐에서 '누가 무엇을 요청했나'를 알 수 없다 —
    # 감사 로그가 actor_name을 붙이는 것과 같은 방식으로 표시 이름/이메일을 함께 준다.
    # names 미제공 시(호출부가 해석하지 않으면) 이름은 None으로 두고 id만 노출한다.
    names = names or {}

    def _name(uid: str | None) -> str | None:
        # 예약 발행 등 시스템이 자동으로 만든 요청은 requested_by="system"으로
        # 기록된다(실제 User가 아니므로 names에 없어 해석이 안 됨) — 원시 영문
        # 리터럴이 한글 화면에 그대로 새지 않도록 여기서 라벨을 붙인다.
        if uid == "system":
            return "시스템(자동)"
        return names.get(uid, {}).get("display_name") if uid else None

    def _email(uid: str | None) -> str | None:
        return names.get(uid, {}).get("email") if uid else None

    return {
        "id": row.id,
        "request_type": row.request_type,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "requested_by": row.requested_by,
        "requester_name": _name(row.requested_by),
        "requester_email": _email(row.requested_by),
        "approver_id": row.approver_id,
        "approver_name": _name(row.approver_id),
        "approver_email": _email(row.approver_id),
        "status": status,
        "request_payload": json.loads(row.request_payload_json),
        "decision_comment": row.decision_comment,
        "requested_at": row.requested_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def resolve_names(db: Session, ids) -> dict[str, dict[str, str]]:
    """user id 집합을 표시 이름/이메일로 일괄 해석한다 (감사 로그와 동일 패턴)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    result: dict[str, dict[str, str]] = {}
    for u in db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(wanted))
    ).all():
        result[u.id] = {"display_name": u.display_name, "email": u.email}
    return result


def needs_approval(actor: User) -> bool:
    """Mandatory-list actions: system_admin applies directly, others request."""
    return actor.role != ROLE_SYSTEM_ADMIN


def create_approval(
    db: Session,
    *,
    request_type: str,
    object_type: str,
    object_id: str,
    requested_by: User,
    payload: dict,
    now: datetime,
    expiry_hours: int = DEFAULT_EXPIRY_HOURS,
) -> Approval:
    if request_type not in APPROVAL_EXECUTORS:
        raise ConflictError(f"승인 실행기가 등록되지 않은 요청 유형입니다: {request_type}")
    # 같은 대상·같은 내용의 대기 중 요청이 이미 있으면 새로 만들지 않고 그 요청을
    # 돌려준다. 예: 비활성 스케줄의 '활성화' 버튼은 승인이 대기 중이어도 계속 눌릴 수
    # 있는 상태로 남는다(화면이 pending 상태를 표시하지 않는다) — 연타마다 중복 pending
    # 승인이 쌓이면 승인 큐가 같은 변경을 여러 번 검토하게 만들고, 하나만 승인돼도
    # 나머지는 STALE로 남아 혼란을 더한다. payload까지 같을 때만 재사용한다 — 같은
    # 대상에 대해 내용이 다른 새 요청(예: 다른 역할로의 재요청)까지 예전 pending 건을
    # 돌려주면 호출자에게 자신이 방금 요청한 것과 다른 내용을 승인 대상으로 보여주게 된다.
    existing = db.execute(
        select(Approval).where(
            Approval.request_type == request_type,
            Approval.object_id == object_id,
            Approval.status == APPROVAL_PENDING,
        )
    ).scalar_one_or_none()
    if existing is not None and json.loads(existing.request_payload_json) == payload:
        return existing
    row = Approval(
        request_type=request_type,
        object_type=object_type,
        object_id=object_id,
        requested_by=requested_by.id,
        status=APPROVAL_PENDING,
        request_payload_json=json.dumps(payload, ensure_ascii=False),
        requested_at=now,
        expires_at=now + timedelta(hours=expiry_hours),
    )
    db.add(row)
    db.flush()
    notify_admins(
        db,
        type_="approval_requested",
        title=f"승인 요청: {request_type}",
        body=f"{requested_by.display_name}님이 {object_type} 변경 승인을 요청했습니다.",
        related=("approval", row.id),
        now=now,
    )
    return row


def get_approval_or_404(db: Session, approval_id: str) -> Approval:
    row = db.get(Approval, approval_id)
    if row is None:
        raise NotFoundError("승인 요청을 찾을 수 없습니다.")
    return row


def _ensure_decidable(row: Approval, now: datetime) -> None:
    if row.status != APPROVAL_PENDING:
        raise ConflictError(f"이미 처리된 승인 요청입니다 (status={row.status}).")
    if row.expires_at is not None and row.expires_at <= now:
        row.status = APPROVAL_EXPIRED
        raise ConflictError("만료된 승인 요청입니다.")


def _fail_pending_document_publish(db: Session, row: Approval, *, message: str) -> None:
    """document.publish 승인이 거절/만료되면 연결된 DocumentGeneration도 실패로 표시한다.

    그러지 않으면 DocumentGeneration.status가 'awaiting_approval'에 영원히 머무른다 —
    문서 화면의 유일한 복구 액션인 '재시도'는 이 상태를 절대 만나지 못하고, 관리자는
    거절/만료된 발행 요청을 다시 발견할 방법이 없다.
    """
    if row.request_type != "document.publish":
        return
    from app.documents.models import (
        STATUS_AWAITING_APPROVAL,
        STATUS_FAILED,
        DocumentGeneration,
    )

    gen = db.get(DocumentGeneration, row.object_id)
    if gen is None or gen.status != STATUS_AWAITING_APPROVAL:
        return
    gen.status = STATUS_FAILED
    gen.error_message = message


def decide(
    db: Session,
    row: Approval,
    approver: User,
    *,
    approve: bool,
    comment: str | None,
    now: datetime,
    self_approval_allowed: bool,
    app_state,
) -> Approval:
    _ensure_decidable(row, now)
    if row.requested_by == approver.id and not self_approval_allowed:
        raise ForbiddenError("자기 승인을 허용하지 않습니다.")

    row.approver_id = approver.id
    row.decision_comment = comment
    row.decided_at = now

    if approve:
        executor = APPROVAL_EXECUTORS.get(row.request_type)
        if executor is None:
            raise ConflictError(f"승인 실행기가 없습니다: {row.request_type}")
        executor(db, row, app_state)  # 예외 시 트랜잭션 롤백 → 상태 변화 없음
        row.status = APPROVAL_APPROVED
    else:
        row.status = APPROVAL_REJECTED
        _fail_pending_document_publish(db, row, message="발행 승인이 거절되었습니다.")

    notify_user(
        db,
        row.requested_by,
        type_="approval_decided",
        title=f"승인 {'완료' if approve else '거절'}: {row.request_type}",
        body=comment,
        related=("approval", row.id),
        now=now,
    )
    db.flush()
    return row


def cancel(db: Session, row: Approval, actor: User, *, now: datetime) -> Approval:
    _ensure_decidable(row, now)
    if row.requested_by != actor.id and actor.role not in CONSOLE_WRITE_ROLES:
        raise ForbiddenError("본인의 승인 요청만 취소할 수 있습니다.")
    row.status = APPROVAL_CANCELLED
    row.decided_at = now
    db.flush()
    return row


def expire_pending(db: Session, *, now: datetime) -> int:
    rows = (
        db.execute(
            select(Approval).where(
                Approval.status == APPROVAL_PENDING,
                Approval.expires_at.is_not(None),
                Approval.expires_at <= now,
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = APPROVAL_EXPIRED
        row.decided_at = now
        _fail_pending_document_publish(db, row, message="발행 승인이 만료되었습니다.")
        notify_user(
            db,
            row.requested_by,
            type_="approval_expired",
            title=f"승인 요청 만료: {row.request_type}",
            related=("approval", row.id),
            now=now,
        )
    db.flush()
    return len(rows)


# --- Executors (replay stored payloads through normal service paths) --------


def _execute_schedule_enable(db: Session, approval: Approval, app_state) -> None:
    from app.core.audit import record_audit
    from app.schedules import cron
    from app.schedules.models import TYPE_ONCE, Schedule
    from app.schedules.service import definition_snapshot

    schedule = db.get(Schedule, approval.object_id)
    if schedule is None:
        raise ConflictError("대상 Schedule이 더 이상 존재하지 않습니다.")
    # 승인은 요청 시점의 정의에 대한 것이다. 대기 중 PUT으로 정의가 바뀌었다면
    # 승인자가 본 적 없는 내용을 활성화하게 되므로 이 승인은 STALE — 거절한다.
    # (스냅샷이 없는 예전 승인도 대조가 불가능하므로 같은 취급 — fail-closed.)
    approved = json.loads(approval.request_payload_json).get("definition")
    if approved != definition_snapshot(schedule):
        raise ConflictError(
            "요청 이후 Schedule 정의가 변경되어 이 승인은 적용할 수 없습니다 (stale). "
            "변경된 정의로 다시 요청하세요."
        )
    now = app_state.clock.now()
    if schedule.schedule_type == TYPE_ONCE:
        if schedule.next_run_at is None or schedule.next_run_at <= now:
            raise ConflictError("once 스케줄의 실행 시각이 이미 지났습니다.")
    else:
        anchor = max(now, schedule.start_at) if schedule.start_at else now
        schedule.next_run_at = cron.next_after(
            schedule.cron_expression, schedule.timezone, anchor
        )
    schedule.enabled = True
    db.flush()
    # _execute_user_role_change의 고정과 같은 이유: 대상 자신의 object_type으로도 남겨야
    # 감사 화면에서 '이 schedule에 무슨 일이 있었나'를 승인(approval) 레코드까지 따라가지
    # 않고도 바로 볼 수 있다.
    record_audit(
        db, actor_id=approval.approver_id, action="schedule.enable",
        object_type="schedule", object_id=schedule.id, after={"enabled": True},
    )


def _execute_runner_config(db: Session, approval: Approval, app_state) -> None:
    from app.core.audit import record_audit
    from app.runners.schemas import RunnerConfig
    from app.runners.service import apply_runner_config, get_runner_or_404

    payload = json.loads(approval.request_payload_json)
    runner = get_runner_or_404(db, approval.object_id)
    config = RunnerConfig.model_validate(payload["config"])
    apply_runner_config(
        db, runner, config,
        allowlists=app_state.allowlists,
        updated_by=approval.requested_by,
    )
    record_audit(
        db, actor_id=approval.approver_id, action="runner.change_config",
        object_type="runner", object_id=runner.id, after={"config": payload.get("config")},
    )


def _execute_user_role_change(db: Session, approval: Approval, app_state) -> None:
    from app.core.audit import record_audit
    from app.users.models import ROLE_SYSTEM_ADMIN
    from app.users.service import get_user_or_404, update_user

    payload = json.loads(approval.request_payload_json)
    user = get_user_or_404(db, approval.object_id)
    # No valid role_change approval ever targets a system_admin (system_admin
    # changes are blocked before an approval is created). If the target became a
    # system_admin between request and approval, this approval is STALE — refuse
    # it rather than silently demoting a system_admin (TOCTOU guard).
    if user.role == ROLE_SYSTEM_ADMIN or payload.get("role") == ROLE_SYSTEM_ADMIN:
        raise ConflictError(
            "대상 계정 상태가 변경되어 이 승인은 더 이상 적용할 수 없습니다 (stale)."
        )
    previous_role = user.role
    update_user(
        db, user,
        session_service=app_state.session_service,
        actor_role="system_admin",
        role=payload["role"],
    )
    # app/health/service.py:CRITICAL_ACTIONS watches for the exact action
    # string "user.role_change" on object_type="user" — before this call the
    # only rows ever written for a role change were "user.role_change_requested"
    # (on request) and "approval.approve" (object_type="approval", not "user"),
    # so the dashboard's critical-action alert could never fire for an actual
    # role escalation. Record it here, at the point the change is applied,
    # keyed to the target user so the dashboard/audit screen can find it.
    record_audit(
        db,
        actor_id=approval.approver_id,
        action="user.role_change",
        object_type="user",
        object_id=user.id,
        before={"role": previous_role},
        after={"role": user.role},
    )


def _execute_document_publish(db: Session, approval: Approval, app_state) -> None:
    """승인된 문서를 발행한다 — 승인자가 검토한 그 미리보기를 그대로 발행한다 (spec §19.3).

    mode를 auto_publish로 바꿔 재생성을 큐에 넣지 않는다. 그렇게 하면 발행되는 것은
    '승인자가 본 문서'가 아니라 '발행 시점에 새로 만든 문서'가 된다.
    """
    from app.core.audit import record_audit
    from app.documents.models import STATUS_AWAITING_APPROVAL, DocumentGeneration
    from app.documents.service import enqueue_approved_publish

    gen = db.get(DocumentGeneration, approval.object_id)
    if gen is None:
        raise ConflictError("대상 문서 생성 레코드가 없습니다.")
    if gen.status != STATUS_AWAITING_APPROVAL:
        raise ConflictError(f"발행 승인 대상이 아닙니다 (status={gen.status}).")
    # 승인은 '승인자가 본 산출물'에 대한 것이다. 그 내용이 없으면 무엇을 승인한 것인지
    # 확정할 수 없으므로 발행하지 않는다 (fail-closed).
    if not gen.preview_json:
        raise ConflictError("승인 대상 미리보기 내용이 없어 발행할 수 없습니다.")
    enqueue_approved_publish(db, gen, now=app_state.clock.now())
    record_audit(
        db, actor_id=approval.approver_id, action="document.publish",
        object_type="document_generation", object_id=gen.id, after={"status": gen.status},
    )


def _execute_integration_config(db: Session, approval: Approval, app_state) -> None:
    from app.core.audit import record_audit
    from app.integrations.schemas import IntegrationConfig
    from app.integrations.service import apply_integration_config, get_integration_or_404

    payload = json.loads(approval.request_payload_json)
    integration = get_integration_or_404(db, approval.object_id)
    config = IntegrationConfig.model_validate(payload["config"])
    apply_integration_config(
        db, integration, config,
        allowlists=app_state.allowlists,
        updated_by=approval.requested_by,
    )
    record_audit(
        db, actor_id=approval.approver_id, action="integration.change_config",
        object_type="integration", object_id=integration.id,
        after={"config": payload.get("config")},
    )


APPROVAL_EXECUTORS["schedule.enable"] = _execute_schedule_enable
APPROVAL_EXECUTORS["runner.change_config"] = _execute_runner_config
APPROVAL_EXECUTORS["integration.change_config"] = _execute_integration_config
APPROVAL_EXECUTORS["user.role_change"] = _execute_user_role_change
APPROVAL_EXECUTORS["document.publish"] = _execute_document_publish
