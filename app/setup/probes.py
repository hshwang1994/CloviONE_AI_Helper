"""항목별 상태 판정 - 이미 있는 것을 읽는다 (9-3, P3).

## 새 판정을 만들지 않는다

여기서 하는 일은 **판단이지 수집이 아니다.** 설치처 고유 설정은
`app/core/tenant_config.py` 가, 시크릿 파일 유무는 `app/core/secret_refs.py` 가, 인증서
만료는 `app/health/service.py` 가, 미러 동기화 상태는 `app/observability` 가, 연동과 러너의
헬스는 각 레지스트리 행이 이미 알고 있다. 이 파일은 그 사실들을 읽어 **"됨 / 안 됨 /
확인 불가"** 세 마디로 번역할 뿐이다.

판정을 여기서 새로 만들면 두 벌이 된다. 두 벌이 되면 한쪽만 고쳐지고, 그러면 "설정했다는데
안 된다" 가 정확히 다시 생긴다.

## 왜 "안 됨" 과 "확인 불가" 를 나누는가

  * **안 됨**(`todo`) 은 사람이 할 일이다. 화면은 무엇을 하라고 말할 수 있다.
  * **확인 불가**(`unknown`) 는 물어볼 일이다. 앱이 있는 자리에서는 알 수 없다.

둘을 합치면 화면은 앞단 프록시가 TLS 를 끊는 정상 설치를 빨갛게 세우고 "인증서를 넣으세요"
라고 말한다. 그 말을 따르면 안 되는데도. 반대로 확인 불가를 초록으로 뭉개면 아무도 안 되는
설치가 다 됐다고 나온다. 둘 다 겪었기 때문에 상태를 셋으로 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_refs import STATUS_CONFIGURED, FileSecretReferenceProvider

STATE_DONE = "done"
STATE_TODO = "todo"
STATE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Outcome:
    """항목 하나의 판정 결과.

    `action` 과 `question` 은 **동시에 채우지 않는다.** 셋 중 무엇인지는 상태가 말하고,
    사람이 다음에 할 행동은 둘 중 하나만 말해야 한다.
    """

    state: str
    detail: str
    action: str | None = None
    question: str | None = None


def _done(detail: str) -> Outcome:
    return Outcome(state=STATE_DONE, detail=detail)


def _todo(detail: str, action: str) -> Outcome:
    return Outcome(state=STATE_TODO, detail=detail, action=action)


def _unknown(detail: str, question: str) -> Outcome:
    return Outcome(state=STATE_UNKNOWN, detail=detail, question=question)


@dataclass(frozen=True)
class ProbeContext:
    """판정에 필요한 것 전부. 라우터가 앱 상태에서 꺼내 한 번만 만든다."""

    db: Session
    settings: Settings
    secrets: FileSecretReferenceProvider
    # 이미 따뜻한 app.state.settings_cache. 없으면 관리 콘솔에서 바꾼 값을 못 보고
    # env 만 읽어 "설정 안 함" 이라고 잘못 말한다(tenant_config.py 의 같은 주의).
    effective: dict


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
        return _todo(
            "시스템 관리자 계정이 없습니다.",
            "scripts/seed_admin.py 로 시스템 관리자 계정을 만드세요.",
        )
    if all(row.must_change_password for row in rows):
        return _todo(
            f"시스템 관리자 {len(rows)}명이 모두 초기 임시 비밀번호 상태입니다.",
            "관리자 계정으로 한 번 로그인해 비밀번호를 바꾸세요.",
        )
    return _done(f"시스템 관리자 {len(rows)}명이 있습니다.")


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
            "데이터베이스 마이그레이션(alembic upgrade head)이 끝났는지 확인해 주세요.",
        )
    if not any((org.name or "").strip() for org in orgs):
        return _todo(
            "조직 이름이 비어 있습니다.",
            "관리 콘솔의 조직 화면에서 회사 이름을 입력하세요.",
        )
    departments = ctx.db.execute(
        select(func.count()).select_from(Department).where(Department.active.is_(True))
    ).scalar_one()
    if not departments:
        return _todo(
            "부서가 하나도 등록되지 않았습니다.",
            "관리 콘솔의 부서 화면에서 부서를 하나 이상 등록하세요.",
        )
    return _done(f"조직 {len(orgs)}개, 부서 {departments}개가 등록돼 있습니다.")


# ── Notion 토큰과 데이터베이스 ───────────────────────────────────────────────

# tenant_config 의 키 중 Notion 항목만 본다. 계정 생성 허용 도메인은 같은 표에 있지만
# Notion 과 무관해서, 함께 세면 도메인을 비워 둔 정상 설치가 Notion 미설정으로 보인다.
_NOTION_TENANT_KEYS = ("notion_tasks_database_id", "notion_documents_database_id")


def probe_notion(ctx: ProbeContext) -> Outcome:
    from app.core.tenant_config import STATE_UNSET, tenant_config_status
    from app.observability.models import (
        COMPONENT_DOCUMENTS,
        COMPONENT_TICKETS,
        SYNC_ERROR,
        SyncStatus,
    )

    status = tenant_config_status(ctx.settings, ctx.effective)
    missing_db = [
        item["label"]
        for item in status["items"]
        if item["key"] in _NOTION_TENANT_KEYS and item["state"] == STATE_UNSET
    ]
    missing_token = [
        ref
        for ref in (
            ctx.settings.notion_report_token_ref,
            ctx.settings.notion_docs_token_ref,
        )
        if ctx.secrets.status(ref) != STATUS_CONFIGURED
    ]
    if missing_db or missing_token:
        parts = []
        if missing_db:
            parts.append("데이터베이스 id 미설정: " + ", ".join(missing_db))
        if missing_token:
            parts.append("토큰 파일 없음: " + ", ".join(missing_token))
        return _todo(
            " / ".join(parts),
            "Notion 통합 토큰을 시크릿 파일로 넣고, 작업과 문서 데이터베이스 id 를 설정하세요.",
        )

    rows = {
        row.component: row
        for row in ctx.db.execute(
            select(SyncStatus).where(
                SyncStatus.component.in_((COMPONENT_TICKETS, COMPONENT_DOCUMENTS))
            )
        )
        .scalars()
        .all()
    }
    succeeded = [row for row in rows.values() if row.last_success_at is not None]
    if succeeded:
        return _done("토큰과 데이터베이스 id 가 설정됐고 동기화가 성공했습니다.")
    failed = [row for row in rows.values() if row.status == SYNC_ERROR]
    if failed:
        return _todo(
            "설정은 돼 있지만 동기화가 실패했습니다.",
            "토큰이 해당 데이터베이스에 연결돼 있는지, 데이터베이스 id 가 맞는지 확인하세요.",
        )
    # 채워졌다는 사실만으로 "됨" 이라 말하면 거짓말이다. 그 토큰이 실제로 통하는지는
    # 한 번이라도 동기화가 성공해야 알 수 있고, 아직 그 일이 없었다.
    return _unknown(
        "토큰과 데이터베이스 id 는 채워졌지만 아직 한 번도 동기화되지 않았습니다.",
        "백그라운드 워커가 실행 중인지 확인해 주세요. 워커가 첫 동기화를 마치면 결과가 여기 나옵니다.",
    )


# ── 사용자 매핑 ──────────────────────────────────────────────────────────────


def probe_user_mapping(ctx: ProbeContext) -> Outcome:
    from app.notion_mapping.models import (
        STATUS_CONFLICT,
        STATUS_VERIFIED,
        UserNotionMapping,
    )
    from app.notion_mapping.service import MAPPING_WORKFLOW_NAME, get_mapping_workflow
    from app.users.models import User

    active_users = ctx.db.execute(
        select(func.count())
        .select_from(User)
        .where(User.active.is_(True), User.archived_at.is_(None))
    ).scalar_one()
    if not active_users:
        # 연결할 사람이 없으면 됐다고도 안 됐다고도 말할 수 없다.
        return _unknown(
            "활성 사용자가 없어 매핑 상태를 판단할 수 없습니다.",
            "사용자를 먼저 등록한 뒤 다시 확인해 주세요.",
        )

    counts = dict(
        ctx.db.execute(
            select(UserNotionMapping.status, func.count()).group_by(
                UserNotionMapping.status
            )
        ).all()
    )
    verified = counts.get(STATUS_VERIFIED, 0)
    if verified:
        # **한 명이라도 연결되면 이 항목은 끝난 것으로 본다.**
        #
        # "전원이 연결됐는가" 로 잡으면 반년 뒤 신입 한 명이 입사한 날 전 직원 화면에
        # "초기 설정이 아직 끝나지 않았습니다" 배너가 다시 뜬다. 그건 사실도 아니고
        # (설정은 끝났다) 아무도 그 배너를 다시는 안 믿게 만든다. 개별 미연결과 충돌은
        # 설치 문제가 아니라 운영 문제라 관리 콘솔의 Notion 연결 화면이 맡는다.
        return _done(
            f"활성 사용자 {active_users}명 중 {verified}명이 Notion 사용자와 연결됐습니다."
        )

    conflicts = counts.get(STATUS_CONFLICT, 0)
    if conflicts:
        return _todo(
            f"이름이 겹쳐 사람이 정해 줘야 하는 연결이 {conflicts}건 있고, 연결된 사람은 아직 없습니다.",
            "관리 콘솔의 Notion 연결 화면에서 충돌을 정리하세요.",
        )
    detail = f"활성 사용자 {active_users}명 중 아무도 Notion 사용자와 연결되지 않았습니다."
    if get_mapping_workflow(ctx.db) is None:
        return _todo(
            detail,
            f"Notion 사용자 매핑 워크플로({MAPPING_WORKFLOW_NAME})를 등록한 뒤 동기화를 실행하세요.",
        )
    return _todo(detail, "관리 콘솔의 Notion 연결 화면에서 매핑 동기화를 실행하세요.")


# ── AI 러너 ──────────────────────────────────────────────────────────────────


def probe_llm(ctx: ProbeContext) -> Outcome:
    from app.runners.models import Runner

    rows = ctx.db.execute(select(Runner)).scalars().all()
    if not rows:
        return _todo(
            "AI 러너가 하나도 등록되지 않았습니다.",
            "관리 콘솔의 러너 화면에서 AI 러너를 등록하고 활성화하세요.",
        )
    enabled = [row for row in rows if row.enabled]
    if not enabled:
        return _todo(
            f"러너 {len(rows)}개가 등록됐지만 전부 비활성 상태입니다.",
            "관리 콘솔의 러너 화면에서 사용할 러너를 활성화하세요.",
        )
    return _health_outcome(
        [row.last_health_status for row in enabled],
        noun="러너",
        fix="러너 서비스가 실행 중인지, 주소와 토큰이 맞는지 확인하세요.",
        ask="관리 콘솔의 러너 화면에서 헬스체크를 한 번 실행해 주세요.",
    )


# ── 외부 연동 ────────────────────────────────────────────────────────────────


def probe_integrations(ctx: ProbeContext) -> Outcome:
    from app.integrations.models import Integration

    rows = ctx.db.execute(select(Integration)).scalars().all()
    if not rows:
        return _todo(
            "외부 연동이 하나도 등록되지 않았습니다.",
            "설치 스크립트의 연동 등록(python -m app.integrations.discovery)을 실행하세요.",
        )
    enabled = [row for row in rows if row.enabled]
    if not enabled:
        return _todo(
            f"연동 {len(rows)}개가 등록됐지만 전부 비활성 상태입니다.",
            "관리 콘솔의 외부 연동 화면에서 사용할 연동을 활성화하세요.",
        )
    return _health_outcome(
        [row.last_health_status for row in enabled],
        noun="연동",
        fix="해당 서비스가 실행 중인지, 주소가 맞는지 확인하세요.",
        ask="관리 콘솔의 외부 연동 화면에서 헬스체크를 한 번 실행해 주세요.",
    )


def _health_outcome(statuses: list[str], *, noun: str, fix: str, ask: str) -> Outcome:
    """헬스 문자열 목록 하나를 셋 중 하나로 옮긴다.

    러너와 연동이 같은 어휘(up/down/unknown)를 쓰므로 판정도 한 번만 적는다.
    **중단이 미점검보다 먼저다**: 죽은 것이 하나라도 있으면 그건 물어볼 일이 아니라
    사람이 고칠 일이다.
    """
    from app.integrations.models import HEALTH_DOWN, HEALTH_UP

    down = [s for s in statuses if s == HEALTH_DOWN]
    if down:
        return _todo(f"{noun} {len(down)}개가 응답하지 않습니다.", fix)
    unchecked = [s for s in statuses if s != HEALTH_UP]
    if unchecked:
        return _unknown(
            f"{noun} {len(unchecked)}개가 아직 한 번도 헬스체크되지 않았습니다.", ask
        )
    return _done(f"{noun} {len(statuses)}개가 모두 정상입니다.")


# ── TLS 인증서 ───────────────────────────────────────────────────────────────


def probe_tls(ctx: ProbeContext) -> Outcome:
    from app.health.service import cert_days_remaining

    cert_path = getattr(ctx.settings, "tls_cert_path", None)
    if not cert_path:
        # 앞단 nginx 가 TLS 를 끊고 앱은 평문 127.0.0.1 로만 받는 설치가 정상적으로 있다.
        # 그 설치에서 "인증서를 넣으세요" 는 따르면 안 되는 지시다.
        return _unknown(
            "이 앱에 인증서 경로가 설정돼 있지 않습니다.",
            "앞단 프록시에서 TLS 를 끊는 구성인가요? 그렇다면 프록시 쪽 인증서를 확인해 주세요.",
        )
    if not Path(cert_path).exists():
        return _todo(
            "설정된 경로에 인증서 파일이 없습니다.",
            "TLS_CERT_PATH 경로를 확인하거나 인증서 파일을 그 자리에 두세요.",
        )
    days = cert_days_remaining(ctx.settings)
    if days is None:
        return _unknown(
            "인증서 파일은 있지만 만료일을 읽지 못했습니다.",
            "올바른 PEM 형식 인증서가 맞는지 확인해 주세요.",
        )
    if days < 0:
        return _todo("인증서가 이미 만료됐습니다.", "새 인증서로 교체하세요.")
    return _done(f"인증서 만료까지 {days}일 남았습니다.")


PROBES = {
    "admin_account": probe_admin_account,
    "organization": probe_organization,
    "notion": probe_notion,
    "user_mapping": probe_user_mapping,
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
]
