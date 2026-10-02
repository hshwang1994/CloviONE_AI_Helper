"""설치기의 ClovirAssist 로컬 릴레이 구성 요소 (계획 M7, D-551).

실제 apt · systemd · Postfix 로는 `scripts/ui_qa/relay_systemd_e2e.py`(Docker, Ubuntu 24.04 + systemd)가 잰다. 여기서는 설치 스크립트의
함수를 떼어 bash 로 돌리되 바깥 명령(apt-get · dpkg · systemctl · ss)을 가짜로 바꾸고 경로를 임시 디렉터리로 옮겨 잰다.

못박는 성질:
1. 기본 설치다 — 꾸러미 셋(postfix · opendkim · libsasl2-modules)을 추천 꾸러미 없이 깔고, 설치하는 동안 서비스가 뜨지 않게
   policy-rc.d(exit 101)를 두었다가 치운다. 이미 policy-rc.d 가 있으면 건드리지 않고 mask 로 같은 효과를 낸 뒤 되돌린다.
2. 기본 꺼짐이다 — 깐 뒤 서비스를 끄고, 켜져 있거나 메일 포트를 듣는 것이 있으면 Stage 를 실패로 멈춘다.
3. 기존 메일 서버를 건드리지 않는다 — 다른 메일 발송 프로그램이 있거나 제품 표지가 없는 main.cf 가 있으면 아무것도 깔거나 끄지 않는다.
4. `--without-mail-relay` 는 꾸러미 설치까지 뺀다. 오프라인 번들에 debs/ 가 없으면 경고하고 메일 구성 요소만 건너뛴다.
5. `clovirassist mail-relay` 가 설치기의 같은 서브커맨드로 넘어간다. 도움말에 새 옵션이 있다.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL = ROOT / "deploy" / "install.sh"
CLI = ROOT / "deploy" / "clovirassist-cli.sh"
GIT_BASH = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = shutil.which("bash") if not GIT_BASH.exists() else str(GIT_BASH)
needs_bash = pytest.mark.skipif(not BASH, reason="bash 없음 — 셸 함수를 실행할 수 없다")

START = "# ── ClovirAssist 로컬 릴레이 구성 요소 (D-551)"
END = "\nstage_1_apt() {"


def _functions(rootfs: pathlib.Path) -> str:
    text = INSTALL.read_text(encoding="utf-8")
    body = text[text.index(START):text.index(END, text.index(START))]
    fs = rootfs.as_posix()
    for path in ("/usr/sbin/policy-rc.d", "/etc/postfix/main.cf", "/etc/apt/sources.list.d"):
        body = body.replace(path, fs + path)
    return body


FAKES = r'''
CALLS="$ROOTFS/calls"
log()  { :; }
fail() { echo "FAIL_REASON=$1"; return "${3:-20}"; }
debconf-set-selections() { cat >>"$ROOTFS/debconf"; }
dpkg-query() { cat "$ROOTFS/dpkg-query.out" 2>/dev/null; }
dpkg() { [ "$1" = -s ] && grep -qx "$2" "$ROOTFS/installed" 2>/dev/null; }
apt-get() {
  echo "apt-get $*" >>"$CALLS"
  if [ "$1" = -y ] || printf '%s\n' "$@" | grep -qx install; then
    if [ -e "$ROOTFS/usr/sbin/policy-rc.d" ]; then echo "guard-present-during-install" >>"$CALLS"; fi
    printf 'postfix\nopendkim\nlibsasl2-modules\n' >>"$ROOTFS/installed"
  fi
  return 0
}
systemctl() {
  echo "systemctl $*" >>"$CALLS"
  case "$1" in
    is-enabled) cat "$ROOTFS/enabled" 2>/dev/null || echo disabled ;;
    is-active) [ -f "$ROOTFS/active" ] && return 0 || return 3 ;;
    *) return 0 ;;
  esac
}
ss() { cat "$ROOTFS/ss.out" 2>/dev/null; }
'''


def _run(tmp_path: pathlib.Path, *, offline=0, without=0, wheelhouse="", files=None) -> tuple[subprocess.CompletedProcess, str]:
    rootfs = tmp_path / "fs"
    for d in ("usr/sbin", "etc/postfix", "etc/apt/sources.list.d"):
        (rootfs / d).mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        target = rootfs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    script = (f'ROOTFS="{rootfs.as_posix()}"\nLOG=/dev/null\nOFFLINE={offline}\nWITHOUT_MAIL_RELAY={without}\n'
              f'WHEELHOUSE="{wheelhouse}"\nMAIL_DEBS=""\nSLUG=clovirassist\n'
              + FAKES + _functions(rootfs)
              + '\ninstall_mail_relay; rc=$?; echo "RC=$rc"; echo "NOTE=$MAIL_RELAY_NOTE"\n')
    result = subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8")
    calls = (rootfs / "calls").read_text(encoding="utf-8") if (rootfs / "calls").exists() else ""
    return result, calls


@needs_bash
def test_a_fresh_server_gets_the_packages_installed_and_left_off(tmp_path):
    result, calls = _run(tmp_path)
    assert "RC=0" in result.stdout, result.stdout + result.stderr
    assert "준비됨(꺼짐)" in result.stdout
    install = [line for line in calls.splitlines() if line.startswith("apt-get") and " install " in f" {line} "]
    assert install and "--no-install-recommends" in install[0]
    assert all(pkg in install[0] for pkg in ("postfix", "opendkim", "libsasl2-modules"))
    assert "guard-present-during-install" in calls, "설치하는 동안 policy-rc.d 가 있어야 서비스가 뜨지 않는다"
    assert not (tmp_path / "fs/usr/sbin/policy-rc.d").exists(), "설치가 끝나면 가드를 치운다"
    assert "postfix/main_mailer_type select No configuration" in (tmp_path / "fs/debconf").read_text(encoding="utf-8")
    assert "systemctl disable --now postfix.service" in calls and "systemctl disable --now opendkim.service" in calls


@needs_bash
def test_an_existing_policy_rc_d_is_kept_and_mask_is_used(tmp_path):
    result, calls = _run(tmp_path, files={"usr/sbin/policy-rc.d": "#!/bin/sh\nexit 0\n"})
    assert "RC=0" in result.stdout, result.stdout
    assert (tmp_path / "fs/usr/sbin/policy-rc.d").read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"
    assert "systemctl mask postfix.service opendkim.service" in calls
    assert "systemctl unmask postfix.service opendkim.service" in calls


@needs_bash
@pytest.mark.parametrize("state, why", [
    ({"enabled": "enabled\n"}, "켜져 있습니다"),
    ({"active": ""}, "돌고 있습니다"),
    ({"ss.out": "LISTEN 0      100          0.0.0.0:25        0.0.0.0:*\n"}, "메일 포트를 듣는 소켓"),
])
def test_anything_left_running_fails_the_stage(tmp_path, state, why):
    result, _calls = _run(tmp_path, files=state)
    assert "RC=0" not in result.stdout
    assert why in result.stdout


@needs_bash
def test_another_mta_means_nothing_is_installed(tmp_path):
    result, calls = _run(tmp_path, files={"dpkg-query.out": "ii |exim4-daemon-light|mail-transport-agent\n"})
    assert "RC=0" in result.stdout
    assert "다른 메일 발송 프로그램(exim4-daemon-light)" in result.stdout
    assert "apt-get" not in calls and "systemctl" not in calls


@needs_bash
def test_a_foreign_postfix_configuration_is_left_alone(tmp_path):
    result, calls = _run(tmp_path, files={"installed": "postfix\nopendkim\nlibsasl2-modules\n",
                                          "etc/postfix/main.cf": "myhostname = mail.example.com\n"})
    assert "RC=0" in result.stdout and "기존 메일 발송 구성" in result.stdout
    assert "systemctl" not in calls, "기존 구성의 서비스를 끄지도 않는다"


@needs_bash
def test_a_managed_relay_is_kept_as_the_admin_left_it(tmp_path):
    result, calls = _run(tmp_path, files={"installed": "postfix\nopendkim\nlibsasl2-modules\n",
                                          "etc/postfix/main.cf": "# managed-by: clovirassist\nmyhostname = x\n",
                                          "active": "", "ss.out": "127.0.0.1:2525\n"})
    assert "RC=0" in result.stdout and "그대로 두었습니다" in result.stdout
    assert "disable" not in calls


@needs_bash
def test_without_mail_relay_skips_the_packages(tmp_path):
    result, calls = _run(tmp_path, without=1)
    assert "RC=0" in result.stdout and "--without-mail-relay" in result.stdout
    assert calls == ""


@needs_bash
def test_an_old_offline_bundle_without_debs_skips_only_the_mail_component(tmp_path):
    wheels = tmp_path / "bundle" / "wheels"
    wheels.mkdir(parents=True)
    result, calls = _run(tmp_path, offline=1, wheelhouse=wheels.as_posix())
    assert "RC=0" in result.stdout and "번들에 메일 구성 요소가 없어" in result.stdout
    assert "apt-get" not in calls


@needs_bash
def test_an_offline_bundle_uses_a_temporary_local_apt_source(tmp_path):
    debs = tmp_path / "bundle" / "debs"
    debs.mkdir(parents=True)
    (debs / "Packages.gz").write_bytes(b"")
    wheels = tmp_path / "bundle" / "wheels"
    wheels.mkdir()
    result, calls = _run(tmp_path, offline=1, wheelhouse=wheels.as_posix())
    assert "RC=0" in result.stdout, result.stdout
    assert "Dir::Etc::sourcelist=" in calls, "번들의 debs 를 로컬 apt 원본으로 건다"
    assert not list((tmp_path / "fs/etc/apt/sources.list.d").iterdir()), "설치가 끝나면 임시 원본을 지운다"


@needs_bash
def test_the_command_forwards_mail_relay(tmp_path):
    fake = tmp_path / "deploy"
    fake.mkdir()
    (fake / "install.sh").write_text('#!/usr/bin/env bash\necho "$*"\n', encoding="utf-8", newline="\n")
    (fake / "install.sh").chmod(0o755)
    result = subprocess.run([BASH, str(CLI), "mail-relay"], capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "CLOVIRASSIST_APP_DIR": tmp_path.as_posix()})
    assert result.returncode == 0 and result.stdout.strip() == "mail-relay"


def test_the_help_and_bundle_know_the_mail_component():
    install = INSTALL.read_text(encoding="utf-8")
    assert "--without-mail-relay" in install and "--mail-debs" in install and "mail-relay  로컬 릴레이 구성 요소" in install
    bundle = (ROOT / "scripts" / "build-bundle.sh").read_text(encoding="utf-8")
    assert "Packages.gz" in bundle and "postfix opendkim libsasl2-modules" in bundle and '"$STAGE/debs"' in bundle
    unit = (ROOT / "deploy" / "systemd" / "clovirassist-privhelper.service").read_text(encoding="utf-8")
    assert "-/etc/postfix" in unit and "-/etc/opendkim" in unit
