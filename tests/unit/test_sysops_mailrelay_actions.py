# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""로컬 릴레이 특권 헬퍼 동작 (계획 M7, D-551) — 가짜 시스템(`FakeRunner`)으로 root 없이 잰다.

못박는 것:
  * 구성 요소 상태 다섯(준비됨 · 동작 중 · 멈춤 · 설치되지 않음 · 기존 구성)과 다른 메일 발송 프로그램이 있으면 「기존 구성」.
  * `apply` 는 기존 구성 · 다른 MTA 가 있으면 아무것도 쓰지 않고 거절한다. 인수 인자는 없다(모르는 키 거절).
  * 켠 뒤 받는 문이 루프백 2525 하나가 아니면(25번이 열렸으면) 끄고 실패로 돌려준다 - 엔진이 설정 파일을 되돌린다.
  * `postfix check` 가 거절하면 서비스를 켜지 않고 되돌린다.
  * 상위 SMTP 비밀번호는 `sasl_passwd`(0600)에만 쓰이고 응답 · 백업 대상에 없다. 앱 열쇠는 비밀 칸(0640)에 쓰인다.
  * DKIM 키는 opendkim 만 읽는다(0600, 디렉터리 0700). 이미 있는 선택자의 키는 덮지 않는다.
  * 로그 읽기의 인자(큐 id · 시작 시각)는 모양을 본다.
  * 모든 동작은 허용 목록의 실행 파일만 부른다(가짜 시스템이 목록 밖을 막는다).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.mail import relay_certs, relay_files as rf
from app.sysops import actions as registry
from app.sysops import actions_mailrelay as mr
from tests.fakes.sysops import FakeRunner

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
SECRETS = "/etc/clovirassist/secrets"
PROTO = "smtp      inet  n       -       y       -       -       smtpd\npickup    unix  n       -       y       60      1       pickup\nqmgr      unix  n       -       n       300     1       qmgr\nsmtp      unix  -       -       y       -       -       smtp\n"
DPKG = [mr.DPKG_QUERY, "-W", f"--showformat={mr.PACKAGE_FORMAT}"]
PKG_OK = ("ii |postfix|3.8.6-1ubuntu0.1|default-mta, mail-transport-agent\n"
          "ii |opendkim|2.11.0~beta2-9build4|\n"
          "ii |libsasl2-modules|2.1.28|\n")
TCP_HEAD = "  sl  local_address rem_address   st\n"
L2525 = "   0: 0100007F:09DD 00000000:0000 0A x\n"
L8891 = "   1: 0100007F:22BB 00000000:0000 0A x\n"
L25 = "   2: 00000000:0019 00000000:0000 0A x\n"


@pytest.fixture(autouse=True)
def _secrets_dir(monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", SECRETS)


def _runner(*, packages=PKG_OK, main_cf=None, active="inactive", enabled="disabled", tcp=""):
    runner = FakeRunner({rf.MASTER_CF_PROTO: PROTO, "/proc/net/tcp": TCP_HEAD + tcp, "/proc/net/tcp6": TCP_HEAD})
    if main_cf is not None:
        runner.files[rf.MAIN_CF] = main_cf
    runner.reply(DPKG, out=packages)
    runner.reply([mr.SYSTEMCTL, "is-active", rf.POSTFIX_INSTANCE_UNIT], out=active + "\n", code=0 if active == "active" else 3)
    runner.reply([mr.SYSTEMCTL, "is-enabled", rf.POSTFIX_UNIT], out=enabled + "\n", code=0 if enabled == "enabled" else 1)
    runner.reply([mr.SYSTEMCTL, "is-active", rf.OPENDKIM_UNIT], out="inactive\n", code=3)
    runner.reply([mr.SYSTEMCTL, "is-enabled", rf.OPENDKIM_UNIT], out="disabled\n", code=1)
    for verb in (["disable", "--now", rf.POSTFIX_UNIT], ["stop", rf.POSTFIX_INSTANCE_UNIT],
                 ["disable", "--now", rf.OPENDKIM_UNIT], ["enable", rf.POSTFIX_UNIT], ["restart", rf.POSTFIX_UNIT],
                 ["enable", rf.OPENDKIM_UNIT], ["restart", rf.OPENDKIM_UNIT]):
        runner.reply([mr.SYSTEMCTL, *verb])
    runner.reply([mr.POSTFIX, "check"])
    runner.reply([mr.POSTQUEUE, "-j"], out="")
    return runner


def _started(runner, *, tcp=L2525):
    """`restart` 뒤 서비스가 돌고 듣는 소켓이 생긴 것처럼 가짜 시스템을 바꾼다."""
    original = runner.run

    def run(argv, *, timeout=20):
        got = original(argv, timeout=timeout)
        if argv[1:] == ["restart", rf.POSTFIX_UNIT]:
            runner.reply([mr.SYSTEMCTL, "is-active", rf.POSTFIX_INSTANCE_UNIT], out="active\n")
            runner.files["/proc/net/tcp"] = TCP_HEAD + tcp
        if argv[1:] == ["restart", rf.OPENDKIM_UNIT]:
            runner.reply([mr.SYSTEMCTL, "is-active", rf.OPENDKIM_UNIT], out="active\n")
        return got

    runner.run = run
    return runner


def _execute(runner, action, params=None):
    return registry.execute(runner, action, params or {}, backup_root="/var/backups/x", now=NOW)


SMART = {"delivery": "smarthost", "sender_domain": "goodmit.co.kr", "helo_name": "",
         "smarthost": {"host": "smtp.office365.com", "port": 587, "security": "starttls", "username": "notify@goodmit.co.kr"}}
DIRECT = {"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "mail.goodmit.co.kr",
          "dkim": None, "transport_overrides": [{"domain": "goodmit.co.kr", "host": "goodmit-co-kr.mail.protection.outlook.com"}]}


# ── 상태 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kwargs, expected", [
    ({"packages": ""}, "not_installed"),
    ({"packages": "ii |exim4-daemon-light|4.97|mail-transport-agent\n"}, "foreign"),
    ({"main_cf": "myhostname = mail.example.com\n"}, "foreign"),
    ({}, "ready"),
    ({"active": "active", "tcp": L2525}, "running"),
])
def test_component_state(kwargs, expected):
    result = _execute(_runner(**kwargs), "mailrelay.status")
    assert result.ok and result.data["component"] == expected


