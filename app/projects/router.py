"""프로젝트 API. **범위 밖은 전부 404** 이고, 그 판정은 함수 하나를 지난다.

목록은 `repository.apply_scope`, id 를 받는 경로는 전부 `service.get_scoped_project_or_404`
를 지난다. 그 둘은 `repository.scope_clause` **하나**에서 갈라지므로 목록에서 가린 것이
id 로 열리는 상태가 생길 자리가 없다(이 저장소가 네 번 반복한 실수 -
`scripts/check_scope_gates.py`).

읽기는 인증만, 쓰기는 운영자군이다. 프로젝트의 목표·일정·부서를 바꾸는 것은 팀의 계획을
바꾸는 일이라 개인 작업물 편집과 성격이 다르다. 다만 **역할이 범위를 대신하지는 않는다** -
운영자여도 범위 밖은 404 다(권한과 범위는 직교한다, `app/core/scope.py`).

이 파일은 API 뿐이다 - 화면은 `frontend/src/screens/Projects.jsx`,
`Project.jsx`, `ProjectWeekly.jsx` 에 있다(둘 다 이미 구현됨). 프로젝트의 정본은 이제
이 서버의 데이터베이스이므로 밖으로 내보내거나 밖에서 당겨오는 경로가 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.dates import iso_date
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES
from app.authz.visibility import visibility_context
from app.core.deps import get_current_user, get_db, get_principal, require_csrf, require_roles
from app.core.pagination import PageParams
from app.core.scope import Principal
from app.org import context as org_context
from app.projects import milestones as milestones_repo
from app.projects import repository, service, weekly
from app.projects.models import Project, ProjectHealthSnapshot, ProjectMilestone
from app.projects.schemas import (
    MilestoneCreate,
    MilestoneUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.settings.gate import block_if_maintenance
from app.users.models import User

router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    dependencies=[
        Depends(get_current_user),
        Depends(require_csrf),
        Depends(block_if_maintenance),
    ],
)

# 쓰기 역할 게이트. 별도 Depends 로 두는 이유: 라우터 전체에 걸면 읽기까지 운영자군만
# 보게 되는데, 프로젝트 현황은 참여자 전원이 봐야 하는 화면이다.
require_write = Depends(require_roles(*CONSOLE_OPS_ROLES))


def _scope_snapshot(project: Project) -> dict:
    """이 프로젝트가 **누구 것인가**. 감사 before/after 전용 (0060 §34)."""
    return {"dept_id": project.dept_id, "org_id": project.org_id}


def _project_view(project: Project) -> dict:
    """목록·상세 공통 조각.

    `progress_pct` 는 **캐시된 계산 결과**이고 NULL 일 수 있다 - 아직 한 번도 계산 안 했다는
    뜻이지 0% 가 아니다. 화면이 둘을 구별해 말할 수 있도록 null 을 그대로 내보낸다
    (0 으로 채워 보내면 화면은 구별할 방법이 없다).
    """
    return {
        "id": project.id,
        "name": project.name,
        "code": project.code,
        "status": project.status,
        "dept_id": project.dept_id,
        "owner_user_id": project.owner_user_id,
        # 화면 계약은 'YYYY-MM-DD' 문자열이다. 컬럼은 `date` 다 (S7 · P-14a) —
        # FastAPI 도 같은 글자를 내지만, 이 파일의 다른 시각 필드가 이미 명시적으로
        # 옮기고 있어(`created_at.isoformat()`) 같은 규약을 쓴다.
        "starts_on": iso_date(project.starts_on),
        "ends_on": iso_date(project.ends_on),
        "goal": project.goal,
        "biz_type": project.biz_type,
        "product": project.product,
        "progress_pct": project.progress_pct,
        "health_score": project.health_score,
        "archived_at": project.archived_at.isoformat() if project.archived_at else None,
        # ── 이관 흔적 여섯은 여기 없다 ────────────────────────────────────────
        #
        # `notion_page_id`·`notion_progress_pct`·`notion_status`·`notion_missing_at`·
        # `notion_synced_at`·`notion_sync_error` 가 있었다. 전부 「저쪽이 말한 사실」이고,
        # 저쪽을 읽고 쓰는 코드가 없어져 값이 이관 시점에 얼어붙었다. 얼어붙은 값을 계속
        # 실어 보내면 화면은 「이관 때 원본 없음」·「이관할 때 문제가 있었습니다」를
        # 영원히 띄우고, 사용자가 무엇을 고쳐도 사라지지 않는다. 컬럼 자체는 이관 흔적으로
        # 남겨 둔다(내리는 것은 이 작업의 범위가 아니다).
        # 편집 시작 시점의 판. 저장할 때 `base_version` 으로 그대로 돌려보내면 그 사이
        # 누가 먼저 저장한 경우 409 로 막힌다 — 안 보내면 예전처럼 덮어쓴다.
        # 티켓·문서와 **같은 이름의 같은 규약**이다 (S6).
        "version": project.version,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


@router.get("")
def list_projects(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    include_archived: bool = Query(default=False),
    # 부서 필터 (0060 §32) — 조회 범위 **안에서만** 좁힌다. 넓히지 못한다.
    department_id: str | None = Query(default=None, max_length=36),
    sort: str | None = Query(default=None, max_length=32),
    order: str | None = Query(default=None, pattern="^(asc|desc)$"),
    principal: Principal = Depends(get_principal),
    user: User = Depends(get_current_user),
):
    """범위 안 프로젝트만. 조건은 단건·수정·삭제와 **같은 것 하나**다."""
    picked = org_context.filter_scope(db, user, department_id)
    rows, total = repository.list_in_scope(
        db,
        visibility_context(db, principal, scope=picked),
        include_archived=include_archived,
        offset=page.offset,
        limit=page.page_size,
        sort=sort,
        order=order,
    )
    return {
        "items": [_project_view(p) for p in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "departments": {
            "selected": department_id,
            "options": org_context.department_options(db, user),
        },
    }


@router.post("")
def create_project(
    request: Request,
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    project = service.create_project(
        db, payload, principal, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="project.create", object_type="project", object_id=project.id,
    )
    return {"project": _project_view(project)}


def _week_from(request: Request, week: str | None) -> weekly.Week:
    """`week` 파라미터 → 그 주. 없으면 **Asia/Seoul 기준 오늘**이 속한 주.

    오늘을 UTC 로 판정하면 KST 09:00 이전에 날짜가 하루 밀려, 월요일 아침에 여는 사람이
    지난 주 리포트를 본다(§불변 9, `app/home/service.py::local_today` 와 같은 판단).
    """
    from app.home.service import local_today

    settings = request.app.state.settings
    today = local_today(settings, request.app.state.clock.now())
    return weekly.resolve_week(week, today=today)


# ⚠️ **이 라우트는 `/{project_id}` 보다 먼저 선언돼야 한다.** FastAPI 는 선언 순서로
# 매칭하므로 뒤에 두면 `weekly-report` 가 프로젝트 id 로 잡혀 404(그것도 "프로젝트를 찾을
# 수 없습니다")가 된다 - 원인이 라우팅인데 증상은 "그 프로젝트가 없다"로 보인다.
@router.get("/weekly-report")
def overall_weekly_report(
    request: Request,
    db: Session = Depends(get_db),
    week: str | None = Query(default=None, max_length=10),
    principal: Principal = Depends(get_principal),
):
    """전체 주간 리포트. **목록과 같은 범위 판정**(`repository.list_in_scope`)을 지난다."""
    return service.overall_weekly_report(
        db, principal,
        week=_week_from(request, week),
        settings=request.app.state.settings,
    )


# ⚠️ `/{project_id}` 보다 **먼저** 선언한다. FastAPI 는 선언 순서로 매칭하므로 뒤에 두면
# `dashboard` 가 프로젝트 id 로 잡혀 "프로젝트를 찾을 수 없습니다" 404 가 된다 - 원인은
# 라우팅인데 증상은 "그 프로젝트가 없다" 로 보인다(`/weekly-report` 와 같은 함정).
@router.get("/dashboard")
def project_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    department_id: str | None = Query(default=None, max_length=36),
    principal: Principal = Depends(get_principal),
    user: User = Depends(get_current_user),
):
    """프로젝트 화면 맨 위의 요약. **집계는 서버가 한다.**

    목록은 20건씩 잘려 나가므로 화면이 그 한 장을 세면 "총 22건인데 대시보드는 20건 기준"
    이 된다. 여기서는 페이지를 모르는 표본으로 센다(service.project_dashboard).

    읽기라 운영자 게이트를 걸지 않는다 - 목록과 같은 사람들이 본다.
    """
    return service.project_dashboard(
        db, principal, today=_today(request),
        scope=org_context.filter_scope(db, user, department_id),
    )


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    project = service.get_scoped_project_or_404(db, project_id, principal)
    return {"project": _project_view(project)}


@router.patch("/{project_id}")
def update_project(
    request: Request,
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """프로젝트를 수정한다. 저장은 이 서버의 데이터베이스에서 끝난다.

    예전에는 저장 뒤에 같은 값을 노션으로 밀어 넣었다. 지금은 프로젝트의 정본이 이
    데이터베이스라 밖으로 내보낼 곳이 없고, 저장 한 번에 붙던 외부 왕복도 사라졌다.
    """
    now = request.app.state.clock.now()
    project = service.get_scoped_project_or_404(db, project_id, principal)
    # 조회와 관리는 다르다 — 상위 부서 프로젝트는 보이지만 고칠 수는 없다.
    service.ensure_project_manageable(project, principal)
    # 소속을 바꾸는 것은 **권한을 바꾸는 것**이다 (0060 §34). 프로젝트가 부서를 옮기면
    # 그 아래 티켓 전부와 그 프로젝트 소유 문서가 통째로 다른 부서에 열리고, 원래 보던
    # 부서에서는 사라진다. 무엇 하나 오류를 내지 않으므로 감사에 남지 않으면 "왜 우리
    # 팀 티켓이 안 보이지" 를 나중에 추적할 방법이 없다.
    before = _scope_snapshot(project)
    service.update_project(db, project, payload, principal, now=now)
    after = _scope_snapshot(project)
    record_audit_from_request(
        request, db, action="project.update", object_type="project", object_id=project.id,
        # 소속이 그대로면 굳이 남기지 않는다 — 모든 수정에 같은 두 줄이 붙으면 정작
        # 소속이 바뀐 항목을 감사에서 찾기 어려워진다.
        before=before if before != after else None,
        after=after if before != after else None,
    )
    return {"project": _project_view(project)}


@router.delete("/{project_id}")
def delete_project(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """보관(soft delete). 하드 삭제를 안 쓰는 이유는 service.archive_project 에 적어 뒀다."""
    project = service.get_scoped_project_or_404(db, project_id, principal)
    service.ensure_project_manageable(project, principal)
    service.archive_project(db, project, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="project.archive", object_type="project", object_id=project.id,
    )
    return {"ok": True, "project": _project_view(project)}


@router.get("/{project_id}/progress")
def get_progress(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """진행률 + **계산 근거**.

    근거를 함께 싣는 이유: Notion 화면과 우리 화면에 서로 다른 진행률이 뜨는 것은 정상
    상태다(취소를 완료로 세는 rollup 을 안 믿는 것이 이 기능의 목적이다). 그때 "무엇을
    어떻게 셌는지" 를 말할 수 없으면 아무도 어느 쪽도 못 믿고 결국 둘 다 안 보게 된다.
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    return {
        "project_id": project.id,
        **service.project_progress(db, project).as_dict(),
        # 저쪽 숫자도 같이 싣는다. 이 화면의 목적이 "두 값이 다르다" 를 **설명**하는 것이라,
        # 비교 대상이 없으면 근거(basis)만 있고 무엇과 비교할 근거인지가 없다.
        "notion_percent": project.notion_progress_pct,
    }


