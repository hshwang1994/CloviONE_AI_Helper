"""0023(프로젝트 지식 공간)·0024(기술 태그) — 실제 자료 한 조각으로 왕복을 잰다.

REAUDIT_PLAN.md §18.1 이 요구하는 행이다: "문서 111 · 판 167 · 첨부 54 유실 0, updated_at
불변, downgrade 왕복". 랩 서버의 실제 111건 전체를 여기서 재현하지 않는다 — 그것은 §19의
운영 스냅샷 사본 리허설의 몫이다. 여기서 보는 것은 **두 마이그레이션의 SQL 자체가
옳은가**다: `RELOCATE`/`DOC_TAGS`에 실제로 있는 문서 id 접두사 하나씩을 심어 두고
그 문서가 진짜로 그 경로를 타는지, 그리고 되감았을 때 정확히 원래대로 돌아오는지를 본다.

## `@pytest.mark.real_db` 인 이유

`downgrade`/`upgrade` 는 스키마를 반복해서 DDL 로 흔드는 시험이다 — 기본 계층(공유 DB +
트랜잭션 되감기)에서 돌리면 다른 시험과 스키마 자체를 두고 경합한다(`conftest.py::
_test_database` 의 갈림길 그대로). 이 시험 전용 DB 를 받아 마음대로 내렸다 올린다.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.regression

# RELOCATE 에 실제로 있는 항목 하나 — 인천국제공항공사 1등급 태그 문서, HAASFT 로 옮겨간다.
DOC_ID = "bf28ff1d-c568-4d76-a056-840ab84c7cbc"
PROJECT_CODE = "HAASFT"
FOLDER_NAME = "01. 회의록"


def _run_migration(db_url: str, fn, *args) -> None:
    """`conftest.py::migrated_db_template` 과 같은 방법 — `DATABASE_URL` 을 이 시험
    전용 DB 로 잠깐 바꾸고 alembic 을 인프로세스로 돌린 뒤 원래 값으로 되돌린다."""
    from alembic import command as _command
    from alembic.config import Config as _Config

    cfg = _Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    try:
        fn(_command, cfg, *args)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior


@pytest.mark.real_db
def test_the_round_trip_relocates_and_tags_the_real_document_then_undoes_it(db_url):
    from app.core.db import normalize_database_url

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 0022 까지 내린다 — `db_url` 은 이미 head 까지 마이그레이션된 전용 DB 다
    # (`_test_database` 가 `migrated_db_template` 을 복제해 만든다).
    _run_migration(db_url, lambda c, cfg: c.downgrade(cfg, "0022_document_folders"))

    with engine.begin() as conn:
        # 0022 는 "문서가 있는 공간에만" 폴더를 만든다 — 빈 시험 DB 에는 만들 문서가
        # 아직 없어서 org 공간·폴더도 없다. 운영에 이미 있는 그 모양(공간 하나 + 폴더
        # 8개 중 이 시험이 쓰는 하나)을 여기서 그대로 심는다.
        org_id = conn.execute(sa.text("SELECT id FROM organizations LIMIT 1")).scalar()
        org_space = conn.execute(sa.text(
            "INSERT INTO knowledge_spaces (id, org_id, name, slug, description, owner_kind,"
            " confidential, archived, version, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :org, '팀 문서', 'reaudit-team-docs', '', 'organization',"
            " false, false, 1, :now, :now) RETURNING id"
        ), {"org": org_id, "now": now}).scalar()
        folder_id = conn.execute(sa.text(
            "INSERT INTO folders (id, space_id, parent_id, name, depth, sort_order, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :space, NULL, :name, 0, 1024, :now, :now) RETURNING id"
        ), {"space": org_space, "name": FOLDER_NAME, "now": now}).scalar()

        project_id = conn.execute(sa.text(
            "INSERT INTO projects (id, name, code, status, notion_owner_ids, org_id,"
            " version, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :name, :code, 'active', '',"
            " (SELECT org_id FROM knowledge_spaces WHERE id = :space), 1, :now, :now)"
            " RETURNING id"
        ), {"name": "인천국제공항공사 [클라우드 인프라 고도화]", "code": PROJECT_CODE,
            "space": org_space, "now": now}).scalar()

        conn.execute(sa.text(
            "INSERT INTO documents (id, space_id, folder_id, title, version, confidential,"
            " archived, source_type, created_at, updated_at)"
            " VALUES (:id, :space, :folder, '[07월 31일 인천공항공사]', 1, false, false, 'USER', :now, :now)"
        ), {"id": DOC_ID, "space": org_space, "folder": folder_id, "now": now})
        seeded_updated_at = conn.execute(sa.text(
            "SELECT updated_at FROM documents WHERE id = :id"
        ), {"id": DOC_ID}).scalar()

    # ── 올린다: 0023 이 문서를 HAASFT 공간으로, 0024 가 Git 태그를 붙여야 한다. ──
    _run_migration(db_url, lambda c, cfg: c.upgrade(cfg, "head"))

    with engine.begin() as conn:
        moved = conn.execute(sa.text(
            "SELECT d.space_id, d.folder_id, d.updated_at, s.owner_kind, p.code"
            " FROM documents d"
            " JOIN knowledge_spaces s ON s.id = d.space_id"
            " LEFT JOIN projects p ON p.id = s.owner_project_id"
            " WHERE d.id = :id"
        ), {"id": DOC_ID}).one()
        assert moved.owner_kind == "project", "HAASFT 프로젝트 공간으로 안 옮겨졌다"
        assert moved.code == PROJECT_CODE
        assert moved.folder_id is None, "새 공간의 폴더 참조가 있으면 안 된다(§14.2)"
        assert moved.updated_at == seeded_updated_at, "재배치가 updated_at 을 건드렸다 — §12.2 위반"

        tag_names = set(conn.execute(sa.text(
            "SELECT t.name FROM document_tags dt JOIN tags t ON t.id = dt.tag_id"
            " WHERE dt.document_id = :id"
        ), {"id": DOC_ID}).scalars().all())
        assert tag_names == {"Git"}, f"0024 의 DOC_TAGS 매핑과 다르다: {tag_names}"

    # ── 내린다: 정확히 원래 상태로 돌아와야 한다. ──
    _run_migration(db_url, lambda c, cfg: c.downgrade(cfg, "0022_document_folders"))

    with engine.begin() as conn:
        back = conn.execute(sa.text(
            "SELECT space_id, folder_id, updated_at FROM documents WHERE id = :id"
        ), {"id": DOC_ID}).one()
        assert back.space_id == org_space, "되감기가 원래 공간으로 안 돌아왔다"
        assert back.folder_id == folder_id, "되감기가 원래 폴더로 안 돌아왔다"
        assert back.updated_at == seeded_updated_at, "되감기가 updated_at 을 건드렸다"

        # 0024 의 되감기는 "0건으로 지운다"가 아니라 "원래 옛 태그로 되돌린다"다 —
        # OLD_TAG_LINKS 에 bf28ff1d 가 원래 달고 있던 옛 태그 둘(인천국제공항공사…·
        # 고객 프로젝트)이 있으므로, 그 둘로 정확히 되돌아와야 하고 기술 태그(Git)는
        # 남으면 안 된다.
        restored_tags = set(conn.execute(sa.text(
            "SELECT t.name FROM document_tags dt JOIN tags t ON t.id = dt.tag_id"
            " WHERE dt.document_id = :id"
        ), {"id": DOC_ID}).scalars().all())
        assert restored_tags == {"인천국제공항공사 [클라우드 인프라 고도화]", "고객 프로젝트"}, (
            f"되감기가 옛 태그로 정확히 안 돌아왔다: {restored_tags}"
        )

        project_space_gone = conn.execute(sa.text(
            "SELECT count(*) FROM knowledge_spaces WHERE owner_project_id = :p"
        ), {"p": project_id}).scalar()
        assert project_space_gone == 0, "되감기가 HAASFT 프로젝트 공간을 안 지웠다"

        # 문서 행 자체는 이 마이그레이션의 책임이 아니라 그대로 있어야 한다(유실 0).
        still_there = conn.execute(sa.text(
            "SELECT count(*) FROM documents WHERE id = :id"
        ), {"id": DOC_ID}).scalar()
        assert still_there == 1, "왕복 도중 문서 행 자체가 사라졌다 — 절대 있으면 안 된다"

    # 다시 올려서 head 로 돌려놓는다 — 시험 DB 는 끝나면 지워지지만, 습관을 들인다.
    _run_migration(db_url, lambda c, cfg: c.upgrade(cfg, "head"))
    engine.dispose()
