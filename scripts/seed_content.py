"""Seed REAL, usable ClovirONE business content (spec §15–§18).

Populates the (empty) registries — Runners, Prompts, Policies, Automation
Templates, Schedules — with coherent data for the internal Korean work-automation
platform, driving the app's OWN service layer so validation, SSRF allowlists,
version snapshots and the Python-side datetime formatting all apply. NEVER writes
raw SQL (raw ``STRFTIME('%f')`` corrupts timestamps — see docs/BUILD_LOG.md §8).

Usage:
    python scripts/seed_content.py

Idempotent: every item is checked by name before creation, so re-running makes
no duplicates and raises no errors. Targets DATABASE_URL from the environment
(so on the server it hits /var/lib/clovirone-web-assistant/web.sqlite3) — the DB
path is never hardcoded.

HARD INVARIANTS respected: sync only; no outbound HTTP (no ``import httpx``);
no hardcoded secrets (all seeded runners use auth_type=none); timestamps are
UTC-naive via the ORM defaults / app helpers.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.allowlist import AllowlistRegistry  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.models_base import utcnow  # noqa: E402
from app.prompts.models import Policy, Prompt  # noqa: E402
from app.prompts.service import get_published, transition  # noqa: E402
from app.runners.models import Runner  # noqa: E402
from app.runners.schemas import RunnerConfig  # noqa: E402
from app.runners.service import create_runner  # noqa: E402
from app.schedules import cron  # noqa: E402
from app.schedules.models import TARGET_WORKFLOW as SCHED_TARGET_WORKFLOW  # noqa: E402
from app.schedules.models import TYPE_CRON, Schedule  # noqa: E402
from app.templates.models import TARGET_WORKFLOW as TMPL_TARGET_WORKFLOW  # noqa: E402
from app.templates.models import AutomationTemplate  # noqa: E402
from app.users.models import ROLE_SYSTEM_ADMIN, User  # noqa: E402
from app.workflows.models import Workflow  # noqa: E402
from app.workflows.service import seed_known_workflows  # noqa: E402

# Ground truth (verified on the live server).
SEED_OWNER_ID = "7d1fa387-fad6-4a40-a5dc-d1fef0a2f2d7"  # system_admin hshwang@goodmit.co.kr
WORK_ASSISTANT_WORKFLOW = "ClovirONE AI 업무 도우미"
NOTION_MAPPING_WORKFLOW = "notion-user-mapping"

# The three real runner services (already running + already in the SSRF
# allowlist config/allowed-runners.json). health_url="" → no plain health path
# on these services (/ and /health return 404), so health checks fall back to
# base_url and never report a false "down". auth_type=none → no secret_ref.
RUNNERS: list[dict] = [
    {
        "name": "티켓 러너",
        "description": "티켓 생성·조회·상태변경 실행기 (claude-ticket-runner)",
        "base_url": "http://127.0.0.1:8787",
        "capabilities": {
            "actions": ["create_ticket", "get_ticket", "update_status", "list_tickets"],
            "domain": "ticketing",
        },
        "tags": ["ticketing", "claude", "local"],
    },
    {
        "name": "요청 해석기",
        "description": "자연어 업무요청 해석기 (claude-request-interpreter)",
        "base_url": "http://127.0.0.1:8788",
        "capabilities": {
            "actions": ["interpret_request", "extract_intent", "extract_entities"],
            "domain": "nlu",
        },
        "tags": ["nlu", "claude", "local"],
    },
    {
        "name": "업무 도우미",
        "description": "통합 업무 도우미 실행기 (claude-work-assistant)",
        "base_url": "http://127.0.0.1:8789",
        "capabilities": {
            # AI-04: 실제로 러너가 받는 경로는 /v1/assistant/message·/context/sync·/quiz
            # 셋뿐이다(assistant.py do_POST). 이전 값("dispatch"·"summarize"·"compose_report")은
            # 시드된 적 없는 기능을 광고했다 — 실재하는 세 경로로 맞춘다.
            "actions": ["send_message", "sync_context", "generate_quiz"],
            "domain": "assistant",
        },
        "tags": ["assistant", "claude", "local"],
    },
]

# Prompts keyed by the runner they drive. content is real operator-facing
# instruction text (not lorem-ipsum). Each is published so it is actually usable.
PROMPTS: list[dict] = [
    {
        "name": "티켓 분류·트리아지",
        "runner_name": "티켓 러너",
        "purpose": "사용자 업무요청을 티켓 유형·우선순위로 분류하고 담당 큐를 제안한다.",
        "content": (
            "당신은 ClovirONE 사내 업무 티켓 분류기다. 입력으로 사용자의 업무요청 원문과\n"
            "요청자(이름·이메일·부서)를 받는다. 다음을 판단해 구조화된 결과만 낸다.\n\n"
            "1. 유형(type): 문의 / 요청 / 장애 / 변경 / 기타 중 하나.\n"
            "2. 우선순위(priority): 긴급 / 높음 / 보통 / 낮음. 업무 중단·마감 임박이면 상향.\n"
            "3. 요약(summary): 한 문장, 존댓말 없이 사실만.\n"
            "4. 담당 큐(queue): 인프라 / 정보보안 / 경영지원 / 개발 / 미지정.\n\n"
            "판단 근거가 부족하면 임의로 지어내지 말고 '미지정'으로 두고 clarify에 물어볼\n"
            "질문 한 개를 담는다. 개인정보(주민번호·전화번호)는 결과에 그대로 담지 않는다."
        ),
    },
    {
        "name": "자연어 업무요청 해석",
        "runner_name": "요청 해석기",
        "purpose": "자유 문장으로 들어온 업무요청을 실행 가능한 액션 구조로 변환한다.",
        "content": (
            "당신은 ClovirONE 업무요청 해석기다. 사용자의 자유 문장을 받아, 플랫폼이 실행할\n"
            "수 있는 액션으로 옮긴다. 반드시 다음만 판단한다.\n\n"
            "- intent: create_ticket / query_status / assign / report / help 중 하나.\n"
            "- entities: 대상(프로젝트/티켓 번호), 담당자(이름 또는 이메일), 기한, 관련 부서.\n"
            "- confidence: 0.0~1.0. 0.6 미만이면 실행하지 말고 사용자에게 되물을 질문을 만든다.\n\n"
            "담당자는 이름만 오면 Notion user id로 매핑해야 하므로, 이메일이 없으면 그대로 이름을\n"
            "넘기고 매핑은 후속 워크플로에 맡긴다(여기서 지어내지 않는다). 실행 부작용이 있는\n"
            "액션(create_ticket, assign)은 confidence가 높아도 승인 정책을 따른다."
        ),
    },
    {
        "name": "주간 업무 리포트 생성",
        "runner_name": "업무 도우미",
        "purpose": "한 주 동안 처리된 티켓·요청을 요약한 리포트 초안을 만든다.",
        "content": (
            "당신은 ClovirONE 주간 업무 리포트 작성기다. 지난 7일간의 티켓·요청 처리 내역을\n"
            "입력으로 받아, 팀 공유용 리포트 초안을 한국어 존댓말로 작성한다.\n\n"
            "구성:\n"
            "1. 한 주 요약 — 처리 건수, 유형별 분포, 미해결 이월 건수.\n"
            "2. 주요 처리 내역 — 우선순위 높음 이상 항목을 불릿으로.\n"
            "3. 지연·리스크 — 기한 초과했거나 담당 미지정으로 멈춘 건.\n"
            "4. 다음 주 제안 — 반복 문의는 FAQ/자동화 후보로 표시.\n\n"
            "수치는 입력 데이터로만 계산하고 추정치를 사실처럼 쓰지 않는다. 외부 링크는 넣지\n"
            "않는다. 개인정보는 담당자 표시에 필요한 이름 수준으로만 둔다."
        ),
    },
]

# Policies stored as JSON objects (content_json). Published so templates can bind
# a live policy_id. Shapes are intentionally small and enforceable.
POLICIES: list[dict] = [
    {
        "name": "승인 정책 — 쓰기 작업",
        "content": {
            "version": 1,
            "description": (
                "티켓 생성·상태변경 등 부작용이 있는 쓰기 작업의 승인 규칙. "
                "읽기 전용 작업에는 적용되지 않는다."
            ),
            "rules": {
                "write_requires_approval": True,
                "auto_approve_roles": ["system_admin"],
                "max_auto_batch": 5,
                "require_reason_over_priority": "높음",
            },
        },
    },
    {
        "name": "콘텐츠·PII 보호 정책",
        "content": {
            "version": 1,
            "description": "러너/워크플로 산출물의 콘텐츠 안전·개인정보 보호 규칙.",
            "pii": {
                "mask_emails": False,
                "mask_phone_numbers": True,
                "mask_resident_registration_numbers": True,
            },
            "content": {
                "max_output_chars": 8000,
                "block_external_links": True,
                "allowed_languages": ["ko", "en"],
            },
        },
    },
]

# Templates wire a published prompt + published policy + a real workflow target.
TEMPLATES: list[dict] = [
    {
        "name": "티켓 자동 생성 (업무요청)",
        "description": (
            "사용자 업무요청을 해석·분류해 티켓을 생성하는 자동화 템플릿. "
            "요청 해석 → 분류 프롬프트 → 승인 정책 순으로 적용된다."
        ),
        "workflow_name": WORK_ASSISTANT_WORKFLOW,
        "prompt_name": "티켓 분류·트리아지",
        "policy_name": "승인 정책 — 쓰기 작업",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_text": {"type": "string", "title": "업무요청 원문"},
                "requester_email": {"type": "string", "title": "요청자 이메일"},
                "priority_hint": {
                    "type": "string",
                    "enum": ["긴급", "높음", "보통", "낮음"],
                    "title": "우선순위 힌트",
                },
            },
            "required": ["request_text", "requester_email"],
        },
        "approval_policy": {"required": True},
    },
    {
        "name": "주간 업무 리포트 초안",
        "description": (
            "지난 한 주 처리 내역으로 팀 공유용 리포트 초안을 만드는 템플릿. "
            "리포트 프롬프트 + 콘텐츠·PII 보호 정책을 적용한다."
        ),
        "workflow_name": WORK_ASSISTANT_WORKFLOW,
        "prompt_name": "주간 업무 리포트 생성",
        "policy_name": "콘텐츠·PII 보호 정책",
        "input_schema": {
            "type": "object",
            "properties": {
                "period_start": {"type": "string", "title": "집계 시작일 (YYYY-MM-DD)"},
                "period_end": {"type": "string", "title": "집계 종료일 (YYYY-MM-DD)"},
                "team": {"type": "string", "title": "대상 팀"},
            },
            "required": ["period_start", "period_end"],
        },
        "approval_policy": {"required": False},
    },
]

# Schedules target a real workflow. Created DISABLED (enabling is approval-gated,
# spec §20) with next_run_at unset — enable_schedule computes it at approval time.
SCHEDULES: list[dict] = [
    {
        "name": "주간 업무 리포트 (월요일 09:00)",
        "description": "매주 월요일 오전 9시(Asia/Seoul)에 주간 업무 리포트 워크플로를 실행한다.",
        "workflow_name": WORK_ASSISTANT_WORKFLOW,
        "cron_expression": cron.PRESETS["weekly"],  # "0 9 * * 1"
        "timezone": "Asia/Seoul",
        "payload_template": {
            "task": "weekly_report",
            "scope": "team",
            "delivery": "notion",
        },
        "retry_policy": {"max_retries": 2, "backoff_seconds": 120},
        "timeout_seconds": 300,
    },
]


def resolve_owner_id(db: Session) -> str | None:
    """Confirm the ground-truth system_admin id exists; else fall back to the
    first active system_admin. Returns None only when no admin exists at all
    (e.g. a fresh local DB) — all created_by columns are nullable, so seeding
    still proceeds with a clear warning."""
    if db.get(User, SEED_OWNER_ID) is not None:
        return SEED_OWNER_ID
    fallback = db.execute(
        select(User)
        .where(User.role == ROLE_SYSTEM_ADMIN, User.active.is_(True))
        .order_by(User.created_at)
    ).scalars().first()
    if fallback is not None:
        print(
            f"  ! 지정된 owner id({SEED_OWNER_ID})가 없어 첫 system_admin으로 대체: "
            f"{fallback.email}"
        )
        return fallback.id
    print(
        "  ! system_admin 계정이 없습니다 — created_by=None으로 시드합니다 "
        "(로컬 검증 환경에서 정상)."
    )
    return None


def ensure_workflows(db: Session, allowlists: AllowlistRegistry) -> None:
    """Make the two referenced workflows exist (idempotent by name). On the
    server they are already registered → skipped; on a fresh local DB they are
    created so templates/schedules have a valid target_ref."""
    created = seed_known_workflows(db, allowlists=allowlists)
    for name in (WORK_ASSISTANT_WORKFLOW, NOTION_MAPPING_WORKFLOW):
        state = "created" if name in created else "skipped"
        print(f"  [workflow] {name}: {state}")


def get_workflow_id(db: Session, name: str) -> str:
    row = db.execute(select(Workflow).where(Workflow.name == name)).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"필수 Workflow가 없습니다: {name}")
    return row.id


def seed_runners(db: Session, allowlists: AllowlistRegistry, owner_id: str | None) -> None:
    print("[Runners]")
    for spec in RUNNERS:
        existing = db.execute(
            select(Runner).where(Runner.name == spec["name"])
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [runner] {spec['name']}: skipped")
            continue
        config = RunnerConfig(
            name=spec["name"],
            description=spec["description"],
            provider_type="local_http",
            base_url=spec["base_url"],
            health_url="",  # no plain health path; falls back to base_url
            capabilities=spec["capabilities"],
            auth_type="none",
            timeout_seconds=60,
            concurrency_limit=1,
            owner="플랫폼 운영팀",
            tags=spec["tags"],
        )
        # create_runner forces enabled=False (spec §15.5: new runners start
        # disabled and require approval to enable) — respected, not overridden.
        create_runner(db, config, allowlists=allowlists, created_by=owner_id)
        print(f"  [runner] {spec['name']}: created (disabled per spec §15.5)")


def publish_versioned(db: Session, row: Prompt | Policy, now: datetime) -> None:
    """Drive draft → test → review → published through the real lifecycle."""
    for step in ("test", "review", "published"):
        transition(db, row, step, now=now)


def seed_prompts(db: Session, owner_id: str | None, now: datetime) -> None:
    print("[Prompts]")
    for spec in PROMPTS:
        exists = db.execute(
            select(Prompt.id).where(Prompt.name == spec["name"]).limit(1)
        ).first()
        if exists is not None:
            print(f"  [prompt] {spec['name']}: skipped")
            continue
        runner = db.execute(
            select(Runner).where(Runner.name == spec["runner_name"])
        ).scalar_one_or_none()
        row = Prompt(
            name=spec["name"],
            purpose=spec["purpose"],
            version=1,
            content=spec["content"],
            status="draft",
            runner_id=runner.id if runner is not None else None,
            created_by=owner_id,
        )
        db.add(row)
        db.flush()
        publish_versioned(db, row, now)
        print(f"  [prompt] {spec['name']}: created + published (v1)")


def seed_policies(db: Session, owner_id: str | None, now: datetime) -> None:
    print("[Policies]")
    for spec in POLICIES:
        exists = db.execute(
            select(Policy.id).where(Policy.name == spec["name"]).limit(1)
        ).first()
        if exists is not None:
            print(f"  [policy] {spec['name']}: skipped")
            continue
        row = Policy(
            name=spec["name"],
            version=1,
            content_json=json.dumps(spec["content"], ensure_ascii=False),
            status="draft",
            created_by=owner_id,
        )
        db.add(row)
        db.flush()
        publish_versioned(db, row, now)
        print(f"  [policy] {spec['name']}: created + published (v1)")


def seed_templates(db: Session, owner_id: str | None) -> None:
    print("[Automation Templates]")
    for spec in TEMPLATES:
        existing = db.execute(
            select(AutomationTemplate).where(AutomationTemplate.name == spec["name"])
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [template] {spec['name']}: skipped")
            continue
        workflow_id = get_workflow_id(db, spec["workflow_name"])
        prompt = get_published(db, Prompt, spec["prompt_name"])
        policy = get_published(db, Policy, spec["policy_name"])
        if prompt is None or policy is None:
            raise RuntimeError(
                f"Template '{spec['name']}'의 published prompt/policy가 없습니다."
            )
        row = AutomationTemplate(
            name=spec["name"],
            description=spec["description"],
            input_schema_json=json.dumps(spec["input_schema"], ensure_ascii=False),
            target_type=TMPL_TARGET_WORKFLOW,
            target_ref=workflow_id,
            prompt_id=prompt.id,
            policy_id=policy.id,
            approval_policy_json=json.dumps(spec["approval_policy"], ensure_ascii=False),
            enabled=False,
            created_by=owner_id,
        )
        db.add(row)
        db.flush()
        print(f"  [template] {spec['name']}: created (disabled)")


def seed_schedules(db: Session, owner_id: str | None) -> None:
    print("[Schedules]")
    for spec in SCHEDULES:
        existing = db.execute(
            select(Schedule).where(Schedule.name == spec["name"])
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [schedule] {spec['name']}: skipped")
            continue
        workflow_id = get_workflow_id(db, spec["workflow_name"])
        # Validate exactly like the router would before persisting.
        cron.validate_timezone(spec["timezone"])
        cron.validate_cron(spec["cron_expression"])
        workflow = db.get(Workflow, workflow_id)
        if workflow.operation_mode == "write" and workflow.approval_required:
            raise RuntimeError(
                f"Schedule '{spec['name']}': 승인 필요 쓰기 워크플로는 예약 실행 불가."
            )
        row = Schedule(
            name=spec["name"],
            description=spec["description"],
            schedule_type=TYPE_CRON,
            cron_expression=spec["cron_expression"],
            timezone=spec["timezone"],
            owner_user_id=owner_id,
            target_type=SCHED_TARGET_WORKFLOW,
            target_ref=workflow_id,
            payload_template_json=json.dumps(spec["payload_template"], ensure_ascii=False),
            retry_policy_json=json.dumps(spec["retry_policy"], ensure_ascii=False),
            misfire_policy="skip",
            concurrency_policy="skip",
            timeout_seconds=spec["timeout_seconds"],
            enabled=False,  # enabling is approval-gated (spec §20)
            next_run_at=None,  # computed at enable time
        )
        db.add(row)
        db.flush()
        print(f"  [schedule] {spec['name']}: created (disabled)")


def print_counts(db: Session) -> None:
    print("[Row counts]")
    for label, model in (
        ("runners", Runner),
        ("prompts", Prompt),
        ("policies", Policy),
        ("automation_templates", AutomationTemplate),
        ("schedules", Schedule),
    ):
        count = db.execute(select(model.id)).all()
        print(f"  {label}: {len(count)}")


def main() -> int:
    settings = Settings()
    print(f"DATABASE_URL: {settings.database_url}")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    allowlists = AllowlistRegistry(settings.config_dir)
    now = utcnow()

    with factory() as db:
        owner_id = resolve_owner_id(db)
        print("[Workflows (referenced targets)]")
        ensure_workflows(db, allowlists)
        seed_runners(db, allowlists, owner_id)
        seed_prompts(db, owner_id, now)
        seed_policies(db, owner_id, now)
        seed_templates(db, owner_id)
        seed_schedules(db, owner_id)
        db.commit()
        print_counts(db)

    print("완료: 시드가 멱등적으로 적용되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
