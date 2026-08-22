"""프로젝트 진행률 — **Notion 이 틀리는 지점 네 개**를 각각 못박는다.

이 테스트가 존재하는 이유는 "계산이 맞나" 가 아니라 **"Notion 과 다르게 세고 있나"** 다.
그래서 표본은 전부 **틀린 방법으로 세면 값이 달라지는** 데이터다. 그렇지 않은 표본으로
쓰면(예: 취소가 하나도 없는 목록) 계산을 통째로 바꿔도 테스트가 통과한다 - 초록불인데
아무것도 증명하지 못하는 상태이고, 이 저장소가 이미 그 실패를 여러 번 겪었다.

각 테스트는 **맞는 값**뿐 아니라 **틀린 값들**도 함께 적어 둔다. 그래야 나중에 누가 계산을
Notion 쪽으로 되돌렸을 때 실패 메시지가 "왜 틀렸는지"를 그 자리에서 말해 준다.
"""

from __future__ import annotations

import pytest

from app.projects.progress import (
    STATUS_CANCELLED,
    STATUS_DONE,
    WEIGHT_COUNT,
    WEIGHT_EST_WD,
    WEIGHT_MIXED,
    WEIGHT_NONE,
    Task,
    compute_progress,
)

pytestmark = pytest.mark.unit

IN_PROGRESS = "진행"


def test_cancelled_tasks_leave_both_the_numerator_and_the_denominator():
    """취소는 **분자에도 분모에도** 없다.

    Notion 은 status 그룹이 `complete = [완료, 취소]` 라서 취소를 완료로 센다 - 10건 중
    3건을 취소하면 진행률이 그냥 +30% 다. 아무 일도 안 하고 올릴 수 있는 숫자는 지표가 아니다.
    반대로 분모에만 남기면 "취소했더니 프로젝트가 나빠졌다" 가 된다. 둘 다 아니다.
    """
    tasks = [
        Task(key="t1", status=STATUS_DONE, est_wd=3),
        Task(key="t2", status=STATUS_CANCELLED, est_wd=7),
        Task(key="t3", status=IN_PROGRESS, est_wd=10),
    ]
    result = compute_progress(tasks)

    # 3 / (3 + 10) = 23.07…
    assert result.percent == 23.1, f"취소를 뺀 값이 아니다: {result.as_dict()}"
    assert result.percent != 50.0, (
        "취소를 완료로 세고 있다 - Notion 의 percent_per_group(Complete) 과 같은 오류다"
    )
    assert result.percent != 15.0, (
        "취소를 분모에만 남겼다 - 취소가 진행률을 끌어내린다"
    )
    assert result.basis.cancelled_excluded == 1
    assert result.basis.counted_tasks == 2, "분모에 취소가 남아 있다"


def test_only_leaf_tasks_are_counted():
    """하위 작업이 있으면 **리프만** 센다. 부모는 자식의 합이지 별개의 일이 아니다.

    Notion 은 상위/하위 self-relation 에 걸린 행을 전부 세어 같은 일을 두 번 센다.
    """
    tasks = [
        Task(key="p", status=IN_PROGRESS, est_wd=10),
        Task(key="c1", parent_key="p", status=STATUS_DONE, est_wd=4),
        Task(key="c2", parent_key="p", status=IN_PROGRESS, est_wd=6),
        Task(key="solo", status=STATUS_DONE, est_wd=10),
    ]
    result = compute_progress(tasks)

    # (4 + 10) / (4 + 6 + 10) = 70%
    assert result.percent == 70.0, f"리프만 센 값이 아니다: {result.as_dict()}"
    assert result.percent != 46.7, (
        "부모를 함께 셌다(이중 계산) - 부모 10WD 가 분모에 또 들어갔다"
    )
    assert result.basis.parent_tasks_excluded == 1
    assert result.basis.counted_tasks == 3


