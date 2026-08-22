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


def role_rank(role: str) -> int:
    """계층상 높이(0 = 계층 밖이거나 알 수 없는 값).

    임퍼소네이션(0033)처럼 "나보다 높은 역할은 흉내 낼 수 없다"를 판정하는 곳이 쓴다.
    순위를 아는 곳을 여기 하나로 두어 호출부가 역할 이름을 다시 나열하지 않게 한다 —
    `tests/security/test_authz_single_source.py` 가 그 사본을 막는다.
    auditor 는 읽기 전용 가지라 계층으로 '세기'를 말할 수 없으므로 0 이고, 그래서
    admin 은 auditor 를 흉내 낼 수 있다(0 < 3). 그건 의도한 결과다: 감사자는 관리자보다
    **좁은** 화면을 본다.
    """
    return _ROLE_LEVELS.get(role, 0)


# ── 관리 범위 어휘(0024) ──────────────────────────────────────────────────────
# 역할(role)이 '무엇을 할 수 있는가'라면 범위(admin_scope)는 '누구에게 할 수 있는가'다.
# 둘은 직교한다: 부서 관리자도 role='admin' 이지만 admin_scope='dept' 다.
# 값 해석과 필터 조립은 app/core/scope.py 한 곳에만 있다.
ADMIN_SCOPE_GLOBAL = "global"
ADMIN_SCOPE_ORG = "org"
ADMIN_SCOPE_DEPT = "dept"

ALL_ADMIN_SCOPES = frozenset({ADMIN_SCOPE_GLOBAL, ADMIN_SCOPE_ORG, ADMIN_SCOPE_DEPT})


# ── 소속 종류(0060) ───────────────────────────────────────────────────────────
# "이 사람이 조직 어디에 붙어 있는가". `admin_scope`(관리 범위)와 다른 축이다 — 이쪽은
# 역할과 무관하게 **모든 계정**에 있고, 일반 사용자의 조회 범위를 정한다.
#
# 세 값을 구분하는 이유는 `department_id IS NULL` 하나로는 서로 다른 두 사실을 구별할 수
# 없기 때문이다: "본부 직속이라 팀이 없다"와 "아직 부서를 안 정했다". 예전에는 이 둘을
# 똑같이 취급하고 전역(GLOBAL)으로 폴백해서, 부서를 안 정한 계정이 전 포털을 봤다.
# 코드가 추측하지 않고 사람이 지정한다 — 지정 전까지는 닫는다(app/core/scope.py).
# ⚠️ 이 값은 **`department_id` 가 비어 있을 때만** 판정에 쓰인다. 부서가 배정돼 있으면
# 그 사람은 그 부서 사람이고 물을 것이 없다 — 두 컬럼이 서로 다른 말을 하는 상태를 판정에서
# 없애기 위해서다(`app/core/scope.py::_membership_scope`).
MEMBERSHIP_DEPARTMENT = "department"      # 특정 부서 소속 → 그 부서 branch 를 본다
MEMBERSHIP_ORGANIZATION = "organization"  # 조직 직속 → 그 조직 전체를 본다
MEMBERSHIP_UNASSIGNED = "unassigned"      # 아직 미지정 → 조직 데이터를 못 본다

ALL_MEMBERSHIP_KINDS = frozenset(
    {MEMBERSHIP_DEPARTMENT, MEMBERSHIP_ORGANIZATION, MEMBERSHIP_UNASSIGNED}
)


class User(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 부서·직책은 명부(app/org)를 가리킨다. 이름을 여기 문자열로 들고 있으면 부서명이
    # 바뀔 때마다 전 직원의 행을 고쳐야 하고, 'ClovirONE팀'과 'ClovirOne팀'이 서로 다른
    # 부서가 된다. 이름은 명부에만 있고 여기엔 참조만 둔다.
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id", ondelete="SET NULL")
    )
    title_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_titles.id", ondelete="SET NULL")
    )
    # 소속 종류(0060). 기본값이 'unassigned' 인 이유는 위 상수 주석 참조 — 새 계정도
    # 사람이 부서나 조직 직속을 **명시**해야 조직 데이터가 보인다. `admin_scope` 와 달리
    # 기본값을 넓게 두지 않는다: 저쪽은 관리 화면이 비는 문제였고 이쪽은 유출이다.
    membership_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MEMBERSHIP_UNASSIGNED,
        server_default=MEMBERSHIP_UNASSIGNED,
        index=True,
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
        String(36), ForeignKey("org_units.id", ondelete="SET NULL")
    )
    # users → departments 경로가 두 개(department_id, scope_dept_id)라 어느 쪽으로 조인할지
    # 명시해야 한다. 안 하면 SQLAlchemy 가 AmbiguousForeignKeysError 로 매핑 자체를 거부한다.
    department_ref: Mapped[Department | None] = relationship(
        "OrgUnit", lazy="joined", foreign_keys=[department_id]
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
