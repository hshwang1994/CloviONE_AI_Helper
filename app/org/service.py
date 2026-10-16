"""부서·직책 명부 서비스 — 웹 API와 CLI가 같이 쓴다(§29).

부서와 직책은 규칙이 같아서 한 벌의 함수가 모델 클래스를 받아 처리한다. 규칙을 두 벌
적으면 한쪽만 고쳐지고, 그러면 '직책은 삭제되는데 부서는 안 되는' 식으로 갈라진다.
"""

from __future__ import annotations

import time
from typing import TypeVar

from sqlalchemy import and_ as sa_and, func, or_ as sa_or, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_insert_race, write_conflict_backoff
from app.core.text import object_particle, subject_particle, topic_particle
from app.org.constants import DEFAULT_ORG_ID, ORG_SUSPENDED
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.org.models import Department, JobTitle, Organization

OrgModel = TypeVar("OrgModel", Department, JobTitle)

# 사람이 읽는 이름. 오류 메시지에 "job_titles를 쓰는 사용자가 3명"이라고 쓰면
# 화면에 그대로 나가 무슨 말인지 알 수 없다.
LABELS: dict[type, str] = {Department: "부서", JobTitle: "직책"}

MAX_NAME_LENGTH = 120

# 후속 재감사(2026-08-15)에서 발견: create_item의 사전 중복 검사(find_by_name)와
# db.add/flush 사이에 SAVEPOINT/재시도가 없었다 — Department.(org_id,name)과
# JobTitle.name(전역)이 실제 UNIQUE 제약이므로, 동시에 같은 이름으로 두 번 POST하면
# 사전 검사를 둘 다 통과하고 나중 flush()가 처리되지 않은 IntegrityError/
# OperationalError("database is locked")로 500을 냈다 — PA-RC-0008이 승격한
# 바로 그 패턴(app/projects/service.py의 PROJ-01과 동일 계열)인데 이 호출부만 빠져 있었다.
_CREATE_ITEM_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES

# PATCH 바디에서 필드를 아예 안 보낸 것("바꾸지 않음")과 명시적으로 null을 보낸 것
# ("지워라")을 구분하기 위한 표식. name=None 기본값 하나만 쓰면 두 경우가 똑같이
# 보여, 라우터가 exclude_unset으로 이미 구분해 둔 정보가 여기서 다시 뭉개진다 —
# {"name": null} PATCH가 조용한 no-op이 되고 프런트는 '저장했습니다' 성공 토스트를
# 띄우면서 감사 로그에는 아무 실제 변경 없는 before==after 항목만 남는다.
_UNSET = object()


def label_for(model: type) -> str:
    return LABELS[model]


