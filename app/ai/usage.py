"""AI 호출 기록 — 한도의 원장, 사용 통계의 원천 (계획 3.10 · 3.11, D-517).

## 한 호출에 한 행

AI 런타임(`app/ai/runtime.py`)이 호출마다 한 행을 남긴다: 성공, 실패(제공자 오류, 시간 초과, 막힌 연결, 폭주 차단),
막힘(한도, 정책). 생성이 꺼져 있거나 설정이 비어 **아무것도 시도하지 않은 호출은 남기지 않는다** - 기능을 끈 설치에서
홈을 열 때마다 행이 쌓이면 통계가 소음이 된다.

행은 **제 짧은 세션으로 곧바로 커밋한다.** 부른 쪽의 트랜잭션이 실패해도 「방금 호출했다」는 사실이 사라지지 않고,
한도 잠금 안에서 같은 사람의 다음 요청이 방금 쓴 한 칸을 곧바로 본다. 기록이 실패해도 예외를 올리지 않는다 - 답은
이미 나갔다.

## 무엇을 세는가

한도는 **성공한 호출**만 센다(`status='ok'`). 실패한 호출과 막힌 호출로 사람의 한도가 줄면 안 된다. 관리자의 연결
확인(`system.connection_test`)은 액션 표에서 한도 밖이다(`counts_quota=False`).

## 무엇을 남기지 않는가

프롬프트 본문, 검색된 문맥, 응답 본문. 누가, 언제, 어떤 기능으로, 어느 모델에, 얼마나 썼고 어떻게 끝났는지만 남긴다.
부서 이름은 그때의 이름이다 - 부서 이름이 바뀌어도 지난달 통계가 새 이름으로 바뀌지 않는다.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

logger = logging.getLogger("app.ai.usage")

RETENTION_DAYS = 180
KST = ZoneInfo("Asia/Seoul")
MAX_RANGE_DAYS = 366

GROUP_ACTION = "action"
GROUP_USER = "user"
GROUP_DEPARTMENT = "department"
GROUP_PROVIDER = "provider"
GROUP_MODEL = "model"
GROUP_STATUS = "status"
GROUP_DAY = "day"
GROUPS = (GROUP_ACTION, GROUP_USER, GROUP_DEPARTMENT, GROUP_PROVIDER, GROUP_MODEL, GROUP_STATUS, GROUP_DAY)

STATUS_LABELS = {
    "ok": "성공",
    "error": "실패",
    "blocked_quota": "한도로 막힘",
    "blocked_policy": "정책으로 막힘",
}


@dataclass(frozen=True)
class Actor:
    """호출한 사람(또는 시스템)."""

    kind: str = "system"
    user_id: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    department_name: str | None = None

    @classmethod
    def of(cls, user) -> "Actor":
        if user is None or not getattr(user, "id", None):
            return cls()
        # `User.department` 는 명부에서 읽은 부서 **이름**이다(`app/users/models.py`). 사람 대신 id 만 든 값이
        # 오면(한도 경합 시험) 이름이 없다.
        department = getattr(user, "department", None)
        return cls(
            kind="user", user_id=user.id, org_id=getattr(user, "org_id", None),
            department_id=getattr(user, "department_id", None),
            department_name=department if isinstance(department, str) else None,
        )


SYSTEM = Actor()


def counted_actions() -> tuple[str, ...]:
    """한도에 세는 액션(`app/ai/actions.py::counts_quota`)."""
    from app.ai.actions import ACTIONS

    return tuple(key for key, action in ACTIONS.items() if action.counts_quota)


def _clip(value, size: int):
    return value[:size] if isinstance(value, str) and value else None


def _department_name(db: Session, department_id: str | None) -> str | None:
    """부른 쪽의 사람 객체에 부서 이름이 실려 있지 않으면(다른 세션에서 온 객체, id 만 든 값) 명부에서 읽는다."""
    if not department_id:
        return None
    from app.org.models import OrgUnit

    unit = db.get(OrgUnit, department_id)
    return unit.name if unit is not None else None


def record(session_factory, *, actor: Actor, action_key: str, status: str, now: datetime, provider=None,
           auth_method=None, model=None, error_code=None, input_tokens=None, output_tokens=None, latency_ms=None,
           prompt_slot=None, prompt_version=None, prompt_source=None, policy_ids=None, truncated_input=False,
           truncated_output=False, request_id=None, job_id=None) -> None:
    """한 행을 제 세션으로 적고 커밋한다. 성공한 사람의 호출이면 한도를 다 썼는지 그 자리에서 본다. 예외를 올리지 않는다."""
    if session_factory is None:
        return
    from app.ai.models import USAGE_OK, AiUsageRecord

    try:
        with session_factory() as db:
            db.add(AiUsageRecord(
                id=str(uuid.uuid4()), created_at=now, actor_kind=actor.kind, user_id=actor.user_id,
                org_id=actor.org_id, department_id=actor.department_id,
                department_name=_clip(actor.department_name or _department_name(db, actor.department_id), 200),
                action_key=action_key,
                provider=_clip(provider, 32), auth_method=_clip(auth_method, 32), model=_clip(model, 200),
                status=status, error_code=_clip(error_code, 64), input_tokens=input_tokens,
                output_tokens=output_tokens, latency_ms=latency_ms, prompt_slot=_clip(prompt_slot, 64),
                prompt_version=prompt_version, prompt_source=_clip(prompt_source, 16),
                policy_ids_json=json.dumps(sorted(policy_ids)) if policy_ids else None,
                truncated_input=bool(truncated_input), truncated_output=bool(truncated_output),
                request_id=_clip(request_id, 64), job_id=_clip(job_id, 36),
            ))
            db.flush()
            if status == USAGE_OK and actor.user_id and action_key in counted_actions():
                # 한도를 **다 쓴 순간**을 아는 곳이 여기다 - 성공한 호출의 뒤이고 커밋되는 경로다.
                from app.quotas.service import announce_if_exhausted

                announce_if_exhausted(db, user_id=actor.user_id, now=now)
            db.commit()
    except Exception:  # noqa: BLE001 - 기록이 답을 막으면 안 된다
        logger.exception("AI 호출 기록을 남기지 못했다")


def record_blocked_quota(session_factory, *, user, action_key: str, now: datetime, request_id=None) -> None:
    """한도에 막힌 요청 한 번. 제공자에는 닿지 않았다 - 통계가 「얼마나 자주 한도에 걸리는가」를 말한다."""
    from app.ai.models import USAGE_BLOCKED_QUOTA

    record(session_factory, actor=Actor.of(user), action_key=action_key, status=USAGE_BLOCKED_QUOTA, now=now,
           error_code="quota_exceeded", request_id=request_id)


# ── 읽기 ─────────────────────────────────────────────────────────────────────


def day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """한국 시간의 날짜 두 개(포함) → UTC 경계(naive, 끝은 다음 날 0시 직전까지)."""
    lo = datetime(start.year, start.month, start.day, tzinfo=KST)
    hi = datetime(end.year, end.month, end.day, tzinfo=KST) + timedelta(days=1)
    return (lo.astimezone(ZoneInfo("UTC")).replace(tzinfo=None), hi.astimezone(ZoneInfo("UTC")).replace(tzinfo=None))


def _filters(record_model, *, start: datetime, end: datetime, visible, action=None, user_id=None, provider=None,
             model=None, status=None, department_id=None) -> list:
    clauses = [record_model.created_at >= start, record_model.created_at < end]
    if visible is not None:
        # 부서 범위 관리자는 자기 범위 사람의 기록만 본다. 시스템 기록(연결 확인)은 전역 관리자만 본다.
        clauses.append(record_model.user_id.in_(visible or {"-"}))
    if action:
        clauses.append(record_model.action_key == action)
    if user_id:
        clauses.append(record_model.user_id == user_id)
    if provider:
        clauses.append(record_model.provider == provider)
    if model:
        clauses.append(record_model.model == model)
    if status:
        clauses.append(record_model.status == status)
    if department_id:
        clauses.append(record_model.department_id == department_id)
    return clauses


def percent(num: int, den: int) -> int | None:
    """반올림은 여기 한 곳에서 한다(ROUND_HALF_UP). 분모가 0 이면 모른다(None)."""
    if not den:
        return None
    return int((Decimal(num) * 100 / Decimal(den)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _group_column(record_model, group_by: str):
    if group_by == GROUP_ACTION:
        return record_model.action_key
    if group_by == GROUP_USER:
        return record_model.user_id
    if group_by == GROUP_DEPARTMENT:
        return func.coalesce(record_model.department_name, "")
    if group_by == GROUP_PROVIDER:
        return func.coalesce(record_model.provider, "")
    if group_by == GROUP_MODEL:
        return func.coalesce(record_model.model, "")
    if group_by == GROUP_STATUS:
        return record_model.status
    # 하루 단위는 한국 시간의 날짜로 자른다(화면의 「오늘」과 같은 경계).
    return func.to_char(func.timezone("Asia/Seoul", func.timezone("UTC", record_model.created_at)), "YYYY-MM-DD")


def stats(db: Session, *, start: datetime, end: datetime, group_by: str, visible=None, **filters) -> list[dict]:
    """묶음별 호출 수, 성공률, 토큰, 평균 지연. 성공률은 막힌 호출을 빼고 계산한다(제공자까지 간 호출 중 성공)."""
    from app.ai.models import USAGE_ERROR, USAGE_OK, AiUsageRecord as R

    key = _group_column(R, group_by).label("key")
    ok = func.sum(case((R.status == USAGE_OK, 1), else_=0)).label("ok")
    errors = func.sum(case((R.status == USAGE_ERROR, 1), else_=0)).label("errors")
    rows = db.execute(
        select(
            key, func.count().label("calls"), ok, errors,
            func.coalesce(func.sum(R.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(R.output_tokens), 0).label("output_tokens"),
            func.avg(R.latency_ms).label("avg_latency_ms"),
            func.max(R.created_at).label("last_at"),
        )
        .where(*_filters(R, start=start, end=end, visible=visible, **filters))
        .group_by(key)
        .order_by(func.count().desc(), key)
    ).all()
    labels = _labels(db, group_by, [row.key for row in rows])
    emails = _emails(db, [row.key for row in rows]) if group_by == GROUP_USER else {}
    out = []
    for row in rows:
        ok_count, error_count = int(row.ok or 0), int(row.errors or 0)
        out.append({
            "key": row.key or "",
            "label": labels.get(row.key, row.key) or "기록 없음",
            # 사람으로 묶을 때는 이름이 같은 두 사람을 가를 수 있게 이메일을 함께 준다(내부 id 로 묶었다).
            "email": emails.get(row.key),
            "calls": int(row.calls),
            "ok": ok_count,
            "errors": error_count,
            "blocked": int(row.calls) - ok_count - error_count,
            "success_rate": percent(ok_count, ok_count + error_count),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "avg_latency_ms": int(round(float(row.avg_latency_ms))) if row.avg_latency_ms is not None else None,
            "last_at": row.last_at.isoformat() if row.last_at else None,
        })
    return out


def _labels(db: Session, group_by: str, keys: list) -> dict:
    if group_by == GROUP_ACTION:
        from app.ai.actions import ACTIONS

        return {k: (ACTIONS[k].label if k in ACTIONS else k) for k in keys}
    if group_by == GROUP_USER:
        from app.impersonation.service import resolve_names

        names = resolve_names(db, [k for k in keys if k])
        return {k: (names.get(k, {}).get("display_name") or "알 수 없는 사용자") if k else "시스템" for k in keys}
    if group_by == GROUP_STATUS:
        return {k: STATUS_LABELS.get(k, k) for k in keys}
    if group_by == GROUP_DEPARTMENT:
        return {k: (k or "부서 없음") for k in keys}
    if group_by in (GROUP_PROVIDER, GROUP_MODEL):
        return {k: (k or "기록 없음") for k in keys}
    return {k: k for k in keys}


def _emails(db: Session, keys: list) -> dict:
    from app.impersonation.service import resolve_names

    names = resolve_names(db, [k for k in keys if k])
    return {k: names.get(k, {}).get("email") for k in keys if k}


def _list_sort():
    from app.ai.models import AiUsageRecord as R
    from app.core.sort import SortSpec

    return SortSpec(
        columns={
            "created_at": R.created_at, "action_key": R.action_key, "status": R.status, "model": R.model,
            "latency_ms": R.latency_ms, "input_tokens": R.input_tokens, "output_tokens": R.output_tokens,
        },
        default="created_at", tiebreak=R.id, default_order="desc",
    )


LIST_SORT = _list_sort()


def records(db: Session, *, start: datetime, end: datetime, visible=None, limit: int = 50, offset: int = 0,
            sort=None, **filters) -> tuple[list[dict], int]:
    """호출 기록 한 쪽과 전체 수. 본문은 없다 - 누가, 언제, 무엇으로, 어떻게 끝났는지만."""
    from app.ai.actions import ACTIONS
    from app.ai.models import AiUsageRecord as R
    from app.core.sort import order_by
    from app.impersonation.service import resolve_names

    clauses = _filters(R, start=start, end=end, visible=visible, **filters)
    total = int(db.execute(select(func.count()).select_from(R).where(*clauses)).scalar_one())
    rows = db.execute(
        select(R).where(*clauses).order_by(*order_by(LIST_SORT, sort)).limit(limit).offset(offset)
    ).scalars().all()
    names = resolve_names(db, [r.user_id for r in rows if r.user_id])
    items = []
    for row in rows:
        person = names.get(row.user_id or "", {})
        items.append({
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "user_id": row.user_id,
            "user_name": (person.get("display_name") or "알 수 없는 사용자") if row.user_id else "시스템",
            "user_email": person.get("email"),
            "department_name": row.department_name,
            "action_key": row.action_key,
            "action_label": ACTIONS[row.action_key].label if row.action_key in ACTIONS else row.action_key,
            "provider": row.provider,
            "model": row.model,
            "status": row.status,
            "status_label": STATUS_LABELS.get(row.status, row.status),
            "error_code": row.error_code,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "latency_ms": row.latency_ms,
            "prompt_slot": row.prompt_slot,
            "prompt_version": row.prompt_version,
            "truncated": bool(row.truncated_input or row.truncated_output),
        })
    return items, total


def purge_old(db: Session, *, now: datetime, retention_days: int = RETENTION_DAYS) -> int:
    """보존 기간(180일)이 지난 기록을 지운다. 보존 틱(`app/core/retention.py`)이 부른다."""
    from sqlalchemy import delete

    from app.ai.models import AiUsageRecord

    result = db.execute(delete(AiUsageRecord).where(AiUsageRecord.created_at < now - timedelta(days=retention_days)))
    return int(result.rowcount or 0)
