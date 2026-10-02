"""로컬 릴레이 설정 파일 생성 (계획 M7, D-551).

못박는 것:
  * main.cf 에 보안 계약 넷의 고정 키가 언제나 있다 — 루프백만 듣고, 보안 연결을 강제하고, 앱 인증서 지문만 중계를 허가하고(`reject`
    로 끝난다), 로컬 배달이 없고, `sendmail` 로 큐에 넣는 길이 닫혀 있다.
  * master.cf 에서 듣는 서비스(`inet`, 25번 smtpd)와 `pickup` 이 빠지고 받는 문은 `127.0.0.1:2525` 하나다. 나머지 서비스는 꾸러미의 것
    그대로다(실제 Ubuntu 24.04 의 master.cf.proto 와 같은 모양의 견본으로 잰다).
  * 상위 SMTP 와 직접 전달의 차이(relayhost · SASL · transport_maps · milter).
  * 인자로 설정 줄을 끼워 넣을 수 없다 — 줄바꿈 · `=` · 공백 · 모르는 키가 거절된다.
  * 제품이 만든 main.cf 인가(표지 + 같은 지문)와 기존 구성의 구분, 듣는 소켓 표 읽기.

실제 Postfix 로 계약을 잰 것은 `scripts/ui_qa/relay_container_e2e.py`(Docker, 17개 확인)다.
"""

from __future__ import annotations

import pytest

from app.mail import relay_files as rf

PROTO = """#
# Postfix master process configuration file.
# ==========================================================================
# service type  private unpriv  chroot  wakeup  maxproc command + args
# ==========================================================================
smtp      inet  n       -       y       -       -       smtpd
#smtp      inet  n       -       y       -       1       postscreen
#submission inet n       -       y       -       -       smtpd
#  -o syslog_name=postfix/submission
pickup    unix  n       -       y       60      1       pickup
cleanup   unix  n       -       y       -       0       cleanup
qmgr      unix  n       -       n       300     1       qmgr
tlsmgr    unix  -       -       y       1000?   1       tlsmgr
rewrite   unix  -       -       y       -       -       trivial-rewrite
bounce    unix  -       -       y       -       0       bounce
smtp      unix  -       -       y       -       -       smtp
relay     unix  -       -       y       -       -       smtp
        -o syslog_name=postfix/$service_name
error     unix  -       -       y       -       -       error
postlog   unix-dgram n  -       n       -       1       postlogd
"""


def _direct(**over):
    raw = {"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "mail.goodmit.co.kr",
           "ipv4_only": False, "dkim": {"selector": "ca1"},
           "transport_overrides": [{"domain": "goodmit.co.kr", "host": "goodmit-co-kr.mail.protection.outlook.com"}]}
    raw.update(over)
    return rf.normalize_params(raw)


def _smarthost(**over):
    raw = {"delivery": "smarthost", "sender_domain": "goodmit.co.kr", "helo_name": "",
           "smarthost": {"host": "smtp.office365.com", "port": 587, "security": "starttls", "username": "notify@goodmit.co.kr"}}
    raw.update(over)
    return rf.normalize_params(raw)


