"""Entry point for the UI QA harness.

  .venv/Scripts/python.exe -m scripts.ui_qa.run --label pre \
      --routes smoke --viewports 1366x768 1920x1080 3840x2160

Always writes ``dist/ui-qa/<label>/results.json`` and ``report.html``; exits
non-zero only when a class listed in ``--fail-on`` actually failed.

``--findings-out`` 를 주면 실패한 Assertion 을 Finding stub JSON 으로도 남긴다. 실행 요약은
휘발되고 ``results.json`` 은 584페이지짜리라 아무도 다시 열지 않는다 — 결함 목록은 따로
있어야 추적된다.

요약표의 **억제** 열은 ``docs/ui-renewal/QA_SUPPRESSIONS.md`` 에서 읽는다. 초록 실행이
무엇을 침묵시킨 채 초록인지 요약만 보고도 알 수 있어야 한다.
"""

from __future__ import annotations

import argparse
import hashlib
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
SUPPRESSIONS_DOC = REPO_ROOT / "docs" / "ui-renewal" / "QA_SUPPRESSIONS.md"
EXIT_OK, EXIT_ASSERTION, EXIT_HARNESS = 0, 1, 2

# Finding stub 의 심각도. 규칙은 하나다 —
#   critical  화면이 뜨지 않았거나 예외로 죽었다. 아래 판정 전부가 무의미해진다.
#   high      사용자가 값을 **잘못 읽거나**(정렬·대비·잘림·읽을 수 없는 글자),
#             **누르지 못하거나**(가림·못 닫는 모달), 제품 정체성이 **없다**(브랜드·마스코트).
#             `QA_SUPPRESSIONS.md` 가 억제를 금지한 클래스는 전부 여기에 있다.
#   medium    공간을 잘못 썼다(빈 캔버스·비율·반복·밀려난 줄). 읽히기는 한다.
# 표에 없는 클래스는 SEVERITY_DEFAULT 로 적고 **경고를 찍는다** — 새 Assertion 이 조용히
# medium 으로 흘러 들어가면 그게 곧 침묵이다.
SEVERITY_BY_CLASS = {
    "auth_ok": "critical",
    "page_errors": "critical",
    "theme_applied": "high",
    "horizontal_overflow": "high",
    "console_errors": "high",
    "broken_images": "high",
    "duplicate_ids": "medium",
    "tiny_text": "high",
    "narrow_main": "medium",
    "vertical_text_collapse": "high",
    "fab_overlap": "high",
    "image_cropped": "high",
    "content_clipped": "high",
    "rail_wider_than_prose": "medium",
    "modal_footer_outside_actions": "medium",
    "modal_full_width_buttons": "medium",
    "modal_offscreen": "high",
    "modal_no_close": "high",
    "modal_cannot_close": "high",
    "modal_radius": "medium",
    "modal_width_spread": "medium",
    "contrast": "high",
    # 정렬/대비/브랜드 계열 신규 Assertion
    "header_cell_alignment_mismatch": "high",
    "numeric_alignment": "high",
    "control_baseline_mismatch": "high",
    "brand_presence": "high",
    # W1 이 이 검사를 추가하면서 severity 표에는 안 넣었다 — 그래서 매 실행이 "표에 없는
    # 검사 1개" 경고를 찍고 SEVERITY_DEFAULT 로 흘려보냈다. 그 경고는 **사람이 분류하라는
    # 뜻**이므로 여기서 분류한다: 이 검사가 실패하면 화면에 있는 Brand 자리가 회색이라는
    # 뜻이고, 그건 위 규칙의 "제품 정체성이 없다" 에 해당한다(D-180).
    "brand_role_coverage": "high",
    "mascot_visible_size": "high",
    "plain_dropdown_for_entity": "high",
    # 공간 계열 신규 Assertion
    "equal_column_split": "medium",
    "column_width_vs_content": "medium",
    "isolated_control_row": "medium",
    "oversized_empty_surface": "medium",
    "dead_blank_region": "medium",
    "detail_side_imbalance": "medium",
    "surface_repetition": "medium",
}
SEVERITY_DEFAULT = "high"
SEVERITY_ORDER = ("critical", "high", "medium")
FINDING_MAX_SAMPLES = 5


def _log(message: str = "") -> None:
    print(message, flush=True)


