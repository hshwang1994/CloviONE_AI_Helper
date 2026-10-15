"""로컬 릴레이의 부품 — 인증서 · 로그 · 큐 · SPF · 준비 점검 판정 (계획 M7, D-551).

못박는 것:
  * 서버 인증서는 127.0.0.1 로 확인되는 자체 서명이고, 클라이언트 열쇠는 키 + 인증서 PEM 하나이며 지문은 Postfix 모양(SHA-256 대문자 콜론)이다.
  * DKIM 공개키는 개인키에서 나오고 TXT 조각은 255자를 넘지 않는다.
  * 실제 Postfix 3.8 의 로그 줄(`tests/fixtures/mail_relay/`, 컨테이너 실측)을 분류기가 읽는다 — 전달함 · 반송(DNS) · 미룸(연결 거부).
    받는 쪽이 말한 5xx · 4xx 와 TLS · 시간 지남도 가른다.
  * `postqueue -j` 를 읽고 깨진 줄은 건너뛴다.
  * SPF 판정 — 통과 · 실패 · 없음 · 레코드 오류(도메인이 아닌 include · 조회 10회 초과 · 레코드 둘).
  * 준비 점검의 줄은 상태 · 지금 상태 · 무엇이 필요한가 · 어디서 고치는가를 말하고, 분리 DNS 를 잡아 전달 서버를 제안한다.
  * 제안은 빠진 것만이다(D-572): DMARC 가 있으면 DMARC 레코드 0(`p=none` 이면 권고 문장만), SPF · DKIM 이 통과하면 그 제안 0.
    웹 IP ≠ 발신 IP 면 메일 전용 이름을 제안하고 A · PTR 이 그 이름이며 NAT 대안을 말한다. 받는 쪽이 Microsoft 365 면 「발신자 표시
    요청」이 서고 허용 목록을 요청하지 않는다. `helo_suggestion` 표.
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


# ── 보내는 도메인은 받는 쪽이 보는 DNS 로 판정한다(P18 랩 E2E) ────────────────


def _sender(system, compare):
    facts = rr.sender_rows(system, compare, domain="goodmit.co.kr", egress_ip=IP, helo="clovirassist.gooddi.lab",
                           dkim_selector="ca1", dkim_public="", dkim_enabled=False)
    return _by_key(facts.rows), facts.current_spf, facts.seen


# 랩 관찰: 내부 해석기는 goodmit.co.kr 의 공개 레코드를 모르고(오류), 사설 이름을 사설 IP 로 푼다. 공개 DNS 는 SPF · DMARC 를 갖고
# 사설 이름은 모른다. SPF 의 셋째 include 는 도메인이 아니다.
SPLIT_SYSTEM = FakeDns(a={"clovirassist.gooddi.lab": ["10.100.64.71"]})
PUBLIC = FakeDns(
    mx={"goodmit.co.kr": ["0 goodmit-co-kr.mail.protection.outlook.com"]},
    txt={"goodmit.co.kr": ["v=spf1 include:spf.protection.outlook.com include:121.78.0.1 -all"],
         "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"],
         "_dmarc.goodmit.co.kr": ["v=DMARC1; p=none"]},
)


def test_split_dns_sender_records_are_judged_by_the_public_view():
    rows, spf, seen = _sender(SPLIT_SYSTEM, [PUBLIC])
    assert seen is True and spf.startswith("v=spf1 include:spf.protection.outlook.com")
    assert rows["sender_domain_public"]["state"] == rr.OK and "분리 DNS" in rows["sender_domain_public"]["message"]
    # 공개 SPF 가 있다 — 「없습니다」가 아니라 레코드 오류(도메인이 아닌 include)다.
    assert rows["spf"]["state"] == rr.FAIL and "오류" in rows["spf"]["message"]
    assert rows["dmarc"]["state"] == rr.OK
    # 받는 쪽에게 사설 이름은 없는 이름이다(내부 해석기의 「다른 IP 로 풀립니다」가 아니다).
    assert rows["helo_dns"]["state"] == rr.FAIL and "없습니다" in rows["helo_dns"]["message"]
    # 제안하는 SPF 는 공개 레코드와 합친 것이다(둘째 SPF 를 만들지 않는다).
    records = {r["key"]: r for r in rr.records_for(
        domain="goodmit.co.kr", egress_ip=IP, current_spf=spf, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
        from_address="noreply@goodmit.co.kr", helo="clovirassist.gooddi.lab", sender_seen=seen)}
    assert records["spf"]["value"].startswith(f"v=spf1 ip4:{IP} include:spf.protection.outlook.com")


def test_counterexample_without_a_public_view_the_rows_say_unknown_and_suggest_no_spf():
    rows, spf, seen = _sender(SPLIT_SYSTEM, [])
    assert seen is False and spf is None
    assert rows["sender_domain_public"]["state"] == rr.WARN
    assert rows["sender_domain_public"]["where"] == "메일 설정의 비교할 공개 DNS 서버"
    for key in ("spf", "dmarc"):
        assert rows[key]["state"] == rr.UNKNOWN, key
        assert "없습니다" not in rows[key]["message"], "보지 못한 것을 없다고 말하지 않는다"
        assert rows[key]["where"] == "메일 설정의 비교할 공개 DNS 서버"
    assert rows["dkim"]["state"] == rr.WARN, "서명을 안 쓰는 것은 DNS 와 무관한 사실이다"
    records = {r["key"] for r in rr.records_for(
        domain="goodmit.co.kr", egress_ip=IP, current_spf=None, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
        from_address="noreply@goodmit.co.kr", helo="clovirassist.gooddi.lab", sender_seen=seen)}
    assert "spf" not in records and "dmarc" not in records, "기존 레코드를 모르는 채 새 SPF · DMARC 를 제안하지 않는다"
    assert {"helo", "ptr"} <= records


def test_a_domain_the_system_resolver_knows_keeps_the_old_judgement():
    system = FakeDns(mx={"goodmit.co.kr": ["0 mx.goodmit.co.kr"]}, txt={"goodmit.co.kr": [f"v=spf1 ip4:{IP} -all"]},
                     a={"clovirassist.gooddi.lab": [IP]}, ptr={IP: ["clovirassist.gooddi.lab"]})
    rows, spf, seen = _sender(system, [])
    assert seen is True and rows["spf"]["state"] == rr.OK and rows["dmarc"]["state"] == rr.WARN
    assert rows["sender_domain_public"]["message"] == "보내는 도메인(goodmit.co.kr)을 DNS 에서 찾았습니다."
    assert rows["ptr_fcrdns"]["state"] == rr.OK and rows["helo_dns"]["state"] == rr.OK


def test_merged_spf_drops_a_term_that_is_not_a_domain():
    # 랩의 공개 SPF 처럼 사이트 확인 값이 include 로 들어간 레코드 — 그 항목 하나로 레코드 전체가 오류다.
    current = "v=spf1 include:spf.protection.outlook.com include:google-site-verification=QY1DgLBO55 -all"
    public = FakeDns(txt={"x.com": [current], "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"]})
    spf, got = rr.spf_row(public, "x.com", IP)
    assert spf["state"] == rr.FAIL and got == current
    assert spf["need"] == "도메인이 아닌 항목을 빼세요. 아래 레코드는 그 항목을 뺀 제안입니다."
    records = {r["key"]: r for r in rr.records_for(
        domain="x.com", egress_ip=IP, current_spf=current, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
        from_address="noreply@x.com", helo="mail.x.com")}
    assert records["spf"]["value"] == f"v=spf1 ip4:{IP} include:spf.protection.outlook.com -all"
    assert "google-site-verification" in records["spf"]["note"] and "원인입니다." in records["spf"]["note"]
    # 사이트 소유 확인 값은 지우라는 뜻이 아니다 — 따로 선 TXT 로 남길 값을 그대로 말한다(담당자가 지우면 소유 확인이 깨진다).
    assert records["spf"]["note"].endswith("TXT 레코드(google-site-verification=QY1DgLBO55)로 남겨 두세요.")
    # 사이트 확인 값이 아닌 깨진 항목에는 그 문장을 붙이지 않는다.
    other = "v=spf1 include:spf.protection.outlook.com include:not_a_domain -all"
    plain = {r["key"]: r for r in rr.records_for(
        domain="x.com", egress_ip=IP, current_spf=other, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
        from_address="noreply@x.com", helo="mail.x.com")}
    assert "남겨 두세요" not in plain["spf"].get("note", "")
    # 제안한 레코드는 오류가 아니다.
    fixed = FakeDns(txt={"x.com": [records["spf"]["value"]], "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"]})
    assert rr.spf_check(fixed, "x.com", IP)[0] == "pass"


def test_counterexample_a_valid_record_keeps_every_term_and_has_no_note():
    current = "v=spf1 include:spf.protection.outlook.com redirect=_spf.x.com"
    records = {r["key"]: r for r in rr.records_for(
        domain="x.com", egress_ip=IP, current_spf=current, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
        from_address="noreply@x.com", helo="mail.x.com")}
    assert "include:spf.protection.outlook.com" in records["spf"]["value"] and "redirect=_spf.x.com" in records["spf"]["value"]
    assert "note" not in records["spf"]


def test_requests_for_groups_records_by_owner_with_a_copyable_text():
    """「담당자에게 요청하기」(D-560) - DNS 담당자에게 SPF · DKIM · DMARC · 서버 이름, 회선 업체에게 PTR. 그대로 보낼 수 있는 글이다."""
    records = rr.records_for(domain="example.com", egress_ip="203.0.113.5", current_spf="v=spf1 include:spf.protection.outlook.com -all",
                             dkim_selector="ca1", dkim_public="QUJD", dkim_enabled=True, from_address="noreply@example.com",
                             helo="mail.example.com")
    requests = rr.requests_for(records, domain="example.com", egress_ip="203.0.113.5", helo="mail.example.com")
    assert [r["owner"] for r in requests] == [rr.OWNER_DNS, rr.OWNER_NETWORK]
    dns, ptr = requests
    assert [r["key"] for r in dns["records"]] == ["spf", "dkim", "dmarc", "helo"]
    assert "example.com 도메인의 DNS 에 아래 레코드를 넣어 주세요." in dns["text"]
    assert "v=spf1 ip4:203.0.113.5 include:spf.protection.outlook.com -all" in dns["text"]
    assert "ca1._domainkey.example.com" in dns["text"]
    assert ptr["records"][0]["key"] == "ptr" and "203.0.113.5" in ptr["text"] and "mail.example.com" in ptr["text"]
    assert "PTR" in ptr["title"]
    assert rr.requests_for([], domain="example.com", egress_ip=None, helo="") == []


# ── 빠진 것만 제안한다 · 메일 전용 서버 이름 · 받는 쪽 관리자 요청 (D-572) ─────────────────

EGRESS = "198.51.100.201"   # 메일이 나가는 IP
WEB = "198.51.100.210"      # 웹 주소가 풀리는 IP(다른 IP)


@pytest.mark.parametrize("helo, web_host, web_ip, helo_addrs, expected", [
    # 랩: 사설 이름 HELO, 웹 주소는 다른 IP - 메일 전용 이름(웹 첫 이름 + -mail)
    ("clovirassist.gooddi.lab", "clovirassist.goodmit.co.kr", WEB, [], ("clovirassist-mail.goodmit.co.kr", False, "private")),
    # 웹 주소를 HELO 로 썼는데 웹 IP 로 풀린다
    ("clovirassist.goodmit.co.kr", "clovirassist.goodmit.co.kr", WEB, [WEB], ("clovirassist-mail.goodmit.co.kr", False, "web_ip")),
    # 도메인 아래 · 발신 IP 로 풀림 - 그대로
    ("clovirassist-mail.goodmit.co.kr", "clovirassist.goodmit.co.kr", WEB, [EGRESS], ("clovirassist-mail.goodmit.co.kr", True, "ok")),
    # 도메인 아래 · 아직 DNS 에 없음 - 그 이름에 A 만 더한다
    ("mail.goodmit.co.kr", "clovirassist.goodmit.co.kr", WEB, [], ("mail.goodmit.co.kr", True, "missing")),
    # 도메인 아래지만 다른 IP(다른 메일 서버)로 풀림 - 남의 이름을 쓰지 않는다
    ("mail.goodmit.co.kr", "clovirassist.goodmit.co.kr", WEB, ["192.0.2.9"], ("clovirassist-mail.goodmit.co.kr", False, "other_ip")),
    # 웹 주소가 메일과 같은 IP 로 나간다 - 웹 주소 그 자체
    ("clovirassist.gooddi.lab", "clovirassist.goodmit.co.kr", EGRESS, [], ("clovirassist.goodmit.co.kr", False, "private")),
    # 웹 주소가 보내는 도메인 밖 - 제품 이름의 메일 전용 이름
    ("host.lab", "portal.example.org", WEB, [], ("mail-clovirassist.goodmit.co.kr", False, "private")),
])
def test_helo_suggestion_table(helo, web_host, web_ip, helo_addrs, expected):
    got = rr.helo_suggestion("goodmit.co.kr", helo, EGRESS, web_host, web_ip, helo_addrs=helo_addrs)
    assert (got["name"], got["keep"], got["reason"]) == expected
    if expected[1]:
        assert got["note"] is None
    else:
        assert got["note"] and "·" not in got["note"]
    if web_ip == WEB and not expected[1] and web_host.endswith("goodmit.co.kr"):
        assert "NAT" in got["note"] and WEB in got["note"] and EGRESS in got["note"]


def test_an_existing_dmarc_gets_no_record_and_p_none_only_advice():
    base = dict(domain="x.com", egress_ip=EGRESS, current_spf=None, dkim_selector="ca1", dkim_public="", dkim_enabled=False,
                from_address="noreply@x.com", helo="mail.x.com")
    assert "dmarc" in {r["key"] for r in rr.records_for(**base)}, "없으면 낸다"
    assert "dmarc" not in {r["key"] for r in rr.records_for(**base, current_dmarc="v=DMARC1; p=none;")}
    assert "dmarc" not in {r["key"] for r in rr.records_for(**base, current_dmarc="v=DMARC1; p=reject")}
    assert rr.dmarc_advice("v=DMARC1; p=none;") == rr.DMARC_NONE_ADVICE and rr.dmarc_advice("v=DMARC1; p=quarantine") is None
    row, current = rr.dmarc_row(FakeDns(txt={"_dmarc.x.com": ["v=DMARC1; p=none;"]}), "x.com")
    assert row["state"] == rr.OK and row["need"] == rr.DMARC_NONE_ADVICE and current == "v=DMARC1; p=none;"
    assert "·" not in rr.DMARC_NONE_ADVICE + rr.DMARC_KEEP + rr.NO_ALLOWLIST


def test_passing_checks_are_not_proposed_again():
    passing = {"spf": rr.OK, "dkim": rr.OK, "helo_dns": rr.OK, "ptr_fcrdns": rr.OK}
    records = rr.records_for(domain="x.com", egress_ip=EGRESS, current_spf=f"v=spf1 ip4:{EGRESS} -all", dkim_selector="ca1",
                             dkim_public="QUJD", dkim_enabled=True, from_address="noreply@x.com", helo="mail.x.com",
                             current_dmarc="v=DMARC1; p=quarantine", states=passing)
    assert records == []
    failing = {**passing, "spf": rr.FAIL, "dkim": rr.FAIL}
    keys = [r["key"] for r in rr.records_for(domain="x.com", egress_ip=EGRESS, current_spf="v=spf1 -all", dkim_selector="ca1",
                                             dkim_public="QUJD", dkim_enabled=True, from_address="noreply@x.com",
                                             helo="mail.x.com", current_dmarc="v=DMARC1; p=none", states=failing)]
    assert keys == ["spf", "dkim"]


class _Probe:
    def __init__(self):
        self.calls = []

    def __call__(self, host, helo):
        self.calls.append((host, helo))
        return {"host": host, "connected": True, "egress_ip": EGRESS, "ehlo": "250 hello"}


def _lab_config(**relay):
    from app.mail.config import smtp_config

    return smtp_config({"enabled": True, "from_address": "noreply@goodmit.co.kr", "from_name": "", "mode": "local_relay",
                        "relay": {"delivery": "direct", "helo_name": "clovirassist.gooddi.lab", "dkim_enabled": True,
                                  "dkim_selector": "ca1", "dkim_public": "QUJD", "compare_resolvers": ["8.8.8.8"], **relay}})


LAB_PUBLIC = FakeDns(
    mx={"goodmit.co.kr": ["0 goodmit-co-kr.mail.protection.outlook.com"]},
    txt={"goodmit.co.kr": ["v=spf1 include:spf.protection.outlook.com include:google-site-verification=abc -all"],
         "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"], "_dmarc.goodmit.co.kr": ["v=DMARC1; p=none;"]},
    a={"clovirassist.goodmit.co.kr": [WEB], "goodmit-co-kr.mail.protection.outlook.com": ["40.93.1.1"]},
)
LAB_SYSTEM = FakeDns(mx={"goodmit.co.kr": ["0 goodmit-co-kr.mail.protection.outlook.com"]},
                     a={"clovirassist.gooddi.lab": ["10.0.0.71"], "clovirassist.goodmit.co.kr": ["10.0.0.71"]})


def _lab_checks(config=None, public=LAB_PUBLIC):
    return rr.run_checks(config or _lab_config(), helper_status={"component": "running", "listeners": ["127.0.0.1:2525", "127.0.0.1:8891"]},
                         app_verify=lambda: {"ok": True}, smarthost_verify=lambda: {"ok": True}, system_dns=LAB_SYSTEM,
                         compare_dns=[public], probe_domain="goodmit.co.kr", mx_probe=_Probe(),
                         web_host="clovirassist.goodmit.co.kr")


def test_lab_web_ip_differs_from_egress_so_a_mail_name_ptr_and_nat_are_proposed():
    """랩 모양: 사설 HELO, 웹 .210 · 메일 .201, 공개 DMARC p=none 있음, 깨진 SPF include, DKIM 키 있고 DNS 엔 없음, 받는 쪽 Microsoft 365."""
    got = _lab_checks()
    rows = _by_key(got["checks"])
    records = {r["key"]: r for r in got["records"]}
    assert list(records) == ["spf", "dkim", "helo", "ptr"], "DMARC 는 이미 있으니 레코드를 내지 않는다"
    assert records["spf"]["value"] == f"v=spf1 ip4:{EGRESS} include:spf.protection.outlook.com -all"
    assert records["helo"] == {"key": "helo", "name": "clovirassist-mail.goodmit.co.kr", "type": "A", "value": EGRESS,
                               "note": records["helo"]["note"]}
    assert "NAT" in records["helo"]["note"]
    assert records["ptr"]["value"] == "clovirassist-mail.goodmit.co.kr" and "gooddi.lab" not in str(records["ptr"])
    # 정보 줄 · 정렬 줄 · 서버 이름 줄
    assert rows["egress_vs_web"]["state"] == rr.OK and WEB in rows["egress_vs_web"]["message"] and EGRESS in rows["egress_vs_web"]["message"]
    assert rows["sender_alignment"]["state"] == rr.OK and "정렬됐습니다" in rows["sender_alignment"]["message"]
    assert rows["helo_dns"]["state"] == rr.FAIL and "clovirassist-mail.goodmit.co.kr" in rows["helo_dns"]["need"]
    assert rows["dmarc"]["state"] == rr.OK and rows["dmarc"]["need"] == rr.DMARC_NONE_ADVICE
    assert got["web_ip"] == WEB and got["helo_suggestion"]["name"] == "clovirassist-mail.goodmit.co.kr"
    assert got["advice"] == [rr.DMARC_KEEP, rr.DMARC_NONE_ADVICE]
    # 요청문 셋 - DNS(있는 레코드만 + 참고), 회선(PTR + NAT 대안), 받는 쪽 Microsoft 365 관리자
    requests = {r["owner"]: r for r in got["requests"]}
    assert list(requests) == [rr.OWNER_DNS, rr.OWNER_NETWORK, rr.OWNER_MAILBOX]
    dns = requests[rr.OWNER_DNS]
    assert [r["key"] for r in dns["records"]] == ["spf", "dkim", "helo"] and "_dmarc" not in dns["text"]
    assert f"참고: {rr.DMARC_KEEP}" in dns["text"] and f"참고: {rr.DMARC_NONE_ADVICE}" in dns["text"]
    ptr = requests[rr.OWNER_NETWORK]
    assert "clovirassist-mail.goodmit.co.kr" in ptr["text"] and "NAT" in ptr["text"] and f"{WEB} 의" in ptr["text"]
    mailbox = requests[rr.OWNER_MAILBOX]
    assert mailbox["title"] == "발신자 표시 요청" and mailbox["provider"] == "Microsoft 365"
    assert "Microsoft 365" in mailbox["text"] and "compauth=pass" in mailbox["text"] and "noreply@goodmit.co.kr" in mailbox["text"]
    assert "공유 사서함" in mailbox["text"] and "「ClovirAssist」" in mailbox["text"] and rr.NO_ALLOWLIST in mailbox["text"]
    # 허용 목록 · 필터 예외를 요청하는 글은 어디에도 없다 - 그 낱말은 「요청하지 않습니다」 문장 안에만 있다.
    for request in got["requests"]:
        rest = request["text"].replace(rr.NO_ALLOWLIST, "")
        assert "허용 목록" not in rest and "예외" not in rest, request["owner"]
        assert "·" not in request["text"], request["owner"]


def test_when_the_web_address_shares_the_mail_ip_the_web_name_is_the_server_name():
    public = FakeDns(mx=LAB_PUBLIC._mx, txt=LAB_PUBLIC._txt, a={"clovirassist.goodmit.co.kr": [EGRESS]})
    got = _lab_checks(public=public)
    records = {r["key"]: r for r in got["records"]}
    assert got["helo_suggestion"]["name"] == "clovirassist.goodmit.co.kr"
    assert "helo" not in records, "웹 주소가 이미 발신 IP 로 풀린다 - A 레코드가 필요 없다"
    assert records["ptr"]["value"] == "clovirassist.goodmit.co.kr"
    ptr_text = next(r["text"] for r in got["requests"] if r["owner"] == rr.OWNER_NETWORK)
    assert "clovirassist.goodmit.co.kr" in ptr_text and "NAT" not in ptr_text, "같은 IP 면 NAT 대안을 말하지 않는다"
    rows = _by_key(got["checks"])
    assert "메일 설정의 서버 이름(HELO)" in rows["helo_dns"]["need"] and rows["helo_dns"]["where"] == "메일 설정"


def test_after_the_records_pass_only_the_optional_mailbox_request_remains():
    name = "clovirassist-mail.goodmit.co.kr"
    public = FakeDns(
        mx=LAB_PUBLIC._mx,
        txt={"goodmit.co.kr": [f"v=spf1 ip4:{EGRESS} include:spf.protection.outlook.com -all"],
             "spf.protection.outlook.com": ["v=spf1 ip4:40.92.0.0/15 -all"], "_dmarc.goodmit.co.kr": ["v=DMARC1; p=quarantine"],
             "ca1._domainkey.goodmit.co.kr": ["v=DKIM1; k=rsa; p=QUJD"]},
        a={"clovirassist.goodmit.co.kr": [WEB], name: [EGRESS]}, ptr={EGRESS: [name]},
    )
    got = _lab_checks(config=_lab_config(helo_name=name), public=public)
    rows = _by_key(got["checks"])
    for key in ("spf", "dkim", "dmarc", "ptr_fcrdns", "helo_dns", "egress_vs_web", "sender_alignment"):
        assert rows[key]["state"] == rr.OK, (key, rows[key])
    assert got["records"] == [] and got["advice"] == [rr.DMARC_KEEP]
    assert [r["owner"] for r in got["requests"]] == [rr.OWNER_MAILBOX]


def test_the_mailbox_request_is_for_the_sending_tenant_only():
    base = dict(domain="goodmit.co.kr", egress_ip=EGRESS, helo="m.goodmit.co.kr", from_address="noreply@goodmit.co.kr")
    assert rr.requests_for([], **base, recipient_mx_host="other-com.mail.protection.outlook.com", recipient_domain="other.com") == []
    generic = rr.requests_for([], **base, recipient_mx_host="mx.goodmit.co.kr", recipient_domain="goodmit.co.kr")
    assert [r["owner"] for r in generic] == [rr.OWNER_MAILBOX]
    assert generic[0]["provider"] is None and "Microsoft 365" not in generic[0]["text"]
    assert "Authentication-Results" in generic[0]["text"] and rr.NO_ALLOWLIST in generic[0]["text"]
