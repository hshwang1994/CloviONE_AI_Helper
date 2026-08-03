"""observability — usage_events / sync_status (§7.1.A, PLAN Phase 4)

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-03

**`GET /metrics` 는 만들지 않는다(계획서에서 드롭됨).** 역할 게이트를 걸면 스크레이퍼가 못
읽고, 127.0.0.1 로 제한하면 역할 게이트가 무의미하다. 게다가 이 스택에 Prometheus 가 없다.
그래서 **테이블과 워커 훅만** 만들고, 숫자는 관리자 대시보드와 사용자 화면 상태 배너로
노출한다.

## usage_events — 저빈도 지점 전용

"누가 무엇을 얼마나 쓰는가"를 남긴다. **채팅 전송·폴링 경로에는 절대 걸지 않는다.**
이유가 성능뿐이 아니다:
  * 채팅 전송은 이미 INSERT + `event_seq` UPDATE 로 SAVEPOINT 재시도를 도는 이 앱에서
    가장 뜨거운 쓰기 경로다(계획 C9). 여기에 INSERT 를 하나 더 얹으면 병목을 정확히
    가장 나쁜 곳에서 키운다.
  * 폴링 경로(놀이 3초, 휴지통 15초, 알림 60초)에 걸면 **읽기가 쓰기가 된다** — ETag/304 로
    아끼려던 것을 그대로 되돌린다.
그래서 대상은 로그인·티켓 생성·문서 생성 요청처럼 **사람이 의도해서 하는, 드문 행동**뿐이다.
이 규칙은 `tests/unit/test_usage_events.py` 가 import 그래프로 못박는다(뜨거운 모듈이
기록 함수를 import 하면 실패한다).

보존은 별도 정책 없이 `created_at` 인덱스만 둔다 — 나중에 retention 스윕이 붙을 자리다.

## sync_status — 미러 동기화 상태 한 표

`document_sync_state`(문서)와 `ticket_sync_state`(티켓)가 이미 각자 있는데 표를 하나 더 두는
이유: 그 둘은 **동기화 구현의 상태**(커서·prune 여부 등 각자 다른 컬럼)이고, 여기 것은
**사람에게 보여줄 공통 모양**이다. 화면 하나가 컴포넌트 목록을 그리려면 표마다 다른 컬럼을
알아야 하는데, 그러면 컴포넌트가 늘 때마다 화면을 고쳐야 한다. 공통 모양 한 표를 워커가
채우고 화면은 그것만 읽는다.

타임스탬프는 파이썬 datetime 으로 만들어 파라미터 바인딩한다(SQLite STRFTIME '%f' 금지,
CLAUDE.md §8).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=True),
        # 계정이 보관·삭제돼도 집계는 남아야 하므로 FK 를 걸지 않는다(감사 로그와 같은 판단).
        sa.Column("user_id", sa.String(36), nullable=True),
        # 'auth.login' / 'ticket.create' 처럼 점으로 구분한 이름.
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(48), nullable=True),
        sa.Column("object_id", sa.String(64), nullable=True),
        # 이벤트별 부가 정보(JSON 문자열). **개인정보·비밀은 넣지 않는다** —
        # 기록 함수가 값을 검사하지 않으므로 부르는 쪽의 책임이다.
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_events_event", "usage_events", ["event"])
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_org_id", "usage_events", ["org_id"])

    op.create_table(
        "sync_status",
        # 'tickets' / 'documents' 처럼 컴포넌트 이름이 그대로 PK. 싱글턴 upsert 라
        # 별도 id 를 두면 중복 행이 생길 여지만 남는다.
        sa.Column("component", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # 시드하지 않는다. 워커가 처음 돌 때 행을 만든다 — 미리 만들어 두면 "한 번도 안 돌았다"와
    # "돌았는데 idle 이다"가 구분되지 않는다(배너가 거짓으로 안심시킨다).


def downgrade() -> None:
    op.drop_table("sync_status")
    op.drop_index("ix_usage_events_org_id", table_name="usage_events")
    op.drop_index("ix_usage_events_user_id", table_name="usage_events")
    op.drop_index("ix_usage_events_event", table_name="usage_events")
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_table("usage_events")
