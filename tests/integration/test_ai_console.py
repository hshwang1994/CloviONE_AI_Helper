"""AI 설정 API — `/api/admin/ai` (계획 3.13 · 3.14, D-515).

qa-contract-replaced-by: tests/integration/test_llm_console.py

옛 `/api/admin/llm` 시험을 대신한다. 서버에 로그인된 명령줄 도구와 환경 변수 오버레이가 없어졌으므로 그 둘을 재던
단언(로그인 안내, 환경 변수 우선순위, 실행 파일)은 옮기지 않았다. 연결 확인이 잡이고 한 번만 시도한다는 것, 감사에
남는다는 것, 시스템 관리자만 쓴다는 것은 여기서 다시 잰다.

못박는 것:
  * 시스템 관리자만 읽고 쓴다(관리자 403).
  * 화면이 한 번에 받는 값: 설정, 연결 상태, 제공자 표(지원하는 인증 방식만), AI 기능 스위치, 범위.
  * 저장은 한 벌로 검사한다 - 모르는 제공자, 모델 없이 켜기, 범위 밖 제한 시간은 422 다. 저장은 감사에 남는다.
  * 키를 넣으면 끝 네 글자만 보인다. 키는 어디에도 되돌아오지 않는다.
  * 모델 목록은 제공자에게서 받고, 못 받으면 502 와 까닭이다.
  * 연결 확인은 잡이다. 워커가 돌면 결과와 연결 상태가 함께 온다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from tests.integration.test_ai_runtime import KEY, MESSAGES, _ok

pytestmark = pytest.mark.integration

MODELS = "https://api.anthropic.com/v1/models"


def _drain(app, settings, fake_clock):
    """워커 한 바퀴. 웹과 같은 런타임과 가짜 전송을 쓴다 - 메일 시험의 `drain_worker` 는 바깥 호출 관문이 없다."""
    from app.ai.runtime import runtime_for_app
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client,
        extras={"ai_runtime": runtime_for_app(app), "secret_provider": app.state.secret_provider,
                "settings_cache": app.state.settings_cache},
    )
    worker = Worker(app.state.session_factory, fake_clock, build_handlers(), ctx)
    for _ in range(20):
        if not worker.run_once():
            break


def _put(client, csrf, body):
    return client.put("/api/admin/ai/config", json=body, headers={"X-CSRF-Token": csrf})


def test_only_a_system_admin_reaches_the_ai_console(client, login_as):
    csrf = login_as("admin")
    assert client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).status_code == 403
    assert _put(client, csrf, {"model": "x"}).status_code == 403


def test_the_overview_has_everything_the_screen_draws(client, login_as):
    csrf = login_as("system_admin")
    body = client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).json()
    assert body["config"]["generation_enabled"] is False
    assert body["state"]["state"] == "unconfigured"
    (anthropic,) = [p for p in body["providers"] if p["key"] == "anthropic"]
    assert [m["key"] for m in anthropic["auth_methods"]] == ["api_key"], "지원하지 않는 인증 방식이 보인다"
    assert set(body["features"]) == {"chat_enabled", "assistant_narrative_enabled", "game_ai_enabled"}
    assert body["limits"]["max_concurrency"] == [1, 8]


def test_saving_validates_the_whole_config_and_is_audited(client, login_as, db):
    csrf = login_as("system_admin")
    assert _put(client, csrf, {"provider": "nobody"}).status_code == 422
    assert _put(client, csrf, {"provider": "anthropic", "generation_enabled": True}).status_code == 422, (
        "모델 없이 켜졌다"
    )
    assert _put(client, csrf, {"timeout_seconds": 3}).status_code == 422
    assert _put(client, csrf, {"auth_method": "chatgpt", "provider": "anthropic"}).status_code == 422

    r = _put(client, csrf, {"provider": "anthropic", "model": "claude-test", "generation_enabled": True})
    assert r.status_code == 200, r.text
    config = r.json()["config"]
    assert (config["provider"], config["auth_method"], config["model"], config["generation_enabled"]) == (
        "anthropic", "api_key", "claude-test", True,
    ), "방식이 하나뿐인 제공자인데 인증 방식을 채우지 않았다"
    db.expire_all()
    row = db.execute(select(AuditLog).where(AuditLog.action == "ai.config.update")).scalar_one()
    assert "claude-test" in (row.after_json or "")


def test_a_saved_key_shows_only_its_last_four_characters(client, login_as, settings):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    response = client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf})
    method = response.json()["providers"][0]["auth_methods"][0]
    assert method["secret_set"] is True and method["secret_hint"] == "끝자리 WXYZ"
    assert KEY not in response.text, "키가 응답에 실렸다"


def test_models_come_from_the_provider_and_a_failure_is_a_502(client, login_as, settings, fake_http):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    fake_http.on(MODELS, status=401, json_body={"error": {"type": "authentication_error"}})
    bad = client.get("/api/admin/ai/models", params={"provider": "anthropic", "auth_method": "api_key"},
                     headers={"X-CSRF-Token": csrf})
    assert bad.status_code == 502 and "거부" in bad.json()["error"]["message"]
    fake_http.on(MODELS, json_body={"data": [{"id": "claude-a", "display_name": "Claude A"}]})
    good = client.get("/api/admin/ai/models", params={"provider": "anthropic", "auth_method": "api_key"},
                      headers={"X-CSRF-Token": csrf})
    assert good.status_code == 200 and good.json()["models"] == [{"id": "claude-a", "label": "Claude A"}]


def test_verify_is_a_one_shot_job_whose_result_carries_the_state(client, login_as, app, settings, fake_http,
                                                                  fake_clock, db):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    assert _put(client, csrf, {"provider": "anthropic", "model": "claude-test"}).status_code == 200
    fake_http.on(MESSAGES, json_body=_ok(text="확인"))
    started = client.post("/api/admin/ai/verify", headers={"X-CSRF-Token": csrf}).json()
    pending = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert pending["pending"] is True and pending["result"] is None, "큐에 있는데 결과를 지어냈다"

    _drain(app, settings, fake_clock)
    done = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert done["pending"] is False and done["result"]["ok"] is True, done
    assert done["state"]["state"] == "ok"
    from app.jobs.models import Job

    db.expire_all()
    assert db.get(Job, started["job_id"]).max_attempts == 1
    assert db.execute(select(AuditLog).where(AuditLog.action == "ai.connection.test")).scalar_one()


def test_a_failed_verify_says_why_in_our_words(client, login_as, app, settings, fake_http, fake_clock):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    _put(client, csrf, {"provider": "anthropic", "model": "claude-test"})
    fake_http.on(MESSAGES, status=401, json_body={"error": {"type": "authentication_error", "message": "raw-secret-ish"}})
    started = client.post("/api/admin/ai/verify", headers={"X-CSRF-Token": csrf}).json()
    _drain(app, settings, fake_clock)
    done = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert done["result"]["ok"] is False and "API 키가 거부" in done["result"]["message"]
    assert "raw-secret-ish" not in str(done), "제공자 원문이 화면으로 나갔다"
    assert done["state"]["state"] == "error"
