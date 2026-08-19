"""QA 실행의 Assertion 실패를 `ROUTE_COVERAGE.json` 의 Surface Finding 으로 **합친다**.

## 왜 스크립트인가

`run.py --findings-out` 은 실패 하나를 stub 하나로 남긴다 — (class, surface, route, theme,
viewport) 단위라 한 실행에 수백 건이다. Control Plane 이 추적하는 것은 그 수백 건이 아니라
**"이 화면의 이 클래스가 아직 깨져 있는가"** 이고, 그래서 `ROUTE_COVERAGE` 는 (class, surface)
로 접은 행을 갖는다(`detail` 에 발화한 조합을 적는다).

W0 은 그 접기를 손으로 했다. Wave 마다 다시 손으로 하면 두 가지가 반드시 일어난다:
① 새로 깨진 것을 빠뜨린다 ② **고쳐진 것을 안 닫는다.** 둘 다 Coverage 를 거짓말하게 만들고,
`C10` 은 "행을 지워서 finding 을 닫을 수 없게" 만들어 두었을 뿐 **닫아야 할 것을 닫는 일**은
아무도 하지 않는다.

## 판정 규칙 (정직성)

* **다시 측정한 것만 판정한다.** 이번 실행이 그 (surface, class) 를 한 번도 재지 않았으면
  기존 행에 손대지 않는다 — 좁은 재실행이 전체 목록을 조용히 닫아 버리는 것을 막는다.
  (`run.py::dropped_unseen` 이 findings 파일에서 지키는 규율과 같은 것이다.)
* **`skip` 은 통과가 아니다.** 전부 skip 이면 "재지 않았다" 로 본다.
* 여전히 실패면 `detail`·`samples` 를 이번 실측으로 **갱신**하고 `first_seen` 은 보존한다.
* 재측정했는데 전부 통과면 `status: CLOSED` + `closed_by` 에 실행 라벨을 남긴다. 행을 지우지
  않는다 — 닫힌 이력이 남아야 다음에 되살아났을 때 "다시 깨졌다"고 말할 수 있다.
* 사람이 등록한 Finding(`detected_by` 가 Assertion 이 아닌 것)은 건드리지 않는다.

## 쓰는 법

    python scripts/merge_qa_findings.py --label w2-after            # 미리보기
    python scripts/merge_qa_findings.py --label w2-after --write
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COVERAGE = ROOT / "docs" / "ui-renewal" / "ROUTE_COVERAGE.json"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def finding_id(cls: str, surface_id: str) -> str:
    """(class, surface) 하나에 id 하나. 실행이 바뀌어도 같은 결함은 같은 id 다."""
    key = "%s|%s" % (cls, surface_id)
    return "F-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:9]


def load_results(label: str) -> dict:
    path = ROOT / "dist" / "ui-qa" / label / "results.json"
    if not path.exists():
        raise SystemExit("[FAIL] 실행 결과가 없다: %s" % path)
    return json.loads(io.open(path, encoding="utf-8").read())


def route_to_surface() -> dict[str, str]:
    from scripts.ui_qa import routes as routes_mod  # noqa: PLC0415
    return {r["id"]: (r.get("surface_id") or r["id"]) for r in routes_mod.inventory()}


def measure(results: dict, mapping: dict[str, str]) -> tuple[dict, dict]:
    """(surface, class) -> 조합별 판정 / 실패 조합의 상세."""
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    detail: dict[tuple[str, str], dict] = {}
    for page in results.get("pages") or []:
        route = page.get("route") or "?"
        sid = mapping.get(route, route)
        combo = "%s/%s" % (page.get("viewport"), page.get("theme"))
        for cls, verdict in (page.get("assertions") or {}).items():
            status = (verdict or {}).get("status", "?")
            seen[(sid, cls)].append(status)
            if status != "fail":
                continue
            slot = detail.setdefault((sid, cls), {"combos": [], "samples": [], "note": "",
                                                  "label": page.get("label") or route,
                                                  "count": 0})
            slot["combos"].append(combo)
            slot["count"] += verdict.get("count") or 0
            if not slot["samples"]:
                slot["samples"] = list(verdict.get("samples") or [])[:5]
            if not slot["note"]:
                slot["note"] = (verdict.get("note") or "").strip()
    return seen, detail


# W4 종료 조건 — "`surface_repetition`·`oversized_empty_surface` Advisory 수치가 Surface 별로
# 기록됨". Finding 은 **실패한 것만** 남기므로 통과한 Surface 는 아무 값도 남기지 않는다.
# 그래서 이 두 클래스는 판정과 별개로 **잰 숫자 자체**를 Surface 에 적는다 — 다음 Wave 가
# "좋아졌는가" 를 물을 때 비교할 수 있는 값이 있어야 한다.
ADVISORY_CLASSES = ("surface_repetition", "oversized_empty_surface")


def measure_advisory(results: dict, mapping: dict[str, str]) -> dict:
    """(surface, class) -> {pass, fail, skip, note, worst_combo}."""
    out: dict[tuple[str, str], dict] = {}
    for page in results.get("pages") or []:
        route = page.get("route") or "?"
        sid = mapping.get(route, route)
        combo = "%s/%s" % (page.get("viewport"), page.get("theme"))
        for cls in ADVISORY_CLASSES:
            verdict = (page.get("assertions") or {}).get(cls)
            if not verdict:
                continue
            slot = out.setdefault((sid, cls), {"pass": 0, "fail": 0, "skip": 0,
                                               "note": "", "worst_combo": ""})
            status = verdict.get("status", "skip")
            slot[status] = slot.get(status, 0) + 1
            # fail 이 있으면 그 노트를, 없으면 첫 pass 노트를 대표로 남긴다.
            note = (verdict.get("note") or "").strip()
            if status == "fail" and (not slot["note"] or slot["worst_combo"] == ""
                                     or slot.get("_kind") != "fail"):
                slot["note"], slot["worst_combo"], slot["_kind"] = note, combo, "fail"
            elif status == "pass" and slot.get("_kind") != "fail" and not slot["note"]:
                slot["note"], slot["worst_combo"], slot["_kind"] = note, combo, "pass"
    for slot in out.values():
        slot.pop("_kind", None)
    return out


SEVERITY_BY_CLASS_PATH = ROOT / "scripts" / "ui_qa" / "run.py"


def severity_of(cls: str) -> str:
    from scripts.ui_qa.run import SEVERITY_BY_CLASS, SEVERITY_DEFAULT  # noqa: PLC0415
    return SEVERITY_BY_CLASS.get(cls, SEVERITY_DEFAULT).capitalize()


def main() -> int:
    ap = argparse.ArgumentParser(description="QA 실패를 Surface Finding 으로 합친다")
    ap.add_argument("--label", required=True, help="dist/ui-qa/<label>")
    ap.add_argument("--write", action="store_true", help="실제로 ROUTE_COVERAGE.json 을 고친다")
    args = ap.parse_args()

    results = load_results(args.label)
    mapping = route_to_surface()
    seen, detail = measure(results, mapping)
    advisory = measure_advisory(results, mapping)
    coverage = json.loads(io.open(COVERAGE, encoding="utf-8").read())

    stats = {"closed": 0, "refreshed": 0, "added": 0, "untouched_not_remeasured": 0,
             "manual_skipped": 0, "advisory": 0}
    closed_rows: list[str] = []
    added_rows: list[str] = []

    for surface in coverage.get("surfaces") or []:
        sid = surface.get("id")

        # Advisory 수치 — 판정과 무관하게 **잰 값**을 남긴다(W4 종료 조건).
        #
        # 위젯 Surface(`shell_topbar`·`shell_sidebar`·`kit_primitives`)는 자기 Route 가 없다 —
        # 전 화면에 렌더되는 그릇이라 캡처를 **host 화면에서 빌린다**(각 Surface 의
        # `after_capture.note` 가 그렇게 적혀 있다). 그래서 route -> surface 매핑만으로는
        # 이 셋에 영원히 수치가 안 붙고, C10b 가 영원히 빨갛다. 대표 host 의 수치를 그대로
        # 쓰고 어느 화면에서 빌렸는지 `borrowed_from` 에 남긴다 — 빌린 값을 자기 값인 척
        # 하지 않는다.
        host = None
        if not any((sid, c) in advisory for c in ADVISORY_CLASSES):
            path = ((surface.get("after_capture") or {}).get("path")
                    or (surface.get("before_capture") or {}).get("path") or "")
            stem = path.rsplit("/", 1)[-1].split("__", 1)[0]
            if stem and any((stem, c) in advisory for c in ADVISORY_CLASSES):
                host = stem

        for cls in ADVISORY_CLASSES:
            slot = advisory.get((sid, cls)) or (advisory.get((host, cls)) if host else None)
            if not slot:
                continue
            surface.setdefault("advisory", {})[cls] = {
                "label": args.label,
                **({"borrowed_from": host} if host else {}),
                "pass": slot["pass"], "fail": slot["fail"], "skip": slot["skip"],
                "measured_note": slot["note"],
                "sample_combo": slot["worst_combo"],
            }
            stats["advisory"] += 1

        rows = surface.get("findings") or []
        by_class = {}
        for row in rows:
            cls = row.get("class")
            detected = str(row.get("detected_by") or "")
            if "Assertion" not in detected:
                stats["manual_skipped"] += 1
                continue
            by_class.setdefault(cls, []).append(row)

        for cls, group in by_class.items():
            statuses = seen.get((sid, cls))
            if not statuses or all(s == "skip" for s in statuses):
                stats["untouched_not_remeasured"] += len(group)
                continue
            hit = detail.get((sid, cls))
            for row in group:
                if hit:
                    row["status"] = "OPEN"
                    row["detail"] = "조합 %d/%d 에서 발화: %s" % (
                        len(hit["combos"]), len(statuses), ", ".join(sorted(hit["combos"])))
                    row["samples"] = hit["samples"]
                    row["last_seen"] = "ev:qa_run:%s" % args.label
                    stats["refreshed"] += 1
                else:
                    if row.get("status") != "CLOSED":
                        closed_rows.append("%s / %s" % (sid, cls))
                    row["status"] = "CLOSED"
                    row["closed_by"] = sorted(set((row.get("closed_by") or [])
                                                  + ["ev:qa_run:%s" % args.label]))
                    row["last_seen"] = "ev:qa_run:%s" % args.label
                    stats["closed"] += 1

        for (msid, cls), hit in detail.items():
            if msid != sid or cls in by_class:
                continue
            statuses = seen.get((sid, cls)) or []
            row = {
                "id": finding_id(cls, sid),
                "class": cls,
                "severity": severity_of(cls),
                "title": "%s — %s %d건%s" % (
                    cls, hit["label"], hit["count"],
                    (" — " + hit["note"]) if hit["note"] else ""),
                "detail": "조합 %d/%d 에서 발화: %s" % (
                    len(hit["combos"]), len(statuses), ", ".join(sorted(hit["combos"]))),
                "samples": hit["samples"],
                "detected_by": "%s (Assertion)" % args.label,
                "first_seen": "ev:qa_run:%s (dist/ui-qa/%s/results.json)" % (args.label, args.label),
                "last_seen": "ev:qa_run:%s" % args.label,
                "requirement_ids": [],
                "status": "OPEN",
                "closed_by": [],
                "accepted_reason": None,
                "wave": surface.get("wave"),
            }
            surface.setdefault("findings", []).append(row)
            added_rows.append("%s / %s (%s)" % (sid, cls, row["severity"]))
            stats["added"] += 1

    print("== QA Finding 병합 (label=%s) ==" % args.label)
    print("  갱신 %(refreshed)d · 신규 %(added)d · 종료 %(closed)d · "
          "재측정 안 함(그대로) %(untouched_not_remeasured)d · 사람 등록(건드리지 않음) %(manual_skipped)d"
          % stats)
    print("  Advisory 수치 기록 %d건 (%s)" % (stats["advisory"], " · ".join(ADVISORY_CLASSES)))
    for row in sorted(closed_rows)[:40]:
        print("   [CLOSED] " + row)
    for row in sorted(added_rows)[:40]:
        print("   [NEW]    " + row)
    if len(added_rows) > 40:
        print("   ... 신규 %d건 더" % (len(added_rows) - 40))

    if args.write:
        io.open(COVERAGE, "w", encoding="utf-8").write(
            json.dumps(coverage, ensure_ascii=False, indent=1) + "\n")
        print("MERGE_WRITTEN %s" % COVERAGE)
    else:
        print("(미리보기 — 실제로 고치려면 --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
