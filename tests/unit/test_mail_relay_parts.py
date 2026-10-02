"""로컬 릴레이의 부품 — 인증서 · 로그 · 큐 · SPF · 준비 점검 판정 (계획 M7, D-551).

못박는 것:
  * 서버 인증서는 127.0.0.1 로 확인되는 자체 서명이고, 클라이언트 열쇠는 키 + 인증서 PEM 하나이며 지문은 Postfix 모양(SHA-256 대문자 콜론)이다.
  * DKIM 공개키는 개인키에서 나오고 TXT 조각은 255자를 넘지 않는다.
  * 실제 Postfix 3.8 의 로그 줄(`tests/fixtures/mail_relay/`, 컨테이너 실측)을 분류기가 읽는다 — 전달함 · 반송(DNS) · 미룸(연결 거부).
    받는 쪽이 말한 5xx · 4xx 와 TLS · 시간 지남도 가른다.
  * `postqueue -j` 를 읽고 깨진 줄은 건너뛴다.
  * SPF 판정 — 통과 · 실패 · 없음 · 레코드 오류(도메인이 아닌 include · 조회 10회 초과 · 레코드 둘).
  * 준비 점검의 줄은 상태 · 지금 상태 · 무엇이 필요한가 · 어디서 고치는가를 말하고, 분리 DNS 를 잡아 전달 서버를 제안한다.
"""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from app.mail import relay_certs, relay_log, relay_readiness as rr
from app.mail.dns import Answer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mail_relay"


# ── 인증서 · DKIM ────────────────────────────────────────────────────────────


def test_server_cert_is_trusted_for_127_0_0_1_and_the_client_bundle_loads(tmp_path):
    crt, key = relay_certs.make_server_cert()
    context = ssl.create_default_context(cadata=crt)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    bundle = relay_certs.make_client_bundle()
    assert bundle.index("PRIVATE KEY") < bundle.index("BEGIN CERTIFICATE"), "키 다음에 인증서"
    path = tmp_path / "client.pem"
    path.write_text(bundle, encoding="ascii")
    context.load_cert_chain(certfile=str(path))
    fp = relay_certs.fingerprint(bundle)
    assert len(fp) == 95 and fp == fp.upper() and fp.count(":") == 31
    assert relay_certs.fingerprint(bundle) != relay_certs.fingerprint(relay_certs.make_client_bundle())
    assert relay_certs.cert_usable(crt) and relay_certs.cert_usable(bundle)
    assert not relay_certs.cert_usable("not a cert") and not relay_certs.cert_usable(None)


def test_dkim_public_comes_from_the_private_key_and_chunks_fit_dns():
    key = relay_certs.make_dkim_key()
    assert "BEGIN RSA PRIVATE KEY" in key
    public = relay_certs.dkim_public(key)
    txt = relay_certs.dkim_txt(public)
    assert txt.startswith("v=DKIM1; k=rsa; p=") and len(txt) > 255
    chunks = relay_certs.txt_chunks(txt)
    assert all(len(c) <= 255 for c in chunks) and "".join(chunks) == txt


# ── 로그 · 큐 ─────────────────────────────────────────────────────────────────


def test_real_postfix_log_lines_are_classified():
    text = (FIXTURES / "postfix-container.log").read_text(encoding="utf-8")
    ids = {line.split(": ", 1)[1].split(":")[0] for line in text.splitlines() if ": to=<" in line}
    got = relay_log.parse_log(text, ids)
    by_status = {v["status"]: v for v in got.values()}
    sent = by_status["delivered"]
    assert sent["dsn"] == "2.0.0" and sent["stage"] is None and sent["said"].startswith("250 ")
    bounced = by_status["bounced"]
    assert bounced["dsn"] == "5.4.4" and bounced["stage"] == relay_log.STAGE_DNS
    deferred = by_status["deferred"]
    assert deferred["dsn"] == "4.4.1" and deferred["stage"] == relay_log.STAGE_CONNECT
    assert any(v.get("removed") for v in got.values())
    # 모르는 큐 id 의 줄은 버린다.
    assert relay_log.parse_log(text, ["AAAAAAAAAA"]) == {}


