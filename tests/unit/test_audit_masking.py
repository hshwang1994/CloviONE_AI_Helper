import pytest

from app.core.audit import MASK, mask_sensitive

pytestmark = pytest.mark.unit


def test_masks_password_like_keys_recursively():
    data = {
        "email": "a@goodmit.co.kr",
        "password": "plain-secret",
        "nested": {"api_key": "abc", "list": [{"session_token": "xyz"}]},
        "secret_ref": "n8n-token-ref",
    }
    masked = mask_sensitive(data)
    assert masked["email"] == "a@goodmit.co.kr"
    assert masked["password"] == MASK
    assert masked["nested"]["api_key"] == MASK
    assert masked["nested"]["list"][0]["session_token"] == MASK
    assert masked["secret_ref"] == MASK


def test_non_dict_values_pass_through():
    assert mask_sensitive([1, "two", None]) == [1, "two", None]
    assert mask_sensitive("plain") == "plain"
