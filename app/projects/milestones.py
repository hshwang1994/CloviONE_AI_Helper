"""마일스톤 CRUD. **범위 게이트는 프로젝트의 것을 그대로 쓴다.**

## 마일스톤 id 로는 남의 팀 것을 못 만진다

이 파일의 모든 조회는 `project_id` 를 **조건에 넣은 채로** 시작한다. 부르는 쪽은 이미
`service.get_scoped_project_or_404` 를 지난 `Project` 객체를 넘겨야 하므로, 마일스톤 id 만
바꿔 찍는 것으로는 다른 프로젝트의 행에 닿을 수 없다.

`db.get(ProjectMilestone, id)` 로 먼저 꺼내 놓고 나중에 `milestone.project_id` 를 비교하는
모양을 일부러 안 쓴다. 그 모양은 비교를 빠뜨릴 자리를 만들고, 이 저장소는 정확히 그 실수를
네 번 했다(`scripts/check_scope_gates.py`). 조건을 조회 자체에 붙이면 빠뜨릴 자리가 없다
(`repository.get_in_scope` 와 같은 관용).

## 삭제는 하드 삭제다

프로젝트(`service.archive_project`)와 다르다. 프로젝트를 지우면 CASCADE 로 헬스 이력과 주간
리포트가 함께 사라지는데 그 둘은 '그때 무엇을 보고 그렇게 판단했는가' 의 기록이라 재계산으로
돌아오지 않는다. 마일스톤에는 딸린 이력이 없다 - 되살릴 것이 없는데 소프트 삭제를 두면
목록 질의마다 `deleted_at IS NULL` 을 붙여야 하고, 그 조건을 한 곳에서 빠뜨리면 지운 것이
다시 보인다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.projects import repository
from app.projects.models import Project, ProjectMilestone
from app.projects.schemas import MilestoneCreate, MilestoneUpdate

# 프로젝트와 **같은 문구**다. 마일스톤이 없는 것과 범위 밖인 것을 문구로 구별할 수 있으면
# 404 로 만든 의미가 없다(service.NOT_FOUND_MESSAGE 와 같은 판단).
NOT_FOUND_MESSAGE = "마일스톤을 찾을 수 없습니다."

# 수정으로 바꿀 수 있는 필드. `project_id` 는 여기 없다 - 마일스톤을 다른 프로젝트로 옮기면
# 그 순간 내 범위 밖으로 나갈 수 있고, 나가면 되돌릴 수도 없다(프로젝트의 dept_id 와 같은
# 부류의 위험이라 같은 결론을 낸다: 옮기기는 기능으로 두지 않는다).
EDITABLE_FIELDS = ("name", "due_on", "status", "sort_order")

# NOT NULL 컬럼. 명시적 null 이 오면 '지우기' 가 아니라 잘못된 입력이다. 그대로 넣으면
# flush 에서 IntegrityError 가 나 사용자는 400 대가 아니라 **500** 을 본다.
REQUIRED_FIELDS = frozenset({"name", "status", "sort_order"})

def list_for_project(db: Session, project: Project) -> list[ProjectMilestone]:
    """목록. 질의는 `repository.milestones_for_project` **하나**를 쓴다.

    여기서 같은 질의를 다시 적지 않는 이유: 주간 리포트와 헬스 판정도 같은 행을 읽는다.
    질의가 세 벌이 되면 정렬이나 필터가 한 곳만 고쳐지고, 증상은 "리포트에는 있는데 목록에는
    없다" 가 된다. 사용자에게는 마일스톤이 사라진 것으로 보인다.
    """
    return repository.milestones_for_project(db, project)


def get_in_project_or_404(
    db: Session, project: Project, milestone_id: str
) -> ProjectMilestone:
    """단건 조회 - **프로젝트 조건을 조회에 붙인 채로** 꺼낸다(모듈 docstring)."""
    row = db.execute(
        select(ProjectMilestone).where(
            ProjectMilestone.id == milestone_id,
            ProjectMilestone.project_id == project.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    return row


def create(
    db: Session, project: Project, payload: MilestoneCreate, *, now: datetime
) -> ProjectMilestone:
    milestone = ProjectMilestone(
        project_id=project.id,
        name=payload.name,
        due_on=payload.due_on,
        status=payload.status,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(milestone)
    db.flush()
    return milestone


def update(
    db: Session, milestone: ProjectMilestone, payload: MilestoneUpdate, *, now: datetime
) -> ProjectMilestone:
    """부분 수정 - **준 필드만** 바꾼다.

    `model_fields_set` 을 읽는 이유는 프로젝트 수정과 같다: `None` 이 '지우기' 인지
    '안 건드림' 인지 값만 보고는 구별할 수 없다. 안 건드린 것을 지우기로 해석하면 폼 한 곳이
    빠진 클라이언트가 저장할 때마다 기한이 조용히 지워진다.
    """
    given = payload.model_fields_set
    for field in EDITABLE_FIELDS:
        if field not in given:
            continue
        value = getattr(payload, field)
        if value is None and field in REQUIRED_FIELDS:
            raise ValidationAppError(f"{field} 값은 비울 수 없습니다.")
        setattr(milestone, field, value)
    milestone.updated_at = now
    db.flush()
    return milestone


def delete(db: Session, milestone: ProjectMilestone) -> None:
    db.delete(milestone)
    db.flush()
