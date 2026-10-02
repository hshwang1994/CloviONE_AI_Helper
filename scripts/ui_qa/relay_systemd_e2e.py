"""ClovirAssist 로컬 릴레이를 **진짜 systemd · apt · Postfix** 로 끝에서 끝까지 잰다 (계획 M7, D-551).

`relay_container_e2e.py` 가 설정 파일 자체(보안 계약 넷)를 잰다면, 이 하네스는 제품이 실제로 하는 일을 그대로 돌린다:

  1. 설치기의 메일 구성 요소 단계(`deploy/install.sh::install_mail_relay`) — 꾸러미가 깔리고, 설치하는 동안 서비스가 뜨지 않으며
     (policy-rc.d), 끝나면 postfix · opendkim 이 disabled · inactive 이고 25 · 2525 · 8891 을 아무도 듣지 않는다. 다시 돌려도 같다.
  2. 특권 헬퍼 동작(`app/sysops/actions_mailrelay.py`)을 실제 실행기(`RealRunner`, root)로 — 상태 → DKIM 키 → 켜기(직접 전달 ·
     DKIM · 받는 도메인별 전달 서버) → 앱의 실제 전송기(`SmtpTransport`, 클라이언트 인증서 · 고정 서버 인증서)로 한 통 →
     받는 쪽(컨테이너 안 25번 받는 쪽)에 DKIM 서명이 붙어 도착 → 로그 읽기가 그 큐 id 를 「전달함」으로 → 끄기.
  3. 다른 메일 발송 프로그램(exim4)이 있는 서버에서는 설치기가 postfix 를 깔지 않는다.

Ubuntu 24.04 컨테이너에서 systemd 를 PID 1 로 띄운다(Docker `--privileged`). 개발 PC 의 Docker 만 쓰고 랩 서버는 건드리지 않는다.

    python -m scripts.ui_qa.relay_systemd_e2e [--keep]

결과는 `dist/qa/relay-systemd/result.json` 과 표준 출력의 PASS · FAIL 줄이다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dist" / "qa" / "relay-systemd"
BASE_IMAGE = "ubuntu:24.04"
SD_IMAGE = "clovirassist-relay-sd:24.04"
NAME = "clovirassist-relay-sd"
PLAIN = "clovirassist-relay-plain"

INSTALL_FUNCS_START = "# ── ClovirAssist 로컬 릴레이 구성 요소 (D-551)"
INSTALL_FUNCS_END = "\nstage_1_apt() {"

STUBS = r'''
LOG=/tmp/install.log
OFFLINE=0
WITHOUT_MAIL_RELAY=0
WHEELHOUSE=""
MAIL_DEBS=""
SLUG=clovirassist
log()  { echo "[log] $*"; echo "$*" >>"$LOG"; }
fail() { echo "FAIL_REASON=$1"; echo "FAIL_ACTION=${2:-}"; return "${3:-20}"; }
'''

HELPER = r'''
import json, os, smtplib, socket, threading, time
os.environ["SECRETS_DIR"] = "/etc/clovirassist/secrets"
from datetime import datetime, timezone
from pathlib import Path
from app.sysops import actions
from app.sysops.runner import RealRunner
from app.mail import relay_files as rf

R = RealRunner()
OUT = {}
def run(name, params=None):
    res = actions.execute(R, name, params or {}, backup_root="/var/backups/clovirassist/sysops", now=datetime.now(timezone.utc))
    return {"ok": res.ok, "detail": res.detail, "data": res.data, "rolled_back": res.rolled_back}

OUT["status_before"] = run("mailrelay.status")
OUT["dkim"] = run("mailrelay.dkim_generate", {"domain": "example.test", "selector": "ca1"})
params = rf.normalize_params({"delivery": "direct", "sender_domain": "example.test", "helo_name": "relay.example.test",
    "ipv4_only": True, "dkim": {"selector": "ca1"},
    "transport_overrides": [{"domain": "example.test", "host": "127.0.0.2"}]})
OUT["apply"] = run("mailrelay.apply", params)
OUT["status_running"] = run("mailrelay.status", {"dkim": {"domain": "example.test", "selector": "ca1"}})
key = Path(rf.dkim_key_path("example.test", "ca1")).stat()
OUT["dkim_key_mode"] = oct(key.st_mode & 0o777)
import pwd
OUT["dkim_key_owner"] = pwd.getpwuid(key.st_uid).pw_name

# 받는 쪽 — 켠 뒤에 띄운다(켜기는 25번이 비어 있어야 통과한다). 받은 메일 원문을 모은다. 127.0.0.1:25 로 보내면 Postfix 가
# 「loops back to myself」(5.4.6)로 반송한다(자기 주소의 25번) - 루프백의 다른 주소 127.0.0.2 를 쓴다.
SINK = []
def sink():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.2", 25)); srv.listen(5)
    while True:
        conn, _ = srv.accept(); f = conn.makefile("rwb")
        def send(line): f.write((line + "\r\n").encode()); f.flush()
        send("220 sink ESMTP"); data, in_data = [], False
        while True:
            raw = f.readline()
            if not raw: break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if in_data:
                if line == ".": in_data = False; SINK.append("\n".join(data)); data = []; send("250 2.0.0 sink accepted")
                else: data.append(line)
                continue
            cmd = line[:4].upper()
            if cmd in ("EHLO", "HELO"): send("250 sink")
            elif cmd == "DATA": in_data = True; send("354 go")
            elif cmd == "QUIT": send("221 bye"); break
            else: send("250 ok")
        conn.close()
threading.Thread(target=sink, daemon=True).start()
time.sleep(0.5)

# 앱의 실제 전송기로 한 통 — 로컬 릴레이 방식 설정, 비밀 칸의 클라이언트 열쇠, /etc/postfix 의 고정 서버 인증서.
from app.core.secret_refs import FileSecretReferenceProvider
from app.mail.config import smtp_config
from app.mail.transport import SmtpTransport
cfg = smtp_config({"enabled": True, "from_address": "noreply@example.test", "from_name": "ClovirAssist", "mode": "local_relay",
                   "relay": {"delivery": "direct", "helo_name": "relay.example.test", "dkim_enabled": True, "dkim_selector": "ca1",
                             "transport_overrides": [{"domain": "example.test", "host": "127.0.0.2"}]}})
provider = FileSecretReferenceProvider(Path("/etc/clovirassist/secrets"))
try:
    receipt = SmtpTransport().send(cfg, provider, to_email="person@example.test", subject="relay systemd e2e",
                                   body="평문 본문입니다.", html="<p>본문</p>")
    OUT["send"] = {"ok": True, "response": receipt.response, "message_id": receipt.message_id}
except Exception as exc:
    OUT["send"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
try:
    OUT["verify"] = SmtpTransport().verify(cfg, provider, probe_recipient="someone@outside.example")
except Exception as exc:
    OUT["verify"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
time.sleep(6)
OUT["sink_count"] = len(SINK)
OUT["sink_has_dkim"] = any("DKIM-Signature:" in m and "s=ca1" in m.replace("\n", "") for m in SINK)
qid = None
if OUT["send"].get("ok"):
    from app.mail.relay_log import queue_id_from_response
    qid = queue_id_from_response(OUT["send"]["response"])
OUT["queue_id"] = qid
if qid:
    OUT["log"] = run("mailrelay.log", {"queue_ids": [qid], "since": int(time.time()) - 600})
OUT["queue"] = run("mailrelay.queue")
OUT["disable"] = run("mailrelay.disable")
OUT["status_after"] = run("mailrelay.status")
print("RESULT " + json.dumps(OUT, ensure_ascii=False, default=str))
'''


def sh(*argv: str, check: bool = True, timeout: int = 1800) -> subprocess.CompletedProcess:
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    return subprocess.run(list(argv), check=check, capture_output=True, text=True, env=env, timeout=timeout,
                          encoding="utf-8", errors="replace")


def dexec(name: str, script: str, *, check: bool = False, timeout: int = 1800) -> subprocess.CompletedProcess:
    return sh("docker", "exec", "-i", name, "bash", "-c", script, check=check, timeout=timeout)


def put(name: str, path: str, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        tmp = fh.name
    try:
        sh("docker", "cp", tmp, f"{name}:{path}")
    finally:
        os.unlink(tmp)


def installer_functions() -> str:
    text = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    start = text.index(INSTALL_FUNCS_START)
    end = text.index(INSTALL_FUNCS_END, start)
    return STUBS + text[start:end] + "\n"


def ensure_image() -> None:
    if sh("docker", "image", "inspect", SD_IMAGE, check=False).returncode == 0:
        return
    sh("docker", "rm", "-f", "relay-sd-build", check=False)
    sh("docker", "run", "-d", "--name", "relay-sd-build", BASE_IMAGE, "sleep", "infinity")
    got = dexec("relay-sd-build", "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq >/dev/null && "
                "apt-get install -y -qq --no-install-recommends systemd systemd-sysv dbus iproute2 python3-venv python3-pip "
                "ca-certificates >/dev/null && echo BUILT")
    if "BUILT" not in got.stdout:
        raise SystemExit("systemd 이미지를 만들지 못했습니다: " + got.stderr[-500:])
    sh("docker", "commit", "relay-sd-build", SD_IMAGE)
    sh("docker", "rm", "-f", "relay-sd-build", check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []
    ensure_image()
    for name in (NAME, PLAIN):
        sh("docker", "rm", "-f", name, check=False)
    sh("docker", "run", "-d", "--name", NAME, "--privileged", "--cgroupns=host", "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw",
       "--tmpfs", "/run", "--tmpfs", "/run/lock", SD_IMAGE, "/lib/systemd/systemd")
    try:
        for _ in range(60):
            state = dexec(NAME, "systemctl is-system-running 2>/dev/null").stdout.strip()
            if state in ("running", "degraded"):
                break
            time.sleep(1)
        checks.append(("systemd 가 PID 1 로 떴다", state in ("running", "degraded"), state))

        put(NAME, "/tmp/mailrelay.sh", installer_functions())
        # 공식 Ubuntu 컨테이너 이미지에는 policy-rc.d 가 이미 있다 - 설치기는 그것을 건드리지 않고 mask 로 막아야 한다.
        guard_before = dexec(NAME, "sha256sum /usr/sbin/policy-rc.d 2>/dev/null || echo NONE").stdout.strip()
        first = dexec(NAME, "source /tmp/mailrelay.sh; install_mail_relay; echo RC=$?; echo NOTE=$MAIL_RELAY_NOTE")
        (OUT / "install-first.txt").write_text(first.stdout + first.stderr, encoding="utf-8")
        checks.append(("설치기: 메일 구성 요소 설치 성공(RC=0)", "RC=0" in first.stdout, first.stdout[-300:]))
        checks.append(("설치기: 「준비됨(꺼짐)」", "준비됨(꺼짐)" in first.stdout, first.stdout[-200:]))
        state = dexec(NAME, "dpkg -s postfix opendkim libsasl2-modules >/dev/null && echo PKGS; "
                            "systemctl is-enabled postfix.service; systemctl is-enabled opendkim.service; "
                            "systemctl is-active postfix.service postfix@-.service opendkim.service; "
                            "ss -ltnH | awk '{print $4}' | grep -E ':(25|2525|8891)$' || echo NO_MAIL_LISTENERS; "
                            "systemctl is-enabled postfix.service opendkim.service | grep -c masked || true; "
                            "test -e /etc/postfix/main.cf && echo MAIN_CF || echo NO_MAIN_CF").stdout
        (OUT / "state-after-install.txt").write_text(state, encoding="utf-8")
        lines = state.split()
        checks.append(("꾸러미 셋이 깔렸다", "PKGS" in state, state[:80]))
        checks.append(("postfix · opendkim 이 disabled", lines.count("disabled") == 2, state[:160]))
        checks.append(("세 유닛이 inactive", state.count("inactive") >= 3, state[:200]))
        checks.append(("메일 포트를 아무도 듣지 않는다", "NO_MAIL_LISTENERS" in state, state))
        guard_after = dexec(NAME, "sha256sum /usr/sbin/policy-rc.d 2>/dev/null || echo NONE").stdout.strip()
        checks.append(("원래 있던 policy-rc.d 는 그대로이고 mask 는 풀렸다",
                       guard_before == guard_after and "masked" not in state, f"{guard_before} → {guard_after}")),
        checks.append(("main.cf 없음(No configuration)", "NO_MAIN_CF" in state, state))
        again = dexec(NAME, "source /tmp/mailrelay.sh; install_mail_relay; echo RC=$?; echo NOTE=$MAIL_RELAY_NOTE")
        checks.append(("설치기를 다시 돌려도 무해", "RC=0" in again.stdout and "준비됨(꺼짐)" in again.stdout, again.stdout[-200:]))

        # 앱 코드와 실행 환경 — 헬퍼는 앱의 venv 로 root 로 돈다.
        dexec(NAME, "mkdir -p /opt/clovirassist")
        sh("docker", "cp", str(ROOT / "requirements.txt"), f"{NAME}:/opt/clovirassist/requirements.txt")
        sh("docker", "cp", str(ROOT / "app"), f"{NAME}:/opt/clovirassist/app")
        venv = dexec(NAME, "cd /opt/clovirassist && python3 -m venv venv && venv/bin/pip install -q -r requirements.txt "
                           ">/tmp/pip.log 2>&1 && echo VENV_OK || tail -5 /tmp/pip.log", timeout=1800)
        checks.append(("앱 실행 환경 준비", "VENV_OK" in venv.stdout, venv.stdout[-300:]))
        dexec(NAME, "mkdir -p /etc/clovirassist/secrets /var/backups/clovirassist/sysops && chmod 0750 /etc/clovirassist/secrets")
        put(NAME, "/tmp/helper_e2e.py", HELPER)
        run = dexec(NAME, "cd /opt/clovirassist && PYTHONPATH=/opt/clovirassist venv/bin/python /tmp/helper_e2e.py", timeout=600)
        (OUT / "helper.txt").write_text(run.stdout + "\n" + run.stderr, encoding="utf-8")
        result = {}
        for line in run.stdout.splitlines():
            if line.startswith("RESULT "):
                result = json.loads(line[len("RESULT "):])
        r = result
        checks.append(("헬퍼 상태: 준비됨", (r.get("status_before") or {}).get("data", {}).get("component") == "ready",
                       json.dumps(r.get("status_before"), ensure_ascii=False)[:300]))
        checks.append(("DKIM 키: opendkim 0600", r.get("dkim_key_mode") == "0o600" and r.get("dkim_key_owner") == "opendkim",
                       f"{r.get('dkim_key_mode')} {r.get('dkim_key_owner')}"))
        checks.append(("켜기 성공", (r.get("apply") or {}).get("ok") is True, json.dumps(r.get("apply"), ensure_ascii=False)[:400]))
        running = (r.get("status_running") or {}).get("data", {})
        checks.append(("켠 뒤 상태: 동작 중", running.get("component") == "running", json.dumps(running, ensure_ascii=False)[:300]))
        checks.append(("켠 뒤 받는 문: 127.0.0.1:2525 와 서명 8891 뿐",
                       sorted(running.get("listeners") or []) == ["127.0.0.1:2525", "127.0.0.1:8891"], str(running.get("listeners"))))
        send = r.get("send") or {}
        checks.append(("앱 전송기가 릴레이에 넘겼다(큐 id)", bool(send.get("ok")) and bool(r.get("queue_id")),
                       json.dumps(send, ensure_ascii=False)[:300]))
        verify = r.get("verify") or {}
        checks.append(("앱 연결 확인(봉투 시험) 통과", verify.get("ok") is True, json.dumps(verify, ensure_ascii=False)[:300]))
        checks.append(("받는 쪽에 도착했고 DKIM 서명이 붙었다", r.get("sink_count", 0) >= 1 and r.get("sink_has_dkim") is True,
                       f"count={r.get('sink_count')} dkim={r.get('sink_has_dkim')}"))
        logged = ((r.get("log") or {}).get("data") or {}).get("results") or {}
        checks.append(("로그 읽기: 그 큐 id 가 전달함", (logged.get(r.get("queue_id") or "") or {}).get("status") == "delivered",
                       json.dumps(logged, ensure_ascii=False)[:300]))
        checks.append(("끄기 성공", (r.get("disable") or {}).get("ok") is True, json.dumps(r.get("disable"), ensure_ascii=False)[:300]))
        after = (r.get("status_after") or {}).get("data", {})
        relay_ports = [x for x in after.get("listeners") or [] if x.rsplit(":", 1)[-1] in ("2525", "8891")]
        checks.append(("끈 뒤: 준비됨 · 릴레이 받는 문 없음", after.get("component") == "ready" and not relay_ports,
                       json.dumps(after, ensure_ascii=False)[:300]))
        enabled = dexec(NAME, "systemctl is-enabled postfix.service opendkim.service").stdout.split()
        checks.append(("끈 뒤: 다음 부팅에도 안 뜬다(disabled)", enabled == ["disabled", "disabled"], " ".join(enabled)))

        # 다른 메일 발송 프로그램이 있는 서버 — 설치기가 postfix 를 깔지 않는다.
        sh("docker", "run", "-d", "--name", PLAIN, BASE_IMAGE, "sleep", "infinity")
        dexec(PLAIN, "export DEBIAN_FRONTEND=noninteractive; printf '#!/bin/sh\\nexit 101\\n' >/usr/sbin/policy-rc.d; "
                     "chmod 755 /usr/sbin/policy-rc.d; apt-get update -qq >/dev/null; "
                     "apt-get install -y -qq --no-install-recommends exim4-daemon-light >/dev/null; rm -f /usr/sbin/policy-rc.d",
              timeout=900)
        put(PLAIN, "/tmp/mailrelay.sh", installer_functions())
        other = dexec(PLAIN, "source /tmp/mailrelay.sh; install_mail_relay; echo RC=$?; echo NOTE=$MAIL_RELAY_NOTE; "
                             "dpkg -s postfix >/dev/null 2>&1 && echo POSTFIX_INSTALLED || echo NO_POSTFIX")
        checks.append(("다른 MTA 가 있으면 깔지 않는다", "RC=0" in other.stdout and "다른 메일 발송 프로그램" in other.stdout
                       and "NO_POSTFIX" in other.stdout, other.stdout[-300:]))
    finally:
        if not args.keep:
            for name in (NAME, PLAIN):
                sh("docker", "rm", "-f", name, check=False)

    ok = all(passed for _, passed, _ in checks)
    for label, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + label + ("" if passed else f" :: {detail}"))
    (OUT / "result.json").write_text(json.dumps(
        {"ok": ok, "checks": [{"label": l, "ok": p, "detail": d} for l, p, d in checks]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("RELAY_SYSTEMD_E2E_OK" if ok else "RELAY_SYSTEMD_E2E_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
