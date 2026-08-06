"""감사 로그의 **행위자 기준** 범위 판정 — 한 곳 (§0-A 2순위 후속).

감사 로그는 *누가 무엇을 했나* 라서 **행위자가 곧 축**이다. 목록·CSV 내보내기·이상 징후가
전부 이 조건 하나만 쓴다.

## 왜 함수로 빼는가

판정을 화면마다 손으로 적으면 화면이 늘 때마다 한 벌씩 늘고, 그중 하나만 빠져도 증상은
"목록에선 안 보이는데 다른 화면에는 다 나온다" 가 된다. 실제로 그 상태였다: 목록과
export.csv 는 조건을 걸었는데 `GET /anomalies` 는 `principal` 파라미터조차 없어서 창 안의
`audit_log` **전량**을 행위자별로 묶었고, 거기에 이름과 **이메일**까지 붙여 내보냈다.
가려 둔 사람의 활동 요약이 그 화면 하나로 통째로 샌 것이다.

`app/jobs/repository.py::scope_clause` 와 같은 모양이고 같은 규약을 쓴다 — 두 모듈이
같은 문제(행위자 없는 자동 처리를 어떻게 다루나)에 같은 답을 내야 하기 때문이다.
"""

from __future__ import annotations

from sqlalchemy import Select, or_ as sa_or

from app.audit.models import AuditLog


def scope_clause(visible: frozenset[str] | None):
    """범위 안 행위자의 기록을 고르는 조건. 전역이면 ``None``(= 조건 없음).

    ``None`` 을 돌려주는 규약은 `core/scope.py::scope_filter` 와 같다 — 조건을 빼먹은
    코드와 '전역이라 조건이 없는' 코드를 눈으로 구별하기 위해서다.

    **시스템 행위(`user_id` 없음)는 남긴다.** 그건 누구의 것도 아니고, 없애면 부서
    관리자가 자기 범위에서 일어난 자동 처리(보존 정리·동기화 실패 등)를 아예 못 본다.
    범위 집합이 비어 있어도 이 갈래는 살아 있다(잡 큐가 같은 이유로 같은 규칙이다).
    """
    if visible is None:
        return None
    return sa_or(
        AuditLog.user_id.in_(tuple(sorted(visible))), AuditLog.user_id.is_(None)
    )


def apply_scope(stmt: Select, visible: frozenset[str] | None) -> Select:
    """``select(AuditLog…)`` 에 범위를 건다. 전역이면 그대로 돌려준다."""
    clause = scope_clause(visible)
    return stmt if clause is None else stmt.where(clause)
