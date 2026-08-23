"""설정 → Adapter 선택 (D-201). **모델 이름이 이 파일에 안 적힌다.**

## 읽는 순서

`Settings` 필드 → 환경변수 → 기본값. `app/llm/provider.py::resolve_config` 와 같은 순서다.
설정 객체는 테스트가 명시적으로 주입할 수 있어 결정적이고, 환경변수는 관리 화면이 생기기
전에도 운영자가 켤 수 있는 통로다. 둘 다 없으면 **꺼진 상태**가 기본이다(fail-closed).

## 왜 `build_gateway()` 는 실패하지 않는가

이 함수는 웹 부팅과 워커 부팅에서 불린다. 모델 파일이 없다고 여기서 예외를 올리면
**모델을 안 넣은 설치는 앱이 아예 안 뜬다.** 못 쓰는 상태는 `capabilities()` 가 말하고,
`/readyz` 와 `ai_cli status` 가 그것을 읽는다.

## 모델 디렉터리는 어디인가

`<data_dir>/ai/models/<모델 디렉터리 이름>`. `storage_providers` 와 **별개**다 — 모델은
사용자 데이터가 아니라 재생성 가능한 자산이고 백업 대상이 아니다(D-203 · D-204).
저장소 표에 끼워 넣지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.ai import catalog
from app.ai.gateway import contract

#: 모델 캐시의 뿌리. `data_dir` 아래 이 이름으로 선다. Stage 12 가 같은 경로를 만든다.
MODEL_DIR_NAME = "ai/models"

#: 한 번에 모델에 태우는 chunk 수. S1 실측에서 batch32 가 가장 빨랐다(D-211).
DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 128


@dataclass(frozen=True)
class AiConfig:
    """한 번 정해지면 안 바뀐다. 기본값은 전부 '꺼짐'이다."""

    enabled: bool = False
    #: 모델 파일이 사는 뿌리. 비어 있으면 `data_dir` 에서 만든다.
    model_root: str = ""
    #: `app/ai/catalog.py` 의 id 중 하나. 모르는 이름이면 `embedding_model()` 이 None 이다.
    embed_model_id: str = ""
    batch_size: int = DEFAULT_BATCH_SIZE
    #: ONNX Runtime intra-op 스레드. 0 이면 런타임 기본값(코어 수)이다.
    threads: int = 0


def _first_str(*values) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _as_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def resolve_config(settings=None, env=None) -> AiConfig:
    """`Settings` 필드 → 환경변수 → 기본값."""
    env = os.environ if env is None else env

    def field(name: str, env_key: str):
        return (getattr(settings, f"ai_{name}", None) if settings is not None else None,
                env.get(env_key))

    enabled_setting, enabled_env = field("enabled", "AI_ENABLED")
    root_setting, root_env = field("model_root", "AI_MODEL_ROOT")
    model_setting, model_env = field("embed_model", "AI_EMBED_MODEL")
    batch_setting, batch_env = field("embed_batch_size", "AI_EMBED_BATCH_SIZE")
    threads_setting, threads_env = field("embed_threads", "AI_EMBED_THREADS")

    enabled = _as_bool(enabled_setting)
    if enabled is None:
        enabled = _as_bool(enabled_env)

    root = _first_str(root_setting, root_env)
    if not root and settings is not None:
        root = str(Path(getattr(settings, "data_dir", "var")) / MODEL_DIR_NAME)

    batch = _as_int(batch_setting)
    if batch is None:
        batch = _as_int(batch_env)
    threads = _as_int(threads_setting)
    if threads is None:
        threads = _as_int(threads_env)

    return AiConfig(
        enabled=bool(enabled),
        model_root=root or "",
        embed_model_id=_first_str(model_setting, model_env) or "",
        batch_size=max(1, min(MAX_BATCH_SIZE, batch or DEFAULT_BATCH_SIZE)),
        threads=max(0, threads or 0),
    )


def model_dir(config: AiConfig, model: catalog.EmbeddingModel) -> Path:
    return Path(config.model_root) / model.dir_name


def build_embed_adapter(config: AiConfig) -> contract.EmbedAdapter | None:
    """설정 → 임베딩 Adapter 하나. 모르는 모델 이름이면 None(호출부가 '설정 안 됨'으로 접는다).

    import 를 함수 안에서 하는 이유: `registry` 만 쓰는 곳이 ONNX Runtime 경계를 함께
    끌고 오지 않게. 층을 나눈 값을 여기서 지킨다 — 그리고 그 런타임은 **없을 수 있다.**
    """
    model = catalog.embedding_model(config.embed_model_id)
    if model is None:
        return None
    from app.ai.gateway.adapters.local_embed import LocalOnnxEmbedAdapter

    return LocalOnnxEmbedAdapter(
        model=model,
        model_dir=model_dir(config, model),
        batch_size=config.batch_size,
        threads=config.threads,
    )


def build_generate_adapter(settings, *, outbound=None) -> contract.GenerateAdapter | None:
    """생성 Adapter. 지금은 `app/llm` 의 CLI/API 백엔드 하나를 감싼 것뿐이다.

    **`app/llm` 을 지우지 않는다.** 지우면 주간 리포트 요약이 멈추고, 두 벌로 두면
    프롬프트 방어가 한쪽에만 걸린다(D-202 가 지적한 바로 그 상태다).
    """
    from app.ai.gateway.adapters.claude_cli import LlmBackendAdapter
    from app.llm import provider as llm_provider

    llm_config = llm_provider.resolve_config(settings)
    if not llm_config.enabled:
        return None
    backend = llm_provider.select_backend(llm_config, outbound=outbound)
    if backend is None:
        return None
    return LlmBackendAdapter(backend=backend, config=llm_config)


def build_gateway(settings=None, *, outbound=None, env=None) -> contract.Gateway:
    """부팅 지점에서 한 번 부른다. **어떤 이유로도 예외를 올리지 않는다.**"""
    config = resolve_config(settings, env=env)
    if not config.enabled:
        return contract.Gateway(enabled=False)
    try:
        embed_adapter = build_embed_adapter(config)
    except Exception:  # noqa: BLE001 - 어댑터를 못 만드는 것이 기동 실패가 되면 안 된다
        _logger().exception("임베딩 어댑터를 만들지 못했다")
        embed_adapter = None
    try:
        generate_adapter = build_generate_adapter(settings, outbound=outbound)
    except Exception:  # noqa: BLE001
        _logger().exception("생성 어댑터를 만들지 못했다")
        generate_adapter = None
    return contract.Gateway(
        enabled=True, embed_adapter=embed_adapter, generate_adapter=generate_adapter
    )


def _logger():
    import logging

    return logging.getLogger("app.ai.gateway")