@router.post("/{project_id}/progress/recompute")
def recompute_progress(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    project = service.get_scoped_project_or_404(db, project_id, principal)
    result = service.recompute_progress(db, project, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="project.progress.recompute",
        object_type="project", object_id=project.id,
    )
    return {"project_id": project.id, **result.as_dict()}


@router.get("/{project_id}/weekly-report")
def get_weekly_report(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    week: str | None = Query(default=None, max_length=10),
    principal: Principal = Depends(get_principal),
):
    """그 주의 사실 + 규칙이 쓴 문장. **저장하지 않는다.**

    GET 이 쓰면 새로고침할 때마다 `generated_at` 이 움직여 "언제 만든 리포트인가" 라는
    질문 자체가 사라진다. 저장은 POST 가 한다(`get_progress` 와 같은 판단).

    범위 밖은 404 다 - 목록·상세와 **같은 게이트**를 지난다.
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    return service.project_weekly_report(
        db, project,
        week=_week_from(request, week),
        settings=request.app.state.settings,
    )


@router.post("/{project_id}/weekly-report")
def generate_weekly_report(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    week: str | None = Query(default=None, max_length=10),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """그 주의 리포트를 만들어 저장한다(한 주에 한 행, 다시 만들면 덮어쓴다).

    LLM 은 아직 붙지 않았으므로 `source` 는 언제나 `rule` 이다.
    """
    now = request.app.state.clock.now()
    project = service.get_scoped_project_or_404(db, project_id, principal)
    body = service.save_weekly_report(
        db, project,
        week=_week_from(request, week),
        settings=request.app.state.settings,
        now=now,
    )
    record_audit_from_request(
        request, db, action="project.weekly_report.generate",
        object_type="project", object_id=project.id,
    )
    return body


@router.post("/{project_id}/weekly-report/llm-summary")
def generate_weekly_llm_summary(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    week: str | None = Query(default=None, max_length=10),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """그 주 AI 요약 생성을 큐에 넣는다(§L). **여기서 기다리지 않는다** - CLI 왕복은
    수십 초가 걸릴 수 있어 워커가 대신 돈다(app/jobs/handlers/project_weekly_summary.py).

    완료 시점은 이 응답이 아니라 그 뒤의 GET 이 `saved.source == "llm"` 로 알려 준다.
    """
    now = request.app.state.clock.now()
    project = service.get_scoped_project_or_404(db, project_id, principal)
    service.request_weekly_llm_summary(
        db, project,
        week=_week_from(request, week),
        user_id=principal.user_id,
        now=now,
    )
    record_audit_from_request(
        request, db, action="project.weekly_report.llm_summary_requested",
        object_type="project", object_id=project.id,
    )
    return {"ok": True, "queued": True}


# ── 마일스톤 ──────────────────────────────────────────────────────────────────
#
# 경로가 `/{project_id}/milestones/...` 인 것이 설계의 전부다. 마일스톤 id 하나로 여는
# 최상위 경로를 만들지 않는다 - 그런 경로가 있으면 프로젝트 범위 게이트를 지나지 않는
# 입구가 하나 더 생기고, 이 저장소는 정확히 그 실수를 네 번 했다(check_scope_gates.py).

def _milestone_view(milestone: ProjectMilestone) -> dict:
    return {
        "id": milestone.id,
        "project_id": milestone.project_id,
        "name": milestone.name,
        "due_on": iso_date(milestone.due_on),
        "status": milestone.status,
        "sort_order": milestone.sort_order,
        "created_at": milestone.created_at.isoformat(),
        "updated_at": milestone.updated_at.isoformat(),
    }


@router.get("/{project_id}/milestones")
def list_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    project = service.get_scoped_project_or_404(db, project_id, principal)
    rows = milestones_repo.list_for_project(db, project)
    return {"items": [_milestone_view(m) for m in rows], "total": len(rows)}


@router.post("/{project_id}/milestones")
def create_milestone(
    request: Request,
    project_id: str,
    payload: MilestoneCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    project = service.get_scoped_project_or_404(db, project_id, principal)
    milestone = milestones_repo.create(
        db, project, payload, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="project.milestone.create",
        object_type="project_milestone", object_id=milestone.id,
    )
    return {"milestone": _milestone_view(milestone)}


@router.patch("/{project_id}/milestones/{milestone_id}")
def update_milestone(
    request: Request,
    project_id: str,
    milestone_id: str,
    payload: MilestoneUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """프로젝트 범위 게이트를 먼저 지나고, 그 프로젝트 안에서만 마일스톤을 찾는다.

    두 단계를 뒤집어 마일스톤을 먼저 꺼내면 남의 팀 행을 손에 쥔 채로 판정하게 되고,
    판정을 빠뜨린 경로가 하나 생기는 순간 마일스톤 id 만으로 남의 팀 일정이 바뀐다.
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    milestone = milestones_repo.get_in_project_or_404(db, project, milestone_id)
    milestones_repo.update(
        db, milestone, payload, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="project.milestone.update",
        object_type="project_milestone", object_id=milestone.id,
    )
    return {"milestone": _milestone_view(milestone)}


@router.delete("/{project_id}/milestones/{milestone_id}")
def delete_milestone(
    request: Request,
    project_id: str,
    milestone_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    project = service.get_scoped_project_or_404(db, project_id, principal)
    milestone = milestones_repo.get_in_project_or_404(db, project, milestone_id)
    view = _milestone_view(milestone)
    milestones_repo.delete(db, milestone)
    record_audit_from_request(
        request, db, action="project.milestone.delete",
        object_type="project_milestone", object_id=view["id"],
    )
    return {"ok": True, "milestone": view}


# ── Health Score ─────────────────────────────────────────────────────────────

def _snapshot_view(row: ProjectHealthSnapshot) -> dict:
    return {
        "week_of": iso_date(row.week_of),
        "score": row.score,
        **service.health_snapshot_reasons(row),
        "created_at": row.created_at.isoformat(),
    }


def _today(request: Request) -> str:
    """판정 기준일 - **Asia/Seoul 달력일**이다.

    UTC 로 판정하면 KST 09:00 이전에 날짜가 하루 밀린다. 헬스는 '어제가 기한인 마일스톤'
    같은 경계를 세므로, 아침에 여는 사람과 오후에 여는 사람이 다른 점수를 보게 된다
    (`_week_from` 과 같은 판단, §불변 9).
    """
    from app.home.service import local_today

    return local_today(
        request.app.state.settings, request.app.state.clock.now()
    ).isoformat()


@router.get("/{project_id}/health")
def get_health(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """지금 점수와 **이유**, 그리고 못 센 지표.

    `unknown` 을 감추지 않는 것이 이 응답의 핵심이다. 마일스톤이 없는 프로젝트를 조용히
    만점으로 세면 가장 정보가 없는 프로젝트가 화면에서 가장 건강해 보인다. 점수가 null 인
    경우도 있다 - 잴 것이 하나도 없었다는 뜻이고, 0점과는 다른 상태다.

    읽기 전용이다. 새로고침이 쓰기를 일으키면 주간 스냅샷이 '그 주의 판단' 이 아니라
    실행 로그가 된다(`/health/snapshot` 이 저장을 맡는다).
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    return {
        "project_id": project.id,
        **service.project_health(db, project, today=_today(request)).as_dict(),
    }


@router.post("/{project_id}/health/snapshot")
def snapshot_health(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    _: object = require_write,
):
    """계산해서 `health_score` 에 캐시하고 그 주의 이력에 남긴다.

    점수를 낼 수 없으면(`score` 가 null) 이력에는 아무것도 안 적는다 - 스냅샷의 점수 열은
    NOT NULL 이라 0이나 100을 적어야 하는데 둘 다 거짓말이고, 몇 주 뒤 추세선에서 진짜
    값과 구별되지 않는다(service.record_health_snapshot).
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    result, row = service.record_health_snapshot(
        db, project, today=_today(request), now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="project.health.snapshot",
        object_type="project", object_id=project.id,
    )
    return {
        "project_id": project.id,
        **result.as_dict(),
        # 안 적었으면 안 적었다고 말한다. 화면이 "저장됨" 이라고만 하면 사용자는 추세에
        # 한 점이 늘었다고 믿는다.
        "snapshot": _snapshot_view(row) if row is not None else None,
    }


@router.get("/{project_id}/health/history")
def get_health_history(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """주간 헬스 이력(최근 주부터). 한 점으로는 "계속 나빠지고 있다" 를 말할 수 없다."""
    project = service.get_scoped_project_or_404(db, project_id, principal)
    rows = service.health_history(db, project)
    return {"project_id": project.id, "items": [_snapshot_view(r) for r in rows]}


# ── WBS 트리 ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/wbs")
def get_wbs(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """작업 계층 트리 + 노드별 가중 진행률.

    `progress` 는 `/progress` 와 **같은 함수, 같은 표본**이다. 두 화면의 숫자가 갈리면
    사용자는 어느 쪽도 안 믿고 결국 둘 다 안 본다.

    `unplaced` 는 못 그린 작업이다(상위 작업이 순환이거나 계층이 너무 깊다). 조용히 빼면
    사용자는 자기 일이 사라진 줄 알고, 고칠 사람은 고칠 곳을 못 찾는다.
    """
    project = service.get_scoped_project_or_404(db, project_id, principal)
    return {"project_id": project.id, **service.project_wbs(db, project).as_dict()}
