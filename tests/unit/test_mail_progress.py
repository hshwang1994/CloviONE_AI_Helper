"""메일 설정의 일곱 단계와 다음 할 일 (기능 개선 회차 P4, D-560).

못박는 성질:
1. 단계는 일곱이고 순서가 고정이다. 다음 할 일은 첫 `current` 또는 `blocked` 다. 전부 되면 다음 할 일이 없다.
2. 「발송 꺼짐 + 로컬 릴레이 켜짐」은 1단계가 할 일이다 - 동작 중인 릴레이가 「사용 안 함」 옆에 서던 상태(사용자가 본 것).
3. 입력 문제는 3단계, 로컬 릴레이의 켜짐 · 적용은 4단계, 건강 상태의 정상 · 실패는 5단계, 시험 메일의 접수 · 실패는 6단계,
   사람의 기록은 7단계다 - 서로 섞이지 않는다. 접수(6)는 도착(7)이 아니다.
4. 외부 SMTP 는 적용 단계가 없어(저장이 곧 적용) 입력이 끝나면 4단계가 곧바로 끝난다.
5. 받은 편지함 기록은 **그 시험 메일**에 대한 것이어야 한다 - 새 시험 메일을 보내면 다시 확인할 일이 된다.
"""

from __future__ import annotations

import pytest

from app.mail import progress
from app.mail.config import MODE_LOCAL_RELAY, smtp_config

pytestmark = pytest.mark.unit


class _Secrets:
    """비밀 칸의 대역 - 적은 칸만 저장돼 있다고 답한다."""

    def __init__(self, *configured: str) -> None:
        self._configured = set(configured)

    def status(self, slot: str) -> str:
        return "configured" if slot in self._configured else "missing"


def _config(**over):
    value = {"enabled": True, "host": "smtp.example.com", "port": 587, "security": "starttls",
             "from_address": "noreply@example.com", "from_name": "", "username": "", "timeout_seconds": 20}
    value.update(over)
    return smtp_config(value)


def _relay_config(**over):
    relay = {"delivery": "direct", "helo_name": "mail.example.com", "dkim_enabled": False}
    relay.update(over.pop("relay", {}))
    return _config(host="", mode=MODE_LOCAL_RELAY, relay=relay, **over)


def _health(state: str, **over):
    return {"state": state, "message": {"ok": "메일 발송을 사용할 수 있습니다.", "failing": "로그인을 거부했습니다."}.get(state, ""),
            "hint": None, **over}


def _states(result):
    return [s["state"] for s in result["steps"]]


def test_the_seven_steps_are_fixed_and_a_fresh_install_starts_at_enable():
    result = progress.compute(_config(enabled=False, host=""), _Secrets(), health=_health("disabled"), relay=None,
                              test=None, inbox=None)
    assert [s["key"] for s in result["steps"]] == [k for k, _ in progress.STEPS]
    assert _states(result) == ["current", "todo", "todo", "todo", "todo", "todo", "todo"]
    assert result["next"]["key"] == "enable" and result["next"]["hint"] == "메일 발송을 켜고 저장하세요."
    assert result["done_count"] == 0 and result["complete"] is False


def test_off_but_running_relay_is_step_one_not_a_working_setup():
    relay = {"delivery": "direct", "component": {"state": "running", "stale": False, "label": "동작 중"}, "outer": None}
    result = progress.compute(_relay_config(enabled=False), _Secrets(), health=_health("disabled"), relay=relay,
                              test=None, inbox=None)
    assert result["next"]["key"] == "enable", "동작 중인 릴레이가 「사용 안 함」 옆에 서도 할 일은 켜기다"
    assert _states(result)[3] == "todo"


def test_missing_inputs_are_step_three_with_the_first_problem_as_the_hint():
    result = progress.compute(_config(from_address=""), _Secrets(), health=_health("unconfigured"), relay=None,
                              test=None, inbox=None)
    assert _states(result)[:4] == ["done", "done", "current", "todo"]
    assert result["next"] == {"key": "inputs", "label": "보내는 사람과 방식별 정보 입력", "state": "current",
                              "hint": "보내는 사람 주소가 비어 있습니다.", "anchor": "section:inputs"}


def test_external_smtp_skips_to_verify_once_inputs_are_complete():
    result = progress.compute(_config(), _Secrets(), health=_health("unverified"), relay=None, test=None, inbox=None)
    assert _states(result) == ["done", "done", "done", "done", "current", "todo", "todo"]
    assert result["next"]["key"] == "verified" and result["next"]["anchor"] == "action:verify"


