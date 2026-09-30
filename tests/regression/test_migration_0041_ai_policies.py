"""0041 — AI 정책의 종류와 적용 대상, 승인을 기다리는 AI 쓰기, 옛 정책 옮기기 (계획 3.9, D-519).

못박는 성질:
1. 옛 승인 규칙은 초안 「AI 문서 만들기 승인」(작업 공간 초안)으로, 옛 개인정보 · 응답 규칙은 초안 「개인정보 가리기」와
   「출력 제한」(모든 기능)으로 옮겨진다. 옮기지 못하는 칸(일괄 수, 우선순위 사유, 언어)은 버린다.
2. 옮긴 것은 **초안**이다 - 발행하기 전에는 아무 요청에도 걸리지 않는다. 옮긴 초안은 원본을 가리킨다.
3. 원본은 모두 보관되고 종류가 `legacy` 가 된다. 모양을 모르는 정책도 보관되고 까닭이 적힌다. 이름마다 한 번만 옮긴다.
4. 옮긴 것이 있으면 활성 시스템 관리자에게만 알림이 한 번 간다.
5. 내리면 칸 셋과 AI 초안 표가 사라지고, 다시 올려도 된다.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0040_prompt_slots"
WHEN = datetime(2026, 9, 1, 0, 0, 0)

APPROVAL_SEED = {"version": 1, "description": "쓰기 작업의 승인 규칙", "rules": {
    "write_requires_approval": True, "auto_approve_roles": ["system_admin", "wizard"], "max_auto_batch": 5,
    "require_reason_over_priority": "높음"}}
PII_SEED = {"version": 1, "pii": {"mask_emails": False, "mask_phone_numbers": True,
                                  "mask_resident_registration_numbers": True},
            "content": {"max_output_chars": 8000, "block_external_links": True, "allowed_languages": ["ko", "en"]}}


def _alembic(url: str, action: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, action)(cfg, target)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior


def _engine(db, db_url):
    from app.core.db import normalize_database_url

    db.close()
    db.get_bind().dispose()
    return sa.create_engine(normalize_database_url(db_url), future=True)


def _policy(conn, *, name: str, version: int, status: str, content: dict, purpose=None) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO policies (id, name, purpose, version, content_json, status, created_at) "
        "VALUES (:id, :name, :purpose, :version, CAST(:content AS jsonb), :status, :at)"
    ), {"id": row_id, "name": name, "purpose": purpose, "version": version,
        "content": json.dumps(content, ensure_ascii=False), "status": status, "at": WHEN})
    return row_id


@pytest.mark.real_db
def test_old_policies_become_reviewable_drafts(db, db_url, make_user):
    active_admin = make_user("mig-admin@goodmit.co.kr", role="system_admin").id
    make_user("mig-gone@goodmit.co.kr", role="system_admin", active=False)
    make_user("mig-user@goodmit.co.kr", role="user")
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _policy(conn, name="승인 정책 — 쓰기 작업", version=1, status="archived", content=APPROVAL_SEED)
            approval = _policy(conn, name="승인 정책 — 쓰기 작업", version=2, status="published", content=APPROVAL_SEED,
                               purpose="쓰기 승인")
            pii = _policy(conn, name="콘텐츠·PII 보호 정책", version=1, status="published", content=PII_SEED)
            odd = _policy(conn, name="필수 칸", version=1, status="draft", content={"required_fields": ["title"]})
        _alembic(db_url, "upgrade", "head")

        with engine.connect() as conn:
            rows = conn.execute(sa.text(
                "SELECT id, name, status, kind, purpose, content_json::text AS content, "
                "applies_to_json::text AS targets, migrated_from_id FROM policies"
            )).all()
            notes = conn.execute(sa.text(
                "SELECT user_id, audience FROM notifications WHERE type = 'ai_policy_migrated'"
            )).all()
            tables = sa.inspect(conn).get_table_names()
        by_name = {}
        for row in rows:
            by_name.setdefault(row.name, []).append(row)

        [approval_draft] = by_name["AI 문서 만들기 승인"]
        assert (approval_draft.status, approval_draft.kind, approval_draft.migrated_from_id) == (
            "draft", "approval", approval)
        assert json.loads(approval_draft.targets) == ["workspace.draft"]
        assert json.loads(approval_draft.content) == {"write_requires_approval": True,
                                                      "auto_approve_roles": ["system_admin"]}
        [privacy] = by_name["개인정보 가리기"]
        assert (privacy.kind, json.loads(privacy.targets), privacy.migrated_from_id) == ("data_protection", ["*"], pii)
        assert json.loads(privacy.content) == {"mask_emails": False, "mask_phone_numbers": True,
                                               "mask_resident_registration_numbers": True}
        [limits] = by_name["출력 제한"]
        assert (limits.kind, limits.status) == ("content", "draft")
        assert json.loads(limits.content) == {"max_output_chars": 8000, "block_external_links": True}

        originals = [r for r in rows if r.id in {approval, pii, odd}] + by_name["승인 정책 — 쓰기 작업"]
        assert {(r.status, r.kind) for r in originals} == {("archived", "legacy")}
        assert next(r for r in rows if r.id == approval).purpose == "새 형식의 초안으로 옮기고 보관했습니다. 쓰기 승인"
        assert next(r for r in rows if r.id == odd).purpose == "적용할 수 없는 형식이라 보관했습니다."
        assert len(by_name["AI 문서 만들기 승인"]) == 1, "같은 이름의 옛 버전마다 초안을 또 만들었다"

        assert [(n.user_id, n.audience) for n in notes] == [(active_admin, "admin")]
        assert "ai_action_requests" in tables

        _alembic(db_url, "downgrade", BEFORE)
        inspector = sa.inspect(engine)
        assert "ai_action_requests" not in inspector.get_table_names()
        assert "kind" not in {c["name"] for c in inspector.get_columns("policies")}
        _alembic(db_url, "upgrade", "head")
        assert "ai_action_requests" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
