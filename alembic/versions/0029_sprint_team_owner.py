"""회차의 소유자는 팀이다 — `sprints.department_id` (D-482, 1단계).

## 무엇이 문제였나

`sprints` 에는 `org_id` 와 선택 `project_id` 뿐이었다. 그래서 「팀 전체 회차」가 사실은
**조직 전체 회차**였고(`project_id IS NULL` 이 조직 검사 없이 전원에게 보였다), 활성
회차가 조직당 하나뿐이라 팀 둘이 각자 회차를 열 수 없었다. 프로젝트 회차는 프로젝트를
소유자로 삼아 그 프로젝트 티켓만 담겼는데, 제품의 회차는 **팀이 한 기간에 하는 일**이라
여러 프로젝트의 티켓을 담아야 한다.

## 무엇을 하는가

1. `department_id`(FK `org_units.id`, ON DELETE SET NULL, 인덱스)를 더한다.
2. 기존 행에 팀을 채운다 — **추측하지 않는다.**
   - 열린 회차(planned·active)는 **지금의 업무 소유**와 담기 규칙(회차 팀 == 티켓 프로젝트의
     팀)을 일치시킨다: O1 프로젝트 회차 → 그 프로젝트의 현재 `dept_id`; O2 프로젝트 없는
     회차 → 담긴 티켓들의 프로젝트 `dept_id` 가 하나로 유일할 때 그 팀.
   - 닫힌 회차는 **과거 기록**이다. 프로젝트가 나중에 다른 팀으로 옮겨졌어도 옛 회차의
     소유가 따라 바뀌면 안 된다. 그래서 감사 기록(`project.create`/`project.update` 의
     `after_json.dept_id`)으로 **닫힌 시점의 팀**이 증명될 때만 채운다(C1·C2). 증거가 없거나
     어긋나면 NULL(팀 미정)로 남긴다.
   - 티켓이 없는 프로젝트 없는 회차는 미정이다. 생성자의 현재 부서로 과거를 추측하지 않는다.
3. **preflight** — 채운 결과로 같은 팀에 활성 회차가 둘이 되거나 같은 이름이 둘이 되거나
   팀의 조직과 회차의 조직이 어긋나면 **중단**한다(트랜잭션이 되돌아간다). 자동으로 닫거나
   합치거나 이름을 바꾸지 않는다 — 충돌 행을 메시지에 적어 사람이 정하게 한다.
4. 유일 인덱스를 팀 축으로 바꾼다: `uq_sprints_name (org_id, coalesce(department_id,''), name)`,
   `uq_sprints_active (org_id, coalesce(department_id,'')) WHERE state='active'`.

## 기존 행

`project_id` 는 **남긴다.** 앱은 더 이상 읽지도 쓰지도 않지만, 되돌리기와 대조를 위해
한 릴리스 동안 값을 보존한다. 삭제는 `0030` 이 한다. 미정으로 남은 건수는 NOTICE 로
보고하고, 운영에서는 `/api/admin/integrity` 의 「팀이 정해지지 않은 회차」가 같은 사실을
보여 준다 — 관리자가 회차 수정에서 팀을 정한다.

## 되돌리기

새 유일 인덱스를 지우고 옛 인덱스(`project_id` 축)를 복원한 뒤 칼럼을 지운다. `project_id`
값이 그대로 있으므로 이전 버전 앱이 그대로 돈다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_sprint_team_owner"
down_revision = "0028_document_legacy_author"
branch_labels = None
depends_on = None


# ── 백필 계획 (순수 SQL — 시험이 같은 문장을 씨앗 위에 돌린다) ──────────────
#
# 각 문장은 `sprint_team_plan(sprint_id, department_id, rule)` 임시 표에 **후보**를 넣는다.
# 먼저 잡힌 규칙이 이긴다(`WHERE NOT EXISTS`). 실제 UPDATE 는 preflight 를 지난 뒤 한 번이다.

PLAN_TABLE_SQL = (
    "CREATE TEMP TABLE sprint_team_plan ("
    " sprint_id varchar(36) PRIMARY KEY, department_id varchar(36) NOT NULL, rule varchar(8) NOT NULL)"
    " ON COMMIT DROP"
)

# O1 — 열린 프로젝트 회차: 프로젝트의 **현재** 팀. 회차의 팀은 담긴 티켓의 팀과 같아야 한다.
PLAN_O1_SQL = """
INSERT INTO sprint_team_plan (sprint_id, department_id, rule)
SELECT s.id, p.dept_id, 'O1'
  FROM sprints s
  JOIN projects p ON p.id = s.project_id
 WHERE s.department_id IS NULL
   AND s.state IN ('planned', 'active')
   AND p.dept_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sprint_team_plan x WHERE x.sprint_id = s.id)
