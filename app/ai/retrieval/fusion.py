"""RRF — 순위 여러 개를 점수 하나로 (D-209 · D-212).

## 왜 점수가 아니라 **순위**를 합치는가

세 레인이 내는 값은 서로 비교할 수 없다. `similarity()` 는 0~1 의 트라이그램 겹침이고,
`ts_rank` 는 문서 길이로 나눈 값이라 상한이 정해져 있지 않으며, 코사인 거리는 작을수록
좋다. 셋을 정규화해서 더하려면 각 분포를 알아야 하고, 그 분포는 코퍼스가 바뀌면 바뀐다 —
**튜닝이 끝나지 않는 종류의 설계**다.

RRF 는 값 대신 **몇 등이었는가**만 본다. 분포를 몰라도 되고, 한 레인이 이상한 값을 내도
그 레인의 등수만 흔들린다. 그래서 문헌의 기본값(k=60)이 그대로 쓸 만하다.

    score(d) = Σ_lane  w_lane × 1 / (k + rank_lane(d))

`k` 가 큰 이유도 여기 있다: 1등과 2등의 차이(1/61 − 1/62 ≈ 0.00026)가 「한 레인에만
있다」와 「두 레인에 다 있다」의 차이(≈ 1/61)보다 훨씬 작다. **여러 레인이 함께 고른
것을 위로 올리는 것**이 이 융합의 요점이고, 한 레인 안의 미세한 등수 차이가 그것을
뒤집지 않는다.

## Re-rank 단계는 없다 (D-212 · D-255)

Cross-encoder 리랭커는 CPU 로 (질의, 문서) 50쌍에 **509ms~6,721ms** 다. 질의당 검색
지연에 0.5초를 더하는 선택이라 안 쓴다. `Gateway.rerank()` 는 계약에만 남아 있고
능력은 `unsupported` 다.

## 가중치는 지어낸 값이 아니다

D-209 가 초기값(`1.0 / 0.5 / 1.0`)을 주고 **S10 이 실제 relevance 로 다시 정한다**고
적었다. 그 측정은 `scripts/bench/retrieval_fusion.py` 이고 원장은
`docs/platform/EVIDENCE/S10/` 다. 아래 값의 근거는 그 실행이다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = [
    "LANE_FTS", "LANE_TRGM", "LANE_VECTOR", "LANES", "WORD_LANES",
    "RRF_K", "VECTOR_MAX_DISTANCE", "WEIGHTS",
    "Fused", "fuse", "semantic_only", "weight_of",
]

# ── 레인 이름 ────────────────────────────────────────────────────────────────
#: 트라이그램. **후보 생성의 정본**이다 — 한국어 어절 내부 부분일치를 이것만 한다.
LANE_TRGM = "trgm"
#: 전문검색(`simple`). 어절 단위로 걸고 **낱말 뭉치의 순위를 매긴다** — 사람이 기억나는
#: 대로 친 질의를 이 레인이 혼자 짊어진다(S10 실측 0.9387 대 트라이그램 0.0350).
LANE_FTS = "fts"
#: 임베딩. 글자가 안 겹쳐도 뜻이 가까운 것을 찾는다. 모델이 없으면 이 레인은 비어 있다.
LANE_VECTOR = "vector"
LANES: tuple[str, ...] = (LANE_TRGM, LANE_FTS, LANE_VECTOR)

#: 융합 상수. 문헌 기본값이고 위 docstring 이 왜 이 크기여야 하는지 적는다.
RRF_K = 60

#: 레인별 가중치. **S10 이 긴 본문으로 측정해서 다시 정한 값이다** — D-209 는 초기값
#: (`1.0 / 0.5 / 1.0`)만 주고 「최종 가중치는 S10 이 실제 relevance 로 정한다」고 적었다.
#: 원장은 `docs/platform/EVIDENCE/S10/retrieval_fusion.json` (한국어 산문 849 chunk ·
#: 중앙값 705자 · 질의 600개 · 실 모델 e5-small).
#:
#: **바뀐 것 둘과 그 이유:**
#:
#: `w_fts` **0.5 → 1.0.** D-209 는 「FTS 가 찾는 것은 pg_trgm 이 이미 전부 찾으므로 FTS 는
#: recall 에 기여할 수 없다」고 적었고, **짧은 제목 글에서는 그것이 맞았다.** 긴 본문에서는
#: 아니다: 사람이 기억나는 대로 친 질의(어절을 절반 버리고 순서를 섞은 것)에서 FTS 는
#: MRR **0.9387** 이고 트라이그램은 **0.0350** 이다. `similarity()` 는 질의를 통짜
#: 문자열로 비교해서 낱말 뭉치를 **찾을 수는 있어도 순위를 매기지 못한다.**
#:
#: `w_vector` **1.0 → 0.5.** 벡터 레인은 이 코퍼스에서 단독 MRR 0.2187 이다. 끄면(0.0)
#: 전체 MRR 0.8693, 0.5 면 **0.8869**, 1.0 이면 0.8313, 1.5 면 0.6781 로 무너진다 —
#: **거들 때는 도움이 되고 앞장서면 해가 된다.**
#:
#: 두 값을 함께 바꾼 결과: D-209 초기값 0.7553 → **0.8869** (MRR@10, +17.4%).
WEIGHTS: dict[str, float] = {
    LANE_TRGM: 1.0,
    LANE_FTS: 1.0,
    LANE_VECTOR: 0.5,
}

#: 🔴 **벡터 레인의 거리 상한.** 이 값이 없으면 벡터 레인은 「못 찾았다」를 말할 수가 없다.
#:
#: 키워드 두 레인은 안 걸리면 0건을 낸다. 벡터 레인은 다르다 — 최근접 이웃은 **언제나**
#: `limit` 건을 내놓는다. 아무 관계 없는 질의에도 상위 50건이 나오고, 그러면
#: 「근거가 없다」가 영원히 성립하지 않는다: 모델은 매번 상관없는 문서를 근거로 받고,
#: 그 답에는 인용 번호까지 붙는다. 사람은 그것을 답으로 읽는다.
#:
#: 코사인 거리다(작을수록 가깝다 — `vector_cosine_ops`). **독립된 측정 둘이 같은 자리를
#: 가리킨다:**
#:
#:   * S9 실 모델 실측 — 질의↔맞는 본문 거리 **0.1151**, 질의↔상관없는 본문 **0.1984**.
#:     그 사이를 자르는 값이다(`EVIDENCE/S9/real_embed_pipeline.json`).
#:   * S10 융합 실측 — 정답 chunk 까지의 거리 p90 이 **0.1591** 이라 0.16 이 참 이웃을
#:     대부분 남긴다. 상한 격자에서 0.14 와 0.16 이 사실상 동점이고(0.8889 대 0.8869),
#:     0.16 이 **어절 내부 질의에서 더 낫다**(0.7423 대 0.7314) — 그 질의군이 한국어에서
#:     가장 어려운 자리다(D-209).
#:
#: 🔴 **이 상한은 순위를 매기라고 있는 것이 아니다.** 주제가 비슷한 문서만 모인 코퍼스에서는
#: 정답과 오답의 거리 분포가 겹쳐서(S10 실측: 정답 p50 0.1401 · 최근접 오답 p50 0.1375)
#: 어떤 상한도 그 둘을 못 가른다. 상한이 하는 일은 **주제가 아예 다른 질의를 걸러 내
#: 「근거가 없다」를 성립시키는 것** 하나이고, 같은 주제 안의 순위는 RRF 가 맡는다.
VECTOR_MAX_DISTANCE = 0.16


def weight_of(lane: str) -> float:
    """모르는 레인은 **0 이 아니라 예외**다.

    0 으로 접으면 오타 하나가 레인 하나를 통째로 끄는데 아무 오류도 안 난다 —
    그 상태는 「검색 품질이 좀 이상하다」로만 보인다.
    """
    try:
        return WEIGHTS[lane]
    except KeyError:
        raise ValueError(f"모르는 검색 레인입니다: {lane!r}") from None


@dataclass(frozen=True)
class Fused:
    """융합 결과 한 줄. **어느 레인이 몇 등으로 골랐는지를 함께 든다.**

    점수만 돌려주면 「왜 이것이 위에 있는가」에 답할 수 없고, 답할 수 없는 순위는
    가중치를 다시 정할 때 측정할 것이 없다. 화면도 이 값으로 「의미 검색이 찾은 것」과
    「낱말이 그대로 있는 것」을 구별해 말한다.
    """

    key: str
    score: float
    #: 레인 → 그 레인에서의 등수(1부터). 그 레인이 못 찾았으면 키가 아예 없다.
    ranks: dict[str, int]

    @property
    def lanes(self) -> tuple[str, ...]:
        """이것을 고른 레인들. `LANES` 순서로 고정한다 — 화면 문구가 요청마다 안 바뀌게."""
        return tuple(lane for lane in LANES if lane in self.ranks)


def fuse(
    rankings: dict[str, Sequence[str]], *, k: int = RRF_K, limit: int | None = None
) -> list[Fused]:
    """레인 → 순위 목록  ⇒  융합 순위 하나.

    `rankings` 의 각 값은 **이미 정렬된** key 목록이다(좋은 것이 앞). 같은 key 가 한
    레인 안에서 두 번 나오면 **처음 것만** 센다 — 뒤엣것을 세면 같은 문서가 한 레인에서
    두 번 표를 던진다.

    동점은 **key 로 깬다.** 사전순에 의미는 없지만 요청마다 순서가 달라지는 것보다
    낫다 — 순서가 흔들리면 「어제와 다른 답이 나온다」의 원인을 아무도 못 찾는다.
    """
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for lane, keys in rankings.items():
        weight = weight_of(lane)
        seen: set[str] = set()
        position = 0
        for key in keys or ():
            if key in seen:
                continue
            seen.add(key)
            position += 1
            scores[key] = scores.get(key, 0.0) + weight / (k + position)
            ranks.setdefault(key, {})[lane] = position

    out = [Fused(key=key, score=score, ranks=ranks[key]) for key, score in scores.items()]
    out.sort(key=lambda row: (-row.score, row.key))
    return out if limit is None else out[:limit]


#: 낱말이 그대로 걸린 레인들. 나머지 하나(`vector`)는 뜻으로 찾는다.
WORD_LANES = frozenset({LANE_TRGM, LANE_FTS})


def semantic_only(lanes: Iterable[str]) -> bool:
    """**뜻으로만** 찾은 결과인가. 화면이 그때만 한 줄을 더 붙인다.

    레인 이름을 화면에 그대로 내보내지 않는다 — `trgm` 은 사람에게 아무 뜻이 없다.
    그리고 「낱말 검색이 찾았습니다」는 사용자가 이미 아는 사실이라 적을 값이 없다.
    적을 값이 있는 것은 **찾은 낱말이 하나도 없는데 나온 문서** 하나뿐이다 — 그것을
    안 알려 주면 사람은 검색이 엉뚱한 것을 물어 왔다고 생각한다.
    """
    picked = set(lanes or ())
    return bool(picked) and not (picked & WORD_LANES)
