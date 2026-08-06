"""커밋된 프런트 번들의 신선도 검사 (P5).

이 검사가 없으면 **소스만 고치고 번들을 안 만든 채 배포**해도 아무 신호가 없다.
git 으로 설치한 서버는 조용히 옛 UI 를 돌리고, 로그에도 화면에도 흔적이 없다.
그래서 여기서는 "검사가 실제로 낡음을 잡는가" 를 본다.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_bundle_fresh.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_bundle_fresh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """가짜 저장소 하나. 실제 저장소의 기준 파일을 건드리지 않는다."""
    mod = _load()
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "App.jsx").write_text("export const a = 1;\n", encoding="utf-8")
    (frontend / "package.json").write_text('{"name":"x"}\n', encoding="utf-8")
    bundle = tmp_path / "app" / "static" / "react"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(mod, "FRONTEND", frontend)
    monkeypatch.setattr(mod, "BUNDLE", bundle)
    monkeypatch.setattr(mod, "STAMP", bundle / "BUILD_STAMP.json")
    return mod, frontend, bundle


def test_a_stale_bundle_is_caught(world):
    """🔴 이게 핵심이다 - 기준을 적은 뒤 소스를 고치면 반드시 걸려야 한다."""
    mod, frontend, _bundle = world
    assert mod.main(["--write"]) == 0

    assert mod.main([]) == 0, "방금 기준을 적었는데 낡았다고 한다"

    (frontend / "src" / "App.jsx").write_text("export const a = 2;\n", encoding="utf-8")
    assert mod.main([]) == 1, "소스를 고쳤는데 번들이 최신이라고 답했다"


def test_a_new_source_file_is_caught(world):
    """파일 내용뿐 아니라 **목록**이 바뀌어도 걸려야 한다."""
    mod, frontend, _bundle = world
    mod.main(["--write"])
    (frontend / "src" / "New.jsx").write_text("export const b = 1;\n", encoding="utf-8")
    assert mod.main([]) == 1, "새 화면 파일이 생겼는데 최신이라고 답했다"


def test_a_missing_stamp_is_a_failure_not_a_pass(world):
    """"모르겠다" 를 "괜찮다" 로 바꾸지 않는다 - 출처를 모르는 번들은 배포하면 안 된다."""
    mod, _frontend, _bundle = world
    assert mod.main([]) == 1


def test_test_files_do_not_mark_the_bundle_stale(world):
    """🔴 오탐이 한 번이라도 나면 사람은 이 검사를 끈다.

    테스트 파일은 번들에 안 들어간다. 그걸 고쳤다고 "낡았다" 고 하면 검사가 소음이 된다.
    """
    mod, frontend, _bundle = world
    mod.main(["--write"])
    (frontend / "src" / "App.test.jsx").write_text("it('x', () => {});\n", encoding="utf-8")
    assert mod.main([]) == 0, "테스트 파일 하나에 번들이 낡았다고 답했다"


def test_line_endings_alone_do_not_change_the_answer(world):
    """CRLF 차이만으로 낡았다고 하면 Windows 와 Linux 가 서로를 낡았다고 부른다."""
    mod, frontend, _bundle = world
    mod.main(["--write"])
    (frontend / "src" / "App.jsx").write_bytes(b"export const a = 1;\r\n")
    assert mod.main([]) == 0, "줄바꿈만 달라졌는데 낡았다고 답했다"


def test_an_empty_frontend_is_a_failure_not_a_silent_pass(world):
    """입력이 0개면 해시가 늘 같아져 **무엇을 고쳐도 통과**하게 된다. 그건 검사가 아니다."""
    mod, frontend, _bundle = world
    for path in sorted(frontend.rglob("*")):
        if path.is_file():
            path.unlink()
    assert mod.main([]) == 1
