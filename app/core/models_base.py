"""Declarative base and shared model mixins.

Convention: all datetime columns store naive UTC (see app.core.db docstring).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid() -> str:
    return str(uuid.uuid4())


# 다중값(관계 이름·id 목록)을 한 컬럼에 담는 구분자. Unit Separator(0x1f)는 Notion 제목이나
# id 에 사실상 나타나지 않으므로 (1) 값에 콤마가 들어가도 안전하고 (2) 필터를 '정확한 토큰'으로
# 매칭할 수 있다(콤마 substring 매칭의 오탐 '보고'⊂'보고서' 방지). 저장은 양끝에도 구분자를
# 붙여(sentinel-wrapped) contains 매칭이 토큰 경계를 정확히 잡게 한다.
#
# 이 규약은 원래 app/team_docs/models.py 가 정의했다. ticket_cache 도 같은 규약을 써야 하므로
# 정의를 여기 한 곳으로 올리고 team_docs 는 그대로 재수출한다(기존 import 경로 무변경).
NAMES_SEP = "\x1f"


def join_names(names) -> str:
    vals = [n.strip() for n in (names or []) if n and str(n).strip()]
    if not vals:
        return ""
    return NAMES_SEP + NAMES_SEP.join(vals) + NAMES_SEP


def split_names(joined: str) -> list[str]:
    return [p for p in (joined or "").split(NAMES_SEP) if p.strip()]


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class OrgScopedMixin:
    """조직 스코프 컬럼(§7.1.A). 0024 부터 `app/core/scope.py` 가 실제로 읽는다.

    nullable 로 두는 이유: 단일 조직 상태에서 NOT NULL 승격은 기존 테이블 전부를 흔드는
    변경인데 얻는 게 없다. 기존 테이블은 0024 마이그레이션이 같은 모양의 컬럼을 붙이고
    DEFAULT_ORG_ID 로 백필했다.

    **`default=DEFAULT_ORG_ID` 가 이 믹스인에서 가장 중요한 한 줄이다.** 컬럼은 nullable
    이지만 값을 비워 두면 두 가지가 조용히 깨진다:
      * SQLite 는 UNIQUE 에서 NULL 을 서로 다른 값으로 본다 → `(org_id, name)` 복합
        유니크가 아무것도 막지 않게 된다(부서가 소리 없이 둘로 갈라진다);
      * SQL 의 `org_id = :org` 는 NULL 행을 고르지 못한다 → 스코프 필터에서 행이 통째로
        사라진다.
    마이그레이션이 백필만 하고 신규 행이 NULL 로 들어가면 다음 날부터 구멍이 다시 열린다.

    declared_attr 를 쓰는 이유: ForeignKey 객체는 여러 테이블이 공유할 수 없어 클래스마다
    새로 만들어야 한다(믹스인 컬럼 복사 규칙).
    """

    @declared_attr
    @classmethod
    def org_id(cls) -> Mapped[str | None]:
        # 지연 import: app.org.constants 는 app 안의 것을 하나도 import 하지 않으므로
        # 순환은 없지만, 모델 기반 모듈이 feature 패키지를 모듈 최상단에서 끌어오는
        # 모양은 피한다.
        from app.org.constants import DEFAULT_ORG_ID

        return mapped_column(
            String(36),
            ForeignKey("organizations.id"),
            nullable=True,
            index=True,
            default=DEFAULT_ORG_ID,
        )
