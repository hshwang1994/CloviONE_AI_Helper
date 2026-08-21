"""부서·직책 명부 + users.department/title 문자열 → FK 이관

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-16

자유 입력 문자열은 'ClovirONE팀'과 'ClovirOne팀'을 서로 다른 부서로 만들고, 부서명이
바뀌면 전 직원의 행을 하나씩 고치게 한다. 이름을 명부 한 곳에만 두고 사용자는 FK로
가리키게 바꾼다.

이관 순서(문자열 컬럼이 살아 있는 동안 값을 옮겨야 한다):
  1. departments / job_titles 생성
  2. users에 department_id / title_id 추가
  3. 기존 문자열에서 DISTINCT 이름을 뽑아 명부 행을 만들고 연결
  4. 문자열 컬럼 제거

다운그레이드 손실(정직하게 적어 둔다): 0014의 스키마에는 명부 테이블이 없어 이름을
'사용자 행'에만 되돌릴 수 있다. 따라서 **아무도 쓰지 않는 부서·직책**과 **active=false
표시**는 다운그레이드로 사라진다(담을 곳이 없다). 사용자에게 배정된 이름은 전부
보존되며 upgrade→downgrade→upgrade 왕복에서 그대로 돌아온다 —
tests/regression/test_migration_0015_org_roundtrip.py가 못 박는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _create_lookup(table: str) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(f"ix_{table}_name", table, ["name"], unique=True)


def _migrate_column_to_rows(conn, *, source_column: str, table: str, fk_column: str) -> None:
    """기존 문자열 값에서 명부 행을 만들고 users를 연결한다.

    공백만 있는 값과 NULL은 부서가 아니다 — 행으로 만들면 명부에 빈 항목이 생긴다.
    TRIM 후 같아지는 이름은 하나로 모은다.
    """
    names = [
        row[0]
        for row in conn.execute(
            sa.text(
                f"SELECT DISTINCT TRIM({source_column}) FROM users"
                f" WHERE {source_column} IS NOT NULL AND TRIM({source_column}) != ''"
            )
        )
    ]
    # created_at은 Python에서 만든다. SQLite의 STRFTIME('…%H:%M:%S.%f')로 만들면 안 된다 —
    # SQLite의 %f는 '초.밀리초'(예: "03.754")라서 %S와 같이 쓰면 초가 두 번 들어간
    # '06:44:03.03.754'가 나오고, SQLAlchemy가 그 행을 읽는 순간 ValueError로 터진다.
    # (CLAUDE.md §8의 "마이크로초 6자리"는 Python의 strftime 이야기다 — 둘은 다른 문법이다.)
    # 실제로 이 실수가 있었고, 프로덕션 데이터로 CLI를 돌려 보고서야 드러났다.
    now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")
    for name in names:
        new_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                f"INSERT INTO {table} (id, name, active, created_at)"
                " VALUES (:id, :name, 1, :now)"
            ),
            {"id": new_id, "name": name, "now": now},
        )
        conn.execute(
            sa.text(
                f"UPDATE users SET {fk_column} = :id WHERE TRIM({source_column}) = :name"
            ),
            {"id": new_id, "name": name},
        )


def upgrade() -> None:
    _create_lookup("departments")
    _create_lookup("job_titles")

    # SQLite는 기존 테이블에 FK 제약을 붙이려면 테이블을 다시 만들어야 한다(batch).
    # env.py가 foreign_keys 프래그마를 켜지 않으므로 sessions→users 참조는 재생성
    # 중에도 이름으로 유지된다(테스트가 확인한다).
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("department_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("title_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_users_department_id", "departments", ["department_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_users_title_id", "job_titles", ["title_id"], ["id"], ondelete="SET NULL",
        )

    conn = op.get_bind()
    _migrate_column_to_rows(
        conn, source_column="department", table="departments", fk_column="department_id"
    )
    _migrate_column_to_rows(
        conn, source_column="title", table="job_titles", fk_column="title_id"
    )

    # 값을 다 옮긴 뒤에야 자유 입력 컬럼을 없앤다. 남겨 두면 언젠가 그리로 다시 쓰게
    # 되고 '두 개의 진실'이 생긴다.
    with op.batch_alter_table("users") as batch:
        batch.drop_column("department")
        batch.drop_column("title")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("department", sa.String(120), nullable=True))
        batch.add_column(sa.Column("title", sa.String(120), nullable=True))

    conn = op.get_bind()
    # 이름을 사용자 행으로 되돌린다(명부 테이블이 없어질 것이므로 여기서 옮겨야 한다).
    conn.execute(
        sa.text(
            "UPDATE users SET department ="
            " (SELECT name FROM departments WHERE departments.id = users.department_id)"
            " WHERE department_id IS NOT NULL"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE users SET title ="
            " (SELECT name FROM job_titles WHERE job_titles.id = users.title_id)"
            " WHERE title_id IS NOT NULL"
        )
    )

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_department_id", type_="foreignkey")
        batch.drop_constraint("fk_users_title_id", type_="foreignkey")
        batch.drop_column("department_id")
        batch.drop_column("title_id")

    op.drop_index("ix_job_titles_name", table_name="job_titles")
    op.drop_table("job_titles")
    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_table("departments")
