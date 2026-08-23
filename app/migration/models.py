"""`legacy_mapping` — 옛 식별자와 우리 식별자를 잇는 다리 (S13 · MASTER_PLAN §7.3).

## 왜 표가 필요한가

Cutover 뒤에도 옛 링크·옛 문서·옛 대화가 Notion page id 로 무언가를 가리킨다. 그때
「이 페이지가 어디로 갔는가」에 답할 수 있어야 한다. 그런데 **운영 Business Logic 은
Migration 이후 Notion ID 를 쓰지 않는다**(§7.3) — 그래서 그 답을 도메인 표의 컬럼이
아니라 **이 표 하나**에 모은다. 도메인 표에 흩어 두면 「어디를 봐야 하는가」가 자원마다
달라지고, 그 지식은 코드에만 남는다.

`documents.legacy_page_id` 와 겹치지 않느냐 — 겹치지 않는다. 저것은 **제품이 계속 쓰는
별칭**이고(옛 주소로 문서가 열려야 한다), 이 표는 **이관 이력**이다. 재실행이 같은 행을
다시 만들지 않게 막는 것도 이쪽 일이다.

티켓 쪽에는 그 별칭이 없다 — 옛 티켓 이름(`GIT-142`)은 이관하지 않기로 했다(D-283).
그래서 옛 Notion 페이지에서 티켓으로 가는 길은 **이 표 하나**다.

## 두 방향 모두 하나여야 한다

옛 식별자 하나가 두 대상을 가리키면 「어디로 갔나」에 답이 둘이다. 반대로 한 대상이
두 옛 식별자를 주장하면 두 옛 페이지가 같은 티켓으로 합쳐졌다는 뜻인데, 그것은 이관
사고이지 정상이 아니다. 유니크 둘이 그 둘을 각각 막는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

# ── 옛 소스 ──────────────────────────────────────────────────────────────────
SRC_SQLITE = "sqlite"
SRC_NOTION = "notion"
LEGACY_SOURCES: tuple[str, ...] = (SRC_SQLITE, SRC_NOTION)

# ── 대상 종류 ────────────────────────────────────────────────────────────────
#
# 도메인 이름이지 표 이름이 아니다. `document` 하나가 `documents` 와
# `document_versions` 두 표를 만들기 때문이다 — 표 이름으로 적으면 「그 판은
# 어디서 왔나」에 답할 자리가 없어진다.
T_TICKET = "ticket"
T_DOCUMENT = "document"
T_PROJECT = "project"
T_FILE = "file"
T_USER = "user"
TARGET_TYPES: tuple[str, ...] = (T_TICKET, T_DOCUMENT, T_PROJECT, T_FILE, T_USER)


class LegacyMapping(UUIDPrimaryKeyMixin, Base):
    """옛 식별자 하나 → 우리 식별자 하나."""

    __tablename__ = "legacy_mapping"

    legacy_source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Notion page id(36) · SQLite uuid(36) · 첨부는 `<page_id>:<n>` 이라 넉넉히 잡는다.
    legacy_source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    migrated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    __table_args__ = (
        Index(
            "uq_legacy_mapping_source",
            "legacy_source", "legacy_source_id", "target_type",
            unique=True,
        ),
        Index(
            "uq_legacy_mapping_target",
            "legacy_source", "target_type", "target_id",
            unique=True,
        ),
    )
