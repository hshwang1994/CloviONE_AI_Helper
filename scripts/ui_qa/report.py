"""Render ``dist/ui-qa/<label>/report.html`` — a self-contained contact sheet.

Everything is inlined (CSS in a <style> block, thumbnails as base64 data URIs),
so the file opens by double-clicking with no network at all. Full-size PNGs are
linked relatively next to the report for click-through.
"""

from __future__ import annotations

import base64
import html
import io
import json
from datetime import datetime
from pathlib import Path

try:  # Pillow only used to shrink screenshots into embeddable thumbnails
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover - degraded but still usable
    Image = None
    HAVE_PIL = False

THUMB_WIDTH = 320
# Full-page screenshots of long screens are extremely tall; showing the top
# 1.6 viewport-widths keeps every tile the same shape and readable.
THUMB_MAX_ASPECT = 1.6

STYLE = """
:root { color-scheme: light dark; --bg:#0f1115; --panel:#171a21; --line:#2a2f3a;
  --fg:#e6e8ee; --muted:#98a1b3; --ok:#3fb950; --bad:#f85149; --skip:#6e7681;
  --accent:#7aa2f7; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.55 "Segoe UI",
  "Malgun Gothic", system-ui, sans-serif; }
header { padding:20px 24px; border-bottom:1px solid var(--line); background:var(--panel); }
h1 { margin:0 0 6px; font-size:20px; }
h2 { margin:28px 0 10px; font-size:16px; }
.meta { color:var(--muted); font-size:12.5px; }
.meta code { color:var(--accent); }
main { padding:0 24px 48px; }
table { border-collapse:collapse; width:100%; margin:8px 0 4px; font-size:13px; }
th, td { border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top; }
th { background:#1d2129; font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.pass { color:var(--ok); }
.fail { color:var(--bad); font-weight:700; }
.skip { color:var(--skip); }
tr.has-fail td { background:#2a1518; }
.badge { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11.5px;
  border:1px solid var(--line); color:var(--muted); }
.badge.fail { background:#3d1d20; border-color:#6b2a2f; color:#ffb3b3; }
.badge.ok { background:#12301b; border-color:#1f5c30; color:#9be5ac; }
.sheet { overflow-x:auto; border:1px solid var(--line); border-radius:8px;
  background:var(--panel); padding:12px; }
.sheet-grid { display:grid; gap:10px; align-items:start; }
.colhead { position:sticky; top:0; font-size:12px; color:var(--muted); padding-bottom:4px;
  text-align:center; }
.rowhead { font-size:12.5px; padding-top:6px; }
.rowhead b { display:block; font-size:13px; color:var(--fg); }
.rowhead span { color:var(--muted); }
.tile { border:1px solid var(--line); border-radius:6px; overflow:hidden; background:#0b0d11;
  position:relative; }
.tile.bad { border-color:var(--bad); box-shadow:0 0 0 1px var(--bad) inset; }
.tile img { display:block; width:100%; height:auto; }
.tile .cap { font-size:11px; padding:3px 6px; color:var(--muted);
  border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:6px; }
.tile .cap .fail { color:#ffb3b3; }
.missing { display:flex; align-items:center; justify-content:center; min-height:120px;
  color:var(--muted); font-size:12px; text-align:center; padding:10px; }
details { margin:10px 0; }
summary { cursor:pointer; color:var(--accent); }
ul.samples { margin:4px 0 0 16px; padding:0; color:var(--muted); font-size:12px; }
ul.samples li { word-break:break-all; }
.note { color:var(--muted); font-size:12px; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f6f7f9; --panel:#fff; --line:#d8dce3; --fg:#1b1f27; --muted:#5b6472;
    --accent:#2f5fd0; }
  th { background:#eef1f5; }
  tr.has-fail td { background:#fdeceb; }
  .tile { background:#fff; }
  .badge.fail { background:#fdeceb; border-color:#f3b6b1; color:#8f1d16; }
  .badge.ok { background:#e9f7ec; border-color:#a9dcb6; color:#1c6b30; }
}
"""


