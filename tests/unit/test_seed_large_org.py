"""큰 조직 시드는 개발 DB 에만 심는다 (O1 · 계획 8.3).

`scripts/dev/seed_large_org.py` 는 지울 수 없는 행 수백 개를 남긴다. 운영 DB 에 한 번 잘못 붙으면 조직도가 견본 부서로 덮인다 —
그래서 거절 조건을 시험으로 못박는다(맞는 견본 · 틀린 견본).
"""
import pytest

from scripts.dev.seed_large_org import MAX_DEPTH, Refused, _tree_plan, ensure_dev_database


@pytest.mark.parametrize("url", [
    "postgresql://u:p@127.0.0.1:55433/clovir_uiqa_1",
    "postgresql+psycopg://u:p@localhost/clovir_dev",
])
def test_loopback_dev_databases_are_accepted(url):
    ensure_dev_database(url, app_env="test")


@pytest.mark.parametrize("url,env", [
    ("postgresql://u:p@10.100.64.71:5432/clovirassist", "test"),
    ("postgresql://u:p@db.internal/clovirassist", "development"),
    ("postgresql://u:p@127.0.0.1:5432/clovirassist", "production"),
    ("postgresql://u:p@127.0.0.1:5432/clovirassist", "PRODUCTION"),
])
def test_remote_or_production_databases_are_refused(url, env):
    with pytest.raises(Refused):
        ensure_dev_database(url, app_env=env)


def test_the_tree_plan_has_two_hundred_departments_within_five_levels():
    plan = _tree_plan()
    assert len(plan) == 200
    levels = [level for _name, level, _parent in plan]
    assert max(levels) == MAX_DEPTH
    assert levels.count(1) == 4
    # 부모는 언제나 앞에 있고 한 단계 위다 — 심는 차례가 곧 부모 먼저다.
    for i, (_name, level, parent) in enumerate(plan):
        if parent is None:
            assert level == 1
        else:
            assert parent < i and plan[parent][1] == level - 1
    assert len({name for name, _l, _p in plan}) == 200
