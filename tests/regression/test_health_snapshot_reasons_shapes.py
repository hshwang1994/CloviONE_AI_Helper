"""헬스 스냅샷의 이유 컬럼은 **한 모양이 아니다** — 읽는 곳도 하나여야 한다 (S18).

## 어떻게 드러났나

S18 이 Pilot 12화면을 로컬에서 찍는데 `/me` 만 콘솔 오류가 났다. 원인은 화면이 아니라
서버였다 — `GET /api/home/work-dashboard` 가 **500** 이었고(48페이지 실행에서 8회),
`AttributeError: 'list' object has no attribute 'get'` 이 그대로 새어 나왔다.

`project_health_snapshots.reasons_json` 에는 세 모양이 실제로 들어 있다:

  * `HealthResult.as_dict()` 가 쓴 객체 (`reasons`·`checked`·`unknown`)
  * **컬럼 기본값 `"[]"`** — 모델이 그렇게 선언돼 있다
  * 이유만 배열로 적힌 옛 모양

읽는 곳이 둘이었고 **한쪽만 그 사실을 알고 있었다.** `health_snapshot_reasons` 는 세
모양을 전부 다뤘는데, `latest_checked_rule_counts` 는 객체라고 가정하고 `.get("checked")`
를 불렀다. `AttributeError` 는 그쪽 `except (TypeError, ValueError)` 에 안 걸린다.

## 여기서 무엇을 못 박나

세 모양 × 두 읽기 경로를 전부 돌린다. 그리고 **홈이 실제로 200 을 낸다**는 것을 컬럼
기본값이 든 행 위에서 확인한다 — 파서 단위 시험만 두면 「그 파서를 안 쓰는 세 번째
호출부」가 생기는 날 이 시험은 여전히 초록이다.
"""

from __future__ import annotations

import json

import pytest

from app.projects.service import (
    health_snapshot_reasons,
    latest_checked_rule_counts,
    parse_health_snapshot_reasons,
)

pytestmark = pytest.mark.integration

FULL = json.dumps({
    "score": 72,
    "reasons": [{"rule": "milestone_overdue", "label": "지연된 마일스톤", "penalty": 20,
                 "detail": "2건"}],
    "checked": ["milestone_overdue", "progress_stalled", "unassigned_tasks"],
    "unknown": [{"rule": "recent_activity", "label": "최근 활동", "why": "작업이 없습니다"}],
}, ensure_ascii=False)
OLD_LIST = json.dumps(["지연된 마일스톤이 2건 있습니다."], ensure_ascii=False)
COLUMN_DEFAULT = "[]"
BROKEN = "{not json"


@pytest.mark.parametrize(("raw", "reasons", "checked"), [
    (FULL, 1, 3),
    (OLD_LIST, 1, 0),
    (COLUMN_DEFAULT, 0, 0),
    (BROKEN, 0, 0),
    (None, 0, 0),
    ("null", 0, 0),
    ('"문자열"', 0, 0),
])
def test_every_shape_parses_without_raising(raw, reasons, checked):
    parsed = parse_health_snapshot_reasons(raw)
    assert set(parsed) == {"reasons", "unknown", "checked"}
    assert len(parsed["reasons"]) == reasons
    assert len(parsed["checked"]) == checked


def test_screen_shape_does_not_leak_checked():
    """화면 응답 계약은 `reasons`·`unknown` 둘이다 — 넓히면 그것도 지킬 약속이 된다."""
    class _Row:
        reasons_json = FULL

    assert set(health_snapshot_reasons(_Row())) == {"reasons", "unknown"}


def _project_with_snapshot(db, make_project, reasons_json: str):
    from datetime import date

    from app.projects.models import ProjectHealthSnapshot

    project = make_project(name="이유 모양 시험")
    db.add(ProjectHealthSnapshot(project_id=project.id, week_of=date(2026, 8, 24),
                                 score=72, reasons_json=reasons_json))
    db.commit()
    return project


# `BROKEN` 은 여기 없다 — 컬럼이 `JSONB` 라 **깨진 JSON 은 애초에 저장되지 않는다**
# (INSERT 가 거절된다). 파서가 그것까지 견디는 것은 위 단위 시험이 지키고, 여기서는
# 실제로 DB 에 들어갈 수 있는 세 모양만 돌린다.
@pytest.mark.parametrize("raw", [FULL, OLD_LIST, COLUMN_DEFAULT])
def test_counts_survive_every_shape(db, make_project, raw):
    project = _project_with_snapshot(db, make_project, raw)
    counts = latest_checked_rule_counts(db, [project.id])
    assert project.id in counts
    assert counts[project.id] == (3 if raw is FULL else 0)


def test_home_work_dashboard_stays_200_on_the_column_default(
    client, login_as, db, make_project
):
    """**이것이 실제로 났던 실패다.** 파서만 고치고 화면을 안 보면 증명이 반쪽이다."""
    login_as("system_admin")
    _project_with_snapshot(db, make_project, COLUMN_DEFAULT)

    res = client.get("/api/home/work-dashboard")
    assert res.status_code == 200, res.text[:400]
    body = res.json()
    # 신뢰도 안내의 근거가 실제로 살아 있는지 — 「안 쟀다」를 「다 쟀다」로 뭉개지 않는다.
    assert "projects" in body
