"""AI 사용 통계 API — `/api/admin/ai/usage` (계획 3.11, D-517).

호출 기록(`ai_usage_records`)을 기간과 조건으로 묶어 보인다. 예전 「사용 통계」는 스케줄이 이름을 참조하는가를
보여 주는 설정 개요였다 - 실제 호출은 어디에도 없었다.

## 누가 무엇을 보는가

관리 콘솔 읽기 역할(운영자, 관리자, 시스템 관리자, 감사자)이 본다. 범위는 관리 범위다: 부서 범위 관리자와 조직
범위 운영자는 자기 범위 사람의 호출만 보고, 사람이 아닌 호출(연결 확인)은 전역 관리자만 본다. 한도 목록이 누가
얼마나 쓰는지를 가리는 것과 같은 판정이다(`app/quotas/router.py`).

## 기간 (D-543)

기간은 프리셋(`period` = 오늘 · 7일 · 30일 · 이번 달)이거나 직접 고른 두 날짜(`custom` + `from` · `to`)다. 날짜는 한국 시간이고
서버 시계로 센다. 비우면 30일이다 - 그리고 응답이 그 기간을 문장으로 말한다(`range_label`). 예전에는 날짜 칸이 비어 있는데
서버가 조용히 30일을 썼다. 한 번에 366일까지 본다.

## 검색 (D-543)

`q` 는 보이는 범위 안 사람의 이름 · 이메일이나 기능 이름에 맞는 기록이다(`usage.search_clause`). 예전 화면은 받은 한 쪽의
행 JSON 을 브라우저에서 훑었다.
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
PERIOD_TODAY, PERIOD_7D, PERIOD_30D, PERIOD_MONTH, PERIOD_CUSTOM = "today", "7d", "30d", "month", "custom"
PERIODS = (
    (PERIOD_TODAY, "오늘"), (PERIOD_7D, "최근 7일"), (PERIOD_30D, "최근 30일"), (PERIOD_MONTH, "이번 달"), (PERIOD_CUSTOM, "직접 선택"),
)
#: 화면의 보기 기준(조건이 아니다). API 는 나머지 묶음도 그대로 받는다(호환).
VIEWS = ((usage.GROUP_ACTION, "기능"), (usage.GROUP_USER, "사용자"), (usage.GROUP_DEPARTMENT, "부서"),
         (usage.GROUP_MODEL, "모델"))


def _today(request: Request) -> date:
    from zoneinfo import ZoneInfo

    now = request.app.state.clock.now()
    return now.replace(tzinfo=ZoneInfo("UTC")).astimezone(usage.KST).date()


def _range(request: Request, start: date | None, end: date | None) -> tuple[date, date]:
    end = end or _today(request)
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if start > end:
        raise ValidationAppError("시작일이 종료일보다 늦습니다. 기간을 다시 선택하세요.")
    if (end - start).days + 1 > usage.MAX_RANGE_DAYS:
        raise ValidationAppError(f"한 번에 {usage.MAX_RANGE_DAYS}일까지 볼 수 있습니다.")
    return start, end


def _period(request: Request, period: str | None, start: date | None, end: date | None) -> tuple[str, date, date]:
    """기간 프리셋 → (프리셋, 시작, 끝). 날짜만 오면 직접 선택이다(옛 주소 · 저장된 뷰가 from/to 를 그대로 든다)."""
    if period is None:
        period = PERIOD_CUSTOM if (start or end) else PERIOD_30D
    today = _today(request)
    if period == PERIOD_TODAY:
        return period, today, today
    if period == PERIOD_7D:
        return period, today - timedelta(days=6), today
    if period == PERIOD_30D:
        return period, today - timedelta(days=DEFAULT_DAYS - 1), today
    if period == PERIOD_MONTH:
        return period, today.replace(day=1), today
    if period == PERIOD_CUSTOM:
        lo, hi = _range(request, start, end)
        return period, lo, hi
    raise ValidationAppError("지원하지 않는 기간입니다.")


def range_label(start: date, end: date) -> str:
    """기간 한 문장 - 「기간은 9월 2일부터 10월 1일까지입니다.」 해가 다르면 해를 붙인다."""
    def day(d: date, with_year: bool) -> str:
        return f"{d.year}년 {d.month}월 {d.day}일" if with_year else f"{d.month}월 {d.day}일"

    with_year = start.year != end.year
    if start == end:
        return f"기간은 {day(start, with_year)} 하루입니다."
    return f"기간은 {day(start, with_year)}부터 {day(end, with_year)}까지입니다."


def _extra(db: Session, q: str | None, visible) -> tuple:
    clause = usage.search_clause(db, q, visible=visible) if q else None
    return (clause,) if clause is not None else ()


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
    period: str | None = Query(default=None, max_length=8),
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, max_length=100),
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
        raise ValidationAppError("지원하지 않는 보기 기준입니다.")
    period, start, end = _period(request, period, start, end)
    lo, hi = usage.day_bounds(start, end)
    visible = _visible(db, principal)
    filters = {**_filters(action, user_id, provider, model, status, department_id), "extra": _extra(db, q, visible)}
    items = usage.stats(db, start=lo, end=hi, group_by=group_by, visible=visible, **filters)
    totals = usage.totals(db, start=lo, end=hi, visible=visible, **filters)
    # 옛 화면이 읽던 합계 칸(`blocked`)은 남긴다 - 새 화면은 한도 초과와 정책 차단을 따로 읽는다.
    totals["blocked"] = totals["blocked_quota"] + totals["blocked_policy"]
    return {"items": items, "total": len(items), "totals": totals, "group_by": group_by, "period": period,
            "range_label": range_label(start, end), "from": start.isoformat(), "to": end.isoformat()}


@router.get("/records")
def usage_records(
    request: Request,
    period: str | None = Query(default=None, max_length=8),
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, max_length=100),
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
    period, start, end = _period(request, period, start, end)
    lo, hi = usage.day_bounds(start, end)
    visible = _visible(db, principal)
    items, total = usage.records(
        db, start=lo, end=hi, visible=visible, limit=page.page_size, offset=page.offset, sort=sort,
        **_filters(action, user_id, provider, model, status, department_id), extra=_extra(db, q, visible),
    )
    return {"items": items, "total": total, "page": page.page, "page_size": page.page_size, "period": period,
            "range_label": range_label(start, end), "from": start.isoformat(), "to": end.isoformat()}


@router.get("/catalog")
def usage_catalog() -> dict:
    """화면의 조건 목록 - 기능(액션)과 결과. 화면이 이름을 지어내지 않게 서버가 준다."""
    from app.ai.actions import ACTIONS

    return {
        "actions": [{"key": key, "label": action.label, "retired": bool(action.retired)} for key, action in ACTIONS.items()],
        "statuses": [{"key": key, "label": label} for key, label in usage.STATUS_LABELS.items()],
        "periods": [{"key": key, "label": label} for key, label in PERIODS],
        "views": [{"key": key, "label": label} for key, label in VIEWS],
        "groups": [
            {"key": usage.GROUP_ACTION, "label": "기능"}, {"key": usage.GROUP_USER, "label": "사용자"},
            {"key": usage.GROUP_DEPARTMENT, "label": "부서"}, {"key": usage.GROUP_PROVIDER, "label": "제공자"},
            {"key": usage.GROUP_MODEL, "label": "모델"}, {"key": usage.GROUP_STATUS, "label": "결과"},
            {"key": usage.GROUP_DAY, "label": "날짜"},
        ],
    }
