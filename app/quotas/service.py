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
from app.observability.service import EVENT_AI_CALL
from app.quotas import quota_lock
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

# 쿼터가 세는 이벤트. 'AI 호출'이라는 **비용 축**이라 다른 감사성 이벤트(로그인·티켓 생성 등)와
# 뜻이 다르지만(meta.kind로 어느 기능인지 구분한다), 값 자체는 여전히 observability/service.py
# 하나에서만 만든다(UB-25) — 예전엔 여기서 별도로 "ai.call"을 다시 정의해서, 그 파일의
# KNOWN_EVENTS(오타 누적 방지용 집합)가 이 이벤트를 몰랐다. 문자열이 같아도 정의가 둘이면
# 결국 갈라진다.

KIND_ASSISTANT_NARRATIVE = "assistant_narrative"
KIND_DOCUMENT_GENERATE = "document_generate"
# AI 도우미 채팅 — **가장 큰 비용 축인데 상한 밖에 있었다**(X11).
KIND_CHAT_MESSAGE = "chat_message"

# `pending()`이 "아직 record_call이 안 불렸지만 이미 큐에 들어간" 것으로 셀 잡 유형(UB-09).
# `ai_quotas.reserve()`(확인→큐 적재를 한 덩어리로 묶는 예약형 경로 — consume()과 달리
# 기록을 워커가 나중에 한다)를 쓰는 잡 유형만 여기 속한다. 새 AI 잡 유형이 reserve()로
# 전환되면 이 집합에도 추가해야 한다 — 안 하면 pending()이 그 잡의 예약을 조용히 놓친다.
# `tests/regression/test_pending_job_types_cover_every_record_call_handler.py`가
# `record_call`을 부르는 잡 핸들러 전부가 이 집합에 있는지 상시 대조한다.
from app.jobs.models import JOB_TYPE_CHAT_MESSAGE  # noqa: E402 — 상수 재수출 목적, 순환 없음

PENDING_JOB_TYPES = frozenset({JOB_TYPE_CHAT_MESSAGE})


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


def used_batch(db: Session, *, pairs: set[tuple[str, str]], now: datetime) -> dict[tuple[str, str], int]:
    """여러 (user_id, period) 쌍의 `used()`를 한 번에 (UB-10).

    `list_quotas`는 사용자 전용 쿼터 행마다 `used()`를 따로 불러 N+1이었다 — 행 수만큼
    질의가 늘었다. 기간은 `ALL_PERIODS`(하루/한 달) 둘뿐이므로, 기간별로 묶어 **최대
    2개** 질의로 전부 답한다. 값이 없는 (user_id, period) 조합은 0이다 — 호출부가
    `.get((uid, period), 0)`로 읽는다.
    """
    if not pairs:
        return {}
    by_period: dict[str, set[str]] = {}
    for user_id, period in pairs:
        by_period.setdefault(period, set()).add(user_id)
    out: dict[tuple[str, str], int] = {}
    for period, user_ids in by_period.items():
        rows = db.execute(
            select(UsageEvent.user_id, func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.event == EVENT_AI_CALL,
                UsageEvent.user_id.in_(user_ids),
                UsageEvent.created_at >= period_start(period, now),
            )
            .group_by(UsageEvent.user_id)
        ).all()
        for user_id, count in rows:
            out[(user_id, period)] = int(count)
    return out


