"""B1 Dashboard — `/me` 와 그 위젯 둘 (W8 · S18).

Pilot 이 이 원형에 묻는 것: **열자마자 오늘 할 일이 보이는가**, 그리고 그 판독 줄이
아래 목록을 실제로 거르는가. 화면이 바뀌었다는 사실은 증거가 아니므로 각 Flow 는
네트워크와 표 행 수를 함께 적는다.
"""

from __future__ import annotations

import re

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    click_then, close_modal, dialogs, flow, hidden_without_role, json, open_row_modal,
    retry_from_error, row_title, stop,
)

METRIC = '.k-metrics[aria-label="내 티켓"] .k-readout'
# 편집 Flow 는 **행이 넉넉한 버킷**에서 한다. 기본 버킷(오늘 마감)은 이 표본에서 한 행뿐이라,
# 앞 Flow 가 그 티켓의 상태를 바꾸는 순간 다음 Flow 에 누를 것이 없어진다 — 실제로 그렇게
# 세 Flow 가 연달아 죽었다. Flow 끼리 데이터를 뺏지 않게 «진행 중»(여러 행)으로 옮겨 둔다.
IN_PROGRESS = 2
# 이 실행이 로그인한 계정의 표시 이름. 담당자를 «나» 로 다시 고르면 바뀐 것이 없다.
ME = "UI QA"


def _focus_busy_bucket(r):
    cells = r.page.locator(METRIC)
    if cells.count() > IN_PROGRESS:
        cells.nth(IN_PROGRESS).click()
        r.settle(900)
WORK = '.k-metrics[aria-label="내 업무 요약"] .k-readout'
ROW_EDIT = 'button[aria-label^="수정"]'
SELECT_LABEL = {"te-status": "진행상태", "te-prio": "우선순위", "te-diff": "난이도"}


# ── /me ────────────────────────────────────────────────────────────────────
BUCKETS = ("due_today", "overdue", "in_progress", "due_soon", "blocked")


def _read(r, ctx):
    """판독 줄의 다섯 숫자를 **서버가 준 다섯 숫자와 견준다**.

    「그려졌다」는 지표 화면의 통과 근거가 아니다(C13). 화면이 스스로 세면 서버와 갈라지고,
    그 갈라짐은 칸이 그려져 있는 한 눈에 안 보인다 — 그래서 여기서 숫자를 맞춰 본다.
    """
    strip = r.page.locator(METRIC)
    cells = [" ".join((strip.nth(i).inner_text() or "").split()) for i in range(strip.count())]
    shown = []
    for text in cells:
        hit = re.search(r"\d+", text)
        shown.append(int(hit.group(0)) if hit else None)
    today = r.api_get("/api/home/today") or {}
    buckets = today.get("tickets") or {}
    want = [(buckets.get(k) or {}).get("count") for k in BUCKETS]
    same = shown == want
    sections = r.page.locator("#main-content h2")
    return {"ui_action": "/me 를 연다",
            "frontend_state": "GET /api/home/today 한 번 → 다섯 버킷",
            "observed": {"metric_cells": strip.count(), "sections": sections.count(),
                         "readout": shown, "api_counts": want, "labels": cells},
            "rendered": "판독 %d칸 %s · 구역 %d개 · 본문 «%s»"
                        % (strip.count(), shown, sections.count(), r.main_text(90)),
            "expected": {"source": "known-data",
                         "rule": "판독 줄의 다섯 숫자가 GET /api/home/today 의 버킷 수와 같다",
                         "buckets": list(BUCKETS), "expect": want, "got": shown},
            "failed": None if (shown and same)
                      else "화면이 말한 수(%s)와 서버가 준 수(%s)가 다르다" % (shown, want)}


flow("FF-0001", "user_me", "read",
     "GET /api/home/today 한 번으로 티켓 5버킷·스프린트·최근 문서를 받아 그린다",
     _read, route="/me", api="/api/home/today")