@pytest.mark.parametrize("component, expected_state, expected_hint", [
    ({"state": "ready", "stale": False}, "current", "로컬 릴레이를 활성화하세요."),
    ({"state": "running", "stale": True}, "current", "저장한 설정을 로컬 릴레이에 다시 적용하세요."),
    ({"state": "not_installed", "stale": False, "message": "구성 요소가 설치되지 않았습니다."}, "blocked",
     "구성 요소가 설치되지 않았습니다."),
])
def test_a_local_relay_that_is_not_applied_is_step_four(component, expected_state, expected_hint):
    secrets = _Secrets()  # 앱 열쇠가 없다 = 릴레이가 아직 켜지지 않았다(입력 문제가 아니다)
    relay = {"delivery": "direct", "component": component, "outer": None}
    result = progress.compute(_relay_config(), secrets, health=_health("unconfigured"), relay=relay, test=None, inbox=None)
    assert _states(result)[2] == "done", "릴레이가 안 켜진 것은 입력 문제가 아니다"
    assert result["next"]["key"] == "applied" and result["next"]["state"] == expected_state
    assert result["next"]["hint"] == expected_hint


def test_a_failing_connection_blocks_step_five_with_the_cause_and_the_hint():
    health = _health("failing", hint="비밀번호가 틀렸거나 앱 비밀번호가 필요합니다.")
    result = progress.compute(_config(), _Secrets(), health=health, relay=None, test=None, inbox=None)
    assert result["next"]["key"] == "verified" and result["next"]["state"] == "blocked"
    assert result["next"]["hint"] == "로그인을 거부했습니다. 비밀번호가 틀렸거나 앱 비밀번호가 필요합니다."


@pytest.mark.parametrize("test, expected_state, expected_hint", [
    (None, "current", "시험 메일을 보내세요."),
    ({"id": "d1", "status": "queued", "remote_status": None}, "current", "시험 메일을 보내는 중입니다."),
    ({"id": "d1", "status": "failed", "error_summary": "받는 사람을 거부했습니다.", "remote_status": None}, "blocked",
     "시험 메일을 보내지 못했습니다. 받는 사람을 거부했습니다."),
])
def test_the_test_mail_is_step_six(test, expected_state, expected_hint):
    result = progress.compute(_config(), _Secrets(), health=_health("ok"), relay=None, test=test, inbox=None)
    assert _states(result)[:5] == ["done"] * 5
    assert result["next"]["key"] == "test_sent" and result["next"]["state"] == expected_state
    assert result["next"]["hint"] == expected_hint


def test_acceptance_is_not_arrival_and_the_person_records_the_inbox():
    sent = {"id": "d1", "status": "sent", "remote_status": None}
    waiting = progress.compute(_config(), _Secrets(), health=_health("ok"), relay=None, test=sent, inbox=None)
    assert _states(waiting) == ["done"] * 6 + ["current"]
    assert waiting["next"]["hint"] == "받은 편지함에서 시험 메일을 확인한 뒤 「받았습니다」를 누르세요."

    received = progress.compute(_config(), _Secrets(), health=_health("ok"), relay=None, test=sent,
                                inbox={"delivery_id": "d1", "received": True})
    assert received["complete"] is True and received["next"] is None and received["done_count"] == 7

    missing = progress.compute(_config(), _Secrets(), health=_health("ok"), relay=None, test=sent,
                               inbox={"delivery_id": "d1", "received": False})
    assert missing["next"]["key"] == "inbox_confirmed" and missing["next"]["state"] == "blocked"

    newer = progress.compute(_config(), _Secrets(), health=_health("ok"), relay=None,
                             test={"id": "d2", "status": "sent", "remote_status": None},
                             inbox={"delivery_id": "d1", "received": True})
    assert newer["next"]["key"] == "inbox_confirmed", "새 시험 메일은 다시 확인할 일이다"


def test_a_bounce_from_the_receiving_server_blocks_the_inbox_step_for_a_direct_relay():
    # 비밀 대역 없이(None) 부른다 - 앱 열쇠 · 서버 인증서 검사는 통합 시험의 몫이고, 여기서는 단계 규칙만 본다.
    relay = {"delivery": "direct", "component": {"state": "running", "stale": False}, "outer": {"status": "bounced"}}
    result = progress.compute(_relay_config(), None, health=_health("ok"), relay=relay,
                              test={"id": "d1", "status": "sent", "remote_status": "bounced"}, inbox=None)
    assert result["next"]["key"] == "inbox_confirmed" and result["next"]["state"] == "blocked"
    assert "담당자" in result["next"]["hint"]
