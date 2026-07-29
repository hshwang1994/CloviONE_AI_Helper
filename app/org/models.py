"""부서·직책 명부 모델.

두 모델은 모양이 같다(id, name, active, created_at). 이름 하나만 다른 두 테이블이지만
합치지 않는다 — 'kind' 컬럼 하나로 묶으면 유일 제약이 (kind, name) 복합이 되어 실수로
부서와 직책이 같은 이름 공간을 나눠 쓰게 되고, FK도 어느 쪽을 가리키는지 스키마가
말해 주지 못한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow


class _OrgNameMixin:
    # 이름이 유일해야 목록을 둔 의미가 있다 — 같은 부서가 둘이면 다시 'ClovirONE팀'과
    # 'ClovirOne팀' 문제로 돌아간다.
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    # 쓰는 사람이 있으면 삭제할 수 없다(FK가 가리키는 행을 지울 수 없다). 대신 비활성으로
    # 두면 새로 고를 수는 없지만 기존 사용자는 그대로 유지된다.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Department(_OrgNameMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "departments"


class JobTitle(_OrgNameMixin, UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_titles"
