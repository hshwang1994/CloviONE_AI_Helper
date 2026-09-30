"""설치본 허용 목록에 새 기본 호스트를 더하는 규칙 (deploy/merge_allowlist.py, D-522).

못박는 성질:
1. 새 버전이 기본 목록에 더한 호스트는 업그레이드한 설치본에 들어간다. 사람이 서버에서 파일을 고치지 않는다.
2. 운영자가 지운 기본 호스트는 되살리지 않는다. 운영자가 더한 호스트는 그대로 둔다.
3. 직전 기본 사본이 없는 첫 병합은 빠진 기본 호스트를 한 번 더한다. 그 뒤로는 사본이 지운 항목을 지킨다.
4. 허용 목록이 아닌 파일이나 모양이 바뀐 파일은 건드리지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "merge_allowlist.py"


def _module():
    spec = importlib.util.spec_from_file_location("merge_allowlist", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: pathlib.Path, hosts, **extra):
    path.write_text(json.dumps({"_comment": "x", "hosts": list(hosts), **extra}), encoding="utf-8")


def _hosts(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))["hosts"]


@pytest.fixture()
def files(tmp_path):
    return tmp_path / "default.json", tmp_path / "installed.json", tmp_path / "record.json"


def test_new_default_hosts_reach_an_upgraded_install(files):
    default, installed, record = files
    merge = _module().merge
    _write(record, ["api.anthropic.com:443"])
    _write(installed, ["api.anthropic.com:443", "svc.internal.example:443"])
    _write(default, ["api.anthropic.com:443", "api.openai.com:443", "auth.openai.com:443"])
    assert merge(default, installed, record) == ["api.openai.com:443", "auth.openai.com:443"]
    assert _hosts(installed) == ["api.anthropic.com:443", "svc.internal.example:443", "api.openai.com:443",
                                 "auth.openai.com:443"]
    assert _hosts(record) == _hosts(default), "이번 기본 목록이 다음 병합의 기준으로 남지 않았다"
    assert json.loads(installed.read_text(encoding="utf-8"))["_comment"] == "x", "운영자 파일의 다른 칸이 사라졌다"
    # 다시 돌려도 더할 것이 없다.
    assert merge(default, installed, record) == []


def test_a_default_host_the_operator_removed_stays_removed(files):
    default, installed, record = files
    merge = _module().merge
    _write(record, ["api.anthropic.com:443", "api.openai.com:443"])
    _write(installed, ["api.anthropic.com:443"])  # 운영자가 OpenAI 를 지웠다
    _write(default, ["api.anthropic.com:443", "api.openai.com:443", "auth.openai.com:443"])
    assert merge(default, installed, record) == ["auth.openai.com:443"]
    assert "api.openai.com:443" not in _hosts(installed)


def test_the_first_merge_without_a_record_adds_missing_defaults_once(files):
    default, installed, record = files
    merge = _module().merge
    _write(installed, ["api.anthropic.com:443"])
    _write(default, ["api.anthropic.com:443", "api.openai.com:443"])
    assert merge(default, installed, record) == ["api.openai.com:443"]
    assert record.exists()
    # 그 뒤 운영자가 지우면 다음 병합은 되살리지 않는다.
    _write(installed, ["api.anthropic.com:443"])
    assert merge(default, installed, record) == []


def test_files_that_are_not_allowlists_are_left_alone(files):
    default, installed, record = files
    merge = _module().merge
    default.write_text(json.dumps({"flags": {"chat_enabled": True}}), encoding="utf-8")
    installed.write_text(json.dumps({"flags": {"chat_enabled": False}}), encoding="utf-8")
    assert merge(default, installed, record) == []
    assert json.loads(installed.read_text(encoding="utf-8")) == {"flags": {"chat_enabled": False}}
    # 운영자가 모양을 바꾼 허용 목록도 어떻게 합칠지 모르므로 손대지 않는다.
    _write(default, ["api.openai.com:443"])
    installed.write_text(json.dumps({"allow": ["x:443"]}), encoding="utf-8")
    assert merge(default, installed, record) == []
    assert json.loads(installed.read_text(encoding="utf-8")) == {"allow": ["x:443"]}


def test_the_shipped_defaults_are_allowlists_the_merge_understands():
    """배포하는 기본 파일이 이 규칙이 읽는 모양인지. 모양이 바뀌면 병합이 조용히 아무것도 안 한다."""
    config = pathlib.Path(__file__).resolve().parents[2] / "config" / "allowed-services.json"
    assert _module()._hosts(json.loads(config.read_text(encoding="utf-8")))
