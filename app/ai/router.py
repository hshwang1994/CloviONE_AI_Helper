"""AI 작업공간 API — 검색 · 질의 · 문서 초안 (S10).

## 권한을 두 겹으로 묻는다

게이트(`AI_USE`)는 **무엇을 할 수 있는가**에 답하고, Retrieval 의
`effective_visibility_clause` 는 **어느 것에 할 수 있는가**에 답한다(D-194). 게이트만
걸고 범위를 안 걸면 AI 를 쓸 수 있는 사람이 남의 부서 문서를 근거로 답을 받는다.

라우터는 범위 판정을 **하지 않는다.** 그것을 여기서 다시 적으면 판정이 두 벌이 되고,
갈라지는 방향 하나는 유출이다(D-202 · D-256).

## 검색과 질의를 나눈 이유

`/search` 는 모델을 안 부르고 `/ask` 는 부른다. 한 엔드포인트로 합치면 「생성이 막혀
있어도 검색과 인용은 계속 동작한다」를 화면이 증명할 수 없다 — 그것이 S10 의 Exit
조건 하나다. 그리고 검색은 쿼터를 안 쓴다: 거기서 도는 임베딩은 서버 CPU 이지 구독
호출이 아니다(D-200).

## 초안은 문서를 **만들고 나서** 돌려준다

「초안 글자만 돌려주고 저장은 화면이」로 두면 모델이 만든 글이 어디에도 안 남는
경로가 생긴다 — 그 요청은 쿼터를 썼는데 결과가 없다. 여기서 `source_type=AI` 로 문서를
만들고 그 id 를 준다. 사람이 편집기에서 고치는 것은 그다음이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.ai.gateway import contract, registry
from app.ai.index import service as index_service
from app.ai.retrieval import answer as answer_mod
from app.ai.retrieval import service as retrieval_service
from app.ai.schemas import AskRequest, DraftRequest
from app.authz import permissions as perms
from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_permission
from app.knowledge import blocks
from app.knowledge import service as knowledge_service
from app.knowledge.models import SOURCE_AI
from app.quotas import service as ai_quotas
from app.search.query import MAX_QUERY_CHARS
from app.settings.gate import block_if_maintenance
from app.users.models import User

router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(block_if_maintenance)],
)


def _gateway(request: Request) -> contract.Gateway:
    """프로세스에 하나뿐인 Gateway (`app/main.py`).

    요청마다 만들면 그때마다 새 Adapter 가 생기고, 임베딩 Adapter 는 첫 호출에 ONNX
    세션을 만든다 — S1 실측 2.3초다. 그 시간을 질의마다 다시 내면 이 화면은 쓸 수 없다.

    폴백을 두는 이유: 시험이 `create_app` 을 안 거치고 라우터만 올리는 경우가 있고,
    거기서 `AttributeError` 로 죽으면 제품 결함처럼 보인다.
    """
    gateway = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        gateway = registry.build_gateway(getattr(request.app.state, "settings", None))
        request.app.state.ai_gateway = gateway
    return gateway


@router.get("/status")
def ai_status(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(perms.AI_USE)),
) -> dict:
    """지금 무엇이 되고 무엇이 안 되는가. **화면이 미리 안내를 고르는 자리다.**

    「안 됩니다」만 말하지 않는다 — 운영자가 고칠 수 있는 것(모델 파일을 안 넣었다)과
    못 고치는 것(어댑터가 없다)이 다른 상태이고, 그 구별을 `capabilities()` 가 든다.
    """
    caps = _gateway(request).capabilities()
    body: dict = {"capabilities": caps.as_dict()}
    try:
        health = index_service.index_health(db)
    except Exception:  # noqa: BLE001 - 표가 아직 없는 설치도 있다
        # 「못 셌다」를 0 으로 적지 않는다. 0 은 「없다」이고 그 둘은 다른 사실이다.
        body["index"] = None
    else:
        body["index"] = {
            "chunks": health["chunks"],
            "embedded": health["embedded"],
            "pending_embedding": health["pending_embedding"],
            "documents": health["documents"],
        }
    return body


@router.get("/search")
def ai_search(
    request: Request,
    q: str = Query("", max_length=MAX_QUERY_CHARS * 4, description="찾을 말"),
    limit: int = Query(
        retrieval_service.TOP_K, ge=1, le=retrieval_service.MAX_TOP_K
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(perms.AI_USE)),
) -> dict:
    """근거 문서만. **모델을 안 부른다** — 생성이 막혀 있어도 이 경로는 그대로 답한다."""
    result = retrieval_service.retrieve(
        db, user, raw_query=q, gateway=_gateway(request), top_k=limit
    )
    return result.as_dict()


@router.post("/ask", dependencies=[Depends(require_csrf)])
def ai_ask(
    payload: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(perms.AI_USE)),
) -> dict:
    """질문 → 근거 + 답변. 근거는 언제나 나가고 답변은 될 때만 나간다.

    쿼터는 **모델을 부르기 전에** 본다. 부른 뒤에 막으면 이미 구독 호출을 쓴 뒤라 상한의
    뜻이 없다. 그리고 성공한 호출만 센다(`record()`) — 모델이 죽은 날 사용자가 답을 못
    받고 상한만 잃으면 안 된다.
    """
    now = request.app.state.clock.now()
    with ai_quotas.consume(
        db,
        user_id=user.id,
        org_id=getattr(user, "org_id", None),
        kind=ai_quotas.KIND_AI_ASK,
        now=now,
    ) as slot:
        result = answer_mod.answer(
            db, user,
            raw_query=payload.question,
            gateway=_gateway(request),
            top_k=payload.top_k or retrieval_service.TOP_K,
        )
        if result.ok:
            slot.record()
            # ⚠️ 잠금 안에서 커밋해야 뜻이 있다(UB-08). 잠금을 놓은 뒤에 커밋하면 그
            # 사이에 들어온 같은 사람의 요청이 방금 쓴 사용량을 못 보고 통과한다.
            db.commit()
    return result.as_dict()


@router.post("/documents", dependencies=[Depends(require_csrf)])
def ai_draft_document(
    payload: DraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(perms.AI_USE)),
) -> dict:
    """근거를 모아 문서 초안을 만들고 **`source_type=AI` 로 저장한다.**

    문서 생성 권한을 따로 묻는다. `AI_USE` 는 「AI 를 쓸 수 있다」이고 문서를 만드는
    것은 다른 일이다 — 합치면 AI 만 쓸 수 있게 해 둔 사람이 문서를 만들게 된다.
    """
    _require_document_create(db, user)

    now = request.app.state.clock.now()
    with ai_quotas.consume(
        db,
        user_id=user.id,
        org_id=getattr(user, "org_id", None),
        kind=ai_quotas.KIND_AI_DRAFT,
        now=now,
    ) as slot:
        result = answer_mod.draft_document(
            db, user,
            instruction=payload.instruction,
            gateway=_gateway(request),
            top_k=payload.top_k or retrieval_service.TOP_K,
        )
        if not result.ok:
            # 초안을 못 만들었으면 **문서를 만들지 않는다.** 빈 문서를 남기면 목록에
            # 제목만 있는 껍데기가 쌓이고, 사람은 그것이 실패의 흔적인 줄 모른다.
            return {**result.as_dict(), "document": None}
        document = knowledge_service.create_document(
            db, user,
            space_id=payload.space_id,
            folder_id=payload.folder_id,
            title=payload.title,
            body=blocks.from_plain_text(result.text or ""),
            source_type=SOURCE_AI,
        )
        record_audit_from_request(
            request, db, action="ai.document.drafted",
            object_type="knowledge_document", object_id=document.id,
            after={"space_id": document.space_id, "citations": len(result.retrieval.citations)},
        )
        slot.record()
        db.commit()
    return {
        **result.as_dict(),
        "document": {"id": document.id, "title": document.title, "route": f"/knowledge/{document.id}"},
    }


def _require_document_create(db: Session, user: User) -> None:
    from app.authz.service import effective_permissions
    from app.core.errors import ForbiddenError

    if perms.DOCUMENT_CREATE not in effective_permissions(db, user):
        raise ForbiddenError()
