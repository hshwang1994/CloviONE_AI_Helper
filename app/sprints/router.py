"""주간 스프린트 회의 도우미 API (조회 전용).

담당자별 완료/생산성 집계는 팀 전원 공개(사용자 결정) — 역할 게이트 없이 인증만. 상태를 바꾸지 않으므로
CSRF 불필요. 배정/편집은 프런트가 기존 /api/tickets 계약(PATCH·claim)을 그대로 호출한다.
Notion 미설정/오류는 리포트·티켓 화면과 동일하게 configured/ok 플래그로 부드럽게 처리.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.sprints import service
from app.users.models import User

router = APIRouter(prefix="/api/sprint", tags=["sprint"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/summary")
def sprint_summary(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    start: str | None = Query(default=None, max_length=10),
    end: str | None = Query(default=None, max_length=10),
):
    """스프린트 요약(완료 현황 + 배분 대상 + 계획). start/end 미지정 시 이번 주(월~다음 주 월)."""
    now = request.app.state.clock.now()
    if not (start and _DATE_RE.match(start) and end and _DATE_RE.match(end)):
        start, end = service.default_sprint_window(now.date())
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        summary = service.build_sprint_summary(
            db, outbound, settings, start=start, end=end, today=now.date(),
            repo=request.app.state.repositories.tickets,
            viewer=user,   # 1순위 유출 #3 - 보는 사람의 팀으로 좁힌다
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "window": {"start": start, "end_exclusive": end}}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "window": {"start": start, "end_exclusive": end}}
    return {"configured": True, "ok": True, **summary}
