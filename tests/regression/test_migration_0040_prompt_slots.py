"""0040 — 프롬프트 사용처와 세 단계 생명주기 (계획 3.8, D-518).

못박는 성질:
1. 「테스트」와 「검토」 상태의 프롬프트와 정책은 초안이 된다.
2. 지워진 실행기를 위한 시드 프롬프트는 상태와 관계없이 보관되고, 설명 앞에 까닭이 붙는다(원래 설명은 남는다).
3. 사용처 없이 발행돼 있던 프롬프트는 보관된다 - 이제 발행은 「이 사용처에서 지금 쓴다」는 뜻이다. 초안은 그대로다.
4. 어떤 옛 프롬프트도 사용처에 자동으로 붙지 않는다 - 업그레이드가 AI 답을 몰래 바꾸지 않는다.
5. `schedules.prompt_id` 가 사라지고 `prompts.slot` · `ai_usage_records.prompt_id` 가 생긴다. 내리면 구조가 돌아온다.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0039_ai_usage_records"
WHEN = datetime(2026, 9, 1, 0, 0, 0)


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


def _prompt(conn, *, name: str, content: str, status: str, purpose=None) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO prompts (id, name, purpose, version, content, status, created_at) "
        "VALUES (:id, :name, :purpose, 1, :content, :status, :at)"
    ), {"id": row_id, "name": name, "purpose": purpose, "content": content, "status": status, "at": WHEN})
    return row_id


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


@pytest.mark.real_db
def test_old_prompts_are_sorted_out_without_changing_any_answer(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            seeded = _prompt(conn, name="티켓 분류", status="published", purpose="티켓을 분류한다.",
                             content="당신은 ClovirONE 사내 업무 티켓 분류기다. 입력으로 ...")
            seeded_draft = _prompt(conn, name="요청 해석", status="review",
                                   content="당신은 ClovirONE 업무요청 해석기다. ...")
            testing = _prompt(conn, name="시험 중", status="test", content="요약해 주세요.")
            published = _prompt(conn, name="발행본", status="published", content="세 줄로 요약해 주세요.")
            drafted = _prompt(conn, name="초안", status="draft", content="초안입니다.")
            conn.execute(sa.text(
                "INSERT INTO policies (id, name, version, content_json, status, created_at) "
                "VALUES (:id, '검토 정책', 1, CAST('{}' AS jsonb), 'review', :at)"
            ), {"id": str(uuid.uuid4()), "at": WHEN})
        # 이 마이그레이션만 올려 본다 - 다음 0041 은 옛 정책을 모두 보관하므로 head 까지 가면 정책 상태를 잴 수 없다.
        _alembic(db_url, "upgrade", "0040_prompt_slots")

        with engine.connect() as conn:
            rows = {r.id: r for r in conn.execute(sa.text("SELECT id, status, purpose, slot FROM prompts")).all()}
            policy = conn.execute(sa.text("SELECT status FROM policies WHERE name = '검토 정책'")).scalar_one()
        assert rows[seeded].status == "archived"
        assert rows[seeded].purpose == "지워진 실행기용 프롬프트라 보관했습니다. 티켓을 분류한다."
        assert rows[seeded_draft].status == "archived"
        assert rows[testing].status == "draft" and policy == "draft"
        assert rows[published].status == "archived"
        assert rows[published].purpose.startswith("사용처가 없어 보관했습니다.")
        assert rows[drafted].status == "draft" and rows[drafted].purpose is None
        assert {r.slot for r in rows.values()} == {None}, "옛 프롬프트가 사용처에 붙었다"

        assert "prompt_id" not in _columns(engine, "schedules")
        assert "slot" in _columns(engine, "prompts") and "prompt_id" in _columns(engine, "ai_usage_records")

        _alembic(db_url, "downgrade", BEFORE)
        assert "prompt_id" in _columns(engine, "schedules")
        assert "slot" not in _columns(engine, "prompts")
        assert "prompt_id" not in _columns(engine, "ai_usage_records")
        _alembic(db_url, "upgrade", "head")
        assert "slot" in _columns(engine, "prompts")
    finally:
        engine.dispose()
