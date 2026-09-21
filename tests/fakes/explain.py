"""`EXPLAIN <select>` — **바인드 파라미터를 그대로 둔 채** 플래너에게 계획을 묻는다.

## 왜 문자열로 렌더링해서 묻지 않는가

`literal_binds` 로 SQL 을 글자로 펼치면 `%` 와 escape 문자까지 렌더러가 다시 escape 한다.
그러면 `LIKE '%…%' ESCAPE '\\'` 가 **문법 오류**가 되거나 다른 패턴이 되고, 검사가 제품이
아니라 렌더링을 시험하게 된다(실제로 한 번 그렇게 빨개졌다). 여기서는 문장 앞에 `EXPLAIN`
만 붙이고 값은 드라이버가 바인드로 넘긴다 — 제품이 실제로 보내는 모양과 같다.

## 「쓰는가」가 아니라 「쓸 수 있는가」

현 코퍼스가 작아서 플래너가 seq scan 을 고르는 것은 **맞는 판단**이다(D-209). 인덱스 식과
질의 식이 어긋났는지를 보려면 `plan_for(..., force_index=True)` 로 seq scan 을 끄고 묻는다 —
식이 어긋나면 강제해도 인덱스를 못 쓴다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable


class Explain(Executable, ClauseElement):
    """`EXPLAIN` 을 앞에 붙인 문장. 실행은 하지 않고 계획만 받는다."""

    inherit_cache = False

    def __init__(self, statement, *, as_json: bool = False):
        self.statement = statement
        self.as_json = as_json


@compiles(Explain, "postgresql")
def _compile_explain(element, compiler, **kw):  # pragma: no cover - 컴파일러 훅
    head = "EXPLAIN (FORMAT JSON) " if element.as_json else "EXPLAIN "
    return head + compiler.process(element.statement, **kw)


def plan_for(db, statement, *, force_index: bool = False) -> str:
    """이 질의의 계획 한 덩이(줄바꿈으로 이은 문자열).

    `force_index=True` 는 이 트랜잭션 안에서만 seq scan 을 끈다(`SET LOCAL`). 시험의
    트랜잭션이 끝나면 설정도 함께 사라진다.
    """
    if force_index:
        db.execute(text("SET LOCAL enable_seqscan = off"))
    return "\n".join(db.execute(Explain(statement)).scalars().all())


def plan_tree(db, statement) -> dict:
    """계획을 나무로 — 맨 위 노드(`Plan`) 하나. 노드마다 `Node Type` · `Relation Name` ·
    `Parent Relationship`(Outer · Inner · SubPlan …) 과 자식 목록(`Plans`)이 있다.

    글자 계획으로는 「이 스캔이 조인의 어느 쪽에 있는가」를 읽기 어렵다. 같은 `Nested Loop` 라도
    바깥쪽에서 한 번 훑는 것과 안쪽에서 행마다 다시 훑는 것은 비용이 전혀 다르다.
    """
    return db.execute(Explain(statement, as_json=True)).scalar()[0]["Plan"]


def walk(node: dict):
    """계획 나무의 노드를 위에서부터 하나씩."""
    yield node
    for child in node.get("Plans", ()):
        yield from walk(child)
