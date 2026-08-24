"""없어진 미러가 남긴 sync_status 행을 지운다 (S14 · C3).

Revision ID: 0015_drop_dead_mirror_sync_rows
Revises: 0014_ticket_attachment_uploader
Create Date: 2026-08-24

## 왜 지우는가

`sync_status` 는 컴포넌트마다 한 행짜리 **현재 상태**다. 그런데 `tickets`·`documents`·
`projects` 세 행에 쓰는 코드가 이제 없다. 미러가 사라졌고 그 셋의 정본은 이 서버다.

쓰는 사람이 없는 상태 행은 시간이 지나도 갱신되지 않고, 마지막으로 적힌 값이 그대로
굳는다. 운영에 실제로 굳어 있는 값이 이렇다(2026-08-24 실측):

  * `documents` = error, 「노션 문서 데이터베이스 id 가 설정되지 않았습니다」
  * `tickets`  = error, 「Notion 응답 오류: HTTP 400 - This API is deprecated.」
  * `projects` = 같은 400 오류

세 줄 모두 **지금은 아무 데도 해당하지 않는 장애**를 말한다. 이 행들이 남아 있으면
운영자 화면(`GET /api/system/status` 의 `components`)이 그것을 그대로 실어 나르고,
나중에 이 표를 읽는 코드를 새로 만드는 사람은 없는 장애를 진짜로 읽는다. 거짓 경보는
정보가 아니라 사람이 진짜 경보까지 무시하게 만드는 원인이다.

행을 지우면 그 컴포넌트는 화면에서 **사라진다**. 「모르는 상태」가 아니라 「그런 것이
없다」가 사실이므로 그 모양이 맞다.

## 살아 있는 두 행은 건드리지 않는다

`search` 는 `app/search/reindex_router.py` 와 `app/worker_main.py` 가, `project_health` 는
`app/worker_main.py` 가 지금도 쓴다. 그래서 지우는 이름을 **하나씩 적어서** 지운다.
`DELETE FROM sync_status` 로 통째로 지우면 살아 있는 잡 둘의 마지막 성공 시각이 함께
사라지고, 그러면 "몇 주째 안 돌았다" 가 "한 번도 안 쟀다" 와 화면에서 같아진다.

## 되감기

**되감을 수 없다.** 지운 행의 내용(마지막 실행 시각·건수·오류 문구)을 이 파일이 모르고,
그것을 만들어 낸 코드도 이미 없어서 다시 채울 방법이 없다. 그래서 `downgrade` 는 아무것도
복구하지 않는다. 대신 그 사실을 로그에 남긴다. 조용히 통과하면 되감기를 돌린 사람이
원래 상태로 돌아왔다고 믿는데, 그것이 이 파일이 만들 수 있는 가장 나쁜 결과다.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = '0015_drop_dead_mirror_sync_rows'
down_revision = '0014_ticket_attachment_uploader'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# 지우는 행의 이름을 여기 하나에 적는다. 시험이 이 목록을 그대로 읽어서, 목록에 없는
# 컴포넌트가 함께 사라지지 않는 것을 확인한다.
DEAD_MIRROR_COMPONENTS = ("documents", "projects", "tickets")

# 살아 있는 소비자가 있는 이름들. 여기 적힌 것은 이 마이그레이션이 절대 건드리지 않는다.
LIVE_COMPONENTS = ("project_health", "search")


def delete_dead_mirror_rows(bind) -> int:
    """죽은 미러 컴포넌트 행만 지우고 지운 수를 돌려준다.

    함수로 빼 둔 이유는 시험이 같은 문장을 그대로 돌려 보기 위해서다. 시험이 SQL 을
    다시 적으면 마이그레이션이 무엇을 지우는지가 아니라 시험이 무엇을 지우는지를 재게 된다.
    """
    statement = sa.text(
        "DELETE FROM sync_status WHERE component IN :names"
    ).bindparams(sa.bindparam("names", expanding=True))
    result = bind.execute(statement, {"names": list(DEAD_MIRROR_COMPONENTS)})
    return int(result.rowcount or 0)


def upgrade() -> None:
    removed = delete_dead_mirror_rows(op.get_bind())
    logger.info(
        "미러가 사라진 sync_status 행 %d개를 지웠습니다 (%s).",
        removed,
        ", ".join(DEAD_MIRROR_COMPONENTS),
    )


def downgrade() -> None:
    # 되감기가 아무것도 복구하지 않는다는 사실을 말하고 지나간다. 예외를 던지지 않는 이유는
    # 이 회차가 스키마를 하나도 바꾸지 않아서다. 여기서 막으면 되돌릴 이유가 전혀 다른
    # 뒷 회차들까지 이 지점에서 함께 멈춘다.
    logger.warning(
        "sync_status 에서 지운 미러 상태 행은 되돌릴 수 없습니다. "
        "지운 행의 마지막 실행 시각과 오류 문구를 이 회차가 갖고 있지 않고, "
        "그 값을 만들던 동기화 코드도 이미 없습니다."
    )
