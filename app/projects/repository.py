"""프로젝트 데이터 접근 — **범위 판정이 사는 단 하나의 자리**.

## 왜 여기 한 곳인가

이 저장소는 같은 실수를 **네 번** 했다(scripts/check_scope_gates.py 가 그 목록을 들고 있다):
목록에는 범위를 걸고 **같은 모듈의 단건·쓰기에는 안 걸었다.** 승인은 큐만 좁히고 approve 는
그대로였고, 잡 큐는 목록만 좁혀 남의 범위에서 Notion 쓰기를 재실행할 수 있었다.

그래서 여기서는 **조건을 두 번 적지 않는다.** 목록·상세·수정·삭제가 전부
`scope_clause` 하나를 지난다. 단건도 `db.get(Project, id)` 로 꺼내 놓고 나중에 판정하지
않고, **조건을 조회 자체에 붙인다** — 판정을 빠뜨릴 자리가 애초에 없어야 한다
(`app/jobs/repository.py::get_in_scope` 와 같은 관용).

## 부서가 없는 프로젝트는 **조직 공통**이다 (0060 에서 바뀐 규칙)

예전에는 `dept_id IS NULL` 인 프로젝트가 `IN (...)` 에 안 걸려 부서 범위 사용자에게
통째로 사라졌고, 그것을 "부서 관리자의 화면이지 전사 화면이 아니다" 로 정당화했다.
그런데 실제로 부서를 하나 고를 수 없는 프로젝트가 있다 — 전사 인프라 개선처럼 조직 전체가
함께 쓰는 것들이다. 그런 프로젝트에 부서를 억지로 하나 붙이면 그 부서 것으로 잘못 좁혀지고,
안 붙이면 아무에게도 안 보인다.

그래서 `dept_id IS NULL` + `org_id` 있음을 **조직 공통 소유**로 읽는다
(`app/core/ownership.py::for_project`). 그 조직 사람은 부서와 무관하게 볼 수 있고,
조직조차 없는 행만 판정 불가(전역 관리자 전용)로 남는다.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.authz.visibility import (
    RESOURCE_PROJECT,
    VisibilityContext,
    effective_visibility_clause,
)
from app.projects.models import MILESTONE_PLANNED, Project, ProjectMilestone
from app.projects.progress import Task, task_from_ticket
from app.tickets.models import TicketCache
from app.tickets.query import token
from app.work import relations


def scope_clause(ctx: VisibilityContext):
    """범위 안 프로젝트를 고르는 조건. 전역이면 ``None``(= 조건 없음).

    ``None`` 규약은 `core/scope.py::scope_filter` 그대로다 — 조건을 빼먹은 코드와 '전역이라
    조건이 없는' 코드를 눈으로 구별하기 위해서다.

    **판정 자체는 여기 없다.** `app/authz/visibility.py::effective_visibility_clause` 한
    곳에 있고 이 함수는 그것을 부른다 — 티켓과 프로젝트 문서가 자기 가시성을 그 함수에서
    그대로 물려받기 때문이다. 여기서 조건을 따로 적으면 "프로젝트는 보이는데 그 티켓은
    안 보인다" 가 다시 생긴다(이 저장소가 네 번 반복한 실수의 정확한 모양).
    """
    return effective_visibility_clause(ctx, RESOURCE_PROJECT)


def apply_scope(stmt: Select, ctx: VisibilityContext) -> Select:
    clause = scope_clause(ctx)
    return stmt if clause is None else stmt.where(clause)


def get_in_scope(db: Session, project_id: str, ctx: VisibilityContext) -> Project | None:
    """단건 조회 — 범위 밖이면 **아예 안 나온다**(부르는 쪽이 404 로 만든다).

    보관(archive)된 프로젝트도 돌려준다. 보관은 범위가 아니라 상태라, 여기서 함께 가리면
    '되살리기'가 자기 자신 때문에 404 가 된다.
    """
    return db.execute(
        apply_scope(select(Project).where(Project.id == project_id), ctx)
    ).scalar_one_or_none()


def list_in_scope(
    db: Session,
    ctx: VisibilityContext,
    *,
    include_archived: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Project], int]:
    """목록. 조건은 단건과 **같은 것 하나**다(`scope_clause`).

    정렬은 전순서다: 보관되지 않은 것 먼저, 최근 갱신 순, 그래도 같으면 id. 마지막 id 가
    없으면 같은 시각에 갱신된 행들의 상대 순서를 DB 가 마음대로 정하고, 그러면 OFFSET
    페이지네이션이 같은 행을 두 번 보여 주거나 빠뜨린다(app/tickets/query.py 의 Z9 와 같다).
    """
    stmt = apply_scope(select(Project), ctx)
    if not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Project.updated_at.desc(), Project.id.asc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return list(rows), int(total)


def summary_rows_in_scope(db: Session, ctx: VisibilityContext) -> list:
    """대시보드가 집계할 **범위 안 프로젝트 전부**(보관 제외). 페이지로 자르지 않는다.

    ## 왜 `list_in_scope` 를 안 쓰는가

    그쪽은 페이지 한 장을 준다. 대시보드가 그것으로 집계하면 "총 22건인데 대시보드는 20건
    기준" 이 된다 - 숫자가 그럴듯해서 아무도 신고하지 않는 종류의 오류다. 집계는 자른 것을
    세면 안 된다.

    ## 왜 상한이 없는가

    이 저장소의 다른 훑기(`overall_weekly_report`, `record_health_snapshots`)에는 상한이
    있다. 그쪽은 **프로젝트마다 티켓 목록을 따로 읽어서**(가시성 판정을 한 곳에 두려고
    일부러 그렇게 한다) 프로젝트 수만큼 질의가 늘어난다. 여기는 한 테이블에서 작은 열
    여덟 개만 읽는 질의 **하나**라 그 함정이 없다. 상한을 두면 대신 '잘린 집계' 라는 더
    나쁜 것이 생긴다.

    조건은 목록과 **같은 것 하나**(`scope_clause`)를 지난다.

    정렬을 고정하는 이유: 차질 목록의 items 는 상한으로 자르는데, 순서가 요청마다 흔들리면
    같은 화면을 두 번 열었을 때 다른 프로젝트가 잘려 나간다.
    """
    stmt = apply_scope(
        select(
            Project.id, Project.name, Project.code, Project.status,
            Project.dept_id, Project.progress_pct, Project.health_score,
            Project.notion_status,
        ).where(Project.archived_at.is_(None)),
        ctx,
    ).order_by(Project.updated_at.desc(), Project.id.asc())
    return list(db.execute(stmt).all())


def overdue_milestones_in_scope(db: Session, ctx: VisibilityContext, *, today: str) -> list:
    """기한이 지났는데 아직 예정인 마일스톤 - **범위 안 프로젝트 전부**에서 한 질의로.

    프로젝트마다 `milestones_for_project` 를 부르면 질의가 프로젝트 수만큼 늘어난다
    (`app/home/work.py` 가 그렇게 하고, 그래서 그쪽은 상한이 있다). 대시보드는 상한 없이
    정확해야 해서 조인 한 번으로 읽는다.

    판정 조건 셋은 `app/home/work.py::_projects_and_milestones` 와 **같은 것**이다:
      * 기한이 있다 (기한 없는 마일스톤은 늦을 수가 없다)
      * 기한이 **오늘(KST)보다 이전**이다 (오늘이 기한이면 아직 자정까지 남았다)
      * 아직 `planned` 다 (완료·놓침은 이미 결론이 난 일이라 계속 빨갛게 띄우면 진짜 지연이 묻힌다)

    `due_on` 은 'YYYY-MM-DD' 문자열이라 사전순이 날짜순과 일치한다(models.py 가 날짜를
    문자열로 두는 근거와 같다). 그래서 문자열 비교로 자를 수 있다.

    보관된 프로젝트의 마일스톤은 빼는 것이 목록과 같은 규약이다 - 끝난 프로젝트의 지난
    기한이 계속 쌓이면 '지금 볼 것' 이 죽은 일로 찬다.
    """
    stmt = apply_scope(
        select(ProjectMilestone, Project.id, Project.name)
        .join(Project, ProjectMilestone.project_id == Project.id)
        .where(
            Project.archived_at.is_(None),
            ProjectMilestone.due_on.is_not(None),
            ProjectMilestone.due_on < today,
            ProjectMilestone.status == MILESTONE_PLANNED,
        ),
        ctx,
    ).order_by(
        ProjectMilestone.due_on.asc(),
        Project.name.asc(),
        ProjectMilestone.id.asc(),
    )
    return list(db.execute(stmt).all())


def ticket_rows_for_project(db: Session, project: Project) -> list[TicketCache]:
    """이 프로젝트에 걸린 작업 행들. **진행률, WBS 트리, 헬스가 전부 여기를 지난다.**

    질의를 한 곳에 두는 이유는 가시성이다. 아래 두 조건(토큰 매칭, 소프트 프룬)을 화면마다
    다시 적으면 한 곳만 고쳐지고, 증상은 "트리에는 있는데 진행률에는 없다" 가 된다. 사용자
    눈에는 숫자가 틀린 것으로 보이고 아무도 원인을 못 찾는다.

    ## 왜 `notion_missing_at IS NULL` 을 거는가

    0043 이 만든 소프트 프룬 상태다. "이번 회차 Notion 응답에서 안 보였다" 로 표시만 된
    행인데, 목록에서는 이미 빠져 있다. 진행률만 그 행을 계속 세면 **화면에 안 보이는 일이
    분모에 남아** 진행률이 이유 없이 낮게 나온다. 다음 회차에 돌아오면 표시가 지워지고
    다시 세어진다 - 그게 0043 의 설계다.

    ## 왜 Notion page id 로 프로젝트를 잇는가

    `tickets.project_ids` 는 외부 소스의 relation id 목록이다. `Project.notion_page_id`
    가 없는(포털 전용) 프로젝트는 아직 걸린 작업이 있을 수 없으므로 **빈 목록**을
    돌려준다. 여기서 '전체 티켓'으로 폴백하면 포털 전용 프로젝트가 회사의 모든 작업을
    자기 분모로 세게 된다.

    **작업 사이의 계층은 이 축이 아니다** (S6). 상하위는 `ticket_relations` 가 정본이고
    티켓 UUID 로 잇는다 — `tasks_for_project` 가 그 표를 한 번에 읽어 넘긴다.

    다중값 열은 `token()` 으로 감싸 맞춘다 - 안 감싸면 page id 접두사가 겹치는 남의
    프로젝트 티켓이 섞인다(app/tickets/query.py::filter_clauses 가 같은 함정을 기록한다).

    정렬은 `id` 로 고정한다. 트리는 형제를 다시 정렬하지만(wbs.py::_sort_key) 진행률 근거의
    표본 수와 순서까지 요청마다 흔들리면 두 화면을 비교할 수 없다.
    """
    page_id = project.notion_page_id
    if not page_id:
        return []
    rows = db.execute(
        select(TicketCache).where(
            TicketCache.project_ids.contains(token(page_id), autoescape=True),
            TicketCache.notion_missing_at.is_(None),
        ).order_by(TicketCache.id.asc())
    ).scalars().all()
    return list(rows)


def tasks_for_project(db: Session, project: Project) -> list[Task]:
    """진행률 계산의 입력. 행 고르기는 `ticket_rows_for_project` 하나가 한다.

    질의를 여기 다시 적지 않는 것이 핵심이다. 트리(`wbs.py`)와 헬스도 같은 함수를 부르므로
    가시성 규칙(토큰 매칭, 0043 소프트 프룬)이 한 곳에만 있다. 두 벌이 되면 한쪽만 고쳐지고
    같은 화면의 두 숫자가 갈라진다.
    """
    rows = ticket_rows_for_project(db, project)
    parents = relations.parent_map(db, [row.id for row in rows])
    return [task_from_ticket(row, parents.get(row.id)) for row in rows]


def milestones_for_project(db: Session, project: Project) -> list[ProjectMilestone]:
    """이 프로젝트의 마일스톤 전부. **주 창으로 여기서 자르지 않는다.**

    목록 화면, 헬스 판정, 주간 리포트가 전부 이 한 질의를 지난다. 세 벌이 되면 정렬이나
    필터가 한 곳만 고쳐지고, 증상은 "리포트에는 있는데 목록에는 없다" 가 된다.

    주간 리포트는 같은 목록을 세 가지로 나눠 쓰는데 그 셋의 **축이 다르다**: '이 주에 바뀐
    것' 은 `updated_at`(naive UTC 타임스탬프)로, '이 주가 기한' 과 '기한 넘김' 은
    `due_on`('YYYY-MM-DD' 달력일)로 자른다. 자르기를 질의로 흩어 놓으면 그중 하나가 축을
    잘못 골라도 아무도 못 알아채므로, 판정은 순수 함수(`weekly.split_milestones`)에 모은다.

    정렬은 사람이 정한 순서 먼저, 같으면 기한 빠른 순, 기한이 없으면 뒤로, **그래도 같으면
    id** 다. 마지막 id 가 전순서를 만든다 - 없으면 같은 sort_order 행들의 순서를 DB 가
    마음대로 정해 화면이 새로고침할 때마다 줄이 바뀐다(app/tickets/query.py 의 Z9 와 같다).
    """
    rows = db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == project.id)
        .order_by(
            ProjectMilestone.sort_order.asc(),
            ProjectMilestone.due_on.asc().nulls_last(),
            ProjectMilestone.id.asc(),
        )
    ).scalars().all()
    return list(rows)
