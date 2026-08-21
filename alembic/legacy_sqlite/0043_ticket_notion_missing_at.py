"""티켓이 Notion 에서 사라져도 **사용자 데이터를 즉시 지우지 않는다** (C2 / 사용자 지적 #4).

## 왜 필요한가 — 재현한 사실

`tests/regression/test_comment_survives_resync.py` 로 재현했다. 티켓이 Notion 응답에서 **한 라운드**
빠지면(페이지네이션 흔들림·필터·일시 권한 문제 — 전부 HTTP 200 이다):

    sync 상태          : ok / error=None          ← 화면은 "정상" 이라 말한다
    사라진 라운드 뒤    : 캐시행=없음 댓글=0 첨부=0   ← CASCADE 가 사용자 데이터를 지웠다
    돌아온 뒤 uid      : 6229d2b9… → 991f965b…     ← 새 UUID (계획서 C2)
    돌아온 뒤 댓글/첨부 : 0 / 0                     ← 영구 소실

`sync_prune` 의 바닥(빈 결과·낙폭 50%)은 **대량 손실**을 막지만, 티켓 한 건이 깜빡이는 것은
정상 삭제로 보여 그대로 지운다. 그리고 그 한 건에 붙어 있던 댓글·첨부·미push 본문은
**Notion 에 없으므로 재동기화로 돌아오지 않는다.**

## 왜 '결정적 UUID'(uuid5) 로 고치지 않았는가

계획서는 `ticket_cache.id` 를 page id 에서 결정적으로 파생시키자고 적었다. 재현해 보니
**그것만으로는 아무것도 못 고친다** — CASCADE 가 **먼저** 자식을 지우므로 같은 id 로 행이
되살아나도 재결합할 것이 남아 있지 않다. PK 를 바꾸는 마이그레이션은 자식 FK 까지 손대야 해서
위험한데 이득이 없다. 그래서 **하지 않는다**(하려던 것을 왜 안 했는지 남긴다).

## 무엇으로 고쳤는가

`notion_missing_at` — "이 회차 소스 응답에서 안 보였다" 를 **표시만** 한다.
  * 목록에서는 즉시 빠진다(사용자에게는 지금과 똑같이 보인다).
  * 댓글·첨부·본문은 그대로 살아 있다.
  * 다음 회차에 돌아오면 표시가 지워지고 아무 일도 없었던 것이 된다.
  * 유예(`retention.MISSING_TICKET_GRACE_DAYS`)를 넘겨도 안 돌아오면 그때 진짜로 지운다 —
    그 시점의 CASCADE 는 **의도된 정리**다(휴지통이 이미 쓰는 관용과 같다).

NULL 이 기본이므로 기존 행은 전부 "정상" 으로 읽힌다. 그게 사실이다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

_TABLE = "ticket_cache"
_COLUMN = "notion_missing_at"
_INDEX = "ix_ticket_cache_notion_missing_at"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))
    # 모든 목록 질의가 `notion_missing_at IS NULL` 을 걸게 되므로 인덱스가 뜨거운 경로에 든다.
    if _INDEX not in {i["name"] for i in insp.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _INDEX in {i["name"] for i in insp.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
