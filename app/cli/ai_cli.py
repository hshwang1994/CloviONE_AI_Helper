"""AI CLI — Installer Stage 12 와 운영자가 같은 코드를 부른다 (S9).

    python -m app.cli.ai_cli status         # 지금 상태를 JSON 으로 낸다
    python -m app.cli.ai_cli install-model  # 모델 파일을 캐시 자리에 놓는다
    python -m app.cli.ai_cli selftest       # 실제로 벡터를 하나 만들어 본다
    python -m app.cli.ai_cli reindex        # 전 문서를 다시 색인하도록 표시한다

Stage 11 이 S8 에서 채워진 모양 그대로다: **제품 CLI 를 부르고, 종료코드를 계약으로
삼고, 셸에서 판정을 다시 하지 않는다.** 셸이 모델 디렉터리에 `ls` 를 걸어 판정하는
순간 판정이 두 벌이 되고, 그 둘은 언젠가 갈린다.

## `status` 의 종료코드가 계약이다

  * **0** — 지금 이 설치가 의도한 상태다. AI 를 끄고 설치했으면 꺼진 것도 0 이다.
  * **1** — 켜기로 해 놓고 못 쓰는 상태다. 런타임이 없거나 모델 파일이 없다.

「AI 를 안 깔았다」와 「깔려고 했는데 깨졌다」는 다른 사실이고, 설치 로그에서 그 둘이
같아 보이면 안 된다.

## `selftest` 가 따로 있는 이유

`status` 는 **파일이 있는가**를 본다. 그것은 「모델이 돈다」와 다르다 — 받다 만
`model.onnx` 는 크기도 있고 이름도 맞는데 세션을 만들다 죽는다. `selftest` 는 실제로
문장 하나를 벡터로 만들고 그 벡터가 **길이 1 인지까지** 본다(D-211 의 계약).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai import catalog, pooling
from app.ai.gateway import contract, registry
from app.ai.index import service as index_service
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.errors import AppError

# 콘솔이 cp949 면 한글에서 죽는다. 결과를 못 읽는 실패는 실패보다 나쁘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: 자기검증에 쓰는 문장. 한국어와 영어를 함께 넣는다 — 다국어 모델이 한쪽만 되는
#: 상태를 「된다」로 읽지 않게.
SELFTEST_TEXTS = ("사내 규정 문서를 찾습니다.", "quarterly planning document")


def _gateway(settings: Settings) -> contract.Gateway:
    return registry.build_gateway(settings)


def _snapshot(settings: Settings) -> dict:
    config = registry.resolve_config(settings)
    model = catalog.embedding_model(config.embed_model_id)
    gateway = _gateway(settings)
    caps = gateway.capabilities()
    return {
        "enabled": config.enabled,
        "model_root": config.model_root,
        "model_dir": str(registry.model_dir(config, model)) if model else "",
        "capabilities": caps.as_dict(),
        "parser_version": catalog.PARSER_VERSION,
        "embedding_version": catalog.EMBEDDING_VERSION,
        "vector_dim": catalog.VECTOR_DIM,
    }


def cmd_status(db: Session, settings: Settings, args) -> int:
    report = _snapshot(settings)
    try:
        report["index"] = index_service.index_health(db)
    except Exception as exc:  # noqa: BLE001 - 표가 아직 없는 설치도 있다
        # 「못 셌다」를 0 으로 적지 않는다. 0 은 「없다」이고 그 둘은 다른 사실이다.
        report["index"] = {"error": type(exc).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if not report["enabled"]:
        # 끄고 설치한 것은 정상 상태다. 설치 로그가 그 사실을 그대로 적는다.
        print("AI 가 꺼져 있습니다.", file=sys.stderr)
        return 0
    embed = report["capabilities"][contract.CAP_EMBED]
    if not embed["available"]:
        print(f"임베딩을 쓸 수 없습니다: {embed['notice']}", file=sys.stderr)
        return 1
    return 0


def cmd_selftest(db: Session, settings: Settings, args) -> int:
    """벡터를 실제로 만들어 본다. **있다 ≠ 된다.**"""
    gateway = _gateway(settings)
    cap = gateway.capabilities().embed
    if not cap.available:
        print(json.dumps({"ok": False, "status": cap.status}, ensure_ascii=False))
        print(f"임베딩을 쓸 수 없습니다: {cap.notice}", file=sys.stderr)
        return 1
    result = gateway.embed(list(SELFTEST_TEXTS), kind=catalog.KIND_PASSAGE)
    problems = []
    if not result.ok:
        problems.append(f"임베딩이 실패했습니다({result.status}).")
    else:
        if len(result.vectors) != len(SELFTEST_TEXTS):
            problems.append("입력 수와 결과 수가 다릅니다.")
        for index, vector in enumerate(result.vectors):
            if len(vector) != catalog.VECTOR_DIM:
                problems.append(f"{index + 1}번 벡터의 차원이 다릅니다.")
            elif not pooling.is_unit_length(vector):
                # 정규화가 빠지면 코사인 거리가 길이에 끌린다 — 오류는 안 나고
                # 검색 순서만 조용히 틀어진다.
                problems.append(f"{index + 1}번 벡터가 길이 1 이 아닙니다.")
    print(json.dumps(
        {
            "ok": not problems,
            "model": result.model,
            "dim": result.dim,
            "count": len(result.vectors),
            "problems": problems,
        },
        ensure_ascii=False, indent=2,
    ))
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def cmd_install_model(db: Session, settings: Settings, args) -> int:
    """모델 파일을 캐시 자리에 놓는다. **네트워크를 쓰지 않는다.**

    받아 오는 경로를 만들지 않는 이유: 폐쇄망이 이 제품의 기본 전제이고, 설치 중에
    바깥 호스트 하나를 새로 여는 것은 그 전제와 정반대다(D-205 가 `curl … | bash` 를
    거절한 이유와 같다). 모델은 오프라인 번들이나 `--from` 으로 **들어온다.**
    """
    config = registry.resolve_config(settings)
    model = catalog.embedding_model(config.embed_model_id)
    if model is None:
        print(f"모르는 임베딩 모델입니다: {config.embed_model_id}", file=sys.stderr)
        return 1
    target = registry.model_dir(config, model)
    source = Path(args.source).expanduser()
    # 원본이 모델 디렉터리 자체일 수도 있고(`…/intfloat__multilingual-e5-small`),
    # 그것을 담은 뿌리일 수도 있다. 둘 다 받는다 — 어느 쪽을 줘야 하는지 외우게
    # 만드는 것이 설치를 어렵게 하는 흔한 이유다.
    if not (source / "tokenizer.json").is_file() and (source / model.dir_name).is_dir():
        source = source / model.dir_name
    missing = [name for name in model.required_files if not (source / name).is_file()]
    if missing:
        print(f"원본에 모델 파일 {len(missing)}개가 없습니다: {', '.join(missing)}", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for name in model.required_files:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == (source / name).resolve():
            continue
        shutil.copy2(source / name, destination)
    print(f"AI_MODEL_OK model={model.model_id} dir={target}")
    return 0


def cmd_reindex(db: Session, settings: Settings, args) -> int:
    """전 문서를 다시 색인하도록 표시한다. **여기서 색인하지는 않는다.**

    색인은 레인이 한다. 이 명령이 직접 돌면 운영자가 실행한 셸에서 몇 분짜리 임베딩이
    돌고, 그것을 Ctrl-C 로 끊으면 절반만 된 상태가 남는다.
    """
    count = index_service.enqueue_all(db)
    db.commit()
    print(f"AI_REINDEX_QUEUED documents={count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    install = sub.add_parser("install-model")
    install.add_argument("--from", dest="source", required=True, help="모델 파일이 있는 디렉터리")
    install.set_defaults(func=cmd_install_model)
    sub.add_parser("reindex").set_defaults(func=cmd_reindex)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        try:
            return args.func(db, settings, args)
        except AppError as exc:
            db.rollback()
            print(f"오류: {exc.message}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
