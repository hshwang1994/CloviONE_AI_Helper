"""Chat page + API (spec §13, §23.2)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.chat.service import (
    DEFAULT_CONVERSATION_LIST_LIMIT,
    MAX_CONVERSATION_LIST_LIMIT,
    conversation_view,
    create_conversation,
    delete_conversation,
    delete_message,
    get_owned_conversation,
    list_conversations,
    list_messages,
    message_view,
    post_user_message,
    regenerate_message,
    rename_conversation,
    retry_message,
    set_conversation_archived,
    set_message_feedback,
)
from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_serialization_conflict, write_conflict_backoff
from app.core.deps import (
    AuthContext,
    get_current_user,
    get_db,
    get_page_auth,
    require_csrf,
)
from app.core.errors import NotFoundError, RateLimitedError
from app.core.feature_flags import load_feature_flags
from app.quotas import service as ai_quotas
from app.settings.gate import block_if_maintenance
from app.users.models import User

router = APIRouter(tags=["chat"])


# AI-45: 다른 선택적 모듈(팀 채팅·게시판·팀 문서·놀이)은 테넌트별로 끌 수 있는데 AI 도우미
# 채팅만 빠져 있었다. team_chat/router.py의 require_team_chat_enabled와 같은 패턴이지만,
# 이 파일의 "/" 는 채팅 전용이 아니라 React 앱 전체의 진입점이라 여기 의존성에서 뺀다 —
# 개별 API 엔드포인트에만 건다(아래).
def require_chat_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("chat_enabled", True):
        raise NotFoundError("AI 도우미 채팅 기능이 비활성화되어 있습니다.")


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
    # AI-30(Med): AssistantDrawer.jsx's routeContextLabel() — a short curated label, but this
    # is client-supplied so it's capped like any other input, not trusted for anything beyond
    # a hint forwarded to the assistant's conversational prompt.
    screen_context: str | None = Field(default=None, max_length=100)


@router.get("/api/conversations", dependencies=[Depends(require_chat_enabled)])
def get_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    # AI-18: 예전엔 100개 고정 상한이라 그 이상은 화면에서 영영 안 보였다. 화면은 이제
    # "더 보기"를 누르면 offset을 이어붙이는 대신 limit을 키워 같은 목록을 처음부터 다시
    # 받는다 — 이어붙이면 그사이 새 대화가 생기거나 updated_at 정렬이 바뀔 때 항목이
    # 중복되거나 빠질 수 있는데, 매번 "상위 N개 전부"를 다시 받으면 그 문제 자체가 없다.
    limit: int = Query(default=DEFAULT_CONVERSATION_LIST_LIMIT, ge=1, le=MAX_CONVERSATION_LIST_LIMIT),
):
    rows, total = list_conversations(db, user, include_archived=include_archived, q=q, limit=limit)
    return {"items": [conversation_view(c) for c in rows], "total": total}


# AI-44: 남은 AI 쿼터가 백엔드는 이미 예약·차감하는데(post_message의 ai_quotas.reserve)
# 화면 어디에도 안 보였다. 관리자 콘솔의 /api/ai-quotas*는 CONSOLE_READ_ROLES 전용이라
# 일반 사용자가 자기 쿼터를 볼 방법이 없었다 — 본인 것만 보는 자기서비스 경로를 새로 연다.
@router.get("/api/me/ai-quota", dependencies=[Depends(require_chat_enabled)])
def get_my_ai_quota(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ai_quotas.status(db, user_id=user.id, now=request.app.state.clock.now())


@router.post("/api/conversations", status_code=201, dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)])
def post_conversation(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = create_conversation(db, user, title=payload.title)
    return {"conversation": conversation_view(conversation)}


@router.patch("/api/conversations/{conversation_id}", dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)])
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


@router.delete("/api/conversations/{conversation_id}", dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)])
def delete_conversation_endpoint(
    request: Request,
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(db, user, conversation_id)
    # AI-16: 러너 미러도 함께 지운다(위생, 실패해도 이 삭제 자체는 진행됨 — delete_conversation
    # 내부에서 outbound 호출을 별도로 감쌈).
    delete_conversation(
        db, conversation,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings, user=user,
    )
    return {"ok": True}


@router.get("/api/conversations/{conversation_id}/messages", dependencies=[Depends(require_chat_enabled)])
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
    dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)],
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
    #
    attachments = (
        [a.model_dump() for a in payload.attachments] if payload.attachments else None
    )

    # PA-RC-0032: 이 경로 전체(확인→적재→커밋)에 SQLite 쓰기 경합 재시도가 없었다 —
    # 실측(TEST SERVER)에서 `database is locked`가 그대로 500으로 샜다. `ai_quotas.reserve`
    # 의 프로세스 내 뮤텍스(quota_guard)는 같은 사용자의 동시 요청끼리만 직렬화하고
    # SQLite 트랜잭션 경합은 막지 않는다 — 매 시도마다 `reserve`를 새로 만들어 블록
    # 전체(확인 재검증 포함)를 다시 실행한다. `client_message_id` 기반 idempotency_key
    # (`jobs.repository.enqueue`)가 있어 재시도로 잡이 중복 적재되지 않는다 — 실패한
    # 시도는 커밋 전이라 rollback으로 전부 되감기고, 성공한 시도만 그 키로 한 번 적재된다.
    _CHAT_WRITE_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES
    message = job = None
    for _attempt in range(_CHAT_WRITE_RETRIES):
        try:
            with ai_quotas.reserve(db, user_id=user.id, now=request.app.state.clock.now()):
                conversation = get_owned_conversation(db, user, conversation_id)
                message, job = post_user_message(
                    db,
                    user,
                    conversation,
                    content=payload.content,
                    client_message_id=payload.client_message_id,
                    settings=request.app.state.settings,
                    now=request.app.state.clock.now(),
                    attachments=attachments,
                    screen_context=payload.screen_context,
                )
                db.commit()
            break
        except OperationalError as exc:
            if not is_serialization_conflict(exc) or _attempt == _CHAT_WRITE_RETRIES - 1:
                raise
            db.rollback()
            time.sleep(write_conflict_backoff(_attempt))
    return {
        "message": message_view(message),
        "job_id": job.id if job is not None else None,
    }


@router.post(
    "/api/messages/{message_db_id}/retry",
    dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)],
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
    # 전송과 **같은 문지기**를 지난다 (Z15) — 한쪽만 묶으면 '다시 시도' 로 우회한다.
    with ai_quotas.reserve(db, user_id=user.id, now=request.app.state.clock.now()):
        message, job = retry_message(
            db,
            user,
            message_db_id,
            settings=request.app.state.settings,
            now=request.app.state.clock.now(),
        )
        db.commit()
    return {"message": message_view(message), "job_id": job.id}


@router.post(
    "/api/messages/{message_db_id}/regenerate",
    dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)],
)
def regenerate(
    request: Request,
    message_db_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # AI-36: 재생성도 새 n8n 호출을 만드는 잡이라 retry/전송과 같은 두 문지기(버스트 차단·
    # AI 쿼터)를 지난다 — 한쪽만 묶으면 '다시 생성'으로 우회한다(retry 엔드포인트의 같은 주석 참고).
    chat_limit_key = f"chat:{user.id}"
    if not request.app.state.chat_ratelimiter.allow(chat_limit_key):
        raise RateLimitedError(
            "메시지를 너무 빠르게 보냈습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(
                chat_limit_key
            ),
        )
    with ai_quotas.reserve(db, user_id=user.id, now=request.app.state.clock.now()):
        message, job = regenerate_message(
            db,
            user,
            message_db_id,
            settings=request.app.state.settings,
            now=request.app.state.clock.now(),
        )
        db.commit()
    return {"message": message_view(message), "job_id": job.id}


@router.delete(
    "/api/messages/{message_db_id}",
    dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)],
)
def delete_message_endpoint(
    message_db_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    message = delete_message(db, user, message_db_id, now=request.app.state.clock.now())
    return {"message": message_view(message)}


class MessageFeedbackRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=16)


@router.patch(
    "/api/messages/{message_db_id}/feedback",
    dependencies=[Depends(require_chat_enabled), Depends(require_csrf), Depends(block_if_maintenance)],
)
def patch_message_feedback(
    message_db_id: str,
    payload: MessageFeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    message = set_message_feedback(db, user, message_db_id, payload.feedback)
    return {"message": message_view(message)}
