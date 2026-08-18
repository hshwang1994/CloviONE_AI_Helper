"""Resource Ownership 과 사용자 소속 종류 — 권한 축을 하나로 모은다.

## 무엇을 고치는가

이 앱은 자원마다 소속을 정하는 축이 달랐다. 티켓은 **담당자**의 부서, 문서는 **작성자**의
부서, 프로젝트만 자기 `dept_id` 를 썼다. 세 축은 서로 다른 답을 내고, 그래서 "프로젝트는
보이는데 그 프로젝트의 티켓은 안 보인다" 가 정상처럼 존재했다. 게다가 사람 축은 **사람이
부서를 옮기면 과거 자원의 소속이 따라 움직인다.**

여기서 세 컬럼 묶음을 심어 축을 하나로 모은다. 자원이 자기 소속을 스스로 들고, 사람의
현재 소속과 무관해진다(`app/core/ownership.py`).

## 1) `users.membership_kind`

`department_id IS NULL` 하나로는 서로 다른 두 사실을 구별할 수 없다: "본부 직속이라 팀이
없다" 와 "아직 부서를 안 정했다". 예전 코드는 둘을 똑같이 취급하고 **전역**으로 폴백해서,
부서를 안 정한 계정이 전 포털을 봤다.

backfill 은 **추측하지 않는다**: 부서가 있으면 `department`, 없으면 `unassigned` 다.
`unassigned` 는 조직 데이터를 못 본다(fail-closed). 조직 직속인 사람을 `organization` 으로
바꾸는 것은 사람의 판단이고, 관리자 진단 화면이 그 대상 목록과 일괄 지정을 제공한다.

## 2) `ticket_cache.project_uid` / `project_link`

티켓의 소속은 **프로젝트**다. `project_ids`(Notion relation 다중값 문자열)는 외부 소스의
원본이고, 그것을 Portal 프로젝트 하나로 해석한 결과를 `project_uid` 에 둔다.
`project_link` 는 그 해석이 어떻게 끝났는지를 남긴다:

    ok          정확히 1개, Portal 프로젝트로 해석됨 → 그 프로젝트의 ACL 을 따른다
    missing     relation 0개 → 정합성 오류
    ambiguous   relation 2개 이상 → 임의로 하나 고르지 않는다
    unresolved  1개인데 Portal 에 짝이 없음 → 아직 프로젝트 동기화가 안 됐거나 지워졌다

`ok` 가 아니면 fail-closed 다(전역 관리자만). 임의로 하나를 고르면 그 티켓이 남의 부서로
새고, 그 사고는 아무도 신고하지 않는다.

값 채우기는 여기서 하지 않는다 — Notion page id ↔ Portal 프로젝트 매칭은 `projects` 표를
읽어야 하고 그 표는 동기화가 채운다. `app/tickets/sync.py` 가 회차마다 해석한다. 컬럼
기본값이 `unresolved` 이므로 해석 전에는 안전한 쪽(fail-closed)에 있다.

## 3) `document_cache.owner_kind` / `owner_dept_id` / `owner_project_id`

**외부 소스에 Portal 조직 컬럼을 요구하지 않는다.** Notion(또는 앞으로 무엇이든)은 콘텐츠의
정본이고, "이 문서가 어느 조직/부서/프로젝트 것인가" 는 Portal 이 정본이다. 그래서 이
세 컬럼은 `app/team_docs/sync.py` 가 **절대 건드리지 않는다**(`restricted`(0057)·
`classification_manual`(0018)과 같은 자리다). 소스가 다른 시스템으로 바뀌어도 이 관계는
그대로 남는다.

기존 문서 이관: 실제 업무 기준으로 기존 팀 문서는 `ClovirONE팀` 소유다. 그 부서를 **이름으로
한 번 찾아** 그 **내부 id** 를 심는다 — 이름은 여기서 입력값으로만 쓰이고, 이후 권한 계산은
id 로만 한다(부서명이 바뀌거나 상위 부서가 새로 생겨도 연결이 안 끊긴다). 그 부서가 없는
환경(로컬·CI)에서는 아무 것도 하지 않는다.

멱등: `owner_kind = 'unset'` 인 행만 건드린다. 두 번 돌려도 이미 지정된 소유가 덮이지 않는다.

## 4) `ticket_cache.scope_dept_id` 제거

0044 가 "담당자의 부서로 유도할 예정" 이라며 열어 둔 문이다. 실측 non-null 0건, 읽는 코드
0건이고, 이제 티켓 소속은 프로젝트가 정하므로 이 문은 영영 안 쓴다. 남겨 두면 다음 사람이
"티켓에도 부서 축이 있구나" 로 읽는다.

Revision ID: 0060
Revises: 0059
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_CLOVIRONE_DEPT_NAME = "ClovirONE팀"


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1) users.membership_kind ─────────────────────────────────────────────
    if "membership_kind" not in _cols("users"):
        op.add_column(
            "users",
            sa.Column(
                "membership_kind", sa.String(16),
                nullable=False, server_default="unassigned",
            ),
        )
        op.create_index("ix_users_membership_kind", "users", ["membership_kind"])
        # 부서가 있으면 그 사실 그대로 'department'. 없으면 추측하지 않고 'unassigned'.
        bind.execute(
            sa.text(
                "UPDATE users SET membership_kind = 'department' "
                "WHERE department_id IS NOT NULL AND department_id != ''"
            )
        )

    # ── 2) ticket_cache: 프로젝트 연결 추가 + 죽은 컬럼 제거 ──────────────────
    #
    # SQLite 는 `ALTER TABLE ADD COLUMN` 에 외래키를 붙일 수 없다(0024 가 같은 벽을 만났다).
    # 배치 모드는 테이블을 다시 만들어 그것을 해낸다 — 어차피 아래에서 `scope_dept_id` 도
    # 지워야 하므로, **재생성을 한 번으로 묶는다**(두 번 하면 큰 표를 두 번 복사한다).
    ticket_cols = _cols("ticket_cache")
    ticket_adds = [c for c in ("project_uid", "project_link") if c not in ticket_cols]
    drop_scope_dept = "scope_dept_id" in ticket_cols
    if ticket_adds or drop_scope_dept:
        if drop_scope_dept:
            # 배치 모드는 기존 인덱스를 **반영해서 다시 만든다** — 지울 컬럼의 인덱스가
            # 남아 있으면 재생성 단계에서 "no such column" 으로 죽는다. 먼저 치운다.
            existing = {
                i["name"] for i in sa.inspect(bind).get_indexes("ticket_cache")
            }
            if "ix_ticket_cache_scope_dept_id" in existing:
                op.drop_index("ix_ticket_cache_scope_dept_id", table_name="ticket_cache")
        with op.batch_alter_table("ticket_cache") as batch:
            if "project_uid" in ticket_adds:
                batch.add_column(sa.Column("project_uid", sa.String(36), nullable=True))
            if "project_link" in ticket_adds:
                batch.add_column(
                    sa.Column(
                        "project_link", sa.String(16),
                        nullable=False, server_default="unresolved",
                    )
                )
            if "project_uid" in ticket_adds:
                batch.create_foreign_key(
                    "fk_ticket_cache_project_uid", "projects", ["project_uid"], ["id"]
                )
            if drop_scope_dept:
                batch.drop_column("scope_dept_id")
        if "project_uid" in ticket_adds:
            op.create_index("ix_ticket_cache_project_uid", "ticket_cache", ["project_uid"])
        if "project_link" in ticket_adds:
            op.create_index("ix_ticket_cache_project_link", "ticket_cache", ["project_link"])

    # ── 3) document_cache ownership ──────────────────────────────────────────
    doc_cols = _cols("document_cache")
    doc_adds = [
        c for c in ("owner_kind", "owner_dept_id", "owner_project_id") if c not in doc_cols
    ]
    if doc_adds:
        with op.batch_alter_table("document_cache") as batch:
            if "owner_kind" in doc_adds:
                batch.add_column(
                    sa.Column(
                        "owner_kind", sa.String(16),
                        nullable=False, server_default="unset",
                    )
                )
            if "owner_dept_id" in doc_adds:
                batch.add_column(sa.Column("owner_dept_id", sa.String(36), nullable=True))
                batch.create_foreign_key(
                    "fk_document_cache_owner_dept_id", "departments",
                    ["owner_dept_id"], ["id"],
                )
            if "owner_project_id" in doc_adds:
                batch.add_column(sa.Column("owner_project_id", sa.String(36), nullable=True))
                batch.create_foreign_key(
                    "fk_document_cache_owner_project_id", "projects",
                    ["owner_project_id"], ["id"],
                )
        for name in doc_adds:
            op.create_index(f"ix_document_cache_{name}", "document_cache", [name])

    # 외부 relation **id** 미러. 이름(`project_names`)만으로는 Portal 프로젝트와 정확히
    # 이을 수 없다 — 이름은 바뀌고 중복될 수 있다. 소유 컬럼과 달리 이것은 콘텐츠 미러라
    # 동기화가 채운다(그래서 FK 가 없다 — 외부 시스템의 키다).
    if "project_external_ids" not in doc_cols:
        op.add_column(
            "document_cache",
            sa.Column("project_external_ids", sa.Text(), nullable=False, server_default=""),
        )

    # 기존 문서 이관 — 이름으로 한 번 찾고, 이후로는 id 만 쓴다. 멱등(unset 만 대상).
    dept = bind.execute(
        sa.text("SELECT id FROM departments WHERE name = :n ORDER BY id LIMIT 1"),
        {"n": _CLOVIRONE_DEPT_NAME},
    ).fetchone()
    if dept is not None:
        bind.execute(
            sa.text(
                "UPDATE document_cache SET owner_kind = 'department', owner_dept_id = :d "
                "WHERE owner_kind = 'unset'"
            ),
            {"d": dept.id},
        )


def downgrade() -> None:
    """되돌리기는 **컬럼만** 되돌린다.

    이관으로 채운 `owner_dept_id` 값은 컬럼과 함께 사라지는데, 그것은 되돌리기의 정의상
    맞다 — 컬럼 자체가 없던 상태로 가는 것이다. 반면 사람이 그 뒤에 손으로 지정한 소유도
    함께 사라지므로, 운영 DB 에서 이 downgrade 를 도는 것은 데이터 손실이다(0024 가 같은
    경고를 남겼다).
    """
    doc_cols = _cols("document_cache")
    doc_drops = [
        c for c in ("owner_project_id", "owner_dept_id", "owner_kind") if c in doc_cols
    ]
    if "project_external_ids" in doc_cols:
        with op.batch_alter_table("document_cache") as batch:
            batch.drop_column("project_external_ids")
        doc_cols = _cols("document_cache")
    if doc_drops:
        for name in doc_drops:
            op.drop_index(f"ix_document_cache_{name}", table_name="document_cache")
        with op.batch_alter_table("document_cache") as batch:
            for name in doc_drops:
                batch.drop_column(name)

    ticket_cols = _cols("ticket_cache")
    ticket_drops = [c for c in ("project_link", "project_uid") if c in ticket_cols]
    if ticket_drops or "scope_dept_id" not in ticket_cols:
        for name in ticket_drops:
            op.drop_index(f"ix_ticket_cache_{name}", table_name="ticket_cache")
        with op.batch_alter_table("ticket_cache") as batch:
            for name in ticket_drops:
                batch.drop_column(name)
            if "scope_dept_id" not in ticket_cols:
                batch.add_column(sa.Column("scope_dept_id", sa.String(36), nullable=True))
        # 인덱스도 **되돌린다**. 컬럼만 살리면 0033 의 downgrade 가 없는 인덱스를 지우려다
        # 죽는다 — 되돌리기 사슬은 한 칸만 어긋나도 그 아래 전부가 못 내려간다.
        if "scope_dept_id" not in ticket_cols:
            op.create_index(
                "ix_ticket_cache_scope_dept_id", "ticket_cache", ["scope_dept_id"]
            )

    if "membership_kind" in _cols("users"):
        op.drop_index("ix_users_membership_kind", table_name="users")
        with op.batch_alter_table("users") as batch:
            batch.drop_column("membership_kind")
