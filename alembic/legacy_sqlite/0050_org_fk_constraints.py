"""org_id 가 진짜 조직을 가리키게 만든다 — 빠져 있던 외래키 8개 (H1)

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-07

## 무엇을 고치는가

`app/core/models_base.py::OrgScopedMixin` 은 `ForeignKey("organizations.id")` 를 선언한다.
그런데 그 제약을 만든 마이그레이션이 없었다. 0024 가 6개 표에 대해 일부러 건너뛰었고
("6개 표를 통째로 다시 만드는 위험이 참조 무결성보다 크다"), 그 뒤 0026(usage_events)과
0030(search_documents)이 같은 모양을 따라갔다. 결과는 **모델은 참조라고 말하는데 DB 는
아무것도 검사하지 않는** 상태다.

이게 왜 나쁜가 - 증상이 오류가 아니라 침묵이기 때문이다.

  * 조직 행을 지우면 그 조직 것이던 행들의 `org_id` 가 아무 데도 안 닿는 값이 된다.
  * 오타나 복사 실수로 없는 `org_id` 가 들어가도 INSERT 가 성공한다.
  * 둘 다 화면에서는 "왜인지 목록이 비어 있다" 로만 보인다. `org_id = :org` 가 0건이 되고,
    그 0건은 "그런 자료가 없다" 와 구별되지 않는다.

0024 의 판단을 뒤집는 근거: 그때는 조직이 하나뿐이라 잘못된 값이 들어갈 경로가 사실상
없었다. 지금은 조직 축이 실제로 쓰이고(범위 관리자, 조직 정지) 표가 여덟 개로 늘었다.
"조용히 0건" 이 나는 자리가 여덟 곳이면 그건 위험이 아니라 시간 문제다.

## SQLite 에서 기존 표에 FK 를 붙이려면 표를 다시 만들어야 한다

ALTER TABLE 로는 안 된다. `batch_alter_table(recreate="always")` 가 새 표를 만들어 행을
복사하고 이름을 바꾼다. 운영 DB 에 티켓 1,071건과 사용자 15명이 있으므로 **행을 하나도
잃지 않는 방법**만 쓴다: 복사는 SQLite 가 하고(`INSERT ... SELECT`), 이 파일은 지우는
문장을 한 줄도 갖지 않는다.

`PRAGMA foreign_keys` 는 alembic env.py 가 켜지 않는다. 그래서 재생성 중에 다른 표가
이 표를 가리키던 FK 는 이름으로 유지된다(0015 와 0024 가 같은 방식으로 이미 증명했다).

## 고아 org_id 를 어떻게 할 것인가 - **기본 조직으로 옮긴다**

제약을 걸기 전에 반드시 정해야 하는 문제다. 지금 데이터에 조직 표에 없는 `org_id` 가
있으면 제약을 건 뒤 그 행들은 손댈 수 없는 행이 된다(UPDATE 도 거부된다).

선택지는 셋이었다.

  1. **지운다** - 안 된다. 게시글, 문서 캐시, 채팅방, 휴지통 항목이다. 사용자가 쓴 내용이
     들어 있고, 지우면 되돌릴 방법이 없다. "정리" 라는 이름의 데이터 유실이다.
  2. **제약을 포기한다** - 그러면 이 마이그레이션이 아무것도 안 한 것과 같다.
  3. **기본 조직으로 옮긴다** - 고른 것. 고아 행이 생기는 유일한 현실적 경로는 조직 행이
     사라졌거나 값이 잘못 들어간 것인데, 두 경우 모두 그 행의 올바른 주인을 이 자리에서
     알아낼 방법이 없다. 기본 조직은 0022 부터 항상 존재하고 단일 조직 설치에서는 곧
     정답이다. 무엇보다 **되돌릴 수 있다** - 행이 남아 있으므로 나중에 올바른 조직으로
     다시 옮길 수 있다.

옮긴 건수는 로그로 남긴다. 조용히 옮기면 배포 뒤에 "왜 이게 여기 있지" 를 아무도 설명하지
못한다.

## NULL 은 그대로 둔다

FK 는 NULL 을 허용한다(참조하지 않는다는 뜻이므로). `usage_events` 는 시스템 행위를
`org_id=NULL` 로 남기는 것이 정상이고, `OrgScopedMixin` 이 nullable 인 이유도 거기 적혀
있다. NOT NULL 승격은 이 마이그레이션의 일이 아니다 - 한 번에 하나씩 바꾼다.

## search_documents 는 FTS5 인덱스가 딸려 있어 순서가 중요하다

`search_index` 는 `content='search_documents'` 인 external content 인덱스이고 **rowid 로**
원본을 가리킨다. 표를 다시 만들면 rowid 가 새로 매겨지고 트리거도 표와 함께 사라진다.
그대로 두면 검색이 조용히 0건이 되거나 **다른 행의 제목**을 돌려준다. 그래서
트리거 삭제 → 표 재생성 → 트리거 재생성 → 인덱스 `rebuild` 순서를 지킨다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# app/org/constants.py 가 정본. 마이그레이션은 적용된 뒤 불변이어야 하므로 import 대신
# 값을 못박는다(0022, 0024 와 같은 관례).
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"

# `OrgScopedMixin` 을 상속하는데 DB 에 제약이 없던 표들. departments / users / ticket_cache /
# projects / offboarding_runs 는 이미 갖고 있어 여기 없다(있는 것을 또 만들지 않는다).
_TABLES = (
    "job_titles",
    "board_posts",
    "document_cache",
    "chat_rooms",
    "game_rooms",
    "trash_items",
    "usage_events",
    "search_documents",
)

_FK_NAME = "fk_{table}_org_id"

# 0030 이 만든 FTS5 트리거. 표를 다시 만들면 함께 사라지므로 여기서 다시 만든다.
_SEARCH_TRIGGERS = (
    (
        "search_documents_ai",
        "CREATE TRIGGER search_documents_ai AFTER INSERT ON search_documents BEGIN"
        "  INSERT INTO search_index(rowid, title, body)"
        "  VALUES (new.rowid, new.title, new.body);"
        "END",
    ),
    (
        "search_documents_ad",
        "CREATE TRIGGER search_documents_ad AFTER DELETE ON search_documents BEGIN"
        "  INSERT INTO search_index(search_index, rowid, title, body)"
        "  VALUES ('delete', old.rowid, old.title, old.body);"
        "END",
    ),
    (
        "search_documents_au",
        "CREATE TRIGGER search_documents_au AFTER UPDATE ON search_documents BEGIN"
        "  INSERT INTO search_index(search_index, rowid, title, body)"
        "  VALUES ('delete', old.rowid, old.title, old.body);"
        "  INSERT INTO search_index(rowid, title, body)"
        "  VALUES (new.rowid, new.title, new.body);"
        "END",
    ),
)


def _adopt_orphans(table: str) -> int:
    """조직 표에 없는 `org_id` 를 기본 조직으로 옮긴다. 옮긴 건수를 돌려준다.

    지우지 않는 이유는 모듈 docstring 에 적혀 있다. NULL 은 건드리지 않는다 - FK 가
    허용하는 값이고, 그것까지 바꾸면 이 마이그레이션이 두 가지 일을 하게 된다.
    """
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            f"UPDATE {table} SET org_id = :org WHERE org_id IS NOT NULL"
            f" AND org_id NOT IN (SELECT id FROM organizations)"
        ).bindparams(org=_DEFAULT_ORG_ID)
    )
    return int(result.rowcount or 0)


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_org_fk(table: str) -> bool:
    return any(
        fk["constrained_columns"] == ["org_id"]
        for fk in sa.inspect(op.get_bind()).get_foreign_keys(table)
    )


def upgrade() -> None:
    tables = _existing_tables()
    moved: dict[str, int] = {}

    for table in _TABLES:
        if table not in tables:
            continue
        # 순서가 중요하다: 고아를 먼저 치우지 않으면 제약을 건 뒤 그 행을 고칠 수 없다.
        count = _adopt_orphans(table)
        if count:
            moved[table] = count

        if table == "search_documents":
            for name, _sql in _SEARCH_TRIGGERS:
                op.execute(f"DROP TRIGGER IF EXISTS {name}")

        with op.batch_alter_table(table, recreate="always") as batch:
            batch.create_foreign_key(
                _FK_NAME.format(table=table), "organizations", ["org_id"], ["id"]
            )

        if table == "search_documents":
            for _name, sql in _SEARCH_TRIGGERS:
                op.execute(sql)
            # 표를 다시 만들면서 rowid 가 새로 매겨졌다. rebuild 하지 않으면 인덱스가
            # 옛 rowid 를 가리켜 검색이 다른 행을 돌려준다.
            op.execute("INSERT INTO search_index(search_index) VALUES('rebuild')")

    if moved:
        logger.warning(
            "0050: 조직 표에 없던 org_id 를 기본 조직으로 옮겼다 (지우지 않았다): %s",
            ", ".join(f"{t}={n}행" for t, n in sorted(moved.items())),
        )


def downgrade() -> None:
    tables = _existing_tables()
    for table in reversed(_TABLES):
        if table not in tables or not _has_org_fk(table):
            continue

        if table == "search_documents":
            for name, _sql in _SEARCH_TRIGGERS:
                op.execute(f"DROP TRIGGER IF EXISTS {name}")

        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(_FK_NAME.format(table=table), type_="foreignkey")

        if table == "search_documents":
            for _name, sql in _SEARCH_TRIGGERS:
                op.execute(sql)
            op.execute("INSERT INTO search_index(search_index) VALUES('rebuild')")
