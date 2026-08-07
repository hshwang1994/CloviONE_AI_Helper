"""n8n Webhook Provider (spec §7.3, §16.4).

Invocation checks: workflow enabled, URL allowlisted (at call time inside
OutboundClient). Reachability test never executes write workflows — it sends
a GET and treats ANY HTTP response as reachable (n8n answers 404 on GET for
POST-only webhooks, which still proves the service is alive).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationAppError
from app.core.http_client import OutboundClient, is_timeout_error, is_transport_error
from app.workflows.models import Workflow
from app.workflows.service import ALLOWLIST


class WorkflowDisabledError(AppError):
    status_code = 409
    code = "workflow_disabled"
    default_message = "비활성화된 Workflow입니다."


class N8nWorkflowProvider:
    def __init__(self, outbound: OutboundClient) -> None:
        self._outbound = outbound

    def invoke(
        self, workflow: Workflow, payload: dict, *, timeout: float
    ) -> dict:
        if not workflow.enabled:
            raise WorkflowDisabledError()
        if workflow.http_method != "POST" and payload:
            # OutboundClient.request()는 POST가 아니면 json=None을 보내 payload를 조용히
            # 버린다(SSRF 경계와 무관한 순수 로직이라 여기서 막는다) — 모든 실제 호출부
            # (schedule_run/document_generate/notion_mapping_sync)가 비어 있지 않은 payload를
            # 만들어 넘긴다고 가정하므로, http_method=GET으로 (오)구성된 workflow는 n8n이
            # 빈 GET을 받고 데이터 없는 정상 응답처럼 보이는 대신 여기서 바로 실패해야 한다.
            raise ValidationAppError(
                f"http_method가 '{workflow.http_method}'인 Workflow는 payload를 보낼 수 "
                "없습니다 (GET 요청은 본문을 보내지 않습니다). Workflow의 http_method를 "
                "POST로 바꾸거나 payload 없이 호출하세요."
            )
        response = self._outbound.request(
            workflow.http_method,
            workflow.webhook_url,
            allowlist=ALLOWLIST,
            json=payload if workflow.http_method == "POST" else None,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def test(self, db: Session, workflow: Workflow, *, now: datetime) -> dict:
        """Reachability only — never triggers workflow execution."""
        try:
            response = self._outbound.get(
                workflow.webhook_url, allowlist=ALLOWLIST, timeout=10.0
            )
            status = "reachable"
            detail = f"HTTP {response.status_code}"
        except Exception as exc:
            if is_timeout_error(exc):
                status, detail = "unreachable", "timeout"
            elif is_transport_error(exc):
                status, detail = "unreachable", "connection_error"
            else:
                raise
        workflow.last_test_status = status
        workflow.last_test_at = now
        db.flush()
        return {"status": status, "detail": detail}
