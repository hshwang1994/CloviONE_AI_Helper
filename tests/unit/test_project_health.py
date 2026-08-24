"""Health Score 규칙 — **규칙마다 점수가 실제로 달라지는 표본**으로 못박는다.

이 테스트가 존재하는 이유는 "점수가 계산되나" 가 아니라 **"각 규칙이 정말로 점수를
움직이나"** 다. 그래서 어느 표본도 "나쁜 것 하나 넣고 100 이 아닌지 본다" 로 끝나지 않는다.
같은 규칙에서 **정도가 다른 두 표본**을 나란히 넣고 두 점수가 서로 다른지 본다.

왜 그렇게까지 하는가: 이 저장소는 초록불인데 아무것도 증명하지 못하는 테스트를 이미 여러 번
겪었다. 예를 들어 지연 비율 규칙을 "지연이 하나라도 있으면 -20" 으로 바꿔 놓아도, 표본이
'지연 있음 / 지연 없음' 둘뿐이면 테스트는 그대로 통과한다. 비율을 실제로 쓰는지 보려면
**1/4 지연과 3/4 지연의 점수가 달라야** 한다.

그리고 이 모듈에서 가장 중요한 계약은 점수가 아니라 **모른다고 말하는 능력**이다.
마일스톤이 하나도 없는 프로젝트를 '일정 준수 100점' 으로 세면 그 점수는 거짓말이고,
거짓말인 줄 아무도 모른다(그럴듯하기 때문이다). 계산할 수 없는 지표는 빼고, 뺐다는 사실을
반환값에 담는지 확인한다.
"""

from __future__ import annotations

import pytest

from app.projects.health import (
    BASE_SCORE,
    MAX_MILESTONE_PENALTY,
    RULE_MILESTONE_OVERDUE,
    RULE_STALE,
    RULE_TASK_OVERDUE,
    RULE_UNASSIGNED,
    HealthInput,
    MilestoneFact,
    TaskFact,
    compute_health,
)
from app.projects.models import (
    MILESTONE_DONE,
    MILESTONE_PLANNED,
)
from app.projects.progress import STATUS_CANCELLED, STATUS_DONE

pytestmark = pytest.mark.unit

TODAY = "2026-08-06"
YESTERDAY = "2026-08-05"
LAST_MONTH = "2026-07-06"
TOMORROW = "2026-08-07"
IN_PROGRESS = "진행"


def _rules(result) -> dict[str, int]:
    """규칙 → 감점. 이유 목록을 이름으로 찾기 쉽게."""
    return {r.rule: r.penalty for r in result.reasons}


def _unknown(result) -> set[str]:
    return {u.rule for u in result.unknown}


def _healthy_task(**over) -> TaskFact:
    """감점 요인이 하나도 없는 열린 작업. 한 축만 바꿔 가며 쓴다."""
    base = {"status": IN_PROGRESS, "due_on": TOMORROW, "assigned": True}
    return TaskFact(**{**base, **over})


def _input(**over) -> HealthInput:
    """모든 규칙이 **계산 가능하고 감점은 0** 인 기준 입력.

    기준이 100 이라야 한 축을 나쁘게 바꿨을 때 그 차이가 곧 그 규칙의 감점이 된다.
    """
    base = {
        "today": TODAY,
        "milestones": (MilestoneFact(due_on=TOMORROW, status=MILESTONE_PLANNED),),
        "tasks": (_healthy_task(),),
        "last_activity_on": TODAY,
    }
    return HealthInput(**{**base, **over})


def test_the_baseline_sample_scores_a_hundred_with_every_rule_checked():
    """기준선이 100 이 아니면 아래 테스트들의 '차이' 가 무엇의 차이인지 알 수 없다."""
    result = compute_health(_input())

    assert result.score == BASE_SCORE, f"기준 표본이 감점됐다: {result.as_dict()}"
    assert result.reasons == (), f"감점 요인이 없는데 이유가 붙었다: {result.as_dict()}"
    assert result.unknown == (), f"전부 계산 가능한 표본인데 모른다고 한다: {result.as_dict()}"
    assert set(result.checked) == {
        RULE_MILESTONE_OVERDUE, RULE_TASK_OVERDUE, RULE_UNASSIGNED, RULE_STALE,
    }


