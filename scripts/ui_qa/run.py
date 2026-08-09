"""Entry point for the UI QA harness.

  .venv/Scripts/python.exe -m scripts.ui_qa.run --label pre \
      --routes smoke --viewports 1366x768 1920x1080 3840x2160

Always writes ``dist/ui-qa/<label>/results.json`` and ``report.html``; exits
non-zero only when a class listed in ``--fail-on`` actually failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/ui_qa/run.py` too
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.ui_qa"

from . import assertions, capture, report, routes as routes_mod  # noqa: E402
from .auth import AuthError, ensure_session  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "dist" / "ui-qa"
EXIT_OK, EXIT_ASSERTION, EXIT_HARNESS = 0, 1, 2


def _log(message: str = "") -> None:
    print(message, flush=True)


def _split_csv(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def _probe_server(base_url: str, insecure: bool = False) -> tuple[bool, str]:
    """Fail fast (and loudly) if the real server is not there.

    A harness that quietly falls back to ``page.set_content()`` measures nothing;
    if we cannot reach 127.0.0.1 we say so and stop.
    """
    url = f"{base_url.rstrip('/')}/readyz"
    try:
        ctx = ssl._create_unverified_context() if insecure else None
        with urllib.request.urlopen(url, timeout=10, context=ctx) as response:
            body = response.read(200).decode("utf-8", "replace")
            return response.status == 200, f"HTTP {response.status} {body.strip()}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} ({url})"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc} ({url})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.ui_qa.run",
        description="React SPA 시각/기하 QA — 라우트 × 테마 × 뷰포트 스크린샷과 검사",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--routes", nargs="*", default=None,
                        help="라우트 id / 해시 경로 / all|smoke|user|admin|detail (기본: all)")
    parser.add_argument("--viewports", nargs="*", default=None,
                        help=f"기본 전체: {', '.join(v.name for v in capture.VIEWPORTS)}")
    parser.add_argument("--themes", nargs="*", default=None, help="light dark (기본: 둘 다)")
    parser.add_argument("--label", default="baseline",
                        help="dist/ui-qa/<label>/ 아래에 저장 (예: pre, post)")
    parser.add_argument("--fail-on", nargs="*", default=None,
                        help=f"치명 처리할 검사 항목: {', '.join(assertions.CLASSES)} (또는 all)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--rebuild-auth", action="store_true", help="세션 캐시를 무시하고 재로그인")
    parser.add_argument(
        "--insecure", action="store_true",
        help=("자체서명 인증서를 신뢰한다. 사내 서버(https://…gooddi.lab)를 겨눌 때 필요하다. "
              "SSH 터널로 http 로 우회하는 방법은 쓰지 마라 — 서버가 COOKIE_SECURE=true 라 "
              "Playwright 의 API 클라이언트가 http 로는 세션 쿠키를 안 실어 /api/me 가 401 이 된다."))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=capture.DEFAULT_SETTLE_MS)
    parser.add_argument("--timeout-ms", type=int, default=capture.DEFAULT_NAV_TIMEOUT_MS)
    parser.add_argument("--no-full-page", action="store_true", help="뷰포트만 캡처")
    parser.add_argument("--ignore-console", nargs="*", default=None,
                        help="콘솔 오류에서 제외할 정규식")
    parser.add_argument(
        "--modals", action="store_true",
        help="화면을 눌러 모달을 열어 검사한다. 클릭이 화면 상태를 바꾸므로 스크린샷과 "
             "기존 검사가 끝난 뒤에만 돈다. 되돌릴 수 없는 동작(삭제·전송·실행 등)은 "
             "interact.DENY 가 막는다.")
    parser.add_argument("--list", action="store_true", help="라우트 목록만 출력하고 종료")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:  # Korean labels must survive a cp949 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = build_parser().parse_args(argv)

    if args.list:
        for route in routes_mod.ALL_ROUTES:
            path = route.hash_template or route.hash_path
            _log(f"{route.id:<26} {route.console:<5} {path:<22} {route.min_role:<12} {route.label}")
        _log(f"총 {len(routes_mod.ALL_ROUTES)}개")
        return EXIT_OK

    selected_routes = routes_mod.resolve(_split_csv(args.routes) or None)
    viewports = capture.resolve_viewports(_split_csv(args.viewports) or None)
    themes = capture.resolve_themes(_split_csv(args.themes) or None)
    fail_on = _split_csv(args.fail_on)
    if "all" in fail_on:
        fail_on = list(assertions.CLASSES)
    unknown = [c for c in fail_on if c not in assertions.CLASSES]
    if unknown:
        _log(f"알 수 없는 --fail-on 항목: {', '.join(unknown)}")
        _log(f"가능한 값: {', '.join(assertions.CLASSES)}")
        return EXIT_HARNESS
    ignores = assertions.compile_ignores(_split_csv(args.ignore_console))

    out_base = Path(args.out_dir)
    out_root = out_base / args.label
    out_root.mkdir(parents=True, exist_ok=True)

    total = len(selected_routes) * len(themes) * len(viewports)
    started_at = datetime.now()
    _log("=" * 78)
    _log(f"UI QA  label={args.label}  base-url={args.base_url}")
    _log(f"라우트 {len(selected_routes)} × 테마 {len(themes)} × 뷰포트 {len(viewports)} = {total} 페이지")
    _log(f"출력: {out_root}")
    _log("=" * 78)

    ok, detail = _probe_server(args.base_url, args.insecure)
    if not ok:
        _log(f"[FATAL] 서버에 닿을 수 없습니다: {detail}")
        _log("        먼저 서버를 띄우세요:")
        _log("        .venv/Scripts/python.exe -m uvicorn app.main:create_app --factory "
             "--host 127.0.0.1 --port 8080")
        return EXIT_HARNESS
    _log(f"[server] {detail}")

    build_before = capture.build_fingerprint()
    if build_before.get("error"):
        _log(f"[FATAL] {build_before['error']}")
        return EXIT_HARNESS
    _log(f"[build ] index {build_before['index_sha256']} "
         f"({build_before['index_mtime']}) assets={len(build_before['assets'])}")

    from playwright.sync_api import sync_playwright

    notes: list[str] = []
    pages: list[dict] = []
    out_of_reach: list = []   # 이 역할로 볼 수 없어 찍지 않은 라우트 (QA-12)
    clock = time.perf_counter()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        try:
            try:
                session = ensure_session(browser, args.base_url, out_base,
                                         rebuild=args.rebuild_auth, log=_log,
                                         insecure=args.insecure)
            except AuthError as exc:
                _log(f"[FATAL] 세션을 만들지 못했습니다: {exc}")
                return EXIT_HARNESS

            # 🔴 이 계정의 역할로 **볼 수 없는** 라우트를 먼저 걷어낸다.
            # 찍으면 권한 거부 배너가 나오고, 21개 검사가 그 배너를 기준으로 전부 통과해
            # 요약에 `ok` 로 올라간다 — 화면이 아니라 배너를 검사한 것이다(BACKLOG `QA-12`).
            # 커버리지 숫자를 정직하게 유지하려면 `ok` 가 아니라 **미검사**로 세야 한다.
            out_of_reach = [r for r in selected_routes if not r.visible_to(session.role)]
            if out_of_reach:
                selected_routes = [r for r in selected_routes if r.visible_to(session.role)]
                for route in out_of_reach:
                    need = " | ".join(route.allowed_roles) or f"{route.min_role} 이상"
                    notes.append(
                        f"{route.id} ({route.label}) **권한부족(미검사)** — "
                        f"이 계정은 {session.role}, 필요한 역할 {need}")
                _log(f"[capture] 역할 {session.role} 로 볼 수 없는 라우트 {len(out_of_reach)}개를 "
                     f"**미검사**로 제외했습니다: "
                     + ", ".join(r.id for r in out_of_reach))

            # Resolve detail-route ids once, with the session's own permissions.
            detail_hashes: dict[str, str] = {}
            probe_ctx = browser.new_context(storage_state=session.storage_state,
                                            ignore_https_errors=args.insecure)
            try:
                for route in selected_routes:
                    if not route.is_detail:
                        continue
                    resolved, note = capture.discover_detail_hash(
                        probe_ctx, args.base_url, route, log=_log)
                    if resolved:
                        detail_hashes[route.id] = resolved
                        _log(f"[capture] {route.id}: {note}")
                    else:
                        notes.append(f"{route.id} ({route.label}) 건너뜀 — {note}")
                        _log(f"[capture] {route.id}: SKIP — {note}")
            finally:
                probe_ctx.close()

            # Unresolvable detail routes drop out of the plan; keep the progress
            # counter honest rather than counting to a total we will never hit.
            capturable = [r for r in selected_routes
                          if not r.is_detail or r.id in detail_hashes]
            total = len(capturable) * len(themes) * len(viewports)
            if len(capturable) != len(selected_routes):
                _log(f"[capture] 촬영 대상 {len(capturable)}/{len(selected_routes)} 라우트 "
                     f"→ {total} 페이지")

            # 로그인 화면은 **세션이 있으면 못 찍는다**(홈으로 튕긴다). 그래서 같은
            # 테마·해상도 안에서 컨텍스트를 둘로 나눈다: 로그인된 것과 아닌 것.
            signed_in = [r for r in capturable if not r.is_public]
            signed_out = [r for r in capturable if r.is_public]

            index = 0
            for theme in themes:
                for viewport in viewports:
                    for group, state in ((signed_out, None), (signed_in, session.storage_state)):
                        if not group:
                            continue
                        context = capture.new_context(
                            browser, storage_state=state,
                            user_id=session.user_id, theme=theme, viewport=viewport,
                            insecure=args.insecure)
                        page = context.new_page()
                        try:
                            for route in group:
                                index += 1
                                hash_path = detail_hashes.get(route.id, route.hash_path)
                                record = capture.capture_route(
                                    page, base_url=args.base_url, route=route,
                                    hash_path=hash_path, theme=theme, viewport=viewport,
                                    out_root=out_root, full_page=not args.no_full_page,
                                    settle_ms=args.settle_ms, timeout_ms=args.timeout_ms,
                                    ignores=ignores, interact_modals=args.modals)
                                pages.append(record)
                                failures = [n for n, v in (record.get("assertions") or {}).items()
                                            if v.get("status") == "fail"]
                                status = ("FAIL " + ",".join(failures)) if failures else "ok"
                                _log(f"[{index:>4}/{total}] {theme:<5} {viewport.name:<13} "
                                     f"{route.id:<26} {status}")
                        finally:
                            page.close()
                            context.close()
        finally:
            browser.close()

    elapsed = time.perf_counter() - clock
    build_after = capture.build_fingerprint()
    if build_after.get("index_sha256") != build_before.get("index_sha256"):
        warning = (
            "프런트엔드 번들이 실행 도중 바뀌었습니다 "
            f"({build_before.get('index_sha256')} → {build_after.get('index_sha256')}). "
            "이 결과는 두 빌드가 섞여 있어 기준선으로 쓸 수 없습니다 — 다시 실행하세요."
        )
        notes.insert(0, warning)
        _log(f"[WARN] {warning}")

    summary = assertions.summarize(pages)
    fatal = sorted({
        name for record in pages
        for name, verdict in (record.get("assertions") or {}).items()
        if verdict.get("status") == "fail" and name in fail_on
    })

    results = {
        "run": {
            "label": args.label,
            "base_url": args.base_url,
            "account": session.email,
            "role": session.role,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 1),
            "themes": themes,
            "viewports": [v.name for v in viewports],
            "routes": [r.id for r in selected_routes],
            # 이 실행의 역할로 볼 수 없어 **찍지 않은** 라우트. 커버리지를 계산하는 쪽이
            # 이 목록을 빼지 않으면 "70라우트 전부 ok" 같은 허수가 나온다(`QA-12`).
            "routes_out_of_reach": [
                {"id": r.id, "label": r.label, "min_role": r.min_role,
                 "allowed_roles": list(r.allowed_roles)} for r in out_of_reach
            ],
            "fail_on": fail_on,
            "full_page": not args.no_full_page,
            "pages_captured": len(pages),
            "build_before": build_before,
            "build_after": build_after,
        },
        "route_inventory": routes_mod.inventory(),
        "summary": summary,
        "notes": notes,
        "pages": pages,
    }
    results_path = capture.write_manifest(out_root, results)
    report_path = report.build(results, out_root)

    _log("")
    _log("=" * 78)
    _log(f"검사 요약 ({len(pages)} 페이지, {elapsed:.1f}s)")
    _log(f"{'검사 항목':<24} {'통과':>6} {'실패':>6} {'건너뜀':>7}   비고")
    never_ran: list[str] = []
    for name in assertions.CLASSES:
        counts = summary.get(name, {})
        passed, failed, skipped = (counts.get('pass', 0), counts.get('fail', 0),
                                   counts.get('skip', 0))
        # 🔴 `통과 0 / 실패 0 / 건너뜀 N` 은 요약만 보면 "문제 없음"으로 읽힌다.
        # 실제로는 **이 검사가 한 번도 돌지 않았다**는 뜻이다 — `tiny_text` 가 폭 2200
        # 미만에서 전부 skip 이라 1920 캡처의 요약이 늘 그렇게 나왔고, 3840 으로 다시
        # 돌리자 6/6 실패였다(BACKLOG `QA-10`). skip 과 pass 를 눈으로 구분시킨다.
        mark = ""
        if passed == 0 and failed == 0 and skipped:
            mark = "  ← 한 번도 돌지 않음"
            never_ran.append(name)
        _log(f"{name:<24} {passed:>6} {failed:>6} {skipped:>7}{mark}")
    if never_ran:
        _log("")
        _log(f"[주의] 이 실행에서 **한 번도 돌지 않은 검사 {len(never_ran)}개**: "
             + ", ".join(never_ran))
        _log("       통과가 아니라 미실행이다. 게이트 조건(뷰포트·모달 등)을 맞춰 다시 돌려야 한다.")
    if notes:
        _log("")
        _log("메모:")
        for note in notes:
            _log(f"  - {note}")
    _log("")
    _log(f"results.json : {results_path}  ({results_path.stat().st_size:,} bytes)")
    _log(f"report.html  : {report_path}  ({report_path.stat().st_size:,} bytes)")

    if fatal:
        _log("")
        _log(f"[FAIL] 치명 검사 실패: {', '.join(fatal)}")
        return EXIT_ASSERTION
    _log(f"[OK] 치명 검사 실패 없음 (--fail-on={','.join(fail_on) or '(없음)'})")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
