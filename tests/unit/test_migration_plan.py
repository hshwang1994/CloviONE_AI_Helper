"""이관 계획이 **소스 전부를 설명하는가** (S13).

계획이 표 하나를 빠뜨리면 그 표는 조용히 안 옮겨진다. 오류가 안 나므로 아무도
알아채지 못하고, 알아채는 시점은 Cutover 뒤 그 화면을 여는 사람이다.
"""

from __future__ import annotations

import pytest

from app.backups.policy import excluded_tables
from app.migration import plan

pytestmark = pytest.mark.unit


def test_the_declared_source_list_is_not_empty():
    """**빈 목록을 훑고 초록을 찍는 상태**가 아님을 먼저 보인다 (D-213)."""
    assert len(plan.LEGACY_TABLES) == 75, (
        f"옛 설치 실측은 75표다 — 지금 {len(plan.LEGACY_TABLES)}표를 선언했다"
    )


def test_every_declared_source_table_is_classified():
    """선언한 75표가 넷 중 하나로 **반드시** 간다. 다섯 번째 칸은 없다."""
    result = plan.classify(plan.LEGACY_TABLES)
    accounted = (
        {c.source for c in result.copy}
        | {table for table, _reason in result.dropped}
        | set(result.derived)
        | set(result.unknown)
    )
    assert accounted == set(plan.LEGACY_TABLES)
    assert not result.unknown, f"계획에 없는 표: {result.unknown}"
    assert not result.missing_target


def test_an_unknown_source_table_is_reported_not_skipped():
    """**반례** — 계획에 없는 표를 만나면 조용히 지나가지 않는다."""
    result = plan.classify(set(plan.LEGACY_TABLES) | {"brand_new_table"})
    assert result.unknown == ("brand_new_table",)
    assert "brand_new_table" not in {c.source for c in result.copy}


def test_a_missing_source_table_is_reported_too():
    """**반례** — 계획에는 있는데 소스에 없으면 그것도 사실로 남는다."""
    shrunk = set(plan.LEGACY_TABLES) - {"users"}
    result = plan.classify(shrunk)
    assert "users" in result.missing_target


def test_derived_tables_come_from_the_backup_policy():
    """파생 목록의 정본은 하나다 (D-270).

    여기서 다시 적으면 갈라지고, 갈라진 사실은 Cutover 뒤 첫 복구 리허설 5단계에서
    처음 드러난다 — 그때는 이미 운영 데이터가 들어간 뒤다.
    """
    assert plan.DERIVED_TABLES == excluded_tables()
    assert "search_documents" in plan.DERIVED_TABLES


def test_renamed_tables_point_at_tables_that_exist():
    order = set(plan.load_order())
    for source, target in plan.RENAMED_TABLES.items():
        assert target in order, f"{source} → {target} 인데 {target} 이 없다"
        assert source not in order, f"{source} 이 아직 대상 스키마에 있다"


def test_dropped_tables_all_carry_a_reason():
    """이유 없는 삭제는 「빠뜨렸다」와 구별되지 않는다."""
    for table, reason in plan.DROPPED_TABLES.items():
        assert reason.strip(), f"{table} 에 이유가 없다"
        assert len(reason) > 10, f"{table} 의 이유가 너무 짧다: {reason}"


def test_copies_are_ordered_so_foreign_keys_hold():
    """부모 표가 먼저다. 순서가 틀리면 적재가 FK 위반으로 죽는다."""
    result = plan.classify(plan.LEGACY_TABLES)
    ordered = [c.target for c in plan.ordered_copies(result)]
    for parent, child in (
        ("organizations", "users"),
        ("users", "projects"),
        ("org_units", "projects"),
        ("projects", "tickets"),
        ("tickets", "ticket_comments"),
    ):
        assert ordered.index(parent) < ordered.index(child), (
            f"{parent} 이 {child} 보다 뒤에 있다"
        )
