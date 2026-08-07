"""알림 audience 구분 - 팀(사용자) 알림과 관리자 알림을 한 벨에서도 구분한다 (0051)

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-07

## 무엇을 고치는가

`notifications.type` 은 자유 텍스트라 "이 알림이 누구를 위한 것인가"를 담지 못했다.
`app/notifications/service.py` 의 `notify_user`/`notify_admins`/`notify_approvers`/
`notify_active_users` 는 수신자는 다르게 골랐지만("관리자 전원" vs "그 사람 한 명") 그
사실을 행에 남기지 않았다 — 그래서 관리자이자 사용자인 사람의 알림 벨에는 자기 티켓
배정 알림과 "백업이 실패했다" 같은 운영 알림이 구분 없이 섞여 나왔다.

## `audience` 를 NOT NULL + server_default 로 만드는 이유

0048(`board_posts.kind`)과 같은 판단이다. nullable 로 두면 새 화면의 `audience = 'user'`
필터가 **이 컬럼이 생기기 전 알림(NULL)을 하나도 못 고른다** — 배포 다음 날 기존 알림이
전부 "관리" 도 "내 업무" 도 아닌 유령 취급을 받는다. `org_id`(OrgScopedMixin)처럼 서비스
계층에서 채우는 nullable 방식도 검토했지만, 그 방식은 "값이 없다 = 아직 조직이 배정 안
됐다"처럼 **NULL 자체에 뜻이 있을 때**를 위한 것이다. audience 는 모든 알림에 뜻이 있고
값이 정확히 둘뿐이라(닫힌 집합) NOT NULL 이 맞는 선택이다.

SQLite 에서 `ALTER TABLE ADD COLUMN ... NOT NULL` 은 기본값 없이는 실패하므로
`server_default` 를 반드시 같이 건다. 그 위에 UPDATE 백필을 한 번 더 돌리는 이유도
0048 과 같다 — server_default 가 채우는 것은 SQLite 의 동작이고 다른 엔진에서 같다는
보장이 없어, 두 줄로 확실히 해 둔다(멱등하다).

## 기존 행을 어떻게 나누는가 - type 만으로는 부족해 title 도 함께 본다

기본값은 'user' 다: 대부분의 알림(티켓 배정, 문서 생성, 채팅 멘션, 승인 결과 통보 등)은
그 사람 개인의 일이다.

`type` 값 자체가 관리자 전용으로만 쓰이는 것들은 그대로 'admin' 으로 옮긴다:
`backup_failed`(`app/backups/service.py`, `notify_admins`만 사용),
`runner_unavailable`(`app/runners/service.py`, `notify_admins`만 사용).

**`account_locked` 와 `approval_requested` 는 type 하나가 두 채널에 겹쳐 쓰인다** —
같은 사건에 대해 잠긴 본인에게 한 통("내 계정" = user), 관리자 전원에게 한 통씩
("처리해야 할 일" = admin) 이 따로 만들어진다(`app/auth/router.py`,
`app/jobs/handlers/document_generate.py` vs `app/approvals/service.py`). type 만 보고
가르면 둘 중 하나가 반드시 틀린다. 두 발송 지점이 **제목 문구를 서로 다르게 굳혀 놨으므로**
그 문구로 가른다:
  * `계정 잠금 발생: {email}` 로 시작 → 관리자에게 간 통지 → admin
  * 그 외 `account_locked`(본인에게 간 "로그인 실패 누적으로 계정이 잠겼습니다") → user
  * `문서 발행 승인 요청`(정확히 일치, 문서 생성 완료 후 관리자 승인 요청) → admin
  * 그 외 `approval_requested`(`승인 요청: {request_type}` 로 시작, 결재자 개인 할 일) → user

## `job_failed` 를 admin 으로 옮기지 않는 이유 (이 저장소 실제 동작과의 차이를 밝혀 둔다)

작업 실패류를 관리자용으로 보는 것이 직관적으로 보일 수 있지만, `app/jobs/worker.py` 를
확인하면 `job_failed` 는 **그 작업을 요청한 사용자 한 명**(`job.user_id`)에게만 간다 —
관리자 전원에게 팬아웃되는 경로가 코드에 없다(`notify_admins` 호출부 전체를 훑어도
`job_failed` 는 없다). "내 요청이 실패했다"는 그 사람의 개인 알림이므로 여기서는 'user'
기본값을 그대로 둔다. 반대로 옮기면 일반 사용자가 자기 작업 실패 알림을 어디서도 못 찾는
사고가 된다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_TABLE = "notifications"
_AUDIENCE_USER = "user"
_AUDIENCE_ADMIN = "admin"

# type 값 자체가 관리자 전용으로만 쓰이는 것들 (app/notifications/service.py의
# _ADMIN_ONLY_TYPES와 같은 목록 — 마이그레이션은 적용된 뒤 불변이어야 하므로 import 대신
# 값을 못박는다, 0050과 같은 관례).
_ADMIN_ONLY_TYPES = ("backup_failed", "runner_unavailable")

# type 하나가 user/admin 두 채널에 겹쳐 쓰이는 것들 — 제목 문구로 가른다(모듈 docstring 참조).
_ADMIN_TITLE_PATTERNS = (
    ("account_locked", "계정 잠금 발생:%"),
    ("approval_requested", "문서 발행 승인 요청"),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(_TABLE)

    if "audience" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "audience", sa.String(16), nullable=False, server_default=_AUDIENCE_USER
            ),
        )
        op.create_index("ix_notifications_audience", _TABLE, ["audience"])

    # 기존 행 백필. server_default로 이미 채워졌더라도 멱등하다.
    op.execute(
        sa.text(f"UPDATE {_TABLE} SET audience = :user WHERE audience IS NULL").bindparams(
            user=_AUDIENCE_USER
        )
    )

    for type_ in _ADMIN_ONLY_TYPES:
        op.execute(
            sa.text(f"UPDATE {_TABLE} SET audience = :admin WHERE type = :type").bindparams(
                admin=_AUDIENCE_ADMIN, type=type_
            )
        )

    for type_, pattern in _ADMIN_TITLE_PATTERNS:
        op.execute(
            sa.text(
                f"UPDATE {_TABLE} SET audience = :admin"
                f" WHERE type = :type AND title LIKE :pattern"
            ).bindparams(admin=_AUDIENCE_ADMIN, type=type_, pattern=pattern)
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(_TABLE)
    if "audience" not in existing:
        return
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    if "ix_notifications_audience" in indexes:
        op.drop_index("ix_notifications_audience", table_name=_TABLE)
    op.drop_column(_TABLE, "audience")
