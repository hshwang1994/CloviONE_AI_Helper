"""TicketRepository 의 자체 DB 구현 (§7.1.C · S14).

## 이 파일이 무엇을 대체하는가

`repository_notion.py` 는 두 개의 저장소가 한 클래스 안에 들어 있는 상태였다. 하나는
로컬 표(`tickets`)를 읽는 SQL 경로였고(`use_cache=True` 일 때의 `_cached_list`),
다른 하나는 Notion 을 실시간으로 왕복하는 경로였다. **여기 있는 것은 앞의 것뿐이다** —
같은 조건, 같은 정렬, 같은 「자르기 전 total」이고, 다른 점은 셋이다.

  * 「캐시가 아직 안 찼으니 Notion 으로 폴백한다」가 없다. 폴백은 미러가 정본이 아닐
    때만 뜻이 있는 장치인데, 이제 이 표가 정본이라 「아직 안 찼다」는 상태가 없다.
    티켓이 0건인 것은 사고가 아니라 사실이고, 그때는 빈 목록이 정답이다.
  * 동기화 상태(`ticket_sync_state`)로 답을 가르지 않는다. 미러가 없으므로 낡을
    것도 없고, 그래서 신선도를 묻는 계약(`sync_state()`, 목록 응답의 `sync` 블록)
    자체가 없어졌다. 「지금 답한 값이 얼마나 낡았나」에 답할 수 없어서가 아니라
    **낡을 수가 없어서** 그 질문이 없어진 것이다. 같은 이유로
    `TicketList.from_cache` 도 `False` 다: 그 이름은 「정본이 아닌 사본으로
    답했다」는 뜻이었고, 여기서 답한 값은 사본이 아니다.
  * 쓰기가 외부로 나가지 않는다. `create`/`update`/`save_body` 는 이 표에 쓰고
    끝난다. 그래서 `save_body` 의 결과에 `synced` 가 없다 — 밀어 넣을 곳이 없는데
    「밀어 넣지 못했다」는 상태를 만들 수는 없다.

## 아웃바운드 호출이 없다는 것을 어떻게 지키는가

이 모듈은 `app/tickets/notion_write.py` · `app/reports/notion_source.py` ·
OutboundClient 를 **import 하지 않는다**. 정적검사(`scripts/static_checks.sh` 의
「Notion 모듈 import 경계」)가 파일 이름으로 그것을 막고, 그 밖의 우회를
`tests/integration/test_native_ticket_repository.py` 가 실제 호출 기록으로 본다
(같은 픽스처에서 Notion 구현체는 왕복을 남기고 이쪽은 안 남긴다 — 반례가 있어야
「0건」이 「안 봤다」와 구별된다).

`app.core.notion_blocks` 는 이름에 Notion 이 들어 있지만 **순수 함수 모듈**이다
(마크다운 한 덩어리를 줄 단위 규칙으로 자른다). 프런트 편집기·게시판·문서 본문이
같은 규칙을 쓰고 있어서 여기서 파서를 새로 쓰면 「미리보기와 저장 결과가 다르다」가
티켓 화면에서만 생긴다 — 그래서 그 한 벌을 그대로 쓴다.

## 식별자 규약 (`page_id` 가 두 가지를 받는다)

API 가 부르는 이름은 여전히 `page_id` 이고 응답의 `id` 도 그 값이다(딥링크·휴지통·
감사가 이미 그 값을 키로 쓴다). 그런데 자체 DB 에서 만든 티켓에는 Notion 페이지가
없다 — `tickets.notion_page_id` 가 `NULL` 이다. 그래서 이 구현체는 **두 값을 다
받는다**:

    page_id == tickets.notion_page_id   (이관해 온 티켓 — 옛 링크가 계속 산다)
    page_id == tickets.id               (자체 DB 에서 만든 티켓 — 새 링크)

둘은 문자열 모양이 겹치지 않는다(Notion page id 는 32자리 16진수 또는 하이픈
UUID, 우리 id 는 소문자 UUID)지만, 겹치더라도 `notion_page_id` 가 unique 이고
`id` 가 PK 라 한 행만 걸린다. 어느 쪽으로도 못 찾으면 `TicketNotFoundError` 다 —
**빈 티켓을 만들어 돌려주지 않는다.** 없는 티켓과 빈 티켓이 같은 답이 되면 화면은
제목 없는 상세를 그리고, 사용자는 자기가 지운 줄 안다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.dates import iso_date, parse_date
from app.core.errors import TicketNotFoundError, ValidationAppError
from app.core.models_base import utcnow
from app.core.notion_blocks import markdown_to_blocks
from app.home.aggregate import priority_rank
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets import project_link
from app.tickets.models import (
    PROJECT_LINK_OK,
    SOURCE_NATIVE,
    SOURCE_NOTION,
    TicketCache,
    join_names,
    split_names,
)
from app.tickets.query import filter_clauses, order_clause, token
from app.tickets.repository import (
    BodySaveResult,
    PageSpec,
    ProjectRef,
    TicketDraft,
    TicketDTO,
    TicketFilters,
    TicketList,
    TicketMeta,
)
from app.work import workflow

# 마크다운 파서(`markdown_to_blocks`)가 내는 블록 종류 → 상세 화면이 읽는 축약형 `kind`.
#
# 이 표가 필요한 이유는 이름이 두 벌이기 때문이지 규칙이 두 벌이어서가 아니다. 「어떤
# 줄이 무엇인가」는 `markdown_to_blocks` 한 곳에서만 정해지고(그래야 프런트 미리보기와
# 어긋나지 않는다), 여기서는 그 결과의 이름만 화면 어휘로 옮긴다. 값은
# `app/tickets/notion_write.py::_TEXT_BLOCK_TYPES` 가 쓰던 것과 같은 문자열이라
# `app/core/notion_blocks.py::rendered_to_markdown` 이 그대로 되읽는다 — 즉 저장한
# 마크다운과 편집기가 다시 여는 마크다운이 같다.
_RENDER_KIND: dict[str, str] = {
    "paragraph": "paragraph",
    "heading_1": "heading_1",
    "heading_2": "heading_2",
    "heading_3": "heading_3",
    "bulleted_list_item": "bulleted",
    "numbered_list_item": "numbered",
}


def _block_text(block: dict) -> str:
    """`markdown_to_blocks` 가 만든 블록 하나에서 글자만 뽑는다.

    우리가 방금 만든 구조를 되읽는 것이라 모양이 표류할 자리가 없다(외부 응답을
    파싱하는 것이 아니다). 그래도 방어적으로 읽는 이유는 빈 줄이 `rich_text: []` 로
    나오기 때문이다 — 그 경우를 예외로 만들면 빈 문단 하나가 본문 전체를 죽인다.
    """
    container = block.get(block.get("type") or "")
    if not isinstance(container, dict):
        return ""
    return "".join(
        (seg.get("text") or {}).get("content") or ""
        for seg in (container.get("rich_text") or [])
        if isinstance(seg, dict)
    )


def _sorted_options(values: list[str], *, by_priority: bool) -> tuple[str, ...]:
    """드롭다운 옵션 목록을 **결정적인 순서**로 세운다.

    옵션 순서가 요청마다 바뀌면 사용자는 같은 자리에 있던 값을 매번 다시 찾는다.
    우선순위는 제품이 이미 갖고 있는 등급(`app/home/aggregate.py::priority_rank`,
    트리아지 정렬이 쓰는 그것)을 그대로 쓴다 — 여기서 순서를 새로 정하면 목록 화면과
    폼이 서로 다른 순서를 말하게 된다. 난이도는 숫자 문자열('1'~'5')이라 사전순으로
    세우면 '10' 이 '2' 앞에 오므로 숫자로 읽을 수 있으면 숫자로 센다.
    """
    if by_priority:
        return tuple(sorted(values, key=lambda v: (priority_rank(v), v)))

    def _numeric_first(value: str) -> tuple[int, float, str]:
        try:
            return (0, float(value), value)
        except ValueError:
            return (1, 0.0, value)

    return tuple(sorted(values, key=_numeric_first))


class NativeTicketRepository:
    """`tickets` 표를 정본으로 읽고 쓰는 구현체. 외부 소스를 부르지 않는다."""

    def __init__(self, settings=None, outbound=None) -> None:
        """`(settings, outbound)` 를 받는 이유는 배선 한 곳(`source_registry`)이 세
        구현체를 **같은 모양으로** 만들기 때문이다. 받되 `outbound` 는 **보관하지
        않는다** — 들고 있으면 언젠가 누군가 그걸로 한 번만 왕복하게 되고, 그 한 번이
        「자체 DB가 정본」이라는 약속을 깬다. 시험이 이 속성의 부재를 고정한다.
        """
        self._settings = settings

    # `app/tickets/service.py::_repo` 가 이 속성에 값을 넣는다(Notion 구현체의 킬
    # 스위치를 켜고 끄는 자리). 여기서는 읽는 곳이 없다 — 자체 DB 는 언제나 자기 표로
    # 답하므로 켜고 끌 대상이 없다. 속성만 남겨 두는 이유는 그 호출부가 저장소 종류를
    # 몰라도 되게 하기 위해서다.
    use_cache: bool = True

    # ── 식별 ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _row(db: Session | None, page_id: str | None) -> TicketCache | None:
        """`page_id` 로 행 하나. 못 찾으면 `None` (모듈 docstring 의 식별자 규약).

        **순서가 계약이다**: 옛 page id 를 먼저 보고, 그다음 자체 uuid 를 본다
        (`app/work/resolve.py` 가 canonical → uuid 순서를 고정한 것과 같은 이유).
        한 질의에 `OR` 로 묶지 않는 이유는 두 컬럼이 서로 다른 행에서 같은 값을 가질
        수 있기 때문이다 — 그때 `scalar_one_or_none()` 은 500 으로 터진다. 확률은
        사실상 0이지만(양쪽 다 uuid4), 「거의 안 일어난다」를 근거로 500 을 남겨 두면
        일어난 날 아무도 원인을 못 찾는다.
        """
        if not page_id or db is None:
            return None
        row = db.execute(
            select(TicketCache).where(TicketCache.notion_page_id == page_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        return db.get(TicketCache, page_id)

    def _require_row(self, db: Session, page_id: str) -> TicketCache:
        row = self._row(db, page_id)
        if row is None:
            raise TicketNotFoundError()
        return row

    # ── DTO 변환 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(row: TicketCache) -> TicketDTO:
        """행 하나 → 도메인 DTO. `repository_notion._from_cache` 와 같은 값을 낸다.

        딱 한 곳이 다르다: `page_id` 를 `notion_page_id` 로만 채우지 않고 없으면 자체
        id 로 떨어진다. 안 그러면 자체 DB 에서 만든 티켓의 API `id` 가 `null` 이 되고,
        그 티켓은 목록에는 보이는데 눌러도 안 열린다 — 그리고 그 상태는 오류를 안 낸다.
        """
        return TicketDTO(
            page_id=row.notion_page_id or row.id,
            uid=row.id,
            number=row.notion_ticket_number,
            key=row.canonical_key,
            url=row.url,
            title=row.title or "",
            status=row.status,
            # 저장은 `date` 이고 DTO 는 문자열 계약이다(S7 · P-14a). 옮기는 자리가
            # 두 벌이 되면 어떤 응답은 날짜 객체, 어떤 응답은 문자열이 된다.
            due=iso_date(row.due_date),
            start=iso_date(row.start_date),
            category=row.category,
            est_wd=row.est_wd,
            act_wd=row.act_wd,
            difficulty=row.difficulty,
            priority=row.priority,
            project_ids=tuple(split_names(row.project_ids)),
            # 해석에 성공한 것만 싣는다 — `ok` 가 아니면 소속을 모르는 것이고, 모르면
            # 판정은 닫는 쪽이다(0060).
            project_uid=row.project_uid if row.project_link == PROJECT_LINK_OK else None,
            project_names=tuple(split_names(row.project_names)),
            assignee_ids=tuple(split_names(row.assignee_notion_ids)),
            body_markdown=row.body_markdown,
            created_at=row.created_at,
            source=row.source or SOURCE_NOTION,
        )

    # ── 목록 ─────────────────────────────────────────────────────────────────

    def _list(
        self, db: Session, stmt,
        filters: TicketFilters | None = None, page: PageSpec | None = None,
    ) -> TicketList:
        """목록 네 곳이 지나는 **하나의 깔때기**. 조건·정렬·자르기가 여기 한 번만 있다.

        `notion_missing_at` 을 계속 거르는 이유: 이관해 온 행들이 그 표시를 달고 넘어와
        있다(0043 — 「소스 응답에서 안 보였다」를 지우지 않고 표시만 한 결과다). 소스가
        없어진 지금 그 컬럼에 새 값이 찍힐 일은 없지만, 이미 찍힌 값은 「사용자에게는
        삭제된 것으로 보였던 티켓」을 뜻한다. 조건을 빼면 그 티켓들이 컷오버 당일 전부
        되살아나고, 그 부활은 아무도 신고하지 않는다(목록이 조금 길어질 뿐이다).
        보관기간이 지난 행은 `app/core/retention.py::purge_missing_tickets` 가 지운다.

        `total` 은 **자르기 전** 건수다. 자른 뒤에 세면 2페이지에서 20이 되고, 화면은
        "20건 중 21-40" 이라는 말이 안 되는 문장을 쓴다.
        """
        stmt = stmt.where(TicketCache.notion_missing_at.is_(None))
        for clause in filter_clauses(filters):
            stmt = stmt.where(clause)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(*order_clause(filters))
        if page is not None and page.limit is not None:
            stmt = stmt.offset(page.offset).limit(page.limit)
        rows = db.execute(stmt).scalars().all()
        return TicketList(
            tickets=tuple(self._to_dto(r) for r in rows),
            # 사본이 아니라 정본으로 답했다 — 모듈 docstring 참조.
            from_cache=False,
            total=total,
        )

    def list_by_assignee(
        self, db: Session, *, assignee_id: str,
        filters: TicketFilters | None = None, page: PageSpec | None = None,
    ) -> TicketList:
        return self._list(
            db,
            select(TicketCache).where(
                TicketCache.assignee_notion_ids.contains(token(assignee_id), autoescape=True)
            ),
            filters, page,
        )

    def list_unassigned(
        self, db: Session, *, filters: TicketFilters | None = None,
        page: PageSpec | None = None,
    ) -> TicketList:
        """담당자가 아무도 없는 티켓 (0060 의 정의 그대로).

        빈 값 표현이 둘(NULL, '')이라 둘 다 본다 — `join_names([])` 는 빈 문자열을
        쓰지만 옛 행이나 직접 넣은 행은 NULL 일 수 있고, 한쪽만 보면 그 행들이 조용히
        빠진다(그리고 미할당 목록에서 빠진 티켓은 아무도 안 가져간다).
        """
        return self._list(
            db,
            select(TicketCache).where(
                or_(
                    TicketCache.assignee_notion_ids.is_(None),
                    TicketCache.assignee_notion_ids == "",
                )
            ),
            filters, page,
        )

    def list_all(
        self, db: Session, *, filters: TicketFilters | None = None,
        page: PageSpec | None = None,
    ) -> TicketList:
        return self._list(db, select(TicketCache), filters, page)

    def list_for_period(
        self, db: Session, *, start: str, end: str,
        filters: TicketFilters | None = None, page: PageSpec | None = None,
    ) -> TicketList:
        """마감일이 반개구간 `[start, end)` 인 티켓.

        인자는 ISO 문자열이다 — 부르는 쪽(리포트·번다운)이 그 규약으로 창을 만든다.
        컬럼은 `date` 라 여기서 한 번 옮긴다 (S7 · P-14a).
        """
        return self._list(
            db,
            select(TicketCache).where(
                TicketCache.due_date.is_not(None),
                TicketCache.due_date >= parse_date(start),
                TicketCache.due_date < parse_date(end),
            ),
            filters, page,
        )

    # ── 단건 ─────────────────────────────────────────────────────────────────

    def get(self, db: Session, *, page_id: str) -> TicketDTO:
        """상세 화면용 단건. 없으면 `TicketNotFoundError`."""
        return self._to_dto(self._require_row(db, page_id))

    def get_live(self, db: Session, *, page_id: str) -> TicketDTO:
        """`get` 과 **글자 그대로 같다**. 그리고 같은 것이 맞다.

        Notion 구현에서 이 둘이 갈라져 있던 이유는 하나뿐이었다: 소유권 판정과 감사
        스냅샷은 미러가 아니라 **정본**을 봐야 하는데, 그때 정본이 Notion 이었다. 지금
        정본은 이 표다 — 「더 살아 있는 값」이 있는 곳이 없다.

        그래도 메서드를 남기는 이유는 부르는 쪽(`app/tickets/service.py::update_ticket`
        의 소유권 확인)이 **정본을 읽겠다는 의도**를 이름으로 말하고 있기 때문이다.
        지우면 그 의도가 호출부에서 사라지고, 나중에 읽기 캐시를 다시 넣는 날 그 자리를
        아무도 못 찾는다.
        """
        return self.get(db, page_id=page_id)

    def body_blocks(self, db: Session, *, page_id: str) -> list[dict]:
        """저장된 본문(마크다운) → 상세 화면이 읽는 `[{kind, text}]`.

        Notion 구현은 페이지 블록을 읽어 이 모양을 만들었다. 자체 DB 에는 정본이
        마크다운으로 있으므로 **같은 파서를 지나** 같은 모양을 만든다:
        `markdown_to_blocks` 로 줄을 해석하고 이름만 화면 어휘로 옮긴다(`_RENDER_KIND`).

        그 왕복을 굳이 지나는 이유는 규칙을 한 벌로 유지하기 위해서다. 여기서 줄을 다시
        해석하면 「'# ' 이 제목인가」 같은 판단이 두 곳이 되고, 한쪽만 고쳐진 날 증상은
        **미리보기와 저장 결과가 다르다**로 나타난다 — 사용자는 자기가 뭘 잘못 쳤는지
        찾는다.

        본문이 없으면 **빈 목록**이다. 빈 문자열을 파서에 넣으면 빈 문단 하나가 나오고
        (`"".split("\\n")` 이 `[""]` 이라서 그렇다), 그러면 본문을 한 번도 안 쓴 티켓의
        상세 화면이 「비어 있음」 대신 빈 줄 하나를 그린다.
        """
        row = self._require_row(db, page_id)
        if not row.body_markdown:
            return []
        out: list[dict] = []
        for block in markdown_to_blocks(row.body_markdown):
            btype = block.get("type") or ""
            if btype == "divider":
                out.append({"kind": "divider", "text": ""})
                continue
            kind = _RENDER_KIND.get(btype)
            if kind is None:
                continue  # 파서가 내지 않는 종류 — 도달할 수 없지만 조용히 지나간다
            out.append({"kind": kind, "text": _block_text(block)})
        return out

    # ── 폼 옵션 ──────────────────────────────────────────────────────────────

    def meta(self, db: Session | None) -> TicketMeta:
        """편집·생성 폼 드롭다운의 허용 옵션.

        **진행상태는 제품이 소유한다.** 어휘의 정본은 `app/work/workflow.py` 이고
        `ticket_statuses` 표는 그 결과다(마이그레이션 0003 이 심고
        `tests/unit/test_work_domain_seed.py` 가 둘을 맞물린다). 표가 아니라 코드를
        읽는 이유는 표가 비어 있을 수 있는 순간(새 DB, 마이그레이션 직전)에도 폼이
        떠야 하기 때문이다 — 그때 빈 드롭다운이 나가면 티켓을 아예 못 만든다.

        **우선순위·난이도는 아직 제품이 소유하지 못했다.** 이 두 축에는
        `ticket_statuses` 같은 표도, 코드에 적힌 목록도 없다 — 예전에는 Notion 스키마의
        select 옵션이 그 자리였다. 그래서 지금 있는 데이터에서 실제로 쓰인 값을 뽑아
        쓴다. 결과는 **오늘 쓰이는 값만 고를 수 있다**는 뜻이고, 새 값은 이 목록을 통해
        생기지 않는다(그래서 `create`/`update` 는 이 두 축을 이 목록으로 검사하지
        않는다 — 검사하면 첫 새 값이 영원히 못 들어와 목록이 스스로를 잠근다).
        어휘를 제품 것으로 만드는 일은 별도 작업이다.
        """
        statuses = tuple(s.key for s in workflow.all_statuses())
        if db is None:
            return TicketMeta(statuses=statuses)
        return TicketMeta(
            statuses=statuses,
            priorities=_sorted_options(self._distinct(db, TicketCache.priority), by_priority=True),
            difficulties=_sorted_options(
                self._distinct(db, TicketCache.difficulty), by_priority=False
            ),
        )

    @staticmethod
    def _distinct(db: Session, column) -> list[str]:
        """그 컬럼에 실제로 들어 있는 값들(빈 값 제외)."""
        rows = db.execute(
            select(column).where(column.is_not(None), column != "").distinct()
        ).scalars().all()
        return [str(v) for v in rows]

    def projects(self, db: Session | None) -> list[ProjectRef]:
        """프로젝트 드롭다운·이름 해석용 목록.

        **`id` 는 Portal `projects.id` 가 아니라 외부 page id 다.** 바꾸고 싶은
        모양이지만 지금 바꾸면 화면의 프로젝트 필터가 조용히 아무것도 안 걸러진다:
        목록 필터는 `TicketFilters.project_id` → `tickets.project_ids`(외부 relation
        id 다중값)로 내려가고(`app/tickets/query.py::filter_clauses`), 티켓 응답의
        `project_ids` 도 같은 값이다. 즉 「티켓이 프로젝트를 부르는 이름」이 아직 외부
        id 라, 이 목록만 Portal id 로 바꾸면 두 축이 갈라진다.

        그래서 짝이 없는(=포털 전용) 프로젝트는 이 목록에 안 나온다. Notion 구현도
        같았다(저쪽 relation 대상 DB 를 조회했으므로 애초에 나올 수 없었다). 정렬도
        같다 — 이름순, 이름 없는 것은 뒤로.
        """
        if db is None:
            return []
        rows = db.execute(
            select(Project.notion_page_id, Project.name).where(
                Project.notion_page_id.is_not(None)
            )
        ).all()
        refs = [ProjectRef(id=r[0], name=r[1] or "") for r in rows if r[0]]
        refs.sort(key=lambda r: (r.name or "￿"))
        return refs

    # ── 쓰기 ─────────────────────────────────────────────────────────────────

    def create(self, db: Session, *, draft: TicketDraft, now: datetime | None = None) -> TicketDTO:
        """새 티켓 한 건을 이 표에 만든다.

        **커밋하지 않는다.** Notion 구현은 느린 외부 호출 앞에서 스냅샷을 새로 뜨려고
        `db.commit()` 을 했다(DBTX 주석 참조). 여기에는 외부 호출이 없고, 대신 부르는
        쪽이 같은 트랜잭션 안에서 활동 기록·알림을 이어 붙인다 — 중간에 커밋하면 그
        뒤가 실패했을 때 「티켓만 남고 기록은 없는」 상태가 남는다.

        **번호는 제품의 채번기가 준다** (D-196). `app/work/service.py::number_if_possible`
        을 그대로 부르는 이유는 그 함수가 이미 세 가지를 한 벌로 하기 때문이다: 코드가
        있는 프로젝트에서만 `numbering.allocate` 를 태우고, 트리거가 `canonical_key` 를
        파생시키게 두고(앱은 그 컬럼을 절대 쓰지 않는다 — D-195), 그 이름이 생긴 사실을
        활동으로 남긴다.

        **프로젝트를 정할 수 없으면 번호 없이 만든다.** `numbering.allocate` 는 코드
        없는 프로젝트에서 `ConflictError` 를 올리는데, 그 예외를 그대로 사용자에게
        보내면 코드가 아직 없는 프로젝트에서는 티켓 생성 자체가 막힌다. 그건 채번
        규칙을 지키려고 제품을 세우는 것이다. `number_if_possible` 은 그 경우 아무것도
        하지 않고 `False` 를 돌려주고, 번호 없는 티켓은 화면에서 제목으로 불린다
        (`app/work/resolve.py::display_key` 가 `None` 을 돌려주는 그 상태다).
        """
        # `app.work.service` 만 지연 import 다 — 그쪽은 권한·휴지통까지 끌고 오는
        # 무거운 모듈이라 배선 시점(앱 기동)에 함께 들어올 이유가 없다.
        from app.work import service as work_service

        stamp = now or utcnow()
        title = (draft.title or "").strip()
        if not title:
            raise ValidationAppError("제목을 입력하세요.")

        # 상태 어휘는 제품이 소유한다 — 모르는 값이면 여기서 막는다. 안 막으면 오타
        # 하나가 새 상태로 저장되고 그 티켓은 어느 칸반 열에도 안 나타난다.
        status = workflow.validate_transition(None, draft.status or workflow.DEFAULT_STATUS)

        project, external_id = self._resolve_project(db, draft.project_id)
        row = TicketCache(
            notion_page_id=None,
            # 조직은 프로젝트가 정한다. 티켓을 조직으로 거르는 코드는 아직 없지만,
            # 비워 두면 스코프 필터가 켜지는 날 이 행들만 통째로 사라진다
            # (`app/core/models_base.py::OrgScopedMixin` 의 그 이유).
            org_id=(project.org_id if project is not None else None) or DEFAULT_ORG_ID,
            title=title,
            status=status,
            priority=draft.priority or None,
            difficulty=draft.difficulty or None,
            est_wd=draft.est_wd,
            due_date=parse_date(draft.due_date),
            project_ids=join_names([external_id] if external_id else []),
            project_names=join_names([project.name] if project is not None and project.name else []),
            assignee_notion_ids=join_names(list(draft.assignee_ids)),
            body_markdown=draft.description_markdown,
            source=SOURCE_NATIVE,
            synced_at=stamp,
            created_at=stamp,
            updated_at=stamp,
        )
        self._apply_project(db, row, project, external_id)
        db.add(row)
        db.flush()
        work_service.number_if_possible(db, row, now=stamp)
        return self._to_dto(row)

    def update(
        self, db: Session, *, page_id: str, changes: dict, now: datetime | None = None
    ) -> TicketDTO:
        """도메인 키만 받아 행에 적용한다 — Notion 구현이 받던 것과 같은 열한 개.

        키 이름이 API 와 다른 것(`project` / `start` / `assignee_notion_ids`)은 서비스가
        이미 번역해 준 결과다(`app/tickets/service.py::update_ticket`). 여기서 다시
        이름을 정하지 않는다 — 두 벌이 되면 한쪽만 고쳐지고, 그러면 어떤 필드는 저장이
        조용히 무시된다.

        모르는 키는 **건너뛴다**(예외가 아니다). 요청 스키마가 이미 `forbid` 라 실제로는
        오지 않고, 여기서 막으면 저장소가 API 스키마를 두 번째로 검사하는 자리가 된다.
        """
        if not changes:
            raise ValidationAppError("변경할 내용이 없습니다.")
        stamp = now or utcnow()
        row = self._require_row(db, page_id)

        for key, value in changes.items():
            if key == "title":
                if not (value or "").strip():
                    raise ValidationAppError("제목은 비울 수 없습니다.")
                row.title = value.strip()
            elif key == "status":
                if not value:
                    raise ValidationAppError("진행상태는 비울 수 없습니다.")
                row.status = workflow.validate_transition(row.status, value)
            elif key == "priority":
                # 빈 값은 '지움'이다(`app/tickets/schemas.py` 가 정한 규약이다).
                # 허용 목록으로 막지 않는 이유는 `meta` 의 docstring 에 적었다 —
                # 그 목록이 지금 데이터에서 나오므로, 검사하면 새 값이 영원히 못
                # 들어오고 목록이 스스로를 잠근다.
                row.priority = value or None
            elif key == "difficulty":
                row.difficulty = value or None
            elif key == "est_wd":
                row.est_wd = value
            elif key == "act_wd":
                row.act_wd = value
            elif key == "due_date":
                row.due_date = parse_date(value)
            elif key == "start":
                row.start_date = parse_date(value)
            elif key == "category":
                row.category = value or None
            elif key == "assignee_notion_ids":
                # 빈 목록은 '전부 해제'라는 뜻이라 그대로 흘려보낸다.
                row.assignee_notion_ids = join_names(list(value or []))
            elif key == "project":
                # 값은 id 목록이다(Notion relation 이 다중값이었던 흔적). 티켓의
                # 프로젝트는 정확히 하나이므로 첫 번째만 본다 (0060).
                wanted = list(value or [])
                project, external_id = self._resolve_project(db, wanted[0] if wanted else None)
                row.project_ids = join_names([external_id] if external_id else [])
                row.project_names = join_names(
                    [project.name] if project is not None and project.name else []
                )
                self._apply_project(db, row, project, external_id)
            # 그 밖의 키는 건너뛴다(위 docstring).

        row.updated_at = stamp
        db.flush()
        return self._to_dto(row)

    def archive(self, db: Session | None, *, page_id: str) -> None:
        """이 티켓을 **영구 삭제한다**. 자체 DB 에서 '보관처리'의 뜻이 그것이다.

        Notion 구현에서 이 메서드는 원본 페이지를 archive 하고(저쪽 휴지통에서 30일
        복구 가능) 로컬 행을 지웠다. 되돌릴 여지를 준 쪽은 **Notion 의 휴지통**이었지
        우리가 아니었다. 자체 DB 에는 그 두 번째 휴지통이 없다.

        그래서 없는 안전망을 흉내 내지 않는다. 이 메서드를 부르는 자리는 하나이고
        (`app/trash/service.py` — 휴지통 보관기간이 지났거나 사람이 「영구 삭제」를
        눌렀을 때), 그 자리의 뜻은 이미 「되돌리지 않는다」다. 우리 휴지통이 그 앞의
        유예를 담당한다.

        딸린 댓글·첨부가 CASCADE 로 함께 사라지는 것은 **의도된 정리**다
        (`app/core/retention.py::purge_missing_tickets` 가 같은 판단을 한다). ORM 을
        거쳐 지우는 것도 같은 이유다 — `delete()` 문 하나로 지우면 세션이 자식 상태를
        모르는 채 남고, 같은 요청이 이어서 다른 정리를 한다.

        `db` 가 없으면 아무것도 할 수 없어서 거절한다. 조용히 넘어가면 휴지통 행만
        사라지고 티켓 행은 남아 **영구 삭제한 티켓이 다음 목록 조회에서 되살아난다**
        (목록의 휴지통 제외 조건이 휴지통 표를 보기 때문이다). 그 부활은 오류를 안
        내므로 아무도 신고하지 않는다.
        """
        if db is None:
            raise ValidationAppError(
                "티켓을 영구 삭제하려면 저장소 세션이 필요합니다."
            )
        row = self._row(db, page_id)
        if row is None:
            return  # 이미 없다 — 지우는 것이 목적이므로 그것으로 끝이다
        db.delete(row)
        db.flush()

    # ── 본문 ─────────────────────────────────────────────────────────────────

    def save_body(
        self, db: Session, *, page_id: str, body_markdown: str, now: datetime | None = None
    ) -> BodySaveResult:
        """본문을 저장한다. 저장 결과에 `synced` 라는 필드가 없다.

        Notion 구현에서 `synced=False` 는 「우리 DB 에는 저장됐지만 소스에는 못 밀어
        넣었다」는 세 번째 상태였다. 그 상태가 존재한 이유는 정본이 두 곳에 있었기
        때문이다 — 우리 표와 Notion 페이지. 지금은 한 곳뿐이라 어긋날 짝이 없다.

        그래서 `body_synced_at` 을 저장 시각으로 채우고 `body_sync_error` 를 지운다.
        지우는 것이 중요하다: 컷오버 전에 push 가 실패해 오류가 적힌 채 넘어온 행이
        있고, 그 행은 상세 화면에 「원본과 어긋났습니다」 배너를 계속 띄운다. 어긋날
        원본이 없어진 뒤에도 그 배너가 남으면 사용자는 고칠 수 없는 경고를 매번 본다.
        """
        stamp = now or utcnow()
        uid = self.ensure_local(db, page_id=page_id, now=stamp)
        row = self._row(db, page_id)
        if row is None:  # ensure_local 직후이므로 실제로는 오지 않는다
            raise ValidationAppError("티켓을 우리 저장소에서 찾지 못했습니다.")
        row.body_markdown = body_markdown
        row.body_sync_error = None
        row.body_synced_at = stamp
        row.updated_at = stamp
        db.flush()
        return BodySaveResult(uid=uid, body_markdown=body_markdown)

    # ── 자체 UUID ────────────────────────────────────────────────────────────

    def local_uid(self, db: Session, *, page_id: str) -> str | None:
        """이미 있는 자체 UUID(없으면 `None`). 댓글 목록처럼 자주 폴링되는 경로가 쓴다."""
        row = self._row(db, page_id)
        return row.id if row is not None else None

    def ensure_local(self, db: Session, *, page_id: str, now: datetime | None = None) -> str:
        """이 티켓의 자체 UUID. **없는 티켓을 만들어 내지 않는다** (S14).

        댓글과 첨부가 `tickets.id` 에 FK 로 걸려 있어서 이 함수가 있다. 미러 구현체는
        행이 없으면 **빈 행을 만들고** 넘어갔다. 그때는 그것이 옳았다 — 미러가 아직
        안 따라온 티켓일 수 있었고, 다음 동기화가 그 행을 채웠다. 빈 행 하나가 남는
        쪽이 사용자가 쓴 글이 사라지는 쪽보다 나았다.

        자체 DB 가 정본이 되면서 그 전제가 없어졌다. **그 「다음 동기화」가 없다.**
        여기서 빈 행을 만들면 소속이 없는 행이 영구히 남고, 소속이 없으면 범위 문이
        닫는다(`ensure_in_scope` 는 `project_link='ok'` 만 통과시킨다) — 방금 댓글을 단
        사람이 그 순간부터 자기가 댓글을 단 티켓을 **못 연다.** 오류는 안 난다.

        그래서 없는 티켓은 없다고 답한다. 사용자의 글이 사라지지도 않는다 — 저장이
        404 로 거절되므로 화면의 입력은 그대로 있고, 무엇이 잘못됐는지도 분명하다.
        「조용히 성공하고 나중에 사라진다」보다 「지금 실패한다」가 낫다.
        """
        row = self._row(db, page_id)
        if row is None:
            raise TicketNotFoundError()
        return row.id

    # ── 프로젝트 해석 ────────────────────────────────────────────────────────

    def _resolve_project(
        self, db: Session, project_id: str | None
    ) -> tuple[Project | None, str | None]:
        """생성·이동이 받은 프로젝트 식별자 → `(Project | None, 외부 page id | None)`.

        **두 가지 모양을 다 받는다.** 오늘 서비스 계층은 Portal id 를 외부 page id 로
        번역해서 넘긴다(`app/tickets/service.py::_resolve_writable_project`) — 티켓
        본체가 Notion 에 살던 시절의 계약이다. 그 번역이 없어지는 날 이 함수가 Portal
        id 를 그대로 받게 되는데, 그때 여기가 못 알아보면 증상은 「프로젝트를 골랐는데
        티켓이 어느 프로젝트에도 안 붙는다」이고 그 티켓은 아무에게도 안 보인다.
        두 모양이 서로 겹치지 않으므로(한쪽은 `projects.notion_page_id`, 다른 쪽은
        `projects.id`) 둘 다 받아도 답이 갈리지 않는다.
        """
        pid = (project_id or "").strip()
        if not pid:
            return None, None
        project = db.execute(
            select(Project).where(Project.notion_page_id == pid)
        ).scalar_one_or_none()
        if project is not None:
            return project, pid
        project = db.get(Project, pid)
        if project is None:
            raise ValidationAppError("프로젝트를 찾을 수 없습니다.")
        return project, project.notion_page_id

    @staticmethod
    def _apply_project(
        db: Session, row: TicketCache, project: Project | None, external_id: str | None
    ) -> None:
        """행의 소속 두 컬럼(`project_uid` · `project_link`)을 채운다 (0060).

        외부 id 로 붙은 티켓은 동기화가 쓰던 **같은 함수**로 해석한다 — 두 벌이 되면
        한쪽만 고쳐지고, 그러면 같은 티켓이 목록에서는 보이는데 상세에서는 범위 밖으로
        판정된다. 포털 전용 프로젝트(외부 짝이 없는 것)는 그 함수가 볼 수 있는 입력이
        아니므로(`project_ids` 가 비어 있다) 여기서 직접 `ok` 로 적는다 —
        `app/work/triage.py::assign_project` 가 사람이 소속을 정할 때 하는 것과 같다.
        """
        if external_id:
            project_link.apply_to_row(row, project_link.portal_project_map(db))
            return
        if project is None:
            project_link.apply_to_row(row, {})
            return
        row.project_uid = project.id
        row.project_link = PROJECT_LINK_OK