def _split_csv(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def check_marker(passed: int, failed: int, skipped: int) -> tuple[str, str]:
    """요약표 한 줄의 비고 문구와 소속 버킷 — 통과/건너뜀을 눈으로 구분시킨다.

    `통과 0 / 실패 0 / 건너뜀 N`은 요약만 보면 "문제 없음"으로 읽힌다. 실제로는
    **이 검사가 한 번도 돌지 않았다**는 뜻이다 — `tiny_text`가 폭 2200 미만에서 전부
    skip이라 1920 캡처의 요약이 늘 그렇게 나왔고, 3840으로 다시 돌리자 6/6 실패였다
    (BACKLOG `QA-10`).

    한 번도 안 돈 것만 문제가 아니다 — `narrow_main`(3840 이상에서만 돈다)처럼 **일부만**
    돈 검사는 `통과 6 / 실패 0 / 건너뜀 60`으로 나와 `never_ran` 조건(통과·실패 둘 다 0)에
    안 걸린다. 그래도 "통과 6"만 보면 이번 실행 대부분을 확인한 것처럼 보이는데, 실제로는
    건너뜀이 통과·실패를 합친 것보다 많다 — 이 실행이 본 것보다 못 본 것이 더 많다는 뜻이다
    (BACKLOG `QA-13`, `never_ran`과 같은 착시의 옅은 버전이라 다른 마커로 구분한다).

    `통과 0 / 실패 0 / 건너뜀 0`은 **skip 조차 없는** 상태다 — 그 검사는 판정 자체를
    만들지 않았다(`--modals` 없이 돌린 모달 7종이 매 실행 그렇다: `classify`가 그 키를
    아예 넣지 않아 `summarize`에 0/0/0으로만 남는다). 요약표에서 `0 0 0`은 가장 조용한
    줄이라 "볼 게 없었다"로 읽히지만 실제로는 건너뜀 전부와 같은 뜻이고 오히려 더 심하다
    — 그래서 같은 `never_ran`으로 센다.
    """
    if passed == 0 and failed == 0:
        return "  ← 한 번도 돌지 않음", "never_ran"
    if skipped and skipped > passed + failed:
        return "  ← 대부분 건너뜀", "mostly_skipped"
    return "", ""


def suppression_marker(failed: int, suppressed: int) -> str:
    """억제가 실패보다 많은 클래스에 붙는 경고 — `check_marker` 와 같은 자리, 다른 문구.

    억제 3건 · 실패 1건이면 이 검사는 "거의 통과"가 아니라 **거의 꺼져 있다**. 억제를
    하나씩 늘리며 초록을 만드는 흐름은 `건너뜀`이 통과처럼 읽히던 착시와 같은 종류이고
    (`check_marker` 참조), 요약을 보는 사람이 그것을 알아채지 못하면 억제 목록은 아무도
    다시 읽지 않는다. `QA_SUPPRESSIONS.md` 규칙 6이 요구하는 표시가 이것이다.
    """
    if suppressed and suppressed > failed:
        return f"  ← 억제({suppressed})가 실패({failed})보다 많음"
    return ""


def read_suppressions(path: Path = SUPPRESSIONS_DOC) -> tuple[dict[str, int] | None, str]:
    """`QA_SUPPRESSIONS.md` 의 표에서 클래스별 억제 행 수를 센다.

    읽지 못하면 `(None, 사유)` 다. **0건과 모름을 같은 값으로 돌려주지 않는다** — 파일이
    없다는 이유로 "억제 0건"을 찍으면 그 실행은 자기가 무엇을 침묵시켰는지 모른 채 초록이 된다.
    """
    if not path.is_file():
        return None, f"{path} 없음"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"

    counts: dict[str, int] = {}
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False  # 표 밖의 산문이 끼면 그 표는 끝난 것이다
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0].strip("*` ").lower() == "id" and cells[1].strip("*` ").lower() == "assertion":
            in_table = True
            continue
        if not in_table:
            continue
        if set("".join(cells)) <= set("-: "):  # `|---|---|` 구분선
            continue
        name = cells[1].strip("`* ")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts, ""


