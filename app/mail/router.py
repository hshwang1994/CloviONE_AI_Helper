"""메일 발송 상태 화면 (9-9 P4).

## 이 화면이 있는 이유

"설정이 없으면 없다고 한다" 는 요구는 사용자 화면만으로 끝나지 않는다. 운영자가
**무엇을 채워야 하는지** 알 수 있어야 하고, 채운 뒤 **실제로 되는지** 확인할 수 있어야
한다. 그래서 둘을 준다: 진단(`GET /status`)과 시험 발송(`POST /test`).

시험 발송은 자기 자신에게만 보낸다. 임의의 주소로 보낼 수 있게 하면 이 앱이 스팸
발송기가 된다(설정된 SMTP 계정의 평판까지 같이 태운다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
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
from app.core.errors import ForbiddenError
from app.core.scope import Principal, require_global_management
from app.mail.config import config_from_cache, mail_status
from app.mail.renderers import KIND_TEST
from app.mail.service import (
    delivery_view,
    queue_counts,
    queue_mail,
    recent_failures,
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


@router.get("/status", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def status(request: Request, db: Session = Depends(get_db)):
    return {
        "mail": current_mail_status(request),
        "counts": queue_counts(db),
        "recent_failures": [delivery_view(r) for r in recent_failures(db)],
    }


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
