"""문자열 날짜 컬럼 → `date` / `timestamp` (S7 · P-14a · SQLite 실측 10번).

Revision ID: 0005_real_dates
Revises: 0004_knowledge_domain
Create Date: 2026-08-22

## 왜 지금인가

계획은 이것을 「새 도메인에서」로 미뤄 뒀고, 소유가 S6·S7 로 갈려 있었다. **반씩 하면 더
나쁘다** — 티켓·프로젝트·문서가 같은 규약을 공유하고 동기화 파서·필터(`due_window`)·
리포트·번다운·홈 위젯이 전부 그 규약으로 비교한다. 한쪽만 바꾸면 같은 화면에서 문자열
비교와 날짜 비교가 섞인다. 그래서 열여섯 컬럼을 **한 번에** 옮긴다.

## 문자열이 막지 못한 것

ISO 문자열은 사전순 정렬이 날짜순과 같아서 비교가 그냥 됐다. 그런데 `'2026-02-31'` 도,
`'TBD'` 도, 빈 문자열도 들어갔다. 앱이 입구마다 정규식 + `date.fromisoformat` 검사를
달았지만 **동기화와 마이그레이션은 그 입구를 안 지난다.** 이제 DB 가 막는다 — 규약을
문서로 약속하는 대신 타입이 강제한다(D-215 가 `jsonb` 에서 쓴 것과 같은 판단).

## 못 읽는 값은 NULL 로 두고, **몇 건인지 말한다**

`ALTER … TYPE date USING (…::date)` 는 값 하나가 못 읽히면 통째로 실패한다. 그러면
업그레이드가 첫 줄에서 죽고, 운영자는 어느 행인지 모른다. 그래서 관용 캐스트 함수를 쓰되
**버려진 건수를 `RAISE NOTICE` 로 남긴다** — 조용히 버리면 「원래 비어 있었나」와
「우리가 지웠나」를 아무도 구별할 수 없다.

달력일에서 앞 10자만 쓰는 이유: 소스(Notion)의 date 속성은 시각을 포함할 수 있고,
그 시각은 달력일에 뜻을 더하지 않는다.

## 되돌리기

`downgrade` 는 `to_char` 로 같은 문자열 규약을 복원한다. 못 읽어서 NULL 이 된 값은
**안 돌아온다** — 그것이 이 이전의 되돌릴 수 없는 부분이고, 위 NOTICE 가 그 크기를 미리
알려 주는 이유다.
"""
from __future__ import annotations

from alembic import op


revision = '0005_real_dates'
down_revision = '0004_knowledge_domain'
branch_labels = None
depends_on = None


# (표, 컬럼) — **달력일**. 시각이 아니라서 시간대 변환을 하지 않는다.
_DATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tickets", "due_date"),
    ("tickets", "start_date"),
    ("projects", "starts_on"),
    ("projects", "ends_on"),
    ("project_milestones", "due_on"),
    ("project_health_snapshots", "week_of"),
    ("project_weekly_reports", "week_of"),
    ("document_cache", "doc_date"),
    ("document_cache", "orig_date"),
    ("sprints", "starts_on"),
    ("sprints", "ends_on"),
)

# (표, 컬럼) — **시각**. 저장은 naive UTC 다(`app/core/db.py` 규약).
_TIMESTAMP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tickets", "notion_created_time"),
    ("tickets", "notion_last_edited"),
    ("projects", "notion_last_edited"),
    ("document_cache", "created_time"),
    ("document_cache", "last_edited"),
)

# NOT NULL 인 컬럼. 캐스트가 NULL 을 만들면 제약이 막으므로 잠시 풀었다가 다시 건다.
# `sprints` 의 두 컬럼은 S6 이 NOT NULL 로 만들었고 CHECK(`starts_on < ends_on`)도 있다.
_NOT_NULL: frozenset[tuple[str, str]] = frozenset({
    ("project_health_snapshots", "week_of"),
    ("project_weekly_reports", "week_of"),
    ("sprints", "starts_on"),
    ("sprints", "ends_on"),
})

