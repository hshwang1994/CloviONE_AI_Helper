"""LLM 관리 화면 (9-5).

## 이 파일이 지키려는 것

1. **화면에서 저장한 값이 실제로 쓰인다.** `app/llm/provider.py::resolve_config` 는
   `Settings` 필드 -> 환경변수 순으로 읽도록 이미 만들어져 있었다. 그 길이 실제로
   이어졌는지 본다 - 화면만 바뀌고 호출은 옛 값으로 나가면 아무 의미가 없다.
2. **연결 테스트가 웹 요청을 잡아 두지 않는다.** 명령줄 도구 호출은 수십 초가 걸릴 수
   있고, 이 저장소의 핸들러는 전부 sync 라 그동안 처리 칸 하나가 통째로 묶인다.
3. **미로그인을 반드시 구분한다.** 도구는 로그인이 안 돼 있어도 `subtype: "success"` 로
   답한다(`app/llm/cli_backend.py` 가 그 함정을 기록해 뒀다). 그것을 성공으로 읽으면
   영어 오류 문장이 그대로 요약문이 된다.
4. **못 하는 것을 되는 척하지 않는다.** 아직 안 끝난 테스트는 결과가 없다고 말한다.

⚠️ **값이 실제로 달라지는 표본**을 쓴다. 한 세계에서 한 번만 부르고 원하는 문자열을 찾는
테스트는 구현이 상수를 돌려줘도 초록불이다.
"""

from __future__ import annotations

import json

import pytest

from app.llm import provider
from app.llm_console import service as console


@pytest.fixture()
def worker(app, fake_clock):
    """이 테스트의 워커. 잡 하나를 결정적으로 돌린다."""
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers

    def _make(backend=None):
        ctx = WorkerContext(
            settings=app.state.settings,
            clock=fake_clock,
            outbound_client=app.state.outbound_client,
            extras={"llm_backend": backend} if backend is not None else {},
        )
        return Worker(app.state.session_factory, fake_clock, build_handlers(), ctx)

    return _make


class FakeBackend:
    """정해진 결과 하나를 돌려주는 백엔드. **프로세스를 띄우지 않는다.**"""

    name = provider.BACKEND_CLI

    def __init__(self, result: provider.LlmResult) -> None:
        self._result = result
        self.calls = 0

    def summarize(self, *, body: str) -> provider.LlmResult:
        self.calls += 1
        return self._result


