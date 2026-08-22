"""Role · Permission · 직접 부여 — 권한을 **코드에서 데이터로** 옮긴 표들 (S5 · D-193).

## 왜 표가 필요한가

지금까지 「누가 무엇을 할 수 있는가」는 파이썬 상수였다. 그래서 역할을 하나 더 만들려면
배포가 필요했고, 「이 사람만 이 문서를 볼 수 있게」는 표현할 방법이 아예 없었다.

## 다섯 역할은 여전히 코드가 정한다

`roles.builtin = true` 인 다섯 행은 **읽기 전용**이다. 그 권한 집합은
`app/authz/permissions.py` 가 정하고 마이그레이션이 심는다. 화면에서 고칠 수 있게 하면
「관리자」의 뜻이 설치처마다 달라지고, 그 순간 이 저장소의 보안 시험은 아무것도 증명하지
못한다. 조합을 바꾸고 싶으면 **새 역할을 만든다**(`builtin = false`).

## 부여는 더하기만 한다 (D-193)

`user_roles` 도 `resource_grants` 도 **넓히기만** 한다. 「이 사람에게서 이것을 뺀다」는
행을 만들 수 없다. 유일한 축소 원시연산은 `confidential` 플래그 하나이고 그 뜻은
`app/authz/visibility.py` 가 한 문장으로 고정한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    new_uuid,
    utcnow,
)

# ── 직접 부여의 대상 ─────────────────────────────────────────────────────────
# 사람 하나, 역할 하나, 조직 단위 하나. 셋 다 **더하는** 대상이다.
GRANTEE_USER = "user"
GRANTEE_ROLE = "role"
GRANTEE_ORG_UNIT = "org_unit"

ALL_GRANTEE_KINDS = frozenset({GRANTEE_USER, GRANTEE_ROLE, GRANTEE_ORG_UNIT})


class Permission(Base):
    """권한 목록. 행은 `app/authz/permissions.py` 의 표에서 나온다.

    키를 그대로 기본키로 쓴다 — UUID 를 두면 `role_permissions` 를 사람이 읽을 수 없고,
    권한 키는 코드 상수라 애초에 바뀌지 않는다(바뀌면 그건 새 권한이다).
    """

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    area: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Role(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """역할 한 개.

    `key` 는 사람이 쓰는 안정적인 이름이다. 기본 제공 다섯의 `key` 는
    `users.role` 컬럼 값(`user`·`operator`·`auditor`·`admin`·`system_admin`)과 **같다** —
    그래야 「이 계정의 주 역할」이 두 곳에서 다른 이름으로 불리지 않는다.
    """

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # true 면 화면·API 에서 고칠 수 없다. 코드가 뜻을 정하는 역할이다.
    builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    __table_args__ = (
        # 이름 유일성은 전역이 아니라 조직 안에서 성립한다 — 부서(`uq_departments_org_name`,
        # 지금은 `uq_org_units_org_name`)와 같은 이유다.
        Index("uq_roles_org_key", "org_id", "key", unique=True),
    )


class RolePermission(Base):
    """역할 하나가 가진 권한 하나."""

    __tablename__ = "role_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_key: Mapped[str] = mapped_column(
        String(48), ForeignKey("permissions.key", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        Index("uq_role_permissions_pair", "role_id", "permission_key", unique=True),
    )


class UserRole(Base):
    """사람 하나에게 **추가로** 준 역할.

    `users.role`(주 역할)을 대체하지 않고 **더한다.** 대체하게 만들면 이관 중에 한 사람의
    권한이 두 곳에서 서로 다른 말을 하는 창이 생기고, 그 창에서 무엇이 옳은지 판정할
    근거가 없다. 유효 권한은 언제나 합집합이다(`app/authz/service.py`).
    """

    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    granted_by: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        Index("uq_user_roles_pair", "user_id", "role_id", unique=True),
    )


class ResourceGrant(Base):
    """자원 하나에 대한 **명시 부여** — D-193 의 「직접 부여」 항.

    유효 권한 = `Role ∪ Organization ∪ Project Member ∪ 직접 부여` 의 마지막 항이 이 표다.
    없으면 `confidential` 의 뜻(「소유자 + **명시 부여자** + `*_ADMIN` 보유자만」)을 구현할 수
    없다 — 소유자와 관리자만 남으면 그건 축소 플래그가 아니라 잠금이다.

    `resource_id` 가 `String(64)` 인 이유: 문서는 Notion page id(32자 hex 또는 UUID),
    프로젝트·티켓은 UUID(36자)다. 자원마다 키 모양이 달라 넉넉히 잡는다.
    """

    __tablename__ = "resource_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    grantee_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    granted_by: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        Index(
            "uq_resource_grants_target",
            "resource_type", "resource_id", "grantee_kind", "grantee_id",
            unique=True,
        ),
        # 「이 자원을 명시로 받은 사람들」을 뽑는 질의가 목록 한 페이지마다 돈다.
        Index("ix_resource_grants_resource", "resource_type", "resource_id"),
    )
