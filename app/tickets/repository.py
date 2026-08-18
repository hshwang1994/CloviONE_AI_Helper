"""티켓 저장소 인터페이스 + 도메인 DTO (§7.1.C).

여기에는 **Notion 이라는 단어가 나오는 곳이 두 군데뿐**이다: 외부 페이지 id(`page_id`)와 담당자
원본 id(`assignee_ids`). 속성 이름('진행상태' 등), 페이지네이션, 스키마 옵션 조회 같은 Notion
구현 세부는 전부 repository_notion.py 안에만 있다. 그래서 나중에 소스를 자체 DB로 바꿀 때
바꿔야 하는 파일이 '구현체 하나'로 좁혀진다.

지금 구현체는 Notion 하나뿐이다. NativeTicketRepository 스텁은 만들지 않는다 — 빈 모듈은
죽은 코드이고, 이 Protocol 이 이미 seam 을 문서화한다.

식별자 규약(§7.1.A):
  * `uid` = 우리 DB의 자체 UUID. 앞으로 내부 참조(댓글·휴지통·알림)는 이걸 쓴다.
  * `page_id` = Notion 페이지 id. 딥링크·휴지통·감사가 여전히 이 값을 키로 쓰므로 API 응답의
    `id` 는 계속 page_id 다. 캐시에 없는(=실시간으로 읽은) 티켓은 uid 가 None 이다.
  * `assignee_ids` = 원본 Notion user id. **응답에 절대 싣지 않는다**(§12.3 IDOR) — 서비스가
    앱 user_id/이름으로 해석한 뒤 그 결과만 내보낸다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

# 기한 버킷. 값 자체가 쿼리 파라미터로 나가므로 여기 한 곳에서만 정한다.
DUE_OVERDUE = "overdue"
DUE_THIS_WEEK = "this_week"
DUE_NEXT_WEEK = "next_week"
DUE_BUCKETS = (DUE_OVERDUE, DUE_THIS_WEEK, DUE_NEXT_WEEK)


def due_window(bucket: str | None, today: str | None) -> tuple[str | None, str | None]:
    """기한 버킷 → 반개구간 ``[start, end)`` ISO 날짜. 조건이 없으면 (None, None).

    주는 **월요일에 시작한다**. 경계를 여기 한 곳에서만 계산하는 이유: 미러 경로는 SQL 로,
    실시간 폴백 경로는 파이썬으로 같은 질문에 답해야 하는데, 경계 계산이 두 벌이면
    언젠가 한쪽만 고쳐지고 그 증상은 "월요일에만 목록이 다르다" 라서 아무도 못 찾는다.

    `today` 가 없으면 판정하지 않는다(조건 없음). 여기서 `date.today()` 를 부르면 시계가
    저장소 안으로 새어 들어와 테스트가 날짜에 따라 흔들린다 - 기준일은 항상 호출부의
    시계(app.state.clock)에서 온다.
    """
    if not bucket or not today:
        return (None, None)
    try:
        anchor = date.fromisoformat(today)
    except ValueError:
        return (None, None)
    monday = anchor - timedelta(days=anchor.weekday())
    if bucket == DUE_OVERDUE:
        return (None, today)                       # 마감이 오늘보다 앞선 것 = 지났다
    if bucket == DUE_THIS_WEEK:
        return (monday.isoformat(), (monday + timedelta(days=7)).isoformat())
    if bucket == DUE_NEXT_WEEK:
        return ((monday + timedelta(days=7)).isoformat(),
                (monday + timedelta(days=14)).isoformat())
    return (None, None)


@dataclass(frozen=True, slots=True)
class PageSpec:
    """한 페이지의 자리. ``limit=None`` 이면 **자르지 않는다**.

    자르지 않는 것이 기본값인 이유: 리포트·스프린트 집계는 목록을 전부 봐야 합계가 맞다.
    상한은 사람이 보는 화면 경로(라우터)에서만 준다.
    """

    offset: int = 0
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ProjectVisibility:
    """범위 안 프로젝트를 **두 표현으로** 들고 다닌다 (0060).

    같은 사실을 두 번 적는 것이 아니라, 두 경로가 서로 다른 키로 조인하기 때문이다:

      * `uids`     — Portal `projects.id`. 미러(SQL) 경로가 `ticket_cache.project_uid` 와 맞춘다.
      * `page_ids` — 외부 소스 page id. 실시간 폴백 경로의 DTO 가 그것만 들고 있다
        (`TicketDTO.project_ids`, 캐시가 준비되기 전에는 Portal id 를 알 수 없다).

    한 곳에서 함께 만들어 함께 넘기므로 두 표현이 갈라질 자리가 없다
    (`app/tickets/service.py::_project_visibility`).
    """

    uids: frozenset[str]
    page_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class TicketFilters:
    """목록 질의 조건 한 벌 — **소스를 모르는 도메인 값**이다.

    두 종류가 섞여 있고, 섞여 있는 것이 의도다.

      * 사용자가 화면에서 고른 것(상태·우선순위·난이도·프로젝트·담당자·기한·대분류·검색어)
      * 앱이 **반드시** 걸어야 하는 것(휴지통 제외, 완료·취소 제외, 범위 안 담당자)

    둘을 다른 통로로 넘기면 페이지네이션이 둘 중 한쪽 뒤에서만 일어나고, 그 순간 total 이
    사용자가 세는 건수와 달라진다. 한 곳에 모아 **같은 질의 안에서** 걸리게 한다.

    `project_any_of` 는 범위 판정의 질의판이다(0060): 티켓의 소속은 **프로젝트**이므로
    "그 프로젝트가 내 범위 안인가" 하나로 판정한다. `None` 은 제한 없음(전역 범위)이고,
    **빈 집합은 아무것도 안 보인다**(fail-closed) - 그 둘을 같은 값으로 표현하면 범위
    계산이 빈 답을 낸 순간 조용히 전 포탈이 열린다.

    예전에는 이 자리가 `assignee_any_of`(담당자 집합)였다. 담당자 축은 사람이 부서를 옮기면
    과거 티켓의 소속이 따라 움직이고, 담당자를 앱 사용자로 해석하지 못하는 티켓(운영 실측
    21.5%)은 어느 부서에도 안 잡혀 전사 버킷으로 새어 나갔다.
    """

    status: str | None = None
    priority: str | None = None
    difficulty: str | None = None
    project_id: str | None = None
    category: str | None = None
    search: str | None = None                       # 제목 부분일치
    due_bucket: str | None = None                   # DUE_BUCKETS 중 하나
    today: str | None = None                        # 기한 버킷 기준일 'YYYY-MM-DD'
    assignee_id: str | None = None                  # 소스 user id (서비스가 해석해 넣는다)
    # 아래 셋은 앱이 거는 조건 — 브라우저에서 오지 않는다.
    exclude_statuses: frozenset[str] = frozenset()
    exclude_page_ids: frozenset[str] = frozenset()
    project_any_of: "ProjectVisibility | None" = None

    @property
    def due_range(self) -> tuple[str | None, str | None]:
        return due_window(self.due_bucket, self.today)

    def matches(self, ticket: "TicketDTO") -> bool:
        """DTO 한 건이 이 조건을 지나는가 — **실시간 폴백 경로 전용**.

        미러 경로는 같은 조건을 SQL 로 건다(`repository_notion._filter_clauses`). 두 벌인 것이
        마음에 들지는 않지만, 대안은 킬 스위치(`ticket_source=notion`)와 첫 기동 직후에
        **필터와 페이지가 조용히 무시되는 것**이다 - 그건 "필터가 걸린 줄 알았는데 안 걸렸다"
        라서 사용자가 못 알아챈다. 두 경로가 같은 답을 내는지는 테스트가 고정한다
        (tests/integration/test_ticket_filters.py).
        """
        if self.status and ticket.status != self.status:
            return False
        if self.priority and ticket.priority != self.priority:
            return False
        if self.difficulty and ticket.difficulty != self.difficulty:
            return False
        if self.category and ticket.category != self.category:
            return False
        if self.project_id and self.project_id not in ticket.project_ids:
            return False
        if self.assignee_id and self.assignee_id not in ticket.assignee_ids:
            return False
        if self.search and self.search.lower() not in (ticket.title or "").lower():
            return False
        start, end = self.due_range
        if start is not None or end is not None:
            if not ticket.due:
                return False
            if start is not None and ticket.due < start:
                return False
            if end is not None and ticket.due >= end:
                return False
        if self.exclude_statuses and (ticket.status or "") in self.exclude_statuses:
            return False
        if self.exclude_page_ids and ticket.page_id in self.exclude_page_ids:
            return False
        if self.project_any_of is not None:
            # 티켓 하나에 프로젝트는 정확히 하나여야 한다(0060). 0개·2개 이상은 소속을
            # 판정할 수 없으므로 닫는다 — 임의로 하나를 고르면 남의 부서로 샌다.
            if len(ticket.project_ids) != 1:
                return False
            if ticket.project_ids[0] not in self.project_any_of.page_ids:
                return False
        return True


@dataclass(frozen=True, slots=True)
class TicketDTO:
    """티켓 한 건의 도메인 표현. 소스가 무엇이든 이 모양으로 나온다."""

    page_id: str | None
    uid: str | None = None
    number: int | None = None          # 화면이 'GIT-<번호>' 로 보여주는 티켓 번호
    url: str | None = None
    title: str = ""
    status: str | None = None
    due: str | None = None             # 'YYYY-MM-DD'
    start: str | None = None           # 'YYYY-MM-DD' — 시작일
    category: str | None = None        # 대분류(자유 텍스트)
    est_wd: float | None = None
    act_wd: float | None = None
    difficulty: str | None = None
    priority: str | None = None
    project_ids: tuple[str, ...] = ()
    # 해석된 **Portal 프로젝트 id**. 미러에서 읽은 티켓만 갖는다 — 실시간 폴백 경로는
    # 아직 Portal 짝을 모르므로 `None` 이고, 그때는 위 외부 id 로 판정한다.
    #
    # 왜 둘 다 필요한가: `project_ids` 는 외부 소스의 relation 이라 Portal 전용 프로젝트
    # (Notion 짝이 없는 프로젝트)에는 아예 값이 없다. 외부 id 로만 판정하면 그런 프로젝트의
    # 티켓이 **모두에게서 사라진다** — 조회 화면은 비어 있고 오류는 없다.
    project_uid: str | None = None
    project_names: tuple[str, ...] = ()
    assignee_ids: tuple[str, ...] = ()  # 원본 소스 user id — 내부 전용
    body_markdown: str | None = None
    # 본문 정본을 소스(Notion)까지 밀어 넣지 못한 상태면 그 이유. None 이면 어긋난 곳이 없다.
    body_sync_error: str | None = None
    source: str = "notion"


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """미러 동기화 상태(신선도 표시용). 캐시에서 답할 때만 의미가 있다."""

    status: str
    last_run_at: str | None
    last_success_at: str | None
    ticket_count: int
    truncated: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class TicketList:
    """목록 + '어디서 답했는지'. from_cache=False 면 sync 는 None 이다.

    `total` 은 **필터를 다 건 뒤, 페이지를 자르기 전**의 건수다. 자르기 전 값이어야 화면이
    "1,058건 중 1-20" 을 쓸 수 있다. `None` 은 '안 셌다'가 아니라 '자르지 않았다'는 뜻으로
    쓰지 않는다 - 구현체는 자르든 안 자르든 항상 채운다(안 채우면 부르는 쪽이 `len(tickets)`
    로 대충 메우게 되고, 그 값은 2페이지에서 조용히 틀린다).
    """

    tickets: tuple[TicketDTO, ...] = ()
    from_cache: bool = False
    sync: SyncStatus | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class TicketMeta:
    """편집·생성 폼 드롭다운의 허용 옵션."""

    statuses: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    difficulties: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectRef:
    id: str
    name: str = ""


@dataclass(frozen=True, slots=True)
class BodySaveResult:
    """본문 저장 결과. `synced=False` 는 '우리 DB에는 저장됐지만 소스에는 못 밀어 넣었다'.

    이 두 상태를 하나로 뭉개면 안 된다 — 사용자가 친 글은 살아 있으니 오류로 던질 수 없고,
    그렇다고 성공이라고 하면 원본과 어긋난 사실을 숨기는 거짓말이 된다.
    """

    uid: str | None
    body_markdown: str
    synced: bool
    sync_error: str | None = None


@dataclass(frozen=True, slots=True)
class TicketDraft:
    """새 티켓 생성 요청(도메인 값만). 담당자는 이미 소스 user id 로 해석돼 온다."""

    title: str
    status: str | None = None
    priority: str | None = None
    difficulty: str | None = None
    est_wd: float | None = None
    due_date: str | None = None
    project_id: str | None = None
    description_markdown: str | None = None
    assignee_ids: tuple[str, ...] = field(default_factory=tuple)


class TicketRepository(Protocol):
    """티켓을 읽고 쓰는 유일한 통로. 서비스 계층은 이 인터페이스만 안다."""

    # -- 읽기 -----------------------------------------------------------------
    #
    # `filters` / `page` 는 **선택**이다. 안 주면 오늘까지와 똑같이 전부 돌려준다 -
    # 리포트·스프린트 집계는 목록을 전부 봐야 합계가 맞기 때문이다. 화면 경로만 상한을 준다.
    def list_by_assignee(
        self, db, *, assignee_id: str,
        filters: TicketFilters | None = None, page: PageSpec | None = None,
    ) -> TicketList: ...

    def list_unassigned(
        self, db, *, filters: TicketFilters | None = None, page: PageSpec | None = None
    ) -> TicketList: ...

    def list_all(
        self, db, *, filters: TicketFilters | None = None, page: PageSpec | None = None
    ) -> TicketList: ...

    def list_for_period(
        self, db, *, start: str, end: str,
        filters: TicketFilters | None = None, page: PageSpec | None = None,
    ) -> TicketList: ...

    def get(self, db, *, page_id: str) -> TicketDTO:
        """단건. 없으면 TicketNotFoundError."""
        ...

    def get_live(self, db, *, page_id: str) -> TicketDTO:
        """소유권 판정용 '지금 이 순간'의 값. 캐시를 믿지 않고 소스에서 다시 읽는다."""
        ...

    def body_blocks(self, db, *, page_id: str) -> list[dict]:
        """본문을 화면 렌더용 [{kind, text, checked?}] 로."""
        ...

    def meta(self, db) -> TicketMeta: ...

    def projects(self, db) -> list[ProjectRef]: ...

    def sync_state(self, db) -> SyncStatus | None:
        """미러로 답할 수 있을 때의 신선도. 실시간으로 답하는 상태면 None."""
        ...

    # -- 쓰기 -----------------------------------------------------------------
    def create(self, db, *, draft: TicketDraft, now) -> TicketDTO: ...

    def update(self, db, *, page_id: str, changes: dict, now) -> TicketDTO:
        """changes 키는 도메인 이름(status/priority/difficulty/est_wd/due_date/assignee_ids)."""
        ...

    def archive(self, db, *, page_id: str) -> None:
        """소스 쪽 원본을 보관처리(휴지통 보관기간 만료 정리)."""
        ...

    def save_body(self, db, *, page_id: str, body_markdown: str, now) -> BodySaveResult:
        """본문을 저장한다. **정본을 먼저 쓰고 그다음 소스에 밀어 넣는다.**

        이 순서가 계약이다: 소스 push 가 실패해도 사용자가 친 텍스트는 남아야 하므로 구현체는
        push 실패를 예외로 던지지 않고 `synced=False` 로 돌려준다(예외로 던지면 요청
        트랜잭션이 롤백되어 방금 저장한 본문까지 사라진다).
        """
        ...

    def local_uid(self, db, *, page_id: str) -> str | None:
        """이미 우리 DB에 있는 자체 UUID(없으면 None). **소스를 부르지 않는다.**

        댓글 목록처럼 자주 폴링되는 경로가 쓰므로 여기서 외부 왕복이 생기면 안 된다.
        """
        ...

    def ensure_local(self, db, *, page_id: str, now=None) -> str:
        """이 티켓의 **자체 UUID**를 확보한다(없으면 로컬 행을 만들어서라도).

        댓글이 `ticket_cache.id` 에 FK 로 걸려 있어서 필요하다 — 아직 미러에 없는 티켓에
        댓글을 달려면 먼저 우리 쪽 행이 있어야 한다.
        """
        ...


def snapshot(ticket: TicketDTO) -> dict:
    """감사 before/after 스냅샷. 키 이름은 기존 감사 기록과 계속 같아야 한다(과거 기록 호환)."""
    return {
        "status": ticket.status,
        "due": ticket.due,
        "assignees": list(ticket.assignee_ids),
        "est_wd": ticket.est_wd,
        "difficulty": ticket.difficulty,
        "priority": ticket.priority,
    }
