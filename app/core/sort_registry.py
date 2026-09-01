"""화면이 고를 수 있는 정렬 키를 **한 곳에서** 모은다.

## 왜 필요한가

허용 키는 서버(도메인 모듈의 `SortSpec`)와 화면(registry 의 `serverSort.keys`) 양쪽에 있다.
두 벌이 갈라지면 증상이 조용하다 — 화면은 화살표를 그리고, 사용자는 누르고, 서버는 모르는
키를 **기본 정렬로 조용히 떨어뜨린다**(그것이 옛 링크를 살리는 옳은 동작이다). 결과는
「눌렀는데 순서가 그대로」이고 아무 데도 오류가 안 남는다.

그래서 `fieldLimits.json` 과 같은 관용을 쓴다: 서버에서 뽑아 JSON 으로 커밋하고, 신선도는
검사가 고정한다(`scripts/check_sort_keys_fresh.py`).

## 라우터가 아니라 서비스/저장소를 import 한다

라우터를 import 하면 앱 전체(의존성·미들웨어)가 끌려 온다. 정렬 계약은 도메인 모듈이 들고
있으므로 그쪽만 읽는다 — `app/core/field_limits.py` 가 스키마만 읽는 것과 같은 단방향이다.
"""

from __future__ import annotations


def all_sort_specs() -> dict:
    """`{화면 키: {"keys": [...], "default": {"key": ..., "dir": ...}}}`.

    화면 키는 registry(`frontend/src/screens/registry/*.js`)의 키와 같은 이름이다 —
    프런트가 자기 선언과 대조할 수 있어야 하기 때문이다.
    """
    from datetime import datetime, timezone

    from app.announcements.router import _list_sort as announcements_sort
    from app.approvals import service as approvals_service
    from app.audit.repository import LIST_SORT as audit_sort
    from app.impersonation.router import _LIST_SORT as impersonation_sort
    from app.jobs.repository import LIST_SORT as jobs_sort
    from app.notifications.router import LIST_SORT as notifications_sort
    from app.offboarding.service import LIST_SORT as offboarding_sort
    from app.schedules.router import _RUN_SORT as schedule_runs_sort

    # 유효 상태 판정이 시계를 보므로 하나 필요하다 — 여기서는 **키 목록만** 쓰므로 어떤
    # 시각이든 결과가 같다.
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)

    specs = {
        "audit": audit_sort,
        "notifications": notifications_sort,
        "admin-notifications": notifications_sort,
        "jobs": jobs_sort,
        "approvals": approvals_service.list_sort_spec(now, admin=True),
        "my-approvals": approvals_service.list_sort_spec(now, admin=False),
        "announcements": announcements_sort(),
        "impersonation": impersonation_sort,
        "offboarding": offboarding_sort,
        "schedule-runs": schedule_runs_sort,
    }
    return {
        key: {"keys": list(spec.keys), "default": {"key": spec.default, "dir": spec.default_order}}
        for key, spec in specs.items()
    }