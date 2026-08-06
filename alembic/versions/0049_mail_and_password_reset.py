"""mail_deliveries + password_reset_tokens (9-9 P4)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 stdout 에 찍고, Windows
콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다(0044, 0045, 0047 과 같은 이유).

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-06

## 왜 표가 둘인가

### mail_deliveries - "보내려 했다" 의 기록

메일 실패가 본 작업을 막지 않는 것은 이 저장소의 기존 규칙이다(알림 실패와 같다).
그런데 실패를 **어디에도 안 남기면** "왜 안 왔지" 에 아무도 답할 수 없다. 잡 큐
(`jobs.last_error`)만으로는 부족하다: 설정이 아예 없어 잡을 만들지도 않은 경우가 있고
(status='unconfigured'), 그 경우가 정확히 사용자가 제일 오래 기다리는 경우다.

**본문(body)을 저장하지 않는다.** 비밀번호 재설정 메일 본문에는 1회용 토큰이 들어간다.
본문을 여기(또는 `jobs.payload_json`)에 담는 순간 토큰 평문이 DB 에 앉는다 - 이 작업이
막으려는 바로 그것이다. 대신 `kind` + `params_json`(비밀 아닌 값만) 을 두고, 워커가
발송 직전에 본문을 만든다.

### password_reset_tokens - 해시만

세션 토큰(0001 의 `sessions.token_hash`)과 같은 규약이다: 원문은 메일로만 나가고 DB 에는
SHA-256 해시만 남는다. `used_at` 이 1회용을, `expires_at` 이 만료를 담당한다.
행을 지우는 대신 `used_at` 을 찍는 이유는, 지워 버리면 "이미 쓴 토큰" 과 "처음 보는 토큰"
이 구별되지 않아 재사용 시도를 셀 수도 없기 때문이다(정리는 만료 뒤 일괄로 한다).

`token_hash` 에 UNIQUE 를 거는 이유: 해시 충돌이 아니라 **삽입 버그**를 잡기 위해서다.
같은 해시가 두 행이면 소비(1회용) 판정이 어느 행을 보느냐에 따라 갈린다.

시드 없음 - 새 표 둘뿐이라 타임스탬프 함정(SQLite STRFTIME '%f' 금지)에 걸릴 일이 없다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_MAIL = "mail_deliveries"
_TOKENS = "password_reset_tokens"

_MAIL_INDEXES = (
    ("ix_mail_deliveries_kind", ["kind"]),
    ("ix_mail_deliveries_status", ["status"]),
    ("ix_mail_deliveries_created_at", ["created_at"]),
)
_TOKEN_INDEXES = (
    ("ix_password_reset_tokens_user_id", ["user_id"]),
    ("ix_password_reset_tokens_expires_at", ["expires_at"]),
)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = set(insp.get_table_names())

    if _MAIL not in existing:
        op.create_table(
            _MAIL,
            sa.Column("id", sa.String(36), primary_key=True),
            # 어떤 메일인가. 본문 렌더러를 고르는 키이기도 하다(app/mail/renderers.py).
            sa.Column("kind", sa.String(64), nullable=False),
            sa.Column("to_email", sa.String(320), nullable=False),
            sa.Column("subject", sa.String(300), nullable=False),
            # queued | sent | failed | unconfigured
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            # 본문이 아니라 **본문을 만들 재료**다. 비밀은 절대 들어가지 않는다.
            sa.Column("params_json", sa.Text(), nullable=False, server_default="{}"),
            # 발송을 맡은 잡. 설정이 없어 큐에 넣지 못했으면 NULL 이다.
            sa.Column("job_id", sa.String(36), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for name, cols in _MAIL_INDEXES:
            op.create_index(name, _MAIL, cols)

    if _TOKENS not in existing:
        op.create_table(
            _TOKENS,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            # 원문은 여기 없다. 메일로만 나간다.
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            # 'reset' | 'invite' - 문구만 다르고 규칙(1회용, 만료)은 같다.
            sa.Column("purpose", sa.String(32), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_ip", sa.String(64), nullable=True),
        )
        for name, cols in _TOKEN_INDEXES:
            op.create_index(name, _TOKENS, cols)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = set(insp.get_table_names())
    for table, indexes in ((_TOKENS, _TOKEN_INDEXES), (_MAIL, _MAIL_INDEXES)):
        if table not in existing:
            continue
        present = {i["name"] for i in insp.get_indexes(table)}
        for name, _cols in indexes:
            if name in present:
                op.drop_index(name, table_name=table)
        op.drop_table(table)
