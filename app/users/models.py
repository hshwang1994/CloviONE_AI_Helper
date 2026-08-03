"""User account model (spec §21.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.org.models import Department, JobTitle

ROLE_USER = "user"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
ROLE_AUDITOR = "auditor"
ROLE_SYSTEM_ADMIN = "system_admin"

ALL_ROLES = frozenset(
    {ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_AUDITOR, ROLE_SYSTEM_ADMIN}
)

# Hierarchical roles (spec §10). auditor sits outside the hierarchy: it is a
# read-only branch granted only where explicitly listed.
_ROLE_LEVELS = {ROLE_USER: 1, ROLE_OPERATOR: 2, ROLE_ADMIN: 3, ROLE_SYSTEM_ADMIN: 4}


def roles_at_least(minimum: str) -> frozenset[str]:
    """Return the set of hierarchical roles at or above ``minimum``."""
    level = _ROLE_LEVELS[minimum]
    return frozenset(role for role, l in _ROLE_LEVELS.items() if l >= level)


# ── 관리 범위 어휘(0024) ──────────────────────────────────────────────────────
# 역할(role)이 '무엇을 할 수 있는가'라면 범위(admin_scope)는 '누구에게 할 수 있는가'다.
# 둘은 직교한다: 부서 관리자도 role='admin' 이지만 admin_scope='dept' 다.
# 값 해석과 필터 조립은 app/core/scope.py 한 곳에만 있다.
ADMIN_SCOPE_GLOBAL = "global"
ADMIN_SCOPE_ORG = "org"
ADMIN_SCOPE_DEPT = "dept"

ALL_ADMIN_SCOPES = frozenset({ADMIN_SCOPE_GLOBAL, ADMIN_SCOPE_ORG, ADMIN_SCOPE_DEPT})


class User(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 부서·직책은 명부(app/org)를 가리킨다. 이름을 여기 문자열로 들고 있으면 부서명이
    # 바뀔 때마다 전 직원의 행을 고쳐야 하고, 'ClovirONE팀'과 'ClovirOne팀'이 서로 다른
    # 부서가 된다. 이름은 명부에만 있고 여기엔 참조만 둔다.
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL")
    )
    title_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_titles.id", ondelete="SET NULL")
    )
    # ── 관리 범위(0024) ───────────────────────────────────────────────────────
    # admin_scope 는 **관리자 역할일 때만** 의미가 있다: 이 계정이 관리 화면에서 볼 수 있는
    # 범위가 전체(global)인지, 한 조직(org)인지, 한 부서 서브트리(dept)인지.
    # 기본값이 'global' 인 이유는 0024 마이그레이션 docstring 에 적어 두었다 — 좁은 값을
    # 기본으로 깔면 마이그레이션 하나로 운영 중인 관리자 화면이 조용히 빈 목록이 된다.
    admin_scope: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ADMIN_SCOPE_GLOBAL,
        server_default=ADMIN_SCOPE_GLOBAL,
    )
    scope_org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id")
    )
    scope_dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL")
    )
    # users → departments 경로가 두 개(department_id, scope_dept_id)라 어느 쪽으로 조인할지
    # 명시해야 한다. 안 하면 SQLAlchemy 가 AmbiguousForeignKeysError 로 매핑 자체를 거부한다.
    department_ref: Mapped[Department | None] = relationship(
        "Department", lazy="joined", foreign_keys=[department_id]
    )
    title_ref: Mapped[JobTitle | None] = relationship("JobTitle", lazy="joined")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=ROLE_USER)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 보관(archive). NULL이면 살아 있는 계정. 계정을 지우는 대신 이 값을 채워 목록·검색·
    # 로그인에서 빼되 행은 남긴다 — 감사 로그의 행위자가 빈칸이 되면 안 되기 때문이다.
    # 되돌릴 수 있다(unarchive → 다시 NULL).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    @property
    def archived(self) -> bool:
        return self.archived_at is not None

    # 이름은 명부에서 읽는다. 응답·감사 스냅숏·프로필은 예전과 똑같이 user.department로
    # 이름을 얻는다 — 부르는 쪽을 전부 고치지 않아도 되고, 명부에서 이름을 바꾸면
    # 여기서 읽는 모든 곳에 그 즉시 반영된다(그것이 이 변경의 목적이다).
    @property
    def department(self) -> str | None:
        return self.department_ref.name if self.department_ref else None

    @property
    def title(self) -> str | None:
        return self.title_ref.name if self.title_ref else None
