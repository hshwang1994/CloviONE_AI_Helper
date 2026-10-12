"""ChatGPT 계정 연결 시도 — 붙여 넣기 로그인 한 번의 규칙 (계획 A3, D-516 · D-540).

## 순서

  1. 관리자가 시작한다(`start`) - state, nonce, 이번 시도의 루프백 포트(49152 ~ 65535 무작위)를 만들고 인가 주소를
     돌려준다. 10분 동안 유효하다. 화면은 같은 클릭 안에서 연 새 창을 그 주소로 보낸다
  2. 관리자가 ChatGPT 에서 승인하면 새 창이 ``http://127.0.0.1:<포트>/auth/callback?code=…&state=…`` 에서 멈춘다
  3. 관리자가 그 주소를 붙여 넣는다(`complete_manual`) - 루프백 주소, 정해진 경로, 이 시도의 포트만 받는다
  4. 서버가 state 를 맞추고 코드를 토큰으로 바꾸고 ID 토큰을 검증한 뒤 묶음을 비밀 칸에 쓴다
  5. 화면은 「연결됨」을 그리고 모델 목록 · 연결 확인으로 이어 간다

흐름이 왜 이 모양인지(순수 웹 왕복이 공식적으로 안 되는 까닭)는 `login_flow.py` 머리말에 있다. 예전의 연결 도우미와
짝짓기 토큰은 걷었다(D-540).

## 포트를 시도마다 고르는 까닭

예전에는 붙여 넣기 경로가 1455 하나를 썼다. 관리자 PC 에서 다른 프로그램(다른 OAuth 도구)이 그 포트를 듣고 있으면
승인 뒤 브라우저가 그 프로그램에 코드를 넘긴다. 시도마다 높은 포트를 무작위로 고르면 우연히 겹칠 일이 없다. 공식
계약은 포트만 바뀔 수 있고 같은 시도 안에서 인가와 교환이 같은 주소이기만 하면 된다.

## 실패 기록은 커밋한다

state 가 틀린 실패는 다섯 번이면 그 시도를 닫는다. 횟수와 닫힘은 요청이 실패로 끝나도 남아야 한다(그래야 다섯 번이
센다). 그래서 실패를 적은 뒤 커밋하고 예외를 올린다.
"""

from __future__ import annotations

import hmac
import logging
import secrets as pysecrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.ai.credentials import chatgpt
from app.ai.providers import base
from app.core.errors import AppError, NotFoundError

logger = logging.getLogger("app.ai.oauth")

TX_TTL = timedelta(minutes=10)
TX_KEEP = timedelta(days=1)
MAX_FAILURES = 5
#: 루프백 포트는 동적 · 사설 범위에서 시도마다 고른다(머리말).
PORT_MIN, PORT_MAX = 49152, 65535
MIN_SESSION_SECRET = 16

PHASE_BROWSER = "browser"
PHASE_DONE = "done"
PHASE_FAILED = "failed"
OPEN_PHASES = (PHASE_BROWSER,)

PHASE_MESSAGES = {
    PHASE_BROWSER: "ChatGPT 에서 승인한 뒤 주소창의 주소를 붙여 넣으세요.",
    PHASE_DONE: "ChatGPT 계정을 연결했습니다.",
    PHASE_FAILED: "ChatGPT 계정을 연결하지 못했습니다.",
}

FAILURE_MESSAGES = {
    "expired": "연결 시간이 지났습니다. 연결을 다시 시작하세요.",
    "too_many_failures": "확인에 여러 번 실패해 이번 연결을 닫았습니다. 연결을 다시 시작하세요.",
    "access_denied": "ChatGPT 에서 연결을 허락하지 않았습니다.",
    "plan_scope_missing": "ChatGPT 요금제 사용을 허락하지 않았습니다. 다시 연결하면서 요금제 사용을 허락하세요.",
    "client_id_missing": "ChatGPT 가 돌려준 주소에 앱 등록 정보가 없습니다. 연결을 다시 시작하세요.",
    "code_missing": "ChatGPT 가 돌려준 주소에 인가 코드가 없습니다. 연결을 다시 시작하세요.",
    "exchange_failed": "ChatGPT 에서 토큰을 받지 못했습니다. 연결을 다시 시작하세요.",
    "id_token_invalid": "ChatGPT 가 준 계정 정보를 확인하지 못했습니다. 연결을 다시 시작하세요.",
    "secret_store_unavailable": "비밀 저장 도우미에 연결할 수 없어 계정 정보를 저장하지 못했습니다.",
    "superseded": "새 연결을 시작해 이 연결을 닫았습니다.",
}