def normalize_name(name: str | None) -> str:
    """앞뒤 공백은 이름의 일부가 아니다. ' 영업팀'과 '영업팀'이 다른 부서로 들어오면
    유일 제약이 있어도 중복이 생긴다."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationAppError("이름을 입력해야 합니다.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationAppError(f"이름은 {MAX_NAME_LENGTH}자를 넘을 수 없습니다.")
    return cleaned


def get_or_404(db: Session, model: type[OrgModel], item_id: str, scope=None) -> OrgModel:
    """단건 조회. `scope` 를 주면 **범위 밖은 없는 것으로 취급한다** (3순위 IDOR).

    목록에서 가린 것이 단건에서 새면 가린 의미가 없다. 그리고 이 함수는 **수정·삭제 경로도
    함께 쓴다** — 즉 범위를 안 걸면 다른 조직 부서를 id 하나로 지울 수 있었다.

    **403 이 아니라 404** — 403 은 그 id 가 존재한다고 알려 준다(저장소 규칙).
    """
    row = db.get(model, item_id)
    if row is None:
        label = label_for(model)
        raise NotFoundError(f"{label}{object_particle(label)} 찾을 수 없습니다.")
    if not scope_allows_item(scope, row):
        label = label_for(model)
        raise NotFoundError(f"{label}{object_particle(label)} 찾을 수 없습니다.")
    return row


# ── 범위 판정 — 목록·트리·단건·생성·수정이 **이 둘만** 쓴다 ────────────────────
#
# 규칙을 두 벌 적으면 한쪽만 고쳐지고, 그때 증상은 "목록에는 없는데 id 로는 열린다"
# (또는 그 반대)다. SQL 절(`scope_clause`)과 손에 든 행(`scope_allows_item`)으로
# 나뉘는 이유는 물어보는 자리가 다르기 때문이고, **문장은 하나여야 한다** — 아래 둘을
# 붙여 두는 이유가 그것이다(한쪽만 고치면 바로 옆에서 티가 난다).
#
# 축은 둘이다:
#   * **조직** — 부서·직책 둘 다. 부서 이름만으로도 그 회사가 무슨 일을 어떤 단위로
#     하는지 드러난다.
#   * **부서 서브트리** — 부서에만. 직책은 조직 단위 어휘라 부서로 나누면 자기 팀에
#     없는 직책을 아무에게도 못 주게 된다.


def scope_allows_item(scope, row) -> bool:
    """행 하나가 이 범위 안인가. ``scope_clause`` 와 **같은 규칙**이다."""
    if scope is None or getattr(scope, "is_global", True):
        return True
    # 범위는 있는데 조직을 모른다 = 설정이 불완전하다. 넓히는 쪽이 아니라 **닫는 쪽으로**
    # 실패한다(`app/core/scope.py::build_scope` 와 같은 규칙 - 화면이 비면 신고가 들어오지만
    # 조용한 권한 확대는 아무도 신고하지 않는다).
    if not getattr(scope, "org_id", None):
        return False
    if getattr(row, "org_id", None) != scope.org_id:
        return False
    if getattr(scope, "is_dept", False) and isinstance(row, Department):
        return _in_dept_subtree(scope, row)
    return True


def _in_dept_subtree(scope, row) -> bool:
    """부서 범위에서 이 부서가 내 서브트리인가.

    **부모가 내 서브트리면 그 자식도 내 서브트리다.** 이 갈래는 이미 저장된 행에는 아무것도
    넓히지 않는다 — 부모가 집합 안이면 `department_subtree_ids` 가 자식도 이미 넣었다.
    필요한 이유는 **방금 만든 행**이다: 그 행은 집합을 계산한 시점에 없었으므로 자기 id 로는
    절대 안 걸리고, 그러면 부서 관리자가 자기 팀 아래에 부서를 하나도 못 만들게 된다.
    """
    ids = getattr(scope, "dept_ids", None) or frozenset()
    if not ids:
        return False
    return row.id in ids or (row.parent_id is not None and row.parent_id in ids)


def scope_clause(scope, model):
    """목록·트리에 거는 조건. 전역이면 ``None``(= 조건 없음).

    ``None`` 규약은 `app/core/scope.py::scope_filter` 와 같다 — 부르는 쪽이
    `if clause is not None:` 을 쓸 수밖에 없어서 '범위를 고려했다'가 코드에 남는다.

    `scope_filter` 를 그대로 쓰지 않는 이유: 그 함수는 부서 범위에서 `dept_column` 을 안 주면
    `MATCH_NOTHING` 으로 떨어진다. 부서와 직책은 걸어야 할 컬럼이 서로 다른데(부서는 자기
    id, 직책은 없음) 한 번의 호출로는 그 차이를 말할 수 없어서, 부서 범위 관리자에게
    **두 목록이 통째로 비는** 상태가 됐다.
    """
    from app.core.scope import MATCH_NOTHING

    if scope is None or getattr(scope, "is_global", True):
        return None
    if not getattr(scope, "org_id", None):
        return MATCH_NOTHING
    clause = model.org_id == scope.org_id
    if getattr(scope, "is_dept", False) and model is Department:
        ids = tuple(sorted(getattr(scope, "dept_ids", None) or ()))
        if not ids:
            return MATCH_NOTHING
        # `parent_id` 갈래는 `_in_dept_subtree` 와 같은 문장이다(저장된 행에는 no-op).
        clause = sa_and(clause, sa_or(model.id.in_(ids), model.parent_id.in_(ids)))
    return clause


def apply_scope(stmt, scope, model):
    """`select(model)` 에 범위를 건다(`app/jobs/repository.py::apply_scope` 와 같은 모양)."""
    clause = scope_clause(scope, model)
    return stmt if clause is None else stmt.where(clause)


def find_by_name(
    db: Session, model: type[OrgModel], name: str, *, org_id: str | None = None
) -> OrgModel | None:
    """이름으로 찾기. `org_id` 를 주면 **그 조직 안에서만** 찾는다.

    대소문자만 다른 이름('Sales' vs 'sales', 'ClovirONE팀' vs 'ClovirOne팀')은 사람 눈엔
    같은 부서·직책이다 — 모델 docstring 이 그 시나리오를 유일 제약의 근거로 든다.

    **왜 조직을 가려야 하나**: 실제 유니크 제약은 `(org_id, name)` 인데 이 검사만 전역이었다.
    그래서 부서 범위 관리자가 남의 조직 부서 이름을 추측해 POST 하면
    `409 "이미 있는 부서입니다: <이름>"` 이 돌아와 **그 이름이 존재한다는 사실이 드러났다** —
    목록·트리를 다 가려 놓고 여기 한 곳으로 이름을 하나씩 확인할 수 있었다.
    검사가 제약보다 넓으면 막는 것 없이 정보만 흘린다.
    """
    stmt = select(model).where(func.lower(model.name) == name.lower())
    if org_id is not None:
        stmt = stmt.where(model.org_id == org_id)
    return db.execute(stmt).scalar_one_or_none()


def list_items(db: Session, model: type[OrgModel], *, active: bool | None = None, scope=None):
    """부서·직책 목록. `scope` 를 주면 그 범위 안만 (2순위 #1).

    조직·부서 관리자가 **다른 조직의 조직도를 통째로** 볼 수 있었다 — 부서 이름만으로도
    그 회사가 무슨 일을 어떤 단위로 하는지 드러난다.

    `Department`/`JobTitle` 은 둘 다 `OrgScopedMixin` 을 상속한다 — **모델은 범위를 선언하는데
    질의가 안 걸고 있었다**(`trash_items` 와 같은 어긋남).

    부서 범위 관리자에게는 **자기 서브트리만** 남긴다. 직책은 조직 단위 어휘라 부서로
    나누지 않는다(그러면 자기 팀에 없는 직책을 아무에게도 못 주게 된다).

    그 의도는 주석에만 있었고 코드는 반대로 동작했다: `scope_filter(scope, org_column=...)`
    를 `dept_column` 없이 불러서 부서 범위면 `MATCH_NOTHING` 으로 떨어졌다 — 두 목록이
    **통째로 비었다**. 유출이 아니라 기능 고장이지만, 직책이 안 보이면 사용자에게 직책을
    지정할 수 없다. 이제 판정은 `scope_clause` 한 곳에 있고 단건·생성이 같은 것을 쓴다.
    """
    stmt = select(model)
    if active is not None:
        stmt = stmt.where(model.active.is_(active))
    return db.execute(
        apply_scope(stmt, scope, model).order_by(model.name)
    ).scalars().all()


def _fk_column(model: type):
    from app.users.models import User

    return User.department_id if model is Department else User.title_id


def usage_count(db: Session, model: type, item_id: str) -> int:
    """이 항목을 쓰는 사용자 수. 보관된 사용자도 센다 — 행이 살아 있고 FK가 이 항목을
    가리키고 있으므로, 안 세면 참조가 있는 행을 지우려다 실패하거나 남의 부서를 지운다."""
    from app.users.models import User

    return db.execute(
        select(func.count()).select_from(User).where(_fk_column(model) == item_id)
    ).scalar_one()


def bulk_usage_count(db: Session, model: type, item_ids) -> dict[str, int]:
    """`usage_count`의 목록판 — 행마다 한 번씩 부르면(UA-16) 목록 N건에 질의 N번이 된다
    (같은 파일의 `_org_names`·`tree.py`의 그룹 질의와 대조적이었다). 그룹 질의 한 번으로
    {item_id: 사용자 수}를 만든다 — 안 쓰는 항목은 딕셔너리에 없다(호출부가 `.get(id, 0)`)."""
    from app.users.models import User

    ids = {i for i in item_ids if i}
    if not ids:
        return {}
    column = _fk_column(model)
    rows = db.execute(
        select(column, func.count()).where(column.in_(ids)).group_by(column)
    ).all()
    return {row[0]: row[1] for row in rows}


def bulk_child_department_count(db: Session, department_ids) -> dict[str, int]:
    """{department_id: 그 부서를 parent_id로 삼는 자식 부서 수}. Department 전용(직책엔
    트리가 없다) — `bulk_usage_count`와 같은 그룹 질의 패턴이다.

    UA-20R: 부서 삭제 확인 문구가 "몇 명이 쓰는가"(`usage_count`, 직속 인원)만 말하고
    "이 부서를 지우면 자식 부서가 어떻게 되는가"는 말하지 않았다. `parent_id`는
    `ondelete="SET NULL"`이라(모델 주석: "부모가 지워지면 자식은 사라지지 않고 최상위로
    올라온다") 데이터가 없어지진 않지만, 3단 트리가 클릭 한 번에 평탄해지는 것을 관리자가
    지우기 전에 알아야 한다."""
    ids = {i for i in department_ids if i}
    if not ids:
        return {}
    rows = db.execute(
        select(Department.parent_id, func.count())
        .where(Department.parent_id.in_(ids))
        .group_by(Department.parent_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def ensure_parent_is_active(parent: Department) -> None:
    """비활성 부서는 **새로** 상위 부서로 고를 수 없다 (xb-08).

    「비활성」은 새로 고를 수 없다는 뜻이다 — 사용자·직책 배정에는 그 규칙이 있는데
    (`resolve_assignable`) 트리 편집에만 없어서, 정리한 부서 아래에 새 부서가 생겼다.
    그렇게 생긴 부서는 정합성 보고서의 어느 갈래에도 안 걸린다(그 진단은 사용자·프로젝트·
    지식 공간만 본다).

    **이미 그 부모 밑에 있는 부서는 건드리지 않는다** — 수정 폼은 이름만 고칠 때에도 지금
    부모를 그대로 다시 보내므로, 여기서 막으면 그 부서는 이름조차 못 고친다
    (`resolve_assignable` 의 `allow_current` 와 같은 이유다). 호출부가 「부모가 실제로
    바뀌는 경우」에만 부른다.
    """
    if not parent.active:
        raise ValidationAppError(
            f"비활성 부서는 상위 부서로 지정할 수 없습니다: {parent.name}"
        )


def create_item(
    db: Session,
    model: type[OrgModel],
    *,
    name: str,
    parent_id: str | None = None,
    org_id: str | None = None,
    scope=None,
) -> OrgModel:
    """새 부서·직책. `scope` 를 주면 **목록과 같은 판정**을 지난다.

    생성 경로만 범위를 안 봤다. `org_id`/`parent_id` 를 존재 여부만 확인했으므로 부서 범위
    관리자가 **남의 조직에, 남의 부서 밑에** 부서를 만들 수 있었고, 만들고 나면 자기
    목록에는 안 보이는 유령 행이 남았다(만든 사람도 지울 수 없다 - 단건이 404 다).
    """
    clean = normalize_name(name)
    # 중복 검사 범위는 **그 모델의 실제 유니크 제약과 같아야 한다**(UA-12). Department 는
    # `(org_id, name)` — 조직 안에서만 본다. JobTitle 은 모델 docstring 이 명시하듯 이름
    # 유니크가 **전역**이다("팀장은 조직이 늘어도 같은 이름을 쓰는 게 자연스럽다") — 여기를
    # org_id 로 좁히면 남의 조직에 같은 이름이 있을 때 사전검사를 통과해 버리고 실제
    # INSERT 의 전역 UNIQUE 에서 잡히지 않은 IntegrityError → 500 이 났다.
    #
    # Department 의 org_id 폴백에 DEFAULT_ORG_ID 를 넣는 이유: 전역 관리자가 org_id 를
    # 안 보내면(scope 도 없다) 아래 `target_org` 가 falsy 라 `row.org_id` 를 명시적으로
    # 안 정하고 컬럼 기본값(DEFAULT_ORG_ID)에 맡긴다 — 그런데 이 사전검사가 그 기본값을
    # 모르고 `org_id=None`(전역)으로 봤다. 실제로는 DEFAULT_ORG_ID 안에서만 겹치면
    # 안 되는데, 전역으로 보면 **관계없는 다른 조직**의 같은 이름과도 충돌해 잘못된
    # 409 가 났다 - 아래에서 실제로 정하는 조직과 같은 식을 써야 검사와 저장이 안 어긋난다.
    dup_org = (
        (org_id or getattr(scope, "org_id", None) or DEFAULT_ORG_ID) if model is Department
        else None
    )
    if find_by_name(db, model, clean, org_id=dup_org) is not None:
        raise ConflictError(f"이미 있는 {label_for(model)}입니다: {clean}")
    row = model(name=clean, active=True)
    # 조직 지정. 안 보내면 **내가 관리하는 조직**에 만들고(스키마가 약속한 동작이다),
    # 범위가 없는 전역 관리자에게만 모델 기본값(DEFAULT_ORG_ID)이 남는다 - 예전 동작이다.
    # 범위가 있는데 기본값에 맡기면 다른 조직에 행이 생겨 만든 사람에게 안 보인다.
    # 보냈으면 **실재하는 조직인지 확인한다**: 없는 id 를 그대로 저장하면 그 부서는 어느
    # 조직 목록에도 안 나오면서 DB 에는 남는, 찾기 어려운 유령이 된다.
    target_org = org_id or getattr(scope, "org_id", None)
    if target_org:
        if db.get(Organization, target_org) is None:
            raise ValidationAppError("알 수 없는 조직입니다.")
        row.org_id = target_org
    if parent_id and model is Department:
        # 새 행이라 자기 자손이 있을 수 없다 — 존재와 **범위**만 확인하면 된다.
        parent = db.get(Department, parent_id)
        # UA-13: scope_allows_item만으로는 전역 관리자가 다른 조직의 부서를 부모로 지정하는
        # 것을 못 막는다(전역 관리자에게는 모든 행이 "범위 안"이다). 부모가 다른 조직이면
        # department_subtree_ids(parent_id 만 따라가는 순수 그래프 순회, org 필터 없음)가
        # 그 조직 부서를 dept 스코프 관리자의 서브트리에 끌어들여 권한이 조용히 넓어진다 —
        # 부모는 반드시 이 행과 같은 조직이어야 한다. dup_org 가 이미 이 행이 실제로 저장될
        # 조직(폴백 포함)과 같은 식이므로 그대로 쓴다.
        if parent is None or not scope_allows_item(scope, parent) or parent.org_id != dup_org:
            # 범위 밖 상위 부서는 **없는 것과 똑같이** 답한다. 여기만 다른 오류를 주면
            # 남의 부서 id 를 찍어 보며 존재를 셀 수 있다(저장소 규칙: 범위 밖은 404).
            raise ValidationAppError("알 수 없는 상위 부서입니다.")
        ensure_parent_is_active(parent)
        row.parent_id = parent_id
    for attempt in range(_CREATE_ITEM_RETRIES):
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            break
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            if attempt == _CREATE_ITEM_RETRIES - 1:
                # 예산 소진 — 진짜 동시 중복이든 낡은 스냅샷 재시도든, 사전 검사가
                # 잡았을 때와 같은 오류로 통일한다(클라이언트가 조금 늦게 요청했어도
                # 같은 응답을 받아야 한다).
                raise ConflictError(f"이미 있는 {label_for(model)}입니다: {clean}") from None
            try:
                # 스냅샷을 새로 뜨는 이 commit 자체도 8-way 이상의 경합에서 같은 이유로
                # 거부될 수 있다(실측: 새 race 시험에서 재현) — 처리 안 하면 그 자리에서
                # 예산이 남았는데도 raw OperationalError가 새 나간다. rollback으로 세션을
                # 정리하고 다음 반복에서 begin_nested()를 새로 연다.
                db.commit()
            except (IntegrityError, OperationalError) as commit_exc:
                if not is_insert_race(commit_exc):
                    raise
                db.rollback()
            time.sleep(write_conflict_backoff(attempt))
    # 목록·단건이 쓰는 **그 판정**을 만들어진 행에 그대로 건다. payload 가 아니라 행에 대고
    # 하는 이유는 `app/users/router.py::create_user_endpoint` 와 같다: 기본값 같은 세부가
    # 바뀌어도 세 경로가 갈라지지 않는다. 여기서 예외가 나면 `get_db` 가 롤백하므로 행은
    # 남지 않는다. 목록이 아니라 '생성 시도'라 숨길 존재가 없으므로 404 가 아니라 403 이다.
    if not scope_allows_item(scope, row):
        label = label_for(model)
        raise ForbiddenError(
            f"관리 범위 밖에는 {label}{object_particle(label)} 추가할 수 없습니다."
        )
    return row


def update_item(
    db: Session,
    row: OrgModel,
    *,
    name: str | None = _UNSET,
    active: bool | None = _UNSET,
    parent_id: str | None = _UNSET,
    scope=None,
) -> OrgModel:
    """이름을 바꾸면 이 항목을 쓰는 모든 사용자에게 그대로 반영된다 — 사용자가 원한
    바로 그 동작이다. 사용자 행은 하나도 건드리지 않는다(이름은 여기에만 있다).

    name/active는 '보내지 않음'(_UNSET, 이 필드는 그대로 둔다)과 '명시적으로 null을
    보냄'(값을 지우려는 시도, 필수 필드라 거부)을 구분한다 — 둘 다 그냥 None이면
    빈 이름 PATCH가 조용히 아무 일도 안 하면서 성공을 반환하게 된다.
    """
    if name is not _UNSET:
        if name is None:
            raise ValidationAppError("이름을 비워 둘 수 없습니다.")
        clean = normalize_name(name)
        # UA-12: create_item과 같은 이유로 모델별 실제 제약 범위를 따른다 — Department만
        # 조직 안에서 본다(JobTitle은 전역 유니크라 org_id로 좁히면 안 된다).
        existing = find_by_name(
            db, type(row), clean, org_id=row.org_id if isinstance(row, Department) else None
        )
        if existing is not None and existing.id != row.id:
            raise ConflictError(f"이미 있는 {label_for(type(row))}입니다: {clean}")
        row.name = clean
    if active is not _UNSET and active is not None:
        row.active = active
    if parent_id is not _UNSET:
        # 부서만 트리다. 직책 라우터는 애초에 이 필드를 받지 않는 스키마를 쓰지만(schemas.py),
        # CLI 등 다른 호출자가 실수로 넘겨도 조용히 무시되지 않도록 여기서도 못박는다.
        if not isinstance(row, Department):
            raise ValidationAppError(f"{label_for(type(row))}에는 상위 항목이 없습니다.")
        from app.org.tree import validate_parent

        # 생성만 막으면 수정으로 같은 일을 한다 — 상위 부서 판정은 두 경로가 함께 쓴다.
        row.parent_id = validate_parent(db, row, parent_id, scope=scope)
        # 옮긴 **뒤에도** 범위 안이어야 한다 (`create_item` 끝의 같은 문). 생성은 막혀
        # 있었는데 수정은 안 막혀서, 부서 범위 관리자가 자기 부서를 최상위로 밀어내고
        # 그 순간 자기도 그 부서를 못 보게 됐다(되돌리려면 전역 관리자가 필요하다).
        # 판정을 행에 대고 하는 이유도 생성과 같다 — 값이 아니라 결과를 본다.
        # 이 갈래는 부서뿐이다(바로 위에서 직책을 거절한다) — 그래서 조사를 짜 맞추지 않고
        # 「부서」라고 그대로 쓴다. 「을(를)」 같은 괄호 표기는 화면 문구가 아니다(§10).
        if not scope_allows_item(scope, row):
            raise ForbiddenError("관리 범위 밖으로 부서를 옮길 수 없습니다.")
    db.flush()
    return row


def _count_where(db: Session, *clauses) -> int:
    """조건에 맞는 행 수. `dependents` 와 `archived_dependents` 가 같은 식으로 센다."""
    return int(db.execute(select(func.count()).where(*clauses)).scalar_one())


def dependents(db: Session, dept_id: str) -> dict[str, int]:
    """이 부서를 **가리키고 있는 것**들의 건수 (0060 §33). 0 이 아닌 항목만 담는다.

    부서를 지우면 이것들이 어떻게 되는지가 문제인데, 참조마다 걸린 FK 가 다르다:

    * `SET NULL` — 사용자(`users.department_id`·`scope_dept_id`)와 하위 부서(`parent_id`).
      **오류가 나지 않는다.** 자식 부서는 조용히 최상위로 올라오고 사람은 소속이 빈칸이
      되며, 삭제한 사람에게는 성공으로 보인다.
    * `ondelete` 없음 — 프로젝트(`projects.dept_id`)·지식 공간(`knowledge_spaces.owner_dept_id`)·
      옛 문서 미러(`document_cache.owner_dept_id`). DB 가 삭제 자체를 거절하는데, 사용자가
      보는 것은 원인이 안 적힌 500 이다.
    * FK 없음 — 팀 채팅방(`chat_rooms.department_id`). DB 는 아무것도 막지 않고, 방은 없는
      부서를 가리킨 채 남는다.

    셋 다 여기서 미리 센다. 한 갈래라도 빠지면 그 갈래는 500 이거나 조용한 유령 참조다 —
    옛 문서와 채팅방이 실제로 그렇게 빠져 있었다.

    센 뒤에 `delete_item` 이 갈래를 **둘로 나눈다**: 지우면 조용히 깨지는 것은 막고
    (`BLOCKING_DEPENDENTS`), 부서를 잃어도 그대로 살아 있는 것은 삭제와 같은 트랜잭션에서
    떼어 낸다(`DETACHABLE_DEPENDENTS`). 세는 자리를 나누지 않는 이유는 화면이 「무엇이
    매달려 있나」를 한 번에 물어보기 때문이다.

    사용자 수(`usage_count`)만 세던 예전 판정은 사람이 한 명도 없는 부서를 "안 쓰는
    부서" 로 읽었다. 실제로는 프로젝트 수십 개와 그 아래 티켓 전부가 거기 매달려 있을 수
    있다.
    """
    from app.knowledge.models import Document, KnowledgeSpace
    from app.projects.models import Project
    from app.team_chat.models import ChatRoom
    from app.team_docs.models import DocumentCache
    from app.users.models import User
    from app.work.models import SPRINT_CLOSED, Sprint

    def _count(clause) -> int:
        return _count_where(db, clause)

    # 문서는 **공간을 거쳐** 이 부서에 매달린다 (D-245). `documents` 에는 소속 컬럼이
    # 아예 없다 — 권한을 공간이 정하기 때문이고, 그래서 부서를 지웠을 때 실제로 닫히는
    # 것은 「그 부서 소유 공간에 든 문서 전부」다.
    #
    # 공간과 문서를 **둘 다** 센다. 문서만 세면 문서가 아직 없는 공간이 0 건으로 나와
    # 삭제가 통과하는 것처럼 보이는데, 그때 DB 가 FK 로 거절해 원인이 안 적힌 오류가 된다.
    # 공간만 세면 반대로 "공간 1개" 라고만 말해 사람이 문서 수십 건을 잃는 줄 모른다.
    documents_in_dept_spaces = int(
        db.execute(
            select(func.count())
            .select_from(Document)
            .join(KnowledgeSpace, KnowledgeSpace.id == Document.space_id)
            .where(KnowledgeSpace.owner_dept_id == dept_id)
        ).scalar_one()
    )

    found = {
        "users": _count(User.department_id == dept_id),
        "child_departments": _count(Department.parent_id == dept_id),
        "projects": _count(Project.dept_id == dept_id),
        "knowledge_spaces": _count(KnowledgeSpace.owner_dept_id == dept_id),
        "documents": documents_in_dept_spaces,
        # 옛 문서 미러(S14 · D1). 사용자에게 보이는 경로는 이 표를 읽지 않지만 FK 는 살아
        # 있다 — 지식 공간과 같은 모양으로 DB 가 삭제를 거절해 원인 없는 500 이 됐다.
        # **떼어 내는 갈래다**: 화면에 존재하지도 않는 행이 부서를 영원히 잠갔다.
        "legacy_documents": _count(DocumentCache.owner_dept_id == dept_id),
        # 부서 방(`ensure_team_room` 이 게으르게 만든다). FK 가 없어 DB 는 막지 않는다 —
        # 지우면 방이 없는 부서를 가리킨 채 남는다. `deleted_at` 이 찍힌 방도 센다: 행은
        # 남아 있고 이 부서 id 를 쥐고 있다(보관된 사용자를 세는 이유와 같다).
        # 이것도 **떼어 내는 갈래다** — 방에 든 대화는 부서가 없어져도 사람들의 기록이다.
        "chat_rooms": _count(ChatRoom.department_id == dept_id),
        # 이 부서를 **관리 범위로 배정받은** 관리자. 지우면 그 계정은 관리 대상이 없는
        # 상태가 되는데, 화면에는 "관리 범위: 지정된 부서 없음" 으로만 보인다.
        "scoped_admins": _count(User.scope_dept_id == dept_id),
        # 회차(D-533) — `sprints.department_id` 는 `SET NULL` 이라 지우면 그 팀의 회차가 조용히 「팀 미정」이 된다. 진행 · 예정
        # 회차는 팀 사용자에게서 사라지고 담기 · 열기가 막히므로 **막는다**. 닫힌 회차는 지난 기록이라 **떼어 낸다** — 회차의
        # 팀은 바꿀 수 없어서 닫힌 회차까지 막으면 지울 수 없는 부서가 생긴다(`detach_dependents`).
        "open_sprints": _count_where(db, Sprint.department_id == dept_id, Sprint.state != SPRINT_CLOSED),
        "closed_sprints": _count_where(db, Sprint.department_id == dept_id, Sprint.state == SPRINT_CLOSED),
    }
    return {k: v for k, v in found.items() if v}


_DEPENDENT_LABELS = {
    "users": "소속 사용자",
    "child_departments": "하위 부서",
    "projects": "프로젝트",
    "knowledge_spaces": "지식 공간",
    "documents": "그 공간에 든 문서",
    "legacy_documents": "옛 문서 기록",
    "chat_rooms": "팀 채팅방",
    "scoped_admins": "이 부서를 관리 범위로 가진 관리자",
    "open_sprints": "진행 중이거나 예정된 회차",
    "closed_sprints": "닫힌 회차",
}

#: 갈래마다 **세는 단위**. 사람은 「명」, 셀 수 있는 것은 「개」, 기록(문서)은 「건」이다.
#:
#: 🔴 한 문장이 같은 사람을 두 단위로 셌다. 「소속 사용자 1건이 연결되어 있어 …
#: 그중 보관된 계정 1명은 …」 — 읽는 사람은 1건과 1명이 같은 행인지 다른 행인지 끝내 알 수
#: 없다. 아래 `_ARCHIVED_LABELS` 가 이미 사람을 「명」으로 세고 있었으므로, 갈라진 쪽은
#: 여기다. 「이 부서를 관리 범위로 가진 관리자」도 사람이라 같은 단위를 쓴다.
#:
#: 셀 수 있는 것(부서 · 프로젝트 · 공간 · 방 · 회차)은 「개」다(D-533 — 「프로젝트 24개」). 「건」은 문서처럼 기록을 셀 때만 쓴다.
_DEPENDENT_UNITS = {
    "users": "명", "scoped_admins": "명",
    "child_departments": "개", "projects": "개", "knowledge_spaces": "개", "chat_rooms": "개",
    "open_sprints": "개", "closed_sprints": "개",
}


def _counted(kind: str, count: int) -> str:
    """「소속 사용자 2명」·「프로젝트 3건」. 라벨과 단위를 한 자리에서 붙인다."""
    return f"{_DEPENDENT_LABELS[kind]} {count}{_DEPENDENT_UNITS.get(kind, '건')}"


#: 보관된 갈래를 사람이 읽는 이름과 세는 단위. 「보관된 소속 사용자 1건」이 아니라
#: 「보관된 계정 1명」이라고 말해야 관리자가 어디를 찾아야 하는지 안다.
_ARCHIVED_LABELS = {
    "users": ("보관된 계정", "명"),
    "projects": ("보관된 프로젝트", "개"),
    "knowledge_spaces": ("보관된 지식 공간", "개"),
}

#: 지우면 **조용히 깨지거나 사라지는** 갈래. 부서 삭제를 막는다.
BLOCKING_DEPENDENTS = (
    "users", "child_departments", "projects", "knowledge_spaces", "documents", "scoped_admins", "open_sprints",
)

#: 부서를 잃어도 **그 자체로 살아 있는** 갈래. 막지 않고 삭제와 같은 트랜잭션에서 떼어 낸다.
#:
#: 막아 두면 빠져나갈 길이 없다는 것이 실측으로 드러났다. 부서 팀 방은 그 부서 사람이
#: 채팅 목록을 한 번만 열어도 `app/team_chat/service.py::ensure_team_room` 이 만드는데,
#: 그 방은 방장이 없어 아무도 파할 수 없고 방의 부서를 바꾸는 경로도 제품에 없다. 옛 문서
#: 기록은 화면에 존재조차 하지 않는다. 그래서 「사람이 한 번이라도 있었던 부서」가 영영
#: 안 지워졌다 — 막는 대신 연결만 끊는다. 방의 대화도, 옛 기록도 지우지 않는다.
DETACHABLE_DEPENDENTS = ("chat_rooms", "legacy_documents", "closed_sprints")


def archived_dependents(db: Session, dept_id: str) -> dict[str, int]:
    """막는 갈래 중 **보관되어 화면에서 안 보이는** 것의 건수. 0 이 아닌 항목만 담는다.

    보관된 프로젝트·지식 공간·계정도 부서를 쥐고 있어 삭제를 막는데, 관리자가 보는 목록에는
    그것이 없다 — 「프로젝트 1건」이라고만 답하면 그 1건을 끝내 못 찾는다(xc-04). 사람도
    같다: 부서에 남은 마지막 한 명이 퇴사자(보관 계정)이면 인원 목록은 0명이라고 말하면서
    삭제는 막힌다(org-08).
    """
    from app.knowledge.models import KnowledgeSpace
    from app.projects.models import Project
    from app.users.models import User

    found = {
        "users": _count_where(
            db, User.department_id == dept_id, User.archived_at.is_not(None)
        ),
        "projects": _count_where(
            db, Project.dept_id == dept_id, Project.archived_at.is_not(None)
        ),
        "knowledge_spaces": _count_where(
            db, KnowledgeSpace.owner_dept_id == dept_id, KnowledgeSpace.archived.is_(True)
        ),
    }
    return {k: v for k, v in found.items() if v}


def _blocked_summary(blocking: dict[str, int]) -> str:
    """삭제가 막힌 이유의 첫 문장만 - `_blocked_message` 의 앞머리와 같은 말이다."""
    parts = ", ".join(_counted(k, v) for k, v in blocking.items())
    return f"이 부서에 {parts}{subject_particle(parts)} 연결되어 있어 삭제할 수 없습니다."


def _blocked_message(blocking: dict[str, int], archived: dict[str, int]) -> str:
    """삭제가 막힌 이유 한 문장. **409 와 화면의 삭제 안내가 이 문장을 함께 쓴다.**

    화면이 자기 계산으로 같은 말을 다시 만들면 둘이 갈라진다 — 실제로 화면은 인원과 하위
    부서만 세어 「지금 삭제할 수 있습니다」라고 말했고 실행하면 409 였다(org-01).
    """
    parts = ", ".join(_counted(k, v) for k, v in blocking.items())
    hidden = ""
    if archived:
        names = ", ".join(
            f"{_ARCHIVED_LABELS[k][0]} {v}{_ARCHIVED_LABELS[k][1]}" for k, v in archived.items()
        )
        hidden = f" 그중 {names}{topic_particle(names)} 목록에 보이지 않으니 보관된 항목도 함께 확인해 주세요."
    return (
        # 조사는 앞 조각의 끝 글자 받침으로 고른다 — 「N개」로 끝나면 「가」, 「N명」 · 「N건」이면 「이」다(「이(가)」 같은
        # 괄호 표기를 쓰지 않는다 — 화면 문구는 완전한 한 문장이어야 한다, CLAUDE.md §10).
        f"이 부서에 {parts}{subject_particle(parts)} 연결되어 있어 삭제할 수 없습니다.{hidden}"
        " 먼저 연결된 항목을 다른 부서로 옮기세요. 또는 '비활성'으로 두면 새로 고를 수는 없지만 기존 연결은"
        " 그대로 유지됩니다."
    )


def detached_message(detached: dict[str, int]) -> str:
    """떼어 낸 것을 말하는 한 문장. 조용히 끊으면 나중에 「왜 이 방이 부서를 잃었나」를
    아무도 설명할 수 없다."""
    names = ", ".join(_counted(k, v) for k, v in detached.items())
    return f"{names}{topic_particle(names)} 부서 연결만 끊고 그대로 두었습니다."


def detach_dependents(db: Session, dept_id: str) -> dict[str, int]:
    """부서를 잃어도 살아 있는 참조를 **삭제와 같은 트랜잭션에서** 끊는다.

    끊는 것이지 지우는 것이 아니다. 팀 방에는 사람들이 쓴 대화가 들어 있고, 옛 문서 기록은
    이관 이력이다 — 부서 하나를 정리한다고 없앨 것이 아니다. 그러니 그 행들은 남고,
    「이 부서 것」이라는 표시만 사라진다.

    옛 문서 기록은 `owner_kind` 도 함께 미지정으로 되돌린다. 「부서 소유인데 부서가 없다」는
    행은 어느 갈래에도 안 걸려, 나중에 그 기록을 찾는 사람이 원인을 알 수 없다.
    """
    from sqlalchemy import update

    from app.core.ownership import OWNER_UNSET
    from app.team_chat.models import ChatRoom
    from app.team_docs.models import DocumentCache
    from app.work.models import SPRINT_CLOSED, Sprint

    rooms = db.execute(
        update(ChatRoom)
        .where(ChatRoom.department_id == dept_id)
        .values(department_id=None)
        .execution_options(synchronize_session=False)
    ).rowcount
    legacy = db.execute(
        update(DocumentCache)
        .where(DocumentCache.owner_dept_id == dept_id)
        .values(owner_dept_id=None, owner_kind=OWNER_UNSET)
        .execution_options(synchronize_session=False)
    ).rowcount
    # 닫힌 회차는 「팀 미정」으로 남긴다(D-533). 이름은 조직 안 팀 미정 회차끼리 유일해야 하므로(`uq_sprints_name`) 겹치면 옛
    # 부서 이름을 붙인다 — 「9-2」가 둘이 되는 대신 「9-2 (플랫폼개발팀)」이다. 겹치지 않으면 이름을 그대로 둔다.
    closed = list(db.execute(
        select(Sprint).where(Sprint.department_id == dept_id, Sprint.state == SPRINT_CLOSED).order_by(Sprint.created_at)
    ).scalars())
    if closed:
        dept_row = db.get(Department, dept_id)
        dept_name = dept_row.name if dept_row else ""
        taken = {
            (org_id, name) for org_id, name in db.execute(
                select(Sprint.org_id, Sprint.name).where(Sprint.department_id.is_(None))
            ).all()
        }
        for sprint in closed:
            name = sprint.name
            if (sprint.org_id, name) in taken:
                n = 1
                while True:
                    suffix = f" ({dept_name})" if n == 1 else f" ({dept_name} {n})"
                    name = sprint.name[: 120 - len(suffix)] + suffix
                    if (sprint.org_id, name) not in taken:
                        break
                    n += 1
            sprint.name = name
            sprint.department_id = None
            taken.add((sprint.org_id, name))
    db.flush()
    detached = {
        "chat_rooms": int(rooms or 0), "legacy_documents": int(legacy or 0), "closed_sprints": len(closed),
    }
    return {k: v for k, v in detached.items() if v}


def delete_precheck(db: Session, dept_id: str) -> dict:
    """지금 이 부서를 지울 수 있는가. **서버가 한 번 판정하고 화면은 그것을 그린다.**

    화면이 자기 계산으로 판정하면 서버가 막는 것과 달라진다 — 상세 판은 인원과 하위 부서
    둘만 세어 「지금 삭제할 수 있습니다」라고 말했고, 눌러 보면 409 였다(org-01). 그래서
    갈래·건수·라벨·이유 문장까지 여기서 만들어 응답에 싣는다.
    """
    found = dependents(db, dept_id)
    archived = archived_dependents(db, dept_id)
    blocking = {k: v for k, v in found.items() if k in BLOCKING_DEPENDENTS}
    detachable = {k: v for k, v in found.items() if k in DETACHABLE_DEPENDENTS}
    hidden = {k: v for k, v in archived.items() if k in blocking}
    return {
        "deletable": not blocking,
        "blockers": [
            {
                "kind": kind,
                "label": _DEPENDENT_LABELS[kind],
                "count": count,
                "unit": _DEPENDENT_UNITS.get(kind, "건"),
                "archived_count": hidden.get(kind, 0),
            }
            for kind, count in blocking.items()
        ],
        "detachables": [
            {"kind": kind, "label": _DEPENDENT_LABELS[kind], "count": count, "unit": _DEPENDENT_UNITS.get(kind, "건")}
            for kind, count in detachable.items()
        ],
        "reason": (
            _blocked_message(blocking, hidden) if blocking
            else detached_message(detachable) if detachable
            else None
        ),
        # 판에 먼저 서는 한 문장(계획 3.6). 긴 이유(보관 계정 안내 · 대안)는 `reason` 이 들고 화면이 「자세히」로 편다.
        "summary": _blocked_summary(blocking) if blocking else None,
    }


def department_impact(db: Session, dept_id: str) -> dict:
    """부서를 지우거나 비활성화하면 무엇이 달라지는가 (D-533). 화면이 **열 때만** 묻는다.

    상세 GET 이 판정을 늘 싣던 동안에는 부서를 고를 때마다 COUNT 열두어 번을 돌았고, 평소 화면이 「지울 수 없습니다」를
    늘 보여 줬다. 이제 「삭제」 · 「비활성화」를 누를 때 이 함수 하나가 답한다 — 삭제 판정은 `delete_precheck`(409 와 같은
    문장)이고, 비활성화는 지워지지 않고 남는 것들의 수다(새 배치 · 새 하위 부서만 막힌다).
    """
    from app.projects.models import Project
    from app.users.models import User

    found = dependents(db, dept_id)
    return {
        "delete": delete_precheck(db, dept_id),
        "deactivate": {
            "members": _count_where(db, User.department_id == dept_id, User.archived_at.is_(None)),
            "child_departments": found.get("child_departments", 0),
            "projects": _count_where(db, Project.dept_id == dept_id, Project.archived_at.is_(None)),
            "scoped_admins": found.get("scoped_admins", 0),
            "open_sprints": found.get("open_sprints", 0),
        },
    }


def organization_impact(db: Session, org_id: str) -> dict:
    """조직을 비활성화하면 누가 로그아웃되는가 (D-533).

    예전 확인 창은 조직의 사람 수(`user_count` — 보관 · 비활성 계정과 시스템 관리자까지 센 수)를 「로그아웃될 사람」으로
    말했다. 실제로 끊기는 사람은 지금 쓸 수 있는 계정(활성 · 보관 안 됨) 가운데 시스템 관리자가 아닌 사람이다 — 시스템
    관리자는 정지를 풀 사람이 남도록 끊지 않는다(`router._revoke_org_sessions` 가 끊는 대상 중 지금 로그인할 수 있는 계정만 센다).
    """
    from app.users.models import User

    in_org = (User.org_id == org_id,)
    live = (*in_org, User.archived_at.is_(None))
    return {
        "suspend": {
            "signed_out_users": _count_where(db, *live, User.active.is_(True), User.role != "system_admin"),
            "exempt_system_admins": _count_where(db, *live, User.active.is_(True), User.role == "system_admin"),
            "inactive_users": _count_where(db, *live, User.active.is_(False)),
            "archived_users": _count_where(db, *in_org, User.archived_at.is_not(None)),
        },
    }


def delete_item(db: Session, row: OrgModel) -> dict[str, int]:
    """**조용히 깨지는 것이 하나라도 있으면** 거부한다. 떼어 낸 것을 돌려준다.

    조용히 지우면 `SET NULL` 참조는 소리 없이 빈칸이 되고, 나머지는 DB 가 원인 없는
    500 으로 거절한다(갈래별 FK 는 `dependents` 참조). 무엇이 몇 건 매달려 있는지와
    대안(비활성)을 함께 알려 준다 — 막기만 하면 사용자는 다음에 무엇을 해야 할지 알 수 없다.

    막지 않는 갈래는 `DETACHABLE_DEPENDENTS` 다. 그 둘까지 막았더니 부서 하나를 지우는 데
    제품 안에 길이 없었다 — 409 가 안내하는 「다른 부서로 옮기기」가 팀 방에는 존재하지
    않는 경로였기 때문이다. 이제 그 둘은 같은 트랜잭션에서 연결만 끊고, 남은 갈래에 대해서만
    409 를 낸다. 그래서 409 의 안내가 실제로 밟을 수 있는 길이 된다.

    부서는 사람 말고도 프로젝트·문서·하위 부서·관리 범위가 매달린다(0060 §33). 직책에는
    사용자만 매달리므로 예전 판정을 그대로 쓴다.
    """
    model = type(row)
    label = label_for(model)
    detached: dict[str, int] = {}
    if model is Department:
        found = dependents(db, row.id)
        blocking = {k: v for k, v in found.items() if k in BLOCKING_DEPENDENTS}
        if blocking:
            archived = {
                k: v for k, v in archived_dependents(db, row.id).items() if k in blocking
            }
            raise ConflictError(
                _blocked_message(blocking, archived),
                details={
                    "name": row.name,
                    "user_count": blocking.get("users", 0),
                    **blocking,
                    "archived": archived,
                },
            )
        # 지우기 **전에** 끊는다 — 옛 문서 기록의 FK 에는 ondelete 가 없어서 순서가 바뀌면
        # DB 가 삭제를 거절하고 사용자는 원인이 안 적힌 500 을 본다.
        detached = detach_dependents(db, row.id)
    else:
        count = usage_count(db, model, row.id)
        if count:
            raise ConflictError(
                f"이 {label}{object_particle(label)} 쓰는 사용자가 {count}명 있어 삭제할 수 없습니다. "
                f"'비활성'으로 두면 새로 고를 수는 없지만 기존 사용자는 그대로 유지됩니다.",
                details={"user_count": count, "name": row.name},
            )
    db.delete(row)
    db.flush()
    return detached


def item_view(
    row: OrgModel, *, user_count: int | None = None, org_name: str | None = None,
    child_department_count: int | None = None,
) -> dict:
    view = {
        "id": row.id,
        "name": row.name,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
    }
    # 부서만 트리다 — 직책 응답에 항상 null 인 parent_id 를 붙이면 '직책도 계층이 있나?'
    # 하는 오해만 남는다. 있는 모델에서만 싣는다(추가 키라 기존 화면은 그대로 동작한다).
    if isinstance(row, Department):
        view["parent_id"] = row.parent_id
        # 어느 조직의 부서인지 화면에서 보여야 한다 — 사용자 지적 P5 의 핵심은
        # "연결이 없다" 였고, 연결을 만들어 놓고 화면에 안 보이면 같은 말을 다시 듣는다.
        #
        # 이름은 **인자로 받는다**. `Department` 에는 `organization` 관계가 없다 —
        # `OrgScopedMixin` 이 FK 를 선언하지만 마이그레이션이 그 제약을 만든 적이 없어서
        # (0024 가 의도적으로 건너뜀) 관계를 붙이면 스키마와 모델이 또 어긋난다.
        # 세션을 가진 라우터가 한 번 조회해 넘긴다.
        view["org_id"] = row.org_id
        view["org_name"] = org_name
        # UA-20R: 삭제 확인 문구가 인원수만 말하고 자식 부서 수는 말하지 않았다.
        if child_department_count is not None:
            view["child_department_count"] = child_department_count
    if user_count is not None:
        view["user_count"] = user_count
    return view


def resolve_assignable(
    db: Session,
    model: type[OrgModel],
    item_id: str | None,
    *,
    allow_current: str | None = None,
) -> OrgModel | None:
    """사용자에게 배정할 항목을 검증하고 **행 자체**를 돌려준다.

    id가 아니라 행을 주는 이유: 부르는 쪽이 user.department_id에 id를 직접 넣으면
    관계(user.department_ref)는 이 세션이 만료될 때까지 옛 값을 들고 있어, 방금 바꾼
    응답이 바뀌기 전 이름을 그대로 보여 준다(CLAUDE.md §8의 "원시 UPDATE 후 refresh
    필요"와 같은 함정). 관계에 행을 넣으면 FK와 이름이 함께 따라온다.

    없는 id를 그대로 두면 FK 위반이 500으로 터지고, 비활성 항목을 새로 고를 수 있으면
    '비활성'이 아무 뜻도 없어진다.

    ``allow_current``는 이 사용자에게 **이미 배정돼 있는** 항목 id다. 그 값과 같으면
    비활성이어도 허용한다 — 관리자가 비활성 직책을 가진 사용자의 이름만 바꾸려 해도
    수정 폼이 모든 select를 다시 보내므로(같은 id 재전송), 이 예외가 없으면 저장이
    통째로 막힌다. 새로 '비활성' 항목을 지정하는 것은 여전히 거부한다.
    """
    if item_id is None:
        return None
    row = db.get(model, item_id)
    label = label_for(model)
    if row is None:
        raise ValidationAppError(f"알 수 없는 {label}입니다.")
    if not row.active and item_id != allow_current:
        raise ValidationAppError(
            f"비활성 {label}{topic_particle(label)} 새로 지정할 수 없습니다: {row.name}"
        )
    return row


def resolve_by_name_or_error(db: Session, model: type[OrgModel], name: str | None) -> str | None:
    """CLI용 — 사람은 uuid가 아니라 이름을 친다. 없으면 고를 수 있는 이름을 함께 알린다
    (없는 이름을 조용히 만들어 주면 자유 입력 시절로 돌아간다)."""
    if name is None:
        return None
    clean = normalize_name(name)
    row = find_by_name(db, model, clean)
    label = label_for(model)
    if row is None:
        available = [r.name for r in list_items(db, model, active=True)]
        hint = ", ".join(available) if available else "(등록된 항목 없음)"
        raise ValidationAppError(f"알 수 없는 {label}입니다: {clean}. 등록된 {label}: {hint}")
    if not row.active:
        raise ValidationAppError(
            f"비활성 {label}{topic_particle(label)} 새로 지정할 수 없습니다: {clean}"
        )
    return row.id


# ── 조직 정지가 실제로 효력을 갖게 하는 판정 (X5) ──────────────────────────────
#
# 정지 버튼·상태 표시·감사 로그는 다 있었는데 **`ORG_SUSPENDED` 를 읽는 코드가 하나도
# 없었다.** 그 조직 사람들은 계속 로그인하고 계속 썼다. 관리자는 실패도 경고도 없이
# "했다" 는 확인만 받는다 — 시스템이 하지 않은 일을 했다고 말하는 부류다.
#
# 판정은 여기 한 곳에 둔다. 로그인 거부와 세션 검증 두 곳이 같은 함수를 부른다 —
# 두 벌이 되면 한쪽만 고쳐지고, 그때 증상은 "정지했는데 아직 쓰고 있다" 다.

_PORTAL_ROLE = "system_admin"


def is_blocked_by_org_suspension(db: Session, user) -> bool:
    """이 사람이 정지된 조직 소속이라 막혀야 하는가.

    **`system_admin` 은 예외다.** 그 사람은 테넌트의 구성원이 아니라 포탈 운영자이고,
    막으면 조직을 정지시킨 순간 **정지를 풀 사람이 없어진다**(자기 자신을 잠근다).
    """
    if getattr(user, "role", None) == _PORTAL_ROLE:
        return False
    org_id = getattr(user, "org_id", None)
    if not org_id:
        return False
    org = db.get(Organization, org_id)
    return org is not None and org.status == ORG_SUSPENDED


def ensure_may_suspend_org(actor, org_id: str) -> None:
    """자기 조직 비활성화는 포탈 운영자(`system_admin`)만 할 수 있다.

    ## 화면이 쓰는 낱말로 말한다

    이 동작을 사용자에게 부르는 이름은 **「비활성화」** 하나다 — 버튼도, 확인 창도, 판의
    안내도 그렇게 쓴다(`OrgDetailPanel.jsx`). 서버만 「정지」라고 답하면 거절 문구를 읽은
    관리자가 자기가 누른 것과 거절당한 것이 같은 동작인지 다시 생각해야 한다. 저장 값
    (`status = "suspended"`)은 그대로 두고 사람에게 보이는 말만 맞춘다.

    정지는 그 조직 구성원의 세션을 **즉시** 전부 끊는다(`app/org/router.py::_revoke_org_sessions`).
    일반 관리자가 자기 조직을 정지시키면 그 요청을 낸 세션까지 끊겨, 정지를 건 사람도
    풀 사람도 조직 안에 없는 상태가 된다 — 클릭 한 번에 테넌트 하나가 잠기고 되살릴 수
    있는 것은 포탈 운영자뿐이다. 그래서 끊기지 않는 유일한 역할(`is_blocked_by_org_suspension`
    이 예외로 두는 같은 `_PORTAL_ROLE`)에게만 허용한다.

    다른 조직을 정지시키는 것은 이 함수의 대상이 아니다 — 자기 세션이 끊기지 않으므로
    범위 판정(`_visible_org_or_404`)만 지나면 예전 계약 그대로다.

    404 가 아니라 **403** 이다: 자기 조직은 이미 화면에 보이는 행이라 숨길 존재가 없고,
    문제는 존재가 아니라 권한이다.
    """
    if getattr(actor, "role", None) == _PORTAL_ROLE:
        return
    if getattr(actor, "org_id", None) == org_id:
        raise ForbiddenError("자기 조직은 시스템 관리자만 비활성화할 수 있습니다.")
