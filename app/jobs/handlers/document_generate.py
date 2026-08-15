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

from app.core.http_client import is_timeout_error, is_transport_error
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


def _invoke_classified(provider: N8nWorkflowProvider, workflow, payload: dict, *, timeout: float) -> dict:
    """provider.invoke()를 감싸 실패를 일시적/확정적으로 분류한다.

    타임아웃·연결 실패는 재시도해도 나을 수 있어 그대로 올려 큐가 재시도하게 둔다. 그 외
    (잘못된 webhook_url, 허용 목록 불일치, 비활성화된 workflow, n8n의 비-JSON 응답 등)는
    재시도해도 똑같이 실패하는 확정적 오류라 PermanentJobError로 감싸 큐가 멈추게 한다 —
    notion_mapping_sync.py의 분류와 동일하게 맞춘다. 이 분류가 없으면(예전 상태) preview와
    publish 호출 모두 worker.py의 기본 재시도 경로를 타서, 결정적으로 실패하는 설정 오류를
    백오프하며 반복 재시도만 하다가 워커 용량을 낭비했다.
    """
    try:
        return provider.invoke(workflow, payload, timeout=timeout)
    except Exception as exc:
        if is_timeout_error(exc) or is_transport_error(exc):
            raise
        raise PermanentJobError(f"Workflow 호출 실패: {type(exc).__name__}") from exc


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
    # DBTX: 아웃바운드 호출(n8n) 바로 앞에서 커밋해 스냅샷을 새로 뜬다. 커밋 없이 이
    # 세션이 앞서 읽은 스냅샷을 쥔 채로 느린 호출을 통과하면, 그 사이 다른 세션이 아무
    # 것도 안 써도 스냅샷이 낡을 수 있고 응답을 받은 뒤의 쓰기가 "database is locked"로
    # 거부된다 — busy_timeout으로 못 구한다(app/core/db.py의 "begin" 이벤트 주석,
    # app/jobs/handlers/chat_message.py의 실측 사고와 같은 근거).
    db.commit()
    preview = _invoke_classified(
        provider, workflow, preview_payload, timeout=float(ctx.settings.n8n_timeout_seconds)
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
        _notify_requester_ready(db, gen, ctx)
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
    # DBTX: 위 preview 호출과 같은 이유로 아웃바운드 호출 직전에 커밋한다.
    db.commit()
    result = _invoke_classified(
        provider, workflow, publish_payload, timeout=float(ctx.settings.n8n_timeout_seconds)
    )
    # Read-back verification (spec §19.5).
    published_ref = result.get("published_ref") if isinstance(result, dict) else None
    if not published_ref:
        raise PermanentJobError("발행 응답에 published_ref가 없습니다 (read-back 실패).")
    gen.published_ref = str(published_ref)
    gen.status = STATUS_PUBLISHED
    db.flush()
    _notify_requester_ready(db, gen, ctx)


# 완료를 알릴 상태 → 화면에 쓸 한국어. 여기 없는 상태(quality_failed, failed,
# awaiting_approval)는 **완료가 아니다** — 실패를 완료로 알리면 알림 자체를 못 믿게 된다.
_READY_LABEL = {
    STATUS_PUBLISHED: "발행",
    STATUS_PREVIEW_READY: "미리보기 준비",
}


def _notify_requester_ready(db: Session, gen: DocumentGeneration, ctx) -> None:
    """요청한 사람에게 "다 만들어졌다"를 알린다 (N2).

    감사 확인: 요청한 문서가 다 만들어져도 **화면을 다시 열어 봐야** 알았다. 생성은 큐를
    거치는 비동기 작업이라 사람이 언제 끝나는지 알 방법이 아예 없었다.

    ## "내가 한 일을 나에게 보내지 않는다"에 걸리지 않는가

    걸리지 않는다. 그 규칙이 막는 것은 **방금 내가 눌러서 그 자리에서 결과를 본 일**이다.
    여기서 사용자가 한 일은 '요청'이고 알리는 것은 몇 분 뒤 워커가 만들어 낸 '결과'다 —
    사용자가 화면을 떠난 뒤에 일어나므로 알려 주지 않으면 알 방법이 없다. 이미 같은 근거로
    작업 실패(job_failed)와 예약 실행 실패(schedule_failed)가 요청자에게 간다.

    ## 딥링크

    관련 객체는 `document_generation` 이다. 서버 목적지 표(notifications/destinations.py)에
    일부러 넣지 않았다 — 이유는 그 파일 아래쪽 주석에 적었다(관리 콘솔 문서 화면의 `?id=`
    딥링크는 프런트 표가 이미 들고 있다).

    ## 실패해도 문서는 발행된 채로 남는다

    알림은 본 작업보다 약한 관심사다. 여기서 예외가 나가면 워커가 이 잡을 **실패로 보고
    재시도**하는데, 그러면 이미 발행된 문서를 다시 만들려 든다.
    """
    try:
        if not gen.requested_by:
            return
        label = _READY_LABEL.get(gen.status)
        if label is None:
            return

        from app.notifications.service import notify_user

        preview = json.loads(gen.preview_json) if gen.preview_json else {}
        doc_title = preview.get("title") if isinstance(preview, dict) else None
        notify_user(
            db, gen.requested_by, type_="document_ready",
            title=f"요청한 문서가 준비되었습니다 ({label})",
            body=(doc_title or "문서 생성이 끝났습니다.")[:200],
            related=("document_generation", gen.id), now=ctx.clock.now(),
        )
    except Exception:  # noqa: BLE001 — 알림이 발행 결과를 되돌리면 안 된다
        logger.exception("문서 생성 완료 알림에 실패했다 (generation_id=%s)", gen.id)


def _create_publish_approval(db, gen, ctx) -> None:
    from app.approvals.models import Approval, APPROVAL_PENDING, DEFAULT_SLA_HOURS
    from app.approvals.service import DEFAULT_EXPIRY_HOURS
    from app.notifications.service import notify_approvers

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
    # SLA (0033): 다른 모든 승인 생성 경로는 `create_approval()`을 거쳐 due_at을 갖는다.
    # 이 경로만 Approval을 손으로 만들어 due_at이 계속 NULL로 남았고, 그러면
    # `is_overdue()`/`approval_view`의 overdue/`delegation.notify_overdue()`가 이 요청
    # 유형에 대해서는 절대 참이 될 수 없었다 — SLA 기능이 document.publish만 조용히
    # 빠져 있었다.
    approval.due_at = now + timedelta(hours=DEFAULT_SLA_HOURS)
    db.add(approval)
    db.flush()
    # X7: `notify_admins`는 관리자(admin/system_admin)에게만 간다. 하지만 이 승인을
    # 실제로 결재할 수 있는 사람은 관리자만이 아니다 — 활성 `ApprovalDelegation`을 받은
    # 비관리자도 `delegation.resolve_authority`상 결재할 수 있다. 다른 모든 승인 생성
    # 경로(`create_approval`)는 `notify_approvers`를 써서 피위임자도 알림을 받는데, 이
    # 경로만 `notify_admins`를 직접 불러 피위임자가 존재를 알 방법이 없는 채로 남아
    # 있었다 — 바로 그 X7 결함을 이 경로에서만 되풀이하고 있었다.
    notify_approvers(
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
