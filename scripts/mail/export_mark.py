"""브랜드 표식을 메일 머리의 PNG 로 한 번 내보낸다 (D-571).

메일 앱 다수(클래식 Outlook 의 Word 엔진, Gmail)는 SVG 를 그리지 못해 로고 표식은 PNG 한 장을 CID 로 싣는다(D-561). 이 스크립트는
그 PNG 를 제품의 정본 표식인 `frontend/src/ui/BrandLogo.jsx` 의 `CloverMark`(잎 경로, 밝은 면 잎 그라디언트, 가운데 원과 별과 점)에서
만든다. 표식을 손으로 다시 그리지 않고 JSX 의 상수를 읽어 SVG 를 세운 뒤 Chromium 으로 찍는다. 표식이 바뀌면 이 스크립트를 다시 돌리면
되고, 읽는 상수가 사라지면 멈춘다(조용히 옛 모양을 내지 않는다).

모양: 36px 칸(흰 바탕 불투명, 모서리 8px)에 표식을 채워 2배(72x72)로 찍는다. 모서리 바깥은 투명이다. 흰 머리 띠 위에서는 칸이 보이지
않고, 메일 앱이 머리를 어둡게 칠하면 흰 둥근 칸으로 선다. 메일 틀은 이 그림을 36px 로 그린다(`content.LOGO_SIZE`).

    .venv/Scripts/python.exe scripts/mail/export_mark.py        # app/mail/assets/mark-72.png 를 다시 쓴다
    .venv/Scripts/python.exe scripts/mail/export_mark.py --out x.png
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "frontend" / "src" / "ui" / "BrandLogo.jsx"
OUT = ROOT / "app" / "mail" / "assets" / "mark-72.png"
TILE = 36          # CSS px - 메일에서 그리는 크기
SCALE = 2          # 2배 그림(72x72)
RADIUS = 8         # CSS px - 칸 모서리
TILE_COLOR = "#FFFFFF"


def mark_svg(source: str, size: int = TILE) -> str:
    """BrandLogo.jsx 의 상수로 표식 SVG 한 장을 세운다. 못 읽으면 SystemExit."""
    path = re.search(r'const CLOVER_PATH =\s*"([^"]+)";', source)
    leaf_block = re.search(r"const LEAF = \{\s*light: \{(.*?)\},\s*dark:", source, re.S)
    grads = re.findall(r'\{ key: "(\w+)", x1: ([\d.]+), y1: ([\d.]+), x2: ([\d.]+), y2: ([\d.]+), rotate: (\d+) \}', source)
    body = re.search(r"function CloverMark\(.*?\n\}\n", source, re.S)
    if not (path and leaf_block and body) or len(grads) != 4:
        raise SystemExit("BrandLogo.jsx 에서 표식 상수(CLOVER_PATH, LEAF.light, GRADS, CloverMark)를 찾지 못했습니다.")
    leaves = {key: (a, b) for key, a, b in re.findall(
        r'(\w+): \["(#[0-9A-Fa-f]{6})", "(#[0-9A-Fa-f]{6})"\]', leaf_block.group(1))}
    if set(leaves) != {g[0] for g in grads}:
        raise SystemExit(f"잎 색({sorted(leaves)})과 그라디언트({[g[0] for g in grads]})가 맞지 않습니다.")
    # 잎 다음의 고정 요소(가운데 원, 별, 점) - 속성이 전부 문자열인 <circle>/<path> 만 고른다(잎은 {CLOVER_PATH} 라 빠진다).
    extras = re.findall(r'<(circle|path)\s+((?:[a-zA-Z]+="[^"]*"\s*)+)/>', body.group(0))
    if len(extras) != 3:
        raise SystemExit(f"CloverMark 의 고정 요소가 셋이 아닙니다({len(extras)}).")
    defs = "".join(
        f'<linearGradient id="m-{key}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{leaves[key][0]}"/><stop offset="1" stop-color="{leaves[key][1]}"/></linearGradient>'
        for key, x1, y1, x2, y2, _rotate in grads
    )
    shapes = "".join(
        f'<path d="{path.group(1)}" fill="url(#m-{key})"' + (f' transform="rotate({rotate} 64 64)"' if rotate != "0" else "") + "/>"
        for key, _x1, _y1, _x2, _y2, rotate in grads
    )
    fixed = "".join(f"<{tag} {' '.join(attrs.split())}/>" for tag, attrs in extras)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="{size}" height="{size}" '
            f'style="display:block"><defs>{defs}</defs>{shapes}{fixed}</svg>')


def export(out: Path) -> Path:
    from playwright.sync_api import sync_playwright

    svg = mark_svg(SOURCE.read_text(encoding="utf-8"))
    html = (f'<!DOCTYPE html><html><body style="margin:0;background:transparent">'
            f'<div id="tile" style="width:{TILE}px;height:{TILE}px;background:{TILE_COLOR};border-radius:{RADIUS}px;'
            f'overflow:hidden">{svg}</div></body></html>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 120, "height": 120}, device_scale_factor=SCALE)
        page.set_content(html)
        page.locator("#tile").screenshot(path=str(out), omit_background=True)
        browser.close()
    _check(out)
    return out


def _check(out: Path) -> None:
    """찍힌 그림이 약속한 모양인가 - 72x72, 모서리 바깥 투명, 칸 가장자리 불투명 흰색, 가운데 불투명."""
    from PIL import Image

    with Image.open(out) as im:
        rgba = im.convert("RGBA")
        size = TILE * SCALE
        problems = []
        if rgba.size != (size, size):
            problems.append(f"크기 {rgba.size}")
        px = rgba.load()
        if px[0, 0][3] != 0:
            problems.append(f"모서리가 투명하지 않음 {px[0, 0]}")
        edge = px[1, size // 2]
        if edge[3] != 255 or min(edge[:3]) < 245:
            problems.append(f"칸 가장자리가 흰색이 아님 {edge}")
        if px[size // 2, size // 2][3] != 255:
            problems.append("가운데가 불투명하지 않음")
    if problems:
        raise SystemExit("표식 PNG 가 약속과 다릅니다: " + "; ".join(problems))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="브랜드 표식을 메일용 PNG 로 내보낸다(D-571)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = export(Path(args.out))
    print(f"MARK_EXPORT_OK {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
