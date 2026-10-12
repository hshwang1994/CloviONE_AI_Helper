"""메일 화면 API — 상태 · 설정 · 발송 기록 · 시험 메일 · 연결 확인 · 메일 모양 (계획 M1 · M2 · M3, D-546 · D-548 · D-549 · D-554 · D-555).

## 이 화면이 있는 이유

"설정이 없으면 없다고 한다" 는 요구는 사용자 화면만으로 끝나지 않는다. 운영자가 **무엇을 채워야 하는지** 알 수 있어야 하고,
채운 뒤 **실제로 되는지** 확인할 수 있어야 한다. 그래서 진단(`GET /status`), 설정(`GET` · `PUT /settings`), 연결 확인
(`POST /verify`), 시험 발송(`POST /test`)을 한 화면(「운영 › 메일」)이 쓴다.

## 설정은 이 API 로만 쓴다 (D-545 · D-548)

SMTP 설정(`smtp` 키)은 시스템 관리자(`SYSTEM_CONFIGURE`)가 형식이 정해진 `PUT /settings` 로만 바꾼다. 범용 설정 API 는 그 키를
거절한다(`app/settings/router.py`). 비밀번호는 **같은 저장**에 실려 고정 칸(`smtp.password`)에 쓰인다 - 예전에는 비밀번호만
즉시 저장되고 나머지는 따로 저장해, 한쪽만 저장된 채 창을 닫는 일이 있었다. 저장하면 보낼 수 있는 설정일 때 연결 확인을
저절로 시작한다.

## 시험 메일은 받는 주소를 고를 수 있다 (D-554)

예전에는 「임의 주소로 보낼 수 있게 하면 스팸 발송기가 된다」며 자기 자신에게만 보냈다. 실제 수신을 확인하려면 다른
주소(회사 메일)로 보내야 해서 받는 주소를 연다 - 대신 다른 주소는 메일 설정 권한(`SYSTEM_CONFIGURE`)이 있는 사람만 넣고,
내용은 고정 틀이며(사람이 쓴 글이 섞이지 않는다), 사람당 10분에 5통 · 설치 전체 1시간에 20통으로 막고, 감사에는 가린 주소만
남긴다. 메일 설정 권한자는 이미 SMTP 계정을 쥐고 있어 새로 생기는 능력이 거의 없다.

## 한 통을 보고, 다시 보내고, 취소한다 (계획 3.3)

`GET /deliveries/{id}` 는 한 통의 상태와 잡의 다음 시도 시각을 준다 - 시험 메일을 보낸 화면이 이것을 끝날 때까지 읽는다.
다시 보내기와 취소, 설정 전에 쌓인 메일 보내기는 시험 발송과 같은 판정(전역 관리 범위)을 지난다 - 설치 한 벌의 SMTP 계정으로
나가는 동작이다.

## 읽기는 받는 사람의 범위로 거른다 (D-547)

발송 기록은 받는 주소 · 티켓 제목 · 알림 본문을 싣는다. 전역 관리 범위가 아니면 받는 사람(`recipient_user_id`)이 관리 범위 안인
메일만 보이고, 받는 사람이 계정이 아닌 메일은 전역 관리 범위만 본다. 범위 밖 상세는 404 다.

## 상태 낱말은 확인한 단계까지만 (D-555)

「보냈습니다」 · 「도착했습니다」를 쓰지 않는다. 다음 서버가 받았으면 「메일 서버가 접수함」이고, 그것은 받은 편지함이 아니다
(`app/mail/labels.py`). 받은 편지함 확인은 사람이 남기는 증거다.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.permissions import SYSTEM_CONFIGURE
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import (
    audit_forbidden_write,
    get_db,
    get_principal,
    require_csrf,
    require_permission,
    require_roles,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, RateLimitedError, ValidationAppError
from app.core.pagination import PageParams
from app.core.scope import Principal, require_global_management, visible_user_ids
from app.core.sort import SortParams
from app.mail.config import (
    DEFAULT_SMTP,
    PASSWORD_SLOT,
    SMTP_SETTING_KEY,
    config_from_db,
    configuration_problems,
    helper_params,
    is_sendable,
    mail_status,
)
from app.mail.models import MAIL_SENT
from app.mail.renderers import KIND_TEST
from app.notifications.mail import admin_catalog as notification_mail_catalog
from app.mail.service import (
    backlog_window_days,
    cancel_delivery,
    delivery_detail,
    delivery_view,
    delivery_views,
    list_deliveries,
    mail_subject,
    pending_unconfigured_count,
    queue_counts,
    queue_mail,
    recent_failures,
    resend_delivery,
    resend_unconfigured,
)

router = APIRouter(
    prefix="/api/admin/mail",
    tags=["admin-mail"],
    dependencies=[Depends(require_csrf)],
)

# 시험 메일의 속도 제한(D-554). 사람당 10분에 5통, 설치 전체 1시간에 20통.
TEST_PER_USER = (5, 5 / 600)
TEST_PER_INSTALL = (20, 20 / 3600)
# 포트 프리셋 — 보안 연결을 바꾸면 화면이 따라 바꾼다.
PORT_PRESETS = {"starttls": 587, "ssl": 465, "none": 25}

_ADDRESS = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def _secrets(request: Request):
    return getattr(request.app.state, "secret_provider", None)


def current_mail_status(request: Request, db: Session | None = None) -> dict:
    """화면과 진단이 같은 값을 보게 하는 한 줄. 판정은 app/mail/config.py 한 곳이다. 요청 안에서는 DB 의 설정을 읽는다
    (프로세스마다 다른 캐시가 낡아 한 응답 안에서 값이 섞이지 않게)."""
    from app.mail.config import config_from_cache

    config = config_from_db(db) if db is not None else config_from_cache(
        getattr(request.app.state, "settings_cache", None))
    return mail_status(config, _secrets(request))


def current_health(request: Request, db: Session) -> dict:
    """저장된 건강 상태(`app/mail/health.py`). 메일 서버에 붙지 않는다."""
    from app.mail.health import health_state

    return health_state(db, config_from_db(db), _secrets(request))


def _password_state(request: Request) -> dict:
    provider = _secrets(request)
    if provider is None:
        return {"stored": False, "updated_at": None}
    from app.core.secret_refs import STATUS_CONFIGURED

    stored = provider.status(PASSWORD_SLOT) == STATUS_CONFIGURED
    updated = provider.modified_at(PASSWORD_SLOT) if stored and hasattr(provider, "modified_at") else None
    return {"stored": stored, "updated_at": updated.isoformat() if updated else None}


def _can_configure(db: Session, user) -> bool:
    from app.authz.service import effective_permissions

    return SYSTEM_CONFIGURE in effective_permissions(db, user)


def _can_operate(user, principal: Principal) -> bool:
    return user.role in CONSOLE_WRITE_ROLES and principal.manages_everything


def _base_url_state(request: Request, can_configure: bool) -> dict:
    """메일 속 링크의 기준 주소. 문제 문장은 고칠 수 있는 사람(메일 설정 권한)에게만 준다 - 설정 키 이름은 쓰지 않는다."""
    value = str(getattr(request.app.state.settings, "app_base_url", "") or "").rstrip("/")
    problem = None
    if not value.startswith("https://"):
        problem = "메일 속 링크가 https 주소가 아닙니다. 설치할 때 정한 접속 주소를 확인하세요."
    elif "127.0.0.1" in value or "localhost" in value:
        problem = "메일 속 링크가 이 서버 안에서만 열리는 주소입니다. 설치할 때 정한 접속 주소를 확인하세요."
    return {"value": value, "problem": problem if can_configure else None}


@router.get("/status", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def status(request: Request, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """메일 화면 한 벌. 전부 DB 의 설정 한 번(`config_from_db`)에서 만든다 - 한 응답 안에서 단추 상태와 문장이 엇갈리지 않게."""
    from app.mail import progress

    config = config_from_db(db)
    now = request.app.state.clock.now()
    health = current_health(request, db)
    can_configure = _can_configure(db, request.state.user)
    relay = _status_relay(request, db, config)
    test = progress.latest_test(db)
    inbox = progress.load_inbox(db)
    return {
        "mail": mail_status(config, _secrets(request)),
        # 다섯 상태(사용 안 함 · 설정 덜 됨 · 확인 전 · 정상 · 발송 실패)와 마지막 확인의 단계 줄(D-546).
        "health": health,
        # 일곱 단계와 다음 할 일(D-560). 화면은 이 순서로 선다.
        "progress": progress.compute(config, _secrets(request), health=health, relay=relay, test=test, inbox=inbox),
        "latest_test": test,
        "inbox": inbox,
        "problems": configuration_problems(config, _secrets(request)) if config.enabled else [],
        "summary": {**config.public_view(), "mode": getattr(config, "mode", "external"),
                    "password": _password_state(request)},
        "counts": queue_counts(db),
        # 받는 주소와 제목이 실리므로 목록과 같은 범위로 거른다(D-547). 상태별 수는 사람 정보가 없어 설치 전체다.
        "recent_failures": delivery_views(db, recent_failures(db, visible=visible_user_ids(db, principal.management))),
        # 설정 전에 쌓여 설정 뒤 다시 보낼 수 있는 메일(초대 · 알림, 최대 나이 안).
        "pending_unconfigured_count": pending_unconfigured_count(db, now=now),
        "backlog": {"count": pending_unconfigured_count(db, now=now), "window_days": backlog_window_days(db)},
        "base_url": _base_url_state(request, can_configure),
        # 로컬 릴레이(M7, D-551) - 그 방식일 때만 구성 요소 상태와 최근 바깥 전달을 싣는다(상태 면의 두 줄).
        "relay": relay,
        "capabilities": {
            "can_configure": can_configure,
            "can_operate": _can_operate(request.state.user, principal),
        },
        # 알림을 메일로도 보내기(계획 3.4) - 관리자가 허용한 유형과 고를 수 있는 유형 전부, 오래된 메일의 기준.
        "notification_mail": notification_mail_catalog(db),
    }


def _status_relay(request: Request, db: Session, config) -> dict | None:
    if not config.local_relay:
        return None
    from app.mail import relay_tracking

    status, detail = _helper_status(request, config)
    component = _component_view(status, config, detail)
    return {"delivery": config.relay.delivery, "component": {k: component[k] for k in ("state", "label", "message", "help", "stale")},
            "outer": relay_tracking.last_outcome(db)}


# ── 설정 (D-545 · D-548) ──────────────────────────────────────────────────────


class SmarthostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="", max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal["none", "starttls", "ssl"] = "starttls"
    username: str = Field(default="", max_length=320)


class TransportOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(max_length=253)
    host: str = Field(max_length=253)


class RelaySettingsRequest(BaseModel):
    """로컬 릴레이 설정(D-551). DKIM 공개키는 사람이 넣지 않는다 - 키를 만들 때 서버가 적는다."""

    model_config = ConfigDict(extra="forbid")

    delivery: Literal["smarthost", "direct"] = "smarthost"
    smarthost: SmarthostRequest = Field(default_factory=SmarthostRequest)
    helo_name: str = Field(default="", max_length=253)
    public_ip: str = Field(default="", max_length=15)
    ipv4_only: bool = False
    dkim_enabled: bool = False
    dkim_selector: str = Field(default="", max_length=63)
    transport_overrides: list[TransportOverride] = Field(default_factory=list, max_length=20)
    compare_resolvers: list[str] = Field(default_factory=list, max_length=3)


class MailSettingsRequest(BaseModel):
    """메일 설정 저장. 모르는 칸(옛 `password_ref` 포함)은 422 다 - 비밀 칸 이름은 사람이 고르지 않는다(D-545)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    host: str = Field(default="", max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal["none", "starttls", "ssl"] = "starttls"
    from_address: str = Field(default="", max_length=320)
    from_name: str = Field(default="", max_length=100)
    username: str = Field(default="", max_length=320)
    timeout_seconds: int = Field(default=20, ge=1, le=300)
    tls_verify: bool = True
    ca_pem: str = Field(default="", max_length=20480)
    # 비밀번호(있으면 같은 저장에서 고정 칸에 쓴다). 응답 · 감사 · 로그 어디에도 값이 나가지 않는다.
    password: str | None = Field(default=None, max_length=1024)
    clear_password: bool = False
    # 보내는 방법(D-551). 「외부 SMTP 사용」이 기본이다.
    mode: Literal["external", "local_relay"] = "external"
    relay: RelaySettingsRequest | None = None
    # 상위 SMTP 비밀번호(로컬 릴레이의 상위 SMTP 이용). 같은 저장에서 고정 칸에 쓴다.
    relay_password: str | None = Field(default=None, max_length=1024)
    clear_relay_password: bool = False


def _settings_view(request: Request, db: Session) -> dict:
    config = config_from_db(db)
    return {
        "settings": {
            "enabled": config.enabled, "host": config.host, "port": config.port, "security": config.security,
            "from_address": config.from_address, "from_name": config.from_name, "username": config.username,
            "timeout_seconds": config.timeout_seconds, "tls_verify": config.tls_verify, "ca_pem": config.ca_pem,
            "mode": config.mode, "relay": config.relay.as_dict(),
        },
        "password": _password_state(request),
        "relay_password": _relay_password_state(request),
        "presets": {"ports": PORT_PRESETS},
        "limits": {"timeout_seconds": [1, 300], "ca_pem_max": 20480, "from_name_max": 100},
    }


def _audit_value(value: dict) -> dict:
    """감사에 남길 설정 모양 — CA 원문은 길이와 해시로 줄인다(비밀은 처음부터 없다)."""
    out = dict(value)
    pem = str(out.pop("ca_pem", "") or "")
    out["ca_pem"] = {"length": len(pem), "sha256": hashlib.sha256(pem.encode("utf-8")).hexdigest()} if pem else None
    return out


@router.get("/settings", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def get_settings(request: Request, db: Session = Depends(get_db)):
    """편집할 값 · 비밀번호 저장 여부 · 포트 프리셋 · 한도. 비밀번호 값은 없다."""
    return _settings_view(request, db)


@router.put("/settings", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def put_settings(body: MailSettingsRequest, request: Request, db: Session = Depends(get_db)):
    """메일 설정을 저장한다. 비밀번호가 실려 있으면 같은 저장에서 고정 칸에 쓰고, 보낼 수 있는 설정이면 연결 확인을 시작한다."""
    from app.admin.secrets_router import secret_store
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE, VERIFY_TIMEOUT_SECONDS
    from app.jobs.repository import enqueue
    from app.settings.registry import validate_value
    from app.settings.service import apply_setting

    from app.core.secret_slots import SLOT_SMTP_RELAY_PASSWORD

    value = body.model_dump(exclude={"password", "clear_password", "relay_password", "clear_relay_password"})
    for key in ("host", "from_address", "from_name", "username"):
        value[key] = str(value[key] or "").strip()
    value["ca_pem"] = str(value["ca_pem"] or "").strip()
    # 로컬 릴레이 칸: 보내지 않았으면 저장된 값을 그대로 둔다. DKIM 공개키는 서버가 적는 칸이라 저장된 값을 이어 쓰고, 선택자를
    # 바꾸면 비운다(새 선택자의 키를 만들면 다시 적힌다).
    stored_relay = _stored_smtp(db).get("relay") or {}
    if value.get("relay") is None:
        value["relay"] = stored_relay
    else:
        relay = value["relay"]
        relay["dkim_selector"] = str(relay.get("dkim_selector") or "").strip().lower()
        same_selector = relay["dkim_selector"] == str(stored_relay.get("dkim_selector") or "")
        relay["dkim_public"] = str(stored_relay.get("dkim_public") or "") if same_selector else ""
    # 저장 전에 모양부터 본다 - 비밀번호를 먼저 써 놓고 설정이 거절되면 반쪽만 저장된다.
    validate_value(SMTP_SETTING_KEY, value)
    now = request.app.state.clock.now()
    if body.relay_password:
        changed = secret_store(request).write(SLOT_SMTP_RELAY_PASSWORD, body.relay_password)
        record_audit_from_request(
            request, db, action="secret.write", object_type="secret", object_id=SLOT_SMTP_RELAY_PASSWORD,
            after={"changed": changed},
        )
    elif body.clear_relay_password:
        changed = secret_store(request).delete(SLOT_SMTP_RELAY_PASSWORD)
        record_audit_from_request(
            request, db, action="secret.delete", object_type="secret", object_id=SLOT_SMTP_RELAY_PASSWORD,
            after={"changed": changed},
        )
    if body.password:
        changed = secret_store(request).write(PASSWORD_SLOT, body.password)
        record_audit_from_request(
            request, db, action="secret.write", object_type="secret", object_id=PASSWORD_SLOT,
            after={"changed": changed},
        )
    elif body.clear_password:
        changed = secret_store(request).delete(PASSWORD_SLOT)
        record_audit_from_request(
            request, db, action="secret.delete", object_type="secret", object_id=PASSWORD_SLOT,
            after={"changed": changed},
        )
    result = apply_setting(
        db, request.app.state.settings_cache, key=SMTP_SETTING_KEY, value=value,
        updated_by=request.state.user.id, now=now,
    )
    record_audit_from_request(
        request, db, action="mail.settings.update", object_type="mail_settings", object_id=SMTP_SETTING_KEY,
        before=_audit_value(result["before"] if isinstance(result.get("before"), dict) else dict(DEFAULT_SMTP)),
        after=_audit_value(value),
    )
    relay_apply_result = None
    saved = config_from_db(db)
    if saved.local_relay:
        # 켜져 있는 릴레이에는 저장한 설정을 곧바로 다시 적용한다 - 저장이 하나이듯 적용도 저장과 함께다. 꺼져 있으면 화면의
        # 「로컬 릴레이 켜기」가 켠다.
        status, _detail = _helper_status(request, saved)
        if status and status.get("component") == "running":
            relay_apply_result = _apply_relay(request, db, reason="settings")
    verify = None
    if is_sendable(config_from_db(db), _secrets(request)):
        job = enqueue(
            db, job_type=MAIL_VERIFY_JOB_TYPE, payload={"auto": True}, now=now,
            user_id=request.state.user.id, max_attempts=1,
        )
        verify = {"job_id": job.id, "timeout_seconds": VERIFY_TIMEOUT_SECONDS}
    return {**_settings_view(request, db), "health": current_health(request, db), "verify": verify,
            "relay_apply": relay_apply_result}


# ── 발송 기록 ─────────────────────────────────────────────────────────────────


@router.get("/deliveries", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def deliveries(
    status: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    since: str | None = Query(default=None, max_length=32),
    until: str | None = Query(default=None, max_length=32),
    page: PageParams = Depends(),
    sort: SortParams = Depends(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """발송 기록 — 상태 · 종류 · 받는 사람과 제목 검색 · 기간(KST 달력일) · 정렬 · 페이지. 범위 안 사람의 메일만(D-547)."""
    rows, total = list_deliveries(
        db, visible=visible_user_ids(db, principal.management), status=status, kind=kind, q=q, since=since, until=until, sort=sort,
        offset=page.offset, limit=page.page_size,
    )
    return {"items": delivery_views(db, rows), "total": total, "page": page.page, "page_size": page.page_size}


@router.get("/deliveries/{delivery_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def delivery(delivery_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """한 통의 상세. 받는 사람이 관리 범위 밖이면 없는 메일과 같은 404 다(D-547)."""
    return {"delivery": delivery_detail(db, delivery_id, visible=visible_user_ids(db, principal.management))}


def _require_mail_operator(request: Request, db: Session, principal: Principal, what: str, verb: str) -> None:
    """설치 한 벌의 SMTP 계정으로 나가는 동작은 전역 관리 범위만 한다(`send_test` 와 같은 판정)."""
    try:
        require_global_management(principal, what, verb=verb)
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise


@router.post("/deliveries/{delivery_id}/resend", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def resend(
    delivery_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """실패 · 설정 없음 · 취소로 끝난 메일을 다시 보낸다. 비밀번호 재설정과 시험 메일은 409 다."""
    _require_mail_operator(request, db, principal, "메일", "다시 보낼")
    row = resend_delivery(
        db, delivery_id, now=request.app.state.clock.now(),
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request, db, action="mail.resend", object_type="mail_delivery", object_id=row.id,
        after={"status": row.status, "kind": row.kind},
    )
    return {"delivery": delivery_view(row)}


@router.post("/deliveries/{delivery_id}/cancel", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def cancel(
    delivery_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """보내기를 기다리는 메일을 취소한다. 워커가 이미 보내는 중이면 409 다."""
    _require_mail_operator(request, db, principal, "메일", "취소할")
    row = cancel_delivery(db, delivery_id, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="mail.cancel", object_type="mail_delivery", object_id=row.id,
        after={"status": row.status, "kind": row.kind},
    )
    return {"delivery": delivery_view(row)}


@router.post("/resend-unconfigured", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def send_unconfigured(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """설정 전에 쌓인 메일(초대 · 알림, 최대 나이 안)을 보낸다. **사람이 누를 때만** 돈다 - 오래된 메일을 예고 없이
    뿌리지 않는다."""
    _require_mail_operator(request, db, principal, "쌓인 메일", "보낼")
    count = resend_unconfigured(
        db, now=request.app.state.clock.now(),
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request, db, action="mail.requeue_unconfigured", object_type="mail_delivery", object_id=None,
        after={"count": count},
    )
    return {"queued": count}


# ── 시험 메일 (D-554) ─────────────────────────────────────────────────────────


class TestMailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 받는 주소. 비우면 내 계정 주소다. 내 주소가 아니면 메일 설정 권한이 있어야 한다.
    to: str | None = Field(default=None, max_length=254)


def mask_address(address: str) -> str:
    """감사 · 증거에 남기는 가린 주소 — `h****g@goodmit.co.kr`. 앞뒤 한 글자만 남긴다."""
    local, _, domain = address.partition("@")
    if len(local) <= 2:
        return f"{'*' * max(1, len(local))}@{domain}"
    return f"{local[0]}****{local[-1]}@{domain}"


def _valid_recipient(raw: str) -> str:
    """받는 주소 하나. ASCII · 254자 · 주소 하나(쉼표 · 세미콜론 · 줄바꿈 · 공백 없음)."""
    text = (raw or "").strip()
    if not text:
        raise ValidationAppError("받는 주소를 넣으세요.")
    if len(text) > 254 or not text.isascii() or any(ch in text for ch in ",;<>\r\n\t ") or not _ADDRESS.match(text):
        raise ValidationAppError("받는 주소는 name@example.com 모양의 주소 하나여야 합니다.")
    return text


def _limiters(request: Request):
    """시험 메일의 두 리미터(사람당 · 설치 전체). 앱 상태에 없으면(옛 앱 객체) 만들어 둔다."""
    from app.core.ratelimit import RateLimiter

    state = request.app.state
    if getattr(state, "mail_test_user_ratelimiter", None) is None:
        state.mail_test_user_ratelimiter = RateLimiter(
            capacity=TEST_PER_USER[0], refill_per_second=TEST_PER_USER[1], clock=state.clock,
            session_factory=state.session_factory,
        )
    if getattr(state, "mail_test_all_ratelimiter", None) is None:
        state.mail_test_all_ratelimiter = RateLimiter(
            capacity=TEST_PER_INSTALL[0], refill_per_second=TEST_PER_INSTALL[1], clock=state.clock,
            session_factory=state.session_factory,
        )
    return state.mail_test_user_ratelimiter, state.mail_test_all_ratelimiter


@router.post("/test", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def send_test(
    request: Request,
    body: TestMailRequest | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """시험 메일 한 통. 보내지 못하면 그 사실이 응답과 아웃박스에 남는다.

    범위 게이트를 여기 두는 이유: 이 시험은 **설치 한 벌의 SMTP 계정**으로 나간다. 그 설정을 바꿀 수 있는 사람과 그것을 실제로
    써 보는 사람이 다르면, 부서 범위 관리자가 자기가 못 고치는 계정으로 발송을 일으키고 그 계정의 평판과 발송 한도를 쓰게 된다.
    다른 주소로 보내는 것은 메일 설정 권한자만이다(D-554).
    """
    from app.users.models import User

    try:
        # 거절되는 것은 **발송**이다 — 화면의 단추 이름 그대로 말한다.
        require_global_management(principal, "시험 메일", verb="보낼")
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise
    me = request.state.user
    requested = (body.to if body is not None else None) or ""
    to = _valid_recipient(requested) if requested.strip() else (me.email or "")
    if not to:
        raise ValidationAppError("내 계정에 이메일이 없습니다. 받는 주소를 넣으세요.")
    own = to.lower() == (me.email or "").lower()
    if not own and not _can_configure(db, me):
        audit_forbidden_write(request, db, me)
        raise ForbiddenError("다른 주소로 보내려면 시스템 관리자 권한이 필요합니다.")
    per_user, per_install = _limiters(request)
    user_key = f"mail_test:user:{me.id}"
    if not per_user.allow(user_key):
        raise RateLimitedError(
            "시험 메일은 10분에 5통까지 보낼 수 있습니다.", retry_after_seconds=per_user.retry_after_seconds(user_key),
        )
    if not per_install.allow("mail_test:all"):
        raise RateLimitedError(
            "시험 메일은 설치 전체에서 1시간에 20통까지 보낼 수 있습니다.",
            retry_after_seconds=per_install.retry_after_seconds("mail_test:all"),
        )
    if own:
        recipient_id = me.id
    else:
        # 받는 주소가 어떤 사용자의 계정 주소면 그 사람의 메일이다(범위 축). 아니면 비워 두고 전역 관리자만 본다(D-547).
        recipient_id = db.execute(
            select(User.id).where(func.lower(User.email) == to.lower()).limit(1)
        ).scalar_one_or_none()
    now = request.app.state.clock.now()
    row = queue_mail(
        db,
        kind=KIND_TEST,
        to_email=to,
        recipient_user_id=recipient_id,
        subject=mail_subject(db, "메일 발송 시험"),
        # 시험을 시작한 사람(받는 사람 재검사가 그 사람의 권한을 다시 본다). 사람이 쓴 글은 없다.
        params={"sender_id": me.id, "own": own},
        now=now,
        secret_provider=getattr(request.app.state, "secret_provider", None),
    )
    record_audit_from_request(
        request,
        db,
        action="mail.test_send",
        object_type="mail_delivery",
        object_id=row.id,
        # 주소는 가려서 남긴다(D-554) - 감사를 읽는 사람이 남의 회사 메일 주소 목록을 얻지 않게.
        after={"status": row.status, "kind": row.kind, "to_domain": to.partition("@")[2].lower(),
               "to_masked": mask_address(to), "own": own},
    )
    from app.mail.labels import test_result_sentence

    return {
        "delivery": delivery_view(row),
        "mail": current_mail_status(request, db),
        "sentence": test_result_sentence(getattr(config_from_db(db), "mode", "external")),
    }


class InboxConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str = Field(min_length=1, max_length=64)
    received: bool = True


@router.post("/inbox-confirm", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def inbox_confirm(
    body: InboxConfirmRequest, request: Request, db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """시험 메일 한 통을 받은 편지함에서 확인했다(또는 못 찾았다)고 **사람이** 기록한다(D-560 ⑦).

    제품은 도착을 잴 수 없다 — 이 기록이 일곱째 단계의 유일한 근거다. 접수된(`sent`) 시험 메일만 대상이고, 범위 밖 메일은 없는
    것과 같다(404). 감사에는 메일 id 와 결과만 남는다(주소는 가린다).
    """
    from app.mail import progress

    _require_mail_operator(request, db, principal, "받은 편지함 확인", "기록할")
    detail = delivery_detail(db, body.delivery_id, visible=visible_user_ids(db, principal.management))
    if detail.get("kind") != KIND_TEST:
        raise ValidationAppError("시험 메일만 받은 편지함 확인을 기록할 수 있습니다.")
    if detail.get("status") != MAIL_SENT:
        raise ConflictError("다음 서버가 아직 접수하지 않은 시험 메일입니다. 접수된 뒤에 확인하세요.")
    now = request.app.state.clock.now()
    record = progress.record_inbox(db, delivery_id=body.delivery_id, received=body.received,
                                   user_id=request.state.user.id, now=now)
    record_audit_from_request(
        request, db, action="mail.inbox_confirm", object_type="mail_delivery", object_id=body.delivery_id,
        after={"received": bool(body.received), "to_masked": mask_address(detail.get("to_email") or "")},
    )
    db.commit()
    return {"inbox": record, "status": status(request, db, principal)}


# ── 연결 확인 (계획 3.3, D-546) ──────────────────────────────────────────────


@router.post("/verify", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def start_verify(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """메일 서버 연결 확인을 큐에 넣고 **곧바로** 잡 id 를 돌려준다. 메일은 보내지 않는다(봉투 시험까지)."""
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE, VERIFY_TIMEOUT_SECONDS
    from app.jobs.repository import enqueue

    _require_mail_operator(request, db, principal, "메일 연결", "확인할")
    job = enqueue(
        db, job_type=MAIL_VERIFY_JOB_TYPE, payload={}, now=request.app.state.clock.now(),
        user_id=request.state.user.id, max_attempts=1,
    )
    record_audit_from_request(
        request, db, action="mail.verify", object_type="mail_settings", object_id=job.id, after={"queued": True},
    )
    return {"job_id": job.id, "status": job.status, "timeout_seconds": VERIFY_TIMEOUT_SECONDS}


@router.get("/verify/{job_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def verify_result(job_id: str, request: Request, db: Session = Depends(get_db)):
    """연결 확인 하나의 결과. 아직 안 끝났으면 **끝난 척하지 않는다**(`result` 가 null 이다)."""
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE
    from app.jobs.models import (
        STATUS_CANCELLED,
        STATUS_FAILED,
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,
        Job,
    )

    job = db.get(Job, job_id)
    if job is None or job.job_type != MAIL_VERIFY_JOB_TYPE:
        raise NotFoundError("연결 확인 기록을 찾을 수 없습니다.")
    result = None
    if job.status == STATUS_SUCCEEDED:
        result = {"ok": True, "message": "메일 서버 연결을 확인했습니다. 메일은 보내지 않았습니다."}
    elif job.status == STATUS_FAILED:
        result = {"ok": False, "message": (job.last_error or "").strip() or "메일 서버 연결을 확인하지 못했습니다."}
    elif job.status == STATUS_CANCELLED:
        result = {"ok": False, "message": "연결 확인이 취소됐습니다."}
    return {
        "job_id": job.id,
        "status": job.status,
        "pending": job.status in (STATUS_QUEUED, STATUS_RUNNING),
        "result": result,
        "health": current_health(request, db),
    }



# ── ClovirAssist 로컬 릴레이 (M7, D-551) ─────────────────────────────────────
#
# 켜고 끄기 · DKIM 키 · 준비 점검 · 지금 다시 보내기. 모두 메일 설정 권한(`SYSTEM_CONFIGURE`)이고 쓰기는 CSRF 를 지난다(라우터 의존).
# 특권 헬퍼에 넘기는 인자는 **저장된 설정에서만** 만든다(`config.helper_params`) - 사람이 인자를 고르는 문이 없고, 인수(takeover) 같은
# 인자도 없다. 기존 메일 발송 구성이 있는 서버에서는 헬퍼가 거절한다.

COMPONENT_WORDS = {
    "ready": ("구성 요소 준비됨", "이 서버에 설치돼 있고 꺼져 있습니다."),
    "running": ("동작 중", "로컬 릴레이가 메일을 받아 바깥으로 전달하고 있습니다."),
    "stopped": ("멈춤", "메일 발송 구성 요소가 동작하지 않습니다."),
    "not_installed": ("설치되지 않음", "이 서버에는 로컬 릴레이 구성 요소가 설치되지 않았습니다."),
    "foreign": ("기존 메일 발송 구성이 있음",
                "이 서버에는 기존 메일 발송 구성이 있습니다. ClovirAssist 로컬 릴레이가 자동으로 구성되지 않았습니다."),
    "unavailable": ("확인할 수 없음", "이 서버의 시스템 도우미에 닿지 못해 로컬 릴레이 상태를 알 수 없습니다."),
}
COMPONENT_HELP = {
    "not_installed": "외부 SMTP 사용을 고르거나 서버에서 구성 요소를 설치하세요.",
    "foreign": "그 구성을 쓰려면 '외부 SMTP 사용'에서 그 서버를 지정하세요.",
    "stopped": "로컬 릴레이를 다시 켜 보세요. 계속 멈추면 기술 정보를 확인하세요.",
}
DEFAULT_DKIM_SELECTOR = "ca1"


def _sysops(request: Request):
    existing = getattr(request.app.state, "sysops_client", None)
    if existing is not None:
        return existing
    from app.sysops.client import SysopsClient

    return SysopsClient()


def _helper_status(request: Request, config) -> tuple[dict | None, str | None]:
    params = {}
    if config.relay.dkim_selector and config.sender_domain:
        params = {"dkim": {"domain": config.sender_domain, "selector": config.relay.dkim_selector}}
    reply = _sysops(request).call("mailrelay.status", params)
    if not (reply.available and reply.ok):
        return None, reply.detail
    return reply.data or {}, None


def _component_view(status: dict | None, config, detail: str | None = None) -> dict:
    from app.mail import relay_files

    state = (status or {}).get("component") or "unavailable"
    label, message = COMPONENT_WORDS.get(state, COMPONENT_WORDS["unavailable"])
    applied = (status or {}).get("applied_relay_fingerprint")
    wanted = None
    try:
        wanted = relay_files.relay_fingerprint(relay_files.normalize_params(helper_params(config)))
    except relay_files.RelayParamsError:
        wanted = None
    return {
        "state": state,
        "label": label,
        "message": message,
        "help": COMPONENT_HELP.get(state),
        # 저장한 설정이 아직 켜진 릴레이에 적용되지 않았는가(다시 적용이 필요한가).
        "stale": state == "running" and bool(wanted) and applied != wanted,
        # 화면은 「기술 정보」 안에서만 그린다 - 꾸러미 · 서비스 · 듣는 소켓 · 기존 구성 여부.
        "technical": {
            "packages": status.get("packages"), "other_mta": status.get("other_mta"), "config": status.get("config"),
            "services": status.get("services"), "listeners": status.get("listeners"),
            "queue_count": status.get("queue_count"),
        } if status else {"helper": detail},
    }


def _relay_password_state(request: Request) -> dict:
    from app.core.secret_refs import STATUS_CONFIGURED
    from app.core.secret_slots import SLOT_SMTP_RELAY_PASSWORD

    provider = _secrets(request)
    stored = bool(provider) and provider.status(SLOT_SMTP_RELAY_PASSWORD) == STATUS_CONFIGURED
    return {"stored": stored}


def _relay_view(request: Request, db: Session) -> dict:
    from app.mail import relay_readiness, relay_tracking

    config = config_from_db(db)
    status, detail = _helper_status(request, config)
    readiness = relay_readiness.load(db)
    if readiness and readiness.get("fingerprint") != config.relay_fingerprint:
        # 점검한 뒤 설정이 바뀌었다 - 옛 결과를 지금 설정의 것처럼 보이지 않는다.
        readiness = {**readiness, "stale": True}
    dkim = (status or {}).get("dkim")
    return {
        "mode": config.mode,
        "component": _component_view(status, config, detail),
        "config": config.relay.as_dict(),
        "password": _relay_password_state(request),
        "dkim": {
            "selector": config.relay.dkim_selector or None,
            "record_name": (dkim or {}).get("record_name"),
            "public": config.relay.dkim_public or (dkim or {}).get("public"),
            "key_exists": bool((dkim or {}).get("key_exists")),
        },
        "readiness": readiness,
        "outer": relay_tracking.last_outcome(db),
    }


def _require_local_relay(config) -> None:
    if not config.local_relay:
        raise ConflictError("보내는 방법을 ClovirAssist 로컬 릴레이로 저장한 뒤에 쓸 수 있습니다.")


def _apply_relay(request: Request, db: Session, *, reason: str) -> dict:
    """저장된 설정으로 헬퍼 `mailrelay.apply` 를 부르고 감사에 남긴다. 결과 한 덩어리를 돌려준다(예외 없음)."""
    from app.mail import relay_files

    config = config_from_db(db)
    try:
        params = relay_files.normalize_params(helper_params(config))
    except relay_files.RelayParamsError as exc:
        raise ValidationAppError(str(exc)) from None
    reply = _sysops(request).call("mailrelay.apply", params)
    record_audit_from_request(
        request, db, action="mail.relay.apply", object_type="mail_settings", object_id=SMTP_SETTING_KEY,
        after={"reason": reason, "available": reply.available, "ok": reply.ok, "changed": reply.changed,
               "rolled_back": reply.rolled_back, "detail": reply.detail},
        result="success" if reply.ok else "failure",
    )
    return {"ok": reply.ok, "available": reply.available, "message": reply.detail,
            "technical": (reply.data or {}).get("technical") if not reply.ok else None}


def _start_verify(request: Request, db: Session) -> dict | None:
    from app.jobs.handlers.mail_verify import MAIL_VERIFY_JOB_TYPE, VERIFY_TIMEOUT_SECONDS
    from app.jobs.repository import enqueue

    if not is_sendable(config_from_db(db), _secrets(request)):
        return None
    job = enqueue(
        db, job_type=MAIL_VERIFY_JOB_TYPE, payload={"auto": True}, now=request.app.state.clock.now(),
        user_id=request.state.user.id, max_attempts=1,
    )
    return {"job_id": job.id, "timeout_seconds": VERIFY_TIMEOUT_SECONDS}


@router.get("/relay", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_state(request: Request, db: Session = Depends(get_db)):
    """로컬 릴레이 한 벌 — 구성 요소 상태 · 설정 · DKIM · 준비 점검 결과 · 최근 바깥 전달."""
    return _relay_view(request, db)


@router.post("/relay/apply", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_apply(request: Request, db: Session = Depends(get_db)):
    """로컬 릴레이를 켜거나 저장한 설정을 다시 적용한다. 성공하면 앱 → 릴레이 연결 확인을 시작한다."""
    config = config_from_db(db)
    _require_local_relay(config)
    result = _apply_relay(request, db, reason="manual")
    verify = _start_verify(request, db) if result["ok"] else None
    return {"result": result, "relay": _relay_view(request, db), "verify": verify, "health": current_health(request, db)}


@router.post("/relay/disable", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_disable(request: Request, db: Session = Depends(get_db)):
    """로컬 릴레이를 끈다. 큐에 남은 메일은 다시 켤 때까지 나가지 않는다(화면이 먼저 확인을 받는다)."""
    reply = _sysops(request).call("mailrelay.disable", {})
    record_audit_from_request(
        request, db, action="mail.relay.disable", object_type="mail_settings", object_id=SMTP_SETTING_KEY,
        after={"available": reply.available, "ok": reply.ok, "detail": reply.detail},
        result="success" if reply.ok else "failure",
    )
    return {"result": {"ok": reply.ok, "available": reply.available, "message": reply.detail},
            "relay": _relay_view(request, db)}


class RelayDkimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str | None = Field(default=None, max_length=63)


@router.post("/relay/dkim", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_dkim(request: Request, body: RelayDkimRequest | None = None, db: Session = Depends(get_db)):
    """DKIM 키를 만든다(이미 있으면 그대로 쓴다). 공개키와 선택자를 설정에 적는다 - 개인키는 서버 밖으로 나가지 않는다."""
    from app.mail import relay_files
    from app.settings.service import apply_setting

    config = config_from_db(db)
    _require_local_relay(config)
    if not config.sender_domain:
        raise ValidationAppError("보내는 사람 주소를 먼저 저장하세요. 그 도메인으로 키를 만듭니다.")
    selector = ((body.selector if body else None) or config.relay.dkim_selector or DEFAULT_DKIM_SELECTOR).strip().lower()
    if not relay_files.SELECTOR_RE.match(selector):
        raise ValidationAppError("DKIM 선택자는 영문 소문자와 숫자, 하이픈으로 씁니다.")
    reply = _sysops(request).call("mailrelay.dkim_generate", {"domain": config.sender_domain, "selector": selector})
    record_audit_from_request(
        request, db, action="mail.relay.dkim", object_type="mail_settings", object_id=SMTP_SETTING_KEY,
        after={"selector": selector, "domain": config.sender_domain, "ok": reply.ok, "changed": reply.changed},
        result="success" if reply.ok else "failure",
    )
    if not (reply.available and reply.ok):
        raise ConflictError(reply.detail or "DKIM 키를 만들지 못했습니다.")
    value = _stored_smtp(db)
    relay = dict(value.get("relay") or {})
    relay.update({"dkim_selector": selector, "dkim_public": str((reply.data or {}).get("public") or "")})
    value["relay"] = relay
    apply_setting(db, request.app.state.settings_cache, key=SMTP_SETTING_KEY, value=value,
                  updated_by=request.state.user.id, now=request.app.state.clock.now())
    return {"result": {"ok": True, "message": reply.detail}, "relay": _relay_view(request, db)}


class RelayCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_domain: str | None = Field(default=None, max_length=253)


@router.post("/relay/check", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_check(request: Request, body: RelayCheckRequest | None = None, db: Session = Depends(get_db)):
    """준비 점검을 큐에 넣는다(대화형 레인). 메일은 보내지 않는다."""
    from app.jobs.handlers.mail_relay_check import MAIL_RELAY_CHECK_JOB_TYPE
    from app.jobs.repository import enqueue
    from app.mail import relay_files

    config = config_from_db(db)
    _require_local_relay(config)
    probe = ((body.probe_domain if body else None) or "").strip().lower()
    if probe and not relay_files.DOMAIN_RE.match(probe):
        raise ValidationAppError("시험할 받는 도메인은 example.com 같은 이름이어야 합니다.")
    job = enqueue(
        db, job_type=MAIL_RELAY_CHECK_JOB_TYPE, payload={"probe_domain": probe or None},
        now=request.app.state.clock.now(), user_id=request.state.user.id, max_attempts=1,
    )
    record_audit_from_request(
        request, db, action="mail.relay.check", object_type="mail_settings", object_id=job.id,
        after={"probe_domain": probe or None},
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/relay/check/{job_id}", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_check_result(job_id: str, request: Request, db: Session = Depends(get_db)):
    from app.jobs.handlers.mail_relay_check import MAIL_RELAY_CHECK_JOB_TYPE
    from app.jobs.models import STATUS_FAILED, STATUS_QUEUED, STATUS_RUNNING, Job
    from app.mail import relay_readiness

    job = db.get(Job, job_id)
    if job is None or job.job_type != MAIL_RELAY_CHECK_JOB_TYPE:
        raise NotFoundError("준비 점검 기록을 찾을 수 없습니다.")
    pending = job.status in (STATUS_QUEUED, STATUS_RUNNING)
    return {
        "job_id": job.id, "status": job.status, "pending": pending,
        "error": (job.last_error or "").strip() or None if job.status == STATUS_FAILED else None,
        "readiness": None if pending else relay_readiness.load(db),
    }


@router.post("/relay/flush", dependencies=[Depends(require_permission(SYSTEM_CONFIGURE))])
def relay_flush(request: Request, db: Session = Depends(get_db)):
    """큐에 남은 메일을 지금 다시 보내도록 한다(받는 쪽이 잠시 거절했던 메일)."""
    reply = _sysops(request).call("mailrelay.flush", {})
    record_audit_from_request(
        request, db, action="mail.relay.flush", object_type="mail_settings", object_id=SMTP_SETTING_KEY,
        after={"available": reply.available, "ok": reply.ok}, result="success" if reply.ok else "failure",
    )
    if not (reply.available and reply.ok):
        raise ConflictError(reply.detail or "큐를 다시 보내지 못했습니다.")
    return {"result": {"ok": True, "message": reply.detail}}


def _stored_smtp(db: Session) -> dict:
    """저장된 `smtp` 값(기본값으로 채운 사본). 서버가 적는 칸(DKIM 공개키)을 고칠 때 쓴다."""
    import copy
    import json as _json

    from app.settings.models import AppSetting

    row = db.get(AppSetting, SMTP_SETTING_KEY)
    value = copy.deepcopy(DEFAULT_SMTP)
    if row is not None:
        try:
            stored = _json.loads(row.value_json)
        except (TypeError, ValueError):
            stored = None
        if isinstance(stored, dict):
            value.update({k: v for k, v in stored.items() if k in DEFAULT_SMTP})
    return value

# ── 메일 모양 미리 보기 (D-549) ──────────────────────────────────────────────


@router.get("/templates", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def templates():
    """미리 볼 수 있는 메일 종류(열 가지)."""
    from app.mail.samples import catalog

    return {"items": catalog()}


@router.get("/templates/{kind}/preview", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def template_preview(kind: str, request: Request, db: Session = Depends(get_db)):
    """표본 한 통 — 제목 · 평문 · HTML. **표본만 쓴다**(실제 사용자 · 티켓 · 토큰이 없다, `app/mail/samples.py`)."""
    from app.mail.content import logo_data_uri, product_name, support_email
    from app.mail.samples import preview

    # 미리 보기는 sandbox iframe 이라 `cid:` 그림을 그릴 수 없다 - 같은 PNG 를 data 주소로 넣는다(실제 메일은 CID, D-561).
    rendered = preview(
        kind, product=product_name(db), base_url=str(getattr(request.app.state.settings, "app_base_url", "") or ""),
        support=support_email(db), logo_src=logo_data_uri(),
    )
    if rendered is None:
        raise NotFoundError("미리 볼 수 없는 메일 종류입니다.")
    return {"kind": kind, "subject": rendered.subject, "text": rendered.text, "html": rendered.html}
