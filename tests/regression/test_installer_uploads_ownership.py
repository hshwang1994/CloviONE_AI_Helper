"""OPS-02: the installer must set ownership on $VAR_DIR/uploads.

app/core/uploads.py's save_upload() does its own mkdir(parents=True,
exist_ok=True), but that's a no-op for ownership if the directory (or a
parent) already exists under the wrong owner — exactly what happened in the
OPS-01 incident (uploads/ was root:750, the unprivileged service user could
never write into it, and no reinstall/upgrade fixed it because this
directory wasn't in the installer's ownership list). The four sibling
directories (exports/generated/temp/locks) were already covered; uploads
was the one left out. Static assertion (portable; matches the existing
test_installer_venv_perms.py pattern — this script only runs on Linux)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

INSTALLER = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "install-clovirone-web-assistant.sh"
)


def test_uploads_dir_is_in_the_ownership_install_block():
    src = INSTALLER.read_text(encoding="utf-8")
    lines = src.splitlines()
    start = next(
        i for i, ln in enumerate(lines)
        if 'install -d -o "$SVC_USER" -g "$SVC_USER"' in ln and '"$VAR_DIR"' in ln
    )
    # The install -d invocation continues on the next line (backslash
    # continuation) — check both for the sibling directories.
    block = "\n".join(lines[start:start + 2])
    for sibling in ("exports", "generated", "temp", "locks", "uploads"):
        assert f'"$VAR_DIR/{sibling}"' in block, f"missing {sibling} in ownership block"
