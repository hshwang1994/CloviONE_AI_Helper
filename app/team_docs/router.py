"""팀 공간 > 문서 API (§17).

조회는 인증만, 상태변경(동기화·즐겨찾기)은 CSRF. 목록·상세 메타는 로컬 캐시에서 읽어
Notion 장애와 무관하게 응답한다(§17.4). 본문 블록만 상세 조회 때 실시간으로 읽고, 실패하면
메타는 보여주되 본문 자리에 '불러올 수 없음'을 표시한다(티켓 등 다른 기능엔 무영향).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dates import iso_date, iso_dt
from app.org import context as org_context
from app.core.audit import record_audit_from_request
from app.authz.visibility import context_for_user
from app.core.authz import MODERATOR_ROLES
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import AppError, NotFoundError
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams
from app.team_docs import service
from app.team_docs.models import split_names
from app.team_docs.schemas import DocumentBodyUpdate, DocumentCreate
from app.tickets.schemas import BulkPageIds  # 티켓·문서 공용 일괄 삭제 스키마
from app.users.models import User
from app.settings.gate import block_if_maintenance


def require_team_docs_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("team_docs_enabled", True):
        raise NotFoundError("문서 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/team-docs",
    tags=["team-docs"],
    dependencies=[Depends(require_team_docs_enabled), Depends(block_if_maintenance)],
)

# FN-41: 목록에서 부서 범위 필터링을 페이지 자르기 **전에** 하려면 검색/타입 등으로 이미
# 좁혀진 결과 전체를 한 번에 봐야 한다. 사고 방지용 상한 — 실제 문서 수(수백~두 자릿수
# 천 단위)를 넉넉히 웃돈다. 이 상한에 걸리면(사실상 발생 안 함) total/rows가 그 상한
# 이후 문서를 못 보는 근사가 되지만, 지금의 "일부 페이지만 보는 근사"보다는 훨씬 낫다.
_SCOPE_FILTER_FETCH_CAP = 5000


def _repo(request: Request):
    """앱 기동 때 배선된 문서 저장소(app.state.repositories.documents).

    소스(Notion) 왕복은 전부 이 구현체 뒤에 있다 — 라우터가 notion_docs 를 직접 부르면
    소스를 바꿀 때 고칠 곳이 화면 수만큼 늘어난다(경계 정적검사가 이걸 막는다).
    """
    return request.app.state.repositories.documents


def _doc_view(row, *, can_restrict: bool = False) -> dict:
    return {
        "id": row.notion_page_id,
        "title": row.title,
        "document_type": row.document_type,
        "work_field": row.work_field,
        "tech_tags": split_names(row.tech_tags),
        "projects": split_names(row.project_names),
        "status": row.status,
        "priority": row.priority,
        "owner": row.owner,
        "author_names": split_names(row.author_names),
        # 화면 계약은 ISO 문자열이다. 앞은 달력일, 뒤는 시각 (S7 · P-14a).
        "doc_date": iso_date(row.doc_date),
        "last_edited": iso_dt(row.last_edited),
        # `url`·`original_url`·`source_url` 은 여기 없다. 세 값 모두 app.notion.com 을
        # 가리키는데, 정본이 이 서버로 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상
        # 쓰지 않는 낡은 사본이다. 화면에 「원본 열기」로 내주면 오늘 고친 내용이 없는
        # 쪽으로 사용자를 보내는 셈이 된다(컬럼 자체는 이관 흔적으로 남겨 둔다).
        "has_files": row.has_files,
        # SEC-10: 이 문서가 이미 나온 이상(범위 판정을 지났다는 뜻) restricted 값 자체를 보여줘도
        # 안전하다 — 제한된 문서를 볼 수 있는 사람은 이미 운영자군이거나 작성자 본인뿐이다.
        "restricted": bool(row.restricted),
        "can_restrict": can_restrict,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
    }


@router.get("")
def list_documents(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    page: PageParams = Depends(),
    q: str | None = Query(default=None, max_length=200),
    doc_type: str | None = Query(default=None, max_length=32),
    work_field: str | None = Query(default=None, max_length=32),
    project: str | None = Query(default=None, max_length=120),
    tech: str | None = Query(default=None, max_length=40),
    # 부서 필터 (0060 §32). **내 조회 범위 안에서만** 동작한다 — 범위 밖 id 는 없는 부서와
    # 똑같이 404 다(`app/org/context.py`). 프런트 선택기만으로 막지 않는다.
    department_id: str | None = Query(default=None, max_length=36),
    sort: str = Query(default="recent"),
):
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    # FN-41: 예전엔 search/type/... 필터까지만 SQL에서 페이지를 자르고 부서 범위는 **그
    # 페이지 결과에만** 사후 적용했다 — 페이지 안에서 범위 밖 문서가 걸리면 total은 "이번
    # 페이지에서 걸러진 수"로만 보정되고(다른 페이지의 손실은 못 잡음), 화면은 "총 N건"
    # 페이저와 그보다 적은 항목을 동시에 보여줬다. 부서 범위를 SQL로 못 옮기는 이유는
    # author_notion_ids가 정규화된 조인 테이블이 아니라 구분자 문자열이라서다(스키마 변경
    # 없이는 안전한 SQL WHERE로 못 씀) — 대신 범위 필터링 **전체를 페이지 자르기 전에** 하도록
    # 순서를 뒤집는다. 이 회사 규모의 문서 수(수백~두 자릿수 천 단위, USE 집계 참고)에서
    # 한 번의 무제한 조회는 무리가 아니다 — 상한만 사고 방지용으로 넉넉히 둔다.
    all_matching, _raw_total = _repo(request).list_documents(
        db,
        search=q,
        doc_type_f=doc_type,
        work_field_f=work_field,
        project_f=project,
        tech_f=tech,
        sort=sort if sort in {"recent", "title"} else "recent",
        offset=0,
        limit=_SCOPE_FILTER_FETCH_CAP,
        exclude_page_ids=trash_repo.trashed_page_ids(db, TRASH_DOCUMENT),  # 휴지통 문서는 숨김
    )
    # 범위 밖 문서를 뺀다 (1순위 유출 #5). 판정은 문서 자신의 소속(0060)이고, 소속을 모르는
    # 문서는 전역 관리자만 본다 — `service.doc_in_scope` 에 이유가 있다.
    # 판정 재료(범위·볼 수 있는 프로젝트·내 매핑)를 한 번만 구해 문서마다 넘긴다(N+1 제거).
    ctx = context_for_user(db, me, scope=org_context.filter_scope(db, me, department_id))
    visible = [r for r in all_matching if service.doc_in_scope(db, r, me, ctx=ctx)]
    total = len(visible)  # 이제 필터링 뒤의 **진짜** 전체 개수다(일부 페이지 근사가 아니다).
    rows = visible[page.offset : page.offset + page.page_size]
    can_restrict = me.role in MODERATOR_ROLES
    return {
        "items": [_doc_view(r, can_restrict=can_restrict) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        # 고를 수 있는 부서는 **서버가** 계산해 준다. 프런트가 스스로 만들면 서버 검증과
        # 갈라지고, 갈라진 쪽이 넓으면 사용자는 404 만 보게 된다.
        "departments": {
            "selected": department_id,
            "options": org_context.department_options(db, me),
        },
    }


@router.post("", dependencies=[Depends(require_csrf)])
def create_document(
    request: Request,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Notion "문서" DB에 새 문서를 생성한다(제목·유형/카테고리/프로젝트·상태·소유자·메모·본문).
    주의: 이 DB가 원본에서 재생성되는 복사본이면 생성분이 덮일 수 있다(운영 데이터소스 구성에 의존)."""
    now = request.app.state.clock.now()

    from app.tickets.service import my_notion_id

    # 프로젝트만 소스 관계로 기록. 문서 종류·업무 분야·기술 태그는 앱측(신규 택소노미)이다.
    project_names = [payload.project] if payload.project else []
    # 작성자 자동 채움: 로그인 사용자의 매핑이 있으면 소스 작성자(person)로도 기록하고,
    # 앱 캐시엔 항상 만든 사람 이름을 넣어 목록에 작성자가 바로 뜨게 한다.
    page = _repo(request).create(
        db, title=payload.title, status=payload.status, priority=payload.priority,
        owner=payload.owner, memo=payload.memo, body=payload.body,
        project_names=project_names, author_id=my_notion_id(db, me),
    )

    row = service.cache_created_document(
        db, page=page, title=payload.title,
        document_type=payload.document_type, work_field=payload.work_field,
        tech_tags=payload.tech_tags, project_names=project_names,
        status=payload.status, priority=payload.priority, owner=payload.owner,
        memo=payload.memo, author_name=me.display_name, now=now,
        # 생성 Context 가 소속을 정한다(0060 §9) — 안 정하면 방금 만든 문서가
        # 만든 사람에게조차 안 보인다.
        creator=me,
    )
    record_audit_from_request(
        request, db, action="team_docs.create", object_type="notion_document",
        object_id=row.notion_page_id, after={"title": payload.title},
    )
    return {"document": _doc_view(row, can_restrict=me.role in MODERATOR_ROLES)}


