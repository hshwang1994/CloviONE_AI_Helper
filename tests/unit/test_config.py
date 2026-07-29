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
    assert s.n8n_timeout_seconds == 180
    assert s.login_max_failures == 5
    assert s.login_lock_seconds == 900
    assert s.timezone == "Asia/Seoul"
    assert s.n8n_work_assistant_url == (
        "http://127.0.0.1:5678/webhook/clovirone-work-assistant"
    )


def test_allowed_email_domain_list_parses_and_normalizes():
    s = _bare_settings(allowed_email_domains="Goodmit.co.kr, example.com ,")
    assert s.allowed_email_domain_list == ["goodmit.co.kr", "example.com"]


def test_is_production_flag():
    assert _bare_settings(app_env="production").is_production
    assert not _bare_settings(app_env="development").is_production
