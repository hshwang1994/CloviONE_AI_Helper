"""Dashboard aggregation + diagnostics (spec §14.1, §14.7)."""

from __future__ import annotations

import logging
import shutil
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit.actions import with_cli_variants
from app.audit.models import AuditLog
from app.backups.service import last_successful_backup
from app.core import uploads
from app.core.config import Settings
from app.health.models import Heartbeat
from app.integrations.models import Integration
from app.jobs.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SUCCEEDED,
    Job,
)
from app.runners.models import Runner
from app.schedules.models import Schedule
from app.storage.service import storage_health
from app.users.models import User
from app.workflows.models import Workflow

logger = logging.getLogger("app.health")

HEARTBEAT_STALE_SECONDS = 90

CRITICAL_ACTIONS = (
    "user.disable", "user.role_change", "runner.rollback", "setting.rollback",
    "approval.approve",
    # workflow.rollback (app/workflows/router.py) can silently swap out the
    # live chat-webhook or Notion-mapping workflow config — the codebase's
    # own registry.js RESERVED_WORKFLOW_NOTES calls this the highest-blast-
    # radius action available, so it belongs here at least as much as the
    # less consequential runner.rollback already does.
    "workflow.rollback",
    # "backup.restore" deliberately excluded: actual restore is script-only,
    # out-of-band, and never writes to this app's audit_log table (spec
    # §14.6, see app/backups/router.py:restore_instructions). Including it
    # here would be permanently-dead filter data implying this dashboard
    # tracks backup restores when it structurally cannot.
)

# The CLI (app/cli/user_cli.py) — CLAUDE.md's officially documented way to
# manage users outside the admin console — records the identical operations
# under a "cli."-prefixed action string, but not always the same base verb
# as the web UI: "cli.user.disable" matches "user."+"disable" directly, but
# role changes are written as "cli.user.set_role" while the web UI's
# equivalent is "user.role_change" — a plain "cli."-prefix of CRITICAL_ACTIONS
# would miss that one. An exact-string filter on CRITICAL_ACTIONS alone
# silently drops every CLI-driven critical action from "최근 주요 변경", even
# though it's exactly the kind of out-of-band change this widget exists to
# surface. Match every known spelling of the same underlying action.
#
# SEC-22: this exact mapping used to be hand-rolled here only — the audit
# anomaly rules (app/audit/anomalies.py) didn't know it, so CLI-driven role
# changes never tripped "critical_action". with_cli_variants() (and its odd-
# spelling exceptions) now lives in app/audit/actions.py so both consumers
# stay in sync.
CRITICAL_ACTIONS_MATCH = with_cli_variants(CRITICAL_ACTIONS)


def write_heartbeat(db: Session, component: str, now: datetime, detail: str | None = None) -> None:
    row = db.get(Heartbeat, component)
    if row is None:
        row = Heartbeat(component=component, last_beat_at=now, detail=detail)
        db.add(row)
    else:
        row.last_beat_at = now
        row.detail = detail
    db.flush()


def _component_status(db: Session, component: str, now: datetime) -> str:
    row = db.get(Heartbeat, component)
    if row is None:
        return "unknown"
    if (now - row.last_beat_at).total_seconds() > HEARTBEAT_STALE_SECONDS:
        return "down"  # spec §14.1: a stale heartbeat reads as down
    return "up"


def _disk_usage(path: str) -> dict:
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
            "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else None,
        }
    except OSError:
        return {"total_gb": None, "used_gb": None, "free_gb": None, "used_pct": None}


def _memory_usage() -> dict:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return {"total_kb": None, "available_kb": None, "used_pct": None}
    values: dict[str, int] = {}
    for line in meminfo.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].rstrip(":") in ("MemTotal", "MemAvailable"):
            values[parts[0].rstrip(":")] = int(parts[1])
    total = values.get("MemTotal")
    avail = values.get("MemAvailable")
    used_pct = round((total - avail) / total * 100, 1) if total and avail else None
    return {"total_kb": total, "available_kb": avail, "used_pct": used_pct}


