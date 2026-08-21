"""팀 공간 > 문서 비즈니스 규칙 (필터 옵션·즐겨찾기·최근 열람).

유니크 제약이 걸린 삽입(즐겨찾기·최근열람)은 동시 요청에서 500이 나지 않도록 SAVEPOINT +
IntegrityError 흡수로 멱등하게 처리한다(자유게시판 검수에서 배운 패턴).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core import ownership
from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_insert_race, write_conflict_backoff
from app.core.errors import ForbiddenError, NotFoundError
from app.team_docs import comments as doc_comments
from app.team_docs import repository
from app.team_docs.models import (
    DocumentCache,
    DocumentFavorite,
    DocumentRecentView,
    join_names,
    split_names,
)
# 수동 동기화는 운영자군만(무분별한 Notion 호출·비용 방지). 주기 동기화는 워커가 전원에게 제공.
# 문서 삭제(휴지통)도 같은 선이다 — 운영자군은 남의 문서도, 그 외는 본인 문서만.
# 다만 그 판정은 **범위 안에서만** 뜻이 있다. 이 줄은 예전에 "운영자군은 무엇이든" 이었고
# 코드도 역할만 봤다 — 다른 부서 운영자가 목록에서 안 보이는 문서를 id 로 지울 수 있었다.
# 이제 범위 밖 문서는 역할과 무관하게 없는 것으로 답한다(`get_doc_in_scope`).
# 예전엔 SYNC_ROLES / _DOC_DELETE_ROLES 두 이름이 **같은 집합**을 각자 계산하고 있었다:
# 한쪽만 고치면 "동기화는 되는데 삭제는 안 되는" 상태가 조용히 생긴다. 이제 이름도
# 지우고 authz 의 MODERATOR_ROLES 를 그대로 쓴다.
from app.core.authz import MODERATOR_ROLES
from app.users.models import User

if TYPE_CHECKING:  # 타입 표기 전용 — 런타임 순환 임포트를 만들지 않는다
    from app.core.scope import Scope

logger = logging.getLogger(__name__)


def can_trigger_sync(user: User) -> bool:
    return user.role in MODERATOR_ROLES


def ensure_can_delete_doc(doc: DocumentCache, user: User, db: Session | None = None) -> None:
    """문서 삭제 권한 — 운영자군이거나 **작성자 본인**.

    ## 이건 범위 판정이 **아니다**

    "삭제 경로가 이 함수를 지나니 안전하다" 고 읽으면 안 된다 — 여기는 *누가* 지울 수 있는가만
    본다. *어느 문서를* 지울 수 있는가는 `doc_in_scope` 가 답하고, 그걸 안 걸어 뒀더니 **다른
    부서 운영자가 목록에서 안 보이는 문서를 id 로 지울 수 있었다.** 그래서 부르는 쪽
    (`trash_document`)이 범위를 **먼저** 본다.

    ## 이름이 아니라 id 로 판정한다 (X2)

    예전에는 `display_name` 문자열을 비교했다. `users.display_name` 에는 **유일 제약이 없어**
    (바로 위 `email` 에는 있다) 두 가지가 동시에 일어났다:

      * **개명하면 자기 문서를 못 지운다** — 이름이 안 맞으니 403.
      * **동명이인은 남의 문서를 지운다** — 이름이 맞으니 통과.

    같은 저장소의 `app/core/people.py` 가 "display_name 에 유일 제약이 없다" 고 이미 경고해
    놓았는데 이 판정만 그 이름을 신뢰하고 있었다.

    ## 폴백: 아직 id 가 없는 행은 이름으로 본다

    작성자 id 는 **다음 동기화가** 채운다(이름에서 역산하면 지금 고치려는 그 동명이인
    문제를 되풀이한다). 그 사이에 이름 판정을 없애면 **재동기화 전까지 아무도 자기 문서를
    못 지운다** — 고치려던 것보다 나쁜 상태가 된다.
    """
    if user.role in MODERATOR_ROLES:
        return

    author_ids = [a for a in split_names(doc.author_notion_ids or "") if a]
    if author_ids and db is not None:
        # id 가 있으면 **id 로만** 판정한다 — 여기서 이름을 같이 보면 동명이인 구멍이 그대로 남는다.
        from app.tickets.service import my_notion_id

        mine = my_notion_id(db, user)
        if mine and mine in author_ids:
            return
        raise ForbiddenError("이 문서를 삭제할 권한이 없습니다(작성자 또는 운영자만 가능).")

    # 폴백 — 아직 동기화가 id 를 채우지 않은 행.
    name = (user.display_name or "").strip()
    authors = {a.strip() for a in split_names(doc.author_names or "")}
    if name and (name in authors or name == (doc.owner or "").strip()):
        return
    raise ForbiddenError("이 문서를 삭제할 권한이 없습니다(작성자 또는 운영자만 가능).")


def _is_doc_author(db: Session, doc, viewer: User) -> bool:
    """`ensure_can_delete_doc` 의 작성자 판정과 같은 규칙(id 우선, id 없으면 이름 폴백) —
    거기서 새 함수로 뽑아 `doc_in_scope` 의 제한 문서 판정과 함께 쓴다(판정 두 벌 방지)."""
    author_ids = [a for a in split_names(doc.author_notion_ids or "") if a]
    if author_ids:
        from app.tickets.service import my_notion_id

        mine = my_notion_id(db, viewer)
        if mine and mine in author_ids:
            return True
        return False
    name = (viewer.display_name or "").strip()
    authors = {a.strip() for a in split_names(doc.author_names or "")}
    return bool(name) and (name in authors or name == (doc.owner or "").strip())


@dataclass(frozen=True)
class DocScopeContext:
    """문서 가시성 판정에 필요한 것들을 **요청당 한 번** 모아 둔 값.

    문서 목록은 행마다 이 판정을 부른다. 예전에는 그때마다 매핑표를 다시 읽어 N+1 이 됐고
    (FN-41), 이제는 프로젝트 집합까지 필요하므로 그대로 두면 질의가 두 배가 된다. 한 번
    만들어 넘긴다.

    `visible_projects` 가 `None` 이면 제한 없음(전역)이다. 빈 집합은 아무것도 안 보인다 —
    둘을 같은 값으로 표현하면 범위 계산이 빈 답을 낸 순간 조용히 전 포탈이 열린다.
    """

    scope: "Scope"
    visible_projects: frozenset[str] | None
    my_notion_id: str | None
    is_moderator: bool


def doc_scope_context(db: Session, viewer: User, scope=None) -> DocScopeContext:
    """판정 재료 한 벌. `scope` 를 주면 **그것으로 더 좁힌다**(넓히지 못한다).

    목록 화면의 부서 필터가 그 인자를 쓴다(`app/org/context.py::filter_scope`) — 부르는
    쪽이 이미 그 사람의 조회 범위 안에서 검증한 값만 넘긴다. 여기서 다시 계산하면 필터가
    범위를 넓히는 길이 열린다.
    """
    from app.core.scope import visibility_scope
    from app.projects.models import Project
    from app.tickets.service import my_notion_id as _my_notion_id

    scope = scope if scope is not None else visibility_scope(db, viewer)
    if scope.is_global:
        projects: frozenset[str] | None = None
    else:
        projects = frozenset(
            db.execute(ownership.visible_project_ids(scope)).scalars().all()
        )
    return DocScopeContext(
        scope=scope,
        visible_projects=projects,
        my_notion_id=_my_notion_id(db, viewer),
        is_moderator=viewer.role in MODERATOR_ROLES,
    )


def document_ownership(doc) -> ownership.Ownership:
    """문서 행 → 소속. **Portal 이 저장한 값만 읽는다.**

    작성자(`author_notion_ids`)를 보지 않는 것이 핵심이다. 작성자와 소유는 다른 개념이고,
    작성자가 다른 부서로 옮겨도 그 사람이 예전에 쓴 문서가 따라 움직이면 안 된다.
    """
    kind = getattr(doc, "owner_kind", None) or ownership.OWNER_UNSET
    if kind == ownership.OWNER_PROJECT:
        return ownership.Ownership(
            ownership.OWNER_PROJECT,
            org_id=getattr(doc, "org_id", None),
            project_id=getattr(doc, "owner_project_id", None),
        )
    if kind == ownership.OWNER_DEPARTMENT:
        return ownership.for_department(
            getattr(doc, "owner_dept_id", None), getattr(doc, "org_id", None)
        )
    if kind == ownership.OWNER_ORGANIZATION:
        return ownership.for_organization(getattr(doc, "org_id", None))
    return ownership.UNSET


def doc_in_scope(db: Session, doc, viewer, *, ctx: DocScopeContext | None = None) -> bool:
    """이 사람이 이 문서를 볼 수 있는가 — **목록·상세·쓰기가 모두 지나는 단 하나의 문**.

    ## 소속은 Portal 이 정한다 (0060 에서 바뀐 규칙)

    예전에는 **작성자의 부서**로 판정했다. 세 가지가 잘못이었다:
      * 작성자가 부서를 옮기면 과거 문서가 따라 움직인다.
      * 작성자를 앱 계정으로 해석하지 못하면 통과시켰다 — Notion 미러라 그런 문서가 흔했다.
      * 프로젝트 문서라는 개념 자체를 표현할 수 없었다.

    이제 문서는 자기 소속을 스스로 들고 있고(`owner_kind` + 두 id), 그 소속이 판정한다.
    소속을 모르는 문서(`unset`)는 **전역 관리자만** 본다 — 추측해서 열지 않는다.

    ## `restricted` 는 그 위에 겹친다

    SEC-10 의 문서 단위 열람 제한이다. 소속이 맞아도(같은 부서 동료라도) 제한 문서는
    운영자군과 작성자만 본다 — 원본에 평문 자격증명이 있는 문서처럼, "같은 팀" 이 곧
    "봐도 되는 사람" 은 아니다.

    `viewer is None`(내부 호출, 범위 무관)은 그대로 통과시킨다.
    """
    if viewer is None:
        return True
    if ctx is None:
        ctx = doc_scope_context(db, viewer)
    if getattr(doc, "restricted", False):
        if not ctx.is_moderator and not _is_doc_author(db, doc, viewer):
            return False
    owner = document_ownership(doc)
    if owner.kind == ownership.OWNER_PROJECT:
        if ctx.visible_projects is None:
            return True
        return bool(owner.project_id) and owner.project_id in ctx.visible_projects
    return ownership.scope_can_view(ctx.scope, owner)


def get_doc_in_scope(db: Session, page_id: str, viewer: User) -> DocumentCache | None:
    """page_id 로 문서 하나 — **범위 밖이면 아예 안 나온다**(부르는 쪽이 404 로 만든다).

    목록은 `doc_in_scope` 로 좁혀 놓고 휴지통 이동·즐겨찾기는 `page_id` 를 그대로 받았다.
    그래서 목록에서 가린 문서를 **id 하나로 휴지통에 넣을** 수 있었다 — 읽기 유출이 아니라
    남의 범위에서의 **쓰기 실행**이고, 문서가 사라진 팀은 원인도 못 찾는다(휴지통 항목은
    지운 사람의 범위에 남는다).

    조회와 판정을 한 함수로 묶는 이유는 잡 큐 `app/jobs/repository.py::get_in_scope` 와 같다:
    먼저 꺼내 놓고 나중에 판정하는 모양이면 **판정을 빠뜨린 새 경로가 조용히 열린다.**
    (판정 자체는 SQL 로 못 쓴다 — 작성자 Notion id 를 앱 사용자로 해석해야 하므로
    `doc_in_scope` 가 파이썬에서 답한다.)
    """
    doc = repository.get_by_page_id(db, page_id)
    if doc is None or not doc_in_scope(db, doc, viewer):
        return None
    return doc


def trash_document(db: Session, *, user: User, page_id: str, now: datetime) -> dict:
    """문서를 휴지통으로 보낸다(노션 원본은 보관기간 뒤 삭제). **범위 안**에서, 작성자/운영자만."""
    from app.trash import service as trash_service
    from app.trash.models import TRASH_DOCUMENT

    # 범위를 **먼저** 본다. `ensure_can_delete_doc` 는 작성자/운영자 판정이라 다른 부서
    # 운영자를 그냥 통과시킨다. 범위 밖은 없는 문서와 **똑같은 404** 로 답한다 — 403 이나
    # 다른 문구는 그 id 가 존재한다는 사실을 알려 준다(저장소 규칙).
    doc = get_doc_in_scope(db, page_id, user)
    if doc is None:
        raise NotFoundError("문서를 찾을 수 없습니다.")
    ensure_can_delete_doc(doc, user, db)
    item = trash_service.move_to_trash(
        db, item_type=TRASH_DOCUMENT, notion_page_id=page_id,
        title=doc.title or "(제목 없음)", url=doc.url, user=user, now=now,
    )
    return {"title": item.title, "url": item.url}


def trash_documents_bulk(db: Session, *, user: User, page_ids: list[str], now: datetime) -> dict:
    """문서 여러 건을 휴지통으로. 건별로 `trash_document` 를 그대로 지나므로 범위·권한 판정이
    단건과 같다(일괄 경로만 열려 있으면 단건을 막은 의미가 없다). 실패는 건너뛰고 계속(부분 성공)."""
    from app.core.errors import AppError

    trashed: list[dict] = []
    failed: list[dict] = []
    for pid in page_ids:
        try:
            result = trash_document(db, user=user, page_id=pid, now=now)
            trashed.append({"id": pid, "title": result["title"]})
        except AppError as exc:
            failed.append({"id": pid, "error": exc.message})
    return {"trashed": trashed, "failed": failed}


def set_doc_restricted(db: Session, *, user: User, page_id: str, restricted: bool) -> DocumentCache:
    """문서 열람 제한을 켜고 끈다(SEC-10) — **범위 안**에서, 운영자군만.

    `trash_document` 와 같은 순서다: 범위를 **먼저** 본다(다른 부서 운영자가 목록에 안 보이는
    문서를 id 로 건드리는 구멍을 다시 만들지 않으려고 — `ensure_can_delete_doc` docstring 참고).
    범위 밖은 없는 문서와 **똑같은 404**. 범위 안인데 운영자가 아니면 403 — 이 조작은 삭제와
    달리 작성자 본인에게도 안 준다(제한을 스스로 풀 수 있으면 제한의 의미가 없다).
    """
    doc = get_doc_in_scope(db, page_id, user)
    if doc is None:
        raise NotFoundError("문서를 찾을 수 없습니다.")
    if user.role not in MODERATOR_ROLES:
        raise ForbiddenError("문서 열람 제한은 운영자만 변경할 수 있습니다.")
    doc.restricted = bool(restricted)
    db.flush()
    return doc


def filter_options(db: Session, viewer: User) -> dict:
    """필터·작성 폼 옵션. 문서 종류·업무 분야·기술 태그는 고정 상수(공통), 프로젝트·상태는
    **그 사람이 볼 수 있는** 캐시 문서에서 실제 쓰이는 값.

    ## 목록만 좁히고 필터는 안 좁혔다

    이 함수에는 `viewer` 인자 자체가 없었다. 목록은 `doc_in_scope` 로 행을 거르고 total 까지
    보정하는데, 드롭다운은 `all_active` 로 **캐시 전량**을 훑었다. 그래서 목록에서 가린 문서의
    **프로젝트 코드명**이 그대로 나갔다 — 그 이름은 대개 그 자체가 정보다(고객사명·제품명이
    들어간다). 상태 어휘도 남의 팀 업무 흐름을 알려 준다.

    본문을 안 줬으니 유출이 아니라고 읽으면 안 된다. "어떤 고객사 일을 하고 있는가" 는 문서를
    한 건도 안 열어도 알 수 있는 사실이고, 옵션 목록은 그걸 정리해서 준다.

    판정은 목록·상세·쓰기가 쓰는 `doc_in_scope` **그 함수**다. 여기서 조건을 새로 적으면
    판정이 두 벌이 되고, 한쪽만 고치는 날 조용히 갈라진다.

    ## 고정 상수는 좁히지 **않는다**

    문서 종류·업무 분야·기술 태그는 캐시가 아니라 `classify.py` 에 박힌 공통 어휘라 누구에게나
    같다 — 가릴 것이 없다. 오히려 좁히면 해가 된다: "우리 팀에 아직 회의록이 없다" 는 이유로
    작성 폼에서 회의록을 고를 수 없게 되고, 그때부터 아무도 새 종류의 문서를 못 만든다.

    ## 판정은 목록과 **같은 함수**다

    필터 후보가 목록보다 넓으면 "고를 수는 있는데 결과가 0건" 이 되고, 좁으면 목록에 보이는
    문서를 필터로 못 고른다. 둘 다 사용자가 원인을 못 찾는 종류의 어긋남이라 같은 문
    (`doc_in_scope`)을 지난다 — 판정 재료는 한 번만 만들어 돌려 쓴다(N+1 방지).
    """
    from app.team_docs.classify import DOC_TYPES, TECH_TAGS, WORK_FIELDS

    ctx = doc_scope_context(db, viewer) if viewer is not None else None
    projects: set[str] = set()
    statuses: set[str] = set()
    for row in repository.all_active(db):
        if not doc_in_scope(db, row, viewer, ctx=ctx):
            continue
        projects.update(split_names(row.project_names))
        if row.status:
            statuses.add(row.status)
    return {
        "doc_types": list(DOC_TYPES),
        "work_fields": list(WORK_FIELDS),
        "tech_tags": list(TECH_TAGS),
        "projects": sorted(projects),
        "statuses": sorted(statuses),
    }


def _document_uid(db: Session, page_id: str) -> str | None:
    """Notion page id → 미러 행의 자체 UUID(0025). 미러에 없으면 None.

    None 이 정상 상태다: 방금 만들어져 아직 동기화되지 않은 문서를 즐겨찾기할 수 있다.
    그래서 이 값을 필수로 만들거나 FK 로 걸지 않는다 — 조회·유일성은 계속 notion_page_id 가
    담당하고 이 컬럼은 소스 전환을 위한 다리일 뿐이다.
    """
    from app.team_docs.models import DocumentCache

    return db.execute(
        select(DocumentCache.id).where(DocumentCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def toggle_favorite(db: Session, *, user_id: str, page_id: str, on: bool, now: datetime) -> bool:
    existing = repository.find_favorite(db, user_id, page_id)
    if on:
        if existing is not None:
            return True
        row = DocumentFavorite(
            user_id=user_id, notion_page_id=page_id, created_at=now,
            document_id=_document_uid(db, page_id),
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            pass  # 동시 요청이 먼저 추가 — 멱등
        return True
    if existing is not None:
        db.delete(existing)
        db.flush()
    return False


_RECORD_VIEW_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES


def record_view(db: Session, *, user_id: str, page_id: str, now: datetime) -> None:
    """최근 열람 기록 — 문서 상세 GET의 부수효과라 실패해도 본문 조회 자체를 막으면 안 된다.

    실측(2026-08-15 E2E): 기존 코드는 "행이 이미 있으면 갱신"(existing 분기)에 재시도가
    전혀 없어, 이미 성공적으로 읽어 온 본문이 있는데도 이 마지막 한 줄의 `database is locked`
    로 문서 상세 전체가 원시 500이 났다(반대로 "행이 아직 없어 새로 만드는" 분기는 이미
    PA-RC-0008 관용대로 한 번은 재시도 폴백이 있었다 — 둘을 하나의 루프로 합쳐 어느
    분기든 같은 예산을 쓰게 한다).

    예산을 다 쓰면(극히 드묾) 조용히 포기한다 — approvals/prompts류(사용자가 직접 일으킨
    쓰기)와 달리 여기엔 사용자에게 409로 알릴 대상 행동이 없다: 최악의 결과는 "최근 열람"
    시각이 이번 조회분만 안 갱신되는 것뿐이라, 로그만 남기고 본문 응답은 그대로 낸다.
    """
    for attempt in range(_RECORD_VIEW_RETRIES):
        try:
            with db.begin_nested():
                existing = repository.find_recent(db, user_id, page_id)
                if existing is not None:
                    existing.viewed_at = now
                else:
                    db.add(DocumentRecentView(
                        user_id=user_id, notion_page_id=page_id, viewed_at=now,
                        document_id=_document_uid(db, page_id),
                    ))
                db.flush()
            return
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            if attempt == _RECORD_VIEW_RETRIES - 1:
                logger.warning(
                    "최근 열람 기록 갱신 재시도 소진(page_id=%s), 조회 자체는 계속 진행합니다.",
                    page_id,
                )
                return
            time.sleep(write_conflict_backoff(attempt))


def cache_created_document(
    db: Session, *, page: dict, title: str, document_type, work_field, tech_tags,
    project_names, status, priority, owner, memo, now: datetime, author_name: str = "",
    creator: User | None = None,
) -> DocumentCache:
    """방금 생성한 문서를 캐시에 즉시 반영해 목록에 바로 뜨게 한다. 신규 택소노미는 사용자가
    고른 값을 저장하고 classification_manual=True 로 둬 이후 sync가 덮어쓰지 않게 한다.

    ## 소속은 **생성 Context** 가 정한다 (0060 §9)

    포털에서 만든 문서는 만든 사람이 지금 있는 자리의 것이다 — 부서가 있으면 그 부서,
    없으면 조직 공통. 이것은 "작성자의 부서를 실시간으로 따라간다"(§6이 금지한 것)와
    다르다: **만들 때 한 번** 정하고 그 뒤로는 작성자가 어디로 옮기든 움직이지 않는다.

    소속을 안 정하면 그 문서는 만든 사람에게조차 안 보인다(fail-closed) — 방금 만든 것이
    사라지는 화면은 보안이 아니라 고장이다.
    """
    pid = page.get("id")
    row = repository.get_by_page_id(db, pid) or DocumentCache(notion_page_id=pid)
    # ⚠️ 새 행은 아직 flush 전이라 `owner_kind` 가 **None** 이다(컬럼 기본값은 flush 때
    # 붙는다). `== OWNER_UNSET` 만 보면 새로 만든 문서가 항상 미지정으로 남는다.
    if creator is not None and (row.owner_kind or ownership.OWNER_UNSET) == ownership.OWNER_UNSET:
        if creator.department_id:
            row.owner_kind = ownership.OWNER_DEPARTMENT
            row.owner_dept_id = creator.department_id
        else:
            row.owner_kind = ownership.OWNER_ORGANIZATION
    row.url = page.get("url")
    row.title = title
    row.type_names = ""
    row.category_names = ""
    row.project_names = join_names(project_names)
    row.document_type = document_type or "기타"
    row.work_field = work_field or "기타"
    row.tech_tags = join_names(tech_tags)
    row.classification_manual = True
    row.status = status
    row.priority = priority
    row.owner = owner or ""
    row.memo = memo or ""
    row.author_names = join_names([author_name]) if author_name else ""
    row.last_edited = page.get("last_edited_time")
    row.created_time = page.get("created_time")
    row.original_url = None
    row.source_url = None
    row.has_files = False
    row.notion_favorite = False
    row.archived = False
    row.synced_at = now
    db.add(row)
    db.flush()
    return row


def recent_documents(db: Session, user_id: str, *, limit: int = 10, viewer: User | None = None) -> list:
    """최근 열람 순으로 캐시 문서를 돌려준다(캐시에 없는 오래된 항목은 건너뛴다).

    `viewer` 로 범위 판정을 지난다(`doc_in_scope`) — 이 함수를 만들 때는 빠져 있었다. 목록은
    범위 밖 문서를 걸러도, "최근 열람"은 **본인이 예전에 본** 문서를 그대로 다시 보여 주는
    별도 경로라 같이 안 막으면 새는 문이 하나 더 생긴다: 부서가 바뀌었거나(범위 밖이 됨)
    문서가 나중에 `restricted` 로 바뀌어도, 예전에 한 번 열어 본 사람에게는 이 목록을 통해
    계속 보인다 — SEC-10 제한 기능 자체를 우회하는 구멍이라 여기서 함께 닫는다.
    """
    views = repository.recent_views(db, user_id, limit=limit)
    ctx = doc_scope_context(db, viewer) if viewer is not None else None
    out = []
    for v in views:
        doc = repository.get_by_page_id(db, v.notion_page_id)
        if doc is not None and doc_in_scope(db, doc, viewer, ctx=ctx):
            out.append(doc)
    return out


# ── 본문 편집 (사용자 지적 #9) ────────────────────────────────────────────────
#
# 사용자 보고는 "문서 편집이 정상적으로 동작하지 않는다" 였지만 확인해 보니 **편집 기능이
# 아예 없었다.** 상세는 Notion 미러를 읽기만 했다.
#
# 배관은 티켓 본문이 이미 갖고 있다(`app/tickets/service.py::save_ticket_body`). 새로 만들지
# 않고 그대로 따른다: 지문은 내용 해시(`body_version`), 저장은 정본 먼저 → 소스 push,
# push 실패는 오류가 아니라 `synced=False`. 그래서 아래 함수들은 티켓 것을 **import 해서**
# 쓴다 - 같은 규칙을 두 벌 적으면 한쪽만 고치는 날 조용히 갈라진다.


def ensure_doc_not_trashed(db: Session, page_id: str) -> None:
    """휴지통에 있는 문서는 **없는 것으로 취급한다** (H2).

    지운 문서가 계속 편집되면, 그렇게 고친 글은 보관기간이 끝날 때 문서와 함께 사라진다.
    사용자에게는 "지웠는데 아직 고쳐지고, 고친 것이 나중에 사라지는" 상태다.

    **403 이 아니라 404** 다. 403 은 "있지만 당신은 안 된다" 라서 존재를 알려 준다
    (`app/tickets/service.py::ensure_not_trashed` 와 같은 판단).
    """
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    if page_id in trash_repo.trashed_page_ids(db, TRASH_DOCUMENT):
        raise NotFoundError("문서를 찾을 수 없습니다.")


def editor_body(doc: DocumentCache, blocks, blocks_error) -> str | None:
    """편집기 초기값. 우리 정본이 있으면 그것, 없으면 방금 읽은 원본을 되읽은 마크다운.

    본문을 못 읽었으면 **None** 이다 - 모르는 것을 빈 문자열로 내려보내면 편집기가 빈 칸으로
    열리고 거기서의 저장이 곧 본문 삭제가 된다. 화면은 이 값이 None 이면 편집을 막는다.
    """
    from app.core.notion_blocks import rendered_to_markdown

    if doc.body_markdown is not None:
        return doc.body_markdown
    if blocks_error is not None or blocks is None:
        return None
    return rendered_to_markdown(blocks)


def body_view(doc: DocumentCache, blocks, blocks_error) -> dict:
    """상세 응답의 본문 편집 관련 부분. 티켓 상세와 **같은 키 이름**을 쓴다.

    이름을 맞추는 것이 취향 문제가 아닌 이유: 두 화면이 같은 렌더러(DocBody)와 같은 편집기
    (BodyEditor)를 공유한다. 키가 갈라지면 화면 코드도 갈라지고, 한쪽에서 고친 버그가
    다른 쪽에 남는다.
    """
    text = editor_body(doc, blocks, blocks_error)
    return {
        "body_markdown": text,
        # 편집을 시작한 시점의 지문. 저장할 때 그대로 돌려보내면 그 사이 누가 먼저 저장한
        # 경우 409 로 막힌다.
        "body_version": _body_version(text),
        # 위 본문이 **우리 정본**인가, 아니면 원본에서 되읽은 근사치인가. 근사치를 저장하면
        # 굵게, 링크 같은 인라인 서식이 사라지고 글자만 남는다 - 그때만 경고하려면 필요하다.
        "body_is_local": doc.body_markdown is not None,
        # 정본은 저장됐는데 원본에 못 밀어 넣은 상태면 그 이유.
        "body_sync_error": doc.body_sync_error,
    }


def _body_version(text: str | None) -> str:
    """내용 해시. 정의는 티켓 것을 그대로 쓴다 - 왜 타임스탬프가 아닌지도 거기 적혀 있다."""
    from app.tickets.service import body_version

    return body_version(text)


def _ensure_body_not_changed(db: Session, *, doc: DocumentCache, base_version: str | None) -> None:
    """그 사이 누가 먼저 저장했으면 막는다.

    문서는 **범위 안이면 누구나 편집한다**(아래 `save_document_body` 참조). 그래서 두 사람이
    동시에 본문을 쓰면 나중 사람이 앞사람 글을 통째로 지우고 **양쪽 다 성공 토스트를 본다.**
    사람이 이미 한 일을 파괴하는 부류라 그 어떤 성능 문제보다 아프다.

    `base_version` 이 없으면(구버전 클라이언트, CLI) 예전대로 덮어쓴다 - 새 계약을 강제해
    기존 경로를 깨뜨리지 않는다.

    ## 아직 정본이 없는 문서는 통과시킨다

    `body_markdown` 이 NULL 이면 포털에서 저장된 적이 없다는 뜻이고, 그때 클라이언트가 든
    지문은 **원본에서 되읽은 근사치의 해시**다. 여기서 그걸 NULL 의 해시와 비교하면 본문이
    있는 문서는 **첫 저장이 늘 409** 가 된다 - 잠금이 아니라 편집 금지다.
    (티켓 쪽은 본문이 빈 티켓만 시험해서 이 자리가 드러나지 않았다.)

    그래도 잠금은 성립한다: 앞사람 저장이 정본을 만들어 놓기 때문에 **뒷사람은 위 비교에
    걸린다.** 잃는 것은 '둘 다 첫 저장' 인 순간의 충돌 하나뿐이고, 그건 우리가 관찰할 근거
    자체가 없는(원본을 다시 읽어야 아는) 상태다.
    """
    if not base_version or doc.body_markdown is None:
        return
    if _body_version(doc.body_markdown) != base_version:
        from app.core.errors import ConflictError

        raise ConflictError(
            "다른 사람이 먼저 저장했습니다. 새로고침해 최신 내용을 확인한 뒤 다시 저장해 주세요."
        )


def save_document_body(
    db: Session, *, repo, user: User, page_id: str, body_markdown: str,
    now: datetime, base_version: str | None = None,
) -> dict:
    """문서 본문을 저장한다(정본 먼저, 그다음 원본 push).

    ## 편집은 **범위**로만 막는다 - 삭제와 다른 축이다

    삭제는 작성자, 운영자만이다(`ensure_can_delete_doc`). 편집을 같은 선으로 좁히면 문서가
    위키가 아니라 개인 메모가 된다: 회의록의 오타를 참석자가 못 고치고, 무엇보다
    `author_notion_ids` 가 아직 대부분 비어 있어서(다음 동기화가 채운다) **지금은 사실상
    아무도 문서를 못 고치는 상태**가 된다. 되돌릴 수 없는 삭제와 달리 편집은 감사 로그에
    남고 원본에도 이력이 남는다.

    막는 축은 범위다. 목록, 상세, 휴지통 이동이 지나는 **그 함수**(`get_doc_in_scope`)를
    그대로 지난다 - 여기서 조건을 새로 적으면 판정이 두 벌이 되고, 한쪽만 고치는 날
    조용히 갈라진다. 범위 밖은 403 이 아니라 **404** 다.

    ## push 실패를 삼키지 않는다

    저장 순서(정본 먼저 → 원본 push)는 저장소 구현체가 지킨다. 여기서 중요한 것은 push
    실패를 **오류로 바꾸지 않는 것**이다 - 오류로 던지면 요청 트랜잭션이 롤백되어 방금
    저장한 사용자 텍스트까지 사라지고, 순서를 지킨 의미가 없어진다. 대신 `synced=False` 와
    이유를 응답에 실어 화면이 "저장됨, 원본 반영 실패" 를 말하게 한다.
    """
    ensure_doc_not_trashed(db, page_id)   # H2 - 휴지통 항목은 없는 것으로 본다
    doc = _doc_or_404(db, page_id, user)  # 범위 밖은 404 (§0-A)
    _ensure_body_not_changed(db, doc=doc, base_version=base_version)
    result = repo.save_body(db, page_id=page_id, body_markdown=body_markdown, now=now)
    return {
        "body_markdown": result.body_markdown,
        "body_version": _body_version(result.body_markdown),
        "body_is_local": True,
        "synced": result.synced,
        "body_sync_error": result.sync_error,
    }


# ── 댓글 ──────────────────────────────────────────────────────────────────────
#
# URL 은 page_id(딥링크 키)로 받고 저장도 page_id 로 한다 -- 왜 티켓과 다른지는
# `models.py::DocumentComment` 에 적어 뒀다(한 회차 prune 에 댓글이 딸려 나가지 않게).
# 응답은 늘 **목록 전체**다: 삭제, 수정 뒤에 클라이언트가 자기 목록을 직접 기워 맞추면
# 툼스톤 규약이 두 곳(서버, 클라)에 생겨 언젠가 갈라진다.
#
# 그 "응답은 늘 목록 전체" 때문에 **쓰기 경로의 범위 판정이 곧 조회 판정이기도 하다**:
# 판정 없이 삭제를 한 번 던지면 그 문서의 댓글 전체가 응답으로 돌아온다(지운 댓글만
# 툼스톤이고 나머지는 본문 그대로다). 그래서 아래 네 함수가 전부 `get_doc_in_scope`
# 한 곳을 지난다 -- 티켓 댓글에서 정확히 이 자리가 뚫려 있었다.


def _doc_or_404(db: Session, page_id: str, me: User) -> DocumentCache:
    """범위 안에서 문서 하나. 범위 밖은 **없는 문서와 똑같은 404** 다(저장소 규칙).

    403 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 준다 -- 그걸 세면 남의 부서 문서의
    존재를 열거할 수 있다. 문구도 없는 문서와 같아야 한다.

    휴지통 판정(H2)도 여기서 같이 본다 -- 네 댓글 함수(list/add/edit/delete)가 전부 이
    함수 하나를 지나므로, 여기 한 번이면 네 곳 모두 지운 문서를 없는 것으로 본다. 따로따로
    적으면 한 곳만 고치는 날 조용히 갈라진다(save_document_body 가 이미 그 갈라짐이었다 --
    본문 저장만 ensure_doc_not_trashed 를 부르고 댓글은 안 불렀다).
    """
    ensure_doc_not_trashed(db, page_id)
    doc = get_doc_in_scope(db, page_id, me)
    if doc is None:
        raise NotFoundError("문서를 찾을 수 없습니다.")
    return doc


def list_document_comments(db: Session, *, page_id: str, me: User) -> dict:
    # 상세와 **같은 규칙**이어야 한다. 상세만 막고 댓글을 열어 두면 id 하나로 논의 전체가
    # 새는데, 그건 상세가 새는 것과 다르지 않다.
    _doc_or_404(db, page_id, me)
    return doc_comments.list_comments(db, page_id=page_id, me=me)


def add_document_comment(
    db: Session, *, page_id: str, me: User, body: str, now: datetime
) -> dict:
    doc = _doc_or_404(db, page_id, me)
    created = doc_comments.create_comment(
        db, page_id=page_id, document_id=doc.id, author=me, body=body, now=now
    )
    _notify_document_comment(db, doc=doc, author=me, now=now)
    return {
        "comment_id": created.id,
        **doc_comments.list_comments(db, page_id=page_id, me=me),
    }


def _notify_document_comment(db: Session, *, doc: DocumentCache, author: User, now) -> None:
    """내 문서에 댓글이 달리면 알린다 (티켓 댓글의 `_notify_ticket_comment` 와 같은 규약).

    ## 누구에게

    문서 작성자 전원(작성자 본인은 뺀다 -- 내가 쓴 것을 나에게 알리면 배지가 늘 켜져 있다).
    작성자를 앱 사용자로 해석하지 못하면 조용히 넘어간다. `author_notion_ids` 는 **다음
    동기화가** 채우므로 지금은 비어 있는 문서가 많고, 그건 정상 상태다 -- 알림 하나 때문에
    댓글 저장을 실패시키지 않는다.

    ## 실패해도 댓글은 남는다

    `notify_user` 가 터져도 이 함수 밖으로 나가지 않는다. 알림은 본 작업(댓글)보다 약한
    관심사이고, 그 반대로 만들면 알림 표 하나가 협업을 멈춘다.
    """
    try:
        from app.tickets.service import _verified_id_to_user

        id_to_user = _verified_id_to_user(db)
        targets = {
            id_to_user.get(n)
            for n in split_names(doc.author_notion_ids or "")
            if id_to_user.get(n)
        }
        targets.discard(author.id)
        if not targets:
            return

        from app.notifications.service import notify_user

        for uid_ in targets:
            notify_user(
                db, uid_, type_="document_comment",
                title=f"문서에 새 댓글: {author.display_name}",
                body=(doc.title or "")[:200],
                related=("document", doc.notion_page_id), now=now,
            )
    except Exception:  # noqa: BLE001 -- 알림이 댓글 저장을 막으면 안 된다
        logger.exception("문서 댓글 알림에 실패했다 (page_id=%s)", doc.notion_page_id)


def edit_document_comment(
    db: Session, *, comment_id: str, body: str, me: User, now: datetime
) -> dict:
    # 범위 판정이 권한 판정보다 **먼저**다. 순서가 뒤집히면 범위 밖 댓글에 403 이 나가고,
    # 403 은 "그 id 는 존재한다"를 알려 준다.
    comment = doc_comments.get_or_404(db, comment_id)
    _doc_or_404(db, comment.notion_page_id, me)
    doc_comments.ensure_can_edit(comment, me)
    doc_comments.update_comment(db, comment, body=body, now=now)
    return doc_comments.list_comments(db, page_id=comment.notion_page_id, me=me)


def delete_document_comment(
    db: Session, *, comment_id: str, me: User, now: datetime
) -> dict:
    # 범위 밖은 404 -- 모더레이션 권한(운영자, 관리자)은 **자기 범위 안에서만** 있다.
    comment = doc_comments.get_or_404(db, comment_id)
    _doc_or_404(db, comment.notion_page_id, me)
    doc_comments.ensure_can_delete(comment, me)
    doc_comments.soft_delete_comment(db, comment, now=now)
    return doc_comments.list_comments(db, page_id=comment.notion_page_id, me=me)
