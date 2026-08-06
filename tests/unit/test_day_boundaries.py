"""M4 — KST 달력일과 UTC 타임스탬프를 **섞어 비교하지 않는다**. 경계 양쪽을 본다.

## 왜 이 파일이 따로 있는가

"오늘 완료" 나 "이번 주" 를 UTC 자정으로 자르면 한국 사용자에게 **9시간 밀린다**. KST 는
UTC+9 라서 월요일 오전 9시 이전에 한 일은 UTC 로는 아직 일요일이고, 그래서 월요일 아침에
한 일이 통째로 지난 주로 새어 나간다. 화면에는 그럴듯한 숫자가 떠 있으니 아무도 신고하지
않고, 그 상태로 몇 달이 간다.

이미 이 저장소에 그 상태인 코드가 있었다: `app/home/readers.py::documents_changed_since` 는
'YYYY-MM-DD' 라는 KST 달력일을 Notion 이 준 UTC 문자열과 그대로 비교했다
(`app/projects/weekly.py` 와 `app/projects/service.py` 의 주석이 M4 라고 이름 붙여 둔 결함).

## 한쪽만 보면 반쪽만 고치고 통과한다

주간 리포트 작업에서 실제로 그랬다. 그래서 이 파일의 모든 창 테스트는 **양쪽 끝**을 본다.

  * 아래쪽: KST 월요일 오전(= UTC 로는 일요일 저녁) 표본이 **들어와야** 한다.
  * 위쪽:   다음 주 월요일 오전 표본이 **끼면 안 된다**.

그리고 표본은 **값이 실제로 달라지는 것**을 쓴다. 잘못된 비교(KST 달력일 문자열)로 바꾸면
아래쪽 표본이 사라지는 것을 같은 테스트가 함께 못 박는다 — 그렇게 하지 않으면 함수는
옳은데 표본이 무해해서 통과하는 '헛것 테스트' 가 된다.

## 새 시간 유틸을 만들지 않는다

주 경계는 `app/projects/weekly.py::week_for`(= `app/sprints/service.py::default_sprint_window`),
KST→UTC 변환은 `app/home/service.py::window_utc_bounds` 다. 이 파일은 그 둘을 쓰는 쪽만
확인한다. 세 번째 벌을 만들면 갈라진 쪽이 조용히 틀린다.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.home.service import local_today, utc_iso_bounds, window_utc_bounds
from app.home.work import recent_week_windows
from app.projects.weekly import week_for
from app.sprints.service import default_sprint_window

pytestmark = pytest.mark.unit

# 클록은 naive UTC 를 준다(저장소 규약). 설정은 timezone 하나만 읽힌다.
SETTINGS = SimpleNamespace(timezone="Asia/Seoul")

# 2026-08-03 은 월요일이다. UTC 2026-08-02 23:00 = KST 2026-08-03(월) 08:00 —
# **날짜가 실제로 갈리는 순간**이다(UTC 로는 아직 일요일).
MONDAY_MORNING_UTC = datetime(2026, 8, 2, 23, 0, 0)
MONDAY_KST = date(2026, 8, 3)

WEEK_START = "2026-08-03"
WEEK_END = "2026-08-10"


def test_local_today_reads_the_kst_calendar_day_not_the_utc_one():
    """표본이 실제로 갈리는지 먼저 못 박는다 — 안 갈리면 아래 테스트가 전부 헛것이다."""
    assert MONDAY_MORNING_UTC.date() == date(2026, 8, 2), "표본이 UTC 로는 일요일이어야 한다"
    assert local_today(SETTINGS, MONDAY_MORNING_UTC) == MONDAY_KST


def test_kst_day_flips_at_utc_15_00_on_both_sides():
    """하루 경계 양쪽. 14:59 는 아직 오늘이고 15:00 부터 내일이다."""
    assert local_today(SETTINGS, datetime(2026, 8, 3, 14, 59, 59)) == date(2026, 8, 3)
    assert local_today(SETTINGS, datetime(2026, 8, 3, 15, 0, 0)) == date(2026, 8, 4)


def test_week_for_the_monday_morning_is_this_week_not_last_week():
    """월요일 오전 KST 에 여는 사람이 **지난 주**를 보면 안 된다.

    UTC 날짜(2026-08-02, 일요일)로 주를 정하면 창이 [07-27, 08-03) 이 된다 — 한 주가
    통째로 밀린다. 두 값을 나란히 확인해 그 차이를 눈에 보이게 남긴다.
    """
    kst_week = week_for(local_today(SETTINGS, MONDAY_MORNING_UTC))
    utc_week = week_for(MONDAY_MORNING_UTC.date())
    assert kst_week.start == WEEK_START and kst_week.end_exclusive == WEEK_END
    assert utc_week.start == "2026-07-27", "표본이 두 판정을 갈라야 의미가 있다"


def test_recent_week_windows_are_kst_weeks_and_match_the_sprint_window():
    """최근 완료 추이가 쓰는 주 목록. 주 경계를 새로 만들지 않았는지 **직접 맞대어** 본다."""
    windows = recent_week_windows(MONDAY_KST, count=4)
    assert [w.start for w in windows] == [
        "2026-07-13", "2026-07-20", "2026-07-27", "2026-08-03",
    ], "과거에서 현재 순, 오늘이 속한 주가 마지막"
    # 스프린트 화면과 다른 주를 '이번 주'라고 부르면 사용자는 둘 중 하나를 거짓말로 받아들인다.
    last = windows[-1]
    assert (last.start, last.end_exclusive) == default_sprint_window(MONDAY_KST)


def test_recent_week_windows_follow_the_kst_day_across_the_boundary():
    """일요일(KST)에 열면 마지막 창이 그 주여야 한다 — 표본이 실제로 달라지는 쌍이다."""
    sunday = recent_week_windows(date(2026, 8, 2), count=2)[-1]
    monday = recent_week_windows(date(2026, 8, 3), count=2)[-1]
    assert sunday.start == "2026-07-27"
    assert monday.start == "2026-08-03"


def test_week_utc_bounds_span_kst_midnight_not_utc_midnight():
    since, until = window_utc_bounds(SETTINGS, WEEK_START, WEEK_END)
    assert since == datetime(2026, 8, 2, 15, 0, 0)
    assert until == datetime(2026, 8, 9, 15, 0, 0)


# Notion 이 주는 last_edited 원문 형식('...Z'). 컬럼이 String 이라 문자열로 비교된다.
DOC_MONDAY_06_KST = "2026-08-02T21:00:00.000Z"      # KST 2026-08-03(월) 06:00 — 창 안
DOC_NEXT_MONDAY_06_KST = "2026-08-09T21:00:00.000Z"  # KST 2026-08-10(월) 06:00 — 창 밖
DOC_SUNDAY_23_KST = "2026-08-02T14:59:59.000Z"       # KST 2026-08-02(일) 23:59 — 창 밖


def test_utc_iso_bounds_include_monday_morning_kst_and_exclude_next_week():
    """M4 의 본론. **양쪽 끝**을 1분 차이 표본으로 못 박는다."""
    since_iso, until_iso = utc_iso_bounds(SETTINGS, WEEK_START, WEEK_END)
    assert (since_iso, until_iso) == ("2026-08-02T15:00:00", "2026-08-09T15:00:00")

    # 아래쪽: 월요일 오전 KST 것이 들어온다.
    assert since_iso <= DOC_MONDAY_06_KST < until_iso
    # 위쪽: 다음 주 것은 안 낀다.
    assert not (since_iso <= DOC_NEXT_MONDAY_06_KST < until_iso)
    # 시작 직전(일요일 밤 KST)도 안 낀다 — 창이 통째로 밀리지 않았는지 확인한다.
    assert not (since_iso <= DOC_SUNDAY_23_KST < until_iso)


def test_the_broken_kst_string_comparison_would_drop_monday_morning():
    """고친 것이 진짜 결함인지 표본으로 남긴다(M4 의 재현 조건).

    예전 코드는 `last_edited >= '2026-08-03'` 이었다. 그 비교에서는 월요일 오전 KST 것이
    사라진다 — 표본이 무해했다면 이 파일 전체가 아무것도 증명하지 못한다.
    """
    assert DOC_MONDAY_06_KST < WEEK_START, "표본이 잘못된 비교에서 실제로 탈락해야 한다"
    assert DOC_NEXT_MONDAY_06_KST >= WEEK_START, "예전 코드에는 위쪽 경계가 아예 없었다"
