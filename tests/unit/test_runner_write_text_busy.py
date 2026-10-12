"""`RealRunner.write_text` — 대상이 마운트 지점이라 rename 이 `EBUSY` 면 제자리에서 덮어쓴다 (랩 결함 2026-10-12).

systemd `ReadWritePaths=` 에 파일 하나를 적어 둔 옛 유닛으로 도는 설치에서도 로컬 릴레이 적용이 죽지 않아야 한다. 다른
OSError 는 그대로 올라가고(가짜 성공 금지) 임시 파일은 남기지 않는다.
"""

from __future__ import annotations

import errno
import os

import pytest

from app.sysops import runner as runner_mod
from app.sysops.runner import RealRunner

pytestmark = pytest.mark.unit


def test_ebusy_on_replace_falls_back_to_in_place_write(tmp_path, monkeypatch):
    target = tmp_path / "opendkim.conf"
    target.write_text("old\n", encoding="utf-8")
    real_replace = os.replace

    def busy_replace(src, dst):
        if str(dst) == str(target):
            raise OSError(errno.EBUSY, "Device or resource busy", str(src), None, str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(runner_mod.os, "replace", busy_replace)
    RealRunner().write_text(str(target), "new\n", mode=0o644)

    assert target.read_text(encoding="utf-8") == "new\n"
    assert not (tmp_path / "opendkim.conf.new").exists(), "임시 파일이 남았다"


def test_other_oserror_is_raised_and_tmp_removed(tmp_path, monkeypatch):
    target = tmp_path / "main.cf"
    target.write_text("old\n", encoding="utf-8")

    def perm_replace(src, dst):
        raise OSError(errno.EACCES, "Permission denied", str(src), None, str(dst))

    monkeypatch.setattr(runner_mod.os, "replace", perm_replace)
    with pytest.raises(OSError):
        RealRunner().write_text(str(target), "new\n", mode=0o644)
    assert target.read_text(encoding="utf-8") == "old\n", "실패했는데 대상이 바뀌었다"
    assert not (tmp_path / "main.cf.new").exists(), "임시 파일이 남았다"


def test_normal_path_is_atomic_rename(tmp_path):
    target = tmp_path / "master.cf"
    RealRunner().write_text(str(target), "x\n", mode=0o644)
    assert target.read_text(encoding="utf-8") == "x\n"
    assert not (tmp_path / "master.cf.new").exists()