class OAuthFlowError(AppError):
    status_code = 409
    code = "ai_oauth_failed"
    default_message = PHASE_MESSAGES[PHASE_FAILED]


class ServerSecretMissingError(AppError):
    status_code = 409
    code = "ai_oauth_unavailable"
    default_message = (
        "서버의 세션 비밀 값(SESSION_SECRET)이 없어 계정 연결을 시작할 수 없습니다. 설치 설정을 확인하세요."
    )


def _model():
    from app.ai.models import AiOAuthTransaction

    return AiOAuthTransaction


# ── 시작 ─────────────────────────────────────────────────────────────────────


def pick_port() -> int:
    return PORT_MIN + pysecrets.randbelow(PORT_MAX - PORT_MIN + 1)


def redirect_for(row) -> str:
    return chatgpt.redirect_uri(row.redirect_port)


def start(db: Session, *, admin_user_id: str, session_id: str | None, session_secret: str, now: datetime,
          port: int | None = None):
    """새 시도 하나. (행, 인가 주소)를 돌려준다.

    같은 관리자가 열어 둔 옛 시도는 닫는다 — 앞 창에서 늦게 붙여 넣은 주소가 새 시도를 덮지 않는다.
    """
    from app.ai.credentials import state as state_mod

    if len(session_secret or "") < MIN_SESSION_SECRET:
        raise ServerSecretMissingError()
    model = _model()
    db.execute(
        update(model)
        .where(model.admin_user_id == admin_user_id, model.phase.in_(OPEN_PHASES))
        .values(phase=PHASE_FAILED, error_code="superseded", updated_at=now)
    )
    account = state_mod.account_row(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now)
    host = state_mod.host_id(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now)
    client_id = account.client_id or chatgpt.DYNAMIC_CLIENT_ID
    row = model(
        id=str(uuid.uuid4()), provider=base.PROVIDER_OPENAI, state=pysecrets.token_urlsafe(32),
        nonce=pysecrets.token_urlsafe(32), admin_user_id=admin_user_id, session_id=session_id,
        phase=PHASE_BROWSER, failures=0, redirect_port=int(port or pick_port()), client_id_used=client_id,
        created_at=now, updated_at=now, expires_at=now + TX_TTL,
    )
    db.add(row)
    db.flush()
    verifier = chatgpt.pkce_verifier(session_secret, row.state)
    url = chatgpt.authorize_url(
        client_id=client_id, redirect=redirect_for(row), state=row.state, nonce=row.nonce,
        challenge=chatgpt.pkce_challenge(verifier), host_id=host,
        login_hint=account.account_label if account.account_label and "@" in account.account_label else None,
    )
    return row, url


def _fail(db: Session, row, *, code: str, now: datetime, count: bool = False) -> None:
    """실패를 적고 **커밋한다**(머리말). 다섯 번째 실패는 시도를 닫는다."""
    if count:
        row.failures = int(row.failures or 0) + 1
        if row.failures >= MAX_FAILURES:
            row.phase = PHASE_FAILED
            row.error_code = "too_many_failures"
    else:
        row.phase = PHASE_FAILED
        row.error_code = code
    row.updated_at = now
    db.commit()


def _expire_if_needed(db: Session, row, now: datetime) -> None:
    if row.phase in OPEN_PHASES and now >= row.expires_at:
        row.phase = PHASE_FAILED
        row.error_code = "expired"
        row.updated_at = now
        db.flush()


# ── 관리자 화면 ───────────────────────────────────────────────────────────────


def _own(db: Session, transaction_id: str, *, admin_user_id: str, session_id: str | None, now: datetime):
    """이 관리자와 이 세션이 시작한 시도만 보인다. 남의 시도는 없는 것과 같다(404)."""
    model = _model()
    row = db.get(model, transaction_id)
    if row is None or row.admin_user_id != admin_user_id or (row.session_id or None) != (session_id or None):
        raise NotFoundError("연결 기록을 찾을 수 없습니다.")
    _expire_if_needed(db, row, now)
    return row


def view(row) -> dict:
    failed = row.phase == PHASE_FAILED
    return {
        "transaction_id": row.id,
        "phase": row.phase,
        "message": FAILURE_MESSAGES.get(row.error_code or "", PHASE_MESSAGES[PHASE_FAILED]) if failed
        else PHASE_MESSAGES.get(row.phase, ""),
        "account_label": row.account_label if row.phase == PHASE_DONE else None,
        "expires_at": row.expires_at.isoformat(),
        "error_code": row.error_code if failed else None,
    }


