import json

import pytest

from app.core.allowlist import Allowlist, AllowlistRegistry, URLNotAllowedError

pytestmark = pytest.mark.security


@pytest.fixture()
def allowlist():
    return Allowlist("test", frozenset({"127.0.0.1:5678", "localhost:8787"}))


def test_listed_host_port_allowed(allowlist):
    allowlist.check("http://127.0.0.1:5678/webhook/x")  # no raise


def test_unlisted_host_blocked(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://192.168.0.10:5678/")


def test_unlisted_port_blocked(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://127.0.0.1:9999/")


def test_default_port_resolution_blocked_unless_listed(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://127.0.0.1/")  # port 80 not listed


def test_file_scheme_blocked(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("file:///etc/passwd")


def test_ftp_scheme_blocked(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("ftp://127.0.0.1:5678/")


def test_userinfo_in_url_blocked(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://evil@127.0.0.1:5678/")


def test_hostname_case_normalized():
    allow = Allowlist("test", frozenset({"localhost:8787"}))
    allow.check("http://LOCALHOST:8787/")  # no raise


def test_missing_allowlist_file_denies_all(tmp_path):
    registry = AllowlistRegistry(tmp_path)
    with pytest.raises(URLNotAllowedError):
        registry.get("services").check("http://127.0.0.1:5678/")


def test_registry_reloads_on_file_change(tmp_path):
    path = tmp_path / "allowed-services.json"
    path.write_text(json.dumps({"hosts": ["127.0.0.1:1111"]}), encoding="utf-8")
    registry = AllowlistRegistry(tmp_path)
    registry.get("services").check("http://127.0.0.1:1111/")

    import os

    path.write_text(json.dumps({"hosts": ["127.0.0.1:2222"]}), encoding="utf-8")
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))
    with pytest.raises(URLNotAllowedError):
        registry.get("services").check("http://127.0.0.1:1111/")
    registry.get("services").check("http://127.0.0.1:2222/")


def test_unknown_allowlist_name_rejected(tmp_path):
    registry = AllowlistRegistry(tmp_path)
    with pytest.raises(URLNotAllowedError):
        registry.get("everything")
