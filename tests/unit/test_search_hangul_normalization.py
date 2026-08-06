"""한글 표기(NFC/NFD) 통일 (Z4).

## 눈에 보이지 않는 결함

`한` 은 두 가지로 쓸 수 있다.
  · NFC: 코드포인트 1개 (`\\uD55C`)                 - Windows·Notion·대부분의 웹
  · NFD: 코드포인트 3개 (`\\u1112\\u1161\\u11AB`)   - macOS 파일 이름, 거기서 복사한 글

**화면에서는 완전히 똑같이 보인다.** 그런데 trigram 은 코드포인트를 훑으므로, 색인이 NFC 인데
질의가 NFD 면 **영원히 0건**이다. 오타도 오류도 아니라 사용자는 "검색이 안 된다" 고만 느끼고,
로그에는 아무 흔적도 없다. 이런 결함은 스스로 드러나지 않으므로 테스트로 고정해야 한다.

색인과 질의 **양쪽**을 같은 방향으로 정규화한다. 한쪽만 하면 고친 것이 아니라 어긋나는
방향만 바뀐다.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.search import query as q
from app.search.indexer import _clip

pytestmark = pytest.mark.unit

NFC = "회의록"
NFD = unicodedata.normalize("NFD", NFC)


def test_the_two_spellings_really_are_different_bytes():
    """오탐 방지 - 둘이 애초에 같으면 이 파일 전체가 아무것도 증명하지 않는다."""
    assert NFC != NFD, "표본이 잘못됐다 - 두 표기가 같다"
    assert len(NFD) > len(NFC), f"NFD 가 더 길어야 한다: {len(NFC)} vs {len(NFD)}"


def test_a_query_typed_on_a_mac_becomes_the_same_text():
    assert q.normalize(NFD) == NFC


def test_indexed_text_becomes_the_same_text():
    assert _clip(NFD) == NFC


def test_both_sides_meet_in_the_middle():
    """🔴 핵심 - 색인과 질의가 **같은 값**이 되어야 검색이 걸린다."""
    assert _clip(NFD) == q.normalize(NFC)
    assert _clip(NFC) == q.normalize(NFD)


def test_a_two_letter_query_is_still_judged_as_two_letters():
    """🔴 정규화를 **세기 전에** 해야 한다.

    NFD 로 온 `회의` 는 코드포인트로 넷이다. 정규화 전에 세면 3자 이상으로 보여 FTS 로 가고,
    trigram 은 2글자에 걸릴 것이 없으므로 **조용히 0건**이 된다. 지금 고치려는 그 증상이다.
    """
    two = unicodedata.normalize("NFD", "회의")
    assert len(two) > 2, f"표본이 잘못됐다 - NFD 인데 짧다: {len(two)}"
    assert q.mode_for(q.normalize(two)) == q.MODE_LIKE


def test_normalization_happens_before_clipping(monkeypatch):
    """자른 뒤에 정규화하면 마지막 글자가 자모로 쪼개진 채 남을 수 있다."""
    long_nfd = unicodedata.normalize("NFD", "회의록" * 500)
    got = _clip(long_nfd, 10)
    assert got == "회의록회의록회의록회", f"잘린 결과가 이상하다: {got!r}"
    assert unicodedata.is_normalized("NFC", got), "자른 결과가 NFC 가 아니다"


def test_plain_ascii_is_untouched():
    """오탐 방지 - 정규화가 영문·숫자를 건드리면 안 된다."""
    assert q.normalize("  Sprint   42 ") == "Sprint 42"
    assert _clip("Sprint 42") == "Sprint 42"
