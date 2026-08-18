"""티켓 ↔ 프로젝트 연결 해석 — **외부 relation 을 Portal 소유로 옮기는 단 하나의 자리**.

## 왜 해석 단계가 따로 있는가

`ticket_cache.project_ids` 는 외부 소스(Notion)의 relation id 목록을 그대로 적어 둔 **원본**
이다. 다중값이고, 0개일 수도 2개 이상일 수도 있고, 가리키는 프로젝트가 Portal 에 아직
없을 수도 있다. 권한 계산이 그 원본을 직접 읽으면 그 세 가지 경우를 판정하는 코드가 읽는
곳마다 생기고, 그중 한 곳이라도 "그럼 첫 번째 것으로 하자" 라고 정하는 순간 그 티켓은
남의 부서로 샌다.

그래서 해석을 **동기화 시점에 한 번** 하고 결과를 두 컬럼에 적어 둔다:

    project_uid   Portal 프로젝트 id (해석 성공했을 때만)
    project_link  ok / missing / ambiguous / unresolved

권한 계산은 `project_link == 'ok'` 인 행만 프로젝트 ACL 로 판정하고 나머지는 닫는다.
"판정할 수 없으면 닫는다" 를 한 곳에서 지키는 구조다.

## 임의로 하나를 고르지 않는다

relation 이 둘이면 `ambiguous` 로 남긴다. 그 티켓은 정합성 오류로 진단 화면에 뜨고,
사람이 원본에서 하나로 정리한다. 코드가 고르면 그 선택은 화면에 정상으로 보이기 때문에
**틀려도 아무도 신고하지 않는다.**

## 다시 해석해야 하는 순간이 있다

프로젝트 동기화가 티켓 동기화보다 늦게 돌면, 그 사이 티켓은 `unresolved` 다(가리키는
프로젝트가 Portal 에 아직 없다). 프로젝트가 들어온 뒤 티켓을 다시 안 훑으면 그 티켓들은
영영 닫힌 채로 남는다 — `reresolve_all()` 이 프로젝트 동기화 뒤에 그것을 푼다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models_base import split_names
from app.projects.models import Project
from app.tickets.models import (
    PROJECT_LINK_AMBIGUOUS,
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    PROJECT_LINK_UNRESOLVED,
    TicketCache,
)


def portal_project_map(db: Session) -> dict[str, str]:
    """외부 page id → Portal 프로젝트 id.

    보관(archive)된 프로젝트도 넣는다 — 보관은 상태이지 소속이 아니고, 여기서 빼면 보관된
    프로젝트의 티켓이 통째로 `unresolved`(= 아무에게도 안 보임)가 된다.
    """
    rows = db.execute(
        select(Project.notion_page_id, Project.id).where(Project.notion_page_id.is_not(None))
    ).all()
    return {r[0]: r[1] for r in rows if r[0]}


def resolve(external_ids, portal_by_external: dict[str, str]) -> tuple[str | None, str]:
    """relation id 목록 → (Portal 프로젝트 id, 연결 상태).

    ``external_ids`` 는 리스트이거나 저장된 다중값 문자열이다 — 두 호출부(동기화 파서,
    이미 저장된 행)를 한 함수로 받기 위해서다.
    """
    if isinstance(external_ids, str):
        ids = split_names(external_ids)
    else:
        ids = [i for i in (external_ids or []) if i]
    if not ids:
        return None, PROJECT_LINK_MISSING
    if len(ids) > 1:
        return None, PROJECT_LINK_AMBIGUOUS
    uid = portal_by_external.get(ids[0])
    if not uid:
        return None, PROJECT_LINK_UNRESOLVED
    return uid, PROJECT_LINK_OK


def apply_to_row(row: TicketCache, portal_by_external: dict[str, str]) -> bool:
    """행 하나의 두 컬럼을 갱신한다. 바뀌었으면 True.

    바뀔 때만 쓰는 이유는 `app/projects/sync.py::_upsert` 와 같다 — 값이 그대로인데 대입만
    해도 행이 dirty 가 되고, 그 UPDATE 에 `TimestampMixin.updated_at` 의 `onupdate` 가 딸려
    붙어 회차마다 전 티켓의 갱신 시각이 같은 값으로 덮인다.
    """
    uid, link = resolve(row.project_ids, portal_by_external)
    if row.project_uid == uid and row.project_link == link:
        return False
    row.project_uid = uid
    row.project_link = link
    return True


def reresolve_all(db: Session) -> dict[str, int]:
    """티켓 전량을 다시 해석한다. 상태별 건수를 돌려준다(진단·로그용).

    프로젝트 동기화 **뒤에** 부른다. 티켓 수가 수천 규모라 한 번 훑는 비용이 작고, 부분만
    고르려면 "무엇이 바뀌었나"를 또 추적해야 하는데 그 추적이 틀리면 티켓이 조용히 닫힌 채
    남는다 — 전량 훑기가 더 싸고 더 안전하다.
    """
    portal = portal_project_map(db)
    counts: dict[str, int] = {
        PROJECT_LINK_OK: 0, PROJECT_LINK_MISSING: 0,
        PROJECT_LINK_AMBIGUOUS: 0, PROJECT_LINK_UNRESOLVED: 0,
    }
    changed = 0
    for row in db.execute(select(TicketCache)).scalars():
        if apply_to_row(row, portal):
            changed += 1
        counts[row.project_link] = counts.get(row.project_link, 0) + 1
    counts["changed"] = changed
    return counts
