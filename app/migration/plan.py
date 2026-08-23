"""무엇을 어디로 옮기고, 무엇을 왜 안 옮기는가 (S13).

## 실측이 만든 계획이다

옛 설치의 표는 **75개**이고 새 스키마는 **93개**다. 그 둘을 컬럼 단위로 대조해 보면
모양이 훨씬 단순하다:

| | 수 | 뜻 |
|---|---|---|
| 이름이 같고 컬럼이 그대로 | **61** | 컬럼 교집합을 그대로 복사한다 |
| 이름만 바뀌었다 | **2** | `departments`→`org_units`(D-234) · `ticket_cache`→`tickets`(D-238) |
| 안 옮긴다 | **12** | 아래 `DROPPED_TABLES` 가 이유를 적는다 |
| 파생이라 안 채운다 | **1** | `search_documents` — 아래 절 |
| 새 표라 소스가 없다 | 30 | 도메인 이전이 채운다(`load.py`) 또는 비어 있는 것이 정상이다 |

옛 컬럼 중 대상에 없는 것은 **둘뿐**이다: `prompts.runner_id` · `schedules.runner_id`.
둘 다 S11 이 러너를 걷으며 사라진 자리다(0009).

## 「빈 결과는 통과가 아니다」 (D-213)

이 파일이 손으로 적은 목록이라는 것이 위험이다 — 소스에 표가 하나 더 생기면 조용히
안 옮겨진다. 그래서 `classify()` 는 **모르는 표를 만나면 findings 로 올린다.** 실행
때마다 실제 SQLite 와 이 목록을 대조하고, 어긋나면 보고서가 말한다.

## 파생 넷은 백업과 **같은 목록**을 쓴다

`app/backups/policy.py::excluded_tables()` 를 import 한다. 두 목록이 갈라지면
Cutover 뒤 첫 복구 리허설이 5단계에서 실패한다 — 「제외 대상인데 행이 있다」로.
그 실패는 백업이 아니라 **이관**이 만든 것이고, 그 사실은 리허설 로그만 봐서는
안 보인다.
"""

from __future__ import annotations

from dataclasses import dataclass

import app.models_registry  # noqa: F401 — 이것을 빼면 `Base.metadata` 가 **일부만** 찬다
from app.backups.policy import excluded_tables
from app.core.models_base import Base

# ── 이름이 바뀐 표 ───────────────────────────────────────────────────────────
RENAMED_TABLES: dict[str, str] = {
    "departments": "org_units",   # D-234 — 컬럼 이름은 그대로다
    "ticket_cache": "tickets",    # D-238 — 컬럼 이름은 그대로다
}

# ── 안 옮기는 표와 그 이유 ───────────────────────────────────────────────────
#
# 「이유」는 보고서에 그대로 실린다. 이관 결과를 검토하는 사람이 저장소를 열지 않고도
# 「왜 이 표가 비었나」를 읽을 수 있어야 한다.
DROPPED_TABLES: dict[str, str] = {
    "alembic_version": "스키마 판 번호다. 새 체인이 자기 값을 갖는다(D-189).",
    "automation_templates": "S11 이 외부 자동화를 걷었다. 부를 곳이 없다(D-267, 0009).",
    "document_generations": "같은 이유다. 문서 생성 러너가 사라졌다(0009).",
    "runners": "같은 이유다. 러너 레지스트리를 내렸다(D-267, 0009).",
    "workflows": "같은 이유다. n8n 워크플로 목록이었다(0009).",
    "search_index": "SQLite FTS5 가상 표다. PG 에는 문법 자체가 없다(D-189).",
    "search_index_config": "위 FTS5 의 그림자 표다.",
    "search_index_data": "위 FTS5 의 그림자 표다.",
    "search_index_docsize": "위 FTS5 의 그림자 표다.",
    "search_index_idx": "위 FTS5 의 그림자 표다.",
}

# ── 안 옮기는 컬럼과 그 이유 ─────────────────────────────────────────────────
DROPPED_COLUMNS: dict[tuple[str, str], str] = {
    ("prompts", "runner_id"): "러너가 사라졌다(0009). 남은 컬럼은 전부 옮긴다.",
    ("schedules", "runner_id"): "같은 이유다.",
}

# ── 뒤 단계가 주인인 컬럼 — 표 복사가 **건드리지 않는다** ────────────────────
#
# 이 셋은 대상에 컬럼이 **있다.** 그런데 값을 정하는 것은 표 복사가 아니라 뒤 단계다.
# 둘 다 쓰면 재실행 두 번째 회차에서 이렇게 터진다:
#
#   1회차: 복사가 `project_uid = NULL` 을 넣고 → 재채번이 소속과 `seq` 를 정한다.
#   2회차: 복사가 **다시** `project_uid = NULL` 을 쓰는데 `seq` 는 이미 있다 →
#          `tickets_set_canonical_key()` 트리거가 「번호는 있는데 프로젝트가 없다」로
#          거절한다(0003).
#
# `projects.code` 는 더 조용하고 더 나쁘다. 소스에서 22건 전부 NULL 이라, 2회차 복사가
# 1회차에 붙인 Project Key 를 **지운다** — 그러면 `canonical_key` 를 만들 근거가
# 사라지고 `project_key_registry` 와 어긋난다.
#
# 값 하나에 주인은 하나다.
DERIVED_COLUMNS: dict[tuple[str, str], str] = {
    ("projects", "code"): "Project Key 는 `apply_confirmed` 가 정한다(D-243).",
    ("ticket_cache", "project_uid"): "소속은 재채번이 소스 relation 에서 다시 푼다(U11).",
    ("ticket_cache", "project_link"): "같은 판정의 결과다. 재채번이 함께 적는다.",
}

