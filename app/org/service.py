"""부서·직책 명부 서비스 — 웹 API와 CLI가 같이 쓴다(§29).

부서와 직책은 규칙이 같아서 한 벌의 함수가 모델 클래스를 받아 처리한다. 규칙을 두 벌
적으면 한쪽만 고쳐지고, 그러면 '직책은 삭제되는데 부서는 안 되는' 식으로 갈라진다.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.org.models import Department, JobTitle

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


def get_or_404(db: Session, model: type[OrgModel], item_id: str) -> OrgModel:
    row = db.get(model, item_id)
    if row is None:
        raise NotFoundError(f"{label_for(model)}을(를) 찾을 수 없습니다.")
    return row


def find_by_name(db: Session, model: type[OrgModel], name: str) -> OrgModel | None:
    # 대소문자만 다른 이름(예: 'Sales' vs 'sales', 'ClovirONE팀' vs 'ClovirOne팀')은
    # 사람 눈엔 같은 부서/직책으로 보인다 — 모델 docstring이 바로 이 시나리오를 유일
    # 제약의 근거로 든다. 대소문자까지 정확히 같아야만 걸리던 예전 비교로는 그 시나리오를
    # 실제로 막지 못했다.
    return db.execute(
        select(model).where(func.lower(model.name) == name.lower())
    ).scalar_one_or_none()


def list_items(db: Session, model: type[OrgModel], *, active: bool | None = None):
    stmt = select(model)
    if active is not None:
        stmt = stmt.where(model.active.is_(active))
    return db.execute(stmt.order_by(model.name)).scalars().all()


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


def create_item(db: Session, model: type[OrgModel], *, name: str) -> OrgModel:
    clean = normalize_name(name)
    if find_by_name(db, model, clean) is not None:
        raise ConflictError(f"이미 있는 {label_for(model)}입니다: {clean}")
    row = model(name=clean, active=True)
    db.add(row)
    db.flush()
    return row


def update_item(
    db: Session,
    row: OrgModel,
    *,
    name: str | None = _UNSET,
    active: bool | None = _UNSET,
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
        existing = find_by_name(db, type(row), clean)
        if existing is not None and existing.id != row.id:
            raise ConflictError(f"이미 있는 {label_for(type(row))}입니다: {clean}")
        row.name = clean
    if active is not _UNSET and active is not None:
        row.active = active
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


def item_view(row: OrgModel, *, user_count: int | None = None) -> dict:
    view = {
        "id": row.id,
        "name": row.name,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
    }
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
        raise ValidationAppError(f"알 수 없는 {label}입니다: {clean} — 등록된 {label}: {hint}")
    if not row.active:
        raise ValidationAppError(f"비활성 {label}은(는) 새로 지정할 수 없습니다: {clean}")
    return row.id
