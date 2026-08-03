"""Phase 2c 마무리 — 포탈과 Notion DB의 분류 기준을 완전히 일치시킨다.

재분류(scripts/phase2c_reclassify.py)로 문서의 유형/카테고리는 신규 택소노미로 바뀌었지만
아직 두 가지가 남아 있다:

  1. 관계 DB에 **아무 문서도 쓰지 않는 옛 분류 항목**이 그대로 남아 있다. 드롭다운을 열면
     쓰지 않는 옛 이름이 계속 보여서, 다음 사람이 그걸 다시 고르면 분류가 또 갈라진다.
  2. 문서 DB에 **`기술 태그` 속성이 아예 없다**. 포탈은 화면에 기술 태그를 보여주는데
     Notion에는 그 값이 없으니, 같은 문서를 두 곳에서 보면 정보가 다르다.

이 스크립트가 둘 다 맞춘다. 태그 값은 포탈이 쓰는 바로 그 함수(app/team_docs/classify.py)로
계산한다 — 다른 규칙으로 계산하면 애초에 맞추려던 불일치가 다시 생긴다.

기본은 드라이런이다. `--apply` 없이는 Notion에 아무것도 쓰지 않는다.

    python scripts/phase2c_taxonomy_align.py                 # 무엇이 바뀌는지만 본다
    python scripts/phase2c_taxonomy_align.py --apply         # 태그 속성 생성 + 값 채우기
    python scripts/phase2c_taxonomy_align.py --apply --prune # 미사용 옛 분류 항목까지 보관 처리

`--prune`은 **참조 문서가 0건인 항목만** 보관 처리한다(사용자 지시: 적용된 게 없는 것만).
보관한 항목 id는 파일로 남겨 되돌릴 수 있다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.allowlist import AllowlistRegistry  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.http_client import OutboundClient  # noqa: E402
from app.core.secret_refs import FileSecretReferenceProvider  # noqa: E402
from app.team_docs import notion_docs  # noqa: E402
from app.team_docs.classify import TECH_TAGS, classify  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "var" / "phase2c"
PROP_TECH = "기술 태그"
SLEEP = 0.4


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _client(settings: Settings) -> OutboundClient:
    secrets = FileSecretReferenceProvider(settings.secrets_dir)
    if secrets.get(settings.notion_docs_token_ref) is None:
        raise SystemExit(f"Notion 토큰이 없습니다: {settings.secrets_dir}/{settings.notion_docs_token_ref}")
    return OutboundClient(AllowlistRegistry(settings.config_dir), secrets)


def ensure_tech_property(outbound, settings, apply: bool) -> bool:
    """문서 DB에 다중 선택 '기술 태그' 속성이 없으면 만든다. 이미 있으면 그대로 둔다."""
    props = notion_docs.fetch_documents_schema(outbound, settings)
    if PROP_TECH in props:
        print(f"'{PROP_TECH}' 속성: 이미 있음")
        return True
    print(f"'{PROP_TECH}' 속성: 없음 → 다중 선택으로 생성 (옵션 {len(TECH_TAGS)}종)")
    if not apply:
        return False
    notion_docs._request(
        outbound, settings, "PATCH", f"/v1/databases/{settings.notion_documents_database_id}",
        json={"properties": {PROP_TECH: {"multi_select": {"options": [{"name": t} for t in TECH_TAGS]}}}},
    )
    print(f"  생성 완료")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="포탈 ↔ Notion 분류 기준 정렬")
    ap.add_argument("--apply", action="store_true", help="실제로 Notion에 쓴다")
    ap.add_argument("--prune", action="store_true", help="참조 0건인 옛 분류 항목을 보관 처리한다")
    args = ap.parse_args()

    settings = Settings()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now()
    outbound = _client(settings)

    rows, truncated = notion_docs.query_all_documents(outbound, settings)
    if truncated:
        print("[중단] 문서 목록이 잘렸다(truncated) — 전체를 못 받은 상태로 정리하면 안 된다.")
        return 2
    schema = notion_docs.fetch_documents_schema(outbound, settings)
    maps = notion_docs.resolve_relation_maps(outbound, settings, schema)
    type_names = maps.get(notion_docs.PROP_TYPE) or {}     # {page_id: name}
    cat_names = maps.get(notion_docs.PROP_CATEGORY) or {}
    print(f"문서 {len(rows)}건, 유형 항목 {len(type_names)}개, 카테고리 항목 {len(cat_names)}개")

    has_prop = ensure_tech_property(outbound, settings, args.apply)

    # 1) 기술 태그 값 — 포탈과 같은 함수로 계산한다.
    plan_tags = []
    for r in rows:
        tnames = [type_names.get(i, "") for i in (r.get("type_ids") or [])]
        cnames = [cat_names.get(i, "") for i in (r.get("category_ids") or [])]
        _dt, _wf, tags = classify(tnames, cnames, r.get("title") or "")
        if tags:
            plan_tags.append({"page_id": r["notion_page_id"], "title": r.get("title"), "tags": tags})
    print(f"\n기술 태그가 붙는 문서: {len(plan_tags)}건 / {len(rows)}건")
    from collections import Counter
    dist = Counter(t for p in plan_tags for t in p["tags"])
    print("  태그 분포:", dict(dist.most_common()))

    # 2) 참조 0건인 분류 항목
    used_types = {i for r in rows for i in (r.get("type_ids") or [])}
    used_cats = {i for r in rows for i in (r.get("category_ids") or [])}
    unused = [("유형", pid, name) for pid, name in type_names.items() if pid not in used_types]
    unused += [("카테고리", pid, name) for pid, name in cat_names.items() if pid not in used_cats]
    print(f"\n참조 0건인 분류 항목: {len(unused)}개")
    for kind, _pid, name in unused:
        print(f"  {kind}: {name}")

    if not args.apply:
        print("\n[드라이런] 아무것도 쓰지 않았습니다. --apply 로 실행하세요.")
        return 0

    # 태그 쓰기
    ok = fail = 0
    audit = OUT_DIR / f"tags-{stamp}.jsonl"
    if has_prop and plan_tags:
        with audit.open("w", encoding="utf-8") as fh:
            for i, p in enumerate(plan_tags, 1):
                try:
                    notion_docs._request(
                        outbound, settings, "PATCH", f"/v1/pages/{p['page_id']}",
                        json={"properties": {PROP_TECH: {"multi_select": [{"name": t} for t in p["tags"]]}}},
                    )
                    p["result"] = "ok"; ok += 1
                except Exception as exc:  # noqa: BLE001
                    p["result"] = "error"; p["error"] = f"{type(exc).__name__}: {exc}"; fail += 1
                fh.write(json.dumps(p, ensure_ascii=False) + "\n"); fh.flush()
                if i % 20 == 0 or i == len(plan_tags):
                    print(f"  태그 {i}/{len(plan_tags)}")
                time.sleep(SLEEP)
        print(f"기술 태그: 성공 {ok}건, 실패 {fail}건 → {audit}")

    # 미사용 항목 보관 처리
    if args.prune and unused:
        pruned = OUT_DIR / f"pruned-{stamp}.jsonl"
        with pruned.open("w", encoding="utf-8") as fh:
            for kind, pid, name in unused:
                try:
                    notion_docs._request(outbound, settings, "PATCH", f"/v1/pages/{pid}", json={"archived": True})
                    res = "ok"
                except Exception as exc:  # noqa: BLE001
                    res = f"error: {exc}"
                fh.write(json.dumps({"kind": kind, "page_id": pid, "name": name, "result": res,
                                     "at": _now()}, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"  보관 {kind}/{name}: {res}")
                time.sleep(SLEEP)
        print(f"보관 기록: {pruned}  (되돌리려면 archived=false 로 되돌리면 된다)")

    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