_TO_DATE_FN = """
CREATE OR REPLACE FUNCTION _p14a_to_date(txt text) RETURNS date AS $$
BEGIN
  IF txt IS NULL OR btrim(txt) = '' THEN
    RETURN NULL;
  END IF;
  -- 앞 10자가 달력일이다. 소스가 'YYYY-MM-DDTHH:MM:SS' 로 줄 때도 같은 답을 낸다.
  RETURN left(btrim(txt), 10)::date;
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""

_TO_TS_FN = """
CREATE OR REPLACE FUNCTION _p14a_to_ts(txt text) RETURNS timestamp AS $$
BEGIN
  IF txt IS NULL OR btrim(txt) = '' THEN
    RETURN NULL;
  END IF;
  -- 오프셋이 있으면 UTC 로 옮기고 tzinfo 를 뗀다. 없으면 이미 UTC 로 본다.
  RETURN (btrim(txt)::timestamptz AT TIME ZONE 'UTC');
EXCEPTION WHEN others THEN
  BEGIN
    RETURN btrim(txt)::timestamp;
  EXCEPTION WHEN others THEN
    RETURN NULL;
  END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""


def _report_losses(table: str, column: str, fn: str) -> None:
    """캐스트가 버릴 값이 몇 건인지 **먼저** 센다.

    조용히 버리면 「원래 비어 있었나」와 「우리가 지웠나」를 아무도 구별할 수 없다.
    """
    op.execute(f"""
DO $$
DECLARE
  lost bigint;
BEGIN
  EXECUTE format(
    'SELECT count(*) FROM %I WHERE %I IS NOT NULL AND btrim(%I) <> '''' AND {fn}(%I) IS NULL',
    '{table}', '{column}', '{column}', '{column}'
  ) INTO lost;
  IF lost > 0 THEN
    RAISE NOTICE 'P-14a: %.% — 날짜로 읽을 수 없는 값 %건을 NULL 로 둔다', '{table}', '{column}', lost;
  END IF;
END $$;
""")


def upgrade() -> None:
    op.execute(_TO_DATE_FN)
    op.execute(_TO_TS_FN)

    # `sprints` 의 기간 CHECK 는 컬럼 타입이 바뀌는 동안 잠시 뗀다 — 두 컬럼을 한 번에
    # 못 바꾸므로, 중간 상태(하나는 date · 하나는 text)에서 비교가 성립하지 않는다.
    op.execute("ALTER TABLE sprints DROP CONSTRAINT IF EXISTS ck_sprints_window")

    for table, column in _DATE_COLUMNS:
        _report_losses(table, column, "_p14a_to_date")
        if (table, column) in _NOT_NULL:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE date "
            f"USING _p14a_to_date({column})"
        )

    for table, column in _TIMESTAMP_COLUMNS:
        _report_losses(table, column, "_p14a_to_ts")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamp without time zone "
            f"USING _p14a_to_ts({column})"
        )

    # NOT NULL 을 되건다. 캐스트로 NULL 이 된 행이 있으면 여기서 **막힌다** — 그것이
    # 맞다: 스프린트에 기간이 없거나 주간 리포트에 주가 없으면 그 행은 뜻이 없다.
    # 위 NOTICE 가 그 상황을 미리 알려 준다.
    for table, column in sorted(_NOT_NULL):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")

    op.execute(
        "ALTER TABLE sprints ADD CONSTRAINT ck_sprints_window CHECK (starts_on < ends_on)"
    )

    op.execute("DROP FUNCTION IF EXISTS _p14a_to_date(text)")
    op.execute("DROP FUNCTION IF EXISTS _p14a_to_ts(text)")


def downgrade() -> None:
    op.execute("ALTER TABLE sprints DROP CONSTRAINT IF EXISTS ck_sprints_window")

    for table, column in _DATE_COLUMNS:
        if (table, column) in _NOT_NULL:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
        # 옛 폭 그대로 돌아간다. `week_of` 는 10, 나머지는 40 이었다.
        width = 10 if column == "week_of" else 40
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar({width}) "
            f"USING to_char({column}, 'YYYY-MM-DD')"
        )

    for table, column in _TIMESTAMP_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar(40) "
            f"USING to_char({column}, 'YYYY-MM-DD\"T\"HH24:MI:SS')"
        )

    for table, column in sorted(_NOT_NULL):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")

    op.execute(
        "ALTER TABLE sprints ADD CONSTRAINT ck_sprints_window CHECK (starts_on < ends_on)"
    )
