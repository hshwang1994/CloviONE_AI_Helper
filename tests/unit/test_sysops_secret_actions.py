"""특권 헬퍼의 비밀 값 액션 (계획 2.3).

헬퍼는 root 로 돈다. 여기서 확인하는 것은 **경계**다 - 표에 없는 이름은 쓰지 않는다, 값은
결과·감사 어디에도 남지 않는다, 비밀 값의 사본을 백업 디렉터리에 두지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.sysops import actions as registry
from app.sysops.helper import handle_request
from app.sysops.protocol import encode_request
from tests.fakes.sysops import FakeRunner

pytestmark = pytest.mark.unit

SECRETS = "/etc/clovirassist/secrets"
NOW = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
VALUE = "sk-test-0123456789abcdef"


@pytest.fixture(autouse=True)
def _secrets_dir(monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", SECRETS)


def _run(runner, name, params):
    return registry.execute(runner, name, params, backup_root="/var/backups/x", now=NOW)


def test_an_allowlisted_slot_is_written_as_a_group_readable_file():
    runner = FakeRunner()
    result = _run(runner, "secret.write", {"name": "ai.anthropic.api_key", "value": f"  {VALUE}\n"})
    assert result.ok, result.detail
    assert result.changed is True
    path = f"{SECRETS}/ai.anthropic.api_key"
    assert runner.files[path] == VALUE, "앞뒤 공백을 떼고 저장해야 한다"
    assert runner.modes[path] == 0o640, "설치 스크립트가 놓는 파일과 같은 권한이어야 웹이 읽는다"


def test_a_name_outside_the_table_is_refused_and_nothing_is_written():
    runner = FakeRunner()
    result = _run(runner, "secret.write", {"name": "../../etc/shadow", "value": VALUE})
    assert result.ok is False
    assert "이름" in result.detail
    assert runner.files == {}, "표에 없는 이름으로 파일이 생겼다"

    result = _run(runner, "secret.write", {"name": "session_secret", "value": VALUE})
    assert result.ok is False
    assert runner.files == {}


def test_the_value_never_appears_in_the_result():
    runner = FakeRunner()
    result = _run(runner, "secret.write", {"name": "smtp.password", "value": VALUE})
    assert VALUE not in result.detail
    assert VALUE not in json.dumps(result.data)

    # 검증 실패 문구에도 값이 실리면 안 된다.
    bad = "line1\nline2-secret"
    refused = _run(runner, "secret.write", {"name": "smtp.password", "value": bad})
    assert refused.ok is False
    assert "line2-secret" not in refused.detail


def test_secrets_are_never_copied_into_the_backup_directory():
    runner = FakeRunner({f"{SECRETS}/smtp.password": "old-password"})
    result = _run(runner, "secret.write", {"name": "smtp.password", "value": VALUE})
    assert result.ok
    assert result.backup_dir is None
    copies = [p for p in runner.files if p.startswith("/var/backups")]
    assert copies == [], f"비밀 값의 사본이 백업 디렉터리에 남았다: {copies}"


def test_writing_the_same_value_is_not_a_change():
    runner = FakeRunner({f"{SECRETS}/smtp.password": VALUE})
    result = _run(runner, "secret.write", {"name": "smtp.password", "value": VALUE})
    assert result.ok and result.changed is False


def test_a_text_slot_refuses_line_breaks():
    runner = FakeRunner()
    result = _run(runner, "secret.write", {"name": "ai.openai.api_key", "value": "abc\ndef"})
    assert result.ok is False
    assert runner.files == {}


def test_the_chatgpt_slot_only_accepts_a_json_object():
    runner = FakeRunner()
    assert _run(runner, "secret.write", {"name": "ai.openai.chatgpt", "value": "not-json"}).ok is False
    ok = _run(runner, "secret.write", {"name": "ai.openai.chatgpt", "value": json.dumps({"a": 1})})
    assert ok.ok, ok.detail


def test_delete_removes_the_file_and_reports_whether_it_existed():
    runner = FakeRunner({f"{SECRETS}/smtp.password": VALUE})
    gone = _run(runner, "secret.delete", {"name": "smtp.password"})
    assert gone.ok and gone.changed is True
    assert f"{SECRETS}/smtp.password" not in runner.files
    again = _run(runner, "secret.delete", {"name": "smtp.password"})
    assert again.ok and again.changed is False


def test_the_helper_audit_log_never_contains_the_value(tmp_path):
    audit = tmp_path / "audit.jsonl"
    raw = encode_request("secret.write", {"name": "smtp.password", "value": VALUE}, request_id="r1")
    reply = handle_request(
        raw, caller_uid=1000, backup_root=str(tmp_path / "backups"), audit_log=str(audit),
        runner=FakeRunner(), now=NOW,
    )
    assert reply["ok"] is True
    text = audit.read_text(encoding="utf-8")
    assert "secret.write" in text
    assert VALUE not in text, "헬퍼 감사 기록에 비밀 값이 남았다"
    assert VALUE not in json.dumps(reply)
