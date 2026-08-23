"""qa-contract-change: S11 이 n8n 설정 둘(n8n_work_assistant_url · n8n_timeout_seconds)을 Settings 에서 걷어냈다 — 그 기본값을 못 박던 단언 둘이 함께 사라졌다. 나머지 기본값 단언은 값도 형태도 그대로이고, 사라진 두 값이 되살아나면 test_external_automation_removed.py 가 배포 산출물 쪽에서 잡는다."""

import pytest

from app.core.config import Settings

pytestmark = pytest.mark.unit


def _bare_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_spec_28_defaults():
    s = _bare_settings()
    assert s.session_ttl_seconds == 28800
    assert s.session_idle_timeout_seconds == 1800
    assert s.max_message_length == 5000
    assert s.login_max_failures == 5
    assert s.login_lock_seconds == 900
    assert s.timezone == "Asia/Seoul"


def test_allowed_email_domain_list_parses_and_normalizes():
    s = _bare_settings(allowed_email_domains="Goodmit.co.kr, example.com ,")
    assert s.allowed_email_domain_list == ["goodmit.co.kr", "example.com"]


def test_is_production_flag():
    assert _bare_settings(app_env="production").is_production
    assert not _bare_settings(app_env="development").is_production
