"""탐색 줄(Search/Filter/Form)을 **실제 브라우저에서** 재고 눌러 본다 (W5).

## 왜 별도 모듈인가

W5 가 바꾼 것 중 셋은 jsdom 이 원리적으로 말할 수 없다.

1. **판이 아니다** 는 레이아웃·페인트 문제다. `filter-row-width.test.jsx` 가 "배경이 없다" 를
   단언해도, 배포된 CSS 가 계산한 값이 그렇다는 보장은 없다. 이 저장소는 그 간극에서 같은
   결함을 세 번 밟았다(`borderInlineStart: 1` — 시험도 콘솔도 조용한데 화면에 선이 없다).
2. **고아 줄** 은 줄바꿈의 결과다. 어떤 컨트롤이 어느 줄에 서는지는 실제 폭에서만 정해진다.
3. **키보드로 고를 수 있는가** 는 상호작용이다. `entity-combobox.test.jsx` 가 jsdom 에서
   재는 것은 이벤트 배선이고, 여기서는 그 배선이 **주소와 네트워크까지** 닿는지 본다.

## 이 모듈이 재는 계약

  · 탐색 줄이 **칠해진 면이 아닌가**(배경·네 변 테두리 없음), 아래 실선 하나로 갈리는가
  · 컨트롤 폭이 **종류를 따르는가** — 같은 줄의 Entity 폭 > 닫힌 열거형 폭
  · **고아 줄이 없는가** — 컨트롤 하나가 줄의 절반 넘게 비우면서 왼쪽에서 시작하는 자리
  · 한 줄 안 컨트롤 **높이가 하나인가**(같은 종류끼리 4px 이내)
  · 「필터 지우기」가 **테두리 상자가 아닌가**, 동작 묶음 안에 있는가
  · **결과 줄이 필터와 목록 사이에** 있는가 (y 좌표로 확인)
  · Entity Combobox 를 **키보드만으로** 열고·거르고·고를 수 있는가, 그리고 그 선택이
    주소(`project_id=`)와 **서버 질의**까지 닿는가
  · 좁은 화면(390)에서 가로 넘침 없이 접히는가

## 쓰는 법

    python -m scripts.ui_qa.filter_e2e --insecure        # 대상은 UI_QA_BASE_URL 또는 --base-url

산출물: `dist/ui-qa/w5-filter-e2e/{surfaces.json,flows.json}` + 단계별 스크린샷.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "w5-filter-e2e"

# 탐색 줄이 있는 화면 넷. **서로 다른 렌더 경로**를 하나씩 고른다 —
# 티켓 필터 바 · 설정 주도(DataScreen) · 손수 만든 목록(TeamDocs) · 도구 줄만 있는 화면(Board).
# 한 경로만 재면 "그 화면은 고쳤다" 밖에 말하지 못한다.
ROUTES = [
    ("my-tickets", "/my-tickets"),
    ("policies", "/policies"),
    ("team-docs", "/team-docs"),
    ("board", "/board"),
]

MEASURE_JS = r"""() => {
  const main = document.querySelector('#main-content') || document.body;
  const surface = main.querySelector('[data-filter-surface]');
  const out = { hasSurface: !!surface, fails: [], checked: 0 };
  if (!surface) { out.fails.push('탐색 줄을 찾지 못했다'); return out; }

  const cs = getComputedStyle(surface);
  out.checked++;
  const bg = cs.backgroundColor;
  const painted = !!bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
  out.background = bg;
  if (painted) out.fails.push('탐색 줄이 칠해진 면이다(판이 되돌아왔다): ' + bg);
  const sides = ['Top', 'Right', 'Left'].map((s) => cs['border' + s + 'Style']);
  out.borders = { top: sides[0], right: sides[1], left: sides[2], bottom: cs.borderBottomStyle };
  if (sides.some((s) => s && s !== 'none')) out.fails.push('탐색 줄이 네 변을 두른다: ' + JSON.stringify(sides));
  if (cs.borderBottomStyle !== 'solid') out.fails.push('목록과 갈리는 아래 실선이 없다');

  /* ── 줄 단위 실측 ────────────────────────────────────────────────────────
     같은 줄인지는 **세로 겹침**으로 정한다(assertions.py 의 flowRows 와 같은 기준). */
  const rows = [];
  for (const row of main.querySelectorAll('[data-filter-row]')) {
    const rr = row.getBoundingClientRect();
    const rcs = getComputedStyle(row);
    const inner = rr.width - (parseFloat(rcs.paddingLeft) || 0) - (parseFloat(rcs.paddingRight) || 0);
    const kids = [];
    for (const k of row.children) {
      const b = k.getBoundingClientRect();
      if (b.width < 1 || b.height < 1) continue;
      kids.push({ el: k, r: b, kind: k.getAttribute('data-filter-kind') || '' });
    }
    kids.sort((a, b2) => (a.r.top - b2.r.top) || (a.r.left - b2.r.left));
    const lines = [];
    for (const k of kids) {
      const last = lines.length ? lines[lines.length - 1] : null;
      if (last) {
        const top = Math.max(last.top, k.r.top), bot = Math.min(last.bottom, k.r.bottom);
        const minH = Math.min(last.bottom - last.top, k.r.height);
        if (minH > 0 && bot - top > minH * 0.5) {
          last.items.push(k); last.top = Math.min(last.top, k.r.top);
          last.bottom = Math.max(last.bottom, k.r.bottom);
          last.left = Math.min(last.left, k.r.left); last.right = Math.max(last.right, k.r.right);
          continue;
        }
      }
      lines.push({ items: [k], top: k.r.top, bottom: k.r.bottom, left: k.r.left, right: k.r.right });
    }
    rows.push({ inner: Math.round(inner), left: rr.left + (parseFloat(rcs.paddingLeft) || 0), lines });
  }

  out.rowCount = rows.length;
  out.orphans = [];
  out.heightSpreads = [];
  out.kindWidths = {};
  for (const row of rows) {
    for (const line of row.lines) {
      out.checked++;
      /* 고아 줄 — **윗줄에 자리가 있었는데** 컨트롤 하나가 아랫줄로 밀렸다(지시 76).
         `assertions.py::isolated_control_row` 와 같은 모델이다. 윗줄 여유를 함께 보지 않으면
         좁은 화면의 정상 wrap 이 전부 걸린다 — 실제로 첫 실행에서 `/policies` 390 과
         `/board` 1920 의 칩 묶음이 그렇게 걸렸고, 둘 다 밀려난 것이 아니라 접히거나 놓인
         것이었다. 첫 줄은 애초에 밀려날 곳이 없으므로 건너뛴다. */
      const li = row.lines.indexOf(line);
      if (line.items.length === 1 && li > 0) {
        const prev = row.lines[li - 1];
        const used = line.right - line.left;
        const free = row.inner - used;
        const freeP = row.inner - (prev.right - prev.left);
        const startedRight = (line.left - row.left) > row.inner * 0.5;
        if (!startedRight && free > 120 && freeP > 120 && freeP >= used + 12) {
          out.orphans.push({ used: Math.round(used), free: Math.round(free),
                             prevFree: Math.round(freeP), inner: row.inner,
                             text: (line.items[0].el.innerText || '').slice(0, 30) });
        }
      }
      // 같은 줄 컨트롤 높이 — 같은 종류끼리 4px 이내.
      const byKind = {};
      for (const it of line.items) {
        const inner2 = it.el.querySelector('.MuiInputBase-root') || it.el;
        const b = inner2.getBoundingClientRect();
        if (b.height < 12) continue;
        const kind = it.kind || 'other';
        (byKind[kind] = byKind[kind] || []).push(b.height);
        if (it.kind) {
          out.kindWidths[it.kind] = Math.max(out.kindWidths[it.kind] || 0, Math.round(b.width));
        }
      }
      for (const [kind, hs] of Object.entries(byKind)) {
        if (hs.length < 2) continue;
        const spread = Math.max(...hs) - Math.min(...hs);
        if (spread > 4) out.heightSpreads.push({ kind, spread: Math.round(spread * 10) / 10 });
      }
    }
  }
  if (out.orphans.length) out.fails.push('고아 줄 ' + out.orphans.length + '자리');
  if (out.heightSpreads.length) out.fails.push('한 줄 안 높이 차 ' + JSON.stringify(out.heightSpreads));

  // 폭이 의미를 따르는가 — Entity 가 닫힌 열거형보다 넓다.
  if (out.kindWidths.entity && out.kindWidths.enum) {
    out.checked++;
    if (out.kindWidths.entity <= out.kindWidths.enum) {
      out.fails.push('Entity 폭이 닫힌 열거형보다 넓지 않다: ' + JSON.stringify(out.kindWidths));
    }
  }

  // 「필터 지우기」 — 테두리 상자가 아니고 동작 묶음 안에 있다.
  const actions = main.querySelector('[data-filter-actions]');
  out.hasActions = !!actions;
  if (actions) {
    const btn = actions.querySelector('button');
    if (btn) {
      out.checked++;
      const bcs = getComputedStyle(btn);
      out.resetBorder = bcs.borderTopStyle + ' ' + bcs.borderTopWidth;
      if (bcs.borderTopStyle !== 'none' && parseFloat(bcs.borderTopWidth) > 0) {
        out.fails.push('되돌리기가 테두리 상자다: ' + out.resetBorder);
      }
    }
  }

  // 결과 줄이 필터와 목록 **사이**에 있는가.
  const line = main.querySelector('[data-result-line]');
  out.hasResultLine = !!line;
  if (line) {
    out.checked++;
    const lr = line.getBoundingClientRect();
    const sr = surface.getBoundingClientRect();
    out.resultLineText = (line.innerText || '').trim().slice(0, 40);
    if (lr.top < sr.bottom - 2) out.fails.push('결과 줄이 탐색 줄보다 위에 있다');
    const table = main.querySelector('table, [data-list-root]');
    if (table) {
      const tr = table.getBoundingClientRect();
      if (tr.top > 0 && lr.top > tr.top + 2) out.fails.push('결과 줄이 목록보다 아래에 있다');
    }
  }

  out.docOverflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  if (out.docOverflow > 1) out.fails.push('가로 넘침 ' + out.docOverflow + 'px');
  out.ok = out.fails.length === 0;
  return out;
}"""


def _goto(page, base: str, path: str) -> None:
    page.goto(f"{base}/#{path}", wait_until="domcontentloaded")
    page.wait_for_timeout(1400)


def _shot(page, out: Path, name: str) -> str:
    p = out / f"{name}.png"
    page.screenshot(path=str(p), full_page=False)
    return str(p.relative_to(REPO_ROOT)).replace("\\", "/")


def keyboard_flow(page, base: str, out: Path) -> dict:
    """Entity Combobox 를 **키보드만으로** 쓰고, 그 선택이 주소와 서버 질의까지 닿는지 본다."""
    calls: list[str] = []
    page.on("request", lambda r: calls.append(r.url) if "/api/tickets" in r.url else None)
    step: list[str] = []
    chain = {"ui_state": "", "url_query": "", "api_request": "", "rendered": ""}
    fails: list[str] = []

    _goto(page, base, "/my-tickets")
    box = page.query_selector('[role="combobox"][aria-autocomplete="list"]')
    if box is None:
        return {"flow": "entity_combobox_keyboard", "status": "FAIL",
                "fails": ["검색형 combobox 를 찾지 못했다 — Entity 축이 평범한 드롭다운으로 남아 있다"],
                "chain": chain, "steps": step}

    label = page.evaluate(
        "(el) => { const f = el.closest('.MuiFormControl-root');"
        " const l = f && f.querySelector('label'); return l ? l.textContent : ''; }", box)
    step.append(f"combobox 를 찾았다: «{label}»")

    box.focus()
    page.wait_for_timeout(150)
    focused = page.evaluate("() => document.activeElement === document.querySelector('[role=\"combobox\"][aria-autocomplete=\"list\"]')")
    if not focused:
        fails.append("포커스가 combobox 에 서지 않는다")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(400)
    expanded = box.get_attribute("aria-expanded")
    step.append(f"ArrowDown 으로 열었다: aria-expanded={expanded}")
    if expanded != "true":
        fails.append("키보드로 목록이 열리지 않는다 (aria-expanded != true)")
    n_before = len(page.query_selector_all('[role="option"]'))
    step.append(f"열린 직후 후보 {n_before}개")
    if n_before < 2:
        fails.append(f"후보가 {n_before}개뿐이다 — 목록이 안 붙었을 수 있다")

    # 실제 후보의 **부분 문자열**을 친다. 아무 글자나 치면 한글 목록에서 0개가 되고,
    # 그러면 "걸러졌다" 와 "아무것도 안 맞았다" 를 구분할 수 없다 — 첫 실행에서 밟았다.
    first = page.query_selector('[role="option"]')
    probe_text = ""
    if first is not None:
        txt = (first.inner_text() or "").strip()
        # 첫 줄(라벨)에서 두 글자. 「… 전체」 항목은 건너뛴다 — 그것은 후보가 아니라 되돌리기다.
        opts = page.query_selector_all('[role="option"]')
        for o in opts[1:] if len(opts) > 1 else opts:
            t = (o.inner_text() or "").strip().splitlines()[0] if (o.inner_text() or "").strip() else ""
            if len(t) >= 2:
                probe_text = t[:2]
                break
        if not probe_text and txt:
            probe_text = txt[:2]
    step.append(f"거를 글자: «{probe_text}»")
    page.keyboard.type(probe_text or "a")
    page.wait_for_timeout(500)
    n_after = len(page.query_selector_all('[role="option"]'))
    step.append(f"입력 후 후보 {n_after}개")
    if n_after == 0:
        fails.append("입력하자 후보가 0개가 됐다 — 거르는 기준이 라벨과 다르다")
    elif n_after >= n_before:
        fails.append(f"입력해도 후보가 안 줄었다 ({n_before} → {n_after}) — 검색이 아니라 목록이다")
    active = box.get_attribute("aria-activedescendant")
    if not active:
        fails.append("aria-activedescendant 가 없다 — 스크린리더가 지금 짚은 후보를 못 읽는다")
    chain["ui_state"] = f"combobox «{label}» 키보드 조작 — 후보 {n_before} → {n_after}"

    before_url = page.url
    calls.clear()
    page.keyboard.press("Enter")
    page.wait_for_timeout(1600)
    after_url = page.url
    step.append(f"Enter 로 골랐다: {before_url.split('#')[-1]} → {after_url.split('#')[-1]}")
    chain["url_query"] = after_url.split("#")[-1]
    if before_url == after_url:
        fails.append("고른 값이 주소에 남지 않는다 — 새로고침·뒤로가기에서 조건이 사라진다")
    hit = [u for u in calls if "project_id=" in u or "assignee" in u]
    chain["api_request"] = (hit[0].split("?")[-1][:120] if hit else "")
    if not hit:
        fails.append("고른 조건이 서버 질의에 실리지 않는다 (요청 %d건 관측)" % len(calls))
    line = page.query_selector('[data-result-line]')
    chain["rendered"] = (line.inner_text().strip()[:40] if line else "")
    if not line:
        fails.append("결과 줄이 없다 — 조건과 결과의 관계를 화면이 말하지 않는다")
    shot = _shot(page, out, "keyboard-after-enter")

    # Escape 로 닫아도 고른 값이 유지되는가.
    box.focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if box.get_attribute("aria-expanded") == "true":
        fails.append("Escape 로 목록이 닫히지 않는다")
    step.append("Escape 로 닫았다")

    return {"flow": "entity_combobox_keyboard", "status": "PASS" if not fails else "FAIL",
            "fails": fails, "chain": chain, "steps": step, "shot": shot}


def main() -> int:
    # 콘솔이 cp949 면 한글 인용부호에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 파이프로 넘길 때는 그냥 둔다
            pass
    ap = argparse.ArgumentParser(description="탐색 줄(Search/Filter/Form) 면 계약 + 키보드 사슬 E2E (W5)")
    # 기본 대상은 `capture.DEFAULT_BASE_URL` 한 곳이 정한다 — 사용법 줄마다 호스트를
    # 적어 두면 이름이 바뀌는 날 그 줄들이 조용히 옛 제품을 가리킨다(W5 · F-W5D-129).
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        insecure = tls.apply_default_https_context()
    print(tls.describe())

    from playwright.sync_api import sync_playwright

    surfaces: list[dict] = []
    flows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        sess = ensure_session(browser, base, REPO_ROOT / "dist" / "ui-qa",
                              insecure=args.insecure, log=print)

        # 좁은 화면을 포함한다 — 줄바꿈은 폭에서만 정해진다.
        for vp in (Viewport("390x844", 390, 844), Viewport("1366x768", 1366, 768),
                   Viewport("1920x1080", 1920, 1080), Viewport("3840x2160", 3840, 2160)):
            for theme in ("light", "dark"):
                ctx = new_context(browser, storage_state=sess.storage_state,
                                  user_id=sess.user_id, theme=theme, viewport=vp,
                                  insecure=args.insecure)
                page = ctx.new_page()
                for name, path in ROUTES:
                    tag = f"{name}-{theme}-{vp.name}"
                    try:
                        _goto(page, base, path)
                        m = page.evaluate(MEASURE_JS)
                    except Exception as exc:  # noqa: BLE001
                        surfaces.append({"label": tag, "error": str(exc)[:140],
                                         "ok": False, "checked": 0,
                                         "fails": ["화면을 열지 못했다"]})
                        continue
                    m["label"], m["route"], m["theme"], m["viewport"] = tag, path, theme, vp.name
                    if vp.name == "1920x1080" and theme == "light":
                        m["shot"] = _shot(page, out, f"surface-{tag}")
                    surfaces.append(m)
                ctx.close()

        # 키보드 사슬 — 한 조합에서만 돌린다(상호작용은 폭이 아니라 배선의 문제다).
        ctx = new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id,
                          theme="light", viewport=Viewport("1920x1080", 1920, 1080),
                          insecure=args.insecure)
        page = ctx.new_page()
        try:
            flows.append(keyboard_flow(page, base, out))
        except Exception as exc:  # noqa: BLE001
            flows.append({"flow": "entity_combobox_keyboard", "status": "FAIL",
                          "fails": [f"{type(exc).__name__}: {exc}"[:160]], "chain": {}, "steps": []})
        ctx.close()
        browser.close()

    (out / "surfaces.json").write_text(json.dumps(surfaces, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "flows.json").write_text(json.dumps(flows, ensure_ascii=False, indent=1), encoding="utf-8")

    bad = [s for s in surfaces if not s.get("ok")]
    print("\n== 탐색 줄 면 계약 ==")
    print("  조합 %d개 · 통과 %d · 실패 %d" % (len(surfaces), len(surfaces) - len(bad), len(bad)))
    for s in bad[:12]:
        print("  [FAIL] %-28s %s" % (s.get("label"), "; ".join(s.get("fails") or [])[:150]))
    print("\n== 키보드 사슬 ==")
    for f in flows:
        print("  [%s] %s" % (f["status"], f["flow"]))
        for k, v in (f.get("chain") or {}).items():
            print("      %-12s %s" % (k, v or "(비어 있음)"))
        for x in f.get("fails") or []:
            print("      - %s" % x)
    ok = not bad and all(f["status"] == "PASS" for f in flows)
    print("\nFILTER_E2E_%s (surfaces %d · flows %d)" % ("OK" if ok else "FAILED", len(surfaces), len(flows)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
