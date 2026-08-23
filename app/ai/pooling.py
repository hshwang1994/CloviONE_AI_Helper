"""토큰 벡터 → 문장 벡터. **mean pooling + L2 정규화** (D-211).

## 왜 이 열 몇 줄을 따로 두는가

여기가 틀리면 **오류가 한 번도 안 난다.** 벡터는 만들어지고, 차원도 맞고, 저장도 되고,
검색도 돈다 — 답만 이상하다. 그런 결함은 「검색이 좀 별로네」로만 보이고 아무도 여기를
안 본다. 그래서 모델 실행(ONNX)과 떼어 놓고, 순수 함수로 두고, 시험이 반례로 못박는다.

## 왜 두 갈래인가

운영에서는 ONNX Runtime 이 numpy 배열을 돌려주고, 배치 하나가 32×512×384 실수다.
그것을 파이썬 리스트로 도는 것은 초 단위로 느리다. 반대로 numpy 는 임베딩 런타임을
깐 설치에만 있다(`requirements-ai.txt` · Stage 12) — 그것을 안 깐 개발 머신과 시험에서
이 함수가 **한 번도 안 돌면** 위 문단의 결함을 잡을 자리가 없어진다.

그래서 같은 답을 내는 두 갈래를 두고, numpy 가 있는 곳에서는 시험이 **둘을 서로
대조한다**. 느린 쪽이 빠른 쪽의 반례다.
"""

from __future__ import annotations

import math


def mean_pool_l2(hidden, mask) -> tuple[tuple[float, ...], ...]:
    """`hidden[batch][token][dim]` 과 `mask[batch][token]` → 정규화된 문장 벡터.

    마스크가 0 인 토큰(패딩)은 평균에서 빠진다. 안 빼면 짧은 글일수록 벡터가 패딩
    쪽으로 끌려가고, 그 편향은 길이가 다른 글끼리 비교할 때만 드러난다.
    """
    if _is_ndarray(hidden):
        return _numpy_path(hidden, mask)
    return _python_path(hidden, mask)


def l2_normalize(vector) -> tuple[float, ...]:
    """길이 1 로 만든다. 길이가 0 이면 **그대로 둔다** — 0 으로 나누지 않는다.

    0 벡터를 돌려주는 것은 정직하다. `vector_cosine_ops` 는 0 벡터와의 거리를 정의하지
    않으므로, 부르는 쪽이 그것을 저장하지 않고 실패로 다룰 수 있다.
    """
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    if norm <= 0.0:
        return tuple(values)
    return tuple(v / norm for v in values)


def is_unit_length(vector, *, tolerance: float = 1e-3) -> bool:
    """정규화가 됐는가. 시험과 `ai_cli` 자기검증이 쓴다."""
    norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    return abs(norm - 1.0) <= tolerance


# ── 두 갈래 ──────────────────────────────────────────────────────────────────


def _is_ndarray(value) -> bool:
    # numpy 를 import 하지 않고 판별한다. 여기서 import 하면 numpy 가 없는 설치에서
    # 이 모듈 자체를 못 읽는다.
    return hasattr(value, "shape") and hasattr(value, "dtype") and hasattr(value, "sum")


def _numpy_path(hidden, mask):
    import numpy as np

    array = np.asarray(hidden, dtype=np.float32)
    weights = np.asarray(mask, dtype=np.float32)[..., None]
    counts = weights.sum(axis=1)
    # 0 으로 나누지 않는다. 마스크가 전부 0 인 줄은 0 벡터가 되고, 부르는 쪽이 그것을
    # 실패로 다룬다.
    counts = np.maximum(counts, 1e-9)
    pooled = (array * weights).sum(axis=1) / counts
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    norms = np.where(norms <= 0.0, 1.0, norms)
    normalized = pooled / norms
    return tuple(tuple(float(v) for v in row) for row in normalized)


def _python_path(hidden, mask):
    out: list[tuple[float, ...]] = []
    for row, row_mask in zip(hidden, mask):
        total: list[float] = []
        count = 0.0
        for token, flag in zip(row, row_mask):
            weight = float(flag)
            if weight == 0.0:
                continue
            count += weight
            if not total:
                total = [0.0] * len(token)
            for i, value in enumerate(token):
                total[i] += float(value) * weight
        if not total or count <= 0.0:
            width = len(row[0]) if row else 0
            out.append(tuple([0.0] * width))
            continue
        out.append(l2_normalize([v / count for v in total]))
    return tuple(out)
