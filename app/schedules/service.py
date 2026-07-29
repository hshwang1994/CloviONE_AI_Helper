"""Schedule definition helpers shared by the router and the approval executor.

Lives apart from the router so the approval executor can import it without a
cycle (router → approvals.service → schedules.service).
"""

from __future__ import annotations

import json

from app.schedules.models import Schedule


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
