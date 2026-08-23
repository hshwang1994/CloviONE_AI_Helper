"""값 하나를 옛 타입에서 새 타입으로 옮긴다 (S13).

## 왜 컬럼 목록이 아니라 **타입**을 보는가

D-248 이 옮긴 날짜 컬럼은 16개다. 그 열여섯을 여기 손으로 적어 두면, 열일곱 번째가
생기는 날 그 컬럼만 문자열로 들어가 `500` 이 난다 — 그리고 그 사실은 그 값을 실제로
읽는 화면을 여는 순간에야 드러난다.

그래서 이 파일은 **대상 컬럼의 SQLAlchemy 타입을 보고** 변환을 고른다. 새 컬럼이
생기면 그 컬럼의 타입이 알아서 자기 변환을 부른다. 목록을 관리할 필요가 없다.

## 못 옮기는 값은 **자르지 않는다**

`VARCHAR(n)` 을 넘는 값을 잘라서 넣으면 적재는 초록이고 데이터는 손상된다. 그 손상은
아무도 신고하지 않는다 — 화면에 뒷부분이 없다는 것을 아는 사람이 없기 때문이다.
그래서 여기서는 **거절하고 findings 로 올린다.** 「길이 초과 0」은 S13 의 Exit 조건이고
(MASTER_PLAN §9.1), 자르기 시작하면 그 수는 언제나 0 이 된다.

## SQLite 의 boolean 은 정수다

`0`/`1` 이 온다. `bool(value)` 로 끝나지 않는 이유는 문자열 `'0'` 이다 — SQLite 는
타입을 강제하지 않아서 같은 컬럼에 `0`·`'0'`·`'false'` 가 섞일 수 있다. 셋 다 거짓이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core import dates
from app.core.models_base import JsonText

__all__ = ["ConvertError", "Converted", "coerce", "text_length_limit"]

_FALSE_WORDS = frozenset({"0", "false", "f", "no", "n", ""})


class ConvertError(ValueError):
    """이 값은 이 컬럼에 못 들어간다. **왜인지**를 들고 있다."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        # `too_long` 과 `unreadable` 을 구별한다 — Exit 조건이 「길이 초과 0」을 따로
        # 세기 때문이고, 대응도 다르다(하나는 컬럼을 넓히는 일이고 하나는 값을 고치는 일이다).
        self.kind = kind
        self.message = message


TOO_LONG = "too_long"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Converted:
    value: object


def text_length_limit(column) -> int | None:
    """이 컬럼이 받는 최대 글자 수. 무제한(`Text`)이면 `None`."""
    type_ = column.type
    if isinstance(type_, JsonText) or isinstance(type_, JSONB):
        return None
    if isinstance(type_, Text):
        return None
    if isinstance(type_, String):
        return type_.length
    return None


def coerce(column, value):
    """소스 값 → 이 컬럼이 받는 값. 못 넣으면 `ConvertError`.

    `None` 은 그대로 통과시킨다. NOT NULL 위반은 여기가 아니라 DB 가 잡는 것이 옳다 —
    여기서 기본값을 지어내면 「비어 있었다」와 「우리가 채웠다」를 구별할 수 없게 된다.
    """
    if value is None:
        return None

    type_ = column.type

    # JsonText 는 저장이 `jsonb` 이고 파이썬 값은 문자열이다. 옛 컬럼은 `Text` 였으므로
    # 그대로 문자열이 온다 — 다만 **깨진 JSON 은 여기서 걸러야 한다.** 안 그러면
    # psycopg 가 던지는 오류가 표 이름도 컬럼 이름도 없이 올라온다.
    if isinstance(type_, JsonText) or isinstance(type_, JSONB):
        return _coerce_json(column, value)

    if isinstance(type_, Boolean):
        return _coerce_bool(value)

    # Date 는 DateTime 의 하위가 아니다 — 두 검사의 순서를 바꿔도 되지만, 달력일과
    # 시각은 다른 축이므로(D-248) 각각 자기 파서를 부르게 둔다.
    if isinstance(type_, Date) and not isinstance(type_, DateTime):
        return _coerce_date(column, value)

    if isinstance(type_, DateTime):
        return _coerce_dt(column, value)

    if isinstance(type_, Integer):
        return _coerce_int(column, value)

    if isinstance(type_, Float):
        return _coerce_float(column, value)

    if isinstance(type_, Numeric):
        return _coerce_numeric(column, value)

    if isinstance(type_, (String, Text)):
        return _coerce_text(column, value)

    return value


def _coerce_json(column, value):
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text:
        # 옛 컬럼에는 빈 문자열이 들어 있는 행이 있다. `jsonb` 는 빈 문자열을 못 받는다 —
        # 「값이 없다」는 뜻이므로 NULL 로 옮긴다. 컬럼이 NOT NULL 이면 DB 가 잡는다.
        return None
    try:
        json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: JSON 을 읽을 수 없습니다."
        ) from exc
    return text


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in _FALSE_WORDS


def _coerce_date(column, value):
    parsed = dates.parse_date(value)
    if parsed is None:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: 날짜로 읽을 수 없습니다."
        )
    return parsed


def _coerce_dt(column, value):
    parsed = dates.parse_dt(value)
    if parsed is None:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: 시각으로 읽을 수 없습니다."
        )
    return parsed


def _coerce_int(column, value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: 정수로 읽을 수 없습니다."
        ) from exc


def _coerce_float(column, value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: 수로 읽을 수 없습니다."
        ) from exc


def _coerce_numeric(column, value):
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ConvertError(
            UNREADABLE, f"{column.table.name}.{column.name}: 수로 읽을 수 없습니다."
        ) from exc


def _coerce_text(column, value):
    if isinstance(value, bytes):
        # 옛 DB 에 BLOB 로 들어간 텍스트가 있다. 못 읽는 바이트는 버리지 않고 거절한다.
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConvertError(
                UNREADABLE, f"{column.table.name}.{column.name}: UTF-8 로 읽을 수 없습니다."
            ) from exc
    elif isinstance(value, (datetime, date)):
        value = value.isoformat()
    elif not isinstance(value, str):
        value = str(value)

    limit = text_length_limit(column)
    if limit is not None and len(value) > limit:
        raise ConvertError(
            TOO_LONG,
            f"{column.table.name}.{column.name}: {len(value)}자인데 컬럼은 {limit}자까지입니다.",
        )
    return value
