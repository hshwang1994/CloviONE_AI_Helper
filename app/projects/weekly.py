"""프로젝트 주간 리포트의 **순수 계산** — DB·네트워크·LLM 을 모른다.

진행률(`progress.py`)과 같은 층 구조다: 여기서는 (입력 → 출력)만 하고, 표를 읽는 일은
`repository.py`, 조립과 시간대 변환은 `service.py` 가 한다. 그렇게 나눠 두면 이 파일의
값은 서버 없이 고정되고, 반대로 화면 숫자가 틀렸을 때 "계산이 틀렸나 표본이 틀렸나"를
갈라서 물어볼 수 있다.

## 주 경계를 여기서 만들지 않는다

`app/sprints/service.py::default_sprint_window` 를 그대로 부른다. 스프린트 회의 화면과
주간 리포트가 서로 다른 주를 '이번 주'라고 부르면 사용자는 둘 중 하나를 거짓말로
받아들이고, 그 다음부터는 둘 다 안 본다. 월요일 계산이 두 벌이 되는 순간 그 상태가
시작되므로, 한 벌만 둔다.

## 시간대: KST 달력일과 UTC 타임스탬프는 **다른 축**이다

이 파일에 들어오는 값은 두 종류다.

  * 마감일(`due_date`) / 마일스톤 기한(`due_on`) — **달력일**이다. 표에서는 `date` 이고
    (S7 · P-14a) 이 파일에 들어올 때 'YYYY-MM-DD' 문자열로 옮겨진다 — 시각이 아니라
    날짜라 창(KST 달력일)과 같은 축이고, 그래서 문자열 그대로 비교해도 맞는다.
  * 마일스톤 갱신 시각(`updated_at`) — DB 에 **naive UTC** 로 저장된 타임스탬프다.
    창과 축이 다르므로 반드시 UTC 경계로 바꿔서 넣어야 한다. 그 변환은 이 파일이 하지
    않고(설정이 필요하다) `service.py` 가 `home.service.window_utc_bounds` 한 곳에서 한다.

이 구별을 놓치면 KST 는 UTC+9 라 **월요일 오전 9시 이전의 일이 UTC 로는 아직 일요일**
이어서 그 주에서 통째로 빠진다. 실제로 주간 다이제스트가 그 상태다
(`app/home/readers.py::documents_changed_since` 는 KST 날짜를 Notion 이 준 UTC 문자열과
그대로 비교한다 — 알려진 결함 M4). 여기서는 되풀이하지 않는다.

## 완료 시각이 없다는 사실을 숨기지 않는다

'이번 주에 완료'를 정확히 말하려면 상태가 완료로 바뀐 시각이 있어야 하는데 소스에 없다
(`app/sprints/burndown.py` 가 같은 사정을 기록한다). 그래서 여기서 말하는 '이번 주 완료'는
**이번 주 마감이면서 지금 완료 상태인 것**이다. 없는 이력을 최종수정 시각으로 추정해
그리면 그건 리포트가 아니라 창작이다. 문장에도 그 기준을 그대로 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.dates import iso_date
from app.projects.models import MILESTONE_DONE, MILESTONE_MISSED, MILESTONE_PLANNED
from app.sprints.service import default_sprint_window

# 상태 어휘는 app/home/aggregate.py, app/projects/progress.py 와 **같은 문자열**이다.
# 새로 정의하면 Notion 의 상태 이름이 바뀔 때 고칠 자리가 하나 더 늘어난다.
STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"
STATUS_BLOCKED = "이슈"
TERMINAL = frozenset({STATUS_DONE, STATUS_CANCELLED})

# 응답에 싣는 항목 수 상한. `count` 는 언제나 진짜 총계이고 `items` 만 잘린다 - 화면이
# "12건" 이라고 쓰면서 5줄을 그리는 어긋남이 구조적으로 안 생긴다(aggregate.bucket 과 같은 규약).
ITEM_LIMIT = 50

# 문장에 나열하는 줄 수. 리포트는 회의에서 읽는 것이라 한 칸이 스무 줄이면 아무도 안 읽는다.
SUMMARY_LINES = 5

DAYS_IN_WEEK = 7


@dataclass(frozen=True)
class Week:
    """리포트가 다루는 한 주. 전부 KST 달력일 문자열이다.

    `prev_week` / `next_week` 를 응답에 함께 싣는 이유: 이동을 화면이 직접 계산하면 주
    경계 계산이 또 한 벌 생긴다(연말·서머타임이 아니라 그냥 '두 벌'이 문제다). 서버가
    같은 함수로 만든 값을 주면 화면은 그것을 그대로 다시 보내기만 하면 된다.
    """

    week_of: str
    start: str
    end_exclusive: str
    next_end_exclusive: str
    prev_week: str
    next_week: str

    def as_dict(self) -> dict:
        return {
            "week_of": self.week_of,
            "start": self.start,
            "end_exclusive": self.end_exclusive,
            "prev_week": self.prev_week,
            "next_week": self.next_week,
        }

    @property
    def last_day(self) -> str:
        """창에 **포함되는** 마지막 날. 문장에만 쓴다.

        계약(`end_exclusive`)은 배타적 끝이 맞다. 하지만 사람에게 "08-03 ~ 08-10" 이라고
        보이면 08-10 이 포함인지 아닌지를 매번 다시 생각해야 하고, 반쯤은 틀리게 읽는다.
        """
        return (date.fromisoformat(self.end_exclusive) - timedelta(days=1)).isoformat()


def week_for(day: date) -> Week:
    """그 날짜가 속한 주. **스프린트와 같은 함수**로 월요일을 정한다."""
    start, end = default_sprint_window(day)
    prev_start, _ = default_sprint_window(day - timedelta(days=DAYS_IN_WEEK))
    next_start, next_end = default_sprint_window(day + timedelta(days=DAYS_IN_WEEK))
    return Week(
        week_of=start,
        start=start,
        end_exclusive=end,
        next_end_exclusive=next_end,
        prev_week=prev_start,
        next_week=next_start,
    )


def resolve_week(value: str | None, *, today: date) -> Week:
    """`week` 파라미터('YYYY-MM-DD', 주 중 아무 날) → 그 주. 없거나 이상하면 이번 주.

    주 중간 날짜를 그 주 월요일로 정규화하는 것은 스프린트 화면의 `week` 규약과 같다
    (`frontend/src/screens/Sprint.jsx::weekMonday`). 이상한 값에 400 을 내지 않는 이유도
    같다 - 주소를 손으로 고친 사람에게 오류 화면을 주는 것보다 이번 주를 보여 주는 편이
    낫고, 응답의 `window` 가 실제로 어느 주인지를 말해 준다.
    """
    if value:
        try:
            return week_for(date.fromisoformat(value))
        except ValueError:
            pass
    return week_for(today)


@dataclass(frozen=True)
class Item:
    """리포트 한 줄. `id` 는 앱 티켓 uid 라 화면이 /tickets/:id 로 딥링크할 수 있다.

    raw Notion id 는 싣지 않는다(§12.3). `tid` 는 옛 소스가 매긴 번호이고 **이름이
    아니다** — 화면과 요약이 부르는 이름은 `key`(`<CODE>-<SEQ>`)다 (D-282).
    """

    id: str
    tid: int | None
    key: str | None
    title: str
    status: str | None
    due: str | None
    est_wd: float | None

    def as_dict(self) -> dict:
        return {
            "id": self.id, "tid": self.tid, "key": self.key, "title": self.title,
            "status": self.status, "due": self.due, "est_wd": self.est_wd,
        }


def item_from_ticket(row) -> Item:
    """`ticket_cache` 행 하나를 리포트 한 줄로. 이 파일이 DB 컬럼 이름을 아는 유일한 자리다."""
    return Item(
        id=row.id,
        tid=row.notion_ticket_number,
        key=row.canonical_key,
        title=row.title or "",
        status=row.status,
        due=iso_date(row.due_date),
        est_wd=row.est_wd,
    )


@dataclass(frozen=True)
class MilestoneItem:
    """마일스톤 한 줄. `updated_at` 은 저장 그대로의 naive UTC ISO 다.

    KST 로 바꾸는 일은 화면이 한다(다른 API 응답과 같은 규약 - `_project_view` 도
    `updated_at` 을 그대로 낸다). 여기서 미리 바꿔 내보내면 한 응답 안에 두 시간대가
    섞여서, 나중에 어느 필드가 무슨 축인지 아무도 확신하지 못한다.
    """

    id: str
    name: str
    due_on: str | None
    status: str
    updated_at: str

    def as_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "due_on": self.due_on,
            "status": self.status, "updated_at": self.updated_at,
        }


def milestone_from_row(row) -> MilestoneItem:
    return MilestoneItem(
        id=row.id,
        name=row.name,
        # DTO 는 'YYYY-MM-DD' 문자열 계약이다 — 아래 정렬 키와 창 비교가 그 규약에
        # 기대고 있고, 그 둘은 창(`week.start`)도 문자열이라 축이 맞는다 (S7 · P-14a).
        due_on=iso_date(row.due_on),
        status=row.status,
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def _bucket(items: list[Item] | list[MilestoneItem]) -> dict:
    """{count, items} — count 는 진짜 총계, items 만 상한으로 자른다."""
    return {
        "count": len(items),
        "items": [i.as_dict() for i in items[:ITEM_LIMIT]],
    }


def _is_active(status: str | None) -> bool:
    return (status or "") not in TERMINAL


def _by_due(items: list[Item]) -> list[Item]:
    """마감 빠른 순, 같은 날이면 번호순. 순서를 고정하지 않으면 같은 주 리포트를 두 번
    만들었을 때 문장이 달라지고, 그러면 저장본 비교가 의미를 잃는다."""
    return sorted(items, key=lambda i: (i.due or "9999-99-99", i.tid or 0))


def build_sections(items: list[Item], week: Week) -> dict:
    """이번 주 완료 / 진행 중 / 지연 / 이슈 / 다음 주 계획.

    창 판정은 **마감일** 기준이다 - 리포트·스프린트·홈이 전부 같은 규칙을 쓴다
    (`app/home/aggregate.py::sprint_progress`). 같은 화면에서 두 숫자가 다른 기준을 쓰면
    사용자는 어느 쪽을 믿어야 할지 알 수 없다.

    칸은 **배타적이지 않다**: '이슈'는 대부분 '진행 중'에도 들어간다. 배타적으로 만들면
    이슈로 표시한 순간 진행 중 목록에서 사라져 개수가 안 맞는 것처럼 보인다
    (aggregate.bucket_my_tickets 가 같은 판단을 기록한다).

    취소는 어느 칸에도 안 들어간다. 진행률이 취소를 분자·분모에서 함께 빼는 것과 같은
    이유다 - 취소한 일은 하기로 한 적 없는 일로 다룬다(`progress.py`).
    """
    in_week = [i for i in items if i.due and week.start <= i.due < week.end_exclusive]
    next_week = [
        i for i in items
        if i.due and week.end_exclusive <= i.due < week.next_end_exclusive
        and (i.status or "") != STATUS_CANCELLED
    ]
    return {
        "done": _bucket(_by_due([i for i in in_week if (i.status or "") == STATUS_DONE])),
        "in_progress": _bucket(_by_due([i for i in in_week if _is_active(i.status)])),
        # 지연 = 창이 시작하기 전에 마감이었는데 아직 안 끝난 것. 마감이 없으면 지연이 아니다.
        "delayed": _bucket(_by_due([
            i for i in items if i.due and i.due < week.start and _is_active(i.status)
        ])),
        # 이슈는 마감과 무관하게 본다 - 막혀 있는 일은 마감이 언제든 이번 주에 말해야 한다.
        "issues": _bucket(_by_due([
            i for i in items
            if (i.status or "") == STATUS_BLOCKED and _is_active(i.status)
        ])),
        "next_week": _bucket(_by_due(next_week)),
    }


def _milestone_key(item: MilestoneItem) -> tuple[str, str]:
    """기한 빠른 순, 기한 없으면 뒤, 같으면 이름순. 순서를 고정해야 같은 주를 두 번 만들어도
    같은 문장이 나온다(저장본을 비교할 수 있어야 한다)."""
    return (item.due_on or "9999-99-99", item.name)


def split_milestones(
    rows, *, week: Week, since_utc: datetime, until_utc: datetime
) -> dict:
    """마일스톤을 '이번 주 변화 / 이번 주 기한 / 기한 넘김'으로 나눈다.

    `since_utc` / `until_utc` 는 **KST 달력일 창을 UTC 로 옮긴** 경계다(모듈 docstring).
    `updated_at` 은 naive UTC 라 이 경계와만 비교할 수 있다 - 창 문자열(`week.start`)과
    직접 비교하면 KST 월요일 오전에 고친 것이 통째로 빠진다.

    반대로 기한(`due_on`)은 달력일이라 창 문자열과 그대로 비교한다. 한 함수 안에서 두
    비교가 다른 축을 쓰는 것이 정상이고, 그것이 이 주석의 존재 이유다.

    '변화'의 근거는 `updated_at` 하나뿐이다. 무엇이 어떻게 바뀌었는지(이전 값)는 어디에도
    기록돼 있지 않으므로 지어내지 않고 현재 상태만 함께 싣는다.
    """
    # 행과 변환값을 짝지어 들고 다닌다. `updated_at` 비교는 **문자열이 아니라 datetime** 으로
    # 해야 해서(문자열로 하면 자릿수가 다른 ISO 표기끼리 사전순이 시간순과 어긋난다) 원본
    # 행을 함께 본다.
    paired = [(row, milestone_from_row(row)) for row in rows]
    changed = [
        item for row, item in paired
        if row.updated_at is not None and since_utc <= row.updated_at < until_utc
    ]
    due_this_week = [
        item for _row, item in paired
        if item.due_on and week.start <= item.due_on < week.end_exclusive
    ]
    overdue = [
        item for _row, item in paired
        if item.due_on and item.due_on < week.start and item.status == MILESTONE_PLANNED
    ]
    return {
        "changed": _bucket(sorted(changed, key=_milestone_key)),
        "due_this_week": _bucket(sorted(due_this_week, key=_milestone_key)),
        "overdue": _bucket(sorted(overdue, key=_milestone_key)),
    }


# ── 문장(규칙 기반). LLM 은 아직 붙이지 않는다 ─────────────────────────────────

# 사용자에게 보이는 문구다. 가운뎃점과 em 대시를 쓰지 않는다(scripts/check_user_text.py).
SECTION_TITLES = (
    ("done", "이번 주 완료"),
    ("in_progress", "진행 중"),
    ("delayed", "지연"),
    ("issues", "이슈"),
    ("next_week", "다음 주 계획"),
)

# 마일스톤 상태의 한국어 이름. 계약(`status`)은 영어 열거값 그대로 나가고 **문장에서만**
# 바꾼다 - 문장에 'planned' 라고 적히면 읽는 사람은 그것이 무슨 뜻인지 알 수 없고,
# 반대로 계약을 한국어로 바꾸면 화면 코드가 표시용 문자열로 분기하게 된다.
MILESTONE_STATUS_LABELS: dict[str, str] = {
    MILESTONE_PLANNED: "예정",
    MILESTONE_DONE: "완료",
    MILESTONE_MISSED: "놓침",
}

# 문구에 「노션」이 없다. 이 서버가 티켓의 정본이라 「저쪽 작업과 연결되어 있지 않다」는
# 상태가 없어졌고, 없는 외부 시스템의 이름을 대면 사용자는 고칠 수 없는 곳을 쳐다보게 된다.
NO_LINK_NOTE = (
    "이 프로젝트에 걸린 작업이 없어 작업 기준 집계를 낼 수 없습니다."
)
RULE_NOTE = (
    "이 요약은 규칙으로 만들었습니다. 완료 여부는 마감일이 이 주에 있는 작업의 현재 "
    "상태로 판단합니다(상태가 바뀐 시각은 소스에 없습니다)."
)


def _line(item: dict) -> str:
    head = item.get("key") or "이름 없음"
    due = item.get("due") or "기한 없음"
    return f"- [{head}] {item['title']} ({item.get('status') or '상태 없음'}, 마감 {due})"


def _section_md(title: str, bucket: dict) -> list[str]:
    lines = [f"### {title} ({bucket['count']}건)"]
    if not bucket["count"]:
        lines.append("없음")
        return lines
    lines.extend(_line(i) for i in bucket["items"][:SUMMARY_LINES])
    hidden = bucket["count"] - min(len(bucket["items"]), SUMMARY_LINES)
    if hidden > 0:
        lines.append(f"그 밖에 {hidden}건")
    return lines


def render_summary_md(
    *, project_name: str, week: Week, sections: dict, milestones: dict,
    tickets_linked: bool,
) -> str:
    """규칙이 쓴 주간 요약(마크다운).

    문장이 스스로 기준을 말한다. 리포트를 몇 주 뒤에 다시 읽는 사람은 그때의 판정 규칙을
    기억하지 못하고, 기준을 모르는 숫자는 결국 안 믿게 된다.
    """
    out = [
        f"## {project_name} 주간 리포트",
        f"기간: {week.start} ~ {week.last_day} (마감일 기준, Asia/Seoul)",
        "",
    ]
    if not tickets_linked:
        out.extend([NO_LINK_NOTE, ""])
    for key, title in SECTION_TITLES:
        out.extend(_section_md(title, sections[key]))
        out.append("")

    changed = milestones["changed"]
    out.append(f"### 마일스톤 변화 ({changed['count']}건)")
    if not changed["count"]:
        out.append("이 주에 바뀐 마일스톤이 없습니다.")
    else:
        out.extend(
            f"- {m['name']} (기한 {m['due_on'] or '없음'}, 현재 "
            f"{MILESTONE_STATUS_LABELS.get(m['status'], m['status'])})"
            for m in changed["items"][:SUMMARY_LINES]
        )
    out.extend(["", RULE_NOTE])
    return "\n".join(out)