def test_status_reports_only_relevant_listeners():
    result = _execute(_runner(active="active", tcp=L2525 + L25), "mailrelay.status")
    assert result.data["listeners"] == ["0.0.0.0:25", "127.0.0.1:2525"]


# ── 켜기 ─────────────────────────────────────────────────────────────────────


def test_apply_refuses_a_foreign_configuration_and_writes_nothing():
    runner = _runner(main_cf="myhostname = mail.example.com\n")
    before = dict(runner.files)
    result = _execute(runner, "mailrelay.apply", DIRECT)
    assert not result.ok and "기존 메일 발송 구성" in result.detail
    # 엔진이 뜬 되돌리기 사본(/var/backups)만 늘었다 - 원래 자리의 파일은 그대로다.
    assert {k: v for k, v in runner.files.items() if not k.startswith("/var/backups/")} == before
    assert not any(call[1:2] == ("enable",) for call in runner.calls if call[0] == mr.SYSTEMCTL)


def test_apply_refuses_when_another_mta_is_installed():
    result = _execute(_runner(packages="ii |sendmail-bin|8.17|mail-transport-agent\n"), "mailrelay.apply", DIRECT)
    assert not result.ok and "기존 메일 발송 구성" in result.detail


def test_there_is_no_takeover_argument():
    result = _execute(_runner(), "mailrelay.apply", {**DIRECT, "takeover": True})
    assert not result.ok and "알 수 없는" in result.detail


def test_apply_direct_writes_managed_files_and_starts():
    runner = _started(_runner())
    result = _execute(runner, "mailrelay.apply", DIRECT)
    assert result.ok, result.detail
    assert runner.files[rf.MAIN_CF].startswith(rf.MARKER)
    assert rf.main_cf_state(runner.files[rf.MAIN_CF], runner.files[rf.MASTER_CF], runner.files[rf.STATE_FILE]) == "managed"
    assert "127.0.0.1:2525 inet" in runner.files[rf.MASTER_CF]
    assert runner.modes[rf.SERVER_KEY] == 0o600
    client_path = f"{SECRETS}/smtp.relay_client"
    assert runner.modes[client_path] == 0o640
    fp = relay_certs.fingerprint(runner.files[client_path])
    assert fp in runner.files[rf.CLIENT_CERTS] and result.data["client_fingerprint"] == fp
    assert runner.files[rf.TRANSPORT_MAP].splitlines()[1] == "goodmit.co.kr smtp:[goodmit-co-kr.mail.protection.outlook.com]:25"
    assert rf.SASL_PASSWD not in runner.files
    assert (mr.POSTFIX, "check") in runner.calls
    # 백업 대상에 개인키 · 비밀번호 · 앱 열쇠가 없다.
    touched = mr._apply_touches({})
    assert rf.SERVER_KEY not in touched and rf.SASL_PASSWD not in touched and client_path not in touched