def test_an_overdue_milestone_costs_points_and_more_of_them_cost_more():
    """기한 지난 마일스톤. **개수에 따라 점수가 달라져야** 한다.

    '하나라도 늦으면 고정 감점' 으로 구현해도 한 건짜리 표본만으로는 안 걸린다.
    """
    one_late = compute_health(_input(milestones=(
        MilestoneFact(due_on=YESTERDAY, status=MILESTONE_PLANNED),
        MilestoneFact(due_on=TOMORROW, status=MILESTONE_PLANNED),
    )))
    two_late = compute_health(_input(milestones=(
        MilestoneFact(due_on=YESTERDAY, status=MILESTONE_PLANNED),
        MilestoneFact(due_on=LAST_MONTH, status=MILESTONE_PLANNED),
    )))

    assert one_late.score < BASE_SCORE, f"기한 지난 마일스톤이 점수를 안 움직인다: {one_late.as_dict()}"
    assert two_late.score < one_late.score, (
        f"늦은 마일스톤이 하나든 둘이든 점수가 같다(개수를 안 센다): "
        f"{one_late.score} vs {two_late.score}"
    )
    assert RULE_MILESTONE_OVERDUE in _rules(one_late), "감점만 하고 이유를 안 남겼다"
    detail = next(r.detail for r in two_late.reasons if r.rule == RULE_MILESTONE_OVERDUE)
    assert "2" in detail, f"이유에 몇 건이 늦었는지가 없다: {detail!r}"


def test_a_finished_milestone_is_not_late_even_if_its_date_has_passed():
    """끝난 일을 계속 지연으로 세면 마일스톤을 닫을 이유가 없어진다."""
    done_late = compute_health(_input(milestones=(
        MilestoneFact(due_on=LAST_MONTH, status=MILESTONE_DONE),
    )))
    still_open = compute_health(_input(milestones=(
        MilestoneFact(due_on=LAST_MONTH, status=MILESTONE_PLANNED),
    )))

    assert done_late.score == BASE_SCORE, (
        f"완료한 마일스톤이 지연으로 세어졌다: {done_late.as_dict()}"
    )
    assert still_open.score < done_late.score, "오탐 방지 - 안 끝난 쪽은 감점돼야 한다"


def test_the_overdue_milestone_penalty_has_a_ceiling():
    """마일스톤 하나로 프로젝트 점수를 0 까지 끌어내리면 다른 규칙이 안 보인다."""
    many = compute_health(_input(milestones=tuple(
        MilestoneFact(due_on=YESTERDAY, status=MILESTONE_PLANNED) for _ in range(20)
    )))
    penalty = _rules(many)[RULE_MILESTONE_OVERDUE]
    assert penalty == MAX_MILESTONE_PENALTY, (
        f"상한이 안 걸렸다: {penalty} (상한 {MAX_MILESTONE_PENALTY})"
    )


def test_the_overdue_task_ratio_moves_the_score_not_just_its_presence():
    """지연 티켓 **비율**. 1/4 지연과 3/4 지연의 점수가 달라야 한다.

    건수만 보거나 '있다/없다' 로만 보면 4건짜리 프로젝트와 400건짜리 프로젝트가 같은 벌을
    받는다. 그 숫자는 팀에게 아무것도 알려 주지 않는다.
    """
    quarter = compute_health(_input(tasks=(
        _healthy_task(due_on=YESTERDAY),
        _healthy_task(), _healthy_task(), _healthy_task(),
    )))
    most = compute_health(_input(tasks=(
        _healthy_task(due_on=YESTERDAY),
        _healthy_task(due_on=YESTERDAY),
        _healthy_task(due_on=YESTERDAY),
        _healthy_task(),
    )))

    assert quarter.score < BASE_SCORE, f"지연 티켓이 점수를 안 움직인다: {quarter.as_dict()}"
    assert most.score < quarter.score, (
        f"1/4 지연과 3/4 지연의 점수가 같다(비율을 안 쓴다): {quarter.score} vs {most.score}"
    )
    assert RULE_TASK_OVERDUE in _rules(quarter)


def test_the_unassigned_ratio_moves_the_score_too():
    half = compute_health(_input(tasks=(
        _healthy_task(assigned=False), _healthy_task(),
    )))
    all_of_them = compute_health(_input(tasks=(
        _healthy_task(assigned=False), _healthy_task(assigned=False),
    )))

    assert half.score < BASE_SCORE, f"미할당이 점수를 안 움직인다: {half.as_dict()}"
    assert all_of_them.score < half.score, (
        f"절반 미할당과 전부 미할당의 점수가 같다: {half.score} vs {all_of_them.score}"
    )
    assert RULE_UNASSIGNED in _rules(half)


