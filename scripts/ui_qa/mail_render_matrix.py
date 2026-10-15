"""메일 틀 렌더 매트릭스 (D-571) — 표본 전부(`app/mail/samples.PREVIEW_KINDS`)를 밝음 · 어둠으로 내고 Chromium 으로 찍어 잰다.

실제 발송과 같은 그리기 함수(`content.render`)로 HTML 을 만든다. 메일 서버도 DB 도 없다 - 표본 재료만 쓴다(`samples.py`).

    .venv/Scripts/python.exe -m scripts.ui_qa.mail_render_matrix                       # dist/ui-qa/mail-templates/<시각>/
    .venv/Scripts/python.exe -m scripts.ui_qa.mail_render_matrix --kinds test invite    # 몇 종류만
    .venv/Scripts/python.exe -m scripts.ui_qa.mail_render_matrix --no-shots             # HTML 만(Outlook 렌더 입력)

나오는 것:
  src/<종류>.html      실제 메일과 같은 HTML(로고는 `cid:`) - `scripts/ui_qa/outlook_render.ps1` 의 입력이다.
  src/mark-72.png      CID 로 붙일 로고 그림. src/manifest.json 은 종류 · 제목 · 파일 · CID 목록.
  shots/<종류>-<보기>-<폭>.png   보기 셋 × 폭 600 · 375. 보기: light(밝음), dark(`prefers-color-scheme` - Apple 메일 등),
                       forced(`data-ogsc` - Outlook.com · 새 Outlook 의 강제 다크 규칙).
  report.json · report.md   찍은 것마다 가로 넘침 · 단추 높이(44±1) · 단추 글자색(흰색) · 단추 바탕(보라) · 머리 띠(흰색) ·
                       로고와 워드마크의 세로 가운데 차이 · 사실 상자 행 높이.
판정 실패가 하나라도 있으면 종료 코드 1 이다(`MAIL_MATRIX_OK` / `MAIL_MATRIX_FAILED`).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_BASE = "https://mail-preview.example.com"
SAMPLE_SUPPORT = "help@example.com"
WIDTHS = (600, 375)
VIEWS = ("light", "dark", "forced")
PURPLE = "rgb(90, 79, 207)"
WHITE = "rgb(255, 255, 255)"

# 한 장을 재는 스크립트 - 단추 · 머리 띠 · 로고 · 사실 행. 값이 없으면 null 이다(단추 없는 종류).
MEASURE = """() => {
  const r = (el) => el ? el.getBoundingClientRect() : null;
  const css = (el, p) => el ? getComputedStyle(el)[p] : null;
  const link = document.querySelector('a.ca-btn-link');
  const label = link ? link.querySelector('span') : null;
  const head = document.querySelector('td.ca-head');
  const logo = head ? head.querySelector('img') : null;
  const word = document.querySelector('td.ca-word');
  const lr = r(logo), wr = r(word);
  const facts = [...document.querySelectorAll('tr.ca-fact')].map((tr) => Math.round(tr.getBoundingClientRect().height));
  return {
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    button: link ? { height: r(link).height, width: r(link).width, color: css(label, 'color'), background: css(link, 'backgroundColor') } : null,
    head_background: css(head, 'backgroundColor'),
    logo: lr ? { width: lr.width, height: lr.height } : null,
    logo_word_center_delta: (lr && wr) ? Math.abs((lr.top + lr.height / 2) - (wr.top + wr.height / 2)) : null,
    fact_rows: facts,
    body_background: css(document.body, 'backgroundColor'),
  };
}"""


def judge(m: dict) -> list[str]:
    """한 장의 측정값 → 실패 문장들(없으면 통과)."""
    bad: list[str] = []
    if m["overflow"] > 1:
        bad.append(f"가로 넘침 {m['overflow']}px")
    button = m.get("button")
    if button:
        if abs(button["height"] - 44) > 1:
            bad.append(f"단추 높이 {button['height']}")
        if button["color"] != WHITE:
            bad.append(f"단추 글자색 {button['color']}")
        if button["background"] != PURPLE:
            bad.append(f"단추 바탕 {button['background']}")
    if m.get("head_background") != WHITE:
        bad.append(f"머리 띠 {m.get('head_background')}")
    if m.get("logo") and (m["logo"]["width"], m["logo"]["height"]) != (36, 36):
        bad.append(f"로고 {m['logo']}")
    delta = m.get("logo_word_center_delta")
    if delta is not None and delta > 1:
        bad.append(f"로고와 워드마크 세로 가운데 차이 {delta:.1f}px")
    return bad


def render_sources(out: Path, kinds: list[str]) -> list[dict]:
    from app.mail import content as c
    from app.mail import samples

    src = out / "src"
    src.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(c.LOGO_FILE, src / c.LOGO_FILE.name)
    labels = {key: label for key, label, _ in samples.PREVIEW_KINDS}
    items = []
    for kind in kinds:
        mail = samples.preview(kind, product="ClovirAssist", base_url=SAMPLE_BASE, support=SAMPLE_SUPPORT)
        (src / f"{kind}.html").write_text(mail.html, encoding="utf-8", newline="\n")
        (src / f"{kind}.txt").write_text(mail.text, encoding="utf-8", newline="\n")
        items.append({"kind": kind, "label": labels.get(kind, kind), "subject": mail.subject, "file": f"{kind}.html",
                      "has_button": 'class="ca-btn-link"' in mail.html})
    manifest = {"logo": c.LOGO_FILE.name, "cid": c.LOGO_CID, "items": items}
    (src / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return items


def shoot(out: Path, kinds: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    from app.mail import content as c
    from app.mail import samples

    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for kind in kinds:
            for view in VIEWS:
                mail = samples.preview(kind, product="ClovirAssist", base_url=SAMPLE_BASE, support=SAMPLE_SUPPORT,
                                       logo_src=c.logo_data_uri(), force_dark=view == "forced")
                for width in WIDTHS:
                    page = browser.new_page(viewport={"width": width, "height": 900},
                                            color_scheme="dark" if view == "dark" else "light")
                    page.set_content(mail.html)
                    page.wait_for_timeout(100)
                    measured = page.evaluate(MEASURE)
                    name = f"{kind}-{view}-{width}.png"
                    page.screenshot(path=str(shots / name), full_page=True)
                    page.close()
                    problems = judge(measured)
                    rows.append({"kind": kind, "view": view, "width": width, "shot": f"shots/{name}",
                                 "ok": not problems, "problems": problems, **measured})
        browser.close()
    return rows


def write_report(out: Path, rows: list[dict]) -> None:
    (out / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    lines = ["# 메일 틀 Chromium 매트릭스", "", f"찍은 것 {len(rows)}장, 실패 {sum(1 for r in rows if not r['ok'])}장.", "",
             "| 종류 | 보기 | 폭 | 판정 | 단추 높이 | 사실 행 높이 | 문제 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        height = f"{r['button']['height']:.0f}" if r.get("button") else "-"
        facts = ",".join(str(h) for h in r.get("fact_rows") or []) or "-"
        lines.append(f"| {r['kind']} | {r['view']} | {r['width']} | {'통과' if r['ok'] else '실패'} | {height} | {facts} | "
                     f"{'; '.join(r['problems'])} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    from app.mail import samples

    ap = argparse.ArgumentParser(description="메일 틀 렌더 매트릭스(D-571)")
    ap.add_argument("--out", default="")
    ap.add_argument("--kinds", nargs="*", default=None)
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args()
    known = [key for key, _label, _ in samples.PREVIEW_KINDS]
    kinds = args.kinds or known
    unknown = [k for k in kinds if k not in known]
    if unknown:
        print(f"모르는 종류: {', '.join(unknown)}")
        return 2
    out = Path(args.out) if args.out else ROOT / "dist" / "ui-qa" / "mail-templates" / datetime.now().strftime("%Y%m%d-%H%M%S")
    render_sources(out, kinds)
    if args.no_shots:
        print(f"MAIL_MATRIX_SOURCES {len(kinds)} → {out / 'src'}")
        return 0
    rows = shoot(out, kinds)
    write_report(out, rows)
    failed = [r for r in rows if not r["ok"]]
    for r in failed:
        print(f"FAIL {r['kind']} {r['view']} {r['width']}: {'; '.join(r['problems'])}")
    print(("MAIL_MATRIX_OK" if not failed else "MAIL_MATRIX_FAILED") + f" ({len(rows) - len(failed)}/{len(rows)}) → {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
