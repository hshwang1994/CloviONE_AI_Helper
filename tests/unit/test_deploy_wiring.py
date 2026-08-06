"""배포 배선이 **파일을 다시 쓰는 사람에 의해 조용히 사라지지 않게** 고정한다.

## 왜 이 파일이 있나

특권 헬퍼(§S)의 systemd 유닛을 만들고 설치/롤백 스크립트에 배선했는데, 같은 시간에 다른
작업자가 그 스크립트들을 **다시 쓰면서 배선 세 곳이 통째로 사라졌다.** 유닛 파일은 남았지만
아무도 설치하지 않고 아무도 띄우지 않는 유닛이 됐다 - 즉 §S 전체가 배포되지 않는 상태였다.

사라진 것을 사람이 알아채기까지 한참 걸렸다(우연히 grep 해 봐서 알았다). 파일을 지키는 것이
아니라 **성질을 지켜야** 다시 사라지지 않는다.

## 여기서 검사하지 않는 것

이 검사는 "스크립트가 그 이름을 언급한다" 까지다. 실제로 설치되는지는 리눅스에서 돌려야
안다. 그걸 이 검사가 하는 척하지 않는다 - 다만 **통째로 빠진 것**은 확실히 잡는다.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL = ROOT / "scripts" / "install-clovirone-web-assistant.sh"
ROLLBACK = ROOT / "scripts" / "rollback-clovirone-web-assistant.sh"
WEB_UNIT = ROOT / "deploy" / "systemd" / "clovirone-web-assistant.service"
HELPER_UNIT = ROOT / "deploy" / "systemd" / "clovirone-privhelper.service"


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"없는 파일이다: {path}"
    return path.read_text(encoding="utf-8")


def test_the_helper_unit_exists_and_runs_as_root():
    """헬퍼의 존재 이유가 root 권한이다. 아니면 /etc 를 못 쓴다."""
    text = _text(HELPER_UNIT)
    assert "User=root" in text, "헬퍼가 root 로 돌지 않으면 시스템 설정을 못 바꾼다"
    assert "app.sysops.helper" in text, "헬퍼가 우리 모듈을 실행하지 않는다"


def test_the_helper_can_write_the_places_its_actions_touch():
    """액션 표가 건드리는 경로가 `ReadWritePaths` 에 없으면 **런타임에** 조용히 실패한다."""
    text = _text(HELPER_UNIT)
    rw = next((ln for ln in text.splitlines() if ln.startswith("ReadWritePaths=")), "")
    assert rw, "헬퍼에 ReadWritePaths 가 없다"
    for needed in ("/etc/hosts", "/etc/systemd", "/etc/ssl/clovirone"):
        assert needed in rw, f"액션이 쓰는 경로가 빠졌다: {needed} / 실제: {rw}"


def test_the_web_unit_keeps_its_hardening():
    """🔴 헬퍼를 만든 이유가 **이 하드닝을 풀지 않기 위해서**다.

    누군가 편하자고 이 줄을 지우면 §S 전체가 무의미해진다(웹을 뚫은 사람이 곧 root 다).
    """
    text = _text(WEB_UNIT)
    for line in ("NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=true"):
        assert line in text, f"웹 유닛의 하드닝이 사라졌다: {line}"


def test_the_web_unit_tolerates_a_missing_helper_socket():
    """헬퍼를 안 깐 설치에서도 웹은 떠야 한다.

    `ReadWritePaths` 에 없는 경로를 `-` 없이 적으면 **유닛이 시작에 실패**한다. 시스템 설정
    기능 하나 때문에 서비스가 통째로 안 뜨는 것은 맞바꿀 수 없는 거래다.
    """
    text = _text(WEB_UNIT)
    rw = next((ln for ln in text.splitlines() if ln.startswith("ReadWritePaths=")), "")
    assert rw, "웹 유닛에 ReadWritePaths 가 없다"
    assert "/run/clovirone-web-assistant" in rw, (
        f"소켓 디렉터리가 웹 유닛에 없다: {rw}"
    )
    assert "-/run/clovirone-web-assistant" in rw, (
        f"`-`(없으면 넘어감)가 없다 - 헬퍼 없는 설치에서 웹이 안 뜬다: {rw}"
    )


def test_the_installer_actually_installs_the_helper():
    """🔴 유닛 파일만 있고 설치 스크립트가 모르면 **아무도 띄우지 않는 유닛**이 된다."""
    text = _text(INSTALL)
    assert "clovirone-privhelper.service" in text, (
        "설치 스크립트가 특권 헬퍼 유닛을 모른다 - §S 가 배포되지 않는다"
    )
    assert "systemctl enable clovirone-privhelper" in text, (
        "헬퍼를 enable 하지 않는다 - 재부팅하면 시스템 설정 기능이 사라진다"
    )


def test_the_installer_prepares_the_certificate_directory():
    """인증서 교체 액션이 쓰는 자리를 설치가 만들어 두지 않으면 첫 교체가 실패한다."""
    assert "/etc/ssl/clovirone" in _text(INSTALL), "인증서 디렉터리를 만들지 않는다"


def test_uninstall_removes_the_helper_too():
    """제거했는데 root 데몬이 남아 있으면 그것 자체가 사고다."""
    text = _text(ROLLBACK)
    assert "clovirone-privhelper" in text, "제거 스크립트가 헬퍼를 모른다 - root 데몬이 남는다"


def test_the_installer_has_no_customer_specific_defaults():
    """P1 - 다른 고객사에 설치했을 때 조용히 남의 워크스페이스를 가리키면 안 된다."""
    text = _text(INSTALL)
    for leaked in ("goodmit.co.kr", "gooddi.lab"):
        assert leaked not in text, f"설치 스크립트에 고객사 고유값이 있다: {leaked}"
