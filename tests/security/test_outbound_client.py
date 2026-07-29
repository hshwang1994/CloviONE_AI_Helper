import json

import pytest

from app.core.allowlist import AllowlistRegistry, URLNotAllowedError
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider, SecretMissingError
from tests.fakes.http import FakeHTTP

pytestmark = pytest.mark.security


@pytest.fixture()
def outbound(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "allowed-services.json").write_text(
        json.dumps({"hosts": ["127.0.0.1:5678"]}), encoding="utf-8"
    )
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "svc-token").write_text("token-plain-value", encoding="utf-8")

    fake = FakeHTTP()
    client = OutboundClient(
        AllowlistRegistry(config_dir),
        FileSecretReferenceProvider(secrets_dir),
        transport=fake.transport(),
    )
    yield client, fake
    client.close()


def test_allowlist_enforced_at_call_time(outbound):
    client, fake = outbound
    with pytest.raises(URLNotAllowedError):
        client.get("http://169.254.169.254/latest/meta-data", allowlist="services")
    assert fake.requests == []  # nothing ever left the building


def test_allowed_call_goes_through(outbound):
    client, fake = outbound
    fake.on("http://127.0.0.1:5678/", json_body={"ok": True})
    response = client.get("http://127.0.0.1:5678/healthz", allowlist="services")
    assert response.status_code == 200
    assert len(fake.requests) == 1


def test_redirects_are_not_followed(outbound):
    client, fake = outbound
    fake.on("http://127.0.0.1:5678/redirect", status=302)
    response = client.get("http://127.0.0.1:5678/redirect", allowlist="services")
    assert response.status_code == 302
    assert len(fake.requests) == 1  # no second request to the redirect target


def test_bearer_auth_injected_from_secret_ref(outbound):
    client, fake = outbound
    fake.on("http://127.0.0.1:5678/", json_body={})
    client.get(
        "http://127.0.0.1:5678/api",
        allowlist="services",
        auth_type="bearer",
        secret_ref="svc-token",
    )
    assert fake.requests[0].headers["Authorization"] == "Bearer token-plain-value"


def test_api_key_header_auth(outbound):
    client, fake = outbound
    fake.on("http://127.0.0.1:5678/", json_body={})
    client.get(
        "http://127.0.0.1:5678/api",
        allowlist="services",
        auth_type="api_key_header",
        secret_ref="svc-token",
    )
    assert fake.requests[0].headers["X-API-Key"] == "token-plain-value"


def test_missing_secret_blocks_request(outbound):
    client, fake = outbound
    with pytest.raises(SecretMissingError):
        client.get(
            "http://127.0.0.1:5678/api",
            allowlist="services",
            auth_type="bearer",
            secret_ref="does-not-exist",
        )
    assert fake.requests == []


def test_no_direct_httpx_import_outside_choke_point():
    """Static guard: only app/core/http_client.py may import httpx."""
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2] / "app"
    offenders = []
    for py_file in app_dir.rglob("*.py"):
        if py_file.name == "http_client.py" and py_file.parent.name == "core":
            continue
        text = py_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import httpx") or stripped.startswith("from httpx"):
                offenders.append(str(py_file))
    assert offenders == [], f"httpx imported outside the choke point: {offenders}"
