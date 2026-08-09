"""번들 업그레이드 경로의 계약 (DEPLOY-01, DEPLOY-02).

## 왜 이런 테스트인가

`scripts/upgrade-clovirone-web-assistant.sh`(번들 경로)는 예전에 installer 가 요구하는
`DNS_NAME`/`BIND_IP` 를 넘기지 않아 installer 가 `exit 2` 로 즉시 죽었는데, 그 시점엔 이미
web·worker 를 둘 다 정지시킨 뒤였고 되살리는 코드가 없어 서비스가 멈춘 채 남았다
(`DEPLOY-01`). 같은 저장소의 git 경로(`update-from-git.sh`)에는 이미 backup ->
install -> verify -> 실패 시 rollback_now 골격이 있었는데 번들 경로에만 없었다
(`DEPLOY-02`). `test_update_script_contract.py` 가 git 경로에 대해 하는 것과 같은
수준(grep 으로 "그 단계가 있다"만 고정 — 실제 서버에서 되는지는 별개)을 번들 경로에도
건다.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
UPGRADE = ROOT / "scripts" / "upgrade-clovirone-web-assistant.sh"

BASH = shutil.which("bash")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _line_of(text: str, needle: str) -> int:
    for idx, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return idx
    raise AssertionError(f"찾지 못했다: {needle!r}")


def _without_comments(text: str) -> str:
    """주석을 지운 사본(test_update_script_contract.py 와 같은 이유 — 한국어 설명문에
    "n8n" 같은 낱말이 그대로 들어 있어, 실제 로직이 아니라 설명이 검사에 걸릴 수 있다)."""
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split(" #")[0] if " #" in line else line)
    return "\n".join(out)


def test_upgrade_script_exists():
    assert UPGRADE.is_file(), f"{UPGRADE} 가 없다"


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_upgrade_script_bash_syntax():
    result = subprocess.run([BASH, "-n", str(UPGRADE)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr


def test_upgrade_script_has_no_crlf():
    assert b"\r\n" not in UPGRADE.read_bytes(), "CRLF 가 있다 - 리눅스에서 command not found 로 죽는다"


def test_upgrade_script_requires_dns_name_and_bind_ip():
    """DEPLOY-01: installer 가 이 값들 없이는 exit 2 한다 - 업그레이드 스크립트가 미리
    걸러야, "서비스를 이미 정지시킨 뒤에" installer 가 죽는 사고가 재발하지 않는다."""
    text = _read(UPGRADE)
    assert '-z "$DNS_NAME"' in text and '-z "$BIND_IP"' in text, \
        "DNS_NAME/BIND_IP 존재를 확인하지 않는다"
    # 서비스 정지보다 먼저 걸러야 한다(정지 후에 걸리면 원래 사고와 같아진다).
    guard_at = _line_of(text, 'if [ -z "$DNS_NAME" ] || [ -z "$BIND_IP" ]')
    stop_at = _line_of(text, "systemctl stop clovirone-web-worker.service")
    assert guard_at < stop_at, "DNS_NAME/BIND_IP 확인이 서비스 정지보다 늦다"


def test_upgrade_script_passes_dns_name_and_bind_ip_to_installer():
    text = _read(UPGRADE)
    install_section = text.split("# ── 3. 재설치")[-1].split("# ── 4. 검증")[0]
    assert 'DNS_NAME="$DNS_NAME"' in install_section, "installer 에 DNS_NAME 을 넘기지 않는다"
    assert 'BIND_IP="$BIND_IP"' in install_section, "installer 에 BIND_IP 를 넘기지 않는다"
    assert "install-clovirone-web-assistant.sh" in install_section


def test_upgrade_script_backs_up_before_installing():
    text = _read(UPGRADE)
    assert "backup-clovirone-web-assistant.sh" in text, "백업 단계가 없다"
    backup_at = _line_of(text, 'BACKUP_OUT="$(bash')
    install_at = _line_of(text, "install-clovirone-web-assistant.sh")
    # install-clovirone-web-assistant.sh 가 여러 줄에서 언급되므로(rollback_now 안내문 등),
    # 실제 설치 호출 줄(STAGE 변수를 함께 넘기는 줄)을 찾는다.
    install_call_at = _line_of(text, 'STAGE="$STAGE" \\')
    assert backup_at < install_call_at, "설치가 백업보다 먼저다 - 되돌릴 지점이 없다"


def test_upgrade_script_stops_services_before_backup_output_is_used():
    """백업은 서비스 정지보다 먼저 뜬다(정지 후 백업하면 그 사이 데이터가 롤백 때 사라진다는
    update-from-git.sh 의 결정과 반대로, 번들 경로는 이미 설치된 실행 중 앱의 백업 스크립트를
    쓰므로 정지 전에 백업 → 정지 → 재설치 순서다). 순서 자체가 흔들리지 않게 고정한다."""
    text = _read(UPGRADE)
    backup_at = _line_of(text, 'BACKUP_OUT="$(bash')
    stop_at = _line_of(text, "systemctl stop clovirone-web-worker.service")
    assert backup_at < stop_at, "백업이 서비스 정지보다 늦다"


def test_upgrade_script_refuses_to_proceed_without_a_backup():
    text = _read(UPGRADE)
    assert 'BACKUP_DIR="" ] || [ ! -d "$BACKUP_DIR"' in text or \
        '-z "$BACKUP_DIR"' in text, "백업 실패를 확인하지 않는다"
    assert "exit 5" in text, "백업 없이 진행을 막지 않는다"


def test_upgrade_script_has_a_rollback_path():
    """되돌리기가 실제 복원 스크립트를 부르는지, 출력 문구가 아니라 실행되는 줄만 본다
    (test_update_script_contract.py 의 같은 함정을 피한다)."""
    text = _read(UPGRADE)
    fn = re.search(r"^rollback_now\(\) \{.*?^\}", text, re.S | re.M)
    assert fn, "실패 처리 함수(rollback_now)가 없다"
    body = fn.group(0)
    runnable = "\n".join(
        line for line in body.splitlines()
        if not line.strip().startswith(("say ", "echo ", "#", "printf "))
    )
    assert "rollback-clovirone-web-assistant.sh" in runnable, \
        "되돌리기가 실제 복원 스크립트를 부르지 않는다(이름만 적혀 있다)"


def test_upgrade_script_calls_rollback_when_install_fails():
    text = _read(UPGRADE)
    install_block = text.split("# ── 3. 재설치")[-1].split("# ── 4. 검증")[0]
    assert 'rollback_now "설치 스크립트가 실패했습니다"' in install_block, \
        "installer 실패가 롤백으로 이어지지 않는다"


def test_upgrade_script_rolls_back_on_verification_failure():
    text = _read(UPGRADE)
    assert "readyz" in text, "readyz 를 보지 않는다 - 마이그레이션이 어긋나도 통과한다"
    assert 'rollback_now "$VERIFY_FAIL"' in text, "검증 실패가 롤백으로 이어지지 않는다"


def test_upgrade_script_does_not_gate_on_unrelated_services():
    text = _read(UPGRADE)
    verify_section = text.split("# ── 4. 검증")[-1]
    gate = _without_comments(verify_section.split('say "[OK ] healthz')[0])
    assert "n8n" not in gate, "판정 구간에서 n8n 을 본다"
    assert "validate-clovirone-web-assistant.sh" not in gate, \
        "판정에 n8n 까지 보는 전체 검증 스크립트를 쓴다"


def test_upgrade_script_falls_back_to_restarting_services_when_there_is_no_backup_to_restore():
    """백업 자체가 안 만들어진 극단(최초 설치 직후 등)에도 rollback_now 가 서비스를 죽은
    채로 두지 않는다."""
    text = _read(UPGRADE)
    fn = re.search(r"^rollback_now\(\) \{.*?^\}", text, re.S | re.M)
    assert fn, "rollback_now 가 없다"
    body = fn.group(0)
    assert "systemctl start clovirone-web-assistant.service" in body
    assert "systemctl start clovirone-web-worker.service" in body