def test_estimated_workdays_actually_weigh_the_result():
    """1일짜리와 20일짜리가 같은 1건이면 안 된다.

    Notion 은 건수만 센다. 1일짜리를 끝내고 20일짜리를 남기면 건수로는 50% 지만 남은 일은
    전체의 95% 다. 그 두 숫자가 갈리는 표본으로 확인한다.
    """
    tasks = [
        Task(key="small", status=STATUS_DONE, est_wd=1),
        Task(key="big", status=IN_PROGRESS, est_wd=19),
    ]
    result = compute_progress(tasks)

    assert result.percent == 5.0, f"예상 WD 로 가중하지 않았다: {result.as_dict()}"
    assert result.percent != 50.0, "건수로 셌다 - 20일짜리와 1일짜리를 같게 봤다"
    assert result.basis.weight_mode == WEIGHT_EST_WD
    assert result.basis.total_weight == 20.0
    assert result.basis.done_weight == 1.0


def test_missing_estimates_fall_back_to_one_and_the_result_says_so():
    """예상 WD 가 없으면 가중 1 로 대체하고 **그 사실을 반환값에 담는다**.

    담지 않으면 화면은 "20% 완료" 라고만 말하는데, 그게 공수 기준인지 건수 기준인지
    구별할 방법이 없다. 두 숫자가 갈렸을 때 어느 쪽이 맞는지 판단할 근거가 사라진다.
    """
    none_at_all = compute_progress([
        Task(key="a", status=STATUS_DONE),
        Task(key="b", status=IN_PROGRESS),
        Task(key="c", status=STATUS_DONE),
        Task(key="d", status=IN_PROGRESS),
    ])
    assert none_at_all.percent == 50.0
    assert none_at_all.basis.weight_mode == WEIGHT_COUNT, (
        "예상 WD 가 하나도 없는데 'WD 기준' 이라고 말한다"
    )
    assert none_at_all.basis.est_wd_missing == 4

    mixed = compute_progress([
        Task(key="a", status=STATUS_DONE, est_wd=3),
        Task(key="b", status=IN_PROGRESS),
    ])
    # 3 / (3 + 1) = 75%
    assert mixed.percent == 75.0, f"없는 WD 를 1 로 대체하지 않았다: {mixed.as_dict()}"
    assert mixed.basis.weight_mode == WEIGHT_MIXED, (
        "가중이 섞였는데 섞였다고 말하지 않는다 - 화면이 근거를 잘못 말하게 된다"
    )
    assert mixed.basis.est_wd_missing == 1


def test_zero_or_negative_estimates_are_treated_as_missing():
    """0 WD 는 '없음'과 같이 다룬다. 가중이 0이면 끝내도 진행률이 안 오른다."""
    result = compute_progress([
        Task(key="a", status=STATUS_DONE, est_wd=0),
        Task(key="b", status=IN_PROGRESS, est_wd=0),
    ])
    assert result.percent == 50.0, f"0 WD 가 분모를 0으로 만들었다: {result.as_dict()}"
    assert result.basis.est_wd_missing == 2


def test_the_basis_says_what_was_counted_and_how():
    """계산 근거가 **실제로 담기는지** 본다. 숫자만 주면 두 값이 갈렸을 때 아무도 못 믿는다."""
    tasks = [
        Task(key="p", status=IN_PROGRESS, est_wd=99),
        Task(key="c1", parent_key="p", status=STATUS_DONE, est_wd=3),
        Task(key="c2", parent_key="p", status=STATUS_CANCELLED, est_wd=7),
        Task(key="c3", parent_key="p", status=IN_PROGRESS, est_wd=10),
    ]
    basis = compute_progress(tasks).basis.as_dict()

    assert basis == {
        "sample_tasks": 4,
        "parent_tasks_excluded": 1,
        "cancelled_excluded": 1,
        "counted_tasks": 2,
        "done_tasks": 1,
        "weight_mode": WEIGHT_EST_WD,
        "est_wd_missing": 0,
        "total_weight": 13.0,
        "done_weight": 3.0,
    }, "계산 근거가 실제로 센 것과 다르다"


