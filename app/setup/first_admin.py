"""첫 관리자 계정 (계획 3.17, D-522).

설치가 끝났는데 사용자가 한 명도 없으면 아무도 로그인할 수 없다. 예전에는 설치가 서버에서 `user_cli add` 를 실행하라고
안내했고(그 안내에는 필수 인자 `--name` 이 빠져 있었다), 임시 비밀번호가 콘솔에 찍혔다. 사람이 서버 셸에 들어가야 첫
화면을 볼 수 있었다. 이제는 이렇게 한다.

1. 설치(Stage 10)가 사용자가 0명일 때만 일회용 설정 코드를 만든다(`issue_code`). 코드 원문은 설치 콘솔에 한 번만 나오고
   설치 로그에는 남지 않는다. 서버에는 sha256 해시, 만료 시각, 실패 횟수만 `DATA_DIR/first-admin.json` 에 남는다.
2. 브라우저에서 `/setup/first-admin` 을 열고 코드, 이메일, 이름, 비밀번호를 넣으면 시스템 관리자 계정이 생긴다.
3. 계정이 생기면 코드 파일을 지운다. 사용자가 한 명이라도 있으면 이 경로는 404 다. 설치가 끝난 서버에는 이 문이 없다.

## 방어

- 코드는 128비트 무작위 값이다(base32 26자). 서버에는 해시만 남고 비교는 `hmac.compare_digest` 로 한다.
- 틀린 코드가 5번 들어오면 코드 파일을 지운다. 다시 만들려면 서버에서 설치 명령을 다시 실행하거나
  `clovirassist first-admin-code` 를 실행한다. 두 경우 모두 서버 관리자 권한이 필요하다.
- 로그인 전 경로라 세션의 CSRF 토큰이 없다. 로그인, 비밀번호 재설정과 같은 Origin 검사(`_verify_login_origin`)와
  IP 단위 속도 제한이 그 자리를 채운다.
- 맞는 코드를 든 두 요청이 겹치면 DB advisory lock 이 한 줄로 세운다. 늦은 쪽은 사용자가 이미 있어 404 를 받는다.
- 코드 원문, 이메일 외의 입력, 비밀번호는 로그와 감사 기록에 남기지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.reset_router import _guard_rate, _is_json_request, extract_body
from app.auth.router import _verify_login_origin
from app.core.advisory_lock import NS_FIRST_ADMIN, wait_lock
from app.core.audit import record_audit
from app.core.deps import get_client_ip, get_db
from app.core.errors import AppError, NotFoundError, ValidationAppError
from app.users.models import ROLE_SYSTEM_ADMIN, User

logger = logging.getLogger("app.setup.first_admin")

CODE_FILE_NAME = "first-admin.json"
CODE_TTL = timedelta(hours=24)
MAX_FAILURES = 5
# 16바이트 = 128비트. base32 로 26자가 되고 사람이 콘솔에서 옮겨 적기 쉽게 네 글자씩 끊어 보인다.
CODE_BYTES = 16

PAGE_PATH = "/setup/first-admin"

router = APIRouter(tags=["setup-first-admin"])


class FirstAdminCodeError(AppError):
    """코드가 없거나, 만료됐거나, 틀렸다. 어느 쪽인지 말해도 코드 자체는 새지 않는다."""

    status_code = 400
    code = "first_admin_code_invalid"
    default_message = "설정 코드가 맞지 않습니다. 설치 화면에 나온 코드를 다시 확인하세요."


@dataclass(frozen=True)
class Issued:
    code: str
    expires_at: datetime


def code_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / CODE_FILE_NAME


def _hash(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode("ascii", "ignore")).hexdigest()


def normalize_code(raw: str) -> str:
    """사람이 옮겨 적은 코드를 비교할 모양으로 바꾼다. 대시, 공백, 대소문자는 뜻이 없다."""
    return "".join(ch for ch in str(raw).upper() if ch.isalnum())


def format_code(code: str) -> str:
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def users_exist(db: Session) -> bool:
    return bool(db.execute(select(func.count()).select_from(User)).scalar_one())


def _read(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # 깨진 파일은 없는 것과 같다. 코드를 다시 만들면 새 파일이 이것을 덮는다.
        logger.warning("첫 관리자 코드 파일을 읽을 수 없어 없는 것으로 봅니다(%s)", path)
        return None
    return payload if isinstance(payload, dict) else None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # 해시만 들어 있어도 남에게 보일 이유가 없다. 서비스 계정만 읽고 쓴다.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


def discard(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def issue_code(db: Session, data_dir: Path | str, *, now: datetime) -> Issued | None:
    """사용자가 0명이면 새 코드를 만들어 해시를 남기고 원문을 돌려준다. 사용자가 있으면 아무것도 하지 않는다.

    같은 서버에서 다시 부르면 옛 코드는 무효가 된다. 원문은 어디에도 남지 않으므로 잃어버린 코드를 다시 보여 줄 방법이
    없고, 새로 만드는 것이 유일한 길이다.
    """
    path = code_path(data_dir)
    if users_exist(db):
        discard(path)
        return None
    code = base64.b32encode(secrets.token_bytes(CODE_BYTES)).decode("ascii").rstrip("=")
    expires_at = now + CODE_TTL
    _write(path, {"hash": _hash(code), "expires_at": expires_at.isoformat(), "failures": 0})
    return Issued(code=code, expires_at=expires_at)


def is_open(db: Session, data_dir: Path | str, *, now: datetime) -> bool:
    if users_exist(db):
        return False
    payload = _read(code_path(data_dir))
    return bool(payload) and _unexpired(payload, now)


def _unexpired(payload: dict, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(str(payload.get("expires_at"))) > now
    except ValueError:
        return False


def create_first_admin(
    db: Session,
    *,
    data_dir: Path | str,
    settings,
    effective_settings: dict,
    code: str,
    email: str,
    name: str,
    password: str,
    now: datetime,
    client_ip: str | None,
    request_id: str | None,
) -> User:
    """코드를 확인하고 시스템 관리자를 만든다. 사용자가 이미 있으면 404 다(이 문은 첫 계정 하나만 연다)."""
    from app.users.service import create_user, user_snapshot

    path = code_path(data_dir)
    with wait_lock(db, NS_FIRST_ADMIN, "first-admin", wait_seconds=5) as got:
        if not got:
            raise AppError("다른 요청을 처리하고 있습니다. 잠시 뒤 다시 시도하세요.")
        if users_exist(db):
            discard(path)
            raise NotFoundError("이 설치에는 이미 계정이 있습니다.")
        payload = _read(path)
        if not payload or not _unexpired(payload, now):
            discard(path)
            raise FirstAdminCodeError(
                "설정 코드가 없거나 만료됐습니다. 서버에서 설치 명령을 다시 실행하면 새 코드가 나옵니다."
            )
        if not hmac.compare_digest(str(payload.get("hash", "")), _hash(code)):
            failures = int(payload.get("failures", 0)) + 1
            if failures >= MAX_FAILURES:
                discard(path)
                record_audit(
                    db, actor_id=None, action="setup.first_admin_locked", object_type="setup",
                    object_id="first_admin", after={"failures": failures}, result="failure",
                    client_ip=client_ip, request_id=request_id,
                )
                db.commit()
                raise FirstAdminCodeError(
                    "틀린 코드가 여러 번 들어와 코드를 폐기했습니다. 서버에서 설치 명령을 다시 실행해 새 코드를 받으세요."
                )
            _write(path, {**payload, "failures": failures})
            raise FirstAdminCodeError()

        user = create_user(
            db,
            email=email,
            display_name=name,
            password=password,
            settings=settings,
            # 이 경로의 권한은 설정 코드가 증명한다. 코드는 서버 관리자만 볼 수 있는 설치 콘솔에만 나왔다.
            actor_role=ROLE_SYSTEM_ADMIN,
            role=ROLE_SYSTEM_ADMIN,
            must_change_password=False,
            enforce_password_policy=True,
            effective_settings=effective_settings,
        )
        record_audit(
            db, actor_id=user.id, action="setup.first_admin_created", object_type="user",
            object_id=user.id, after=user_snapshot(user), client_ip=client_ip, request_id=request_id,
        )
        db.commit()
        discard(path)
        return user


# ── 화면 ─────────────────────────────────────────────────────────────────────


def _page(request: Request, context: dict, *, status_code: int = 200):
    branding = request.app.state.settings_cache.current_value("ui_branding") or {}
    policy = request.app.state.settings_cache.current_value("password_policy") or {}
    return request.app.state.templates.TemplateResponse(
        request,
        "first_admin.html",
        {
            "app_name": branding.get("product_name", "ClovirAssist"),
            "policy": policy,
            "error": None,
            "done": False,
            "submitted_email": "",
            "submitted_name": "",
            **context,
        },
        status_code=status_code,
    )


def _now(request: Request) -> datetime:
    return request.app.state.clock.now()


def _data_dir(request: Request) -> Path:
    return Path(request.app.state.settings.data_dir)


@router.get(PAGE_PATH)
def first_admin_page(request: Request, db: Session = Depends(get_db)):
    if users_exist(db):
        raise NotFoundError("이 설치에는 이미 계정이 있습니다.")
    opened = is_open(db, _data_dir(request), now=_now(request))
    return _page(request, {"code_ready": opened})


@router.post(PAGE_PATH, dependencies=[Depends(_verify_login_origin)])
def create_first_admin_route(
    request: Request,
    data: dict = Depends(extract_body),
    db: Session = Depends(get_db),
):
    # sync 핸들러(불변 §1): Argon2 해싱과 sync SQLAlchemy 가 스레드풀에서 돈다.
    _guard_rate(request, "first_admin")
    email = str(data.get("email", "")).strip()
    name = str(data.get("name", "")).strip()
    password = str(data.get("password", ""))
    confirm = data.get("password_confirm")
    try:
        if confirm is not None and str(confirm) != password:
            raise ValidationAppError("두 번 입력한 비밀번호가 다릅니다.")
        if not email or not name or not password:
            raise ValidationAppError("코드, 이메일, 이름, 비밀번호를 모두 입력하세요.")
        user = create_first_admin(
            db,
            data_dir=_data_dir(request),
            settings=request.app.state.settings,
            effective_settings=request.app.state.settings_cache.current(),
            code=str(data.get("code", "")),
            email=email,
            name=name,
            password=password,
            now=_now(request),
            client_ip=get_client_ip(request),
            request_id=getattr(request.state, "request_id", None),
        )
    except (FirstAdminCodeError, ValidationAppError) as exc:
        if _is_json_request(request):
            raise
        detail = getattr(exc, "details", None)
        message = exc.message if not detail else " ".join(str(d) for d in detail) if isinstance(detail, list) else exc.message
        return _page(
            request,
            {"code_ready": True, "error": message, "submitted_email": email, "submitted_name": name},
            status_code=exc.status_code,
        )
    if _is_json_request(request):
        return JSONResponse({"ok": True, "email": user.email}, status_code=201)
    return _page(request, {"code_ready": False, "done": True, "submitted_email": user.email}, status_code=201)