def _settings(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


@pytest.mark.parametrize("params", [_direct(), _smarthost()])
def test_the_fixed_security_keys_are_always_there(params):
    text = rf.render_main_cf(params)
    assert text.startswith(rf.MARKER)
    keys = _settings(text)
    assert keys["inet_interfaces"] == "loopback-only"
    assert keys["smtpd_tls_security_level"] == "encrypt"
    assert keys["smtpd_tls_ask_ccert"] == "yes"
    assert keys["smtpd_tls_fingerprint_digest"] == "sha256"
    assert keys["relay_clientcerts"] == f"texthash:{rf.CLIENT_CERTS}"
    assert keys["smtpd_relay_restrictions"] == "permit_tls_clientcerts, reject"
    assert keys["smtpd_recipient_restrictions"] == "permit_tls_clientcerts, reject"
    # 로컬 배달 없음 · postmaster 알림 없음.
    assert keys["mydestination"] == "" and keys["local_recipient_maps"] == "" and keys["alias_maps"] == ""
    assert keys["local_transport"].startswith("error:")
    assert keys["notify_classes"] == ""
    # `sendmail` 로 큐에 넣는 길을 닫는다(계약 4) - 빈 목록 = 아무도 못 넣는다.
    assert keys["authorized_submit_users"] == ""
    assert keys["authorized_mailq_users"] == "root" and keys["authorized_flush_users"] == "root"
    assert keys["disable_vrfy_command"] == "yes"
    assert "permit_sasl_authenticated" not in text and "permit_mynetworks, permit" not in text


def test_master_cf_listens_only_on_loopback_2525_and_drops_pickup():
    text = rf.render_master_cf(PROTO)
    active = [line for line in text.splitlines() if line and not line[0].isspace() and not line.startswith("#")]
    inet = [line for line in active if line.split()[1] == "inet"]
    assert inet == [rf.OUR_SERVICE.splitlines()[0]], "받는 문은 127.0.0.1:2525 하나여야 한다"
    assert inet[0].startswith("127.0.0.1:2525 ")
    assert not any(line.split()[0] == "pickup" for line in active), "sendmail 의 집배원(pickup)이 남았다"
    names = [line.split()[0] for line in active]
    # 나머지 서비스는 꾸러미 그대로다 - smtp 클라이언트(unix) · qmgr · cleanup · postlog 는 남는다.
    for kept in ("cleanup", "qmgr", "smtp", "relay", "error", "postlog"):
        assert kept in names
    assert "        -o syslog_name=postfix/$service_name" in text, "남긴 서비스의 이어지는 줄은 그대로다"
    assert text.startswith(rf.MARKER)


def test_smarthost_and_direct_differ_only_where_they_should():
    smart = _settings(rf.render_main_cf(_smarthost()))
    direct = _settings(rf.render_main_cf(_direct()))
    assert smart["relayhost"] == "[smtp.office365.com]:587"
    assert smart["smtp_tls_security_level"] == "encrypt"
    assert smart["smtp_sasl_auth_enable"] == "yes"
    assert smart["smtp_sasl_password_maps"] == f"texthash:{rf.SASL_PASSWD}"
    assert "smtpd_milters" not in smart, "상위 SMTP 를 거치면 서명은 상위 서버가 맡는다"
    assert "relayhost" not in direct
    assert direct["smtp_tls_security_level"] == "may"
    assert direct["transport_maps"] == f"texthash:{rf.TRANSPORT_MAP}"
    assert direct["smtpd_milters"] == f"inet:127.0.0.1:{rf.MILTER_PORT}"
    assert direct["milter_default_action"] == "accept"
    assert direct["myhostname"] == "mail.goodmit.co.kr"
    assert _settings(rf.render_main_cf(_direct(ipv4_only=True)))["inet_protocols"] == "ipv4"
    ssl = _settings(rf.render_main_cf(_smarthost(smarthost={"host": "smtp.x.com", "port": 465, "security": "ssl",
                                                            "username": ""})))
    assert ssl["smtp_tls_wrappermode"] == "yes" and "smtp_sasl_auth_enable" not in ssl


@pytest.mark.parametrize("raw, message", [
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "mail.x.com\nrelayhost = evil"}, "HELO"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "a=b.com"}, "HELO"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "mail x.com"}, "HELO"),
    ({"delivery": "direct", "sender_domain": "evil.com\nmynetworks = 0.0.0.0/0", "helo_name": "m.x.com"}, "도메인"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": ""}, "HELO"),
    ({"delivery": "smarthost", "sender_domain": "goodmit.co.kr",
      "smarthost": {"host": "smtp.x.com", "port": 587, "security": "starttls", "username": "a b"}}, "계정"),
    ({"delivery": "smarthost", "sender_domain": "goodmit.co.kr",
      "smarthost": {"host": "smtp.x.com\nrelayhost = [evil]", "port": 587, "security": "starttls", "username": ""}},
     "주소"),
    ({"delivery": "smarthost", "sender_domain": "goodmit.co.kr",
      "smarthost": {"host": "smtp.x.com", "port": "587", "security": "starttls", "username": ""}}, "포트"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "m.x.com", "takeover": True}, "알 수 없는"),
    ({"delivery": "open", "sender_domain": "goodmit.co.kr"}, "전달 방식"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "m.x.com",
      "transport_overrides": [{"domain": "x.com", "host": "mx.x.com]:25 smtp:[evil"}]}, "전달 서버"),
    ({"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "m.x.com", "dkim": {"selector": "a b"}}, "선택자"),
])
def test_injection_shapes_are_refused(raw, message):
    with pytest.raises(rf.RelayParamsError) as caught:
        rf.normalize_params(raw)
    assert message in str(caught.value)


