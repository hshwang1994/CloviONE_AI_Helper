"""공지 삭제가 닫힘 기록을 고아로 남기던 문제 — FK + CASCADE (UB-19)

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-11

## 무엇이 문제였나

`announcement_dismissals.announcement_id`는 FK가 아니라 그냥 문자열이었다. 관리자가
공지를 삭제해도(정상적인 CRUD 경로, `DELETE /api/admin/announcements/{id}`) 그 공지를
닫았던 사용자들의 `AnnouncementDismissal` 행은 그대로 남는다 - 가리키는 대상이 없는
고아 행이다.

이게 왜 나쁜가 - 이 표는 폴링마다(배너를 보여줄지 판정하려고, `service.py::for_user`)
**로그인한 사용자의 닫힘 집합 전체**를 읽는다. 그 집합에는 오래전에 지워진 공지의 닫힘
기록까지 영원히 남아 있어 - 실제로 아무 판정에도 안 쓰이는데(그 공지 자체가 없으니
`row.id not in dismissed` 비교의 `row` 쪽이 애초에 없다) 매 폴링 읽기 비용만 늘린다.
사용자가 활발히 공지를 닫아 갈수록, 그리고 공지가 자주 교체될수록 이 집합은 무한히
자란다.

## 사용자(users)와 다른 이유

프로젝트 전체에서 `User` 행은 하드 삭제 경로가 없다(퇴사 처리는 비활성화+보관, `db.delete`
가 아니다 - 확인함, grep으로 전체 재확인). 반면 `Announcement`는 평범한 CRUD로 삭제된다
(`app/announcements/router.py::delete_announcement`가 `db.delete(row)`를 그냥 부른다) -
그래서 이 고아 문제는 실제로 일어난다(UB-20처럼 전제 자체가 재현 안 되는 경우가 아니다).

## 배포 전 기존 고아 정리

이미 삭제된 공지를 가리키는 닫힘 행이 있으면 FK 생성 자체가 실패하지는 않는다(SQLite는
기존 데이터를 새 FK로 소급 검사하지 않는다 - alembic env.py가 `PRAGMA foreign_keys`를
안 켜 두므로). 하지만 그 행 자체가 이미 의미 없는 쓰레기이므로(0050의 org_id 고아와
달리 되살릴 값이 없다 - "누가 이미 없는 공지를 닫았었다"는 사실은 아무 화면에도 안
쓰인다) 조건 없이 지운다. 지운 건수는 로그로 남긴다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_FK_NAME = "fk_announcement_dismissals_announcement_id"


def upgrade() -> None:
    bind = op.get_bind()
    if "announcement_dismissals" not in sa.inspect(bind).get_table_names():
        return
    result = bind.execute(
        sa.text(
            "DELETE FROM announcement_dismissals "
            "WHERE announcement_id NOT IN (SELECT id FROM announcements)"
        )
    )
    if result.rowcount:
        logger.warning(
            "0055: 이미 삭제된 공지를 가리키던 고아 닫힘 기록 %d건을 지웠다", result.rowcount
        )
    with op.batch_alter_table("announcement_dismissals", recreate="always") as batch:
        batch.create_foreign_key(
            _FK_NAME, "announcements", ["announcement_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "announcement_dismissals" not in sa.inspect(bind).get_table_names():
        return
    with op.batch_alter_table("announcement_dismissals", recreate="always") as batch:
        batch.drop_constraint(_FK_NAME, type_="foreignkey")
