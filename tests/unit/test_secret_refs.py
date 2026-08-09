import pytest

from app.core.secret_refs import (
    STATUS_CONFIGURED,
    STATUS_MISSING,
    FileSecretReferenceProvider,
    InvalidSecretRefError,
    SecretMissingError,
    SecretValue,
)

pytestmark = pytest.mark.unit


def test_secret_value_masks_itself_everywhere():
    secret = SecretValue("super-plain-secret")
    assert str(secret) == "***"
    assert repr(secret) == "***"
    assert f"{secret}" == "***"
    assert "super-plain-secret" not in f"log line: {secret!r} {secret}"
    assert secret.reveal() == "super-plain-secret"


def test_provider_reads_and_strips(tmp_path):
    (tmp_path / "n8n-token").write_text("  the-token-value\n", encoding="utf-8")
    provider = FileSecretReferenceProvider(tmp_path)
    assert provider.status("n8n-token") == STATUS_CONFIGURED
    assert provider.get("n8n-token").reveal() == "the-token-value"


def test_missing_secret(tmp_path):
    provider = FileSecretReferenceProvider(tmp_path)
    assert provider.status("nope") == STATUS_MISSING
    assert provider.get("nope") is None
    with pytest.raises(SecretMissingError):
        provider.require("nope")


# CORE-12: this exception's .message is put verbatim into the HTTP response
# body by register_error_handlers (errors.py) — and require() is reachable
# from ordinary (non-admin) user actions via OutboundClient, not just admin
# screens. The internal reference name (which secret *file* backs an
# integration) must never ride along in what the caller sees; code
# "secret_missing" is enough for the frontend to render a message.
def test_missing_secret_error_does_not_leak_the_reference_name(tmp_path):
    provider = FileSecretReferenceProvider(tmp_path)
    with pytest.raises(SecretMissingError) as exc_info:
        provider.require("n8n-runner-token-prod")
    assert "n8n-runner-token-prod" not in exc_info.value.message
    assert exc_info.value.code == "secret_missing"


def test_path_traversal_names_rejected(tmp_path):
    provider = FileSecretReferenceProvider(tmp_path)
    for evil in ["../etc/passwd", "..\\x", "/abs/path", "a/b", ".hidden-start-dot"]:
        with pytest.raises(InvalidSecretRefError):
            provider.get(evil)
    assert provider.status("../etc/passwd") == STATUS_MISSING