def poll(db: Session, *, transaction_id: str, admin_user_id: str, session_id: str | None, now: datetime) -> dict:
    return view(_own(db, transaction_id, admin_user_id=admin_user_id, session_id=session_id, now=now))


def open_attempt(db: Session, *, admin_user_id: str, now: datetime) -> dict | None:
    """이 관리자의 열린(만료 전) 시도 하나 — 화면의 「로그인 진행 중」(D-558). 없으면 None. 비밀은 싣지 않는다."""
    model = _model()
    row = db.execute(
        select(model)
        .where(model.admin_user_id == admin_user_id, model.phase.in_(OPEN_PHASES), model.expires_at > now)
        .order_by(model.created_at.desc()).limit(1)
    ).scalars().first()
    if row is None:
        return None
    return {"transaction_id": row.id, "expires_at": row.expires_at.isoformat()}


def parse_callback_url(raw, *, port: int | None) -> dict:
    """붙여 넣은 콜백 주소 → 콜백 값. 루프백 주소와 정해진 경로와 이 시도의 포트만 받는다."""
    if not isinstance(raw, str) or len(raw) > 8192:
        raise OAuthFlowError("붙여 넣은 주소를 읽지 못했습니다.")
    parts = urlsplit(raw.strip())
    try:
        got_port = parts.port
    except ValueError:
        got_port = None
    if (parts.scheme != "http" or parts.hostname != chatgpt.REDIRECT_HOST or parts.path != chatgpt.REDIRECT_PATH
            or (port is not None and got_port != port)):
        raise OAuthFlowError("브라우저 주소창에 남은 http://127.0.0.1 주소를 그대로 붙여 넣으세요.")
    query = parse_qs(parts.query, keep_blank_values=False)

    def one(key: str) -> str | None:
        values = query.get(key)
        return values[0] if values else None

    return {key: one(key) for key in ("code", "state", "client_id", "scope", "error")}


def complete_manual(db: Session, *, transaction_id: str, admin_user_id: str, session_id: str | None,
                    callback_url, context) -> dict:
    now = context.now
    row = _own(db, transaction_id, admin_user_id=admin_user_id, session_id=session_id, now=now)
    if row.phase != PHASE_BROWSER:
        # 끝난 시도에 같은 주소를 다시 붙여 넣어도 코드를 두 번 쓰지 않는다.
        raise OAuthFlowError(view(row)["message"] if row.phase == PHASE_FAILED
                             else "이 연결은 이미 끝났습니다. 다시 연결하려면 처음부터 시작하세요.")
    callback = parse_callback_url(callback_url, port=row.redirect_port)
    return _complete(db, row, callback=callback, context=context)


# ── 끝내기 ───────────────────────────────────────────────────────────────────


class CompleteContext:
    """끝내기에 필요한 바깥 것들. 라우터가 채운다."""

    def __init__(self, *, now: datetime, outbound, tokens, session_secret: str, settings_values: dict) -> None:
        self.now = now
        self.outbound = outbound
        self.tokens = tokens
        self.session_secret = session_secret
        self.settings_values = settings_values


