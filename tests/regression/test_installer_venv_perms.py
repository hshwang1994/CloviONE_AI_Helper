"""iter3 High: the installer's permission normalization must NOT strip the
execute bit from the runtime venv (would break pip/uvicorn on upgrade).

qa-contract-change: 대상을 옛 slug 설치 스크립트(scripts/install-clovirone-web-assistant.sh)에서 실제로 배포되는 설치기(deploy/install.sh)로 옮겼다 — S4 가 그 둘을 하나로 합쳤고 S14 가 옛 것을 지웠으므로, 옛 파일을 계속 읽는 시험은 아무도 안 쓰는 스크립트를 지키는 초록불이 된다. 못박는 성질과 단언 수는 그대로다.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

INSTALLER = Path(__file__).resolve().parents[2] / "deploy" / "install.sh"


def test_permission_chmod_excludes_venv():
    """iter3 High guard: the ownership/permission normalization must prune the
    venv so a blanket chmod 0644 never strips pip/uvicorn's execute bit on an
    upgrade re-run. Static assertion (portable; execution verified manually on
    Linux/Git Bash: venv stays 755, source normalizes to 644)."""
    src = INSTALLER.read_text(encoding="utf-8")
    # Both the dir and file chmod passes, and the chown pass, must prune venv.
    prune = '-path "$APP_DIR/venv" -prune -o'
    chmod_lines = [ln for ln in src.splitlines() if "chmod 0644" in ln or "chmod 0755" in ln]
    dir_file_lines = [ln for ln in chmod_lines if "-type" in ln]
    assert dir_file_lines, "expected -type d/f chmod normalization lines"
    for ln in dir_file_lines:
        assert prune in ln, f"chmod line missing venv prune: {ln.strip()}"
    # The chown normalization must also prune venv.
    chown_lines = [ln for ln in src.splitlines() if "chown root:root" in ln and "find" in ln]
    assert chown_lines, "expected a find-based chown normalization line"
    assert all(prune in ln for ln in chown_lines)
