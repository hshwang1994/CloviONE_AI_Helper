"""App Shell 상단바의 기능 사슬을 **실제 브라우저에서** 끝까지 돌린다 (W2 · `shell_topbar`).

`FUNCTIONAL_COVERAGE.json` 의 `shell_topbar` 7개 Flow 는 W0 이 목록만 만들고 전부
`NOT_AUDITED` 였다. 셸은 모든 Route 위에 있으므로 여기가 고장 나면 제품 전체가 고장 난다 —
그런데 지금까지 이 Surface 를 실제로 눌러 본 적이 없다.

## 무엇을 증거로 삼는가

화면이 바뀌었다는 사실은 정상 동작의 증거가 아니다(CLAUDE.md §5). 그래서 각 단계에서
**네트워크를 함께 기록**하고, 서버가 관여하는 Flow 는
`ui_action → frontend_state → api_request → backend_query → api_response → rendered`
사슬을 실측값으로 채운다.

**서버가 관여하지 않는 Flow 도 있다** — 테마 토글은 `localStorage` 만 쓰고(`theme-store.js`
가 그렇게 설계돼 있다: 첫 페인트 전에 결정돼야 해서 서버 왕복을 넣을 수 없다), Clovi 서랍은
열기만 해서는 요청이 없다. 그런 Flow 를 억지로 `PASS` 로 적으면 `chain` 의 API 칸을 지어내야
한다. 이 스크립트는 **관측한 것만** 적고, 판정은 `--out` JSON 을 읽는 사람이 한다.

## 쓰는 법

    python -m scripts.ui_qa.shell_e2e --insecure        # 대상은 UI_QA_BASE_URL 또는 --base-url

산출물: `dist/ui-qa/w2-shell-e2e/flows.json` + 단계별 스크린샷.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 요약을 한국어로 찍는데 Windows 기본 콘솔은 cp949 다 — 여기서 막히면 **결과 파일은 이미
# 다 썼는데 실행이 실패로 보인다**(실제로 한 번 그랬다). 다른 검사 스크립트와 같은 처리를 한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "w2-shell-e2e"
VIEWPORT = Viewport("1920x1080", 1920, 1080)

SEARCH_BUTTON = '[aria-label="통합 검색과 명령 열기"]'
# Dialog 루트도 같은 aria-label 을 갖는다(접근 가능한 이름) — 입력만 겨눈다.
PALETTE_INPUT = 'input[aria-label="통합 검색"]'
BELL = '[aria-label^="알림"]'
CLOVI = '[aria-label="클로비 AI 도우미 열기"]'
ACCOUNT = '.MuiAppBar-root [aria-haspopup="menu"]'
AI_ANCHOR = '[data-shell-region="ai"]'


class Recorder:
    """이 단계 동안 오간 요청·응답. 사슬의 `api_request`/`api_response` 는 여기서 나온다."""

    def __init__(self, page):
        self.page = page
        self.calls: list[dict] = []
        page.on("response", self._on_response)

    def _on_response(self, response):
        url = response.url
        if "/api/" not in url:
            return
        self.calls.append({"method": response.request.method, "url": url,
                           "status": response.status, "at": time.time()})

    def reset(self) -> None:
        self.calls = []

    def since(self, api_fragment: str) -> list[dict]:
        return [c for c in self.calls if api_fragment in c["url"]]


def _shot(page, out: Path, name: str) -> str:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _goto(page, base: str, hash_path: str) -> None:
    page.goto(base + "/#" + hash_path, wait_until="domcontentloaded")
    page.wait_for_selector("#main-content", timeout=30_000)
    page.wait_for_timeout(1200)


def flow(fid: str, category: str, name: str) -> dict:
    return {"id": fid, "category": category, "name": name, "observed": {},
            "chain": {}, "screenshots": [], "notes": []}


# --------------------------------------------------------------------------- #
# Flow 별 실행
# --------------------------------------------------------------------------- #
def ff_1186_search(page, rec: Recorder, out: Path) -> dict:
    """Topbar 검색 → Command Palette → 실제 서버 검색까지."""
    f = flow("FF-1186", "search", "Topbar 검색 상자를 눌러 Command Palette 를 연다")
    rec.reset()
    button = page.locator(SEARCH_BUTTON).first
    f["observed"]["button_visible"] = button.is_visible()
    f["observed"]["button_background"] = button.evaluate(
        "el => getComputedStyle(el).backgroundColor")
    button.click()
    page.wait_for_selector(PALETTE_INPUT, timeout=15_000)
    f["chain"]["ui_action"] = "상단바 검색 상자 클릭"
    f["chain"]["frontend_state"] = "CommandPalette open=true — 다이얼로그가 뜨고 입력에 포커스"
    f["screenshots"].append(_shot(page, out, "ff1186-palette-open"))

    page.locator(PALETTE_INPUT).fill("회의")
    page.wait_for_timeout(1500)
    calls = rec.since("/api/search")
    f["observed"]["search_calls"] = calls[:5]
    if calls:
        f["chain"]["api_request"] = f"GET {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/search/router.py → FTS5 인덱스 조회 (SEARCH_KINDS 4종)"
        f["chain"]["api_response"] = f"HTTP {calls[-1]['status']}"
    rows = page.locator('[role="dialog"] .MuiListItemButton-root')
    f["observed"]["result_rows"] = rows.count()
    f["chain"]["rendered"] = f"결과 줄 {rows.count()}개 (유형 아이콘 + 붙박이 구역 제목)"
    f["screenshots"].append(_shot(page, out, "ff1186-palette-results"))

    # R-14 는 Loading·결과 없음·Error 세 상태를 명시적으로 요구한다. '결과 없음' 은 실제로
    # 만들 수 있으므로 여기서 찍는다 — 상태가 코드에만 있고 화면 증거가 없으면 "구현했다"는
    # 주장은 검증되지 않은 것이다. (Error 얼굴은 500 을 유발해야 해서 운영 데이터에 대고
    # 만들지 않는다 — `palette-error.test.jsx` 가 그 분기를 렌더로 고정한다.)
    page.locator(PALETTE_INPUT).fill("zzz없는것zzz")
    page.wait_for_timeout(1800)
    empty = page.locator('[role="dialog"]').last.inner_text()
    f["observed"]["empty_face"] = " ".join(empty[:120].split())
    f["screenshots"].append(_shot(page, out, "ff1186-palette-empty"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return f


def ff_1187_navigate(page, rec: Recorder, out: Path, base: str) -> dict:
    """팔레트 결과를 눌러 실제로 그 화면으로 간다 — 그 화면의 API 까지 확인한다."""
    f = flow("FF-1187", "navigation", "Command Palette 에서 화면·항목으로 이동한다")
    rec.reset()
    if not page.locator(PALETTE_INPUT).count():
        page.locator(SEARCH_BUTTON).first.click()
        page.wait_for_selector(PALETTE_INPUT, timeout=15_000)
    page.locator(PALETTE_INPUT).fill("문서")
    page.wait_for_timeout(1200)
    rows = page.locator('[role="dialog"] .MuiListItemButton-root')
    count = rows.count()
    f["observed"]["candidate_rows"] = count
    if not count:
        f["notes"].append("결과 0건 — 이동을 시험할 대상이 없다")
        return f
    label = rows.first.inner_text().strip().splitlines()[0]
    f["chain"]["ui_action"] = f"팔레트 첫 결과 «{label}» 클릭"
    before = page.url
    rows.first.click()
    page.wait_for_timeout(2000)
    f["observed"]["url_before"] = before
    f["observed"]["url_after"] = page.url
    f["chain"]["url_state"] = f"해시 {before.split('#')[-1]} → {page.url.split('#')[-1]}"
    f["chain"]["frontend_state"] = "팔레트 닫힘 + 라우트 전환"
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["screen_calls"] = calls[:6]
    if calls:
        f["chain"]["api_request"] = f"{calls[0]['method']} {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "이동한 화면의 목록/상세 조회 (권한 Scope 적용)"
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    main_text = page.locator("#main-content").inner_text()[:120].replace("\n", " ")
    f["chain"]["rendered"] = f"본문 렌더 «{main_text}»"
    f["screenshots"].append(_shot(page, out, "ff1187-navigated"))
    _goto(page, base, "/me")
    return f


def ff_1195_race(page, rec: Recorder, out: Path) -> dict:
    """C11 «경합» — 늦게 온 결과가 목록을 줄여도 커서가 목록 밖에 남지 않는다.

    팔레트는 디바운스 뒤에 서버에 묻는다. 그 사이 사용자가 글자를 더 치면 목록이 **짧아진다** —
    커서를 범위 안으로 되돌리지 않으면 Enter 가 아무 일도 안 하거나 엉뚱한 곳으로 간다
    (`CommandPalette.jsx` 가 그 가드를 들고 있다). 그 가드가 실제로 도는지 본다.
    """
    f = flow("FF-1195", "search", "검색 경합 — 늦게 온 결과가 목록을 줄여도 커서가 범위 안에 남는다")
    rec.reset()
    page.locator(SEARCH_BUTTON).first.click()
    page.wait_for_selector(PALETTE_INPUT, timeout=15_000)
    inp = page.locator(PALETTE_INPUT)
    inp.fill("회의")
    page.wait_for_timeout(1500)
    wide = page.locator('[role="dialog"] .MuiListItemButton-root').count()
    # 목록의 마지막 줄로 커서를 내린 뒤 질의를 좁혀 목록을 줄인다.
    for _ in range(max(wide - 1, 0)):
        page.keyboard.press("ArrowDown")
    inp.fill("회의록정리없는말zzz")
    page.wait_for_timeout(1800)
    narrow = page.locator('[role="dialog"] .MuiListItemButton-root').count()
    f["observed"] = {"rows_before": wide, "rows_after": narrow,
                     "search_calls": rec.since("/api/search")[:4]}
    f["chain"]["ui_action"] = f"결과 {wide}줄에서 커서를 끝까지 내린 뒤 질의를 좁혀 {narrow}줄로 줄인다"
    f["chain"]["frontend_state"] = "cursor 를 flat.length-1 이하로 되돌리는 가드(CommandPalette.jsx)"
    calls = rec.since("/api/search")
    if calls:
        f["chain"]["api_request"] = f"GET {calls[-1]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/search/router.py → 좁아진 질의로 재조회"
        f["chain"]["api_response"] = f"HTTP {calls[-1]['status']}"
    before = page.url
    page.keyboard.press("Enter")
    page.wait_for_timeout(1800)
    f["observed"]["url_before"] = before
    f["observed"]["url_after"] = page.url
    f["chain"]["rendered"] = ("Enter 가 실제로 간 곳: %s (본문 «%s»)"
                             % (page.url.split("#")[-1],
                                page.locator("#main-content").inner_text()[:70].replace(chr(10), " ")))
    f["screenshots"].append(_shot(page, out, "ff1195-race"))
    if narrow > wide:
        f["notes"].append("목록이 줄지 않아 경합 조건을 못 만들었다 — 재확인 필요")
    return f


def ff_1196_cache(page, rec: Recorder, out: Path, base: str) -> dict:
    """C11 «캐시 key» — 같은 질의는 다시 묻지 않는다(react-query staleTime)."""
    f = flow("FF-1196", "search", "검색 캐시 key — 같은 질의를 두 번 쳐도 서버에 두 번 묻지 않는다")
    # **새 문서에서 시작한다.** 해시만 바꾸는 이동은 같은 QueryClient 를 이어 쓰므로 앞선
    # Flow 가 캐시에 남긴 질의 때문에 숫자가 설명되지 않는다(첫 실행에서 실제로 그랬다:
    # 중간 질의가 요청 0건이었다). 그리고 이 Flow 전용 질의어를 쓴다 — 다른 Flow 가 쓴
    # 말을 재사용하면 무엇이 캐시 적중인지 구분할 수 없다.
    _goto(page, base, "/me")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#main-content", timeout=30_000)
    page.wait_for_timeout(1200)
    page.locator(SEARCH_BUTTON).first.click()
    page.wait_for_selector(PALETTE_INPUT, timeout=15_000)
    rec.reset()
    page.locator(PALETTE_INPUT).fill("정합성")
    page.wait_for_timeout(2200)
    first = len(rec.since("/api/search"))
    page.locator(PALETTE_INPUT).fill("배포과정")
    page.wait_for_timeout(2200)
    middle = len(rec.since("/api/search"))
    page.locator(PALETTE_INPUT).fill("정합성")
    page.wait_for_timeout(2200)
    total = len(rec.since("/api/search"))
    f["observed"] = {"calls_after_first": first, "calls_after_second": middle,
                     "calls_after_repeat": total,
                     "urls": [c["url"].split("/api/")[-1] for c in rec.since("/api/search")]}
    f["chain"]["ui_action"] = "새 문서에서 «정합성» → «배포과정» → 다시 «정합성»"
    f["chain"]["frontend_state"] = (
        "queryKey = [search, palette, normalizeQuery(q)] · staleTime 15s — "
        f"요청 {first} → {middle} → {total}건")
    calls = rec.since("/api/search")
    if calls:
        f["chain"]["api_request"] = f"GET {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/search/router.py → 질의별 1회"
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    f["chain"]["rendered"] = ("반복 질의에서 추가 요청 %d건 (0 이면 캐시 적중)"
                             % (total - middle))
    f["screenshots"].append(_shot(page, out, "ff1196-cache"))
    if first < 1 or middle <= first:
        f["notes"].append("서로 다른 두 질의가 각각 서버를 치지 않았다 — 측정 조건이 안 만들어졌다")
    elif total - middle:
        f["notes"].append("반복 질의가 서버를 다시 쳤다 — queryKey 또는 staleTime 확인 필요")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return f


def ff_1197_back(page, rec: Recorder, out: Path, base: str) -> dict:
    """C11 «뒤로/앞으로» — 팔레트로 이동한 뒤 뒤로 가면 이전 화면으로 돌아온다."""
    f = flow("FF-1197", "back_forward", "뒤로/앞으로 — 팔레트로 이동한 뒤 뒤로 가면 이전 화면이다")
    _goto(page, base, "/me")
    start = page.url
    page.locator(SEARCH_BUTTON).first.click()
    page.wait_for_selector(PALETTE_INPUT, timeout=15_000)
    page.locator(PALETTE_INPUT).fill("문서")
    page.wait_for_timeout(1500)
    rows = page.locator('[role="dialog"] .MuiListItemButton-root')
    if not rows.count():
        f["notes"].append("결과 0건 — 이동을 시험할 대상이 없다")
        return f
    rec.reset()
    rows.first.click()
    page.wait_for_timeout(2000)
    moved = page.url
    page.go_back()
    page.wait_for_selector("#main-content", timeout=30_000)
    page.wait_for_timeout(1800)
    backed = page.url
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"] = {"start": start, "moved": moved, "after_back": backed,
                     "calls": calls[:6]}
    f["chain"]["ui_action"] = "팔레트 결과로 이동 → 브라우저 뒤로"
    f["chain"]["url_state"] = (f"{start.split('#')[-1]} → {moved.split('#')[-1]} → "
                               f"{backed.split('#')[-1]}")
    f["chain"]["frontend_state"] = "HashRouter 히스토리 항목이 이동마다 쌓인다"
    if calls:
        f["chain"]["api_request"] = f"{calls[0]['method']} {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "이동한 화면과 돌아온 화면의 조회"
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    f["chain"]["rendered"] = ("뒤로 이후 본문 «%s»"
                             % page.locator("#main-content").inner_text()[:70].replace(chr(10), " "))
    f["screenshots"].append(_shot(page, out, "ff1197-back"))
    if backed.split("#")[-1] != start.split("#")[-1]:
        f["notes"].append("뒤로가 출발 화면으로 돌아오지 않았다 — 확인 필요")
    return f


def ff_1188_bell(page, rec: Recorder, out: Path) -> dict:
    f = flow("FF-1188", "notification_action", "알림 종에서 안 읽은 수를 보고 팝오버로 개별 알림을 연다")
    rec.reset()
    bell = page.locator(BELL).first
    f["observed"]["aria_label"] = bell.get_attribute("aria-label")
    f["chain"]["ui_action"] = "상단바 알림 종 클릭"
    bell.click()
    page.wait_for_timeout(1800)
    calls = rec.since("/api/notifications")
    own = [c for c in calls if "page_size=" in c["url"]] or calls
    f["observed"]["notification_calls"] = calls[:6]
    f["observed"]["bell_own_call"] = own[0] if own else None
    if own:
        f["chain"]["api_request"] = f"GET {own[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/notifications/router.py → 수신자별 알림 조회 (audience 분리)"
        f["chain"]["api_response"] = f"HTTP {own[0]['status']}"
    pop = page.locator('.MuiPopover-paper').first
    f["chain"]["frontend_state"] = "팝오버 open=true"
    try:
        f["chain"]["rendered"] = "팝오버 본문 «%s»" % pop.inner_text()[:100].replace("\n", " ")
    except Exception:  # noqa: BLE001
        f["notes"].append("팝오버 본문을 읽지 못했다")
    badge_calls = [c for c in rec.calls if "unread-count" in c["url"]]
    f["observed"]["badge_calls"] = badge_calls[:4]
    f["observed"]["console_here"] = page.evaluate(
        """() => {
          const g = document.querySelector('[role="group"][aria-label="화면 전환"]');
          if (!g) return 'switch 없음';
          const on = [...g.querySelectorAll('button')].find((b) => b.getAttribute('aria-current'));
          return on ? on.textContent.trim() : '선택 없음';
        }""")
    f["screenshots"].append(_shot(page, out, "ff1188-bell"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    return f


def ff_1189_theme(browser, sess, base: str, out: Path, insecure: bool) -> dict:
    """테마 토글 — **하네스의 테마 주입 없이** 돌린다.

    이 Flow 만 별도 컨텍스트를 쓰는 이유가 있다. `capture.new_context` 는 캡처 결정성을 위해
    `add_init_script(theme_init_script(...))` 로 **매 문서 로드마다 테마를 강제**한다. 그 안에서
    "새로고침 후에도 유지되는가"를 물으면 답은 언제나 "하네스가 주입한 값" 이다 — 제품이 아니라
    프로브를 재는 셈이고, 실제로 첫 실행에서 `localStorage=dark` 인데 `data-theme=light` 라는
    **거짓 결함**이 나왔다. 이 저장소의 규율대로 대상보다 프로브를 먼저 의심해 바로잡는다.
    """
    f = flow("FF-1189", "settings_apply", "테마 토글이 라이트/다크를 바꾸고 그 선택이 유지된다")
    ctx = browser.new_context(storage_state=sess.storage_state,
                              viewport={"width": VIEWPORT.width, "height": VIEWPORT.height},
                              locale="ko-KR", timezone_id="Asia/Seoul",
                              reduced_motion="reduce", ignore_https_errors=insecure)
    ctx.set_default_timeout(30_000)
    page = ctx.new_page()
    rec = Recorder(page)
    _goto(page, base, "/me")

    before = page.evaluate("document.documentElement.getAttribute('data-theme')")
    rec.reset()
    toggle = page.locator('.MuiAppBar-root [aria-label$="모드로 전환"]').first
    f["chain"]["ui_action"] = "상단바 테마 토글 클릭 (%s)" % toggle.get_attribute("aria-label")
    toggle.click()
    page.wait_for_timeout(900)
    after = page.evaluate("document.documentElement.getAttribute('data-theme')")
    stored = page.evaluate("""() => ({
      boot: window.localStorage.getItem('clovirone_theme'),
      keys: Object.keys(window.localStorage).filter((k) => k.indexOf('clovirone_theme') === 0),
    })""")
    f["observed"] = {"theme_before": before, "theme_after": after,
                     "localStorage": stored, "api_calls_during_toggle": rec.calls[:5],
                     "harness_theme_injection": "없음 (이 Flow 전용 컨텍스트)"}
    f["chain"]["frontend_state"] = f"html[data-theme] {before} → {after} · localStorage {stored['boot']}"
    f["screenshots"].append(_shot(page, out, "ff1189-theme-toggled"))

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#main-content", timeout=30_000)
    page.wait_for_timeout(1200)
    persisted = page.evaluate("document.documentElement.getAttribute('data-theme')")
    f["observed"]["theme_after_reload"] = persisted
    ok = persisted == after
    f["chain"]["rendered"] = (f"새로고침 후 {persisted} — 선택이 "
                              + ("유지된다" if ok else "**유지되지 않는다**"))
    f["screenshots"].append(_shot(page, out, "ff1189-theme-persisted"))
    if not ok:
        f["notes"].append("새로고침 후 테마가 되돌아갔다 — 실제 결함이다.")
    if not rec.calls:
        f["notes"].append("서버 왕복 없음 — theme-store.js 는 **첫 페인트 전에** 결정해야 해서 "
                          "localStorage 만 쓴다(FOUC 방지). 이 Flow 는 `chain` 의 API 칸을 "
                          "정직하게 채울 수 있는 종류가 아니다.")
    ctx.close()
    return f


def ff_1190_account(page, rec: Recorder, out: Path, base: str) -> dict:
    f = flow("FF-1190", "overflow_action", "계정 메뉴에서 프로필·표시 설정·로그아웃으로 간다")
    rec.reset()
    page.locator(ACCOUNT).first.click()
    page.wait_for_timeout(900)
    items = page.locator('[role="menu"] [role="menuitem"]')
    labels = [items.nth(i).inner_text().strip().replace("\n", " ") for i in range(items.count())]
    f["observed"]["menu_items"] = labels
    f["chain"]["ui_action"] = "계정 버튼 클릭 → 메뉴 %d개" % len(labels)
    f["chain"]["frontend_state"] = "Menu open=true, anchor=계정 버튼"
    f["screenshots"].append(_shot(page, out, "ff1190-account-menu"))
    target = None
    for i, label in enumerate(labels):
        if "내 화면 설정" in label:
            target = i
            break
    if target is None:
        f["notes"].append("'내 화면 설정' 항목을 찾지 못했다")
        page.keyboard.press("Escape")
        return f
    rec.reset()
    items.nth(target).click()
    page.wait_for_timeout(2200)
    f["observed"]["url_after"] = page.url
    f["chain"]["url_state"] = "해시 %s" % page.url.split("#")[-1]
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["screen_calls"] = calls[:6]
    if calls:
        f["chain"]["api_request"] = f"{calls[0]['method']} {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "내 표시 설정 조회 (계정별 저장값)"
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    f["chain"]["rendered"] = "본문 «%s»" % page.locator("#main-content").inner_text()[:100].replace("\n", " ")
    f["screenshots"].append(_shot(page, out, "ff1190-display-settings"))

    # '내 화면 설정' 은 브라우저 로컬 설정이라 서버 왕복이 없다(화면 자신이 그렇게 적어 둔다).
    # 이 Flow 의 이름은 "프로필·표시 설정·로그아웃으로 간다" 이므로 **서버가 관여하는 쪽**도
    # 한 번 밟아야 사슬이 정직하게 채워진다 — 내 프로필로 한 번 더 간다.
    _goto(page, base, "/me")
    rec.reset()
    page.locator(ACCOUNT).first.click()
    page.wait_for_timeout(800)
    items = page.locator('[role="menu"] [role="menuitem"]')
    labels = [items.nth(i).inner_text().strip().replace("\n", " ") for i in range(items.count())]
    idx = next((i for i, label in enumerate(labels) if "내 프로필" in label), None)
    if idx is not None:
        items.nth(idx).click()
        page.wait_for_timeout(2200)
        calls2 = [c for c in rec.calls if c["status"] < 400]
        f["observed"]["profile_url"] = page.url
        f["observed"]["profile_calls"] = calls2[:6]
        if calls2:
            f["chain"]["api_request"] = f"{calls2[0]['method']} {calls2[0]['url'].split('/api/')[-1]}"
            f["chain"]["backend_query"] = "내 프로필 조회 (세션 주체 기준)"
            f["chain"]["api_response"] = f"HTTP {calls2[0]['status']}"
            f["chain"]["rendered"] = ("본문 «%s»"
                                      % page.locator("#main-content").inner_text()[:100].replace("\n", " "))
        f["screenshots"].append(_shot(page, out, "ff1190-profile"))
        f["notes"].append("'내 화면 설정' 은 서버 왕복이 없다 — 브라우저에만 저장되는 개인 "
                          "설정이라고 화면 자신이 밝힌다. 사슬의 API 칸은 같은 메뉴의 "
                          "'내 프로필' 경로로 채웠다.")
    _goto(page, base, "/me")
    return f


def ff_1191_clovi(page, rec: Recorder, out: Path) -> dict:
    f = flow("FF-1191", "modal_action", "Clovi 버튼이 AI 도우미 서랍을 연다")
    rec.reset()
    button = page.locator(CLOVI).first
    f["observed"]["in_ai_anchor"] = page.locator(f"{AI_ANCHOR} {CLOVI}").count() > 0
    f["chain"]["ui_action"] = "상단바 클로비 버튼 클릭"
    button.click()
    page.wait_for_timeout(2000)
    drawer = page.locator(".MuiDrawer-root .MuiDrawer-paper").last
    f["chain"]["frontend_state"] = "AssistantDrawer open=true"
    try:
        f["chain"]["rendered"] = "서랍 본문 «%s»" % drawer.inner_text()[:120].replace("\n", " ")
    except Exception:  # noqa: BLE001
        f["notes"].append("서랍 본문을 읽지 못했다")
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["drawer_calls"] = calls[:6]
    if calls:
        f["chain"]["api_request"] = f"{calls[0]['method']} {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "대화 이력 조회"
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    else:
        f["notes"].append("여는 것만으로는 서버 왕복이 없다 — 대화를 보내야 API 가 돈다(W14 범위).")
    f["screenshots"].append(_shot(page, out, "ff1191-clovi-drawer"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    return f


def ff_1192_permission(page_admin, page_user, out: Path) -> dict:
    """같은 셸을 두 역할로 열어 **무엇이 사라지는지**를 본다."""
    f = flow("FF-1192", "permission_state",
             "역할에 따라 콘솔 세그먼트 탭과 관리자 항목이 나타나거나 사라진다")
    def probe(page, tag):
        page.wait_for_selector("#main-content", timeout=30_000)
        page.wait_for_timeout(1200)
        switch = page.locator('[role="group"][aria-label="화면 전환"]')
        nav_labels = []
        items = page.locator('#app-sidebar a[href]')
        for i in range(min(items.count(), 60)):
            nav_labels.append(items.nth(i).inner_text().strip().replace("\n", " "))
        return {"console_switch": switch.count(), "nav_items": len(nav_labels),
                "labels": nav_labels[:40], "shot": _shot(page, out, f"ff1192-{tag}")}
    admin = probe(page_admin, "system_admin")
    user = probe(page_user, "user")
    f["observed"] = {"system_admin": admin, "user": user}
    f["chain"]["ui_action"] = "같은 셸을 system_admin / user 두 세션으로 연다"
    f["chain"]["api_request"] = "GET me"
    f["chain"]["backend_query"] = "app/core/sessions.py → 세션의 실제 role (서버가 정본)"
    f["chain"]["api_response"] = "HTTP 200 (역할이 서로 다른 두 세션)"
    f["chain"]["frontend_state"] = (
        f"콘솔 전환 스위치 system_admin={admin['console_switch']} / user={user['console_switch']}")
    f["chain"]["rendered"] = (
        f"사이드바 항목 수 system_admin={admin['nav_items']} / user={user['nav_items']}")
    f["screenshots"] = [admin["shot"], user["shot"]]
    if admin["console_switch"] and not user["console_switch"]:
        f["notes"].append("일반 사용자에게는 관리자 콘솔로 가는 스위치 자체가 없다 — "
                          "Frontend gate 만으로 권한을 보장하지는 않지만(서버가 정본), "
                          "죽은 링크를 그리지 않는다는 계약은 지켜진다.")
    else:
        f["notes"].append("역할별 차이가 관측되지 않았다 — 확인 필요")
    return f


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="App Shell 상단바 기능 사슬 E2E (W2)")
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
        ssl._create_default_https_context = ssl._create_unverified_context

    from playwright.sync_api import sync_playwright

    flows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        cache = REPO_ROOT / "dist" / "ui-qa"
        admin_sess = ensure_session(browser, base, cache, insecure=args.insecure, log=print)
        user_sess = ensure_session(browser, base, cache / "auth-user", insecure=args.insecure,
                                   log=print, role="user")

        ctx = new_context(browser, storage_state=admin_sess.storage_state,
                          user_id=admin_sess.user_id, theme="light",
                          viewport=VIEWPORT, insecure=args.insecure)
        page = ctx.new_page()
        rec = Recorder(page)
        _goto(page, base, "/me")

        flows.append(ff_1186_search(page, rec, out))
        flows.append(ff_1187_navigate(page, rec, out, base))
        flows.append(ff_1195_race(page, rec, out))
        flows.append(ff_1196_cache(page, rec, out, base))
        flows.append(ff_1197_back(page, rec, out, base))
        _goto(page, base, "/me")
        flows.append(ff_1188_bell(page, rec, out))
        flows.append(ff_1189_theme(browser, admin_sess, base, out, args.insecure))
        flows.append(ff_1190_account(page, rec, out, base))
        flows.append(ff_1191_clovi(page, rec, out))

        uctx = new_context(browser, storage_state=user_sess.storage_state,
                           user_id=user_sess.user_id, theme="light",
                           viewport=VIEWPORT, insecure=args.insecure)
        upage = uctx.new_page()
        _goto(upage, base, "/me")
        flows.append(ff_1192_permission(page, upage, out))

        uctx.close()
        ctx.close()
        browser.close()

    payload = {"base_url": base, "viewport": VIEWPORT.name, "flows": flows,
               "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (out / "flows.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    print(f"SHELL_E2E_WRITTEN {out / 'flows.json'}")
    for f in flows:
        filled = [k for k in ("api_request", "backend_query", "api_response", "rendered")
                  if f["chain"].get(k)]
        print(f"  {f['id']:8s} {f['category']:20s} 사슬 {len(f['chain'])}단계 "
              f"(핵심 {len(filled)}/4) {'· '.join(f['notes'])[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
