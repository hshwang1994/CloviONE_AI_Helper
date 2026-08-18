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
from app.core.org_tree import MAX_DEPARTMENT_DEPTH, DeptTree
from app.org.constants import ORG_ACTIVE
from app.org.models import Department, Organization
from app.users.models import User

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


def _is_in_cycle(row_id: str, by_id: dict[str, Department]) -> bool:
    """UA-21: `row_id`에서 `parent_id`를 따라 올라가며 **실제로 자기 자신에게 돌아오는지**만
    본다 — 깊이 상한(아래 `_emit`의 `depth < MAX_DEPARTMENT_DEPTH`)과는 완전히 무관한
    독립 판정이다. 그 상한 때문에 루트에서 못 닿은 행은 진짜 사이클과 "그냥 32단보다
    깊을 뿐인 정상 트리"가 섞여 있었는데, 둘 다 같은 `cycle: true`로 보고돼 사이클이
    없는 부서에도 "상위 관계 오류" 배지가 뜨고 관리자가 멀쩡한 부모를 고치라고 안내받았다.
    """
    visited: set[str] = set()
    current: str | None = row_id
    while current is not None:
        if current in visited:
            return True
        visited.add(current)
        row = by_id.get(current)
        if row is None:
            return False
        current = row.parent_id
    return False


def build_rows(db: Session, rows: list[Department]) -> list[dict]:
    """깊이 우선 평탄화 + 서브트리 인원 합계.

    사이클이 있으면(부모가 서로를 가리키는 상태) 그 덩어리는 루트에서 닿지 않는다 —
    빠뜨리지 않고 맨 뒤에 `cycle: true` 로 붙여 **눈에 보이게** 한다. 조용히 감추면
    "부서가 목록에서 사라졌다"는 신고만 남고 원인은 영영 안 보인다.

    루트에서 못 닿은 행이 전부 사이클은 아니다 — 깊이 상한(`MAX_DEPARTMENT_DEPTH`)에
    걸려 못 닿았을 수도 있다(UA-21). `_is_in_cycle`로 실제 사이클만 `cycle: true`로
    표시하고, 그냥 깊을 뿐인 행은 `cycle: false`로 둔다(잘못된 "부모를 고치라"는
    안내를 없앤다) — 다만 화면에 평평하게 펴는 depth 자체는 상한을 넘는 실제 깊이를
    표현할 방법이 없어 여전히 0부터 다시 매긴다(이 한계는 그대로 남는다).
    """
    by_id = {row.id: row for row in rows}
    children = _children_map(rows)
    direct = _direct_user_counts(db)
    # UA-21: 순환 여부를 모든 행에 대해 **미리 한 번에** 계산해 둔다. 순환에 갇힌 덩어리를
    # 처음 만나는 행 하나만 사이클로 표시하고 나머지는 그 행의 "자식"으로 재귀되며(
    # `_children_map`은 순환을 모르고 parent→children만 뒤집으므로 재귀가 그 안까지
    # 따라 들어간다) `_emit`의 기본값 `False`로 덮이면, 같은 순환의 다른 쪽 절반만
    # "정상"으로 보이는 절반짜리 수정이 된다 — 실제로 처음 이 방식대로 짰다가 2행짜리
    # 순환(a↔b)에서 a만 cycle:true, b는 cycle:false로 나오는 것을 시험이 잡아냈다.
    in_cycle = {row.id: _is_in_cycle(row.id, by_id) for row in rows}

    out: list[dict] = []
    seen: set[str] = set()

    def _emit(row: Department, depth: int, path: list[str]) -> int:
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
            "org_id": row.org_id,
            "active": row.active,
            "user_count": direct.get(row.id, 0),
            "child_count": len(kids),
            "cycle": in_cycle.get(row.id, False),
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
    # 루트에서 닿지 않은 것들 — 사이클에 갇혔거나, 깊이 상한 때문에 그 아래로 못 내려간
    # 정상 트리다(위에서 미리 계산한 in_cycle이 어느 쪽인지 정확히 가른다).
    for row in rows:
        if row.id not in seen:
            _emit(row, 0, [])
    return out


def _org_rows(db: Session, scope=None) -> dict[str, Organization]:
    """트리 맨 위에 놓을 조직 행. 범위가 있으면 **내가 관리하는 조직 하나**뿐이다.

    부서 행과 판정을 나눌 수밖에 없는 이유: `Organization` 에는 `org_id` 가 없다(자기 자신이
    조직이다). 근거는 같은 값(`scope.org_id`)을 본다.
    """
    stmt = select(Organization)
    if scope is not None and not getattr(scope, "is_global", True):
        if not getattr(scope, "org_id", None):
            return {}   # 범위는 있는데 조직을 모른다 → 닫는 쪽으로 실패한다
        stmt = stmt.where(Organization.id == scope.org_id)
    return {o.id: o for o in db.execute(stmt).scalars()}


