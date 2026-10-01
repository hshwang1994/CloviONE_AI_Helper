"""최종 시각 수용(8.5 · D-553)의 대조표와 판정 기록 틀을 만든다.

자동 검증(치수 · 조합 · 시각 규율 프로브, Playwright, 스크린샷 비교)을 모두 통과한 **뒤에** 사람이 최종 스크린샷을 본다. 이
스크립트는 그 일을 돕는 두 파일을 만든다 — 판정은 하지 않는다.

    dist/ui-qa/<label>/review.html                 화면(· 상태) × 폭 스크린샷 대조표. 칸마다 시각 규율 프로브의 실패와 보고값
                                                   (판 수 · 상태색 갈래 · 빈 판 · 보라 면적 · 첫 데이터 윗변)을 곁에 둔다
    dist/ui-qa/<label>/visual-acceptance-template.md  판정 기록 틀(화면 · 상태 · 폭 · 열다섯 항목 · 판정 · 발견 · 고친 커밋).
                                                   채운 기록은 `docs/platform/EVIDENCE/ui/<날짜>-visual-acceptance.md` 로 옮긴다

쓰는 법:

    python -m scripts.ui_qa.local_capture --label ux-after --routes … --viewports 1366x768 1600x900 1920x1080 2560x1440
    python -m scripts.ui_qa.local_capture --harness kit_measure --measure-label ux-after-measure --routes … --viewports …
    python -m scripts.ui_qa.visual_review --label ux-after --measure ux-after-measure

1366 · 1920 은 전부 눈으로 보고, 1600 · 2560 은 프로브 보고가 걸린 칸만 본다(8.5). 사용자도 같은 대조표를 열 수 있다.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.visual_probes import VISUAL_CHECKS  # noqa: E402

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"

# 8.5 의 열다섯 항목. 하나라도 보이면 그 화면의 UI 는 완료가 아니다.
ITEMS = (
    "화면의 첫 시선이 이상함",
    "주 동작을 찾기 어려움",
    "입력과 단추가 어긋나 보임",
    "라벨 시작점이 다름",
    "카드가 너무 많음",
    "빈 공간이 너무 큼",
    "보라 면적이 과함",
    "첫 열이 다시 폭을 독점함",
    "중요한 값이 잘림",
    "필터 폭이 이상함",
    "상태색이 너무 많음",
    "설명이 너무 김",
    "단추가 떠 있는 것처럼 보임",
    "화면마다 밀도가 다름",
    "생성형 AI 가 쓴 것 같은 문구가 남음",
)
# 사람이 전부 보는 폭(8.5). 나머지 폭은 프로브 보고가 걸린 칸만 본다.
HUMAN_VIEWPORTS = ("1366x768", "1920x1080")


def load_pages(label: str) -> list[dict]:
    results = OUT_BASE / label / "results.json"
    data = json.loads(results.read_text(encoding="utf-8"))
    return [p for p in data.get("pages", []) if p.get("screenshot")]


def load_measure(label: str | None) -> dict:
    if not label:
        return {}
    path = OUT_BASE / label / "measure.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("pages", {})


def probe_note(measured: dict | None) -> tuple[list[str], dict]:
    """(실패 문장 목록, 보고값)."""
    if not measured:
        return [], {}
    fails = []
    for name in VISUAL_CHECKS:
        got = measured.get(name) or {}
        for sample in (got.get("bad") or [])[:3]:
            fails.append(f"{name}: {sample.get('problem', '')}")
    report = dict(measured.get("visual_report") or {})
    if "first_data_top" in measured:
        report["first_data_top"] = measured["first_data_top"]
    return fails, report


def build(label: str, measure_label: str | None) -> tuple[Path, Path]:
    pages = load_pages(label)
    measured = load_measure(measure_label)
    routes: dict[str, dict] = {}
    viewports: list[str] = []
    for p in pages:
        key = p["route"] + (f" · {p['state']}" if p.get("state") else "")
        routes.setdefault(key, {"label": p.get("label") or p["route"], "cells": {}})
        routes[key]["cells"][p["viewport"]] = p
        if p["viewport"] not in viewports:
            viewports.append(p["viewport"])
    viewports.sort(key=lambda v: int(v.split("x")[0]))

    rows = []
    for key, entry in routes.items():
        cells = []
        for vp in viewports:
            page = entry["cells"].get(vp)
            if not page:
                cells.append("<td class='none'>없음</td>")
                continue
            theme = page.get("theme", "light")
            fails, report = probe_note(measured.get(f"{page['route']}__{theme}__{vp}"))
            human = vp in HUMAN_VIEWPORTS or bool(fails)
            notes = "".join(f"<li class='fail'>{html.escape(f)}</li>" for f in fails)
            if report:
                notes += ("<li>판 {s} · 상태색 {c} · 빈 판 {e} · 보라 {b}%{t}</li>".format(
                    s=report.get("surface_count", "?"), c=report.get("status_color_count", "?"),
                    e=report.get("empty_plate", "?"), b=report.get("brand_pct", "?"),
                    t=f" · 첫 데이터 {report['first_data_top']}px" if "first_data_top" in report else ""))
            shot = html.escape(page["screenshot"])
            cells.append(
                f"<td class='{'human' if human else 'probe'}'><a href='{shot}' target='_blank'>"
                f"<img loading='lazy' src='{shot}' alt='{html.escape(entry['label'])} {vp}'></a>"
                f"<div class='tag'>{'눈으로 봄' if human else '프로브만'}</div><ul>{notes}</ul></td>")
        rows.append(f"<tr><th scope='row'>{html.escape(entry['label'])}<div class='key'>{html.escape(key)}</div></th>{''.join(cells)}</tr>")

    items = "".join(f"<li>{html.escape(t)}</li>" for t in ITEMS)
    head = "".join(f"<th scope='col'>{vp}</th>" for vp in viewports)
    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>시각 수용 대조표 {html.escape(label)}</title>
<style>
  body {{ font-family: Pretendard, system-ui, sans-serif; margin: 24px; color: #1c2033; background: #eef0f7; word-break: keep-all; }}
  h1 {{ font-size: 22px; }}
  table {{ border-collapse: collapse; background: #fff; }}
  th, td {{ border: 1px solid #dcdfec; padding: 8px; vertical-align: top; }}
  th[scope=row] {{ text-align: left; min-width: 10rem; }}
  .key {{ font-size: 12px; color: #6b7083; font-weight: 400; }}
  img {{ width: 360px; display: block; border: 1px solid #dcdfec; }}
  td.probe img {{ opacity: .75; }}
  .tag {{ font-size: 12px; color: #6b7083; margin-top: 4px; }}
  ul {{ margin: 4px 0 0; padding-left: 18px; font-size: 12px; max-width: 360px; }}
  li.fail {{ color: #c62828; }}
  td.none {{ color: #6b7083; }}
  ol {{ background: #fff; border: 1px solid #dcdfec; padding: 12px 12px 12px 36px; max-width: 48rem; }}
</style></head><body>
<h1>시각 수용 대조표 — {html.escape(label)}</h1>
<p>열다섯 항목 중 하나라도 보이면 그 화면의 UI 는 완료가 아닙니다. 1366 · 1920 은 전부 눈으로 보고, 나머지 폭은 프로브가 걸린 칸만 봅니다.</p>
<ol>{items}</ol>
<table><thead><tr><th scope="col">화면</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>
"""
    out_dir = OUT_BASE / label
    review = out_dir / "review.html"
    review.write_text(doc, encoding="utf-8")

    lines = [
        f"# 시각 수용 판정 기록 — {label}",
        "",
        "판정 규칙은 계획 8.5 다. 항목 번호는 아래 목록이고, 칸에는 걸린 항목 번호만 적는다(없으면 「없음」).",
        "",
        *[f"{i + 1}. {t}" for i, t in enumerate(ITEMS)],
        "",
        "| 화면 | 상태 | 폭 | 걸린 항목 | 판정 | 발견 | 고친 커밋 |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, entry in routes.items():
        state = key.split(" · ", 1)[1] if " · " in key else "기본"
        for vp in viewports:
            if vp in HUMAN_VIEWPORTS and vp in entry["cells"]:
                lines.append(f"| {entry['label']} | {state} | {vp} |  |  |  |  |")
    template = out_dir / "visual-acceptance-template.md"
    template.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return review, template


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="최종 시각 수용 대조표 · 판정 기록 틀")
    ap.add_argument("--label", required=True, help="local_capture 의 라벨(dist/ui-qa/<label>/results.json)")
    ap.add_argument("--measure", default=None, help="kit_measure 의 라벨(dist/ui-qa/<label>/measure.json, 선택)")
    args = ap.parse_args(argv)
    review, template = build(args.label, args.measure)
    print(f"VISUAL_REVIEW_OK review={review} template={template}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
