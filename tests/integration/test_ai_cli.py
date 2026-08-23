"""AI CLI — Installer Stage 12 가 부르는 그 코드다 (S9).

## 🔴 종료코드가 계약이다

Stage 11 이 S8 에서 채워진 모양 그대로다: 제품 CLI 를 부르고, **종료코드를 계약으로
삼고**, 셸에서 판정을 다시 하지 않는다. 셸이 모델 디렉터리에 `ls` 를 거는 순간 판정이
두 벌이 되고, 그 둘은 언젠가 갈린다.

  * **0** — 지금 이 설치가 의도한 상태다. AI 를 끄고 설치했으면 꺼진 것도 0 이다.
  * **1** — 켜기로 해 놓고 못 쓰는 상태다.

「AI 를 안 깔았다」와 「깔려고 했는데 깨졌다」는 다른 사실이고, 설치 로그에서 그 둘이
같아 보이면 안 된다.
"""

from __future__ import annotations

import json

import pytest

from app.ai import catalog
from app.ai.gateway import contract
from app.cli import ai_cli

pytestmark = pytest.mark.integration


class _Args:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _run(db, settings, command, **kwargs) -> int:
    return command(db, settings, _Args(**kwargs))


# ── status ───────────────────────────────────────────────────────────────────


def test_status_is_zero_when_ai_is_deliberately_off(db, settings, capsys):
    """끄고 설치한 것은 정상 상태다. 설치 로그가 그 사실을 그대로 적는다."""
    assert _run(db, settings, ai_cli.cmd_status) == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["enabled"] is False
    assert "꺼져" in out.err


def test_status_is_one_when_ai_is_on_but_the_model_is_missing(db, settings, capsys):
    """켜 놓고 못 쓰는 상태는 설치가 멈춰야 하는 상태다."""
    settings.ai_enabled = "true"
    assert _run(db, settings, ai_cli.cmd_status) == 1
    out = capsys.readouterr()
    report = json.loads(out.out)
    embed = report["capabilities"][contract.CAP_EMBED]
    assert embed["available"] is False
    # 「런타임이 없다」와 「모델이 없다」를 구별해서 말한다.
    assert embed["status"] in (
        contract.STATUS_RUNTIME_MISSING, contract.STATUS_MODEL_MISSING
    )


def test_status_reports_the_index_numbers(db, settings, capsys):
    """색인이 밀린 건수와 벡터가 없는 chunk 수가 보여야 한다 — 조용히 낡는 것이
    이 축의 가장 나쁜 실패다."""
    _run(db, settings, ai_cli.cmd_status)
    report = json.loads(capsys.readouterr().out)
    assert report["index"]["chunks"] == 0
    assert report["index"]["documents"] == {"pending": 0, "ok": 0, "failed": 0}
    assert report["vector_dim"] == catalog.VECTOR_DIM
    assert report["parser_version"] == catalog.PARSER_VERSION


# ── selftest ─────────────────────────────────────────────────────────────────


def test_selftest_fails_when_embedding_is_not_available(db, settings, capsys):
    settings.ai_enabled = "true"
    assert _run(db, settings, ai_cli.cmd_selftest) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_selftest_checks_the_vector_is_unit_length(db, settings, monkeypatch, capsys):
    """🔴 **있다 ≠ 된다.** 그리고 정규화가 빠진 벡터는 오류를 안 내고 검색 순서만
    조용히 틀어 놓는다 — 그래서 길이까지 본다."""

    class BadEmbed(contract.EmbedAdapter):
        name = "bad"
        model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        dim = catalog.VECTOR_DIM

        def capability(self):
            return contract.available(contract.CAP_EMBED, model=self.model)

        def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
            # 정규화를 빠뜨린 벡터. 차원도 맞고 오류도 없다.
            return contract.EmbedResult(
                status=contract.STATUS_OK, model=self.model, dim=self.dim,
                vectors=tuple(tuple(9.0 for _ in range(self.dim)) for _ in texts),
            )

    monkeypatch.setattr(
        ai_cli, "_gateway",
        lambda _s: contract.Gateway(enabled=True, embed_adapter=BadEmbed()),
    )
    assert _run(db, settings, ai_cli.cmd_selftest) == 1
    report = json.loads(capsys.readouterr().out)
    assert any("길이 1" in p for p in report["problems"])