def test_apply_smarthost_puts_the_password_only_in_sasl_passwd():
    runner = _started(_runner())
    secret = "relay-pw-SENTINEL-77"
    runner.files[f"{SECRETS}/smtp.relay_password"] = secret
    result = _execute(runner, "mailrelay.apply", SMART)
    assert result.ok, result.detail
    assert runner.files[rf.SASL_PASSWD] == f"[smtp.office365.com]:587 notify@goodmit.co.kr:{secret}\n"
    assert runner.modes[rf.SASL_PASSWD] == 0o600
    assert secret not in result.detail and secret not in str(result.data)
    assert secret not in runner.files[rf.MAIN_CF]


def test_apply_smarthost_without_a_saved_password_is_refused():
    result = _execute(_started(_runner()), "mailrelay.apply", SMART)
    assert not result.ok and "비밀번호" in result.detail


def test_a_failed_postfix_check_starts_nothing_and_rolls_back():
    runner = _runner()
    runner.reply([mr.POSTFIX, "check"], code=1, err="postfix: fatal: bad config")
    result = _execute(runner, "mailrelay.apply", DIRECT)
    assert not result.ok and result.rolled_back
    assert rf.MAIN_CF not in runner.files and rf.STATE_FILE not in runner.files, "없던 파일은 지워져야 원래 상태다"
    assert not any(call[1:2] in (("enable",), ("restart",)) for call in runner.calls if call[0] == mr.SYSTEMCTL)


def test_if_port_25_is_listening_after_start_the_relay_is_stopped():
    runner = _started(_runner(), tcp=L2525 + L25)
    result = _execute(runner, "mailrelay.apply", DIRECT)
    assert not result.ok and "비활성화했습니다" in result.detail
    assert "port 25" in result.data["technical"]
    assert (mr.SYSTEMCTL, "disable", "--now", rf.POSTFIX_UNIT) in runner.calls
    assert result.rolled_back


def test_dkim_needs_a_key_first():
    result = _execute(_started(_runner()), "mailrelay.apply", {**DIRECT, "dkim": {"selector": "ca1"}})
    assert not result.ok and "DKIM 키" in result.detail


def test_dkim_signing_starts_the_milter_and_listens_on_loopback():
    runner = _started(_runner(), tcp=L2525 + L8891)
    runner.files[rf.dkim_key_path("goodmit.co.kr", "ca1")] = relay_certs.make_dkim_key()
    result = _execute(runner, "mailrelay.apply", {**DIRECT, "dkim": {"selector": "ca1"}})
    assert result.ok, result.data
    assert runner.files[rf.OPENDKIM_CONF].startswith(rf.MARKER)
    assert "smtpd_milters = inet:127.0.0.1:8891" in runner.files[rf.MAIN_CF]


# ── 끄기 · DKIM · 로그 ───────────────────────────────────────────────────────


def test_disable_turns_both_services_off_and_keeps_the_files():
    runner = _runner(main_cf="x")
    result = _execute(runner, "mailrelay.disable")
    assert result.ok
    assert (mr.SYSTEMCTL, "disable", "--now", rf.POSTFIX_UNIT) in runner.calls
    assert (mr.SYSTEMCTL, "disable", "--now", rf.OPENDKIM_UNIT) in runner.calls
    assert runner.files[rf.MAIN_CF] == "x"


def test_dkim_key_is_private_to_opendkim_and_never_overwritten():
    runner = _runner()
    result = _execute(runner, "mailrelay.dkim_generate", {"domain": "goodmit.co.kr", "selector": "ca1"})
    assert result.ok and result.changed
    path = rf.dkim_key_path("goodmit.co.kr", "ca1")
    assert runner.modes[path] == 0o600 and runner.owners[path] == ("opendkim", "opendkim")
    assert runner.owners[f"{rf.OPENDKIM_KEYS}/goodmit.co.kr"] == ("opendkim", "opendkim")
    assert runner.modes[f"{rf.OPENDKIM_KEYS}/goodmit.co.kr"] == 0o700
    assert "PRIVATE" not in str(result.data) and result.data["public"] == relay_certs.dkim_public(runner.files[path])
    key = runner.files[path]
    again = _execute(runner, "mailrelay.dkim_generate", {"domain": "goodmit.co.kr", "selector": "ca1"})
    assert again.ok and not again.changed and runner.files[path] == key


