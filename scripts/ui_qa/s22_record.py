"""S22 전량 캡처 결과를 Surface 원장에 적는다 (W15).

증거는 하나다 — 전량 실행이 남긴 `results.json`(무엇이 그려졌는가). 원장도 하나다 —
`ROUTE_COVERAGE.json`.

## 왜 스크립트인가

95 Surface × (검사 21종 + Responsive 교차곱)을 손으로 옮기면 반드시 두 가지가 일어난다:
옮기다 틀리고, 다시 돌렸을 때 어느 쪽이 최신인지 아무도 모른다. S18 이 같은 이유로
`pilot_record.py` 를 만들었고 여기서는 그 부품(`pages_for` · `qa_run_map` · `advisory_map` ·
`matrix_for` · `worst`)을 그대로 쓴다 — 두 벌을 만들면 두 원장이 갈린다.

## 적지 않는 것

  * **통과하지 않은 것을 통과로.** `visual_audit.result` 는 그 화면의 캡처 조합 중 하나라도
    **승격 검사**가 실패했으면 `FAIL` 이다. 승격 목록은 `--fail-on` 과 같은 것을 받는다 —
    자문(advisory) 검사가 빨갛다고 시각 감사를 FAIL 로 적으면 그 판정은 게이트가 승격한
    적 없는 규칙으로 화면을 떨어뜨리는 것이다.
  * **못 찍은 화면을 찍은 것으로.** 이 실행에 페이지가 없는 Surface 는 **건드리지 않는다.**
  * **사람이 판단해야 하는 글.** `notes` 는 짓지 않는다.

## 상태 값

`DONE` 은 기능 축과 시각 축이 **둘 다** 통과한 화면에만 준다. 하나라도 FAIL 이거나 아직
없으면 그 화면의 상태는 그대로 둔다 — 이 스크립트가 상태를 올리는 유일한 방향은
「둘 다 PASS 이면 DONE」 하나다.

    python -m scripts.ui_qa.s22_record --capture s22-final --at 2026-08-26
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "ROUTE_COVERAGE.json"

from scripts.ui_qa.pilot_record import (  # noqa: E402
    advisory_map, dump, load, matrix_for, pages_for, qa_run_map,
)

HARNESS_BY = "S22 — scripts/ui_qa/run.py --full (실 브라우저 Chromium · 로컬 PostgreSQL 씨앗)"

#: 시각 감사 판정에 쓰는 **승격 검사**. `run.py --fail-on` 에 넘긴 것과 같아야 한다 —
#: 자문 검사(빈 면·반복 면 같은 것)는 원장의 `advisory` 칸이 수치로 들고, 판정은 안 바꾼다.
PROMOTED = (
    "brand_role_coverage", "column_width_vs_content", "control_baseline_mismatch",
    "detail_side_imbalance", "equal_column_split", "header_cell_alignment_mismatch",
    "isolated_control_row", "mascot_visible_size", "numeric_alignment",
    "plain_dropdown_for_entity",
    # 이 넷은 Wave 승격표 밖이지만 «화면이 깨졌다» 는 사실 자체라 언제나 판정에 든다.
    "auth_ok", "page_errors", "horizontal_overflow", "content_clipped",
)


def harness_route(surface: dict, by_id: dict) -> str:
    host = by_id.get(surface.get("host_surface") or "") or {}
    return surface.get("harness_id") or host.get("harness_id") or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="S22 전량 캡처 → Surface 원장")
    ap.add_argument("--capture", required=True, help="캡처 실행 라벨 (dist/ui-qa/<label>/)")
    ap.add_argument("--at", required=True, help="감사 날짜(YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results_path = REPO_ROOT / "dist" / "ui-qa" / args.capture / "results.json"
    if not results_path.exists():
        print("캡처 결과가 없다: %s" % results_path)
        return 2
    results = load(results_path)
    run = results.get("run") or {}
    build_sha = ((run.get("build_after") or {}).get("index_sha256")
                 or (run.get("build_before") or {}).get("index_sha256") or "")
    if not build_sha:
        print("번들 지문을 못 읽었다 — 이 실행이 어느 빌드를 찍었는지 모른 채로 원장에 적지 않는다")
        return 2

    cov = load(ROUTE_LEDGER)
    surfaces = cov.get("surfaces") or []
    by_id = {s.get("id"): s for s in surfaces}
    profiles = cov.get("responsive_profiles") or {}

    touched, no_pages, failing = [], [], {}
    for sf in surfaces:
        sid = sf.get("id")
        if sf.get("status") == "RETIRED":
            continue
        route = harness_route(sf, by_id)
        pages = pages_for(results, route) if route else []
        if not pages:
            no_pages.append("%s (harness=%r)" % (sid, route))
            continue

        qa = qa_run_map(pages)
        bad = sorted(c for c in PROMOTED if qa.get(c) == "fail")
        if bad:
            failing[sid] = bad

        evidence = sf.get("evidence") or {}
        evidence["qa_run"] = qa
        evidence["build_index_sha256"] = [build_sha]
        sf["evidence"] = evidence
        sf["advisory"] = advisory_map(pages, args.capture)

        resp = sf.get("responsive_audit") or {}
        profile = profiles.get(resp.get("required_profile") or "")
        if profile:
            rows = matrix_for(pages, args.capture, route, profile)
            resp["matrix"] = rows
            resp["result"] = "FAIL" if any(r["result"] == "FAIL" for r in rows) else "PASS"
            sf["responsive_audit"] = resp

        combos = sorted({"%s/%s" % (p.get("viewport"), p.get("theme")) for p in pages})
        va = sf.get("visual_audit") or {}
        va["result"] = "FAIL" if bad else "PASS"
        va["by"] = HARNESS_BY
        va["at"] = args.at
        va["evidence"] = [
            "ev:qa_run:%s (dist/ui-qa/%s/results.json)" % (args.capture, args.capture),
            "ev:capture:dist/ui-qa/%s/light/1920x1080/%s.png" % (args.capture, route),
        ]
        va["combos"] = len(combos)
        if bad:
            va["failing_classes"] = bad
        sf["visual_audit"] = va

        fa_result = (sf.get("functional_audit") or {}).get("result")
        if not bad and fa_result == "PASS" and sf.get("status") in ("FUNCTIONAL_PASS", "DONE"):
            sf["status"] = "DONE"
        touched.append(sid)

    print("적은 Surface: %d" % len(touched))
    print("이 실행에 페이지가 없어 **안 건드린** Surface: %d" % len(no_pages))
    for line in no_pages:
        print("  - %s" % line)
    if failing:
        print("승격 검사가 실패한 Surface: %d" % len(failing))
        for sid, classes in sorted(failing.items()):
            print("  - %s: %s" % (sid, ", ".join(classes)))
    else:
        print("승격 검사 실패 Surface 0")

    if args.dry_run:
        print("(dry-run — 원장을 안 고쳤다)")
        return 0
    dump(ROUTE_LEDGER, cov)
    print("원장 갱신: %s" % ROUTE_LEDGER)
    return 0


if __name__ == "__main__":
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    raise SystemExit(main())