def _filter(r, ctx):
    before = r.rows()
    label = r.click(METRIC, index=1)   # 「지연」
    after = r.rows()
    heading = " ".join((r.page.locator("#main-content h2").first.inner_text() or "").split())
    return {"ui_action": "판독 줄의 «%s» 칸을 누른다" % " ".join(label.split()),
            "frontend_state": "focus=overdue",
            "observed": {"rows": {"before": before, "after": after}, "heading": heading},
            "rendered": "표 %d행 → %d행 · 구역 제목 «%s»" % (before, after, heading),
            "expected": {"source": "derived-check",
                         "rule": "누른 칸의 이름이 아래 구역 제목에 그대로 나타난다",
                         "expect": "지연", "got": heading,
                         "rows": {"before": before, "after": after}},
            "failed": None if "지연" in heading else "칸을 눌렀는데 구역 제목이 안 따라왔다"}


flow("FF-0002", "user_me", "filter",
     "지표 줄 5칸(오늘 마감·지연·진행 중·7일 내 마감·막힘)을 눌러 아래 티켓 표의 대상 버킷을 바꾼다",
     _filter, route="/me", api="/api/home/today", server=False)


def _poll(r, ctx):
    """30초 폴링. 「설정에 그렇게 적혀 있다」가 아니라 **실제로 다시 부르는지**를 본다."""
    r.rec.reset()
    r.page.wait_for_timeout(1500)
    idle = len(r.rec.matching("/api/home/today"))
    r.page.wait_for_timeout(31_000)
    calls = r.rec.matching("/api/home/today")
    return {"ui_action": "화면을 그대로 두고 31초를 기다린다",
            "frontend_state": "refetchInterval=30000",
            "observed": {"idle_calls_1_5s": idle, "calls_after_31s": len(calls)},
            "rendered": "31초 동안 재조회 %d회 (직전 1.5초 동안 %d회)" % (len(calls), idle),
            "expected": {"source": "derived-check",
                         "rule": "가만히 둬도 30초 안에 한 번은 다시 부른다(그 전 1.5초에는 안 부른다)",
                         "expect": ">=1 in 31s", "got": len(calls), "idle_1_5s": idle},
            "failed": None if calls else "30초가 지나도 재조회가 없었다"}


flow("FF-0003", "user_me", "refresh", "화면이 떠 있는 동안 30초마다 자동 재조회한다",
     _poll, route="/me", api="/api/home/today", tags=("slow",))

flow("FF-0004", "user_me", "refresh", "오류 상태에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/home/today", "홈 오늘"), route="/me", api="/api/home/today")


def _open_ticket(r, ctx):
    label = r.click("table tbody tr td button", index=0)
    return {"ui_action": "표의 첫 티켓 «%s» 을 누른다" % label,
            "frontend_state": "from=\"/me\" 를 들고 상세로",
            "url_state": "→ %s" % r.hash_of(),
            "rendered": "이동한 화면 본문 «%s»" % r.main_text(90),
            "expected": {"source": "derived-check",
                         "rule": "티켓 제목을 누르면 주소가 /tickets/:id 가 된다",
                         "expect": "/tickets/", "got": r.hash_of()},
            "failed": None if "/tickets/" in r.hash_of()
                      else "티켓 상세로 안 갔다: %s" % r.hash_of()}


flow("FF-0005", "user_me", "deep_link",
     "티켓 제목을 누르면 from:\"/me\" 상태와 함께 /tickets/:id 로 간다",
     _open_ticket, route="/me", api="/api/tickets/")

flow("FF-0006", "user_me", "navigation", "'내 티켓 전체' 링크로 /my-tickets 로 넘어간다",
     click_then("link=내 티켓 전체", expect="/my-tickets"),
     route="/me", api="/api/tickets/mine")

flow("FF-0008", "user_me", "navigation", "레일의 '스프린트 회의'·'문서 전체' 링크",
     click_then("link=스프린트 회의", expect="/sprint"), route="/me", api="/api/sprint")

flow("FF-0009", "user_me", "navigation", "최근 문서 행을 누르면 문서 상세로 간다",
     click_then("link=문서 01", expect="문서 01"),
     route="/me", api="/api/knowledge/documents/")


