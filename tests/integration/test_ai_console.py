"""AI 연결 API — `/api/admin/ai` (계획 A3, D-515 · D-539). 화면은 `/ai-connection` 이다.

qa-contract-replaced-by: tests/integration/test_llm_console.py

qa-contract-change: 모델 목록 응답에 추천 표지(`recommended` · `recommended_id`)가 붙고, 인증 · 모델을 바꾸거나 AI 사용을 켜면
저장 응답이 연결 확인 잡을 함께 연다(D-539) — 그래서 「확인 잡의 감사가 정확히 한 행」 단언을 「저장이 연 확인을 「지금 확인」이
다시 쓰고, 감사에 까닭이 남는다」로 옮겼다. 확인 단추를 누르지 않아도 정상에 닿는다는 성질과 상태 낱말(확인 중 · 꺼짐)은 새
시험이 잰다.

옛 `/api/admin/llm` 시험을 대신한다. 서버에 로그인된 명령줄 도구와 환경 변수 오버레이가 없어졌으므로 그 둘을 재던
단언(로그인 안내, 환경 변수 우선순위, 실행 파일)은 옮기지 않았다. 연결 확인이 잡이고 한 번만 시도한다는 것, 감사에
남는다는 것, 시스템 관리자만 쓴다는 것은 여기서 다시 잰다.

못박는 것:
  * 시스템 관리자만 읽고 쓴다(관리자 403).
  * 화면이 한 번에 받는 값: 설정, 연결 상태, 제공자 표(지원하는 인증 방식만), AI 기능 스위치, 범위.
  * 저장은 한 벌로 검사한다 - 모르는 제공자, 모델 없이 켜기, 범위 밖 제한 시간은 422 다. 저장은 감사에 남는다.
  * 키를 넣으면 끝 네 글자만 보인다. 키는 어디에도 되돌아오지 않는다.
  * 모델 목록은 제공자에게서 받고, 못 받으면 502 와 까닭이다. 추천은 표의 앞머리 순서다(저장하지 않는다).
  * 연결 확인은 잡이다. 인증 · 모델을 바꾸거나 AI 사용을 켜면 저절로 열리고, 워커가 돌면 결과와 연결 상태가 함께 온다.
  * 상태 낱말은 서버가 정한다: 미설정 · 확인 중 · 꺼짐 · 정상 · 연결 오류(초기 설정의 AI 항목과 같은 함수).
  * 연결 확인은 도구 시험까지 한다 - 도구 호출이 오면 「도구 호출 사용 가능」이다. 도구 시험의 실패는 확인을 실패시키지 않는다.
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
    assert good.status_code == 200
    assert good.json() == {"models": [{"id": "claude-a", "label": "Claude A", "recommended": False}],
                           "recommended_id": None}


def test_the_recommendation_follows_the_table_and_is_not_saved(client, login_as, settings, fake_http):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    fake_http.on(MODELS, json_body={"data": [
        {"id": "claude-haiku-9-1", "display_name": "Claude Haiku 9.1"},
        {"id": "claude-sonnet-9-2", "display_name": "Claude Sonnet 9.2"},
        {"id": "claude-sonnet-9-1", "display_name": "Claude Sonnet 9.1"},
    ]})
    body = client.get("/api/admin/ai/models", params={"provider": "anthropic", "auth_method": "api_key"},
                      headers={"X-CSRF-Token": csrf}).json()
    assert body["recommended_id"] == "claude-sonnet-9-2", "서버 순서(최신 먼저)의 첫 sonnet 이 추천이다"
    assert [m["id"] for m in body["models"] if m["recommended"]] == ["claude-sonnet-9-2"]
    assert client.get("/api/admin/ai").json()["config"]["model"] == "", "추천만으로 저장하지 않는다"


def test_verify_is_a_one_shot_job_whose_result_carries_the_state(client, login_as, app, settings, fake_http,
                                                                  fake_clock, db):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    saved = _put(client, csrf, {"provider": "anthropic", "model": "claude-test"})
    assert saved.status_code == 200
    opened = saved.json()["verify_job_id"]
    assert opened, "인증 · 모델이 정해졌는데 확인을 저절로 열지 않았다"
    assert saved.json()["state"]["display"]["label"] == "확인 중"
    fake_http.on(MESSAGES, json_body=_ok(text="확인"))
    started = client.post("/api/admin/ai/verify", headers={"X-CSRF-Token": csrf}).json()
    assert started["job_id"] == opened, "큐에 있는 확인이 있으면 같은 설정을 두 번 재지 않는다"
    pending = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert pending["pending"] is True and pending["result"] is None, "큐에 있는데 결과를 지어냈다"

    _drain(app, settings, fake_clock)
    done = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert done["pending"] is False and done["result"]["ok"] is True, done
    assert done["state"]["state"] == "ok"
    from app.jobs.models import Job

    db.expire_all()
    assert db.get(Job, started["job_id"]).max_attempts == 1
    reasons = sorted(row.after_json for row in db.execute(
        select(AuditLog).where(AuditLog.action == "ai.connection.test")).scalars())
    assert len(reasons) == 2 and '"config"' in reasons[0] and '"manual"' in reasons[1], reasons


def test_saving_the_connection_reaches_ok_without_pressing_verify(client, login_as, app, settings, fake_http,
                                                                    fake_clock):
    """D-539: 키를 넣고 모델을 정하면 사람이 확인 단추를 누르지 않아도 「확인 중 → 정상」이다. 제한 시간만 바꾸면 다시
    재지 않는다. AI 사용을 켜면 다시 잰다. 꺼져 있으면 연결이 정상이어도 낱말은 「꺼짐」이다."""
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    assert client.get("/api/admin/ai").json()["state"]["display"]["label"] == "미설정"
    fake_http.on(MESSAGES, json_body=_ok(text="확인"))
    assert _put(client, csrf, {"provider": "anthropic", "model": "claude-test"}).json()["verify_job_id"]
    _drain(app, settings, fake_clock)
    shown = client.get("/api/admin/ai").json()["state"]
    assert shown["verifying"] is False and shown["state"] == "ok"
    assert shown["display"]["label"] == "꺼짐", "AI 사용이 꺼져 있으면 연결이 정상이어도 꺼짐이다"

    assert _put(client, csrf, {"timeout_seconds": 45}).json()["verify_job_id"] is None, "연결의 성질이 아닌 값"
    turned_on = _put(client, csrf, {"generation_enabled": True}).json()
    assert turned_on["verify_job_id"], "AI 사용을 켜면 다시 잰다"
    _drain(app, settings, fake_clock)
    assert client.get("/api/admin/ai").json()["state"]["display"]["label"] == "정상"


def test_an_automatically_chosen_model_is_marked_in_the_audit(client, login_as, settings, db):
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    assert _put(client, csrf, {"provider": "anthropic", "model": "claude-sonnet-9-2", "auto_model": True}).status_code == 200
    db.expire_all()
    row = db.execute(select(AuditLog).where(AuditLog.action == "ai.config.update")).scalar_one()
    assert '"auto": true' in row.after_json and "claude-sonnet-9-2" in row.after_json


def test_verify_also_probes_tools_and_a_refusal_does_not_fail_it(client, login_as, app, settings, fake_http,
                                                                   fake_clock):
    import json as _json

    import httpx

    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    seen: list = []

    def provider(request):
        body = _json.loads(request.content)
        seen.append(body)
        if body.get("tools"):
            assert body["tool_choice"] == {"type": "tool", "name": "ping"}
            return httpx.Response(200, json={"content": [{"type": "tool_use", "id": "t1", "name": "ping", "input": {}}],
                                             "stop_reason": "tool_use",
                                             "usage": {"input_tokens": 3, "output_tokens": 2}}, request=request)
        return httpx.Response(200, json=_ok(text="확인"), request=request)

    fake_http.on_handler(MESSAGES, provider)
    _put(client, csrf, {"provider": "anthropic", "model": "claude-test"})
    _drain(app, settings, fake_clock)
    body = client.get("/api/admin/ai").json()
    assert body["state"]["state"] == "ok"
    assert body["capabilities"]["tools"] == "ok", "도구 호출을 받았는데 모른다고 했다"
    assert [bool(b.get("tools")) for b in seen] == [False, True], "생성 한 번, 도구 시험 한 번이다"


def test_verify_right_after_saving_reads_what_was_saved_not_a_stale_worker_cache(
    client, login_as, app, settings, fake_http, fake_clock
):
    """워커는 웹과 다른 프로세스라 설정 캐시가 따로 있다(TTL 30초). 저장 직후 연결 확인이 그 캐시의 옛 값으로 돌아
    「AI 제공자를 아직 고르지 않았습니다」라고 답하던 결함을 막는다(Release 리허설 실측). 위의 시험들은 워커가 웹과 같은
    캐시를 써서 이 경우를 볼 수 없었다."""
    from app.ai.runtime import AiRuntime
    from app.jobs.worker import Worker, WorkerContext
    from app.settings.service import SettingsCache
    from app.worker_main import build_handlers

    worker_cache = SettingsCache(settings, ttl_seconds=3600)
    with app.state.session_factory() as s:
        worker_cache.load(s)  # 저장 전에 채운 워커 캐시 - TTL 이 길어 스스로는 새로 읽지 않는다
    worker_runtime = AiRuntime(settings=settings, outbound=app.state.outbound_client,
                               secrets=app.state.secret_provider, session_factory=app.state.session_factory,
                               settings_cache=worker_cache, clock=fake_clock)

    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    assert _put(client, csrf, {"provider": "anthropic", "model": "claude-test"}).status_code == 200
    fake_http.on(MESSAGES, json_body=_ok(text="확인"))
    started = client.post("/api/admin/ai/verify", headers={"X-CSRF-Token": csrf}).json()

    ctx = WorkerContext(settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client,
                        extras={"ai_runtime": worker_runtime, "secret_provider": app.state.secret_provider,
                                "settings_cache": worker_cache})
    worker = Worker(app.state.session_factory, fake_clock, build_handlers(), ctx)
    for _ in range(20):
        if not worker.run_once():
            break
    done = client.get(f"/api/admin/ai/verify/{started['job_id']}", headers={"X-CSRF-Token": csrf}).json()
    assert done["result"]["ok"] is True, done


def test_another_web_process_with_a_stale_cache_still_shows_what_was_saved(client, login_as, app, settings):
    """웹 프로세스가 여럿이면 저장을 받지 않은 프로세스의 캐시는 30초 동안 옛 값이다. AI 설정 조회는 그 캐시를 믿지 않고
    다시 읽는다(Release 리허설에서 연결 확인 결과의 상태 칸이 「미설정」으로 어긋났다)."""
    (settings.secrets_dir / "ai.anthropic.api_key").write_text(KEY, encoding="utf-8")
    csrf = login_as("system_admin")
    cache = app.state.settings_cache
    with app.state.session_factory() as s:
        stale = cache.load(s)  # 저장 전 값
    assert _put(client, csrf, {"provider": "anthropic", "model": "claude-test"}).status_code == 200
    with cache._lock:  # 저장을 받지 않은 다른 프로세스의 캐시 - 저장 전 값을 그대로 들고 있다
        cache._values = dict(stale)
    body = client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).json()
    assert body["config"]["provider"] == "anthropic", "다른 프로세스가 저장 전 값을 보였다"


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
    assert client.get("/api/admin/ai").json()["state"]["display"]["label"] == "연결 오류"


# ── 문서 검색(의미 검색) 상태 — 정직한 낱말 (D-570) ─────────────────────────────────────────────────────────


class _Embed:
    """임베딩 능력 하나만 흉내 낸다 — 콘솔은 `capabilities().embed.status` 만 읽는다."""

    def __init__(self, status):
        from app.ai.gateway import contract

        self.name, self.model, self.dim = "fake", "fake", 384
        self._cap = (contract.available(contract.CAP_EMBED, model="fake") if status == "ok"
                     else contract.unavailable(contract.CAP_EMBED, status, model="fake"))

    def capability(self):
        return self._cap


@pytest.mark.parametrize("status", ["runtime_missing", "model_missing", "ok"])
def test_the_embed_status_is_the_gateways_reason_in_our_words(status):
    from app.ai.console import service
    from app.ai.gateway import contract

    gateway = contract.Gateway(enabled=True, embed_adapter=_Embed(status))
    assert service.embed_status_of(gateway) == status
    assert service.embed_status_of(contract.Gateway(enabled=False)) == "disabled"
    assert service.embed_status_of(contract.Gateway(enabled=True, embed_adapter=None)) == "unconfigured"
    assert service.embed_status_of(None) == "disabled"


def test_the_document_search_label_and_hint_for_every_state():
    from app.ai.console import service

    labels = {status: service.embed_label(status) for status in service.EMBED_STATUSES}
    assert labels == {
        "disabled": "낱말 검색(의미 검색 기능 꺼짐)",
        "unconfigured": "낱말 검색(의미 검색 모델 미설치)",
        "runtime_missing": "낱말 검색(의미 검색 런타임 미설치)",
        "model_missing": "낱말 검색(의미 검색 모델 미설치)",
        "failed": "낱말 검색(의미 검색 오류)",
        "ok": "낱말 검색 + 의미 검색",
    }
    assert service.embed_label("ok", pending=40, embedded=2197, chunks=2237) == \
        "낱말 검색 + 의미 검색 준비 중(색인 2197/2237)"
    assert service.embed_label("disabled", model_installed=True) == "낱말 검색(의미 검색 기능 꺼짐, 모델 설치됨)"
    assert service.embed_hint("ok") is None
    hint = service.embed_hint("disabled")
    assert "sudo clovirassist ai --with-ai" in hint and "--download-model" in hint and hint.endswith("니다.")
    assert service.embed_hint("model_missing") == hint
    assert "ai-cli status" in service.embed_hint("failed")


def test_next_step_names_the_server_command_only_when_the_connection_itself_is_fine():
    from types import SimpleNamespace

    from app.ai.console import service

    config = SimpleNamespace(method=lambda: None, model="m")
    ok = {"key": "ok"}
    assert service.next_view(ok, config, {}, credentials={"ready": True},
                             index={"embed_hint": service.EMBED_HINT}) == {"label": service.EMBED_HINT,
                                                                         "action": "server"}
    assert service.next_view(ok, config, {}, credentials={"ready": True}, index={"embed_hint": None}) is None
    off = service.next_view({"key": "off"}, config, {}, credentials={"ready": True},
                            index={"embed_hint": service.EMBED_HINT})
    assert off["action"] == "enable", "연결 할 일이 의미 검색 안내에 가리면 안 된다"


def test_the_overview_says_semantic_search_is_off_and_whether_the_model_is_already_there(
    client, login_as, app, settings,
):
    from app.ai import catalog
    from app.ai.gateway import contract, registry

    csrf = login_as("system_admin")
    app.state.ai_gateway = contract.Gateway(enabled=False)
    index = client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).json()["index"]
    assert index["embed_status"] == "disabled"
    assert index["embed_status_label"] == "낱말 검색(의미 검색 기능 꺼짐)"
    assert index["model_installed"] is False
    assert index["pending_embedding"] == index["chunks"] - index["embedded"]
    assert index["semantic"] is False and "sudo clovirassist ai --with-ai" in index["embed_hint"]

    config = registry.resolve_config(settings)
    model = catalog.embedding_model(config.embed_model_id)
    folder = registry.model_dir(config, model)
    for name in model.required_files:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"x")
    index = client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).json()["index"]
    assert index["model_installed"] is True
    assert index["embed_status_label"] == "낱말 검색(의미 검색 기능 꺼짐, 모델 설치됨)"
