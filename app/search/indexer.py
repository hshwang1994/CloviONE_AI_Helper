"""검색 인덱스 채우기 — **워커 틱에서만** 돈다 (PLAN Phase 5).

## 뜨거운 경로에 훅을 걸지 않는다

"글 하나 저장할 때 인덱스도 같이 갱신" 이 얼핏 더 신선해 보이지만, 이 앱에서 그 방식은
정확히 가장 나쁜 곳을 때린다. 채팅 전송은 이미 INSERT + `event_seq` UPDATE 로 SAVEPOINT
재시도를 도는 가장 뜨거운 쓰기 경로이고(PLAN C9), 폴링 경로에 인덱스 쓰기를 걸면 **읽기가
쓰기가 된다** — ETag/304 로 아낀 것을 그대로 되돌린다. 그래서 인덱싱은 워커 틱 한 곳에서만
일어나고, 검색 결과는 최대 한 틱만큼 늦다. 그 지연은 사람이 못 느끼고, 병목은 확실히 안 는다.
(이 규칙은 `tests/unit/test_search_no_hot_path.py` 가 import 그래프로 못박는다.)

## 티켓·문서는 저장소 seam 으로만 읽는다

`app/tickets/repository.py` / `app/team_docs/repository_iface.py` 뒤로만 간다. Notion 구현
모듈을 직접 import 하면 정적 검사가 막고, 무엇보다 소스를 바꿀 때 고칠 곳이 흩어진다.
게시판·사용자는 애초에 자체 DB가 정본이라 모델을 직접 읽는다.

## 전체 재구축(full rebuild)이다

증분 갱신은 '무엇이 바뀌었는가'를 네 유형이 각자 다른 방식으로 알려 줘야 하고, 한 유형이
조용히 신호를 빠뜨리면 그 항목만 영원히 옛 내용으로 남는다 — 가장 알아채기 어려운 결함이다.
코퍼스가 수천 건이라 전체 재구축이 1초 안쪽이므로 단순한 쪽을 택했다. 단 **바뀐 행만
UPDATE** 한다(내용이 같으면 건드리지 않는다) — 안 그러면 트리거가 매 틱마다 FTS 인덱스를
통째로 다시 쓴다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.board.models import Post
from app.core.models_base import split_names
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.reports.service import load_display_maps
from app.trash import repository as trash_repo
from app.trash.models import TRASH_DOCUMENT, TRASH_TICKET
from app.search.models import (
    KIND_BOARD,
    KIND_DOCUMENT,
    KIND_TICKET,
    KIND_USER,
    SearchDocument,
    join_owner_ids,
)
from app.users.models import User

logger = logging.getLogger("app.search.indexer")

# 본문은 검색에 걸릴 만큼만 담는다. 통째로 담으면 인덱스가 원본만큼 커지고 trigram 이
# 문서 하나에 수만 개 트라이그램을 만든다.
BODY_CHARS = 2000

# 한 유형에서 인덱싱할 최대 건수. 코퍼스 상한을 두지 않으면 어느 날 티켓이 5만 건이 됐을 때
# 워커 틱 하나가 조용히 수십 초를 먹는다.
MAX_ROWS_PER_KIND = 5000


@dataclass(frozen=True)
class IndexResult:
    """한 번의 재구축 결과. 워커가 sync_status 로 옮겨 적는다."""

    status: str
    item_count: int = 0
    error: str | None = None
    # 유형별 건수 — 한 유형만 0이 되는 사고(소스 장애)를 상태 화면에서 바로 본다.
    per_kind: tuple[tuple[str, int], ...] = ()
    truncated: bool = False


def _clip(text: str | None, limit: int = BODY_CHARS) -> str:
    """색인에 들어가는 모든 글은 **여기 하나**를 지난다 — 그래서 정규화도 여기서 한다 (Z4).

    한글은 **같은 글자를 두 가지로 쓸 수 있다.** `한`(NFC, 1코드포인트)과 `한`(NFD, ㅎ+ㅏ+ㄴ
    3코드포인트)은 화면에서 똑같이 보이지만 **바이트가 다르다.** macOS 에서 만든 파일 이름이나
    거기서 복사한 글은 NFD 로 들어오는 일이 흔하다.

    trigram 은 코드포인트를 훑으므로, 색인은 NFC 인데 질의가 NFD 면(또는 반대면) **영원히
    0건**이다. 오타도 아니고 오류도 아니라 사용자는 "검색이 안 된다" 고만 느끼고, 로그에도
    아무 흔적이 없다.

    자르기 **전에** 정규화한다. NFD 는 같은 글자를 여러 코드포인트로 쓰므로, 먼저 자르면
    같은 글이 표기에 따라 다른 길이에서 잘리고 마지막 글자가 자모로 쪼개진 채 남을 수 있다.
    """
    import unicodedata

    return unicodedata.normalize("NFC", str(text or ""))[:limit]


def _joined(parts) -> str:
    """검색 본문 한 덩이. 빈 조각은 버리고 공백으로 잇는다."""
    return " ".join(str(p).strip() for p in parts if str(p or "").strip())


def _joined_sep(parts) -> str:
    """결과 줄의 부제 한 줄(가운뎃점으로 구분)."""
    return ", ".join(str(p).strip() for p in parts if str(p or "").strip())


def _dept_names(db: Session) -> dict[str, str]:
    rows = db.execute(select(Department.id, Department.name)).all()
    return {row[0]: row[1] or "" for row in rows}


def _ticket_rows(db: Session, repo, maps) -> list[dict]:
    """티켓 — 저장소 seam(`list_all`)으로만 읽는다.

    담당자는 **원본 Notion id 가 아니라 앱 user_id 로 해석해서** 저장한다. 원본 id 를 넣으면
    범위 판정이 못 하고(§12.3), 인덱스가 원본 식별자를 들고 있게 된다.
    """
    listing = repo.list_all(db)
    # 휴지통에 넣은 티켓은 색인하지 않는다(H2). 예전에는 보관기간(기본 7일) 내내 검색과
    # ⌘K 에 계속 나왔다 — "지웠는데 검색에는 있다" 는 지운 적이 없다는 말처럼 읽힌다.
    # 목록 API 는 이미 `_drop_trashed` 로 거른다. 색인만 빠져 있었다.
    trashed = trash_repo.trashed_page_ids(db, TRASH_TICKET)
    out: list[dict] = []
    for t in listing.tickets[:MAX_ROWS_PER_KIND]:
        if not t.page_id or t.page_id in trashed:
            continue
        number = f"GIT-{t.number}" if t.number is not None else ""
        out.append({
            "kind": KIND_TICKET,
            "ref_id": t.page_id,
            "org_id": DEFAULT_ORG_ID,
            "owner_user_ids": join_owner_ids(
                maps.id_to_user[a] for a in t.assignee_ids if a in maps.id_to_user
            ),
            "title": _clip(t.title, 500),
            "body": _clip(_joined([number, t.status, *t.project_names, t.body_markdown])),
            "subtitle": _clip(_joined_sep([number, t.status, ", ".join(t.project_names)]), 300),
            "route": f"/tickets/{t.page_id}",
            "url": t.url,
            "sort_key": t.due,
        })
    return out


def _document_rows(db: Session, repo, maps) -> list[dict]:
    """문서 — 저장소 seam(`list_documents`)으로만 읽는다.

    소유자 해석은 표시 이름으로 한다(문서에는 앱 계정 참조가 없다). 못 맞추면 소유자가 빈
    행이 되고, 부서 범위에서는 안 보인다 — fail-closed 다.
    """
    rows, _total = repo.list_documents(
        db,
        search=None, doc_type_f=None, work_field_f=None, project_f=None, tech_f=None,
        favorite_page_ids=None, favorites_only=False,
        sort="recent", offset=0, limit=MAX_ROWS_PER_KIND,
    )
    # 티켓과 같은 이유로 휴지통 문서도 뺀다(H2).
    trashed_docs = trash_repo.trashed_page_ids(db, TRASH_DOCUMENT)
    rows = [r for r in rows if getattr(r, "notion_page_id", None) not in trashed_docs]
    out: list[dict] = []
    for d in rows:
        # 이 필드들은 콤마가 아니라 NAMES_SEP(\x1f) 로 이어져 있다. 콤마로 자르면 이름 하나가
        # 통째로 안 맞아 소유자 해석이 조용히 0명이 된다.
        authors = split_names(d.author_names)
        names = [*authors, d.owner] if d.owner else list(authors)
        owners = [maps.name_to_user[n.strip()] for n in names if n.strip() in maps.name_to_user]
        out.append({
            "kind": KIND_DOCUMENT,
            "ref_id": d.notion_page_id,
            "org_id": getattr(d, "org_id", None) or DEFAULT_ORG_ID,
            "owner_user_ids": join_owner_ids(owners),
            "title": _clip(d.title, 500),
            "body": _clip(_joined([
                d.memo, d.owner, *authors,
                *split_names(d.project_names), *split_names(d.type_names),
                *split_names(d.tech_tags),
            ])),
            "subtitle": _clip(_joined_sep([d.document_type, d.work_field, d.owner]), 300),
            "route": f"/team-docs/{d.notion_page_id}",
            "url": d.original_url or d.source_url,
            "sort_key": d.last_edited or d.doc_date,
        })
    return out


def _board_rows(db: Session, dept_names: dict[str, str]) -> list[dict]:
    """게시판 — 자체 DB가 정본이라 모델을 직접 읽는다. 삭제된 글은 인덱싱하지 않는다."""
    rows = db.execute(
        select(Post, User)
        .outerjoin(User, User.id == Post.author_user_id)
        .where(Post.deleted_at.is_(None))
        .order_by(Post.created_at.desc())
        .limit(MAX_ROWS_PER_KIND)
    ).all()
    out: list[dict] = []
    for post, author in rows:
        out.append({
            "kind": KIND_BOARD,
            "ref_id": post.id,
            "org_id": getattr(post, "org_id", None) or DEFAULT_ORG_ID,
            "owner_user_ids": join_owner_ids([post.author_user_id]),
            "title": _clip(post.title, 500),
            "body": _clip(_joined([post.body, author.display_name if author else ""])),
            "subtitle": _clip(_joined_sep([
                post.category,
                author.display_name if author else "",
                dept_names.get(author.department_id, "") if author else "",
            ]), 300),
            "route": f"/board/{post.id}",
            "url": None,
            "sort_key": post.created_at.isoformat() if post.created_at else None,
        })
    return out


def _user_rows(db: Session, dept_names: dict[str, str]) -> list[dict]:
    """사용자 — 이름·부서·직책만 담는다. **이메일은 인덱싱하지 않는다.**

    이미 있는 `/api/team-chat/directory` 가 정확히 이 세 가지만 내보낸다(이메일·역할 제외).
    검색이 그보다 더 내보내면 화면에서 가려 둔 것을 검색이 되돌리는 셈이고, 이메일이 본문에
    있으면 "이 주소가 우리 회사에 있는가"를 검색창으로 확인할 수 있게 된다(계정 열거).
    결과 자체도 사용자 화면을 열 수 있는 역할에게만 나간다(app/search/service.py).
    """
    rows = db.execute(
        select(User)
        .where(User.active.is_(True), User.archived_at.is_(None))
        .order_by(User.display_name)
        .limit(MAX_ROWS_PER_KIND)
    ).scalars().all()
    out: list[dict] = []
    for u in rows:
        dept = dept_names.get(u.department_id or "", "")
        title = u.title_ref.name if getattr(u, "title_ref", None) else ""
        out.append({
            "kind": KIND_USER,
            "ref_id": u.id,
            "org_id": getattr(u, "org_id", None) or DEFAULT_ORG_ID,
            "owner_user_ids": join_owner_ids([u.id]),
            "title": _clip(u.display_name, 500),
            "body": _joined([dept, title]),
            "subtitle": _clip(_joined_sep([dept, title]), 300),
            # 사용자 화면은 id 딥링크를 받지 않고 검색어(`?q=`)만 받는다. id 를 넘기면
            # 화면이 그 값을 무시하고 **필터 없는 전체 목록**을 그린다 — 눌렀는데 아무 일도
            # 안 한 것처럼 보인다. 화면이 실제로 이해하는 파라미터로 보낸다.
            "route": "/users?q=" + quote(u.display_name or ""),
            "url": None,
            "sort_key": None,
        })
    return out


_FIELDS = (
    "org_id", "owner_user_ids", "title", "body", "subtitle", "route", "url", "sort_key",
)


def _apply(db: Session, desired: list[dict], now: datetime) -> int:
    """원하는 상태로 맞춘다(있으면 갱신, 없으면 삽입, 사라진 것은 삭제).

    **내용이 같으면 UPDATE 하지 않는다.** external content FTS5 는 UPDATE 트리거에서
    인덱스 항목을 지우고 다시 넣으므로, 매 틱마다 전 행을 건드리면 인덱스를 통째로 다시
    쓰는 것과 같다.
    """
    existing = {
        (row.kind, row.ref_id): row
        for row in db.execute(select(SearchDocument)).scalars().all()
    }
    seen: set[tuple[str, str]] = set()
    for item in desired:
        key = (item["kind"], item["ref_id"])
        if not key[1] or key in seen:
            continue
        seen.add(key)
        row = existing.get(key)
        if row is None:
            db.add(SearchDocument(kind=key[0], ref_id=key[1], indexed_at=now, **{
                f: item.get(f) if f in ("url", "sort_key", "org_id") else (item.get(f) or "")
                for f in _FIELDS
            }))
            continue
        changed = False
        for field in _FIELDS:
            new_value = item.get(field) if field in ("url", "sort_key", "org_id") else (item.get(field) or "")
            if getattr(row, field) != new_value:
                setattr(row, field, new_value)
                changed = True
        if changed:
            row.indexed_at = now
    for key, row in existing.items():
        if key not in seen:
            db.delete(row)
    db.flush()
    return len(seen)


def reindex_all(db: Session, *, tickets, documents, now: datetime) -> IndexResult:
    """검색 인덱스를 통째로 다시 만든다. **예외는 절대 밖으로 나가지 않는다.**

    워커 틱이 죽으면 스케줄러·하트비트까지 함께 멈춘다(문서·티켓 sync 와 같은 관용).
    유형 하나가 실패해도 나머지는 인덱싱한다 — 소스(Notion) 장애로 티켓을 못 읽었다고
    게시판 검색까지 사라질 이유가 없다.
    """
    per_kind: list[tuple[str, int]] = []
    errors: list[str] = []
    desired: list[dict] = []
    try:
        maps = load_display_maps(db)
        dept_names = _dept_names(db)
        for kind, build in (
            (KIND_TICKET, lambda: _ticket_rows(db, tickets, maps)),
            (KIND_DOCUMENT, lambda: _document_rows(db, documents, maps)),
            (KIND_BOARD, lambda: _board_rows(db, dept_names)),
            (KIND_USER, lambda: _user_rows(db, dept_names)),
        ):
            try:
                rows = build()
            except Exception as exc:  # noqa: BLE001 — 한 유형의 실패가 전체를 못 죽이게
                logger.exception("검색 인덱싱 실패: %s", kind)
                errors.append(f"{kind}: {type(exc).__name__}")
                # 실패한 유형은 **기존 인덱스를 그대로 둔다**. 빈 목록을 흘리면 prune 이
                # 그 유형을 통째로 지워, 소스 장애가 검색 결과 소멸로 번진다.
                rows = [
                    {
                        "kind": r.kind, "ref_id": r.ref_id, "org_id": r.org_id,
                        "owner_user_ids": r.owner_user_ids, "title": r.title, "body": r.body,
                        "subtitle": r.subtitle, "route": r.route, "url": r.url,
                        "sort_key": r.sort_key,
                    }
                    for r in db.execute(
                        select(SearchDocument).where(SearchDocument.kind == kind)
                    ).scalars().all()
                ]
            per_kind.append((kind, len(rows)))
            desired.extend(rows)
        count = _apply(db, desired, now)
    except Exception as exc:  # noqa: BLE001 — 워커 틱 밖으로 아무것도 던지지 않는다
        logger.exception("검색 인덱스 재구축 실패")
        return IndexResult(status="error", error=f"{type(exc).__name__}: {exc}")
    return IndexResult(
        status="error" if errors else "ok",
        item_count=count,
        error="; ".join(errors) or None,
        per_kind=tuple(per_kind),
    )
