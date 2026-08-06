"""업무 대시보드의 **조립** — 새 표도, 새 범위 게이트도, 새 시간 유틸도 만들지 않는다.

`/dashboard` 는 지금까지 **운영 지표만** 있었다(잡 큐, 하트비트, 디스크). 사용자가 자기
일을 보는 자리가 없어서 "내가 지금 뭘 놓치고 있나"에 답하려면 화면 네 개를 돌아야 했다.
이 파일은 그 답을 한 번에 만든다: 차질 프로젝트 / 지연 마일스톤 / 내 미완료 /
이번 주 마감 / 최근 완료 추이.

## 이 파일이 **하지 않는** 세 가지

1. **범위를 다시 걸지 않는다.** 프로젝트는 `app/projects/repository.py::list_in_scope`
   하나를 지난다. 여기서 조건을 한 번 더 적으면 두 벌이 되고, 갈라진 쪽은 "목록에서는
   안 보이는데 대시보드에는 뜬다" 로 드러난다 — 이 저장소가 네 번 반복한 실수의 정확한
   모양이다(`scripts/check_scope_gates.py`). 마일스톤도 마찬가지로 **범위를 지난
   프로젝트 객체를 받아** `milestones.list_for_project` 로만 읽는다.

2. **진행률·헬스·마일스톤을 다시 계산하지 않는다.** 그 값들은 이미 `app/projects/` 가
   갖고 있다(`health_score`, `notion_status`, `ProjectMilestone.due_on`). 여기서는 읽어서
   고르기만 한다.

3. **주 경계와 시간대 변환을 새로 쓰지 않는다.** 주는 `app/projects/weekly.py::week_for`
   (그 함수가 다시 `app/sprints/service.py::default_sprint_window` 를 부른다), 오늘은
   `app/home/service.py::local_today` 다. 월요일 계산이 세 벌이 되는 순간 스프린트·주간
   리포트·이 화면이 서로 다른 주를 '이번 주'라고 부르고, 사용자는 셋 다 안 믿게 된다.

## '오늘'과 '이번 주'는 반드시 KST 달력일이다 (M4)

UTC 자정으로 자르면 한국 사용자에게 9시간 밀린다. KST 월요일 오전 8시에 이 화면을 여는
사람은 UTC 로는 아직 일요일이라 **지난 주**를 보게 된다 — 그 주에 한 일이 통째로 빠지고,
화면에는 그럴듯한 숫자가 남아서 아무도 신고하지 않는다. 그래서 이 파일의 모든 날짜 판정은
`local_today(settings, now)` 가 준 KST 달력일에서 출발한다.

## 없는 것을 있는 척 그리지 않는다

  * 티켓 소스를 못 읽으면 `mine` 과 `completion_trend` 는 **None** 이다(0 이 아니다).
    0 으로 그리면 "할 일이 없다" 는 거짓말이 된다.
  * `health_score` 가 NULL 인 프로젝트는 차질이 **아니다**. 아직 안 잰 것이다. 0 점과
    구별해 `unscored` 로 따로 센다(0 은 재 봤더니 나쁜 것이라 차질에 든다).
  * '최근 완료 추이' 의 완료는 **마감일 기준**이다. 소스에 상태가 완료로 바뀐 시각이
    없다(`app/projects/weekly.py` 와 `app/sprints/burndown.py` 가 같은 사정을 적어 뒀다).
    없는 이력을 최종수정 시각으로 추정해 선을 그으면 그건 추이가 아니라 창작이다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.scope import Principal
from app.home import aggregate, service as home_service
from app.projects import health as project_health
from app.projects import milestones as milestones_repo
from app.projects import repository as projects_repo
from app.projects import service as projects_service
from app.projects import weekly
from app.projects.models import MILESTONE_PLANNED
from app.users.models import User

# 추이에 그리는 주 수. 4주면 스프린트 두 사이클이라 "지난번보다 나아졌나" 에 답할 수 있고,
# 그보다 길면 이 카드가 화면의 절반을 먹는다(전체 이력은 /me/stats 가 갖고 있다).
TREND_WEEKS = 4

# 목록에 싣는 줄 수. `count` 는 언제나 진짜 총계이고 `items` 만 잘린다 — 화면이 "12건"
# 이라고 쓰면서 5줄을 그리는 어긋남이 구조적으로 안 생긴다(aggregate.bucket 과 같은 규약).
ITEM_LIMIT = aggregate.DEFAULT_ITEM_LIMIT

# 이 점수 아래면 '차질' 로 본다. 근거: `app/projects/health.py` 의 감점 상한이 규칙당
# 40(지연 작업 비율)·36(마일스톤)·25(노션 차질)이다. 100 에서 40 넘게 깎였다는 것은 규칙
# 하나가 통째로 걸렸거나 둘 이상이 겹쳤다는 뜻이고, 그 정도면 사람이 봐야 한다.
TROUBLE_HEALTH_SCORE = 60

# 차질 이유 문구. 노션 사유는 헬스 규칙의 라벨을 **그대로** 가져다 쓴다 — 같은 사실을 두
# 화면이 다른 말로 부르면 사용자는 서로 다른 문제라고 읽는다.
REASON_LOW_HEALTH = "Health 점수 낮음"
REASON_NOTION_TROUBLE = project_health.RULE_LABELS[project_health.RULE_NOTION_TROUBLE]


def recent_week_windows(today: date, *, count: int = TREND_WEEKS) -> list[weekly.Week]:
    """오늘이 속한 주로 **끝나는** 최근 `count` 주 (과거 → 현재 순).

    주 경계를 여기서 만들지 않는다. `week_for` 하나만 부르고, 뒤로 갈 때도 날짜에서 7일씩
    빼서 같은 함수에 다시 넣는다 — 직접 월요일을 계산하면 그것이 이 저장소의 **세 번째**
    주 경계 구현이 된다(`app/profiles/stats.py::_week_start` 가 이미 두 번째다).

    순서를 과거→현재로 고정하는 이유: 추이 그래프는 왼쪽이 과거여야 읽히고, 순서가 요청마다
    흔들리면 같은 화면을 두 번 열었을 때 그림이 뒤집힌다.
    """
    if count < 1:
        return []
    return [
        weekly.week_for(today - timedelta(days=weekly.DAYS_IN_WEEK * back))
        for back in range(count - 1, -1, -1)
    ]


def _trend_point(window: weekly.Week, tickets: list[dict], *, today_iso: str) -> dict:
    """추이 한 점. 세는 일은 `aggregate.sprint_progress` 가 한다 — 홈의 '이번 주 내 진척'
    카드와 **같은 함수**라 두 화면의 같은 주가 다른 숫자를 말할 수 없다.

    `assigned` / `done` 만 싣는다. 그 함수가 내는 나머지(완료율·WD 합계)는 한 점짜리
    막대에 담을 수 없고, 안 쓰는 값을 실어 보내면 화면이 그걸 그리려다 다른 기준을 섞는다.
    """
    progress = aggregate.sprint_progress(
        tickets, start=window.start, end=window.end_exclusive, today=today_iso
    )
    return {
        "week_of": window.week_of,
        "assigned": progress["assigned"],
        "done": progress["done"],
    }


def _bucket(items: list[dict]) -> dict:
    """{count, items} — count 는 진짜 총계, items 만 상한으로 자른다."""
    return {"count": len(items), "items": items[:ITEM_LIMIT]}


def _trouble_reasons(project) -> list[str]:
    """이 프로젝트가 차질인 이유. 비어 있으면 차질이 아니다.

    이유를 함께 내는 것이 이 지표의 존재 이유다. "차질 3건" 만 보여 주면 그것을 본 팀장이
    할 수 있는 일이 없다 — 이유가 곧 할 일 목록이다(`app/projects/health.py` 가 점수와
    이유를 함께 내는 것과 같은 판단).

    순서는 노션 사유 먼저다. 그쪽은 사람이 직접 '차질' 이라고 적어 둔 것이라 규칙이 계산한
    점수보다 근거가 강하다.
    """
    reasons: list[str] = []
    if (project.notion_status or "") == project_health.NOTION_STATUS_TROUBLE:
        reasons.append(REASON_NOTION_TROUBLE)
    # NULL 은 '아직 안 쟀다' 라 여기 걸리면 안 된다. 0 은 '재 봤더니 나쁘다' 라 걸려야 한다.
    if project.health_score is not None and project.health_score < TROUBLE_HEALTH_SCORE:
        reasons.append(REASON_LOW_HEALTH)
    return reasons


def _project_row(project, reasons: list[str]) -> dict:
    """차질 목록 한 줄. `progress_pct` 와 `health_score` 는 **null 을 그대로** 낸다.

    0 으로 채워 보내면 화면이 "아직 계산 안 함" 과 "0%" 를 구별할 방법이 없다
    (`app/projects/router.py::_project_view` 와 같은 규약, frontend/src/screens/
    project-format.js 가 그 두 상태에 서로 다른 문구를 준다).
    """
    return {
        "project_id": project.id,
        "name": project.name,
        "code": project.code,
        "status": project.status,
        "health_score": project.health_score,
        "progress_pct": project.progress_pct,
        "notion_status": project.notion_status,
        "reasons": reasons,
    }


def _milestone_row(project, milestone) -> dict:
    """지연 마일스톤 한 줄. 프로젝트 이름을 함께 싣는다 — 마일스톤 이름만으로는
    ('1차 오픈') 어느 프로젝트 것인지 알 수 없고, 화면이 다시 물어보면 요청이 N 번이 된다."""
    return {
        "id": milestone.id,
        "project_id": project.id,
        "project_name": project.name,
        "name": milestone.name,
        "due_on": milestone.due_on,
        "status": milestone.status,
    }


def _projects_and_milestones(db: Session, principal: Principal, *, today_iso: str) -> tuple[dict, dict]:
    """범위 안 프로젝트에서 차질 목록과 지연 마일스톤을 뽑는다.

    상한은 전체 주간 리포트와 **같은 값**(`OVERALL_PROJECT_LIMIT`)을 쓴다. 프로젝트마다
    마일스톤을 따로 읽으므로(가시성 판정이 한 곳이어야 해서 일부러 그렇게 한다) 무제한으로
    두면 이 화면 하나가 DB 를 오래 잡는다. 잘렸다는 사실은 `truncated` 로 말한다 — 조용히
    자르면 "차질 0건" 이 사실인지 잘린 결과인지 아무도 모른다.
    """
    rows, total = projects_repo.list_in_scope(
        db, principal.scope, include_archived=False,
        offset=0, limit=projects_service.OVERALL_PROJECT_LIMIT,
    )
    troubled: list[dict] = []
    unscored = 0
    overdue: list[dict] = []
    for project in rows:
        if project.health_score is None:
            unscored += 1
        reasons = _trouble_reasons(project)
        if reasons:
            troubled.append(_project_row(project, reasons))
        for milestone in milestones_repo.list_for_project(db, project):
            # 지연 = 기한이 **오늘(KST)보다 이전**인데 아직 예정 상태. 기한이 오늘이면 아직
            # 늦은 것이 아니다(오늘 자정까지 남아 있다). 완료·놓침 처리된 것은 지연이 아니다
            # — 이미 결론이 난 일을 계속 빨갛게 띄우면 진짜 지연이 묻힌다.
            if milestone.due_on and milestone.due_on < today_iso \
                    and milestone.status == MILESTONE_PLANNED:
                overdue.append(_milestone_row(project, milestone))

    # 순서를 고정한다. 나쁜 것이 위로 오되(점수 낮은 순), 같은 점수면 이름순이라 같은 화면을
    # 두 번 열어도 줄이 뛰지 않는다. 점수가 없는 차질(노션 사유만)은 뒤로 보낸다.
    troubled.sort(key=lambda p: (
        p["health_score"] if p["health_score"] is not None else TROUBLE_HEALTH_SCORE + 1,
        p["name"],
    ))
    overdue.sort(key=lambda m: (m["due_on"], m["project_name"], m["name"]))
    return (
        {
            "in_scope": len(rows),
            # '못 잼' 을 0 으로 뭉개지 않는다. 차질 0건이 "다 건강하다" 인지 "아무것도 안
            # 쟀다" 인지는 완전히 다른 사실이고, 화면이 그 둘을 구별해 말해야 한다.
            "unscored": unscored,
            "truncated": total > len(rows),
            "troubled": _bucket(troubled),
        },
        {"overdue": _bucket(overdue)},
    )


def build_work_dashboard(
    db: Session, outbound, settings, user: User, principal: Principal, *,
    repo, now: datetime,
) -> dict:
    """업무 대시보드 한 화면에 필요한 모든 숫자. 문장(LLM)은 여기 없다.

    장애 격리(§17.4): 티켓 소스가 죽어도 프로젝트·마일스톤은 그대로 나온다. 다른 소스가
    죽었다고 함께 사라지면 사용자는 화면 전체가 고장 난 줄 안다.
    """
    today = home_service.local_today(settings, now)
    today_iso = today.isoformat()
    week = weekly.week_for(today)

    state = home_service.load_my_tickets(db, outbound, settings, user, repo=repo)
    tickets = state["tickets"]
    # 미러가 비어 있거나 매핑이 없으면 **모른다**. 0 으로 그리지 않는다(홈 '오늘'의
    # sprint 블록이 같은 판단을 한다 — 두 화면이 같은 상황에서 다른 말을 하면 안 된다).
    usable = state["ok"] and state["mapped"]

    mine = None
    trend = None
    if usable:
        buckets = aggregate.bucket_my_tickets(tickets, today=today_iso, limit=ITEM_LIMIT)
        this_week = aggregate.sprint_progress(
            tickets, start=week.start, end=week.end_exclusive, today=today_iso
        )
        mine = {
            # 활성(완료·취소 아님) 전체. 홈의 '진행 중' 카드와 **같은 함수**가 센 값이다.
            "open": buckets["in_progress"]["count"],
            "overdue": buckets["overdue"]["count"],
            # 이번 주 창 안에 마감이 있는 내 티켓(상태 무관) — 창 판정은 마감일 기준이다.
            "due_this_week": this_week["assigned"],
            "done_this_week": this_week["done"],
        }
        trend = [
            _trend_point(window, tickets, today_iso=today_iso)
            for window in recent_week_windows(today, count=TREND_WEEKS)
        ]

    projects, milestones = _projects_and_milestones(db, principal, today_iso=today_iso)
    return {
        "ok": True,
        "today": today_iso,
        # 창을 응답에 싣는다. 화면이 직접 계산하면 주 경계가 또 한 벌 생기고, 무엇보다
        # 사용자가 '이번 주'가 어느 주인지 확인할 방법이 없어진다.
        "window": {"start": week.start, "end_exclusive": week.end_exclusive},
        "tickets": {k: v for k, v in state.items() if k != "tickets"},
        "mine": mine,
        "completion_trend": trend,
        "projects": projects,
        "milestones": milestones,
    }