@pytest.mark.parametrize("params", [
    {"queue_ids": [], "since": int(time.time())},
    {"queue_ids": ["ABC; rm -rf /"], "since": int(time.time())},
    {"queue_ids": ["ABCDEF12"], "since": 0},
    {"queue_ids": ["ABCDEF12"] * 51, "since": int(time.time())},
])
def test_log_arguments_are_checked(params):
    result = _execute(_runner(), "mailrelay.log", params)
    assert not result.ok


def test_log_returns_a_summary_not_the_raw_journal():
    runner = _runner()
    since = int(time.time()) - 60
    runner.reply([mr.JOURNALCTL, "-u", rf.POSTFIX_INSTANCE_UNIT, "--since", f"@{since}", "-o", "cat", "--no-pager", "-n", "2000"],
                 out="C87DBF6954: to=<a@b.com>, relay=mx.b.com[192.0.2.1]:25, delay=1, delays=0/0/0/1, dsn=2.0.0, status=sent (250 ok)\n"
                     "OTHERQUEUE: to=<secret@c.com>, relay=none, dsn=5.1.1, status=bounced (said: 550 no)\n")
    result = _execute(runner, "mailrelay.log", {"queue_ids": ["C87DBF6954"], "since": since})
    assert result.ok and list(result.data["results"]) == ["C87DBF6954"]
    assert result.data["results"]["C87DBF6954"]["status"] == "delivered"
    assert "secret@c.com" not in str(result.data), "물어보지 않은 큐 id 의 줄은 돌려주지 않는다"


def test_every_relay_action_only_uses_allowed_binaries():
    # 가짜 시스템은 허용 목록 밖의 실행 파일을 막는다 - 모든 동작을 한 번씩 돌려 본다.
    runner = _started(_runner())
    runner.files[f"{SECRETS}/smtp.relay_password"] = "x"
    for action, params in (("mailrelay.status", {}), ("mailrelay.apply", SMART), ("mailrelay.disable", {}),
                           ("mailrelay.dkim_generate", {"domain": "goodmit.co.kr", "selector": "ca2"}),
                           ("mailrelay.queue", {}), ("mailrelay.flush", {})):
        _execute(runner, action, params)
    assert all(call[0] in __import__("app.sysops.runner", fromlist=["ALLOWED_BINARIES"]).ALLOWED_BINARIES
               for call in runner.calls)


UBUNTU_DEFAULT_OPENDKIM = """# This is a basic configuration for signing and verifying. It can easily be
# adapted to suit a basic installation. See opendkim.conf(5) and
# /usr/share/doc/opendkim/examples/opendkim.conf.sample for complete
# documentation of available configuration parameters.
Syslog			yes
SyslogSuccess		yes
#LogWhy			no

# Common signing and verification parameters. In Debian, the "From" header is
# oversigned, because it is often the identity key used by reputation systems
# and thus somewhat security sensitive.
Canonicalization	relaxed/simple
#Mode			sv
#SubDomains		no
OversignHeaders		From

# Signing domain, selector, and key (required). For example, perform signing
# for domain "example.com" with selector "2020" (2020._domainkey.example.com),
# using the private key stored in /etc/dkimkeys/example.private. More granular
# setup options can be found in /usr/share/doc/opendkim/README.opendkim.
#Domain			example.com
#Selector		2020
#KeyFile		/etc/dkimkeys/example.private

UserID			opendkim
UMask			007
Socket			local:/run/opendkim/opendkim.sock
PidFile			/run/opendkim/opendkim.pid
TrustAnchorFile		/usr/share/dns/root.key
"""


def test_the_package_default_opendkim_conf_is_not_foreign_but_a_signing_setup_is():
    """실제 systemd 컨테이너가 찾은 결함: 꾸러미 기본 파일의 주석 예시(`#KeyFile …`)를 기존 서명 설정으로 읽었다."""
    assert mr._opendkim_is_ours_or_default(UBUNTU_DEFAULT_OPENDKIM)
    assert mr._opendkim_is_ours_or_default(None)
    assert mr._opendkim_is_ours_or_default(rf.render_opendkim_conf({"domain": "x.com", "selector": "ca1"}))
    assert not mr._opendkim_is_ours_or_default(UBUNTU_DEFAULT_OPENDKIM.replace("#KeyFile", "KeyFile"))
    assert not mr._opendkim_is_ours_or_default(UBUNTU_DEFAULT_OPENDKIM.replace(
        "local:/run/opendkim/opendkim.sock", "inet:12301@localhost"))


def test_disable_ignores_port_25_that_belongs_to_someone_else():
    runner = _runner(tcp=L25)
    result = _execute(runner, "mailrelay.disable")
    assert result.ok, result.data
