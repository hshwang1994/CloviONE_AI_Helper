"""개발자 월간 리포트 관리자 API.

조회 전용(GET)이라 CSRF 토큰이 필요 없다(상태를 바꾸지 않음). 담당자별 생산성이 담긴
민감한 집계라 operator 는 제외하고 admin/system_admin/auditor 만 본다(감사 로그 조회 권한과 같은 선).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.authz import SENSITIVE_READ_ROLES
from app.core.deps import get_db, get_principal, require_roles
from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.core.scope import Principal, visible_user_ids
from app.home.service import local_today
from app.reports.service import build_dev_monthly_report

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"])

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/dev-monthly", dependencies=[Depends(require_roles(*SENSITIVE_READ_ROLES))])
def dev_monthly(
    request: Request,
    period: str | None = Query(default=None, max_length=7),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """마감일이 지정한 달인 티켓을 담당자별로 집계해 돌려준다.

    period 는 'YYYY-MM'. 생략하면 오늘 기준 이번 달. Notion 토큰이 아직 없으면
    오류 대신 configured=false 를 돌려줘, 화면이 '연동 필요' 안내를 그리게 한다.

    관리 범위(0024)가 걸린 두 곳 중 하나다(다른 하나는 `/api/admin/users`). 전역 관리자면
    `visible_user_ids` 가 None 이라 예전 응답과 바이트 단위로 같다.
    """
    now = request.app.state.clock.now()
    settings = request.app.state.settings
    # UA-08(M4): `now`는 UTC다. 매월 1일 KST 00:00~09:00엔 `now.month`가 아직 지난달이라
    # period 기본값이 지난달 리포트가 되고, `today=now.date()`도 하루 밀려 그 9시간 동안
    # "어제 마감"이 overdue로 안 세어진다. `DevReport.jsx`는 브라우저 로컬(=KST)로 기본
    # period를 계산해 화면 기본값과 API 기본값이 이미 어긋나 있었다.
    today = local_today(settings, now)
    if period is None:
        period = f"{today.year:04d}-{today.month:02d}"
    if not _PERIOD_RE.match(period):
        return {"configured": True, "ok": False, "error": "기간 형식이 올바르지 않습니다(YYYY-MM)."}

    outbound = request.app.state.outbound_client
    try:
        report = build_dev_monthly_report(
            db, outbound, settings, period=period, today=today,
            repo=request.app.state.repositories.tickets,
            visible_user_ids=visible_user_ids(db, principal.scope),
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "period": period}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "period": period}

    report["configured"] = True
    report["ok"] = True
    report["generated_at"] = now.isoformat()
    return report
