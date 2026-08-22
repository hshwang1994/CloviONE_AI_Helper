"""날짜의 경계 — 바깥 문자열과 안쪽 `date`/`datetime` 사이 (S7 · P-14a).

## 무엇이 문제였나

이 저장소는 날짜를 **문자열 'YYYY-MM-DD'** 로 저장했다. 그 선택에는 근거가 있었다 —
ISO 문자열은 사전순 정렬이 날짜순 정렬과 같아서 `ORDER BY` 와 범위 비교가 그냥 된다.

그런데 문자열은 **틀린 값을 막지 못한다.** `'2026-02-31'` 도, `'TBD'` 도, 빈 문자열도
들어간다. 그리고 그 값 하나가 기간 필터·공수 집계·번다운을 조용히 왜곡했다 — 번다운은
`ValueError` 를 잡아 `[]` 를 돌려주는 바람에 **HTTP 200 에 합계는 채워지고 그래프만 빈**
화면이 나왔다(`app/tickets/schemas.py::_ensure_real_date` 에 그 전말이 적혀 있다).
앱이 그것을 막으려고 정규식 + `date.fromisoformat` 검사를 **입구마다** 달았고, 달지 않은
입구(동기화·마이그레이션)로는 그대로 들어왔다.

이제 컬럼이 `date` 다. **DB 가 막는다** — 규약을 문서로 약속하지 않는다(D-215 가
`jsonb` 에서 쓴 것과 같은 판단).

## 그래서 이 파일이 하는 일

**경계는 하나여야 한다.** 바깥에서 오는 값(Notion 응답 · API 요청 · 마이그레이션 입력)은
문자열이고 안쪽은 `date`/`datetime` 다. 그 변환을 부르는 쪽마다 적으면 어떤 곳은
`fromisoformat` 을, 어떤 곳은 `strptime` 을, 어떤 곳은 앞 10자 자르기를 쓰게 되고,
그중 하나가 시간대를 잘못 다루는 날 「하루 밀린 목록」이 나온다.

## 시간대: 달력일과 타임스탬프는 다른 축이다

  * **달력일**(`due_date` · `starts_on` · `week_of`)은 시각이 아니다. KST 달력일과 같은
    축이고 시간대 변환을 하지 않는다. 여기에 시간대를 적용하면 자정 근처의 날짜가 하루씩
    밀린다.
  * **타임스탬프**(`notion_last_edited`)는 시각이다. 저장은 **naive UTC** 이고
    (`app/core/db.py` 의 규약), 들어오는 값에 오프셋이 있으면 UTC 로 옮겨서 tzinfo 를 뗀다.

이 구별을 놓치면 KST 는 UTC+9 라 **월요일 오전 9시 이전의 일이 UTC 로는 아직 일요일**
이어서 그 주에서 통째로 빠진다(`app/projects/weekly.py` 가 같은 함정을 적어 뒀다).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

__all__ = [
    "parse_date",
    "parse_dt",
    "iso_date",
    "iso_dt",
    "as_date",
]

# 날짜만 필요한 자리에서 타임스탬프가 들어오는 일이 흔하다(Notion 의 date 속성은
# 시각을 포함할 수 있다). 앞 10자가 달력일이다.
_DATE_LEN = 10


def parse_date(value) -> date | None:
    """바깥 값 → 달력일. 못 읽으면 `None`.

    **예외를 안 던진다.** 이 함수를 부르는 자리 대부분은 동기화 루프 안이고, 거기서
    예외가 나면 미러 한 회차가 통째로 멈춘다 — 값 하나 때문에. 검사가 필요한 자리
    (API 요청)는 `app/tickets/schemas.py` 가 이미 422 로 거절한다.

    `datetime` 을 주면 그 날짜를 낸다 — 시간대 변환을 **하지 않는다**. 달력일은 시각이
    아니라서, 옮기면 자정 근처가 하루 밀린다.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:_DATE_LEN])
    except ValueError:
        return None


def parse_dt(value) -> datetime | None:
    """바깥 값 → **naive UTC** 타임스탬프. 못 읽으면 `None`.

    `2026-08-22T10:00:00.000Z` 처럼 `Z` 로 끝나는 값을 받는다 — `fromisoformat` 은
    파이썬 3.11 부터 `Z` 를 읽지만, 그 이전 형식과 섞여 들어오므로 여기서 한 번 더
    정규화한다. 오프셋이 있으면 UTC 로 옮기고 tzinfo 를 뗀다.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return _to_naive_utc(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return _to_naive_utc(datetime.fromisoformat(text))
    except ValueError:
        # 날짜만 온 경우도 받는다 — 소스가 date 속성을 timestamp 자리에 넣는 일이 있다.
        parsed = parse_date(text)
        return datetime(parsed.year, parsed.month, parsed.day) if parsed else None


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def iso_date(value) -> str | None:
    """안쪽 값 → 'YYYY-MM-DD'. 화면과 외부 소스가 읽는 형태다.

    ⚠️ **API 응답에는 대개 필요 없다.** FastAPI 가 `date` 를 그대로 'YYYY-MM-DD' 로
    직렬화하므로, 응답을 만들려고 이 함수를 부르면 같은 일을 두 번 하는 것이다.
    이 함수가 필요한 자리는 **외부 소스에 보낼 때**(Notion 속성값)와 문자열 비교가
    남아 있는 자리다.
    """
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def iso_dt(value) -> str | None:
    """안쪽 값 → ISO 8601 문자열(UTC, `Z` 없이)."""
    parsed = parse_dt(value)
    return parsed.isoformat() if parsed else None


def as_date(value, *, fallback: date | None = None) -> date | None:
    """`parse_date` 와 같지만 못 읽으면 주어진 값으로 떨어진다.

    「없으면 오늘」 같은 자리가 여러 곳이라, 그 관용구를 한 이름으로 둔다.
    """
    parsed = parse_date(value)
    return parsed if parsed is not None else fallback
