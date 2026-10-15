"""운영 콘솔의 시스템 설정 API (§S, 9-6).

## 왜 `CONSOLE_WRITE_ROLES` 가 아니라 `ROLE_SYSTEM_ADMIN` 인가

`CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고, 이 제품의 `admin` 은 **부서 범위로 좁혀질 수
있다**(`admin_scope="dept"`). 부서 관리자는 자기 부서 사람을 관리하는 사람이지 서버의 DNS·
호스트 이름·TLS 인증서를 바꾸는 사람이 아니다. 여기서 바뀌는 것은 조직 단위가 아니라
**서버 한 대 전체**라 범위라는 개념 자체가 없다. 그래서 범위가 없는 역할만 통과시킨다.

## 여기서도 검증하지만, **믿는 검증은 헬퍼 쪽이다**

이 라우터의 검증은 사용자에게 빠르고 친절한 오류를 주기 위한 것이다. 진짜 경계는 헬퍼
안에 있다(`app/sysops/actions.py`). 웹이 뚫렸다는 가정에서도 헬퍼가 버텨야 하므로,
웹에서 한 검증을 헬퍼가 다시 한다 - 중복이 아니라 **다른 목적**이다.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.authz.permissions import SYSTEM_CONFIGURE
from app.core.deps import get_db, require_csrf, require_permission
from app.sysops import actions_domain
from app.sysops.actions import UnknownActionError, list_actions
from app.sysops.client import STATUS_OK, SysopsClient

router = APIRouter(
    prefix="/api/admin/system",
    tags=["admin-system"],
    dependencies=[Depends(require_csrf), Depends(require_permission(SYSTEM_CONFIGURE))],
)

OBJECT_TYPE = "system_setting"

# 비밀 값 액션은 이 범용 경로로 부를 수 없다. 전용 라우터(`app/admin/secrets_router.py`)가
# 감사 모양과 슬롯 검사를 따로 갖고 있다 - 여기로 열어 두면 그 검사를 우회하는 두 번째 문이 된다.
# 로컬 릴레이 동작(`mailrelay.*`, D-551)도 같다: 인자는 메일 API 가 저장된 설정에서 만든다(`app/mail/router.py`).
PRIVATE_ACTION_PREFIXES = ("secret.", "mailrelay.")

# 대표 주소 바꾸기(D-573)는 인증서 · nginx · 뒷단 유닛 재시작 · 자체 확인을 한 번에 한다. 도우미의 기본 기다림(90초)보다 길게,
# nginx 의 `proxy_read_timeout`(180초, deploy/nginx/clovirassist.conf)보다는 짧게 기다린다.
DOMAIN_APPLY_TIMEOUT = 170
DOMAIN_APPLY = "domain.apply"
RECENT_APPLIES = 5


def _public_actions() -> list[dict]:
    return [a for a in list_actions() if not a["name"].startswith(PRIVATE_ACTION_PREFIXES)]


class ActionRequest(BaseModel):
    params: dict = {}


def _client(request: Request) -> SysopsClient:
    # 앱 상태에 있으면 그것을 쓴다(테스트가 가짜를 꽂는 자리). 없으면 기본 경로.
    existing = getattr(request.app.state, "sysops_client", None)
    return existing or SysopsClient()


@router.get("")
def system_overview(request: Request):
    """시스템 정보 + **도우미를 쓸 수 있는지**.

    도우미가 없어도 200 이다. 없다는 것은 오류가 아니라 이 서버의 상태이고, 화면은 그
    사실을 그대로 말해야 한다. 500 을 주면 화면이 "일시적 오류" 로 읽고 재시도만 반복한다.
    """
    reply = _client(request).probe()
    info = reply.data if reply.available and reply.ok else {}
    return {
        "available": reply.available,
        "status": reply.status,
        "detail": reply.detail,
        "info": info,
        "certificate": _certificate_view(request),
        "actions": _public_actions(),
        # 서비스 주소 카드(D-573): 지금 이 화면을 연 주소와 서버가 아는 대표 주소 · 별칭을 나란히 보인다.
        "request": request_view(request),
        "domain": info.get("domain") if isinstance(info.get("domain"), dict) else None,
    }


def request_view(request: Request) -> dict:
    """이 요청이 들어온 주소 — 앞단 프록시가 붙인 `X-Forwarded-Host` 를 먼저, 없으면 `Host` 를 본다.

    화면에 보여 주기만 한다(권한 · 링크 생성에 쓰지 않는다). 앞단 nginx 가 `X-Forwarded-Proto` 는 덮어쓰지만 `X-Forwarded-Host` 는
    지나가게 두므로 사용자가 꾸민 값일 수 있다 — 그래서 판정이 아니라 「지금 접속한 주소」 표시로만 쓴다."""
    forwarded = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    authority = (forwarded or request.headers.get("host") or request.url.netloc or "").strip().lower()[:255]
    try:
        host = urlsplit(f"//{authority}").hostname or authority
    except ValueError:
        host = authority
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    scheme = proto if proto in ("http", "https") else request.url.scheme
    return {"host": host, "authority": authority, "scheme": scheme, "url": f"{scheme}://{authority}" if authority else None}


def _recent_applies(db: Session) -> list[dict]:
    """감사에 남은 최근 대표 주소 적용(성공 · 실패). 인자는 감사에 없다 — 남는 것은 결과와 문장뿐이다(개인키가 인자로 올 수 있다)."""
    from app.audit.models import AuditLog
    from app.users.models import User

    rows = db.execute(
        select(AuditLog).where(
            AuditLog.action == "system_action", AuditLog.object_type == OBJECT_TYPE, AuditLog.object_id == DOMAIN_APPLY,
        ).order_by(AuditLog.created_at.desc()).limit(RECENT_APPLIES)
    ).scalars().all()
    names: dict[str, str] = {}
    ids = {r.user_id for r in rows if r.user_id}
    if ids:
        for user in db.execute(select(User).where(User.id.in_(ids))).scalars().all():
            names[user.id] = user.display_name
    out = []
    for r in rows:
        try:
            after = json.loads(r.after_json) if r.after_json else {}
        except ValueError:
            after = {}
        out.append({
            "at": r.created_at.isoformat() if r.created_at else None,
            "ok": r.result == "success",
            "detail": after.get("detail"),
            "rolled_back": bool(after.get("rolled_back")),
            "actor": names.get(r.user_id),
        })
    return out


@router.get("/domain")
def domain_preview(
    request: Request,
    db: Session = Depends(get_db),
    host: str | None = Query(None, max_length=260),
    aliases: str | None = Query(None, max_length=1600),
    resolvers: str | None = Query(None, max_length=200),
):
    """서비스 주소 미리 확인(`domain.preview`, 읽기). 감사에 남기지 않는다 — 바꾸는 것이 없다.

    값이 틀리면 도우미까지 가지 않고 여기서 422 로 답한다(같은 검증 함수를 도우미도 다시 돈다). 비교할 공개 DNS 를 주지 않으면 메일
    설정의 「비교할 공개 DNS」를 쓴다 — 공개 해석기에는 관리자가 넣은 주소로만 묻는다(`app/mail/dns.py` 머리말과 같은 허용 목록)."""
    params = {"host": host or None, "aliases": aliases or None, "resolvers": resolvers or None}
    actions_domain.normalize_preview(params)
    if not params["resolvers"]:
        params["resolvers"] = _mail_compare_resolvers(db)
    reply = _client(request).call("domain.preview", params)
    return {
        "available": reply.available,
        "status": reply.status,
        "ok": reply.ok,
        "detail": reply.detail,
        "preview": reply.data if reply.status == STATUS_OK else {},
        "recent_applies": _recent_applies(db),
        "request": request_view(request),
    }


def _mail_compare_resolvers(db: Session) -> list[str]:
    from app.mail.config import config_from_db

    try:
        return list(config_from_db(db).relay.compare_resolvers)[: actions_domain.MAX_RESOLVERS]
    except Exception:  # noqa: BLE001 - 메일 설정을 못 읽어도 미리 확인은 이 서버 해석기만으로 한다
        return []


def _certificate_view(request: Request) -> dict:
    """TLS 인증서의 **현재 상태**. 도우미가 없어도 답할 수 있다.

    지시 33 은 "버튼을 누르기 전에 현재 설정을 이해할 수 있어야 한다" 를 요구한다. 그런데
    `system.info` 는 호스트 이름·타임존·시각 동기화만 준다 - 인증서 교체 버튼 옆에 놓을
    현재 값이 없었다. 만료일 판정은 이미 대시보드가 쓰는 함수가 있으므로(두 화면이 서로 다른
    날짜를 말하지 않도록) 그것을 그대로 부른다. 파일 경로는 내보내지 않는다(지시 36).
    """
    from app.health.service import cert_days_remaining, is_self_signed_cert

    settings = request.app.state.settings
    days = cert_days_remaining(settings, request.app.state.clock.now())
    return {
        "known": days is not None,
        "days_remaining": days,
        "self_signed": is_self_signed_cert(settings),
    }


@router.post("/{action_name}")
def run_action(
    action_name: str,
    body: ActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """시스템 동작 하나를 실행한다.

    성공·실패·되돌림을 **전부 감사에 남긴다.** 실패도 남기는 이유: 인증서 교체 실패처럼
    되돌아간 시도는 나중에 "그때 무슨 일이 있었나" 를 재구성할 유일한 단서다.
    ⚠️ `body.params` 는 감사에 넣지 않는다 - 인증서 개인키가 들어 있다.
    """
    if action_name.startswith(PRIVATE_ACTION_PREFIXES):
        raise UnknownActionError()
    timeout = None
    if action_name == DOMAIN_APPLY:
        # 값이 틀리면 도우미에 닿기 전에 친절한 422 로 답한다(도우미도 같은 함수로 다시 거른다 — 그쪽이 경계다).
        actions_domain.normalize_apply(body.params)
        timeout = DOMAIN_APPLY_TIMEOUT
    client = _client(request)
    # 기다림을 늘릴 때만 `timeout` 을 넘긴다 — 다른 동작은 예전과 같은 호출 모양이다(시험의 가짜 도우미도 그 모양을 쓴다).
    reply = client.call(action_name, body.params, timeout=timeout) if timeout else client.call(action_name, body.params)

    record_audit_from_request(
        request, db,
        action="system_action",
        object_type=OBJECT_TYPE,
        object_id=action_name,
        after={
            "available": reply.available,
            "ok": reply.ok,
            "changed": reply.changed,
            "rolled_back": reply.rolled_back,
            "detail": reply.detail,
        },
        result="success" if reply.ok else "failure",
    )
    db.commit()

    return {
        "available": reply.available,
        "status": reply.status,
        "ok": reply.ok,
        "changed": reply.changed,
        "rolled_back": reply.rolled_back,
        "detail": reply.detail,
        "data": reply.data if reply.status == STATUS_OK else {},
    }