def _cert_days_remaining(settings: Settings, now: datetime | None = None) -> int | None:
    """Days until the configured TLS certificate expires, or None.

    Parses the certificate with the stdlib ``ssl`` module (no ``openssl``
    subprocess, no third-party ``cryptography`` dependency). Uses a
    timezone-aware ``now`` so the comparison is unambiguous. Any missing file
    or parse failure returns None — this feeds a dashboard tile and must never
    raise.

    ``now``: optional injected clock, so this agrees with the rest of
    ``build_dashboard``/``build_diagnostic_bundle`` (both thread the same
    ``now`` through every other computation, e.g. ``generated_at``) instead of
    silently reading real wall-clock time even when the rest of the payload is
    frozen under a fake clock. Defaults to real time for callers with no clock
    of their own (e.g. ``app/setup/probes.py``, which has no ``now`` to pass).
    Per ``app/core/clock.py``, an injected ``now`` is naive UTC — treated as
    such here if it has no tzinfo.
    """
    cert_path = getattr(settings, "tls_cert_path", None)
    if not cert_path or not Path(cert_path).exists():
        return None
    try:
        # _test_decode_cert is the only stdlib entry point that decodes a PEM
        # file on disk without opening a socket. It returns a dict whose
        # "notAfter" is an ssl-style time string, e.g. "Jul 14 00:00:00 2027 GMT".
        cert = ssl._ssl._test_decode_cert(str(cert_path))  # type: ignore[attr-defined]
        not_after = cert.get("notAfter")
        if not not_after:
            return None
        # cert_time_to_seconds parses the ssl time string to a UTC epoch,
        # sidestepping locale/%Z ambiguities in strptime.
        expiry = datetime.fromtimestamp(
            ssl.cert_time_to_seconds(not_after), tz=timezone.utc
        )
        reference = now if now is not None else datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return (expiry - reference).days
    except Exception as exc:  # pragma: no cover - defensive: never break the dashboard
        # 인증서 확인이 조용히 죽으면 만료를 놓친다. 원인(메시지만, 인증서 내용은 아님)을
        # journalctl에 남겨 최소한 눈에는 띄게 한다 — 화면(대시보드 타일)은 여전히 None.
        logger.warning("cert expiry check failed for %s: %s", cert_path, exc)
        return None


def cert_days_remaining(settings: Settings, now: datetime | None = None) -> int | None:
    """`_cert_days_remaining` 의 공개 이름.

    셋업 체크리스트(app/setup/probes.py)도 인증서 만료를 말해야 한다. 판정을 거기서 다시
    쓰면 두 화면이 서로 다른 날짜를 말하게 되므로 같은 함수를 부른다. 밑줄 이름을 모듈
    밖에서 부르면 "여기까지가 이 모듈의 약속" 이라는 신호가 사라져 공개 이름을 하나 둔다
    (기존 호출부와 테스트는 밑줄 이름을 그대로 쓴다).
    """
    return _cert_days_remaining(settings, now)


def is_self_signed_cert(settings: Settings) -> bool | None:
    """SYS-05: 인증서의 issuer == subject 인지(자체서명 여부).

    `probe_tls`(app/setup/probes.py)가 "만료일까지 며칠 남았다"만 보고 초록으로
    판정하면, 자체서명 인증서는 만료 전이어도 **오늘 이미** 브라우저 경고를 띄우고
    있는데 화면은 "됨"이라고 말한다 — 측정하는 것(만료)과 실제 해악(신뢰 안 됨)이
    다르다. 파일이 없거나 파싱 실패하면 None(모른다) — `_cert_days_remaining`과 같은
    "모르면 거짓으로 단정하지 않는다" 규약.
    """
    cert_path = getattr(settings, "tls_cert_path", None)
    if not cert_path or not Path(cert_path).exists():
        return None
    try:
        cert = ssl._ssl._test_decode_cert(str(cert_path))  # type: ignore[attr-defined]
        subject, issuer = cert.get("subject"), cert.get("issuer")
        if not subject or not issuer:
            return None
        return subject == issuer
    except Exception as exc:  # pragma: no cover - defensive: never break the checklist
        logger.warning("cert self-signed check failed for %s: %s", cert_path, exc)
        return None


