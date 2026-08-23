"""S9 이 만든 것이 **실제 실행 경로에 붙어 있는가** (회귀).

새 함수와 새 표를 만드는 것과 그것이 실제로 불리는 것은 다르다. 이 저장소가 이미
여러 번 겪은 패턴이라(CLAUDE.md §5) 배선을 따로 지킨다:

  * 색인 레인이 진입점의 선택지에 있고, 유닛이 배포본에 있고, 설치 목록에 있는가
  * `/readyz` 가 「켜 놓고 못 쓰는 AI」를 unready 로 말하는가 — 그 상태로 뜨면
    색인이 조용히 벡터 없이 쌓인다
  * 대시보드가 AI 축을 보여 주는가
  * 🔴 **모델 이름이 어디에도 안 박혀 있는가** (P-19)
"""

from __future__ import annotations

import pathlib

import pytest

from app.ai import catalog
from app.core import product
from app.jobs import lanes
from app.llm import provider

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── 색인 레인 배선 ───────────────────────────────────────────────────────────


def test_the_index_lane_is_a_choice_of_the_worker_entry_point():
    """진입점이 `--lane index` 를 모르면 유닛이 그 자리에서 죽는다."""
    import argparse

    from app import worker_main

    with pytest.raises(SystemExit):
        worker_main.main(["--lane", "없는레인"])
    parser = argparse.ArgumentParser()
    # 진입점의 선택지를 직접 읽는다 — 유닛의 ExecStart 와 같은 값이어야 한다.
    source = (ROOT / "app" / "worker_main.py").read_text(encoding="utf-8")
    assert "LANE_INDEX," in source
    assert "run_index_loop(session_factory, clock, stop_event, settings)" in source
    assert parser is not None


def test_the_index_unit_exists_and_starts_that_lane():
    unit = ROOT / "deploy" / "systemd" / product.INDEX_UNIT
    assert unit.is_file(), "색인 레인이 소스에 있는데 systemd 유닛이 없다"
    text = unit.read_text(encoding="utf-8")
    assert "--lane=index" in text
    assert "After=network-online.target postgresql.service" in text
    # 재부팅 뒤 스스로 복귀한다.
    assert "WantedBy=multi-user.target" in text


def test_the_index_unit_does_not_deny_write_execute_memory():
    """다른 넷과 다른 유일한 자리다. ONNX Runtime 은 CPU 커널을 실행 시점에 만들 수
    있고, 그때 `MemoryDenyWriteExecute` 가 켜져 있으면 프로세스가 SIGSEGV 로 죽는다 —
    증상은 「색인 레인이 조용히 재시작만 반복한다」로만 보인다."""
    text = (ROOT / "deploy" / "systemd" / product.INDEX_UNIT).read_text(encoding="utf-8")
    assert "\nMemoryDenyWriteExecute=true" not in text
    # 나머지 하드닝은 그대로다 — 하나를 껐다고 전부 느슨해지지 않는다.
    for option in ("NoNewPrivileges=true", "ProtectSystem=strict", "PrivateTmp=true"):
        assert option in text


def test_the_installer_installs_and_enables_the_index_unit():
    text = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert 'INDEX_UNIT="$SLUG-index.service"' in text
    assert '"$INDEX_UNIT"' in text
    assert product.INDEX_UNIT in product.ALL_UNITS
    # 기본이 켜짐이라 재부팅 뒤 **떠 있어야** 한다.
    assert product.INDEX_UNIT in product.ALWAYS_ACTIVE_UNITS


def test_the_lane_has_its_own_lease_and_liveness_name():
    """리스 이름이 겹치면 색인이 도는 동안 배치 워커가 멈춘다. liveness 이름이 겹치면
    한쪽이 죽어도 대시보드가 계속 «정상» 이라고 말한다."""
    names = {
        lanes.lock_filename(lane)
        for lane in (lanes.LANE_BATCH, lanes.LANE_CONVERSATIONAL, lanes.LANE_SCHEDULER,
                     lanes.LANE_INDEX)
    }
    assert len(names) == 4
    components = {
        lanes.liveness_component(lane)
        for lane in (lanes.LANE_BATCH, lanes.LANE_CONVERSATIONAL, lanes.LANE_SCHEDULER,
                     lanes.LANE_INDEX)
    }
    assert len(components) == 4


def test_the_index_lane_claims_no_jobs():
    """할 일 목록이 이미 `ai_index_state` 표다. 잡 큐를 하나 더 두면 「큐에서는
    사라졌는데 결과가 없는」 상태가 만들어지고, 그 상태는 아무 화면에도 안 나온다."""
    source = (ROOT / "app" / "worker_main.py").read_text(encoding="utf-8")
    body = source[source.index("def run_index_loop("):source.index("def build_batch_worker(")]
    assert "Worker(" not in body
    assert "claim_next" not in body


# ── /readyz ──────────────────────────────────────────────────────────────────


