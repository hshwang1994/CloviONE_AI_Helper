"""Phase 2c — 문서 109건을 신규 택소노미로 재분류(Notion 원본 쓰기).

읽기 전용 드라이런이 기본이다. `--apply` 없이는 Notion에 아무것도 쓰지 않는다.

## 왜 이 스크립트가 따로 필요한가

`docs/migration_backups/classify_docs.py`는 **분류 결과를 계산만** 한다(출력: doc_classification.json).
앱 화면에 보이는 분류는 이미 `app/team_docs/classify.py`가 동기화마다 로컬로 계산해 제공하므로,
여기서 하는 일은 그 위에 얹는 별개 작업 — **Notion 원본을 바꾸는 것**이다. 되돌리기 어려우므로
백업·감사 로그·롤백을 이 스크립트가 직접 책임진다.

## 착수 전 반드시 알아야 할 것 (조사로 확인한 사실)

`유형`(PROP_TYPE)과 `카테고리`(PROP_CATEGORY)는 select가 아니라 **relation** 속성이다.
값이 문자열이 아니라 다른 DB의 페이지 id다. 백업 시점 기준 기존 유형 15종은 전부 옛 택소노미이고,
신규 택소노미 8종 중 실제로 존재하는 것은 `회의록`·`작업 계획서` 둘뿐이다.

따라서 전면 적용은 다음을 수반한다:
  1. 유형 관계 DB에 신규 페이지 생성(참고자료·기획서·설계서·매뉴얼·보고서·기타 등)
  2. 업무 분야를 담을 관계 DB 페이지 생성(자동화·개발·운영·보안·사내 업무 등)
  3. `기술 태그`에 해당하는 속성이 **아예 없다** — 새 속성을 만들거나 카테고리로 흡수해야 한다

즉 "태그 갈아끼우기"가 아니라 **워크스페이스 스키마 변경**이다. `--allow-schema-change` 없이는
새 페이지를 만들지 않고, 매핑되지 않는 문서는 건너뛰고 그 사실을 보고한다.

## 사용법

    # 1) 드라이런 — 무엇이 바뀌는지만 본다(쓰기 없음)
    python scripts/phase2c_reclassify.py

    # 2) 신선한 백업만 다시 뜬다(적용 전 필수 — 7월 백업은 오래됐다)
    python scripts/phase2c_reclassify.py --backup-only

    # 3) 기존 분류 페이지로 매핑되는 것만 적용(스키마 변경 없음)
    python scripts/phase2c_reclassify.py --apply

    # 4) 신규 분류 페이지 생성까지 허용해 전량 적용
    python scripts/phase2c_reclassify.py --apply --allow-schema-change

    # 5) 되돌리기 — 감사 로그의 before 값으로 복원
    python scripts/phase2c_reclassify.py --rollback var/phase2c/audit-<타임스탬프>.jsonl

토큰은 앱과 같은 방식으로 읽는다(`secrets_dir/<notion_docs_token_ref>`). 로컬 개발 환경에는
보통 없고 운영 서버에만 있다 — 없으면 즉시 멈추고 그렇게 말한다.
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

REPO = Path(__file__).resolve().parents[1]
CLASSIFICATION = REPO / "docs" / "migration_backups" / "doc_classification.json"
OUT_DIR = REPO / "var" / "phase2c"

# Notion API는 통합당 평균 3 req/s가 상한이다. 여유를 두고 초당 2.5건으로 던진다 —
# 109건이면 45초 남짓이고, 429를 맞고 재시도하는 것보다 처음부터 느리게 가는 편이 안전하다.
SLEEP_BETWEEN_WRITES = 0.4


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_classification() -> dict:
    if not CLASSIFICATION.exists():
        raise SystemExit(f"분류 결과가 없다: {CLASSIFICATION}\n먼저 docs/migration_backups/classify_docs.py를 실행하세요.")
    return json.loads(CLASSIFICATION.read_text(encoding="utf-8"))


def _client(settings: Settings) -> OutboundClient:
    # 앱(worker_main)과 똑같이 만든다 — 아웃바운드는 반드시 allowlist 관문을 지나고,
    # 토큰은 파일 참조로만 읽는다(평문을 코드나 인자로 넘기지 않는다).
    secrets = FileSecretReferenceProvider(settings.secrets_dir)
    if secrets.get(settings.notion_docs_token_ref) is None:
        raise SystemExit(
            f"Notion 토큰이 없습니다: {settings.secrets_dir}/{settings.notion_docs_token_ref}\n"
            "토큰 파일을 두거나, 토큰이 있는 환경(운영 서버)에서 실행하세요."
        )
    return OutboundClient(AllowlistRegistry(settings.config_dir), secrets)


def fetch_backup(outbound, settings) -> dict:
    """지금 이 순간의 Notion 상태를 그대로 뜬다 — 적용 전 마지막 되돌림 지점."""
    # query_all_documents는 원시 Notion 행이 아니라 parse_document()를 거친 dict를 준다 —
    # page id는 `notion_page_id` 키에 있다. 원시 행으로 착각해 row["id"]를 읽으면 전부 None이
    # 되고, 그러면 "분류 결과와 하나도 안 맞는다"는 잘못된 결론이 나온다(실제로 한 번 그랬다).
    rows, truncated = notion_docs.query_all_documents(outbound, settings)
    schema = notion_docs.fetch_documents_schema(outbound, settings)
    maps = notion_docs.resolve_relation_maps(outbound, settings, schema)
    docs = [{
        "page_id": r.get("notion_page_id"),
        "title": r.get("title"),
        "type_ids": r.get("type_ids") or [],
        "category_ids": r.get("category_ids") or [],
    } for r in rows]
    return {
        "taken_at": _now(),
        "truncated": truncated,
        "database_id": settings.notion_documents_database_id,
        "relation_maps": maps,
        "documents": docs,
    }


def _title_property_name(outbound, settings, database_id: str) -> str:
    """관계 대상 DB의 제목 속성 이름을 찾는다.

    Notion에서 제목 속성 이름은 DB마다 다르다("이름"/"Name"/"제목"…). 하드코딩하면 다른
    워크스페이스에서 조용히 실패하므로 스키마에서 type=='title'인 속성을 찾아 쓴다.
    """
    data = notion_docs._request(outbound, settings, "GET", f"/v1/databases/{database_id}")
    for name, prop in (data.get("properties") or {}).items():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return name
    raise SystemExit(f"제목 속성을 찾지 못했습니다: database_id={database_id}")


def _create_relation_item(outbound, settings, database_id: str, title_key: str, name: str) -> str:
    data = notion_docs._request(
        outbound, settings, "POST", "/v1/pages",
        json={"parent": {"database_id": database_id},
              "properties": {title_key: {"title": [{"text": {"content": name}}]}}},
    )
    return data.get("id")


def _write_page_relations(outbound, settings, page_id: str, type_ids, category_ids) -> None:
    props = {}
    if type_ids is not None:
        props[notion_docs.PROP_TYPE] = {"relation": [{"id": i} for i in type_ids]}
    if category_ids is not None:
        props[notion_docs.PROP_CATEGORY] = {"relation": [{"id": i} for i in category_ids]}
    if not props:
        return
    notion_docs._request(outbound, settings, "PATCH", f"/v1/pages/{page_id}", json={"properties": props})


def main() -> int:
    ap = argparse.ArgumentParser(description="문서 재분류(Notion 원본) — 기본은 드라이런")
    ap.add_argument("--apply", action="store_true", help="실제로 Notion에 쓴다")
    ap.add_argument("--allow-schema-change", action="store_true",
                    help="신규 분류 페이지 생성을 허용한다(워크스페이스 구조가 바뀐다)")
    ap.add_argument("--backup-only", action="store_true", help="백업만 뜨고 끝낸다")
    ap.add_argument("--rollback", metavar="AUDIT_JSONL", help="감사 로그의 before 값으로 되돌린다")
    ap.add_argument("--limit", type=int, default=0, help="처음 N건만 처리(시험용)")
    args = ap.parse_args()

    settings = Settings()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now()

    if args.rollback:
        return _rollback(settings, Path(args.rollback))

    classification = _load_classification()
    print(f"분류 결과 {len(classification)}건 로드")

    outbound = _client(settings)

    backup = fetch_backup(outbound, settings)
    backup_path = OUT_DIR / f"backup-{stamp}.json"
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"백업 저장: {backup_path} ({len(backup['documents'])}건)")
    if backup["truncated"]:
        print("[중단] Notion 목록이 잘렸다(truncated). 전체를 못 받은 상태로 덮어쓰면 안 된다.")
        return 2
    if args.backup_only:
        return 0

    # 관계 페이지 이름 → id. 이 매핑에 없는 신규 택소노미가 스키마 변경이 필요한 항목이다.
    maps = backup.get("relation_maps") or {}
    type_map = {v: k for k, v in (maps.get(notion_docs.PROP_TYPE) or {}).items()}
    cat_map = {v: k for k, v in (maps.get(notion_docs.PROP_CATEGORY) or {}).items()}

    by_id = {d["page_id"]: d for d in backup["documents"]}
    plan, missing_type, missing_field, skipped = [], set(), set(), 0

    for page_id, new in classification.items():
        cur = by_id.get(page_id)
        if not cur:
            skipped += 1
            continue
        want_type, want_field = new["doc_type"], new["work_field"]
        tid, cid = type_map.get(want_type), cat_map.get(want_field)
        if tid is None:
            missing_type.add(want_type)
        if cid is None:
            missing_field.add(want_field)
        if tid is None or cid is None:
            continue
        if cur["type_ids"] == [tid] and cur["category_ids"] == [cid]:
            continue  # 이미 그 값이다
        plan.append({"page_id": page_id, "title": cur["title"],
                     "before": {"type_ids": cur["type_ids"], "category_ids": cur["category_ids"]},
                     "after": {"type_ids": [tid], "category_ids": [cid]}})

    print(f"\n적용 대상: {len(plan)}건")
    if skipped:
        print(f"  분류 결과에는 있으나 지금 Notion에 없는 문서: {skipped}건 (건너뜀)")
    if missing_type:
        print(f"  [스키마 변경 필요] 유형 관계 DB에 없는 새 분류: {sorted(missing_type)}")
    if missing_field:
        print(f"  [스키마 변경 필요] 카테고리 관계 DB에 없는 새 업무 분야: {sorted(missing_field)}")
    if (missing_type or missing_field) and not args.allow_schema_change:
        print("\n  → 위 항목이 필요한 문서는 이번 실행에서 제외됩니다.")
        print("    전량 적용하려면 --allow-schema-change 를 주고 다시 실행하세요(워크스페이스에 페이지가 생깁니다).")
    print("  기술 태그: 이 문서 DB에는 해당 속성이 없습니다 — 이번 스크립트는 건드리지 않습니다.")

    if not args.apply:
        preview = OUT_DIR / f"plan-{stamp}.json"
        preview.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[드라이런] 아무것도 쓰지 않았습니다. 계획 저장: {preview}")
        return 0

    if args.allow_schema_change and (missing_type or missing_field):
        # 신규 택소노미 항목을 관계 대상 DB에 항목으로 추가한다. 사용자 승인 사항이다.
        # 되돌릴 수 있게 만든 항목의 id를 파일로 남긴다(Notion에서 보관 처리하면 원복).
        # fetch_documents_schema()는 응답을 감싸지 않고 **속성 dict 자체**를 돌려준다
        # (최상위 키가 '날짜'·'유형'처럼 속성 이름이다). schema["properties"]로 읽으면 None이 되어
        # "관계 대상 DB를 찾지 못했다"는 엉뚱한 결론이 난다 — 실제로 한 번 그랬다.
        sprops = notion_docs.fetch_documents_schema(outbound, settings)
        type_db = notion_docs._relation_target_db(sprops.get(notion_docs.PROP_TYPE) or {})
        cat_db = notion_docs._relation_target_db(sprops.get(notion_docs.PROP_CATEGORY) or {})
        if not type_db or not cat_db:
            print("\n[중단] 관계 대상 DB를 찾지 못했습니다 — 스키마를 확인하세요.")
            return 3

        title_key = _title_property_name(outbound, settings, type_db)
        cat_title_key = _title_property_name(outbound, settings, cat_db)
        created_path = OUT_DIR / f"created-{stamp}.jsonl"
        print(f"\n신규 분류 항목 추가: 유형 {len(missing_type)}개, 카테고리 {len(missing_field)}개")
        with created_path.open("w", encoding="utf-8") as fh:
            for db_id, key, names, target in ((type_db, title_key, sorted(missing_type), type_map),
                                              (cat_db, cat_title_key, sorted(missing_field), cat_map)):
                for name in names:
                    made = _create_relation_item(outbound, settings, db_id, key, name)
                    target[name] = made
                    fh.write(json.dumps({"database_id": db_id, "name": name, "page_id": made,
                                         "at": _now()}, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(f"  추가 {name} → {made}")
                    time.sleep(SLEEP_BETWEEN_WRITES)
        print(f"추가 기록: {created_path}  (되돌리려면 이 항목들을 Notion에서 보관 처리)")

        # 새 매핑으로 계획을 다시 세운다 — 방금 추가한 항목 덕분에 대상이 늘어난다.
        plan = []
        for page_id, new in classification.items():
            cur = by_id.get(page_id)
            if not cur:
                continue
            tid, cid = type_map.get(new["doc_type"]), cat_map.get(new["work_field"])
            if tid is None or cid is None:
                continue
            if cur["type_ids"] == [tid] and cur["category_ids"] == [cid]:
                continue
            plan.append({"page_id": page_id, "title": cur["title"],
                         "before": {"type_ids": cur["type_ids"], "category_ids": cur["category_ids"]},
                         "after": {"type_ids": [tid], "category_ids": [cid]}})
        print(f"재계산된 적용 대상: {len(plan)}건")

    audit_path = OUT_DIR / f"audit-{stamp}.jsonl"
    ok = fail = 0
    with audit_path.open("w", encoding="utf-8") as fh:
        for i, item in enumerate(plan if not args.limit else plan[: args.limit], 1):
            rec = dict(item, at=_now())
            try:
                _write_page_relations(outbound, settings, item["page_id"],
                                      item["after"]["type_ids"], item["after"]["category_ids"])
                rec["result"] = "ok"
                ok += 1
            except Exception as exc:  # noqa: BLE001 — 한 건 실패가 전체를 멈추면 안 된다
                rec["result"] = "error"
                rec["error"] = f"{type(exc).__name__}: {exc}"
                fail += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()   # 중간에 죽어도 여기까지는 되돌릴 수 있어야 한다
            print(f"  [{i}/{len(plan)}] {rec['result']:<5} {item['title'][:40]}")
            time.sleep(SLEEP_BETWEEN_WRITES)

    print(f"\n완료: 성공 {ok}건, 실패 {fail}건")
    print(f"감사 로그: {audit_path}")
    print(f"되돌리기: python scripts/phase2c_reclassify.py --rollback {audit_path}")
    return 1 if fail else 0


def _rollback(settings: Settings, audit_path: Path) -> int:
    if not audit_path.exists():
        raise SystemExit(f"감사 로그가 없다: {audit_path}")
    outbound = _client(settings)
    done = failed = 0
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("result") != "ok":
            continue   # 애초에 안 바뀐 건 되돌릴 것도 없다
        try:
            _write_page_relations(outbound, settings, rec["page_id"],
                                  rec["before"]["type_ids"], rec["before"]["category_ids"])
            done += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  실패 {rec['page_id']}: {exc}")
        time.sleep(SLEEP_BETWEEN_WRITES)
    print(f"되돌림 {done}건, 실패 {failed}건")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