def _empty_action(r, ctx):
    """티켓 0건 얼굴은 **응답으로** 만든다 — 없는 상태를 상상해서 적지 않는다."""
    empty = {"tickets": {k: {"count": 0, "items": []} for k in
                         ("due_today", "overdue", "in_progress", "due_soon", "blocked")},
             "sprint": None, "recent": {"documents": []}}
    pattern = "**/api/home/today**"
    r.page.route(pattern, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(empty)))
    try:
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(1600)
        face = r.main_text(140)
        button = r.page.get_by_role("link", name="미할당 티켓 보기")
        if not button.count():
            button = r.page.get_by_role("button", name="미할당 티켓 보기")
        found = bool(button.count())
        if found:
            button.first.click()
            r.settle(1400)
    finally:
        r.page.unroute(pattern)
    return {"ui_action": "티켓 0건 상태에서 «미할당 티켓 보기» 를 누른다",
            "frontend_state": "anyTicket=false → EmptyState(art=tickets)",
            "observed": {"empty_face": face, "action_present": found},
            "rendered": "빈 얼굴 «%s» → 이동 후 «%s»" % (face[:70], r.main_text(70)),
            "expected": {"source": "known-data",
                         "rule": "다섯 버킷을 0건으로 만든 응답에서는 빈 얼굴과 «미할당 티켓 보기» 가 나온다",
                         "expect": {k: 0 for k in BUCKETS}, "got": face[:80],
                         "action_present": found},
            "failed": None if found else "티켓 0건인데 다음 행동이 없다"}


flow("FF-0007", "user_me", "navigation",
     "티켓이 하나도 없을 때 '미할당 티켓 보기'로 /unassigned 로 넘어간다",
     _empty_action, route="/me", api="/api/tickets/unassigned")


def _row_edit(r, ctx):
    _focus_busy_bucket(r)
    label = open_row_modal(r, ctx, opener=ROW_EDIT)
    # **마지막** 대화상자를 읽는다 — 셸에 상시 떠 있는(안 보이는) 대화상자가 하나 있어서
    # `.first` 는 그것을 붙들고, 안 보이는 요소의 글을 읽으려다 30초 뒤에 죽는다.
    head = r.page.locator('[role="dialog"]').last.locator(".MuiDialogTitle-root")
    title = " ".join((head.first.inner_text() or "").split()) if head.count() else ""
    return {"ui_action": "행의 수정 아이콘 «%s» 을 누른다" % label,
            "frontend_state": "editing=<그 행의 티켓> → Modal open",
            "observed": {"opener": label, "dialog_title": title},
            "rendered": "대화상자 «%s»" % title,
            "expected": {"source": "derived-check",
                         "rule": "그 행의 수정 아이콘을 누르면 «티켓 수정» 대화상자가 뜬다",
                         "expect": "티켓 수정", "got": title},
            "failed": None if "수정" in title
                      else "편집 모달이 아니다: «%s»" % title,
            "screenshots": [r.shot("ff0010-edit-modal")]}


flow("FF-0010", "user_me", "row_action",
     "compact 표의 수정 아이콘 버튼으로 그 행의 편집 모달을 연다",
     _row_edit, route="/me", server=False)


def _modal_open_close(r, ctx):
    _focus_busy_bucket(r)
    base = dialogs(r)
    open_row_modal(r, ctx, opener=ROW_EDIT)
    opened = dialogs(r)
    close_modal(r)
    closed = dialogs(r)
    return {"ui_action": "편집 모달을 열고 닫는다",
            "frontend_state": "open=true → open=false",
            "observed": {"base": base, "opened": opened, "after_close": closed},
            "rendered": "상시 %d · 열림 %d → 닫힘 %d" % (base, opened, closed),
            "expected": {"source": "derived-check",
                         "rule": "열면 대화상자가 하나 늘고, 닫으면 원래대로 돌아온다",
                         "dialogs": {"base": base, "opened": opened, "closed": closed}},
            "failed": None if (opened > base and closed <= base)
                      else "열리거나 닫히지 않았다"}


flow("FF-0011", "user_me", "modal_action", "TicketEditModal 을 이 화면에서 열고 닫는다",
     _modal_open_close, route="/me", server=False)


