"""목록 정렬 기계(`app/core/sort.py`)의 계약.

여기서 재는 것은 「정렬이 되는가」가 아니라 **어긋나면 아무 소리도 안 나는 네 가지**다:
화이트리스트 밖 값의 처리 · 방향 기본값 · tiebreak 가 1차 키와 같은 방향인가 · NULL 자리.
그 넷 중 하나만 빠져도 무한 스크롤에서 행이 건너뛰어지거나 중복되고, 오류는 안 난다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from app.core.sort import SortParams, SortSpec, order_by

pytestmark = pytest.mark.unit

Base = declarative_base()


class Row(Base):
    __tablename__ = "sort_probe"
    id = Column(String(36), primary_key=True)
    created_at = Column(String(32))
    name = Column(String(64))
    count = Column(Integer)
    secret = Column(String(64))


SPEC = SortSpec(
    columns={"created_at": Row.created_at, "name": Row.name, "count": Row.count},
    default="created_at",
    tiebreak=Row.id,
    default_order="desc",
)


def sql(clauses):
    return [str(c.compile(compile_kwargs={"literal_binds": True})) for c in clauses]


def test_default_when_no_params():
    got = sql(order_by(SPEC, None))
    assert got[0].startswith("sort_probe.created_at DESC")
    assert got[1].startswith("sort_probe.id DESC")


def test_unknown_key_falls_back_to_default_not_400():
    """모르는 키는 **거절하지 않는다** — 순서만 기본으로 돌아간다.

    틀린 정렬 값은 어느 행이 나오는지를 안 바꾼다. 400 으로 거절하면 옛 저장된 뷰와
    북마크가 그 순간 통째로 죽는다.
    """
    got = sql(order_by(SPEC, SortParams(sort="없는키", order="asc")))
    assert got[0].startswith("sort_probe.created_at ASC")


def test_whitelist_is_a_dict_lookup_not_getattr():
    """`getattr(Model, key)` 였다면 여기서 `secret` 컬럼이 나온다.

    멤버십 검사와 속성 조회가 떨어져 있으면 다음 사람이 하나만 옮긴다 — 그 틈으로
    아무 컬럼이나 정렬 키가 된다.
    """
    got = sql(order_by(SPEC, SortParams(sort="secret", order="asc")))
    assert "secret" not in got[0]
    assert got[0].startswith("sort_probe.created_at ASC")


def test_tiebreak_follows_primary_direction():
    """tiebreak 가 1차 키와 **다른 방향**이면 동률 구간의 순서가 쪽마다 뒤집힌다."""
    asc = sql(order_by(SPEC, SortParams(sort="name", order="asc")))
    assert asc[0].startswith("sort_probe.name ASC")
    assert asc[1].startswith("sort_probe.id ASC")
    desc = sql(order_by(SPEC, SortParams(sort="name", order="desc")))
    assert desc[0].startswith("sort_probe.name DESC")
    assert desc[1].startswith("sort_probe.id DESC")


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_nulls_last_in_both_directions(order):
    """PG 는 ASC 에서 NULL 을 뒤로, SQLite 는 앞으로 놓는다 — 명시 안 하면 백엔드마다 다르다."""
    got = sql(order_by(SPEC, SortParams(sort="count", order=order)))
    assert "NULLS LAST" in got[0]


def test_order_default_comes_from_spec():
    spec = SortSpec(columns={"name": Row.name}, default="name", tiebreak=Row.id, default_order="asc")
    got = sql(order_by(spec, SortParams(sort="name", order=None)))
    assert got[0].startswith("sort_probe.name ASC")


def test_keys_are_stable_and_sorted():
    """프런트 미러가 이 목록을 그대로 받아 적는다 — 순서가 흔들리면 신선도 검사가 매번 빨개진다."""
    assert SPEC.keys == ("count", "created_at", "name")


def test_default_must_be_in_columns():
    with pytest.raises(ValueError):
        SortSpec(columns={"a": Row.name}, default="b", tiebreak=Row.id)