"""AI 쿼터 판정 — 소비량은 `usage_events` 에서 센다 (0033, PLAN Phase 6).

기간 경계는 **Asia/Seoul 달력**으로 자른다. UTC 로 자르면 사용자가 체감하는 '오늘'과
9시간 어긋나 아침 9시 전에 상한이 초기화되는 것처럼 보인다(감사 로그의 날짜 필터가
이미 같은 이유로 KST 를 쓴다 — `app/audit/router.py::_parse_boundary`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import RateLimitedError, ValidationAppError
from app.observability.models import UsageEvent
from app.quotas.models import (
    ALL_PERIODS,
    ALL_SCOPES,
    GLOBAL_USER_ID,
    PERIOD_DAY,
    PERIOD_MONTH,
    SCOPE_GLOBAL,
    SCOPE_USER,
    AiQuota,
)

logger = logging.getLogger("app.quotas")

_KST = ZoneInfo("Asia/Seoul")

# 쿼터가 세는 이벤트. `app/observability/service.py` 의 이벤트 이름들과 달리 이건 'AI 호출'
# 이라는 **비용 축**이라 별도 이름을 쓴다 — meta.kind 로 어느 기능인지 구분한다.
EVENT_AI_CALL = "ai.call"

KIND_ASSISTANT_NARRATIVE = "assistant_narrative"
KIND_DOCUMENT_GENERATE = "document_generate"
# AI 도우미 채팅 — **가장 큰 비용 축인데 상한 밖에 있었다**(X11).
KIND_CHAT_MESSAGE = "chat_message"


def validate(scope_type: str, period: str, max_calls: int) -> None:
    if scope_type not in ALL_SCOPES:
        raise ValidationAppError(f"scope_type 은 {', '.join(ALL_SCOPES)} 중 하나여야 합니다.")
    if period not in ALL_PERIODS:
        raise ValidationAppError(f"period 는 {', '.join(ALL_PERIODS)} 중 하나여야 합니다.")
    if not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls < 0:
        raise ValidationAppError("max_calls 는 0 이상의 정수여야 합니다.")


def period_start(period: str, now: datetime) -> datetime:
    """기간 시작 시각(naive UTC). 경계는 KST 달력으로 자른다."""
    local = now.replace(tzinfo=timezone.utc).astimezone(_KST)
    if period == PERIOD_MONTH:
        local_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc).replace(tzinfo=None)


def period_end(period: str, now: datetime) -> datetime:
    """다음 기간이 시작하는 시각(naive UTC) — 사용자에게 '언제 풀리는가'를 말해 준다."""
    start = period_start(period, now)
    local = start.replace(tzinfo=timezone.utc).astimezone(_KST)
    if period == PERIOD_MONTH:
        nxt = (local.replace(day=28) + timedelta(days=7)).replace(day=1)
    else:
        nxt = local + timedelta(days=1)
    return nxt.astimezone(timezone.utc).replace(tzinfo=None)


def used(db: Session, *, user_id: str, period: str, now: datetime) -> int:
    """이번 기간에 이 사용자가 쓴 AI 호출 수."""
    return int(
        db.execute(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.event == EVENT_AI_CALL,
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= period_start(period, now),
            )
        ).scalar_one()
    )


def used_all(db: Session, *, period: str, now: datetime) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.event == EVENT_AI_CALL,
                UsageEvent.created_at >= period_start(period, now),
            )
        ).scalar_one()
    )


def effective_quota_rows(db: Session, user_id: str) -> dict[str, AiQuota]:
    """period → **실제로 적용되는 쿼터 행**. 사용자 전용 행이 전역보다 우선한다.

    사용자 행이 있으면 그 값이 이깁니다 — '이 사람만 늘려 준다'와 '이 사람만 줄인다'를
    같은 방식으로 표현할 수 있어야 하기 때문이다(전역 최소치를 강제하면 전자를 못 한다).

    **행을 돌려주는 쪽이 원본이다.** 소진 알림이 "어느 쿼터에 걸렸는가"를 알림에 실어야
    해서(중복 발송을 막는 열쇠가 그 행의 id 다) 상한 숫자만으로는 부족해졌다. 우선순위
    규칙을 두 벌로 쓰면 한쪽만 고쳐지고, 그때 증상은 "어떤 사람만 알림을 못 받는다"라
    찾기가 매우 어렵다.
    """
    rows = (
        db.execute(
            select(AiQuota).where(
                AiQuota.scope_type.in_((SCOPE_GLOBAL, SCOPE_USER)),
                AiQuota.user_id.in_((GLOBAL_USER_ID, user_id)),
            )
        )
        .scalars()
        .all()
    )
    picked: dict[str, AiQuota] = {}
    for row in rows:
        if row.scope_type == SCOPE_GLOBAL and row.user_id == GLOBAL_USER_ID:
            picked.setdefault(row.period, row)
        elif row.scope_type == SCOPE_USER and row.user_id == user_id:
            picked[row.period] = row
    return picked


def effective_limits(db: Session, user_id: str) -> dict[str, tuple[int, str]]:
    """period → (상한, 어디서 온 상한인가). 판정은 `effective_quota_rows` 한 곳이다."""
    return {
        period: (row.max_calls, row.scope_type)
        for period, row in effective_quota_rows(db, user_id).items()
    }


def status(db: Session, *, user_id: str, now: datetime) -> dict:
    """이 사용자의 현재 소비 상황. 화면과 오류 메시지가 같은 값을 쓴다."""
    limits = effective_limits(db, user_id)
    out = []
    for period in ALL_PERIODS:
        limit = limits.get(period)
        out.append(
            {
                "period": period,
                "limit": limit[0] if limit else None,
                "source": limit[1] if limit else None,
                "used": used(db, user_id=user_id, period=period, now=now),
                "resets_at": period_end(period, now).isoformat(),
            }
        )
    return {"user_id": user_id, "periods": out}


def enforce(db: Session, *, user_id: str, now: datetime) -> None:
    """상한을 넘었으면 429. 상한 행이 없으면 아무 제한도 없다(fail-open).

    **fail-open 인 이유**: 쿼터는 비용 통제 장치이지 보안 장치가 아니다. 표가 비어 있는
    기본 상태에서 AI 기능이 통째로 막히면, 이 기능을 켠 적도 없는 운영자가 원인을 찾느라
    한나절을 쓴다. 반대로 상한이 명시돼 있으면 그건 의도된 값이므로 정확히 지킨다.
    """
    limits = effective_limits(db, user_id)
    if not limits:
        return
    for period in (PERIOD_DAY, PERIOD_MONTH):
        limit = limits.get(period)
        if limit is None:
            continue
        max_calls, _source = limit
        if used(db, user_id=user_id, period=period, now=now) >= max_calls:
            resets = period_end(period, now)
            label = "하루" if period == PERIOD_DAY else "이번 달"
            raise RateLimitedError(
                f"{label} AI 사용 상한({max_calls}회)에 도달했습니다. "
                f"{resets.replace(tzinfo=timezone.utc).astimezone(_KST):%m월 %d일 %H시} 이후 다시 사용할 수 있습니다.",
                retry_after_seconds=max(1, int((resets - now).total_seconds())),
            )


def record_call(db: Session, *, user_id: str, org_id: str | None, kind: str, now: datetime) -> None:
    """AI 호출 한 번을 기록한다. 기록 실패는 요청을 죽이지 않는다(record_usage 규약).

    센 **직후**에 소진 여부를 본다 — 상한에 닿은 순간을 아는 유일한 자리다(아래 함수 참조).
    """
    from app.observability.service import record_usage

    record_usage(
        db,
        event=EVENT_AI_CALL,
        user_id=user_id,
        org_id=org_id,
        object_type="ai",
        object_id=kind,
        meta={"kind": kind},
        now=now,
    )
    _announce_exhausted(db, user_id=user_id, now=now)


def _announce_exhausted(db: Session, *, user_id: str, now: datetime) -> None:
    """상한을 **다 쓴 순간** 알린다 (N2).

    감사 확인: 사용자는 **쓰려는 순간에야** 상한에 걸린 것을 알았다. 429 를 보고서야 아는
    것은 너무 늦다 — 그때는 이미 하려던 일을 못 한 뒤다. 마지막 한 번을 쓴 직후에 알리면
    다음 작업을 계획할 여지가 남는다.

    ## 왜 `enforce` 가 아니라 여기인가

    두 가지 이유다.

    1. `enforce` 는 429 를 **던진다**. 예외가 나가면 `get_db` 가 요청 세션을 통째로
       롤백하므로 거기서 만든 알림 행은 사라진다 — 즉 그 자리에서는 알림을 남길 수 없다.
    2. `enforce` 는 막힌 **모든 시도**에서 돈다. 거기서 알리면 상한에 걸린 사람이 새로고침을
       누를 때마다 알림이 쌓여서, 하필 그 사람의 배지만 폭주한다.

    여기(`record_call`)는 성공한 호출의 뒤이고 커밋되는 경로다.

    ## 중복 방지

    이번 기간에 **그 쿼터 행**으로 이미 보낸 알림이 있으면 다시 보내지 않는다. 열쇠를
    쿼터 행 id 로 잡는 이유: 하루 상한과 한 달 상한은 서로 다른 사건이고, 기간이 바뀌면
    (내일이 되면) 같은 행이라도 다시 알려야 한다. 두 조건을 같이 봐야 둘 다 맞는다.

    실패해도 호출 기록은 남는다 — 알림은 본 작업보다 약한 관심사다.
    """
    try:
        from app.notifications.models import Notification
        from app.notifications.service import notify_user

        rows = effective_quota_rows(db, user_id)
        for period in (PERIOD_DAY, PERIOD_MONTH):
            row = rows.get(period)
            if row is None:
                continue
            if used(db, user_id=user_id, period=period, now=now) < row.max_calls:
                continue
            already = db.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.type == "ai_quota_exhausted",
                    Notification.related_object_id == row.id,
                    Notification.created_at >= period_start(period, now),
                )
            ).scalar_one()
            if already:
                continue
            resets = period_end(period, now)
            label = "하루" if period == PERIOD_DAY else "이번 달"
            notify_user(
                db, user_id, type_="ai_quota_exhausted",
                title=f"{label} AI 사용 상한({row.max_calls}회)을 다 썼습니다",
                body=(
                    f"{resets.replace(tzinfo=timezone.utc).astimezone(_KST):%m월 %d일 %H시}"
                    " 이후 다시 사용할 수 있습니다."
                ),
                related=("ai_quota", row.id), now=now,
            )
    except Exception:  # noqa: BLE001 — 알림이 AI 호출 기록을 막으면 안 된다
        logger.exception("AI 쿼터 소진 알림에 실패했다 (user_id=%s)", user_id)


def view(row: AiQuota, names: dict[str, dict[str, str]] | None = None) -> dict:
    names = names or {}
    target = names.get(row.user_id, {})
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "user_id": row.user_id or None,
        "user_name": target.get("display_name"),
        "user_email": target.get("email"),
        "period": row.period,
        "max_calls": row.max_calls,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