@pytest.mark.parametrize("status, said, expected", [
    ("bounced", "host mx.x.com[192.0.2.1] said: 550 5.7.1 Service unavailable; client blocked (in reply to RCPT TO command)",
     ("bounced", "rejected")),
    ("deferred", "host mx.x.com[192.0.2.1] said: 451 4.7.500 Server busy. Please try again later. (in reply to RCPT TO command)",
     ("deferred", "temporary")),
    ("deferred", "connect to mx.x.com[192.0.2.1]:25: Connection timed out", ("deferred", "connect")),
    ("deferred", "Host or domain name not found. Name service error for name=x.com type=MX: Host not found, try again",
     ("deferred", "dns")),
    ("deferred", "Cannot start TLS: handshake failure", ("deferred", "tls")),
    ("expired", "connect to mx.x.com[192.0.2.1]:25: Connection refused", ("expired", "expired")),
    ("sent", "250 2.0.0 OK", ("delivered", None)),
])
def test_classifier_table(status, said, expected):
    assert relay_log.classify(status, said) == expected


def test_queue_id_comes_from_the_data_reply():
    assert relay_log.queue_id_from_response("250 2.0.0 Ok: queued as C87DBF6954") == "C87DBF6954"
    assert relay_log.queue_id_from_response("250 2.0.0 OK") is None


def test_postqueue_json_is_read_and_broken_lines_are_skipped():
    text = (FIXTURES / "postqueue.jsonl").read_text(encoding="utf-8") + "\nnot json\n{\"queue_id\": \"bad id!\"}\n"
    items = relay_log.parse_postqueue(text)
    assert len(items) == 1
    item = items[0]
    assert item["queue_name"] == "deferred" and item["recipients"][0]["address"] == "later@deferred.test"
    assert relay_log.queue_state(item) == ("deferred", "connect", "connect to 127.0.0.1[127.0.0.1]:2699: Connection refused")
    assert relay_log.queue_state({"queue_name": "active", "recipients": []}) == ("queued", None, None)


# ── SPF ──────────────────────────────────────────────────────────────────────


class FakeDns:
    def __init__(self, txt=None, mx=None, a=None, ptr=None):
        self._txt, self._mx, self._a, self._ptr = txt or {}, mx or {}, a or {}, ptr or {}

    def txt(self, name):
        return Answer(values=self._txt[name]) if name in self._txt else Answer(error="nxdomain")

    def mx(self, name):
        return Answer(values=self._mx[name]) if name in self._mx else Answer(error="noanswer")

    def a(self, name):
        return Answer(values=self._a[name]) if name in self._a else Answer(error="nxdomain")

    def ptr(self, ip):
        return Answer(values=self._ptr[ip]) if ip in self._ptr else Answer(error="nxdomain")


IP = "221.147.80.10"


@pytest.mark.parametrize("records, expected", [
    ({"x.com": ["v=spf1 ip4:221.147.80.0/24 -all"]}, "pass"),
    ({"x.com": ["v=spf1 include:spf.y.com ~all"], "spf.y.com": [f"v=spf1 ip4:{IP} -all"]}, "pass"),
    ({"x.com": ["v=spf1 include:spf.y.com ~all"], "spf.y.com": ["v=spf1 ip4:10.0.0.1 -all"]}, "softfail"),
    ({"x.com": ["v=spf1 ip4:10.0.0.1 -all"]}, "fail"),
    ({"x.com": ["v=spf1 a mx -all"]}, "fail"),
    ({"x.com": ["v=spf1 redirect=spf.y.com"], "spf.y.com": [f"v=spf1 ip4:{IP} -all"]}, "pass"),
    ({"x.com": ["something else"]}, "none"),
    # goodmit.co.kr 랩 관찰처럼 include 대상이 도메인이 아니면 레코드 오류다.
    ({"x.com": ["v=spf1 include:spf.protection.outlook.com include:121.78.0.1 -all"],
      "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"]}, "permerror"),
    ({"x.com": ["v=spf1 -all", "v=spf1 +all"]}, "permerror"),
    ({"x.com": ["v=spf1 " + " ".join(f"include:s{i}.y.com" for i in range(11)) + " -all"],
      **{f"s{i}.y.com": ["v=spf1 -all"] for i in range(11)}}, "permerror"),
])
def test_spf_table(records, expected):
    result, _why = rr.spf_check(FakeDns(txt=records), "x.com", IP)
    assert result == expected