@router.get("/filters")
def get_filters(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """필터 드롭다운. 옵션도 목록과 **같은 범위 판정**을 지난다.

    목록만 좁혀 놓으면 가린 문서의 프로젝트 코드명이 드롭다운으로 새어 나간다 — 이유는
    `service.filter_options` 에 적어 뒀다. 행위자를 넘기는 것이 이 저장소의 관용이고,
    인자가 없던 시절이 정확히 그 결함 상태였다.

    「최근 열람」은 여기 없다. 그 축은 정본 문서로 옮겨 갔다 (S14 · C2 —
    `app/knowledge/recent_views.py`).
    """
    return service.filter_options(db, me)


@router.get("/projects")
def all_projects(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """생성 폼용 전체 프로젝트 목록(Notion 기준). Notion 장애 시 캐시 기반 프로젝트로 폴백한다
    (이 엔드포인트만 영향받고 목록/상세는 캐시로 계속 동작 — §17.4 격리)."""
    # 캐시 폴백은 `filter_options` 를 그대로 쓰므로 목록과 같은 범위 판정을 지난다.
    # (소스 조회 쪽은 Notion 의 프로젝트 DB 전체라 이 판정이 닿지 않는다 — 별개 축이다.)
    try:
        names = _repo(request).project_names(db)
    except AppError:
        names = service.filter_options(db, me)["projects"]
    if not names:
        names = service.filter_options(db, me)["projects"]
    return {"projects": names}


@router.post("/trash-bulk", dependencies=[Depends(require_csrf)])
def trash_documents_bulk(
    request: Request,
    payload: BulkPageIds,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """문서 여러 건을 한 번에 휴지통으로(목록 다중선택). 건별 권한 검사, 부분 성공.
    (리터럴 경로라 아래 GET /{page_id} 보다 먼저 선언.)"""
    result = service.trash_documents_bulk(db, user=me, page_ids=payload.page_ids, now=request.app.state.clock.now())
    for it in result["trashed"]:
        record_audit_from_request(request, db, action="team_docs.trash", object_type="notion_document",
                                  object_id=it["id"], before={"title": it.get("title")})
    return {"ok": True, **result}


# ── 댓글은 여기 없다 (S14 · C2) ───────────────────────────────────────────────
#
# 문서 댓글의 축은 정본 문서(`documents`)로 옮겼다 — `app/knowledge/router.py` 가 
# `/api/knowledge/documents/{document_id}/comments` 로 답한다. 같은 자원의 같은 축이
# 두 주소에 있으면, 한쪽에 쓴 글이 다른 쪽에서 안 보인다.


@router.get("/{page_id}")
def get_document(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # 휴지통 문서는 상세로도 없는 것으로 본다(H2, 티켓과 같은 규칙 —
    # service.ensure_doc_not_trashed 주석 참고). 목록만 걸러 두면 지운 문서가 계속
    # 상세로 열리고, 그 상태로 계속 즐겨찾기·댓글이 쌓이다가 보관기간이 끝나면 함께 사라진다.
    service.ensure_doc_not_trashed(db, page_id)
    row = _repo(request).get(db, page_id=page_id)
    if row is None:
        raise NotFoundError("문서를 찾을 수 없습니다. 동기화가 필요할 수 있습니다.")
    # 목록에서 가린 것이 단건에서 새면 가린 의미가 없다. **403 이 아니라 404** (저장소 규칙).
    if not service.doc_in_scope(db, row, me):
        raise NotFoundError("문서를 찾을 수 없습니다.")
    # 본문 블록은 실시간 — Notion 장애면 메타만 보여주고 본문은 null(§17.4 격리).
    blocks = None
    blocks_error = None
    try:
        blocks = _repo(request).body_blocks(db, page_id=page_id)
    except AppError as exc:
        blocks_error = exc.message
    except Exception:
        blocks_error = "본문을 불러오지 못했습니다."
    return {
        "document": _doc_view(row, can_restrict=me.role in MODERATOR_ROLES),
        "blocks": blocks,
        "blocks_error": blocks_error,
        # 편집기를 여는 데 쓰는 마크다운과 그 지문(사용자 지적 #9). 이걸 안 주면 프런트가
        # 마크다운 변환기를 한 벌 더 갖거나, 편집기가 빈 채로 열려 '저장'이 본문 삭제가 된다.
        **service.body_view(row, blocks, blocks_error),
    }


@router.put("/{page_id}/body", dependencies=[Depends(require_csrf)])
def save_document_body(
    request: Request,
    page_id: str,
    payload: DocumentBodyUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """문서 본문 저장. 쓸 곳은 이 서버의 문서 표 하나다.

    예전에는 정본을 먼저 쓰고 그다음 원본(Notion)에 밀어 넣었고, 그 push 가 실패하면
    `synced: false` 와 이유를 함께 돌려줬다. 밀어 넣을 원본이 없어졌으므로 그 갈래도
    없어졌다 — 언제나 참인 필드를 계속 실으면 화면이 그것을 보고 없는 실패 상태를 되살린다.

    범위 판정은 목록, 상세가 쓰는 것과 같은 함수이고 `service.save_document_body` 안에 있다.
    """
    result = service.save_document_body(
        db, repo=_repo(request), user=me, page_id=page_id,
        body_markdown=payload.body_markdown,
        now=request.app.state.clock.now(),
        base_version=payload.base_version,   # 낙관적 잠금
    )
    record_audit_from_request(
        request, db, action="team_docs.body.update", object_type="notion_document",
        object_id=page_id, after={"body_version": result["body_version"]},
    )
    return {"ok": True, **result}


@router.post("/{page_id}/trash", dependencies=[Depends(require_csrf)])
def trash_document(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """문서를 휴지통으로 보낸다(노션 원본은 보관기간 뒤 보관처리).

    범위 안에서, 작성자/운영자만 + 감사. 범위 판정은 목록이 쓰는 것과 같은 함수이고
    `service.trash_document` 안에 있다 — 여기서 한 번 더 적으면 두 벌이 된다.
    """
    result = service.trash_document(db, user=me, page_id=page_id, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="team_docs.trash", object_type="notion_document",
        object_id=page_id, before={"title": result["title"]},
    )
    return {"ok": True}


@router.post("/{page_id}/restrict", dependencies=[Depends(require_csrf)])
def set_restricted(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    on: bool = Query(default=True),
):
    """문서 열람 제한 토글(SEC-10) — 운영자만. 켜면 운영자군/작성자 본인 외에는 목록·상세
    어디서도 이 문서가 보이지 않는다(`service.doc_in_scope`). 원본 Notion 콘텐츠는 그대로다 —
    이 앱이 할 수 있는 것은 열람 범위 축소뿐이라는 SEC-10 기록과 일치한다."""
    doc = service.set_doc_restricted(db, user=me, page_id=page_id, restricted=on)
    record_audit_from_request(
        request, db, action="team_docs.restrict", object_type="notion_document",
        object_id=page_id, after={"restricted": doc.restricted},
    )
    return {"ok": True, "restricted": doc.restricted}


class AllowedUsersRequest(BaseModel):
    """열람 제한 문서를 명시로 볼 수 있는 사람들. **전체 명단**을 보낸다(부분 추가가 아니다).

    부분 추가/삭제 API 로 만들면 화면이 "지금 명단" 을 스스로 재구성해야 하고, 두 사람이
    동시에 고치면 어느 쪽도 의도한 결과가 아니게 된다. 명단 전체를 보내면 마지막에 저장한
    사람의 의도가 그대로 남는다.
    """

    user_ids: list[str] = Field(default_factory=list, max_length=200)


@router.get("/{page_id}/allowed-users")
def list_allowed_users(
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """이 문서를 명시로 볼 수 있는 사람들 (S5 · D-193).

    범위 밖 문서는 **404** — 목록에서 가린 문서에 대해 "누가 볼 수 있는가" 를 답하면 그
    자체가 정보다.
    """
    return {"user_ids": service.doc_allowed_users(db, user=me, page_id=page_id)}


@router.put("/{page_id}/allowed-users", dependencies=[Depends(require_csrf)])
def set_allowed_users(
    request: Request,
    page_id: str,
    payload: AllowedUsersRequest,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """열람 제한 문서의 명시 열람자 명단을 통째로 바꾼다 — 운영자만.

    `restricted` 를 켜는 것과 **같은 권한**이다. 제한을 걸 수 있는 사람이 그 예외도 정한다 —
    둘을 다른 권한으로 나누면 "제한은 걸었는데 아무도 못 여는" 상태를 만든 사람이 그것을
    풀 수 없다.
    """
    user_ids = service.set_doc_allowed_users(
        db, user=me, page_id=page_id, user_ids=payload.user_ids
    )
    record_audit_from_request(
        request, db, action="team_docs.allowed_users", object_type="notion_document",
        object_id=page_id, after={"user_ids": user_ids},
    )
    return {"ok": True, "user_ids": user_ids}
