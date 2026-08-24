"""WBS 트리 — `ticket_relations` 의 상하위로 작업 계층을 만든다 (순수 함수, DB 없음).

## 계층을 새로 만들지 않는다

노션 작업 DB 에 상위, 하위 self-relation 이 있고 0044 가 그것을 `parent_page_id` 로
미러링했다. S6 이 그 값을 `ticket_relations` 로 **파생**시키면서 계층의 정본이 그 표
하나가 됐다(`app/work/relations.py::sync_parent_links`). 이 파일은 여전히 계층을 만들지
않는다 — 받아서 그릴 뿐이고, 달라진 것은 어느 표에서 오는가뿐이다.

## 진행률은 `compute_progress` 를 그대로 쓴다

노드마다 하위 트리의 작업을 모아 **같은 함수**에 넣는다. 여기서 다시 세면 계산이 두 벌이
되고, 트리의 숫자와 헤더의 숫자가 갈라진다. 그때 사용자는 어느 쪽도 안 믿고 결국 둘 다
안 보게 된다(그 실패는 `progress.py` 모듈 docstring 에 이미 적혀 있다).

트리 전체 진행률도 마찬가지다. 루트들의 합으로 다시 세지 않고 **표본 전체**를 그대로
`compute_progress` 에 넣는다. 그래야 아래의 `unplaced`(순환, 깊이 초과로 못 그린 작업)가
있어도 헤더 숫자와 정확히 같은 값이 나온다.

## 순환 방어 (이 파일이 있는 진짜 이유)

노션에서 A의 상위가 B, B의 상위가 A 인 상태가 만들어질 수 있다. 순진하게 재귀하면 요청
하나가 스택을 다 쓰고 프로세스를 죽인다.

방어는 그래프의 성질에서 나온다: 부모는 **한 칸짜리 필드**라 노드마다 부모가 최대 하나다.
그래서 '표본 안에 부모가 없는 노드'(= 루트)에서 자식 방향으로만 내려가면 순환에는 **닿을
수가 없다** - 순환 안의 노드는 그 부모가 순환 안에 있어서 순환 밖에서 도달할 길이 없기
때문이다. 즉 루트에서 시작하는 것 자체가 방어다.

그래도 깊이 상한을 함께 둔다. 위 논증은 '부모가 한 칸' 이라는 전제에 기대는데, 데이터
모양이 바뀌면 그 전제가 조용히 깨질 수 있다. 그물 하나에만 기대지 않는다
(`app/core/scope.py::department_subtree_ids` 가 부서 트리에서 같은 판단을 기록한다).

## 못 그린 것은 못 그렸다고 말한다

순환에 걸렸거나 상한을 넘은 작업을 조용히 빼면 사용자는 자기 일이 사라진 줄 안다.
`unplaced` 에 이유와 함께 담아 화면이 말할 수 있게 한다 - 고칠 사람은 노션에서 고친다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.projects.progress import ProgressResult, Task, compute_progress, task_from_ticket

# 깊이 상한. 이 깊이의 노드까지는 그리고, 그 **자식부터** 안 그린다.
# 부서 트리(`MAX_DEPARTMENT_DEPTH`)와 같은 값을 쓴다 - 사람이 만든 계층이 서른 단계를 넘는
# 것은 계층이 아니라 데이터 사고다.
MAX_WBS_DEPTH = 32

# 못 그린 이유. 화면이 두 경우를 다르게 안내해야 한다(순환은 노션에서 고쳐야 하고,
# 깊이 초과는 대개 데이터가 이상하다는 신호다).
UNPLACED_CYCLE = "cycle"
UNPLACED_TOO_DEEP = "too_deep"


@dataclass(frozen=True)
class WbsItem:
    """트리 한 칸. 진행률에 쓰는 사실(`task`)과 화면에 그릴 사실을 나눠 둔다.

    `task` 를 재사용하는 이유: 키, 부모, 상태, 예상 WD 를 여기서 다시 뽑으면 헤더와 트리가
    **서로 다른 규칙으로 같은 값을 만들게 된다.** 특히 키 축(티켓 UUID)이 갈리면 부모와
    자식이 영원히 안 만난다(progress.py::task_from_ticket).
    """

    task: Task
    title: str
    url: str | None = None
    # 옛 소스의 번호. **형제 정렬에만** 쓴다 — 이름이 아니다.
    ticket_number: int | None = None
    # 화면이 부르는 이름 `<CODE>-<SEQ>` (D-282). 화면이 접두사를 붙여 이름을 지어내면
    # 그 문자열은 제품 어디에도 없는 이름이 된다.
    ticket_key: str | None = None


@dataclass(frozen=True)
class WbsNode:
    """그려진 노드 하나. `progress` 는 **자기 하위 트리만** 센 값이다."""

    key: str
    title: str
    status: str | None
    est_wd: float | None
    ticket_number: int | None
    ticket_key: str | None
    depth: int
    children: tuple["WbsNode", ...]
    progress: ProgressResult

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "est_wd": self.est_wd,
            # `url` 은 여기 없다 - 옛 Notion 주소라 화면의 「원본」 링크가 우리가 더 이상
            # 쓰지 않는 낡은 사본을 열었다. 티켓 목록·상세와 같은 이유로 걷었다.
            "ticket_number": self.ticket_number,
            "ticket_key": self.ticket_key,
            "depth": self.depth,
            "progress": self.progress.as_dict(),
            "children": [c.as_dict() for c in self.children],
        }


@dataclass(frozen=True)
class WbsUnplaced:
    """트리에 못 넣은 작업. 조용히 버리지 않는다(모듈 docstring)."""

    key: str
    title: str
    reason: str

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "reason": self.reason}


@dataclass(frozen=True)
class WbsResult:
    roots: tuple[WbsNode, ...]
    unplaced: tuple[WbsUnplaced, ...]
    # 표본 전체의 진행률. 루트들의 합이 아니라 **헤더와 같은 입력, 같은 함수**다.
    progress: ProgressResult

    def as_dict(self) -> dict:
        return {
            "roots": [n.as_dict() for n in self.roots],
            "unplaced": [u.as_dict() for u in self.unplaced],
            "progress": self.progress.as_dict(),
        }


def wbs_item_from_ticket(row, parent_key: str | None = None) -> WbsItem:
    """`tickets` 행 하나를 트리 한 칸으로. 질의는 repository 가 한다.

    상위는 **인자로 받는다** — 진행률과 같은 규약이다(progress.py::task_from_ticket).
    여기서 표를 읽으면 이 파일이 순수 함수가 아니게 되고, 트리가 헤더와 다른 계층을
    쓸 자리가 생긴다.
    """
    return WbsItem(
        task=task_from_ticket(row, parent_key),
        title=row.title or "",
        url=row.url,
        ticket_number=row.notion_ticket_number,
        ticket_key=row.canonical_key,
    )


def _sort_key(item: WbsItem) -> tuple:
    """형제 정렬: 티켓 번호 순, 없으면 뒤로, 같으면 제목, **그래도 같으면 키**.

    마지막 키가 전순서를 만든다. 없으면 번호가 비슷한 형제들의 순서를 파이썬 정렬이 아니라
    질의 결과 순서가 정하게 되고, 그건 요청마다 달라질 수 있다 - 새로고침할 때마다 트리가
    뒤섞이면 사용자는 자기가 보던 줄을 다시 못 찾는다.
    """
    number = item.ticket_number
    return (number is None, number or 0, item.title, item.task.key)


def _children_map(items_by_key: dict[str, WbsItem]) -> dict[str, list[str]]:
    """부모 키 → 자식 키들. **표본 안에 부모가 있을 때만** 잇는다.

    표본 밖 부모(다른 프로젝트의 작업)를 가리키는 작업은 여기 안 걸리므로 루트가 된다.
    자식까지 숨기면 이 프로젝트에 걸린 일이 통째로 사라진다(progress.py 와 같은 규칙).
    """
    out: dict[str, list[str]] = {}
    for key, item in items_by_key.items():
        parent = item.task.parent_key
        if parent and parent in items_by_key:
            out.setdefault(parent, []).append(key)
    return out


def _ordered(keys, items_by_key: dict[str, WbsItem]) -> list[str]:
    return sorted(keys, key=lambda k: _sort_key(items_by_key[k]))


def _descendants(key: str, children: dict[str, list[str]]) -> list[str]:
    """깊이 상한에 걸려 통째로 못 그린 가지. 여기도 방문 표시를 둔다 - 이 함수가 불리는
    상황은 이미 '데이터가 이상하다' 는 뜻이라 트리라는 가정을 더 믿지 않는다."""
    out: list[str] = []
    seen: set[str] = {key}
    frontier = list(children.get(key, ()))
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        out.append(current)
        frontier.extend(children.get(current, ()))
    return out


def build_wbs(items) -> WbsResult:
    """작업 목록 하나에서 트리와 진행률을 낸다.

    `items` 는 `WbsItem` 들이다. 이 표본이 곧 세계다 - 부모, 자식 판정도 여기 있는 것들
    사이에서만 한다(`compute_progress` 의 리프 판정과 같은 규약이라 두 결과가 어긋나지 않는다).
    """
    # 한 번만 훑는다. 아래 전체 진행률은 **이 목록 그대로**를 쓴다 - 트리를 만들며 걸러 낸
    # 것으로 세면 헤더와 같은 값이라는 보장이 사라진다.
    rows = list(items)

    items_by_key: dict[str, WbsItem] = {}
    for item in rows:
        key = item.task.key
        # 키가 겹치면 먼저 온 것을 남긴다. `notion_page_id` 는 unique 라 정상 상태에서는
        # 겹치지 않지만, 겹친 채로 자식 목록을 두 번 붙이면 같은 가지가 두 번 그려진다.
        if key and key not in items_by_key:
            items_by_key[key] = item

    children = _children_map(items_by_key)
    roots = [k for k, it in items_by_key.items()
             if not (it.task.parent_key and it.task.parent_key in items_by_key)]

    placed: set[str] = set()
    too_deep: list[str] = []

    def build(key: str, depth: int) -> tuple[WbsNode, list[Task]]:
        item = items_by_key[key]
        placed.add(key)
        kids: list[WbsNode] = []
        subtree: list[Task] = [item.task]
        if depth < MAX_WBS_DEPTH:
            for child_key in _ordered(children.get(key, ()), items_by_key):
                # 이미 그린 노드를 다시 그리지 않는다. 위 논증대로면 일어날 수 없지만,
                # 논증이 틀린 날 죽는 것은 워커다.
                if child_key in placed:
                    continue
                child, child_tasks = build(child_key, depth + 1)
                kids.append(child)
                subtree.extend(child_tasks)
        else:
            too_deep.extend(_descendants(key, children))
        node = WbsNode(
            key=key,
            title=item.title,
            status=item.task.status,
            est_wd=item.task.est_wd,
            ticket_number=item.ticket_number,
            ticket_key=item.ticket_key,
            depth=depth,
            children=tuple(kids),
            # 하위 트리만 센다. 자기 자신은 자식이 있으면 `compute_progress` 가 부모로
            # 알아서 뺀다 - 리프 판정을 여기서 다시 하지 않는다.
            progress=compute_progress(subtree),
        )
        return node, subtree

    root_nodes = [build(key, 0)[0] for key in _ordered(roots, items_by_key)]

    unplaced: list[WbsUnplaced] = []
    for key in sorted(too_deep):
        unplaced.append(WbsUnplaced(
            key=key, title=items_by_key[key].title, reason=UNPLACED_TOO_DEEP,
        ))
    too_deep_set = set(too_deep)
    for key in sorted(items_by_key):
        # 루트에서 도달하지 못했고 깊이 때문도 아니라면 순환 안에 있는 것이다
        # (부모가 한 칸짜리 필드라 그 밖의 경우가 없다 - 모듈 docstring).
        if key not in placed and key not in too_deep_set:
            unplaced.append(WbsUnplaced(
                key=key, title=items_by_key[key].title, reason=UNPLACED_CYCLE,
            ))

    return WbsResult(
        roots=tuple(root_nodes),
        unplaced=tuple(unplaced),
        # 헤더와 **같은 입력, 같은 함수**. 못 그린 작업도 여기에는 들어간다 - 트리에 안
        # 보인다고 분모에서 빼면 순환 하나에 프로젝트 진행률이 통째로 흔들린다.
        progress=compute_progress([it.task for it in rows]),
    )
