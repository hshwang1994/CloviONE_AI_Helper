"""임베딩 모델 받기 (계획 3.16, D-522).

받는 것은 설치 스크립트이고, 제품 CLI 는 받을 목록을 적고 받은 파일을 고정 값과 맞춰 본다.

못박는 성질:
1. 받을 곳은 커밋 해시로 고정한 revision 이다. `main` 을 받으면 모델 저장소가 바뀐 날 다른 모델이 깔린다.
2. 파일마다 크기와 sha256 이 있고, 카탈로그의 필수 파일 전부에 그 값이 있다.
3. `install-model --verify` 는 한 바이트라도 다른 파일을 캐시에 놓지 않는다. 맞는 파일은 놓는다.
4. 모델 호스트는 제품의 바깥 허용 목록에 없다. 제품은 모델을 받으러 나가지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from app.ai import catalog
from app.cli import ai_cli

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_the_download_is_pinned_to_a_commit_and_every_required_file_has_a_checksum():
    model = catalog.embedding_model(None)
    assert model.source is not None
    assert re.fullmatch(r"[0-9a-f]{40}", model.source.revision), "revision 이 커밋 해시가 아니다"
    pinned = {item.path: item for item in model.source.files}
    assert set(pinned) == set(model.required_files)
    for item in pinned.values():
        assert re.fullmatch(r"[0-9a-f]{64}", item.sha256) and item.size > 0
        assert model.source.url_for(item).startswith("https://")
        assert f"/resolve/{model.source.revision}/" in model.source.url_for(item)


def test_the_plan_lists_url_checksum_size_and_path(capsys):
    rc = ai_cli.cmd_download_plan(None, _settings(), SimpleNamespace())
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    model = catalog.embedding_model(None)
    assert len(lines) == len(model.required_files)
    for line in lines:
        url, sha, size, rel = line.split(" ")
        assert url.endswith("/" + rel) and len(sha) == 64 and int(size) > 0


def _settings(tmp_path: pathlib.Path | None = None):
    from app.core.config import Settings

    root = str(tmp_path / "models") if tmp_path else ""
    return Settings(ai_model_root=root, ai_embed_model="")


def _fake_model_files(source: pathlib.Path) -> dict[str, bytes]:
    blobs = {"onnx/model.onnx": b"onnx-bytes", "tokenizer.json": b"{}", "config.json": b'{"x": 1}'}
    for rel, blob in blobs.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(blob)
    return blobs


def _pin(monkeypatch, blobs: dict[str, bytes]):
    model = catalog.embedding_model(None)
    files = tuple(catalog.ModelFile(rel, len(blob), hashlib.sha256(blob).hexdigest()) for rel, blob in blobs.items())
    pinned = catalog.ModelSource(base_url=model.source.base_url, revision=model.source.revision, files=files)
    patched = catalog.EmbeddingModel(**{**model.__dict__, "source": pinned})
    monkeypatch.setitem(catalog.EMBEDDING_MODELS, model.model_id, patched)
    return patched


def test_verify_refuses_a_file_that_differs_by_one_byte(tmp_path, monkeypatch, capsys):
    source = tmp_path / "download"
    blobs = _fake_model_files(source)
    model = _pin(monkeypatch, blobs)
    (source / "tokenizer.json").write_bytes(b"[]")  # 같은 크기, 다른 내용
    args = SimpleNamespace(source=str(source), verify=True)
    assert ai_cli.cmd_install_model(None, _settings(tmp_path), args) == 1
    assert "tokenizer.json" in capsys.readouterr().err
    assert not (tmp_path / "models" / model.dir_name / "tokenizer.json").exists(), "틀린 파일이 캐시에 놓였다"


def test_verify_accepts_matching_files(tmp_path, monkeypatch):
    source = tmp_path / "download"
    blobs = _fake_model_files(source)
    model = _pin(monkeypatch, blobs)
    args = SimpleNamespace(source=str(source), verify=True)
    assert ai_cli.cmd_install_model(None, _settings(tmp_path), args) == 0
    assert (tmp_path / "models" / model.dir_name / "onnx" / "model.onnx").read_bytes() == blobs["onnx/model.onnx"]


def test_the_model_host_is_not_in_the_runtime_allowlist():
    hosts = json.loads((ROOT / "config" / "allowed-services.json").read_text(encoding="utf-8"))["hosts"]
    model_host = catalog.embedding_model(None).source.base_url.split("/")[2]
    assert not any(h.startswith(model_host) for h in hosts), "제품이 모델 호스트로 나갈 수 있다"
