"""AI 정책의 종류와 적용 대상, 승인을 기다리는 AI 쓰기, 옛 정책 옮기기 (계획 3.9, D-519).

Revision ID: 0041_ai_policies
Revises: 0040_prompt_slots

## 무엇이 바뀌나

- `policies.kind` (approval · data_protection · content · legacy), `policies.applies_to_json` (액션 키 목록이거나
  ["*"]), `policies.migrated_from_id` (옛 정책에서 옮긴 초안이면 그 원본).
- `ai_action_requests`: 쓰기 승인 정책이 걸린 사람의 작업 공간 초안. 승인되면 실행기가 문서를 만든다.

## 옛 정책 (지워진 실행기 시절의 시드와 관리자가 넣은 자유 JSON)

런타임은 이 표를 한 번도 읽지 않았다. 옛 정책마다(이름마다 발행본, 없으면 가장 최근 버전 하나를 본다) **내용의
모양**으로 가른다 - 이름에는 가운뎃점과 긴 줄표가 있고 관리자가 바꿨을 수 있다.

  `rules.write_requires_approval` 가 있는 승인 규칙   → 초안 「AI 문서 만들기 승인」(쓰기 승인, 작업 공간 초안)
  `pii` 가 있는 개인정보 규칙                        → 초안 「개인정보 가리기」(모든 기능)
  `content` 가 있는 응답 규칙                        → 초안 「출력 제한」(모든 기능)

옮기지 않는 칸이 있다: `max_auto_batch`(일괄 실행이 없다), `require_reason_over_priority`(티켓 우선순위를 바꾸는 AI
동작이 없다), `allowed_languages`(강제할 방법이 없다). 원본은 모두 보관하고 종류를 `legacy` 로 둔다. 모양을 모르는
정책도 보관하고 「적용할 수 없는 형식」이라고 적는다.

**옮긴 것은 초안이다** - 관리자가 검토하고 발행할 때까지 AI 답이 바뀌지 않는다. 옮긴 것이 하나라도 있으면 활성
시스템 관리자에게 알림을 한 번 남긴다.

## 되돌리기

구조만 되돌린다(칸 셋, `ai_action_requests`). 옮긴 초안과 보관한 원본은 남는다 - 되돌린 코드에서 그 행들은 이름이
다른 평범한 정책이다.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_ai_policies"
down_revision = "0040_prompt_slots"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0041")

MOVED_NOTE = "새 형식의 초안으로 옮기고 보관했습니다."
UNKNOWN_NOTE = "적용할 수 없는 형식이라 보관했습니다."
APPROVABLE_ROLES = ("system_admin", "admin", "operator", "user")
HARD_MAX_OUTPUT_CHARS = 12000
MIN_OUTPUT_CHARS = 100


def _note(purpose: str | None, note: str) -> str:
    return note if not purpose else f"{note} {purpose}"


def _free_name(conn, base: str) -> str:
    name, n = base, 1
    while conn.execute(sa.text("SELECT 1 FROM policies WHERE name = :n LIMIT 1"), {"n": name}).first():
        n += 1
        name = f"{base} {n}"
    return name


def _converted(content: dict) -> list[tuple[str, str, list[str], dict, str]]:
    """옛 내용 → [(새 이름, 종류, 적용 대상, 규칙, 설명)]. 모르는 모양이면 빈 목록."""
    out = []
    rules = content.get("rules") if isinstance(content.get("rules"), dict) else None
    if rules is not None and "write_requires_approval" in rules:
        roles = [r for r in (rules.get("auto_approve_roles") or []) if r in APPROVABLE_ROLES]
        out.append(("AI 문서 만들기 승인", "approval", ["workspace.draft"], {
            "write_requires_approval": bool(rules.get("write_requires_approval")),
            "auto_approve_roles": sorted(set(roles), key=APPROVABLE_ROLES.index),
        }, "작업 공간의 AI 초안을 문서로 저장하기 전에 승인을 받습니다."))
    pii = content.get("pii") if isinstance(content.get("pii"), dict) else None
    if pii is not None:
        out.append(("개인정보 가리기", "data_protection", ["*"], {
            "mask_emails": bool(pii.get("mask_emails", False)),
            "mask_phone_numbers": bool(pii.get("mask_phone_numbers", True)),
            "mask_resident_registration_numbers": bool(pii.get("mask_resident_registration_numbers", True)),
        }, "AI 에 보내는 글과 받은 답에서 개인정보를 가립니다."))
    limits = content.get("content") if isinstance(content.get("content"), dict) else None
    if limits is not None:
        cap = limits.get("max_output_chars")
        cap = max(MIN_OUTPUT_CHARS, min(int(cap), HARD_MAX_OUTPUT_CHARS)) if isinstance(cap, int) else None
        out.append(("출력 제한", "content", ["*"], {
            "max_output_chars": cap, "block_external_links": bool(limits.get("block_external_links", False)),
        }, "AI 답의 길이를 줄이고 제품 밖 링크를 누를 수 없게 합니다."))
    return out


def upgrade() -> None:
    op.add_column("policies", sa.Column("kind", sa.String(24), nullable=False, server_default="legacy"))
    op.add_column("policies", sa.Column("applies_to_json", postgresql.JSONB(), nullable=False,
                                        server_default=sa.text("'[]'::jsonb")))
    op.add_column("policies", sa.Column("migrated_from_id", sa.String(36)))
    op.create_index("ix_policies_kind", "policies", ["kind"])
    op.create_table(
        "ai_action_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action_key", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("target_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.String(36)),
        sa.Column("approval_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("executed_at", sa.DateTime()),
    )
    op.create_index("ix_ai_action_requests_requested_by", "ai_action_requests", ["requested_by"])
    op.create_index("ix_ai_action_requests_approval_id", "ai_action_requests", ["approval_id"])

    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = conn.execute(sa.text(
        "SELECT id, name, version, status, purpose, content_json::text AS content FROM policies "
        "ORDER BY name, (status = 'published') DESC, version DESC"
    )).all()
    seen: set[str] = set()
    moved = unknown = 0
    for row in rows:
        try:
            content = json.loads(row.content or "{}")
        except ValueError:
            content = {}
        converted = _converted(content) if isinstance(content, dict) else []
        representative = row.name not in seen
        seen.add(row.name)
        if converted and representative:
            for base, kind, targets, rules, purpose in converted:
                conn.execute(sa.text(
                    "INSERT INTO policies (id, name, purpose, version, content_json, status, kind, applies_to_json, "
                    "migrated_from_id, created_at) VALUES (:id, :name, :purpose, 1, CAST(:rules AS jsonb), 'draft', "
                    ":kind, CAST(:targets AS jsonb), :origin, :at)"
                ), {"id": str(uuid.uuid4()), "name": _free_name(conn, base), "purpose": purpose,
                    "rules": json.dumps(rules, ensure_ascii=False), "kind": kind,
                    "targets": json.dumps(targets), "origin": row.id, "at": now})
                moved += 1
        note = MOVED_NOTE if converted else UNKNOWN_NOTE
        if not converted:
            unknown += 1
        conn.execute(sa.text(
            "UPDATE policies SET status = 'archived', kind = 'legacy', purpose = :purpose WHERE id = :id"
        ), {"purpose": _note(row.purpose, note), "id": row.id})
    logger.info("0041: 옛 정책 %s건을 보관했고 새 형식의 초안 %s건을 만들었다(모양을 모르는 것 %s건)",
                len(rows), moved, unknown)

    if moved:
        admins = conn.execute(sa.text(
            "SELECT id FROM users WHERE role = 'system_admin' AND active AND archived_at IS NULL"
        )).scalars().all()
        for admin_id in admins:
            conn.execute(sa.text(
                "INSERT INTO notifications (id, user_id, type, audience, title, body, related_object_type, created_at) "
                "VALUES (:id, :user_id, 'ai_policy_migrated', 'admin', :title, :body, 'policy_review', :at)"
            ), {"id": str(uuid.uuid4()), "user_id": admin_id,
                "title": "옛 AI 정책을 새 형식의 초안으로 옮겼습니다",
                "body": "정책 화면에서 옮긴 초안을 검토하고 발행하면 AI 요청에 적용됩니다.", "at": now})


def downgrade() -> None:
    op.drop_index("ix_ai_action_requests_approval_id", table_name="ai_action_requests")
    op.drop_index("ix_ai_action_requests_requested_by", table_name="ai_action_requests")
    op.drop_table("ai_action_requests")
    op.drop_index("ix_policies_kind", table_name="policies")
    op.drop_column("policies", "migrated_from_id")
    op.drop_column("policies", "applies_to_json")
    op.drop_column("policies", "kind")