# ── 준비 점검의 줄 ───────────────────────────────────────────────────────────


def _by_key(rows):
    return {r["key"]: r for r in rows}


def test_component_rows_tell_the_state_need_and_place():
    rows = _by_key(rr.component_rows({"component": "not_installed", "listeners": []}, dkim=False))
    assert rows["relay_installed"]["state"] == rr.FAIL and rows["relay_installed"]["where"]
    rows = _by_key(rr.component_rows({"component": "running", "listeners": ["127.0.0.1:2525"]}, dkim=False))
    assert rows["relay_running"]["state"] == rr.OK and rows["relay_managed"]["state"] == rr.OK
    rows = _by_key(rr.component_rows({"component": "running", "listeners": ["127.0.0.1:2525", "0.0.0.0:25"]}, dkim=False))
    assert rows["relay_managed"]["state"] == rr.FAIL, "25번이 열려 있으면 받는 문이 예상과 다르다"
    rows = _by_key(rr.component_rows(None, dkim=False))
    assert {r["state"] for r in rows.values()} == {rr.UNKNOWN}


def test_split_dns_is_caught_and_an_override_is_suggested():
    system = FakeDns()                                 # 내부 해석기 - goodmit.co.kr 의 MX 를 모른다
    public = FakeDns(mx={"goodmit.co.kr": ["0 goodmit-co-kr.mail.protection.outlook.com"]})
    line, host, suggest = rr.recipient_mx_row(system, [public], "goodmit.co.kr", {})
    assert line["state"] == rr.FAIL and "분리 DNS" in line["message"]
    assert host is None and suggest == "goodmit-co-kr.mail.protection.outlook.com"
    line, host, _ = rr.recipient_mx_row(system, [public], "goodmit.co.kr",
                                        {"goodmit.co.kr": "goodmit-co-kr.mail.protection.outlook.com"})
    assert line["state"] == rr.OK and host == "goodmit-co-kr.mail.protection.outlook.com"


def test_ptr_dkim_dmarc_and_helo_rows():
    lookup = FakeDns(
        txt={"_dmarc.x.com": ["v=DMARC1; p=none"], "ca1._domainkey.x.com": ["v=DKIM1; k=rsa; p=ABC"]},
        a={"mail.x.com": [IP], "other.x.com": ["1.2.3.4"]}, ptr={IP: ["mail.x.com"]},
    )
    assert rr.ptr_row(lookup, IP, "mail.x.com")["state"] == rr.OK
    assert rr.ptr_row(FakeDns(), IP, "mail.x.com")["where"] == "회선이나 클라우드 업체"
    assert rr.dkim_row(lookup, "x.com", "ca1", "ABC", True)["state"] == rr.OK
    assert rr.dkim_row(lookup, "x.com", "ca1", "XYZ", True)["state"] == rr.FAIL
    assert rr.dkim_row(lookup, "x.com", "ca1", "", False)["state"] == rr.WARN
    assert rr.dmarc_row(lookup, "x.com")[0]["state"] == rr.OK
    assert rr.helo_row(lookup, "mail.x.com", IP)["state"] == rr.OK
    assert rr.helo_row(lookup, "other.x.com", IP)["state"] == rr.WARN
    assert rr.helo_row(lookup, "none.x.com", IP)["state"] == rr.FAIL


def test_records_merge_the_existing_spf():
    records = {r["key"]: r for r in rr.records_for(
        domain="x.com", egress_ip=IP, current_spf="v=spf1 include:spf.y.com -all", dkim_selector="ca1",
        dkim_public="ABC", dkim_enabled=True, from_address="noreply@x.com", helo="mail.x.com")}
    assert records["spf"]["value"] == f"v=spf1 ip4:{IP} include:spf.y.com -all"
    assert records["dkim"]["name"] == "ca1._domainkey.x.com" and records["dkim"]["value"].endswith("p=ABC")
    assert records["dmarc"]["value"] == "v=DMARC1; p=none; rua=mailto:noreply@x.com"
    assert records["helo"] == {"key": "helo", "name": "mail.x.com", "type": "A", "value": IP}
    assert IP in records["ptr"]["request"] and "mail.x.com" in records["ptr"]["request"]