def test_closed_tasks_are_neither_late_nor_unassigned():
    """완료, 취소한 작업은 지금 손 쓸 일이 아니다. 분모에 남기면 끝낸 프로젝트일수록
    점수가 나빠진다 - 지표가 팀에게 반대로 행동하라고 말하는 셈이다."""
    closed = compute_health(_input(tasks=(
        TaskFact(status=STATUS_DONE, due_on=LAST_MONTH, assigned=False),
        TaskFact(status=STATUS_CANCELLED, due_on=LAST_MONTH, assigned=False),
        _healthy_task(),
    )))

    assert closed.score == BASE_SCORE, (
        f"끝난 작업이 지연, 미할당으로 세어졌다: {closed.as_dict()}"
    )
    assert RULE_TASK_OVERDUE not in _rules(closed)
    assert RULE_UNASSIGNED not in _rules(closed)


def test_a_long_silence_costs_points_and_a_longer_one_costs_more():
    """최근 활동 없음. **얼마나 오래** 조용했는지가 점수에 남아야 한다."""
    fresh = compute_health(_input(last_activity_on=TODAY))
    quiet = compute_health(_input(last_activity_on="2026-07-20"))   # 17일 전
    silent = compute_health(_input(last_activity_on="2026-06-01"))  # 66일 전

    assert fresh.score == BASE_SCORE
    assert quiet.score < fresh.score, f"3주 가까이 조용한데 감점이 없다: {quiet.as_dict()}"
    assert silent.score < quiet.score, (
        f"17일 침묵과 66일 침묵의 점수가 같다: {quiet.score} vs {silent.score}"
    )
    assert RULE_STALE in _rules(quiet)


def test_the_frozen_mirror_column_no_longer_takes_points_away():
    """예전에는 이 시험이 반대를 단언했다: 미러 컬럼이 '차질' 이면 25점을 깎는다.

    그 컬럼(`projects.notion_status`)에 쓰는 코드가 없어져 값이 이관 시점에 얼어붙었다.
    얼어붙은 값으로 점수를 계속 깎으면 팀이 무엇을 고쳐도 사라지지 않는 벌점이 되고, 그건
    지표가 아니다. 그래서 규칙을 통째로 걷었다 - 되살리면 이 시험이 빨개진다.
    """
    from app.projects import health as health_mod

    assert hasattr(health_mod, "RULE_NOTION_TROUBLE") is False
    assert hasattr(health_mod, "NOTION_STATUS_TROUBLE") is False
    assert hasattr(health_mod, "PENALTY_NOTION_TROUBLE") is False
    assert hasattr(health_mod, "_rule_notion_trouble") is False
    assert "notion_status" not in HealthInput.__dataclass_fields__
    assert "notion_trouble" not in set(health_mod.RULE_ORDER)
    assert "notion_trouble" not in set(health_mod.RULE_LABELS)


def test_a_metric_that_cannot_be_computed_is_reported_not_assumed_healthy():
    """마일스톤이 없는 프로젝트는 '일정을 잘 지키는 프로젝트' 가 아니다. **모르는 것**이다.

    조용히 만점으로 세면 그 점수는 거짓말이고, 그럴듯해서 아무도 신고하지 않는다.
    """
    no_milestones = compute_health(_input(milestones=()))

    assert RULE_MILESTONE_OVERDUE in _unknown(no_milestones), (
        f"계산할 수 없는 지표를 계산한 척한다: {no_milestones.as_dict()}"
    )
    assert RULE_MILESTONE_OVERDUE not in no_milestones.checked
    why = next(u.why for u in no_milestones.unknown if u.rule == RULE_MILESTONE_OVERDUE)
    assert why, "왜 계산할 수 없었는지를 안 적었다"

    # 기한이 하나도 안 적힌 마일스톤만 있는 경우도 같다.
    undated = compute_health(_input(milestones=(
        MilestoneFact(due_on=None, status=MILESTONE_PLANNED),
    )))
    assert RULE_MILESTONE_OVERDUE in _unknown(undated), (
        "기한 없는 마일스톤을 '기한을 지켰다' 로 셌다"
    )


