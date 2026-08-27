"""기본 아바타와 자르기 — 사람을 이름으로만 부르지 않는다.

Revision ID: 0019_avatar_default_and_crop
Revises: 0018_status_signal_axis
Create Date: 2026-08-27

## 무엇이 문제였나

사진을 올린 사람에게만 아바타가 있었다. 나머지는 목록에서도 채팅에서도 이름 글자
하나였고, 화면 코드 셋이 각각 「사진이 없으면 아무것도 안 그린다」를 적고 있었다.
그래서 같은 목록에서 어떤 줄에는 원이 있고 어떤 줄에는 없어 왼쪽 모서리가 들쭉날쭉했다.

## 이 회차가 만드는 자리

**사진과 기본 그림은 다른 축이다.** 사진을 지워도 이 사람이 고른 기본 그림은 남아야
하고, 기본 그림을 골라 뒀다고 사진이 사라지면 안 된다. 그래서 컬럼을 나눈다.

    avatar_source        default | uploaded — 지금 무엇을 보여 주는가
    avatar_default_key   고른 기본 그림. 비어 있으면 사용자 id 로 안정 배정한다
    avatar_thumb_name    표시용 썸네일. 원본과 **다른 파일**이다
    avatar_crop_x/y/zoom 원본의 어느 사각형을 잘랐는가 (짧은 변을 1.0 으로 본 비율)

썸네일을 따로 두는 이유: 원본을 매번 줄여 보내면 20px 목록 한 줄에 몇 MB 가 실린다.
원본을 남겨 두는 이유: 다시 자를 때 원본이 없으면 이미 자른 그림을 또 자르게 되고
그때마다 화질이 떨어진다.

자르기를 픽셀이 아니라 비율로 적는 이유: 원본 해상도가 바뀌면 픽셀 좌표의 뜻이 같이
바뀌는데 비율은 안 바뀐다.

## 기존 행

이미 사진이 있는 사람은 `avatar_source = 'uploaded'` 로 옮긴다 — 그 사람들에게는 그것이
사실이다. 썸네일은 **안 만든다**: 마이그레이션은 이미지 디코더를 부르지 않는다(그러면
스키마 변경이 Pillow 설치에 걸린다). 썸네일이 없는 동안은 서빙 경로가 원본을 그대로
내보내고, 다음에 사진을 바꾸면 그때 썸네일이 생긴다.

## 되감기

되감을 수 있다. 컬럼 다섯을 지운다 — 사진 자체(`avatar_stored_name`)는 안 건드린다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0019_avatar_default_and_crop'
down_revision = '0018_status_signal_axis'
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    ("avatar_source", sa.String(length=16), False, "default"),
    ("avatar_default_key", sa.String(length=32), True, None),
    ("avatar_thumb_name", sa.String(length=64), True, None),
    ("avatar_crop_x", sa.Float(), True, None),
    ("avatar_crop_y", sa.Float(), True, None),
    ("avatar_crop_zoom", sa.Float(), True, None),
)


def upgrade() -> None:
    for name, type_, nullable, default in NEW_COLUMNS:
        op.add_column(
            "user_preferences",
            sa.Column(
                name, type_, nullable=nullable,
                server_default=sa.text(f"'{default}'") if default is not None else None,
            ),
        )
    # 이미 사진이 있는 사람에게는 `uploaded` 가 사실이다.
    op.execute(
        "UPDATE user_preferences SET avatar_source = 'uploaded' "
        "WHERE avatar_stored_name IS NOT NULL"
    )


def downgrade() -> None:
    for name, _type, _nullable, _default in reversed(NEW_COLUMNS):
        op.drop_column("user_preferences", name)