def _complete(db: Session, row, *, callback: dict, context: CompleteContext) -> dict:
    from app.ai.credentials import state as state_mod

    now = context.now
    if callback.get("error"):
        _fail(db, row, code="access_denied", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["access_denied"])
    got_state = callback.get("state")
    if not isinstance(got_state, str) or not hmac.compare_digest(got_state, row.state):
        _fail(db, row, code="", now=now, count=True)
        raise OAuthFlowError("연결 요청이 이 시도와 맞지 않습니다. 연결을 다시 시작하세요.")
    code = callback.get("code")
    if not isinstance(code, str) or not code:
        _fail(db, row, code="code_missing", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["code_missing"])
    client_id = callback.get("client_id") or (row.client_id_used if row.client_id_used != chatgpt.DYNAMIC_CLIENT_ID else None)
    if not isinstance(client_id, str) or not client_id or client_id == chatgpt.DYNAMIC_CLIENT_ID:
        _fail(db, row, code="client_id_missing", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["client_id_missing"])
    if not context.tokens.store_ready():
        # 저장할 수 없으면 인가 코드를 쓰지 않는다 - 바꾼 토큰을 버리게 된다.
        _fail(db, row, code="secret_store_unavailable", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["secret_store_unavailable"])

    verifier = chatgpt.pkce_verifier(context.session_secret, row.state)
    try:
        payload = chatgpt.exchange_code(
            context.outbound, code=code, client_id=client_id, redirect=chatgpt.redirect_uri(row.redirect_port),
            verifier=verifier,
        )
    except chatgpt.OAuthError as exc:
        logger.warning("ChatGPT 인가 코드 교환 실패: %s", exc.reason)
        _fail(db, row, code="exchange_failed", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["exchange_failed"]) from None
    scopes = chatgpt.scopes_of(payload, fallback=callback.get("scope"))
    if chatgpt.PLAN_SCOPE not in scopes:
        _fail(db, row, code="plan_scope_missing", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["plan_scope_missing"])
    id_token = payload.get("id_token")
    try:
        if not isinstance(id_token, str) or not id_token:
            raise chatgpt.IdTokenError("id_token_missing")
        claims = chatgpt.verified_claims(context.outbound, id_token, client_id=client_id, nonce=row.nonce)
    except (chatgpt.IdTokenError, chatgpt.OAuthError) as exc:
        logger.warning("ChatGPT ID 토큰 검증 실패: %s", getattr(exc, "reason", type(exc).__name__))
        _fail(db, row, code="id_token_invalid", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["id_token_invalid"]) from None

    access_fallback, refresh_fallback, _lead = chatgpt.settings_numbers(context.settings_values)
    expiry = chatgpt.compute_expiry(payload, now=now, access_fallback_seconds=access_fallback,
                                    refresh_fallback_days=refresh_fallback)
    host = state_mod.host_id(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now)
    bundle = chatgpt.new_bundle(payload=payload, claims=claims, client_id=client_id, host_id=host, expiry=expiry,
                                now=now, scopes=scopes, owner_user_id=row.admin_user_id)
    try:
        context.tokens.save_login(bundle)
    except Exception:  # noqa: BLE001 - 값은 싣지 않는다
        logger.error("ChatGPT 계정 연결 정보를 저장하지 못했다")
        _fail(db, row, code="secret_store_unavailable", now=now)
        raise OAuthFlowError(FAILURE_MESSAGES["secret_store_unavailable"]) from None

    label = (bundle.get("email") or bundle.get("subject") or "")[:200] or None
    state_mod.update_account(
        db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now, account_label=label, client_id=client_id,
        access_expires_at=expiry.access_expires_at, refresh_expires_at=expiry.refresh_expires_at,
        refresh_obtained_at=now, expiry_source=expiry.source[:32], refresh_warned_at=None,
    )
    row.phase = PHASE_DONE
    row.used_at = now
    row.account_label = label
    row.client_id_used = client_id
    row.updated_at = now
    db.flush()
    return {"ok": True, "account_label": label, "transaction_id": row.id, "admin_user_id": row.admin_user_id}


# ── 끊기와 정리 ───────────────────────────────────────────────────────────────


def logout(db: Session, *, tokens, outbound, now: datetime) -> dict:
    """연결을 끊는다. 제공자에 갱신 토큰 무효화를 먼저 요청하고, 결과와 상관없이 이 서버의 토큰을 지운다.

    무효화를 확인하지 못하면 사람에게 ChatGPT 설정에서 연결을 끊으라고 말한다(공식 안내).
    """
    from app.ai.credentials import state as state_mod

    bundle = tokens.bundle()
    revoked = False
    if bundle and bundle.get("refresh_token") and bundle.get("client_id"):
        revoked = chatgpt.revoke(outbound, refresh_token=bundle["refresh_token"], client_id=bundle["client_id"])
    existed = tokens.forget()
    state_mod.update_account(
        db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now, account_label=None, access_expires_at=None,
        refresh_expires_at=None, refresh_obtained_at=None, expiry_source=None, refresh_warned_at=None,
    )
    if revoked or not existed:
        message = "ChatGPT 계정 연결을 끊었습니다."
    else:
        message = ("이 서버의 연결 정보를 지웠지만 ChatGPT 쪽 연결 해제를 확인하지 못했습니다. "
                   "ChatGPT 설정에서 이 앱의 연결을 끊어 주세요.")
    return {"revoked": revoked, "removed": existed, "message": message}


def cleanup(db: Session, *, now: datetime) -> int:
    """하루 지난 시도를 지운다. 열린 채 만료된 시도는 먼저 닫는다."""
    model = _model()
    db.execute(
        update(model).where(model.phase.in_(OPEN_PHASES), model.expires_at <= now)
        .values(phase=PHASE_FAILED, error_code="expired", updated_at=now)
    )
    result = db.execute(delete(model).where(model.expires_at <= now - TX_KEEP))
    return int(result.rowcount or 0)
