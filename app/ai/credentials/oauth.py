"""ChatGPT 계정 연결 시도 — 연결 도우미와 서버가 한 번의 로그인을 주고받는 규칙 (계획 3.14, D-516).

## 왜 도우미가 필요한가

공식 계약상 인가는 `http://127.0.0.1:<포트>/auth/callback` 으로만 돌아온다. 그 주소는 **브라우저가 도는 PC** 이지
원격 서버가 아니다(자체 호스팅 VM 지침). 그래서 순수 웹 화면만으로는 콜백을 받을 수 없다. 관리자 PC 에서 도는 작은
도우미(`tools/connect/`)가 콜백만 받아 서버에 넘기고, 인가 코드를 토큰으로 바꾸는 일은 서버가 제 PKCE verifier 로
한다. 토큰은 도우미를 거치지 않는다.

## 순서

  1. 관리자가 시작한다(`start`) - 짝짓기 토큰(256비트, 원문은 응답에 한 번)과 state, nonce 를 만든다. 10분 동안 유효하다
  2. 도우미가 짝짓기 토큰과 자기가 연 포트를 알린다(`begin`) - 서버가 그 포트로 인가 주소를 만들어 준다
  3. 관리자가 브라우저에서 승인하면 도우미가 콜백을 받아 넘긴다(`complete_from_helper`)
  4. 서버가 state 를 맞추고 코드를 토큰으로 바꾸고 ID 토큰을 검증한 뒤 묶음을 비밀 칸에 쓴다
  5. 화면은 `view` 를 물어 「도우미를 기다리는 중 → 브라우저에서 승인하는 중 → 연결됨」을 그린다

도우미를 돌릴 수 없는 PC 는 대체 경로가 있다: 화면이 인가 주소를 주고(`manual_authorize`), 관리자가 승인 뒤 브라우저가
멈춘 콜백 주소를 붙여 넣는다(`complete_manual`). 같은 끝내기 규칙을 지난다.

## 짝짓기 토큰의 규칙

사람이 외워 치는 값이 아니라 복사한 명령으로 전달되므로 짧게 줄이지 않는다(`secrets.token_urlsafe(32)`). 서버에는
sha256 해시만 두고, 한 번 쓰면 끝이며, state 가 틀리는 실패가 다섯 번이면 그 시도를 닫는다. 로그와 감사에는 원문을
적지 않는다. 확인에 실패한 까닭을 도우미에게 자세히 말하지 않는다 - 틀린 토큰과 만료된 토큰은 같은 한 문장이다.

## 실패 기록은 커밋한다

실패 횟수와 닫힘은 요청이 실패로 끝나도 남아야 한다(그래야 다섯 번이 센다). 그래서 실패를 적은 뒤 커밋하고 예외를 올린다.
"""

from __future__ import annotations

import hashlib
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
MIN_PORT, MAX_PORT = 1024, 65535
MIN_SESSION_SECRET = 16

PHASE_WAITING = "waiting_helper"
PHASE_BROWSER = "browser"
PHASE_DONE = "done"
PHASE_FAILED = "failed"
OPEN_PHASES = (PHASE_WAITING, PHASE_BROWSER)

