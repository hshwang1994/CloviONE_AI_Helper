"""조직도 트리 — `Department.parent_id`(0024) 를 실제로 읽는 곳.

0024 가 부모 컬럼을 심었지만 그때까지 그 값을 **보여 주는 화면이 없었다**. 부모를 지정할 수도,
누가 누구 밑인지 확인할 수도 없으니 컬럼은 있으나 마나였다. 여기서 두 가지를 준다:

  1. **평탄화된 트리** — 관리 콘솔의 목록 화면 하나(`DataScreen`)가 그대로 그릴 수 있게 트리를
     깊이 우선 순서의 행 목록으로 편다. 트리를 그리려고 새 화면 규격을 만들지 않는다:
     파일 탐색기처럼 `depth` 만큼 들여쓴 이름 열이면 표 하나로 조직도가 된다.
  2. **부모 지정의 안전장치** — 자기 자신·자기 자손을 부모로 지정하면 트리가 사이클이 되고,
     `app/core/scope.py::department_subtree_ids` 는 사이클에서도 멈추도록 이미 방어돼 있지만
     그건 '이미 망가진 데이터에서 프로세스를 지키는' 장치이지 데이터를 지키는 장치가 아니다.
     들어오는 순간 막는다.

하위 부서 전개 규칙 자체(`department_subtree_ids`)는 `app/core/scope.py` 한 곳에만 있다 —
여기서 두 번째 구현을 만들지 않는다.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.core.scope import MAX_DEPARTMENT_DEPTH, department_subtree_ids
from app.org.models import Department

# 경로 표기의 구분자. '›' 는 부서 이름에 쓰일 일이 사실상 없고, 화면에서 계층으로 읽힌다.
PATH_SEP = " › "


def _direct_user_counts(db: Session) -> dict[str, int]:
    """부서별 소속 인원(직접). 보관된 사용자도 센다 — `app/org/service.py::usage_count` 와
    **같은 규칙**이어야 한다(두 화면이 다른 숫자를 보여 주면 어느 쪽을 믿을지 알 수 없다)."""
    from app.users.models import User

    rows = db.execute(
        select(User.department_id, func.count())
        .where(User.department_id.is_not(None))
        .group_by(User.department_id)
    ).all()
    return {dept_id: count for dept_id, count in rows}


def _children_map(rows: list[Department]) -> dict[str | None, list[Department]]:
    known = {row.id for row in rows}
    children: dict[str | None, list[Department]] = {}
    for row in rows:
        # 부모가 목록에 없으면(데이터 이상) 최상위로 올려 보여 준다 — 안 그러면 그 부서와 그
        # 아래 전체가 화면에서 통째로 사라진다(조용한 소실이 가장 나쁜 실패다).
        parent = row.parent_id if row.parent_id in known else None
        children.setdefault(parent, []).append(row)
    for bucket in children.values():
        bucket.sort(key=lambda r: r.name)
    return children


def build_rows(db: Session, rows: list[Department]) -> list[dict]:
    """깊이 우선 평탄화 + 서브트리 인원 합계.

    사이클이 있으면(부모가 서로를 가리키는 상태) 그 덩어리는 루트에서 닿지 않는다 —
    빠뜨리지 않고 맨 뒤에 `cycle: true` 로 붙여 **눈에 보이게** 한다. 조용히 감추면
    "부서가 목록에서 사라졌다"는 신고만 남고 원인은 영영 안 보인다.
    """
    by_id = {row.id: row for row in rows}
    children = _children_map(rows)
    direct = _direct_user_counts(db)

    out: list[dict] = []
    seen: set[str] = set()

    def _emit(row: Department, depth: int, path: list[str], *, cycle: bool = False) -> int:
        """이 부서와 그 아래를 순서대로 out 에 넣고 **서브트리 인원 합**을 돌려준다."""
        seen.add(row.id)
        here = path + [row.name]
        index = len(out)
        kids = children.get(row.id, []) if depth < MAX_DEPARTMENT_DEPTH else []
        parent = by_id.get(row.parent_id) if row.parent_id else None
        out.append({
            "id": row.id,
            "name": row.name,
            "depth": depth,
            "path": PATH_SEP.join(here),
            "parent_id": row.parent_id,
            "parent_name": parent.name if parent else None,
            "active": row.active,
            "user_count": direct.get(row.id, 0),
            "child_count": len(kids),
            "cycle": cycle,
            "created_at": row.created_at.isoformat(),
        })
        total = direct.get(row.id, 0)
        for kid in kids:
            if kid.id in seen:
                continue
            total += _emit(kid, depth + 1, here)
        out[index]["subtree_user_count"] = total
        return total

    for root in children.get(None, []):
        _emit(root, 0, [])
    # 루트에서 닿지 않은 것들 = 사이클에 갇힌 덩어리.
    for row in rows:
        if row.id not in seen:
            _emit(row, 0, [], cycle=True)
    return out


def tree_rows(db: Session, *, active: bool | None = None) -> list[dict]:
    """조직도 행 목록. `active` 필터는 **그 부서만** 거른다(하위는 그대로 남는다).

    필터로 중간 부서를 빼면 그 아래가 고아가 되므로, 걸러진 뒤에도 `_children_map` 이
    부모 없는 행을 최상위로 올려 보여 준다 — 사라지지 않는다.
    """
    stmt = select(Department)
    if active is not None:
        stmt = stmt.where(Department.active.is_(active))
    rows = list(db.execute(stmt).scalars().all())
    return build_rows(db, rows)


def validate_parent(db: Session, row: Department, parent_id: str | None) -> str | None:
    """부모 지정 검증. 통과하면 저장해도 되는 값을 돌려준다(빈 문자열은 '최상위'로 읽는다)."""
    if parent_id is None or parent_id == "":
        return None
    if parent_id == row.id:
        raise ValidationAppError("부서를 자기 자신의 하위로 둘 수 없습니다.")
    parent = db.get(Department, parent_id)
    if parent is None:
        raise ValidationAppError("알 수 없는 상위 부서입니다.")
    # 자기 자손을 부모로 삼으면 트리가 고리가 되고, 그 순간 그 덩어리 전체가 조직도의 루트에서
    # 사라진다(위 build_rows 가 `cycle` 로 드러내지만, 애초에 들어오게 두지 않는다).
    if parent_id in department_subtree_ids(db, row.id):
        raise ValidationAppError(
            f"‘{parent.name}’은(는) 이 부서의 하위 부서입니다. 하위 부서를 상위로 지정할 수 없습니다."
        )
    return parent_id
