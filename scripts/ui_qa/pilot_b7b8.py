"""B7 Report/회의 — `/sprint` · B8 Operations console — `/jobs` (W8 · S18).

  * **회의 화면(B7)** — 주를 옮기고 조건을 거는 것이 회의 중에 즉시 되는가. 이 원형의
    조건은 서버 왕복이 아니라 **그 주치를 전량 받아 화면에서 거르는** 계약이라(쪽이
    없다), 조건 다섯 축의 「쪽 초기화」는 «초기화할 쪽이 없다» 가 정답이다.
  * **운영 콘솔(B8)** — 지금 확인할 것이 무엇인지 화면이 먼저 말하는가. 실패를 눈으로
    찾게 하지 않는 것이 이 원형의 첫 질문이다.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    back_forward, blocked_route, cache_key, choose_then, click_then, close_modal, compound,
    flow, modal_open_close, open_row, open_row_modal, page_reset, pager, race,
    retry_from_error, search_then, stop, title_like, unquote_hash,
)

ADMIN = "/admin"
SPRINT_SEARCH = '#main-content input[aria-label="검색어"]'
JOB_RUN_ID = "label=실행 건 ID"


# ═══════════════════════════════════════════════════════════════════════════
# B7 — /sprint
# ═══════════════════════════════════════════════════════════════════════════
def _sprint_read(r, ctx):
    """구역이 그려졌는가가 아니라 **서버가 준 사람들이 다 있는가**를 본다 (C13)."""
    sections = r.page.locator("#main-content h2")
    labels = [" ".join((sections.nth(i).inner_text() or "").split())
              for i in range(sections.count())]
    summary = r.api_get("/api/sprint") or {}
    want = [d.get("name") for d in (summary.get("by_assignee") or []) if d.get("name")]
    body = r.main_text(4000)
    missing = [n for n in want if n not in body]
    return {"ui_action": "/sprint 를 연다",
            "frontend_state": "그 주(월~일)치를 전량 받아 화면에서 거른다",
            "observed": {"sections": labels, "tables": r.page.locator("table").count(),
                         "api_assignees": want, "missing_on_screen": missing},
            "rendered": "구역 %d개 %s · 담당자 %d명 중 화면에 없는 사람 %d명"
                        % (len(labels), labels, len(want), len(missing)),
            "expected": {"source": "known-data",
                         "rule": "GET /api/sprint 가 준 담당자가 모두 화면에 있다",
                         "expect": want, "missing": missing},
            "failed": ("구역이 하나도 안 그려졌다" if not labels
                       else ("서버가 준 담당자 %s 가 화면에 없다" % missing if missing
                             else None))}


flow("FF-0159", "user_sprint", "read", "그 주(월~일) 스프린트 요약을 전량 조회한다",
     _sprint_read, route="/sprint", api="/api/sprint")


def _week_move(button: str):
    def _act(r, ctx):
        before = r.hash_of()
        r.rec.reset()
        r.click("button=" + button)
        calls = r.rec.matching("/api/sprint")
        return {"ui_action": "«%s» 를 누른다" % button,
                "url_state": "%s → %s" % (before, r.hash_of()),
                "observed": {"calls": [(c["path"], c["query"][:60]) for c in calls][:2]},
                "rendered": "주소 «%s» · 본문 «%s»" % (r.hash_of(), r.main_text(70)),
                "expected": {"source": "derived-check",
                             "rule": "주를 옮기면 주소의 week 가 그 주 월요일로 바뀐다",
                             "expect": "≠ %s" % before, "got": r.hash_of()},
                "failed": None if r.hash_of() != before
                          else "주를 옮겼는데 주소가 그대로다"}
    return _act


flow("FF-0160", "user_sprint", "filter",
     "이전 주/이번 주/다음 주로 기간을 옮긴다(주소의 week = 그 주 월요일)",
     _week_move("이전 주"), route="/sprint", api="/api/sprint")

flow("FF-0161", "user_sprint", "filter", "'조회 부서'로 회의 대상 팀을 바꾼다(화면 Context)",
     choose_then("플랫폼", "서비스운영팀"), route="/sprint", api="/api/sprint")

flow("FF-0162", "user_sprint", "search", "제목 검색으로 두 목록을 함께 좁힌다(화면에서 거른다)",
     search_then("업무 0", box=SPRINT_SEARCH), route="/sprint", server=False)

flow("FF-0163", "user_sprint", "filter", "프로젝트 조건",
     choose_then("프로젝트", "포털 개편"), route="/sprint", server=False)
flow("FF-0164", "user_sprint", "filter", "진행상태 조건",
     choose_then("상태", "진행"), route="/sprint", server=False)
flow("FF-0165", "user_sprint", "filter", "우선순위 조건",
     choose_then("우선순위", "높음"), route="/sprint", server=False)
flow("FF-0166", "user_sprint", "filter", "난이도 조건",
     choose_then("난이도", "상"), route="/sprint", server=False)
flow("FF-0167", "user_sprint", "filter", "담당자 조건",
     choose_then("담당자", "UI QA"), route="/sprint", server=False)


def _assignee_card(r, ctx):
    # 상단바의 계정 버튼도 «UI QA» 다 — 본문에서 찾는다.
    card = r.in_main("button", "UI QA")
    if not card.count():
        stop("담당자 카드가 없다")
    before = r.rows()
    label = " ".join((card.first.inner_text() or "").split())[:50]
    card.first.click()
    r.settle(1000)
    mid = r.rows()
    card.first.click()   # 토글
    r.settle(1000)
    return {"ui_action": "담당자 카드 «%s» 를 눌렀다 다시 누른다" % label,
            "frontend_state": "assignee=<그 사람> → 해제",
            "observed": {"rows": {"before": before, "picked": mid, "toggled_off": r.rows()}},
            "rendered": "표 %d → %d → %d행" % (before, mid, r.rows()),
            "expected": {"source": "derived-check",
                         "rule": "카드를 껐다 켜면 행 수가 원래대로 돌아온다",
                         "expect": before, "got": r.rows(), "while_on": mid},
            "failed": None if r.rows() == before
                      else "토글을 껐는데 원래대로 안 돌아왔다"}


flow("FF-0168", "user_sprint", "filter",
     "담당자 카드를 눌러 아래 목록을 그 사람 티켓만으로 좁힌다(토글)",
     _assignee_card, route="/sprint", server=False)


def _sprint_clear(r, ctx):
    before = r.rows()
    r.choose("상태", "진행")
    narrowed = r.rows()
    button = r.page.get_by_role("button", name="필터 초기화")
    if not button.count():
        button = r.page.get_by_role("button", name="지우기")
    if not button.count():
        stop("«필터 초기화» 가 없다 — %d행 → %d행 인 화면: «%s»"
             % (before, narrowed, r.main_text(220)))
    button.first.click()
    r.settle(1200)
    return {"ui_action": "조건을 건 뒤 «필터 초기화» 를 누른다",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"rows": {"before": before, "narrowed": narrowed,
                                  "cleared": r.rows()}},
            "rendered": "표 %d행 → %d행 · 주소 «%s»" % (narrowed, r.rows(), r.hash_of()),
            "expected": {"source": "derived-check",
                         "rule": "조건을 지우면 좁아졌던 결과가 다시 넓어진다",
                         "expect": ">= %d" % narrowed, "got": r.rows(),
                         "hash": r.hash_of()},
            "failed": None if r.rows() >= narrowed else "지웠는데 행이 안 늘었다"}


flow("FF-0169", "user_sprint", "filter", "'필터 지우기'로 주소에 남을 수 있는 조건 전부를 지운다",
     _sprint_clear, route="/sprint", server=False)


def _sprint_edit(r, ctx):
    open_row_modal(r, ctx, opener="button=수정")
    before, picked = r.choose_other("진행상태")
    r.settle(400)
    r.rec.reset()
    r.page.get_by_role("button", name="저장").first.click()
    r.settle(2000)
    calls = r.rec.matching("/api/tickets/")
    return {"ui_action": "회의 중 «수정» 으로 티켓 상태를 «%s» → «%s» 로 바꾼다" % (before, picked),
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(90),
            "expected": {"source": "derived-check",
                         "rule": "회의 중 고친 상태가 PATCH 로 나간다",
                         "expect": "%s → %s" % (before, picked),
                         "got": [(c["method"], c["status"]) for c in calls][:3]},
            "failed": None if any(c["method"] == "PATCH" for c in calls)
                      else "저장했는데 PATCH 가 없었다"}


flow("FF-0170", "user_sprint", "edit", "'수정'으로 티켓 상태·담당자·마감을 회의 중 바로 바꾼다",
     _sprint_edit, route="/sprint", api="/api/tickets/")

flow("FF-0171", "user_sprint", "modal_action", "티켓 편집 모달 열기·저장·닫기",
     modal_open_close("button=수정"), route="/sprint", server=False)


def _sprint_open_ticket(r, ctx):
    # 사이드바의 «내 업무» 가 아니라 **본문의 티켓 제목**이다.
    button = r.page.locator("#main-content").get_by_role("button", name=title_like("업무"))
    if not button.count():
        stop("티켓 제목 버튼이 없다")
    label = " ".join((button.first.inner_text() or "").split())[:40]
    button.first.click()
    r.settle(1600)
    return {"ui_action": "티켓 «%s» 을 누른다" % label,
            "frontend_state": "회의 화면 → 티켓 상세",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"picked": label, "hash": r.hash_of()},
            "rendered": "본문 «%s»" % r.main_text(90),
            "expected": {"source": "derived-check",
                         "rule": "티켓 제목을 누르면 주소가 /tickets/:id 가 된다",
                         "expect": "/tickets/", "got": r.hash_of()},
            "failed": None if "/tickets/" in r.hash_of() else "티켓 상세로 안 갔다"}


flow("FF-0172", "user_sprint", "navigation", "티켓 제목을 눌러 티켓 상세로 간다",
     _sprint_open_ticket, route="/sprint", api="/api/tickets/")

flow("FF-0173", "user_sprint", "navigation", "'미할당 티켓 화면 열기'로 배분 화면으로 보낸다",
     click_then("button=‘미할당 티켓’ 화면 열기", expect="/unassigned"), route="/sprint",
     api="/api/tickets/unassigned")


def _collapse_group(r, ctx):
    button = r.in_main("button", "UI QA")
    if not button.count():
        stop("담당자 묶음 머리가 없다")
    before = r.rows()
    button.first.click()
    r.settle(900)
    after = r.rows()
    return {"ui_action": "담당자 묶음 머리를 누른다",
            "frontend_state": "그 사람 묶음을 접는다",
            "observed": {"rows": {"before": before, "after": after}},
            "rendered": "표 %d행 → %d행" % (before, after),
            "expected": {"source": "derived-check",
                         "rule": "묶음 머리를 누른 뒤 표에 남은 행 수를 그대로 적는다",
                         "rows": {"before": before, "after": after}}}


flow("FF-0174", "user_sprint", "row_action",
     "담당자 그룹을 접었다 펴며 한 사람씩 훑는다(collapsible)",
     _collapse_group, route="/sprint", server=False)


def _sprint_deep_link(r, ctx):
    r.goto("/sprint?status=진행")
    rows = r.rows()
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(1600)
    return {"ui_action": "조건이 붙은 회의 주소로 들어가 새로고침한다",
            "url_state": "/sprint?status=진행 → %s" % r.hash_of(),
            "observed": {"rows": {"before": rows, "after": r.rows()}},
            "rendered": "표 %d행 → %d행" % (rows, r.rows()),
            "expected": {"source": "derived-check",
                         "rule": "조건이 붙은 주소는 새로고침해도 그 조건을 그대로 갖는다",
                         "expect": "status=진행", "got": unquote_hash(r.hash_of()),
                         "rows": {"before": rows, "after": r.rows()}},
            "failed": None if "status" in unquote_hash(r.hash_of())
                      else "새로고침 뒤 조건이 사라졌다: %s" % r.hash_of()}


flow("FF-0175", "user_sprint", "deep_link", "주·부서·조건을 주소에 실어 회의 링크를 공유한다",
     _sprint_deep_link, api="/api/sprint")


def _sprint_back(r, ctx):
    r.goto("/sprint")
    first = r.hash_of()
    r.click("button=이전 주")
    moved = r.hash_of()
    r.back()
    r.settle(1500)
    return {"ui_action": "주를 옮긴 뒤 뒤로가기",
            "url_state": "%s → %s → (뒤로) %s" % (first, moved, r.hash_of()),
            "observed": {"hashes": [first, moved, r.hash_of()]},
            "rendered": "주소 %s" % r.hash_of(),
            "expected": {"source": "derived-check",
                         "rule": "주 이동은 push 라 뒤로가기가 앞 주소로 돌아간다",
                         "expect": "≠ %s" % moved, "got": r.hash_of()},
            "failed": None if r.hash_of() != moved
                      else "주 이동이 replace 라 뒤로가기가 안 먹는다"}


flow("FF-0176", "user_sprint", "back_forward", "주 이동은 push라 뒤로가기로 이전 주로 돌아간다",
     _sprint_back, api="/api/sprint")

flow("FF-0177", "user_sprint", "refresh", "조회 오류에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/sprint", "스프린트 요약"), route="/sprint", api="/api/sprint")


def _sprint_blocked_face(r, ctx):
    pattern = "**/api/sprint**"
    r.page.route(pattern, lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='{"configured": false, "ok": false, "message": "티켓 소스를 읽지 못했습니다."}'))
    try:
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(1600)
        face = r.main_text(160)
    finally:
        r.page.unroute(pattern)
    return {"ui_action": "티켓 소스를 못 읽는 응답을 받는다",
            "frontend_state": "configured=false",
            "observed": {"face": face},
            "rendered": "본문 «%s»" % face,
            "expected": {"source": "known-data",
                         "rule": "configured=false 응답에서는 이유를 말하는 얼굴이 나온다",
                         "expect": "티켓 소스를 읽지 못했습니다.", "got": face[:120]},
            "failed": None if face else "이유를 말하는 얼굴이 없다"}


flow("FF-0178", "user_sprint", "permission_state",
     "연동 미설정·조회 실패는 티켓 화면 공용 안내로 대체한다",
     _sprint_blocked_face, route="/sprint", api="/api/sprint")


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
def _sprint_compound(r, ctx):
    before = r.rows()
    r.choose("상태", "진행")
    mid = r.rows()
    r.choose("우선순위", "높음")
    return {"ui_action": "상태와 우선순위를 **함께** 건다",
            "frontend_state": "status=진행 & priority=높음",
            "observed": {"rows": {"none": before, "one": mid, "both": r.rows()}},
            "rendered": "표 %d → %d → %d행" % (before, mid, r.rows()),
            "expected": {"source": "derived-check",
                         "rule": "조건을 더할수록 결과는 좁아지기만 한다",
                         "expect": "both <= one <= none",
                         "got": {"none": before, "one": mid, "both": r.rows()}},
            "failed": None if r.rows() <= mid <= before
                      else "조건을 더했는데 결과가 늘었다"}


flow("FF-1361", "user_sprint", "filter", "복합 — 프로젝트 × 상태",
     _sprint_compound, route="/sprint", server=False)


def _sprint_no_page(r, ctx):
    r.choose("상태", "진행")
    hash_after = r.hash_of()
    pager_button = r.page.get_by_role("button", name="다음")
    return {"ui_action": "조건을 바꾼 뒤 주소와 페이저를 본다",
            "frontend_state": "이 화면은 그 주치를 **전량** 받는다 — 쪽이 없다",
            "observed": {"hash": hash_after, "pager_buttons": pager_button.count()},
            "rendered": "주소 «%s» · 페이저 %d개" % (hash_after, pager_button.count()),
            "expected": {"source": "derived-check",
                         "rule": "쪽이 없는 화면이라 조건을 바꿔도 주소에 page 가 안 붙는다",
                         "expect": "page= 없음", "got": hash_after},
            "failed": None if "page=" not in hash_after
                      else "쪽이 없는 화면인데 주소에 page 가 붙었다"}


flow("FF-1362", "user_sprint", "filter",
     "조건을 바꿔도 쪽 초기화가 필요 없다 — 그 주치를 전량 받는다",
     _sprint_no_page, route="/sprint", server=False)

flow("FF-1363", "user_sprint", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(SPRINT_SEARCH, "업", "업무 02"), route="/sprint", server=False)

flow("FF-1364", "user_sprint", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/sprint?status=진행", "/sprint?status=완료"), api="/api/sprint")

flow("FF-1365", "user_sprint", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/sprint?status=진행", "/sprint?status=완료"), api="/api/sprint")


# ═══════════════════════════════════════════════════════════════════════════
# B8 — /jobs
# ═══════════════════════════════════════════════════════════════════════════
JOB_STRIP = '#main-content .k-readout'


def _jobs_summary_click(r, ctx):
    cells = r.page.locator(JOB_STRIP)
    if not cells.count():
        stop("작업 큐의 판독 줄이 없다")
    labels = [" ".join((cells.nth(i).inner_text() or "").split())[:24]
              for i in range(cells.count())]
    before = r.rows()
    target = None
    for i in range(cells.count()):
        if "실패" in labels[i]:
            target = i
            break
    if target is None:
        target = 0
    cells.nth(target).click()
    r.settle(1400)
    return {"ui_action": "판독 줄의 «%s» 칸을 누른다" % labels[target],
            "frontend_state": "status=failed",
            "observed": {"cells": labels, "rows": {"before": before, "after": r.rows()}},
            "rendered": "표 %d행 → %d행 · 주소 «%s»" % (before, r.rows(), r.hash_of()),
            "failed": None if r.rows() <= before
                      else "실패만 골랐는데 행이 늘었다"}


flow("FF-0929", "admin_jobs", "filter",
     "요약 카드(대기·실행 중·실패·최근 24시간 실패·가장 오래된 대기)를 눌러 그 상태로 목록을 좁힌다",
     _jobs_summary_click, route="/jobs", shell=ADMIN, api="/api/admin/jobs")

flow("FF-0930", "admin_jobs", "filter", "상태(대기/실행 중/완료/실패/취소됨)로 좁힌다",
     choose_then("상태", "실패"), route="/jobs", shell=ADMIN, api="/api/admin/jobs")

flow("FF-0931", "admin_jobs", "filter",
     "유형(채팅 메시지·예약 실행·메일 발송)으로 좁힌다 — 문서 생성·Notion 동기화는 S11 이 걷었다",
     choose_then("유형", "메일 발송"), route="/jobs", shell=ADMIN, api="/api/admin/jobs")


def _typed_filter(label: str, value: str):
    """자유 입력 조건 — 값이 없으면 **0행이 정답**이다."""
    def _act(r, ctx):
        box = r.page.get_by_label(label, exact=False)
        if not box.count():
            stop("«%s» 입력칸이 없다" % label)
        before = r.rows()
        box.first.fill(value)
        r.settle(1500)
        return {"ui_action": "«%s» 에 %r 을 넣는다" % (label, value),
                "frontend_state": "%s=%s" % (label, value),
                "observed": {"rows": {"before": before, "after": r.rows()}},
                "rendered": "표 %d행 → %d행" % (before, r.rows()),
                "failed": None if r.rows() <= before
                          else "없는 id 로 걸렀는데 행이 늘었다"}
    return _act


flow("FF-0932", "admin_jobs", "filter", "연결된 스케줄 ID로 좁힌다",
     _typed_filter("연결된 스케줄", "00000000-0000-0000-0000-000000000000"),
     route="/jobs", shell=ADMIN, api="/api/admin/jobs")
flow("FF-0933", "admin_jobs", "filter", "실행 건 ID로 좁힌다",
     _typed_filter("실행 건", "00000000-0000-0000-0000-000000000000"),
     route="/jobs", shell=ADMIN, api="/api/admin/jobs")
# FF-0934 「연결된 문서 생성 ID로 좁힌다」는 **여기 없다.** 그 조건이 가리키던 기능
# (문서 생성 잡)을 S11 이 걷었고, 화면에도 그 입력 칸이 없다 — 없는 것을 누르는 Flow 를
# 쓰면 그 실패는 제품이 아니라 표가 낡았다는 뜻이 된다. 원장에서 `exists: false` 로
# 정정했다(`FUNCTIONAL_COVERAGE.json`).


def _jobs_clear(r, ctx):
    r.choose("상태", "실패")
    narrowed = r.rows()
    button = r.page.get_by_role("button", name="필터 초기화")
    if not button.count():
        button = r.page.get_by_role("button", name="지우기")
    if not button.count():
        stop("«필터 초기화» 가 없다")
    button.first.click()
    r.settle(1400)
    return {"ui_action": "조건을 건 뒤 «필터 초기화» 를 누른다",
            "observed": {"rows": {"narrowed": narrowed, "cleared": r.rows()}},
            "rendered": "표 %d행 → %d행 · 주소 «%s»" % (narrowed, r.rows(), r.hash_of()),
            "failed": None if r.rows() >= narrowed else "지웠는데 행이 안 늘었다"}


flow("FF-0935", "admin_jobs", "filter", "‘필터 지우기’로 필터를 한 번에 해제한다",
     _jobs_clear, route="/jobs", shell=ADMIN, api="/api/admin/jobs")


def _saved_views(r, ctx):
    button = r.page.get_by_role("button", name="저장된 뷰")
    if not button.count():
        stop("«저장된 뷰» 가 없다")
    button.first.click()
    r.settle(700)
    panel = r.page.locator('[role="dialog"], [role="menu"], [role="presentation"]').last
    text = " ".join((panel.inner_text() or "").split())[:140] if panel.count() else ""
    r.press("Escape")
    return {"ui_action": "«저장된 뷰» 를 연다",
            "observed": {"panel": text},
            "rendered": "패널 «%s»" % text,
            "failed": None if text else "저장된 뷰 패널이 비었다"}


flow("FF-0936", "admin_jobs", "filter",
     "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     _saved_views, route="/jobs", shell=ADMIN, server=False)

flow("FF-0937", "admin_jobs", "pagination",
     "목록 위·아래 페이저로 페이지를 넘긴다(100행 화면이라 위에도 둔다)",
     pager(), route="/jobs", shell=ADMIN, api="/api/admin/jobs", server=False)


def _job_detail(r, ctx):
    if not r.page.locator("table tbody tr").count():
        stop("작업이 한 행도 없다")
    open_row(r)
    body = r.main_text(180)
    ctx["job_open"] = True
    return {"ui_action": "작업 행을 눌러 상세를 연다",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"body": body},
            "rendered": "상세 «%s»" % body,
            "failed": None if body else "상세가 비었다"}


flow("FF-0938", "admin_jobs", "read",
     "행을 눌러 작업 상세(시도 횟수·소요 시간·마지막 오류 원문)를 연다",
     _job_detail, route="/jobs", shell=ADMIN, api="/api/admin/jobs")


def _job_action(name: str, expect_word: str):
    def _act(r, ctx):
        button = r.page.get_by_role("button", name=name)
        if not button.count():
            menu = r.page.get_by_label("더 보기")
            if menu.count():
                menu.first.click()
                r.settle(500)
                button = r.page.get_by_role("menuitem", name=name)
        if not button.count():
            return {"ui_action": "«%s» 를 찾는다" % name,
                    "notes": ["이 작업의 상태에서는 «%s» 가 없는 것이 맞다" % name],
                    "rendered": "«%s» 없음 · 본문 «%s»" % (name, r.main_text(90))}
        r.rec.reset()
        button.first.click()
        r.settle(800)
        dialog = r.page.locator('[role="dialog"]')
        text = " ".join((dialog.first.inner_text() or "").split())[:180] if dialog.count() else ""
        cancel = r.page.get_by_role("button", name="취소")
        if cancel.count():
            cancel.first.click()
            r.settle(500)
        writes = [c for c in r.rec.calls if c["method"] in ("POST", "DELETE")]
        return {"ui_action": "«%s» 를 누르고 확인 문구를 읽은 뒤 취소한다" % name,
                "observed": {"confirm": text, "writes_before_confirm": len(writes)},
                "rendered": "확인 문구 «%s»" % text,
                "failed": None if not writes else "확인 전에 이미 보냈다"}
    return _act


flow("FF-0939", "admin_jobs", "admin_op", "‘재시도’로 실패한 작업을 다시 큐에 넣는다(확인 후)",
     _job_action("재시도", "재시도"), shell=ADMIN, server=False)
flow("FF-0940", "admin_jobs", "admin_op",
     "‘취소’로 대기 중 작업을 취소한다(연결된 티켓·문서·스케줄도 정리된다)",
     _job_action("취소", "취소"), shell=ADMIN, server=False)
flow("FF-0941", "admin_jobs", "overflow_action",
     "위험·확인이 붙은 액션(취소)은 상세 하단 넘침 메뉴에서 실행한다",
     _job_action("취소", "취소"), shell=ADMIN, server=False)


def _job_links(what: str, href_part: str):
    def _act(r, ctx):
        link = r.page.locator('#main-content a[href*="%s"]' % href_part)
        if not link.count():
            return {"ui_action": "상세에서 %s 링크를 찾는다" % what,
                    "notes": ["이 작업에는 %s 가 연결돼 있지 않다 — 링크가 없는 것이 맞다" % what],
                    "rendered": "본문 «%s»" % r.main_text(110)}
        label = " ".join((link.first.inner_text() or "").split())[:40]
        link.first.click()
        r.settle(1500)
        return {"ui_action": "«%s» 를 누른다" % label,
                "url_state": "→ %s" % r.hash_of(),
                "rendered": "본문 «%s»" % r.main_text(90)}
    return _act


flow("FF-0942", "admin_jobs", "navigation",
     "상세의 연결된 스케줄·문서 생성 링크로 그 화면의 상세를 곧바로 연다",
     _job_links("연결된 스케줄", "/schedules"), shell=ADMIN, server=False)
flow("FF-0943", "admin_jobs", "navigation", "‘감사 로그에서 보기’로 이 작업의 감사 기록으로 이동한다",
     _job_links("감사 로그", "/audit"), shell=ADMIN, server=False)


def _jobs_deep_link(r, ctx):
    r.goto("/jobs?status=failed", shell=ADMIN)
    rows = r.rows()
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(1600)
    return {"ui_action": "?status=failed 로 들어가 새로고침한다",
            "url_state": "/jobs?status=failed → %s" % r.hash_of(),
            "observed": {"rows": {"before": rows, "after": r.rows()}},
            "rendered": "표 %d행 → %d행" % (rows, r.rows()),
            "failed": None if "status" in r.hash_of()
                      else "새로고침 뒤 조건이 사라졌다: %s" % r.hash_of()}


flow("FF-0944", "admin_jobs", "deep_link",
     "?job_id= 로 상세를, ?schedule_run_id=·?generation_id= 로 필터가 걸린 목록을 연다",
     _jobs_deep_link, shell=ADMIN, api="/api/admin/jobs")

flow("FF-0945", "admin_jobs", "refresh",
     "조회 실패 시 ‘다시 시도’로 목록을 다시 받는다(진행 중 작업이 있으면 4초마다 자동 갱신)",
     retry_from_error("/api/admin/jobs", "작업 큐"), route="/jobs", shell=ADMIN,
     api="/api/admin/jobs")

flow("FF-0946", "admin_jobs", "permission_state",
     "라우트 역할 가드 + 재시도·취소의 운영 역할 게이트",
     blocked_route("/jobs", role="user", shell=ADMIN), route="/jobs", shell=ADMIN,
     server=False)


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
#
# 조건 하나를 «맞는다» 고 선언한 화면은 조건이 함께 지켜야 하는 다섯을 함께 보여야 한다.
# 이 화면은 쪽이 있는 서버 목록이라 다섯이 전부 실질적이다.
flow("FF-1410", "admin_jobs", "filter", "복합 — 상태 × 유형",
     compound(("상태", "실패"), ("유형", "채팅 메시지")),
     route="/jobs", shell=ADMIN, server=False)
flow("FF-1411", "admin_jobs", "filter", "조건을 바꾸면 쪽이 1로 초기화된다",
     page_reset("상태", "완료"), route="/jobs", shell=ADMIN, server=False)
flow("FF-1412", "admin_jobs", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(JOB_RUN_ID, "abc", "s18-run-id"), route="/jobs", shell=ADMIN, server=False)
flow("FF-1413", "admin_jobs", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/jobs?status=succeeded", "/jobs?status=failed", shell=ADMIN),
     shell=ADMIN, api="/api/admin/jobs")
flow("FF-1414", "admin_jobs", "filter",
     "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/jobs?job_type=chat_message", "/jobs?job_type=mail_send", shell=ADMIN),
     shell=ADMIN, api="/api/admin/jobs")
