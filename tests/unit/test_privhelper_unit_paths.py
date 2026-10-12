"""특권 헬퍼 유닛의 `ReadWritePaths=` 에 **파일**을 적지 않는다 (랩 결함 2026-10-12).

systemd 는 `ReadWritePaths=` 의 항목마다 bind mount 를 만든다. 디렉터리면 그 안에서 `rename()` 이 그대로 되지만,
파일이면 그 파일이 자기 위에 마운트된 마운트 지점이 되어 새 파일을 그 위로 rename 할 수 없다(`EBUSY`). 랩에서
`/etc/opendkim.conf` 를 적어 둔 채 DKIM 을 켜자 `os.replace()` 가 「Device or resource busy」 로 죽어 로컬 릴레이 적용이
통째로 실패했다 — 헬퍼의 `write_text` 는 임시 파일 + rename 이 기본이기 때문이다.

예외는 헬퍼가 제자리에서 고치는 `/etc/hosts` 뿐이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

UNIT = Path(__file__).resolve().parents[2] / "deploy" / "systemd" / "clovirassist-privhelper.service"
IN_PLACE_FILES = {"/etc/hosts"}


def _read_write_paths() -> list[str]:
    text = UNIT.read_text(encoding="utf-8")
    m = re.search(r"^ReadWritePaths=(.*)$", text, re.M)
    assert m, "ReadWritePaths= 줄이 없다"
    return [item.lstrip("-+") for item in m.group(1).split()]


def test_read_write_paths_name_directories_not_files():
    offenders = []
    for path in _read_write_paths():
        if path in IN_PLACE_FILES:
            continue
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if "." in last:
            offenders.append(path)
    assert not offenders, (
        f"파일을 ReadWritePaths 에 적었다 — bind mount 된 파일 위로는 rename 이 EBUSY 다: {offenders}"
    )


def test_opendkim_conf_is_covered_by_a_directory_rule_not_a_file_rule():
    """`/etc/opendkim.conf` 는 `/etc` 바로 아래 파일이라 디렉터리 항목으로 덮을 수 없다 — 아예 적지 않는다(유닛에 ProtectSystem= 이
    없어 root 는 목록 밖도 쓴다)."""
    assert "/etc/opendkim.conf" not in _read_write_paths()
    assert "/etc/opendkim" in _read_write_paths(), "DKIM 키 디렉터리는 목록에 남아 있어야 한다"