def test_overrides_are_capped_and_unique():
    many = [{"domain": f"d{i}.com", "host": "mx.x.com"} for i in range(21)]
    with pytest.raises(rf.RelayParamsError, match="20줄"):
        rf.normalize_overrides(many)
    with pytest.raises(rf.RelayParamsError, match="두 번"):
        rf.normalize_overrides([{"domain": "a.com", "host": "m.a.com"}, {"domain": "a.com", "host": "n.a.com"}])
    assert rf.render_transport(rf.normalize_overrides([{"domain": "A.com", "host": "MX.A.com"}])).splitlines()[1] == \
        "a.com smtp:[mx.a.com]:25"


def test_the_sasl_line_refuses_line_breaks_and_holds_the_value_only_in_the_file():
    sh = {"host": "smtp.x.com", "port": 587, "security": "starttls", "username": "u@x.com"}
    assert rf.render_sasl_passwd(sh, "p w") == "[smtp.x.com]:587 u@x.com:p w\n"
    for bad in ("", "a\nb", "a\rb", "a\x00b"):
        with pytest.raises(rf.RelayParamsError):
            rf.render_sasl_passwd(sh, bad)


def test_opendkim_signs_only_on_loopback_with_a_safe_key():
    text = rf.render_opendkim_conf({"domain": "goodmit.co.kr", "selector": "ca1"})
    lines = dict(line.split("\t", 1) for line in text.splitlines()[1:])
    assert lines["Mode"] == "s"
    assert lines["Socket"] == f"inet:{rf.MILTER_PORT}@127.0.0.1"
    assert lines["KeyFile"] == "/etc/opendkim/keys/goodmit.co.kr/ca1.private"
    assert lines["RequireSafeKeys"] == "yes"
    assert rf.dkim_record_name("goodmit.co.kr", "ca1") == "ca1._domainkey.goodmit.co.kr"


def test_managed_or_foreign():
    params = _direct()
    main, master = rf.render_main_cf(params), rf.render_master_cf(PROTO)
    state = rf.render_state(main, master, relay_fingerprint=rf.relay_fingerprint(params))
    assert rf.main_cf_state(None, None, None) == "absent"
    assert rf.main_cf_state(main, master, state) == "managed"
    assert rf.main_cf_state("myhostname = x\n", master, None) == "foreign", "표지가 없으면 기존 구성이다"
    assert rf.main_cf_state(main + "relayhost = [evil]\n", master, state) == "foreign", "손으로 고치면 기존 구성이다"
    assert rf.main_cf_state(main, master, None) == "foreign", "상태 파일이 없으면 우리 것이라 말하지 않는다"
    assert rf.applied_relay_fingerprint(state) == rf.relay_fingerprint(params)


def test_listener_table_reads_ipv4_and_ipv6():
    tcp = ("  sl  local_address rem_address   st\n"
           "   0: 0100007F:09DD 00000000:0000 0A 00000000:00000000\n"     # 127.0.0.1:2525 LISTEN
           "   1: 00000000:0019 00000000:0000 0A 00000000:00000000\n"     # 0.0.0.0:25 LISTEN
           "   2: 0100007F:22C3 0100007F:A000 01 00000000:00000000\n")    # established, 무시
    tcp6 = ("  sl  local_address                         rem_address   st\n"
            "   0: 00000000000000000000000001000000:22C3 00000000000000000000000000000000:0000 0A x\n"
            "   1: 00000000000000000000000000000000:0019 00000000000000000000000000000000:0000 0A x\n")
    found = rf.parse_listeners(tcp, tcp6)
    assert "127.0.0.1:2525" in found and "0.0.0.0:25" in found
    assert "[::1]:8899" in found and "[::]:25" in found
    assert rf.listening_on(found, 25) == ["0.0.0.0:25", "[::]:25"]
