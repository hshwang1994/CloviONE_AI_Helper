"""사람이 쓴 질문 → 찾을 낱말 (D-536).

AI 에게는 문장을 쓴다. 검색창 규칙(접은 질의 한 덩이 · 3자 이상 낱말의 AND)으로는 「연차 신청은 어떻게 하나요?」가 0건이다.
`search_text.keywords()` 는 조사 · 어미 · 부탁 말 · 잇는 말을 걷고 2자 이상 낱말을 순서대로 남긴다. 여기서 지키는 것:

* 좋은 경우 — 사용자가 든 질문들이 찾을 낱말만 남긴다.
* 뜻을 바꾸지 않는다 — 조사는 남는 어간이 2자 이상일 때만 걷는다(「회의」 · 「휴가」가 「회」 · 「휴」가 되지 않는다).
* 질의 문법이 들어갈 수 없다 — 낱말은 `[0-9a-z가-힣]` 뿐이다(FTS 의 `& | ! : * ( )`, LIKE 의 `% _ \\`).
* 상한 — 여덟 개(D-568), 중복 없음, 표시형과 달리 질문 원문은 100자로 자르지 않는다.
* 라틴 · 한글이 붙은 낱말은 통째 낱말 뒤에 조각을 함께 낸다(「sk하이닉스」 → 「하이닉스」 · 「sk」, D-568). 조각도 불용어를 지난다.
"""
import re

import pytest

from app.core.search_text import (
    MAX_KEYWORDS,
    MAX_QUERY_CHARS,
    MAX_QUESTION_CHARS,
    keywords,
    normalize_query,
    normalize_question,
)


@pytest.mark.parametrize("question,expected", [
    ("인프라 정비 관련 문서 찾아줘", ("인프라", "정비")),
    ("연차 신청은 어떻게 하나요?", ("연차", "신청")),
    ("휴가 신청 방법을 사내 문서에서 찾아 줘", ("휴가", "신청")),
    ("프로젝트의 진행 상황을 알려줘", ("프로젝트", "진행", "상황")),
    ("내가 결재할 거 있어?", ("결재",)),
    ("변경된 정책 내용", ("변경", "정책")),
    ("SLA가 뭐야?", ("sla",)),
    ("ＣＬＯＶＩＲＯＮＥ 휴가가", ("clovirone", "휴가")),
    ("플랫폼개발팀에 누가 있어?", ("플랫폼개발팀",)),
    ("신청하나요 신청 신청은", ("신청",)),
])
def test_questions_keep_only_the_words_worth_searching(question, expected):
    assert keywords(question) == expected


@pytest.mark.parametrize("word", ["회의", "휴가", "평가", "온도", "도로", "확인", "승인", "개인"])
def test_a_one_letter_stem_keeps_the_original_word(word):
    """조사처럼 보이는 끝 글자를 걷으면 한 글자만 남는 낱말은 그대로 둔다 — 뜻을 바꾸지 않는다."""
    assert keywords(word) == (word,)


@pytest.mark.parametrize("question", ["", "   ", "​", "가 나 다", "좀 혹시 관련 문서", "찾아줘 알려줘 하나요"])
def test_nothing_worth_searching_is_an_empty_tuple(question):
    assert keywords(question) == ()


def test_query_syntax_cannot_ride_along():
    """FTS 질의 문법과 LIKE 메타문자는 낱말이 될 수 없다 — 낱말은 `[0-9a-z가-힣]` 뿐이다."""
    hostile = "a & b | !c :* (x) 'y' % _ \\ z 문서:* 보안&정책 100%확인 연차_신청"
    words = keywords(hostile)
    assert all(re.fullmatch(r"[0-9a-z가-힣]+", w) for w in words), words
    assert words == ("보안", "정책", "100", "확인", "연차", "신청")


def test_at_most_eight_words_in_order_without_duplicates():
    words = keywords("가나다 라마바 사아자 차카타 파하타 나다라 마바사 가나다 아자차 하하하 호호호")
    assert MAX_KEYWORDS == 8
    assert len(words) == MAX_KEYWORDS
    assert words == ("가나다", "라마바", "사아자", "차카타", "파하타", "나다라", "마바사", "아자차")


@pytest.mark.parametrize("question,expected", [
    ("SK하이닉스 프로젝트 진행된 작업", ("sk하이닉스", "하이닉스", "sk", "프로젝트", "진행", "작업")),
    ("sk하이닉스의 k8s 클러스터", ("sk하이닉스", "하이닉스", "sk", "k8s", "클러스터")),
    ("2031년 우주 출장 규정", ("2031년", "2031", "우주", "출장", "규정")),
    # 조각이 불용어(「관련」)면 그 조각은 버린다 — 통째 낱말은 남는다.
    ("vm관련 자료", ("vm관련", "vm")),
    # 한 글자 조각은 버린다(전 행에 걸린다).
    ("a팀 회의", ("a팀", "회의")),
    # 라틴과 숫자만이면 혼합이 아니다 — 나누지 않는다.
    ("k8s vsphere8", ("k8s", "vsphere8")),
])
def test_mixed_latin_and_hangul_words_also_yield_their_parts(question, expected):
    assert keywords(question) == expected


def test_parts_count_toward_the_limit_and_can_be_turned_off():
    assert keywords("SK하이닉스 프로젝트", split_mixed=False) == ("sk하이닉스", "프로젝트")
    many = keywords("ab가나 cd다라 ef마바 gh사아")
    assert len(many) == MAX_KEYWORDS and many[:3] == ("ab가나", "가나", "ab")
    assert keywords("SK하이닉스 프로젝트", limit=2) == ("sk하이닉스", "하이닉스")


def test_the_question_for_the_model_is_not_cut_at_the_display_limit():
    """표시형은 100자에서 잘리고, 모델에 가는 질문은 원문 그대로다 — 뒤쪽 조건을 잃지 않는다."""
    long = "보안 정책 " * 30 + "마지막 조건은 이번 분기입니다"
    assert len(normalize_query(long)) == MAX_QUERY_CHARS
    question = normalize_question(long)
    assert question.endswith("마지막 조건은 이번 분기입니다")
    assert len(normalize_question("가" * (MAX_QUESTION_CHARS + 50))) == MAX_QUESTION_CHARS
    assert normalize_question("  여러   칸의\n공백  ") == "여러 칸의 공백"
