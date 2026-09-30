"""메일 발송 상태 화면 (9-9 P4).

## 이 화면이 있는 이유

"설정이 없으면 없다고 한다" 는 요구는 사용자 화면만으로 끝나지 않는다. 운영자가
**무엇을 채워야 하는지** 알 수 있어야 하고, 채운 뒤 **실제로 되는지** 확인할 수 있어야
한다. 그래서 둘을 준다: 진단(`GET /status`)과 시험 발송(`POST /test`).

시험 발송은 자기 자신에게만 보낸다. 임의의 주소로 보낼 수 있게 하면 이 앱이 스팸
발송기가 된다(설정된 SMTP 계정의 평판까지 같이 태운다).

## 한 통을 보고, 다시 보내고, 취소한다 (계획 3.3)

`GET /deliveries/{id}` 는 한 통의 상태와 잡의 다음 시도 시각을 준다 - 시험 메일을 보낸 화면이 이것을 끝날
때까지 읽는다(예전에는 `queued` 응답을 실패로 읽어 성공한 시험 메일도 「보내지 못했습니다」였다).
다시 보내기와 취소, 설정 전에 쌓인 메일 보내기는 시험 발송과 같은 판정(전역 관리 범위)을 지난다 - 설치 한
벌의 SMTP 계정으로 나가는 동작이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import (
    audit_forbidden_write,
    get_db,
    get_principal,
    require_csrf,
    require_roles,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import Principal, require_global_management
from app.core.sort import SortParams
from app.mail.config import config_from_cache, config_from_db, mail_status
from app.mail.renderers import KIND_TEST
from app.notifications.mail import admin_catalog as notification_mail_catalog
from app.mail.service import (
    cancel_delivery,
    delivery_detail,
    delivery_view,
    list_deliveries,
    pending_unconfigured_count,
    queue_counts,
    queue_mail,
    recent_failures,
    resend_delivery,
    resend_unconfigured,
)

router = APIRouter(
    prefix="/api/admin/mail",
    tags=["admin-mail"],
    dependencies=[Depends(require_csrf)],
)


def current_mail_status(request: Request) -> dict:
    """화면과 진단이 같은 값을 보게 하는 한 줄. 판정은 app/mail/config.py 한 곳이다."""
    return mail_status(
        config_from_cache(getattr(request.app.state, "settings_cache", None)),
        getattr(request.app.state, "secret_provider", None),
    )


def _secrets(request: Request):
    return getattr(request.app.state, "secret_provider", None)


def current_health(request: Request, db: Session) -> dict:
    """저장된 건강 상태(`app/mail/health.py`). 메일 서버에 붙지 않는다."""
    from app.mail.health import health_state

    return health_state(db, config_from_db(db), _secrets(request))


@router.get("/status", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def status(request: Request, db: Session = Depends(get_db)):
    return {
        "mail": current_mail_status(request),
        # 「값이 있다」와 「동작한다」를 가른 상태(미설정 · 확인 전 · 정상 · 발송 실패)와 마지막 확인 시각.
        "health": current_health(request, db),
        "counts": queue_counts(db),
        "recent_failures": [delivery_view(r) for r in recent_failures(db)],
        # 설정 전에 쌓여 설정 뒤 다시 보낼 수 있는 메일(초대 등, 최근 7일). 화면이 그 단추 옆에 건수를 말한다.
        "pending_unconfigured_count": pending_unconfigured_count(db, now=request.app.state.clock.now()),
        # 알림을 메일로도 보내기(계획 3.4) - 관리자가 허용한 유형과 고를 수 있는 유형 전부, 오래된 메일의 기준.
        "notification_mail": notification_mail_catalog(db),
    }


@router.get("/deliveries", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def deliveries(
    status: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    since: str | None = Query(default=None, max_length=32),
    until: str | None = Query(default=None, max_length=32),
    page: PageParams = Depends(),
    sort: SortParams = Depends(),
    db: Session = Depends(get_db),
):
    """발송 기록 — 상태 · 종류 · 받는 사람과 제목 검색 · 기간(KST 달력일) · 정렬 · 페이지."""
    rows, total = list_deliveries(
        db, status=status, kind=kind, q=q, since=since, until=until, sort=sort,
        offset=page.offset, limit=page.page_size,
    )
    return {"items": [delivery_view(r) for r in rows], "total": total, "page": page.page, "page_size": page.page_size}


@router.get("/deliveries/{delivery_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def delivery(delivery_id: str, db: Session = Depends(get_db)):
    """한 통의 상세. 메일 기록은 조직 범위가 없는 설치 전체의 발송함이라 콘솔 읽기 역할이 본다."""
    return {"delivery": delivery_detail(db, delivery_id)}


def _require_mail_operator(request: Request, db: Session, principal: Principal, what: str, verb: str) -> None:
    """설치 한 벌의 SMTP 계정으로 나가는 동작은 전역 관리 범위만 한다(`send_test` 와 같은 판정)."""
    try:
        require_global_management(principal, what, verb=verb)
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise


@router.post("/deliveries/{delivery_id}/resend", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def resend(
    delivery_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """실패 · 설정 없음 · 취소로 끝난 메일을 다시 보낸다. 비밀번호 재설정과 시험 메일은 409 다."""
    _require_mail_operator(request, db, principal, "메일", "다시 보낼")
    row = resend_delivery(
        db, delivery_id, now=request.app.state.clock.now(),
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request, db, action="mail.resend", object_type="mail_delivery", object_id=row.id,
        after={"status": row.status, "kind": row.kind},
    )
    return {"delivery": delivery_view(row)}


@router.post("/deliveries/{delivery_id}/cancel", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def cancel(
    delivery_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """보내기를 기다리는 메일을 취소한다. 워커가 이미 보내는 중이면 409 다."""
    _require_mail_operator(request, db, principal, "메일", "취소할")
    row = cancel_delivery(db, delivery_id, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="mail.cancel", object_type="mail_delivery", object_id=row.id,
        after={"status": row.status, "kind": row.kind},
    )
    return {"delivery": delivery_view(row)}


@router.post("/resend-unconfigured", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def send_unconfigured(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """설정 전에 쌓인 메일(초대 등, 최근 7일)을 보낸다. **사람이 누를 때만** 돈다 - 오래된 메일을 예고 없이
    뿌리지 않는다."""
    _require_mail_operator(request, db, principal, "쌓인 메일", "보낼")
    count = resend_unconfigured(
        db, now=request.app.state.clock.now(),
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request, db, action="mail.requeue_unconfigured", object_type="mail_delivery", object_id=None,
        after={"count": count},
    )
    return {"queued": count}


@router.post("/test", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def send_test(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """자기 자신에게 시험 메일. 보내지 못하면 그 사실이 응답과 아웃박스에 남는다.

    범위 게이트를 여기 두는 이유: 이 시험은 **설치 한 벌의 SMTP 계정**으로 나간다. 그
    설정(`smtp` 키)을 바꿀 수 있는 사람과 그것을 실제로 써 보는 사람이 다르면, 부서 범위
    관리자가 자기가 못 고치는 계정으로 발송을 일으키고 그 계정의 평판과 발송 한도를
    쓰게 된다. 그래서 설정 표와 같은 판정을 쓴다(`app/settings/router.py::_guard_scope`).

    막은 시도는 역할 게이트와 같은 자리에 남긴다 — 범위 게이트는 핸들러 안에서 판정하므로
    `require_roles` 의 감사 기록을 지나지 않는다.
    """
    try:
        # 거절되는 것은 **발송**이다 — 「메일 발송 설정은 … 바꿀 수 있습니다」로 답하면
        # 건드린 적도 없는 설정 화면을 찾아가게 만든다. 화면의 단추 이름 그대로 말한다.
        require_global_management(principal, "시험 메일", verb="보낼")
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise
    me = request.state.user
    now = request.app.state.clock.now()
    row = queue_mail(
        db,
        kind=KIND_TEST,
        to_email=me.email,
        subject="[ClovirAssist] 메일 발송 시험",
        params={},
        now=now,
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request,
        db,
        action="mail.test_send",
        object_type="mail_delivery",
        object_id=row.id,
        after={"status": row.status, "kind": row.kind},
    )
    return {"delivery": delivery_view(row), "mail": current_mail_status(request)}


# ── 연결 확인 (계획 3.3) ──────────────────────────────────────────────────────

@router.post("/verify", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def start_verify(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """메일 서버 연결 확인을 큐에 넣고 **곧바로** 잡 id 를 돌려준다. 메일은 보내지 않는다."""
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE, VERIFY_TIMEOUT_SECONDS
    from app.jobs.repository import enqueue

    _require_mail_operator(request, db, principal, "메일 연결", "확인할")
    job = enqueue(
        db, job_type=MAIL_VERIFY_JOB_TYPE, payload={}, now=request.app.state.clock.now(),
        user_id=request.state.user.id, max_attempts=1,
    )
    record_audit_from_request(
        request, db, action="mail.verify", object_type="mail_settings", object_id=job.id, after={"queued": True},
    )
    return {"job_id": job.id, "status": job.status, "timeout_seconds": VERIFY_TIMEOUT_SECONDS}


@router.get("/verify/{job_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def verify_result(job_id: str, request: Request, db: Session = Depends(get_db)):
    """연결 확인 하나의 결과. 아직 안 끝났으면 **끝난 척하지 않는다**(`result` 가 null 이다)."""
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE
    from app.jobs.models import (
        STATUS_CANCELLED,
        STATUS_FAILED,
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,
        Job,
    )

    job = db.get(Job, job_id)
    if job is None or job.job_type != MAIL_VERIFY_JOB_TYPE:
        raise NotFoundError("연결 확인 기록을 찾을 수 없습니다.")
    result = None
    if job.status == STATUS_SUCCEEDED:
        result = {"ok": True, "message": "메일 서버에 연결했고, 로그인이 필요한 설정이면 로그인까지 확인했습니다."}
    elif job.status == STATUS_FAILED:
        result = {"ok": False, "message": (job.last_error or "").strip() or "메일 서버 연결을 확인하지 못했습니다."}
    elif job.status == STATUS_CANCELLED:
        result = {"ok": False, "message": "연결 확인이 취소됐습니다."}
    return {
        "job_id": job.id,
        "status": job.status,
        "pending": job.status in (STATUS_QUEUED, STATUS_RUNNING),
        "result": result,
        "health": current_health(request, db),
    }