def pending(db: Session, *, user_id: str, period: str, now: datetime) -> int:
    """아직 세어지지 않았지만 **이미 쓰기로 확정된** AI 호출 수 (Z15).

    ## 왜 이것까지 세야 하나

    AI 도우미 채팅은 확인(라우터)과 기록(워커)이 서로 다른 프로세스에 있다. 큐에 들어간
    호출은 워커가 끝낼 때까지 `usage_events` 어디에도 없으므로, 그동안 `used()` 만 보면
    **아무것도 안 쓴 사람**으로 보인다. 하루 상한이 1인 사람도 워커가 도는 사이에 원하는
    만큼 보낼 수 있었다. 잠금으로는 못 막는다. 잠금은 이 프로세스 안 이야기이고, 여기서
    빠져 있는 것은 '이미 확정된 소비' 라는 사실 자체다.

    그래서 예약을 **DB 에서** 읽는다. 잡 행이 곧 예약이다: 큐에 들어간 순간 생기고,
    워커가 끝내면 상태가 바뀌어 사라지고, 그 자리를 `record_call` 이 이어받는다.
    이중으로 세지 않는 근거가 그것이다. 예약이 사라지는 시점과 기록이 생기는 시점이
    같은 트랜잭션이다(`app/jobs/handlers/chat_message.py`).

    ## 기간 경계로 막는 이유

    워커가 죽어 잡이 `queued` 로 굳으면 그 사람의 상한이 한 칸 줄어든 채로 남는다.
    기간 시작 이후에 만들어진 잡만 세면 늦어도 다음 날 자정(KST)에는 저절로 풀린다.

    ## 화면 숫자에는 넣지 않는다

    `status()` 의 `used` 는 **실제로 쓴 수**여야 한다. 예약은 몇 초 뒤 사라지는 값이라
    거기 섞으면 새로고침할 때마다 숫자가 오르내린다. 상한 판정만 이 값을 함께 본다.

    ## 왜 `job_type` 이 하드코딩 하나가 아니라 집합인가 (UB-09)

    이 함수는 "`record_call`을 나중에 부르는 잡 유형 전부"를 세어야 하는데, 예전엔
    `chat_message` 하나만 봤다. **오늘은 맞다** — `record_call`을 부르는 잡 핸들러는
    `app/jobs/handlers/chat_message.py` 뿐이다(`tests/regression/
    test_pending_job_types_cover_every_record_call_handler.py`가 이 사실 자체를
    상시 검증한다). 하지만 하드코딩 하나로는 다음 AI 잡 유형이 같은 예약→기록 패턴
    (`ai_quotas.reserve`)을 새로 쓰기 시작해도 이 함수가 **조용히** 그걸 놓친다 —
    증상은 "청구서가 예상보다 크다"로 몇 달 뒤에야 드러난다(모듈이 스스로 적어 둔
    경고). `PENDING_JOB_TYPES`를 한 곳에 모아 두면 새 잡 유형을 추가하는 사람이
    적어도 검색으로 이 자리를 찾을 수 있고, 위 완결성 시험이 추가를 깜빡한 경우를 잡는다.
    """
    from app.jobs.models import STATUS_QUEUED, STATUS_RUNNING, Job

    return int(
        db.execute(
            select(func.count())
            .select_from(Job)
            .where(
                Job.job_type.in_(PENDING_JOB_TYPES),
                Job.user_id == user_id,
                Job.status.in_((STATUS_QUEUED, STATUS_RUNNING)),
                Job.created_at >= period_start(period, now),
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


def max_user_used(db: Session, *, period: str, now: datetime) -> int:
    """이번 기간에 **가장 많이 쓴 한 사람**의 호출 수 (UB-02).

    `enforce()`는 전역(global) 상한도 `used(user_id=...)`, 즉 **사용자별**로 판정한다
    (전사 공용 풀이 아니다 — 그러려면 사용자 전원을 아우르는 잠금이 있어야 하는데 지금은
    사람별 잠금뿐이다). 예전엔 관리 화면 목록이 전역 행의 '현재 사용'에 `used_all`
    (전 사용자 합계)을 보여줘서, 실제로는 아무도 안 막힌 상황에서도 "150 / 100 — 상한
    도달"처럼 존재하지 않는 차단을 알리는 화면이 됐다. 여기서는 **실제 판정이 보는 값**과
    같은 축(개인별 사용량)으로 답한다 — 이 값이 상한에 닿아야 그 사람이 실제로 막힌다.
    """
    rows = db.execute(
        select(UsageEvent.user_id, func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.event == EVENT_AI_CALL,
            UsageEvent.created_at >= period_start(period, now),
        )
        .group_by(UsageEvent.user_id)
    ).all()
    return max((count for _user_id, count in rows), default=0)


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

    **기록된 호출 + 예약된 호출**을 함께 본다 (Z15). 기록만 보면 큐에 들어간 호출이
    아무 데도 안 세어져 상한이 새고, 예약만 보면 이미 끝난 호출을 두 번 센다.
    이 함수는 혼자 쓰면 여전히 창이 열려 있다 - `consume`/`reserve` 로 감싼다.
    """
    limits = effective_limits(db, user_id)
    if not limits:
        return
    for period in (PERIOD_DAY, PERIOD_MONTH):
        limit = limits.get(period)
        if limit is None:
            continue
        max_calls, _source = limit
        counted = used(db, user_id=user_id, period=period, now=now) + pending(
            db, user_id=user_id, period=period, now=now
        )
        if counted >= max_calls:
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


# ── 확인과 소비를 한 덩어리로 (Z15) ──────────────────────────────────────────
#
# `enforce()` 를 그냥 부르고 나중에 `record_call()` 을 부르면 그 사이가 잠기지 않은 창이다.
# 동시 요청이 같은 숫자를 읽고 **함께** 통과한다. 아래 두 문지기가 그 구간을 감싼다.
# 잠금이 프로세스 안이어도 되는 근거(그리고 워커를 늘리는 날 무엇을 같이 고쳐야 하는지)는
# `app/quotas/quota_lock.py` 모듈 docstring 에 있다.


class consume:
    """확인 → AI 호출 → 기록을 한 덩어리로 (동기 경로 전용).

        with ai_quotas.consume(db, user_id=…, org_id=…, kind=…, now=now) as slot:
            result = call_the_ai()
            if succeeded(result):
                slot.record()
                db.commit()   # 기록이 다른 요청에 보여야 뜻이 있다

    **`record()` 를 부르지 않으면 세지 않는다.** 성공한 호출만 센다는 기존 규약 그대로다
    (러너가 죽은 날 사용자가 답을 못 받고 상한만 잃으면 안 된다). 잠금은 블록을 나갈 때
    풀리므로, 호출이 오래 걸리는 동안 같은 사람의 다른 요청은 기다린다.

    ⚠️ **`record()` 뒤에는(그리고 블록이 끝나기 전에) 반드시 `db.commit()` 해야 한다** —
    `reserve` 와 정확히 같은 이유(UB-08)다. SQLite 는 커밋 전 쓰기를 다른 커넥션에 보여
    주지 않는다. `record()`(→ `record_call`)는 `flush()` 만 하고 커밋은 이 블록을 부른
    라우터가 요청 맨 끝(`get_db`)에서야 한다 — 그 사이(잠금이 풀린 뒤부터 실제 커밋까지)
    같은 사용자의 다른 요청이 잠금을 얻어 `enforce()` 를 돌리면, 방금 쓴(아직 커밋 안 된)
    사용량을 못 보고 상한을 통과할 수 있다. 잠금을 걸어 놓고 그 목적을 못 지키는 것과
    같다 — `reserve` 의 docstring 이 이미 이 원칙을 못박아 뒀는데 `consume` 의 두 호출부
    (`documents/router.py`, `assistant/router.py`)만 안 지키고 있었다.
    """

    def __init__(
        self,
        db: Session,
        *,
        user_id: str,
        org_id: str | None,
        kind: str,
        now: datetime,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._org_id = org_id
        self._kind = kind
        self._now = now
        self._guard = quota_lock.quota_guard(db, user_id)

    def __enter__(self) -> "consume":
        self._guard.__enter__()
        try:
            enforce(self._db, user_id=self._user_id, now=self._now)
        except BaseException:
            # 막힌 요청은 블록 안으로 들어가지 못하므로 __exit__ 이 안 불린다.
            self._guard.__exit__(None, None, None)
            raise
        return self

    def record(self) -> None:
        record_call(
            self._db, user_id=self._user_id, org_id=self._org_id,
            kind=self._kind, now=self._now,
        )

    def __exit__(self, *exc) -> None:
        self._guard.__exit__(*exc)


class reserve:
    """확인 → 큐 적재를 한 덩어리로 (기록을 워커가 하는 경로 전용).

        with ai_quotas.reserve(db, user_id=…, now=now):
            message, job = post_user_message(…)
            db.commit()   # 예약(잡 행)이 다른 요청에 보여야 뜻이 있다

    ⚠️ **블록 안에서 커밋해야 한다.** 커밋 전 쓰기는 다른 트랜잭션에 안 보이므로, 잠금을
    놓은 뒤에 커밋하면 그 사이에 들어온 요청이 이 잡을 못 보고 같은 한 칸을 또 가져간다 -
    잠금을 걸어 놓고 아무것도 못 막는 상태가 된다.

    advisory `xact` 잠금에서는 **그 커밋이 곧 해제**다(D-192). 즉 '보이게 만드는 것'과
    '놓는 것'이 한 순간에 일어나 그 틈 자체가 사라진다 — 순서를 지켜야 하는 규약이
    순서를 틀릴 수 없는 구조가 됐다.
    """

    def __init__(self, db: Session, *, user_id: str, now: datetime) -> None:
        self._db = db
        self._user_id = user_id
        self._now = now
        self._guard = quota_lock.quota_guard(db, user_id)

    def __enter__(self) -> "reserve":
        self._guard.__enter__()
        try:
            enforce(self._db, user_id=self._user_id, now=self._now)
        except BaseException:
            self._guard.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        self._guard.__exit__(*exc)


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
