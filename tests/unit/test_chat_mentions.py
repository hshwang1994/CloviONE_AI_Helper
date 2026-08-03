"""@멘션 파싱 규칙 (app/team_chat/mentions.py).

프런트(frontend/src/screens/chat-text.js)가 **같은 규칙으로 같은 자리에 밑줄을 긋는다.**
여기서 고정하는 네 가지가 그 계약이다: 경계(이메일 제외) · 최장 일치 · 정확 일치 · 중복 제거.
"""

from __future__ import annotations

import pytest

from app.team_chat.mentions import find_mentioned, mention_preview

pytestmark = pytest.mark.unit

NAMES = {"홍길동": "u-hong", "김철": "u-cheol", "김철수": "u-cheolsu", "Ann": "u-ann"}


def test_plain_mention_matches_a_member():
    assert find_mentioned("@홍길동 확인 부탁드립니다", NAMES) == ["u-hong"]


def test_mention_in_the_middle_of_a_sentence():
    assert find_mentioned("이건 @홍길동 님이 맡기로 했어요", NAMES) == ["u-hong"]


def test_longest_name_wins():
    """'김철'과 '김철수'가 함께 있을 때 짧은 쪽이 이기면 **엉뚱한 사람**에게 알림이 간다."""
    assert find_mentioned("@김철수 봐주세요", NAMES) == ["u-cheolsu"]
    assert find_mentioned("@김철 봐주세요", NAMES) == ["u-cheol"]


def test_email_is_not_a_mention():
    """'@' 앞이 영숫자면 멘션이 아니다 — 이메일 한 줄이 알림을 만들면 안 된다."""
    assert find_mentioned("문의는 Ann@goodmit.co.kr 로 주세요", {"goodmit": "u-x", **NAMES}) == []


def test_unknown_name_notifies_nobody():
    """부분·유사 일치를 허용하면 '없는 사람을 부른' 메시지가 엉뚱한 사람에게 간다."""
    assert find_mentioned("@홍길 확인", NAMES) == []
    assert find_mentioned("@없는사람 확인", NAMES) == []


def test_same_person_twice_is_one_notification():
    assert find_mentioned("@홍길동 @홍길동 급해요", NAMES) == ["u-hong"]


def test_multiple_people_keep_the_order_they_appear_in():
    assert find_mentioned("@김철수 와 @홍길동 함께 봐요", NAMES) == ["u-cheolsu", "u-hong"]


def test_no_at_sign_short_circuits():
    assert find_mentioned("멘션 없는 평범한 메시지", NAMES) == []
    assert find_mentioned("", NAMES) == []
    assert find_mentioned(None, NAMES) == []
    assert find_mentioned("@홍길동", {}) == []


def test_bare_at_signs_do_not_crash_or_match():
    assert find_mentioned("@@@ @ @", NAMES) == []


def test_preview_collapses_newlines_and_truncates():
    assert mention_preview("첫 줄\n둘째 줄") == "첫 줄 둘째 줄"
    long = "가" * 200
    out = mention_preview(long, limit=20)
    assert len(out) == 20 and out.endswith("…")
