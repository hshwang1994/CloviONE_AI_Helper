"""프로젝트 Notion 양방향 동기화 컬럼과 동기화 싱글턴 (0045)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 stdout 에 찍고, Windows
콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다(0044 와 같은 이유).

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-06

## 왜 Notion 값을 **별도 컬럼**에 담는가

`projects.progress_pct` 는 앱이 다시 계산한 값이고, Notion 의 `티켓 진행률`(rollup) /
`프로젝트 진행률`(formula)은 **취소한 티켓을 완료로 센다**(0044 docstring, app/projects/
progress.py). 그 값을 `progress_pct` 에 받아 적으면 틀린 숫자가 앱의 정본이 된다.

그렇다고 버리지도 않는다. Notion 화면과 포털 화면에 서로 다른 진행률이 뜨는 것은 **정상
상태**이고, 그때 한쪽 숫자만 보이면 사용자는 "포털이 틀렸다"고 결론 내린다. 두 값을 나란히
놓고 무엇을 어떻게 셌는지 말할 수 있어야 둘 다 믿을 수 있다. 그래서 `notion_progress_pct`
로 따로 담는다.

`notion_status` 도 같은 이유다. Notion 진행 상태 어휘(백로그/계획 중/진행 중/차질/완료/취소)와
앱의 `status`(planned/active/on_hold/done)는 **서로 다른 축**이라 1:1 로 겹치지 않는다.
'차질' 은 앱에 없고 'on_hold' 는 Notion 에 없다. 억지로 맞추면 위험 신호('차질')가 '진행 중'
으로 뭉개져 **가장 봐야 할 상태가 화면에서 사라진다.** 원문을 그대로 담고, 포털에서 그
값을 고치면 그대로 Notion 에 되돌려 보낸다.

## 왜 `notion_missing_at` 인가 (지우지 않는다)

Notion 응답에서 사라진 프로젝트를 지우면 CASCADE 로 `project_members` /
`project_milestones` / `project_health_snapshots` / `project_weekly_reports` 가 함께
사라진다. **넷 다 Notion 에 없다** - 앱에만 있는 사용자 데이터라 재동기화로 돌아오지 않는다.
티켓(0043)이 댓글·첨부 때문에 소프트 프룬으로 바뀐 것과 같은 사정이고, 프로젝트 쪽이 더
나쁘다: 프로젝트 행 자체가 앱 정본(부서·코드·목표)이라 Notion 이 한 회차 깜빡였다고 앱의
정본을 지우는 것이 된다.

그래서 티켓과 **다른 점**도 하나 있다. 티켓은 표시된 행을 목록에서 감추지만(미러니까),
프로젝트는 감추지 않는다. 감추면 Notion 이 깜빡인 순간 포털의 마일스톤·주간 리포트가
통째로 화면에서 사라진다. 표시는 "Notion 짝이 안 보인다"는 사실을 화면이 말하기 위한
배지일 뿐이고, `app/core/retention.py` 도 이 표는 건드리지 않는다.

## 왜 `notion_sync_error` 를 행에 두는가

push(앱 → Notion)가 실패해도 로컬 저장은 롤백하지 않는다. 롤백하면 사용자가 방금 고친
이름·기간이 함께 사라지는데, 그건 Notion 장애의 대가를 사용자 입력으로 치르게 하는 것이다
(`ticket_cache.body_sync_error` 가 같은 판단을 기록한다). 대신 어긋난 상태를 여기 적어
상세 화면이 "저장됨, Notion 반영 실패" 를 말하게 한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_PROJECTS = "projects"
_MISSING_IDX = "ix_projects_notion_missing_at"

# (컬럼, 타입). 0044 가 만든 것에 **더하기만** 한다.
_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    # Notion 이 계산한 진행률(0..100). 참고값이지 정본이 아니다(모듈 docstring).
    ("notion_progress_pct", sa.Float()),
    # Notion 진행 상태 원문. 앱의 status 와 다른 축이라 별도 컬럼이다.
    ("notion_status", sa.String(64)),
    # 담당자(정)의 Notion person id 목록(NAMES_SEP 로 감싼 다중값).
    # 앱 사용자로 해석되지 않는 사람(포털 미가입·매핑 미검증)이 있어도 값을 잃지 않으려고
    # 원문을 그대로 둔다. ticket_cache.assignee_notion_ids 와 같은 규약이다.
    ("notion_owner_ids", sa.Text()),
    # "이번 회차 Notion 응답에서 안 보였다". 지우지 않고 표시만 한다(모듈 docstring).
    ("notion_missing_at", sa.DateTime()),
    ("notion_last_edited", sa.String(40)),
    # 마지막으로 Notion 과 맞춘 시각. updated_at 과 다르다 - 저쪽은 앱 안에서의 변경 시각이다.
    ("notion_synced_at", sa.DateTime()),
    ("notion_sync_error", sa.Text()),
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _table_names()

    if _PROJECTS in tables:
        existing = _columns(_PROJECTS)
        for name, type_ in _NEW_COLUMNS:
            if name not in existing:
                # 전부 nullable 이다. NULL 은 "아직 Notion 과 맞춘 적이 없다" 는 뜻이고,
                # 0 이나 빈 문자열로 채우면 포털 전용 프로젝트가 'Notion 진행률 0%' 로 보인다.
                op.add_column(_PROJECTS, sa.Column(name, type_, nullable=True))
        if _MISSING_IDX not in _indexes(_PROJECTS):
            # 동기화가 매 회차 "표시되지 않은 행" 만 후보로 뽑는다. 인덱스가 없으면
            # 프로젝트가 늘수록 그 질의가 풀스캔이 된다.
            op.create_index(_MISSING_IDX, _PROJECTS, ["notion_missing_at"])

    if "project_sync_state" not in tables:
        # 단일 행 싱글턴. ticket_sync_state 와 **같은 모양**으로 둔다 - 운영자가 두 화면에서
        # 같은 단어(ok/error, last_success_at, truncated, pruned_count)를 본다.
        op.create_table(
            "project_sync_state",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column(
                "project_count", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            # 상한에 걸려 일부만 받아온 회차. True 면 prune 을 건너뛰었다는 뜻이다.
            sa.Column(
                "truncated", sa.Boolean(), nullable=False, server_default=sa.text("0")
            ),
            # 실제로 **표시한** 건수(소프트 프룬이라 삭제 건수가 아니다).
            sa.Column(
                "pruned_count", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    tables = _table_names()

    if "project_sync_state" in tables:
        op.drop_table("project_sync_state")

    if _PROJECTS in tables:
        if _MISSING_IDX in _indexes(_PROJECTS):
            op.drop_index(_MISSING_IDX, table_name=_PROJECTS)
        existing = _columns(_PROJECTS)
        for name, _type in reversed(_NEW_COLUMNS):
            if name in existing:
                op.drop_column(_PROJECTS, name)
