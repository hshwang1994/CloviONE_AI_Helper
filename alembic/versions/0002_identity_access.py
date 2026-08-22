"""Identity & Access — Role · Permission · 직접 부여, 그리고 `departments` → `org_units` (S5).

Revision ID: 0002_identity_access
Revises: 0001_pg_baseline
Create Date: 2026-08-22

앱 코드를 import 하지 않는다. 마이그레이션은 **그 시점 스키마의 얼어붙은 스냅숏**이라,
`app/authz/permissions.py` 를 참조하면 나중에 그 표를 고치는 날 이 파일의 뜻이 소리 없이
함께 바뀐다. 그래서 값을 여기 그대로 적고, **시험이 둘을 맞물려 둔다**:
`tests/unit/test_identity_access_seed.py` 가 아래 세 리터럴이 코드의 표와 같은지 확인한다.

## 표 이름을 바꾼다 — `departments` → `org_units`

0024 이후 이 표에는 본부·팀·파트가 함께 들어 있었고 그 셋을 「부서」 한 단어로 부르면
권한 상속을 설명할 수 없다(`app/org/models.py::OrgUnit`). **컬럼 이름은 그대로 둔다** —
`users.department_id` · `projects.dept_id` 는 API 응답과 화면 어휘에 그대로 나가는 이름이라
바꾸면 사용자에게 보이는 말이 바뀐다.

PostgreSQL 의 `ALTER TABLE … RENAME TO` 는 인덱스·제약을 **옛 이름 그대로** 데려간다.
그러면 다음 사람이 `ix_departments_name` 을 보고 없는 표를 찾는다. 그래서 이름도 함께 옮긴다.

## 기본 제공 역할은 이 파일이 심는다

다섯 역할과 그 권한 조합은 **코드가 정한다**(`app/core/authz.py` 의 그룹 상수 →
`app/authz/permissions.py` 의 표). 여기서는 그 결과를 데이터로 굳힐 뿐이고, `builtin = true`
인 행은 화면에서 고칠 수 없다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = '0002_identity_access'
down_revision = '0001_pg_baseline'
branch_labels = None
depends_on = None


_DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
_ORG_UNIT_DEPARTMENT = "department"


# ── 시드 값 (코드의 표를 그대로 옮긴 것) ─────────────────────────────────────
_PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("PROJECT_READ", "프로젝트 조회", "프로젝트", "역할이 아니라 범위가 정한다. 어느 프로젝트가 보이는지는 app/authz/visibility.py 가 답한다."),
    ("PROJECT_WRITE", "프로젝트 내용 편집", "프로젝트", "현행 app/projects/router.py 의 require_write 와 같은 집합이다."),
    ("PROJECT_ADMIN", "프로젝트 소속 변경과 삭제", "프로젝트", "소속을 바꾸는 것은 편집이 아니라 조직 결정이다(app/core/ownership.py::can_manage)."),
    ("TICKET_READ", "티켓 조회", "티켓", ""),
    ("TICKET_CREATE", "티켓 생성", "티켓", ""),
    ("TICKET_UPDATE", "티켓 편집", "티켓", "담당자와 작성자 판정, 그리고 프로젝트 범위가 실제 문을 지킨다. 역할로는 막지 않는다."),
    ("TICKET_DELETE", "티켓 삭제와 휴지통 이동", "티켓", "본인 것이 아니어도 지울 수 있는 권한이라 중재 권한과 같은 선이다."),
    ("TICKET_TRANSITION", "티켓 상태 전이", "티켓", ""),
    ("SPACE_READ", "지식 공간 조회", "지식", "S7 에서 생긴다."),
    ("SPACE_WRITE", "지식 공간 편집", "지식", "S7 에서 생긴다."),
    ("SPACE_ADMIN", "지식 공간 관리", "지식", "S7 에서 생긴다. confidential 문서를 여는 *_ADMIN 이 이것이 된다."),
    ("DOCUMENT_READ", "문서 조회", "문서", ""),
    ("DOCUMENT_CREATE", "문서 생성", "문서", ""),
    ("DOCUMENT_UPDATE", "문서 편집", "문서", ""),
    ("DOCUMENT_DELETE", "문서 삭제와 동기화", "문서", "현행 app/team_docs 의 중재 경로와 같은 집합이다."),
    ("DOCUMENT_PUBLISH", "문서 발행", "문서", "S7 이 Version/발행을 만들 때 확정한다. 지금은 중재 권한과 같은 선에 둔다."),
    ("DOCUMENT_ADMIN", "열람 제한 문서 관리", "문서", "confidential 을 켜고 끄고, 켜진 문서를 볼 수 있는 권한(D-193 의 *_ADMIN)."),
    ("FILE_UPLOAD", "파일 업로드", "파일", ""),
    ("FILE_DOWNLOAD", "파일 다운로드", "파일", ""),
    ("FILE_DELETE", "남의 첨부 삭제", "파일", "자기 첨부를 지우는 것은 소유권 판정이라 권한이 필요 없다."),
    ("USER_MANAGE", "사용자 계정 관리", "사용자", "대상은 언제나 자기 관리 범위 안으로 제한된다(app/core/scope.py)."),
    ("ORG_MANAGE", "부서와 직책, 조직도 편집", "사용자", ""),
    ("ROLE_MANAGE", "역할과 권한 편집", "사용자", "기본 제공 역할은 편집할 수 없다. 그것이 다섯 역할의 뜻을 고정한다."),
    ("BACKUP_READ", "백업 목록과 이력 조회", "시스템", "현행 app/backups/router.py 의 목록 게이트와 같은 집합이다."),
    ("BACKUP_EXECUTE", "백업 생성과 검증", "시스템", ""),
    ("BACKUP_CONFIGURE", "백업 정책과 일정 설정", "시스템", ""),
    ("STORAGE_CONFIGURE", "파일 저장소 설정", "시스템", "S8 에서 생긴다."),
    ("AI_USE", "AI 질의와 작업공간 사용", "AI", ""),
    ("AI_CONFIGURE", "모델과 프롬프트, 쿼터 설정", "AI", "현행 app/llm_console 과 같은 집합이다. S9 이 Gateway 로 넓힌다."),
    ("AUDIT_READ", "감사 로그와 민감 집계 조회", "감사", "사람에 대한 평가가 담기므로 운영자를 뺀다."),
    ("SYSTEM_CONFIGURE", "시스템 설정(TLS, 호스트 이름, 서비스 제어)", "시스템", "바뀌는 대상이 서버 한 대 전체라 admin_scope 라는 개념 자체가 없다."),
    ("IMPERSONATE", "대리 보기 시작", "사용자", "운영자는 남의 화면을 볼 수 없다. 감사자는 기록 조회만 할 수 있다."),
)

_BUILTIN_ROLES: tuple[tuple[str, str, str], ...] = (
    ("user", "일반 사용자", "포털을 쓰는 일반 사용자."),
    ("operator", "운영자", "운영 동작을 하되 설정은 바꾸지 않는다."),
    ("auditor", "감사자", "읽기 전용 가지. 감사 로그와 민감 집계를 본다."),
    ("admin", "관리자", "조직 설정과 사용자를 관리한다. 관리 범위로 좁혀질 수 있다."),
    ("system_admin", "시스템 관리자", "설치 한 벌 전체. 백업·TLS·서비스 제어까지 본다."),
)

_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "user": (
        "AI_USE", "DOCUMENT_CREATE", "DOCUMENT_READ", "DOCUMENT_UPDATE", "FILE_DOWNLOAD",
        "FILE_UPLOAD", "PROJECT_READ", "SPACE_READ", "SPACE_WRITE", "TICKET_CREATE",
        "TICKET_READ", "TICKET_TRANSITION", "TICKET_UPDATE",
    ),
    "operator": (
        "AI_USE", "BACKUP_READ", "DOCUMENT_ADMIN", "DOCUMENT_CREATE", "DOCUMENT_DELETE",
        "DOCUMENT_PUBLISH", "DOCUMENT_READ", "DOCUMENT_UPDATE", "FILE_DELETE", "FILE_DOWNLOAD",
        "FILE_UPLOAD", "PROJECT_READ", "PROJECT_WRITE", "SPACE_READ", "SPACE_WRITE",
        "TICKET_CREATE", "TICKET_DELETE", "TICKET_READ", "TICKET_TRANSITION", "TICKET_UPDATE",
    ),
    "auditor": (
        "AI_USE", "AUDIT_READ", "BACKUP_READ", "DOCUMENT_CREATE", "DOCUMENT_READ",
        "DOCUMENT_UPDATE", "FILE_DOWNLOAD", "FILE_UPLOAD", "PROJECT_READ", "SPACE_READ",
        "SPACE_WRITE", "TICKET_CREATE", "TICKET_READ", "TICKET_TRANSITION", "TICKET_UPDATE",
    ),
    "admin": (
        "AI_USE", "AUDIT_READ", "BACKUP_READ", "DOCUMENT_ADMIN", "DOCUMENT_CREATE",
        "DOCUMENT_DELETE", "DOCUMENT_PUBLISH", "DOCUMENT_READ", "DOCUMENT_UPDATE",
        "FILE_DELETE", "FILE_DOWNLOAD", "FILE_UPLOAD", "IMPERSONATE", "ORG_MANAGE",
        "PROJECT_ADMIN", "PROJECT_READ", "PROJECT_WRITE", "ROLE_MANAGE", "SPACE_ADMIN",
        "SPACE_READ", "SPACE_WRITE", "TICKET_CREATE", "TICKET_DELETE", "TICKET_READ",
        "TICKET_TRANSITION", "TICKET_UPDATE", "USER_MANAGE",
    ),
    "system_admin": (
        "AI_CONFIGURE", "AI_USE", "AUDIT_READ", "BACKUP_CONFIGURE", "BACKUP_EXECUTE",
        "BACKUP_READ", "DOCUMENT_ADMIN", "DOCUMENT_CREATE", "DOCUMENT_DELETE",
        "DOCUMENT_PUBLISH", "DOCUMENT_READ", "DOCUMENT_UPDATE", "FILE_DELETE", "FILE_DOWNLOAD",
        "FILE_UPLOAD", "IMPERSONATE", "ORG_MANAGE", "PROJECT_ADMIN", "PROJECT_READ",
        "PROJECT_WRITE", "ROLE_MANAGE", "SPACE_ADMIN", "SPACE_READ", "SPACE_WRITE",
        "STORAGE_CONFIGURE", "SYSTEM_CONFIGURE", "TICKET_CREATE", "TICKET_DELETE",
        "TICKET_READ", "TICKET_TRANSITION", "TICKET_UPDATE", "USER_MANAGE",
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    # ── 1. departments → org_units ──────────────────────────────────────────
    op.execute("ALTER TABLE departments RENAME TO org_units")
    op.execute("ALTER INDEX ix_departments_name RENAME TO ix_org_units_name")
    op.execute("ALTER INDEX ix_departments_org_id RENAME TO ix_org_units_org_id")
    op.execute("ALTER INDEX ix_departments_parent_id RENAME TO ix_org_units_parent_id")
    op.execute("ALTER INDEX uq_departments_org_name RENAME TO uq_org_units_org_name")
    op.execute("ALTER INDEX departments_pkey RENAME TO org_units_pkey")
    op.execute(
        "ALTER TABLE org_units RENAME CONSTRAINT departments_org_id_fkey "
        "TO org_units_org_id_fkey"
    )
    op.execute(
        "ALTER TABLE org_units RENAME CONSTRAINT departments_parent_id_fkey "
        "TO org_units_parent_id_fkey"
    )
    op.add_column(
        "org_units",
        sa.Column(
            "kind", sa.String(length=16), nullable=False,
            server_default=_ORG_UNIT_DEPARTMENT,
        ),
    )

    # ── 2. 권한 모델 ────────────────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("area", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "roles",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roles_builtin"), "roles", ["builtin"], unique=False)
    op.create_index(op.f("ix_roles_key"), "roles", ["key"], unique=False)
    op.create_index(op.f("ix_roles_org_id"), "roles", ["org_id"], unique=False)
    op.create_index("uq_roles_org_key", "roles", ["org_id", "key"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("permission_key", sa.String(length=48), nullable=False),
        sa.ForeignKeyConstraint(["permission_key"], ["permissions.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_key"), "role_permissions",
        ["permission_key"], unique=False,
    )
    op.create_index(
        op.f("ix_role_permissions_role_id"), "role_permissions", ["role_id"], unique=False
    )
    op.create_index(
        "uq_role_permissions_pair", "role_permissions",
        ["role_id", "permission_key"], unique=True,
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"], unique=False)
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"], unique=False)
    op.create_index("uq_user_roles_pair", "user_roles", ["user_id", "role_id"], unique=True)

    op.create_table(
        "resource_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("grantee_kind", sa.String(length=16), nullable=False),
        sa.Column("grantee_id", sa.String(length=36), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_resource_grants_grantee_id"), "resource_grants", ["grantee_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_grants_resource_id"), "resource_grants", ["resource_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_grants_resource_type"), "resource_grants",
        ["resource_type"], unique=False,
    )
    op.create_index(
        "ix_resource_grants_resource", "resource_grants",
        ["resource_type", "resource_id"], unique=False,
    )
    op.create_index(
        "uq_resource_grants_target", "resource_grants",
        ["resource_type", "resource_id", "grantee_kind", "grantee_id"], unique=True,
    )

    # ── 3. 시드 ─────────────────────────────────────────────────────────────
    _seed()


def _seed() -> None:
    bind = op.get_bind()
    now = _now()

    bind.execute(
        sa.text(
            "INSERT INTO permissions (key, label, area, description) "
            "VALUES (:key, :label, :area, :description)"
        ),
        [
            {"key": key, "label": label, "area": area, "description": note or None}
            for key, label, area, note in _PERMISSIONS
        ],
    )

    role_ids: dict[str, str] = {}
    role_rows = []
    for key, name, description in _BUILTIN_ROLES:
        role_ids[key] = str(uuid.uuid4())
        role_rows.append({
            "id": role_ids[key], "key": key, "name": name, "description": description,
            "builtin": True, "org_id": _DEFAULT_ORG_ID, "created_at": now, "updated_at": now,
        })
    bind.execute(
        sa.text(
            "INSERT INTO roles (id, key, name, description, builtin, org_id, created_at, updated_at) "
            "VALUES (:id, :key, :name, :description, :builtin, :org_id, :created_at, :updated_at)"
        ),
        role_rows,
    )

    link_rows = [
        {"id": str(uuid.uuid4()), "role_id": role_ids[role_key], "permission_key": perm_key}
        for role_key, perm_keys in _ROLE_PERMISSIONS.items()
        for perm_key in perm_keys
    ]
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (id, role_id, permission_key) "
            "VALUES (:id, :role_id, :permission_key)"
        ),
        link_rows,
    )


def downgrade() -> None:
    op.drop_index("uq_resource_grants_target", table_name="resource_grants")
    op.drop_index("ix_resource_grants_resource", table_name="resource_grants")
    op.drop_index(op.f("ix_resource_grants_resource_type"), table_name="resource_grants")
    op.drop_index(op.f("ix_resource_grants_resource_id"), table_name="resource_grants")
    op.drop_index(op.f("ix_resource_grants_grantee_id"), table_name="resource_grants")
    op.drop_table("resource_grants")

    op.drop_index("uq_user_roles_pair", table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_user_id"), table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_role_id"), table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("uq_role_permissions_pair", table_name="role_permissions")
    op.drop_index(op.f("ix_role_permissions_role_id"), table_name="role_permissions")
    op.drop_index(op.f("ix_role_permissions_permission_key"), table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("uq_roles_org_key", table_name="roles")
    op.drop_index(op.f("ix_roles_org_id"), table_name="roles")
    op.drop_index(op.f("ix_roles_key"), table_name="roles")
    op.drop_index(op.f("ix_roles_builtin"), table_name="roles")
    op.drop_table("roles")
    op.drop_table("permissions")

    op.drop_column("org_units", "kind")
    op.execute(
        "ALTER TABLE org_units RENAME CONSTRAINT org_units_parent_id_fkey "
        "TO departments_parent_id_fkey"
    )
    op.execute(
        "ALTER TABLE org_units RENAME CONSTRAINT org_units_org_id_fkey "
        "TO departments_org_id_fkey"
    )
    op.execute("ALTER INDEX org_units_pkey RENAME TO departments_pkey")
    op.execute("ALTER INDEX uq_org_units_org_name RENAME TO uq_departments_org_name")
    op.execute("ALTER INDEX ix_org_units_parent_id RENAME TO ix_departments_parent_id")
    op.execute("ALTER INDEX ix_org_units_org_id RENAME TO ix_departments_org_id")
    op.execute("ALTER INDEX ix_org_units_name RENAME TO ix_departments_name")
    op.execute("ALTER TABLE org_units RENAME TO departments")