"""

# O2 — 열린 프로젝트 없는 회차: 담긴 티켓 프로젝트의 현재 팀이 **하나로 유일**할 때.
PLAN_O2_SQL = """
INSERT INTO sprint_team_plan (sprint_id, department_id, rule)
SELECT s.id, x.dept, 'O2'
  FROM sprints s
  JOIN (
        SELECT t.sprint_id, min(p.dept_id) AS dept
          FROM tickets t
          JOIN projects p ON p.id = t.project_uid
         WHERE t.sprint_id IS NOT NULL
         GROUP BY t.sprint_id
        HAVING count(DISTINCT p.dept_id) = 1 AND count(*) = count(p.dept_id)
       ) x ON x.sprint_id = s.id
 WHERE s.department_id IS NULL
   AND s.project_id IS NULL
   AND s.state IN ('planned', 'active')
   AND NOT EXISTS (SELECT 1 FROM sprint_team_plan y WHERE y.sprint_id = s.id)
"""

# 닫힌 회차의 증거 — 닫힌 시점(sprint.close 감사, 없으면 updated_at) 이전의 마지막 프로젝트
# 감사 기록이 말하는 `dept_id`. 기록이 JSON 이 아니면 증거가 아니다.
EVIDENCE_VIEW_SQL = """
CREATE TEMP TABLE sprint_close_evidence ON COMMIT DROP AS
WITH closed AS (
    SELECT s.id AS sprint_id,
           COALESCE((SELECT max(a.created_at) FROM audit_logs a
                      WHERE a.action = 'sprint.close' AND a.object_id = s.id), s.updated_at) AS closed_at
      FROM sprints s
     WHERE s.state = 'closed' AND s.department_id IS NULL
), members AS (
    SELECT c.sprint_id, c.closed_at, s.project_id AS own_project, t.project_uid AS member_project
      FROM closed c
      JOIN sprints s ON s.id = c.sprint_id
 LEFT JOIN tickets t ON t.sprint_id = s.id
), targets AS (
    SELECT DISTINCT sprint_id, closed_at, COALESCE(own_project, member_project) AS project_id
      FROM members
     WHERE COALESCE(own_project, member_project) IS NOT NULL
), evidence AS (
    SELECT tg.sprint_id, tg.project_id,
           (SELECT CASE WHEN jsonb_typeof(a.after_json) = 'object' THEN (a.after_json ->> 'dept_id') END
              FROM audit_logs a
             WHERE a.object_type = 'project' AND a.object_id = tg.project_id
               AND a.action IN ('project.create', 'project.update')
               AND a.created_at <= tg.closed_at
             ORDER BY a.created_at DESC, a.id DESC
             LIMIT 1) AS dept_at_close
      FROM targets tg
)
SELECT * FROM evidence
"""

# C1 — 닫힌 프로젝트 회차: 닫힌 시점의 프로젝트 팀이 증명될 때만.
PLAN_C1_SQL = """
INSERT INTO sprint_team_plan (sprint_id, department_id, rule)
SELECT s.id, e.dept_at_close, 'C1'
  FROM sprints s
  JOIN sprint_close_evidence e ON e.sprint_id = s.id AND e.project_id = s.project_id
 WHERE s.department_id IS NULL
   AND s.state = 'closed'
   AND s.project_id IS NOT NULL
   AND e.dept_at_close IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sprint_team_plan y WHERE y.sprint_id = s.id)
