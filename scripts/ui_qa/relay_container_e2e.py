"""ClovirAssist 로컬 릴레이 설정을 **진짜 Postfix** 로 잰다 (계획 M7, D-551).

`app/mail/relay_files.py` · `app/mail/relay_certs.py` 가 만드는 설정을 Ubuntu 24.04 컨테이너의 Postfix · OpenDKIM 에 그대로 얹고,
보안 계약 넷과 전달 경로를 실제 연결로 확인한다. 개발 PC 의 Docker 만 쓴다(랩 서버를 건드리지 않는다).

확인하는 것:
  1. 외부에서 접근할 수 없다 — 듣는 소켓이 127.0.0.1:2525 (와 서명 구성 요소의 127.0.0.1:8891)뿐이고 25번이 없다.
     컨테이너 밖(다른 네트워크 주소)에서 2525 에 붙으면 거절된다.
  2. ClovirAssist 만 쓸 수 있다 — 앱의 클라이언트 인증서로 붙으면 바깥 도메인 받는 사람을 받아 준다.
  3. 열린 중계가 될 수 없다 — 인증서 없이 보안 연결만 맺고 바깥 도메인을 넣으면 554 5.7.1 「Access denied」다. 보안 연결 없이는
     시작도 못 한다(530 5.7.0).
  4. 일반 로컬 프로세스가 임의로 발송할 수 없다 — 다른 OS 사용자가 2525 에 붙어도 3 과 같고, `sendmail` 명령은 거절된다.
  + 받는 도메인별 전달 서버(transport_maps)로 컨테이너 안의 받는 쪽에 전달되고, 그 메일에 DKIM 서명이 붙는다.
  + 해석할 수 없는 도메인은 반송되고(5.4.4), 닫힌 전달 서버로 가는 메일은 큐에 남는다(`postqueue -j` 의 지연 까닭). 실제 로그
    줄은 `dist/qa/relay-container/postfix.log` 에 남아 분류기 시험의 견본이 된다.

    python -m scripts.ui_qa.relay_container_e2e [--keep]

결과는 `dist/qa/relay-container/result.json` 과 표준 출력의 PASS · FAIL 줄이다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.mail import relay_certs, relay_files  # noqa: E402

IMAGE = "ubuntu:24.04"
NAME = "clovirassist-relay-e2e"
OUT = ROOT / "dist" / "qa" / "relay-container"
SENDER_DOMAIN = "example.test"
SINK_PORT = 2626
CLOSED_PORT = 2699

INSTALL = r"""
set -e
export DEBIAN_FRONTEND=noninteractive
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod 755 /usr/sbin/policy-rc.d
apt-get update -qq >/dev/null
echo "postfix postfix/main_mailer_type select No configuration" | debconf-set-selections
apt-get install -y -qq --no-install-recommends postfix opendkim libsasl2-modules ca-certificates python3 iproute2 >/dev/null
rm -f /usr/sbin/policy-rc.d
test ! -e /etc/postfix/main.cf && echo NO_MAIN_CF
useradd -m tester
"""

# 컨테이너 안에서 도는 시험(파이썬 표준 라이브러리만). 결과를 JSON 한 줄로 낸다.
PROBE = r'''
import json, os, smtplib, socket, ssl, subprocess, sys, threading, time

RESULTS = {}
SINK = []

def sink():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", %(sink)d)); srv.listen(5)
    while True:
        conn, _ = srv.accept()
        f = conn.makefile("rwb")
        def send(line): f.write((line + "\r\n").encode()); f.flush()
        send("220 sink ESMTP")
        data, in_data = [], False
        while True:
            raw = f.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if in_data:
                if line == ".":
                    in_data = False; SINK.append("\n".join(data)); data = []; send("250 2.0.0 sink queued")
                else:
                    data.append(line)
                continue
            cmd = line[:4].upper()
            if cmd in ("EHLO", "HELO"): send("250 sink")
            elif cmd == "DATA": in_data = True; send("354 go")
            elif cmd == "QUIT": send("221 bye"); break
            else: send("250 ok")
        conn.close()

threading.Thread(target=sink, daemon=True).start()
time.sleep(0.3)

server_ctx = lambda: ssl.create_default_context(cadata=open("/etc/postfix/clovirassist/server.crt").read())

def attempt(label, rcpt, *, cert, tls=True, data=False):
    try:
        s = smtplib.SMTP("127.0.0.1", 2525, timeout=15)
        s.ehlo("client.test")
        if tls:
            ctx = server_ctx()
            if cert:
                ctx.load_cert_chain("/root/client.pem")
            s.starttls(context=ctx); s.ehlo("client.test")
        code, msg = s.mail("noreply@%(domain)s")
        if code != 250:
            RESULTS[label] = {"stage": "mail", "code": code, "msg": msg.decode()}; s.close(); return
        code, msg = s.rcpt(rcpt)
        if code not in (250, 251) or not data:
            RESULTS[label] = {"stage": "rcpt", "code": code, "msg": msg.decode()}
            s.rset(); s.quit(); return
        code, msg = s.data(b"From: noreply@%(domain)s\r\nTo: " + rcpt.encode() + b"\r\nSubject: relay e2e\r\n\r\nhello\r\n")
        RESULTS[label] = {"stage": "data", "code": code, "msg": msg.decode()}
        s.quit()
    except Exception as exc:
        RESULTS[label] = {"stage": "error", "error": f"{type(exc).__name__}: {exc}"}

mode = sys.argv[1]
if mode == "root":
    attempt("cert_relay_out", "someone@outside.example", cert=True)
    attempt("cert_deliver_sink", "person@%(domain)s", cert=True, data=True)
    attempt("cert_unresolvable", "nobody@no-such-host.invalid", cert=True, data=True)
    attempt("cert_deferred", "later@deferred.test", cert=True, data=True)
    attempt("nocert_tls_out", "someone@outside.example", cert=False)
    attempt("plain_no_tls", "someone@outside.example", cert=False, tls=False)
    time.sleep(8)
    RESULTS["sink_messages"] = SINK
else:
    attempt("other_user_tls_out", "someone@outside.example", cert=False)
    p = subprocess.run(["/usr/sbin/sendmail", "-f", "x@%(domain)s", "victim@outside.example"],
                       input=b"Subject: x\n\nx\n", capture_output=True, timeout=20)
    RESULTS["other_user_sendmail"] = {"code": p.returncode, "err": p.stderr.decode()[-300:]}
print("RESULT " + json.dumps(RESULTS))
''' % {"sink": SINK_PORT, "domain": SENDER_DOMAIN}


def sh(*argv: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    return subprocess.run(list(argv), check=check, capture_output=True, text=True, input=input_text, env=env,
                          encoding="utf-8", errors="replace")


def dexec(script: str, *, user: str = "root", check: bool = True) -> subprocess.CompletedProcess:
    return sh("docker", "exec", "-u", user, "-i", NAME, "sh", "-c", script, check=check)


def put(path: str, text: str, mode: str = "0644") -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        tmp = fh.name
    try:
        sh("docker", "cp", tmp, f"{NAME}:{path}")
        dexec(f"chmod {mode} {path} && chown root:root {path}")
    finally:
        os.unlink(tmp)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="끝난 뒤 컨테이너를 남긴다")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sh("docker", "rm", "-f", NAME, check=False)
    sh("docker", "run", "-d", "--name", NAME, IMAGE, "sleep", "infinity")
    checks: list[tuple[str, bool, str]] = []
    try:
        got = dexec(INSTALL)
        checks.append(("설치 직후 main.cf 없음(No configuration)", "NO_MAIN_CF" in got.stdout, got.stdout.strip()[-80:]))
        proto = dexec("cat /etc/postfix/master.cf.proto").stdout

        params = relay_files.normalize_params({
            "delivery": "direct", "sender_domain": SENDER_DOMAIN, "helo_name": "relay.example.test",
            "ipv4_only": True, "dkim": {"selector": "ca1"},
            "transport_overrides": [{"domain": SENDER_DOMAIN, "host": "127.0.0.1"},
                                    {"domain": "deferred.test", "host": "127.0.0.1"}],
        })
        main_cf = relay_files.render_main_cf(params) + "maillog_file = /var/log/postfix.log\n"
        master_cf = relay_files.render_master_cf(proto)
        server_crt, server_key = relay_certs.make_server_cert()
        client = relay_certs.make_client_bundle()
        dkim_key = relay_certs.make_dkim_key()

        dexec(f"mkdir -p {relay_files.MANAGED_DIR} {relay_files.OPENDKIM_KEYS}/{SENDER_DOMAIN}")
        put(relay_files.MAIN_CF, main_cf)
        put(relay_files.MASTER_CF, master_cf)
        put(relay_files.SERVER_CERT, server_crt)
        put(relay_files.SERVER_KEY, server_key, "0600")
        put(relay_files.CLIENT_CERTS, relay_files.render_client_certs([relay_certs.fingerprint(client)]))
        transport = relay_files.render_transport(params["transport_overrides"])
        transport = transport.replace(f"{SENDER_DOMAIN} smtp:[127.0.0.1]:25", f"{SENDER_DOMAIN} smtp:[127.0.0.1]:{SINK_PORT}")
        transport = transport.replace("deferred.test smtp:[127.0.0.1]:25", f"deferred.test smtp:[127.0.0.1]:{CLOSED_PORT}")
        put(relay_files.TRANSPORT_MAP, transport)
        put(relay_files.OPENDKIM_CONF, relay_files.render_opendkim_conf(params["dkim"]))
        key_path = relay_files.dkim_key_path(SENDER_DOMAIN, "ca1")
        put(key_path, dkim_key, "0600")
        dexec(f"chown -R opendkim:opendkim {relay_files.OPENDKIM_KEYS} && chmod 0700 {relay_files.OPENDKIM_KEYS}/{SENDER_DOMAIN}"
              f" && chown opendkim:opendkim {key_path}")
        put("/root/client.pem", client, "0600")
        put("/tmp/probe.py", PROBE)
        dexec("chmod 0644 /tmp/probe.py")

        check = dexec("postfix check 2>&1; echo EXIT=$?", check=False).stdout
        checks.append(("postfix check 통과", "EXIT=0" in check and "warning" not in check.lower(), check.strip()[-300:]))
        dexec("mkdir -p /run/opendkim && chown opendkim:opendkim /run/opendkim && /usr/sbin/opendkim -x /etc/opendkim.conf")
        # systemd 유닛의 ExecStartPre 와 같은 준비(감옥 안의 resolv.conf · services 복사)를 한 뒤 띄운다.
        start = dexec("/usr/lib/postfix/configure-instance.sh - >/dev/null 2>&1; postfix start 2>&1; echo EXIT=$?",
                      check=False).stdout
        checks.append(("postfix start", "EXIT=0" in start, start.strip()[-200:]))
        time.sleep(3)
        listeners = dexec("ss -ltnH | awk '{print $4}' | sort -u").stdout.split()
        checks.append(("받는 문은 127.0.0.1:2525 하나(+서명 8891)",
                       sorted(listeners) == ["127.0.0.1:2525", "127.0.0.1:8891"], ",".join(listeners)))
        checks.append(("25번을 아무도 듣지 않음", not any(x.endswith(":25") for x in listeners), ",".join(listeners)))

        root_run = dexec("python3 /tmp/probe.py root", check=False)
        other_run = dexec("python3 /tmp/probe.py other", user="tester", check=False)
        results: dict = {}
        for run in (root_run, other_run):
            for line in run.stdout.splitlines():
                if line.startswith("RESULT "):
                    results.update(json.loads(line[len("RESULT "):]))
        r = results
        checks.append(("인증서로 바깥 받는 사람 허가", r.get("cert_relay_out", {}).get("code") in (250, 251),
                       json.dumps(r.get("cert_relay_out"), ensure_ascii=False)))
        checks.append(("인증서 없는 보안 연결은 중계 거절",
                       r.get("nocert_tls_out", {}).get("code") == 554
                       and "denied" in r.get("nocert_tls_out", {}).get("msg", ""),
                       json.dumps(r.get("nocert_tls_out"), ensure_ascii=False)))
        plain = r.get("plain_no_tls", {})
        checks.append(("보안 연결 없이는 시작 못 함", plain.get("code") == 530 or plain.get("stage") == "error",
                       json.dumps(plain, ensure_ascii=False)))
        checks.append(("다른 OS 사용자도 인증서 없으면 거절",
                       r.get("other_user_tls_out", {}).get("code") == 554,
                       json.dumps(r.get("other_user_tls_out"), ensure_ascii=False)))
        sendmail = r.get("other_user_sendmail", {})
        checks.append(("다른 OS 사용자의 sendmail 거절", sendmail.get("code") not in (0, None),
                       json.dumps(sendmail, ensure_ascii=False)))
        delivered = r.get("cert_deliver_sink", {})
        checks.append(("인증서로 보낸 메일이 접수(큐 id)", delivered.get("code") == 250 and "queued as" in delivered.get("msg", ""),
                       json.dumps(delivered, ensure_ascii=False)))
        sink = r.get("sink_messages") or []
        checks.append(("받는 도메인별 전달 서버로 전달됨", len(sink) >= 1, f"{len(sink)}통"))
        checks.append(("DKIM 서명이 붙음", any("DKIM-Signature:" in m and "s=ca1" in m.replace("\n", "") for m in sink),
                       (sink[0][:200] if sink else "")))

        # 외부(다른 네트워크 주소)에서 2525 로 붙어 본다 — 컨테이너 IP 로.
        ip = sh("docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", NAME).stdout.strip()
        outside = dexec(f"python3 -c \"import socket;s=socket.socket();s.settimeout(3);print(s.connect_ex(('{ip}',2525)))\"",
                        check=False).stdout.strip()
        checks.append(("컨테이너 주소의 2525 는 닫힘", outside not in ("0", ""), f"connect_ex={outside} ({ip})"))

        time.sleep(4)
        queue = dexec("postqueue -j", check=False).stdout
        (OUT / "postqueue.jsonl").write_text(queue, encoding="utf-8")
        checks.append(("닫힌 전달 서버로 가는 메일은 큐에 남음", "deferred.test" in queue and "delay_reason" in queue, queue[:200]))
        log = dexec("cat /var/log/postfix.log", check=False).stdout
        (OUT / "postfix.log").write_text(log, encoding="utf-8")
        checks.append(("해석 못 하는 도메인은 반송(5.4.4)", "dsn=5.4.4, status=bounced" in log, ""))
        submit = dexec("postconf -h authorized_submit_users; postconf -h inet_interfaces", check=False).stdout.split("\n")
        checks.append(("authorized_submit_users 빈 목록", submit[0].strip() == "", submit[0]))
    finally:
        if not args.keep:
            sh("docker", "rm", "-f", NAME, check=False)

    ok = all(passed for _, passed, _ in checks)
    for label, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + label + ("" if passed else f" :: {detail}"))
    (OUT / "result.json").write_text(json.dumps(
        {"ok": ok, "checks": [{"label": l, "ok": p, "detail": d} for l, p, d in checks]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("RELAY_CONTAINER_E2E_OK" if ok else "RELAY_CONTAINER_E2E_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
