"""0029 — 회차의 소유자가 팀이 됐는가 (D-482, 1단계).

여기서 못박는 성질 넷:

1. **스키마가 모델과 같은 모양이다** — `department_id` 칼럼·SET NULL FK·인덱스, 유일 축이
   프로젝트에서 팀(`coalesce(department_id, '')`)으로 옮겨졌고 `project_id` 는 아직 남아 있다
   (0030 이 걷는다). 시험 DB 는 conftest 가 `alembic upgrade head` 로 만들므로 이 단언이
   통과하면 0029 의 DDL 이 실제로 그 모양을 만들었다는 뜻이다.
2. **SET NULL 이 실제로 동작한다** — 팀을 지우면 회차는 남고 팀만 풀린다(팀 미정).
3. **백필이 추측하지 않는다** — 열린 회차는 지금의 업무 소유(O1·O2)를 따르고, 닫힌 회차는
   감사 증거가 닫힌 시점의 팀을 증명할 때만(C1·C2) 채우며, 나머지는 미정으로 남는다.
   프로젝트가 닫힌 뒤 다른 팀으로 옮겨져도 옛 회차의 팀은 따라가지 않는다.
4. **preflight 가 충돌에서 멈춘다** — 같은 팀에 활성 회차 둘, 같은 이름 둘, 조직 불일치를
   자동으로 닫거나 합치거나 이름을 바꾸지 않고 행을 나열해 중단한다.

마이그레이션 모듈은 앱 코드를 import 하지 않으므로 시험이 그 파일을 직접 읽어 같은 SQL 을
씨앗 위에 돌린다(0026 이 `_slugify` 두 벌을 대조하는 것과 같은 이유).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.audit.models import AuditLog
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work.models import Sprint

pytestmark = pytest.mark.regression

TODAY = date(2026, 9, 14)
_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0029_sprint_team_owner.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0029", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _indexdefs(db, table: str) -> dict[str, str]:
    rows = db.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :t"), {"t": table}
    ).all()
    return {name: definition for name, definition in rows}


# ── 1 · 스키마 모양 ───────────────────────────────────────────────────────────


def test_sprints_have_a_team_column_and_still_carry_the_legacy_project(db):
    cols = _cols(db, "sprints")
    assert "department_id" in cols, "팀 칸이 없다 — 0029 가 안 돌았다"
    assert "project_id" in cols, "project_id 는 0030 까지 남아야 한다(되돌리기·대조용)"


def test_the_team_fk_sets_null_and_is_indexed(db):
    insp = inspect(db.get_bind())
    fks = {tuple(fk["constrained_columns"]): fk for fk in insp.get_foreign_keys("sprints")}
    fk = fks.get(("department_id",))
    assert fk is not None, "FK 선언이 없다"
    assert fk["referred_table"] == "org_units"
    assert (fk.get("options") or {}).get("ondelete", "").upper() == "SET NULL"
    assert "ix_sprints_department_id" in _indexdefs(db, "sprints")


def test_the_unique_axes_moved_from_project_to_team(db):
    defs = _indexdefs(db, "sprints")
    assert "uq_sprints_name" in defs and "uq_sprints_active" in defs
    assert "department_id" in defs["uq_sprints_name"] and "project_id" not in defs["uq_sprints_name"]
    assert "department_id" in defs["uq_sprints_active"] and "project_id" not in defs["uq_sprints_active"]
    active = defs["uq_sprints_active"].replace("::text", "").replace("(state)", "state")
    assert "WHERE (state = 'active')" in active


# ── 2 · SET NULL 실동작 ───────────────────────────────────────────────────────


def test_deleting_a_team_leaves_the_sprint_unassigned(db):
    team = Department(name="0029팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.flush()
    sprint = Sprint(
        name="0029 회차", department_id=team.id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY, ends_on=TODAY + timedelta(days=7), state="planned",
    )
    db.add(sprint)
    db.commit()
    db.execute(text("DELETE FROM org_units WHERE id = :i"), {"i": team.id})
    db.commit()
    db.expire_all()
    row = db.get(Sprint, sprint.id)
    assert row is not None, "팀을 지우면 회차가 사라졌다 — 기록이 유실된다"
    assert row.department_id is None


# ── 3 · 백필 규칙 ─────────────────────────────────────────────────────────────


@pytest.fixture()
def legacy_world(db):
    """팀 둘, 프로젝트 셋(A·B·조직 공통), 그리고 규칙마다 하나씩의 레거시 회차."""
    team_a = Department(name="0029 A팀", org_id=DEFAULT_ORG_ID)
    team_b = Department(name="0029 B팀", org_id=DEFAULT_ORG_ID)
    db.add_all([team_a, team_b])
    db.flush()
    pa = work_codes.insert_with_code(
        db, Project(name="0029 A 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_a.id)
    )
    pb = work_codes.insert_with_code(
        db, Project(name="0029 B 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_b.id)
    )
    p0 = work_codes.insert_with_code(
        db, Project(name="0029 공통 프로젝트", org_id=DEFAULT_ORG_ID)
    )
    db.flush()

    made = 0

    def sprint(name, *, project_id, state, department_id=None, updated_at=None):
        row = Sprint(
            name=name, project_id=project_id, department_id=department_id,
            org_id=DEFAULT_ORG_ID,
            starts_on=TODAY - timedelta(days=10), ends_on=TODAY + timedelta(days=4),
            state=state,
        )
        if updated_at is not None:
            row.updated_at = updated_at
        db.add(row)
        db.flush()
        return row

    def ticket(sprint_row, project):
        nonlocal made
        made += 1
        row = Ticket(
            title=f"0029 티켓 {made}", notion_page_id=f"mig29-{made}",
            project_uid=project.id, project_link=PROJECT_LINK_OK, status="진행",
            org_id=DEFAULT_ORG_ID, source="notion", notion_ticket_number=9000 + made,
            seq=9000 + made, sprint_id=sprint_row.id,
        )
        db.add(row)
        db.flush()
        return row

    def audit(action, object_type, object_id, *, after, at):
        db.add(AuditLog(
            user_id=None, action=action, object_type=object_type, object_id=object_id,
            after_json=json.dumps(after), created_at=at,
        ))
        db.flush()

    long_ago = datetime(2026, 8, 1, 9, 0)
    close_time = datetime(2026, 9, 1, 9, 0)
    after_close = datetime(2026, 9, 10, 9, 0)

    world = {"team_a": team_a, "team_b": team_b, "pa": pa, "pb": pb, "p0": p0}
    # O1 — 열린 프로젝트 회차 → 프로젝트의 현재 팀.
    world["o1"] = sprint("O1 열린 프로젝트 회차", project_id=pa.id, state="planned")
    # O2 — 열린 프로젝트 없는 회차, 담긴 티켓이 전부 A 프로젝트.
    world["o2"] = sprint("O2 열린 팀 회차", project_id=None, state="planned")
    ticket(world["o2"], pa)
    ticket(world["o2"], pa)
    # 팀이 섞인 열린 회차 → 미정 + mixed 보고.
    world["mixed"] = sprint("섞인 회차", project_id=None, state="planned")
    ticket(world["mixed"], pa)
    ticket(world["mixed"], pb)
    # 조직 공통 프로젝트만 담긴 회차 → 팀이 없으므로 미정.
    world["common"] = sprint("공통만 담긴 회차", project_id=None, state="planned")
    ticket(world["common"], p0)
    # C1 — 닫힌 프로젝트 회차. 닫힌 시점의 증거는 A, 그 뒤 프로젝트가 B 로 옮겨졌다.
    world["c1"] = sprint("C1 닫힌 프로젝트 회차", project_id=pa.id, state="closed",
                         updated_at=close_time)
    audit("sprint.close", "sprint", world["c1"].id, after={"sprint_id": world["c1"].id}, at=close_time)
    audit("project.create", "project", pa.id, after={"dept_id": team_a.id, "org_id": DEFAULT_ORG_ID},
          at=long_ago)
    audit("project.update", "project", pa.id, after={"dept_id": team_b.id, "org_id": DEFAULT_ORG_ID},
          at=after_close)
    # 증거가 없는 닫힌 프로젝트 회차 → 미정(현재 부서로 추측하지 않는다).
    world["c1_none"] = sprint("증거 없는 닫힌 회차", project_id=pb.id, state="closed",
                              updated_at=close_time)
    # C2 — 닫힌 프로젝트 없는 회차, 담긴 티켓 프로젝트(A)의 증거가 하나로 일치.
    world["c2"] = sprint("C2 닫힌 팀 회차", project_id=None, state="closed", updated_at=close_time)
    ticket(world["c2"], pa)
    # 빈 닫힌 회차 → 미정.
    world["empty"] = sprint("빈 닫힌 회차", project_id=None, state="closed", updated_at=close_time)
    db.commit()
    return world


def _plan(db, module) -> dict[str, tuple[str, str]]:
    conn = db.connection()
    module.plan_team_assignments(conn)
    rows = conn.execute(text("SELECT sprint_id, department_id, rule FROM sprint_team_plan")).all()
    return {sid: (dept, rule) for sid, dept, rule in rows}


def test_open_sprints_follow_current_ownership(db, legacy_world):
    module = _load_migration()
    plan = _plan(db, module)
    w = legacy_world
    assert plan[w["o1"].id] == (w["team_a"].id, "O1")
    assert plan[w["o2"].id] == (w["team_a"].id, "O2")
    assert w["mixed"].id not in plan, "팀이 섞인 회차를 임의로 한 팀에 귀속했다"
    assert w["common"].id not in plan, "조직 공통 프로젝트만 담긴 회차에 팀을 지어냈다"


def test_closed_sprints_follow_evidence_at_close_time_not_current_ownership(db, legacy_world):
    module = _load_migration()
    plan = _plan(db, module)
    w = legacy_world
    # 프로젝트는 지금 B 팀이지만 닫힌 시점의 증거는 A — 옛 회차는 A 로 남는다.
    assert plan[w["c1"].id] == (w["team_a"].id, "C1")
    assert w["c1_none"].id not in plan, "증거 없는 닫힌 회차를 현재 부서로 추측했다"
    assert plan[w["c2"].id] == (w["team_a"].id, "C2")
    assert w["empty"].id not in plan


def test_apply_fills_only_planned_rows_and_reports_the_rest(db, legacy_world):
    module = _load_migration()
    conn = db.connection()
    module.plan_team_assignments(conn)
    assert module.preflight_conflicts(conn) == []
    result = module.apply_team_assignments(conn)
    db.expire_all()
    w = legacy_world
    assert result["by_rule"] == {"O1": 1, "O2": 1, "C1": 1, "C2": 1}
    assert db.get(Sprint, w["o1"].id).department_id == w["team_a"].id
    assert db.get(Sprint, w["c1"].id).department_id == w["team_a"].id
    for key in ("mixed", "common", "c1_none", "empty"):
        assert db.get(Sprint, w[key].id).department_id is None, key
    assert w["mixed"].id in result["mixed"]
    # 이 시험이 만든 미정 넷은 전부 센다(다른 시험의 행이 섞여 있어도 최소 넷).
    assert result["unassigned"] >= 4


# ── 4 · preflight ────────────────────────────────────────────────────────────


def _legacy_unique_axes(db):
    """0029 이전의 유일 축(프로젝트별 활성 하나·프로젝트별 이름)으로 잠시 되돌린다.

    시험 DB 는 이미 head 라서 팀 축의 유일 인덱스가 걸려 있다. 레거시 데이터가 실제로
    가질 수 있던 모양 — 같은 팀의 프로젝트 둘에 활성 회차가 하나씩, 같은 이름이 프로젝트만
    다르게 둘 — 을 심으려면 그 축을 내려야 한다. 트랜잭션 안의 DDL 이라 시험이 끝나면 되감긴다.
    """
    db.execute(text("DROP INDEX uq_sprints_active"))
    db.execute(text("DROP INDEX uq_sprints_name"))
    db.execute(text("CREATE UNIQUE INDEX uq_sprints_name ON sprints (org_id, project_id, name)"))
    db.execute(text(
        "CREATE UNIQUE INDEX uq_sprints_active ON sprints (org_id, coalesce(project_id, '')) "
        "WHERE state = 'active'"
    ))


def test_preflight_stops_on_two_active_sprints_in_one_team(db, legacy_world):
    module = _load_migration()
    w = legacy_world
    _legacy_unique_axes(db)
    # 옛 축에서는 프로젝트마다 활성 하나가 허용됐다 — 같은 팀의 프로젝트 둘이 각각 활성 회차를
    # 가지면 팀 축으로 옮기는 순간 충돌한다.
    pa2 = work_codes.insert_with_code(
        db, Project(name="0029 A 둘째 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=w["team_a"].id)
    )
    db.flush()
    for name, project in (("활성 하나", w["pa"]), ("활성 둘", pa2)):
        db.add(Sprint(
            name=name, project_id=project.id, org_id=DEFAULT_ORG_ID,
            starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4), state="active",
        ))
    db.commit()
    conn = db.connection()
    module.plan_team_assignments(conn)
    problems = module.preflight_conflicts(conn)
    assert any("활성 회차 충돌" in p and "활성 하나" in p and "활성 둘" in p for p in problems), problems
    # 중단이지 정리가 아니다 — 아무것도 적용되지 않았다.
    db.expire_all()
    assert db.get(Sprint, w["o1"].id).department_id is None


def test_preflight_stops_on_duplicate_names_within_a_team(db, legacy_world):
    module = _load_migration()
    w = legacy_world
    _legacy_unique_axes(db)
    # 옛 축에서는 프로젝트가 다르면 같은 이름이 허용됐다. O2 로 A팀이 되는 프로젝트 없는 회차와
    # O1 로 A팀이 되는 프로젝트 회차가 같은 이름이면 팀 축에서 둘이 된다.
    db.add(Sprint(
        name="O2 열린 팀 회차", project_id=w["pa"].id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=30), ends_on=TODAY - timedelta(days=20), state="planned",
    ))
    db.commit()
    conn = db.connection()
    module.plan_team_assignments(conn)
    problems = module.preflight_conflicts(conn)
    assert any("이름 충돌" in p and "O2 열린 팀 회차" in p for p in problems), problems


def test_preflight_stops_when_the_team_belongs_to_another_org(db, legacy_world):
    module = _load_migration()
    from app.org.models import Organization

    other = Organization(id="0029-other-org", slug="mig-0029", name="다른 조직")
    db.add(other)
    db.flush()
    foreign_team = Department(name="0029 타조직팀", org_id=other.id)
    db.add(foreign_team)
    db.flush()
    foreign_project = work_codes.insert_with_code(
        db, Project(name="0029 타조직 프로젝트", org_id=other.id, dept_id=foreign_team.id)
    )
    db.add(Sprint(
        name="조직이 어긋난 회차", project_id=foreign_project.id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4), state="planned",
    ))
    db.commit()
    conn = db.connection()
    module.plan_team_assignments(conn)
    problems = module.preflight_conflicts(conn)
    assert any("조직 불일치" in p and "조직이 어긋난 회차" in p for p in problems), problems
