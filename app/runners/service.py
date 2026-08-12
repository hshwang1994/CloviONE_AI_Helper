"""Runner Registry service: config lifecycle + circuit breaker (spec §15)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.allowlist import AllowlistRegistry
from app.core.errors import ConflictError, NotFoundError
from app.core.http_client import OutboundClient, is_timeout_error, is_transport_error
from app.core.secret_refs import FileSecretReferenceProvider
from app.core.versioning import get_version, load_snapshot, snapshot_config
from app.runners.models import (
    CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD,
    MAINT_DEGRADED,
    MAINT_NORMAL,
    Runner,
)
from app.runners.schemas import RunnerConfig

OBJECT_TYPE = "runner"
ALLOWLIST = "runners"


def runner_snapshot(row: Runner) -> dict:
    return {
        "name": row.name,
        "description": row.description,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "health_url": row.health_url,
        "version": row.version,
        "capabilities": json.loads(row.capabilities_json),
        "auth_type": row.auth_type,
        "secret_ref": row.secret_ref,
        "timeout_seconds": row.timeout_seconds,
        "concurrency_limit": row.concurrency_limit,
        "retry_policy": json.loads(row.retry_policy_json),
        "enabled": row.enabled,
        "maintenance_state": row.maintenance_state,
        "owner": row.owner,
        "tags": json.loads(row.tags_json),
        "integration_id": row.integration_id,
    }


def runner_view(row: Runner, secrets: FileSecretReferenceProvider) -> dict:
    view = runner_snapshot(row)
    view.update(
        {
            "id": row.id,
            "secret_status": secrets.status(row.secret_ref) if row.secret_ref else None,
            "last_health_status": row.last_health_status,
            "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
            "config_version": row.config_version,
            "consecutive_failures": row.consecutive_failures,
            "circuit_open_until": (
                row.circuit_open_until.isoformat() if row.circuit_open_until else None
            ),
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
    )
    return view


def get_runner_or_404(db: Session, runner_id: str) -> Runner:
    row = db.get(Runner, runner_id)
    if row is None:
        raise NotFoundError("Runner를 찾을 수 없습니다.")
    return row


def _validate_urls(config: RunnerConfig, allowlists: AllowlistRegistry) -> None:
    allowlist = allowlists.get(ALLOWLIST)
    allowlist.check(config.base_url)
    if config.health_url:
        allowlist.check(config.health_url)


def _check_name_clash(db: Session, name: str, *, exclude_id: str | None = None) -> None:
    stmt = select(Runner).where(Runner.name == name)
    if exclude_id:
        stmt = stmt.where(Runner.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise ConflictError(f"이미 등록된 Runner 이름입니다: {name}")


def _apply_fields(row: Runner, config: RunnerConfig) -> None:
    row.name = config.name
    row.description = config.description
    row.provider_type = config.provider_type
    row.base_url = config.base_url
    row.health_url = config.health_url
    row.version = config.version
    row.capabilities_json = json.dumps(config.capabilities, ensure_ascii=False)
    row.auth_type = config.auth_type
    row.secret_ref = config.secret_ref
    row.timeout_seconds = config.timeout_seconds
    row.concurrency_limit = config.concurrency_limit
    row.retry_policy_json = json.dumps(config.retry_policy, ensure_ascii=False)
    row.enabled = config.enabled
    row.maintenance_state = config.maintenance_state
    row.owner = config.owner
    row.tags_json = json.dumps(config.tags, ensure_ascii=False)
    row.integration_id = config.integration_id


def create_runner(
    db: Session,
    config: RunnerConfig,
    *,
    allowlists: AllowlistRegistry,
    created_by: str | None,
) -> Runner:
    _validate_urls(config, allowlists)
    _check_name_clash(db, config.name)
    row = Runner(config_version=1)
    _apply_fields(row, config)
    # Spec §15.5: 신규 Runner는 Disabled 상태로 저장.
    row.enabled = False
    db.add(row)
    db.flush()
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=row.id,
        snapshot=runner_snapshot(row), created_by=created_by,
    )
    return row


def apply_runner_config(
    db: Session,
    row: Runner,
    config: RunnerConfig,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Runner:
    _validate_urls(config, allowlists)
    if config.name != row.name:
        _check_name_clash(db, config.name, exclude_id=row.id)
    _apply_fields(row, config)
    row.config_version += 1
    db.flush()
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=row.id,
        snapshot=runner_snapshot(row), created_by=updated_by,
    )
    return row


def rollback_runner(
    db: Session,
    row: Runner,
    version: int,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Runner:
    snapshot_row = get_version(db, OBJECT_TYPE, row.id, version)
    config = RunnerConfig.model_validate(load_snapshot(snapshot_row))
    return apply_runner_config(db, row, config, allowlists=allowlists, updated_by=updated_by)


def clone_runner(
    db: Session,
    source: Runner,
    new_name: str,
    *,
    allowlists: AllowlistRegistry,
    created_by: str | None,
) -> Runner:
    config = RunnerConfig.model_validate({**runner_snapshot(source), "name": new_name})
    return create_runner(db, config, allowlists=allowlists, created_by=created_by)


# --- Circuit breaker (spec §15.6) -------------------------------------------


def can_dispatch(runner: Runner, now: datetime) -> tuple[bool, str | None]:
    if not runner.enabled:
        return False, "runner_disabled"
    if runner.maintenance_state == "maintenance":
        return False, "runner_maintenance"
    if runner.circuit_open_until is not None and runner.circuit_open_until > now:
        return False, "circuit_open"
    return True, None


def record_runner_result(
    db: Session,
    runner: Runner,
    *,
    success: bool,
    now: datetime,
    threshold: int = CIRCUIT_FAILURE_THRESHOLD,
    cooldown_seconds: int = CIRCUIT_COOLDOWN_SECONDS,
) -> None:
    if success:
        runner.consecutive_failures = 0
        runner.circuit_open_until = None
        if runner.maintenance_state == MAINT_DEGRADED:
            runner.maintenance_state = MAINT_NORMAL  # 자동 복구 (spec §15.6)
    else:
        was_degraded = runner.maintenance_state == MAINT_DEGRADED
        runner.consecutive_failures += 1
        if runner.consecutive_failures >= threshold:
            runner.maintenance_state = MAINT_DEGRADED
            runner.circuit_open_until = now + timedelta(seconds=cooldown_seconds)
            # spec §13.5는 'Runner 장애 공지'를 8개 알림 유형 중 하나로 커밋한다 — 이 전이가
            # 그 유일한 발생 지점이다. 매 실패마다가 아니라 정상→degraded로 막 넘어가는
            # 순간에만 한 번 보낸다(연속 실패마다 관리자 알림함을 채우지 않는다).
            if not was_degraded:
                from app.notifications.service import notify_admins

                notify_admins(
                    db, type_="runner_unavailable",
                    title=f"Runner 장애: {runner.name}",
                    body=f"연속 {runner.consecutive_failures}회 실패로 점검 상태(degraded)로 전환되었습니다.",
                    related=("runner", runner.id), now=now,
                )
    db.flush()


def run_runner_health_check(
    db: Session, row: Runner, *, outbound: OutboundClient, now: datetime
) -> dict:
    """단건(수동) 상태 확인. `run_all_runner_health_checks`(자동 스윕)와 판정 기준이
    같아야 한다 — 다르면 운영자가 '상태 확인' 버튼을 누를 때마다 정상 러너가 'down'으로
    오판되고, 그 오판이 아래 record_runner_result(success=False)를 통해 서킷 브레이커에
    반영돼 연속 몇 번 클릭만으로 멀쩡한 러너가 실제로 degraded/circuit_open 상태에
    빠진다(round36 감사에서 발견).
    """
    url = row.health_url or row.base_url
    started = time.perf_counter()
    try:
        response = outbound.get(
            url, allowlist=ALLOWLIST, timeout=10.0,
            auth_type=row.auth_type, secret_ref=row.secret_ref,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        # 전용 health_url이 있으면 엄격 기준(2xx/3xx). 없으면 base_url로는 '도달
        # 가능성'만 본다 — 인증된 POST만 받는 러너가 GET에 404를 주는 경우가 흔해서다
        # (run_all_runner_health_checks 문서 참조, 같은 근거).
        healthy = response.status_code < 400 if row.health_url else response.status_code < 500
        status = "up" if healthy else "down"
        detail = f"HTTP {response.status_code}"
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        if is_timeout_error(exc):
            status, detail = "down", "timeout"
        elif is_transport_error(exc):
            status, detail = "down", "connection_error"
        else:
            raise
    row.last_health_status = status
    # RN-12: 여러 러너를 한 스윕에서 점검하면 바닥 now를 그대로 쓸 때 전부 초 단위까지
    # 같은 시각이 찍혀 "이 러너가 실제로 언제 응답했는가"를 개별로 알 수 없었다. 이미
    # 위에서 잰 latency_ms를 그대로 더해 각 응답이 실제로 도착한 순간을 반영한다.
    row.last_health_at = now + timedelta(milliseconds=latency_ms)
    record_runner_result(db, row, success=(status == "up"), now=now)
    return {"status": status, "latency_ms": round(latency_ms, 1), "detail": detail, "checked_url": url}


def run_all_runner_health_checks(db: Session, *, outbound: OutboundClient, now: datetime) -> dict:
    """활성 러너의 상태를 한 번에 점검한다(워커가 주기적으로 호출).

    수동 POST /{id}/health 만 있을 때는 아무도 누르지 않아 last_health_status 가 영원히 'unknown'
    이었다 — 대시보드/러너 목록이 실제 상태를 보이도록 자동으로 채운다.

    판정 기준(거짓 'down' 방지):
    - **비활성 러너는 점검하지 않는다** — 꺼 둔 러너를 'down'으로 표시하면 오해를 준다(UI는 '비활성'으로 표시).
    - 전용 상태확인 주소(health_url)가 있으면 2xx/3xx 만 정상(전용 헬스 엔드포인트 규약).
    - 없으면 base_url 로 '도달 가능성'만 본다 — 응답이 오면(404 등 4xx 포함) 프로세스는 살아있는
      것이므로 정상으로 본다. 러너 다수가 인증된 POST 만 받고 GET/ 에는 404 를 주므로, 엄격한
      2xx 기준을 쓰면 살아있는 러너가 전부 'down' 으로 잘못 표시됐다. 연결거부/타임아웃만 'down'.
    한 러너의 예외가 스윕 전체를 멈추지 않게 각 러너를 격리한다.
    """
    rows = db.execute(select(Runner)).scalars().all()
    checked = up = down = 0
    for row in rows:
        if not row.enabled:
            continue  # 비활성 러너는 점검 대상이 아니다(UI가 '비활성'으로 구분 표시)
        url = row.health_url or row.base_url
        if not url:
            continue
        checked += 1
        started = time.perf_counter()
        try:
            resp = outbound.get(
                url, allowlist=ALLOWLIST, timeout=10.0,
                auth_type=row.auth_type, secret_ref=row.secret_ref,
            )
            reachable = resp.status_code < 400 if row.health_url else resp.status_code < 500
        except Exception as exc:
            # 연결거부/타임아웃은 물론, allowlist·설정 오류 등 다른 예외도 점검 실패(=down)로 본다.
            _ = is_timeout_error(exc) or is_transport_error(exc)
            reachable = False
        row.last_health_status = "up" if reachable else "down"
        # RN-12: 러너마다 바닥 now를 그대로 쓰면 스윕에 든 러너 전부가 초 단위까지 같은
        # 시각으로 찍혀 "이 러너가 실제로 언제 응답했는가"를 개별로 알 수 없었다 — 이
        # 러너까지 걸린 시간을 더해 각 응답이 실제로 도착한 순간을 반영한다.
        row.last_health_at = now + timedelta(milliseconds=(time.perf_counter() - started) * 1000)
        record_runner_result(db, row, success=reachable, now=now)
        if reachable:
            up += 1
        else:
            down += 1
    return {"checked": checked, "up": up, "down": down}
