"""prune 바닥 — 소스가 "빈 결과"를 **정상으로** 돌려줘도 캐시를 비우지 않는다.

동기화의 prune 은 "이번 조회에서 못 본 행"을 지운다. 그 판단의 근거는 소스가 준 목록 하나뿐이라,
소스가 오류 대신 **빈 목록**을 주면(통합 권한 재조정, DB id 오설정, 워크스페이스에서 이동·필터,
일시적 버그 — 전부 HTTP 200 이다) 전량 삭제가 "정상 동기화"로 실행된다.

캐시는 순수 미러가 아니라서 그 대가가 크다:

  * `ticket_comments`·`ticket_attachments` 가 CASCADE 로 함께 사라진다. 둘 다 Notion 에 없다.
  * `ticket_cache.body_markdown` 은 "로컬이 정본, Notion push 는 나중" 설계라 **push 전 본문은
    우리 DB 에만 있다**. `_upsert` 는 그 값을 다시 채우지 않는다.
  * `document_cache.classification_manual` 로 표시된 수동 분류는 Notion 에 대응 필드가 없다.

즉 **재동기화로 돌아오지 않는 것들**이 지워진다. 그래서 삭제 자체에 바닥을 둔다:

  * 소스가 한 건도 안 줬으면(`keep` 이 빔) 절대 지우지 않는다.
  * 한 번에 기존의 절반(`MAX_DROP_RATIO`)을 넘게 지우려 하면 지우지 않는다.

둘 다 "소스가 틀렸을 가능성이 캐시가 틀렸을 가능성보다 높은" 구간이다. 거부하면 이유를 돌려주고,
호출측은 그것을 `SYNC_ERROR` 로 남긴다 — 조용히 넘어가면 캐시가 낡아 가는 것을 아무도 모른다.

`search/indexer.py` 에도 같은 규율이 있지만 그쪽은 **예외가 났을 때만** 기존 색인을 보존한다.
빈 결과는 예외가 아니므로 그 방어로는 이 경우가 안 막힌다 — 발동 조건을 넓힌 판이 여기다.

의도적으로 **하지 않은 것**: 자식 표를 RESTRICT 로 바꾸는 것. `tickets/models.py` 가 CASCADE 를
고른 이유를 적어 놨다 — 정상 삭제된 티켓에 댓글이 하나라도 붙어 있으면 그 DELETE 가 실패하고
sync 가 예외를 삼켜 **동기화 전체가 조용히 멈춘다**. 바닥은 삭제 지점에 두는 것이 맞다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 한 번의 동기화가 지울 수 있는 최대 비율. 이걸 넘으면 소스 장애로 본다.
MAX_DROP_RATIO = 0.5

# 비율 바닥을 적용할 최소 캐시 크기. 이보다 작으면 비율은 보지 않는다.
#
# 캐시가 3건일 때 1건 삭제는 33%, 2건일 때는 50%, 1건일 때는 100% 다 — 작은 캐시에서는
# **정상 삭제가 거의 항상 비율을 넘는다**. 그대로 두면 신규 설치나 소규모 워크스페이스에서
# 삭제가 영구히 거부되고 매 회차 SYNC_ERROR 만 쌓인다(운영자가 풀 방법도 없다).
# 비율 바닥은 "많던 것이 갑자기 사라졌다"를 잡는 장치라 표본이 있어야 의미가 있다.
# 최악(전량 삭제)은 아래 `keep` 이 비었는지 보는 바닥이 크기와 무관하게 막는다.
MIN_ROWS_FOR_RATIO_GUARD = 10


@dataclass(frozen=True)
class PruneResult:
    """삭제 결과. `refused` 가 있으면 **아무것도 지우지 않았다**는 뜻이다."""

    deleted: int = 0
    considered: int = 0
    refused: str | None = None
    # `mark` 전략을 쓴 경우 True — `deleted` 는 "지운 건수" 가 아니라 "표시한 건수" 다.
    # 호출측 문구가 "지웠습니다" 로 남지 않게 하려고 결과에 실어 보낸다.
    soft: bool = False

    @property
    def ok(self) -> bool:
        return self.refused is None


def prune_missing(
    db: Any,
    rows: Sequence[Any],
    keep: set[str],
    *,
    key: Callable[[Any], str | None],
    label: str,
    mark: Callable[[Any], None] | None = None,
) -> PruneResult:
    """`rows` 중 `keep` 에 없는 것을 지운다. 바닥에 걸리면 한 건도 지우지 않는다.

    `rows` 는 **prune 대상만** 담아 넘긴다(예: 티켓은 notion_page_id 가 있는 행만 — 자체 생성
    티켓은 소스 조회 결과에 없는 것이 당연하므로 애초에 후보가 아니다).

    `mark` 를 주면 **지우는 대신 그 함수를 부른다**(소프트 프룬, 0043). 티켓처럼 자식 표에
    사용자 데이터(댓글·첨부)가 CASCADE 로 매달린 경우에 쓴다 — 한 회차 깜빡임으로 그것들이
    사라지면 재동기화로 돌아오지 않기 때문이다. **바닥(빈 결과·낙폭)은 두 전략이 공유한다** —
    두 벌이 되면 한쪽만 고쳐지고, 그때 증상은 "어떤 동기화만 데이터를 지운다" 가 된다.
    """
    doomed = [r for r in rows if key(r) not in keep]
    if not doomed:
        return PruneResult(considered=len(rows))

    if not keep:
        reason = (
            f"{label} 소스가 0건을 돌려줘 삭제 {len(doomed)}건을 취소했습니다. "
            f"캐시({len(rows)}건)는 그대로 둡니다."
        )
        logger.warning("prune 거부: %s", reason)
        return PruneResult(considered=len(rows), refused=reason)

    ratio = len(doomed) / len(rows)
    if len(rows) >= MIN_ROWS_FOR_RATIO_GUARD and ratio > MAX_DROP_RATIO:
        reason = (
            f"{label} 한 번에 {len(doomed)}/{len(rows)}건({ratio:.0%})을 지우려 해 취소했습니다. "
            f"소스가 {len(keep)}건만 돌려줬습니다. 캐시는 그대로 둡니다."
        )
        logger.warning("prune 거부: %s", reason)
        return PruneResult(considered=len(rows), refused=reason)

    for row in doomed:
        if mark is not None:
            mark(row)
        else:
            db.delete(row)
    if doomed:
        # 드리프트 지표. 지금까지는 몇 건이 지워졌는지 세지도 남기지도 않아서, 2000 → 0 이 되어도
        # 상태에는 {status: ok, count: 0} 만 남았다.
        logger.info(
            "prune: %s %d건 %s(전체 %d건)",
            label, len(doomed), "표시" if mark is not None else "삭제", len(rows),
        )
    return PruneResult(
        deleted=len(doomed), considered=len(rows), soft=mark is not None
    )
