#!/usr/bin/env bash
# S1 / P-03 (C) — CPU 임베딩 벤치 환경. torch 없이 ONNX Runtime 만 쓴다 (D-200 · INSTALLATION §5 Stage 12).
set -uo pipefail
BASE="$HOME/s1bench"
mkdir -p "$BASE"
cd "$BASE" || exit 1

echo "== venv =="
[ -d venv ] || python3 -m venv venv
. venv/bin/activate
pip install -q --upgrade pip
pip install -q onnxruntime==1.20.1 tokenizers numpy huggingface_hub || { echo "PIP_FAIL"; exit 1; }
python -c "import onnxruntime, numpy, tokenizers; print('ORT', onnxruntime.__version__, '| providers', onnxruntime.get_available_providers())"

echo "== download =="
python - <<'PY'
import os
from huggingface_hub import hf_hub_download

BASE = os.path.expanduser("~/s1bench/models")
WANT = {
    "intfloat/multilingual-e5-small": ["onnx/model.onnx", "tokenizer.json", "config.json"],
    "intfloat/multilingual-e5-base": ["onnx/model.onnx", "tokenizer.json", "config.json"],
    "BAAI/bge-m3": ["onnx/model.onnx", "onnx/model.onnx_data", "tokenizer.json", "config.json"],
}
for repo, files in WANT.items():
    for f in files:
        try:
            p = hf_hub_download(repo_id=repo, filename=f,
                                local_dir=os.path.join(BASE, repo.replace("/", "__")))
            print("OK  %-42s %-26s %.1f MB" % (repo, f, os.path.getsize(p) / 1e6))
        except Exception as exc:
            print("ERR %-42s %-26s %s" % (repo, f, exc))
PY
echo "MODELS_READY"
du -sh "$BASE/models" 2>/dev/null
