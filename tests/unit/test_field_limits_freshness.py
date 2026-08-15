"""fieldLimits.json 신선도 검사 (PA-RC-0005, check_bundle_fresh.py와 같은 발상).

이 검사가 없으면 백엔드 스키마의 max_length를 고치고 생성기를 다시 안 돌려도 아무 신호가
없다 - 화면은 조용히 낡은 상한을 계속 보여준다(더 엄격해졌으면 정상 입력을 조용히 막고,
완화됐으면 더 이상 필요 없는 제한을 계속 강제한다). 그래서 여기서는 "검사가 실제로 낡음을
잡는가"를 본다 — PA-RC-0005 acceptance_criteria (3): 유도값과 백엔드 선언의 불일치를 잡는
테스트가 있고 실제로 잡는다.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

import scripts.generate_field_limits as gen

pytestmark = pytest.mark.unit

CHECK_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_field_limits_fresh.py"


def _load_check():
    spec = importlib.util.spec_from_file_location("check_field_limits_fresh", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """가짜 출력 경로 하나. 실제 저장소의 커밋된 fieldLimits.json을 건드리지 않는다."""
    check = _load_check()
    out = tmp_path / "fieldLimits.json"
    monkeypatch.setattr(gen, "OUT", out)
    monkeypatch.setattr(check, "OUT", out)
    return check


def _set_limits(monkeypatch, limits):
    monkeypatch.setattr(gen, "all_field_limits", lambda: limits)


def test_a_stale_generated_file_is_caught(world, monkeypatch):
    """🔴 이게 핵심이다 - 기준을 적은 뒤 스키마 상한이 바뀌면 반드시 걸려야 한다."""
    check = world
    _set_limits(monkeypatch, {"prompts": {"create": {"name": 120}}})
    assert check.main(["--write"]) == 0

    assert check.main([]) == 0, "방금 기준을 적었는데 낡았다고 한다"

    _set_limits(monkeypatch, {"prompts": {"create": {"name": 121}}})
    assert check.main([]) == 1, "스키마 상한이 바뀌었는데 최신이라고 답했다"


def test_a_new_field_appearing_is_caught(world, monkeypatch):
    """값뿐 아니라 필드 **목록**이 바뀌어도(스키마에 필드 추가) 걸려야 한다."""
    check = world
    _set_limits(monkeypatch, {"prompts": {"create": {"name": 120}}})
    check.main(["--write"])
    _set_limits(monkeypatch, {"prompts": {"create": {"name": 120, "purpose": 2000}}})
    assert check.main([]) == 1, "필드가 새로 생겼는데 최신이라고 답했다"


def test_a_missing_generated_file_is_a_failure_not_a_pass(world):
    """"모르겠다"를 "괜찮다"로 바꾸지 않는다 — 기준이 없으면 화면이 어떤 상한을 쓰는지 알 수 없다."""
    check = world
    assert check.main([]) == 1


def test_write_then_check_round_trips(world, monkeypatch):
    check = world
    _set_limits(monkeypatch, {"users": {"create": {"email": 255}}})
    assert check.main(["--write"]) == 0
    assert check.OUT.is_file()
    assert check.main([]) == 0
