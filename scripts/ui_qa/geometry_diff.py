"""화면의 **뼈대**를 적어 두고 전후를 비교한다 (핸드오프 §0-10 · 표 5).

공통 부품을 갈아 끼우는 회차는 「보기에는 같다」로 끝내면 안 된다. 홈 · 내 업무량 · 내 프로필 ·
작업 보드 · 스프린트 회의는 **개별 리디자인 금지** 화면이라, 부품 치환이 레이아웃 · 정보 구조 ·
문구를 건드리지 않았다는 것을 숫자로 보여야 한다. 스크린샷 두 장을 눈으로 대 보는 것은 증명이
아니다 — 카드 하나가 12px 내려간 것과 열 비율이 바뀐 것은 사진에서 구별되지 않는다.

## 적는 것 (route × 테마 × 뷰포트마다 JSON 하나)

  headings   h1~h6 의 **순서**(태그 + 글자). 순서가 바뀌면 정보 구조가 바뀐 것이다.
  texts      본문에 보이는 글자 조각 + `aria-label` · `placeholder` · `title` 값. 숫자는 `#` 로
             접는다 — 씨앗의 상대 시각(「3분 전」)이 실행마다 달라 거짓 차이를 만든다.
  blocks     카드 · 판(`section`, `.MuiPaper-root`)의 사각형과 순서. 열쇠는 그 안 첫 제목.
  grids      격자의 `grid-template-columns` 계산값과 **비율**(열 폭 / 합).
  tables     표 머리 칸의 글자와 폭 비율.
  charts     `svg`(아이콘 제외) · `canvas` 크기.
  filter     `[data-filter-surface]` 의 아래 끝과 컨트롤 줄 수, 칸반 판(`[data-equal-grid=kanban]`)의 윗변.

## 쓰는 법

    # 기준(코드를 고치기 전 빌드)
    python -m scripts.ui_qa.local_capture --harness geometry_diff \\
        --routes user_me user_my-stats --viewports 1920x1080 1366x768 1200x900 \\
        --manifest-label handoff-before

    # 비교(브라우저 없이)
    python -m scripts.ui_qa.geometry_diff --diff handoff-before handoff-b1 [--tol-h 24]

`--label` · `--themes` 는 `local_capture` 가 먼저 먹는 이름이라 여기서는 `--manifest-label` ·
`--geo-themes` 를 쓴다(그 둘을 넘기면 하네스에 안 온다).

## 판정

  위반(종료 코드 1)  제목 순서 변화 · **낱말** 추가/삭제 · 블록 수 변화 · 격자/표 열 비율 변화(>2%) ·
                    차트 크기 변화(>4px)
  조각(보고만)       글자 조각의 개수 차이. 부품을 갈아 끼우면 같은 문구가 다른 마디로 쪼개진다 —
                    노치 라벨 「역할」 + 값 「역할 전체」가 칸 안 접두 「역할」 + 값 「전체」가 되고,
                    아이콘 표지의 `aria-label` 「지연」이 보이는 낱말 「지연」이 된다. 문구는 그대로인데
                    조각 목록은 달라진다(handoff-a 에서 142화면이 이 이유로 빨갛게 섰다). 그래서 문구
                    판정은 화면 전체의 **낱말 집합**(보이는 글자 + `aria-label` · `title` · `placeholder`)
                    으로 하고, 조각 차이는 사람이 훑을 수 있게 보고만 한다.
  이동(보고만)       블록 사각형의 dx/dy/dw/dh. `--tol-*` 를 넘으면 목록에 올린다 — 토큰 변경에서
                    유도한 허용 delta(카드 안쪽 −4px 등)인지 사람이 표 5 와 대조한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"
PROTECTED = ("user_me", "user_my-stats", "user_profile", "user_work-board", "user_sprint")

MANIFEST_JS = r"""
() => {
  const root = document.querySelector('#main-content') || document.body;
  const offY = root.scrollTop || 0;
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top + offY),
             w: Math.round(r.width), h: Math.round(r.height) };
  };
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none';
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().replace(/[0-9]+/g, '#');
  const firstHeading = (el) => {
    const h = el.querySelector('h1,h2,h3,h4,h5,h6,[role=heading]');
    return h ? norm(h.innerText).slice(0, 48) : '';
  };

  const headings = [...root.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .filter(shown).map((h) => h.tagName.toLowerCase() + ':' + norm(h.innerText).slice(0, 80));

  const texts = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = norm(n.textContent);
    if (!t) continue;
    const p = n.parentElement;
    if (!p || !shown(p)) continue;
    if (p.closest('script,style,noscript')) continue;
    texts.push(t.slice(0, 120));
  }
  root.querySelectorAll('[aria-label],[placeholder],[title]').forEach((el) => {
    if (!shown(el)) return;
    for (const [attr, tag] of [['aria-label', '@aria:'], ['placeholder', '@ph:'], ['title', '@title:']]) {
      const v = el.getAttribute(attr);
      if (v && v.trim()) texts.push(tag + norm(v).slice(0, 120));
    }
  });

  const blockSel = [
    '.MuiCard-root', 'section', '[data-section]',
    '.MuiPaper-root:not(.MuiPopover-paper):not(.MuiMenu-paper):not(.MuiDialog-paper):not(.MuiAutocomplete-paper)',
  ].join(',');
  const seen = new Counter();
  function Counter() { const m = new Map(); return { next: (k) => { const v = (m.get(k) || 0) + 1; m.set(k, v); return v; } }; }
  const blocks = [];
  root.querySelectorAll(blockSel).forEach((el) => {
    if (!shown(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 24) return;
    const key = firstHeading(el) || ('<' + el.tagName.toLowerCase() + '>');
    blocks.push({ key: key + '#' + seen.next(key), ...rect(el) });
  });

  const gridSeen = new Counter();
  const grids = [];
  for (const el of root.querySelectorAll('*')) {
    if (grids.length >= 80) break;
    const st = getComputedStyle(el);
    if (st.display !== 'grid' && st.display !== 'inline-grid') continue;
    if (el.closest('table,[role=table],[role=row]')) continue;
    if (el.children.length < 2 || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 200) continue;
    const tracks = st.gridTemplateColumns.split(' ').map(parseFloat).filter((v) => !Number.isNaN(v));
    if (tracks.length < 2) continue;
    const sum = tracks.reduce((a, b) => a + b, 0) || 1;
    const scope = el.closest('.MuiCard-root,section,[data-section]');
    const key = (scope ? firstHeading(scope) : '') || '(root)';
    grids.push({ key: key + '#' + gridSeen.next(key), columns: st.gridTemplateColumns,
                 ratio: tracks.map((t) => Math.round((t / sum) * 1000) / 1000), ...rect(el) });
  }

  const tables = [];
  root.querySelectorAll('table,[role=table]').forEach((t, i) => {
    if (!shown(t)) return;
    const heads = [...t.querySelectorAll('th,[role=columnheader]')].filter(shown);
    const sum = heads.reduce((a, h) => a + h.getBoundingClientRect().width, 0) || 1;
    tables.push({ key: 'table#' + (i + 1),
                  heads: heads.map((h) => norm(h.innerText).slice(0, 40)),
                  ratio: heads.map((h) => Math.round((h.getBoundingClientRect().width / sum) * 1000) / 1000),
                  ...rect(t) });
  });

  const chartSeen = new Counter();
  const charts = [];
  root.querySelectorAll('svg,canvas').forEach((el) => {
    if (el.tagName.toLowerCase() === 'svg' && (el.classList.contains('MuiSvgIcon-root') || el.closest('button'))) return;
    if (!shown(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 48 || r.height < 48) return;
    const scope = el.closest('.MuiCard-root,section,[data-section]');
    const key = (scope ? firstHeading(scope) : '') || '(root)';
    charts.push({ key: key + '#' + chartSeen.next(key), w: Math.round(r.width), h: Math.round(r.height) });
  });

  const fs = root.querySelector('[data-filter-surface]');
  let filter = null;
  if (fs && shown(fs)) {
    const tops = new Set();
    fs.querySelectorAll('[data-filter-kind],.MuiButton-root,.MuiFormControlLabel-root,[role=tablist]').forEach((c) => {
      if (shown(c)) tops.add(Math.round(c.getBoundingClientRect().top / 8));
    });
    filter = { bottom: Math.round(fs.getBoundingClientRect().bottom + offY), rows: tops.size };
  }
  const board = root.querySelector('[data-equal-grid=kanban]');
  const head = root.querySelector('.k-page-head');
  return {
    viewport: { w: innerWidth, h: innerHeight },
    pageHead: head && shown(head) ? rect(head) : null,
    headings, texts, blocks, grids, tables, charts, filter,
    boardTop: board && shown(board) ? Math.round(board.getBoundingClientRect().top + offY) : null,
  };
}
"""


def _manifest_dir(label: str) -> Path:
    return OUT_BASE / label / "geometry"


def capture(args) -> int:
    from scripts.ui_qa import capture as cap, routes as routes_mod, tls
    from scripts.ui_qa.auth import ensure_session

    base = args.base_url or cap.DEFAULT_BASE_URL
    insecure = tls.apply_default_https_context()
    routes = routes_mod.resolve(args.routes or list(PROTECTED))
    viewports = cap.resolve_viewports(args.viewports or ["1920x1080"])
    themes = args.geo_themes or ["light"]
    out = _manifest_dir(args.manifest_label)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    written = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, OUT_BASE / "auth-geometry",
                                     insecure=insecure, log=print)
            probe = browser.new_context(storage_state=session.storage_state,
                                        ignore_https_errors=insecure)
            hashes: dict[str, str] = {}
            try:
                for route in routes:
                    if route.is_detail:
                        found, note = cap.discover_detail_hash(probe, base, route, log=print)
                        if found:
                            hashes[route.id] = found
                        else:
                            print(f"[geometry] {route.id}: 건너뜀 — {note}")
            finally:
                probe.close()
            for theme in themes:
                for viewport in viewports:
                    ctx = cap.new_context(browser, storage_state=session.storage_state,
                                          user_id=session.user_id, theme=theme,
                                          viewport=viewport, insecure=insecure)
                    page = ctx.new_page()
                    try:
                        for route in routes:
                            if route.is_public or not route.visible_to(session.role):
                                continue
                            if route.is_detail and route.id not in hashes:
                                continue
                            hash_path = hashes.get(route.id, route.hash_path)
                            page.goto(route.url(base, hash_path), wait_until="domcontentloaded",
                                      timeout=args.timeout_ms)
                            notes = cap._settle(page, settle_ms=args.settle_ms,
                                                timeout_ms=args.timeout_ms)
                            data = page.evaluate(MANIFEST_JS)
                            data.update({"route": route.id, "theme": theme,
                                         "viewport_name": viewport.name, "settle_notes": notes})
                            name = f"{route.id}__{theme}__{viewport.name}.json"
                            (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
                            written += 1
                            print(f"[geometry] {theme:<5} {viewport.name:<10} {route.id:<28} "
                                  f"제목 {len(data['headings'])} 글자 {len(data['texts'])} "
                                  f"블록 {len(data['blocks'])} 격자 {len(data['grids'])}", flush=True)
                    finally:
                        page.close()
                        ctx.close()
        finally:
            browser.close()
    print(f"GEOMETRY_CAPTURED {written} → {out}")
    return 0 if written else 2


def _by_key(items: list[dict]) -> dict[str, dict]:
    return {it["key"]: it for it in items}


# 씨앗 데이터가 실행마다 새로 뽑는 값 — 프로젝트 키 앞머리(`CUYNPN-12`)와 UUID 조각. 글자 비교에서
# 이 차이는 문구 변화가 아니다. 숫자는 매니페스트를 적을 때 이미 `#` 로 접었다.
_SEED_KEY = re.compile(r"\b[A-Z]{6}(?:-#)?\b")
_SEED_HEX = re.compile(r"(?<![\w#])[0-9a-f#]{1,12}(?:-[0-9a-f#]{1,12}){3,4}(?:-…|…)?")


# 대시 없는 16진 식별자(요청 id 등) — 숫자가 `#` 로 접혀 `#acb#f#e` 처럼 남는다.
_SEED_HEXRUN = re.compile(r"(?<![\w#])(?=[0-9a-f#]*#)(?=[0-9a-f#]*[a-f])[0-9a-f#]{6,}(?![\w#])")
_CHANNEL = re.compile(r"^@(aria|title|ph):")
_WORD = re.compile(r"[가-힣]+|[A-Za-z]+")


def _norm_text(text: str) -> str:
    return _SEED_HEXRUN.sub("<id>", _SEED_HEX.sub("<id>", _SEED_KEY.sub("KEY", text)))


def _words(texts: list[str]) -> set[str]:
    """화면의 낱말 집합 — 채널 표지를 떼고, 한글 · 라틴 낱말만 센다(숫자 · 기호는 뼈대가 아니다)."""
    out: set[str] = set()
    for t in texts:
        out.update(_WORD.findall(_norm_text(_CHANNEL.sub("", t))))
    return out


def compare(before: dict, after: dict, *, tol_x: int, tol_w: int, tol_h: int,
            tol_y: int) -> dict:
    """한 화면(route×테마×뷰포트)의 두 매니페스트를 대 본다."""
    violations: list[str] = []
    moves: list[str] = []

    if [_norm_text(h) for h in before["headings"]] != [_norm_text(h) for h in after["headings"]]:
        violations.append("제목 순서: " + json.dumps(
            {"before": before["headings"], "after": after["headings"]}, ensure_ascii=False))

    wb, wa = _words(before["texts"]), _words(after["texts"])
    lost_words, new_words = sorted(wb - wa), sorted(wa - wb)
    if lost_words or new_words:
        violations.append("글자: 빠진 낱말 " + json.dumps(lost_words[:16], ensure_ascii=False)
                          + " / 생긴 낱말 " + json.dumps(new_words[:16], ensure_ascii=False)
                          + (f" (빠짐 {len(lost_words)} · 생김 {len(new_words)})"))
    notes: list[str] = []
    tb = Counter(_norm_text(t) for t in before["texts"])
    ta = Counter(_norm_text(t) for t in after["texts"])
    removed = sorted((tb - ta).elements())
    added = sorted((ta - tb).elements())
    if removed or added:
        notes.append("글자 조각: 빠짐 " + json.dumps(removed[:8], ensure_ascii=False)
                     + " / 생김 " + json.dumps(added[:8], ensure_ascii=False)
                     + (f" (빠짐 {len(removed)} · 생김 {len(added)})"))

    kb = Counter(b["key"].rsplit("#", 1)[0] for b in before["blocks"])
    ka = Counter(b["key"].rsplit("#", 1)[0] for b in after["blocks"])
    if kb != ka:
        lost = sorted((kb - ka).elements())
        new = sorted((ka - kb).elements())
        violations.append("블록 수: 빠짐 " + json.dumps(lost[:10], ensure_ascii=False)
                          + " / 생김 " + json.dumps(new[:10], ensure_ascii=False))

    bb, ba = _by_key(before["blocks"]), _by_key(after["blocks"])
    for key, b in bb.items():
        a = ba.get(key)
        if not a:
            continue
        dx, dy, dw, dh = a["x"] - b["x"], a["y"] - b["y"], a["w"] - b["w"], a["h"] - b["h"]
        if abs(dx) > tol_x or abs(dw) > tol_w or abs(dh) > tol_h or abs(dy) > tol_y:
            moves.append(f"{key}: dx {dx:+d} dy {dy:+d} dw {dw:+d} dh {dh:+d}")

    for kind in ("grids", "tables"):
        gb, ga = _by_key(before[kind]), _by_key(after[kind])
        for key, g in gb.items():
            h = ga.get(key)
            if not h:
                continue
            if len(g["ratio"]) != len(h["ratio"]) or any(
                    abs(x - y) > 0.02 for x, y in zip(g["ratio"], h["ratio"])):
                violations.append(f"{kind} 열 비율 {key}: {g['ratio']} → {h['ratio']}")
            if kind == "tables" and g.get("heads") != h.get("heads"):
                violations.append(f"표 머리 {key}: {g.get('heads')} → {h.get('heads')}")

    cb, ca = _by_key(before["charts"]), _by_key(after["charts"])
    for key, c in cb.items():
        d = ca.get(key)
        if d and (abs(d["w"] - c["w"]) > 4 or abs(d["h"] - c["h"]) > 4):
            violations.append(f"차트 크기 {key}: {c['w']}x{c['h']} → {d['w']}x{d['h']}")

    fb, fa = before.get("filter"), after.get("filter")
    if fb and fa and fb.get("rows") != fa.get("rows"):
        violations.append(f"필터 줄 수 {fb.get('rows')} → {fa.get('rows')}")
    extra = {}
    if before.get("boardTop") is not None or after.get("boardTop") is not None:
        extra["boardTop"] = [before.get("boardTop"), after.get("boardTop")]
    return {"violations": violations, "moves": moves, "notes": notes, **extra}


def selftest() -> int:
    """Known Good / Known Bad — 판정을 제품에 대기 전에 견본으로 확인한다(CLAUDE.md §7.1)."""
    base = {"headings": ["h1:사용자"], "blocks": [], "grids": [], "tables": [], "charts": [],
            "texts": ["역할", "역할 전체", "@aria:지연", "요청 #f#a#c#e"]}

    def make(texts):
        return {**base, "texts": texts}

    cases = [
        # 쪼개짐 · 채널 이동 · 씨앗 식별자 — 문구는 그대로다(숫자는 매니페스트가 이미 `#` 로 접었다)
        ("good: 접두 라벨로 쪼개짐", make(["역할", "전체", "@aria:지연", "요청 #f#a#c#e"]), False),
        ("good: aria → 보이는 낱말", make(["역할", "역할 전체", "지연", "요청 #f#a#c#e"]), False),
        ("good: 씨앗 16진 id", make(["역할", "역할 전체", "@aria:지연", "요청 #acb#f#e"]), False),
        # 문구 변화 — 잡아야 한다
        ("bad: 낱말이 바뀜", make(["역할", "권한 전체", "@aria:지연", "요청 #f#a#c#e"]), True),
        ("bad: 낱말이 빠짐", make(["역할", "역할 전체", "요청 #f#a#c#e"]), True),
        ("bad: 새 낱말", make(["역할", "역할 전체", "@aria:지연", "요청 #f#a#c#e", "필수 항목"]), True),
    ]
    before = make([_norm_text(t) for t in base["texts"]])
    ok = True
    for name, after, expect_violation in cases:
        after = make([_norm_text(t) for t in after["texts"]])
        got = bool([v for v in compare(before, after, tol_x=2, tol_w=2, tol_h=24, tol_y=48)["violations"]
                    if v.startswith("글자")])
        status = "OK " if got == expect_violation else "BAD"
        ok = ok and got == expect_violation
        print(f"  {status} {name} → 위반 {got}")
    print("GEOMETRY_DIFF_SELFTEST_" + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def diff(args) -> int:
    before_label, after_label = args.diff
    bdir, adir = _manifest_dir(before_label), _manifest_dir(after_label)
    if not bdir.is_dir() or not adir.is_dir():
        print(f"[FATAL] 매니페스트 폴더가 없다: {bdir if not bdir.is_dir() else adir}")
        return 2
    wanted = set(args.routes or [])
    report: dict[str, dict] = {}
    compared = 0
    bad = 0
    for path in sorted(adir.glob("*.json")):
        route = path.name.split("__", 1)[0]
        if wanted and route not in wanted:
            continue
        other = bdir / path.name
        if not other.is_file():
            report[path.stem] = {"violations": ["기준 매니페스트 없음"], "moves": []}
            bad += 1
            continue
        before = json.loads(other.read_text(encoding="utf-8"))
        after = json.loads(path.read_text(encoding="utf-8"))
        result = compare(before, after, tol_x=args.tol_x, tol_w=args.tol_w,
                         tol_h=args.tol_h, tol_y=args.tol_y)
        report[path.stem] = result
        compared += 1
        if result["violations"]:
            bad += 1
        mark = "위반" if result["violations"] else ("이동" if result["moves"] else "같음")
        line = f"{path.stem:<48} {mark}"
        if "boardTop" in result:
            line += f"  판 시작 {result['boardTop'][0]} → {result['boardTop'][1]}"
        print(line)
        for v in result["violations"]:
            print("    ✗ " + v[:400])
        for m in result["moves"][:args.max_moves]:
            print("    ~ " + m)
        if args.show_notes:
            for n in result.get("notes", []):
                print("    · " + n[:300])
        if len(result["moves"]) > args.max_moves:
            print(f"    ~ … 외 {len(result['moves']) - args.max_moves}건")
    out = OUT_BASE / after_label / "geometry-diff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"before": before_label, "after": after_label, "pages": report},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    if not compared:
        print("[FATAL] 비교한 화면이 0개다 — 라벨·route 를 확인하라.")
        return 2
    if bad:
        print(f"GEOMETRY_DIFF_FAILED ({bad}/{compared} 화면에 위반) → {out}")
        return 1
    print(f"GEOMETRY_DIFF_OK ({compared} 화면, 위반 0) → {out}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="화면 뼈대 매니페스트와 전후 비교")
    ap.add_argument("--routes", nargs="*", default=None)
    ap.add_argument("--viewports", nargs="*", default=None)
    ap.add_argument("--geo-themes", nargs="*", default=None)
    ap.add_argument("--manifest-label", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--settle-ms", type=int, default=600)
    ap.add_argument("--timeout-ms", type=int, default=45_000)
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"), default=None)
    ap.add_argument("--tol-x", type=int, default=2)
    ap.add_argument("--tol-w", type=int, default=2)
    ap.add_argument("--tol-h", type=int, default=24)
    ap.add_argument("--tol-y", type=int, default=48)
    ap.add_argument("--max-moves", type=int, default=12)
    ap.add_argument("--show-notes", action="store_true",
                    help="글자 조각 차이(보고만)도 찍는다")
    ap.add_argument("--selftest", action="store_true",
                    help="낱말 판정이 문구 변화는 잡고 쪼개짐은 넘기는지 견본으로 먼저 확인한다")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.diff:
        return diff(args)
    if not args.manifest_label:
        print("[FATAL] --manifest-label 이 필요하다(또는 --diff BEFORE AFTER).")
        return 2
    return capture(args)


if __name__ == "__main__":
    raise SystemExit(main())