def _thumbnail_data_uri(png_path: Path) -> str | None:
    if not png_path.exists():
        return None
    if not HAVE_PIL:
        return None
    try:
        with Image.open(png_path) as im:
            im = im.convert("RGB")
            max_height = int(im.width * THUMB_MAX_ASPECT)
            if im.height > max_height:
                im = im.crop((0, 0, im.width, max_height))
            ratio = THUMB_WIDTH / im.width
            size = (THUMB_WIDTH, max(1, int(im.height * ratio)))
            im = im.resize(size, Image.LANCZOS)
            buffer = io.BytesIO()
            im.save(buffer, format="JPEG", quality=72, optimize=True)
    except Exception:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _fail_classes(record: dict) -> list[str]:
    return [name for name, verdict in (record.get("assertions") or {}).items()
            if verdict.get("status") == "fail"]


def _summary_table(summary: dict) -> str:
    rows = []
    for name, counts in summary.items():
        failed = counts.get("fail", 0)
        rows.append(
            f'<tr class="{"has-fail" if failed else ""}">'
            f"<td><code>{html.escape(name)}</code></td>"
            f'<td class="num pass">{counts.get("pass", 0)}</td>'
            f'<td class="num {"fail" if failed else ""}">{failed}</td>'
            f'<td class="num skip">{counts.get("skip", 0)}</td></tr>'
        )
    return ("<table><thead><tr><th>검사 항목</th><th>통과</th><th>실패</th><th>건너뜀</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def _failure_table(records: list[dict]) -> str:
    rows = []
    for record in records:
        for name, verdict in (record.get("assertions") or {}).items():
            if verdict.get("status") != "fail":
                continue
            samples = verdict.get("samples") or []
            sample_html = ""
            if samples:
                items = "".join(f"<li>{html.escape(str(s))}</li>" for s in samples)
                sample_html = f'<ul class="samples">{items}</ul>'
            rows.append(
                "<tr class='has-fail'>"
                f"<td>{html.escape(record.get('label') or '')}<br>"
                f"<span class='note'>{html.escape(record.get('route',''))}</span></td>"
                f"<td>{html.escape(record.get('theme',''))}</td>"
                f"<td>{html.escape(record.get('viewport',''))}</td>"
                f"<td><code class='fail'>{html.escape(name)}</code></td>"
                f"<td class='num'>{verdict.get('count', 0)}</td>"
                f"<td>{html.escape(verdict.get('note') or '')}{sample_html}</td>"
                "</tr>"
            )
    if not rows:
        return "<p class='note'>실패한 검사가 없습니다.</p>"
    return ("<table><thead><tr><th>화면</th><th>테마</th><th>뷰포트</th><th>검사</th>"
            "<th>건수</th><th>내용</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def _contact_sheet(records: list[dict], out_root: Path, columns: list[tuple[str, str]]) -> str:
    by_route: dict[str, dict] = {}
    order: list[str] = []
    for record in records:
        route_id = record["route"]
        if route_id not in by_route:
            by_route[route_id] = {"label": record.get("label", route_id),
                                  "console": record.get("console_kind", ""),
                                  "hash": record.get("hash_path", ""), "cells": {}}
            order.append(route_id)
        by_route[route_id]["cells"][(record.get("theme"), record.get("viewport"))] = record

    head = ['<div class="rowhead"></div>']
    for theme, viewport in columns:
        head.append(f'<div class="colhead">{html.escape(theme)}<br>{html.escape(viewport)}</div>')

    body = []
    for route_id in order:
        entry = by_route[route_id]
        body.append(
            f'<div class="rowhead"><b>{html.escape(entry["label"])}</b>'
            f'<span>{html.escape(entry["console"])} · {html.escape(entry["hash"])}<br>'
            f'{html.escape(route_id)}</span></div>'
        )
        for key in columns:
            record = entry["cells"].get(key)
            if record is None:
                body.append('<div class="tile"><div class="missing">촬영 안 함</div></div>')
                continue
            failures = _fail_classes(record)
            rel = record.get("screenshot")
            uri = _thumbnail_data_uri(out_root / rel) if rel else None
            if uri:
                img = (f'<a href="{html.escape(rel)}" target="_blank" rel="noopener">'
                       f'<img src="{uri}" alt="{html.escape(record.get("label", ""))}"></a>')
            elif rel:
                img = (f'<a href="{html.escape(rel)}" target="_blank" rel="noopener">'
                       f'<div class="missing">썸네일 생성 실패<br>PNG 열기</div></a>')
            else:
                reason = record.get("screenshot_error") or record.get("error") or "스크린샷 없음"
                img = f'<div class="missing">{html.escape(str(reason)[:120])}</div>'
            cap_right = (f'<span class="fail">{len(failures)} FAIL</span>' if failures
                         else '<span>OK</span>')
            body.append(
                f'<div class="tile {"bad" if failures else ""}">{img}'
                f'<div class="cap"><span>{html.escape(record.get("viewport", ""))}</span>'
                f"{cap_right}</div></div>"
            )

    template_columns = f"180px repeat({len(columns)}, {THUMB_WIDTH}px)"
    return (f'<div class="sheet"><div class="sheet-grid" style="grid-template-columns:'
            f'{template_columns}">' + "".join(head) + "".join(body) + "</div></div>")


def build(results: dict, out_root: Path) -> Path:
    """Write report.html next to results.json and return its path."""
    out_root = Path(out_root)
    records = results.get("pages") or []
    columns: list[tuple[str, str]] = []
    for record in records:
        key = (record.get("theme"), record.get("viewport"))
        if key not in columns:
            columns.append(key)

    meta = results.get("run") or {}
    fail_total = sum(len(_fail_classes(r)) for r in records)
    thumbs = sum(1 for r in records if r.get("screenshot"))
    generated = str(meta.get("finished_at") or datetime.now().isoformat(timespec="seconds"))
    build = meta.get("build_before") or {}

    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>UI QA · {html.escape(str(meta.get('label', '')))}</title>",
        f"<style>{STYLE}</style></head><body>",
        "<header><h1>ClovirONE UI 시각/기하 QA 리포트</h1>",
        "<div class='meta'>",
        f"label <code>{html.escape(str(meta.get('label', '')))}</code> · ",
        f"생성 {html.escape(generated)} · ",
        f"base-url <code>{html.escape(str(meta.get('base_url', '')))}</code> · ",
        f"계정 <code>{html.escape(str(meta.get('account', '')))}</code> "
        f"(role={html.escape(str(meta.get('role', '')))})<br>",
        f"번들 <code>{html.escape(str(build.get('index_sha256', '?')))}</code> "
        f"({html.escape(str(build.get('index_mtime', '?')))})<br>",
        f"페이지 {len(records)}개 · 스크린샷 {thumbs}개 · 실패 검사 {fail_total}건",
        "</div></header><main>",
        "<h2>검사 요약</h2>",
        _summary_table(results.get("summary") or {}),
        "<h2>실패 상세</h2>",
        _failure_table(records),
        "<h2>콘택트 시트</h2>",
    ]
    if not HAVE_PIL:
        parts.append("<p class='note'>Pillow가 없어 썸네일을 인라인하지 못했습니다 "
                     "(<code>pip install Pillow</code>). PNG 링크만 제공합니다.</p>")
    parts.append(_contact_sheet(records, out_root, columns))
    notes = results.get("notes") or []
    if notes:
        items = "".join(f"<li>{html.escape(str(n))}</li>" for n in notes)
        parts.append(f"<h2>실행 메모</h2><ul class='samples'>{items}</ul>")
    parts.append("</main></body></html>")

    path = out_root / "report.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """``python -m scripts.ui_qa.report --label pre`` — rebuild HTML from results.json."""
    import argparse

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="results.json → report.html")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--out-dir", default=str(repo_root / "dist" / "ui-qa"))
    args = parser.parse_args(argv)

    out_root = Path(args.out_dir) / args.label
    results = json.loads((out_root / "results.json").read_text(encoding="utf-8"))
    path = build(results, out_root)
    print(f"{path}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