def test_readyz_is_ready_when_ai_is_off(client):
    """끄고 설치한 것은 정상이다. 여기서 막으면 AI 를 안 쓰는 설치가 영영 안 뜬다."""
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_is_unready_when_ai_is_on_but_unusable(client, app):
    """🔴 그 상태로 뜨면 색인이 조용히 벡터 없이 쌓인다."""
    app.state.settings.ai_enabled = "true"
    try:
        response = client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unready"
        assert body["reason"].startswith("ai_")
    finally:
        app.state.settings.ai_enabled = ""


def test_readyz_stays_ready_when_only_generation_is_missing(client, app):
    """생성 Provider 가 없어도 검색·Retrieval 은 그대로 돈다(D-201). 그것을 unready 로
    읽으면 「요약이 안 된다」가 「서비스가 죽었다」가 된다."""
    from app.ai.gateway import contract

    def fake_gateway(_settings=None, **_kwargs):
        class _Embed(contract.EmbedAdapter):
            name = "fake"
            model = catalog.DEFAULT_EMBEDDING_MODEL_ID
            dim = catalog.VECTOR_DIM

            def capability(self):
                return contract.available(contract.CAP_EMBED, model=self.model)

        return contract.Gateway(enabled=True, embed_adapter=_Embed(), generate_adapter=None)

    from app.ai.gateway import registry

    original = registry.build_gateway
    registry.build_gateway = fake_gateway
    app.state.settings.ai_enabled = "true"
    try:
        assert client.get("/readyz").status_code == 200
    finally:
        registry.build_gateway = original
        app.state.settings.ai_enabled = ""


# ── 대시보드 ─────────────────────────────────────────────────────────────────


def test_the_dashboard_shows_the_ai_axis(db, settings):
    from app.core.models_base import utcnow
    from app.health.service import build_dashboard

    payload = build_dashboard(db, settings, utcnow())
    assert "ai" in payload
    assert payload["ai"]["enabled"] is False
    assert "index" in payload["ai"]


# ── 🔴 P-19: 모델 이름이 어디에도 안 박혀 있다 ─────────────────────────────


def test_the_product_does_not_choose_a_generation_model_for_you():
    """예전에는 `DEFAULT_MODEL = "sonnet"` 이 있었다. 그 한 줄이 「설정에서 모델을
    지운다」와 「그 모델을 쓴다」를 같은 상태로 만들었다."""
    assert provider.DEFAULT_MODEL == ""
    assert provider.resolve_config(None, env={"LLM_ENABLED": "true"}).model == ""


def test_an_unconfigured_model_is_refused_not_defaulted():
    """빈 문자열을 `--model` 에 넘기면 CLI 가 자기 기본 모델로 돈다. 그건 우리가 고른
    모델이 아니고, 로그에도 「무엇으로 돌았는지」가 안 남는다."""
    from app.llm import cli_backend

    config = provider.LlmConfig(enabled=True, model="")
    with pytest.raises(cli_backend.ModelNotConfiguredError):
        cli_backend.build_argv(config, system_prompt="시스템")

    backend = cli_backend.ClaudeCliBackend(config)
    result = backend.run(system="시스템", user="사용자")
    assert result.status == provider.STATUS_UNCONFIGURED


def test_the_api_backend_refuses_an_unconfigured_model():
    """API 는 `model` 이 필수라 빈 값이면 400 이 오는데, 그 400 은 「설정 안 됨」이
    아니라 「실패」로 읽혀 원인이 가려진다."""
    from app.llm import api_backend

    class _Outbound:
        def request(self, *args, **kwargs):  # pragma: no cover - 여기 오면 안 된다
            raise AssertionError("모델 없이 바깥 호출이 나갔다")

    config = provider.LlmConfig(
        enabled=True, backend=provider.BACKEND_API, model="",
        api_model="", api_secret_ref="ref",
    )
    backend = api_backend.AnthropicApiBackend(config, outbound=_Outbound())
    assert backend.run(system="시스템", user="사용자").status == provider.STATUS_UNCONFIGURED


def test_the_runner_that_had_a_default_model_is_gone():
    """D-254 가 지우게 한 하드코딩 둘 중 하나는 러너에 있었다. S11 이 그 러너를 통째로
    걷어냈으니, 이제 지킬 것은 「기본 모델이 없다」가 아니라 **「그 파일이 없다」**다."""
    assert not (ROOT / "runner").exists(), "지운 러너 소스가 되살아났다"


def test_the_embedding_model_lives_only_in_the_catalog():
    """임베딩 모델은 성격이 다르다 — 차원이 DB 컬럼이라 아무 이름이나 받을 수 없다.
    그래서 **제품이 아는 목록에서 고르는** 자리이고, 그 목록은 하나뿐이다."""
    assert catalog.embedding_model("없는/모델") is None
    assert set(catalog.EMBEDDING_MODELS) == {catalog.DEFAULT_EMBEDDING_MODEL_ID}
    # 정적 검사가 이 파일 하나만 예외로 둔다.
    checker = (ROOT / "scripts" / "check_domain_single_source.py").read_text(encoding="utf-8")
    assert '"app/ai/catalog.py"' in checker
