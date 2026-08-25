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

from datetime import timedelta

from sqlalchemy import case, false, or_

from app.core.dates import parse_date
from app.core.models_base import NAMES_SEP
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.tickets.repository import PageSpec, TicketFilters, as_filter_values
from app.work import workflow


def token(value: str) -> str:
    """sentinel-wrapped 토큰 하나 — LIKE contains 로 '정확한 토큰' 매칭을 하기 위한 형태."""
    return NAMES_SEP + value + NAMES_SEP


# 목록 정렬: 화면이 sort 를 안 주면 **예전 전순서**를 쓴다(마감 → 번호 → id).
# API 목록은 `TicketFilters.sort_key` 로 기본 `created_at` 을 넣는다. 내부 집계
# 호출부는 sort_key 를 비워 두어 이 ORDER 를 그대로 탄다 — 화면 기본 정렬을 바꾸려고
# 리포트 순서까지 바꾸지 않는다.
#
# 마지막 `id` 가 Z9 다. 1차 키만으로 정렬하면 같은 값 행들의 상대 순서를 DB 가 마음대로
# 정하고, 그 순간 OFFSET 페이지네이션은 **1페이지에 나온 행이 2페이지에 또 나오거나 아예
# 빠지는** 결과를 낸다.
ORDER = (
    TicketCache.due_date.asc().nulls_last(),
    TicketCache.notion_ticket_number.asc().nulls_last(),
    TicketCache.id.asc(),
)

# 클라이언트가 보낸 컬럼명을 SQL 에 붙이지 않는다. 이 표에 있는 키만 정렬한다.
SORT_KEYS = frozenset({
    "created_at", "updated_at", "due_date", "title", "status", "priority",
    "est_wd", "act_wd", "tid", "key",
})

# 우선순위는 업무 순서다. 문자열 가나다(긴급이 높음보다 뒤)로 정렬하면 틀린 일이 된다.
_PRIORITY_RANK = {
    "긴급": 10, "urgent": 10, "critical": 10,
    "높음": 20, "high": 20, "1": 20,
    "보통": 30, "medium": 30, "normal": 30, "2": 30,
    "낮음": 40, "low": 40, "3": 40,
}


def _status_rank():
    return case(
        {s.key: s.sort_order for s in workflow.STATUSES},
        value=TicketCache.status,
        else_=10_000,
    )


def _priority_rank():
    return case(_PRIORITY_RANK, value=TicketCache.priority, else_=10_000)


def _sort_column(key: str):
    if key in ("tid", "key"):
        return TicketCache.notion_ticket_number
    if key == "status":
        return _status_rank()
    if key == "priority":
        return _priority_rank()
    return getattr(TicketCache, key)


def order_clause(filters: TicketFilters | None):
    """필터 객체가 고른 1차 키 + 방향, 항상 id 타이브레이크.

    sort_key 가 없거나 allowlist 밖이면 위 `ORDER`(내부 기본)로 떨어진다.
    """
    if filters is None or not filters.sort_key:
        return ORDER
    key = filters.sort_key
    if key not in SORT_KEYS:
        return ORDER
    col = _sort_column(key)
    descending = (filters.sort_dir or "desc").lower() != "asc"
    primary = col.desc().nulls_last() if descending else col.asc().nulls_last()
    tie = TicketCache.id.desc() if descending else TicketCache.id.asc()
    return (primary, tie)


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
    statuses = as_filter_values(f.status)
    if statuses:
        out.append(TicketCache.status.in_(statuses))
    priorities = as_filter_values(f.priority)
    if priorities:
        out.append(TicketCache.priority.in_(priorities))
    difficulties = as_filter_values(f.difficulty)
    if difficulties:
        out.append(TicketCache.difficulty.in_(difficulties))
    if f.category:
        out.append(TicketCache.category == f.category)
    projects = as_filter_values(f.project_id)
    if projects:
        project_bits = [
            or_(
                TicketCache.project_ids.contains(token(pid), autoescape=True),
                TicketCache.project_uid == pid,
            )
            for pid in projects
        ]
        out.append(or_(*project_bits))
    assignees = as_filter_values(f.assignee_id)
    if assignees:
        out.append(or_(*(
            TicketCache.assignee_notion_ids.contains(token(aid), autoescape=True)
            for aid in assignees
        )))
    if f.search:
        # icontains = 대소문자 무시 LIKE. autoescape 로 사용자가 넣은 %/_ 가 와일드카드가
        # 되지 않게 막는다(안 막으면 '%' 한 글자가 전체 조회가 된다).
        out.append(TicketCache.title.icontains(f.search, autoescape=True))
    start, end = (parse_date(v) for v in f.due_range)
    if start is not None or end is not None:
        out.append(TicketCache.due_date.is_not(None))
        if start is not None:
            out.append(TicketCache.due_date >= start)
        if end is not None:
            out.append(TicketCache.due_date < end)
    created_from = parse_date(f.created_from) if f.created_from else None
    created_to = parse_date(f.created_to) if f.created_to else None
    if created_from is not None:
        out.append(TicketCache.created_at >= created_from)
    if created_to is not None:
        out.append(TicketCache.created_at < created_to + timedelta(days=1))
    if f.est_wd_min is not None:
        out.append(TicketCache.est_wd.is_not(None))
        out.append(TicketCache.est_wd >= f.est_wd_min)
    if f.est_wd_max is not None:
        out.append(TicketCache.est_wd.is_not(None))
        out.append(TicketCache.est_wd <= f.est_wd_max)
    if f.act_wd_min is not None:
        out.append(TicketCache.act_wd.is_not(None))
        out.append(TicketCache.act_wd >= f.act_wd_min)
    if f.act_wd_max is not None:
        out.append(TicketCache.act_wd.is_not(None))
        out.append(TicketCache.act_wd <= f.act_wd_max)
    if f.exclude_statuses:
        out.append(or_(
            TicketCache.status.is_(None),
            TicketCache.status.notin_(tuple(sorted(f.exclude_statuses))),
        ))
    if f.exclude_page_ids:
        # 휴지통에 있는 티켓을 뺀다. **행의 id 도 함께 본다** (S14).
        #
        # 예전에는 `notion_page_id` 만 봤고, `NULL` 인 행(자체 DB 에서 만든 티켓)은 조건
        # 자체를 통과시켰다 — 그때는 그 행이 아직 없었으므로 「빼지 말라」는 뜻으로 옳았다.
        # 이제는 자체 DB 티켓이 실제로 생기고, 그 티켓의 휴지통 키는 **행의 uuid** 다
        # (`repository_native` 의 식별자 규약). 안 보면 영구 삭제 대기 중인 티켓이 목록에
        # 남고, 파이썬 그물(`service._drop_trashed`)이 뒤늦게 걸러도 **자르기 뒤**라
        # `total` 이 실제보다 크게 나온다.
        excluded = tuple(sorted(f.exclude_page_ids))
        out.append(or_(
            TicketCache.notion_page_id.is_(None),
            TicketCache.notion_page_id.notin_(excluded),
        ))
        out.append(TicketCache.id.notin_(excluded))
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
