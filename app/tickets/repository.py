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
from typing import Protocol


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
    """목록 + '어디서 답했는지'. from_cache=False 면 sync 는 None 이다."""

    tickets: tuple[TicketDTO, ...] = ()
    from_cache: bool = False
    sync: SyncStatus | None = None


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
    def list_by_assignee(self, db, *, assignee_id: str) -> TicketList: ...

    def list_unassigned(self, db) -> TicketList: ...

    def list_all(self, db) -> TicketList: ...

    def list_for_period(self, db, *, start: str, end: str) -> TicketList: ...

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