def test_selftest_passes_on_a_healthy_adapter(db, settings, monkeypatch, capsys):
    """자기검증이 **항상 실패**하면 위 시험들이 아무것도 확인하지 않는다."""
    import math

    class GoodEmbed(contract.EmbedAdapter):
        name = "good"
        model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        dim = catalog.VECTOR_DIM

        def capability(self):
            return contract.available(contract.CAP_EMBED, model=self.model)

        def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
            unit = 1.0 / math.sqrt(self.dim)
            return contract.EmbedResult(
                status=contract.STATUS_OK, model=self.model, dim=self.dim,
                vectors=tuple(tuple(unit for _ in range(self.dim)) for _ in texts),
            )

    monkeypatch.setattr(
        ai_cli, "_gateway",
        lambda _s: contract.Gateway(enabled=True, embed_adapter=GoodEmbed()),
    )
    assert _run(db, settings, ai_cli.cmd_selftest) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and report["problems"] == []
    # 한국어와 영어를 함께 태운다 — 다국어 모델이 한쪽만 되는 상태를 「된다」로 안 읽는다.
    assert report["count"] == len(ai_cli.SELFTEST_TEXTS) == 2


# ── install-model ────────────────────────────────────────────────────────────


def _fake_model_dir(root, model=catalog.E5_SMALL):
    directory = root / model.dir_name
    for name in model.required_files:
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * 8)
    return directory


def test_install_model_copies_the_required_files(db, settings, tmp_path, capsys):
    settings.ai_model_root = str(tmp_path / "cache")
    source = _fake_model_dir(tmp_path / "src")
    assert _run(db, settings, ai_cli.cmd_install_model, source=str(source)) == 0
    installed = tmp_path / "cache" / catalog.E5_SMALL.dir_name
    for name in catalog.E5_SMALL.required_files:
        assert (installed / name).is_file()
    assert "AI_MODEL_OK" in capsys.readouterr().out


def test_install_model_accepts_the_parent_directory_too(db, settings, tmp_path):
    """어느 쪽을 줘야 하는지 외우게 만드는 것이 설치를 어렵게 하는 흔한 이유다."""
    settings.ai_model_root = str(tmp_path / "cache")
    _fake_model_dir(tmp_path / "src")
    assert _run(db, settings, ai_cli.cmd_install_model, source=str(tmp_path / "src")) == 0


def test_install_model_refuses_a_half_downloaded_source(db, settings, tmp_path, capsys):
    """받다 만 디렉터리를 그대로 깔면 세션을 만들다 죽고, 증상은 「색인 레인이 조용히
    재시작만 반복한다」로만 보인다."""
    settings.ai_model_root = str(tmp_path / "cache")
    source = tmp_path / "src" / catalog.E5_SMALL.dir_name
    (source / "onnx").mkdir(parents=True)
    (source / "onnx" / "model.onnx").write_bytes(b"x")
    assert _run(db, settings, ai_cli.cmd_install_model, source=str(source)) == 1
    assert "없습니다" in capsys.readouterr().err


def test_install_model_refuses_an_unknown_model(db, settings, tmp_path, capsys):
    settings.ai_model_root = str(tmp_path / "cache")
    settings.ai_embed_model = "없는/모델"
    assert _run(db, settings, ai_cli.cmd_install_model, source=str(tmp_path)) == 1
    assert "모르는" in capsys.readouterr().err


# ── reindex ──────────────────────────────────────────────────────────────────


def test_reindex_queues_but_does_not_index(db, settings, capsys):
    """운영자가 실행한 셸에서 몇 분짜리 임베딩이 돌면 안 된다 — Ctrl-C 로 끊으면
    절반만 된 상태가 남는다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="공간", slug="s", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    db.add(Document(space_id=space.id, title="문서"))
    db.flush()
    assert _run(db, settings, ai_cli.cmd_reindex) == 0
    assert "AI_REINDEX_QUEUED documents=1" in capsys.readouterr().out
    from app.ai.index.service import index_health

    assert index_health(db)["documents"]["pending"] == 1
    assert index_health(db)["chunks"] == 0


# ── 파서 ─────────────────────────────────────────────────────────────────────


def test_the_parser_knows_every_subcommand_the_installer_calls():
    """설치 스크립트가 부르는 이름이 바뀌면 Stage 12 가 그 자리에서 죽는다."""
    parser = ai_cli.build_parser()
    for argv in (["status"], ["selftest"], ["reindex"], ["install-model", "--from", "x"]):
        assert parser.parse_args(argv).func is not None