def _edit_field(field: str, value: str, *, says: str):
    """편집 모달에서 칸 하나를 바꿔 저장하고 **PATCH 본문**까지 확인한다.

    `value` 가 `None` 이면 «지금과 다른 값» 을 고른다 — 값을 고정하면 그 값이 이미 들어
    있는 행에서 「바뀐 것이 없다」가 되고, 그건 화면이 옳은데 Flow 가 틀린 것이다.
    """
    def _act(r, ctx):
        picked = value
        _focus_busy_bucket(r)
        target = row_title(r)
        open_row_modal(r, ctx, opener=ROW_EDIT)
        sent: list[dict] = []
        r.page.on("request", lambda req: sent.append(
            {"url": req.url, "body": req.post_data}) if req.method == "PATCH" else None)
        # **선택 상자는 역할로 고른다.** `#te-status` 는 MUI 가 숨겨 둔 `<input>` 이라
        # 그것을 누르면 클릭이 30초를 기다리다 시간 초과로 죽는다 — 실제로 그랬다.
        # 사람이 누르는 것은 `role="combobox"` 인 보이는 상자다.
        if field in ("te-status", "te-prio", "te-diff"):
            before, picked = r.choose_other(SELECT_LABEL[field])
        else:
            r.page.locator("#" + field).fill(value)
        r.settle(600)
        save = r.page.get_by_role("button", name="저장")
        disabled = save.first.is_disabled() if save.count() else None
        if save.count():
            save.first.click()
        r.settle(2000)
        patches = [s for s in sent if "/api/tickets/" in s["url"]]
        body = (patches[0]["body"] or "")[:200] if patches else None
        dialog_text = ""
        if dialogs(r) > 1:
            dialog_text = " ".join(
                (r.page.locator('[role="dialog"]').last.inner_text() or "").split())[:200]
        # 저장이 막히면 **화면이 이유를 말한다**(토스트). 그 문장을 안 읽으면 「PATCH 가
        # 없었다」까지만 알고 왜 없었는지는 모른 채로 남는다.
        toast = ""
        alerts = r.page.locator('[role="alert"], .MuiSnackbar-root')
        if alerts.count():
            toast = " ".join((alerts.last.inner_text() or "").split())[:120]
        return {"ui_action": "%s (%s → %s)" % (says, field, picked),
                "frontend_state": "form.%s=%s (dirty)" % (field, picked),
                "observed": {"patch_body": body, "save_disabled": disabled,
                             "toast": toast, "dialog_after": dialog_text},
                "cross": {"row": target, "expect": picked},
                "expected": {"source": "derived-check",
                             "rule": "저장하면 **바꾼 칸만** PATCH 본문에 실려 나간다",
                             "field": field, "value": picked, "patch_body": body},
                "rendered": "모달 닫힘 %s · 표 %d행 · 보낸 것 %s"
                            % (dialogs(r) <= 1, r.rows(), body),
                "failed": None if patches
                          else "저장을 눌렀는데 PATCH 가 없었다 — 화면이 말한 것: «%s»" % toast}
    return _act


flow("FF-0012", "user_me", "edit", "편집 모달 저장이 바뀐 필드만 PATCH 한다",
     _edit_field("te-wd", "2.5", says="예상 WD 를 2.5 로 바꿔 저장한다"),
     route="/me", api="/api/tickets/")
flow("FF-0013", "user_me", "status_change", "편집 모달의 진행상태 select 로 상태를 바꾼다",
     _edit_field("te-status", None, says="진행상태를 지금과 다른 값으로 바꿔 저장한다"),
     route="/me", api="/api/tickets/", cross=("/my-tickets", "/"))
flow("FF-0014", "user_me", "priority_change", "편집 모달의 우선순위 select 로 우선순위를 바꾼다",
     _edit_field("te-prio", None, says="우선순위를 지금과 다른 값으로 바꿔 저장한다"),
     route="/me", api="/api/tickets/", cross=("/my-tickets", "/"))


