"""프로젝트 Health Score — 규칙 기반, **순수 함수**(DB, 외부 호출 없음).

## 왜 점수만 주면 안 되는가

"이 프로젝트 47점" 은 아무에게도 행동을 알려 주지 않는다. 47점을 본 팀장이 할 수 있는 일이
없기 때문이다. 그래서 이 모듈은 점수와 **이유 목록**을 함께 낸다: 어떤 규칙이 몇 점을
깎았고 무엇을 보고 그렇게 판단했는지. 이유가 곧 할 일 목록이다.

## 왜 '모른다' 를 따로 담는가 (이 모듈에서 가장 중요한 계약)

마일스톤이 하나도 없는 프로젝트는 '일정을 잘 지키는 프로젝트' 가 **아니다.** 모르는 것이다.
그런데 규칙을 조용히 건너뛰고 감점만 안 하면 결과는 만점이고, 화면에는 가장 정보가 없는
프로젝트가 가장 건강한 프로젝트로 뜬다. 그럴듯해서 아무도 신고하지 않는다.

그래서 세 가지를 함께 돌려준다.
  * `reasons`  실제로 점수를 깎은 규칙과 그 근거
  * `checked`  판정할 수 있었던 규칙들(감점 0이어도 여기 들어간다)
  * `unknown`  판정할 수 없었던 규칙과 **왜 못 했는지**

그리고 `checked` 가 비면 `score` 는 0이 아니라 **None** 이다. `progress.py` 가 분모 0에서
None 을 돌려주는 것과 같은 규칙이다: "재 보니 나쁘다" 와 "잴 것이 없다" 는 다른 말이고,
0이나 100으로 뭉개면 화면에서 둘을 구별할 방법이 사라진다.

## 규칙을 다섯 개로 한정한 이유

**이 저장소가 실제로 들고 있는 사실로만** 만들었다. 각 규칙 옆에 그 사실이 어디서 오는지
적어 뒀다. 번아웃, 예산 소진, 리스크 등급 같은 그럴듯한 지표는 만들지 않는다 - 계산할
자료가 없는 지표는 결국 상수를 그럴듯하게 포장한 것이고, 한 번 화면에 뜨면 아무도 그게
상수인 줄 모른다.

감점은 전부 상수로 뽑아 둔다. 값의 근거는 각 상수 옆에 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.projects.models import MILESTONE_DONE
from app.projects.progress import STATUS_CANCELLED, STATUS_DONE

# 규칙 키. 화면, 스냅샷 JSON, 테스트가 같은 문자열을 쓴다.
RULE_MILESTONE_OVERDUE = "milestone_overdue"
RULE_TASK_OVERDUE = "task_overdue"
RULE_UNASSIGNED = "unassigned"
RULE_STALE = "stale"
RULE_NOTION_TROUBLE = "notion_trouble"

# 규칙 이름(한국어). 키를 그대로 화면에 보이면 사용자는 무엇을 본 것인지 알 수 없다.
RULE_LABELS: dict[str, str] = {
    RULE_MILESTONE_OVERDUE: "기한 지난 마일스톤",
    RULE_TASK_OVERDUE: "지연 작업 비율",
    RULE_UNASSIGNED: "담당자 없는 작업 비율",
    RULE_STALE: "최근 활동 없음",
    RULE_NOTION_TROUBLE: "노션 진행 상태가 차질",
}

# 규칙을 늘 이 순서로 낸다. 순서가 요청마다 흔들리면 화면이 이유 목록을 렌더할 때마다
# 줄이 뛰고, 스냅샷 JSON 을 두 주 비교할 때도 diff 가 의미를 잃는다.
RULE_ORDER: tuple[str, ...] = (
    RULE_NOTION_TROUBLE, RULE_MILESTONE_OVERDUE, RULE_TASK_OVERDUE,
    RULE_UNASSIGNED, RULE_STALE,
)

BASE_SCORE = 100

# 마일스톤 하나가 늦는 것은 분명한 신호지만, 마일스톤을 잘게 쪼개 두는 팀이 그것만으로
# 0점이 되면 나머지 네 규칙이 화면에서 아무 의미가 없어진다. 그래서 건당 감점 + 상한이다.
PENALTY_PER_OVERDUE_MILESTONE = 12
MAX_MILESTONE_PENALTY = 36

# 비율 규칙은 **비율에 비례해서** 깎는다. '지연이 하나라도 있으면 -20' 같은 계단식으로 하면
# 4건짜리 프로젝트와 400건짜리 프로젝트가 같은 벌을 받는다 - 그 점수는 팀 규모만 말한다.
MAX_TASK_OVERDUE_PENALTY = 40
MAX_UNASSIGNED_PENALTY = 20

# 침묵의 기준. 2주는 스프린트 한 사이클이라 "이번 사이클에 아무 일도 없었다" 는 뜻이고,
# 4주는 그것이 두 번 반복됐다는 뜻이다.
STALE_DAYS = 14
VERY_STALE_DAYS = 28
PENALTY_STALE = 10
PENALTY_VERY_STALE = 20

# 노션 진행 상태 원문 중 '차질'. 앱 `status` 어휘에는 없는 값이라 따로 본다
# (models.py::Project.notion_status - 억지로 맞추면 가장 봐야 할 상태가 뭉개진다).
NOTION_STATUS_TROUBLE = "차질"
PENALTY_NOTION_TROUBLE = 25

# 열린 작업 = 완료도 취소도 아닌 것. 취소를 '안 끝난 일' 로 세면 취소할수록 점수가 나빠져
# 지표가 팀에게 반대로 행동하라고 말한다(progress.py 가 같은 판단을 기록한다).
CLOSED_STATUSES = frozenset({STATUS_DONE, STATUS_CANCELLED})


@dataclass(frozen=True)
class MilestoneFact:
    """마일스톤 한 건에서 규칙이 보는 것 전부. 표에서 읽지만 이 함수는 표를 모른다."""

    due_on: str | None
    status: str


@dataclass(frozen=True)
class TaskFact:
    """작업 한 건에서 규칙이 보는 것 전부.

    `assigned` 를 담당자 목록이 아니라 불리언으로 받는 이유: 이 모듈은 '누가' 를 쓰지 않고
    '있는가' 만 쓴다. 목록을 받으면 여기서 사람을 세게 되고, 그러면 미할당 판정 규칙이
    두 벌(여기와 티켓 화면)이 된다.
    """

    status: str | None
    due_on: str | None
    assigned: bool


@dataclass(frozen=True)
class HealthInput:
    """판정에 필요한 사실 전부. **여기 없는 것은 규칙이 볼 수 없다.**

    `today` 를 인자로 받는 이유: 안에서 `date.today()` 를 부르면 순수 함수가 아니게 되고,
    무엇보다 테스트가 오늘 날짜에 따라 다르게 실패한다(그런 테스트는 곧 무시된다).

    `last_activity_on` 은 이 프로젝트에 걸린 작업들이 마지막으로 움직인 날이다. 없으면
    None 이고, 그때 '최근 활동' 규칙은 판정하지 않는다(0으로 채우면 새 프로젝트가 전부
    방치된 프로젝트로 보인다).
    """

    today: str
    notion_status: str | None = None
    milestones: tuple[MilestoneFact, ...] = field(default_factory=tuple)
    tasks: tuple[TaskFact, ...] = field(default_factory=tuple)
    last_activity_on: str | None = None


@dataclass(frozen=True)
class HealthReason:
    """점수를 깎은 규칙 하나. `detail` 이 없으면 이유가 아니라 그냥 숫자다."""

    rule: str
    label: str
    penalty: int
    detail: str

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "label": self.label,
            "penalty": self.penalty,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HealthUnknown:
    """판정할 수 없었던 규칙과 그 이유. **감점 0과 다른 상태다**(모듈 docstring)."""

    rule: str
    label: str
    why: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "label": self.label, "why": self.why}


@dataclass(frozen=True)
class HealthResult:
    """`score` 는 판정한 규칙이 하나도 없으면 **None** 이다(0이 아니다)."""

    score: int | None
    reasons: tuple[HealthReason, ...]
    checked: tuple[str, ...]
    unknown: tuple[HealthUnknown, ...]

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "reasons": [r.as_dict() for r in self.reasons],
            "checked": list(self.checked),
            "unknown": [u.as_dict() for u in self.unknown],
        }


def _as_date(value) -> date | None:
    """ISO 'YYYY-MM-DD' 만 날짜로 인정한다.

    미러 컬럼은 빈 문자열, None, 노션의 datetime 원문('2026-08-06T05:00:00.000Z')이 섞여
    들어온다. 앞 10글자만 떼어 보는 이유는 그 datetime 원문도 날짜로는 읽을 수 있어야 하기
    때문이다. 읽을 수 없으면 **'기한 없음' 과 같이** 다룬다 - 여기서 예외를 올리면 미러 한
    줄이 이상해진 날 프로젝트 화면 전체가 500이 된다.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_open(task: TaskFact) -> bool:
    return task.status not in CLOSED_STATUSES