def _save(client, csrf, key, value):
    response = client.put(
        f"/api/admin/settings/{key}", json={"value": value}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text
    return response


# ── 1. 권한 ──────────────────────────────────────────────────────────────────


def test_console_is_system_admin_only(client, login_as):
    """실행 파일 경로는 그대로 argv[0] 이 된다. 부서 관리자가 정할 값이 아니다."""
    login_as("admin")
    assert client.get("/api/admin/llm").status_code == 403

    login_as("system_admin")
    assert client.get("/api/admin/llm").status_code == 200


def test_llm_settings_reject_non_system_admin(client, login_as):
    csrf = login_as("admin")
    denied = client.put(
        "/api/admin/settings/llm_executable",
        json={"value": "/opt/bin/claude"},
        headers={"X-CSRF-Token": csrf},
    )
    assert denied.status_code == 403


# ── 2. 화면에서 저장한 값이 실제로 쓰인다 ────────────────────────────────────


def test_saved_settings_win_over_the_environment(client, login_as):
    """저장 -> `resolve_config` 가 그 값을 읽는다. 두 세계를 비교한다."""
    csrf = login_as("system_admin")
    live = client.app.state.settings

    before = client.get("/api/admin/llm").json()["config"]
    assert before["enabled"] is False  # 기본은 꺼짐(fail-closed)
    assert provider.resolve_config(live).enabled is False

    _save(client, csrf, "llm_enabled", "on")
    _save(client, csrf, "llm_model", "opus")
    _save(client, csrf, "llm_executable", "/opt/bin/claude")
    _save(client, csrf, "llm_timeout_seconds", 45)
    _save(client, csrf, "llm_max_concurrency", 3)

    after = client.get("/api/admin/llm").json()["config"]
    assert after["enabled"] is True
    assert after["model"] == "opus"
    assert after["executable"] == "/opt/bin/claude"
    assert after["timeout_seconds"] == 45
    assert after["max_concurrency"] == 3
    assert after != before

    # 🔴 화면 응답이 아니라 **호출부가 읽는 것**을 본다. provider 를 한 줄도 안 고치고
    # 그쪽이 이기는지가 이 과제의 요점이다.
    resolved = provider.resolve_config(live)
    assert resolved.enabled is True
    assert resolved.model == "opus"
    assert resolved.executable == "/opt/bin/claude"
    assert resolved.timeout_seconds == 45

    # 화면이 "이 값이 어디서 왔는가" 를 말할 수 있어야 "저장했는데 왜 안 바뀌지" 의 답이
    # 화면 안에 있다. 저장한 키와 안 한 키가 서로 다르게 나와야 뜻이 있다.
    sources = client.get("/api/admin/llm").json()["sources"]
    assert sources["llm_model"] == "settings"
    assert sources["llm_backend"] == "env"


def test_clearing_a_value_returns_to_the_default(client, login_as):
    """비우기 = '안 정함'. 지운 값이 남아 있으면 화면이 거짓말을 하게 된다."""
    csrf = login_as("system_admin")
    _save(client, csrf, "llm_model", "opus")
    assert client.get("/api/admin/llm").json()["config"]["model"] == "opus"

    _save(client, csrf, "llm_model", "")
    assert client.get("/api/admin/llm").json()["config"]["model"] == provider.DEFAULT_MODEL


def test_zero_timeout_does_not_silence_the_environment_variable(app, settings):
    """0 은 '끄기' 가 아니라 '안 정함' 이다.

    ⚠️ 이 결함을 실제로 만들었다. 오버레이가 `_is_set` 을 그대로 썼는데 `_is_set(0)` 은
    True 라, **아무도 손대지 않은 설치에서 레지스트리 기본값 0 이 그대로 얹혀** env 의
    `LLM_TIMEOUT_SECONDS` 를 조용히 지웠다. 화면에는 아무 표시도 안 났다.
    """
    from app.core.tenant_config import apply_overrides

    settings.llm_timeout_seconds = 300  # env 로 정해 둔 설치
    baseline = {}
    apply_overrides(settings, {"llm_timeout_seconds": 0}, baseline)
    assert settings.llm_timeout_seconds == 300
    assert provider.resolve_config(settings).timeout_seconds == 300

    # 값을 실제로 넣으면 그때는 그쪽이 이긴다(오버레이가 죽어 있는 것이 아니다).
    apply_overrides(settings, {"llm_timeout_seconds": 45}, baseline)
    assert provider.resolve_config(settings).timeout_seconds == 45

    # 다시 0 으로 비우면 env 값으로 되돌아간다.
    apply_overrides(settings, {"llm_timeout_seconds": 0}, baseline)
    assert provider.resolve_config(settings).timeout_seconds == 300


def test_settings_reject_values_that_would_break_the_call(client, login_as):
    csrf = login_as("system_admin")
    headers = {"X-CSRF-Token": csrf}
    assert client.put(
        "/api/admin/settings/llm_backend", json={"value": "gpt"}, headers=headers
    ).status_code == 422
    assert client.put(
        "/api/admin/settings/llm_enabled", json={"value": "yes"}, headers=headers
    ).status_code == 422
    # 상한을 넘는 동시성은 사람의 구독 몫을 빼앗는다.
    assert client.put(
        "/api/admin/settings/llm_max_concurrency", json={"value": 99}, headers=headers
    ).status_code == 422
    # argv 로 들어가는 값에 줄바꿈이 섞이면 실패 원인을 로그에서 못 읽는다.
    assert client.put(
        "/api/admin/settings/llm_executable", json={"value": "claude\nrm -rf /"}, headers=headers
    ).status_code == 422


def test_overview_does_not_claim_the_connection_works(client, login_as):
    """설정만 읽는 화면이 초록불을 그리면 "설정은 됐는데 안 된다" 가 다시 생긴다."""
    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")
    payload = client.get("/api/admin/llm").json()
    assert payload["config"]["enabled"] is True
    assert payload["verified"] is False
    assert payload["verified_note"].strip()


def test_login_guide_changes_with_the_backend(client, login_as):
    """구독 명령줄 도구와 API 는 **할 일이 완전히 다르다.**"""
    csrf = login_as("system_admin")
    cli = client.get("/api/admin/llm").json()["login"]
    assert cli["backend"] == provider.BACKEND_CLI
    # 자격 증명은 로그인한 계정의 홈에 저장된다 - 서비스 계정으로 해야 한다는 사실이 핵심이다.
    assert "서비스 계정" in cli["note"]

    _save(client, csrf, "llm_backend", "api")
    api = client.get("/api/admin/llm").json()["login"]
    assert api["backend"] == provider.BACKEND_API
    assert api["steps"] != cli["steps"]


# ── 3. 연결 테스트는 웹 요청을 잡아 두지 않는다 ──────────────────────────────


def test_connection_test_is_queued_and_does_not_run_the_cli_in_the_web_request(
    client, login_as, monkeypatch
):
    """웹 요청에서 프로세스를 띄우면 그 처리 칸이 수십 초 잠긴다.

    `subprocess.run` 을 폭탄으로 바꿔 둔다 - 웹이 부르면 그 자리에서 터진다.
    """
    import subprocess

    def _boom(*args, **kwargs):  # pragma: no cover - 불리면 실패다
        raise AssertionError("웹 요청에서 CLI 를 띄웠다")

    csrf = login_as("system_admin")
    # 🔴 **먼저 켠다.** 꺼져 있으면 동기로 돌려도 프로세스를 안 띄우므로(꺼짐은 락도 안
    # 잡는다) 폭탄이 안 터진다 - 즉 이 테스트가 아무것도 확인하지 않게 된다.
    _save(client, csrf, "llm_enabled", "on")
    monkeypatch.setattr(subprocess, "run", _boom)

    response = client.post("/api/admin/llm/test", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] == "queued"
    # 왜 기다려야 하는지 화면이 말해야 한다.
    assert payload["note"].strip()
    assert payload["timeout_seconds"] == console.TEST_TIMEOUT_SECONDS

    pending = client.get(f"/api/admin/llm/test/{payload['job_id']}").json()
    assert pending["pending"] is True
    # 🔴 아직 안 끝났으면 결과가 **없다**. 초록불을 그리면 아무것도 확인하지 않은 것이다.
    assert pending["result"] is None


def test_connection_test_result_is_not_found_for_an_unknown_job(client, login_as):
    login_as("system_admin")
    assert client.get("/api/admin/llm/test/no-such-job").status_code == 404


def test_worker_reports_a_successful_connection(client, login_as, worker, fake_clock):
    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")
    job_id = client.post("/api/admin/llm/test", headers={"X-CSRF-Token": csrf}).json()["job_id"]

    backend = FakeBackend(provider.ok("알겠습니다.", provider.BACKEND_CLI))
    assert worker(backend).run_once(fake_clock.now()) is True
    assert backend.calls == 1

    result = client.get(f"/api/admin/llm/test/{job_id}").json()
    assert result["pending"] is False
    assert result["result"]["status"] == provider.STATUS_OK
    assert result["result"]["message"].strip()


def test_worker_distinguishes_not_logged_in_from_a_generic_failure(
    client, login_as, worker, fake_clock
):
    """미로그인은 다른 실패와 **구분돼야** 한다. 운영자가 할 일이 다르기 때문이다.

    두 세계를 돌려 결과가 서로 다른지 본다 - 하나만 보면 구현이 늘 같은 값을 돌려줘도
    초록불이다.
    """
    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")

    def run_with(result: provider.LlmResult) -> dict:
        job_id = client.post(
            "/api/admin/llm/test", headers={"X-CSRF-Token": csrf}
        ).json()["job_id"]
        assert worker(FakeBackend(result)).run_once(fake_clock.now()) is True
        return client.get(f"/api/admin/llm/test/{job_id}").json()["result"]

    not_logged_in = run_with(
        provider.failure(provider.STATUS_NOT_LOGGED_IN, provider.BACKEND_CLI)
    )
    missing_cli = run_with(provider.failure(provider.STATUS_MISSING_CLI, provider.BACKEND_CLI))
    failed = run_with(provider.failure(provider.STATUS_FAILED, provider.BACKEND_CLI))

    assert not_logged_in["status"] == provider.STATUS_NOT_LOGGED_IN
    assert missing_cli["status"] == provider.STATUS_MISSING_CLI
    assert failed["status"] == provider.STATUS_FAILED
    assert len({not_logged_in["message"], missing_cli["message"], failed["message"]}) == 3
    # 미로그인 안내는 "그래서 무엇을 해야 하는가" 로 끝나야 한다.
    assert "로그인" in not_logged_in["message"]


def test_disabled_ai_is_reported_as_disabled_not_as_a_failure(
    client, login_as, worker, fake_clock
):
    """꺼져 있으면 프로세스를 띄우지 않고, 그 사실을 그대로 말한다."""
    csrf = login_as("system_admin")
    job_id = client.post("/api/admin/llm/test", headers={"X-CSRF-Token": csrf}).json()["job_id"]

    backend = FakeBackend(provider.ok("불려서는 안 된다", provider.BACKEND_CLI))
    assert worker(backend).run_once(fake_clock.now()) is True
    assert backend.calls == 0

    result = client.get(f"/api/admin/llm/test/{job_id}").json()["result"]
    assert result["status"] == provider.STATUS_DISABLED
    assert "꺼져" in result["message"]


def test_connection_test_does_not_retry(client, login_as, worker, fake_clock, db):
    """로그인 안 됨은 5초 뒤에도 같은 답이다. 재시도는 워커 시간만 태운다."""
    from app.jobs.models import STATUS_FAILED, Job

    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")
    job_id = client.post("/api/admin/llm/test", headers={"X-CSRF-Token": csrf}).json()["job_id"]
    worker(FakeBackend(provider.failure(provider.STATUS_NOT_LOGGED_IN, "cli"))).run_once(
        fake_clock.now()
    )

    row = db.get(Job, job_id)
    db.refresh(row)
    assert row.status == STATUS_FAILED
    assert row.max_attempts == 1


def test_raw_tool_output_never_reaches_the_response_or_the_audit_log(
    client, login_as, worker, fake_clock, db
):
    """도구가 준 원문을 그대로 옮기지 않는다.

    경로와 계정 이름이 섞여 있고, 이 저장소가 화면에서 쓰지 않기로 한 글자도 들어 있다.
    """
    from app.audit.models import AuditLog

    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")
    job_id = client.post("/api/admin/llm/test", headers={"X-CSRF-Token": csrf}).json()["job_id"]

    leaked = "Not logged in: run /login at /home/clovirone-web/.claude"
    worker(FakeBackend(provider.LlmResult(status=provider.STATUS_NOT_LOGGED_IN,
                                          backend="cli", text=leaked))).run_once(fake_clock.now())

    body = client.get(f"/api/admin/llm/test/{job_id}").text
    assert leaked not in body
    assert "/home/clovirone-web" not in body

    rows = [r for r in db.query(AuditLog).all() if r.action == "llm.connection.test"]
    assert rows
    assert leaked not in json.dumps([r.after_json for r in rows], ensure_ascii=False)


# ── 4. 동시 실행 수가 진짜로 작동한다 ────────────────────────────────────────


def test_concurrency_setting_actually_limits_parallel_runs(tmp_path):
    """설정이 '되는 척하는 스위치' 가 아닌지 본다. 슬롯 수만큼 잡히고 그 다음은 막힌다."""
    from app.llm.service import concurrency_lock

    def take(n: int):
        locks = [
            concurrency_lock(tmp_path, timeout_seconds=30, max_concurrency=n)
            for _ in range(n + 1)
        ]
        acquired = [lock.acquire() for lock in locks]
        for lock in locks:
            lock.release()
        return acquired

    # 1개면 첫 번째만 잡힌다.
    assert take(1) == [True, False]
    # 3개면 셋까지 잡히고 넷째가 막힌다 - 값이 달라지면 동작도 달라진다.
    assert take(3) == [True, True, True, False]


def test_busy_slots_are_reported_as_busy_not_as_a_failure(
    client, login_as, worker, fake_clock, settings
):
    """슬롯이 차 있는 것은 사고가 아니라 정상적인 상태다."""
    from app.llm.service import concurrency_lock

    csrf = login_as("system_admin")
    _save(client, csrf, "llm_enabled", "on")
    held = concurrency_lock(settings.data_dir, timeout_seconds=30, max_concurrency=1)
    assert held.acquire() is True
    try:
        job_id = client.post(
            "/api/admin/llm/test", headers={"X-CSRF-Token": csrf}
        ).json()["job_id"]
        backend = FakeBackend(provider.ok("불려서는 안 된다", provider.BACKEND_CLI))
        worker(backend).run_once(fake_clock.now())
        assert backend.calls == 0
        result = client.get(f"/api/admin/llm/test/{job_id}").json()["result"]
        assert result["status"] == provider.STATUS_BUSY
    finally:
        held.release()


def test_test_timeout_is_capped_below_the_configured_timeout(client, login_as, settings):
    """설정이 600초여도 테스트는 60초에서 끊는다. 잡 큐가 반나절 잠기면 안 된다."""
    from app.jobs.handlers.llm_connection_test import build_test_service

    csrf = login_as("system_admin")
    _save(client, csrf, "llm_timeout_seconds", 600)
    service = build_test_service(client.app.state.settings)
    assert service._config.timeout_seconds == console.TEST_TIMEOUT_SECONDS
    assert provider.resolve_config(client.app.state.settings).timeout_seconds == 600
