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

from sqlalchemy import case, false, func, or_, select

from app.core.dates import parse_date
from app.core.models_base import NAMES_SEP
from app.core.search_text import contains_folded
from app.tickets.models import PROJECT_LINK_OK, TicketCache, api_page_id_expr
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
#
# 화면이 머리에 정렬 단추를 그린 열은 **전부** 여기 있어야 한다. 없는 키는 조용히 생성일
# 정렬로 떨어지고(`app/tickets/service.py::build_filters`), 사용자에게는 「눌렀는데 순서가
# 그대로」로만 보인다 — 난이도가 그렇게 빠져 있었다. 작업 보드의 백로그도 이 표를 그대로
# 쓴다(`app/work/service.py::backlog`).
SORT_KEYS = frozenset({
    "created_at", "updated_at", "due_date", "title", "status", "priority", "difficulty",
    "est_wd", "act_wd", "tid", "key",
})

# 우선순위는 업무 순서다. 문자열 가나다(긴급이 높음보다 뒤)로 정렬하면 틀린 일이 된다.
# 「중간」은 이관 원본의 선택지 이름이다(`docs/platform/INVENTORY/07_NOTION.md` — 높음 · 중간 ·
# 낮음). 표에 없으면 그 값만 「모르는 값」이 되어 낮음보다 뒤로 밀린다.
_PRIORITY_RANK = {
    "긴급": 10, "urgent": 10, "critical": 10,
    "높음": 20, "high": 20, "1": 20,
    "보통": 30, "중간": 30, "medium": 30, "normal": 30, "2": 30,
    "낮음": 40, "low": 40, "3": 40,
}

# 난이도는 **폼 드롭다운과 같은 순서**로 선다(`repository_native._sorted_options`): 숫자 등급이
# 먼저 숫자 크기대로 서고, 그다음이 상 · 중 · 하다. 이관 원본의 난이도는 1~6 선택지이고
# (`docs/platform/INVENTORY/07_NOTION.md`), 상 · 중 · 하로 적힌 행도 있다. 이 표에 없는 값은
# 순위가 없어서 어느 방향이든 끝에 선다.
_DIFFICULTY_RANK = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "상": 11, "중": 12, "하": 13,
}


# 순위 표 셋은 **모르는 값에 순위를 주지 않는다**(`ELSE` 가 없다 — 결과가 NULL 이다). 예전에는
# 모르는 값과 빈 값을 `10_000` 으로 보냈는데, 그러면 오름차순에서는 끝이지만 내림차순에서는
# **맨 앞**이 된다 — 우선순위를 내림차순으로 고르면 우선순위가 빈 티켓이 첫 줄을 차지했다.
# NULL 이면 아래 `sort_order` 의 `nulls_last()` 가 어느 방향이든 끝에 세운다.
def _status_rank():
    return case(
        {s.key: s.sort_order for s in workflow.STATUSES},
        value=TicketCache.status,
    )


def _priority_rank():
    return case(_PRIORITY_RANK, value=TicketCache.priority)


def _difficulty_rank():
    return case(_DIFFICULTY_RANK, value=TicketCache.difficulty)


def _sort_columns(key: str) -> tuple:
    """정렬 키 하나가 세우는 열들. 대부분 하나이고, 티켓 이름은 둘이다.

    티켓 열이 그리는 것은 이름(`<CODE>-<SEQ>`, `canonical_key`)이다. 그래서 정렬도 그 이름의
    두 조각 — 프로젝트 코드, 그 안의 번호 — 으로 한다. 예전에는 옛 소스의 번호
    (`notion_ticket_number`)로 정렬했는데, 그 값은 이름이 아니고(D-281) 이 서버에서 만든
    티켓에는 아예 없다. 그래서 새 티켓이 전부 끝으로 밀린 채 서로의 순서도 없었다. 번호는
    숫자로 비교한다 — 문자열로 비교하면 「-10」이 「-9」 앞에 선다.
    """
    if key in ("tid", "key"):
        return (func.split_part(TicketCache.canonical_key, "-", 1), TicketCache.seq)
    if key == "status":
        return (_status_rank(),)
    if key == "priority":
        return (_priority_rank(),)
    if key == "difficulty":
        return (_difficulty_rank(),)
    return (getattr(TicketCache, key),)


