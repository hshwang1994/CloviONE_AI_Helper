"""개발자 월간 리포트 관리자 API.

조회 전용(GET)이라 CSRF 토큰이 필요 없다(상태를 바꾸지 않음). 담당자별 생산성이 담긴
민감한 집계라 operator 는 제외하고 admin/system_admin/auditor 만 본다(감사 로그 조회 권한과 같은 선).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.reports.service import build_dev_monthly_report

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"])

READ_ROLES = ("admin", "system_admin", "auditor")
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/dev-monthly", dependencies=[Depends(require_roles(*READ_ROLES))])
def dev_monthly(
    request: Request,
    period: str | None = Query(default=None, max_length=7),
    db: Session = Depends(get_db),
):
    """마감일이 지정한 달인 티켓을 담당자별로 집계해 돌려준다.

    period 는 'YYYY-MM'. 생략하면 오늘 기준 이번 달. Notion 토큰이 아직 없으면
    오류 대신 configured=false 를 돌려줘, 화면이 '연동 필요' 안내를 그리게 한다.
    """
    now = request.app.state.clock.now()
    if period is None:
        period = f"{now.year:04d}-{now.month:02d}"
    if not _PERIOD_RE.match(period):
        return {"configured": True, "ok": False, "error": "기간 형식이 올바르지 않습니다(YYYY-MM)."}

    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        report = build_dev_monthly_report(
            db, outbound, settings, period=period, today=now.date(),
            repo=request.app.state.repositories.tickets,
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "period": period}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "period": period}

    report["configured"] = True
    report["ok"] = True
    report["generated_at"] = now.isoformat()
    return report