def tree_rows(db: Session, *, active: bool | None = None, scope=None) -> list[dict]:
    """조직도 행 목록. `active` 필터는 **그 부서만** 거른다(하위는 그대로 남는다).

    `scope` 는 목록(`app/org/service.py::scope_clause`)과 **같은 판정**이다. 이 경로만
    범위를 안 받고 있었는데, 트리는 목록보다 더 많이 준다 — 조직 이름·slug·인원수와
    모든 부서의 계층 path·상위 부서·인원수가 한 번에 나갔다.

    필터로 중간 부서를 빼면 그 아래가 고아가 되므로, 걸러진 뒤에도 `_children_map` 이
    부모 없는 행을 최상위로 올려 보여 준다 — 사라지지 않는다.

    **맨 위에 조직 행을 놓는다**(2026-08-04 사용자 지시 §3: "조직 > 부서 > 사용자(직책)"
    구조와 포함 관계가 한눈에 보여야 한다). 예전에는 부서부터 시작해서, 화면만 봐서는
    이 부서들이 **어느 조직 소속인지** 알 수 없었다 — 조직이 하나뿐이어도 그 사실 자체가
    화면에 없으면 사용자는 알 수 없다. 조직 행은 `kind: "organization"` 으로 표시하고
    부서 행은 한 칸 더 들여쓴다(depth+1).
    """
    from app.org.service import apply_scope

    stmt = select(Department)
    if active is not None:
        stmt = stmt.where(Department.active.is_(active))
    rows = list(db.execute(apply_scope(stmt, scope, Department)).scalars().all())
    dept_rows = build_rows(db, rows)

    orgs = _org_rows(db, scope)
    if not orgs:
        return dept_rows   # 조직 행이 없으면(초기화 전) 예전 모양 그대로 — 빈 화면보다 낫다

    by_org: dict[str, list[dict]] = {}
    for row in dept_rows:
        by_org.setdefault(row.get("org_id") or "", []).append(row)

    out: list[dict] = []
    for org in sorted(orgs.values(), key=lambda o: o.name or ""):
        kids = by_org.pop(org.id, [])
        out.append({
            "id": org.id,
            "kind": "organization",
            "name": org.name or org.slug,
            "depth": 0,
            "path": org.name or org.slug,
            "parent_id": None,
            "parent_name": None,
            "active": org.status == ORG_ACTIVE,
            # 부서 행의 규칙을 그대로 따른다: user_count 는 '이 층에 직접', subtree 는 '아래 전부'.
            # 조직에서 '직접'은 **부서가 지정되지 않은 사람**이다 — 그 수가 0 이 아니면 그 자체가
            # 관리자가 알아야 할 사실이라(어디에도 안 속한 계정) 숨기지 않는다.
            "user_count": _org_user_count(db, org.id, no_department=True, scope=scope),
            "child_count": sum(1 for k in kids if k["depth"] == 0),
            "subtree_user_count": _org_user_count(db, org.id, scope=scope),
            "cycle": False,
            "created_at": org.created_at.isoformat(),
        })
        out.extend({**k, "kind": "department", "depth": k["depth"] + 1,
                    "path": (org.name or org.slug) + PATH_SEP + k["path"]} for k in kids)

    # 조직 행이 없는 부서(데이터가 어긋난 상태)는 감추지 않고 맨 뒤에 그대로 붙인다 —
    # 조용히 빠지면 "부서가 사라졌다"는 신고만 남고 원인은 안 보인다(사이클 처리와 같은 규칙).
    for leftover in by_org.values():
        out.extend({**k, "kind": "department"} for k in leftover)
    return out


def _org_user_count(
    db: Session, org_id: str, *, no_department: bool = False, scope=None
) -> int:
    """이 조직에 속한 사람 수. `no_department=True` 면 부서가 지정되지 않은 사람만.

    사람을 세는 규칙은 사용자 목록과 같아야 한다 — 그래서 `apply_user_scope` 를 그대로
    쓴다. 안 그러면 부서 관리자가 볼 수 있는 사람은 자기 팀뿐인데 머릿수만 전사 인원으로
    보이는, **화면끼리 어긋나는** 숫자가 된다.
    """
    from app.core.scope import apply_user_scope

    stmt = select(func.count()).select_from(User).where(User.org_id == org_id)
    if no_department:
        stmt = stmt.where(User.department_id.is_(None))
    if scope is not None:
        stmt = apply_user_scope(stmt, scope)
    return db.execute(stmt).scalar_one()


def validate_parent(
    db: Session, row: Department, parent_id: str | None, scope=None
) -> str | None:
    """부모 지정 검증. 통과하면 저장해도 되는 값을 돌려준다(빈 문자열은 '최상위'로 읽는다).

    `scope` 를 주면 **범위 밖 부서는 없는 것과 똑같이** 답한다(생성 경로와 같은 판정,
    같은 문구). 여기만 다른 오류를 내면 남의 부서 id 를 찍어 보며 존재를 셀 수 있다.
    """
    from app.org.service import scope_allows_item

    if parent_id is None or parent_id == "":
        return None
    if parent_id == row.id:
        raise ValidationAppError("부서를 자기 자신의 하위로 둘 수 없습니다.")
    parent = db.get(Department, parent_id)
    # UA-13: scope_allows_item만으로는 전역 관리자가 다른 조직의 부서를 부모로 지정하는
    # 것을 못 막는다 — DeptTree.descendants(parent_id 만 따라가는 순수 그래프 순회,
    # org 필터 없음)가 그 조직 부서를 dept 스코프 관리자의 서브트리에 끌어들여 권한이
    # 조용히 넓어진다. 부모는 반드시 이 행(row)과 같은 조직이어야 한다.
    if parent is None or not scope_allows_item(scope, parent) or parent.org_id != row.org_id:
        raise ValidationAppError("알 수 없는 상위 부서입니다.")
    # 자기 자손을 부모로 삼으면 트리가 고리가 되고, 그 순간 그 덩어리 전체가 조직도의 루트에서
    # 사라진다(위 build_rows 가 `cycle` 로 드러내지만, 애초에 들어오게 두지 않는다).
    if parent_id in DeptTree.load(db).descendants(row.id):
        raise ValidationAppError(
            f"‘{parent.name}’은(는) 이 부서의 하위 부서입니다. 하위 부서를 상위로 지정할 수 없습니다."
        )
    return parent_id