def sort_order(key: str, *, descending: bool) -> tuple:
    """정렬 키 하나 → `ORDER BY` 절 묶음. **목록 정렬 계약의 한 곳**이다.

    세 가지를 언제나 지킨다: 허용 표(`SORT_KEYS`) 밖의 키는 받지 않는다, 값이 없는(NULL)
    행은 어느 방향이든 끝에 선다, 마지막에 id 를 같은 방향으로 붙여 전순서를 만든다(Z9).
    티켓 목록(`order_clause`)과 작업 보드의 백로그가 같은 키로 같은 순서를 받는다.
    """
    if key not in SORT_KEYS:
        raise ValueError(f"모르는 정렬 키입니다: {key}")
    parts = [
        col.desc().nulls_last() if descending else col.asc().nulls_last()
        for col in _sort_columns(key)
    ]
    parts.append(TicketCache.id.desc() if descending else TicketCache.id.asc())
    return tuple(parts)


def order_clause(filters: TicketFilters | None):
    """필터 객체가 고른 1차 키 + 방향, 항상 id 타이브레이크.

    sort_key 가 없거나 allowlist 밖이면 위 `ORDER`(내부 기본)로 떨어진다.
    """
    if filters is None or not filters.sort_key:
        return ORDER
    key = filters.sort_key
    if key not in SORT_KEYS:
        return ORDER
    descending = (filters.sort_dir or "desc").lower() != "asc"
    return sort_order(key, descending=descending)


def number_range_clauses(column, low: float | None, high: float | None) -> list:
    """숫자 범위 — **양 끝을 포함**한다. 범위가 걸리면 값이 없는(NULL) 행은 빠진다.

    티켓 목록의 예상 · 실제 WD 와 작업 보드의 예상 WD 가 이 한 벌을 쓴다. 두 화면이 같은 범위를
    다르게 읽으면(한쪽만 끝을 포함하거나 한쪽만 빈 값을 남기면) 같은 조건이 다른 수를 낸다.
    """
    out: list = []
    if low is None and high is None:
        return out
    out.append(column.is_not(None))
    if low is not None:
        out.append(column >= low)
    if high is not None:
        out.append(column <= high)
    return out


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
    # 검색어는 제목 **과 티켓 이름**(`ABC-12`)을 본다 — 작업 보드와 같은 뜻 하나다. 사람들은
    # 티켓을 번호로 기억하고, 한 화면에서 찾던 이름이 다른 화면에서 안 걸리면 검색이 아니라
    # 고장으로 보인다. 대조 규칙은 공용 하나다(`app/core/search_text.py` — 양쪽 접기 · escape).
    # 접은 뒤 빈 검색어(공백·제로폭 공백만)는 조건이 아니다.
    search_clause = contains_folded((TicketCache.title, TicketCache.canonical_key), f.search)
    if search_clause is not None:
        out.append(search_clause)
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
    out.extend(number_range_clauses(TicketCache.est_wd, f.est_wd_min, f.est_wd_max))
    out.extend(number_range_clauses(TicketCache.act_wd, f.act_wd_min, f.act_wd_max))
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


def not_trashed_clause():
    """이 티켓이 휴지통에 없다 - **SQL 절**로. 휴지통을 빼야 하는 모든 질의가 이 한 벌을 쓴다.

    작업 보드(`app/work/service.py`)가 처음 만든 절을 여기로 옮겼다(계획 2.6). 프로젝트 진행률 ·
    Health(`app/projects/repository.py`)와 월간 리포트, 정합성 검사가 각자 휴지통을 모르고 셌다 -
    휴지통에 넣은 티켓이 진행률 분모에 남고 리포트의 담당 수에 들어갔다.

    휴지통 키는 API 가 부르는 이름(`api_page_id_expr`)이다. 자체 DB 티켓은 행의 uuid, 옛 티켓은
    Notion page id 라 두 축을 한 식으로 본다. 파이썬 집합으로 거르면 쪽 단위 목록에서 `total` 과
    받은 수가 어긋난다(보드가 겪은 일이다).
    """
    from app.trash.models import TRASH_TICKET, TrashItem

    return ~(
        select(TrashItem.id)
        .where(
            TrashItem.item_type == TRASH_TICKET,
            TrashItem.notion_page_id == api_page_id_expr(),
        )
        .correlate(TicketCache)
        .exists()
    )