def finding_id(cls: str, surface_id: str, route: str, theme: str, viewport: str) -> str:
    """같은 결함은 재실행에서도 같은 id 를 갖는다.

    라벨(`before-renewal` / `after-…`)은 **일부러 빼둔다**. 같은 화면의 같은 결함이
    before 와 after 에서 다른 id 를 받으면 "고쳤는가"를 id 로 물을 수 없다. 샘플 문자열도
    뺀다 — 셀 안의 상대 시각("14일 전") 같은 값이 실행마다 달라 id 가 흔들린다.
    """
    key = "|".join((cls, surface_id, route, theme, viewport))
    return "F-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def load_prior_findings(path: Path) -> list[dict]:
    """이전 findings 파일의 행들. 없거나 깨졌으면 빈 목록 — 이번 실행이 첫 관측이다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def first_seen_map(prior: list[dict]) -> dict[str, str]:
    """이전 findings 의 `first_seen` 을 이어받는다 — 재실행이 결함의 나이를 지우면 안 된다."""
    return {row["id"]: row["first_seen"] for row in prior
            if row.get("id") and row.get("first_seen")}


def dropped_unseen(prior: list[dict], findings: list[dict],
                   covered: set) -> list[dict]:
    """이전 파일에 있었는데 이번 실행이 **보지도 않은** 결함.

    `--findings-out` 은 파일을 통째로 덮어쓴다. 좁은 재실행(`--routes smoke`, 한 뷰포트만)이
    전체 실행의 목록을 덮으면 나머지 결함은 고쳐져서가 아니라 **아무도 다시 보지 않았기
    때문에** 사라진다. 파일에서 조용히 없어진 결함은 다음에 이 파일을 읽는 사람에게
    "고쳐졌다"로 읽힌다 — 그러면 이 파일은 추적 장치가 아니라 그 반대가 된다.

    같은 화면을 다시 찍었는데 실패가 사라진 것은 정상(고쳐졌을 수 있다)이라 세지 않는다.
    구분 기준은 이번 실행이 그 `(route, theme, viewport)` 를 실제로 찍었는가 하나뿐이다.
    """
    current = {f["id"] for f in findings}
    return [row for row in prior
            if row.get("id") not in current
            and (row.get("route"), row.get("theme"), row.get("viewport")) not in covered]


def build_findings(pages: list[dict], *, label: str, surfaces: dict[str, str],
                   seen_at: str, first_seen: dict[str, str]) -> tuple[list[dict], list[str]]:
    """fail 인 Assertion 하나를 Finding stub 하나로 옮긴다.

    Stub 이지 Finding 이 아니다 — 원인·수정·검증은 사람이 채운다. 여기서 하는 일은
    **실행이 끝나면 사라지던 실패를 파일로 남기는 것**뿐이다.
    """
    findings: list[dict] = []
    unmapped: set[str] = set()
    for record in pages:
        route = record.get("route") or "?"
        theme = record.get("theme") or "?"
        viewport = record.get("viewport") or "?"
        surface_id = surfaces.get(route, route)
        for name, verdict in sorted((record.get("assertions") or {}).items()):
            if verdict.get("status") != "fail":
                continue
            if name not in SEVERITY_BY_CLASS:
                unmapped.add(name)
            ident = finding_id(name, surface_id, route, theme, viewport)
            count = verdict.get("count") or 0
            note = (verdict.get("note") or "").strip()
            title = (f"{name} — {record.get('label') or route} "
                     f"({theme}/{viewport}) {count}건")
            findings.append({
                "id": ident,
                "class": name,
                "severity": SEVERITY_BY_CLASS.get(name, SEVERITY_DEFAULT),
                "surface_id": surface_id,
                "route": route,
                "theme": theme,
                "viewport": viewport,
                "title": f"{title} — {note}" if note else title,
                "samples": list(verdict.get("samples") or [])[:FINDING_MAX_SAMPLES],
                "label": label,
                "first_seen": first_seen.get(ident, seen_at),
            })
    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"])
                                 if f["severity"] in SEVERITY_ORDER else len(SEVERITY_ORDER),
                                 f["class"], f["surface_id"], f["viewport"], f["theme"]))
    return findings, sorted(unmapped)


def unverified_gates(summary: dict, gates: list[str]) -> list[str]:
    """`--fail-on` 으로 걸었는데 이번 실행에서 **판정을 하나도 내지 않은** 검사.

    `fatal` 은 `status == "fail"` 인 것만 모은다. 그래서 게이트로 건 검사가 전부 skip
    이거나(뷰포트 게이트에 안 걸림) 기록조차 없으면(`--modals` 없이 건 모달 검사) `fatal`
    이 비고 종료 코드 0 과 `[OK] 치명 검사 실패 없음` 이 나간다. 그 줄을 읽는 쪽은 "이
    게이트가 통과했다"로 읽지만 사실은 **게이트가 꺼져 있었다** — QA-10 이 요약표에서
    고친 착시를 종료 코드가 그대로 되풀이하고 있었다.

    `--fail-on all` 은 이 판정에서 뺀다(호출부). `all` 은 "돌아간 것 전부에 걸겠다"는
    쓸어담기라 `--modals` 없는 실행에서 모달 7종이 늘 미실행이고, 그것까지 실패로 만들면
    이 규칙은 첫날 꺼진다. 이름을 **직접 적은** 게이트만 의도로 본다.
    """
    blind = []
    for name in gates:
        counts = summary.get(name, {})
        if counts.get("pass", 0) == 0 and counts.get("fail", 0) == 0:
            blind.append(name)
    return blind


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
    parser.add_argument(
        "--findings-out", default=None, metavar="PATH",
        help=("실패한 Assertion 을 Finding stub JSON 배열로 쓴다. id 는 클래스·Surface·"
              "테마·뷰포트에서 만든 안정 해시라 재실행·다른 라벨에서도 같은 결함이 같은 "
              "id 를 갖는다. 이미 있는 파일의 first_seen 은 이어받는다."))
    parser.add_argument("--rebuild-auth", action="store_true", help="세션 캐시를 무시하고 재로그인")
    parser.add_argument(
        "--role", default=None, choices=sorted(routes_mod.ROLE_RANK, key=routes_mod.ROLE_RANK.get),
        help=("기본 system_admin. user/operator/auditor/admin 으로 돌리면 그 역할이 실제로 "
              "보는 메뉴·데이터 범위·권한부족(미검사) 처리를 검증할 수 있다(QA-05) — "
              "route.visible_to()/out_of_reach 로직은 이미 있었지만 지금까지 system_admin "
              "말고 다른 역할로 돈 적이 없었다(system_admin은 전부 보이므로 그 로직이 한 번도 "
              "실제로 갈라지지 않았다). 역할마다 별도 계정 + 별도 세션 캐시(--out-dir/auth-<role>)를 쓴다."),
    )
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
    fail_on_is_all = "all" in fail_on
    if fail_on_is_all:
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
    # 역할별로 계정도 세션 캐시도 분리한다 — 같은 out_dir을 role만 바꿔 재사용하면
    # 매번 "캐시된 역할과 다름"으로 재로그인하게 된다(auth.py의 안전장치, 그 자체는
    # 맞는 동작이지만 반복 실행마다 헛도는 건 낭비다). 기본 역할(system_admin)은
    # 기존 경로를 그대로 써서 이전부터 있던 캐시와 호환된다.
    auth_dir = out_base if not args.role else out_base / f"auth-{args.role}"

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

    build_before = capture.build_fingerprint(base_url=args.base_url, insecure=args.insecure)
    if build_before.get("error"):
        _log(f"[FATAL] {build_before['error']}")
        return EXIT_HARNESS
    # 원격 실행의 지문에는 mtime 이 없다 — 서버가 서브한 바이트를 해시한 것이라 파일 시각이
    # 우리 것이 아니다. 대신 **어디서 읽었는지**(source)를 찍는다. 그 줄이 "이 실행이 무엇을
    # 쟀는가" 를 말한다.
    _origin = build_before.get("index_mtime") or build_before.get("source", "?")
    _log(f"[build ] index {build_before['index_sha256']} "
         f"({_origin}) assets={len(build_before['assets'])}")
    if build_before.get("fallback_reason"):
        _log(f"[build ] 주의 — {build_before['fallback_reason']}")

    from playwright.sync_api import sync_playwright

    notes: list[str] = []
    pages: list[dict] = []
    out_of_reach: list = []   # 이 역할로 볼 수 없어 찍지 않은 라우트 (QA-12)
    clock = time.perf_counter()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        try:
            try:
                session = ensure_session(browser, args.base_url, auth_dir,
                                         rebuild=args.rebuild_auth, log=_log,
                                         insecure=args.insecure, role=args.role)
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
                    for kind in ("signed_out", "signed_in"):
                        group = signed_out if kind == "signed_out" else signed_in
                        if not group:
                            continue
                        state = None
                        if kind == "signed_in":
                            # **세션이 살아 있는지 묶음마다 다시 확인한다.**
                            #
                            # 예전에는 실행 시작에 한 번만 확인했다. 664 페이지 실행은 한
                            # 시간이 넘고, 서버의 세션은 절대 수명(`session_ttl_seconds`,
                            # 기본 8시간)을 갖는다 — **시작 시점에 유효한 것과 끝까지 유효한
                            # 것은 다른 사실이다.** 실제로 W4 의 첫 전량 실행이 286페이지째부터
                            # 로그인 화면을 찍기 시작했고(캐시된 세션이 그 사이 절대 수명에
                            # 닿았다), 남은 379페이지가 전부 같은 로그인 스크린샷이 될 뻔했다.
                            # `auth_ok` 검사가 그것을 fail 로 적기는 하지만, 그때는 이미 한
                            # 시간을 버린 뒤다.
                            #
                            # `ensure_session(rebuild=False)` 은 캐시를 **먼저 검증**하고
                            # 죽었으면 다시 로그인한다. 묶음마다 `/api/me` 한 번이라 비용은
                            # 실행당 여덟 번이고, 그 대가로 "증거가 통째로 로그인 화면" 이라는
                            # 실패 모드가 사라진다.
                            session = ensure_session(
                                browser, args.base_url, auth_dir, rebuild=False, log=_log,
                                insecure=args.insecure, role=args.role)
                            state = session.storage_state
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
    build_after = capture.build_fingerprint(base_url=args.base_url, insecure=args.insecure)
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

    suppressions, suppression_error = read_suppressions(SUPPRESSIONS_DOC)
    suppressed_total = sum(suppressions.values()) if suppressions is not None else None
    suppressed_label = "?" if suppressed_total is None else str(suppressed_total)

    _log("")
    _log("=" * 78)
    _log(f"검사 요약 ({len(pages)} 페이지, {elapsed:.1f}s)")
    # 폭 31 은 가장 긴 검사 이름(`header_cell_alignment_mismatch`, 30자)에 맞춘 값이다 —
    # 이름이 열을 밀어내면 억제 열이 행마다 다른 자리에 찍혀 비교가 안 된다.
    _log(f"{'검사 항목':<31} {'통과':>6} {'실패':>6} {'건너뜀':>7} {'억제':>6}   비고")
    never_ran: list[str] = []
    mostly_skipped: list[str] = []
    over_suppressed: list[str] = []
    for name in assertions.CLASSES:
        counts = summary.get(name, {})
        passed, failed, skipped = (counts.get('pass', 0), counts.get('fail', 0),
                                   counts.get('skip', 0))
        mark, bucket = check_marker(passed, failed, skipped)
        if bucket == "never_ran":
            never_ran.append(name)
        elif bucket == "mostly_skipped":
            mostly_skipped.append(name)
        if suppressions is None:
            suppressed, sup_mark = "?", ""
        else:
            suppressed = suppressions.get(name, 0)
            sup_mark = suppression_marker(failed, suppressed)
            if sup_mark:
                over_suppressed.append(name)
        _log(f"{name:<31} {passed:>6} {failed:>6} {skipped:>7} {suppressed:>6}{mark}{sup_mark}")
    if suppressions is None:
        _log("")
        _log(f"[주의] 억제 목록을 읽지 못했습니다 ({suppression_error}).")
        _log("       억제 0건이라는 뜻이 아니라 **모른다**는 뜻이다 — 위 억제 열은 전부 `?` 다.")
    else:
        stray = sorted(k for k in suppressions if k not in assertions.CLASSES)
        if stray:
            _log("")
            _log(f"[주의] 억제 목록에 **검사 항목이 아닌 이름 {len(stray)}개**: " + ", ".join(stray))
            _log("       오타이거나 이름이 바뀐 검사다. 그 행은 아무것도 억제하지 못한 채 "
                 "억제된 것처럼 보인다.")
    if over_suppressed:
        _log("")
        _log(f"[주의] 이 실행에서 **억제가 실패보다 많은 검사 {len(over_suppressed)}개**: "
             + ", ".join(over_suppressed))
        _log("       초록에 가까운 것이 아니라 거의 꺼져 있는 것이다. "
             "docs/ui-renewal/QA_SUPPRESSIONS.md 의 해당 행을 다시 읽어라.")
    if never_ran:
        _log("")
        _log(f"[주의] 이 실행에서 **한 번도 돌지 않은 검사 {len(never_ran)}개**: "
             + ", ".join(never_ran))
        _log("       통과가 아니라 미실행이다. 게이트 조건(뷰포트·모달 등)을 맞춰 다시 돌려야 한다.")
    if mostly_skipped:
        _log("")
        _log(f"[주의] 이 실행에서 **건너뜀이 우세한 검사 {len(mostly_skipped)}개**: "
             + ", ".join(mostly_skipped))
        _log("       통과 수만 보면 널리 확인된 것처럼 보이지만, 실제로는 이번 실행 대부분에서 건너뛰었다"
             "(예: narrow_main은 3840 이상에서만 돈다 — QA-13).")
    if notes:
        _log("")
        _log("메모:")
        for note in notes:
            _log(f"  - {note}")
    _log("")
    _log(f"results.json : {results_path}  ({results_path.stat().st_size:,} bytes)")
    _log(f"report.html  : {report_path}  ({report_path.stat().st_size:,} bytes)")

    if args.findings_out:
        findings_path = Path(args.findings_out)
        findings_path.parent.mkdir(parents=True, exist_ok=True)
        surfaces = {r["id"]: (r.get("surface_id") or r["id"]) for r in routes_mod.inventory()}
        prior = load_prior_findings(findings_path)
        findings, unmapped = build_findings(
            pages, label=args.label, surfaces=surfaces,
            seen_at=started_at.isoformat(timespec="seconds"),
            first_seen=first_seen_map(prior))
        findings_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        by_severity = ", ".join(
            f"{level} {sum(1 for f in findings if f['severity'] == level)}"
            for level in SEVERITY_ORDER)
        _log(f"findings.json: {findings_path}  ({len(findings)}건 — {by_severity})")
        if unmapped:
            _log(f"[주의] 심각도 표(SEVERITY_BY_CLASS)에 없는 검사 {len(unmapped)}개를 "
                 f"우선 {SEVERITY_DEFAULT} 로 적었습니다: " + ", ".join(unmapped))
        covered = {(r.get("route"), r.get("theme"), r.get("viewport")) for r in pages}
        vanished = dropped_unseen(prior, findings, covered)
        if vanished:
            _log(f"[주의] 이전 findings 의 {len(vanished)}건은 이번 실행이 **찍지 않은** "
                 "화면의 결함이라 이 파일에서 사라졌습니다 (고쳐져서가 아니다): "
                 + ", ".join(f"{v.get('class')}@{v.get('surface_id') or v.get('route')}"
                             for v in vanished[:5])
                 + (f" 외 {len(vanished) - 5}건" if len(vanished) > 5 else ""))
            _log("       좁은 실행이 전체 실행의 목록을 덮었다면 --findings-out 경로를 "
                 "분리하거나 전체 범위로 다시 돌려라.")

    blind = [] if fail_on_is_all else unverified_gates(summary, fail_on)
    if blind:
        _log("")
        _log(f"[FATAL] --fail-on 으로 건 검사 {len(blind)}개가 이번 실행에서 "
             f"**판정을 하나도 내지 않았습니다**: {', '.join(blind)}")
        _log("        통과가 아니라 미실행이다 — 이 게이트는 꺼진 채였다. 게이트 조건"
             "(뷰포트·--modals·역할·라우트 범위)을 맞춰 다시 돌려라.")

    if fatal:
        _log("")
        _log(f"[FAIL] 치명 검사 실패: {', '.join(fatal)}  (억제 {suppressed_label}건)")
        return EXIT_ASSERTION
    if blind:
        return EXIT_HARNESS
    # 초록 줄에도 억제 총량을 반드시 찍는다 — 이 실행이 무엇을 침묵시킨 채 통과했는지
    # 요약만 보는 사람에게도 보여야 한다.
    _log(f"[OK] 치명 검사 실패 없음 (--fail-on={','.join(fail_on) or '(없음)'}), "
         f"억제 {suppressed_label}건")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