def test_tasks_that_cannot_answer_a_rule_leave_that_rule_unknown():
    """열린 작업이 없으면 지연 비율도 미할당 비율도 분모가 0 이다."""
    nothing_open = compute_health(_input(tasks=(
        TaskFact(status=STATUS_DONE, due_on=YESTERDAY, assigned=True),
    )))
    assert {RULE_TASK_OVERDUE, RULE_UNASSIGNED} <= _unknown(nothing_open), (
        f"분모가 0 인데 비율을 냈다: {nothing_open.as_dict()}"
    )

    # 기한이 안 적힌 열린 작업은 늦었는지 알 수 없다. 미할당 여부는 여전히 알 수 있다.
    undated = compute_health(_input(tasks=(_healthy_task(due_on=None),)))
    assert RULE_TASK_OVERDUE in _unknown(undated), (
        "기한 없는 작업을 '기한을 지켰다' 로 셌다"
    )
    assert RULE_UNASSIGNED in undated.checked, (
        "한 규칙을 못 세었다고 다른 규칙까지 버렸다"
    )


def test_nothing_computable_is_none_not_a_hundred():
    """아무 지표도 못 세는 프로젝트에 100 점을 주면 **가장 정보가 없는 프로젝트가 가장
    건강해 보인다.** 진행률이 분모 0 에서 None 인 것과 같은 이유다(progress.py)."""
    empty = compute_health(HealthInput(today=TODAY))

    assert empty.score is None, f"아무것도 못 셌는데 점수를 냈다: {empty.as_dict()}"
    assert empty.checked == (), f"{empty.as_dict()}"
    assert _unknown(empty) == {
        RULE_MILESTONE_OVERDUE, RULE_TASK_OVERDUE, RULE_UNASSIGNED, RULE_STALE,
    }, "못 센 지표를 목록에서 빠뜨렸다 - 화면이 무엇을 모르는지 말할 수 없다"


def test_the_score_never_goes_below_zero():
    """감점 합이 100 을 넘어도 음수 점수는 화면에서 뜻을 잃는다."""
    worst = compute_health(HealthInput(
        today=TODAY,
        milestones=tuple(
            MilestoneFact(due_on=LAST_MONTH, status=MILESTONE_PLANNED) for _ in range(9)
        ),
        tasks=(TaskFact(status=IN_PROGRESS, due_on=LAST_MONTH, assigned=False),),
        last_activity_on="2026-01-01",
    ))
    assert sum(r.penalty for r in worst.reasons) > BASE_SCORE, (
        "표본이 약해서 하한을 시험하지 못한다"
    )
    assert worst.score == 0, f"점수가 음수로 내려갔다: {worst.as_dict()}"


def test_every_reason_carries_a_readable_why():
    """점수만 주면 아무도 행동하지 못한다. 이유마다 한국어 설명이 붙어야 한다."""
    result = compute_health(_input(
        milestones=(MilestoneFact(due_on=YESTERDAY, status=MILESTONE_PLANNED),),
        tasks=(_healthy_task(due_on=YESTERDAY, assigned=False),),
        last_activity_on="2026-05-01",
    ))

    assert {r.rule for r in result.reasons} == {
        RULE_MILESTONE_OVERDUE, RULE_TASK_OVERDUE, RULE_UNASSIGNED, RULE_STALE,
    }, f"규칙 넷이 전부 걸리는 표본인데 일부가 빠졌다: {result.as_dict()}"
    for reason in result.reasons:
        assert reason.label, f"{reason.rule} 에 이름이 없다"
        assert reason.detail, f"{reason.rule} 에 설명이 없다"
        assert reason.penalty > 0, f"{reason.rule} 이 0 점짜리 이유로 실려 있다"


def test_the_result_round_trips_to_a_dict_for_the_snapshot():
    """이유 목록은 주간 스냅샷에 JSON 으로 저장된다. 저장할 수 있는 모양이어야 한다."""
    import json

    result = compute_health(_input(
        milestones=(MilestoneFact(due_on=YESTERDAY, status=MILESTONE_PLANNED),),
    ))
    payload = result.as_dict()

    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert payload["score"] == result.score
    assert payload["reasons"][0]["rule"] == RULE_MILESTONE_OVERDUE
