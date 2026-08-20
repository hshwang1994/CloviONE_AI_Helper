"""접근성 시맨틱 실측 — 하네스에 **없는 축**.

`KBD`(포커스)·`CTR`(대비)와 겹치지 않는 부분을 본다: **스크린리더가 이 화면을 이해할 수 있는가.**

  1. 제목 계층 — `h1` 이 하나 있는가, 단계를 건너뛰지 않는가(h1→h3)
  2. 랜드마크 — `main`·`nav`·`banner` 가 있는가(없으면 "본문으로" 이동 자체가 불가능)
  3. **이름 없는 버튼** — 아이콘만 있는 버튼에 `aria-label`·`title`·텍스트가 없으면
     스크린리더는 "버튼"이라고만 읽는다. 이 제품은 아이콘 버튼이 많다
  4. 라벨 없는 입력 — `<label for>`·`aria-label`·`aria-labelledby` 중 아무것도 없는 것
  5. 표 머리 — `th` 가 있는가, `scope` 가 있는가(없으면 셀이 어느 열인지 못 읽는다)
  6. `alt` 없는 이미지 — 장식이면 `alt=""` 가 **명시**돼야 한다(속성 자체가 없으면 파일명을 읽는다)
  7. 중복 `id`(이미 하네스에 있음)와 별개로 **중복 `aria-label`** — 같은 이름 버튼이 여러 개면
     음성 조작이 안 된다
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa.routes import BY_ID  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/semantics")

PROBE = """() => {
  const vis = (el) => { const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1 && getComputedStyle(el).visibility !== 'hidden'; };
  const name = (el) => (
    (el.getAttribute('aria-label') || '') ||
    (el.getAttribute('title') || '') ||
    (el.getAttribute('aria-labelledby') ? 'labelledby' : '') ||
    (el.innerText || '').trim()
  ).trim();

  const heads = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(vis)
    .map(h => ({ level: +h.tagName[1], text: (h.innerText || '').trim().slice(0, 32) }));
  let skips = [];
  for (let i = 1; i < heads.length; i++)
    if (heads[i].level - heads[i - 1].level > 1)
      skips.push(`h${heads[i-1].level}→h${heads[i].level} «${heads[i].text}»`);

  const btns = [...document.querySelectorAll('button,[role=button]')].filter(vis);
  const unnamed = btns.filter(b => !name(b)).map(b => ({
    cls: (b.className || '').toString().slice(0, 42),
    html: b.innerHTML.slice(0, 46),
    box: [Math.round(b.getBoundingClientRect().left), Math.round(b.getBoundingClientRect().top)],
  }));

  const inputs = [...document.querySelectorAll('input,select,textarea')].filter(vis);
  const unlabeled = inputs.filter(i => {
    if (i.getAttribute('aria-label') || i.getAttribute('aria-labelledby')) return false;
    if (i.id && document.querySelector(`label[for="${i.id}"]`)) return false;
    if (i.closest('label')) return false;
    if (i.type === 'hidden') return false;
    return true;
  }).map(i => ({ type: i.type || i.tagName.toLowerCase(),
                 ph: i.placeholder || '', cls: (i.className || '').toString().slice(0, 36) }));

  const tables = [...document.querySelectorAll('table')].filter(vis).map(t => ({
    ths: t.querySelectorAll('th').length,
    scoped: t.querySelectorAll('th[scope]').length,
    rows: t.querySelectorAll('tbody tr').length,
  }));

  const imgs = [...document.querySelectorAll('img')].filter(vis);
  const noAlt = imgs.filter(i => !i.hasAttribute('alt')).map(i => (i.src || '').slice(-40));

  const labels = btns.map(name).filter(Boolean);
  const dupCount = {};
  labels.forEach(l => { dupCount[l] = (dupCount[l] || 0) + 1; });
  const dupes = Object.entries(dupCount).filter(([, n]) => n > 2)
    .sort((a, b) => b[1] - a[1]).slice(0, 5).map(([l, n]) => `${l} ×${n}`);

  return {
    landmarks: {
      main: document.querySelectorAll('main,[role=main]').length,
      nav: document.querySelectorAll('nav,[role=navigation]').length,
      banner: document.querySelectorAll('header,[role=banner]').length,
    },
    h1: heads.filter(h => h.level === 1).length,
    heading_skips: skips.slice(0, 4),
    headings: heads.slice(0, 6),
    buttons: btns.length, unnamed_buttons: unnamed.length, unnamed_samples: unnamed.slice(0, 5),
    inputs: inputs.length, unlabeled_inputs: unlabeled.length, unlabeled_samples: unlabeled.slice(0, 5),
    tables, images: imgs.length, no_alt: noAlt.length, no_alt_samples: noAlt.slice(0, 3),
    duplicate_button_names: dupes,
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*", default=[
        "user_me", "admin_users", "user_my-tickets", "user_chat",
        "admin_jobs", "user_new-ticket", "admin_integrations", "user_team-docs"])
    ap.add_argument("--auth-dir", default="dist/ui-qa-admin-2")
    args = ap.parse_args()

    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path(args.auth_dir), insecure=True, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1600x1000", 1600, 1000), insecure=True)
        page = ctx.new_page()
        for rid in args.routes:
            route = BY_ID.get(rid)
            if route is None:
                continue
            page.goto(f"{BASE}{route.shell}#{route.hash_path}",
                      wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2400)
            got = page.evaluate(PROBE)
            report[rid] = got
            lm = got["landmarks"]
            print(f"{rid:<20} h1={got['h1']} 계층건너뜀={len(got['heading_skips'])} "
                  f"main/nav/banner={lm['main']}/{lm['nav']}/{lm['banner']} "
                  f"이름없는버튼={got['unnamed_buttons']}/{got['buttons']} "
                  f"라벨없는입력={got['unlabeled_inputs']}/{got['inputs']} "
                  f"alt없음={got['no_alt']}/{got['images']} "
                  f"th/scope={[str(x['ths']) + '/' + str(x['scoped']) for x in got['tables']]}",
                  flush=True)
        ctx.close()
        b.close()

    (OUT / "semantics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
