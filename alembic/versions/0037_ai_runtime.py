"""AI 생성 설정을 `ai_*` 로 옮기고 연결 상태 표를 만든다 (계획 3.13 · 3.15 · 3.16, D-515).

Revision ID: 0037_ai_runtime
Revises: 0036_notification_mail_prefs

## 설정 옮기기

  llm_backend = api                   → ai_provider = anthropic, ai_auth_method = api_key, ai_model = llm_model,
                                        ai_generation_enabled = (llm_enabled == on)
  llm_backend = cli 이거나 비었는데 켜짐 → ai_generation_enabled = false, 관리자 알림 「AI 연결을 다시 설정해야 합니다」
  llm_timeout_seconds, llm_max_concurrency → ai_timeout_seconds, ai_max_concurrency(새 범위로 접는다)

서버에 로그인된 구독 명령줄 도구로 돌던 설치는 몰래 다른 자격으로 바꾸지 않는다 - 끄고 알린다(공식 정책상 그 길은
더 쓸 수 없다). `llm_*` 행은 지운다. 바꾼 이력(`config_versions`)은 남는다.

환경 변수(`LLM_ENABLED` 등)로만 켜 둔 설치는 이 마이그레이션이 볼 수 없다. 그 설치의 키 파일 옮기기는 설치
스크립트의 업그레이드가 한다(계획 3.16).

## 되돌리기

`ai_*` 를 `llm_*` 로 되옮긴다(anthropic 이면 api, 아니면 비움). 연결 상태 표는 지운다 - 다시 쓰면 확인 전부터 다시
센다.
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0037_ai_runtime"
down_revision = "0036_notification_mail_prefs"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0037")

TYPES = {
    "ai_generation_enabled": "bool", "ai_provider": "string", "ai_auth_method": "string", "ai_model": "string",
    "ai_timeout_seconds": "int", "ai_max_concurrency": "int",
    "llm_enabled": "string", "llm_backend": "string", "llm_model": "string", "llm_timeout_seconds": "int",
    "llm_max_concurrency": "int",
}

RECONFIGURE_TITLE = "AI 연결을 다시 설정해야 합니다"
RECONFIGURE_BODY = (
    "서버에 로그인된 명령줄 도구로 AI 를 쓰던 설정은 이번 업그레이드에서 더 쓸 수 없게 되어 AI 답변 생성을 껐습니다. "
    "AI 설정 화면에서 제공자와 API 키를 넣은 뒤 다시 켜세요."
)


def _read(conn, prefix: str) -> dict:
    """``value_json`` 은 jsonb 라 드라이버가 이미 풀어서 준다 - 문자열로 받아 한 가지 방법으로만 푼다."""
    rows = conn.execute(
        sa.text("SELECT key, value_json::text FROM app_settings WHERE key LIKE :p ESCAPE '\\'"),
        {"p": prefix.replace("_", "\\_") + "%"},
    )
    out = {}
    for key, raw in rows:
        try:
            out[key] = json.loads(raw)
        except (TypeError, ValueError):
            continue
    return out


def _write(conn, key: str, value) -> None:
    conn.execute(sa.text(
        "INSERT INTO app_settings (key, value_json, value_type, restart_required, updated_at) "
        "VALUES (:k, :v, :t, false, now() AT TIME ZONE 'UTC') "
        "ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = EXCLUDED.updated_at"
    ), {"k": key, "v": json.dumps(value, ensure_ascii=False), "t": TYPES[key]})


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def upgrade() -> None:
    op.create_table(
        "ai_credential_state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("reason_text", sa.String(300)),
        sa.Column("config_fingerprint", sa.String(64)),
        sa.Column("account_label", sa.String(200)),
        sa.Column("client_id", sa.String(200)),
        sa.Column("ext_agent_host_id", sa.String(100)),
        sa.Column("access_expires_at", sa.DateTime()),
        sa.Column("refresh_obtained_at", sa.DateTime()),
        sa.Column("refresh_expires_at", sa.DateTime()),
        sa.Column("expiry_source", sa.String(32)),
        sa.Column("last_verified_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("last_failure_at", sa.DateTime()),
        sa.Column("last_changed_at", sa.DateTime()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_notified_state", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "auth_method", name="uq_ai_credential_state_pair"),
    )

    conn = op.get_bind()
    old = _read(conn, "llm_")
    enabled = old.get("llm_enabled") == "on"
    backend = old.get("llm_backend") or ""
    model = old.get("llm_model") if isinstance(old.get("llm_model"), str) else ""
    notify = False
    if backend == "api":
        _write(conn, "ai_provider", "anthropic")
        _write(conn, "ai_auth_method", "api_key")
        if model.strip():
            _write(conn, "ai_model", model.strip())
        _write(conn, "ai_generation_enabled", enabled)
    elif enabled:
        _write(conn, "ai_generation_enabled", False)
        notify = True
    timeout = _int(old.get("llm_timeout_seconds"))
    if timeout and timeout > 0:
        _write(conn, "ai_timeout_seconds", max(5, min(300, timeout)))
    concurrency = _int(old.get("llm_max_concurrency"))
    if concurrency and concurrency > 1:
        _write(conn, "ai_max_concurrency", max(1, min(8, concurrency)))
    conn.execute(sa.text("DELETE FROM app_settings WHERE key LIKE 'llm\\_%' ESCAPE '\\'"))
    if notify:
        admins = conn.execute(sa.text(
            "INSERT INTO notifications (id, user_id, type, audience, title, body, created_at) "
            "SELECT gen_random_uuid()::text, u.id, 'ai_provider_state', 'admin', :t, :b, now() AT TIME ZONE 'UTC' "
            "FROM users u WHERE u.role IN ('admin', 'system_admin') AND u.active AND u.archived_at IS NULL"
        ), {"t": RECONFIGURE_TITLE, "b": RECONFIGURE_BODY}).rowcount
        logger.info("0037: 명령줄 도구로 켜져 있던 AI 를 껐고 관리자 %s명에게 알렸다", admins)
    logger.info("0037: 옛 AI 설정 %s개를 옮겼다(backend=%s)", len(old), backend or "비어 있음")


def downgrade() -> None:
    conn = op.get_bind()
    new = _read(conn, "ai_")
    if new.get("ai_provider") == "anthropic":
        _write(conn, "llm_backend", "api")
        if isinstance(new.get("ai_model"), str) and new["ai_model"]:
            _write(conn, "llm_model", new["ai_model"])
        _write(conn, "llm_enabled", "on" if new.get("ai_generation_enabled") is True else "off")
    timeout = _int(new.get("ai_timeout_seconds"))
    if timeout:
        _write(conn, "llm_timeout_seconds", timeout)
    concurrency = _int(new.get("ai_max_concurrency"))
    if concurrency:
        _write(conn, "llm_max_concurrency", min(4, concurrency))
    conn.execute(sa.text(
        "DELETE FROM app_settings WHERE key IN ('ai_generation_enabled', 'ai_provider', 'ai_auth_method', "
        "'ai_model', 'ai_timeout_seconds', 'ai_max_concurrency')"
    ))
    op.drop_table("ai_credential_state")
