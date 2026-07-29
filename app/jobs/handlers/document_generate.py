"""document_generate job handler (spec §19.2–19.5).

Calls the n8n document workflow to build a PREVIEW, runs quality gates, then:
- preview_only          → stop at preview_ready
- preview_then_approve  → create an approval (published on approve)
- auto_publish          → publish immediately if gates pass
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.documents.models import (
    MODE_AUTO_PUBLISH,
    MODE_PREVIEW_ONLY,
    MODE_PREVIEW_THEN_APPROVE,
    STATUS_AWAITING_APPROVAL,
    STATUS_FAILED,
    STATUS_PREVIEW_READY,
    STATUS_PUBLISHED,
    STATUS_QUALITY_FAILED,
    DocumentGeneration,
)
from app.documents.quality import check_document
from app.documents.service import build_workflow_payload
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.workflows.models import Workflow
from app.workflows.provider_n8n import N8nWorkflowProvider

logger = logging.getLogger("app.handlers.document")


def _requester(gen: DocumentGeneration, db: Session) -> dict:
    from app.users.models import User

    if gen.requested_by:
        user = db.get(User, gen.requested_by)
        if user is not None:
            return {"user_id": user.id, "email": user.email, "name": user.display_name}
    return {"user_id": None, "email": None, "name": "system"}


def handle_document_generate(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    gen = db.get(DocumentGeneration, payload.get("generation_id", ""))
    if gen is None:
        raise PermanentJobError("문서 생성 레코드가 없습니다.")

    # 재시도 단락(short-circuit): 이미 Notion에 발행됐다(published_ref 존재)면 다시
    # preview+품질 게이트를 처음부터 돌리지 않는다. 재렌더는 발행본과 달라질 수 있고,
    # 그 결과가 품질 게이트에 걸리면 문서는 실제로 살아 있는데 status만 quality_failed로
    # 뒤집혀 발행 완료가 조용히 실패로 둔갑한다 (§32.8 "Notion에 생성됐지만 응답이 실패").
    # published_ref가 곧 read-back 증거이므로 succeeded로 확정하고 끝낸다.
    if gen.published_ref:
        if gen.status != STATUS_PUBLISHED:
            gen.status = STATUS_PUBLISHED
            gen.error_message = None
            db.flush()
        return

    workflow = db.get(Workflow, gen.workflow_id)
    if workflow is None:
        raise PermanentJobError("대상 Workflow가 없습니다.")

    config = json.loads(gen.config_json)
    provider = N8nWorkflowProvider(ctx.outbound_client)

    # 승인된 발행은 다시 만들지 않는다 — 승인된 산출물을 그대로 싣고 publish만 한다.
    if payload.get("publish_approved"):
        _publish_approved(db, gen, workflow, config, provider, ctx)
        return

    preview_payload = build_workflow_payload(
        config, _requester(gen, db), action="preview"
    )
    preview = provider.invoke(
        workflow, preview_payload, timeout=float(ctx.settings.n8n_timeout_seconds)
    )
    if not isinstance(preview, dict):
        raise PermanentJobError("Workflow preview 응답이 객체가 아닙니다.")

    gen.preview_json = json.dumps(preview, ensure_ascii=False)

    problems = check_document(
        title=preview.get("title"),
        body=preview.get("body"),
        source_row_count=int(preview.get("source_row_count", 0)),
        notion_links=preview.get("notion_links"),
    )
    if problems:
        gen.status = STATUS_QUALITY_FAILED
        gen.quality_problems_json = json.dumps(problems, ensure_ascii=False)
        db.flush()
        logger.warning("document %s failed quality gates: %s", gen.id, problems)
        return  # 품질 게이트 실패 = 정상 종료(발행 안 함), 재시도 대상 아님

    gen.quality_problems_json = None

    if gen.mode == MODE_PREVIEW_ONLY:
        gen.status = STATUS_PREVIEW_READY
        db.flush()
        return

    if gen.mode == MODE_PREVIEW_THEN_APPROVE:
        gen.status = STATUS_AWAITING_APPROVAL
        db.flush()
        _create_publish_approval(db, gen, ctx)
        return

    if gen.mode == MODE_AUTO_PUBLISH:
        _publish(db, gen, workflow, config, provider, ctx)
        return

    raise PermanentJobError(f"알 수 없는 mode: {gen.mode}")


def _publish_approved(db, gen, workflow, config, provider, ctx) -> None:
    """승인 시점의 미리보기를 그대로 발행한다 (spec §19.3).

    다시 렌더하지 않는 이유: 승인은 승인자가 검토한 그 산출물에 대한 것이다. 재렌더한
    문서는 승인받은 적이 없고, 재렌더가 품질 게이트에 걸리면 발행이 조용히 중단된다.
    실패는 PermanentJobError로 드러내 status=failed + 요청자 알림으로 이어진다.
    """
    if gen.status != STATUS_AWAITING_APPROVAL:
        raise PermanentJobError(f"발행 승인 대상이 아닙니다 (status={gen.status}).")
    approved = json.loads(gen.preview_json) if gen.preview_json else None
    if not isinstance(approved, dict):
        raise PermanentJobError("승인된 미리보기 내용이 없어 발행할 수 없습니다.")
    _publish(db, gen, workflow, config, provider, ctx, content=approved)


def _publish(db, gen, workflow, config, provider, ctx, *, content=None) -> None:
    publish_payload = build_workflow_payload(
        config, _requester(gen, db), action="publish", content=content
    )
    # §32.8 "Notion에 생성됐지만 응답이 실패": if a publish succeeds on n8n but the
    # response is lost and the job retries, the same idempotency key lets n8n
    # dedup so a duplicate document is not created. (n8n workflow must honor it.)
    publish_payload["idempotency_key"] = gen.idempotency_key
    result = provider.invoke(
        workflow, publish_payload, timeout=float(ctx.settings.n8n_timeout_seconds)
    )
    # Read-back verification (spec §19.5).
    published_ref = result.get("published_ref") if isinstance(result, dict) else None
    if not published_ref:
        raise PermanentJobError("발행 응답에 published_ref가 없습니다 (read-back 실패).")
    gen.published_ref = str(published_ref)
    gen.status = STATUS_PUBLISHED
    db.flush()


def _create_publish_approval(db, gen, ctx) -> None:
    from app.approvals.models import Approval, APPROVAL_PENDING
    from app.approvals.service import DEFAULT_EXPIRY_HOURS
    from app.notifications.service import notify_admins

    now = ctx.clock.now()
    # {"generation_id": ...} alone forces a reviewer to leave the approvals
    # screen and open the documents screen just to see WHAT they're being asked
    # to publish. Pull the reviewable summary (title, target, source row count)
    # out of the already-built preview/config so it renders directly in the
    # approval's '요청 내용' — mirrors why user.role_change now carries
    # previous_role instead of only the new value.
    preview = json.loads(gen.preview_json) if gen.preview_json else {}
    config = json.loads(gen.config_json) if gen.config_json else {}
    approval_payload = {
        "generation_id": gen.id,
        "title": preview.get("title") if isinstance(preview, dict) else None,
        "target_parent_page": config.get("target_parent_page")
        if isinstance(config, dict)
        else None,
        "source_row_count": preview.get("source_row_count")
        if isinstance(preview, dict)
        else None,
    }
    approval = Approval(
        request_type="document.publish",
        object_type="document_generation",
        object_id=gen.id,
        requested_by=gen.requested_by or "system",
        status=APPROVAL_PENDING,
        request_payload_json=json.dumps(approval_payload, ensure_ascii=False),
        requested_at=now,
    )
    from datetime import timedelta

    approval.expires_at = now + timedelta(hours=DEFAULT_EXPIRY_HOURS)
    db.add(approval)
    db.flush()
    notify_admins(
        db, type_="approval_requested",
        title="문서 발행 승인 요청",
        body="생성된 문서 미리보기를 검토하고 발행을 승인하세요.",
        related=("approval", approval.id), now=now,
    )


def on_failure(db: Session, job: Job, ctx: WorkerContext, error: str) -> None:
    try:
        payload = parse_payload(job)
    except PermanentJobError:
        return
    gen = db.get(DocumentGeneration, payload.get("generation_id", ""))
    if gen is None:
        return
    gen.status = STATUS_FAILED
    gen.error_message = (error or "")[:2000]
    db.flush()


handle_document_generate.on_failure = on_failure
