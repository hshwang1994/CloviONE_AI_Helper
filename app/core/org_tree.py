"""부서 트리를 읽는 **단 하나의 자리**.

## 왜 트리를 통째로 들고 오는가

`departments` 는 수십 행 규모다(조직 하나에 본부·팀·파트를 다 합쳐도 백 단위를 넘지
않는다). 그런데 이 트리에 물어야 할 질문은 요청 하나에서 여러 번 나온다 — 범위 계산에
서브트리, 상향 가시성에 조상, 화면 표시에 경로, 목록 한 페이지의 행마다 소속 경로.
그때마다 재귀 질의를 돌리면 목록 20행짜리 화면 하나가 부서 질의 수십 번이 된다(문서
목록이 매행 매핑표를 다시 읽어 N+1 이 됐던 FN-41 과 같은 모양이다).

그래서 **요청당 한 번** 전량을 읽어 이 객체를 만들고(`app/core/deps.py::get_principal`),
그 요청이 끝날 때까지 재사용한다. 질의는 한 번, 이후는 전부 메모리 사전 조회다.

## 경로 문자열을 저장하지 않는다

`"굿모닝아이텍 > 브로드컴사업본부 > ClovirONE팀"` 같은 문자열은 **권한 키가 아니다.**
부서 이름이 바뀌거나 중간에 상위 부서가 하나 생기는 순간 그 문자열은 거짓이 되고, 그걸
어딘가에 저장해 두면 조직 개편 때마다 저장된 문자열을 전부 다시 써야 한다. 권한과 표시
양쪽 모두 **안정적인 내부 id 관계**만 쓰고, 사람이 읽는 경로는 여기서 **그때그때 계산**한다.

## 세 가지 집합을 구분한다

    ancestors(d)    d 의 조상들 (자기 제외, 위로)
    descendants(d)  d 와 그 아래 전부 (자기 포함)
    branch(d)       ancestors ∪ descendants — 같은 줄기 전체

`descendants` 는 **관리 범위**(부서 관리자는 자기 아래를 관리한다)이고 `branch` 는
**조회 범위**(하위 팀 사람도 상위 공통 업무를 본다)다. 둘을 한 함수로 뭉치면 "볼 수는
있는데 관리할 수는 없는" 상태를 표현할 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

# 사이클(A→B→A)이 생겨도 요청 하나가 프로세스를 잡아먹지 않게 하는 안전 상한.
# visited 집합으로 이미 막지만, 깊이 상한도 함께 둬서 데이터가 이상해도 끝난다.
MAX_DEPARTMENT_DEPTH = 32


@dataclass(frozen=True)
class DeptNode:
    id: str
    name: str
    parent_id: str | None
    org_id: str | None
    active: bool


class DeptTree:
    """한 번 읽은 부서 표. **불변으로 쓴다** — 요청 처리 중에 늘리지 않는다."""

    __slots__ = ("_nodes", "_children")

    def __init__(self, nodes: list[DeptNode]) -> None:
        self._nodes: dict[str, DeptNode] = {n.id: n for n in nodes}
        children: dict[str | None, list[str]] = {}
        for node in nodes:
            children.setdefault(node.parent_id, []).append(node.id)
        self._children = children

    # ── 생성 ────────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, db: Session) -> "DeptTree":
        from app.org.models import Department

        rows = db.execute(
            select(
                Department.id, Department.name, Department.parent_id,
                Department.org_id, Department.active,
            )
        ).all()
        return cls([
            DeptNode(id=r[0], name=r[1], parent_id=r[2], org_id=r[3], active=bool(r[4]))
            for r in rows
        ])

    # ── 조회 ────────────────────────────────────────────────────────────────
    def get(self, dept_id: str | None) -> DeptNode | None:
        return self._nodes.get(dept_id) if dept_id else None

    def exists(self, dept_id: str | None) -> bool:
        return bool(dept_id) and dept_id in self._nodes

    def org_of(self, dept_id: str | None) -> str | None:
        node = self.get(dept_id)
        return node.org_id if node else None

    def ancestors(self, dept_id: str | None) -> tuple[str, ...]:
        """가까운 부모부터 위로. **자기 자신은 안 들어간다.**"""
        out: list[str] = []
        seen: set[str] = set()
        node = self.get(dept_id)
        for _ in range(MAX_DEPARTMENT_DEPTH):
            if node is None or not node.parent_id or node.parent_id in seen:
                break
            seen.add(node.parent_id)
            out.append(node.parent_id)
            node = self.get(node.parent_id)
        return tuple(out)

    def descendants(self, dept_id: str | None) -> frozenset[str]:
        """``dept_id`` 와 그 아래 전부. 없는 id 면 빈 집합(fail-closed)."""
        if not self.exists(dept_id):
            return frozenset()
        seen = {dept_id}
        frontier = [dept_id]
        for _ in range(MAX_DEPARTMENT_DEPTH):
            if not frontier:
                break
            nxt: list[str] = []
            for parent in frontier:
                for child in self._children.get(parent, ()):
                    if child not in seen:
                        seen.add(child)
                        nxt.append(child)
            frontier = nxt
        return frozenset(seen)

    def branch(self, dept_id: str | None) -> frozenset[str]:
        """조상 ∪ 자기 ∪ 후손 — **일반 사용자의 조회 범위**.

        같은 조직 안에서만 성립한다. 조상을 따라 올라가다 조직이 바뀌는 데이터는
        정상이 아니므로(부서 트리는 조직 안에서 닫혀 있다) 그 지점에서 멈춘다.
        """
        if not self.exists(dept_id):
            return frozenset()
        org_id = self.org_of(dept_id)
        out = set(self.descendants(dept_id))
        for anc in self.ancestors(dept_id):
            if self.org_of(anc) != org_id:
                break
            out.add(anc)
        return frozenset(out)

    def path(self, dept_id: str | None) -> tuple[DeptNode, ...]:
        """root → leaf 순서의 노드 경로. 화면 표시 전용(권한 판정에 쓰지 않는다)."""
        node = self.get(dept_id)
        if node is None:
            return ()
        chain = [node]
        for anc in self.ancestors(dept_id):
            anc_node = self.get(anc)
            if anc_node is None:
                break
            chain.append(anc_node)
        chain.reverse()
        return tuple(chain)

    def path_names(self, dept_id: str | None) -> tuple[str, ...]:
        return tuple(n.name for n in self.path(dept_id))

    def has_children(self, dept_id: str | None) -> bool:
        return bool(self._children.get(dept_id))

    def all_ids(self) -> frozenset[str]:
        return frozenset(self._nodes)

    def in_org(self, org_id: str | None) -> frozenset[str]:
        if not org_id:
            return frozenset()
        return frozenset(i for i, n in self._nodes.items() if n.org_id == org_id)
