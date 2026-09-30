"""AI 생성의 유일한 문 — 설정, 연결 상태, 차단기, 출력 규칙 (계획 3.13 · 3.15, D-515).

qa-contract-replaced-by: tests/integration/test_llm_cli_backend.py

서버에 로그인된 구독 명령줄 도구 백엔드와 `LlmService` 는 공식 정책상 더 쓸 수 없어 걷었다. 그 시험이 재던 것 중
남는 성질(동시 실행 슬롯, 실패를 값으로 돌려주기, 출력 정제)은 여기서 런타임에 대해 다시 잰다.

진짜 Anthropic 어댑터를 가짜 전송(`tests/fakes/http.py`) 위에서 돌린다. 못박는 것:

  * 생성은 관리자가 켜기 전에는 나가지 않는다. 설정을 바꾸면 **재시작 없이** 다음 호출이 새 값을 쓴다.
  * 제공자에는 조립이 끝난 프롬프트만 가고, 키는 헤더로만 간다.
  * 성공이 연결 상태를 「정상」으로 만든다. 키가 거부되면 사람이 새 키를 넣을 때까지 제공자에 다시 가지 않는다.
  * 일시 실패는 다음 호출을 막지 않는다. 짧은 사이에 세 번 이어지면 30초만 곧바로 돌려보낸다.
  * 관리자는 막힌 상태를 한 번, 복구를 한 번 듣는다.
  * 글 액션은 자르고 표시하며, JSON 액션은 자르지 않고 실패한다. 슬롯이 다 차 있으면 기다리지 않고 값으로 알린다.
"""

from __future__ import annotations

import json
import os

import pytest

from app.ai.gateway import contract

pytestmark = pytest.mark.integration

MESSAGES = "https://api.anthropic.com/v1/messages"
KEY = "sk-ant-test-" + "a" * 20 + "WXYZ"


def _key_file(settings):
    return settings.secrets_dir / "ai.anthropic.api_key"


def _configure(app, settings, *, enabled=True, model="claude-test", key=KEY):
    from app.settings.service import apply_setting

    if key is not None:
        _key_file(settings).write_text(key, encoding="utf-8")
    with app.state.session_factory() as db:
        for name, value in {
            "ai_provider": "anthropic", "ai_auth_method": "api_key", "ai_model": model,
            "ai_generation_enabled": enabled,
        }.items():
            apply_setting(db, app.state.settings_cache, key=name, value=value, updated_by=None,
                          now=app.state.clock.now())
        db.commit()


