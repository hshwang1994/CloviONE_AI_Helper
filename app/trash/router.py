"""휴지통 API — 목록 조회 / 복원 / 영구 삭제.

목록은 로그인 사용자 누구나 본다(팀 공용 휴지통). 복원·영구삭제는 운영자 이상 또는 그 항목을
버린 본인만(service.ensure_can_manage). 티켓/문서를 '삭제'해 넣는 동작은 각 모듈(tickets/team_docs)
라우터에 있고, 여기서는 넣은 뒤의 관리를 맡는다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import MODERATOR_ROLES
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.etag import etag_json_response
from app.core.errors import NotFoundError
from app.core.ownership import OWNER_ORGANIZATION
from app.trash import repository, service
from app.trash.schemas import TrashBulkIds
from app.users.models import User
from app.settings.gate import block_if_maintenance

router = APIRouter(
    prefix="/api/trash",
    tags=["trash"],
    dependencies=[Depends(block_if_maintenance)],
)

_TYPE_LABELS = {"ticket": "티켓", "document": "문서"}

#: Native 문서 항목의 id 앞머리. 휴지통 항목 id 와 문서 id 를 **한 목록에서** 구별한다.
#:
#: 왜 `trash_items` 에 행을 만들지 않는가: 그 표의 유일키가 `notion_page_id` 이고 Native
#: 문서에는 그런 id 가 없다. 만들어 넣으면 없는 개념을 지어내는 것이고, 지시 22.7 이
#: 「Legacy `trash_items`/Notion page id 구조를 Native 복원의 정본으로 쓰지 말라」고 적었다.
#: 정본은 `documents.archived` 하나이고, 이 화면은 두 출처를 **합쳐서 보여 줄 뿐**이다.
DOC_PREFIX = "doc:"


def _document_id(trash_id: str) -> str | None:
    """휴지통 항목 id 가 Native 문서를 가리키면 그 문서 id, 아니면 None."""
    return trash_id[len(DOC_PREFIX):] if trash_id.startswith(DOC_PREFIX) else None


def _document_view(document, extras, *, retention_days: int | None, me: User) -> dict:
    """Native 문서 한 건을 휴지통 줄로. 열 이름은 옛 항목과 **같다**.

    같지 않으면 화면이 종류마다 다른 표를 그리게 되고, 그 순간 「티켓과 문서를 한 목록에서
    본다」는 지시가 이름만 남는다.
    """
    from app.knowledge import service as knowledge_service

    deleted_at = document.archived_at
    # 자동 삭제가 꺼져 있으면 `retention_days` 가 None 이고, 그때는 삭제 예정도 없다.
    purge_after = (
        deleted_at + timedelta(days=retention_days)
        if (deleted_at and retention_days is not None) else None
    )
    people = extras.get("people") or {}
    archiver = people.get(document.archived_by) or {}
    folder = (extras.get("folders") or {}).get(document.folder_id) if document.folder_id else None
    # 프로젝트 소유 공간은 "프로젝트"로 보인다(§11.2) — 부서 공간은 이 화면의 범위 밖이라
    # (§11.2 는 조직·프로젝트 두 경우만 정한다) 그 공간의 실제 이름을 그대로 쓴다.
    # 🔴 **조직 공통 공간의 이름**을 이 칸에 적지 않는다. 이 값은 화면에서 「프로젝트」
    # 열에 서는데, 거기에 「팀 문서」가 서면 그것이 프로젝트 이름처럼 읽힌다 — 목록과
    # 문서 상세는 같은 문서를 「프로젝트 미지정」이라고 부른다(문서 개편 1·5번).
    # 부서 공간은 그대로 둔다: §11.2 는 조직·프로젝트 두 경우만 정하고, 부서 공간은
    # 이 화면의 범위 밖이라 그 공간의 실제 이름이 사용자에게 더 정확하다.
    # 빈 문자열은 또 다른 뜻이다 — 「옛 미러 항목이라 모른다」.
    project = (extras.get("projects") or {}).get(document.space_id)
    if project:
        space = project["name"]
    elif (extras.get("space_kinds") or {}).get(document.space_id) == OWNER_ORGANIZATION:
        space = "프로젝트 미지정"
    else:
        space = (extras.get("spaces") or {}).get(document.space_id, "")
    return {
        "id": DOC_PREFIX + document.id,
        "item_type": "document",
        "type_label": "문서",
        # 옛 미러 문서와 지금 문서는 **되살리는 방법이 다르다.** 화면이 그것을 알아야
        # 같은 버튼이 두 종류의 요청을 낼 수 있다.
        "source": "knowledge",
        "title": document.title,
        # 🔴 **본문 첫머리.** `list_page_extras` 가 이미 160자 발췌를 계산하고 있었는데
        # 이 응답이 안 실어서 그대로 버려졌다 — 폴링마다 계산하고 폴링마다 버렸다.
        # 영구 삭제는 되돌릴 수 없는데, 그 결정을 제목 한 줄로만 하게 두고 있었다.
        "excerpt": (extras.get("excerpts") or {}).get(document.id, ""),
        "notion_page_id": None,
        "space": space,
        "folder": folder["path"] if folder else "",
        "deleted_by": archiver.get("display_name") or "",
        # 0021 이전에 보관된 문서는 시각을 모른다. 그때는 **비워 둔다** — `updated_at` 을
        # 대신 적으면 「이때 버렸다」는 거짓말이 되고, 삭제 예정일도 함께 틀린다.
        "deleted_at": deleted_at.isoformat() if deleted_at else None,
        "purge_after": purge_after.isoformat() if purge_after else None,
        "can_manage": knowledge_service.can_manage_trashed(me, document),
    }


def _retention_days(request: Request) -> int:
    try:
        return max(1, int(request.app.state.settings_cache.current_value("trash_retention_days") or 7))
    except (TypeError, ValueError):
        return 7


def _document_policy(request: Request) -> tuple[bool, int]:
    """문서 휴지통의 자동 영구 삭제 정책 — **켜졌는가와 며칠인가** (D-352).

    티켓 쪽 기간과 따로 읽는다. 두 정책이 하는 일이 다르기 때문이다: 옛 항목의 정리는
    원본을 보관처리하는 것이고, 문서는 이미 보관된 상태라 다음 단계가 **행을 지우는 것**이다.

    꺼져 있으면 화면이 「삭제 예정」을 말하면 안 된다 — 안 지워지는데 날짜를 적으면 거짓말이다.
    """
    cache = request.app.state.settings_cache
    try:
        days = max(1, int(cache.current_value("document_trash_retention_days") or 7))
    except (TypeError, ValueError):
        days = 7
    enabled = cache.current_value("document_trash_autopurge")
    return (True if enabled is None else bool(enabled)), days


def _item_view(item, *, retention_days: int, me: User) -> dict:
    purge_after = item.deleted_at + timedelta(days=retention_days)
    can_manage = me.role in MODERATOR_ROLES or item.deleted_by_user_id == me.id
    return {
        "id": item.id,
        "item_type": item.item_type,
        "type_label": _TYPE_LABELS.get(item.item_type, item.item_type),
        # 옛 미러(티켓·`document_cache`)에서 온 항목이라는 표시. Native 문서와 되살리는
        # 경로가 다르다.
        "source": "legacy",
        "title": item.title,
        # 옛 미러 행에는 본문이 없다 — 그 표가 제목과 page id 만 든다. 발췌 자리를 **비워
        # 두되 키는 둔다**: 화면이 종류마다 다른 모양을 다루지 않게 하려면 열 이름이 같아야
        # 한다(이 파일의 `_document_view` 머리말과 같은 이유). 본문은 미리보기가 따로 연다.
        "excerpt": "",
        # 옛 항목은 공간/폴더를 모른다 — 그 개념이 없는 표에서 왔다. 빈 값으로 두고
        # 화면이 자리를 비운다(없는 값을 「-」로 지어내지 않는다).
        "space": "",
        "folder": "",
        # `url` 은 여기 없다. 옛 Notion 주소라 목록의 제목을 그 링크로 만들면 사용자가
        # 지운 것을 확인하려다 낡은 사본을 열게 된다(행에는 이관 흔적으로 남는다).
        # FN-14 — 프런트의 문서 상세 캐시 키가 notion_page_id다([team-doc, id], TeamDoc.jsx).
        # 이게 없으면 복원·영구삭제 뒤 그 캐시를 무효화할 방법이 없어 상세를 다시 열면 옛
        # 내용이 잠깐 보인다. 이미 이 행(TicketCache 아님, TrashItem)에 not-null로 있다 — 조인 없음.
        "notion_page_id": item.notion_page_id,
        "deleted_by": item.deleted_by_name,
        "deleted_at": item.deleted_at.isoformat(),
        "purge_after": purge_after.isoformat(),
        "can_manage": can_manage,
    }


#: 화면이 고를 수 있는 정렬 축. 이름을 그대로 `order_by` 에 넣지 않는 이유는 다른 목록과
#: 같다 — 모르는 값은 기본으로 떨어진다(거절하면 옛 주소를 들고 온 사람의 목록이 깨진다).
TRASH_SORTS: tuple[str, ...] = ("deleted_at", "purge_after", "title")
DEFAULT_TRASH_SORT = "deleted_at"


def _doc_sort_axis(sort: str, descending: bool) -> str:
    """휴지통의 축 → 문서 원천(`knowledge.service._order_by`)의 축 이름.

    🔴 두 원천이 **같은 축·같은 방향**으로 정렬돼 있어야 한다. 이 목록은 각 원천에서 앞
    `limit` 줄씩 받아 합치는데, 한쪽만 다른 축으로 정렬돼 있으면 합친 앞 `limit` 줄이
    전역 순서가 아니게 된다 — 실제로 그래서 목록 한가운데가 통째로 비었다.

    `purge_after` 가 `deleted_at` 과 같은 축으로 가는 것은 사실이다: 문서의 삭제 예정일은
    `archived_at + 보관기간` 이고 보관기간은 이 원천 안에서 상수라 두 축의 순서가 같다.
    (원천끼리는 보관기간이 다르지만, 합친 뒤 **실제 `purge_after` 값**으로 다시 세우므로
    그 차이는 거기서 해소된다.)
    """
    if sort == "title":
        return "title_desc" if descending else "title"
    return "archived" if descending else "archived_asc"


def _fetch_documents(db: Session, me: User, *, want: int, sort: str):
    """문서 원천에서 최대 `want` 건. 없으면 `([], 0)`.

    🔴 `list_documents` 는 한 번에 `PAGE_MAX`(200)까지만 준다. 그런데 `total` 은 상한 없이
    센다 — 그래서 보관 문서가 200건을 넘으면 화면의 「더 보기」가 **영원히 수렴하지 않았고**
    (`items.length < total` 이 계속 참), 열 번쯤 누르면 `limit` 이 상한(1000)을 넘어 422 가
    나면서 목록 전체가 오류 화면으로 바뀌었다. 200번째 뒤의 문서는 어떤 방법으로도 화면에서
    볼 수 없었다.

    상한을 올리는 대신 **이어 받는다.** 정렬이 전순서라(`_order_by` 가 `id` 를 붙인다)
    offset 페이지네이션이 같은 행을 두 번 주거나 빠뜨리지 않는다.
    """
    from app.knowledge import service as knowledge_service

    if want <= 0:
        return [], 0
    out: list = []
    offset = 0
    total = 0
    while True:
        page, total = knowledge_service.list_documents(
            db, me, archived_only=True, sort=sort,
            limit=min(want - len(out), knowledge_service.PAGE_MAX), offset=offset,
        )
        out.extend(page)
        offset += len(page)
        if not page or len(out) >= want or offset >= total:
            break
    return out, total


def _merge_sorted(rows: list[dict], *, sort: str, descending: bool) -> list[dict]:
    """두 원천을 합친 줄들을 하나의 **전순서**로 세운다.

    값을 모르는 줄(0021 이전에 보관돼 시각이 없는 문서, 자동 삭제가 꺼져 `purge_after` 가
    없는 문서)은 **어느 방향에서도 뒤**다 — 문서 원천의 `nullslast()` 와 같은 규칙이다.
    앞에 세우면 「가장 최근에 버린 것」 자리에도 「가장 오래된 것」 자리에도 시각을 모르는
    행이 서서 양쪽 다 거짓말이 된다.

    동점은 `id` **오름차순**으로 깬다 — 방향과 무관하게. 두 원천의 SQL 정렬이 그렇게
    잡혀 있어서(`(X.desc(), id.asc())`), 여기서만 뒤집으면 상한 경계의 동점 묶음에서 각
    원천이 잘라 온 것과 합친 결과가 어긋난다.
    """
    field = "title" if sort == "title" else ("purge_after" if sort == "purge_after" else "deleted_at")

    def value(row):
        v = row.get(field)
        # 🔴 제목 축의 **빈 제목은 「모른다」가 아니다.** 빈 문자열로 두어야 두 원천의 SQL
        # 정렬(`title.asc()` / `title.desc()`)과 같은 자리에 선다 — `None` 으로 바꾸면
        # 이쪽만 그 행을 뒤로 보내서, 상한 경계에서 그 행이 목록에서 사라진다.
        # 날짜 축은 반대다: 값을 **정말 모르는** 행이 있고(0021 이전 보관, 자동 삭제 꺼짐)
        # 두 원천의 SQL 이 그것을 `nullslast()` 로 뒤에 둔다.
        if field == "title":
            return (v or "").lower()
        return v or None

    known = [r for r in rows if value(r) is not None]
    unknown = [r for r in rows if value(r) is None]
    # 두 번 센다: 파이썬 정렬은 안정 정렬이라 뒤 정렬이 앞 정렬의 순서를 동점 안에서 지킨다.
    known.sort(key=lambda r: r["id"])
    known.sort(key=value, reverse=descending)
    # 🔴 값을 모르는 줄도 **원천이 실제로 정렬해 온 축**으로 세운다. `id` 로만 세우면
    # 어긋나는 경우가 실제로 있다: 자동 삭제가 꺼진 조직에서 「삭제 예정」으로 정렬하면
    # **모든 문서 줄의 `purge_after` 가 없어** 전부 이 통에 들어오는데, 원천은 그 N 줄을
    # `archived_at` 순으로 골라 왔다. 골라 온 기준과 세우는 기준이 다르면 상한을 늘릴 때
    # 없던 줄이 목록 한가운데로 들어온다 — 이 회차가 잡으려던 바로 그 증상이다.
    # 두 원천 모두 그 축이 `deleted_at` 이다(문서는 `archived_at` 이 그 값이다).
    unknown.sort(key=lambda r: r["id"])
    unknown.sort(key=lambda r: r.get("deleted_at") or "", reverse=descending)
    return known + unknown


@router.get("")
def list_trash(
    request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user),
    # UA-10 확증 — 예전에는 이 값이 아예 없어 응답이 무제한이었고 total도 안 실려서
    # "더 보기" 자체가 불가능했다(?limit=1을 줘도 조용히 무시됐다).
    limit: int = Query(default=repository.DEFAULT_TRASH_LIST_LIMIT, ge=1, le=repository.MAX_TRASH_LIST_LIMIT),
    # 종류로 좁히는 것은 **서버가 한다**. 화면에서만 거르면 상한 너머의 그 종류가 안 보이면서
    # 화면은 「이게 전부」라고 말한다 — 문서 화면의 「휴지통」이 이 조건을 걸고 연다.
    kind: str | None = Query(default=None, max_length=16),
    # 정렬도 **서버가 한다**. 이 목록은 두 원천을 각각 잘라 합치는 자리라, 화면이 받은
    # 것만 다시 세우면 상한 너머가 빠진 채로 「정렬했다」고 말하게 된다.
    sort: str | None = Query(default=None, max_length=16),
    dir: str | None = Query(default=None, max_length=4),
):
    days = _retention_days(request)
    doc_autopurge, doc_days = _document_policy(request)
    # 범위를 건다 — 예전에는 조건이 하나도 없어 남의 팀이 지운 것까지 보였다.
    from app.core.scope import visibility_scope
    from app.knowledge import service as knowledge_service

    scope = visibility_scope(db, me)
    axis = sort if sort in TRASH_SORTS else DEFAULT_TRASH_SORT
    descending = (dir or "desc").lower() != "asc"
    want_documents = kind != "ticket"

    # 옛 미러 표에는 티켓과 문서가 함께 있다. 「문서만」을 골라도 그쪽 문서는 남아야 한다 —
    # 옛 문서를 되살릴 길이 거기 하나뿐이다.
    # 범위를 건 옛 미러 행은 **한 번만** 읽는다 — 아래 목록·개수·급한 건수가 같은 것을 쓴다.
    legacy_rows = repository.scoped_rows(db, scope)
    items, total = repository.list_visible(
        db, scope, limit=limit,
        item_type=kind if kind in ("ticket", "document") else None,
        sort=axis, descending=descending, rows=legacy_rows,
    )
    rows = [_item_view(i, retention_days=days, me=me) for i in items]

    # 🔴 **Native 문서는 이 표에 없다.** 문서 삭제는 `documents.archived` 를 세우는
    # 것이고(그래야 판·멘션·관계가 안 사라진다), 그 사실이 여기 안 실리면 문서를 지운
    # 사람은 되살릴 자리를 찾지 못한다 — 지시 22.7 이 지목한 그 상태다.
    #
    # 가시성은 문서 쪽 문(`list_documents`)이 건다 — 휴지통이 자기 규칙을 갖는 순간
    # 목록에서 가린 문서가 휴지통에서 보인다.
    docs, doc_total = (
        _fetch_documents(db, me, want=limit, sort=_doc_sort_axis(axis, descending))
        if want_documents else ([], 0)
    )
    extras = knowledge_service.list_page_extras(db, me, docs)
    rows += [
        _document_view(d, extras, retention_days=doc_days if doc_autopurge else None, me=me)
        for d in docs
    ]
    # 종류가 섞이므로 고른 축으로 **다시 세운다.**
    rows = _merge_sorted(rows, sort=axis, descending=descending)
    # 🔴 그리고 **자른다.** 예전에는 두 원천을 각각 `limit` 만큼 받아 이어 붙이고 자르지
    # 않아서, `limit=100` 인데 응답이 200줄이었다. 그것만이면 낭비지만 진짜 문제는 순서였다:
    # 두 잘린 앞토막의 합집합이라 **앞 100자리만** 전역 순서가 맞고, 그 뒤는 한쪽 원천의
    # 100~149번이 통째로 빠진 목록이었다. 「더 보기」를 누르면 없던 줄이 목록 한가운데에
    # 나타나 아래가 전부 밀렸다 — 체크박스를 고르는 중이면 고른 줄이 바뀐다.
    rows = rows[:limit]

    # 종류별 개수는 **조건과 상한을 적용하기 전** 기준이다. 예전에는 화면이 받아 온 목록에서
    # 세느라, 문서 화면의 「휴지통」이 `?kind=document` 로 열면 첫 화면부터 「티켓 0」이 떴다.
    legacy_counts = repository.counts_visible(db, scope, rows=legacy_rows)
    counts = {
        "ticket": legacy_counts.get("ticket", 0),
        # 옛 미러 문서와 Native 문서는 화면에서 같은 「문서」다.
        # `doc_total` 은 위 `_fetch_documents` 가 이미 세어 온 값이다 — 같은 가시성 절로
        # 같은 COUNT 를 15초마다 두 번 돌릴 이유가 없다. 티켓만 보는 갈래에서만 따로 센다.
        "document": legacy_counts.get("document", 0) + (
            doc_total if want_documents else _archived_document_total(db, me)
        ),
    }
    counts["all"] = counts["ticket"] + counts["document"]
    counts["urgent"] = _urgent_count(
        request, db, me, legacy_rows, retention_days=days,
        doc_retention_days=(doc_days if doc_autopurge else None),
    )

    # 휴지통은 15초마다 폴링되는데 실제로는 며칠에 한 번 바뀐다 — 전형적인 304 대상이다.
    return etag_json_response(request, {
        "items": rows,
        "retention_days": days,
        # 문서 정책은 따로 싣는다 — 화면이 「문서는 이레 뒤 자동으로 지워집니다」와
        # 「문서는 자동으로 지워지지 않습니다」를 구별해서 말할 수 있어야 한다.
        "document_autopurge": doc_autopurge,
        "document_retention_days": doc_days,
        "total": total + doc_total,
        "sort": axis,
        "dir": "desc" if descending else "asc",
        # 화면의 탭이 이 값을 그린다. `total` 은 조건이 걸린 수고 이쪽은 조건과 무관한 수다 —
        # 둘 다 필요하다(하나는 「지금 목록이 몇 건인가」, 하나는 「저 탭에 몇 건 있는가」).
        "counts": counts,
    })


def _archived_document_total(db: Session, me: User) -> int:
    """보관된 Native 문서의 전체 개수 — 목록을 안 받고 수만 센다."""
    from app.knowledge import service as knowledge_service

    _, total = knowledge_service.list_documents(db, me, archived_only=True, limit=1)
    return int(total)


def _urgent_count(request: Request, db: Session, me: User, legacy_rows, *,
                  retention_days: int, doc_retention_days: int | None) -> int:
    """24시간 안에 영구 삭제될 건수 — **조건·상한과 무관하게** 센다.

    「보관기간이 지나면 사라진다」만으로는 언제가 그 순간인지 알 수 없어서 화면이 이 수를
    앞에 내놓는다. 그런데 예전에는 화면이 **받아 온 목록**을 세서, 종류를 좁히거나 항목이
    상한을 넘으면 그 수가 조용히 줄었다. 급한 건수를 실제보다 적게 말하는 경고는 경고가 아니다.

    두 원천의 보관기간이 다르므로 각자 자기 기준선을 계산한다. 자동 삭제가 꺼진 문서는
    **영원히 급하지 않다** — `purge_after` 자체가 없다(D-352).
    """
    from app.knowledge import service as knowledge_service

    now = request.app.state.clock.now()
    horizon = now + timedelta(days=1)
    # purge_after = deleted_at + 보관기간 <= horizon  ⇔  deleted_at <= horizon - 보관기간
    legacy_cutoff = horizon - timedelta(days=retention_days)
    n = sum(
        1 for r in legacy_rows
        if r.deleted_at is not None and r.deleted_at <= legacy_cutoff
    )
    if doc_retention_days is not None:
        n += knowledge_service.count_archived_due_before(
            db, me, horizon - timedelta(days=doc_retention_days)
        )
    return n


@router.get("/{trash_id}/preview")
def preview(request: Request, trash_id: str, db: Session = Depends(get_db),
            me: User = Depends(get_current_user)):
    """지우기 전에 **무엇을 지우는지 본다** — 옛 미러 항목(티켓·문서) 전용, 읽기 전용.

    ## 왜 이 경로가 따로 필요한가

    영구 삭제는 되돌릴 수 없고 댓글·첨부까지 함께 지운다. 그런데 이 표에서 티켓과 옛 미러
    문서는 **제목 문자열 말고는 볼 방법이 전혀 없었다.** 평소 경로는 전부 막혀 있다 —
    `ticket_detail` 은 첫 줄에서 `ensure_not_trashed` 를, `GET /api/team-docs/{id}` 는
    `ensure_doc_not_trashed` 를 지난다(H2).

    그 가드는 **편집을 막으려고** 있다. 「지웠는데 아직 고쳐지고, 고친 것이 나중에 사라진다」가
    그 머리말이 적은 증상이다. 보기를 막는 것은 그 목적이 아니었고, 오히려 보기를 막은
    결과가 「무엇인지 모른 채 영구 삭제」다. 그래서 여기서는 그 가드를 **의도적으로 건너뛰고**
    나머지는 전부 지난다.

    ## 무엇을 확인하는가 — 셋 다 지난다

    1. **휴지통 행의 범위** (`repository.visible_to`) — 목록에서 가린 것이 여기서 새면
       가린 의미가 없다.
    2. **자원 자신의 범위** (`tickets.ensure_in_scope` · `team_docs.doc_in_scope`) — 1번은
       「누가 버렸나」 기준이라, 그것만 보면 원래 볼 수 없던 티켓을 **팀원이 버렸다는
       이유로** 읽게 된다. 권한의 정본은 자원 쪽이다.
    3. 쓰기는 없다. 이 경로는 GET 하나뿐이고 아무것도 안 바꾼다.

    Native 문서는 여기 오지 않는다 — 그쪽은 문서 화면이 직접 연다(`get_scoped_document_or_404`
    가 `archived` 를 안 막는다). 한 곳에 두 벌의 본문 조립을 두지 않는다.
    """
    from app.core.errors import AppError
    from app.core.scope import visibility_scope

    if _document_id(trash_id):
        # 화면이 실수로 여기로 보내면 조용히 빈 것을 주지 않고 어디로 가야 하는지 말한다.
        raise NotFoundError("이 문서는 문서 화면에서 직접 엽니다.")
    item = _get_or_404(db, trash_id)
    if not repository.visible_to(db, item, visibility_scope(db, me)):
        raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")

    blocks: list | None = None
    blocks_error: str | None = None
    if item.item_type == "ticket":
        from app.tickets import service as tickets_service

        tickets_service.ensure_in_scope(db, item.notion_page_id, me)
        repo = request.app.state.repositories.tickets
    else:
        from app.team_docs import service as team_docs_service

        repo = request.app.state.repositories.documents
        row = repo.get(db, page_id=item.notion_page_id)
        if row is None or not team_docs_service.doc_in_scope(db, row, me):
            raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")
    try:
        blocks = repo.body_blocks(db, page_id=item.notion_page_id)
    except AppError as exc:
        # 본문을 못 읽는 것과 항목이 없는 것은 다른 사실이다. 미리보기가 실패해도 제목과
        # 「영구 삭제는 되돌릴 수 없다」는 그대로 보여야 한다(§17.4 격리와 같은 관용).
        blocks_error = exc.message
    except Exception:
        blocks_error = "본문을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."

    return {
        "id": item.id,
        "item_type": item.item_type,
        "title": item.title,
        "blocks": blocks,
        "blocks_error": blocks_error,
    }


def _get_or_404(db: Session, trash_id: str):
    item = repository.get(db, trash_id)
    if item is None:
        raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")
    return item


def _split_ids(ids: list[str]) -> tuple[list[str], list[str]]:
    """휴지통 항목 id 와 Native 문서 id 를 가른다. 한 요청에 둘이 섞여 온다."""
    legacy: list[str] = []
    docs: list[str] = []
    for raw in ids:
        document_id = _document_id(raw)
        (docs if document_id else legacy).append(document_id or raw)
    return legacy, docs


def _bulk_documents(request: Request, db: Session, me: User, ids: list[str], result: dict,
                    *, key: str, act) -> None:
    """문서 몫을 건별로 처리해 **같은 결과 사전에** 실어 준다.

    실패를 건별로 격리하는 것은 옛 경로와 같은 규칙이다 — 한 건이 권한에 막혔다고 나머지
    아홉 건이 함께 실패하면, 사용자는 어느 것이 처리됐는지 알 수 없어 전부 다시 누른다.
    """
    from app.core.errors import AppError

    for document_id in ids:
        try:
            act(request, db, me, document_id)
            result[key].append({"id": DOC_PREFIX + document_id, "item_type": "document"})
        except AppError as exc:
            result["failed"].append({"id": DOC_PREFIX + document_id, "error": exc.message})


@router.post("/restore-bulk", dependencies=[Depends(require_csrf)])
def restore_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 복원(운영자 이상 또는 버린 본인). 부분 성공.
    (리터럴 경로라 아래 /{trash_id}/... 보다 먼저 선언 — trash_id 로 잡히지 않게.)"""
    legacy, docs = _split_ids(payload.ids)
    result = service.restore_bulk(db, legacy, me)
    _bulk_documents(request, db, me, docs, result, key="restored", act=_restore_document)
    for it in result["restored"]:
        # 문서 몫은 `_restore_document` 가 이미 자기 기록을 남겼다(`notion_page_id` 가 없다).
        if it.get("notion_page_id") is None:
            continue
        record_audit_from_request(request, db, action="trash.restore",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  after={"title": it["title"]})
    return {"ok": True, **result}


