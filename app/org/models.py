"""조직·조직 단위(부서)·직책 명부 모델.

OrgUnit/JobTitle 두 모델은 모양이 같다(id, name, active, created_at). 이름 하나만 다른 두
테이블이지만 합치지 않는다 — 한 표에 담으면 유일 제약이 (kind, name) 복합이 되어 실수로
부서와 직책이 같은 이름 공간을 나눠 쓰게 되고, FK도 어느 쪽을 가리키는지 스키마가
말해 주지 못한다. `OrgUnit.kind` 는 **조직도 안의** 마디 종류이고 직책은 조직도 밖이다.

Organization 은 제품화 대비(§7.1.A)로 먼저 심는 1급 엔티티다. 0022 가 DEFAULT_ORG_ID 한 행을
시드했고, 0024 부터 부서·직책·내용물 테이블이 org_id 로 그 행을 가리킨다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    JsonText,
    OrgScopedMixin,
    UUIDPrimaryKeyMixin,
    new_uuid,
    utcnow,
)
from app.org.constants import ORG_ACTIVE


class Organization(Base):
    """테넌트 한 곳. 단일 조직으로 운영하는 동안에도 행이 하나 있어야 org_id FK 가 의미를 갖는다."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # slug 는 사람이 쓰는 안정적인 키(URL·설정·운영 스크립트에서 UUID 대신 쓴다).
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ORG_ACTIVE)
    # 조직별 설정(브랜딩·쿼터 등)을 담을 자리. 지금은 항상 NULL — 스키마 churn 없이 나중에 채운다.
    settings_json: Mapped[str | None] = mapped_column(JsonText)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class _OrgNameMixin:
    # 쓰는 사람이 있으면 삭제할 수 없다(FK가 가리키는 행을 지울 수 없다). 대신 비활성으로
    # 두면 새로 고를 수는 없지만 기존 사용자는 그대로 유지된다.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ── 조직 단위의 종류 (S5) ────────────────────────────────────────────────────
# 트리에 담기는 마디의 성격이다. 지금은 부서 하나뿐이고, 본부·팀·파트는 **깊이**로
# 표현된다(그것이 0024 이후의 실제 데이터다). 값을 미리 늘려 두지 않는다 — 쓰지 않는
# 종류는 화면마다 "그건 뭐죠" 를 만들고, 필요해지는 Session 이 자기 뜻과 함께 추가한다.
ORG_UNIT_DEPARTMENT = "department"

ALL_ORG_UNIT_KINDS = frozenset({ORG_UNIT_DEPARTMENT})


class OrgUnit(_OrgNameMixin, OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """조직 안의 단위 한 곳 — **트리**다(parent_id 자기참조).

    ## 왜 `departments` 가 아니라 `org_units` 인가 (S5)

    이 표가 담는 것은 처음부터 「부서」가 아니라 **조직도의 마디**였다. 0024 가 트리로 만든
    뒤로 같은 표에 본부·팀·파트가 함께 들어 있고, 그 셋을 부서라는 한 단어로 부르면
    권한 상속을 설명할 때마다 「부서의 부서」 같은 말을 하게 된다. 이름을 마디의 이름으로
    바꾸고 `kind` 를 붙여, 나중에 다른 성격의 마디가 필요해질 때 **표를 하나 더 만들지
    않도록** 한다.

    컬럼 이름(`users.department_id` · `projects.dept_id`)은 그대로 둔다. 그쪽은 API 응답과
    화면 어휘에 그대로 나가는 이름이라, 바꾸면 이 Session 의 범위가 아니라 사용자에게
    보이는 말이 바뀐다.

    이름 유일성은 전역이 아니라 **조직 안에서** 성립한다(`uq_org_units_org_name`).
    조직이 둘 이상이 되는 순간 전역 유니크는 다른 회사의 '개발팀' 등록을 막아 버린다.

    트리를 별도 closure 테이블 없이 parent_id 하나로 두는 이유: 마디 수가 수십 규모라
    재귀 조회 비용이 무의미하고, closure 테이블은 이동·삭제 때마다 동기화해야 하는
    두 번째 진실이 된다. 하위 전개는 `app/core/org_tree.py` 한 곳에서만 한다.
    """

    __tablename__ = "org_units"

    # 이름이 유일해야 목록을 둔 의미가 있다 — 같은 부서가 둘이면 다시 'ClovirONE팀'과
    # 'ClovirOne팀' 문제로 돌아간다. 유일성은 아래 복합 인덱스가 건다.
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ORG_UNIT_DEPARTMENT,
        server_default=ORG_UNIT_DEPARTMENT,
    )
    # 최상위 마디는 NULL. 부모가 지워지면 자식은 사라지지 않고 최상위로 올라온다.
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id", ondelete="SET NULL"), index=True
    )

    __table_args__ = (
        Index("uq_org_units_org_name", "org_id", "name", unique=True),
    )


# 옛 이름. 부서는 지금도 이 표의 유일한 종류이고, 도메인 코드 열일곱 곳이 이 이름으로
# 부른다. 별칭 하나로 두는 이유는 「같은 표를 두 이름으로 부르는 것」과 「표가 둘인 것」이
# 전혀 다른 상태이기 때문이다 — 여기서는 표도 클래스도 하나다.
Department = OrgUnit


class JobTitle(_OrgNameMixin, OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """직책 한 개. 부서와 달리 이름 유일성은 **전역**으로 남긴다.

    '팀장'은 조직이 늘어도 같은 이름을 쓰는 것이 자연스럽고, 유니크를 바꾸면 재생성
    범위만 넓어지고 얻는 것이 없다. 부서 트리가 0024 의 목적이므로 부서에만 조직별
    유니크를 건다.
    """

    __tablename__ = "job_titles"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
