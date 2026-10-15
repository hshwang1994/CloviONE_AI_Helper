"""AI 검색의 동의어 표 — 저장소 안의 작은 표 하나 (D-568).

사람은 「VMware 네트워크 자동화」라고 묻고 문서는 「NSX」 · 「vSphere」 · 「Ansible」이라고 적는다. 형태소 분석기도 외부
사전도 쓰지 않는다(폐쇄망 설치). 그 대신 이 제품이 다루는 도메인(가상화 · 네트워크 · 자동화 · 저장소)의 낱말 묶음을 여기
적어 두고, 질문의 낱말이 어느 묶음에 들면 그 묶음의 **다른 낱말**을 절반 가중으로 함께 찾는다
(`app/ai/retrieval/query.py::keyword_weights`).

규칙 셋:
  * 묶음은 **뜻이 같거나 늘 함께 나오는** 낱말만 — 「네트워크」와 「보안」처럼 주제가 다른 것을 한 묶음에 넣지 않는다.
  * 낱말은 `search_text.keywords()` 와 같은 꼴(소문자 · `[0-9a-z가-힣]`)이다. 표에 적힌 꼴 그대로 LIKE 가지가 된다.
  * 덧붙이는 수는 `limit` 로 막는다 — 가지가 많아질수록 레인이 느려지고 순위가 흐려진다.

통합 검색 화면(`/search`)은 이 표를 쓰지 않는다(P-123 — 그 화면의 AND 는 기억나는 구절에 맞다).
"""

from __future__ import annotations

#: 함께 찾는 낱말 묶음. 한 낱말이 두 묶음에 들 수 있다(「vsphere」는 vmware 묶음과 가상화 묶음) — 그 낱말의 짝은 두 묶음의
#: 합이다. 묶음 안의 순서가 우선순위다: 제품 이름처럼 그 분야에서만 쓰는 낱말을 앞에 둔다(「네트워크」 → 「nsx」 먼저).
GROUPS: tuple[tuple[str, ...], ...] = (
    ("vmware", "vsphere", "esxi", "vcenter", "vcf"),
    ("네트워크", "nsx", "network"),
    ("자동화", "automation", "ansible", "terraform"),
    ("쿠버네티스", "kubernetes", "k8s"),
    ("가상화", "virtualization", "vsphere", "가상머신"),
    ("스토리지", "storage", "vsan"),
    ("하이닉스", "hynix", "skhynix"),
    ("클러스터", "cluster"),
)

#: 한 질문에 덧붙이는 낱말 수의 상한.
MAX_EXPANSIONS = 4


def _build_index() -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = {}
    for group in GROUPS:
        for word in group:
            partners = index.setdefault(word, [])
            partners.extend(w for w in group if w != word and w not in partners)
    return {word: tuple(partners) for word, partners in index.items()}


_INDEX: dict[str, tuple[str, ...]] = _build_index()


def partners_of(word: str) -> tuple[str, ...]:
    """한 낱말의 짝(묶음 순서대로). 표에 없으면 빈 튜플."""
    return _INDEX.get(word, ())


def expand(words, *, limit: int = MAX_EXPANSIONS) -> tuple[str, ...]:
    """질문의 낱말 → 함께 찾을 낱말(중복 없이, 원래 낱말은 빼고, 최대 `limit` 개).

    낱말마다 첫 짝부터 **돌아가며** 고른다 — 「VMware 네트워크 자동화」에서 vmware 의 짝 넷이 상한을 다 채우면 「nsx」가
    빠진다. 한 바퀴에 낱말마다 하나씩 고르면 질문의 낱말이 고루 넓어진다.
    """
    given = [w for w in (words or ()) if isinstance(w, str)]
    seen = set(given)
    queues = [partners_of(w) for w in given]
    out: list[str] = []
    depth = 0
    while len(out) < limit and any(depth < len(queue) for queue in queues):
        for queue in queues:
            if depth >= len(queue):
                continue
            partner = queue[depth]
            if partner in seen:
                continue
            seen.add(partner)
            out.append(partner)
            if len(out) >= limit:
                break
        depth += 1
    return tuple(out)