PHASE_MESSAGES = {
    PHASE_WAITING: "연결 도우미를 기다리고 있습니다. 안내한 명령을 이 PC 에서 실행하세요.",
    PHASE_BROWSER: "브라우저에서 ChatGPT 승인을 기다리고 있습니다.",
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
PAIRING_REJECTED = "연결 요청을 확인하지 못했습니다. 화면에서 연결을 다시 시작한 뒤 새 명령을 실행하세요."


class OAuthFlowError(AppError):
    status_code = 409
    code = "ai_oauth_failed"
    default_message = PHASE_MESSAGES[PHASE_FAILED]


class PairingRejectedError(AppError):
    status_code = 403
    code = "ai_pairing_rejected"
    default_message = PAIRING_REJECTED


class ServerSecretMissingError(AppError):
    status_code = 409
    code = "ai_oauth_unavailable"
    default_message = (
        "서버의 세션 비밀 값(SESSION_SECRET)이 없어 계정 연결을 시작할 수 없습니다. 설치 설정을 확인하세요."
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _model():
    from app.ai.models import AiOAuthTransaction

    return AiOAuthTransaction


# ── 시작 ─────────────────────────────────────────────────────────────────────


def start(db: Session, *, admin_user_id: str, session_id: str | None, session_secret: str, now: datetime):
    """새 시도 하나. (행, 짝짓기 토큰 원문)을 돌려준다 - 원문은 이 응답에만 실린다.

    같은 관리자가 열어 둔 옛 시도는 닫는다. 도우미 두 개가 서로 다른 시도에 붙는 혼란을 막는다.
    """
    if len(session_secret or "") < MIN_SESSION_SECRET:
        raise ServerSecretMissingError()
    model = _model()
    db.execute(
        update(model)
        .where(model.admin_user_id == admin_user_id, model.phase.in_(OPEN_PHASES))
        .values(phase=PHASE_FAILED, error_code="superseded", updated_at=now)
    )
    token = pysecrets.token_urlsafe(32)
    row = model(
        id=str(uuid.uuid4()), provider=base.PROVIDER_OPENAI, pairing_token_hash=hash_token(token),
        state=pysecrets.token_urlsafe(32), nonce=pysecrets.token_urlsafe(32), admin_user_id=admin_user_id,
        session_id=session_id, phase=PHASE_WAITING, failures=0, created_at=now, updated_at=now,
        expires_at=now + TX_TTL,
    )
    db.add(row)
    db.flush()
    return row, token


# ── 도우미 ───────────────────────────────────────────────────────────────────


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


def _by_pairing_token(db: Session, token, now: datetime):
    if not isinstance(token, str) or not token:
        raise PairingRejectedError()
    model = _model()
    row = db.execute(
        select(model).where(model.pairing_token_hash == hash_token(token)).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise PairingRejectedError()
    _expire_if_needed(db, row, now)
    if row.phase not in OPEN_PHASES:
        db.commit()
        raise PairingRejectedError()
    return row


def _authorize_for(db: Session, row, *, port: int, now: datetime, session_secret: str) -> str:
    from app.ai.credentials import state as state_mod

    if len(session_secret or "") < MIN_SESSION_SECRET:
        raise ServerSecretMissingError()
    account = state_mod.account_row(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now)
    host = state_mod.host_id(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now)
    client_id = account.client_id or chatgpt.DYNAMIC_CLIENT_ID
    row.redirect_port = int(port)
    row.client_id_used = client_id
    row.phase = PHASE_BROWSER
    row.updated_at = now
    db.flush()
    verifier = chatgpt.pkce_verifier(session_secret, row.state)
    return chatgpt.authorize_url(
        client_id=client_id, redirect=chatgpt.redirect_uri(port), state=row.state, nonce=row.nonce,
        challenge=chatgpt.pkce_challenge(verifier), host_id=host,
        login_hint=account.account_label if account.account_label and "@" in account.account_label else None,
    )


def begin(db: Session, *, pairing_token, port, session_secret: str, now: datetime) -> dict:
    """도우미가 자신과 포트를 알린다. 인가 주소를 돌려준다."""
    row = _by_pairing_token(db, pairing_token, now)
    if row.phase != PHASE_WAITING:
        _fail(db, row, code="", now=now, count=True)
        raise PairingRejectedError()
    if not isinstance(port, int) or isinstance(port, bool) or not (MIN_PORT <= port <= MAX_PORT):
        raise OAuthFlowError("도우미가 알린 포트가 올바르지 않습니다.")
    url = _authorize_for(db, row, port=port, now=now, session_secret=session_secret)
    return {"transaction_id": row.id, "authorize_url": url, "redirect_uri": chatgpt.redirect_uri(port)}


def complete_from_helper(db: Session, *, pairing_token, transaction_id, callback, context) -> dict:
    now = context.now
    row = _by_pairing_token(db, pairing_token, now)
    if row.id != transaction_id or row.phase != PHASE_BROWSER:
        _fail(db, row, code="", now=now, count=True)
        raise PairingRejectedError()
    return _complete(db, row, callback=callback if isinstance(callback, dict) else {}, context=context)


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


def manual_authorize(db: Session, *, transaction_id: str, admin_user_id: str, session_id: str | None,
                     session_secret: str, now: datetime) -> dict:
    """대체 경로: 도우미 없이 인가 주소를 받는다. 승인 뒤 브라우저가 멈춘 주소를 붙여 넣는다."""
    row = _own(db, transaction_id, admin_user_id=admin_user_id, session_id=session_id, now=now)
    if row.phase not in OPEN_PHASES:
        raise OAuthFlowError(view(row)["message"])
    port = row.redirect_port or chatgpt.DEFAULT_REDIRECT_PORT
    url = _authorize_for(db, row, port=port, now=now, session_secret=session_secret)
    return {"transaction_id": row.id, "authorize_url": url, "redirect_uri": chatgpt.redirect_uri(port)}


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
        raise OAuthFlowError(view(row)["message"] if row.phase == PHASE_FAILED else "먼저 인가 주소를 여세요.")
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
                                now=now, scopes=scopes)
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