# ── 파생이라 안 채우는 표 ────────────────────────────────────────────────────
#
# **목록의 정본은 백업 정책이다.** 여기서 다시 적지 않는다 — 두 벌이 되는 순간
# 갈라지고, 갈라진 사실은 복구 리허설이 실패할 때 처음 드러난다(D-270).
DERIVED_TABLES: tuple[str, ...] = excluded_tables()

# ── 옛 설치의 표 목록 (실측 2026-08-23 · 운영 SQLite 스냅숏) ─────────────────
#
# 이 상수는 **시험이 읽는 지문**이다. 소스에 표가 생기거나 사라지면 실행이 findings 로
# 말하고(`classify`), 이 상수는 그때 사람이 갱신한다. 지금 값을 바꾸는 것은 「실측이
# 달라졌다」는 뜻이므로 근거와 함께 바꾼다.
LEGACY_TABLES: frozenset[str] = frozenset({
    "ai_quotas", "alembic_version", "announcement_dismissals", "announcements",
    "app_settings", "approval_delegations", "approvals", "audit_logs",
    "automation_templates", "backups", "board_attachments", "board_comments",
    "board_posts", "board_reactions", "chat_message_images", "chat_messages",
    "chat_read_cursors", "chat_room_members", "chat_rooms", "config_versions",
    "conversations", "departments", "document_cache", "document_comments",
    "document_favorites", "document_generations", "document_recent_views",
    "document_sync_state", "game_events", "game_room_members", "game_rooms",
    "heartbeats", "impersonation_sessions", "integrations", "job_titles", "jobs",
    "mail_deliveries", "messages", "notifications", "offboarding_runs",
    "offboarding_ticket_moves", "organizations", "password_reset_tokens", "policies",
    "project_health_snapshots", "project_members", "project_milestones",
    "project_sync_state", "project_weekly_reports", "projects", "prompts",
    "restore_rehearsals", "runners", "saved_views", "schedule_runs", "schedules",
    "search_documents", "search_index", "search_index_config", "search_index_data",
    "search_index_docsize", "search_index_idx", "sessions", "sync_status",
    "ticket_attachments", "ticket_cache", "ticket_comments", "ticket_meta_cache",
    "ticket_sync_state", "trash_items", "usage_events", "user_notion_mappings",
    "user_preferences", "users", "workflows",
})


@dataclass(frozen=True)
class TableCopy:
    """표 하나를 그대로 옮기는 계획."""

    source: str
    target: str

    @property
    def renamed(self) -> bool:
        return self.source != self.target


@dataclass(frozen=True)
class Classification:
    """소스 표 전부를 넷으로 가른 결과. **다섯 번째 칸은 없다.**"""

    copy: tuple[TableCopy, ...]
    dropped: tuple[tuple[str, str], ...]       # (표, 이유)
    derived: tuple[str, ...]                   # 표는 만들되 행은 안 넣는다
    unknown: tuple[str, ...]                   # 계획에 없는 표 — findings 로 올라간다
    missing_target: tuple[str, ...]            # 옮기려는데 대상 표가 없다


def _target_tables() -> frozenset[str]:
    return frozenset(Base.metadata.tables)


def classify(source_tables) -> Classification:
    """실제 소스의 표 목록을 계획과 대조한다.

    **`source_tables` 는 실행 시점의 SQLite 에서 읽은 것**이지 위 상수가 아니다.
    상수를 상수와 비교하면 언제나 통과하고, 그 통과는 아무것도 증명하지 않는다.
    """
    present = {str(name) for name in source_tables}
    targets = _target_tables()
    derived = set(DERIVED_TABLES)

    copies: list[TableCopy] = []
    dropped: list[tuple[str, str]] = []
    derived_hit: list[str] = []
    unknown: list[str] = []
    missing: list[str] = []

    for name in sorted(present):
        if name in DROPPED_TABLES:
            dropped.append((name, DROPPED_TABLES[name]))
            continue
        target = RENAMED_TABLES.get(name, name)
        if target in derived:
            derived_hit.append(name)
            continue
        if target not in targets:
            unknown.append(name)
            continue
        copies.append(TableCopy(source=name, target=target))

    # 계획이 아는데 소스에 없는 표. 「옛 설치마다 다르다」가 정상인 자리이므로 오류가
    # 아니라 사실로 보고한다 — 다만 조용히 사라지면 안 된다.
    for name in sorted(LEGACY_TABLES - present):
        missing.append(name)

    return Classification(
        copy=tuple(copies),
        dropped=tuple(dropped),
        derived=tuple(derived_hit),
        unknown=tuple(unknown),
        missing_target=tuple(missing),
    )


def load_order() -> tuple[str, ...]:
    """대상 표를 **FK 가 성립하는 순서**로 (`Base.metadata.sorted_tables`).

    손으로 적지 않는 이유: 표가 하나 늘 때마다 이 목록을 고쳐야 하고, 안 고치면 그
    표의 적재가 FK 위반으로 죽는다. 순환(`documents` ↔ `document_versions`)은
    SQLAlchemy 가 `use_alter` FK 를 빼고 정렬하므로 여기서 따로 다루지 않는다.
    """
    return tuple(table.name for table in Base.metadata.sorted_tables)


def ordered_copies(classification: Classification) -> tuple[TableCopy, ...]:
    """복사 계획을 적재 순서로 정렬한다."""
    order = {name: i for i, name in enumerate(load_order())}
    return tuple(sorted(classification.copy, key=lambda c: order.get(c.target, 10_000)))
