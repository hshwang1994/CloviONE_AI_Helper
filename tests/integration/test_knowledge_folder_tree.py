"""폴더 트리 — **`path` 와 `depth` 는 트리거가 만든다** (S7 · D-244).

## 왜 실 DB 여야 하는가

이 시험이 보는 것은 전부 DB 안에서만 일어난다: BEFORE 트리거의 파생, 순환 거절,
그리고 부모가 바뀔 때 **자손 전부**를 따라 고치는 AFTER 트리거. 파이썬 층을 흉내 내면
「앱이 안 지나는 경로」를 못 보는데, 트리거를 둔 이유가 정확히 그 경로다.

## 반례를 함께 둔다

각 단정에 「정상 동작은 통과한다」를 함께 둔다. 「거절한다」만 확인하면 **전부 거절하는
트리거**도 통과하고, 그 상태에서는 폴더를 하나도 못 만든다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.core.errors import ValidationAppError
from app.knowledge import folders
from app.knowledge.models import Document, Folder, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID

pytestmark = pytest.mark.integration


@pytest.fixture()
def space(db):
    row = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="설계 문서", slug="design", owner_kind="organization",
    )
    db.add(row)
    db.commit()
    return row


def _mk(db, space, name, parent=None):
    folder = folders.create(
        db, space_id=space.id, name=name, parent_id=parent.id if parent else None
    )
    db.commit()
    return folder


# ── 트리거가 파생시킨다 ──────────────────────────────────────────────────────


def test_a_root_folder_gets_its_own_path_and_depth_zero(db, space):
    folder = _mk(db, space, "뿌리")
    db.refresh(folder)
    assert folder.path == f"/{folder.id}/"
    assert folder.depth == 0


def test_a_child_inherits_the_parent_path(db, space):
    parent = _mk(db, space, "부모")
    child = _mk(db, space, "자식", parent)
    db.refresh(child)
    assert child.path == f"/{parent.id}/{child.id}/"
    assert child.depth == 1


def test_the_app_cannot_write_path_or_depth(db, space):
    """앱이 무엇을 적든 트리거가 덮어쓴다 — 어긋날 자리가 없다 (D-236 과 같은 성질)."""
    folder = Folder(space_id=space.id, name="거짓말", path="/거짓/", depth=99, sort_order=1)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    assert folder.path == f"/{folder.id}/", "앱이 적은 path 가 살아남았다"
    assert folder.depth == 0, "앱이 적은 depth 가 살아남았다"


# ── 옮기면 자손이 따라온다 ───────────────────────────────────────────────────


def test_moving_a_folder_rewrites_every_descendant_path(db, space):
    """AFTER 트리거가 없으면 옮긴 폴더 아래 것들이 **옛 조상을 계속 가리킨다.**

    증상은 조용하다 — 「이 폴더 아래 전부」가 한 건도 안 나오거나, 옮기기 전 자리에
    계속 나온다. 오류는 안 난다.
    """
    a = _mk(db, space, "A")
    b = _mk(db, space, "B")
    a1 = _mk(db, space, "A1", a)
    a2 = _mk(db, space, "A2", a1)

    folders.move(db, a, parent_id=b.id)
    db.commit()
    for row in (a, a1, a2):
        db.refresh(row)

    assert a.path == f"/{b.id}/{a.id}/"
    assert a1.path == f"/{b.id}/{a.id}/{a1.id}/"
    assert a2.path == f"/{b.id}/{a.id}/{a1.id}/{a2.id}/"
    assert (a.depth, a1.depth, a2.depth) == (1, 2, 3)


def test_moving_a_folder_to_the_root_rewrites_descendants_too(db, space):
    a = _mk(db, space, "A")
    a1 = _mk(db, space, "A1", a)
    a2 = _mk(db, space, "A2", a1)

    folders.move(db, a1, parent_id=None)
    db.commit()
    for row in (a1, a2):
        db.refresh(row)
    assert a1.path == f"/{a1.id}/"
    assert a2.path == f"/{a1.id}/{a2.id}/"
    assert (a1.depth, a2.depth) == (0, 1)


def test_subtree_lookup_finds_the_whole_branch_after_a_move(db, space):
    a = _mk(db, space, "A")
    b = _mk(db, space, "B")
    a1 = _mk(db, space, "A1", a)
    folders.move(db, a, parent_id=b.id)
    db.commit()
    db.refresh(b)
    assert set(folders.subtree_ids(db, b)) == {b.id, a.id, a1.id}


# ── 순환은 두 층에서 막는다 ──────────────────────────────────────────────────


def test_the_app_refuses_to_move_a_folder_into_its_own_subtree(db, space):
    a = _mk(db, space, "A")
    a1 = _mk(db, space, "A1", a)
    with pytest.raises(ValidationAppError):
        folders.move(db, a, parent_id=a1.id)


def test_the_database_refuses_a_cycle_even_without_the_app(db, space):
    """**앱을 안 지나는 경로**가 언젠가 생긴다 — 마이그레이션 · 콘솔 · 스크립트.

    앱에서만 막으면 그 경로 하나로 트리가 통째로 안 열린다(무한 재귀).
    """
    a = _mk(db, space, "A")
    a1 = _mk(db, space, "A1", a)
    with pytest.raises(Exception) as caught:
        db.execute(
            text("UPDATE folders SET parent_id = :child WHERE id = :parent"),
            {"child": a1.id, "parent": a.id},
        )
        db.flush()
    assert "subtree" in str(caught.value), f"순환이 아닌 다른 이유로 실패했다: {caught.value}"
    db.rollback()


def test_an_ordinary_move_still_works(db, space):
    """반대편 — 여기서 실패하면 위 둘은 「전부 거절하는 트리거」도 통과시킨다."""
    a = _mk(db, space, "A")
    b = _mk(db, space, "B")
    folders.move(db, b, parent_id=a.id)
    db.commit()
    db.refresh(b)
    assert b.parent_id == a.id and b.depth == 1


# ── 깊이 상한 ────────────────────────────────────────────────────────────────


def test_the_tree_cannot_grow_past_the_depth_limit(db, space):
    from app.knowledge.models import MAX_FOLDER_DEPTH

    parent = None
    for level in range(MAX_FOLDER_DEPTH + 1):
        parent = _mk(db, space, f"L{level}", parent)
    assert parent.depth == MAX_FOLDER_DEPTH
    with pytest.raises(ValidationAppError):
        folders.create(db, space_id=space.id, name="한 겹 더", parent_id=parent.id)


# ── 형제 이름과 순서 ─────────────────────────────────────────────────────────


def test_two_siblings_cannot_share_a_name(db, space):
    parent = _mk(db, space, "부모")
    _mk(db, space, "같은 이름", parent)
    with pytest.raises(Exception):
        _mk(db, space, "같은 이름", parent)
    db.rollback()


def test_two_root_folders_cannot_share_a_name(db, space):
    """PG 에서 NULL 은 서로 다르다 — 부분 유니크가 없으면 뿌리에만 중복이 생긴다."""
    _mk(db, space, "뿌리")
    with pytest.raises(Exception):
        _mk(db, space, "뿌리")
    db.rollback()


def test_the_same_name_in_two_spaces_is_fine(db, space):
    other = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="다른 공간", slug="other", owner_kind="organization",
    )
    db.add(other)
    db.commit()
    _mk(db, space, "회의록")
    _mk(db, other, "회의록")


def test_reorder_puts_a_folder_between_its_two_neighbours(db, space):
    first = _mk(db, space, "1")
    second = _mk(db, space, "2")
    third = _mk(db, space, "3")
    folders.reorder(db, third, before_id=first.id, after_id=second.id)
    db.commit()
    names = [f.name for f in folders.children_of(db, space.id, None)]
    assert names == ["1", "3", "2"], f"자리가 안 바뀌었다: {names}"


def test_the_tree_endpoint_nests_children_under_parents(db, space):
    a = _mk(db, space, "A")
    _mk(db, space, "A1", a)
    _mk(db, space, "B")
    tree = folders.tree(db, space.id)
    assert [n["name"] for n in tree] == ["A", "B"]
    assert [n["name"] for n in tree[0]["children"]] == ["A1"]


# ── 폴더를 지워도 문서는 안 지운다 ──────────────────────────────────────────


def test_deleting_a_folder_keeps_its_documents(db, space):
    """CASCADE 로 두면 폴더 하나를 잘못 지운 날 그 아래 글이 전부 사라진다.

    글은 재계산으로 안 돌아온다 — 그것이 폴더와 문서를 다른 규칙으로 둔 이유다.
    """
    folder = _mk(db, space, "회의")
    document = Document(space_id=space.id, folder_id=folder.id, title="주간 회의")
    db.add(document)
    db.commit()

    db.delete(folder)
    db.commit()
    # 세션이 `expire_on_commit=False` 라 DB 쪽 SET NULL 을 다시 읽어야 보인다.
    db.expire_all()

    surviving = db.execute(select(Document).where(Document.id == document.id)).scalars().first()
    assert surviving is not None, "폴더를 지웠더니 문서가 함께 사라졌다"
    assert surviving.folder_id is None, "지워진 폴더를 계속 가리킨다"


def test_deleting_a_folder_deletes_its_subfolders(db, space):
    parent = _mk(db, space, "부모")
    child = _mk(db, space, "자식", parent)
    db.delete(parent)
    db.commit()
    # `db.get` 은 아이덴티티 맵을 먼저 본다 — DB 가 CASCADE 로 지운 행을 그대로 돌려주거나
    # 되읽기에서 터진다. 실제로 남아 있는지는 질의로 묻는다.
    left = db.execute(select(Folder.id).where(Folder.id == child.id)).scalars().first()
    assert left is None, "하위 폴더가 남았다"
