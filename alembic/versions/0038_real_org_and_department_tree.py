"""조직명을 실제 조직으로 되돌리고, 부서 계층을 실제 구조로 만든다.

## 무엇이 잘못됐나

0034 가 리브랜딩을 하면서 **제품명과 조직명을 같은 것으로 취급**해 둘 다 "ClovirAssist" 로
바꿨다. 제품명은 맞지만 조직명은 아니다 — 이 포털을 쓰는 조직은 **굿모닝아이텍** 이고
"ClovirAssist" 는 그들이 쓰는 제품의 이름이다. 화면에 조직 이름이 나오는 자리마다
회사 이름 대신 제품 이름이 찍혔다(사용자 지적 P5).

부서도 마찬가지로 실제 구조가 아니다. 실제는 **브로드컴사업본부 > ClovirONE팀** 인데
운영에는 `ClovirONE팀` 하나만 있고 상위 부서가 없다.

## 왜 0034 의 downgrade 를 쓰지 않는가

`0034.downgrade()` 는 조직명을 `ClovirONE` 으로 되돌린다 — 굿모닝아이텍이 아니다. 그리고
**제품명까지 함께 되돌려** 로그인 화면이 "ClovirONE 업무 도우미" 가 되고,
`scripts/verify_deploy.sh` 가 로그인 화면에서 "ClovirAssist" 를 찾으므로 배포 검증이 실패한다.
고쳐야 할 것은 조직명 하나뿐이므로 그것만 건드린다.

`app/org/constants.py` 의 `DEFAULT_ORG_NAME` 도 같이 고쳤다. 그러지 않으면 다음 시드나
새 환경 구축에서 잘못된 이름이 되살아난다.

## 되돌릴 때

downgrade 는 조직명만 "ClovirAssist" 로 되돌린다. 부서 계층은 **건드리지 않는다** —
실제 조직 구조를 마이그레이션 되감기로 지우는 것은 데이터 손실이고, 이 마이그레이션이
만든 것인지 사람이 만든 것인지 구분할 방법도 없다.

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_WRONG_ORG_NAME = "ClovirAssist"   # 제품명이 조직명 자리에 들어와 있던 값
_REAL_ORG_NAME = "굿모닝아이텍"

_PARENT_DEPT = "브로드컴사업본부"
_CHILD_DEPT = "ClovirONE팀"


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ── 1) 조직명 ────────────────────────────────────────────────────────────
    # 이름으로 찾는다(고정 id 로 찍지 않는다) — 이미 손으로 고쳐 둔 환경을 덮지 않는다.
    bind.execute(
        sa.text("UPDATE organizations SET name = :real WHERE name = :wrong"),
        {"real": _REAL_ORG_NAME, "wrong": _WRONG_ORG_NAME},
    )

    # ── 2) 부서 계층 ─────────────────────────────────────────────────────────
    # `ClovirONE팀` 이 있는 환경에서만 손댄다. 테스트 데이터만 있는 개발 DB 에서는
    # 아무 일도 하지 않는다 — 없는 조직 구조를 만들어 넣지 않는다.
    child = bind.execute(
        sa.text("SELECT id, org_id, parent_id FROM departments WHERE name = :n"),
        {"n": _CHILD_DEPT},
    ).fetchone()
    if child is None:
        return
    if child.parent_id:
        return  # 이미 상위가 있다. 사람이 정한 구조를 덮지 않는다.

    parent = bind.execute(
        sa.text("SELECT id FROM departments WHERE name = :n"), {"n": _PARENT_DEPT}
    ).fetchone()
    parent_id = parent.id if parent else str(uuid.uuid4())
    if parent is None:
        bind.execute(
            # 컬럼 목록은 실제 스키마 그대로다: id, name, active, created_at, org_id, parent_id.
            # (`updated_at` 은 이 표에 없다 — 모델에 있다고 가정하고 쓰면 여기서 터진다.)
            sa.text(
                "INSERT INTO departments (id, name, active, org_id, created_at) "
                "VALUES (:id, :name, 1, :org, :now)"
            ),
            {"id": parent_id, "name": _PARENT_DEPT, "org": child.org_id, "now": now},
        )
    bind.execute(
        sa.text("UPDATE departments SET parent_id = :p WHERE id = :id"),
        {"p": parent_id, "id": child.id},
    )


def downgrade() -> None:
    # 조직명만 되돌린다. 부서 계층은 그대로 둔다(위 주석 참조).
    op.get_bind().execute(
        sa.text("UPDATE organizations SET name = :wrong WHERE name = :real"),
        {"real": _REAL_ORG_NAME, "wrong": _WRONG_ORG_NAME},
    )
