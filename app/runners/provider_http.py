"""Local HTTP Runner Provider (spec §7.3 initial implementation)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.http_client import OutboundClient
from app.integrations.models import Integration
from app.runners.models import Runner
from app.runners.service import ALLOWLIST, can_dispatch, record_runner_result


class RunnerUnavailableError(AppError):
    status_code = 409
    code = "runner_unavailable"
    default_message = "Runner를 현재 사용할 수 없습니다."


class RunnerHttpProvider:
    def __init__(self, outbound: OutboundClient) -> None:
        self._outbound = outbound

    def invoke(
        self,
        db: Session,
        runner: Runner,
        payload: dict,
        *,
        now: datetime,
    ) -> dict:
        allowed, reason = can_dispatch(runner, now)
        if not allowed:
            raise RunnerUnavailableError(f"Runner 사용 불가: {reason}")
        # Integration 화면의 활성/비활성화는 여태까지 이 러너 dispatch 경로에서 전혀 읽히지 않아
        # 껐다 켜도 아무 영향이 없었다(장식용 스위치). integration_id로 연결된 통합이 비활성이면
        # 여기서 실제로 막아 그 스위치를 진짜 킬 스위치로 만든다.
        if runner.integration_id is not None:
            integration = db.get(Integration, runner.integration_id)
            if integration is not None and not integration.enabled:
                raise RunnerUnavailableError("연결된 Integration이 비활성화되어 있습니다.")
        try:
            response = self._outbound.post(
                runner.base_url,
                allowlist=ALLOWLIST,
                json=payload,
                timeout=float(runner.timeout_seconds),
                auth_type=runner.auth_type,
                secret_ref=runner.secret_ref,
            )
        except Exception:
            record_runner_result(db, runner, success=False, now=now)
            raise
        success = response.status_code < 500
        record_runner_result(db, runner, success=success, now=now)
        if not success:
            raise RunnerUnavailableError(f"Runner 서버 오류 HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise RunnerUnavailableError("Runner 응답이 올바른 JSON이 아닙니다.") from exc

    def test_request(self, db: Session, runner: Runner, *, now: datetime) -> dict:
        """Safe test invoke — explicit ping payload, never a real work request."""
        result = self.invoke(db, runner, {"ping": True, "test": True}, now=now)
        return {"ok": True, "response": result}
