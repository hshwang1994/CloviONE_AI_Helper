"""항목별 상태 판정 - 이미 있는 것을 읽는다 (9-3, P3 · 계획 3.5, D-520).

## 새 판정을 만들지 않는다

여기서 하는 일은 **판단이지 수집이 아니다.** 설치처 고유 설정은
`app/core/tenant_config.py` 가, 시크릿 파일 유무는 `app/core/secret_refs.py` 가, 인증서
만료는 `app/health/service.py` 가, 메일 발송의 건강은 `app/mail/health.py` 가, AI 연결은
`app/ai/runtime.py::AiRuntime.status` 가, 연동의 헬스는 레지스트리 행이 이미 알고 있다. 이 파일은 그 사실들을 읽어
**"됨 / 안 됨 / 확인 불가"** 세 마디로 번역할 뿐이다.

판정을 여기서 새로 만들면 두 벌이 된다. 두 벌이 되면 한쪽만 고쳐지고, 그러면 "설정했다는데
안 된다" 가 정확히 다시 생긴다.

## 요청 안에서 네트워크를 쓰지 않는다

메일과 AI 는 **저장된 상태**만 읽는다(연결 확인과 실제 발송 · 호출이 적어 둔 결과). 이 판정은 모든 관리자의 상태
폴링에서 돌기 때문에, 여기서 서버에 붙으면 화면을 열 때마다 바깥으로 호출이 나간다.

## 왜 "안 됨" 과 "확인 불가" 를 나누는가

  * **안 됨**(`todo`) 은 사람이 할 일이다. 화면은 무엇을 하라고 말할 수 있다.
  * **확인 불가**(`unknown`) 는 물어볼 일이다. 앱이 있는 자리에서는 알 수 없다.

둘을 합치면 화면은 앞단 프록시가 TLS 를 끊는 정상 설치를 빨갛게 세우고 "인증서를 넣으세요"
라고 말한다. 그 말을 따르면 안 되는데도. 반대로 확인 불가를 초록으로 뭉개면 아무도 안 되는
설치가 다 됐다고 나온다. 둘 다 겪었기 때문에 상태를 셋으로 둔다. 선택 항목을 「사용하지 않음」으로 표시하면 넷째
상태(`skipped`)가 된다 - 그 판정은 체크리스트가 한다(`checklist.py`).

## 링크는 서버가 준다

항목마다 고치는 화면으로 가는 주소(`href`)와 그 이름(`link_label`)을 판정이 함께 준다. 같은 항목이라도 상태마다 가야
할 곳이 다르다 - 메일이 비어 있으면 설정 표의 그 줄, 확인 전이거나 실패하면 메일 발송 화면이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_refs import FileSecretReferenceProvider

STATE_DONE = "done"
STATE_TODO = "todo"
STATE_UNKNOWN = "unknown"
# 선택 항목을 「사용하지 않음」으로 표시했다(D-520). 체크리스트가 정한다.
STATE_SKIPPED = "skipped"

LINK_USERS = ("#/users", "사용자 화면 열기")
LINK_DEPARTMENTS = ("#/departments", "부서 화면 열기")
LINK_MAIL_SETTING = ("#/mail?tab=settings", "메일 설정 열기")
LINK_MAIL_SCREEN = ("#/mail?tab=settings", "메일 화면 열기")
LINK_AI = ("#/ai-connection", "AI 연결 열기")
LINK_DIAGNOSTICS_INTEGRATIONS = ("#/diagnostics", "진단에서 연동 상태 보기")
LINK_DIAGNOSTICS_TLS = ("#/diagnostics", "진단에서 인증서 확인")
# 인증서 만료가 이만큼 가까우면 다시 할 일이다.
TLS_RENEW_DAYS = 14


@dataclass(frozen=True)
class Outcome:
    """항목 하나의 판정 결과.

    `action` 과 `question` 은 **동시에 채우지 않는다.** 셋 중 무엇인지는 상태가 말하고,
    사람이 다음에 할 행동은 둘 중 하나만 말해야 한다.

    `configured` 는 관리자가 이 항목에 무언가를 넣었는가다. 「사용하지 않음」은 비어 있을 때만 뜻이 있다 - 값을 채우면
    선택과 무관하게 실제 상태를 보인다(D-520).
    """

    state: str
    detail: str
    action: str | None = None
    question: str | None = None
    href: str | None = None
    link_label: str | None = None
    checked_at: str | None = None
    configured: bool = True


def _done(detail: str, *, link=None, checked_at=None) -> Outcome:
    return Outcome(state=STATE_DONE, detail=detail, href=link[0] if link else None,
                   link_label=link[1] if link else None, checked_at=checked_at)


def _todo(detail: str, action: str, *, link=None, checked_at=None, configured=True) -> Outcome:
    return Outcome(state=STATE_TODO, detail=detail, action=action, href=link[0] if link else None,
                   link_label=link[1] if link else None, checked_at=checked_at, configured=configured)


def _unknown(detail: str, question: str, *, link=None, checked_at=None) -> Outcome:
    return Outcome(state=STATE_UNKNOWN, detail=detail, question=question, href=link[0] if link else None,
                   link_label=link[1] if link else None, checked_at=checked_at)


@dataclass(frozen=True)
class ProbeContext:
    """판정에 필요한 것 전부. 라우터가 앱 상태에서 꺼내 한 번만 만든다."""

    db: Session
    settings: Settings
    secrets: FileSecretReferenceProvider
    # 이미 따뜻한 app.state.settings_cache. 없으면 관리 콘솔에서 바꾼 값을 못 보고
    # env 만 읽어 "설정 안 함" 이라고 잘못 말한다(tenant_config.py 의 같은 주의).
    effective: dict
    # 프로세스에 하나뿐인 Gateway(`app.state.ai_gateway`). 여기서 새로 만들면 임베딩
    # Adapter 가 매번 ONNX 세션을 열고(S1 실측 2.3초), 무엇보다 **화면이 실제로 쓰는
    # 것과 다른 객체**를 재게 된다. None 이면 설정에서 만든다(스크립트 호출부).
    gateway: object | None = None
    # 프로세스에 하나뿐인 AI 런타임(`app.state.ai_runtime`, D-515). 답변 생성의 판정은 여기서 온다.
    runtime: object | None = None


# ── 관리자 계정 ──────────────────────────────────────────────────────────────


def probe_admin_account(ctx: ProbeContext) -> Outcome:
    from app.users.models import ROLE_SYSTEM_ADMIN, User

    rows = (
        ctx.db.execute(
            select(User).where(
                User.role == ROLE_SYSTEM_ADMIN,
                User.active.is_(True),
                User.archived_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        # 이 화면은 시스템 관리자만 연다 - 사람이 보는 자리에서는 닿지 않는 판정이지만 API 로는 닿는다.
        return _todo(
            "활성 시스템 관리자 계정이 없습니다.",
            "시스템 관리자 역할의 활성 계정을 하나 이상 만드세요.",
            link=LINK_USERS,
        )
    if all(row.must_change_password for row in rows):
        return _todo(
            f"시스템 관리자 {len(rows)}명이 모두 초기 임시 비밀번호 상태입니다.",
            "관리자 계정으로 한 번 로그인해 비밀번호를 바꾸세요.",
            link=LINK_USERS,
        )
    return _done(f"시스템 관리자 {len(rows)}명이 있습니다.", link=LINK_USERS)


# ── 메일(SMTP) 발송 ──────────────────────────────────────────────────────────


def probe_mail(ctx: ProbeContext) -> Outcome:
    """메일은 선택 항목이다(D-520). 판정은 메일 발송 화면과 같은 건강 상태(`app/mail/health.py::health_state`)다.

    예전에는 값이 채워져 있으면 「됨」이었다 - 발송이 전부 실패해도 초기 설정은 끝난 것처럼 보였다. 이제 실제 연결
    확인이나 발송이 성공해야 「됨」이다.
    """
    from app.mail import health as mail_health
    from app.mail.config import config_from_db

    config = config_from_db(ctx.db)
    state = mail_health.health_state(ctx.db, config, ctx.secrets)
    checked_at = state.get("checked_at")
    if state["state"] == mail_health.STATE_DISABLED:
        return _todo(
            "메일 발송이 꺼져 있습니다.",
            "메일을 쓰려면 메일 화면에서 발송을 켜고 설정을 채우세요. 메일을 쓰지 않는다면 이 항목을 사용하지 않음으로 표시하세요.",
            link=LINK_MAIL_SETTING, configured=False,
        )
    if state["state"] == mail_health.STATE_UNCONFIGURED:
        return _todo(
            f"메일 발송 설정이 비어 있습니다. {state['message']}",
            "메일 설정을 채우세요. 메일을 쓰지 않는다면 이 항목을 사용하지 않음으로 표시하세요.",
            link=LINK_MAIL_SETTING, configured=False,
        )
    if state["state"] == mail_health.STATE_UNVERIFIED:
        return _unknown(
            "메일 설정은 채워졌지만 아직 발송을 확인하지 않았습니다.",
            "메일 화면에서 연결 확인을 눌러 주세요.",
            link=LINK_MAIL_SCREEN, checked_at=checked_at,
        )
    if state["state"] == mail_health.STATE_FAILING:
        return _todo(
            f"메일 발송이 실패하고 있습니다. {state['message']}",
            "메일 화면에서 원인을 확인하고 설정을 고치세요.",
            link=LINK_MAIL_SCREEN, checked_at=checked_at,
        )
    return _done(f"메일 발송이 확인됐습니다({config.host}:{config.port}).", link=LINK_MAIL_SCREEN,
                 checked_at=checked_at)


# ── 조직과 부서 ──────────────────────────────────────────────────────────────


def probe_organization(ctx: ProbeContext) -> Outcome:
    from app.org.constants import ORG_ACTIVE
    from app.org.models import Department, Organization

    orgs = (
        ctx.db.execute(select(Organization).where(Organization.status == ORG_ACTIVE))
        .scalars()
        .all()
    )
    if not orgs:
        # 마이그레이션 0022 가 기본 조직 한 행을 심는다. 그 행이 없다는 것은 설정을 안
        # 한 것이 아니라 설치가 덜 끝났다는 뜻이라 사람에게 시킬 일을 특정할 수 없다.
        return _unknown(
            "조직 행을 하나도 찾지 못했습니다.",
            "데이터베이스 마이그레이션이 끝났는지 설치 로그를 확인해 주세요.",
        )
    if not any((org.name or "").strip() for org in orgs):
        return _todo(
            "조직 이름이 비어 있습니다.",
            "조직 관리 화면에서 회사 이름을 입력하세요.",
            link=LINK_DEPARTMENTS,
        )
    departments = ctx.db.execute(
        select(func.count()).select_from(Department).where(Department.active.is_(True))
    ).scalar_one()
    if not departments:
        return _todo(
            "부서가 하나도 등록되지 않았습니다.",
            "조직 관리 화면에서 부서를 하나 이상 등록하세요.",
            link=LINK_DEPARTMENTS,
        )
    return _done(f"조직 {len(orgs)}개, 부서 {departments}개가 등록돼 있습니다.", link=LINK_DEPARTMENTS)


# ── AI ───────────────────────────────────────────────────────────────────────


def probe_llm(ctx: ProbeContext) -> Outcome:
    """AI 는 선택 항목이다(D-520). 판정은 AI 연결 화면의 상태 면과 같은 함수가 한다(A8, `state_display`).

    런타임은 저장된 연결 상태만 읽고 제공자에 붙지 않는다. 정상이면 완료다 - 도구 지원을 알든 모르든. 의미 검색 모델이
    없어도 완료이고 메모만 단다(낱말 검색이 자연어 질문을 덮는다, D-536). 설치 명령을 안내하지 않는다 - 그 안내는 AI 연결
    화면의 색인 줄에 있다. AI 사용 꺼짐 · 미설정 · 막힘은 할 일, 확인 전 · 확인 중 · 일시 장애는 확인할 일이다.
    """
    from app.ai.console import service as console

    gateway = ctx.gateway
    if gateway is None:
        from app.ai.gateway.registry import build_gateway

        gateway = build_gateway(ctx.settings)
    runtime = ctx.runtime
    if runtime is None:
        from app.ai.runtime import AiRuntime

        runtime = AiRuntime(settings=ctx.settings, secrets=ctx.secrets)
    embed = gateway.capabilities().embed
    info = runtime.status(ctx.db)
    checked_at = info.get("checked_at")
    configured = bool(info.get("provider"))
    shown = console.state_display(info, verifying=console.pending_verify(ctx.db) is not None,
                                  embed_available=bool(embed.available))
    setup = shown["setup"]
    detail = " ".join(filter(None, [setup["detail"], setup.get("note")]))
    if setup["state"] == console.SETUP_DONE:
        return _done(detail, link=LINK_AI, checked_at=checked_at)
    if setup["state"] == console.SETUP_TODO:
        return _todo(detail, setup.get("action") or "AI 연결 화면을 여세요.", link=LINK_AI,
                     configured=configured, checked_at=checked_at)
    return _unknown(detail, setup.get("question") or "AI 연결 화면에서 지금 확인을 누르세요.", link=LINK_AI,
                    checked_at=checked_at)


# ── 외부 연동 ────────────────────────────────────────────────────────────────


def probe_integrations(ctx: ProbeContext) -> Outcome:
    from app.integrations.models import Integration

    rows = ctx.db.execute(select(Integration)).scalars().all()
    if not rows:
        # 🔴 예전에는 이 자리가 `_todo` 였고 「discovery 를 실행하세요」라고 말했다. 그
        # 문장이 참이던 시절이 있었지만 지금은 아니다 — S11·S14 가 걷어내면서 시드 목록
        # (`KNOWN_INTEGRATIONS`)이 비었고, 그 명령을 돌려도 아무것도 안 생긴다. 없는 할
        # 일을 시키는 빨간 줄이 남으면 체크리스트 전체를 안 믿게 된다.
        #
        # 외부 연동은 **선택**이다. 하나도 없는 것은 장애가 아니라 「이 설치는 바깥으로
        # 나가는 호출이 없다」는 정상 상태다.
        return _done("추가된 외부 연동이 없습니다. 이 설치는 바깥으로 나가는 호출을 쓰지 않습니다.",
                     link=LINK_DIAGNOSTICS_INTEGRATIONS)
    enabled = [row for row in rows if row.enabled]
    if not enabled:
        # 전부 꺼 둔 것도 운영자의 선택이다 — 「사용 안 함」이지 「고장」이 아니다.
        return _done(f"연동 {len(rows)}개가 전부 사용 안 함 상태입니다.", link=LINK_DIAGNOSTICS_INTEGRATIONS)
    return _health_outcome(
        [row.last_health_status for row in enabled],
        noun="연동",
        fix="해당 서비스가 실행 중인지, 주소가 맞는지 확인하세요.",
        ask="진단 화면에서 연동 상태를 확인해 주세요.",
    )


def _health_outcome(statuses: list[str], *, noun: str, fix: str, ask: str) -> Outcome:
    """헬스 문자열 목록 하나를 셋 중 하나로 옮긴다.

    **중단이 미점검보다 먼저다**: 죽은 것이 하나라도 있으면 그건 물어볼 일이 아니라
    사람이 고칠 일이다.
    """
    from app.integrations.models import HEALTH_DOWN, HEALTH_UP

    down = [s for s in statuses if s == HEALTH_DOWN]
    if down:
        return _todo(f"{noun} {len(down)}개가 응답하지 않습니다.", fix, link=LINK_DIAGNOSTICS_INTEGRATIONS)
    unchecked = [s for s in statuses if s != HEALTH_UP]
    if unchecked:
        return _unknown(
            f"{noun} {len(unchecked)}개가 아직 한 번도 헬스체크되지 않았습니다.", ask,
            link=LINK_DIAGNOSTICS_INTEGRATIONS,
        )
    return _done(f"{noun} {len(statuses)}개가 모두 정상입니다.", link=LINK_DIAGNOSTICS_INTEGRATIONS)


# ── TLS 인증서 ───────────────────────────────────────────────────────────────


def probe_tls(ctx: ProbeContext) -> Outcome:
    from app.health.service import cert_days_remaining, is_self_signed_cert

    cert_path = getattr(ctx.settings, "tls_cert_path", None)
    if not cert_path:
        # 앞단 nginx 가 TLS 를 끊고 앱은 평문 127.0.0.1 로만 받는 설치가 정상적으로 있다.
        # 그 설치에서 "인증서를 넣으세요" 는 따르면 안 되는 지시다.
        return _unknown(
            "이 앱에 인증서 경로가 설정돼 있지 않습니다.",
            "앞단 프록시에서 TLS 를 끊는 구성인가요? 그렇다면 프록시 쪽 인증서를 확인해 주세요.",
            link=LINK_DIAGNOSTICS_TLS,
        )
    if not Path(cert_path).exists():
        return _todo(
            "설정된 경로에 인증서 파일이 없습니다.",
            "TLS_CERT_PATH 경로를 확인하거나 인증서 파일을 그 자리에 두세요.",
            link=LINK_DIAGNOSTICS_TLS,
        )
    days = cert_days_remaining(ctx.settings)
    if days is None:
        return _unknown(
            "인증서 파일은 있지만 만료일을 읽지 못했습니다.",
            "올바른 PEM 형식 인증서가 맞는지 확인해 주세요.",
            link=LINK_DIAGNOSTICS_TLS,
        )
    if days < 0:
        return _todo("인증서가 이미 만료됐습니다.", "새 인증서로 교체하세요.", link=LINK_DIAGNOSTICS_TLS)
    if days <= TLS_RENEW_DAYS:
        return _todo(f"인증서 만료까지 {days}일 남았습니다.", "만료되기 전에 새 인증서로 교체하세요.",
                     link=LINK_DIAGNOSTICS_TLS)
    # TLS 는 필수 항목이고 설치가 자체 서명 인증서를 만들어 처음부터 끝나 있다(계획 3.5, D-520). 예전에는 자체 서명을
    # 「확인 불가」로 두었는데, 필수 항목이 된 뒤로 그 판정은 모든 새 설치를 영원히 미완료로 만든다. 끝난 것으로 두고
    # 신뢰된 인증서로 바꾸기를 권한다 - 브라우저가 지금도 경고를 띄운다는 사실은 그대로 적는다.
    if is_self_signed_cert(ctx.settings):
        return _done(
            f"설치가 만든 자체 서명 인증서가 있습니다(만료까지 {days}일). 브라우저가 경고를 띄우므로 사용자에게 "
            "공개하는 주소라면 신뢰된 인증서로 바꾸기를 권합니다.",
            link=LINK_DIAGNOSTICS_TLS,
        )
    return _done(f"인증서 만료까지 {days}일 남았습니다.", link=LINK_DIAGNOSTICS_TLS)


PROBES = {
    "admin_account": probe_admin_account,
    "mail": probe_mail,
    "organization": probe_organization,
    "llm": probe_llm,
    "integrations": probe_integrations,
    "tls": probe_tls,
}

__all__ = [
    "Outcome",
    "ProbeContext",
    "PROBES",
    "STATE_DONE",
    "STATE_TODO",
    "STATE_UNKNOWN",
    "STATE_SKIPPED",
]
