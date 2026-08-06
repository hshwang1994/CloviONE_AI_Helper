"""특권 헬퍼 입력 검증 (§S).

이 값들은 root 로 도는 프로세스에 전달되고 시스템 설정 파일에 그대로 적힌다.
`shell=False` 라 셸 확장은 없지만, 그것만 믿지 않는다 - 설정 파일 문법을 깨뜨리는 값 하나로
다음 부팅에 서비스가 안 뜨는 것도 같은 크기의 사고다.
"""

from __future__ import annotations

import pytest

from app.sysops import validate as v

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "Asia/Seoul; rm -rf /",
    "Asia/Seoul\nExtra=1",
    "Nowhere/Nothing",
    "",
    "   ",
    None,
    123,
])
def test_timezone_rejects_anything_the_system_does_not_know(bad):
    """정규식이 아니라 **시스템이 아는 목록과 대조**한다."""
    with pytest.raises(v.InvalidSysopsValueError):
        v.timezone(bad)


def test_timezone_accepts_a_real_zone():
    assert v.timezone(" Asia/Seoul ") == "Asia/Seoul"


@pytest.mark.parametrize("bad", [
    "srv;reboot", "srv 1", "srv\nname", "-srv", "srv-", "a" * 64, "sr/v", "srv.example.com", "",
])
def test_hostname_rejects_shell_and_config_breaking_characters(bad):
    with pytest.raises(v.InvalidSysopsValueError):
        v.hostname(bad)


def test_hostname_normalizes_case():
    assert v.hostname("SRV-01") == "srv-01"


@pytest.mark.parametrize("bad", ["nodots", "a..b", "-a.example.com", "a" * 250 + ".example.com"])
def test_fqdn_rejects_malformed_names(bad):
    with pytest.raises(v.InvalidSysopsValueError):
        v.fqdn(bad)


def test_fqdn_drops_the_trailing_dot():
    assert v.fqdn("Portal.Example.COM.") == "portal.example.com"


@pytest.mark.parametrize("bad", ["10.0.0.256", "1.2.3", "dns.example.com", "10.0.0.1 8.8.8.8"])
def test_dns_servers_take_addresses_only(bad):
    """이름을 받으면 그 이름을 풀 방법이 없다 - DNS 를 설정하는 중이기 때문이다."""
    with pytest.raises(v.InvalidSysopsValueError):
        v.dns_servers([bad])


def test_dns_servers_reject_duplicates_and_overflow():
    with pytest.raises(v.InvalidSysopsValueError):
        v.dns_servers(["10.0.0.1", "10.0.0.1"])
    with pytest.raises(v.InvalidSysopsValueError):
        v.dns_servers(["10.0.0.%d" % i for i in range(1, 9)])
    with pytest.raises(v.InvalidSysopsValueError):
        v.dns_servers([])


def test_dns_servers_accept_v4_and_v6():
    assert v.dns_servers(["10.0.0.1", "2001:db8::1"]) == ["10.0.0.1", "2001:db8::1"]


def test_ntp_accepts_names_because_pool_addresses_are_names():
    assert v.ntp_servers(["kr.pool.ntp.org", "10.0.0.5"]) == ["kr.pool.ntp.org", "10.0.0.5"]


@pytest.mark.parametrize("bad", ["kr.pool.ntp.org extra", "srv;id", "-bad.example.com"])
def test_ntp_rejects_malformed_servers(bad):
    with pytest.raises(v.InvalidSysopsValueError):
        v.ntp_servers([bad])


def test_proxy_rejects_credentials_in_the_url():
    """🔴 프록시 주소는 전 시스템이 읽는 자리에 적힌다 - 비밀번호를 넣으면 안 된다."""
    with pytest.raises(v.InvalidSysopsValueError) as err:
        v.proxy_url("http://user:secret@proxy.example.com:3128")
    assert "secret" not in str(err.value), f"거절하면서 비밀번호를 되풀이했다: {err.value}"


@pytest.mark.parametrize("bad", [
    "ftp://proxy.example.com:3128",
    "proxy.example.com:3128",
    "http://proxy.example.com:3128/path",
    "http://proxy.example.com:3128?a=1",
    "http://:3128",
])
def test_proxy_rejects_malformed_urls(bad):
    with pytest.raises(v.InvalidSysopsValueError):
        v.proxy_url(bad)


def test_proxy_accepts_a_plain_url():
    assert v.proxy_url("http://proxy.example.com:3128") == "http://proxy.example.com:3128"


def test_no_proxy_allows_leading_dot_for_subdomains():
    assert v.no_proxy(" .example.com, 10.0.0.1 ,localhost ") == ".example.com,10.0.0.1,localhost"


@pytest.mark.parametrize("bad", ["a;b", "", ",,,"])
def test_no_proxy_rejects_malformed_entries(bad):
    with pytest.raises(v.InvalidSysopsValueError):
        v.no_proxy(bad)