"""

# C2 — 닫힌 프로젝트 없는 회차: 담긴 티켓 프로젝트들의 증거가 **전부 있고 하나로 일치**할 때.
PLAN_C2_SQL = """
INSERT INTO sprint_team_plan (sprint_id, department_id, rule)
SELECT s.id, x.dept, 'C2'
  FROM sprints s
  JOIN (
        SELECT e.sprint_id, min(e.dept_at_close) AS dept
          FROM sprint_close_evidence e
         GROUP BY e.sprint_id
        HAVING count(*) > 0
           AND count(*) = count(e.dept_at_close)
           AND count(DISTINCT e.dept_at_close) = 1
       ) x ON x.sprint_id = s.id
 WHERE s.department_id IS NULL
   AND s.state = 'closed'
   AND s.project_id IS NULL
   AND NOT EXISTS (SELECT 1 FROM sprint_team_plan y WHERE y.sprint_id = s.id)
"""

PLAN_SQL = (PLAN_O1_SQL, PLAN_O2_SQL, EVIDENCE_VIEW_SQL, PLAN_C1_SQL, PLAN_C2_SQL)

# preflight — 계획을 적용했을 때 생길 충돌. 어느 하나라도 있으면 중단한다.
PREFLIGHT_ACTIVE_SQL = """
WITH planned AS (
    SELECT s.id, s.name, s.state, s.org_id,
           COALESCE(s.department_id, p.department_id, '') AS team
      FROM sprints s
 LEFT JOIN sprint_team_plan p ON p.sprint_id = s.id
)
SELECT org_id, team, string_agg(id || ' «' || name || '»', ', ' ORDER BY name) AS rows
  FROM planned
 WHERE state = 'active'
 GROUP BY org_id, team
HAVING count(*) > 1
"""

PREFLIGHT_NAME_SQL = """
WITH planned AS (
    SELECT s.id, s.name, s.state, s.org_id,
           COALESCE(s.department_id, p.department_id, '') AS team
      FROM sprints s
 LEFT JOIN sprint_team_plan p ON p.sprint_id = s.id
)
SELECT org_id, team, name, string_agg(id || ' (' || state || ')', ', ' ORDER BY id) AS rows
  FROM planned
 GROUP BY org_id, team, name
HAVING count(*) > 1
"""

PREFLIGHT_ORG_SQL = """
SELECT s.id, s.name, s.org_id, d.org_id AS team_org
  FROM sprints s
  JOIN sprint_team_plan p ON p.sprint_id = s.id
  JOIN org_units d ON d.id = p.department_id
 WHERE s.org_id IS NOT NULL AND d.org_id IS NOT NULL AND s.org_id <> d.org_id
"""

APPLY_SQL = (
    "UPDATE sprints s SET department_id = p.department_id"
    "  FROM sprint_team_plan p WHERE p.sprint_id = s.id AND s.department_id IS NULL"
)

# 팀이 정해진 회차의 조직은 팀의 조직이다 (팀 미정은 그대로).
ORG_SYNC_SQL = (
    "UPDATE sprints s SET org_id = d.org_id FROM org_units d"
    " WHERE d.id = s.department_id AND (s.org_id IS NULL OR s.org_id <> d.org_id)"
)

MIXED_TEAM_SQL = """
SELECT s.id, s.name, s.state
  FROM sprints s
 WHERE s.department_id IS NULL
   AND EXISTS (SELECT 1 FROM tickets t WHERE t.sprint_id = s.id)
   AND (SELECT count(DISTINCT p.dept_id) FROM tickets t JOIN projects p ON p.id = t.project_uid
         WHERE t.sprint_id = s.id AND p.dept_id IS NOT NULL) > 1