def test_nothing_to_count_is_none_not_zero():
    """분모가 0이면 **None** 이다. 0% 라고 하면 두 상태가 화면에서 똑같아진다:
    '작업이 아직 안 붙은 프로젝트' 와 '붙었는데 하나도 못 끝낸 프로젝트'. 후자만 문제다."""
    empty = compute_progress([])
    assert empty.percent is None, "셀 것이 없는데 0% 라고 답한다"
    assert empty.basis.weight_mode == WEIGHT_NONE

    all_cancelled = compute_progress([
        Task(key="a", status=STATUS_CANCELLED, est_wd=5),
        Task(key="b", status=STATUS_CANCELLED, est_wd=5),
    ])
    assert all_cancelled.percent is None, (
        "전부 취소인데 0% 다 - 취소를 분모에 남겼다는 뜻이다"
    )
    assert all_cancelled.basis.cancelled_excluded == 2


def test_a_parent_outside_the_sample_does_not_hide_its_child():
    """표본 밖의 부모를 가리키는 작업은 **리프로 센다**.

    다른 프로젝트의 작업이 부모일 수 있는데, 그 부모는 이 프로젝트의 분모가 아니다.
    자식까지 빼 버리면 프로젝트에 걸린 일이 통째로 사라진다.
    """
    result = compute_progress([
        Task(key="c1", parent_key="somewhere-else", status=STATUS_DONE, est_wd=4),
        Task(key="c2", parent_key="somewhere-else", status=IN_PROGRESS, est_wd=4),
    ])
    assert result.percent == 50.0, f"표본 밖 부모 때문에 자식이 사라졌다: {result.as_dict()}"
    assert result.basis.counted_tasks == 2


def test_it_reads_the_ticket_columns_it_claims_to_read():
    """`task_from_ticket` 이 실제로 읽는 것과 **받는 것**을 가른다 (S6).

    키는 **티켓 UUID** 다. 0044 때는 `notion_page_id` 였는데, 그때는 계층의 출처가
    미러의 `parent_page_id`(page id 축)였기 때문이다. S6 이 계층의 정본을
    `ticket_relations`(uuid 축)로 옮기면서 키도 그 축으로 갔다 — 두 축을 섞으면 부모와
    자식이 영원히 안 만나고, 리프 판정이 조용히 전부 리프가 된다(= 이중 계산).

    상위는 **인자로 받는다.** 행에서 읽으면 이 순수 함수가 DB 를 아는 두 번째 자리가 된다.
    """
    from app.projects.progress import task_from_ticket
    from app.tickets.models import TicketCache

    row = TicketCache(
        id="uid-1", notion_page_id="page-child", parent_page_id="page-parent",
        status=STATUS_DONE, est_wd=2.5,
    )
    task = task_from_ticket(row, "uid-parent")

    assert task.key == "uid-1", "계층과 같은 축(티켓 UUID)이어야 부모와 자식이 만난다"
    assert task.parent_key == "uid-parent"
    assert task.status == STATUS_DONE
    assert task.est_wd == 2.5


def test_it_does_not_read_the_hierarchy_off_the_mirror_column():
    """**미러 컬럼을 안 본다** — 계층은 `ticket_relations` 가 답한다 (S6).

    이 단정이 없으면 「인자를 받도록 바꿨는데 행도 계속 읽는」 상태가 통과한다. 그
    상태에서는 두 값이 다를 때 어느 쪽이 이기는지가 코드 순서에 달려 있다.
    """
    from app.projects.progress import task_from_ticket
    from app.tickets.models import TicketCache

    row = TicketCache(
        id="uid-1", notion_page_id="page-child", parent_page_id="page-parent",
        status=STATUS_DONE, est_wd=2.5,
    )
    assert task_from_ticket(row).parent_key is None, (
        "관계 표가 상위를 안 준 티켓인데 미러 컬럼에서 상위를 읽어 왔다"
    )
