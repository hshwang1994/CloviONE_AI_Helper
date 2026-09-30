"""바깥 호출의 프록시 — 시스템 설정의 환경 변수를 명시적으로 읽는다 (계획 2.10, D-516).

못박는 성질:
1. 프록시 환경 변수가 없으면 라우팅이 없다 - 지금과 똑같이 곧바로 연결한다.
2. `HTTPS_PROXY` 가 있으면 https 목적지가 그 프록시로 간다. `NO_PROXY` 의 호스트와 하위 이름은 곧바로 간다.
3. `trust_env` 는 여전히 꺼져 있다 - 프록시 세 값 말고 다른 환경 영향을 들이지 않는다.
4. 프록시가 있어도 허용 목록은 목적지에 그대로 걸린다(요청이 나가기 전에 막힌다).
5. 시험이 전송을 끼우면 프록시 라우팅을 걸지 않는다 - 가짜 대신 진짜 네트워크로 나가지 않는다.
6. 화면에 보이는 값에는 자격 증명이 없다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core import outbound_proxy
from app.core.allowlist import AllowlistRegistry, URLNotAllowedError
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from tests.fakes.http import FakeHTTP

PROXY = "http://proxy.corp.example:3128"


def _registry(tmp_path, hosts=("api.openai.com:443", "svc.internal.example:443")):
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "allowed-services.json").write_text(json.dumps({"hosts": list(hosts)}), encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    return AllowlistRegistry(config), FileSecretReferenceProvider(secrets)


def test_no_proxy_environment_means_direct_connections(tmp_path):
    settings = outbound_proxy.proxy_settings_from_env({})
    assert settings.enabled is False
    assert outbound_proxy.mount_plan(settings) == []
    allowlists, secrets = _registry(tmp_path)
    client = OutboundClient(allowlists, secrets, proxy=settings)
    try:
        assert client.proxy_display is None
        assert client._client._mounts == {}
    finally:
        client.close()


def test_https_proxy_routes_https_destinations_and_no_proxy_goes_direct(tmp_path):
    settings = outbound_proxy.proxy_settings_from_env({
        "HTTPS_PROXY": PROXY, "NO_PROXY": ".internal.example,10.0.0.5,localhost,partner.example",
    })
    plan = dict(outbound_proxy.mount_plan(settings))
    assert plan["https://"] == PROXY
    assert plan["all://*.internal.example"] is None
    assert plan["all://10.0.0.5"] is None
    assert plan["all://localhost"] is None
    assert plan["all://*partner.example"] is None

    allowlists, secrets = _registry(tmp_path)
    client = OutboundClient(allowlists, secrets, proxy=settings)
    try:
        default = client._client._transport
        to_openai = client._client._transport_for_url(httpx.URL("https://api.openai.com/v1/models"))
        to_internal = client._client._transport_for_url(httpx.URL("https://svc.internal.example/x"))
        to_partner = client._client._transport_for_url(httpx.URL("https://partner.example/x"))
        assert to_openai is not default, "https 목적지가 프록시를 지나지 않는다"
        assert to_internal is default and to_partner is default, "NO_PROXY 의 호스트가 프록시로 간다"
        assert client._client._trust_env is False
    finally:
        client.close()


def test_star_in_no_proxy_disables_the_proxy_entirely():
    settings = outbound_proxy.proxy_settings_from_env({"HTTPS_PROXY": PROXY, "NO_PROXY": "*"})
    assert outbound_proxy.mount_plan(settings) == []


def test_uppercase_wins_and_unusable_values_are_ignored():
    settings = outbound_proxy.proxy_settings_from_env({
        "HTTPS_PROXY": PROXY, "https_proxy": "http://other:1", "HTTP_PROXY": "ftp://nope:21",
    })
    assert settings.https == PROXY
    assert settings.http is None, "http/https 가 아닌 프록시 주소를 쓰면 안 된다"
    lower = outbound_proxy.proxy_settings_from_env({"https_proxy": "http://lower.example:8080"})
    assert lower.https == "http://lower.example:8080"


def test_display_never_shows_credentials():
    settings = outbound_proxy.ProxySettings(https="http://user:secret@proxy.corp.example:3128")
    assert settings.display() == "proxy.corp.example:3128"
    assert "secret" not in settings.display()


def test_the_allowlist_still_guards_destinations_behind_a_proxy(tmp_path):
    allowlists, secrets = _registry(tmp_path)
    client = OutboundClient(allowlists, secrets, proxy=outbound_proxy.ProxySettings(https=PROXY))
    try:
        with pytest.raises(URLNotAllowedError):
            client.get("https://169.254.169.254/latest/meta-data", allowlist="services")
    finally:
        client.close()


def test_an_injected_test_transport_is_never_routed_through_a_proxy(tmp_path):
    allowlists, secrets = _registry(tmp_path)
    fake = FakeHTTP()
    fake.on("https://api.openai.com/", json_body={"ok": True})
    client = OutboundClient(allowlists, secrets, transport=fake.transport(),
                            proxy=outbound_proxy.ProxySettings(https=PROXY))
    try:
        assert client._client._mounts == {}
        assert client.get("https://api.openai.com/v1/models", allowlist="services").status_code == 200
        assert len(fake.requests) == 1
        # 화면에는 프로세스가 읽은 프록시가 그대로 보인다(전송을 끼운 것은 시험의 사정이다).
        assert client.proxy_display == "proxy.corp.example:3128"
    finally:
        client.close()


def test_the_conversational_worker_receives_the_proxy_dropin():
    """채팅 답변과 연결 확인을 보내는 대화형 워커가 드롭인 대상에 빠지면 프록시 뒤에서 채팅만 끝내 닿지 못한다."""
    from app.core import product
    from app.sysops.actions_system import PROXY_DROPIN_UNITS

    assert product.WORKER_CONVERSATIONAL_UNIT in PROXY_DROPIN_UNITS
    assert product.INDEX_UNIT not in PROXY_DROPIN_UNITS, "색인 레인은 바깥으로 나가지 않는다"
    assert {product.WEB_UNIT, product.WORKER_UNIT, product.SCHEDULER_UNIT} <= set(PROXY_DROPIN_UNITS)