def _assignee(r, ctx):
    """담당자에 **나 아닌 사람**을 더한다.

    이 상자는 한 명이 아니라 **여럿을 담는다**(칩으로 쌓인다). 그래서 첫 후보가 나 자신이면
    누르는 순간 «더하기» 가 아니라 **나를 빼기** 가 되고, 그 티켓은 내 목록에서 사라진다 —
    실제로 그렇게 「그 행이 없다」가 나왔다. 나를 건너뛰고 다른 사람을 더한 뒤, 그 이름이
    `/my-tickets` 의 그 행에 도착했는지 본다(C13).
    """
    _focus_busy_bucket(r)
    target = row_title(r)
    open_row_modal(r, ctx, opener=ROW_EDIT)
    box = r.page.locator('[role="dialog"] .MuiAutocomplete-root input')
    if not box.count():
        box = r.page.locator('[role="dialog"] input[role="combobox"]')
    if not box.count():
        close_modal(r)
        stop("담당자 Combobox 가 없다")
    box.first.click()
    r.settle(900)
    options = r.page.get_by_role("option")
    count = options.count()
    label = ""
    for i in range(count):
        text = " ".join((options.nth(i).inner_text() or "").split())[:40]
        if ME in text:
            continue
        label = text
        options.nth(i).click()
        r.settle(400)
        break
    r.page.get_by_role("button", name="저장").first.click()
    r.settle(1800)
    return {"ui_action": "담당자 Combobox 를 열어 «%s» 를 고른다" % (label or "(나 아닌 후보 없음)"),
            "frontend_state": "options=%d" % count,
            "observed": {"option_count": count, "picked": label, "ticket": target},
            "cross": {"row": target, "expect": label.split()[0]} if label else {},
            "rendered": "후보 %d명 · 모달 닫힘 %s" % (count, dialogs(r) <= 1),
            "expected": {"source": "derived-check",
                         "rule": "더한 담당자가 내 티켓 목록의 그 행에도 나타난다",
                         "options": count, "picked": label, "ticket": target},
            "failed": None if label else "나 아닌 담당자 후보가 하나도 없다(후보 %d명)" % count}


flow("FF-0015", "user_me", "assignee_change",
     "편집 모달의 담당자 Autocomplete 로 배정을 바꾼다", _assignee,
     route="/me", api="/api/tickets/", cross=("/my-tickets", "/"))


def _validation(r, ctx):
    _focus_busy_bucket(r)
    open_row_modal(r, ctx, opener=ROW_EDIT)
    r.page.locator("input#te-title").fill("")
    r.settle(300)
    sent: list[str] = []
    r.page.on("request", lambda req: sent.append(req.url) if req.method == "PATCH" else None)
    r.page.get_by_role("button", name="저장").first.click()
    r.settle(1000)
    still = dialogs(r) > 1
    message = ""
    helper = r.page.locator(
        '[role="dialog"] .MuiFormHelperText-root, [role="dialog"] [role="alert"]')
    if helper.count():
        message = " ".join((helper.first.inner_text() or "").split())[:80]
    close_modal(r)
    return {"ui_action": "제목을 비우고 저장을 누른다",
            "frontend_state": "required 위반 → 제출 차단",
            "observed": {"patch_requests": len(sent), "message": message,
                         "dialog_still_open": still},
            "rendered": "모달 유지 %s · 안내 «%s» · PATCH %d건" % (still, message, len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "필수값이 비면 모달이 열린 채 남고 PATCH 는 0건이다",
                         "expect": {"dialog_open": True, "patch_requests": 0},
                         "got": {"dialog_open": still, "patch_requests": len(sent)},
                         "message": message},
            "failed": None if (still and not sent) else "필수값이 비었는데 서버로 보냈다"}


flow("FF-0016", "user_me", "form_validation",
     "저장 전 제목·진행상태 필수와 WD 숫자 형식을 검사한다",
     _validation, route="/me", server=False)


# ── 위젯: 내 업무 요약 ──────────────────────────────────────────────────────
def _work_read(r, ctx):
    cells = r.page.locator(WORK)
    first = " ".join((cells.first.inner_text() or "").split())[:60] if cells.count() else ""
    return {"ui_action": "/me 의 «내 업무» 구역을 받는다",
            "observed": {"cells": cells.count(), "first": first},
            "rendered": "판독 %d칸 · 첫 칸 «%s»" % (cells.count(), first),
            "failed": None if cells.count() else "판독 줄이 하나도 안 그려졌다"}


flow("FF-1143", "user_me__work-summary", "read",
     "내 업무 요약(미완료·이번 주 마감·지연 / 차질 프로젝트·지연 마일스톤·완료 추이)을 받는다",
     _work_read, route="/me", api="/api/home/work-dashboard")

flow("FF-1144", "user_me__work-summary", "navigation",
     "'내 미완료'·'이번 주 마감'·'지연 티켓' 칸을 누르면 /my-tickets 로 간다",
     click_then(WORK, index=0), route="/me", api="/api/tickets/mine")

flow("FF-1145", "user_me__work-summary", "navigation",
     "'차질 프로젝트'·'지연 마일스톤' 칸을 누르면 /projects 로 간다",
     click_then(WORK, index=3), route="/me", api="/api/projects")

