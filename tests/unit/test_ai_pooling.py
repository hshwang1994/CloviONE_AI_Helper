"""토큰 벡터 → 문장 벡터. **여기가 틀리면 오류가 한 번도 안 난다** (S9 · D-211).

벡터는 만들어지고, 차원도 맞고, 저장도 되고, 검색도 돈다 — 답만 이상하다. 그래서
반례로 못박는다: 손으로 계산한 값과 비교하고, 빠른 갈래(numpy)와 느린 갈래(순수
파이썬)를 서로 대조한다. 느린 쪽이 빠른 쪽의 반례다.
"""

from __future__ import annotations

import math

import pytest

from app.ai import pooling

pytestmark = pytest.mark.unit


def test_padding_tokens_do_not_move_the_vector():
    """마스크가 0 인 토큰은 평균에서 빠진다.

    안 빼면 짧은 글일수록 벡터가 패딩 쪽으로 끌리고, 그 편향은 길이가 다른 글끼리
    비교할 때만 드러난다 — 즉 실제로 쓸 때만 드러난다.
    """
    hidden = [[[3.0, 4.0], [1000.0, -1000.0]]]
    mask = [[1, 0]]
    (vector,) = pooling.mean_pool_l2(hidden, mask)
    # (3,4) 를 정규화하면 (0.6, 0.8) 이다. 패딩이 섞였으면 이 값이 안 나온다.
    assert vector == pytest.approx((0.6, 0.8))


def test_the_mean_is_a_real_mean():
    """두 토큰의 평균이 그 둘의 가운데인가. 합만 하고 안 나누면 여기서 걸린다."""
    hidden = [[[1.0, 0.0], [0.0, 1.0]]]
    mask = [[1, 1]]
    (vector,) = pooling.mean_pool_l2(hidden, mask)
    half = 1 / math.sqrt(2)
    assert vector == pytest.approx((half, half))


def test_every_vector_has_length_one():
    """정규화가 빠지면 코사인 거리가 길이에 끌린다 — 순서만 조용히 틀어진다."""
    hidden = [
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        [[0.1, 0.0, 0.0], [0.2, 0.0, 0.0]],
    ]
    mask = [[1, 1], [1, 1]]
    for vector in pooling.mean_pool_l2(hidden, mask):
        assert pooling.is_unit_length(vector)


def test_a_zero_vector_stays_zero_instead_of_dividing_by_zero():
    """0 벡터를 돌려주는 것이 정직하다. `vector_cosine_ops` 는 0 벡터와의 거리를
    정의하지 않으므로, 부르는 쪽이 그것을 저장하지 않고 실패로 다룰 수 있다."""
    assert pooling.l2_normalize([0.0, 0.0, 0.0]) == (0.0, 0.0, 0.0)


def test_an_all_padding_row_gives_a_zero_vector():
    hidden = [[[5.0, 5.0], [5.0, 5.0]]]
    mask = [[0, 0]]
    (vector,) = pooling.mean_pool_l2(hidden, mask)
    assert vector == (0.0, 0.0)


def test_is_unit_length_says_no_when_it_is_not():
    """검사기 자신이 항상 참을 돌려주면 위 시험들이 아무것도 확인하지 않는다."""
    assert not pooling.is_unit_length([1.0, 1.0])
    assert not pooling.is_unit_length([0.0, 0.0])


def test_the_fast_path_and_the_slow_path_agree():
    """numpy 갈래와 순수 파이썬 갈래가 **같은 답**을 낸다.

    운영은 numpy 로 돌고(ONNX 출력이 numpy 배열이다) 시험 대부분은 리스트로 돈다.
    둘이 갈리면 시험이 통과하는데 운영이 틀린다 — 가장 나쁜 종류의 통과다.
    """
    numpy = pytest.importorskip("numpy", reason="임베딩 런타임을 안 깐 환경에서는 이 갈래가 없다")
    raw = [
        [[0.5, -1.5, 2.0, 0.25], [1.0, 1.0, -1.0, 0.0], [9.0, 9.0, 9.0, 9.0]],
        [[-2.0, 0.0, 0.5, 1.0], [0.0, 0.0, 0.0, 0.0], [1.0, 2.0, 3.0, 4.0]],
    ]
    mask = [[1, 1, 0], [1, 1, 1]]
    slow = pooling.mean_pool_l2(raw, mask)
    fast = pooling.mean_pool_l2(numpy.asarray(raw, dtype=numpy.float32), mask)
    assert len(fast) == len(slow)
    for a, b in zip(fast, slow):
        assert a == pytest.approx(b, abs=1e-6)


def test_the_fast_path_is_actually_taken():
    """위 시험이 두 갈래를 정말 갈랐는지 본다 — 판별이 틀리면 같은 갈래를 두 번 돈다."""
    numpy = pytest.importorskip("numpy")
    assert pooling._is_ndarray(numpy.zeros((1, 1, 2), dtype=numpy.float32))
    assert not pooling._is_ndarray([[[0.0, 0.0]]])
