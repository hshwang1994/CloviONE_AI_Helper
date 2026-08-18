"""Document automation API (spec §19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.observability.service import EVENT_DOCUMENT_GENERATE, record_usage
from app.quotas import service as ai_quotas
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.pagination import PageParams
from app.core.scope import Principal, visible_user_ids
from app.documents.models import DocumentGeneration
from app.documents.repository import apply_scope
from app.documents.service import (
    generation_view,
    get_generation_or_404,
    request_generation,
    retry_generation,
)

router = APIRouter(
    prefix="/api/admin/documents",
    tags=["admin-documents"],
    dependencies=[Depends(require_csrf)],
)



class GenerateRequest(BaseModel):
    workflow_id: str
    mode: str = "preview_then_approve"
    period: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def _config_default(cls, v):
        # 관리자 콘솔의 빈 JSON 입력은 null로 온다 — 선택 필드이므로 빈 객체로 본다(round16 스윕 B2).
        return {} if v is None else v


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_generations(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=24),
    principal: Principal = Depends(get_principal),
):
    stmt = select(DocumentGeneration)
    # 범위 밖 사람이 요청한 이력은 안 보인다 (§0-A). 이 목록은 아래에서 요청자 id 를
    # **이름·이메일로 해석해** 붙이고, 각 행에는 요청 내용(config)이 실린다 — 훑는 것만으로
    # 남의 팀이 무엇을 어디에 쓰는지 읽는 것과 같다.
    #
    # 조건은 상세·재시도와 **같은 것 하나**다(`repository.scope_clause` — 요청자 없는
    # 시스템 생성을 남기는 이유도 거기 적혀 있다). 여기 손으로 다시 적으면 두 벌이 되고,
    # 한쪽만 고쳐진 상태의 증상은 "어떤 사람만 안 된다" 라서 찾기가 어렵다.
    stmt = apply_scope(stmt, visible_user_ids(db, principal.management))
    if status:
        stmt = stmt.where(DocumentGeneration.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(DocumentGeneration.created_at.desc(), DocumentGeneration.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    # 요청자(requested_by)는 지금껏 원시 UUID로만 내려가 운영/감사 화면에서 '누가
    # 요청했나'를 알 수 없었다 — 승인 화면과 같은 패턴으로 페이지의 요청자 id를 한 번에
    # 이름/이메일로 해석해(N+1 회피) 각 행에 붙인다(round30 감사 E).
    from app.approvals.service import resolve_names

    names = resolve_names(db, {r.requested_by for r in rows})

    def _with_requester(r: DocumentGeneration) -> dict:
        view = generation_view(r)
        info = names.get(r.requested_by or "")
        view["requested_by_name"] = info.get("display_name") if info else None
        view["requested_by_email"] = info.get("email") if info else None
        return view

    return {
        "items": [_with_requester(r) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.post("/generate", status_code=202, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def generate(request: Request, payload: GenerateRequest, db: Session = Depends(get_db)):
    # AI 쿼터(0033) — **요청을 큐에 넣기 전에** 본다. 넣은 뒤에 막으면 이미 러너 슬롯과
    # 토큰을 쓴 뒤라 상한의 뜻이 없다. 상한 행이 없으면 아무 제한도 없다(fail-open,
    # app/quotas/service.py::enforce 주석). 여기는 사람이 폼을 한 번 누르는 저빈도 지점이라
    # 0026 의 '뜨거운 경로 금지' 규칙에 걸리지 않는다.
    #
    # 확인과 기록을 **한 덩어리로** 묶는다 (Z15). 예전에는 `enforce()` 와 `record_call()`
    # 사이에 큐 적재와 감사 기록이 통째로 들어 있었고, 그 사이에 들어온 같은 사람의 다른
    # 요청이 같은 숫자를 읽어 둘 다 통과했다.
    with ai_quotas.consume(
        db,
        user_id=request.state.user.id,
        org_id=getattr(request.state.user, "org_id", None),
        # AI 쿼터가 세는 이벤트는 따로다 — 'document.generate'는 기능별 통계이고, 'ai.call'은
        # 비용 축이다. 한 이름으로 합치면 나중에 AI 를 쓰지 않는 생성 경로가 생겼을 때
        # 쿼터가 잘못 깎인다.
        kind=ai_quotas.KIND_DOCUMENT_GENERATE,
        now=request.app.state.clock.now(),
    ) as slot:
        # document_automation_enabled는 이제 관리 콘솔 Settings 화면에서 켜고 끌 수 있는
        # settings_cache 값이다(예전엔 서버 파일로만 존재해 화면에 노출되지 않았다).
        doc_automation_enabled = bool(
            request.app.state.settings_cache.current_value("document_automation_enabled")
        )
        gen = request_generation(
            db,
            workflow_id=payload.workflow_id,
            mode=payload.mode,
            config=payload.config,
            period=payload.period,
            requested_by=request.state.user.id,
            now=request.app.state.clock.now(),
            document_automation_enabled=doc_automation_enabled,
        )
        record_audit_from_request(
            request, db, action="document.generate_requested",
            object_type="document_generation", object_id=gen.id,
            after={"mode": gen.mode, "workflow_id": gen.workflow_id},
        )
        # 사용 통계(0026) — 저빈도 지점(문서 생성은 사람이 폼으로 한 번 누르는 행동이다).
        record_usage(
            db, event=EVENT_DOCUMENT_GENERATE, user_id=request.state.user.id,
            org_id=getattr(request.state.user, "org_id", None),
            object_type="document_generation", object_id=gen.id,
            now=request.app.state.clock.now(),
        )
        slot.record()
        # UB-08: 잠금이 풀리기 전에 커밋해야 한다 — 안 그러면 잠금이 풀린 뒤(이 with 블록이
        # 끝난 뒤) 같은 사용자의 다른 요청이 아직 안 보이는(커밋 전) 이 사용량을 못 보고
        # 상한을 통과할 수 있다(app/quotas/service.py의 consume 문서 참조).
        db.commit()
    return {"generation": generation_view(gen)}


@router.post(
    "/{generation_id}/retry",
    status_code=202,
    dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))],
)
def retry(
    request: Request,
    generation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 실패/품질 실패 행을 같은 레코드로 다시 큐에 넣는다 — 생성 폼 재오픈(같은 기간·대상
    # 새 생성 → idempotency 중복 409)의 막다른 길을 없앤다(round30 감사 E High).
    #
    # 범위 밖은 404 이고, 그 문은 **상태 검사보다 먼저** 지난다: 409("실패 또는 품질 실패
    # 상태의 문서만…")로 답하면 그 id 의 존재와 상태까지 알려 주기 때문이다. 여기서 새는
    # 것은 읽기가 아니라 **쓰기 실행**이다 — 러너를 다시 불러 남의 팀 문서를 다시 만든다.
    gen = get_generation_or_404(db, generation_id, visible_user_ids(db, principal.management))
    retry_generation(db, gen, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="document.retry_requested",
        object_type="document_generation", object_id=gen.id,
        after={"status": gen.status},
    )
    return {"generation": generation_view(gen)}


@router.get("/{generation_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_generation(
    generation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 목록과 같은 판정을 지난다 — 상세에는 요청자와 요청 내용(config)이 통째로 실린다.
    gen = get_generation_or_404(db, generation_id, visible_user_ids(db, principal.management))
    return {"generation": generation_view(gen)}
