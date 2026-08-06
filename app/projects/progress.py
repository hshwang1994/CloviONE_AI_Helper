"""프로젝트 진행률을 **앱이 다시 계산한다** (순수 함수, DB·외부 호출 없음).

## Notion 의 진행률을 왜 안 쓰는가 — 실측한 근거 세 가지

1. **취소한 티켓이 '완료'로 집계된다.** 작업 DB `진행상태` 의 status 그룹이
   `complete = [완료, 취소]` 이고, 프로젝트 DB `티켓 진행률` rollup 은
   `operator=percent_per_group, groupName="Complete"` 다. 즉 10건 중 3건을 취소하면
   진행률이 그냥 **+30%** 다. 아무 일도 안 하고 올릴 수 있는 숫자는 지표가 아니다.
2. **하위 작업이 부모와 이중 계산된다.** 작업 DB 에 상위/하위 self-relation 이 있는데
   rollup 은 관계에 걸린 행을 전부 센다 — 부모 1건 + 자식 3건이면 같은 일이 4번 세어진다.
3. **예상 WD 가중이 없다.** 1일짜리와 20일짜리가 똑같이 1건이다. 20일짜리 하나만 남기고
   1일짜리 열아홉 개를 끝내면 95% 인데, 남은 일은 전체의 절반이다.

여기에 `프로젝트 진행률` 은 formula 라 코드가 불투명해 **검증조차 불가능**하다. 그래서
숫자를 받아 적지 않고 앱이 원자료(작업 목록)에서 다시 센다.

## 세는 규칙

    완료율 = Σ(완료 리프 작업 예상WD × 가중) / Σ(전체 리프 작업 예상WD × 가중)

  * **취소는 분자·분모에서 함께 뺀다.** 분모에만 남기면(미완료 취급) 취소가 진행률을
    끌어내려 "취소했더니 프로젝트가 나빠졌다"가 된다. 분자에만 넣으면 Notion 과 같은
    거짓말이다. 취소한 일은 **하기로 한 적 없는 일**로 취급하는 것이 맞다.
  * **리프만 센다.** 이 표본 안에서 누군가의 부모로 지목된 작업은 제외한다. 부모는 자식의
    합이지 별개의 일이 아니다.
  * **예상 WD 가 없으면 가중 1** 로 대체한다. 그리고 **그 사실을 반환값에 담는다** —
    가중이 섞였다는 것을 모르면 두 숫자가 갈렸을 때 어느 쪽이 맞는지 판단할 수 없다.

## 왜 숫자만 돌려주지 않는가

화면이 "무엇을 어떻게 셌는지" 말할 수 있어야 한다. Notion 화면과 우리 화면에 서로 다른
진행률이 뜨는 것은 **정상 상태**다(그게 이 모듈의 존재 이유다). 그때 근거가 없으면 아무도
어느 쪽도 못 믿고, 결국 둘 다 안 보게 된다. 그래서 `ProgressResult` 는 퍼센트 하나가 아니라
표본 수·가중 방식·제외 건수를 함께 들고 다닌다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 상태 어휘는 app/reports/service.py, app/sprints/burndown.py 와 **같은 문자열**이다.
# 여기서 새로 정의하면 Notion 의 상태 이름이 바뀔 때 고칠 자리가 세 곳이 된다.
STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"

# 가중 방식을 이름으로 남긴다. 화면이 "예상 WD 기준" 인지 "건수 기준" 인지 말할 수 있어야
# 하고, 섞였다면 섞였다고 말해야 한다.
WEIGHT_EST_WD = "est_wd"   # 리프 전부가 예상 WD 를 갖는다
WEIGHT_MIXED = "mixed"     # 일부만 갖는다 (없는 것은 1로 대체)
WEIGHT_COUNT = "count"     # 아무도 안 갖는다 = 사실상 건수 기준
WEIGHT_NONE = "none"       # 셀 것이 하나도 없다

# 예상 WD 가 없을 때 쓰는 대체 가중. '1건'을 뜻한다.
FALLBACK_WEIGHT = 1.0


@dataclass(frozen=True)
class Task:
    """진행률 계산에 필요한 최소 사실.

    `parent_key` 는 Notion 작업 DB 의 상위 작업 page id 다. 계층을 앱에서 새로 만들지 않고
    거기 이미 있는 것을 그대로 쓴다(`ticket_cache.parent_page_id`, 0044) — 계층이 두 벌이
    되면 둘이 갈라지고, 갈라진 쪽을 아무도 못 고친다.
    """

    key: str
    parent_key: str | None = None
    status: str | None = None
    est_wd: float | None = None


@dataclass(frozen=True)
class ProgressBasis:
    """**계산 근거.** 숫자 하나만 주면 두 값이 갈렸을 때 아무도 못 믿는다(모듈 docstring)."""

    # 넘겨받은 작업 전체. 여기서 아래 세 가지를 빼면 실제로 센 것(counted_tasks)이 된다.
    sample_tasks: int
    # 부모라서 뺀 것 (Notion 은 여기서 이중 계산한다)
    parent_tasks_excluded: int
    # 취소라서 뺀 것 (Notion 은 여기서 완료로 센다)
    cancelled_excluded: int
    # 실제로 분모에 들어간 리프 작업 수와, 그중 완료된 것
    counted_tasks: int
    done_tasks: int
    # 가중 방식과, 예상 WD 가 없어 1로 대체한 건수
    weight_mode: str
    est_wd_missing: int
    total_weight: float
    done_weight: float

    def as_dict(self) -> dict:
        return {
            "sample_tasks": self.sample_tasks,
            "parent_tasks_excluded": self.parent_tasks_excluded,
            "cancelled_excluded": self.cancelled_excluded,
            "counted_tasks": self.counted_tasks,
            "done_tasks": self.done_tasks,
            "weight_mode": self.weight_mode,
            "est_wd_missing": self.est_wd_missing,
            "total_weight": self.total_weight,
            "done_weight": self.done_weight,
        }


@dataclass(frozen=True)
class ProgressResult:
    """`percent` 는 셀 것이 없으면 **None** 이다 — 0.0 이 아니다.

    분모가 0인데 0% 라고 답하면 "작업이 아직 하나도 안 붙은 프로젝트"와 "붙었는데 하나도
    못 끝낸 프로젝트"가 화면에서 똑같아 보인다. 둘은 완전히 다른 상태이고, 후자만 문제다.
    """

    percent: float | None
    basis: ProgressBasis

    def as_dict(self) -> dict:
        return {"percent": self.percent, "basis": self.basis.as_dict()}


def _num(value) -> float | None:
    """예상 WD 는 소스에서 None·빈 문자열·문자열 숫자로 온다(app/profiles/stats.py 와 같은 사정).

    0 이나 음수는 '없음'과 같이 취급한다 — 가중이 0이면 그 작업은 분모에 있으나 마나이고,
    끝내도 진행률이 안 오른다(끝낸 사람에게는 버그로 보인다).
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _weight_mode(counted: int, missing: int) -> str:
    if counted == 0:
        return WEIGHT_NONE
    if missing == 0:
        return WEIGHT_EST_WD
    if missing == counted:
        return WEIGHT_COUNT
    return WEIGHT_MIXED


