"""Approval workflow (spec §20).

Gate rule: actions on the mandatory list apply immediately when performed by
system_admin; any other authorized role creates a PENDING approval instead.
Approving replays the stored payload through the same service-layer write
path (executor registry) exactly once. Self-approval is banned unless the
self_approval_allowed feature flag is on.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.approvals.models import (
    APPROVAL_APPROVED,
    APPROVAL_CANCELLED,
    APPROVAL_EXPIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    DEFAULT_EXPIRY_HOURS,
    DEFAULT_SLA_HOURS,
    Approval,
)
from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.db import is_write_conflict, write_conflict_backoff
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.notifications.service import notify_approvers, notify_user
from app.users.models import ROLE_SYSTEM_ADMIN, User

# request_type → executor(db, approval, app_state). Registered by modules below.
APPROVAL_EXECUTORS: dict[str, Callable] = {}

# APPR-02: 알림 제목·메일 제목이 request_type 코드 상수를 그대로 노출했다("승인 요청:
# user.role_change") — 사람이 읽는 화면에 내부 식별자가 새는 것이다. 실제로 쓰이는 값은
# request_type= 리터럴을 등록하는 5개 호출부(users/router.py, integrations/router.py,
# runners/router.py, schedules/router.py, jobs/handlers/document_generate.py)뿐이다.
_REQUEST_TYPE_KO = {
    "user.role_change": "역할 변경",
    "integration.change_config": "연동 설정 변경",
    "runner.change_config": "러너 설정 변경",
    "schedule.enable": "스케줄 활성화",
    "document.publish": "문서 발행",
}


def _request_type_ko(request_type: str) -> str:
    # 모르는 값을 지어내지 않는다 — 매핑에 없으면(새 요청 유형이 아직 안 올라온 경우)
    # 원문 코드를 그대로 보여준다. 지금까지의 완전 노출보다 나빠지지 않는다.
    return _REQUEST_TYPE_KO.get(request_type, request_type)


def approval_view(
    row: Approval,
    now: datetime | None = None,
    names: dict[str, dict[str, str]] | None = None,
    can_decide: bool | None = None,
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

    def _path(uid: str | None) -> list:
        return names.get(uid, {}).get("dept_path", []) if uid else []

    return {
        "id": row.id,
        "request_type": row.request_type,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "requested_by": row.requested_by,
        "requester_name": _name(row.requested_by),
        "requester_email": _email(row.requested_by),
        # 요청자의 조직 경로(0060 §22). 승인은 "누구의 무엇을" 을 묻는 자리라 동명이인을
        # 이름만으로 구별하게 두면 안 된다 — 그 상태로 인사·권한 변경이 결재된다.
        "requester_path": _path(row.requested_by),
        "approver_id": row.approver_id,
        "approver_name": _name(row.approver_id),
        "approver_email": _email(row.approver_id),
        "status": status,
        "request_payload": json.loads(row.request_payload_json),
        "decision_comment": row.decision_comment,
        "requested_at": row.requested_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        # ── SLA (0033) ────────────────────────────────────────────────────────
        # `overdue` 판정도 여기 한 곳에서만 한다(status 와 같은 이유) — 목록과 상세가
        # 서로 다른 답을 내면 관리자가 어느 쪽을 믿을지 알 수 없다.
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "overdue": bool(
            now is not None
            and status == APPROVAL_PENDING
            and row.due_at is not None
            and row.due_at <= now
        ),
        "decided_on_behalf_of": row.decided_on_behalf_of,
        "decided_on_behalf_of_name": _name(row.decided_on_behalf_of),
        # 위임(delegation.py)까지 아는 결정 권한 판정 — 프런트가 role만 보고 버튼을 켜면
        # 위임받은 대리 결재자(operator 등 CONSOLE_WRITE_ROLES 아닌 역할)에게는 승인/거절
        # 버튼이 영원히 안 뜬다(FN-11). 판정은 여기(서버) 한 곳에서만 한다 — overdue와
        # 같은 이유(바로 위 주석): 목록과 상세가 서로 다른 답을 내면 안 된다.
        "can_decide": bool(can_decide),
    }


def resolve_names(db: Session, ids) -> dict[str, dict]:
    """user id 집합을 표시 이름/이메일/**조직 경로**로 일괄 해석한다 (감사 로그와 동일 패턴).

    조직 경로를 함께 싣는 이유(0060 §22): 승인 화면은 "누구의 무엇을 승인하는가" 를 묻는
    자리인데, 이름만 있으면 동명이인을 구별할 수 없다 — 그 상태로 인사·권한 변경을 결재하게
    두면 안 된다. 경로는 지금 조직 트리에서 계산한다(문자열을 저장하지 않는다).
    """
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    from app.core.org_tree import DeptTree

    tree = DeptTree.load(db)
    result: dict[str, dict] = {}
    for u in db.execute(
        select(User.id, User.display_name, User.email, User.department_id).where(
            User.id.in_(wanted)
        )
    ).all():
        result[u.id] = {
            "display_name": u.display_name,
            "email": u.email,
            "dept_path": [{"id": n.id, "name": n.name} for n in tree.path(u.department_id)],
        }
    return result


def needs_approval(actor: User) -> bool:
    """Mandatory-list actions: system_admin applies directly, others request."""
    return actor.role != ROLE_SYSTEM_ADMIN


# 동시에 여러 요청이 같은 (request_type, object_id, payload)로 경합할 때(실측: 8-way)
# 한 번의 실패-재조회로 안 끝날 수 있다 — `app/team_chat/service.py`의 `_SEQ_RETRIES`와
# 같은 관용. PA-RC-0008: 공용 기본값(`app/core/db.py::DEFAULT_WRITE_CONFLICT_RETRIES`
# = 10)보다 일부러 크다 — 이 경로는 관측된 경합이 더 잦다.
_CREATE_RETRIES = 12


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
    sla_hours: int = DEFAULT_SLA_HOURS,
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
    #
    # **`.scalars().first()`를 쓴다 (`.scalar_one_or_none()`이 아니다).** 이 대상에 대해
    # payload가 다른 pending 요청이 이미 둘 이상 있는 것은 위 설계상 정상 상태다(재요청
    # 허용). `scalar_one_or_none()`은 그런 정상 상태에서도, 또 아래 삽입이 경합으로
    # 중복 pending을 만들어 낸 뒤에도 `MultipleResultsFound`를 던져 이 대상에 대한 모든
    # 향후 요청을 500으로 막아 버린다 — 가장 최근 것 하나만 보고 판단하면 그런 실패
    # 모드 자체가 없어진다.
    existing = (
        db.execute(
            select(Approval)
            .where(
                Approval.request_type == request_type,
                Approval.object_id == object_id,
                Approval.status == APPROVAL_PENDING,
            )
            .order_by(Approval.requested_at.desc())
        )
        .scalars()
        .first()
    )
    if existing is not None and json.loads(existing.request_payload_json) == payload:
        return existing
    # 위 조회~삽입 사이에는 아직 커밋이 없다(`get_db`가 요청 끝에 한 번만 커밋한다) — 그
    # 동안 똑같은 요청이 다시 들어오면(더블클릭, 폼 재제출) 둘 다 "기존 pending 없음"을
    # 보고 각자 삽입을 시도할 수 있다. DB의 부분 유일 인덱스(migration 0052,
    # `ux_approvals_pending_dedup`)가 그 경합의 승자를 하나로 정해 주므로, 진 쪽은
    # `IntegrityError`를 받고 승자가 만든 행을 그대로 돌려준다 — `jobs/repository.py::enqueue`
    # 와 같은 패턴이다.
    #
    # 여러 요청이 한꺼번에 경합하면(실측: 8-way) 한 번의 "실패→승자 재조회"로 안 끝날 수
    # 있다 — 이 세션의 스냅샷이 낡아 재조회 시점에도 아직 아무도 커밋 안 한 것처럼 보이면
    # (`app/core/versioning.py::snapshot_config`와 같은 이유) 승자가 없다. 그러면 이
    # 세션도 다시 시도해 본다 — 재시도 자체가 스스로 승자가 될 수도, 이번엔 진짜 승자를
    # 볼 수도 있다. `games/service.py::_append_event`의 `_SEQ_RETRIES`와 같은 관용.
    for _attempt in range(_CREATE_RETRIES):
        row = Approval(
            request_type=request_type,
            object_type=object_type,
            object_id=object_id,
            requested_by=requested_by.id,
            status=APPROVAL_PENDING,
            request_payload_json=json.dumps(payload, ensure_ascii=False),
            requested_at=now,
            expires_at=now + timedelta(hours=expiry_hours),
            # 기한(SLA)은 만료보다 짧다 — 만료와 같으면 '기한 초과' 표시가 요청이 죽는
            # 순간에야 뜨고, 그때는 알려 봐야 아무 소용이 없다(app/approvals/models.py 주석).
            due_at=now + timedelta(hours=sla_hours),
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            break
        except (IntegrityError, OperationalError) as exc:
            if not is_write_conflict(exc):
                raise
            # 스냅샷을 새로 뜨는 이 commit 자체도 경합에서 같은 이유로 거부될 수 있다
            # (org/service.py::create_item과 같은 자리, D-75/PA-08과 같은 패턴) —
            # 처리 안 하면 예산이 남았는데도 raw OperationalError가 새 나간다.
            try:
                db.commit()
            except (IntegrityError, OperationalError) as commit_exc:
                if not is_write_conflict(commit_exc):
                    raise
                db.rollback()
            winner = (
                db.execute(
                    select(Approval)
                    .where(
                        Approval.request_type == request_type,
                        Approval.object_id == object_id,
                        Approval.status == APPROVAL_PENDING,
                        Approval.request_payload_json == row.request_payload_json,
                    )
                    .order_by(Approval.requested_at.desc())
                )
                .scalars()
                .first()
            )
            if winner is not None:
                return winner
            if _attempt == _CREATE_RETRIES - 1:
                # PA-RC-0008: 예산을 다 썼는데 승자도 못 찾으면(재조회 시점에도 아직
                # 아무도 안 커밋한 것처럼 보이는 낡은 스냅샷이 반복) 처리 안 된
                # IntegrityError/OperationalError를 그대로 올려 500을 내던 자리다 —
                # 사용자에게 뜻이 통하는 409로 바꾼다.
                raise ConflictError(
                    "다른 승인 요청과 계속 겹쳐 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."
                ) from None
            # 아직 아무도 안 이겼다(내 스냅샷이 낡아 그렇게 보일 뿐) — 다시 시도한다.
            time.sleep(write_conflict_backoff(_attempt))
    else:
        raise AssertionError("unreachable")  # pragma: no cover
    notify_approvers(
        db,
        type_="approval_requested",
        title=f"승인 요청: {_request_type_ko(request_type)}",
        body=f"{requested_by.display_name}님이 {object_type} 변경 승인을 요청했습니다.",
        related=("approval", row.id),
        now=now,
    )
    _mail_approvers(db, row, requested_by, now=now)
    return row


def _mail_approvers(db: Session, row: Approval, requested_by: User, *, now: datetime) -> None:
    """승인 요청을 메일로도 알린다 (9-9 P4).

    화면 안 알림만으로는 부족하다: 결재자가 포털을 안 열고 있으면 요청은 만료될 때까지
    아무도 모른다(`expire_pending` 이 조용히 죽인다). 승인 큐가 밀리는 이유 중 하나였다.

    **수신자 목록을 여기서 다시 정하지 않는다.** 바로 위 `notify_approvers` 와 똑같이
    `approver_user_ids` 를 쓴다 - 관리자만 골랐다가는 "결재하라고 권한을 준 피위임자가
    영원히 못 받는다" 는 예전 결함(X7)을 메일 쪽에서 그대로 되풀이한다.

    **메일 실패가 승인 생성을 막지 않는다** - 이 저장소의 기존 규칙이다(알림 실패와 같다).
    다만 조용히 사라지지도 않는다: 못 보낸 사실은 `mail_deliveries` 에 남는다.
    """
    try:
        from app.mail.renderers import KIND_APPROVAL_REQUESTED
        from app.mail.service import queue_mail_to_users
        from app.notifications.service import approver_user_ids

        queue_mail_to_users(
            db,
            approver_user_ids(db, now=now),
            kind=KIND_APPROVAL_REQUESTED,
            subject=f"[ClovirAssist] 승인 요청: {_request_type_ko(row.request_type)}",
            params={
                "request_type": row.request_type,
                "requested_by": requested_by.display_name,
                "object_type": row.object_type,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001 - 알림 경로가 본 작업을 죽이면 안 된다
        import logging

        logging.getLogger("app.approvals").exception(
            "승인 요청 메일을 큐에 넣지 못했다 (승인 자체는 생성됐다)"
        )


def get_approval_or_404(db: Session, approval_id: str) -> Approval:
    """범위를 **보지 않는** 조회. 라우터에서 직접 쓰지 말 것 — `get_scoped_approval_or_404`.

    실행기(executor)나 워커처럼 요청 주체가 없는 경로를 위해 남겨 둔다.
    """
    row = db.get(Approval, approval_id)
    if row is None:
        raise NotFoundError("승인 요청을 찾을 수 없습니다.")
    return row


# ── 범위 (§0-A 1순위) ────────────────────────────────────────────────────────
#
# 승인 큐를 목록에서만 좁히는 것은 **아무 의미가 없다** — approve/reject/cancel 은 승인 id 를
# 직접 받는다. 그리고 여기서 새는 것은 읽기 유출이 아니라 **권한 부여 실행**이다: 부서 범위
# 관리자가 남의 팀에서 올라온 `user.role_change` 요청을 결재해 admin 을 만들어 낼 수 있었다.
#
# 그래서 목록과 단건이 **같은 함수**를 지난다. 두 벌로 적으면 한쪽만 고쳐지고, 증상은
# "어떤 사람만 안 된다" 로 나타나 원인을 찾기가 어렵다.
#
# 시스템 소유 예외는 **없다**: 잡(`jobs.user_id`)과 달리 `approvals.requested_by` 는 NOT NULL
# 이라 소유자 없는 행 자체가 존재하지 않는다(목록 주석의 결론 그대로).


def scope_clause(visible: frozenset[str] | None):
    """요청자가 범위 안인가. 전역(``visible is None``)이면 ``None`` = 조건 없음.

    ``None`` 을 돌려주는 이유는 `app/core/scope.py::scope_filter` 와 같다 — 부르는 쪽이
    `if clause is None` 을 쓸 수밖에 없어 '범위를 고려했다'가 코드에 남는다.
    """
    if visible is None:
        return None
    return Approval.requested_by.in_(tuple(sorted(visible)))


def apply_scope(stmt: Select, visible: frozenset[str] | None) -> Select:
    clause = scope_clause(visible)
    return stmt if clause is None else stmt.where(clause)


def get_scoped_approval_or_404(
    db: Session, approval_id: str, visible: frozenset[str] | None
) -> Approval:
    """단건 조회 — 범위 밖은 **없는 것과 똑같이 404** 다.

    403 은 "그 승인은 존재한다"를 알려 준다. 승인 id 를 찍어 보며 403/404 를 세면 다른 팀의
    승인 큐가 있다는 사실과 그 규모를 열거할 수 있다. 문구까지 `get_approval_or_404` 와
    동일하게 맞춰 둔다 — 응답으로 두 경우를 구별할 수 없어야 한다.

    조건을 **조회 자체에** 붙인다(`jobs/repository.py::get_in_scope` 와 같은 이유): 먼저
    꺼내 놓고 나중에 판정하면 판정을 빠뜨린 새 경로가 조용히 열린다.
    """
    row = db.execute(
        apply_scope(select(Approval).where(Approval.id == approval_id), visible)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("승인 요청을 찾을 수 없습니다.")
    return row


def _ensure_decidable(row: Approval, now: datetime) -> None:
    if row.status != APPROVAL_PENDING:
        raise ConflictError(f"이미 처리된 승인 요청입니다 (status={row.status}).")
    if row.expires_at is not None and row.expires_at <= now:
        # 여기서 row.status를 EXPIRED로 대입하지 않는다 — 대입해도 절대 저장되지 않는다.
        # 이 함수는 `decide()`/`cancel()`을 거쳐 라우터에서 곧장 호출되고, 아래 줄에서 던지는
        # ConflictError는 `app/core/deps.py::get_db`의 `except Exception: db.rollback(); raise`
        # 를 그대로 타고 나가 요청 트랜잭션 전체를 롤백한다 — flush조차 되기 전에 대입이
        # 사라진다. 실제 만료 영속화는 별도 백그라운드 스윕(`expire_pending`)만 한다 — 그
        # 쪽은 `_fail_pending_document_publish`도 같이 호출해 연결된 문서 발행까지 정리한다.
        # (표시용 만료 판정은 `approval_view`가 이 컬럼과 무관하게 조회 시점에 한다.)
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
    on_behalf_of: str | None = None,
) -> Approval:
    _ensure_decidable(row, now)
    if row.requested_by == approver.id and not self_approval_allowed:
        raise ForbiddenError("자기 승인을 허용하지 않습니다.")

    row.approver_id = approver.id
    # 위임으로 결재했다면 누구의 권한을 빌린 것인지 남긴다(0033). 이게 없으면 나중에
    # "운영자가 왜 승인할 수 있었지?"에 답할 방법이 로그 어디에도 없다.
    row.decided_on_behalf_of = on_behalf_of
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
        title=f"승인 {'완료' if approve else '거절'}: {_request_type_ko(row.request_type)}",
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
    # 본인이 취소했으면 이미 알고 있다 — 자기 자신에게 알림을 보내지 않는다. 통보가 필요한
    # 경우는 admin/system_admin이 남의 대기 요청을 대신 끝냈을 때뿐이다(위 검사가 허용하는
    # 두 번째 경로). 그때 요청자는 벨도 /notifications도 신호가 없었다 — decide()·
    # expire_pending() 형제 함수는 이미 notify_user를 부르는데 이 함수만 빠져 있었다.
    if actor.id != row.requested_by:
        notify_user(
            db,
            row.requested_by,
            type_="approval_cancelled",
            title=f"승인 요청 취소됨: {_request_type_ko(row.request_type)}",
            related=("approval", row.id),
            now=now,
        )
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
    from app.runners.service import apply_runner_config, get_runner_or_404, runner_snapshot

    payload = json.loads(approval.request_payload_json)
    runner = get_runner_or_404(db, approval.object_id)
    # 승인은 요청 시점에 승인자가 본 runner 상태에 대한 것이다. 대기 중 직접 수정이나
    # 다른 승인이 먼저 적용돼 그 상태가 바뀌었다면, 이 승인을 그대로 적용하는 것은
    # 승인자가 검토한 적 없는 변경(옛 설정으로의 조용한 되돌림)을 만든다 — STALE로
    # 거절한다. (스냅샷이 없는 예전 승인도 대조가 불가능하므로 같은 취급 — fail-closed,
    # `_execute_schedule_enable`과 같은 패턴.)
    before = payload.get("before")
    if before is None or runner_snapshot(runner) != before:
        raise ConflictError(
            "요청 이후 Runner 설정이 변경되어 이 승인은 적용할 수 없습니다 (stale). "
            "변경된 설정으로 다시 요청하세요."
        )
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
    from app.integrations.service import (
        apply_integration_config,
        get_integration_or_404,
        integration_snapshot,
    )

    payload = json.loads(approval.request_payload_json)
    integration = get_integration_or_404(db, approval.object_id)
    # 승인은 요청 시점에 승인자가 본 integration 상태에 대한 것이다. 대기 중 직접
    # 수정이나 다른 승인이 먼저 적용돼 그 상태가 바뀌었다면, 이 승인을 그대로 적용하는
    # 것은 승인자가 검토한 적 없는 변경(옛 설정으로의 조용한 되돌림)을 만든다 — STALE로
    # 거절한다. (스냅샷이 없는 예전 승인도 대조가 불가능하므로 같은 취급 — fail-closed,
    # `_execute_schedule_enable`과 같은 패턴.)
    before = payload.get("before")
    if before is None or integration_snapshot(integration) != before:
        raise ConflictError(
            "요청 이후 Integration 설정이 변경되어 이 승인은 적용할 수 없습니다 (stale). "
            "변경된 설정으로 다시 요청하세요."
        )
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
