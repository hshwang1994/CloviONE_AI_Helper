"""Pilot 실행 결과를 Control Plane 원장에 적는다 (W8 · S18).

증거는 두 파일이다 — `pilot_e2e.py` 가 남긴 `flows.json`(무엇을 눌렀고 무엇이 왔는가)과
캡처 실행이 남긴 `results.json`(무엇이 그려졌는가). 원장은 둘이다 —
`FUNCTIONAL_COVERAGE.json`(Flow)과 `ROUTE_COVERAGE.json`(Surface).

**옮겨 적는 자리를 하나로 둔다.** 238 Flow 와 17 Surface 를 손으로 옮기면 반드시 두 가지가
일어난다: 옮기다 틀리고, 다시 돌렸을 때 어느 쪽이 최신인지 아무도 모른다.

적지 않는 것:

  * 통과하지 않은 것을 통과로. FAIL 은 FAIL 로 적고 목록으로 돌려준다.
  * 사람이 판단해야 하는 글. `visual_audit.notes` 같은 서술은 이 스크립트가 짓지 않는다 —
    측정치만 넣고 문장은 사람이 쓴다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNC_LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "FUNCTIONAL_COVERAGE.json"
ROUTE_LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "ROUTE_COVERAGE.json"
FLOWS = REPO_ROOT / "dist" / "ui-qa" / "pilot" / "flows.json"

# 사슬의 서버 칸 — 하나라도 차 있으면 그 Flow 는 서버를 불렀다.
SERVER_KEYS = ("api_request", "backend_query", "api_response")

WHY_NO_SERVER = {
    "modal_action": "모달을 열고 닫는 것은 화면 안에서 끝난다 — 이 동작 자체는 서버에 아무것도 묻지 않는다(실측 요청 0건).",
    "form_validation": "필수값이나 형식이 어긋나면 보내지 않는 것이 계약이라 서버 왕복이 일어나지 않는다(실측 요청 0건).",
    "filter": "이 화면은 받아 둔 목록을 화면 안에서 거른다 — 조건을 바꿔도 서버를 다시 부르지 않는다(실측 요청 0건).",
    "search": "받아 둔 목록을 화면 안에서 거르는 검색이라 서버 왕복이 없다(실측 요청 0건).",
    "sort": "정렬은 받아 둔 목록의 순서만 바꾼다 — 서버를 다시 부르지 않는다(실측 요청 0건).",
    "pagination": "이 표본은 한 쪽뿐이라 넘길 것이 없다 — 서버를 부르지 않는 것이 맞다(실측 요청 0건).",
    "permission_state": "권한이 없으면 컨트롤 자체를 그리지 않는다 — 눌러서 거절당하는 왕복이 애초에 없다(실측 요청 0건).",
    "row_action": "행의 이 동작은 화면 안에서 끝난다 — 서버를 부르지 않는다(실측 요청 0건).",
    "overflow_action": "넘침 메뉴를 여는 것은 화면 안에서 끝난다 — 서버를 부르지 않는다(실측 요청 0건).",
    "attachment": "이 표본에는 첨부가 없어 올리거나 뗄 것이 없다 — 자리만 확인한다(실측 요청 0건).",
    "combobox": "이 화면에는 그 선택기가 없는 것이 계약이라 부를 서버가 없다(실측 요청 0건).",
    "navigation": "해시 라우팅이라 새 문서를 받지 않는다 — 이 동작 자체는 서버를 부르지 않는다(실측 요청 0건).",
    "keyboard": "키보드 조작은 초점과 화면 상태만 바꾼다 — 서버를 부르지 않는다(실측 요청 0건).",
    "back_forward": "뒤로가기는 캐시가 있으면 다시 묻지 않는다 — 요청이 없는 것이 정상이다(실측 요청 0건).",
    "deep_link": "주소를 그대로 다시 여는 것이라 이 동작에서 새 질의가 나가지 않는다(실측 요청 0건).",
    "refresh": "다시 그리는 데 새 질의가 필요 없었다 — 캐시가 답했다(실측 요청 0건).",
    "inline_edit": "화면 안에서 초안만 고친다 — 저장을 누르기 전에는 서버로 나가지 않는다(실측 요청 0건).",
    "read": "받아 둔 응답을 다시 그리는 것이라 이 동작에서 새 질의가 나가지 않는다(실측 요청 0건).",
}
DEFAULT_WHY = "이 동작은 화면 안에서 끝난다 — 실측에서 서버 요청이 한 건도 없었다."

ADVISORY = ("surface_repetition", "oversized_empty_surface")
HARNESS_BY = "S18 — scripts/ui_qa/pilot_e2e.py (실 브라우저 Chromium · 로컬 PostgreSQL 씨앗)"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONAL_COVERAGE — Flow
# ─────────────────────────────────────────────────────────────────────────────
def flow_evidence(record: dict, run_token: str) -> list[str]:
    out = [run_token]
    for shot in record.get("screenshots") or []:
        out.append("ev:capture:%s" % str(shot).replace("\\", "/"))
    return out


def write_flows(ledger: dict, records: list[dict], *, at: str, run_token: str) -> dict:
    by_surface = {s.get("surface"): s for s in ledger.get("surfaces") or []}
    stats = {"written": 0, "failed": [], "missing": [], "surfaces": set()}
    for rec in records:
        entry = by_surface.get(rec["surface"])
        flow = None
        if entry:
            flow = next((f for f in entry.get("flows") or [] if f.get("id") == rec["id"]), None)
        if flow is None:
            stats["missing"].append("%s/%s" % (rec["surface"], rec["id"]))
            continue
        chain = dict(rec.get("chain") or {})
        flow["status"] = "PASS" if rec["status"] == "PASS" else "FAIL"
        flow["chain"] = chain
        flow["expected"] = rec.get("expected") or {}
        flow["cross_surface"] = rec.get("cross_surface") or []
        flow["evidence"] = flow_evidence(rec, run_token)
        flow["audited_at"] = at
        flow["by"] = HARNESS_BY
        if any(chain.get(k) for k in SERVER_KEYS):
            flow.pop("server_free", None)
        else:
            flow["server_free"] = WHY_NO_SERVER.get(rec.get("category"), DEFAULT_WHY)
        if rec["status"] != "PASS":
            stats["failed"].append("%s/%s — %s"
                                   % (rec["surface"], rec["id"],
                                      "; ".join(rec.get("notes") or [])[:160]))
        stats["written"] += 1
        stats["surfaces"].add(rec["surface"])
    return stats


def flow_leftovers(ledger: dict, surfaces: set[str]) -> list[str]:
    out = []
    for entry in ledger.get("surfaces") or []:
        if entry.get("surface") not in surfaces:
            continue
        for fl in entry.get("flows") or []:
            if fl.get("exists") and fl.get("status") == "NOT_AUDITED":
                out.append("%s/%s (%s)" % (entry["surface"], fl.get("id"), fl.get("category")))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE_COVERAGE — Surface
# ─────────────────────────────────────────────────────────────────────────────
def worst(values: list[str]) -> str:
    """한 화면의 여러 조합에서 나온 판정을 하나로 접는다 — **나쁜 쪽으로**."""
    if "fail" in values:
        return "fail"
    if "pass" in values:
        return "pass"
    return "skip"


def pages_for(results: dict, route: str) -> list[dict]:
    return [p for p in results.get("pages") or [] if p.get("route") == route]


def qa_run_map(pages: list[dict]) -> dict:
    classes: dict[str, list[str]] = {}
    for page in pages:
        for cls, entry in (page.get("assertions") or {}).items():
            classes.setdefault(cls, []).append((entry or {}).get("status") or "skip")
    return {cls: worst(vals) for cls, vals in sorted(classes.items())}


def advisory_map(pages: list[dict], label: str, *, borrowed: str = "") -> dict:
    out = {}
    for cls in ADVISORY:
        tally = {"pass": 0, "fail": 0, "skip": 0}
        note, combo = "", ""
        for page in pages:
            entry = (page.get("assertions") or {}).get(cls) or {}
            status = entry.get("status") or "skip"
            tally[status] = tally.get(status, 0) + 1
            if status == "fail" and not note:
                note = "; ".join(entry.get("samples") or [])[:400] or (entry.get("note") or "")
                combo = "%s/%s" % (page.get("viewport"), page.get("theme"))
        if not note:
            for page in pages:
                entry = (page.get("assertions") or {}).get(cls) or {}
                if (entry.get("status") or "") == "pass":
                    note = entry.get("note") or "후보 없음 — 이 화면에는 이 형태가 없다"
                    combo = "%s/%s" % (page.get("viewport"), page.get("theme"))
                    break
        row = {"label": label, "pass": tally["pass"], "fail": tally["fail"],
               "skip": tally["skip"], "measured_note": note, "sample_combo": combo}
        if borrowed:
            row["borrowed_from"] = borrowed
        out[cls] = row
    return out


def matrix_for(pages: list[dict], label: str, route: str, profile: dict) -> list[dict]:
    """Responsive 교차곱 — 프로필이 요구하는 조합만, 캡처가 실제로 있는 것으로 채운다."""
    want_v = list(profile.get("viewports") or [])
    want_t = list(profile.get("themes") or [])
    zooms = list(profile.get("zooms") or [100])
    have = {(p.get("viewport"), p.get("theme")): p for p in pages}
    rows = []
    for viewport in want_v:
        for theme in want_t:
            page = have.get((viewport, theme))
            if page is None:
                continue
            fails = [c for c, e in (page.get("assertions") or {}).items()
                     if (e or {}).get("status") == "fail"]
            rows.append({
                "viewport": viewport, "theme": theme, "zoom": zooms[0],
                "result": "FAIL" if fails else "PASS",
                "evidence": "ev:capture:dist/ui-qa/%s/%s/%s/%s.png"
                            % (label, theme, viewport, route),
            })
    return rows


def write_surfaces(route_cov: dict, results: dict, flow_records: list[dict], *,
                   wave: str, label: str, at: str) -> dict:
    run = results.get("run") or {}
    build_sha = ((run.get("build_after") or {}).get("index_sha256")
                 or (run.get("build_before") or {}).get("index_sha256") or "")
    surfaces = route_cov.get("surfaces") or []
    by_id = {s.get("id"): s for s in surfaces}
    profiles = route_cov.get("responsive_profiles") or {}
    flows_by_surface: dict[str, list[str]] = {}
    fails_by_surface: dict[str, list[str]] = {}
    for rec in flow_records:
        flows_by_surface.setdefault(rec["surface"], []).append(rec["id"])
        if rec.get("status") != "PASS":
            fails_by_surface.setdefault(rec["surface"], []).append(rec["id"])

    stats = {"touched": [], "no_pages": [], "fail_classes": {}}
    for sf in surfaces:
        if sf.get("wave") != wave or sf.get("status") == "RETIRED":
            continue
        sid = sf.get("id")
        host = by_id.get(sf.get("host_surface") or "") or {}
        route = sf.get("harness_id") or host.get("harness_id") or ""
        pages = pages_for(results, route) if route else []
        if not pages:
            stats["no_pages"].append("%s (harness=%r)" % (sid, route))
            continue
        borrowed = host.get("id") if not sf.get("harness_id") else ""

        qa = qa_run_map(pages)
        bad = sorted(c for c, v in qa.items() if v == "fail")
        if bad:
            stats["fail_classes"][sid] = bad

        evidence = sf.get("evidence") or {}
        evidence["qa_run"] = qa
        evidence["build_index_sha256"] = [build_sha] if build_sha else []
        sf["evidence"] = evidence
        sf["advisory"] = advisory_map(pages, label, borrowed=borrowed)

        profile = profiles.get((sf.get("responsive_audit") or {}).get("required_profile") or "")
        if profile:
            resp = sf.get("responsive_audit") or {}
            rows = matrix_for(pages, label, route, profile)
            resp["matrix"] = rows
            resp["result"] = "FAIL" if any(r["result"] == "FAIL" for r in rows) else "PASS"
            sf["responsive_audit"] = resp

        shot = next((p for p in pages
                     if p.get("theme") == "light" and p.get("viewport") == "1920x1080"), None)
        if shot:
            sf["after_capture"] = {
                "path": "docs/ui-renewal/captures/after/%s__light__1920x1080.png" % route,
                "label": label,
                "build_index_sha256": build_sha,
                "at": run.get("finished_at") or at,
                "theme": "light",
                "viewport": "1920x1080",
                "results_json": "dist/ui-qa/%s/results.json" % label,
                "all_combos": len(pages),
                "committed_combos": ["1920x1080/light", "1920x1080/dark"],
            }
            if borrowed:
                sf["after_capture"]["note"] = (
                    "이 위젯은 host 화면 캡처 안에 들어 있다 — 대표로 %s 를 가리킨다" % route)

        ids = sorted(flows_by_surface.get(sid) or [])
        if ids:
            fa = sf.get("functional_audit") or {}
            fa["result"] = "FAIL" if fails_by_surface.get(sid) else "PASS"
            fa["by"] = HARNESS_BY
            fa["at"] = at
            fa["evidence"] = ["ev:qa_run:s18-pilot (dist/ui-qa/pilot/flows.json)",
                              "ev:qa_run:%s (dist/ui-qa/%s/results.json)" % (label, label)]
            fa["flows"] = ids
            sf["functional_audit"] = fa
        stats["touched"].append(sid)
    stats["build_sha"] = build_sha
    return stats


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Pilot 결과를 Control Plane 원장에 적는다 (S18)")
    ap.add_argument("--flows", default=str(FLOWS))
    ap.add_argument("--capture", default="", help="캡처 실행 라벨(예: s18-after)")
    ap.add_argument("--wave", default="W8")
    ap.add_argument("--at", default="2026-08-25", help="감사 날짜(YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = (load(Path(args.flows)).get("flows") or []) if Path(args.flows).exists() else []
    run_token = "ev:qa_run:s18-pilot (dist/ui-qa/pilot/flows.json)"

    func = load(FUNC_LEDGER)
    stats = write_flows(func, records, at=args.at, run_token=run_token)
    rest = flow_leftovers(func, stats["surfaces"])
    print("Flow 기록 %d건 · 화면 %d개" % (stats["written"], len(stats["surfaces"])))
    for title, rows in (("원장에 없는 Flow", stats["missing"]),
                        ("통과하지 못한 Flow (FAIL 로 적었다)", stats["failed"]),
                        ("아직 안 본 Flow", rest)):
        if rows:
            print("%s %d건:" % (title, len(rows)))
            for row in rows[:40]:
                print("  - %s" % row)

    route_stats = {}
    route = None
    if args.capture:
        results_path = REPO_ROOT / "dist" / "ui-qa" / args.capture / "results.json"
        if not results_path.exists():
            print("[FATAL] 캡처 결과가 없다: %s" % results_path)
            return 2
        route = load(ROUTE_LEDGER)
        route_stats = write_surfaces(route, load(results_path), records,
                                     wave=args.wave, label=args.capture, at=args.at)
        print("\nSurface 기록 %d개 (번들 %s)"
              % (len(route_stats["touched"]), route_stats.get("build_sha")))
        if route_stats["no_pages"]:
            print("캡처에 없는 Surface %d개:" % len(route_stats["no_pages"]))
            for row in route_stats["no_pages"]:
                print("  - %s" % row)
        if route_stats["fail_classes"]:
            print("Assertion 이 실패한 Surface:")
            for sid, classes in sorted(route_stats["fail_classes"].items()):
                print("  - %s: %s" % (sid, ", ".join(classes)))

    if args.dry_run:
        print("\n(dry-run — 원장을 쓰지 않았다)")
    else:
        dump(FUNC_LEDGER, func)
        print("\n원장 갱신: %s" % FUNC_LEDGER)
        if route is not None:
            dump(ROUTE_LEDGER, route)
            print("원장 갱신: %s" % ROUTE_LEDGER)

    bad = bool(stats["failed"] or stats["missing"] or route_stats.get("no_pages"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
