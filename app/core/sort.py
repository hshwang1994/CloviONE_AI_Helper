"""목록 정렬의 **기계**. 어떤 키를 허용할지는 도메인이 정한다.

## 왜 기계만 여기 있는가

틀리는 것은 기계 쪽이다 — 파싱 → 화이트리스트 대조 → `nulls_last()` → **동방향 tiebreak**
네 단계 중 마지막 하나만 빠져도 증상은 「2쪽에 1쪽 행이 또 나온다」이고 **오류가 안 난다**.
아홉 라우터에 복붙하면 그중 하나는 반드시 빠진다.

정책(어떤 키를 허용하는가, 기본이 무엇인가)은 도메인 모듈이 든다. 그 지식이 옆의 필터 절과
반드시 일치해야 하기 때문이다 — 승인의 `status` 정렬은 저장 상태가 아니라 **유효 상태**여야
하고(만료 지난 pending 을 만료로 보는 그 판정), 공지의 `level` 은 가나다가 아니라 심각도
순이어야 한다. 그 둘을 여기로 끌어오면 필터 절과 정렬 절이 다른 파일에서 갈라진다.
`app/tickets/query.py` 가 `SORT_KEYS` 를 `filter_clauses()` 바로 옆에 두는 것과 같은 이유다.

## 라우터가 지켜야 하는 절 순서

    ① 조건  →  ② 범위(D-202)  →  ③ 정렬  →  ④ 상한

정렬을 상한 뒤로 옮기면 「100건을 뽑아 그 안에서 정렬」이 되어 조용히 틀린 순서가 나온다.
범위가 상한보다 앞이어야 하는 이유는 D-202 그대로다.

## 전순서(total order)

무한 스크롤은 쪽을 **이어 붙인다**. 정렬이 전순서가 아니면 같은 행이 두 묶음에 나오거나
아예 빠지고, 그 어긋남은 오류를 안 낸다. 그래서 1차 키 뒤에 **언제나** PK 를 같은 방향으로
붙인다. (그래도 쪽 사이에 행이 삽입·삭제되면 여전히 건너뛴다 — 그것은 커서 페이징이라야
풀리고, 이번 범위가 아니다. 각 라우터 docstring 에 그 한계를 적어 둔다.)
"""

from __future__ import annotations

from fastapi import Query


class SortParams:
    """`sort` · `order` 질의 파라미터. 라우터가 `Depends()` 로 받는다."""

    def __init__(
        self,
        sort: str | None = Query(default=None, max_length=32),
        order: str | None = Query(default=None, pattern="^(asc|desc)$"),
    ) -> None:
        self.sort = (sort or "").strip() or None
        self.order = order


class SortSpec:
    """한 목록의 정렬 계약.

    `columns` 는 **키 → 컬럼(또는 표현식)** 딕셔너리다. `getattr(Model, key)` 를 하지 않는
    이유: 멤버십 검사와 속성 조회가 떨어져 있으면 다음 사람이 하나만 옮긴다. 딕셔너리 조회는
    화이트리스트와 조회가 같은 한 줄이라 그 틈이 없다.
    """

    def __init__(self, *, columns: dict, default: str, tiebreak, default_order: str = "desc") -> None:
        if default not in columns:
            raise ValueError(f"기본 정렬 키 {default!r} 가 columns 에 없다")
        if default_order not in ("asc", "desc"):
            raise ValueError("default_order 는 asc 또는 desc 다")
        self.columns = columns
        self.default = default
        self.tiebreak = tiebreak
        self.default_order = default_order

    @property
    def keys(self) -> tuple[str, ...]:
        """화면이 고를 수 있는 키. 프런트 미러(`sortKeys.json`)가 이 값을 읽는다."""
        return tuple(sorted(self.columns))


def order_by(spec: SortSpec, params: SortParams | None):
    """정렬 절 두 개(1차 키, tiebreak)를 튜플로.

    🔴 화이트리스트 밖 값은 **400 이 아니라 조용히 기본 정렬로 떨어진다.** 필터와 다르다 —
    틀린 필터 값은 목록을 0건으로 좁혀 「없다」로 오독되지만, 틀린 정렬 값은 **어느 행이
    나오는지를 바꾸지 않는다.** 순서만 문서화된 기본으로 돌아가므로 옛 저장된 뷰·북마크가
    계속 산다(`app/users/router.py` · `app/board/router.py` 가 이미 같은 판단을 했다).

    `nulls_last()` 는 **언제나** 건다. PostgreSQL 은 ASC 에서 NULL 을 뒤로, SQLite 는 앞으로
    놓는다 — 명시하지 않으면 백엔드에 따라 묶음 경계가 달라진다.
    """
    key = (params.sort if params else None) or spec.default
    if key not in spec.columns:
        key = spec.default
    descending = ((params.order if params else None) or spec.default_order) == "desc"
    col = spec.columns[key]
    primary = col.desc().nulls_last() if descending else col.asc().nulls_last()
    tie = spec.tiebreak.desc() if descending else spec.tiebreak.asc()
    return (primary, tie)