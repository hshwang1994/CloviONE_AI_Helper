"""문서 생성 이력 조회 + **범위 판정** (§0-A).

목록·상세·재시도가 **이 조건 하나**만 쓴다. 판정을 두 벌로 적으면 한쪽만 고쳐지고, 증상은
"목록엔 보이는데 id 로는 404"(또는 그 반대)가 된다 — 찾기 어려운 모양이다. 그래서 단건도
`db.get` 이 아니라 **같은 조건이 붙은 SELECT** 로 찾는다(`app/jobs/repository.py::get_in_scope`
와 같은 이유): 먼저 꺼내 놓고 나중에 판정하면 판정을 빠뜨린 새 경로가 조용히 열린다.

## 무엇이 새는가

* **목록·상세** — 이력에는 요청자(라우터가 이메일·이름까지 해석해 붙인다)와 **요청 내용**
  (`config_json`: 어떤 Notion DB 를 어떤 필터로 뽑아 어디에 쓰는지, 프롬프트 이름, 기간)이
  들어 있다. 남의 팀이 무엇을 어디에 쓰고 있는지가 그대로 보인다.
* **재시도** — 읽기 유출이 아니라 **쓰기 실행**이다. 이력을 다시 큐에 올리면 워커가 러너
  (n8n)를 다시 불러 문서를 다시 만들고, 승인이 필요 없는 대상이면 발행까지 간다.
"""

from __future__ import annotations

from sqlalchemy import Select, or_ as sa_or, select
from sqlalchemy.orm import Session

from app.documents.models import DocumentGeneration


def scope_clause(visible: frozenset[str] | None):
    """요청자가 범위 안인가. 전역(``visible is None``)이면 ``None`` = 조건 없음.

    ``None`` 을 돌려주는 규약은 `app/core/scope.py::scope_filter` 와 같다 — 부르는 쪽이
    `if clause is None` 을 쓸 수밖에 없어 '범위를 고려했다'가 코드에 남는다.

    **요청자 없는 이력(`requested_by IS NULL`)은 남긴다.** 이 컬럼은 nullable 이고
    `service.request_generation` 이 `requested_by=None` 을 받는다 — 러너 핸들러가 그런 행을
    `requester.name="system"` 으로 다루는 것이 그 증거다
    (`app/jobs/handlers/document_generate.py::_requester`). 소유자 없는 자동 생성까지 가리면
    부서 관리자가 **자기 범위에 걸린 자동 처리 실패를 못 본다**. 잡 큐
    (`app/jobs/repository.py::scope_clause`)와 같은 규칙이고, 승인(`app/approvals/service.py`)
    에 이 갈래가 없는 것은 그쪽 `requested_by` 가 NOT NULL 이라 그런 행이 아예 존재하지
    않기 때문이지 규칙이 달라서가 아니다.
    """
    if visible is None:
        return None
    return sa_or(
        DocumentGeneration.requested_by.in_(tuple(sorted(visible))),
        DocumentGeneration.requested_by.is_(None),
    )


def apply_scope(stmt: Select, visible: frozenset[str] | None) -> Select:
    clause = scope_clause(visible)
    return stmt if clause is None else stmt.where(clause)


def get_in_scope(
    db: Session, generation_id: str, visible: frozenset[str] | None
) -> DocumentGeneration | None:
    """단건 조회 — 범위 밖이면 **아예 안 나온다**(부르는 쪽이 404 로 만든다)."""
    return db.execute(
        apply_scope(
            select(DocumentGeneration).where(DocumentGeneration.id == generation_id), visible
        )
    ).scalar_one_or_none()