def _pct(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


class _Ledger:
    """규칙들이 결과를 적어 넣는 장부. 세 목록을 손으로 관리하다 빠뜨리지 않으려고 둔다."""

    def __init__(self) -> None:
        self._reasons: dict[str, HealthReason] = {}
        self._checked: set[str] = set()
        self._unknown: dict[str, HealthUnknown] = {}

    def checked(self, rule: str, penalty: int = 0, detail: str = "") -> None:
        """판정했다. 감점이 0이면 이유 목록에는 안 실리지만 `checked` 에는 남는다."""
        self._checked.add(rule)
        if penalty > 0:
            self._reasons[rule] = HealthReason(
                rule=rule, label=RULE_LABELS[rule], penalty=penalty, detail=detail,
            )

    def unknown(self, rule: str, why: str) -> None:
        self._unknown[rule] = HealthUnknown(
            rule=rule, label=RULE_LABELS[rule], why=why,
        )

    def result(self) -> HealthResult:
        reasons = tuple(self._reasons[r] for r in RULE_ORDER if r in self._reasons)
        checked = tuple(r for r in RULE_ORDER if r in self._checked)
        unknown = tuple(self._unknown[r] for r in RULE_ORDER if r in self._unknown)
        if not checked:
            # 잴 것이 하나도 없었다. 100(건강함)도 0(나쁨)도 거짓말이다.
            return HealthResult(score=None, reasons=reasons, checked=(), unknown=unknown)
        penalty = sum(r.penalty for r in reasons)
        return HealthResult(
            score=max(0, BASE_SCORE - penalty),
            reasons=reasons, checked=checked, unknown=unknown,
        )


def _rule_notion_trouble(data: HealthInput, out: _Ledger) -> None:
    """사람이 직접 찍은 신호. 다른 지표가 좋아도 이건 봐야 한다.

    출처: `projects.notion_status`(노션 프로젝트 DB 의 진행 상태 원문).
    """
    if not data.notion_status:
        out.unknown(
            RULE_NOTION_TROUBLE,
            "노션에 짝이 없는 포털 전용 프로젝트라 진행 상태를 볼 수 없습니다.",
        )
        return
    if data.notion_status == NOTION_STATUS_TROUBLE:
        out.checked(
            RULE_NOTION_TROUBLE, PENALTY_NOTION_TROUBLE,
            f"노션 진행 상태가 '{NOTION_STATUS_TROUBLE}' 로 표시돼 있습니다.",
        )
        return
    out.checked(RULE_NOTION_TROUBLE)


def _rule_milestone_overdue(data: HealthInput, out: _Ledger) -> None:
    """기한이 지났는데 아직 안 끝난 마일스톤.

    출처: `project_milestones.due_on` / `.status`.
    완료한 마일스톤은 날짜가 지났어도 지연이 아니다 - 끝난 일을 계속 세면 마일스톤을 닫을
    이유가 없어진다.
    """
    today = _as_date(data.today)
    dated = [(m, _as_date(m.due_on)) for m in data.milestones]
    dated = [(m, due) for m, due in dated if due is not None]
    if today is None or not dated:
        out.unknown(
            RULE_MILESTONE_OVERDUE,
            "기한이 적힌 마일스톤이 없어 일정 준수 여부를 판정할 수 없습니다.",
        )
        return
    overdue = [m for m, due in dated if due < today and m.status != MILESTONE_DONE]
    penalty = min(len(overdue) * PENALTY_PER_OVERDUE_MILESTONE, MAX_MILESTONE_PENALTY)
    out.checked(
        RULE_MILESTONE_OVERDUE, penalty,
        f"기한이 적힌 마일스톤 {len(dated)}건 중 {len(overdue)}건이 기한을 넘겼습니다.",
    )


def _rule_task_overdue(data: HealthInput, out: _Ledger) -> None:
    """마감이 지난 열린 작업의 **비율**.

    출처: `ticket_cache.due_date` / `.status`.
    분모는 '기한이 적힌 열린 작업' 이다. 기한이 없는 작업까지 분모에 넣으면 기한을 안 적는
    팀일수록 점수가 좋아진다 - 지표가 기록을 안 하도록 부추기는 셈이다.
    """
    today = _as_date(data.today)
    open_tasks = [t for t in data.tasks if _is_open(t)]
    dated = [(t, _as_date(t.due_on)) for t in open_tasks]
    dated = [(t, due) for t, due in dated if due is not None]
    if today is None or not dated:
        out.unknown(
            RULE_TASK_OVERDUE,
            "기한이 적힌 열린 작업이 없어 지연 비율을 계산할 수 없습니다.",
        )
        return
    late = [t for t, due in dated if due < today]
    ratio = len(late) / len(dated)
    penalty = round(ratio * MAX_TASK_OVERDUE_PENALTY)
    out.checked(
        RULE_TASK_OVERDUE, penalty,
        f"기한이 적힌 열린 작업 {len(dated)}건 중 {len(late)}건이 마감을 넘겼습니다"
        f"({_pct(len(late), len(dated))}%).",
    )


def _rule_unassigned(data: HealthInput, out: _Ledger) -> None:
    """담당자가 없는 열린 작업의 **비율**.

    출처: `ticket_cache.assignee_notion_ids`(비어 있으면 미할당).
    완료, 취소한 작업은 분모에서 뺀다. 끝난 일에 담당자가 안 적힌 것은 지금 손 쓸 일이 아니고,
    분모에 남기면 프로젝트를 끝낼수록 점수가 나빠진다.
    """
    open_tasks = [t for t in data.tasks if _is_open(t)]
    if not open_tasks:
        out.unknown(
            RULE_UNASSIGNED,
            "열린 작업이 없어 담당자 배정 비율을 계산할 수 없습니다.",
        )
        return
    orphans = [t for t in open_tasks if not t.assigned]
    ratio = len(orphans) / len(open_tasks)
    penalty = round(ratio * MAX_UNASSIGNED_PENALTY)
    out.checked(
        RULE_UNASSIGNED, penalty,
        f"열린 작업 {len(open_tasks)}건 중 {len(orphans)}건에 담당자가 없습니다"
        f"({_pct(len(orphans), len(open_tasks))}%).",
    )


def _rule_stale(data: HealthInput, out: _Ledger) -> None:
    """마지막으로 작업이 움직인 날로부터 얼마나 지났는가.

    출처: `ticket_cache.notion_last_edited`(없으면 미러 행의 `updated_at`).
    프로젝트 행의 `updated_at` 을 안 쓰는 이유: 그 값은 누가 프로젝트 설명을 고쳐도 갱신돼서
    **실제 작업이 멈춘 것을 감춘다.**
    """
    today = _as_date(data.today)
    last = _as_date(data.last_activity_on)
    if today is None or last is None:
        out.unknown(
            RULE_STALE,
            "걸린 작업이 없어 마지막 활동 시각을 알 수 없습니다.",
        )
        return
    days = (today - last).days
    if days <= STALE_DAYS:
        # 미래 날짜(시계 차이, 예정일이 들어온 경우)도 여기로 온다. 음수 일수를 감점으로
        # 바꾸면 점수가 100을 넘는다.
        out.checked(RULE_STALE)
        return
    penalty = PENALTY_VERY_STALE if days > VERY_STALE_DAYS else PENALTY_STALE
    out.checked(
        RULE_STALE, penalty,
        f"마지막 작업 변경이 {days}일 전({data.last_activity_on})입니다.",
    )


# 규칙은 전부 같은 모양이다: 사실을 보고 장부에 '판정함(감점 n)' 또는 '못 함(이유)' 을 적는다.
# 새 규칙을 여기 한 줄 더하는 것 말고 다른 곳을 고칠 필요가 없어야 한다.
RULES = (
    _rule_notion_trouble,
    _rule_milestone_overdue,
    _rule_task_overdue,
    _rule_unassigned,
    _rule_stale,
)


def compute_health(data: HealthInput) -> HealthResult:
    """규칙을 전부 돌려 점수와 이유, 그리고 **못 센 것**을 낸다."""
    ledger = _Ledger()
    for rule in RULES:
        rule(data, ledger)
    return ledger.result()


# ── '차질' 판정 — 점수 계산이 아니라 **점수를 읽고 고르는** 규칙 ────────────────────
#
# 위의 `compute_health` 는 티켓과 마일스톤을 다시 세어 점수를 만든다. 아래는 이미 계산돼
# 행에 캐시된 값(`health_score`, `notion_status`)만 보고 "사람이 봐야 할 프로젝트인가" 를
# 고른다 - 값이 싸서 목록/대시보드가 프로젝트마다 부를 수 있다.
#
# 🔴 **여기 한 곳에 둔 이유.** 예전에는 이 규칙이 `app/home/work.py` 안에만 있었다. 프로젝트
# 대시보드가 같은 판정을 다시 적으면 두 화면이 같은 프로젝트를 두고 하나는 '차질', 하나는
# 아니라고 말하게 되고, 그때 사용자는 둘 다 안 믿는다(이 저장소가 범위 판정에서 네 번 겪은
# 실수의 같은 모양이다).

# 이 점수 아래면 '차질' 로 본다. 근거: 위 감점 상한이 규칙당 40(지연 작업 비율)·36(마일스톤)·
# 25(노션 차질)이다. 100 에서 40 넘게 깎였다는 것은 규칙 하나가 통째로 걸렸거나 둘 이상이
# 겹쳤다는 뜻이고, 그 정도면 사람이 봐야 한다.
TROUBLE_HEALTH_SCORE = 60

# 사용자에게 보이는 문구다. 가운뎃점과 em 대시를 쓰지 않는다(scripts/check_user_text.py).
REASON_LOW_HEALTH = "Health 점수 낮음"


def trouble_reasons(notion_status: str | None, health_score: int | None) -> list[str]:
    """이 프로젝트가 차질인 **이유 목록**. 비어 있으면 차질이 아니다.

    이유를 함께 내는 것이 이 판정의 존재 이유다. "차질 3건" 만 보여 주면 그것을 본 팀장이
    할 수 있는 일이 없다 - 이유가 곧 할 일 목록이다.

    순서는 노션 사유 먼저다. 그쪽은 사람이 직접 '차질' 이라고 적어 둔 것이라 규칙이 계산한
    점수보다 근거가 강하다.

    **`health_score is None` 은 차질이 아니다.** 아직 한 번도 안 잰 것이지 나쁜 것이 아니다.
    0 점은 재 봤더니 나쁜 것이라 걸린다. 둘을 뭉치면 한 번도 안 잰 프로젝트가 전부 빨갛게
    떠서 진짜 차질이 그 안에 묻힌다.
    """
    reasons: list[str] = []
    if (notion_status or "") == NOTION_STATUS_TROUBLE:
        reasons.append(RULE_LABELS[RULE_NOTION_TROUBLE])
    if health_score is not None and health_score < TROUBLE_HEALTH_SCORE:
        reasons.append(REASON_LOW_HEALTH)
    return reasons