@router.post("/purge-bulk", dependencies=[Depends(require_csrf)])
def purge_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 영구삭제(원본 보관처리 + 제거). 부분 성공."""
    legacy, docs = _split_ids(payload.ids)
    result = service.purge_bulk(
        db, legacy, me,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings,
    )
    _bulk_documents(request, db, me, docs, result, key="purged", act=_purge_document)
    for it in result["purged"]:
        if it.get("notion_page_id") is None:
            continue
        record_audit_from_request(request, db, action="trash.purge",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  before={"title": it["title"]})
    return {"ok": True, **result}


def _restore_document(request: Request, db: Session, me: User, document_id: str) -> dict:
    """Native 문서 되살리기 — **판정도 쓰기도 문서 도메인이 한다.**

    여기서 `archived = False` 를 직접 적지 않는 이유는 하나다: 되살리기는 색인을 다시
    거는 일까지 포함하고(보관 중에는 검색·AI 후보에서 빠져 있다), 그 절차가 두 곳에
    적히면 한쪽만 고쳐진다.
    """
    from app.core.errors import ForbiddenError
    from app.knowledge import service as knowledge_service

    document = knowledge_service.get_scoped_document_or_404(db, me, document_id)
    if not knowledge_service.can_manage_trashed(me, document):
        raise ForbiddenError("이 문서를 되살릴 권한이 없습니다.")
    title = document.title
    knowledge_service.restore_document(db, me, document_id)
    record_audit_from_request(
        request, db, action="trash.restore", object_type="document",
        object_id=document_id, after={"title": title},
    )
    return {"ok": True}


def _purge_document(request: Request, db: Session, me: User, document_id: str) -> dict:
    """Native 문서 영구 삭제 — 행을 지운다. 되돌릴 수 없다."""
    from app.core.errors import ForbiddenError
    from app.knowledge import service as knowledge_service

    document = knowledge_service.get_scoped_document_or_404(db, me, document_id)
    if not knowledge_service.can_manage_trashed(me, document):
        raise ForbiddenError("이 문서를 영구 삭제할 권한이 없습니다.")
    info = knowledge_service.purge_document(db, me, document_id)
    record_audit_from_request(
        request, db, action="trash.purge", object_type="document",
        object_id=document_id, before={"title": info["title"]},
    )
    return {"ok": True}


@router.post("/{trash_id}/restore", dependencies=[Depends(require_csrf)])
def restore(request: Request, trash_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    document_id = _document_id(trash_id)
    if document_id:
        return _restore_document(request, db, me, document_id)
    item = _get_or_404(db, trash_id)
    itype, pid, title = item.item_type, item.notion_page_id, item.title
    service.restore(db, item, me)
    record_audit_from_request(
        request, db, action="trash.restore", object_type=f"notion_{itype}",
        object_id=pid, after={"title": title},
    )
    return {"ok": True}


@router.post("/{trash_id}/purge", dependencies=[Depends(require_csrf)])
def purge(request: Request, trash_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """영구 삭제 — 원본을 보관처리하고 휴지통에서 제거(운영자 이상 또는 버린 본인).

    Native 문서는 **뜻이 다르다.** 그쪽은 이미 보관된 상태로 여기 와 있으므로 「보관처리」가
    할 일이 없고, 영구 삭제는 행을 지우는 일이다(지시 22.7 의 「권한이 허용된 영구 삭제」).
    """
    document_id = _document_id(trash_id)
    if document_id:
        return _purge_document(request, db, me, document_id)
    item = _get_or_404(db, trash_id)
    itype, pid, title = item.item_type, item.notion_page_id, item.title
    service.purge_by_user(
        db, item, me,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings,
    )
    record_audit_from_request(
        request, db, action="trash.purge", object_type=f"notion_{itype}",
        object_id=pid, before={"title": title},
    )
    return {"ok": True}
