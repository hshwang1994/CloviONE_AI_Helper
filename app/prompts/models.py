"""프롬프트와 정책의 버전 (spec §21.10). 버전 하나가 한 행이고, 발행한 내용은 덮어쓰지 않는다 (spec §17.1).

## 생명주기는 셋이다 (D-518)

초안 → 발행 → 보관. 예전에는 초안과 발행 사이에 「테스트」와 「검토」가 있었는데 둘 다 상태 글자만 바꿀 뿐 무엇도
실행하거나 검증하지 않았다. 0040 이 그 두 상태의 행을 초안으로 되돌렸다. 되돌리기는 옛 버전의 내용을 **새 버전으로**
발행한다.

## 프롬프트의 사용처 (`slot`)

프롬프트는 사용처(`app/ai/prompts/catalog.py`) 하나에 붙는다. 사용처마다 발행본은 하나이고, AI 런타임이 다음
호출부터 그것을 쓴다. 발행본이 없는 사용처는 기본 제공 지시문을 쓴다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, UUIDPrimaryKeyMixin, utcnow

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

# 생명주기(spec §17.1, D-518). 되돌리기는 옛 버전을 새 버전으로 다시 발행하는 것이다.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_PUBLISHED, STATUS_ARCHIVED}),
    STATUS_PUBLISHED: frozenset({STATUS_ARCHIVED}),
    STATUS_ARCHIVED: frozenset(),
}


class Prompt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompts_name_version"),
    # 발행본은 이름당 하나뿐이다(마이그레이션 0053). **부분** 유니크라 초안·보관본은
    # 몇 개든 상관없다 — 전체 유니크로 만들면 같은 이름의 두 번째 버전 자체를 못 만든다.
    # 0053 은 `sqlite_where=` 로 걸었고 그 키워드는 PG 에서 무시된다.
        Index(
            "ux_prompts_published_dedup", "name", unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        # 사용처마다 발행본은 하나다(0040). 두 관리자가 같은 사용처에 거의 동시에 발행하면 진 쪽이 409 를 받는다.
        Index(
            "ux_prompts_slot_published", "slot", unique=True,
            postgresql_where=text("status = 'published' AND slot IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 사용처(`app/ai/prompts/catalog.py`). 비어 있으면 어디에도 쓰이지 않는다 - 발행하려면 골라야 한다.
    slot: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class Policy(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_policies_name_version"),
        # `Prompt` 와 같은 규칙이다(0053 이 두 표에 같은 인덱스를 걸었다).
        Index(
            "ux_policies_published_dedup", "name", unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # WF1 단독 결함 — 자매 엔티티 Prompt에는 있는데 Policy에는 없어 "이 정책이 무엇을
    # 강제하는가"를 목록에서 말할 방법이 없었다(마이그레이션 0058).
    purpose: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 규칙. 종류(`kind`)마다 칸이 정해져 있다(`app/ai/policy/schemas.py`, D-519).
    content_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    # 종류: approval · data_protection · content, 그리고 새로 만들 수 없는 legacy(0041 이 보관한 옛 원본).
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="legacy", server_default="legacy",
                                      index=True)
    # 적용 대상: 액션 키 목록이거나 ["*"](그 종류가 붙을 수 있는 모든 기능).
    applies_to_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="[]", server_default="[]")
    # 0041 이 옛 정책을 새 형식으로 옮긴 초안이면 그 원본(보관한 행)의 id. 화면이 검토를 요청하는 표식이다.
    migrated_from_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
