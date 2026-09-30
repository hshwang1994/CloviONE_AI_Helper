"""AI 사용 통계 API — `/api/admin/ai/usage` (계획 3.11, D-517).

호출 기록(`ai_usage_records`)을 기간과 조건으로 묶어 보인다. 예전 「사용 통계」는 스케줄이 이름을 참조하는가를
보여 주는 설정 개요였다 - 실제 호출은 어디에도 없었다.

## 누가 무엇을 보는가

관리 콘솔 읽기 역할(운영자, 관리자, 시스템 관리자, 감사자)이 본다. 범위는 관리 범위다: 부서 범위 관리자와 조직
범위 운영자는 자기 범위 사람의 호출만 보고, 사람이 아닌 호출(연결 확인)은 전역 관리자만 본다. 한도 목록이 누가
얼마나 쓰는지를 가리는 것과 같은 판정이다(`app/quotas/router.py`).

## 기간

날짜는 한국 시간으로 받는다(오늘을 포함하는 끝 날짜). 비우면 오늘을 끝으로 30일이다. 한 번에 366일까지 본다.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.ai import usage
from app.core.authz import CONSOLE_READ_ROLES
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.errors import ValidationAppError
from app.core.pagination import PageParams
from app.core.scope import Principal
from app.core.sort import SortParams

router = APIRouter(
    prefix="/api/admin/ai/usage",
    tags=["admin-ai-usage"],
    dependencies=[Depends(require_csrf), Depends(require_roles(*CONSOLE_READ_ROLES))],
)

DEFAULT_DAYS = 30


def _today(request: Request) -> date:
    from zoneinfo import ZoneInfo

    now = request.app.state.clock.now()
    return now.replace(tzinfo=ZoneInfo("UTC")).astimezone(usage.KST).date()


def _range(request: Request, start: date | None, end: date | None) -> tuple[date, date]:
    end = end or _today(request)
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if start > end:
        raise ValidationAppError("시작 날짜가 끝 날짜보다 늦습니다.")
    if (end - start).days + 1 > usage.MAX_RANGE_DAYS:
        raise ValidationAppError(f"한 번에 {usage.MAX_RANGE_DAYS}일까지 볼 수 있습니다.")
    return start, end


def _visible(db: Session, principal: Principal):
    if principal.management.is_global:
        return None
    from app.core.scope import visible_user_ids

    return set(visible_user_ids(db, principal.management) or set())


def _filters(action, user_id, provider, model, status, department_id) -> dict:
    return {"action": action, "user_id": user_id, "provider": provider, "model": model, "status": status,
            "department_id": department_id}


@router.get("/stats")
def usage_stats(
    request: Request,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    group_by: str = Query(default=usage.GROUP_ACTION, max_length=16),
    action: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    provider: str | None = Query(default=None, max_length=32),
    model: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=24),
    department_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    if group_by not in usage.GROUPS:
        raise ValidationAppError("지원하지 않는 묶음 기준입니다.")
    start, end = _range(request, start, end)
    lo, hi = usage.day_bounds(start, end)
    items = usage.stats(db, start=lo, end=hi, group_by=group_by, visible=_visible(db, principal),
                        **_filters(action, user_id, provider, model, status, department_id))
    totals = {key: sum(item[key] for item in items)
              for key in ("calls", "ok", "errors", "blocked", "input_tokens", "output_tokens")}
    totals["success_rate"] = usage.percent(totals["ok"], totals["ok"] + totals["errors"])
    return {"items": items, "total": len(items), "totals": totals, "group_by": group_by,
            "from": start.isoformat(), "to": end.isoformat()}


@router.get("/records")
def usage_records(
    request: Request,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    action: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    provider: str | None = Query(default=None, max_length=32),
    model: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=24),
    department_id: str | None = Query(default=None, max_length=36),
    page: PageParams = Depends(),
    sort: SortParams = Depends(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    """호출 기록 - 기간(한국 시간 날짜) · 조건 · 정렬(`usage.LIST_SORT`, 모르는 키는 기본 정렬) · 페이지."""
    start, end = _range(request, start, end)
    lo, hi = usage.day_bounds(start, end)
    items, total = usage.records(
        db, start=lo, end=hi, visible=_visible(db, principal), limit=page.page_size, offset=page.offset, sort=sort,
        **_filters(action, user_id, provider, model, status, department_id),
    )
    return {"items": items, "total": total, "page": page.page, "page_size": page.page_size,
            "from": start.isoformat(), "to": end.isoformat()}


@router.get("/catalog")
def usage_catalog() -> dict:
    """화면의 조건 목록 - 기능(액션)과 결과. 화면이 이름을 지어내지 않게 서버가 준다."""
    from app.ai.actions import ACTIONS

    return {
        "actions": [{"key": key, "label": action.label} for key, action in ACTIONS.items()],
        "statuses": [{"key": key, "label": label} for key, label in usage.STATUS_LABELS.items()],
        "groups": [
            {"key": usage.GROUP_ACTION, "label": "기능"}, {"key": usage.GROUP_USER, "label": "사용자"},
            {"key": usage.GROUP_DEPARTMENT, "label": "부서"}, {"key": usage.GROUP_PROVIDER, "label": "제공자"},
            {"key": usage.GROUP_MODEL, "label": "모델"}, {"key": usage.GROUP_STATUS, "label": "결과"},
            {"key": usage.GROUP_DAY, "label": "날짜"},
        ],
    }
