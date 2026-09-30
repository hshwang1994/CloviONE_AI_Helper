"""바깥 호출의 문이 폼 본문, 스트리밍, JSON 묶음의 한 값을 다룬다 (D-516).

OAuth 토큰 교환은 폼 본문을, ChatGPT 요금제의 응답 API 는 스트리밍을, 계정 연결의 access token 은 비밀 칸의 JSON 묶음
안의 한 값을 요구한다. 셋 다 같은 문을 지나야 한다 - 허용 목록, redirect 금지, 비밀 주입이 같다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.allowlist import AllowlistRegistry, URLNotAllowedError
from app.core.errors import ValidationAppError
from app.core.http_client import AUTH_BEARER, OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider, SecretMissingError
from tests.fakes.http import FakeHTTP

BASE = "https://api.openai.com"


@pytest.fixture()
def outbound(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "allowed-services.json").write_text(json.dumps({"hosts": ["api.openai.com:443"]}), encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "bundle").write_text(json.dumps({"access_token": "at-123", "refresh_token": "rt-9"}), encoding="utf-8")
    (secrets / "empty-bundle").write_text(json.dumps({"client_id": "c"}), encoding="utf-8")
    (secrets / "not-json").write_text("plain", encoding="utf-8")
    fake = FakeHTTP()
    client = OutboundClient(AllowlistRegistry(config), FileSecretReferenceProvider(secrets), transport=fake.transport())
    yield client, fake
    client.close()


def test_form_body_is_sent_form_encoded(outbound):
    client, fake = outbound
    fake.on(BASE + "/token", json_body={"ok": True})
    client.request("POST", BASE + "/token", allowlist="services", data={"grant_type": "refresh_token", "a": "b c"})
    sent = fake.requests[0]
    assert sent.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert sent.content.decode() == "grant_type=refresh_token&a=b+c"


def test_json_and_form_together_are_refused_before_sending(outbound):
    client, fake = outbound
    with pytest.raises(ValidationAppError):
        client.request("POST", BASE + "/x", allowlist="services", json={"a": 1}, data={"b": 2})
    assert fake.requests == []


def test_secret_field_takes_one_value_from_a_json_bundle(outbound):
    client, fake = outbound
    fake.on(BASE + "/v1/models", json_body={})
    client.get(BASE + "/v1/models", allowlist="services", auth_type=AUTH_BEARER, secret_ref="bundle",
               secret_field="access_token")
    assert fake.requests[0].headers["Authorization"] == "Bearer at-123"


@pytest.mark.parametrize("ref", ["empty-bundle", "not-json"])
def test_a_missing_bundle_field_is_a_missing_secret(outbound, ref):
    client, fake = outbound
    with pytest.raises(SecretMissingError):
        client.get(BASE + "/v1/models", allowlist="services", auth_type=AUTH_BEARER, secret_ref=ref,
                   secret_field="access_token")
    assert fake.requests == []


def test_stream_reads_lines_and_keeps_the_same_guards(outbound):
    client, fake = outbound
    body = 'data: {"type":"response.output_text.delta","delta":"안녕"}\n\ndata: {"type":"response.completed"}\n\n'
    fake.on_handler(BASE + "/v1/responses", lambda request: httpx.Response(
        200, text=body, headers={"content-type": "text/event-stream"}, request=request))
    with client.stream("POST", BASE + "/v1/responses", allowlist="services", json={"stream": True},
                       auth_type=AUTH_BEARER, secret_ref="bundle", secret_field="access_token") as response:
        lines = [line for line in response.iter_lines() if line]
    assert lines[0].startswith("data: ") and "안녕" in lines[0]
    assert fake.requests[0].headers["Authorization"] == "Bearer at-123"
    with pytest.raises(URLNotAllowedError):
        with client.stream("POST", "https://evil.example/v1/responses", allowlist="services", json={}):
            pass
    assert len(fake.requests) == 1


def test_stream_does_not_follow_redirects(outbound):
    client, fake = outbound
    fake.on(BASE + "/v1/responses", status=302)
    with client.stream("POST", BASE + "/v1/responses", allowlist="services", json={}) as response:
        assert response.status_code == 302
    assert len(fake.requests) == 1
