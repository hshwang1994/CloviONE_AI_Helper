"""S21 — 남은 Functional Flow 전부를 **실제 브라우저에서** 돌린다 (W14).

## 왜 실행기를 따로 두는가

엔진은 S18 이 만든 것을 그대로 쓴다(`pilot_e2e.Runner` · `run_flow`). 바꾸는 것은 둘뿐이다.

1. **Flow 표가 다르다.** S18 의 표는 Pilot 17 화면이고, 여기는 나머지 72 화면이다.
2. **한 프로세스가 전부를 돌지 않는다.** 800 건이 한 브라우저 세션에 붙으면 한 번 멈출 때
   전부를 잃는다. `--chunk k/n` 으로 나눠 붙이고 `--merge` 로 합친다(지시 §7 의 bounded batch).

`pilot_e2e.py` 자체는 안 건드린다 — 그 파일은 S18 의 증거를 만든 도구이고, 기본 동작을
바꾸면 그 회차의 기록을 다시 못 만든다(지시 §11).

## 쓰는 법

    python -m scripts.ui_qa.s21_e2e --base-url http://127.0.0.1:8099 --chunk 1/8
    python -m scripts.ui_qa.s21_e2e --surfaces user_my-tickets --out dist/ui-qa/s21-try
    python -m scripts.ui_qa.s21_e2e --merge
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, new_context  # noqa: E402
from scripts.ui_qa.pilot_e2e import (  # noqa: E402
    Backend, Recorder, Runner, VIEWPORT, run_flow,
)

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "s21"


def load_flows():
    from scripts.ui_qa import s21_flows

    return list(s21_flows.FLOWS)


def merge(out: Path) -> int:
    """묶음별 결과를 하나로 합친다 — **뒤에 온 것이 이긴다**(재실행이 앞 결과를 덮는다)."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    parts = sorted(out.glob("flows-*.json"), key=lambda p: p.stat().st_mtime)
    for part in parts:
        payload = json.loads(part.read_text(encoding="utf-8"))
        for rec in payload.get("flows") or []:
            if rec["id"] not in by_id:
                order.append(rec["id"])
            by_id[rec["id"]] = rec
    records = [by_id[i] for i in order]
    (out / "flows.json").write_text(json.dumps(
        {"harness": "s21_e2e", "merged_from": [p.name for p in parts],
         "flows": records}, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in records if r["status"] != "PASS"]
    print("합친 결과: %d Flow · %d 실패 → %s" % (len(records), len(bad), out / "flows.json"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 Functional E2E (W14)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--surfaces", nargs="*", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--chunk", default="", help="k/n — n 묶음 중 k 번째만 (1부터)")
    ap.add_argument("--merge", action="store_true", help="묶음 결과를 합치고 끝낸다")
    ap.add_argument("--list", action="store_true", help="Flow 목록만 인쇄한다")
    ap.add_argument("--session-dir", default="",
                    help="로그인 세션을 둘 자리. 여러 묶음을 동시에 돌릴 때 서로 안 덮게 나눈다")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.merge:
        return merge(out)

    selected = load_flows()
    if args.surfaces:
        selected = [f for f in selected if f.surface in set(args.surfaces)]
    if args.only:
        selected = [f for f in selected if f.id in set(args.only)]
    tag = "all"
    if args.chunk:
        k, n = (int(x) for x in args.chunk.split("/"))
        # **화면 단위로 자른다.** Flow 를 번호로 자르면 같은 화면의 Flow 가 두 묶음으로
        # 갈리고, 앞 Flow 가 열어 둔 상세 주소(`ctx:`)를 뒤 묶음이 못 찾는다.
        surfaces: list[str] = []
        for f in selected:
            if f.surface not in surfaces:
                surfaces.append(f.surface)
        mine = {s for i, s in enumerate(surfaces) if i % n == (k - 1)}
        selected = [f for f in selected if f.surface in mine]
        tag = "%d-of-%d" % (k, n)

    if args.list:
        for f in selected:
            print("%-9s %-34s %-16s %s" % (f.id, f.surface, f.category, f.name[:70]))
        print("총 %d Flow" % len(selected))
        return 0
    if not selected:
        print("[FATAL] 고른 Flow 가 없다.", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    started = time.time()
    records: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            session_dir = (Path(args.session_dir).resolve() if args.session_dir
                           else REPO_ROOT / "dist" / "ui-qa")
            session_dir.mkdir(parents=True, exist_ok=True)
            session = ensure_session(browser, args.base_url, session_dir,
                                     insecure=args.insecure)
            context = new_context(browser, storage_state=session.storage_state,
                                  user_id=session.user_id, theme="light",
                                  viewport=VIEWPORT, insecure=args.insecure)
            page = context.new_page()
            # **없는 것을 30초씩 기다리지 않는다.** 표가 겨눈 컨트롤이 그 화면에 없으면
            # 8초 뒤에도 없다 — 기본 시간 초과를 그대로 두면 실패 하나가 30초를 먹고,
            # 팔백 건짜리 회차에서 그것이 곧 몇 시간이다. 판정은 안 바뀐다(«없다» 는
            # 여전히 «없다»). 오래 걸리는 것이 정상인 자리는 각자 시간을 따로 준다.
            page.set_default_timeout(10_000)
            rec = Recorder(page)
            spec = context.request.get(args.base_url.rstrip("/") + "/openapi.json",
                                       timeout=30_000).json()
            runner = Runner(page, rec, Backend(spec), args.base_url.rstrip("/"), out,
                            browser=browser, insecure=args.insecure)
            runner.session_dir = session_dir
            ctx: dict = {"base": args.base_url.rstrip("/")}
            for flow in selected:
                record = run_flow(flow, runner, ctx)
                records.append(record)
                mark = "OK  " if record["status"] == "PASS" else "FAIL"
                print("[%s] %-8s %-34s %s" % (mark, flow.id, flow.surface, flow.name[:56]),
                      flush=True)
            runner.close_role_pages()
            context.close()
        finally:
            browser.close()

    payload = {"harness": "s21_e2e", "base_url": args.base_url, "chunk": tag,
               "viewport": VIEWPORT.name, "elapsed_s": round(time.time() - started, 1),
               "flows": records}
    (out / ("flows-%s.json" % tag)).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in records if r["status"] != "PASS"]
    print("\n%d Flow 중 %d 실패 · %.1fs" % (len(records), len(bad), payload["elapsed_s"]))
    for r in bad:
        print("  - %s %s: %s" % (r["id"], r["name"][:46], "; ".join(r["notes"])[:150]))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