def _ok(text="답입니다.", input_tokens=12, output_tokens=5):
    return {"content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}


def _runtime(app):
    from app.ai.runtime import runtime_for_app

    return runtime_for_app(app)


def _generate(app, *, action="chat.answer", data="질문입니다."):
    with app.state.session_factory() as db:
        result = _runtime(app).generate(db, action_key=action, task="짧게 답하세요.", data=data)
        db.commit()
    return result


def _status(app):
    with app.state.session_factory() as db:
        return _runtime(app).status(db)


def _sequence(fake_http, responses):
    """부를 때마다 다음 응답을 준다. `(status, body)` 목록이다."""
    calls = {"n": 0}

    def handler(request):
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[index]

    fake_http.on_handler(MESSAGES, handler)
    return calls


def _messages_calls(fake_http):
    return [r for r in fake_http.requests if str(r.url).startswith(MESSAGES)]


# ── 설정 ─────────────────────────────────────────────────────────────────────

def test_generation_is_off_until_an_admin_turns_it_on(app, settings, fake_http):
    _configure(app, settings, enabled=False)
    fake_http.on(MESSAGES, json_body=_ok())
    result = _generate(app)
    assert result.status == contract.STATUS_DISABLED
    assert _messages_calls(fake_http) == [], "꺼져 있는데 제공자를 불렀다"


def test_a_saved_setting_applies_to_the_next_call_without_a_restart(app, settings, fake_http):
    _configure(app, settings, enabled=False)
    fake_http.on(MESSAGES, json_body=_ok())
    assert _generate(app).status == contract.STATUS_DISABLED
    _configure(app, settings, enabled=True, model="claude-next")
    result = _generate(app)
    assert result.ok, result
    body = json.loads(_messages_calls(fake_http)[-1].content)
    assert body["model"] == "claude-next", "바꾼 모델이 다음 호출에 쓰이지 않았다"


def test_a_missing_key_is_unconfigured(app, settings, fake_http):
    _configure(app, settings, key=None)
    assert _generate(app).status == contract.STATUS_UNCONFIGURED
    status = _status(app)
    assert status["state"] == "unconfigured" and "API 키" in " ".join(status["problems"])
    assert _messages_calls(fake_http) == []


# ── 제공자에 가는 것 ─────────────────────────────────────────────────────────

def test_the_provider_sees_only_the_assembled_prompt_and_the_key_header(app, settings, fake_http):
    _configure(app, settings)
    fake_http.on(MESSAGES, json_body=_ok())
    _generate(app, action="workspace.draft", data="사용자가 쓴 글")
    (request,) = _messages_calls(fake_http)
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["max_tokens"] == 4000, "액션의 출력 한도를 넘기지 않았다"
    assert "사용자가 쓴 글" not in body["system"], "사용자 글이 시스템 지시 자리에 섰다"
    assert "사용자가 쓴 글" in body["messages"][0]["content"]
    assert KEY not in request.content.decode("utf-8"), "키가 본문에 실렸다"


def test_success_marks_the_connection_ok_and_reports_tokens(app, settings, fake_http):
    _configure(app, settings)
    fake_http.on(MESSAGES, json_body=_ok(input_tokens=30, output_tokens=7))
    assert _status(app)["state"] == "unverified", "성공한 호출이 없는데 정상이라고 한다"
    result = _generate(app)
    assert result.ok and (result.input_tokens, result.output_tokens) == (30, 7)
    status = _status(app)
    assert status["state"] == "ok" and status["last_success_at"]


# ── 막힌 상태와 일시 장애 ────────────────────────────────────────────────────

def test_a_rejected_key_blocks_until_a_new_key_is_saved(app, settings, fake_http):
    _configure(app, settings)
    calls = _sequence(fake_http, [(401, {"error": {"type": "authentication_error"}}), (200, _ok())])
    assert _generate(app).status == contract.STATUS_CREDENTIAL_ERROR
    assert _status(app)["state"] == "error"
    assert _generate(app).status == contract.STATUS_CREDENTIAL_ERROR
    assert calls["n"] == 1, "거부된 키로 제공자를 다시 불렀다"

    _key_file(settings).write_text(KEY.replace("WXYZ", "ABCD"), encoding="utf-8")
    stat = _key_file(settings).stat()
    os.utime(_key_file(settings), ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert _status(app)["state"] == "unverified", "새 키를 넣었는데 옛 거부 기록이 남았다"
    assert _generate(app).ok
    assert calls["n"] == 2


def test_a_transient_failure_does_not_block_the_next_call(app, settings, fake_http):
    _configure(app, settings)
    _sequence(fake_http, [(503, {"error": {"type": "api_error"}}), (200, _ok())])
    assert _generate(app).status == contract.STATUS_DEGRADED
    assert _status(app)["state"] == "degraded"
    assert _generate(app).ok, "일시 장애 한 번이 다음 호출을 막았다"
    assert _status(app)["state"] == "ok"


def test_repeated_transient_failures_fail_fast_for_a_short_while(app, settings, fake_http, fake_clock):
    _configure(app, settings)
    calls = _sequence(fake_http, [(529, {"error": {"type": "overloaded_error"}})] * 3 + [(200, _ok())])
    for _ in range(3):
        _generate(app)
        fake_clock.advance(5)
    result = _generate(app)
    assert result.status == contract.STATUS_DEGRADED and calls["n"] == 3, "열린 차단기가 호출을 보냈다"
    fake_clock.advance(31)
    assert _generate(app).ok, "쉬는 시간이 지난 첫 호출을 막았다"
    assert calls["n"] == 4


def test_admins_hear_about_a_hard_failure_once_and_about_the_recovery_once(app, settings, fake_http, make_user, db):
    from sqlalchemy import select

    from app.notifications.models import Notification

    boss = make_user("ai-boss@goodmit.co.kr", role="system_admin")
    db.commit()
    _configure(app, settings)
    _sequence(fake_http, [(401, {"error": {"type": "authentication_error"}})])
    _generate(app)
    _generate(app)

    def titles():
        db.expire_all()
        return [n.title for n in db.execute(
            select(Notification).where(Notification.user_id == boss.id, Notification.type == "ai_provider_state")
            .order_by(Notification.created_at)
        ).scalars()]

    assert len(titles()) == 1, titles()
    fake_http.handlers.clear()
    fake_http.on(MESSAGES, json_body=_ok())
    with app.state.session_factory() as s:
        assert _runtime(app).verify(s)["ok"]
        s.commit()
    assert len(titles()) == 2 and "복구" in titles()[-1], titles()


# ── 출력 규칙 ────────────────────────────────────────────────────────────────

def test_long_text_is_cut_and_marked_but_long_json_fails(app, settings, fake_http):
    _configure(app, settings)
    fake_http.on(MESSAGES, json_body=_ok(text="가" * 5000))
    text = _generate(app, action="chat.answer")
    assert text.ok and len(text.text) == 4000 and text.truncated
    fake_http.on(MESSAGES, json_body=_ok(text="[" + "1," * 5000 + "1]"))
    quiz = _generate(app, action="game.quiz")
    assert quiz.status == contract.STATUS_FAILED and quiz.error_code == "output_too_long", "자른 JSON 을 돌려줬다"


def test_control_characters_never_reach_the_screen(app, settings, fake_http):
    _configure(app, settings)
    fake_http.on(MESSAGES, json_body=_ok(text="안녕\x1b[31m하세요\x07\n다음 줄"))
    assert _generate(app).text == "안녕[31m하세요\n다음 줄"


def test_all_slots_busy_is_a_value_not_a_hang(app, settings, fake_http):
    from app.ai.runtime import AiRuntime

    class _Busy:
        def acquire(self):
            return False

        def release(self):
            pass

    _configure(app, settings)
    fake_http.on(MESSAGES, json_body=_ok())
    runtime = AiRuntime(
        settings=app.state.settings, outbound=app.state.outbound_client, secrets=app.state.secret_provider,
        session_factory=app.state.session_factory, settings_cache=app.state.settings_cache, clock=app.state.clock,
        lock_factory=lambda config: _Busy(),
    )
    with app.state.session_factory() as db:
        result = runtime.generate(db, action_key="chat.answer", task="짧게", data="질문")
    assert result.status == contract.STATUS_BUSY
    assert _messages_calls(fake_http) == []


# ── 연결 확인 ────────────────────────────────────────────────────────────────

def test_verify_runs_even_while_generation_is_off_and_marks_the_check_time(app, settings, fake_http):
    _configure(app, settings, enabled=False)
    fake_http.on(MESSAGES, json_body=_ok(text="확인"))
    with app.state.session_factory() as db:
        outcome = _runtime(app).verify(db)
        db.commit()
    assert outcome["ok"], outcome
    status = _status(app)
    assert status["state"] == "ok" and status["checked_at"], status
    body = json.loads(_messages_calls(fake_http)[0].content)
    assert body["max_tokens"] <= 32, "연결 확인이 긴 답을 청했다"
