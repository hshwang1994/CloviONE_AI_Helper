"""Schedule definition helpers shared by the router and the approval executor.

Lives apart from the router so the approval executor can import it without a
cycle (router → approvals.service → schedules.service).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from app.core.errors import ConflictError, ValidationAppError
from app.schedules import cron
from app.schedules.models import TYPE_ONCE, Schedule

#: 판(`definition_version`)을 만들 때 빼는 스냅샷 항목. `next_run_at` 은 정의가 아니라
#: **실행 장부**다 — 스케줄러가 실행할 때마다 다시 쓴다.
_VERSION_EXCLUDED = frozenset({"next_run_at"})


def definition_version(row: Schedule) -> str:
    """이 행의 **정의**가 어느 판인가. 편집 폼이 그대로 돌려보내면 낙관적 잠금이 된다.

    `updated_at` 을 쓰지 않는다. 스케줄러가 한 번 돌 때마다 `last_run_at` 과 `next_run_at`
    을 쓰고, 그 쓰기가 `TimestampMixin` 의 `onupdate` 를 건드려 `updated_at` 을 올린다
    (`지금 실행`·`재시도` 도 같은 칸을 쓴다). 그러면 매시 도는 일정의 편집 폼을 09:59 에
    연 관리자가 10:01 에 저장할 때 "다른 사람이 먼저 저장했습니다" 를 듣는다 — 먼저 저장한
    사람은 없고, 그가 고쳐서 통과할 수 있는 것도 없다. 짧은 주기로 도는 일정일수록 잠금
    경로로는 아예 저장할 수 없게 된다.

    잠금이 지켜야 하는 것은 **정의**이므로 정의에서만 판을 만든다. 정의를 이미 한 벌로
    모아 둔 곳이 `definition_snapshot` 이라 그것을 그대로 쓰고, 실행 장부인 `next_run_at`
    하나만 뺀다. 같은 값으로 저장하면 판도 그대로다 — 아무것도 안 바뀐 저장이 남의 편집
    창을 깨뜨리지 않는다.
    """
    fields = {
        key: value
        for key, value in definition_snapshot(row).items()
        if key not in _VERSION_EXCLUDED
    }
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def ensure_enablable(row: Schedule, now: datetime) -> datetime | None:
    """활성화가 성립하는지 보고, 성립하면 **첫 예정 시각**을 돌려준다. 행은 바꾸지 않는다.

    ## 왜 판정이 여기 있나

    활성화에는 문이 둘이다(spec §20). system_admin 은 그 자리에서 적용하고, 나머지 관리자는
    승인 요청을 만든다 — 그리고 승인을 거치는 쪽이 system_admin 이 **아닌 모든** 관리자다
    (`app/approvals/service.py::needs_approval`). 판정을 적용 쪽에만 두면 실제로 사람들이
    쓰는 경로는 그 검사를 한 번도 지나지 않는다. 같은 일정을 system_admin 이 켜면 409 인데
    관리자가 켜면 켜지는, 답이 둘인 상태가 된다.

    그래서 두 갈래가 갈라지기 **전에** 한 번 본다. 성립하지 않는 활성화로는 승인 요청도
    만들지 않는다 — 승인자에게 절대 적용될 수 없는 결재를 보내지 않는다는 뜻이다.

    돌려주는 값은 활성화됐을 때의 `next_run_at` 이다. cron 은 여기서 계산하고, once 는
    이미 저장된 실행 시각이 그대로 첫 예정이다.

    승인 실행기(`app/approvals/service.py::_execute_schedule_enable`)는 승인 시점에 같은
    계산을 제 손으로 다시 한다. 그쪽도 이 함수를 부르게 하면 「요청은 기간 안이었는데
    결재가 기간이 끝난 뒤에 났다」는 남은 한 경우까지 닫힌다.
    """
    if row.schedule_type == TYPE_ONCE:
        if row.next_run_at is None or row.next_run_at <= now:
            raise ConflictError("1회 실행 일정의 실행 시각이 이미 지났습니다.")
        # 활성화 시점에도 run_at < start_at을 거부한다 — 정의는 create/update에서 막지만,
        # start_at만 나중에 바뀌는 등으로 어긋난 상태가 게이트를 통과하지 못하게 한다.
        if row.start_at is not None and row.next_run_at < row.start_at:
            raise ValidationAppError(
                "1회 실행 일정의 실행 시각이 시작 시각보다 빠릅니다. 실행 시각을 시작 시각 뒤로 정하세요."
            )
        next_run_at = row.next_run_at
    else:
        anchor = max(now, row.start_at) if row.start_at else now
        next_run_at = cron.next_after(row.cron_expression, row.timezone, anchor)
    # 유효 기간 밖의 예정으로는 활성화하지 않는다. 예전에는 기간이 이미 끝난 일정도
    # 활성으로 올라가 목록에 '다음 실행' 시각을 적었고, 스케줄러는 그 한 번을 실제로
    # 돌린 뒤에야 내려갔다(once 형이 지난 실행 시각을 거절하는 것과 같은 규칙이다).
    if row.end_at is not None and next_run_at is not None and next_run_at > row.end_at:
        raise ConflictError(
            "유효 기간 안에 남은 실행이 없습니다. 종료 시각을 미룬 뒤 다시 활성화하세요."
        )
    return next_run_at


def definition_snapshot(row: Schedule) -> dict:
    """승인 시점의 '무엇을 활성화하는가'를 고정한 스냅샷.

    승인은 그 시점의 정의에 대한 것이다. 승인 화면에 그대로 보여 주고(무엇을 승인하는지),
    실행 직전 현재 정의와 대조해 대기 중 바뀐 정의가 승인 없이 활성화되는 것을 막는다.
    실행 결과를 바꾸는 필드는 물론, 승인자가 판단 근거로 읽는 이름/설명까지 포함한다.
    """
    return {
        "name": row.name,
        "description": row.description,
        "schedule_type": row.schedule_type,
        "cron_expression": row.cron_expression,
        "timezone": row.timezone,
        "target_type": row.target_type,
        "target_ref": row.target_ref,
        "payload_template": json.loads(row.payload_template_json or "{}"),
        "retry_policy": json.loads(row.retry_policy_json or "{}"),
        "misfire_policy": row.misfire_policy,
        "concurrency_policy": row.concurrency_policy,
        "timeout_seconds": row.timeout_seconds,
        "start_at": row.start_at.isoformat() if row.start_at else None,
        "end_at": row.end_at.isoformat() if row.end_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
    }
