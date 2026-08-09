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


# CORE-05: `urlsplit(...).port` validates the port range (0-65535) lazily, on
# access — not on parse. base_url/health_url/webhook_url have no URL validation
# at save time, so an admin saving a bad port used to turn every healthcheck's
# policy decision into an opaque 500 instead of the documented 400 contract.
def test_out_of_range_port_is_a_url_not_allowed_error_not_a_crash(allowlist):
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://runner.internal:99999/health")


def test_registry_reloads_when_size_changes_but_mtime_does_not(tmp_path):
    """CORE-06: `st_mtime`(초 단위) 하나만 캐시 키로 쓰면, 타임스탬프를 보존하는 복원
    (`cp -p`·`rsync -a`·tar·installer)이 예전 mtime을 그대로 들고 왔을 때 그 이후로
    바뀐 내용을 프로세스 수명 내내 못 본다. 여기서는 mtime을 **똑같이 고정**한 채
    내용(크기)만 바꿔, 그 상황을 직접 재현한다 — `st_mtime`만 보는 옛 캐시 키였다면
    이 테스트는 실패해야 한다."""
    import os

    path = tmp_path / "allowed-services.json"
    path.write_text(json.dumps({"hosts": ["127.0.0.1:1111"]}), encoding="utf-8")
    frozen_mtime = path.stat().st_mtime
    registry = AllowlistRegistry(tmp_path)
    registry.get("services").check("http://127.0.0.1:1111/")

    path.write_text(json.dumps({"hosts": ["127.0.0.1:1111", "127.0.0.1:2222"]}), encoding="utf-8")
    os.utime(path, (frozen_mtime, frozen_mtime))  # mtime 복원(타임스탬프 보존 복사 흉내)
    assert path.stat().st_mtime == frozen_mtime, "테스트 전제가 깨졌다 — mtime이 고정되지 않았다"

    registry.get("services").check("http://127.0.0.1:2222/")  # 새로 추가된 호스트가 보여야 한다
