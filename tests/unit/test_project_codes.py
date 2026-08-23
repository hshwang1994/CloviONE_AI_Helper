"""Project Code 의 규칙 (D-282).

qa-contract-replaced-by: tests/unit/test_work_keys.py
qa-contract-replaced-by: tests/unit/test_project_keys_confirmed.py

이 파일이 대체하는 두 파일은 **앞 정책의 시험**이었다. 하나는 사람이 치는 Key 의 모양과
초안 만들기(초성 로마자화)를 못박았고, 다른 하나는 사람이 확정한 20건 표가 문서와 코드에서
같은지를 봤다. 서버가 코드를 짓는 지금 그 둘은 대상이 없다 — 치는 사람이 없고 표가 없다.

대신 여기서 못박는 것은 셋이다: **모양** · **결정성** · **분포**.

셋 중 마지막이 이 파일에 있는 이유를 적어 둔다. 언제나 `"AAAAAA"` 를 돌려주는 생성기는
모양 검사도 결정성 검사도 전부 통과한다. 그 생성기가 실제로 하는 일은 두 번째 프로젝트부터
유니크 제약에 걸려 32번 다시 짓고 실패하는 것이고, 그 사실은 **두 번째 프로젝트를 만드는
사람**이 처음 본다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.work import codes

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── 모양 ─────────────────────────────────────────────────────────────────────


def test_the_alphabet_is_exactly_the_policy():
    """스물셋 — `I`·`L`·`O` 만 빠졌다.

    문자열 비교로 고정하는 이유: 글자 하나가 늘거나 순서가 바뀌면 **같은 씨앗이 다른
    코드**를 낸다. 그 순간 이미 발급된 코드와 새로 짓는 코드가 다른 규칙에서 나온다.
    """
    assert codes.CODE_ALPHABET == "ABCDEFGHJKMNPQRSTUVWXYZ"
    assert len(codes.CODE_ALPHABET) == 23
    assert set("ILO").isdisjoint(codes.CODE_ALPHABET)
    assert codes.CODE_LENGTH == 6


def test_generated_codes_all_match_the_shape():
    """표본을 크게 잡고 **표본 수를 함께 단언한다.**

    「하나도 안 틀렸다」는 0건을 검사해도 참이다. 몇 개를 봤는지 같이 못박아야 이 시험이
    실제로 무언가를 본 것이 된다.
    """
    shape = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ]{6}$")
    sample = [codes.derive(f"seed-{n}") for n in range(500)]
    assert len(sample) == 500
    assert all(shape.match(code) for code in sample)
    assert not any(ch in "ILO" for code in sample for ch in code)


def test_is_valid_refuses_what_the_generator_cannot_make():
    """모양 판정은 **양쪽으로** 움직여야 한다."""
    assert codes.is_valid("ABCDEF")
    assert not codes.is_valid(None)
    assert not codes.is_valid("")
    assert not codes.is_valid("ABCDE")       # 다섯 글자
    assert not codes.is_valid("ABCDEFG")     # 일곱 글자
    assert not codes.is_valid("ABCDE1")      # 숫자
    assert not codes.is_valid("ABCDEI")      # 뺀 글자
    assert not codes.is_valid("ABCDEL")
    assert not codes.is_valid("ABCDEO")
    assert not codes.is_valid("abcdef")      # 소문자를 고쳐서 받지 않는다
    assert not codes.is_valid("SKH")         # 옛 정책의 Key


def test_the_db_check_and_the_alphabet_are_the_same_string():
    """`0012` 의 정규식과 이 모듈의 상수가 갈리면 **앱이 만든 코드를 DB 가 거절한다.**

    두 곳에 적은 이유는 앱을 안 거치는 쓰기(이관·수동 SQL·되감기)가 실제로 있기 때문이고,
    두 곳에 적었으면 둘이 같은지 기계가 봐야 한다.
    """
    text = (ROOT / "alembic/versions/0012_project_code_policy.py").read_text(
        encoding="utf-8"
    )
    expected = f"^[{codes.CODE_ALPHABET}]{{{codes.CODE_LENGTH}}}$"
    assert f'_CODE_SHAPE = "{expected}"' in text


# ── 결정성 ───────────────────────────────────────────────────────────────────


def test_the_same_seed_always_gives_the_same_code():
    """Dry Run 과 Cutover 가 같은 코드를 내는 근거 전부가 이 한 줄이다."""
    assert codes.derive("page-1") == codes.derive("page-1")
    assert codes.derive("page-1", 3) == codes.derive("page-1", 3)


def test_a_different_seed_gives_a_different_code():
    assert codes.derive("page-1") != codes.derive("page-2")


def test_a_later_attempt_gives_a_different_candidate():
    """충돌은 **회차 번호**로 푼다 — 다시 뽑지 않는다.

    다시 뽑으면 그 프로젝트의 코드가 회차마다 달라지고, 그것이 이 정책이 막으려는 상태다.
    """
    candidates = [codes.derive("page-1", n) for n in range(8)]
    assert len(set(candidates)) == 8


def test_the_generator_is_not_degenerate():
    """서로 다른 씨앗 1,000개가 서로 다른 코드를 낸다.

    23⁶ = 148,035,889 중 1,000개를 뽑으면 겹칠 확률이 0.3% 남짓이라 **씨앗을 고정해**
    이 시험이 어쩌다 빨개지지 않게 한다. 보는 것은 무작위성이 아니라 「상수를 돌려주지
    않는다」이다.
    """
    sample = {codes.derive(f"stable-seed-{n}") for n in range(1000)}
    assert len(sample) == 1000


def test_first_letters_are_spread_over_the_alphabet():
    """첫 글자가 한두 개에 몰리면 그 자리가 사실상 안 쓰이는 것이다."""
    heads = {codes.derive(f"spread-{n}")[0] for n in range(400)}
    assert len(heads) >= 20
