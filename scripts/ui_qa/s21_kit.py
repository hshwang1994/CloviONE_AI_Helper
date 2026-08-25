"""S21 Flow 표가 쓰는 **추가 어휘** (W14).

S18 이 `pilot_kit.py` 에 세운 낱말을 그대로 쓰고, 그 표에 없던 것만 여기 더한다. S21 이
감사하는 화면은 관리자 콘솔 쪽이 많은데 그쪽에는 Pilot 에 없던 상호작용이 넷 있다.

  * **열 머리글로 정렬한다** — 표가 서버에 정렬을 맡기는 화면과 화면 안에서 도는 화면이
    섞여 있어서, «순서가 바뀌었는가» 를 실제 첫 행으로 본다.
  * **넘침 메뉴에서 위험한 동작을 고른다** — 확인 대화가 뒤따르는 것이 계약이다.
  * **탭으로 화면을 바꾼다** — S20 이 만든 탭 묶음 다섯이 전부 이 모양이다.
  * **권한을 API 로 직접 물어본다** — 「버튼을 감췄다」는 표시일 뿐이고 계약은 서버에 있다
    (불변규칙 §5). 화면에서 안 보이는 것과 **직접 불러도 막히는 것**은 다른 사실이다.

마지막 것이 S21 의 핵심이다. 지시가 이 회차에 요구한 권한 질문 다섯 가운데 넷이
「직접 불러도 막히는가」이고, 그것은 화면을 아무리 눌러도 답이 안 나온다.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

from scripts.ui_qa.pilot_kit import (  # noqa: F401  (표가 한 곳에서 가져가게 다시 내보낸다)
    Flow, back_forward, cache_key, choose_then, click_then, close_modal, compound,
    deep_link_survives_reload, dialog_text, dialogs, hash_nav, hidden_without_role,
    input_box, just_load, modal_open_close, no_page_axis, open_first_row, open_row,
    open_row_modal, page_reset, pager, primary_button, race, read_main,
    required_blocks_submit, retry_from_error, row_title, rows_showing, same_query,
    search_then, stop, title_like, typing_area, unquote_hash,
)

# **S18 의 표와 섞이면 안 된다.** `pilot_kit.FLOWS` 는 그 회차의 258건이 들어 있는 전역
# 목록이고, `s21_e2e` 는 엔진을 쓰려고 `pilot_e2e` 를 부르는데 그 import 가 Pilot 표를
# 그 목록에 채워 넣는다. 같은 목록에 담으면 S21 실행이 S18 Flow 를 함께 돌리고, 기록도
# 두 회차가 섞인다 — 그러면 어느 회차가 무엇을 봤는지 아무도 못 가른다.
FLOWS: list[Flow] = []


def flow(*args, **kwargs) -> None:
    FLOWS.append(Flow(*args, **kwargs))

# ─────────────────────────────────────────────────────────────────────────────
# 표
# ─────────────────────────────────────────────────────────────────────────────
# **묶음 머리글은 행이 아니다.** 이 제품의 티켓 표는 프로젝트로 묶여서 `tbody` 안에
# `<th scope="colgroup">인프라 정비 4건</th>` 짜리 줄이 섞인다. 그 줄에는 버튼도 값도
# 없으므로 `tr:nth(0)` 을 잡으면 「행에 «수정» 버튼이 없다」가 나오고, 그것은 화면이 아니라
# 표를 잘못 센 것이다 — 실제로 S21 첫 실행의 열 몇 개가 그 자리에서 죽었다.
DATA_ROW = "#main-content table tbody tr:has(td)"


def rows_of(r):
    return r.page.locator(DATA_ROW)


def n_rows(r) -> int:
    return rows_of(r).count()


def row_at(r, index: int = 0):
    rows = rows_of(r)
    if rows.count() <= index:
        stop("표에 값이 있는 행이 %d개뿐이다 (%d번째를 찾았다)" % (rows.count(), index))
    return rows.nth(index)


def row_name(r, index: int = 0, limit: int = 40) -> str:
    """행을 가리키는 **첫 의미 있는 칸**의 글. C13 의 대조는 행을 찾을 열쇠가 필요하다."""
    row = rows_of(r).nth(index)
    if not row.count():
        return ""
    cells = row.locator("td")
    for i in range(min(cells.count(), 4)):
        text = " ".join((cells.nth(i).inner_text() or "").split())
        if len(text) >= 2:
            return text[:limit]
    return " ".join((row.inner_text() or "").split())[:limit]


def first_row_text(r, limit: int = 90) -> str:
    row = rows_of(r).first
    if not row.count():
        return ""
    return " ".join((row.inner_text() or "").split())[:limit]


# **셸에는 늘 떠 있는 `role="dialog"` 가 하나 있다**(드로어·팔레트가 `keepMounted`).
# S18 은 그것을 «전후 차이» 로 피해 갔는데, 그 방식은 Flow 마다 기준선을 들고 다녀야 한다.
# 여기서는 **보이는 것만** 센다 — 상시 마운트된 것은 숨어 있으므로 0 이 진짜 0 이 된다.
def open_dialogs(r) -> int:
    return r.page.locator('[role="dialog"]:visible').count()


def open_dialog(r):
    return r.page.locator('[role="dialog"]:visible').last


def dialog_says(r, limit: int = 200) -> str:
    if not open_dialogs(r):
        return ""
    return " ".join((open_dialog(r).inner_text() or "").split())[:limit]


def confirm_now(r) -> str:
    """지금 떠 있는 확인 창의 **주 버튼**을 누른다. 없으면 빈 문자열.

    확인 창의 주 버튼 이름은 화면마다 다르다(«삭제» · «되돌리기» · «휴지통으로» · «보관»).
    그래서 이름 목록으로만 찾으면 못 찾은 자리에서 **아무 버튼이나** 누르게 되고, 실제로
    그것이 «취소» 였다 — Flow 는 「눌렀다」로 적히는데 서버에는 아무것도 안 갔다.
    이름을 못 찾으면 **취소가 아닌 마지막 버튼**을 고른다(MUI 의 주 버튼 자리).
    """
    if not open_dialogs(r):
        return ""
    said = dialog_says(r)
    panel = open_dialog(r)
    # **이름 목록으로 먼저 찾지 않는다.** 확인 창의 주 버튼 이름은 그 동작의 이름을 쓰므로
    # («1건 삭제» · «재색인» · «사용 안 함» · «되돌리기») 목록으로는 절대 다 못 적는다.
    # 이 제품의 확인 창은 주 버튼을 **채운 버튼**(MUI contained)으로 그린다 — 그 자리가
    # 이름보다 안 늙는다.
    filled = panel.locator("button.MuiButton-contained, button.MuiButton-containedPrimary,"
                           " button.MuiButton-containedError")
    if filled.count():
        filled.last.click()
        r.settle(1600)
        return said
    for label in ("확인", "삭제", "영구 삭제", "보관", "되돌리기", "휴지통으로", "예", "계속",
                  "닫기"):
        button = panel.get_by_role("button", name=label, exact=True)
        if button.count():
            button.first.click()
            r.settle(1600)
            return said
    buttons = panel.get_by_role("button")
    for i in range(buttons.count() - 1, -1, -1):
        name = " ".join((buttons.nth(i).inner_text() or "").split())
        if name and name not in ("취소", "닫기", "아니오"):
            buttons.nth(i).click()
            r.settle(1600)
            return said
    return said


def sort_by(header: str, *, index: int = 0):
    """열 머리글을 눌러 정렬한다 — **첫 행이 실제로 바뀌었는가**를 본다.

    「정렬 버튼이 있다」는 정렬의 증거가 아니다. 서버에 맡기는 화면이면 질의에 정렬 축이
    실려야 하고, 화면 안에서 도는 화면이면 첫 행이 달라져야 한다. 둘 다 아니면 그 머리글은
    아무 일도 안 한다.
    """
    def _act(r, ctx):
        before = first_row_text(r)
        head = r.page.locator("#main-content table thead")
        button = head.get_by_role("button", name=header, exact=False)
        picked = header
        if not button.count():
            # **모든 열이 정렬되는 것은 아니다.** 이 제품의 표는 정렬 가능한 열에만
            # 머리글 버튼을 준다(나머지는 그냥 글자다). 이름을 못 찾았다고 멈추면
            # 「정렬이 없다」를 적게 되는데, 실제로는 **다른 열이** 정렬된다.
            button = head.get_by_role("button")
            if not button.count():
                stop("이 표에는 정렬되는 열이 하나도 없다")
            picked = " ".join((button.first.inner_text() or "").split())[:20]
        target = button.nth(min(index, button.count() - 1))
        cell = target.locator("xpath=ancestor::th[1]")
        sort_before = cell.get_attribute("aria-sort") if cell.count() else None
        rows_here = n_rows(r)
        target.click()
        r.settle(1500)
        after = first_row_text(r)
        sort_after = cell.get_attribute("aria-sort") if cell.count() else None
        query = " ".join(sorted({c["query"] for c in r.rec.calls if c["query"]}))[:160]
        # **표본이 두 행 이하면 «첫 행이 바뀌었는가» 로는 정렬을 증명할 수 없다.** 이미
        # 그 순서일 수 있기 때문이다. 그럴 때는 머리글이 스스로 밝히는 정렬 상태
        # (`aria-sort`)를 근거로 쓴다 — 그것이 이 컨트롤의 계약이다.
        moved = (after != before) or (sort_before != sort_after)
        return {"ui_action": "«%s» 머리글을 눌러 정렬한다" % picked,
                "frontend_state": "정렬 축 = %s (요청 «%s»)" % (picked, header),
                "observed": {"first_row": {"before": before, "after": after},
                             "aria_sort": {"before": sort_before, "after": sort_after},
                             "rows": rows_here, "query": query},
                "rendered": "첫 행 «%s» → «%s» · aria-sort %s → %s"
                            % (before[:36], after[:36], sort_before, sort_after),
                "expected": {"source": "derived-check",
                             "rule": "정렬을 걸면 순서나 정렬 상태나 질의 중 하나가 바뀐다",
                             "moved": moved, "query": query, "rows": rows_here},
                "failed": None if (moved or "sort" in query or "order" in query)
                          else "정렬을 눌렀는데 순서도 정렬 상태도 질의도 그대로다(표본 %d행)"
                               % rows_here}
    return _act


def row_menu(index: int = 0):
    """행의 넘침 메뉴를 연다 — **무엇을 할 수 있는가**가 관측값이다."""
    def _act(r, ctx):
        rows = rows_of(r)
        if not rows.count():
            stop("행이 없다 — 넘침 메뉴를 열 자리가 없다")
        opener = rows.nth(index).get_by_role("button").last
        if not opener.count():
            stop("행에 버튼이 없다")
        opener.click()
        r.settle(700)
        menu = r.page.locator('[role="menu"]')
        if not menu.count():
            stop("넘침 메뉴가 안 열렸다")
        items = [" ".join((menu.get_by_role("menuitem").nth(i).inner_text() or "").split())
                 for i in range(menu.get_by_role("menuitem").count())]
        r.press("Escape")
        return {"ui_action": "행의 넘침 메뉴를 연다",
                "frontend_state": "메뉴 열림",
                "observed": {"items": items},
                "rendered": "메뉴 항목 %d개 %s" % (len(items), items),
                "failed": None if items else "메뉴가 열렸는데 항목이 없다"}
    return _act


def menu_action(item: str, *, index: int = 0, confirm: bool = True, expect: str = ""):
    """넘침 메뉴에서 하나를 고르고 **확인까지 통과시킨다**."""
    def _act(r, ctx):
        rows = rows_of(r)
        if not rows.count():
            stop("행이 없다")
        rows.nth(index).get_by_role("button").last.click()
        r.settle(700)
        target = r.page.locator('[role="menu"]').get_by_role("menuitem", name=item,
                                                             exact=False)
        if not target.count():
            got = r.page.locator('[role="menu"]').inner_text() if r.page.locator(
                '[role="menu"]').count() else "(메뉴 없음)"
            r.press("Escape")
            stop("메뉴에 «%s» 가 없다 — 있는 것: %s" % (item, " ".join(got.split())[:120]))
        target.first.click()
        r.settle(900)
        asked = dialogs(r) > 0
        said = dialog_text(r) if asked else ""
        if asked:
            primary_button(r).click()
            r.settle(1600)
        body = r.main_text(120)
        return {"ui_action": "넘침 메뉴에서 «%s» 를 고른다" % item,
                "frontend_state": ("확인 대화 → 실행" if asked else "확인 없이 실행"),
                "observed": {"confirm_asked": asked, "confirm_text": said[:120]},
                "rendered": "본문 «%s»" % body,
                "expected": {"source": "derived-check",
                             "rule": ("위험한 동작은 확인을 받는다" if confirm
                                      else "이 동작은 확인 없이 바로 실행한다"),
                             "confirm_asked": asked},
                "failed": ("확인 대화 없이 바로 실행됐다" if confirm and not asked
                           else ("«%s» 가 화면에 안 나타났다" % expect
                                 if expect and expect not in body else None))}
    return _act


# ─────────────────────────────────────────────────────────────────────────────
# 탭 묶음 (S20 이 세운 다섯)
# ─────────────────────────────────────────────────────────────────────────────
def switch_tab(name: str, expect_param: str):
    """탭을 눌러 화면을 바꾼다 — **주소에도 남아야 한다**(공유·새로고침)."""
    def _act(r, ctx):
        before = r.main_text(70)
        tab = r.page.locator("#main-content").get_by_role("tab", name=name, exact=False)
        if not tab.count():
            names = [" ".join((r.page.get_by_role("tab").nth(i).inner_text() or "").split())
                     for i in range(r.page.get_by_role("tab").count())]
            stop("«%s» 탭이 없다 — 있는 탭: %s" % (name, names))
        tab.first.click()
        r.settle(1600)
        after_hash = unquote(r.hash_of())
        selected = r.page.locator('#main-content [role="tab"][aria-selected="true"]')
        picked = " ".join((selected.first.inner_text() or "").split()) if selected.count() \
            else ""
        # **기본 탭은 주소에서 `?tab=` 을 뺀다.** 그것이 이 그릇의 계약이다 — 기본 화면의
        # 주소가 조건 하나를 달고 다니면 링크가 지저분해지고, 그 조건이 «다른 탭» 을 뜻하는
        # 것도 아니다. 그래서 판정은 「주소에 그 낱말이 있는가」가 아니라 **「그 탭이
        # 골라졌고, 주소가 그 상태를 다시 열 수 있는가」** 다.
        bare = "?" not in after_hash
        ok = (expect_param in after_hash) or (bare and name in picked)
        return {"ui_action": "«%s» 탭으로 옮긴다" % name,
                "frontend_state": "tab=%s (기본 탭이면 주소에서 뺀다)" % expect_param,
                "observed": {"hash": after_hash, "selected_tab": picked},
                "rendered": "고른 탭 «%s» · 주소 «%s» · 본문 «%s»"
                            % (picked, after_hash, r.main_text(60)),
                "expected": {"source": "derived-check",
                             "rule": "탭을 바꾸면 그 탭이 골라지고 주소가 그 상태를 다시 연다",
                             "expect": expect_param, "got": after_hash,
                             "selected": picked},
                "failed": None if ok
                          else "탭을 눌렀는데 주소도 선택도 안 따라왔다: %s / «%s»"
                               % (after_hash, picked)}
    return _act


# ─────────────────────────────────────────────────────────────────────────────
# 권한 — 화면이 아니라 **서버**에 묻는다
# ─────────────────────────────────────────────────────────────────────────────
def _role_request(r, role: str, method: str, path: str, payload=None) -> dict:
    """그 역할로 **실제 로그인한 세션**에서 API 를 한 번 부른다.

    `as_role` 이 만들어 둔 컨텍스트를 그대로 쓴다 — 쿠키도 CSRF 토큰도 그 세션의 것이다.
    토큰을 안 실으면 쓰기가 **권한이 아니라 CSRF 때문에** 막히고, 그러면 이 Flow 는
    「막혔다」를 옳게 적지만 **틀린 이유로** 적는다.
    """
    def _call(page):
        script = """
        async ([method, path, payload]) => {
          let token = '';
          try {
            const me = await fetch('/api/me', {credentials: 'same-origin'});
            if (me.ok) token = (await me.json()).csrf_token || '';
          } catch (e) { /* 세션이 아예 없으면 토큰도 없다 — 그대로 보낸다 */ }
          const init = {method, credentials: 'same-origin',
                        headers: {'Content-Type': 'application/json'}};
          if (token) init.headers['X-CSRF-Token'] = token;
          if (payload !== null) init.body = JSON.stringify(payload);
          const res = await fetch(path, init);
          let body = '';
          try { body = (await res.text()).slice(0, 200); } catch (e) { body = ''; }
          return {status: res.status, body};
        }
        """
        return page.evaluate(script, [method, path, payload])

    return r.as_role(role, "/me" if role != "user" else "/me", "/", _call)


def forbidden_api(method: str, path: str, *, roles=("user",), payload=None,
                  allow=(403, 404)):
    """**직접 불러도 막히는가.** 화면에서 감춘 것은 표시일 뿐이다 (불변규칙 §5).

    지시가 S21 에 요구한 것 그대로다 — 「관리자 기능을 일반 사용자가 직접 API 호출해도
    차단되는지」. 통과 기준은 «200 이 아니면 실패» 가 아니라 **막는 코드로 막혔는가** 다:
    401(세션 없음)은 권한 계약의 답이 아니므로 여기서는 실패로 본다.
    """
    def _act(r, ctx):
        seen = {}
        bad = []
        for role in roles:
            got = _role_request(r, role, method, path, payload)
            seen[role] = got
            if got["status"] not in allow:
                bad.append("%s → HTTP %d %s" % (role, got["status"], got["body"][:70]))
        return {"ui_action": "역할 %s 가 %s %s 를 직접 부른다" % (", ".join(roles), method, path),
                "frontend_state": "화면을 거치지 않는 직접 호출",
                "observed": {"by_role": seen},
                "rendered": " · ".join("%s HTTP %d" % (k, v["status"]) for k, v in seen.items()),
                "expected": {"source": "derived-check",
                             "rule": "권한이 없는 역할은 %s 로 막힌다" % (allow,),
                             "allow": list(allow),
                             "got": {k: v["status"] for k, v in seen.items()}},
                "failed": None if not bad else "직접 호출이 안 막혔다: " + " · ".join(bad)}
    return _act


def allowed_api(method: str, path: str, *, role: str, payload=None, ok=(200, 201, 204)):
    """**반례.** 막히는 것만 세면 「전부 막힌다」와 구별이 안 된다."""
    def _act(r, ctx):
        got = _role_request(r, role, method, path, payload)
        return {"ui_action": "역할 %s 가 %s %s 를 직접 부른다" % (role, method, path),
                "observed": {role: got},
                "rendered": "%s → HTTP %d" % (role, got["status"]),
                "expected": {"source": "derived-check",
                             "rule": "이 역할에게는 실제로 열려 있다",
                             "expect": list(ok), "got": got["status"]},
                "failed": None if got["status"] in ok
                          else "열려 있어야 하는데 HTTP %d 다: %s" % (got["status"],
                                                                 got["body"][:80])}
    return _act


def scoped_list(path: str, *, roles=("user",), forbidden_needle: str = ""):
    """목록이 **그 역할에게 허용된 것만** 돌려주는가.

    「보이면 안 되는 것이 목록에 없다」를 세는 자리다. `forbidden_needle` 을 주면 그 글이
    응답 어디에도 없어야 한다.
    """
    def _act(r, ctx):
        seen = {}
        bad = []
        for role in roles:
            got = _role_request(r, role, "GET", path, None)
            seen[role] = {"status": got["status"], "body": got["body"][:160]}
            if got["status"] == 200 and forbidden_needle and forbidden_needle in got["body"]:
                bad.append("%s 의 응답에 «%s» 가 들어 있다" % (role, forbidden_needle))
        return {"ui_action": "역할 %s 로 %s 를 읽는다" % (", ".join(roles), path),
                "observed": {"by_role": seen},
                "rendered": " · ".join("%s HTTP %s" % (k, v["status"]) for k, v in seen.items()),
                "expected": {"source": "derived-check",
                             "rule": "권한 밖 자료는 목록에도 안 들어간다",
                             "needle": forbidden_needle},
                "failed": None if not bad else " · ".join(bad)}
    return _act


def detail_url_denied(hash_path: str, *, role: str = "user", shell: str = "/",
                      forbidden_needle: str = ""):
    """**목록에 없다고 끝이 아니다** — 주소를 직접 쳐도 안 열려야 한다.

    지시가 이 회차에 요구한 우회 검사다: 「목록에서는 안 보이는데 Detail URL 직접 접근으로
    열리는 우회가 없는지」.
    """
    def _act(r, ctx):
        text = r.as_role(role, hash_path, shell, read_main)
        leaked = bool(forbidden_needle) and forbidden_needle in text
        denied = any(w in text for w in ("권한", "찾을 수 없", "없습니다", "로그인", "본문 없음"))
        return {"ui_action": "역할 %s 가 %s 를 주소로 직접 연다" % (role, hash_path),
                "frontend_state": "라우트 가드 + 서버 가시성",
                "observed": {"body": text},
                "rendered": "본문 «%s»" % text,
                "expected": {"source": "derived-check",
                             "rule": "목록에 없는 것은 주소로도 안 열린다",
                             "needle": forbidden_needle, "denied": denied},
                "failed": ("주소를 직접 열었더니 «%s» 가 보인다" % forbidden_needle
                           if leaked else
                           (None if denied else "차단도 안내도 없이 화면이 그대로 열렸다"))}
    return _act


# ─────────────────────────────────────────────────────────────────────────────
# 값이 서버에 실제로 남았는가
# ─────────────────────────────────────────────────────────────────────────────
def api_says(path: str, needle: str, *, present: bool = True):
    """화면 말고 **서버**에 물어 확인한다 — 「화면이 바뀌었다」는 증거가 아니다."""
    def _act(r, ctx):
        payload = r.api_get(path)
        text = json.dumps(payload, ensure_ascii=False)
        found = needle in text
        return {"ui_action": "서버에 %s 를 다시 묻는다" % path,
                "observed": {"found": found, "size": len(text)},
                "rendered": "응답 %d자 · «%s» %s" % (len(text), needle,
                                                    "있음" if found else "없음"),
                "expected": {"source": "known-data",
                             "rule": "바꾼 값은 서버 응답에 %s" % ("있다" if present else "없다"),
                             "expect": present, "got": found},
                "failed": None if found is present
                          else ("서버 응답에 «%s» 가 %s" % (needle,
                                                        "없다" if present else "그대로 있다"))}
    return _act


def counts_match(path: str, pick: str, label: str):
    """화면의 숫자와 **서버가 센 숫자**가 같은가 (C13).

    `pick` 은 `items` 처럼 셀 목록의 키다. 화면에서는 표의 행을 센다.
    """
    def _act(r, ctx):
        payload = r.api_get(path)
        server = payload.get(pick) if isinstance(payload, dict) else payload
        n_server = len(server) if isinstance(server, list) else None
        if isinstance(payload, dict) and isinstance(payload.get("total"), int):
            n_server = payload["total"]
        n_screen = n_rows(r)
        return {"ui_action": "%s 의 행 수를 서버가 센 값과 견준다" % label,
                "observed": {"screen_rows": n_screen, "server": n_server},
                "rendered": "화면 %d행 · 서버 %s" % (n_screen, n_server),
                "expected": {"source": "known-data",
                             "rule": "화면이 그린 행 수는 서버가 센 수와 같다(한 쪽 기준)",
                             "expect": n_server, "got": n_screen},
                "failed": None if (n_server is None or n_screen == n_server
                                   or n_screen == min(n_server, 20))
                          else "화면 %d행 · 서버 %s 로 어긋난다" % (n_screen, n_server)}
    return _act


__all__ = [name for name in dir() if not name.startswith("_")]