def compute_progress(tasks) -> ProgressResult:
    """작업 목록 하나에서 진행률과 그 근거를 낸다.

    `tasks` 는 `Task` 들이다. **이 표본이 곧 세계다** — 리프 판정도 여기 있는 것들 사이에서만
    한다. 부모가 표본 밖에 있으면(예: 다른 프로젝트의 작업) 그 자식은 리프로 센다. 표본 밖의
    부모를 추적하려고 DB 를 다시 부르면 이 함수가 순수하지 않게 되고, 무엇보다 **그 부모는
    이 프로젝트의 분모가 아니다.**
    """
    rows = list(tasks)

    keys = {t.key for t in rows if t.key}
    # 이 표본 안에서 **누군가의 부모로 지목된** 작업. 부모는 자식의 합이지 별개의 일이 아니다.
    parent_keys = {t.parent_key for t in rows if t.parent_key and t.parent_key in keys}

    leaves = [t for t in rows if t.key not in parent_keys]
    parents_excluded = len(rows) - len(leaves)

    counted: list[Task] = []
    cancelled = 0
    for task in leaves:
        # 취소는 분자·분모에서 **함께** 빠진다. 한쪽에만 빼면 취소가 지표를 움직인다.
        if task.status == STATUS_CANCELLED:
            cancelled += 1
            continue
        counted.append(task)

    total_weight = 0.0
    done_weight = 0.0
    done_tasks = 0
    missing = 0
    for task in counted:
        weight = _num(task.est_wd)
        if weight is None:
            weight = FALLBACK_WEIGHT
            missing += 1
        total_weight += weight
        if task.status == STATUS_DONE:
            done_tasks += 1
            done_weight += weight

    basis = ProgressBasis(
        sample_tasks=len(rows),
        parent_tasks_excluded=parents_excluded,
        cancelled_excluded=cancelled,
        counted_tasks=len(counted),
        done_tasks=done_tasks,
        weight_mode=_weight_mode(len(counted), missing),
        est_wd_missing=missing,
        total_weight=round(total_weight, 2),
        done_weight=round(done_weight, 2),
    )
    percent = round(done_weight / total_weight * 100, 1) if total_weight > 0 else None
    return ProgressResult(percent=percent, basis=basis)


def task_from_ticket(row) -> Task:
    """`ticket_cache` 행 하나를 `Task` 로. 이 파일에서 DB 를 아는 유일한 자리이고, 아는 것은
    **컬럼 이름 네 개뿐**이다(질의는 repository 가 한다).

    `notion_page_id` 를 키로 쓰는 이유: 부모를 가리키는 값(`parent_page_id`)이 Notion page id
    라서 같은 축이어야 이어진다. 자체 UUID(`id`)를 키로 쓰면 부모/자식이 영원히 안 만난다.
    """
    return Task(
        key=row.notion_page_id or row.id,
        parent_key=row.parent_page_id,
        status=row.status,
        est_wd=row.est_wd,
    )
