"""Pilot 8 Archetype 의 기능 사슬을 **실제 브라우저에서** 끝까지 돌린다 (W8 · S18).

## 왜 하네스를 하나 더 만드는가

`FUNCTIONAL_COVERAGE.json` 의 W8 소유 Surface 열일곱에는 Flow 가 235개 있고 **전부
`NOT_AUDITED`** 였다. W0 이 목록만 만들었고 그 뒤로 아무도 누른 적이 없다. W8 의 종료
조건이 「Pilot 화면의 Functional Flow 가 PASS」인 이유가 그것이다 — 디자인만 통과한
Pilot 은 Pilot 이 아니다.

`shell_e2e`·`nav_e2e`·`kit_e2e` 는 Flow 하나마다 함수 하나를 손으로 썼다. Flow 열 개까지는
그것이 가장 정직한 방법이지만 235개에서는 **하네스 자체가 읽을 수 없는 물건**이 된다.
그래서 여기서는 뒤집는다: Flow 는 **표**로 적고, 엔진 하나가 그것을 실행한다.

## 무엇을 증거로 삼는가

화면이 바뀌었다는 사실은 정상 동작의 증거가 아니다(CLAUDE.md §5). 각 Flow 마다
네트워크를 함께 기록하고 사슬을 **실측값으로** 채운다:

    ui_action → frontend_state → url_state → api_request → backend_query
              → api_response → rendered

`backend_query` 는 **손으로 적지 않는다.** 관측한 `METHOD /경로` 를 서버가 스스로 밝힌
라우트 표(`/openapi.json` 의 `operationId`)에 물어 어느 핸들러가 돌았는지 찾는다.
손으로 적은 문자열은 코드가 옮겨 가는 날 조용히 거짓이 되고, 그것을 알아채는 검사가 없다.

## 관측한 것만 적는다

서버가 관여하지 않는 Flow 가 있다(모달 열기, 탭 전환, 클라이언트 검증). 그런 Flow 에
`api_request` 를 지어내면 사슬 전체가 창작이 된다. 엔진은 **관측한 칸만** 채우고, 표가
`server=False` 로 선언한 Flow 는 사슬의 서버 칸을 요구하지 않는다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness pilot_e2e
    python -m scripts.ui_qa.local_capture --harness pilot_e2e -- --surfaces user_me
    python -m scripts.ui_qa.local_capture --harness pilot_e2e -- --inventory

`--inventory` 는 각 화면의 **접근 가능한 이름 목록**(제목·버튼·링크·입력·표)을 덤프한다.
Flow 표를 쓸 때 선택자를 소스에서 짐작하지 않기 위한 것이고, 화면이 자기 컨트롤에 이름을
안 준 자리를 함께 드러낸다.

산출물: `dist/ui-qa/w8-pilot-e2e/flows.json` + 단계별 스크린샷.
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
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402
from scripts.ui_qa.pilot_flows import FLOWS, Flow  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "w8-pilot-e2e"
VIEWPORT = Viewport("1920x1080", 1920, 1080)


# --------------------------------------------------------------------------- #
# 서버가 스스로 밝히는 라우트 표
# --------------------------------------------------------------------------- #
class Backend:
    """`METHOD /경로` → 어느 핸들러가 돌았는가.

    OpenAPI 의 `operationId` 는 FastAPI 가 **핸들러 함수 이름**에서 만든다. 그래서 이
    표는 코드가 옮겨 가면 함께 옮겨 간다 — 하네스에 손으로 적은 문자열과 달리 늙지 않는다.
    """

    def __init__(self, spec: dict) -> None:
        self.exact: dict[tuple[str, str], str] = {}
        self.templates: list[tuple[str, list[str], str]] = []
        for path, ops in (spec.get("paths") or {}).items():
            for method, op in ops.items():
                if method.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                    continue
                name = op.get("operationId") or op.get("summary") or ""
                # FastAPI 의 operationId 는 `이름_경로_method` 꼴이라 뒤쪽이 소음이다.
                name = name.split("_api_")[0]
                key = (method.upper(), path)
                self.exact[key] = name
                if "{" in path:
                    self.templates.append((method.upper(), path.split("/"), name))

    def resolve(self, method: str, path: str) -> str:
        method = method.upper()
        hit = self.exact.get((method, path))
        if hit:
            return "%s (%s %s)" % (hit, method, path)
        parts = path.split("/")
        for tmethod, tparts, name in self.templates:
            if tmethod != method or len(tparts) != len(parts):
                continue
            if all(t.startswith("{") or t == p for t, p in zip(tparts, parts)):
                return "%s (%s %s)" % (name, method, "/".join(tparts))
        return ""


# --------------------------------------------------------------------------- #
# 이 단계 동안 오간 요청
# --------------------------------------------------------------------------- #
class Recorder:
    def __init__(self, page) -> None:
        self.calls: list[dict] = []
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        url = response.url
        if "/api/" not in url:
            return
        path = "/api/" + url.split("/api/", 1)[1]
        query = ""
        if "?" in path:
            path, query = path.split("?", 1)
        body = None
        try:
            if response.request.method in ("GET",) and "json" in (
                    response.headers.get("content-type") or ""):
                body = response.json()
        except Exception:  # noqa: BLE001 — 본문을 못 읽는 것이 판정을 바꾸지는 않는다
            body = None
        self.calls.append({
            "method": response.request.method, "path": path, "query": query,
            "status": response.status, "at": time.time(), "body": body,
        })

    def reset(self) -> None:
        self.calls = []

    def matching(self, fragment: str) -> list[dict]:
        return [c for c in self.calls if fragment in c["path"] or fragment in c["query"]]


def _shape(body) -> dict:
    """응답을 «몇 건인가» 로 줄인다 — 원문을 통째로 싣지 않는다(비밀·용량)."""
    if isinstance(body, dict):
        for key in ("items", "rows", "data", "results"):
            if isinstance(body.get(key), list):
                out = {"count": len(body[key])}
                for extra in ("total", "page", "page_size", "has_more"):
                    if extra in body:
                        out[extra] = body[extra]
                return out
        return {"keys": sorted(body.keys())[:12]}
    if isinstance(body, list):
        return {"count": len(body)}
    return {}


# --------------------------------------------------------------------------- #
# 액션 — Flow 표가 쓰는 어휘
# --------------------------------------------------------------------------- #
class Stop(Exception):
    """이 Flow 를 여기서 멈춘다 — 판정은 `--out` JSON 을 읽는 사람이 한다."""


def _resolve(page, selector: str):
    """`role=…` · `text=…` · CSS 를 한 어휘로 받는다."""
    if selector.startswith("label="):
        return page.get_by_label(selector[6:], exact=False)
    if selector.startswith("text="):
        return page.get_by_text(selector[5:], exact=False)
    if selector.startswith("button="):
        return page.get_by_role("button", name=selector[7:], exact=False)
    if selector.startswith("link="):
        return page.get_by_role("link", name=selector[5:], exact=False)
    if selector.startswith("tab="):
        return page.get_by_role("tab", name=selector[4:], exact=False)
    return page.locator(selector)


class Runner:
    def __init__(self, page, rec: Recorder, backend: Backend, base: str, out: Path,
                 *, browser=None, insecure: bool = False) -> None:
        self.page = page
        self.rec = rec
        self.backend = backend
        self.base = base
        self.out = out
        self._browser = browser
        self._insecure = insecure
        self._role_pages: dict[str, object] = {}
        # 역할별 «어디에 떨어졌는가» — 본문이 안 그려지면 그 사실이 곧 관측이다.
        self.role_landing: dict[str, dict] = {}

    # ── 다른 역할의 눈 ──────────────────────────────────────────────────────
    def as_role(self, role: str, hash_path: str, shell: str, fn):
        """그 역할로 **실제로 로그인해** 같은 화면을 열고 `fn(page)` 를 잰다.

        화면이 준 플래그를 가로채 «없는 척» 만들지 않는다 — 그렇게 재면 「서버가 무엇을
        보내는가」는 확인되지 않고, 권한 질문의 절반이 그쪽이다. 역할마다 컨텍스트를
        하나씩 만들어 두고 재사용한다(로그인은 역할당 한 번이다).
        """
        if self._browser is None:
            raise Stop("역할 전환에는 브라우저가 필요하다 — Runner 에 안 넘겨졌다")
        page = self._role_pages.get(role)
        if page is None:
            # 세션 자리를 바꿀 수 있게 둔다 — 같은 표를 여러 프로세스가 나눠 돌릴 때
            # (S21 의 bounded batch) 네 실행이 같은 `storage_state.json` 을 서로 덮으면
            # 한쪽이 남의 역할로 로그인한 채로 잰다.
            base = getattr(self, "session_dir", None) or (REPO_ROOT / "dist" / "ui-qa")
            out_dir = base / ("role-" + role)
            session = ensure_session(self._browser, self.base, out_dir,
                                     insecure=self._insecure, role=role)
            context = new_context(self._browser, storage_state=session.storage_state,
                                  user_id=session.user_id, theme="light",
                                  viewport=VIEWPORT, insecure=self._insecure)
            page = context.new_page()
            self._role_pages[role] = page
        page.goto(self.base + shell + "#" + hash_path, wait_until="domcontentloaded")
        # **못 들어가는 것도 답이다.** 관리자 콘솔을 일반 사용자로 열면 본문이 아예 안
        # 그려진다 — 그것이 「버튼을 숨긴다」보다 강한 형태의 차단이다. 예전에는 여기서
        # 30초를 기다리다 죽었고, 그 죽음이 「측정 실패」로 기록돼 제품의 정답이 결함처럼
        # 보였다. 기다리되, 안 오면 **무엇이 왔는지 적고** 그대로 재게 한다.
        landed = True
        try:
            page.wait_for_selector("#main-content", timeout=12_000)
        except Exception:  # noqa: BLE001
            landed = False
        page.wait_for_timeout(1400)
        body = ""
        try:
            body = " ".join((page.evaluate("() => document.body.innerText || ''")
                             or "").split())[:200]
        except Exception:  # noqa: BLE001
            pass
        self.role_landing[role] = {"main_content": landed, "body": body}
        return fn(page)

    def dismiss_overlays(self) -> None:
        """열려 있는 대화상자·메뉴를 Esc 로 닫는다. 최대 세 번만 — 안 닫히면 그대로 둔다."""
        for _ in range(3):
            if not self.page.locator('[role="dialog"] .MuiDialogTitle-root').count() \
                    and not self.page.locator('[role="menu"]').count():
                return
            try:
                self.page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                return
            self.page.wait_for_timeout(350)
            # dirty 확인 창이 뜨면 «버리기» 로 답한다.
            for label in ("버리고 닫기", "닫기", "예", "취소"):
                button = self.page.locator('[role="dialog"]').last.get_by_role(
                    "button", name=label, exact=True)
                if button.count():
                    try:
                        button.first.click(timeout=3000)
                    except Exception:  # noqa: BLE001
                        pass
                    self.page.wait_for_timeout(350)
                    break

    def in_main(self, kind: str, name: str):
        """**본문 안에서만** 그 역할·이름을 찾는다.

        셸에는 같은 낱말을 쓰는 컨트롤이 많다 — 사이드바의 «내 업무» 묶음 머리, 상단바의
        계정 버튼(«UI QA»). 페이지 전체에서 찾으면 그것들이 먼저 잡히고, 눌러도 화면이
        안 바뀌므로 Flow 는 「눌렀는데 아무 일도 없다」로 죽는다.
        """
        return self.page.locator("#main-content").get_by_role(kind, name=name, exact=False)

    def count_control(self, kind: str, name: str) -> int:
        return self.page.get_by_role(kind, name=name, exact=False).count()

    def api_get(self, path: str):
        """세션을 그대로 써서 API 를 한 번 읽는다 — **Flow 가 쓸 실제 id 를 얻는 자리**다.

        딥링크 Flow 는 `?department_id=<진짜 id>` 같은 값이 필요하다. 그 값을 표에서
        긁으면 화면이 id 를 안 그리는 순간 Flow 가 깨지고, 손으로 박으면 씨앗이 바뀌는
        순간 거짓이 된다. 서버에 물어보는 것이 가장 안 늙는다.
        """
        response = self.page.context.request.get(self.base + path, timeout=20_000)
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            return {}

    def close_role_pages(self) -> None:
        for page in self._role_pages.values():
            try:
                page.context.close()
            except Exception:  # noqa: BLE001
                pass
        self._role_pages = {}

    # ── 이동 ────────────────────────────────────────────────────────────────
    def goto(self, hash_path: str, *, shell: str = "/") -> None:
        """그 화면을 **처음 여는 것처럼** 연다.

        해시만 다른 주소로 `goto` 하면 브라우저는 문서를 다시 안 읽는다 — SPA 라 그게
        맞는 동작이지만, Flow 표에서는 그 때문에 **앞 Flow 가 남긴 캐시가 다음 Flow 로
        샌다.** 실제로 그렇게 새어 나갔다: 응답을 비워 «티켓 0건» 얼굴을 만든 Flow 가
        끝난 뒤, 다음 Flow 가 같은 해시로 이동하자 react-query 가 그 빈 응답을 그대로
        재사용해 표에 행이 하나도 없었고, 다음 여덟 Flow 가 «누를 것이 없다» 로 죽었다.
        Flow 는 서로 독립이어야 하므로 같은 문서로 갈 때는 한 번 더 읽는다.
        """
        target = self.base + shell + "#" + hash_path
        same_document = self.page.url.split("#", 1)[0] == target.split("#", 1)[0]
        self.page.goto(target, wait_until="domcontentloaded")
        if same_document:
            self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_selector("#main-content", timeout=30_000)
        self.settle()

    def settle(self, ms: int = 900) -> None:
        self.page.wait_for_timeout(ms)

    # ── 조작 ────────────────────────────────────────────────────────────────
    def click(self, selector: str, *, index: int = 0) -> str:
        loc = _resolve(self.page, selector).nth(index)
        if not loc.count():
            raise Stop("누를 것이 없다: %s" % selector)
        label = " ".join((loc.inner_text() or "").split())[:60] or selector
        loc.scroll_into_view_if_needed()
        loc.click()
        self.settle()
        return label

    def fill(self, selector: str, value: str, *, index: int = 0) -> str:
        loc = _resolve(self.page, selector).nth(index)
        if not loc.count():
            raise Stop("입력할 곳이 없다: %s" % selector)
        loc.fill(value)
        self.settle(1300)   # 디바운스보다 길게
        return value

    def choose(self, combo: str, option: str, *, index: int = 0) -> str:
        """MUI Select — 닫힌 상자를 열고 옵션을 고른다.

        `<select>` 가 아니라 팝오버라 `select_option` 이 안 통한다. 옵션이 없으면
        멈춘다 — 「고를 것이 없다」를 「골랐다」로 적지 않는다.
        """
        box = self.page.get_by_role("combobox", name=combo, exact=False).nth(index)
        if not box.count():
            raise Stop("선택 상자가 없다: %s — 지금 화면의 선택 상자: %s"
                       % (combo, self.combobox_names()))
        box.click()
        self.settle(400)
        item = self.page.get_by_role("option", name=option, exact=False)
        if not item.count():
            self.press("Escape")
            raise Stop("«%s» 에 «%s» 선택지가 없다" % (combo, option))
        label = " ".join((item.first.inner_text() or "").split())[:40]
        had = self.page.get_by_role("combobox").count()
        item.first.click()
        self.settle(500)
        self.close_listbox()
        self.wait_controls(had)
        return label

    def close_listbox(self) -> bool:
        """**여러 개를 담는 선택 상자는 고른 뒤에도 열린 채로 있다** — 그것이 그 컨트롤의 계약이다.

        그런데 그 동안 MUI 는 나머지 화면 전체를 `aria-hidden` 으로 덮는다. 닫지 않으면 그
        뒤의 모든 역할 질의가 «아무것도 없다» 를 본다 — 실제로 그렇게 `/sprint` 의 두 Flow 가
        「선택 상자가 없다」로 죽었고, DOM 에는 여섯 개가 멀쩡히 있었다.
        """
        if not self.page.locator('[role="listbox"]').count():
            return False
        self.press("Escape")
        self.settle(500)
        return True

    def wait_controls(self, at_least: int, timeout_ms: int = 8000) -> int:
        """조건을 바꾼 뒤 **필터 줄이 돌아올 때까지** 기다린다.

        조건 하나를 바꾸면 그 화면이 다시 불러오고, 그 동안 스켈레톤이 필터 줄까지 통째로
        갈아 끼우는 화면이 있다(스프린트). 그 순간에 다음 조건을 찾으면 「선택 상자가 없다」가
        되는데, 그건 화면이 아니라 **표가 이른 것**이다 — 실제로 그렇게 두 Flow 가 죽었다.
        """
        if at_least <= 0:
            return 0
        waited, step = 0, 300
        while waited < timeout_ms:
            got = self.page.get_by_role("combobox").count()
            if got >= at_least:
                return got
            self.page.wait_for_timeout(step)
            waited += step
        return self.page.get_by_role("combobox").count()

    def combobox_names(self) -> list:
        """지금 화면에 있는 선택 상자의 이름들 — 「없다」가 무엇을 뜻하는지 함께 적는다.

        접근성 트리로 0개인데 DOM 에는 있는 경우가 있다: 열린 모달이 나머지를
        `aria-hidden` 으로 덮으면 역할 질의는 아무것도 못 본다. 둘을 함께 적는다.
        """
        boxes = self.page.get_by_role("combobox")
        out = []
        for i in range(min(boxes.count(), 14)):
            name = boxes.nth(i).get_attribute("aria-label") or ""
            if not name:
                name = " ".join((boxes.nth(i).inner_text() or "").split())[:24]
            out.append(name or "(이름 없음)")
        if not out:
            raw = self.page.evaluate(
                "() => ({dom: document.querySelectorAll('[role=combobox]').length,"
                " hidden: Array.from(document.querySelectorAll('[aria-hidden=\"true\"]'))"
                ".map(el => el.tagName + '.' + (el.className || '').toString().slice(0, 40))"
                ".slice(0, 6), dialogs: document.querySelectorAll('[role=dialog]').length,"
                " presentation: document.querySelectorAll('.MuiModal-root').length})")
            out.append("(역할 0개 · DOM %s)" % raw)
        return out

    def choose_other(self, combo: str, *, index: int = 0) -> tuple[str, str]:
        """지금 값과 **다른** 선택지를 고른다. `(이전, 고른 것)` 을 돌려준다.

        값을 고정해 두면 그 값이 이미 들어 있는 행에서 「바뀐 것이 없다」가 되고, 화면은
        옳게 «수정한 내용이 없습니다» 라고 말한다 — 그런데 Flow 는 그것을 「저장이 안
        된다」로 적는다. 실제로 그렇게 두 Flow 가 거짓 실패를 냈다. 바꾸는 것이 목적인
        Flow 는 **지금과 다른 값**을 골라야 한다.
        """
        box = self.page.get_by_role("combobox", name=combo, exact=False).nth(index)
        if not box.count():
            raise Stop("선택 상자가 없다: %s" % combo)
        current = " ".join((box.inner_text() or "").split())
        box.click()
        self.settle(400)
        options = self.page.get_by_role("option")
        for i in range(options.count()):
            label = " ".join((options.nth(i).inner_text() or "").split())
            if label and label != current and label not in ("없음", "-"):
                had = self.page.get_by_role("combobox").count()
                options.nth(i).click()
                self.settle(500)
                self.close_listbox()
                self.wait_controls(had)
                return current, label
        self.press("Escape")
        raise Stop("«%s» 에 지금 값(%s)과 다른 선택지가 없다" % (combo, current))

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)
        self.settle(500)

    def back(self) -> None:
        self.page.go_back()
        self.settle()

    def forward(self) -> None:
        self.page.go_forward()
        self.settle()

    # ── 측정 ────────────────────────────────────────────────────────────────
    def rows(self) -> int:
        return self.page.locator("table tbody tr").count()

    def hash_of(self) -> str:
        return self.page.url.split("#", 1)[-1] if "#" in self.page.url else self.page.url

    def main_text(self, limit: int = 160) -> str:
        try:
            text = self.page.locator("#main-content").inner_text()
        except Exception:  # noqa: BLE001
            text = ""
        return " ".join(text.split())[:limit]

    def shot(self, name: str) -> str:
        """화면 하나를 찍고 **기록에 적을 경로**를 돌려준다.

        저장소 안이면 상대경로로 적는다(증거 토큰이 머신마다 달라지면 안 된다). 밖이면
        절대경로 그대로다 — 예전에는 여기서 `relative_to` 가 그냥 죽었고, 그 죽음이
        「모달이 안 열렸다」로 기록됐다. 찍는 자리가 판정을 뒤집으면 안 된다.
        """
        self.out.mkdir(parents=True, exist_ok=True)
        path = (self.out / (name + ".png")).resolve()
        self.page.screenshot(path=str(path), full_page=False)
        try:
            return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")


# --------------------------------------------------------------------------- #
# 한 Flow 실행
# --------------------------------------------------------------------------- #
def run_flow(flow: Flow, runner: Runner, ctx: dict) -> dict:
    rec = runner.rec
    record = {
        "id": flow.id, "surface": flow.surface, "category": flow.category,
        "name": flow.name, "chain": {}, "observed": {}, "expected": {}, "notes": [],
        "screenshots": [], "status": "PASS",
    }
    hash_before = ""
    try:
        # **앞 Flow 가 열어 둔 덮개를 먼저 걷는다.** 모달이 하나 남아 있으면 그 뒤의
        # Flow 는 전부 «누를 것이 없다» 로 죽는다 — 실제로 그렇게 열 몇 개가 연달아
        # 무너졌다. Flow 는 서로 독립이어야 하므로 시작 전에 화면을 원래대로 돌린다.
        runner.dismiss_overlays()
        # **화면을 여는 것도 동작이다.** `read` 범주의 Flow 는 «열었더니 무엇이 왔는가» 가
        # 전부라, 이동 중 오간 요청을 지우면 사슬의 서버 칸이 통째로 빈다. 그래서 이동
        # 요청과 조작 요청을 따로 담아 두고, 조작이 아무것도 안 불렀을 때만 이동 쪽을 쓴다.
        rec.reset()
        route = flow.route
        # `ctx:<키>` 는 **앞 Flow 가 찾아 둔 주소**다. 상세 화면의 id 는 씨앗마다 달라
        # 표에 적을 수 없고, 그렇다고 주소를 안 적으면 그 사이에 다른 Flow 가 목록으로
        # 나가 버린 뒤에 상세를 본다고 착각한다.
        if route.startswith("ctx:"):
            route = ctx.get(route[4:], "")
        if route:
            runner.goto(route, shell=flow.shell)
        load_calls = list(rec.calls)
        hash_before = runner.hash_of()
        # **어느 화면에서 돌았는지를 언제나 적는다.** 앞 Flow 가 다른 화면으로 나가 버리면
        # 뒤 Flow 는 «누를 것이 없다» 라고만 말하고, 그 이유는 기록에 안 남는다.
        record["observed"]["at"] = hash_before
        rows_before = runner.rows()
        rec.reset()

        action = flow.act(runner, ctx) or {}
        record["observed"].update(action.get("observed") or {})
        # **무엇과 견줬는가** (C13). 「그려졌다」는 지표 화면의 통과 근거가 될 수 없다 —
        # 그 Flow 가 무엇을 기대했고 무엇을 봤는지가 남아야 다음 사람이 다시 잴 수 있다.
        if action.get("expected"):
            record["expected"] = action["expected"]
        for note in action.get("notes") or []:
            record["notes"].append(note)

        chain = record["chain"]
        chain["ui_action"] = action.get("ui_action") or flow.name
        if action.get("frontend_state"):
            chain["frontend_state"] = action["frontend_state"]
        hash_after = runner.hash_of()
        if hash_after != hash_before:
            chain["url_state"] = "%s → %s" % (hash_before, hash_after)
        elif action.get("url_state"):
            chain["url_state"] = action["url_state"]

        def _pick(source):
            out = [c for c in source if not c["path"].startswith("/api/home/unread")]
            if flow.api:
                out = [c for c in out if flow.api in c["path"] or flow.api in c["query"]]
            return out

        calls = _pick(rec.calls)
        if not calls:
            calls = _pick(load_calls)
            if calls:
                record["observed"]["calls_from"] = "화면을 여는 동안"
        record["observed"]["calls"] = [
            {"method": c["method"], "path": c["path"], "query": c["query"][:120],
             "status": c["status"]} for c in calls[:8]
        ]
        if calls:
            first = calls[0]
            last = calls[-1]
            chain["api_request"] = "%s %s%s" % (
                first["method"], first["path"],
                ("?" + first["query"]) if first["query"] else "")
            resolved = runner.backend.resolve(first["method"], first["path"])
            if resolved:
                chain["backend_query"] = resolved
            shape = _shape(last["body"])
            chain["api_response"] = "HTTP %d%s" % (
                last["status"], (" " + json.dumps(shape, ensure_ascii=False)) if shape else "")
        elif flow.server:
            record["status"] = "FAIL"
            record["notes"].append(
                "서버가 관여한다고 선언했는데 이 동작에서 `%s` 요청이 하나도 없었다"
                % (flow.api or "/api/"))

        rendered = action.get("rendered")
        if rendered is None:
            rows_after = runner.rows()
            rendered = "본문 «%s»" % runner.main_text()
            if rows_after or rows_before:
                rendered = "표 %d행 → %d행 · %s" % (rows_before, rows_after, rendered)
        chain["rendered"] = rendered

        if action.get("failed"):
            record["status"] = "FAIL"
            record["notes"].append(str(action["failed"]))
        record["screenshots"] = action.get("screenshots") or []

        if flow.cross and record["status"] == "PASS":
            record["cross_surface"] = _cross_check(runner, flow, action, record)
    except Stop as exc:
        record["status"] = "FAIL"
        record["notes"].append(str(exc))
        record["screenshots"].append(runner.shot("%s-stopped" % flow.id.lower()))
    except Exception as exc:  # noqa: BLE001
        record["status"] = "FAIL"
        record["notes"].append("%s: %s" % (type(exc).__name__, str(exc).split("\n")[0][:200]))
        try:
            record["screenshots"].append(runner.shot("%s-error" % flow.id.lower()))
        except Exception:  # noqa: BLE001
            pass
    return record


def _cross_check(runner: "Runner", flow: Flow, action: dict, record: dict) -> list:
    """**바꾼 값이 다른 화면에도 도착했는가** (C13).

    「한 화면이 200 이라고 완료가 아니다」가 이 조건의 문장이다. 그래서 쓰기 Flow 는
    끝난 뒤 다른 화면으로 가서 그 값을 **눈으로 다시 찾는다**. 찾을 화면이 애초에 하나뿐인
    값(티켓 본문·채팅방 이름 등)은 `@reload` 로 문서를 새로 읽는다 — 그건 화면 간 정합성이
    아니라 «서버에 들어갔는가» 를 보는 것이고, 기록에도 그렇게 적는다(다르게 부르지 않는다).

    `act` 가 돌려주는 `cross` 는 셋 중 하나다:
      {"row": 행을 찾을 글, "expect": 그 행에 있어야 할 값}
      {"needle": 본문에 있어야 할 글}
      {"absent": 본문에 **없어야** 할 글}
    """
    spec = action.get("cross") or {}
    hash_path, shell = (list(flow.cross) + [""])[:2]
    reload_only = hash_path == "@reload"
    where = runner.hash_of() if reload_only else hash_path
    if reload_only:
        runner.page.reload(wait_until="domcontentloaded")
        runner.page.wait_for_selector("#main-content", timeout=30_000)
        runner.settle(1600)
    else:
        runner.goto(hash_path, shell=shell or "/")

    kind = "새 문서로 다시 읽었다(서버에 들어갔는가)" if reload_only else "다른 화면에서 다시 찾았다"
    entry = {"surface": where, "check": kind}
    # 설정 화면의 값은 **입력칸 안**에 있어서 `innerText` 에는 한 글자도 안 나온다. 그것을
    # 안 보태면 「초안이 서버에 안 들어갔다」 같은 대조가 언제나 참이 되어, 통과했는데
    # 아무것도 안 본 기록이 남는다.
    values = runner.page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'#main-content input, #main-content textarea'))"
        ".map(el => el.value || '').filter(Boolean).join(' | ')") or ""
    text = (runner.main_text(4000) + " | " + values)[:8000]
    if spec.get("row"):
        # **묶음 머리글은 행이 아니다.** 티켓 표는 프로젝트로 묶여서 `tbody` 안에 값이 없는
        # 줄이 섞인다. 그 줄이 먼저 잡히면 대조는 언제나 «인프라 정비 5건» 을 보고 실패한다 —
        # 화면이 아니라 표를 잘못 센 것이다(S21 이 여섯 Flow 에서 같은 자리를 밟았다).
        row = runner.page.locator("table tbody tr:has(td)").filter(
            has_text=spec["row"]).first
        row_text = " ".join((row.inner_text() or "").split()) if row.count() else ""
        if spec.get("row_absent"):
            entry.update({"row": spec["row"], "expect": "그 행에 없어야 한다: %s" % spec["row_absent"],
                          "observed": row_text[:200],
                          "found": bool(row_text) and spec["row_absent"] not in row_text})
        else:
            entry.update({"row": spec["row"], "expect": spec.get("expect"),
                          "observed": row_text[:200],
                          "found": bool(row_text) and str(spec.get("expect", "")) in row_text})
    elif spec.get("needle"):
        entry.update({"expect": spec["needle"], "observed": text[:200],
                      "found": spec["needle"] in text})
    elif spec.get("absent"):
        entry.update({"expect": "없어야 한다: " + spec["absent"], "observed": text[:200],
                      "found": spec["absent"] not in text})
    else:
        entry.update({"observed": text[:200], "found": None,
                      "note": "이 Flow 는 대조할 값을 안 남겼다"})

    if entry.get("found") is False:
        record["status"] = "FAIL"
        record["notes"].append(
            "%s 에서 확인하지 못했다 — 찾은 것: «%s»" % (where, entry.get("observed", "")[:120]))
    return [entry]


# --------------------------------------------------------------------------- #
# 화면의 «이름 목록» 덤프
# --------------------------------------------------------------------------- #
INVENTORY_JS = """
() => {
  const name = (el) => (el.getAttribute('aria-label') || el.innerText || el.value || '')
      .replace(/\\s+/g, ' ').trim().slice(0, 60);
  const pick = (sel) => Array.from(document.querySelectorAll(sel))
      .map(name).filter(Boolean);
  return {
    headings: pick('#main-content h1, #main-content h2, #main-content h3'),
    buttons: Array.from(new Set(pick('#main-content button'))),
    links: Array.from(new Set(pick('#main-content a'))),
    inputs: Array.from(document.querySelectorAll('#main-content input, #main-content textarea'))
        .map(el => (el.getAttribute('aria-label') || el.getAttribute('placeholder')
                    || el.name || el.type || '')).filter(Boolean),
    selects: Array.from(document.querySelectorAll('#main-content [role="combobox"]'))
        .map(el => (el.getAttribute('aria-label') || el.innerText || '')
             .replace(/\\s+/g,' ').trim().slice(0,40)).filter(Boolean),
    tabs: pick('#main-content [role="tab"]'),
    tables: Array.from(document.querySelectorAll('#main-content table')).map(t => ({
      headers: Array.from(t.querySelectorAll('thead th')).map(th => th.innerText.trim()),
      rows: t.querySelectorAll('tbody tr').length,
    })),
    switches: pick('#main-content [role="switch"], #main-content input[type=checkbox]'),
    testids: Array.from(new Set(Array.from(
        document.querySelectorAll('#main-content [data-testid]'))
        .map(el => el.getAttribute('data-testid')))),
  };
}
"""


def dump_inventory(runner: Runner, routes: list[tuple[str, str, str]]) -> dict:
    out: dict = {}
    for sid, hash_path, shell in routes:
        try:
            runner.goto(hash_path, shell=shell)
            out[sid] = runner.page.evaluate(INVENTORY_JS)
            out[sid]["hash"] = runner.hash_of()
        except Exception as exc:  # noqa: BLE001
            out[sid] = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    return out


INVENTORY_ROUTES = [
    ("user_me", "/me", "/"),
    ("user_projects", "/projects", "/"),
    ("user_sprint", "/sprint", "/"),
    ("user_chat-rooms", "/chat-rooms", "/"),
    ("user_board", "/board", "/"),
    ("user_my-tickets", "/my-tickets", "/"),
    ("admin_users", "/users", "/admin"),
    ("admin_organizations", "/organizations", "/admin"),
    ("admin_jobs", "/jobs", "/admin"),
    ("admin_settings", "/settings", "/admin"),
    ("admin_settings__os", "/settings?tab=os", "/admin"),
    ("admin_settings__ai", "/settings?tab=ai", "/admin"),
]


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Pilot 8 Archetype 기능 사슬 (W8 · S18)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--surfaces", nargs="*", default=None,
                    help="이 Surface 들만 (기본: 전부)")
    ap.add_argument("--only", nargs="*", default=None, help="이 Flow id 만")
    ap.add_argument("--inventory", action="store_true",
                    help="화면의 접근 가능한 이름 목록만 덤프하고 끝낸다")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    selected = list(FLOWS)
    if args.surfaces:
        selected = [f for f in selected if f.surface in set(args.surfaces)]
    if args.only:
        selected = [f for f in selected if f.id in set(args.only)]

    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            session = ensure_session(browser, args.base_url, REPO_ROOT / "dist" / "ui-qa",
                                     insecure=args.insecure)
            context = new_context(browser, storage_state=session.storage_state,
                                  user_id=session.user_id, theme="light",
                                  viewport=VIEWPORT, insecure=args.insecure)
            page = context.new_page()
            rec = Recorder(page)
            spec = context.request.get(args.base_url.rstrip("/") + "/openapi.json",
                                       timeout=30_000).json()
            backend = Backend(spec)
            runner = Runner(page, rec, backend, args.base_url.rstrip("/"), out,
                            browser=browser, insecure=args.insecure)

            if args.inventory:
                inv = dump_inventory(runner, INVENTORY_ROUTES)
                (out / "inventory.json").write_text(
                    json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
                print(json.dumps(inv, ensure_ascii=False, indent=1))
                return 0

            ctx: dict = {"base": args.base_url.rstrip("/")}
            records = []
            for flow in selected:
                record = run_flow(flow, runner, ctx)
                records.append(record)
                mark = "OK  " if record["status"] == "PASS" else "FAIL"
                print("[%s] %-8s %-28s %s" % (mark, flow.id, flow.surface, flow.name[:64]),
                      flush=True)
            runner.close_role_pages()
            context.close()
        finally:
            browser.close()

    payload = {
        "harness": "pilot_e2e",
        "base_url": args.base_url,
        "viewport": VIEWPORT.name,
        "elapsed_s": round(time.time() - started, 1),
        "flows": records,
    }
    (out / "flows.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    bad = [r for r in records if r["status"] != "PASS"]
    print("\n%d Flow 중 %d 실패 · %.1fs" % (len(records), len(bad), payload["elapsed_s"]))
    for r in bad:
        print("  - %s %s: %s" % (r["id"], r["name"][:50], "; ".join(r["notes"])[:160]))
    print("flows.json: %s" % (out / "flows.json"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
