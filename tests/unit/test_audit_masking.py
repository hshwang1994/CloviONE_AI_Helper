import pytest

from app.core.audit import MASK, mask_sensitive

pytestmark = pytest.mark.unit


def test_masks_password_like_keys_recursively():
    data = {
        "email": "a@goodmit.co.kr",
        "password": "plain-secret",
        "nested": {"api_key": "abc", "list": [{"session_token": "xyz"}]},
    }
    masked = mask_sensitive(data)
    assert masked["email"] == "a@goodmit.co.kr"
    assert masked["password"] == MASK
    assert masked["nested"]["api_key"] == MASK
    assert masked["nested"]["list"][0]["session_token"] == MASK


# CORE-12: secret_ref/secret_reference hold a reference NAME (a pointer into
# SECRETS_DIR), never the secret's actual value — app/core/versioning.py's
# config_versions snapshots already store them unmasked for exactly this
# reason (restore needs to know which name was in effect). Masking them here
# too made the audit trail for "the secret_ref changed" look like nothing
# happened ("***" -> "***"), while the same change was visible by name in the
# config version history right next to it.
def test_secret_ref_name_is_not_masked_but_other_secret_keys_still_are():
    data = {
        "secret_ref": "n8n-token-ref",
        "secret_reference": "runner-key-ref",
        "client_secret": "should-still-be-masked",
        "secret_value": "should-still-be-masked",
    }
    masked = mask_sensitive(data)
    assert masked["secret_ref"] == "n8n-token-ref"
    assert masked["secret_reference"] == "runner-key-ref"
    assert masked["client_secret"] == MASK
    assert masked["secret_value"] == MASK


def test_non_dict_values_pass_through():
    assert mask_sensitive([1, "two", None]) == [1, "two", None]
    assert mask_sensitive("plain") == "plain"
