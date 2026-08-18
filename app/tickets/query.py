"""티켓 미러(`ticket_cache`) 목록 질의 조립 — 조건·정렬·자르기.

`repository_notion.py` 에서 떼어 낸 이유는 크기만이 아니다. 저 파일은 **Notion 이라는 구현
세부가 사는 곳**이고(속성 이름·스키마·쓰기 페이로드), 여기 있는 것들은 Notion 을 한 글자도
모른다 - 우리 표 하나에 조건을 거는 SQL 이다. 소스를 자체 DB 로 바꿔도 이 파일은 그대로 산다.

이 모듈이 지키는 것 셋:

  * 다중값 열(`project_ids` / `assignee_notion_ids`)은 반드시 `token()` 으로 감싸 맞춘다.
  * 제외 조건에는 `IS NULL` 을 함께 건다 - `NOT IN` 은 NULL 앞에서 행을 조용히 떨어뜨린다.
  * 정렬은 **전순서**여야 한다(Z9). 아니면 OFFSET 페이지네이션이 행을 반복하거나 빠뜨린다.
"""

from __future__ import annotations

from sqlalchemy import false, or_

from app.core.models_base import NAMES_SEP
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.tickets.repository import PageSpec, TicketFilters


def token(value: str) -> str:
    """sentinel-wrapped 토큰 하나 — LIKE contains 로 '정확한 토큰' 매칭을 하기 위한 형태."""
    return NAMES_SEP + value + NAMES_SEP


# 목록 정렬: 마감 빠른 순, 없으면 뒤로, 같으면 티켓 번호 순, **그래도 같으면 id 순**.
#
# 마지막 `id` 가 Z9 다. `due_date` 만으로 정렬하면 같은 날짜 행들의 상대 순서를 DB 가 마음대로
# 정하고, 그 순간 OFFSET 페이지네이션은 **1페이지에 나온 행이 2페이지에 또 나오거나 아예
# 빠지는** 결과를 낸다. 사용자에게는 "티켓이 사라졌다" 로 보이고, 새로고침하면 돌아와서
# 재현조차 안 된다. `notion_ticket_number` 도 NULL 일 수 있으므로(마감 없는 티켓과 같은
# 처지) 유일한 열인 PK 까지 붙여야 전순서가 된다.
ORDER = (
    TicketCache.due_date.asc().nulls_last(),
    TicketCache.notion_ticket_number.asc().nulls_last(),
    TicketCache.id.asc(),
)


def page_slice(items: list, page: PageSpec | None) -> list:
    """페이지 한 장. `page` 가 없거나 상한이 없으면 자르지 않는다(집계 호출부의 기존 계약)."""
    if page is None or page.limit is None:
        return items
    return items[page.offset:page.offset + page.limit]


def filter_clauses(f: TicketFilters | None) -> list:
    """도메인 조건 → SQLAlchemy 불리언 절 목록. 조건이 없으면 빈 목록이다.

    ## 다중값 열은 반드시 `token()` 으로 감싼다

    `project_ids` / `assignee_notion_ids` 는 NAMES_SEP 로 감싸 이어 붙인 문자열이다. 여기에
    `contains("abc")` 를 그냥 걸면 `abcd` 를 담은 행이 함께 걸린다 - 외부 page id 는 서로
    접두사가 되는 일이 흔하고, 그 오탐은 "남의 프로젝트 티켓이 내 필터에 섞인다" 로 나타나
    눈에 잘 안 띈다. 구분자로 감싼 토큰이면 부분일치가 곧 정확일치다.

    ## NULL 을 빠뜨리지 않는다

    `NOT IN` 은 NULL 앞에서 NULL 이 되고, SQL 은 그것을 '거짓'처럼 취급해 **행을 떨어뜨린다**.
    상태가 비어 있는 티켓과 page id 가 없는(source='native') 티켓이 제외 조건 하나 때문에
    통째로 사라지는 것이 그 증상이라, 두 제외 조건에는 `IS NULL` 을 함께 건다.
    """
    if f is None:
        return []
    out: list = []
    if f.status:
        out.append(TicketCache.status == f.status)
    if f.priority:
        out.append(TicketCache.priority == f.priority)
    if f.difficulty:
        out.append(TicketCache.difficulty == f.difficulty)
    if f.category:
        out.append(TicketCache.category == f.category)
    if f.project_id:
        out.append(TicketCache.project_ids.contains(token(f.project_id), autoescape=True))
    if f.assignee_id:
        out.append(
            TicketCache.assignee_notion_ids.contains(token(f.assignee_id), autoescape=True)
        )
    if f.search:
        # icontains = 대소문자 무시 LIKE. autoescape 로 사용자가 넣은 %/_ 가 와일드카드가
        # 되지 않게 막는다(안 막으면 '%' 한 글자가 전체 조회가 된다).
        out.append(TicketCache.title.icontains(f.search, autoescape=True))
    start, end = f.due_range
    if start is not None or end is not None:
        out.append(TicketCache.due_date.is_not(None))
        if start is not None:
            out.append(TicketCache.due_date >= start)
        if end is not None:
            out.append(TicketCache.due_date < end)
    if f.exclude_statuses:
        out.append(or_(
            TicketCache.status.is_(None),
            TicketCache.status.notin_(tuple(sorted(f.exclude_statuses))),
        ))
    if f.exclude_page_ids:
        out.append(or_(
            TicketCache.notion_page_id.is_(None),
            TicketCache.notion_page_id.notin_(tuple(sorted(f.exclude_page_ids))),
        ))
    if f.project_any_of is not None:
        # 범위 판정의 질의판(0060). 티켓의 소속은 **프로젝트**이고, 그 소속은 동기화가
        # 이미 한 컬럼으로 해석해 뒀다(`app/tickets/project_link.py`).
        #
        # 두 조건을 **함께** 건다:
        #   * `project_link == 'ok'` — 소속을 판정할 수 있는 행만. relation 이 0개거나
        #     2개 이상이면 어느 부서 것인지 모르는 것이고, 모르면 닫는다(fail-closed).
        #   * `project_uid IN (...)` — 그 프로젝트가 이 사람 범위 안인가.
        #
        # 빈 집합은 아무것도 안 보인다 - `false()` 는 SQLite 에서 `0 = 1` 로 나와 조건을
        # 빼먹은 코드와 눈으로 구별된다(scope.py 의 MATCH_NOTHING 과 같은 이유).
        uids = f.project_any_of.uids
        if not uids:
            out.append(false())
        else:
            out.append(TicketCache.project_link == PROJECT_LINK_OK)
            out.append(TicketCache.project_uid.in_(tuple(sorted(uids))))
    return out
