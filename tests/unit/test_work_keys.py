"""Project Key 의 규칙 (§5.2 · D-196 · D-197).

되돌릴 수 없는 이름이라 **모양을 받는 자리에서 막는다.** 잘못 지은 Key 는 `retired` 로
물러날 뿐 사라지지 않고, 그동안 발급된 `<KEY>-<SEQ>` 도 남는다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.work import keys

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("raw", ["SKH", "A1", "abc", " skh ", "PROJECT01", "X9"])
def test_valid_keys_are_normalized_upward(raw):
    """대소문자 무관 유일이므로 **위로 맞춘다.** 안 맞추면 `skh` 와 `SKH` 가 두 Key 가 된다."""
    assert keys.validate(raw) == raw.strip().upper()


@pytest.mark.parametrize(
    "raw,because",
    [
        ("", "빈 값"),
        (None, "없음"),
        ("A", "한 글자 — 최소 2자"),
        ("ABCDEFGHIJK", "열한 글자 — 최대 10자"),
        ("1AB", "숫자로 시작"),
        ("A-B", "하이픈 — `<KEY>-<SEQ>` 의 구분자와 부딪힌다"),
        ("A_B", "밑줄"),
        ("에이비", "한글 — URL 안전이 아니다"),
        ("A B", "공백"),
    ],
)
def test_bad_shapes_are_refused(raw, because):
    with pytest.raises(ValidationAppError):
        keys.validate(raw)


def test_the_error_says_which_rule_was_broken():
    """"형식이 올바르지 않습니다" 하나로 뭉치면 사람이 시행착오를 한다.

    이 값을 치는 사람은 규칙을 외우고 있지 않다 — 길이가 문제인지 첫 글자가 문제인지
    말해 줘야 다음 시도가 맞는다.
    """
    with pytest.raises(ValidationAppError) as long_key:
        keys.validate("ABCDEFGHIJK")
    assert "10" in str(long_key.value)

    with pytest.raises(ValidationAppError) as digit_first:
        keys.validate("1AB")
    assert "영문" in str(digit_first.value)


def test_hyphen_is_refused_because_it_is_the_key_separator():
    """`A-B` 를 허용하면 `A-B-7` 이 만들어지고, 그것을 `A` 의 7번인지 `A-B` 의 7번인지
    갈라 읽을 방법이 없다. Resolution 순서로도 못 푼다."""
    with pytest.raises(ValidationAppError):
        keys.validate("A-B")


# ── 초안 만들기 ──────────────────────────────────────────────────────────────


def test_chosung_table_has_exactly_nineteen_entries():
    """한글 초성은 **19개**다.

    한 글자라도 어긋나면 그 뒤 초성이 전부 한 칸씩 밀린다. 결과는 오류가 아니라
    **그럴듯한 다른 문자열**이라 눈으로는 안 잡힌다 — 실제로 처음 작성했을 때
    20자였고, 「브로드컴」이 `MTNC` 로 나왔다.
    """
    assert len(keys._CHOSUNG) == 19


@pytest.mark.parametrize(
    "name,expected",
    [
        ("브로드컴", "BRDK"),      # ㅂ ㄹ ㄷ ㅋ
        ("현대모비스", "HDMB"),    # ㅎ ㄷ ㅁ ㅂ
        ("포스코DX", "PSKD"),      # ㅍ ㅅ ㅋ + D
    ],
)
def test_initials_map_to_the_right_letters(name, expected):
    """초성 표가 밀리지 않았는지 **실제 이름으로** 고정한다."""
    assert keys.suggest(name) == expected


def test_suggest_strips_the_prefix_and_the_bracketed_work():
    """실측한 이름은 전부 `M. 고객사 [일감]` 모양이다.

    구분자를 안 떼면 초안 Key 가 전부 `P`·`M`·`D` 로 시작하고, 대괄호 안을 안 떼면
    일감이 이름을 밀어낸다.
    """
    assert keys.suggest("M. 브로드컴 [VCF9 Value Pack 제작]") == "BRDK"


def test_suggest_avoids_names_already_taken():
    """이미 쓰인 후보면 숫자를 붙인다 — **그 숫자까지 사람이 보고 고치라는 뜻**이다."""
    first = keys.suggest("브로드컴")
    second = keys.suggest("브로드컴", taken={first})
    assert second != first and second.startswith(first[:-1] or first)


def test_suggest_never_proposes_a_reserved_key():
    """`GIT` 을 제안하면 사람이 그대로 확정할 수 있고, 그러면 옛 링크가 갈린다."""
    for _ in range(3):
        assert keys.suggest("깃 프로젝트") not in keys.RESERVED_KEYS


def test_suggest_always_returns_something_usable():
    """이름이 비었거나 뽑을 글자가 없어도 **모양이 맞는 값**을 준다.

    빈 문자열을 돌려주면 화면이 빈 칸을 초안이라고 보여 주고, 사람은 그것을 그대로 저장한다.
    """
    for name in ("", "   ", "!!!", "[]", "M. [일감만 있다]"):
        assert keys.KEY_RE.match(keys.suggest(name)), f"«{name}» 의 초안이 규칙을 어긴다"
