"""부서·직책 명부 서비스 — 웹 API와 CLI가 같이 쓴다(§29).

부서와 직책은 규칙이 같아서 한 벌의 함수가 모델 클래스를 받아 처리한다. 규칙을 두 벌
적으면 한쪽만 고쳐지고, 그러면 '직책은 삭제되는데 부서는 안 되는' 식으로 갈라진다.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import and_ as sa_and, func, or_ as sa_or, select
from sqlalchemy.orm import Session

from app.org.constants import ORG_SUSPENDED
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
        raise NotFoundError(f"{label_for(model)}을(를) 찾을 수 없습니다.")
    if not scope_allows_item(scope, row):
        raise NotFoundError(f"{label_for(model)}을(를) 찾을 수 없습니다.")
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
    # 중복 검사는 **만들려는 조직 안에서만** 한다(유니크 제약이 `(org_id, name)` 이다).
    # 전역으로 보면 남의 조직 이름을 409 로 확인할 수 있다.
    # 아래에서 실제로 정하는 조직과 **같은 식**을 쓴다(두 벌이 되면 검사와 저장이 어긋난다).
    dup_org = org_id or getattr(scope, "org_id", None)
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
        if parent is None or not scope_allows_item(scope, parent):
            # 범위 밖 상위 부서는 **없는 것과 똑같이** 답한다. 여기만 다른 오류를 주면
            # 남의 부서 id 를 찍어 보며 존재를 셀 수 있다(저장소 규칙: 범위 밖은 404).
            raise ValidationAppError("알 수 없는 상위 부서입니다.")
        row.parent_id = parent_id
    db.add(row)
    db.flush()
    # 목록·단건이 쓰는 **그 판정**을 만들어진 행에 그대로 건다. payload 가 아니라 행에 대고
    # 하는 이유는 `app/users/router.py::create_user_endpoint` 와 같다: 기본값 같은 세부가
    # 바뀌어도 세 경로가 갈라지지 않는다. 여기서 예외가 나면 `get_db` 가 롤백하므로 행은
    # 남지 않는다. 목록이 아니라 '생성 시도'라 숨길 존재가 없으므로 404 가 아니라 403 이다.
    if not scope_allows_item(scope, row):
        raise ForbiddenError(f"관리 범위 밖에는 {label_for(model)}을(를) 만들 수 없습니다.")
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
            raise ValidationAppError("이름을 비워둘 수 없습니다.")
        clean = normalize_name(name)
        # 수정도 같은 조직 안에서만 본다 — 생성과 규칙이 갈리면 한쪽으로 이름이 샌다.
        existing = find_by_name(db, type(row), clean, org_id=row.org_id)
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
    db.flush()
    return row


def delete_item(db: Session, row: OrgModel) -> None:
    """쓰는 사람이 있으면 거부한다.

    조용히 지우면 그 사람들의 부서가 소리 없이 빈칸이 된다(FK가 SET NULL이므로 오류도
    나지 않는다). 몇 명이 쓰는지와 대안(비활성)을 함께 알려 준다 — 막기만 하면 사용자는
    다음에 무엇을 해야 할지 알 수 없다.
    """
    model = type(row)
    count = usage_count(db, model, row.id)
    if count:
        label = label_for(model)
        raise ConflictError(
            f"이 {label}을(를) 쓰는 사용자가 {count}명 있어 삭제할 수 없습니다. "
            f"'비활성'으로 두면 새로 고를 수는 없지만 기존 사용자는 그대로 유지됩니다.",
            details={"user_count": count, "name": row.name},
        )
    db.delete(row)
    db.flush()


def item_view(
    row: OrgModel, *, user_count: int | None = None, org_name: str | None = None
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
        raise ValidationAppError(f"비활성 {label}은(는) 새로 지정할 수 없습니다: {row.name}")
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
        raise ValidationAppError(f"알 수 없는 {label}입니다: {clean}: 등록된 {label}: {hint}")
    if not row.active:
        raise ValidationAppError(f"비활성 {label}은(는) 새로 지정할 수 없습니다: {clean}")
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
