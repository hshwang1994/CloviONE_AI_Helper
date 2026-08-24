"""클로비 포즈 자산의 **보이는 캐릭터 경계**를 재서 잠근다 (PLAN «Clovi 계약», 지시 71).

## 왜 필요한가

포즈 PNG 는 전부 1024×1024 인데 캐릭터는 그 안에 투명 여백을 두고 앉아 있다. 여백의 양이
자산마다 다르다 — `clovi-idle-blink` 는 세로의 85% 를 캐릭터가 채우고 `clovi-button` 은 67%
뿐이다. 그래서 **CSS 박스에 같은 숫자를 주면 자산마다 보이는 크기가 18%p 까지 벌어진다.**
지시 71 이 "실제 브라우저에서 클로비가 너무 작다" 고 지적한 것의 정확한 메커니즘이 이것이고,
박스 크기를 재는 어떤 검사로도 안 보인다.

이 스크립트는 그 여백을 실측해서 두 곳에 적어 둔다:

  · `app/static/brand/mascot/mascot-bounds.json` — 정본. 사람과 다른 도구가 읽는다.
  · `frontend/src/ui/mascotBounds.js`            — 화면이 읽는 사본. `Mascot.jsx` 가
                                                   «보이는 크기 → 박스» 를 이 값으로 나눈다.

둘 다 생성물이다. 손으로 고치지 마라 — `--check` 가 드리프트를 잡는다.

## 측정 정의 (PLAN 이 정한 것)

  알파 ≥ 128 인 픽셀의 bounding box.
  단 **opaque 픽셀이 반대 차원의 0.5% 미만인 행/열은 버린다**(부유 픽셀 제거).

부유 픽셀 제거는 장식이 아니라 필수다. `clovi-talking.png` 는 거의 투명한 픽셀이 캔버스
가장자리까지 흩어져 있어서, 그냥 «알파가 0 보다 크면 잉크» 로 세면 bbox 가 1024×1024 ·
`hfrac=1.000` 이 된다 — 실제 캐릭터는 세로의 **81.7%** 인데 검사는 100% 라고 말한다.
그 차이만큼 «보이는 크기» 가 부풀고, 정말 작은 마스코트가 통과한다.

저장소가 이미 같은 개념을 쓴다 — `app/static/brand/login/mascot-lock.json` 의
`canonicalVisibleBounds`. 이 스크립트는 그것을 전 포즈로 확장한 것이고,
`tests/regression/test_mascot_visible_bounds.py` 가 같은 정의로 다시 재서 대조한다.

## 쓰는 법

    python scripts/gen_mascot_bounds.py            # 생성
    python scripts/gen_mascot_bounds.py --check    # 드리프트 검사 (static_checks.sh 용)

`scripts/generate_design_tokens.mjs --check` 와 같은 관용이다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MASCOT_DIR = REPO / "app" / "static" / "brand" / "mascot"
LOGIN_DIR = REPO / "app" / "static" / "brand" / "login"
ART_DIR = REPO / "app" / "static" / "brand" / "empty-states"
JSON_OUT = MASCOT_DIR / "mascot-bounds.json"
JS_OUT = REPO / "frontend" / "src" / "ui" / "mascotBounds.js"

SCHEMA_VERSION = 1
# PLAN «Clovi 계약» 이 정한 두 상수. 여기를 바꾸면 판정 자체가 바뀐다.
ALPHA_MIN = 128
FLOATING_ROW_FRACTION = 0.005


def _assets() -> list[Path]:
    """재는 대상 — 런타임 포즈, 로그인 정본, 그리고 빈/오류 화면 일러스트.

    `frames/`·`layers/` 는 참고용 보존 자산이고 런타임 합성이 금지라(assets.js) 대상이 아니다.
    `character-sheet.png` 도 화면에 안 나간다.

    `empty-states/` 를 함께 재는 이유: 그 그림들도 같은 여백 문제를 갖고 있고, PLAN 의 Clovi
    계약표가 «Page-level Empty · `ART[...]` 또는 `clovi-sleep` · 132px» 처럼 **같은 밴드로**
    다룬다. 빈 화면의 그림은 클로비가 사는 자리 가운데 가장 큰 자리다.
    """
    poses = sorted(p for p in MASCOT_DIR.glob("clovi-*.png") if p.is_file())
    canonical = sorted(p for p in LOGIN_DIR.glob("clovi-canonical-*.png") if p.is_file())
    art = sorted(p for p in ART_DIR.glob("*.png") if p.is_file())
    return poses + canonical + art


def visible_bounds(path: Path) -> dict:
    """한 자산의 보이는 경계. PLAN 의 정의 그대로다.

    Pillow 만 쓴다(numpy 는 AI 런타임 전용 의존이라 개발 환경에 없을 수 있다). 행·열 개수는
    바이트 슬라이스의 `count()` 로 세므로 1024² 도 즉시 끝난다.
    """
    from PIL import Image  # noqa: PLC0415 — 개발 의존이라 import 를 함수 안에 둔다

    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        mask = rgba.getchannel("A").point(lambda v: 255 if v >= ALPHA_MIN else 0)
        by_row = mask.tobytes()
        by_col = mask.transpose(Image.Transpose.TRANSPOSE).tobytes()

    row_min = FLOATING_ROW_FRACTION * w
    col_min = FLOATING_ROW_FRACTION * h
    ys = [y for y in range(h) if by_row[y * w:(y + 1) * w].count(255) >= row_min]
    xs = [x for x in range(w) if by_col[x * h:(x + 1) * h].count(255) >= col_min]
    if not ys or not xs:
        raise ValueError(f"{path.name}: 불투명 픽셀이 하나도 없다 — 빈 자산이다")

    left, right, top, bottom = xs[0], xs[-1], ys[0], ys[-1]
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": [w, h],
        "visibleBounds": [left, top, right, bottom],
        # 소수 셋째 자리까지다. 이 값으로 박스 픽셀을 계산하므로 1024px 자산에서 오차는 1px 미만이다.
        "hfrac": round((bottom - top + 1) / h, 3),
        "wfrac": round((right - left + 1) / w, 3),
    }


def build() -> dict:
    entries = [visible_bounds(p) for p in _assets()]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedBy": "scripts/gen_mascot_bounds.py",
        "definition": {
            "alphaMin": ALPHA_MIN,
            "floatingRowFraction": FLOATING_ROW_FRACTION,
            "note": ("알파 >= alphaMin 인 픽셀의 bbox. 단 불투명 픽셀이 반대 차원의 "
                     "floatingRowFraction 미만인 행/열은 부유 픽셀로 보고 버린다."),
        },
        "assets": {e["file"]: e for e in entries},
    }


def render_json(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def render_js(doc: dict) -> str:
    rows = []
    for name, e in doc["assets"].items():
        rows.append(
            f'  "{name}": {{ hfrac: {e["hfrac"]}, wfrac: {e["wfrac"]},'
            f' size: [{e["size"][0]}, {e["size"][1]}] }},'
        )
    body = "\n".join(rows)
    return f'''/* 생성물이다. 손으로 고치지 마라.
 *
 *   python scripts/gen_mascot_bounds.py
 *
 * 정본은 `app/static/brand/mascot/mascot-bounds.json` 이고 그 값을 만든 정의는
 * `scripts/gen_mascot_bounds.py` 머리말에 있다 — 알파 ≥ {ALPHA_MIN} 인 픽셀의 bbox,
 * 단 불투명 픽셀이 반대 차원의 {FLOATING_ROW_FRACTION:.1%} 미만인 행/열은 버린다.
 *
 * `hfrac` 은 «자산 세로 가운데 캐릭터가 실제로 차지하는 비율» 이다. 화면이 «보이는 크기»
 * 를 말하면 `Mascot.jsx` 가 이 값으로 나눠 CSS 박스를 만든다 — 그래서 여백이 다른 자산끼리
 * 같은 크기로 보인다. 이 파일이 낡으면 `scripts/static_checks.sh` 가 잡는다.
 */

export const MASCOT_BOUNDS = {{
{body}
}};

/** 자산 경로(또는 파일 이름) → 세로 잉크 비율. 모르는 자산이면 1(= 여백 없음)로 본다. */
export function hfracOf(src) {{
  const name = String(src || "").split("/").pop();
  const entry = MASCOT_BOUNDS[name];
  return entry ? entry.hfrac : 1;
}}
'''


def main() -> int:
    ap = argparse.ArgumentParser(description="클로비 포즈 자산의 보이는 경계를 잠근다")
    ap.add_argument("--check", action="store_true", help="생성물이 자산과 어긋나면 실패")
    args = ap.parse_args()

    doc = build()
    want_json, want_js = render_json(doc), render_js(doc)

    if args.check:
        problems = []
        for path, want in ((JSON_OUT, want_json), (JS_OUT, want_js)):
            got = path.read_text(encoding="utf-8") if path.exists() else None
            if got is None:
                problems.append(f"{path.relative_to(REPO).as_posix()}: 없다")
            elif got != want:
                problems.append(f"{path.relative_to(REPO).as_posix()}: 자산과 어긋난다")
        if problems:
            print("\n".join(problems))
            print("python scripts/gen_mascot_bounds.py 를 다시 돌려라")
            return 1
        print(f"mascot bounds fresh ({len(doc['assets'])} assets)")
        return 0

    JSON_OUT.write_text(want_json, encoding="utf-8")
    JS_OUT.write_text(want_js, encoding="utf-8")
    for name, e in doc["assets"].items():
        print(f"{name:34} hfrac={e['hfrac']:.3f} wfrac={e['wfrac']:.3f}")
    print(f"\n-> {JSON_OUT.relative_to(REPO).as_posix()}")
    print(f"-> {JS_OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