def build_dashboard(
    db: Session,
    settings: Settings,
    now: datetime,
    *,
    include_critical_audit: bool = True,
    cache=None,
) -> dict:
    since = now - timedelta(hours=24)

    # 유지보수 모드는 이 앱에서 blast-radius가 가장 큰 운영 상태다(app/settings/gate.py가
    # 켜져 있는 동안 일반 사용자의 모든 쓰기를 막는다). 대시보드는 그 '변경'은 최근 주요
    # 변경에서 보여 주면서 정작 '지금 켜져 있는가'는 노출하지 않았다 — 화면이 상단 배너/
    # 경보로 띄울 수 있게 payload에 현재 상태를 싣는다. cache가 없으면(구 호출부) 안전하게
    # False로 둔다. import는 순환 참조를 피해 함수 안에서 한다.
    maintenance = False
    if cache is not None:
        from app.settings.service import is_maintenance_mode

        maintenance = is_maintenance_mode(db, cache)

    total_24h = db.execute(
        select(func.count()).select_from(Job).where(Job.created_at >= since)
    ).scalar_one()
    succeeded_24h = db.execute(
        select(func.count()).select_from(Job).where(
            Job.created_at >= since, Job.status == STATUS_SUCCEEDED
        )
    ).scalar_one()
    # success_rate_pct's denominator must be jobs that actually finished in
    # the window, not every job merely *created* in it (total_24h includes
    # still-queued/running/cancelled jobs). Otherwise a burst of freshly
    # submitted-but-unfinished jobs drives the rate toward 0 with nothing
    # having actually failed — misleading on the Dashboard's top alert.
    failed_24h = db.execute(
        select(func.count()).select_from(Job).where(
            Job.created_at >= since, Job.status == STATUS_FAILED
        )
    ).scalar_one()
    cancelled_24h = db.execute(
        select(func.count()).select_from(Job).where(
            Job.created_at >= since, Job.status == STATUS_CANCELLED
        )
    ).scalar_one()
    finished_24h = succeeded_24h + failed_24h + cancelled_24h
    failed_open = db.execute(
        select(func.count()).select_from(Job).where(Job.status == STATUS_FAILED)
    ).scalar_one()
    # VIS-107R — failed_open was a bare count with no time axis, so "미해결 실패 4건" reads
    # the same whether all four just failed or have sat there for three weeks (the exact gap
    # a Chrome-driven audit surfaced: 4 open failures untouched for 21+ days). The sibling
    # failed_24h metric already has a time window; this one had none. Surface the oldest
    # still-open failure's created_at so the UI can show an age instead of a bare count —
    # None when there are none open (failed_open == 0).
    failed_open_oldest_at = db.execute(
        select(func.min(Job.created_at)).select_from(Job).where(Job.status == STATUS_FAILED)
    ).scalar_one()
    queued = db.execute(
        select(func.count()).select_from(Job).where(Job.status == STATUS_QUEUED)
    ).scalar_one()

    # Average processing time over *successfully finished* jobs in the window
    # (seconds) — scoped to STATUS_SUCCEEDED only. Cancelled jobs were already
    # excluded incidentally (repository.cancel_queued nulls started_at), but
    # permanently-failed jobs were not: repository.fail keeps the original
    # started_at, so their durations used to blend into this KPI and skew
    # "average processing time" toward however long jobs typically take to
    # fail rather than to succeed (round28 감사 E — Dashboard.jsx labels this
    # KPI "평균 처리", read by operators as "how fast do jobs normally
    # complete").
    finished = db.execute(
        select(Job.started_at, Job.finished_at).where(
            Job.created_at >= since, Job.finished_at.is_not(None),
            Job.started_at.is_not(None), Job.status == STATUS_SUCCEEDED,
        )
    ).all()
    durations = [
        (f - s).total_seconds() for s, f in finished if s is not None and f is not None
    ]
    avg_seconds = round(sum(durations) / len(durations), 2) if durations else None

    success_rate = round(succeeded_24h / finished_24h * 100, 1) if finished_24h else None

    # recent_critical_audit는 민감한 감사 슬라이스(누가 역할 변경/백업 복원/롤백/승인했나)라
    # 감사 로그 열람 권한(admin/system_admin/auditor)이 있는 역할에만 내려야 한다. operator는
    # 대시보드는 보지만 감사 로그는 못 보므로(app/audit/router.py) 여기서도 빼서 우회 노출을
    # 막는다(round10 감사 E).
    recent_critical = (
        db.execute(
            select(AuditLog)
            .where(
                or_(
                    AuditLog.action.in_(CRITICAL_ACTIONS_MATCH),
                    # 유지보수 모드 on/off는 이 앱의 blast-radius가 가장 큰 관리 동작이다
                    # (app/settings/gate.py block_if_maintenance — 전체 사용자 쓰기를
                    # 막는다) 하지만 app/settings/router.py는 모든 설정 PUT을 동일한
                    # 범용 action="setting.update"로 기록해 CRITICAL_ACTIONS의 정확
                    # 문자열 매치에 걸리지 않았다. object_id는 설정 key라 여기서
                    # maintenance_mode 하나만 골라 매치한다(다른 설정의 흔한 변경까지
                    # '주요 변경'에 끌려오지 않게).
                    (AuditLog.action == "setting.update")
                    & (AuditLog.object_id == "maintenance_mode"),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(5)
        )
        .scalars()
        .all()
    ) if include_critical_audit else []
    # Resolve actor ids to display names so the dashboard can show WHO acted
    # (spec §14.1 "최근 주요 변경"). Missing/system actors fall back to "시스템".
    actor_ids = {a.user_id for a in recent_critical if a.user_id}
    actor_names: dict[str, str] = {}
    if actor_ids:
        for u in db.execute(
            select(User.id, User.display_name).where(User.id.in_(actor_ids))
        ).all():
            actor_names[u.id] = u.display_name

    last_backup = last_successful_backup(db)

    return {
        "components": {
            "web": "up",  # if this endpoint responds, web is up
            "worker": _component_status(db, "worker", now),
            "scheduler": _component_status(db, "scheduler", now),
            # D-118: 켠 설치처만 이 타일을 본다. 대부분의 설치는 이 레인을 켠 적이 없어
            # (기본값 꺼짐) 하트비트 행 자체가 없다 — 무조건 넣으면 켠 적도 없는 기능이
            # 모든 배포에서 "응답 없음"으로 영구히 붉게 보인다(끈 기능이 알람처럼
            # 보이는 것 — VIS-134류와 반대 방향의 실수). 켰던 적이 있는 설치(하트비트
            # 행이 존재)에서만 실제 상태를 보여준다.
            **(
                {"worker_conversational": _component_status(db, "worker_conversational", now)}
                if settings.worker_conversational_lane_enabled
                or db.get(Heartbeat, "worker_conversational") is not None
                else {}
            ),
        },
        "integrations": {
            i.name: {"enabled": i.enabled, "last_health": i.last_health_status}
            for i in db.execute(select(Integration)).scalars().all()
        },
        "counts": {
            "runners": db.execute(select(func.count()).select_from(Runner)).scalar_one(),
            "active_workflows": db.execute(
                select(func.count()).select_from(Workflow).where(Workflow.enabled.is_(True))
            ).scalar_one(),
            "active_schedules": db.execute(
                select(func.count()).select_from(Schedule).where(Schedule.enabled.is_(True))
            ).scalar_one(),
        },
        "jobs_24h": {
            "total": total_24h,
            "succeeded": succeeded_24h,
            "success_rate_pct": success_rate,
            "avg_processing_seconds": avg_seconds,
            "queued": queued,
            "failed_open": failed_open,
            "failed_open_oldest_at": (
                failed_open_oldest_at.isoformat() if failed_open_oldest_at is not None else None
            ),
        },
        "recent_critical_audit": [
            {"action": a.action, "object_type": a.object_type, "object_id": a.object_id,
             "created_at": a.created_at.isoformat(),
             # Dashboard.jsx renders `a.actor || "시스템"` — None must mean "no actor
             # at all" (a truly system-initiated row), never "we couldn't resolve who
             # it was". If user_id is set but the user no longer resolves (deleted/
             # unavailable), say so explicitly instead of letting a real, accountable
             # human action get mislabeled as an automated one on a widget whose whole
             # point is "who did this".
             "actor": (
                 actor_names.get(a.user_id, "(알 수 없는 사용자)") if a.user_id else None
             )}
            for a in recent_critical
        ],
        "disk": _disk_usage(str(settings.data_dir)),
        # OPS-03: 디스크 용량과 별개로, 실제 쓰기 가능 여부를 매 대시보드 조회마다 보여준다
        # — OPS-01처럼 용량은 멀쩡한데 소유권 드리프트로 못 쓰는 경우를 며칠씩 아무도
        # 모르고 지나가지 않게 한다.
        "uploads_writable": uploads.uploads_writable(settings.data_dir),
        # S8: 파일 저장소. `uploads_writable` 과 다른 결함을 잡는다 — 저쪽은 로컬
        # `data_dir` 만 보므로 NFS/SMB 가 안 붙은 상태를 못 본다. 운영과 백업이 같은
        # 장치일 때의 경고도 여기 실린다(D-199 16번).
        "storage": storage_health(db),
        "memory": _memory_usage(),
        "cert_days_remaining": _cert_days_remaining(settings, now),
        "last_backup_at": last_backup.created_at.isoformat() if last_backup else None,
        "last_backup_status": last_backup.status if last_backup else None,
        # 현재 유지보수 모드 상태(app/settings/gate.py) — 화면이 danger 배너/경보로 띄운다.
        "maintenance": maintenance,
    }


def build_diagnostic_bundle(
    db: Session, settings: Settings, now: datetime, cache=None,
    *, include_critical_audit: bool = True,
) -> dict:
    """Masked diagnostics — no secrets, no raw journals (spec §14.7).

    ``cache``: the app-wide, already-warm ``SettingsCache`` (app.state.settings_cache).
    Callers should pass it — a fresh ``SettingsCache()`` starts empty, so
    ``effective_settings`` would otherwise re-query every AppSetting row from
    the DB on every diagnostics collect, duplicating work the app already did
    once at startup/on write, for no behavioral difference (falls back to a
    throwaway instance only if a caller genuinely has none, e.g. ad-hoc scripts).

    ``include_critical_audit``: PA-RC-0026 — this bundle embeds a full
    ``build_dashboard()`` call, whose own ``/api/admin/dashboard`` endpoint
    gates the "최근 주요 변경" critical-audit slice to SENSITIVE_READ_ROLES
    (operator excluded). ``build_dashboard`` defaults this to True, so once
    this endpoint's own role gate was widened to CONSOLE_OPS_ROLES (operator
    included), a naive unparameterized call here would have quietly handed
    operator the exact slice the sibling endpoint deliberately withholds from
    them. The caller must pass the same ``role in SENSITIVE_READ_ROLES`` test
    the dashboard route already does.
    """
    from app.core.audit import mask_sensitive
    from app.core.tenant_config import tenant_config_status
    from app.mail.config import config_from_cache, mail_status
    from app.mail.service import queue_counts as mail_queue_counts
    from app.settings.service import SettingsCache, effective_settings

    recent_job_errors = (
        db.execute(
            select(Job.job_type, Job.last_error, Job.created_at)
            .where(Job.status == STATUS_FAILED)
            .order_by(Job.created_at.desc())
            .limit(20)
        )
        .all()
    )
    bundle_cache = cache or SettingsCache()
    effective = effective_settings(db, bundle_cache)
    # mask_sensitive matches on *key names*, so calling it on the whole envelope
    # would test the setting name itself (e.g. "password_policy") against the
    # sensitive-key regex and collapse the entire non-secret envelope — value,
    # type, description, everything — to "***" just because the setting's name
    # contains "password". Masking each setting's "value" sub-object
    # individually instead means the key-name match only ever applies to actual
    # field names *inside* the value (e.g. smtp.password_ref), never to the
    # setting/category name.
    masked_settings = {
        key: {**envelope, "value": mask_sensitive(envelope["value"])}
        for key, envelope in effective.items()
    }
    return {
        "generated_at": now.isoformat(),
        "dashboard": build_dashboard(
            db, settings, now, cache=bundle_cache,
            include_critical_audit=include_critical_audit,
        ),
        "settings": masked_settings,
        # 설치처 고유 설정이 비었는지(app/core/tenant_config.py). 마스킹된 settings 덤프만
        # 봐서는 "비어 있음"과 "원래 그런 값"이 구별되지 않는다 — 상태를 따로 싣는다.
        # 다른 고객사 설치에서 아무 설정 없이 동작하지 않는 이유가 화면에 안 뜨던 문제를 막는다.
        "tenant_config": tenant_config_status(settings, effective),
        # 메일 발송 상태(9-9 P4). 진단이 이걸 말하지 않으면 "재설정 메일이 안 온다"는
        # 신고를 받고도 원인이 SMTP 미설정인지 발송 실패인지 구별할 수 없다.
        # 판정은 app/mail/config.py 한 곳이라 관리 화면(/api/admin/mail/status)과 같은 답이 나온다.
        # secret_provider 를 넘기지 않는 이유: 이 함수는 app.state 를 받지 않는다.
        # 비밀번호 secret 파일 존재 여부는 관리 화면 쪽에서 확인한다.
        "mail": {
            **mail_status(config_from_cache(bundle_cache)),
            "counts": mail_queue_counts(db),
        },
        "recent_job_errors": [
            {"job_type": jt, "error": err, "at": ts.isoformat()}
            for jt, err, ts in recent_job_errors
        ],
        # "integration_errors"(다운된 연동만 걸러낸 map)는 계산만 되고 화면 어디서도
        # 읽히지 않았다(spec §14.7의 '외부 연동' 섹션은 대신 dash.integrations 전체를
        # 쓴다) — 매 요청 계산해 버리기만 하던 죽은 필드를 없앤다.
    }
