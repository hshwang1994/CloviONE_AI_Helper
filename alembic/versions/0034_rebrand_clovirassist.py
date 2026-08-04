"""제품명 ClovirONE → ClovirAssist (저장된 값 갱신)

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-04

## 왜 마이그레이션이 필요한가

제품명은 코드 상수가 아니라 **설정값**이다(`app/settings/registry.py` 의 `ui_branding`).
`SettingSpec` 의 기본값만 바꾸면 **한 번도 저장한 적 없는 설치에서만** 새 이름이 보인다.
관리자가 설정 화면에서 한 번이라도 저장했다면 `app_settings` 에 행이 생기고, 그 저장된 값이
기본값을 이긴다 — 운영 서버가 정확히 그 상태다. 그래서 저장된 값을 여기서 함께 옮긴다.

## 왜 문자열 치환이 아니라 JSON 파싱인가

`value_json` 은 `{"product_name": "..."}` 한 키만 있는 지금도 앞으로 키가 늘 수 있는 객체다.
문자열 replace 로 처리하면 나중에 `{"product_name": ..., "logo_url": ...}` 가 됐을 때
조용히 깨지거나 다른 값을 건드린다. 파싱해서 그 키만 바꾸고 다시 직렬화한다.

## 왜 '옛 이름일 때만' 바꾸는가

관리자가 이미 직접 다른 이름으로 바꿔 뒀을 수 있다. 무조건 덮어쓰면 그 선택을 지운다.
알려진 옛 이름과 정확히 같을 때만 옮기고, 그 외에는 손대지 않는다. 그래서 재실행해도 안전하다.

## organizations 도 함께 옮긴다

0022 가 기본 조직 이름을 `"ClovirONE"` 으로 심었다. 이 행은 Phase 5 에서 조직 관리 화면에
그대로 보이므로, 두고 가면 화면 한 곳에 옛 브랜드가 남는다. 같은 이유로 **옛 이름일 때만** 바꾼다.

## 타임스탬프

`app_settings.updated_at` 은 NOT NULL 이다. SQLite `STRFTIME` 은 이 저장소에서 금지돼 있어
(과거에 부서 화면을 죽인 함정, CLAUDE.md §8) **파이썬에서 만들어 바인딩**한다.
`updated_by` 는 건드리지 않는다 — 사람이 바꾼 것이 아니라 마이그레이션이 옮긴 것이고,
없는 사용자 id 를 지어내면 감사 화면이 거짓말을 하게 된다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_OLD_PRODUCT_NAME = "ClovirONE 업무 도우미"
_NEW_PRODUCT_NAME = "ClovirAssist"
_OLD_ORG_NAME = "ClovirONE"
_NEW_ORG_NAME = "ClovirAssist"


def _rename_product(old: str, new: str) -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT value_json FROM app_settings WHERE key = 'ui_branding'")
    ).fetchone()
    if row is None:
        return  # 저장된 적 없음 — 레지스트리 기본값이 이미 새 이름이다

    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        # 값이 JSON 이 아니면 우리가 아는 형태가 아니다. 추측해서 고치지 않는다.
        return
    if not isinstance(payload, dict) or payload.get("product_name") != old:
        return

    payload["product_name"] = new
    bind.execute(
        sa.text(
            "UPDATE app_settings SET value_json = :v, updated_at = :ts "
            "WHERE key = 'ui_branding'"
        ),
        {
            "v": json.dumps(payload, ensure_ascii=False),
            "ts": datetime.now(timezone.utc).replace(tzinfo=None),
        },
    )


def _rename_org(old: str, new: str) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE organizations SET name = :new WHERE name = :old"),
        {"new": new, "old": old},
    )


def upgrade() -> None:
    _rename_product(_OLD_PRODUCT_NAME, _NEW_PRODUCT_NAME)
    _rename_org(_OLD_ORG_NAME, _NEW_ORG_NAME)


def downgrade() -> None:
    _rename_product(_NEW_PRODUCT_NAME, _OLD_PRODUCT_NAME)
    _rename_org(_NEW_ORG_NAME, _OLD_ORG_NAME)
