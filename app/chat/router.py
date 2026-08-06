"""Chat page + API (spec §13, §23.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.chat.service import (
    conversation_view,
    create_conversation,
    delete_conversation,
    get_owned_conversation,
    list_conversations,
    list_messages,
    message_view,
    post_user_message,
    rename_conversation,
    retry_message,
    set_conversation_archived,
)
from app.core.deps import (
    AuthContext,
    get_current_user,
    get_db,
    get_page_auth,
    require_csrf,
)
from app.core.errors import RateLimitedError
from app.quotas import service as ai_quotas
from app.settings.gate import block_if_maintenance
from app.users.models import User

router = APIRouter(tags=["chat"])


@router.get("/")
def index(request: Request, auth: AuthContext = Depends(get_page_auth)):
    if auth.user.must_change_password:
        return RedirectResponse("/change-password", status_code=303)
    # 사용자 홈(채팅)도 React 셸이 서빙한다. React 앱이 경로(/)를 보고 채팅 화면을 기본으로
    # 연다(admin/router.py의 _react_shell과 같은 셸·같은 no-store 정책).
    from app.admin.router import _react_shell

    return _react_shell()


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


class MessageAttachment(BaseModel):
    filename: str = Field(default="", max_length=200)
    media_type: str = Field(min_length=3, max_length=40)
    data: str = Field(min_length=1, max_length=5_600_000)  # base64 of ≤3MB (validated in service)


class MessageCreateRequest(BaseModel):
    # min_length=0: an image-only message is allowed (service substitutes a marker).
    content: str = Field(default="", max_length=20000)  # hard cap; policy limit checked in service
    client_message_id: str = Field(min_length=8, max_length=64)
    attachments: list[MessageAttachment] | None = Field(default=None, max_length=3)


@router.get("/api/conversations")
def get_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    include_archived: bool = Query(default=False),
):
    rows = list_conversations(db, user, include_archived=include_archived)
    return {"items": [conversation_view(c) for c in rows]}


@router.post("/api/conversations", status_code=201, dependencies=[Depends(require_csrf), Depends(block_if_maintenance)])
def post_conversation(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = create_conversation(db, user, title=payload.title)
    return {"conversation": conversation_view(conversation)}


@router.patch("/api/conversations/{conversation_id}", dependencies=[Depends(require_csrf), Depends(block_if_maintenance)])
def patch_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(db, user, conversation_id)
    if payload.title is not None:
        rename_conversation(db, conversation, payload.title)
    if payload.archived is not None:
        set_conversation_archived(db, conversation, payload.archived)
    return {"conversation": conversation_view(conversation)}


@router.delete("/api/conversations/{conversation_id}", dependencies=[Depends(require_csrf), Depends(block_if_maintenance)])
def delete_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(db, user, conversation_id)
    delete_conversation(db, conversation)
    return {"ok": True}


@router.get("/api/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    after: str | None = Query(default=None, max_length=36),
):
    conversation = get_owned_conversation(db, user, conversation_id)
    rows = list_messages(db, conversation, after=after)
    return {
        "conversation": conversation_view(conversation),
        "items": [message_view(m) for m in rows],
    }


@router.post(
    "/api/conversations/{conversation_id}/messages",
    status_code=202,
    dependencies=[Depends(require_csrf), Depends(block_if_maintenance)],
)
def post_message(
    request: Request,
    conversation_id: str,
    payload: MessageCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 사용자당 전송 폭주 차단(잡 큐·다운스트림 보호). 버스트 후 초과분은 429.
    chat_limit_key = f"chat:{user.id}"
    if not request.app.state.chat_ratelimiter.allow(chat_limit_key):
        raise RateLimitedError(
            "메시지를 너무 빠르게 보냈습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(
                chat_limit_key
            ),
        )
    # AI 사용 상한(X11). 예전에는 **메인 채팅만 상한 밖**이었다 — 문장 생성·문서 생성에는
    # 걸면서 정작 비용이 가장 큰 축을 열어 뒀고, 그래서 화면의 "300/100" 같은 숫자가
    # 아무도 막지 않는 값이었다. 레이트리미터(폭주 차단)와는 다른 일이다: 저쪽은 초 단위
    # 버스트, 이쪽은 하루·한 달 총량이다.
    ai_quotas.enforce(db, user_id=user.id, now=request.app.state.clock.now())
    conversation = get_owned_conversation(db, user, conversation_id)
    message, job = post_user_message(
        db,
        user,
        conversation,
        content=payload.content,
        client_message_id=payload.client_message_id,
        settings=request.app.state.settings,
        now=request.app.state.clock.now(),
        attachments=(
            [a.model_dump() for a in payload.attachments] if payload.attachments else None
        ),
    )
    return {
        "message": message_view(message),
        "job_id": job.id if job is not None else None,
    }


@router.post(
    "/api/messages/{message_db_id}/retry",
    dependencies=[Depends(require_csrf), Depends(block_if_maintenance)],
)
def retry(
    request: Request,
    message_db_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # retry enqueues an identical chat_message job to POST
    # /api/conversations/{id}/messages (see post_message above) — the same
    # per-user chat_ratelimiter guards the job queue/n8n from burst abuse
    # there, but this endpoint had no equivalent check, so a user could
    # bypass the send-rate limit entirely by hammering '다시 시도' instead.
    chat_limit_key = f"chat:{user.id}"
    if not request.app.state.chat_ratelimiter.allow(chat_limit_key):
        raise RateLimitedError(
            "메시지를 너무 빠르게 보냈습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(
                chat_limit_key
            ),
        )
    # AI 사용 상한(X11) — 재시도도 같은 문을 지난다. 예전에는 **메인 채팅만 상한 밖**이었다 — 문장 생성·문서 생성에는
    # 걸면서 정작 비용이 가장 큰 축을 열어 뒀고, 그래서 화면의 "300/100" 같은 숫자가
    # 아무도 막지 않는 값이었다. 레이트리미터(폭주 차단)와는 다른 일이다: 저쪽은 초 단위
    # 버스트, 이쪽은 하루·한 달 총량이다.
    ai_quotas.enforce(db, user_id=user.id, now=request.app.state.clock.now())
    message, job = retry_message(
        db,
        user,
        message_db_id,
        settings=request.app.state.settings,
        now=request.app.state.clock.now(),
    )
    return {"message": message_view(message), "job_id": job.id}
