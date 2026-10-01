"""메일 비밀번호 칸 고정 — `smtp` 설정에서 `password_ref` 를 걷는다 (D-545).

Revision ID: 0042_smtp_password_slot
Revises: 0041_ai_policies

## 왜

`smtp.password_ref` 는 아무 비밀 이름이나 받았다. 메일 설정을 바꿀 수 있는 사람이 그 이름을 AI 키나 ChatGPT 토큰
묶음 같은 다른 비밀로 바꾸고 메일 서버 주소를 자기 서버로 돌린 뒤 「연결 확인」을 누르면, 워커가 그 진짜 비밀로
그 서버에 로그인했다. 이제 로그인 비밀번호는 언제나 고정 칸 `smtp.password` 에서 읽고(`app/mail/config.py`),
설정 검증기는 비어 있지 않은 `password_ref` 를 거절한다(`app/settings/registry.py::_smtp`).

## 무엇을 하나

`app_settings` 의 `smtp` 값에서 `password_ref` 키를 걷는다. 다른 키는 그대로다. 비밀 파일은 건드리지 않는다 -
비밀 디렉터리는 root 소유이고, 옛 이름이 가리키던 파일을 고정 칸으로 옮기는 일은 설치기가 이 마이그레이션 **앞에서**
한다(`deploy/install.sh::copy_legacy_smtp_secret`, 이름이 `smtp` 로 시작할 때만). 옛 이름이 비어 있지 않았고
고정 칸이 아니었으면 경고를 남긴다 - 설치기가 옮기지 못한 설치는 메일 화면에서 비밀번호를 다시 넣어야 한다.

설정 버전 기록(`config_versions`)의 옛 스냅숏은 고쳐 쓰지 않는다. 그 스냅숏으로 되돌리면 검증기가 비어 있지
않은 `password_ref` 를 거절하므로 옛 이름이 되살아나지 않는다.

## 되돌리기

할 일이 없다. 걷은 이름은 되살리지 않는다(되살리면 막은 길이 다시 열린다). 되돌린 코드는 빈 이름을 「고정 칸을
쓴다」로 읽으므로 그대로 동작한다.
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0042_smtp_password_slot"
down_revision = "0041_ai_policies"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0042")

FIXED_SLOT = "smtp.password"


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'smtp'")).first()
    if row is None:
        return
    raw = row[0]
    try:
        # 칸은 jsonb 라 드라이버가 dict 로 준다. 옛 Text 저장소(시험용 SQLite 등)는 문자열을 준다.
        value = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    except (TypeError, ValueError):
        logger.warning("smtp 설정 값을 JSON 으로 읽지 못해 그대로 둔다")
        return
    if not isinstance(value, dict) or "password_ref" not in value:
        return
    legacy = str(value.pop("password_ref") or "").strip()
    bind.execute(
        sa.text("UPDATE app_settings SET value_json = CAST(:v AS jsonb) WHERE key = 'smtp'"),
        {"v": json.dumps(value, ensure_ascii=False)},
    )
    if legacy and legacy != FIXED_SLOT:
        # 이름만 남긴다. 값은 이 마이그레이션이 읽지 않는다.
        logger.warning(
            "smtp 설정이 고정 칸이 아닌 비밀 이름(%s)을 가리켰다. 설치기가 옮기지 못했으면 메일 화면에서 비밀번호를 다시 넣어야 한다",
            legacy,
        )


def downgrade() -> None:
    # 모듈 머리말 「되돌리기」.
    pass
