"""user_preferences + saved_views (PLAN Phase 6 — 사용자 백로그)

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-03

계획서 Phase 6 '사용자' 다섯 항목이 남겨야 하는 상태를 담는 표 둘이다.

## `user_preferences` — 사용자당 한 행

아바타·알림 설정·방해금지·투어 상태를 한 행에 모은다. `users` 테이블에 컬럼을 붙이지
않는 이유가 두 가지다.

1. **`users` 는 신원과 권한의 표다.** 로그인·RBAC·감사가 매 요청 이 행을 읽는다. 취향
   설정(테마 옆에 무엇을 뮤트했는가)을 같은 행에 섞으면 그 뜨거운 경로가 넓어지고,
   설정 하나 추가할 때마다 계정 스키마를 흔들게 된다.
2. **없어도 되는 값이다.** 행이 없으면 전부 기본값 — 신규 사용자도 마이그레이션 백필도
   필요 없다. 서비스가 처음 쓸 때 만든다(get-or-create).

**방해금지(DND)는 알림을 삼키지 않는다.** 이 표에는 '조용히 할 것인가'만 담기고 알림
행 자체는 평소대로 쌓인다 — 자세한 근거는 `app/profiles/prefs.py` 모듈 docstring 참조.

**`muted_types` 는 콤마 구분 문자열이다.** 값이 `^[a-z][a-z0-9_]*$` 인 알림 유형 키만
들어가므로(서비스가 레지스트리로 검증) 콤마가 값 안에 나타날 수 없다. JSON 으로 담으면
SQLite 에서 부분 검색이 불가능해지고, 다중값 표(0x1f 규약)를 쓰기엔 여기 값은 목록이
아니라 짧은 집합이다.

## `saved_views` — 자주 쓰는 필터 조합

`query` 에 담는 것은 **URL 쿼리 문자열**(`q=x&status=failed`)이다. 화면이 필터를 URL 로
조립하는 기존 규약(`frontend/src/screens/DataScreen.jsx`)을 그대로 저장하므로, 뷰를 부르는
일이 곧 '그 URL 로 가는 일'이 되고 링크 공유가 공짜로 따라온다. 필터를 구조화된 JSON 으로
저장했다면 화면의 필터 정의가 바뀔 때마다 저장된 뷰를 마이그레이션해야 한다.

`(user_id, screen_key, name)` 유니크 — 같은 화면에 같은 이름 두 개는 사용자가 어느 쪽을
고를지 알 수 없다. 이름이 겹치면 409 로 돌려주고 덮어쓸지 묻는다.

타임스탬프는 애플리케이션이 Python 에서 만들어 바인딩한다 — `STRFTIME` 을 쓰지 않는다
(CLAUDE.md §8: SQLite `STRFTIME('%f')` 가 과거 부서 화면을 죽인 함정).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        # unique — 사용자당 한 행. 두 행이 생기면 '어느 쪽이 내 설정인가'가 모호해진다.
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        # ── 아바타 ────────────────────────────────────────────────────────────
        # 파일 자체는 data_dir/uploads/avatar/<user_id>/ 에 있다(app/core/uploads.py).
        # 여기 남는 것은 서버가 만든 저장명과 서버가 매직바이트로 판정한 media_type 뿐이다 —
        # 사용자 파일명도 확장자도 신뢰하지 않는다.
        sa.Column("avatar_stored_name", sa.String(64), nullable=True),
        sa.Column("avatar_media_type", sa.String(64), nullable=True),
        sa.Column("avatar_updated_at", sa.DateTime(), nullable=True),
        # ── 알림 설정 ─────────────────────────────────────────────────────────
        # 뮤트해도 알림 행은 그대로 쌓인다. 배지(푸시)에서만 빠진다.
        sa.Column("muted_types", sa.Text(), nullable=False, server_default=""),
        # ── 방해금지 ──────────────────────────────────────────────────────────
        sa.Column("dnd_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        # 시각이 지나면 자동으로 풀린다. NULL 이면 수동으로 끌 때까지 유지.
        sa.Column("dnd_until", sa.DateTime(), nullable=True),
        sa.Column(
            "quiet_hours_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        # 'HH:MM' (Asia/Seoul 벽시계). 자정을 넘는 구간(22:00→08:00)도 허용한다.
        sa.Column("quiet_start", sa.String(5), nullable=False, server_default="22:00"),
        sa.Column("quiet_end", sa.String(5), nullable=False, server_default="08:00"),
        # ── 첫 로그인 투어 ────────────────────────────────────────────────────
        # 버전으로 남기는 이유: 나중에 투어 내용이 크게 바뀌면 버전을 올려 다시 보여줄 수
        # 있다. bool 하나면 그때 전 사용자의 행을 건드려야 한다.
        sa.Column("tour_seen_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # 끝까지 본 것과 건너뛴 것은 다른 사건이다 — 둘 다 '다시 안 뜬다'는 같지만,
        # 얼마나 많은 사람이 도중에 나갔는지는 투어를 고칠 때 유일한 단서다.
        sa.Column("tour_skipped", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("tour_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "saved_views",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        # 화면 키(registry.js 의 config.key 와 같은 값: 'audit', 'jobs', 'notifications'…).
        sa.Column("screen_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        # URL 쿼리 문자열. 모듈 docstring 참조.
        sa.Column("query", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "screen_key", "name", name="uq_saved_views_user_screen_name"
        ),
    )
    op.create_index(
        "ix_saved_views_user_screen", "saved_views", ["user_id", "screen_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_saved_views_user_screen", table_name="saved_views")
    op.drop_table("saved_views")
    op.drop_table("user_preferences")
