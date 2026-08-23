"""값 변환이 **틀린 쪽으로도 움직이는가** (S13).

「전부 통과」만 보이는 변환기는 아무것도 안 하는 변환기와 구별되지 않는다. 그래서 각
항목을 Known Good 과 Known Bad 로 짝지어 본다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
import sqlalchemy as sa

from app.core.models_base import Base, JsonText
from app.migration.convert import TOO_LONG, UNREADABLE, ConvertError, coerce

pytestmark = pytest.mark.unit

_META = sa.MetaData()
SAMPLE = sa.Table(
    "convert_sample", _META,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("short", sa.String(8)),
    sa.Column("body", sa.Text()),
    sa.Column("payload", JsonText()),
    sa.Column("flag", sa.Boolean()),
    sa.Column("day", sa.Date()),
    sa.Column("moment", sa.DateTime()),
    sa.Column("count", sa.Integer()),
    sa.Column("ratio", sa.Float()),
    sa.Column("rank", sa.Numeric()),
)


def col(name: str):
    return SAMPLE.c[name]


# ── 날짜: D-248 이 옮긴 자리 ─────────────────────────────────────────────────


def test_calendar_day_reads_iso_and_timestamps():
    assert coerce(col("day"), "2026-08-23") == date(2026, 8, 23)
    # 소스가 시각을 날짜 칸에 넣는 일이 흔하다. 앞 10자가 달력일이다.
    assert coerce(col("day"), "2026-08-23T14:00:00.000Z") == date(2026, 8, 23)


def test_calendar_day_refuses_what_it_cannot_read():
    """**Known Bad** — `'TBD'` 를 조용히 NULL 로 만들지 않는다."""
    with pytest.raises(ConvertError) as caught:
        coerce(col("day"), "TBD")
    assert caught.value.kind == UNREADABLE
    with pytest.raises(ConvertError):
        coerce(col("day"), "2026-02-31")


def test_timestamp_lands_in_naive_utc():
    assert coerce(col("moment"), "2026-08-23T14:00:00.000Z") == datetime(
        2026, 8, 23, 14, 0
    )
    # 오프셋이 있으면 UTC 로 옮기고 tzinfo 를 뗀다 (app/core/db.py 의 저장 규약).
    assert coerce(col("moment"), "2026-08-23T23:00:00+09:00") == datetime(
        2026, 8, 23, 14, 0
    )


def test_none_passes_through_untouched():
    """NOT NULL 위반은 DB 가 잡는 것이 옳다 — 여기서 기본값을 지어내지 않는다."""
    for name in ("short", "day", "moment", "flag", "payload", "count"):
        assert coerce(col(name), None) is None


# ── 길이: Exit 조건이 세는 자리 ──────────────────────────────────────────────


def test_a_value_that_fits_goes_in():
    assert coerce(col("short"), "12345678") == "12345678"


def test_a_value_that_does_not_fit_is_refused_not_truncated():
    """**자르지 않는다.** 자르면 적재는 초록이고 데이터는 손상된다."""
    with pytest.raises(ConvertError) as caught:
        coerce(col("short"), "123456789")
    assert caught.value.kind == TOO_LONG
    assert "9자인데" in caught.value.message
    assert "convert_sample.short" in caught.value.message


def test_text_has_no_ceiling():
    """`Text` 는 상한이 없다 — 긴 본문이 길이 때문에 거절되면 안 된다."""
    assert coerce(col("body"), "가" * 100_000).startswith("가")


# ── boolean: SQLite 는 타입을 강제하지 않는다 ────────────────────────────────


@pytest.mark.parametrize("value", [0, "0", "false", "FALSE", "no", "", False])
def test_falsey_shapes_all_read_as_false(value):
    assert coerce(col("flag"), value) is False


@pytest.mark.parametrize("value", [1, "1", "true", "yes", True])
def test_truthy_shapes_all_read_as_true(value):
    assert coerce(col("flag"), value) is True


# ── jsonb: 깨진 JSON 은 여기서 멈춘다 ────────────────────────────────────────


def test_valid_json_string_passes_through_as_a_string():
    """`JsonText` 의 파이썬 계약은 **문자열**이다 (D-215)."""
    assert coerce(col("payload"), '{"a": 1}') == '{"a": 1}'


def test_broken_json_is_named_here_not_by_the_driver():
    """**Known Bad** — 드라이버가 던지면 표 이름도 컬럼 이름도 안 남는다."""
    with pytest.raises(ConvertError) as caught:
        coerce(col("payload"), "{not json")
    assert caught.value.kind == UNREADABLE
    assert "convert_sample.payload" in caught.value.message


def test_empty_string_becomes_null_because_jsonb_cannot_hold_it():
    assert coerce(col("payload"), "") is None
    assert coerce(col("payload"), "   ") is None


# ── 수 ───────────────────────────────────────────────────────────────────────


def test_numbers_read_from_strings():
    assert coerce(col("count"), "42") == 42
    assert coerce(col("ratio"), "1.5") == 1.5
    assert str(coerce(col("rank"), "1024")) == "1024"


def test_a_number_that_is_not_a_number_is_refused():
    with pytest.raises(ConvertError):
        coerce(col("count"), "마흔둘")


# ── 실제 스키마 위에서 ───────────────────────────────────────────────────────


def test_the_real_schema_has_the_columns_this_module_must_handle():
    """이 파일이 만든 표가 **제품 스키마와 같은 종류**를 다루는지 확인한다.

    합성 표만 시험하면 제품이 쓰는 타입이 하나 늘 때 그 사실을 못 본다.
    """
    import app.models_registry  # noqa: F401

    kinds = {
        type(column.type).__name__
        for table in Base.metadata.sorted_tables
        for column in table.columns
    }
    for expected in ("String", "Text", "Boolean", "Date", "DateTime", "Integer", "JsonText"):
        assert expected in kinds, f"제품 스키마에 {expected} 가 없다 — 시험이 낡았다"