flow("FF-1146", "user_me__work-summary", "navigation",
     "구역 머리의 '오늘 화면 열기 →' 링크가 /me 로 이동한다",
     click_then("button=오늘 화면 열기"), route="/me", api="/api/home/today")

flow("FF-1147", "user_me__work-summary", "refresh", "오류 상태의 '다시 시도'",
     retry_from_error("/api/home/work-dashboard", "내 업무 요약"),
     route="/me", api="/api/home/work-dashboard")


# ── 위젯: AI 도우미 패널 ────────────────────────────────────────────────────
def _assistant_read(r, ctx):
    tabs = r.page.locator('#main-content [role="tab"]')
    return {"ui_action": "AI 도우미 패널의 기본 탭(오늘 브리핑)을 받는다",
            "observed": {"tabs": tabs.count()},
            "rendered": "탭 %d개 · 본문 «%s»" % (tabs.count(), r.main_text(90)),
            "failed": None if tabs.count() >= 4 else "탭이 넷이 아니다"}


flow("FF-1148", "user_me__assistant-panel", "read",
     "고른 탭의 집계를 받는다(오늘 브리핑·스탠드업 초안·주간 다이제스트·미할당 트리아지)",
     _assistant_read, route="/me", api="/api/assistant")

flow("FF-1149", "user_me__assistant-panel", "filter",
     "탭 4개로 보는 관점을 바꾼다 — 옮기면 문장 요약 요청은 초기화된다",
     click_then("tab=스탠드업 초안"), route="/me", api="/api/assistant")


def _narrate(r, ctx):
    button = r.page.get_by_role("button", name="문장 요약 만들기")
    if not button.count():
        stop("«문장 요약 만들기» 가 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2600)
    calls = r.rec.matching("narrate")
    return {"ui_action": "«문장 요약 만들기» 를 누른다",
            "frontend_state": "narrate=true 로 같은 탭을 다시 요청",
            "observed": {"narrate_calls": [c["query"] for c in calls][:3]},
            "rendered": r.main_text(120),
            "failed": None if calls else "narrate 요청이 없었다"}


flow("FF-1150", "user_me__assistant-panel", "read",
     "'문장 요약 만들기'를 누르면 같은 탭을 ?narrate=true 로 다시 요청해 문장을 받는다",
     _narrate, route="/me", api="/api/assistant")


def _tab_then_go(tab: str, href_part: str, what: str):
    def _act(r, ctx):
        r.click("tab=" + tab)
        target = r.page.locator('#main-content a[href*="%s"]' % href_part)
        if not target.count():
            return {"ui_action": "«%s» 탭에서 %s 로 가는 링크를 찾는다" % (tab, what),
                    "notes": ["이 표본에는 %s 로 갈 항목이 없다 — 링크가 없는 것이 맞다" % what],
                    "rendered": "본문 «%s»" % r.main_text(110)}
        label = " ".join((target.first.inner_text() or "").split())[:50]
        target.first.click()
        r.settle(1500)
        return {"ui_action": "«%s» 탭에서 «%s» 를 누른다" % (tab, label),
                "url_state": "→ %s" % r.hash_of(),
                "rendered": "이동 후 본문 «%s»" % r.main_text(90),
                "failed": None if href_part in r.hash_of()
                          else "%s 로 안 갔다: %s" % (what, r.hash_of())}
    return _act


flow("FF-1151", "user_me__assistant-panel", "deep_link",
     "스탠드업·트리아지의 티켓 제목이 #/tickets/:id 로 간다",
     _tab_then_go("스탠드업 초안", "/tickets/", "티켓 상세"),
     route="/me", api="/api/tickets/")

flow("FF-1152", "user_me__assistant-panel", "navigation",
     "주간 다이제스트의 바뀐 문서가 문서 상세로 간다",
     _tab_then_go("주간 다이제스트", "/knowledge/", "문서 상세"),
     route="/me", api="/api/knowledge/")

flow("FF-1153", "user_me__assistant-panel", "navigation",
     "트리아지 안내가 실제 배정 화면(#/unassigned)으로 보낸다",
     _tab_then_go("미할당 트리아지", "/unassigned", "미할당 티켓"),
     route="/me", api="/api/tickets/unassigned")

flow("FF-1154", "user_me__assistant-panel", "refresh", "오류 상태의 '다시 시도'",
     retry_from_error("/api/assistant", "AI 도우미"), route="/me", api="/api/assistant")
