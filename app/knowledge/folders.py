"""폴더 트리 — 만들고 · 이름 바꾸고 · 옮기고 · 순서를 정한다 (S7).

## 이 파일이 **안 하는** 것 둘

**`path` 와 `depth` 를 안 쓴다.** DB 트리거가 부모에서 파생시키고, 옮기면 자손을 따라
고친다(D-244). 앱이 그것을 계산하면 「한 곳만 안 고친 날」에 하위 목록이 조용히 빈다.

**권한을 안 만든다.** 폴더는 정리 축이고 권한 축은 공간이다(§5.3). 그래서 여기에는
가시성 판정이 한 줄도 없다 — 부르는 쪽(`service.py`)이 공간을 먼저 통과시킨다.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.knowledge.models import MAX_FOLDER_DEPTH, Folder
from app.work import rank

__all__ = [
    "create",
    "rename",
    "move",
    "reorder",
    "children_of",
    "subtree_ids",
    "tree",
    "PATH_SEP",
]

# `path` 의 구분자. 트리거가 쓰는 값과 **같아야 한다** — 마이그레이션의 함수 본문에
# 같은 글자가 있고, `tests/unit/test_knowledge_folders.py` 가 둘을 맞물려 둔다.
PATH_SEP = "/"


def _siblings(db: Session, space_id: str, parent_id: str | None):
    stmt = (
        select(Folder)
        .where(Folder.space_id == space_id)
        .order_by(Folder.sort_order)
    )
    stmt = stmt.where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    )
    return list(db.execute(stmt).scalars().all())


def _rank_between(
    db: Session, space_id: str, parent_id: str | None,
    before_id: str | None, after_id: str | None,
) -> Decimal:
    """두 이웃 사이의 순서 값. **인덱스가 아니라 이웃으로 받는다.**

    S6 이 백로그에서 배운 것 그대로다: 인덱스로 받으면 다른 사람이 방금 하나를 지운
    목록에서 한 칸씩 밀린 자리에 놓인다. 이웃 id 는 그 사이에 무엇이 생기든 뜻이 안 변한다.
    """
    rows = _siblings(db, space_id, parent_id)
    value = _between(rows, before_id, after_id)
    if rank.needs_rebalance(value):
        _rebalance(db, space_id, parent_id)
        value = _between(_siblings(db, space_id, parent_id), before_id, after_id)
    return value


def _between(rows, before_id: str | None, after_id: str | None):
    """이웃 둘 사이. **이웃을 하나도 안 주면 맨 뒤에 붙인다.**

    ⚠️ 여기가 한 번 틀렸다. `rank.between(None, None)` 을 그대로 쓰면 목록이 비었다는
    뜻의 첫 값(`STEP`)이 나온다 — 형제가 이미 셋 있어도. 그러면 새로 만든 폴더가 전부
    같은 순서 값을 받고, 목록 순서가 요청마다 달라진다. 오류가 아니라서 아무도 신고하지
    않는다("어제는 이 순서였는데").
    """
    index = {f.id: f for f in rows}
    before = index.get(before_id) if before_id else None
    after = index.get(after_id) if after_id else None
    if before_id and before is None:
        raise ValidationAppError("앞 폴더를 찾지 못했습니다.")
    if after_id and after is None:
        raise ValidationAppError("뒤 폴더를 찾지 못했습니다.")
    if before is None and after is None and rows:
        before = rows[-1]
    return rank.between(
        before.sort_order if before else None,
        after.sort_order if after else None,
    )


def _rebalance(db: Session, space_id: str, parent_id: str | None) -> None:
    """한 부모의 형제들만 다시 매긴다. 드물게 한 번이고, 전체가 아니다."""
    for index, folder in enumerate(_siblings(db, space_id, parent_id), start=1):
        folder.sort_order = rank.STEP * index
    db.flush()


def create(
    db: Session, *, space_id: str, name: str, parent_id: str | None = None,
    before_id: str | None = None, after_id: str | None = None,
) -> Folder:
    """새 폴더. `path`·`depth` 는 안 넘긴다 — 트리거가 만든다."""
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("폴더 이름을 입력해 주세요.")

    if parent_id is not None:
        parent = db.get(Folder, parent_id)
        if parent is None or parent.space_id != space_id:
            raise ValidationAppError("상위 폴더를 찾지 못했습니다.")
        if parent.depth + 1 > MAX_FOLDER_DEPTH:
            raise ValidationAppError(f"폴더는 {MAX_FOLDER_DEPTH}단계까지 만들 수 있습니다.")

    folder = Folder(
        space_id=space_id,
        parent_id=parent_id,
        name=clean,
        sort_order=_rank_between(db, space_id, parent_id, before_id, after_id),
    )
    db.add(folder)
    db.flush()
    # 트리거가 `path`·`depth` 를 만들었다. 세션은 `expire_on_commit=False` 라 다시 읽지
    # 않으면 **앱이 넘긴 빈 값**을 계속 든다 — 그러면 응답의 `depth` 가 전부 0 이 되고,
    # 화면의 트리가 평면으로 그려진다.
    db.refresh(folder)
    return folder


def rename(db: Session, folder: Folder, name: str) -> Folder:
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("폴더 이름을 입력해 주세요.")
    folder.name = clean
    db.flush()
    return folder


def move(
    db: Session, folder: Folder, *, parent_id: str | None,
    before_id: str | None = None, after_id: str | None = None,
) -> Folder:
    """부모를 바꾸고, 새 형제들 사이에 놓는다.

    순환은 여기서 **한 번**, 트리거에서 **한 번** 막는다. 두 벌인 것이 낭비가 아니다:
    여기서 막는 것은 사람이 읽을 수 있는 메시지를 주기 위해서이고, 트리거가 막는 것은
    이 함수를 안 지나는 경로가 언젠가 생기기 때문이다(마이그레이션 · 콘솔 · 스크립트).
    """
    if parent_id == folder.id:
        raise ValidationAppError("폴더를 자기 안으로 옮길 수 없습니다.")

    if parent_id is not None:
        parent = db.get(Folder, parent_id)
        if parent is None or parent.space_id != folder.space_id:
            raise ValidationAppError("상위 폴더를 찾지 못했습니다.")
        if _is_descendant(parent, folder):
            raise ValidationAppError("폴더를 자기 하위 폴더 안으로 옮길 수 없습니다.")
        depth_below = _subtree_height(db, folder)
        if parent.depth + 1 + depth_below > MAX_FOLDER_DEPTH:
            raise ValidationAppError(f"폴더는 {MAX_FOLDER_DEPTH}단계까지 만들 수 있습니다.")

    folder.parent_id = parent_id
    folder.sort_order = _rank_between(
        db, folder.space_id, parent_id, before_id, after_id
    )
    db.flush()
    # 트리거가 이 행과 자손의 `path`·`depth` 를 이미 고쳤다. 세션이 든 옛 값을 버려야
    # 같은 요청 안에서 이어지는 조회가 옛 트리를 본다.
    db.expire_all()
    return folder


def reorder(
    db: Session, folder: Folder, *, before_id: str | None, after_id: str | None
) -> Folder:
    """같은 부모 안에서 자리만 바꾼다."""
    folder.sort_order = _rank_between(
        db, folder.space_id, folder.parent_id, before_id, after_id
    )
    db.flush()
    return folder


def _is_descendant(candidate: Folder, ancestor: Folder) -> bool:
    """`candidate` 가 `ancestor` 아래에 있는가 — `path` 를 **읽기만** 한다."""
    return f"{PATH_SEP}{ancestor.id}{PATH_SEP}" in (candidate.path or "")


def _subtree_height(db: Session, folder: Folder) -> int:
    """이 폴더 아래로 몇 겹이 더 있는가. 옮긴 뒤 상한을 넘는지 미리 본다."""
    deepest = db.execute(
        select(Folder.depth)
        .where(
            Folder.space_id == folder.space_id,
            Folder.path.like(f"%{PATH_SEP}{folder.id}{PATH_SEP}%"),
        )
        .order_by(Folder.depth.desc())
        .limit(1)
    ).scalar()
    return max(0, (deepest or folder.depth) - folder.depth)


def children_of(db: Session, space_id: str, parent_id: str | None) -> list[Folder]:
    return _siblings(db, space_id, parent_id)


def subtree_ids(db: Session, folder: Folder) -> list[str]:
    """자기 자신을 포함한 하위 전부. 문서 목록이 「이 폴더 아래」를 물을 때 쓴다."""
    rows = db.execute(
        select(Folder.id).where(
            Folder.space_id == folder.space_id,
            Folder.path.like(f"{folder.path}%"),
        )
    ).scalars().all()
    return list(rows)


def tree(db: Session, space_id: str) -> list[dict]:
    """공간 전체의 트리 한 번에. **질의 한 번**이다.

    화면이 폴더마다 자식을 물으면 그대로 N+1 이고, 그 화면은 폴더가 늘수록 느려진다.
    깊이 순으로 훑으면 부모가 자식보다 먼저 나오므로 한 번에 붙일 수 있다.
    """
    rows = db.execute(
        select(Folder)
        .where(Folder.space_id == space_id)
        .order_by(Folder.depth, Folder.sort_order)
    ).scalars().all()

    nodes: dict[str, dict] = {}
    roots: list[dict] = []
    for folder in rows:
        node = {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "depth": folder.depth,
            "sort_order": str(folder.sort_order),
            "children": [],
        }
        nodes[folder.id] = node
        parent = nodes.get(folder.parent_id) if folder.parent_id else None
        (parent["children"] if parent else roots).append(node)
    return roots
