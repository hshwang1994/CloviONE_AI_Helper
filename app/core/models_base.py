"""Declarative base and shared model mixins.

Convention: all datetime columns store naive UTC (see app.core.db docstring).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import TypeDecorator


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


class JsonText(TypeDecorator):
    """저장은 **`jsonb`**, 파이썬 쪽 값은 **JSON 문자열** 그대로인 컬럼 (실행목록 6·7).

    SQLite 시절 이 컬럼들은 전부 `Text` 였고 앱은 `json.dumps` / `json.loads` 로 직접
    직렬화했다. PG 로 옮기면서 두 가지를 동시에 얻어야 했다:

      * 저장 타입은 진짜 `jsonb` 여야 한다 — 그래야 `->>` 로 키를 뽑고(`json_extract`
        대체) GIN 인덱스를 걸 수 있다. `Text` 로 두면 그 둘이 다 불가능하다.
      * 그런데 **호출부 100곳 이상이 이 값을 문자열로 읽고 쓴다.** S2 는 "도메인 변경
        없이 이식" 이므로 그 계약을 여기서 바꾸지 않는다.

    그래서 경계를 이 타입 하나에 둔다. 컬럼은 `jsonb` 이고, 파이썬이 보는 값은 문자열이다.

    **이 타입이 만드는 실제 변화 셋** — 전부 의도한 것이다:

      1. **깨진 JSON 을 저장할 수 없다.** `Text` 는 깨진 조각도 받았고 그 행은 읽는 쪽에서
         터졌다. 이제 쓰는 쪽에서 거부된다 — 틀린 값이 DB 에 들어가지 않는다.
      2. **키 순서와 공백이 정규화된다.** 같은 내용을 키 순서만 바꿔 적은 두 값이 이제
         같은 값이다. `approvals.request_payload_json` 이 유니크 키의 일부라 이 성질이
         중요하다 — 예전에는 키 순서만 바꿔 보내면 중복 pending 요청이 만들어졌다.
         **정규화 규약을 문서로 약속하는 대신 DB 가 강제한다.**
      3. **`LIKE` 를 직접 못 쓴다.** `jsonb` 에는 `LIKE` 연산자가 없다. 문자열로 훑어야
         하는 자리는 `payload_json.cast(Text)` 처럼 명시적으로 캐스트한다
         (`app/core/retention.py` · `app/schedules/router.py`).
    """

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            # 이미 dict/list 면 그대로 넘긴다 — 이 타입은 문자열 계약을 지키지만, 값을
            # 만들어 주는 쪽이 객체를 넣었을 때 조용히 두 번 감싸는 것보다 낫다.
            return value
        return json.loads(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # `ensure_ascii=False` 라야 한글이 이스케이프로 부풀지 않는다. 구분자는 파이썬
        # 기본값 그대로다 — 기존 코드가 만들던 문자열과 같은 모양이다.
        return json.dumps(value, ensure_ascii=False)


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
