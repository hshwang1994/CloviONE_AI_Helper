"""구슬 레이스 판 자료 가져오기 (D-578) — 원본(lazygyu/roulette)의 `src/data/maps.ts` 를 읽어 엔진 판 파일을 만든다.

    git clone --depth 1 https://github.com/lazygyu/roulette <작업 폴더>/upstream-roulette     # 내려받은 저장소는 자기 폴더에 둔다
    .venv/Scripts/python.exe -I scripts/marble_import_maps.py <작업 폴더>/upstream-roulette/src/data/maps.ts --commit <원본 커밋>

내려받은 저장소는 **믿지 않는 자료**다 — 그 저장소의 빌드 · 스크립트를 돌리지 않고, 이 스크립트도 `maps.ts` 를 실행하지 않는다. TypeScript
객체 리터럴을 글자 단위로 훑어 JSON 으로 옮긴다(주석 · 따옴표 없는 열쇠 · 홑따옴표 · 끝 쉼표). 식(`Math.PI` 같은 계산)이 나오면 멈춘다.

만드는 것: `frontend/src/screens/game-room/marble/engine/stages/{pot,bubble,yoru}.js`. 옮기는 값은 물리에 쓰는 것뿐이다 — 판 이름 ·
`goalY` · `zoomY` · 엔티티(종류 · 위치 · 모양 · 밀도 · 반발 · 각속도 · `life`). 그리기 색(`color` · `bloomColor`) · 광고판 · 연출 구역은
옮기지 않는다(그리기는 제품 팔레트가 정한다). 이미 있는 `wheel.js`(원본 커밋 3f59495e)는 다시 쓰지 않고, 지금 원본과 같은지 대조만 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGES_DIR = REPO_ROOT / "frontend" / "src" / "screens" / "game-room" / "marble" / "engine" / "stages"

#: 원본 제목 → (열쇠, 상수 이름, 우리 이름)
WANTED = {
    "Pot of greed": ("pot", "POT", "탐욕의 항아리"),
    "BubblePop": ("bubble", "BUBBLE", "비눗방울"),
    "Yoru ni Kakeru": ("yoru", "YORU", "밤을 달리다"),
}
WHEEL_TITLE = "Wheel of fortune"

SHAPE_KEYS = {
    "box": ("type", "width", "height", "rotation"),
    "circle": ("type", "radius"),
    "polyline": ("type", "rotation", "points"),
}
PROP_KEYS = ("density", "angularVelocity", "restitution", "life")


class LiteralError(ValueError):
    pass


def ts_literal_to_json(text: str) -> str:
    """TypeScript 객체 · 배열 리터럴 → JSON 글. 문자열 밖에서만 주석을 걷고 열쇠에 따옴표를 두르고 끝 쉼표를 지운다."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            buf: list[str] = []
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i:i + 2])
                    i += 2
                    continue
                if quote == "`" and text[i] == "$" and i + 1 < n and text[i + 1] == "{":
                    raise LiteralError("템플릿 식은 옮기지 않는다")
                buf.append(text[i])
                i += 1
            if i >= n:
                raise LiteralError("닫히지 않은 문자열")
            raw = "".join(buf)
            if quote == "'":
                raw = raw.replace("\\'", "'").replace('"', '\\"')
            out.append('"' + raw + '"')
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise LiteralError("닫히지 않은 주석")
            i = end + 2
            continue
        if ch.isalpha() or ch == "_" or ch == "$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            word = text[i:j]
            k = j
            while k < n and text[k] in " \t\r\n":
                k += 1
            if k < n and text[k] == ":":
                out.append('"' + word + '"')
                i = j
                continue
            if word in ("true", "false", "null"):
                out.append(word)
                i = j
                continue
            raise LiteralError(f"식은 옮기지 않는다: {word!r}")
        if ch == ",":
            k = i + 1
            while k < n and (text[k] in " \t\r\n" or (text[k] == "/" and k + 1 < n and text[k + 1] in "/*")):
                if text[k] == "/" and text[k + 1] == "/":
                    while k < n and text[k] != "\n":
                        k += 1
                elif text[k] == "/" and text[k + 1] == "*":
                    k = text.find("*/", k + 2) + 2
                else:
                    k += 1
            if k < n and text[k] in "]}":
                i += 1  # 끝 쉼표
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_stages(source: str) -> list[dict]:
    marker = "export const stages"
    start = source.find(marker)
    if start < 0:
        raise LiteralError("`export const stages` 를 찾지 못했다")
    eq = source.find("=", start)
    open_at = source.find("[", eq)
    depth = 0
    in_str = None
    i = open_at
    while i < len(source):
        ch = source[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ("'", '"', "`"):
            in_str = ch
        elif ch == "/" and source[i + 1:i + 2] == "/":
            i = source.find("\n", i)
            continue
        elif ch == "/" and source[i + 1:i + 2] == "*":
            i = source.find("*/", i) + 2
            continue
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                literal = source[open_at:i + 1]
                return json.loads(ts_literal_to_json(literal))
        i += 1
    raise LiteralError("stages 배열이 닫히지 않았다")


def clean_entity(e: dict) -> dict:
    kind = e.get("type")
    if kind not in ("static", "kinematic"):
        raise LiteralError(f"모르는 엔티티 종류: {kind!r}")
    shape = e["shape"]
    keys = SHAPE_KEYS.get(shape.get("type"))
    if keys is None:
        raise LiteralError(f"모르는 모양: {shape.get('type')!r}")
    clean_shape = {k: shape[k] for k in keys if k in shape}
    if "rotation" in keys and "rotation" not in clean_shape:
        clean_shape["rotation"] = 0
    props = e.get("props") or {}
    clean_props = {k: props[k] for k in PROP_KEYS if k in props}
    for k in ("density", "angularVelocity", "restitution"):
        clean_props.setdefault(k, 0 if k != "density" else 1)
    pos = e["position"]
    return {"type": kind, "position": {"x": pos["x"], "y": pos["y"]}, "shape": clean_shape, "props": clean_props}


def clean_stage(stage: dict) -> dict:
    return {
        "title": stage["title"],
        "goalY": stage["goalY"],
        "zoomY": stage["zoomY"],
        "entities": [clean_entity(e) for e in stage.get("entities") or []],
    }


def summary(stage: dict) -> str:
    ents = stage["entities"]
    kinds: dict[str, int] = {}
    for e in ents:
        key = f"{e['type']}/{e['shape']['type']}"
        kinds[key] = kinds.get(key, 0) + 1
    life = sum(1 for e in ents if (e["props"].get("life") or -1) > 0)
    return f"{stage['title']}: goalY={stage['goalY']} zoomY={stage['zoomY']} entities={len(ents)} {kinds} life={life}"


def render_module(key: str, const: str, label: str, stage: dict, commit: str) -> str:
    body = json.dumps(stage, ensure_ascii=False, indent=1)
    return (
        f"/* 경주 판 「{label}」(원본 이름 「{stage['title']}」) — lazygyu/roulette 의 src/data/maps.ts 에서 옮긴 자료 (MIT, ATTRIBUTION.md).\n"
        f" * 원본 커밋 {commit} 의 값을 그대로 둔다 — 좌표 · 반폭 · 회전(라디안) · 밀도 · 반발 · 각속도 · life. 그리기 색은 여기 없다(제품 팔레트가 정한다).\n"
        f" * `scripts/marble_import_maps.py` 가 만든 파일이라 손으로 고치지 않는다. */\n\n"
        f"export const {const} = {body};\n\nexport default {const};\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maps_ts", help="원본 src/data/maps.ts 의 경로(내려받은 저장소 안)")
    ap.add_argument("--commit", required=True, help="원본 커밋 해시(머리말에 적는다)")
    ap.add_argument("--out", default=str(STAGES_DIR))
    ap.add_argument("--check", action="store_true", help="파일을 쓰지 않고 지금 파일과 같은지만 본다")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    source = Path(args.maps_ts).read_text(encoding="utf-8")
    stages = extract_stages(source)
    by_title = {s.get("title"): s for s in stages}
    out_dir = Path(args.out)
    changed = 0
    for title, (key, const, label) in WANTED.items():
        if title not in by_title:
            print(f"[import] 원본에 「{title}」 판이 없다", file=sys.stderr)
            return 2
        stage = clean_stage(by_title[title])
        text = render_module(key, const, label, stage, args.commit)
        path = out_dir / f"{key}.js"
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != text:
            changed += 1
            if not args.check:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
        print(f"[import] {key}.js — {summary(stage)}{'' if old == text else ' (바뀜)'}")
    if WHEEL_TITLE in by_title:
        upstream_wheel = clean_stage(by_title[WHEEL_TITLE])
        ours = (out_dir / "wheel.js").read_text(encoding="utf-8")
        mine, _ = json.JSONDecoder().raw_decode(ours, ours.index("{", ours.index("export const WHEEL")))
        def norm(value):  # 30 과 30.0 은 같은 값이다 — 수를 실수로 맞춰 비교한다
            return json.dumps(json.loads(json.dumps(value), parse_int=float), sort_keys=True)

        same = norm(mine["entities"]) == norm(upstream_wheel["entities"]) \
            and mine["goalY"] == upstream_wheel["goalY"] and mine["zoomY"] == upstream_wheel["zoomY"]
        print(f"[import] wheel.js 대조 — 지금 원본과 {'같다' if same else '다르다(wheel.js 는 그대로 둔다)'}")
    if args.check and changed:
        print(f"[import] {changed}개 파일이 원본과 다르다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
