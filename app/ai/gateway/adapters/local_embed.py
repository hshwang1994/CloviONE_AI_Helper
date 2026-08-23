"""임베딩 Adapter — **CPU · Local · ONNX Runtime** (D-200 · D-211).

GPU 를 전제하지 않는다. 서버는 VMware VM 8 vCPU 이고 지금도 앞으로도 GPU 가 없다.
torch 를 안 쓰는 이유도 같다 — CPU 추론에 그 무게가 필요 없고, 폐쇄망 설치에서
받아야 하는 wheel 만 커진다.

## 이 파일이 지키는 것 넷

1. **런타임이 없어도 import 가 된다.** `onnxruntime` · `tokenizers` 는
   `requirements-ai.txt` 에 있고 Installer Stage 12 가 깐다. 안 깐 설치에서 이 모듈을
   못 읽으면 **웹과 워커가 통째로 안 뜬다.** 그래서 무거운 import 는 전부 함수 안이다.
2. **모델이 없는 것과 런타임이 없는 것을 구별한다.** 「안 깔림」과 「안 넣음」은 운영자가
   해야 할 일이 다르다. 상태 어휘가 둘로 나뉘어 있다(`runtime_missing`·`model_missing`).
3. **접두사를 붙인다.** e5 계열은 질의에 `query: `, 본문에 `passage: ` 를 요구한다.
   안 붙여도 **오류가 하나도 안 나고** 품질만 조용히 떨어진다 — 그래서 카탈로그가
   접두사를 계약으로 들고 있고 이 파일이 그것만 읽는다.
4. **세션을 한 번만 만든다.** ONNX 세션 로드가 S1 실측에서 2.3초다. 호출마다 만들면
   색인 한 판이 그 시간의 배수가 된다.

## 왜 배치로 도는가

S1 실측(D-211): batch8 112 docs/s · batch16 114 · batch32 **120**. 큰 차이는 아니지만
같은 값이면 큰 쪽을 쓴다. 상한은 `registry.MAX_BATCH_SIZE` 가 강제한다 — 무한히 키우면
한 배치의 RSS 가 그대로 는다(실측 최대 1.5 GB).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.ai import catalog, pooling
from app.ai.gateway import contract

logger = logging.getLogger("app.ai.embed")

#: ONNX 모델이 받는 입력 이름. e5 계열은 셋을 다 받지만 `token_type_ids` 가 없는
#: export 도 있다 — 세션이 실제로 요구하는 것만 넣는다.
_INPUT_IDS = "input_ids"
_ATTENTION_MASK = "attention_mask"
_TOKEN_TYPE_IDS = "token_type_ids"


class LocalOnnxEmbedAdapter(contract.EmbedAdapter):
    """모델 디렉터리 하나 = 임베딩 능력 하나."""

    def __init__(
        self,
        *,
        model: catalog.EmbeddingModel,
        model_dir: Path,
        batch_size: int = 32,
        threads: int = 0,
    ) -> None:
        self._model = model
        self._dir = Path(model_dir)
        self._batch_size = max(1, int(batch_size))
        self._threads = max(0, int(threads))
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._session_inputs: tuple[str, ...] = ()
        self.name = "local_onnx"
        self.model = model.model_id
        self.dim = model.dim

    # ── 능력 ─────────────────────────────────────────────────────────────────

    def missing_files(self) -> tuple[str, ...]:
        """모델 디렉터리에서 **없는 파일**만. 있으면 빈 튜플이다.

        「디렉터리가 있다」로 판정하지 않는다 — 받다 만 디렉터리가 정확히 그 모양이고,
        그때는 세션을 만들다 죽는다. 무엇이 없는지를 운영자에게 그대로 말한다.
        """
        return tuple(
            name for name in self._model.required_files if not (self._dir / name).is_file()
        )

    def runtime_available(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
        except Exception:  # noqa: BLE001 - import 실패는 종류를 안 가린다
            return False
        return True

    def capability(self) -> contract.Capability:
        if not self.runtime_available():
            return contract.unavailable(
                contract.CAP_EMBED, contract.STATUS_RUNTIME_MISSING, model=self.model,
                detail="설치 명령의 AI 단계를 다시 실행하십시오.",
            )
        missing = self.missing_files()
        if missing:
            return contract.unavailable(
                contract.CAP_EMBED, contract.STATUS_MODEL_MISSING, model=self.model,
                detail=f"모델 파일 {len(missing)}개가 없습니다.",
            )
        return contract.available(contract.CAP_EMBED, model=self.model)

    # ── 임베딩 ───────────────────────────────────────────────────────────────

    def embed(self, texts, *, kind: str = catalog.KIND_PASSAGE) -> contract.EmbedResult:
        cap = self.capability()
        if not cap.available:
            return contract.EmbedResult(
                status=cap.status, model=self.model, detail=cap.detail
            )
        prefix = self._model.prefix_for(kind)
        prepared = [f"{prefix}{_as_text(t)}" for t in texts]
        try:
            vectors = self._run_batches(prepared)
        except Exception:  # noqa: BLE001 - 색인 루프는 임베딩 하나 때문에 죽지 않는다
            logger.exception("임베딩 실행이 실패했다 model=%s", self.model)
            return contract.EmbedResult(status=contract.STATUS_FAILED, model=self.model)
        if any(len(v) != self.dim for v in vectors):
            # 차원이 다르면 저장 자체가 막힌다(`vector(384)`). 그 전에 여기서 말한다 —
            # 모델을 바꿔 놓고 마이그레이션을 안 한 상태가 정확히 이 모양이다.
            logger.error("임베딩 차원이 계약과 다르다 기대=%d model=%s", self.dim, self.model)
            return contract.EmbedResult(status=contract.STATUS_FAILED, model=self.model)
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim, vectors=vectors
        )

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _run_batches(self, prepared: list[str]) -> tuple[tuple[float, ...], ...]:
        session, tokenizer = self._ensure_loaded()
        out: list[tuple[float, ...]] = []
        for start in range(0, len(prepared), self._batch_size):
            chunk = prepared[start:start + self._batch_size]
            out.extend(self._run_one_batch(session, tokenizer, chunk))
        return tuple(out)

    def _run_one_batch(self, session, tokenizer, chunk: list[str]):
        encoded = tokenizer.encode_batch(chunk)
        ids = [e.ids for e in encoded]
        mask = [e.attention_mask for e in encoded]
        feed = {_INPUT_IDS: ids, _ATTENTION_MASK: mask}
        if _TOKEN_TYPE_IDS in self._session_inputs:
            feed[_TOKEN_TYPE_IDS] = [[0] * len(row) for row in ids]
        import numpy as np

        feed = {name: np.asarray(value, dtype=np.int64) for name, value in feed.items()}
        outputs = session.run(None, feed)
        # 첫 출력이 last_hidden_state 다. 모델에 따라 pooler_output 이 두 번째로 오지만
        # **그것을 안 쓴다** — e5 는 mean pooling 을 전제로 학습됐고, pooler 를 쓰면
        # 같은 모델에서 다른 공간의 벡터가 나온다.
        hidden = outputs[0]
        return pooling.mean_pool_l2(hidden, mask)

    def _ensure_loaded(self):
        """세션과 토크나이저를 **한 번만** 만든다. 여러 스레드가 동시에 와도 하나다."""
        if self._session is not None and self._tokenizer is not None:
            return self._session, self._tokenizer
        with self._lock:
            if self._session is None or self._tokenizer is None:
                self._session, self._tokenizer = self._load()
                self._session_inputs = tuple(i.name for i in self._session.get_inputs())
        return self._session, self._tokenizer

    def _load(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        if self._threads:
            options.intra_op_num_threads = self._threads
        session = ort.InferenceSession(
            str(self._dir / "onnx" / "model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        tokenizer = Tokenizer.from_file(str(self._dir / "tokenizer.json"))
        # 자르지 않으면 512 토큰이 넘는 chunk 에서 모델이 그대로 죽는다. 패딩을 켜야
        # 배치 안의 줄 길이가 같아진다.
        tokenizer.enable_truncation(max_length=self._model.max_tokens)
        tokenizer.enable_padding()
        logger.info("임베딩 모델을 열었다 model=%s dir=%s", self.model, self._dir)
        return session, tokenizer


def _as_text(value) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))