"""


def plan_team_assignments(conn) -> None:
    """임시 표 `sprint_team_plan` 을 채운다. 시험이 씨앗 위에서 같은 함수를 부른다."""
    conn.execute(sa.text("DROP TABLE IF EXISTS sprint_team_plan"))
    conn.execute(sa.text("DROP TABLE IF EXISTS sprint_close_evidence"))
    conn.execute(sa.text(PLAN_TABLE_SQL))
    for stmt in PLAN_SQL:
        conn.execute(sa.text(stmt))


def preflight_conflicts(conn) -> list[str]:
    """적용 전에 충돌을 센다. 비어 있지 않으면 **중단**해야 한다."""
    problems: list[str] = []
    for org_id, team, rows in conn.execute(sa.text(PREFLIGHT_ACTIVE_SQL)).all():
        problems.append(
            f"활성 회차 충돌 — 조직 {org_id} 팀 {team or '(미정)'} 에 활성 회차가 둘 이상: {rows}"
        )
    for org_id, team, name, rows in conn.execute(sa.text(PREFLIGHT_NAME_SQL)).all():
        problems.append(
            f"이름 충돌 — 조직 {org_id} 팀 {team or '(미정)'} 에 «{name}» 이 둘 이상: {rows}"
        )
    for sprint_id, name, org_id, team_org in conn.execute(sa.text(PREFLIGHT_ORG_SQL)).all():
        problems.append(
            f"조직 불일치 — 회차 {sprint_id} «{name}» 의 조직 {org_id} 과 팀의 조직 {team_org} 이 다르다"
        )
    return problems


def apply_team_assignments(conn) -> dict:
    """계획을 적용하고 결과를 센다. `plan_team_assignments` 뒤에만 부른다."""
    by_rule = dict(
        conn.execute(
            sa.text("SELECT rule, count(*) FROM sprint_team_plan GROUP BY rule")
        ).all()
    )
    conn.execute(sa.text(APPLY_SQL))
    conn.execute(sa.text(ORG_SYNC_SQL))
    unassigned = conn.execute(
        sa.text("SELECT count(*) FROM sprints WHERE department_id IS NULL")
    ).scalar_one()
    mixed = conn.execute(sa.text(MIXED_TEAM_SQL)).all()
    return {"by_rule": by_rule, "unassigned": int(unassigned), "mixed": [r[0] for r in mixed]}


def upgrade() -> None:
    op.add_column("sprints", sa.Column("department_id", sa.String(length=36), nullable=True))
    # 이름을 명시하는 이유: 이름 없는 제약은 autogenerate 가 모델과 대조할 때마다
    # 삭제 diff 를 낸다 (0026 `documents_category_id_fkey` 와 같은 관례).
    op.create_foreign_key(
        "sprints_department_id_fkey", "sprints", "org_units",
        ["department_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_sprints_department_id"), "sprints", ["department_id"])

    conn = op.get_bind()
    plan_team_assignments(conn)
    problems = preflight_conflicts(conn)
    if problems:
        # 자동으로 닫거나 합치거나 이름을 바꾸지 않는다. 사람이 정한 뒤 다시 돌린다.
        raise RuntimeError(
            "0029 중단 — 팀 소유로 옮기면 충돌이 생기는 회차가 있습니다. 아래 행을 정리한 뒤 "
            "다시 실행하세요.\n  " + "\n  ".join(problems)
        )
    result = apply_team_assignments(conn)
    # 무엇을 어떻게 채웠고 무엇이 남았는지 — 조용히 지나가면 아무도 미정 회차를 안 본다.
    # (0005 `_report_losses` 와 같은 관례: 잃거나 못 정한 것은 NOTICE 로 말한다.)
    rules = " ".join(f"{k}={v}" for k, v in sorted(result["by_rule"].items())) or "none"
    summary = (
        f"0029 sprints: assigned[{rules}] unassigned={result['unassigned']} "
        f"mixed_team={len(result['mixed'])}"
    ).replace("'", "")
    conn.execute(sa.text(f"DO $$ BEGIN RAISE NOTICE '{summary}'; END $$"))

    # 유일 축을 프로젝트에서 팀으로. `project_id` 칼럼·FK·인덱스는 남긴다(0030 이 걷는다).
    op.execute("DROP INDEX IF EXISTS uq_sprints_active")
    op.drop_index("uq_sprints_name", table_name="sprints")
    op.execute(
        "CREATE UNIQUE INDEX uq_sprints_name ON sprints (org_id, coalesce(department_id, ''), name)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sprints_active ON sprints (org_id, coalesce(department_id, '')) "
        "WHERE state = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sprints_active")
    op.execute("DROP INDEX IF EXISTS uq_sprints_name")
    op.create_index("uq_sprints_name", "sprints", ["org_id", "project_id", "name"], unique=True)
    op.execute(
        "CREATE UNIQUE INDEX uq_sprints_active ON sprints (org_id, coalesce(project_id, '')) "
        "WHERE state = 'active'"
    )
    op.drop_index(op.f("ix_sprints_department_id"), table_name="sprints")
    op.drop_constraint("sprints_department_id_fkey", "sprints", type_="foreignkey")
    op.drop_column("sprints", "department_id")
