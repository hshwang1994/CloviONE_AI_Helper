"""Document automation orchestration (spec §19).

The web app never holds a Notion token; documents are produced by an approved
n8n workflow (spec §19.1). This service builds the standard payload, runs the
generation through a job, applies quality gates on the returned preview, and
decides preview-vs-publish per mode.

Standard workflow payload (documented for n8n integration, spec §19.6):
    {
      "action": "preview" | "publish",
      "source": {"database": ..., "filter": ..., "grouping": ..., "date_range": ...},
      "prompt_template": <name>,
      "output_format": <str>,
      "target": {"parent_page": ..., "database": ...},
      "title_rule": <str>,
      "requester": {"user_id","email","name"}
    }
Workflow preview response (expected):
    {"title": str, "body": str, "source_row_count": int, "notion_links": [str]}
Publish response:
    {"published_ref": <notion url>, "title": str}
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.documents.models import (
    MODE_AUTO_PUBLISH,
    MODE_PREVIEW_ONLY,
    MODE_PREVIEW_THEN_APPROVE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_QUALITY_FAILED,
    DocumentGeneration,
)
from app.documents.quality import duplicate_key
from app.documents.repository import get_in_scope
from app.jobs import repository as jobs_repo
from app.workflows.models import Workflow

VALID_MODES = {MODE_PREVIEW_ONLY, MODE_PREVIEW_THEN_APPROVE, MODE_AUTO_PUBLISH}


def publish_approval_required(db: Session, workflow: Workflow, config: dict) -> bool:
    """발행에 승인이 필요한지는 서버가 정한다 (Workflow 등록 정보 + 템플릿 정책).

    요청자가 고른 mode는 '무엇을 원하는가'일 뿐 권한이 아니다 (spec §19.3, §20).
    """
    if workflow.approval_required:
        return True
    template_id = config.get("template_id")
    if not template_id:
        return False
    from app.templates.models import AutomationTemplate

    template = db.get(AutomationTemplate, str(template_id))
    # 비활성화된 템플릿은 없는 것으로 취급한다 — 활성화/비활성화가 이 화면의 유일한
    # 컨트롤인데 이 플래그를 아무 런타임 경로도 읽지 않으면 토글이 장식이 된다. 여기서
    # 존중해야 '비활성화하면 이 템플릿의 승인 정책이 더 이상 발효되지 않는다'가 성립한다.
    if template is None or not template.enabled:
        return False
    try:
        policy = json.loads(template.approval_policy_json or "{}")
    except ValueError:
        # 정책을 읽을 수 없으면 승인 없이 발행하지 않는다 (fail-closed).
        return True
    return bool(isinstance(policy, dict) and policy.get("required"))


def _resolve_published_binding(db: Session, model, pinned_id: str):
    """version 고정 id를 그 이름의 '현재 published' 버전으로 해석한다 (spec §17.1).

    템플릿은 특정 버전 '행'의 id(prompt_id/policy_id)를 저장하는데, '새 버전' 발행과
    '롤백'은 매번 새 행(새 id)을 만든다. 그래서 고정 id를 그대로 소비하면 템플릿이
    옛 버전을 영원히 가리켜, 발행/롤백이 실제로 소비되는 내용을 바꾸지 못한다(inert).
    이름으로 현재 published 버전을 찾아 그 행으로 바꿔 반환한다 — 이렇게 해야
    발행/롤백이 다음 생성부터 반영된다. published가 없으면(예: 초안만 존재) 고정 id를
    유지한다(fail-safe: 참조 자체는 살아 있고, 없는 걸 만들어내지 않는다).
    반환: (해석된 id, 해석된 행 또는 None)."""
    from app.prompts.service import get_published

    row = db.get(model, pinned_id)
    if row is None:
        return pinned_id, None
    published = get_published(db, model, row.name)
    if published is None:
        return pinned_id, row
    return published.id, published


def _policy_payload(policy) -> dict:
    """발행된 정책을 payload에 실을 형태로 만든다 (id가 아니라 실제 content).

    이렇게 해야 정책의 draft→...→published 생명주기가 in-app 소비자를 갖는다 —
    안 그러면 정책 화면의 발행/롤백이 어떤 런타임 경로에도 닿지 않아 장식이 된다
    (round14 E: High|contract|policies)."""
    try:
        content = json.loads(policy.content_json or "{}")
    except ValueError:
        content = {}
    return {"name": policy.name, "version": policy.version, "content": content}


def apply_template_bindings(
    db: Session, *, workflow_id: str, config: dict
) -> tuple[str, dict]:
    """템플릿(config.template_id)이 지정되면 그 바인딩을 실제 생성에 반영한다.

    템플릿 화면이 모으는 target_ref/prompt_id/policy_id/input_schema를 어떤 런타임
    경로도 읽지 않으면 템플릿 생성·수정이 막다른 길이 된다(spec §21.12). 여기서:
    - target_type=workflow면 target_ref를 대상 Workflow로 삼고,
    - input_schema를 config 기본값으로 깔고(요청자가 보낸 값이 우선),
    - prompt_id/policy_id를 config에 채운다(요청자가 지정하지 않았을 때만).
      단, 템플릿이 가리키는 고정 버전 id를 그대로 쓰지 않고 그 이름의 '현재 published'
      버전으로 해석해 넣는다 — 그래야 정책/프롬프트의 발행·롤백이 실제 소비를 바꾼다
      (템플릿은 논리적 정책을 가리키고, 소비 시점에 published로 auto-resolve한다).
      정책은 content까지 payload에 실어 발행된 내용이 실제로 소비되게 한다.
    비활성 템플릿은 없는 것으로 취급한다(publish_approval_required와 동일 규칙).
    """
    template_id = config.get("template_id")
    if not template_id:
        return workflow_id, config
    from app.prompts.models import Policy, Prompt
    from app.templates.models import TARGET_WORKFLOW, AutomationTemplate

    template = db.get(AutomationTemplate, str(template_id))
    if template is None or not template.enabled:
        return workflow_id, config

    try:
        schema_defaults = json.loads(template.input_schema_json or "{}")
    except ValueError:
        schema_defaults = {}
    # 요청자가 보낸 config가 템플릿 기본값을 이긴다.
    merged = {**schema_defaults, **config} if isinstance(schema_defaults, dict) else dict(config)
    if template.prompt_id and not merged.get("prompt_id"):
        resolved_prompt_id, _ = _resolve_published_binding(db, Prompt, template.prompt_id)
        merged["prompt_id"] = resolved_prompt_id
    if template.policy_id and not merged.get("policy_id"):
        resolved_policy_id, policy_row = _resolve_published_binding(
            db, Policy, template.policy_id
        )
        merged["policy_id"] = resolved_policy_id
        if policy_row is not None:
            merged["policy"] = _policy_payload(policy_row)

    effective_workflow_id = workflow_id
    if template.target_type == TARGET_WORKFLOW and template.target_ref:
        effective_workflow_id = template.target_ref
    return effective_workflow_id, merged


def build_workflow_payload(
    config: dict, requester: dict, *, action: str, content: dict | None = None
) -> dict:
    """Workflow 호출 payload를 만든다 (spec §19.6).

    content는 '이 내용을 그대로 발행하라'는 뜻이다. 승인 발행에서 이것을 넘기지 않으면
    n8n이 발행 시점에 다시 렌더하게 되어, 승인자가 검토한 것과 다른 문서가 발행될 수
    있다. 승인은 그 시점의 산출물에 대한 것이므로 발행에는 그 산출물을 실어 보낸다.
    """
    payload = {
        "action": action,
        "source": {
            "database": config.get("source_database"),
            "filter": config.get("filter"),
            "grouping": config.get("grouping"),
            "date_range": config.get("date_range"),
        },
        "prompt_template": config.get("prompt_template"),
        "output_format": config.get("output_format", "markdown"),
        "target": {
            "parent_page": config.get("target_parent_page"),
            "database": config.get("target_database"),
        },
        "title_rule": config.get("title_rule"),
        "requester": requester,
    }
    # 템플릿 바인딩에서 채워진 prompt/policy를 n8n/러너가 볼 수 있게 payload에 싣는다.
    if config.get("prompt_id"):
        payload["prompt_id"] = config.get("prompt_id")
    if config.get("policy_id"):
        payload["policy_id"] = config.get("policy_id")
    # 발행된 정책의 실제 content를 싣는다 — id만으로는 소비자가 없어 발행/롤백이 무효였다.
    if config.get("policy"):
        payload["policy"] = config.get("policy")
    if content is not None:
        payload["content"] = content
    return payload


def enqueue_approved_publish(
    db: Session, gen: DocumentGeneration, *, now: datetime
) -> None:
    """승인된 미리보기를 그대로 발행하는 Job을 넣는다 (spec §19.3).

    왜 '다시 생성'이 아니라 '승인된 산출물'인가: 승인은 승인자가 검토한 그 시점의
    산출물에 대한 것이다. 발행 시점에 다시 렌더하면 그 사이 소스 데이터가 바뀌어
    승인받지 않은 문서가 발행될 수 있고, 재렌더가 품질 게이트에 걸리면 승인은
    completed인데 발행만 조용히 사라진다.

    실패는 Job 실패로 드러난다(on_failure가 status=failed + 사유를 남기고, 요청자에게
    알림이 간다) — user_id를 넘기는 이유다.
    """
    jobs_repo.enqueue(
        db,
        job_type="document_generate",
        payload={"generation_id": gen.id, "publish_approved": True},
        now=now,
        user_id=gen.requested_by,
        # 승인 1회 = 발행 1회 (spec §19.3).
        idempotency_key=f"docpublish:{gen.id}",
    )


def request_generation(
    db: Session,
    *,
    workflow_id: str,
    mode: str,
    config: dict,
    period: str,
    requested_by: str | None,
    now: datetime,
    document_automation_enabled: bool,
) -> DocumentGeneration:
    if not document_automation_enabled:
        raise ConflictError("문서 자동화 기능이 비활성화되어 있습니다.")
    if mode not in VALID_MODES:
        raise ValidationAppError(f"mode는 {sorted(VALID_MODES)} 중 하나여야 합니다.")
    # 템플릿이 지정되면 그 바인딩(대상 Workflow, prompt/policy, input_schema 기본값)을
    # 실제 생성에 반영한다 — 안 그러면 템플릿 화면이 모은 값이 어디서도 쓰이지 않는다.
    workflow_id, config = apply_template_bindings(db, workflow_id=workflow_id, config=config)
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise ValidationAppError("대상 Workflow가 없습니다.")
    if not workflow.enabled:
        raise ConflictError("비활성화된 Workflow로는 문서를 생성할 수 없습니다.")

    # 요청자가 mode=auto_publish를 골라 승인 정책을 건너뛸 수 없다. 승인이 필요한
    # 대상이면 서버가 미리보기 후 승인 경로로 강제한다 (요청자 선택 < 서버 정책).
    effective_mode = (
        MODE_PREVIEW_THEN_APPROVE
        if mode == MODE_AUTO_PUBLISH and publish_approval_required(db, workflow, config)
        else mode
    )

    # UA-29: config는 자유형 dict(GenerateRequest.config, 타입 검증 없음)라
    # template_version에 숫자로 안 바뀌는 값("v2" 등)이 오면 int()가 처리 안 된
    # ValueError/TypeError로 500이 났다 — 사용자 입력 오류는 422여야 한다.
    raw_template_version = config.get("template_version", 1)
    try:
        template_version = int(raw_template_version)
    except (TypeError, ValueError):
        raise ValidationAppError(
            f"template_version은 정수여야 합니다: {raw_template_version!r}"
        ) from None

    key = duplicate_key(
        schedule_id=config.get("schedule_id", "manual"),
        period=period,
        target_ref=config.get("target_parent_page") or config.get("target_database") or "?",
        template_version=template_version,
    )
    existing = db.execute(
        select(DocumentGeneration).where(DocumentGeneration.idempotency_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        # 동일 기간·대상 중복 생성 방지 (spec §19.4).
        raise ConflictError(f"이미 생성된 문서입니다 (기간/대상 중복): {existing.status}")

    # period는 문서의 핵심 업무 차원('무슨 기간을 다루는 문서인가')이자 중복 판정 키의
    # 일부다. 별도 인자로만 받으면 idempotency_key 안에만 남아 생성 후 화면 어디에도
    # 보이지 않는다 — config_json에 함께 저장해 generation_view가 돌려줄 수 있게 한다.
    stored_config = {**config, "period": period}
    gen = DocumentGeneration(
        template_id=config.get("template_id"),
        workflow_id=workflow_id,
        mode=effective_mode,
        idempotency_key=key,
        status=STATUS_PENDING,
        config_json=json.dumps(stored_config, ensure_ascii=False),
        requested_by=requested_by,
        created_at=now,
    )
    db.add(gen)
    db.flush()

    jobs_repo.enqueue(
        db,
        job_type="document_generate",
        payload={"generation_id": gen.id},
        now=now,
        user_id=requested_by,
        idempotency_key=f"docgen:{gen.id}",
    )
    return gen


def retry_generation(
    db: Session, generation: DocumentGeneration, *, now: datetime
) -> DocumentGeneration:
    """실패/품질 실패한 문서 생성을 같은 레코드로 다시 시도한다 (idempotency_key 재사용).

    '재시도'가 생성 폼을 다시 여는 방식은 같은 기간·대상으로 새 생성을 만들어
    idempotency_key 중복(ConflictError '이미 생성된 문서입니다')으로 막다른 길이었다
    (round30 감사 E High). 대신 이 레코드를 초기화(pending)해 다시 큐에 넣는다 — 키는
    그대로라 중복 문제가 없다. 이미 발행된(published_ref) 문서는 재시도 대상이 아니다
    (handler가 published_ref면 succeeded로 단락하므로 status로도 걸러진다).

    기존 docgen 잡이 있으면 그 잡을 requeue한다(품질 실패는 잡이 정상 종료라 succeeded,
    실패는 failed — retry_failed는 두 경우 모두 queued로 되돌린다). 잡이 없으면 새로 넣는다.
    """
    if generation.status not in (STATUS_FAILED, STATUS_QUALITY_FAILED):
        raise ConflictError("실패 또는 품질 실패 상태의 문서만 다시 시도할 수 있습니다.")
    generation.status = STATUS_PENDING
    generation.error_message = None
    generation.quality_problems_json = None
    generation.preview_json = None
    generation.updated_at = now
    db.flush()
    existing = jobs_repo.get_by_idempotency_key(db, f"docgen:{generation.id}")
    if existing is not None:
        jobs_repo.retry_failed(db, existing, now=now)
    else:
        jobs_repo.enqueue(
            db,
            job_type="document_generate",
            payload={"generation_id": generation.id},
            now=now,
            user_id=generation.requested_by,
            idempotency_key=f"docgen:{generation.id}",
        )
    return generation


def generation_view(row: DocumentGeneration) -> dict:
    config = json.loads(row.config_json)
    return {
        "id": row.id,
        # template_id는 전용 컬럼(models.py)인데 지금껏 config 안에 묻혀만 있었다.
        # 어떤 템플릿이 이 문서를 만들었는지는 운영·감사의 기본 질문이라 최상위로 노출한다.
        "template_id": row.template_id,
        "workflow_id": row.workflow_id,
        "mode": row.mode,
        "status": row.status,
        # period는 config_json 안에 저장돼 있다(request_generation) — 최상위로도 꺼내
        # 화면이 컬럼/상세로 바로 쓸 수 있게 한다.
        "period": config.get("period"),
        # 누가 이 문서를 요청했는지는 감사·운영 화면의 기본 질문이다 — 최상위로 노출해
        # 화면이 감사 로그를 교차 조회하지 않고도 요청자를 붙일 수 있게 한다.
        "requested_by": row.requested_by,
        "config": config,
        "preview": json.loads(row.preview_json) if row.preview_json else None,
        "quality_problems": (
            json.loads(row.quality_problems_json) if row.quality_problems_json else None
        ),
        "published_ref": row.published_ref,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def get_generation_or_404(
    db: Session, generation_id: str, visible: frozenset[str] | None
) -> DocumentGeneration:
    """단건 조회 — 범위 밖은 **없는 것과 똑같이 404** 다 (§0-A).

    `visible` 에 기본값을 두지 않은 것이 이 함수의 요점이다. 기본값(`None` = 전역)을 주면
    새 호출부가 **아무것도 안 적고** 전 범위를 열게 된다 — 이 함수의 예전 모습(`db.get`
    하나)이 정확히 그랬다. 인자를 비워 두면 호출 자체가 안 되므로 빠뜨릴 자리가 없다.

    403 이 아니라 404 인 이유는 `app/core/scope.py` 모듈 docstring 참조 — 403 은 "그 id 는
    존재한다"를 알려 주고, id 를 찍어 403/404 를 세면 남의 팀 생성 이력의 존재와 규모가
    열거된다. 문구도 '없음' 과 동일하게 둔다: 응답으로 두 경우를 구별할 수 없어야 한다.

    판정은 목록이 쓰는 `repository.scope_clause` 하나이고, 조건은 **조회 자체에** 붙는다.
    """
    row = get_in_scope(db, generation_id, visible)
    if row is None:
        raise NotFoundError("문서 생성 요청을 찾을 수 없습니다.")
    return row


EXAMPLE_TEMPLATE = {
    "name": "[예시] 주간 프로젝트 보고서 (비활성)",
    "description": "n8n 문서 생성 Workflow 연결 후 활성화하세요. Payload 스키마는 "
    "DOCUMENT_AUTOMATION.md 참조. 임의 Notion Write는 자동 생성되지 않습니다 (spec §19.6).",
    "input_schema": {
        "source_database": "프로젝트 DB",
        "filter": {"status": ["진행"]},
        "date_range": "last_week",
        "prompt_template": "weekly-project-report",
        "output_format": "markdown",
        "target_parent_page": "<Notion 페이지 ID>",
        "title_rule": "주간 보고서 {week}",
        "duplicate_rule": "schedule+period+target+version",
        "approval_rule": "preview_then_approve",
    },
    "approval_policy": {"required": True},
}
