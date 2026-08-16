"""프로젝트 비즈니스 규칙. **범위 게이트는 이 파일의 첫 함수 하나뿐이다.**

`get_scoped_project_or_404` 를 목록 이외의 모든 경로가 지난다 — 상세·수정·삭제·진행률.
목록은 같은 판정의 질의판(`repository.apply_scope`)을 쓰고, 그 둘은 `repository.scope_clause`
**하나**에서 갈라진다. 판정을 두 벌로 적으면 한쪽만 고쳐지고 증상은 "어떤 사람만 안 된다"가
된다(`scripts/check_scope_gates.py` 가 이 저장소에서 네 번 반복된 그 실수를 기록한다).

범위 밖은 **403 이 아니라 404** 다. 403 은 "그 id 는 존재하는데 너는 못 본다"를 알려 주므로,
id 를 찍어 보며 응답 코드를 세면 남의 부서 프로젝트 목록을 통째로 열거할 수 있다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.db import is_write_conflict
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.models_base import split_names
from app.core.scope import Principal
from app.org.constants import DEFAULT_ORG_ID
from app.projects import milestones as milestones_repo
from app.projects import repository, sync, weekly
from app.projects.health import (
    TROUBLE_HEALTH_SCORE,
    HealthInput,
    HealthResult,
    MilestoneFact,
    TaskFact,
    compute_health,
)
# 차질 판정은 `health.py` 한 곳이다. 여기서는 이름만 빌려 온다 - `trouble_reasons` 라는
# 이름을 그대로 쓰면 이 모듈의 다른 함수와 섞여 "여기가 판정하는 자리" 로 읽힌다.
from app.projects.health import trouble_reasons as compute_trouble_reasons
from app.projects.models import (
    PROJECT_STATUSES,
    REPORT_SOURCE_LLM,
    REPORT_SOURCE_RULE,
    Project,
    ProjectHealthSnapshot,
    ProjectWeeklyReport,
)
from app.projects.progress import ProgressResult, compute_progress
from app.projects.schemas import ProjectCreate, ProjectUpdate
from app.projects.wbs import WbsResult, build_wbs, wbs_item_from_ticket

# 범위 밖과 없는 것은 **같은 문구**로 답한다. 문구가 갈리면 응답 본문만 읽어도 존재 여부가
# 새어 나가고, 그러면 404 로 만든 의미가 없다.
logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "프로젝트를 찾을 수 없습니다."

# 수정으로 바꿀 수 있는 필드. `progress_pct` / `health_score` / `archived_at` 은 여기 없다 —
# 앞의 둘은 앱이 계산하고, 보관은 전용 경로(archive)가 감사 기록과 함께 다룬다.
#
# `notion_status` 는 여기 **있다**: 포털에서 노션 진행 상태를 고치면 그대로 push 한다(사용자
# 지시). 반대로 `notion_progress_pct` / `notion_missing_at` / `notion_synced_at` 은 없다 —
# 저것들은 저쪽이 말한 사실이지 사람이 정하는 값이 아니고, 손으로 고칠 수 있게 두면 화면이
# 자기가 보고 싶은 숫자를 써 넣을 수 있다.
EDITABLE_FIELDS = (
    "name", "code", "status", "dept_id", "owner_user_id",
    "starts_on", "ends_on", "goal", "biz_type", "product", "notion_status",
)

# NOT NULL 인 컬럼. 여기에 명시적 null 이 오면 "지우기" 가 아니라 잘못된 입력이다.
# 그대로 넣으면 flush 에서 IntegrityError 가 나 사용자는 400 이 아니라 **500** 을 본다 —
# 화면은 "서버 오류" 라고 말하지만 원인은 입력이라, 아무도 자기 입력을 의심하지 않는다.
REQUIRED_FIELDS = frozenset({"name", "status"})

# 헬스 이력을 한 번에 돌려주는 주 수. 추세를 보려는 것이지 원장을 뜨려는 것이 아니라
# 상한을 둔다 - 한 해가 넘어가면 스파크라인이 화면 폭에서 뭉개져 아무것도 안 보인다.
HEALTH_HISTORY_LIMIT = 26


def get_scoped_project_or_404(
    db: Session, project_id: str, principal: Principal
) -> Project:
    """**단 하나의 범위 게이트.** 상세·수정·삭제·진행률이 전부 여기를 지난다.

    `db.get(Project, id)` 로 먼저 꺼내 놓고 나중에 판정하지 않는다 — 조건을 조회 자체에
    붙여 두면 새로 생긴 경로가 판정을 빠뜨릴 자리가 없다(`repository.get_in_scope`).
    """
    project = repository.get_in_scope(db, project_id, principal.scope)
    if project is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    return project


def ensure_dept_in_scope(db: Session, principal: Principal, dept_id: str | None) -> None:
    """**쓰기가 범위 밖으로 나가는 것도 막는다.**

    읽기만 막으면 부서 관리자가 남의 팀 `dept_id` 로 프로젝트를 만들거나, 자기 프로젝트를
    남의 팀으로 옮겨 넣을 수 있다. 옮긴 순간 그 행은 자기 범위에서 사라지므로 **되돌릴
    수도 없다** — 읽기 유출보다 나쁘다.

    **없는 부서도 여기서 막는다.** FK 에 맡기면 IntegrityError 가 500 으로 나가고, FK 가
    꺼진 환경이면 어느 부서 목록에도 안 나오면서 DB 에는 남는 유령 행이 된다
    (`app/org/service.py::create_named` 가 조직 쪽에서 같은 함정을 기록한다).

    범위 밖 부서는 없는 부서와 **똑같이 404** 다. 문구도 코드도 같아야 한다 - 갈리면
    응답만 보고 "그 부서는 존재한다" 를 알 수 있다.
    """
    if dept_id is None:
        return

    from app.org.models import Department

    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    if principal.scope.is_global:
        return
    if principal.scope.is_org:
        # 조직 범위 관리자는 자기 조직의 부서만 쓸 수 있다. 여기를 비워 두면 남의 조직
        # 부서를 단 프로젝트가 자기 조직에 생긴다 - 범위 탈출은 아니지만 조직도가 어긋난다.
        if not principal.scope.org_id or dept.org_id != principal.scope.org_id:
            raise NotFoundError(NOT_FOUND_MESSAGE)
        return
    if dept_id not in principal.scope.dept_ids:
        raise NotFoundError(NOT_FOUND_MESSAGE)


def ensure_code_is_free(
    db: Session, code: str | None, org_id: str | None, *, exclude_id: str | None = None
) -> None:
    """프로젝트 코드는 **조직 안에서만** 유일하다(`uq_projects_org_code`).

    제약에 맡기고 IntegrityError 를 흘리면 사용자는 500 을 본다. 미리 보고 409 로 답한다
    (`app/org/service.py::create_named` 와 같은 관용).

    중복을 **만들려는 조직 안에서만** 찾는 것이 중요하다. 전역으로 보면 남의 조직이 어떤
    코드를 쓰는지 409 응답으로 하나씩 확인할 수 있다.
    """
    if not code:
        # NULL 은 서로 다른 값이다(SQLite). 코드 없는 프로젝트는 몇 개든 있을 수 있다.
        return
    stmt = select(Project.id).where(Project.code == code, Project.org_id == org_id)
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    if db.execute(stmt).first() is not None:
        raise ConflictError(f"이미 있는 프로젝트 코드입니다: {code}")


def create_project(
    db: Session, payload: ProjectCreate, principal: Principal, *, now: datetime
) -> Project:
    """새 프로젝트. 부서를 안 주면 **만든 사람의 부서**가 된다.

    비워 두면 안 되는 이유: `dept_id IS NULL` 인 프로젝트는 부서 범위에서 통째로 안 보인다.
    만든 사람 본인조차 목록에서 못 찾는 상태가 되고, 증상이 "권한 없음"이 아니라 "목록이
    비어 있음"이라 원인을 찾기 어렵다(`core/scope.py` 의 신규 입사자 폴백과 같은 함정).
    """
    dept_id = payload.dept_id if payload.dept_id else principal.department_id
    ensure_dept_in_scope(db, principal, dept_id)
    org_id = principal.org_id or DEFAULT_ORG_ID
    # 검사와 저장이 **같은 식**으로 조직을 정한다. 두 벌이 되면 검사가 통과한 뒤 저장이
    # 유니크 제약에 걸린다(app/org/service.py 가 같은 함정을 기록한다).
    ensure_code_is_free(db, payload.code, org_id)

    project = Project(
        name=payload.name,
        code=payload.code,
        status=payload.status,
        dept_id=dept_id,
        org_id=org_id,
        owner_user_id=payload.owner_user_id or principal.user_id,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        goal=payload.goal,
        biz_type=payload.biz_type,
        product=payload.product,
        created_at=now,
        updated_at=now,
    )
    try:
        # PROJ-01: 위 ensure_code_is_free는 순차 요청에서만 409를 준다 — 두 요청이 같은
        # (org_id, code)로 동시에 도착하면 둘 다 그 사전검사를 통과할 수 있다. SAVEPOINT로
        # 감싸 진 쪽의 uq_projects_org_code 위반이 세션 전체를 망가뜨리지 않게 하고, 같은
        # 메시지의 409로 두 경로를 수렴시킨다(profiles/service.py::create_view와 같은 관용).
        with db.begin_nested():
            db.add(project)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError(f"이미 있는 프로젝트 코드입니다: {payload.code}") from exc
    return project


def update_project(
    db: Session, project: Project, payload: ProjectUpdate, principal: Principal,
    *, now: datetime,
) -> Project:
    """부분 수정 — **준 필드만** 바꾼다.

    `model_fields_set` 을 읽는 이유: `None` 이 "지우기"인지 "안 건드림"인지 값만 보고는
    구별할 수 없다. 안 건드린 것을 지우기로 해석하면 폼 한 곳이 빠진 클라이언트가 저장할
    때마다 목표와 일정이 조용히 지워진다.

    **낙관적 잠금은 아무것도 바꾸기 전에 본다**(0045). 검사를 뒤로 미루면 충돌로 거절하기
    전에 이미 세션에 값이 올라가 있고, 같은 트랜잭션의 다른 쓰기와 함께 새어 나갈 수 있다.
    """
    given = payload.model_fields_set
    # 두 사람이 같은 폼을 열어 두면 나중 사람이 앞사람 변경을 조용히 덮어쓰고 **양쪽 다
    # 성공 화면을 본다.** 지문을 안 보내는 클라이언트는 예전대로 동작한다(sync.ensure_not_changed).
    sync.ensure_not_changed(project, payload.base_notion_version)
    if "dept_id" in given:
        # 남의 팀으로 옮기면 그 행은 내 범위에서 사라진다 — 되돌릴 수도 없다.
        ensure_dept_in_scope(db, principal, payload.dept_id)
    if "code" in given:
        ensure_code_is_free(db, payload.code, project.org_id, exclude_id=project.id)
    for field in EDITABLE_FIELDS:
        if field not in given:
            continue
        value = getattr(payload, field)
        if value is None and field in REQUIRED_FIELDS:
            raise ValidationAppError(f"{field} 값은 비울 수 없습니다.")
        setattr(project, field, value)
    project.updated_at = now
    try:
        # PROJ-01: create_project와 같은 이유 — code를 동시에 같은 값으로 바꾸는 두 요청이
        # 위 ensure_code_is_free를 둘 다 통과할 수 있다.
        with db.begin_nested():
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError(f"이미 있는 프로젝트 코드입니다: {payload.code}") from exc
    return project


def archive_project(db: Session, project: Project, *, now: datetime) -> Project:
    """삭제 = **보관**이다(soft delete).

    하드 삭제를 안 쓰는 이유는 CASCADE 다: 주간 헬스 이력과 주간 리포트가 함께 사라지는데,
    그 둘은 '그때 무엇을 보고 그렇게 판단했는가'의 기록이라 재계산으로 돌아오지 않는다.
    되돌릴 수 없는 것을 한 번의 요청으로 지우게 두지 않는다.

    이미 보관된 프로젝트를 다시 보관해도 시각을 덮어쓰지 않는다 — 언제 보관했는지가 그
    한 번의 실수로 사라지면 안 된다.
    """
    if project.archived_at is None:
        project.archived_at = now
    project.updated_at = now
    db.flush()
    return project


def project_progress(db: Session, project: Project) -> ProgressResult:
    """이 프로젝트의 진행률과 **계산 근거**.

    값을 저장하지 않는 읽기 전용이다. 화면이 새로고침할 때마다 쓰기가 일어나면 GET 이
    쓰기가 되고(캐시·재시도와 어긋난다), 무엇보다 `progress_pct` 는 '주기적으로 계산한 값'
    이라야 헬스 이력과 시점이 맞는다.
    """
    return compute_progress(repository.tasks_for_project(db, project))


def recompute_progress(db: Session, project: Project, *, now: datetime) -> ProgressResult:
    """계산해서 `progress_pct` 에 **캐시한다**. 목록이 프로젝트마다 티켓을 다시 세지 않으려고.

    셀 것이 없으면(`percent is None`) NULL 로 되돌린다 — 0.0 으로 적으면 "작업이 아직 안
    붙었다"와 "붙었는데 하나도 못 끝냈다"가 화면에서 똑같아진다(progress.py 참조).

    🔴 **값이 실제로 안 바뀌면 `updated_at` 을 건드리지 않는다.** 이 함수는 이제 동기화
    회차마다 프로젝트 전체에 불린다(app/projects/sync.py). 매번 `updated_at = now` 를 쓰면
    티켓 하나 안 바뀐 프로젝트도 목록 정렬(`updated_at DESC`)의 맨 위로 튀어 오른다 -
    `sync._upsert` 가 정확히 같은 이유로 이미 지키고 있는 규칙이다.
    """
    result = project_progress(db, project)
    if project.progress_pct == result.percent:
        return result
    project.progress_pct = result.percent
    project.updated_at = now
    db.flush()
    return result


# ── 주간 리포트 (#12) — 규칙 기반. 조립과 **시간대 변환**이 여기 있다 ──────────────
#
# 계산은 `weekly.py`(순수), 행 고르기는 `repository.py` / `milestones.py` 가 한다. 이 층이
# 하는 일은 셋뿐이다: 주를 정하고, KST 창을 UTC 경계로 옮기고, 결과를 합친다.
#
# ## 시간대 변환을 여기서 새로 쓰지 않는 이유
#
# `app/home/service.py::window_utc_bounds` 를 그대로 부른다. 같은 변환을 한 벌 더 쓰면
# 두 벌이 갈라지고, 갈라진 쪽은 **월요일 오전 9시간이 조용히 사라지는** 모습으로만
# 드러난다(알려진 결함 M4 가 정확히 그 상태다 -
# `app/home/readers.py::documents_changed_since` 는 KST 달력일을 Notion 이 준 UTC 문자열과
# 그대로 비교한다). 화면에는 그럴듯한 숫자가 떠 있어서 아무도 신고하지 않는다.

# 전체 리포트가 한 번에 훑는 프로젝트 수 상한. 프로젝트마다 작업 목록을 따로 읽으므로
# (가시성 판정이 `repository.ticket_rows_for_project` 한 곳이어야 해서 일부러 그렇게 한다)
# 무제한으로 두면 조직이 커질 때 이 화면 하나가 DB 를 오래 잡는다. 잘렸다는 사실은
# 응답의 `truncated` 로 말한다 - 조용히 자르면 합계가 틀린 줄도 모른다.
OVERALL_PROJECT_LIMIT = 100


def _weekly_facts(db: Session, project: Project, week: weekly.Week, settings) -> dict:
    """프로젝트 한 건의 그 주 사실. **저장하지 않는다**(읽기가 쓰기를 하면 안 된다).

    `basis` 를 함께 내는 이유는 진행률과 같다: 0건과 "셀 것이 없다"는 다른 말이다. 노션에
    짝이 없는 포털 전용 프로젝트는 걸린 작업이 있을 수 없으므로 `tickets_linked` 가 False 이고,
    화면과 문장이 그 사실을 그대로 말한다.
    """
    from app.home.service import window_utc_bounds

    rows = repository.ticket_rows_for_project(db, project)
    items = [weekly.item_from_ticket(r) for r in rows]
    sections = weekly.build_sections(items, week)

    # KST 달력일 창 → DB 가 쓰는 naive UTC 경계. 마일스톤 `updated_at` 은 이 축에서만
    # 비교할 수 있다(weekly.split_milestones 의 주석 참조).
    since_utc, until_utc = window_utc_bounds(settings, week.start, week.end_exclusive)
    milestone_rows = milestones_repo.list_for_project(db, project)
    milestones = weekly.split_milestones(
        milestone_rows, week=week, since_utc=since_utc, until_utc=until_utc
    )

    tickets_linked = bool(project.notion_page_id)
    return {
        **sections,
        "milestones": milestones,
        "basis": {
            "tickets_linked": tickets_linked,
            "sample_tickets": len(items),
            "sample_milestones": len(milestone_rows),
        },
        "summary_md": weekly.render_summary_md(
            project_name=project.name, week=week, sections=sections,
            milestones=milestones, tickets_linked=tickets_linked,
        ),
        # 규칙이 쓴 문장이라는 사실을 응답에도 남긴다. 저장 행의 `source` 와 같은 어휘다.
        "source": REPORT_SOURCE_RULE,
        # LLM 요약 자리. 없는 것을 있는 척 채우지 않는다.
        "llm_summary": None,
        # **왜** 규칙 요약을 보고 있는지 화면이 말할 자리 (§L). 이유를 안 주면 화면은 침묵하고
        # 사용자는 AI 요약이 켜져 있는데 고장 났다고 믿는다.
        #
        # ⚠️ 여기서 LLM 을 **부르지 않는다.** 이 함수는 화면을 여는 GET 경로이고 CLI 왕복은
        # 수십 초가 걸린다. 설정만 읽어(프로세스를 띄우지 않는다) 상태를 말한다.
        "llm_notice": _llm_notice(settings),
    }


def _llm_notice(settings) -> str | None:
    """AI 요약이 왜 없는지 한 줄. 켜져 있으면 None(할 말이 없다).

    설정만 읽는다 - `resolve_config` 는 프로세스를 띄우지 않는다. 실제로 불러 봐야 아는 것
    (로그인 안 됨 등)은 여기서 판정할 수 없고, 그건 생성 경로가 알려 준다.
    """
    try:
        from app.llm import provider as llm_provider

        if llm_provider.resolve_config(settings).enabled:
            return None
    except Exception:  # noqa: BLE001 - 안내 한 줄 때문에 리포트가 통째로 실패하면 안 된다
        return "AI 요약 설정을 확인하지 못해 규칙 기반 요약을 보여 줍니다."
    return "AI 요약이 꺼져 있어 규칙 기반 요약을 보여 줍니다."


def project_weekly_report(
    db: Session, project: Project, *, week: weekly.Week, settings
) -> dict:
    """프로젝트 한 건의 주간 리포트(사실 + 규칙 문장 + 저장본).

    저장본(`saved`)은 **그 주의 것만** 붙인다. 주가 다르면 None 이다 - 지난 주를 보는데
    이번 주 문장이 붙어 나오면 사용자는 그것이 지난 주 이야기라고 읽는다.
    """
    saved = _saved_report(db, project.id, week.week_of)
    return {
        "project": {
            "id": project.id, "name": project.name, "code": project.code,
            "status": project.status, "progress_pct": project.progress_pct,
            "notion_page_id": project.notion_page_id,
        },
        "window": week.as_dict(),
        **_weekly_facts(db, project, week, settings),
        "saved": _saved_view(saved),
    }


def overall_weekly_report(
    db: Session, principal: Principal, *, week: weekly.Week, settings
) -> dict:
    """전체(범위 안 프로젝트 전부)의 주간 리포트.

    **목록과 같은 판정을 지난다** - `repository.list_in_scope` 다. 여기서 조건을 다시 적으면
    프로젝트 목록에서 가린 것이 전체 리포트에서 새어 나온다(이 저장소가 네 번 반복한 실수의
    정확한 모양이다: 목록에는 걸고 다른 경로에는 안 걸기).

    합계는 프로젝트별 숫자를 **실제로 더해서** 만든다. 따로 세면 두 화면이 다른 말을 하고,
    그때 사용자는 어느 쪽도 믿지 않는다.
    """
    rows, total = repository.list_in_scope(
        db, principal.scope, include_archived=False,
        offset=0, limit=OVERALL_PROJECT_LIMIT,
    )
    keys = [key for key, _title in weekly.SECTION_TITLES]
    totals = {key: 0 for key in keys}
    totals["milestones_changed"] = 0
    projects: list[dict] = []
    for project in rows:
        facts = _weekly_facts(db, project, week, settings)
        changed = facts["milestones"]["changed"]["count"]
        for key in keys:
            totals[key] += facts[key]["count"]
        totals["milestones_changed"] += changed
        projects.append({
            "project_id": project.id,
            "name": project.name,
            "code": project.code,
            "status": project.status,
            "progress_pct": project.progress_pct,
            "tickets_linked": facts["basis"]["tickets_linked"],
            **{key: facts[key]["count"] for key in keys},
            "milestones_changed": changed,
        })
    return {
        "window": week.as_dict(),
        "totals": totals,
        "projects": projects,
        "project_count": len(projects),
        # 상한에 걸려 일부만 셌다는 사실. 조용히 자르면 합계가 틀린 줄도 모른다.
        "truncated": total > len(projects),
        "source": REPORT_SOURCE_RULE,
        "llm_summary": None,
    }


# ── 프로젝트 대시보드 (요약 집계) ─────────────────────────────────────────────────
#
# ## 왜 서버가 집계하는가
#
# 목록은 20건씩 잘려 나간다(`PageParams`). 화면이 그 한 장을 세면 "총 22건인데 대시보드는
# 20건 기준" 이 된다 - 숫자가 그럴듯해서 아무도 신고하지 않는 종류의 오류다. 그래서 집계는
# 페이지를 모르는 자리(여기)에서, 자르지 않은 표본으로 한다
# (`repository.summary_rows_in_scope`).
#
# ## 범위는 목록과 같은 판정 하나를 지난다
#
# `scope_clause` 다. 여기서 조건을 다시 적으면 목록에서 가린 프로젝트가 대시보드 숫자에
# 섞이고, 그건 목록에 범위를 건 의미를 통째로 없앤다.

# 목록에 싣는 줄 수. `count` 는 언제나 진짜 총계이고 `items` 만 잘린다 - 화면이 "12건" 이라고
# 쓰면서 5줄을 그리는 어긋남이 구조적으로 안 생긴다(`app/home/aggregate.py` 와 같은 규약).
DASHBOARD_ITEM_LIMIT = 5


def _dashboard_bucket(items: list[dict]) -> dict:
    return {"count": len(items), "items": items[:DASHBOARD_ITEM_LIMIT]}


def project_dashboard(db: Session, principal: Principal, *, today: str) -> dict:
    """프로젝트 화면 맨 위의 요약. **읽기 전용이고 아무것도 다시 계산하지 않는다.**

    진행률과 헬스는 이미 행에 캐시돼 있다(`recompute_progress`, `record_health_snapshot`).
    여기서 다시 세면 같은 화면의 목록과 요약이 서로 다른 숫자를 말할 수 있다.

    ## 평균 진행률에서 None 을 0 으로 세지 않는다

    `progress_pct` 가 NULL 인 것은 "아직 한 번도 계산 안 했다" 지 0% 가 아니다. 0 으로 세면
    프로젝트를 새로 만들 때마다 팀 전체의 평균이 떨어지고, 그 하락에는 아무 의미가 없다.
    분모에서 빼고, **몇 건을 못 셌는지**를 함께 낸다 - 안 말하면 "평균 41%" 가 22건의 평균인지
    3건의 평균인지 알 수 없다.

    ## Health 가 NULL 인 것은 '하위' 가 아니다

    아직 안 잰 것이다. 0 점(재 봤더니 나쁨)과 뭉치면 한 번도 안 잰 프로젝트가 전부 빨갛게
    떠서 진짜 차질이 그 안에 묻힌다. 판정은 `health.trouble_reasons` 하나가 한다.
    """
    rows = repository.summary_rows_in_scope(db, principal.scope)

    by_status = {status: 0 for status in PROJECT_STATUSES}
    trouble: list[dict] = []
    percents: list[float] = []
    unscored = 0
    for row in rows:
        # 모르는 상태 값(옛 행, 손으로 넣은 값)도 세긴 세야 총합이 맞는다. 미리 만든 칸이
        # 없으면 그 자리에서 만든다 - 조용히 빼면 상태별 합이 전체 건수보다 작아진다.
        by_status[row.status] = by_status.get(row.status, 0) + 1
        if row.progress_pct is not None:
            percents.append(float(row.progress_pct))
        if row.health_score is None:
            unscored += 1
        reasons = compute_trouble_reasons(row.notion_status, row.health_score)
        if reasons:
            trouble.append({
                "project_id": row.id,
                "name": row.name,
                "code": row.code,
                "status": row.status,
                "health_score": row.health_score,
                "progress_pct": row.progress_pct,
                "notion_status": row.notion_status,
                "reasons": reasons,
            })

    # 나쁜 것이 위로(점수 낮은 순), 같으면 이름순. 순서를 고정해야 같은 화면을 두 번 열어도
    # 잘려 나가는 줄이 바뀌지 않는다. 점수가 없는 차질(노션 사유만)은 뒤로 보낸다.
    trouble.sort(key=lambda p: (
        p["health_score"] if p["health_score"] is not None else TROUBLE_HEALTH_SCORE + 1,
        p["name"],
    ))

    overdue = [
        {
            "id": milestone.id,
            "project_id": project_id,
            "project_name": project_name,
            "name": milestone.name,
            "due_on": milestone.due_on,
            "status": milestone.status,
        }
        for milestone, project_id, project_name
        in repository.overdue_milestones_in_scope(db, principal.scope, today=today)
    ]

    return {
        # 판정 기준일을 응답에 싣는다. 화면이 직접 오늘을 구하면 브라우저 시간대로 판정하게
        # 되고, KST 09:00 이전에는 하루 밀린 '지연' 을 그린다(§불변 9).
        "today": today,
        "total": len(rows),
        "by_status": by_status,
        "progress": {
            # 소수 한 자리. 화면이 그 자리까지만 그린다(project-format.js::percentText).
            "average_pct": round(sum(percents) / len(percents), 1) if percents else None,
            "counted": len(percents),
            # 안 센 건수를 감추지 않는다. 감추면 "평균 41%" 의 표본을 알 수 없다.
            "not_counted": len(rows) - len(percents),
        },
        "health": {
            # 차질 0건이 "다 건강하다" 인지 "아무것도 안 쟀다" 인지는 완전히 다른 사실이다.
            "unscored": unscored,
            "trouble": _dashboard_bucket(trouble),
        },
        "milestones": {"overdue": _dashboard_bucket(overdue)},
    }


def _saved_report(db: Session, project_id: str, week_of: str) -> ProjectWeeklyReport | None:
    return db.execute(
        select(ProjectWeeklyReport).where(
            ProjectWeeklyReport.project_id == project_id,
            ProjectWeeklyReport.week_of == week_of,
        )
    ).scalar_one_or_none()


def _saved_view(row: ProjectWeeklyReport | None) -> dict | None:
    if row is None:
        return None
    return {
        "week_of": row.week_of,
        "summary_md": row.summary_md,
        "source": row.source,
        "generated_at": row.generated_at.isoformat(),
    }


def save_weekly_report(
    db: Session, project: Project, *, week: weekly.Week, settings, now: datetime
) -> dict:
    """그 주의 리포트를 만들어 **한 행에 덮어쓴다**(uq_project_weekly_reports_week).

    행을 쌓지 않는 이유: 한 주에 여러 행이 있으면 "그 주의 리포트" 에 답이 여러 개가 되고,
    화면은 그중 하나를 임의로 고르게 된다. 다시 만드는 것은 정정이지 새 사건이 아니다.

    `source` 는 `rule` 이다. LLM 요약은 `save_llm_weekly_summary`(아래)가 만들며, 그 함수는
    **같은 (project_id, week_of) 행을 `llm` 로 덮어쓴다** - 따로 두지 않기로 정했다("그 주의
    리포트"는 규칙이 썼든 AI 가 썼든 하나이므로). 이 함수가 방금 `rule` 로 쓴 행을 워커가
    나중에 `llm` 로 덮어쓸 수 있다는 뜻이다 - 정상 흐름이다.
    """
    report = project_weekly_report(db, project, week=week, settings=settings)
    row = _saved_report(db, project.id, week.week_of)
    if row is None:
        row = ProjectWeeklyReport(
            project_id=project.id, week_of=week.week_of,
            created_at=now, updated_at=now,
        )
        db.add(row)
    row.summary_md = report["summary_md"]
    row.source = REPORT_SOURCE_RULE
    row.generated_at = now
    row.updated_at = now
    db.flush()
    return {**report, "saved": _saved_view(row)}


def save_llm_weekly_summary(
    db: Session, project: Project, *, week: weekly.Week, text: str, now: datetime
) -> ProjectWeeklyReport:
    """AI 가 쓴 요약을 그 주의 저장본에 **덮어쓴다**(app/jobs/handlers/project_weekly_summary.py 가 부른다).

    같은 (project_id, week_of) 행을 `save_weekly_report` 와 공유한다 - "그 주의 리포트"는
    규칙이 썼든 AI 가 썼든 하나다. 행을 나누면 화면이 둘 중 뭘 보여줄지 또 판단해야 한다.
    이 함수는 워커에서만 불린다(§L) - 여기서 LLM 을 다시 호출하지 않는다, 이미 받은
    문장을 저장만 한다.
    """
    row = _saved_report(db, project.id, week.week_of)
    if row is None:
        row = ProjectWeeklyReport(
            project_id=project.id, week_of=week.week_of,
            created_at=now, updated_at=now,
        )
        db.add(row)
    row.summary_md = text
    row.source = REPORT_SOURCE_LLM
    row.generated_at = now
    row.updated_at = now
    db.flush()
    return row


def request_weekly_llm_summary(
    db: Session, project: Project, *, week: weekly.Week, user_id: str | None, now: datetime
) -> None:
    """그 주 AI 요약 생성을 큐에 넣는다. **여기서 LLM 을 부르지 않는다** - 워커가 부른다(§L).

    idempotency_key 에 타임스탬프를 넣어 다시 생성(재생성) 요청을 허용한다 - 고정 키를 쓰면
    한 주에 딱 한 번만 생성할 수 있게 되어 "다시 만들어줘"가 안 먹는다. 짧은 시간에 두 번
    눌려도 `LlmService` 의 동시 실행 슬롯이 실제 CLI 중복 실행은 막는다(app/llm/service.py).
    """
    from app.jobs import repository as jobs_repo

    jobs_repo.enqueue(
        db,
        job_type="project_weekly_summary",
        payload={"project_id": project.id, "week_of": week.week_of},
        now=now,
        user_id=user_id,
        idempotency_key=f"weekly-llm:{project.id}:{week.week_of}:{now.strftime('%Y%m%d%H%M%S%f')}",
    )


def project_wbs(db: Session, project: Project) -> WbsResult:
    """작업 계층(WBS) 트리. **진행률과 같은 행**을 읽는다.

    `repository.ticket_rows_for_project` 를 지나므로 0043 소프트 프룬과 토큰 매칭이 자동으로
    따라온다. 트리만 다른 질의를 쓰면 "트리에는 있는데 진행률에는 없는 작업" 이 생기고,
    그 순간 같은 화면의 두 숫자가 갈라진다.
    """
    rows = repository.ticket_rows_for_project(db, project)
    return build_wbs(wbs_item_from_ticket(row) for row in rows)


def _last_activity_on(rows) -> str | None:
    """이 프로젝트의 작업이 마지막으로 움직인 날('YYYY-MM-DD'). 없으면 None.

    `notion_last_edited` 를 먼저 본다 - 저쪽에서 실제로 사람이 만진 시각이다. 그 값이 없는
    행(포털에서 만든 native 티켓)은 미러 행의 `updated_at` 으로 대신한다. 둘 다 없는 상태는
    없으므로(NOT NULL), '모른다' 가 되는 경우는 **걸린 작업이 하나도 없을 때뿐**이다.

    프로젝트 행의 `updated_at` 을 쓰지 않는 이유는 health.py 의 규칙 주석에 적어 뒀다:
    누가 설명 한 줄만 고쳐도 갱신돼서 작업이 멈춘 사실을 감춘다.
    """
    days = []
    for row in rows:
        edited = row.notion_last_edited
        if isinstance(edited, str) and len(edited) >= 10:
            days.append(edited[:10])
        elif row.updated_at is not None:
            days.append(row.updated_at.date().isoformat())
    # ISO 문자열은 사전순과 날짜순이 일치한다(models.py 가 날짜를 문자열로 두는 근거와 같다).
    return max(days) if days else None


def health_input(db: Session, project: Project, *, today: str) -> HealthInput:
    """헬스 판정에 넣을 사실을 모은다. **판정 자체는 여기서 하지 않는다**(health.py).

    나눠 두는 이유: 규칙을 순수 함수로 두면 표본을 손으로 만들어 시험할 수 있고, 반대로
    화면 숫자가 이상할 때 "규칙이 틀렸나 표본이 틀렸나" 를 갈라서 물어볼 수 있다.
    """
    rows = repository.ticket_rows_for_project(db, project)
    return HealthInput(
        today=today,
        notion_status=project.notion_status,
        milestones=tuple(
            MilestoneFact(due_on=m.due_on, status=m.status)
            for m in milestones_repo.list_for_project(db, project)
        ),
        tasks=tuple(
            TaskFact(
                status=row.status,
                due_on=row.due_date,
                # 담당자 열은 구분자로 감싼 다중값이다. 빈 문자열이면 미할당 - 여기서
                # 사람을 세지 않고 '있는가' 만 넘긴다(health.py::TaskFact).
                assigned=bool(split_names(row.assignee_notion_ids)),
            )
            for row in rows
        ),
        last_activity_on=_last_activity_on(rows),
    )


def project_health(db: Session, project: Project, *, today: str) -> HealthResult:
    """지금 시점의 헬스 점수와 이유. 읽기 전용이다(진행률과 같은 규약).

    GET 이 쓰기를 하면 캐시, 재시도와 어긋나고, 무엇보다 주간 스냅샷은 '그 주의 판단' 이라
    화면을 새로고침할 때마다 덮이면 이력이 실행 로그가 된다.
    """
    return compute_health(health_input(db, project, today=today))


def record_health_snapshot(
    db: Session, project: Project, *, today: str, now: datetime
) -> tuple[HealthResult, ProjectHealthSnapshot | None]:
    """계산해서 `health_score` 에 캐시하고 **그 주의 이력**에 남긴다.

    ## 왜 주 단위로 덮어쓰는가(행을 쌓지 않는가)

    `uq_project_health_snapshots_week` 가 (프로젝트, 주) 유일을 강제한다. 재계산이 행을
    쌓으면 '주간 이력' 이 아니라 '실행 로그' 가 되고, 추세선이 계산을 몇 번 돌렸는지를
    그리게 된다. 그래서 같은 주면 갱신한다.

    ## 점수가 None 이면 이력에 아무것도 안 적는다

    잴 것이 하나도 없었다는 뜻이다(health.py). 스냅샷 `score` 는 NOT NULL 이라 0이나 100을
    적어야 하는데 **둘 다 거짓말**이고, 그 거짓말은 몇 주 뒤 추세선에서 진짜 값과 구별되지
    않는다. 없으면 없다고 두는 편이 낫다. 대신 `health_score` 는 NULL 로 되돌려 화면이
    "아직 판정할 수 없음" 을 말할 수 있게 한다(`recompute_progress` 와 같은 규약).

    ## 이유까지 저장하는 이유

    점수만 남기면 6주 뒤에 "왜 그때 47점이었나" 에 아무도 답하지 못하고, 그러면 점수 자체를
    아무도 안 믿게 된다(models.py::ProjectHealthSnapshot). 못 센 지표(`unknown`)도 함께
    남긴다 - 그 주에 무엇을 **못 봤는지**가 점수만큼 중요하다.

    ## 점수가 그대로면 프로젝트 행을 한 글자도 안 건드린다

    이 함수는 이제 워커가 **주기적으로 전 프로젝트에** 부른다(worker_main). 회차마다
    `updated_at` 을 찍으면 전 프로젝트의 갱신 시각이 같은 값으로 덮이고, 목록 정렬이
    `updated_at DESC` 라(repository.list_in_scope) 정렬이 사실상 id 순으로 무너진다 -
    사용자가 방금 고친 프로젝트가 맨 위에 오지 않는다. 원인이 정렬 코드에 없어서 아무도
    못 찾는다. `sync.py::_upsert` 가 같은 함정을 같은 방식으로 피한다.
    """
    result = project_health(db, project, today=today)
    if project.health_score != result.score:
        # 값이 실제로 달라질 때만 쓴다. 같은 값을 다시 대입하면 SQLAlchemy 가 변경으로
        # 세지 않아 그 컬럼이 UPDATE 에서 빠지고, 결국 `onupdate=utcnow` 가 이긴다.
        project.health_score = result.score
        project.updated_at = now
    if result.score is None:
        db.flush()
        return result, None

    # 주 경계도 판정 기준일(KST 달력일)에서 뽑는다. `now`(naive UTC)로 뽑으면 월요일
    # 오전 9시 이전의 저장이 **지난 주 칸**에 들어가 그 주 값을 덮어쓴다.
    # 월요일 계산은 스프린트와 같은 함수 하나를 쓴다(weekly.week_for).
    week_of = weekly.week_for(date.fromisoformat(today)).week_of
    payload = json.dumps(result.as_dict(), ensure_ascii=False)
    row = db.execute(
        select(ProjectHealthSnapshot).where(
            ProjectHealthSnapshot.project_id == project.id,
            ProjectHealthSnapshot.week_of == week_of,
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProjectHealthSnapshot(
            project_id=project.id, week_of=week_of, score=result.score,
            reasons_json=payload, created_at=now,
        )
        db.add(row)
    else:
        row.score = result.score
        row.reasons_json = payload
    db.flush()
    return result, row


def latest_checked_rule_counts(db: Session, project_ids: list[str]) -> dict[str, int]:
    """프로젝트별 **가장 최근** 헬스 스냅샷이 실제로 판정한 규칙 수 (FN-42).

    `Project.health_score` 는 정수 하나뿐이라 "5개 규칙을 다 재서 100점"과 "1개만
    재서(그것도 감점 없이) 100점"을 화면에서 구별할 수 없다 — 둘 다 만점으로 보이지만
    신뢰도는 다르다. `record_health_snapshot` 이 점수를 쓸 때마다 **같은 트랜잭션**에서
    `reasons_json` 에 `checked` 목록도 함께 남기므로(health.py 의 계약), 새 컬럼이나
    마이그레이션 없이 이미 있는 이력에서 답할 수 있다.

    스냅샷이 아예 없는 프로젝트(워커가 아직 한 번도 안 돈 경우)는 결과 dict 에서 빠진다 —
    "신뢰도를 모른다"는 뜻이고, 호출부가 그 경우를 "다 쟀다"로 착각하면 안 된다.
    """
    if not project_ids:
        return {}
    latest_week = (
        select(
            ProjectHealthSnapshot.project_id,
            func.max(ProjectHealthSnapshot.week_of).label("week_of"),
        )
        .where(ProjectHealthSnapshot.project_id.in_(project_ids))
        .group_by(ProjectHealthSnapshot.project_id)
        .subquery()
    )
    rows = db.execute(
        select(ProjectHealthSnapshot.project_id, ProjectHealthSnapshot.reasons_json).join(
            latest_week,
            (ProjectHealthSnapshot.project_id == latest_week.c.project_id)
            & (ProjectHealthSnapshot.week_of == latest_week.c.week_of),
        )
    ).all()
    counts: dict[str, int] = {}
    for project_id, reasons_json in rows:
        try:
            checked = json.loads(reasons_json).get("checked") or []
        except (TypeError, ValueError):
            continue
        counts[project_id] = len(checked)
    return counts


# ── 주간 헬스 스냅샷 일괄 기록 ──────────────────────────────────────────────────
#
# `record_health_snapshot` 하나만 있던 시절에는 **사람이 버튼을 눌러야만** 이력이 쌓였다.
# 즉 추세선은 영원히 비어 있었고, 빈 추세선은 "아무도 안 쟀다" 가 아니라 "별일 없었다" 처럼
# 보인다. 아래 스윕이 그 구멍을 메운다. 부르는 곳은 워커 틱 하나뿐이다(worker_main).


# 한 회차가 훑는 프로젝트 수 상한. 무제한으로 두면 조직이 커질 때 이 잡 하나가 DB 를 오래
# 잡고, 그 동안 워커 루프의 다른 틱(스케줄러, 동기화)이 밀린다. 잘렸다는 사실은 결과의
# `truncated` 로 말한다 - 조용히 자르면 "왜 어떤 프로젝트만 추세선이 비지?" 가 된다.
HEALTH_SNAPSHOT_SWEEP_LIMIT = 500


@dataclass(frozen=True)
class HealthSnapshotFailure:
    """한 프로젝트에서 스냅샷이 실패한 사실. **이름까지 담는다.**

    id 만 남기면 운영자가 화면에서 그 id 를 다시 찾아 이름을 알아내야 하고, 그 한 단계
    때문에 대부분은 안 본다.
    """

    project_id: str
    project_name: str
    error: str

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "error": self.error,
        }


@dataclass(frozen=True)
class HealthSnapshotSweep:
    """한 회차의 결과. **세 숫자가 서로 다른 사실이라 따로 센다.**

    `recorded`(이력에 적었다), `skipped`(점수를 낼 수 없어 일부러 안 적었다),
    `failed`(적으려 했는데 터졌다)를 하나로 뭉치면 "0건 기록" 이 세 가지 뜻을 갖는다:
    프로젝트가 없거나, 전부 잴 것이 없거나, 전부 실패했거나. 운영자는 그 셋에 각각 다르게
    행동해야 한다.
    """

    recorded: int
    skipped: int
    failed: int
    failures: tuple[HealthSnapshotFailure, ...]
    # 상한에 걸려 일부만 훑은 회차. True 면 이번 회차가 전 프로젝트를 본 것이 **아니다**.
    truncated: bool = False

    @property
    def total(self) -> int:
        return self.recorded + self.skipped + self.failed

    def as_dict(self) -> dict:
        return {
            "recorded": self.recorded,
            "skipped": self.skipped,
            "failed": self.failed,
            "truncated": self.truncated,
            "failures": [f.as_dict() for f in self.failures],
        }

    def error_summary(self) -> str | None:
        """운영 화면(`sync_status.error`)에 그대로 실을 한 줄. 실패가 없으면 None.

        None 을 돌려주는 것이 중요하다 - 빈 문자열을 넣으면 '실패가 있는데 설명이 없다' 와
        '실패가 없다' 가 화면에서 같아진다.
        """
        if not self.failures:
            return None
        head = ", ".join(f"{f.project_name}({f.error})" for f in self.failures[:3])
        if len(self.failures) > 3:
            head += f" 외 {len(self.failures) - 3}건"
        return f"헬스 스냅샷 실패 {self.failed}건: {head}"


def record_health_snapshots(
    db: Session, *, today: str, now: datetime, limit: int = HEALTH_SNAPSHOT_SWEEP_LIMIT
) -> HealthSnapshotSweep:
    """전 프로젝트를 돌며 그 주의 헬스를 이력에 남긴다. **커밋하지 않는다**(부르는 쪽 몫).

    ## 여러 번 돌아도 안전하다

    `record_health_snapshot` 이 (프로젝트, 주) 유일 인덱스에 맞춰 upsert 한다. 그래서 이
    스윕을 한 시간에 한 번 돌리든 하루에 한 번 돌리든 그 주의 행은 한 줄이고, 값은 마지막
    회차의 판단으로 갱신된다. 워커가 재시작해도 같다.

    ## 보관된 프로젝트는 빼는 이유

    보관은 소프트 삭제다(models.py::Project.archived_at). 지난 이력은 남기되 새 점은 안
    찍는다 - 끝난 프로젝트의 추세선이 계속 자라면 "지금 볼 것" 목록이 죽은 프로젝트로 찬다.

    ## 한 건이 터져도 나머지는 저장된다

    프로젝트마다 SAVEPOINT 를 잡는다. 그냥 try/except 만 두면 터진 프로젝트가 세션에 남긴
    반쪽짜리 변경이 바깥 트랜잭션에 그대로 붙어, **커밋 한 번에 전부** 날아가거나 이상한
    행이 함께 커밋된다.

    그리고 실패를 **삼키지 않는다**: 스택은 로그에, 사실은 결과에 남긴다. 로그에만 남기면
    아무도 안 보고("백업 실패를 로그만 남기고 삼킨다" 가 이 저장소의 미해결 항목이다),
    결과에만 남기면 원인을 못 찾는다.
    """
    stmt = (
        select(Project)
        .where(Project.archived_at.is_(None))
        # 정렬을 고정한다. 상한에 걸릴 때 회차마다 다른 프로젝트가 잘리면 어떤 프로젝트는
        # 영원히 안 찍히고, 그 사실이 아무 데도 안 남는다.
        .order_by(Project.created_at.asc(), Project.id.asc())
        .limit(limit + 1)
    )
    projects = list(db.execute(stmt).scalars().all())
    truncated = len(projects) > limit
    if truncated:
        projects = projects[:limit]
        logger.warning(
            "헬스 스냅샷 스윕이 상한(%d)에 걸렸다. 이번 회차는 전 프로젝트를 보지 못했다.",
            limit,
        )

    recorded = skipped = 0
    failures: list[HealthSnapshotFailure] = []
    for project in projects:
        # 이름과 id 를 미리 붙잡아 둔다 - 실패 후에는 SAVEPOINT 롤백으로 객체가 만료돼
        # 속성을 읽는 것 자체가 다시 질의가 되고, 그 질의도 터질 수 있다.
        project_id, project_name = project.id, project.name
        try:
            with db.begin_nested():
                _, row = record_health_snapshot(db, project, today=today, now=now)
        except Exception as exc:
            logger.exception(
                "프로젝트 헬스 스냅샷 실패 (나머지는 계속한다): %s(%s)",
                project_name, project_id,
            )
            failures.append(HealthSnapshotFailure(
                project_id=project_id, project_name=project_name,
                error=f"{type(exc).__name__}: {exc}",
            ))
            continue
        if row is None:
            # 점수를 낼 수 없었다. 이건 실패가 아니라 **일부러 안 적은 것**이다.
            skipped += 1
        else:
            recorded += 1
    return HealthSnapshotSweep(
        recorded=recorded, skipped=skipped, failed=len(failures),
        failures=tuple(failures), truncated=truncated,
    )


def health_history(
    db: Session, project: Project, *, limit: int = HEALTH_HISTORY_LIMIT
) -> list[ProjectHealthSnapshot]:
    """주간 헬스 이력, 최근 주부터. 추세는 한 점으로는 말할 수 없는 문장이다.

    `week_of` 로 정렬한다(`created_at` 이 아니라). 지난주 값을 나중에 다시 계산해 넣으면
    생성 시각 순서와 주 순서가 어긋나고, 그러면 추세선이 뒤로 간다.
    """
    rows = db.execute(
        select(ProjectHealthSnapshot)
        .where(ProjectHealthSnapshot.project_id == project.id)
        .order_by(ProjectHealthSnapshot.week_of.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


def health_snapshot_reasons(row: ProjectHealthSnapshot) -> dict:
    """저장된 이유 JSON 을 화면이 쓸 모양으로. **깨진 값에 500 을 내지 않는다.**

    이력은 과거에 다른 모양으로 적혔을 수 있고(컬럼 기본값은 빈 리스트다), 한 줄이 깨졌다고
    추세 화면 전체가 죽으면 남은 이력까지 못 보게 된다. 읽을 수 없으면 빈 목록으로 둔다.
    """
    try:
        parsed = json.loads(row.reasons_json or "[]")
    except (TypeError, ValueError):
        return {"reasons": [], "unknown": []}
    if isinstance(parsed, list):
        # 컬럼 기본값(빈 리스트) 또는 이유만 적힌 옛 모양.
        return {"reasons": parsed, "unknown": []}
    if isinstance(parsed, dict):
        return {
            "reasons": parsed.get("reasons") or [],
            "unknown": parsed.get("unknown") or [],
        }
    return {"reasons": [], "unknown": []}
