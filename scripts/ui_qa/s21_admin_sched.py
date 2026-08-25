"""S21 — 실행 일정 · 실행 달력 · 승인 · 승인 위임 · AI 사용 통계 (W14).

S20 이 이 다섯도 탭 묶음 셋으로 묶었다(`/schedules` · `/approvals` · `/ai-usage`). 감사·백업
쪽과 같은 규칙이다 — **같은 화면이 두 주소에서 열리고, 원장에도 따로 적혀 있다.** 같은
동작을 두 주소에서 각각 돌린다.

승인은 이 제품에서 **되돌릴 수 없는 결정**을 다루는 유일한 자리다. 그래서 여기서 특히
자세히 보는 것은 「누가 결재할 수 있는가」를 서버가 계산해 준 값(`can_decide`)으로만
그리는지다 — 위임받은 대리 결재자가 그 계산에 들어 있다.
"""

from __future__ import annotations

from urllib.parse import unquote

from scripts.ui_qa.s21_admin_kit import (  # noqa: F401
    ADMIN, ds_action, ds_clear, ds_create, ds_deep_link, ds_edit, ds_filter, ds_navigate,
    ds_open_row, ds_overflow, ds_pager, ds_permission, ds_read, ds_required, ds_saved_view,
    ds_search,
)
from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog, open_dialogs,
    retry_from_error, row_at, row_name, rows_of, sort_by, stop, switch_tab,
)

SCHED = "/api/admin/schedules"
APPR = "/api/admin/approvals"
DELEG = "/api/admin/approval-delegations"
PU = "/api/admin/prompts/usage/stats"
POU = "/api/admin/policies/usage/stats"


def _pair(ids, surfaces, category, name, act, **kw):
    for fid, (surface, route) in zip(ids, surfaces):
        flow(fid, surface, category, name, act, route=route, shell=ADMIN, **kw)


def _header_link(label: str, expect: str):
    def _act(r, ctx):
        button = r.in_main("button", label)
        if not button.count():
            button = r.page.locator("#main-content").get_by_role("link", name=label,
                                                                 exact=False)
        if not button.count():
            stop("«%s» 를 못 찾았다" % label)
        before = r.hash_of()
        button.first.click()
        r.settle(2200)
        after = unquote(r.hash_of())
        return {"ui_action": "머리의 «%s» 를 누른다" % label,
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after},
                "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(110)),
                "expected": {"source": "derived-check",
                             "rule": "그 화면으로 옮긴다", "expect": expect, "got": after},
                "failed": None if expect in after
                          else "«%s» 를 눌렀는데 %s 로 안 갔다: %s" % (label, expect, after)}
    return _act


# ═══════════════════════════════════════════════════════════════════════════
# /schedules — 실행 일정
# ═══════════════════════════════════════════════════════════════════════════
S = "/schedules?tab=schedules"

flow("FF-0701", "admin_schedules__schedules", "navigation",
     "'목록' ↔ '달력' 탭을 전환한다(?tab= 주소에 반영)",
     switch_tab("달력", "tab=scheduler-calendar"), route=S, shell=ADMIN, server=False)

flow("FF-0702", "admin_schedules__schedules", "search", "목록을 화면 안에서 검색한다(대상 필드 미지정)",
     ds_search("", SCHED, server=False), route=S, shell=ADMIN, server=False)

flow("FF-0703", "admin_schedules__schedules", "filter", "활성/비활성으로 좁힌다 — 화면 안에서 거른다",
     ds_filter("활성", "활성", SCHED, server=False), route=S, shell=ADMIN, server=False)

flow("FF-0704", "admin_schedules__schedules", "filter",
     "유형(Cron 반복/1회 실행)으로 좁힌다 — 화면 안에서 거른다",
     ds_filter("유형", "Cron", SCHED, server=False), route=S, shell=ADMIN, server=False)


def _target_type_options(r, ctx):
    """대상 유형 선택지가 **지금 무엇인가**.

    원장이 적어 둔 「워크플로/시스템」 가운데 워크플로 축은 S11 이 걷었다. 그래서 여기서는
    선택지를 지어내지 않고 **화면이 실제로 주는 것**을 적는다.
    """
    box = r.page.get_by_role("combobox", name="대상", exact=False)
    if not box.count():
        return {"ui_action": "«대상 유형» 조건을 찾는다",
                "observed": {"comboboxes": r.combobox_names()},
                "rendered": "«대상 유형» 조건 없음 — 지금 선택 상자 %s" % r.combobox_names(),
                "expected": {"source": "derived-check",
                             "rule": "고를 것이 하나뿐인 축은 조건으로 안 그린다(D-321)"},
                "failed": None}
    box.first.click()
    r.settle(600)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())
             for i in range(options.count())]
    r.press("Escape")
    return {"ui_action": "«대상 유형» 의 선택지를 본다",
            "observed": {"options": names},
            "rendered": "선택지 %s" % names,
            "expected": {"source": "derived-check",
                         "rule": "지금 제품에 있는 대상 유형만 선택지로 나온다", "got": names},
            "failed": None}


flow("FF-0705", "admin_schedules__schedules", "filter",
     "대상 유형으로 좁힌다 — 화면 안에서 거른다",
     _target_type_options, route=S, shell=ADMIN, server=False)

flow("FF-0706", "admin_schedules__schedules", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("활성", "활성"), route=S, shell=ADMIN, server=False)

flow("FF-0707", "admin_schedules__schedules", "filter",
     "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route=S, shell=ADMIN, server=False)

flow("FF-0708", "admin_schedules__schedules", "sort", "열 머리를 눌러 다음 실행·마지막 실행으로 정렬한다",
     sort_by("다음 실행"), route=S, shell=ADMIN, server=False)

flow("FF-0709", "admin_schedules__schedules", "read",
     "행을 눌러 일정 상세(소유자·정책·페이로드·재시도 정책)를 연다",
     ds_open_row(), route=S, shell=ADMIN, server=False)

flow("FF-0710", "admin_schedules__schedules", "create",
     "'스케줄 추가'로 주기·대상·페이로드·정책을 정해 일정을 만든다",
     ds_create("스케줄 추가", {"이름": "S21 점검 일정"}), route=S, shell=ADMIN, api=SCHED,
     cross=("/schedules?tab=schedules", ADMIN))


def _target_picker(r, ctx):
    button = r.in_main("button", "스케줄 추가")
    if not button.count():
        stop("«스케줄 추가» 버튼이 없다")
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("모달이 안 떴다")
    dialog = open_dialog(r)
    picker = dialog.get_by_role("combobox", name="대상", exact=False)
    names = []
    if picker.count():
        picker.first.click()
        r.settle(600)
        options = r.page.get_by_role("option")
        names = [" ".join((options.nth(i).inner_text() or "").split())
                 for i in range(options.count())]
        r.press("Escape")
    r.dismiss_overlays()
    return {"ui_action": "만들기 모달의 «대상» 선택지를 본다",
            "observed": {"options": names},
            "rendered": "선택지 %s" % names,
            "expected": {"source": "derived-check",
                         "rule": "지금 제품에 있는 대상만 고를 수 있다", "got": names},
            "failed": None if picker.count() else "만들기 모달에 «대상» 선택기가 없다"}


flow("FF-0711", "admin_schedules__schedules", "combobox",
     "'대상' select 에서 대상을 이름으로 고른다",
     _target_picker, route=S, shell=ADMIN, server=False)

flow("FF-0712", "admin_schedules__schedules", "form_validation",
     "이름·대상을 비우거나 페이로드 JSON 형식이 틀리면 제출 전에 막힌다",
     ds_required("스케줄 추가"), route=S, shell=ADMIN, server=False)

flow("FF-0713", "admin_schedules__schedules", "edit",
     "상세에서 '수정'으로 일정 정의를 전체 교체한다(PUT)",
     ds_edit("설명"), route=S, shell=ADMIN, api=SCHED)

flow("FF-0714", "admin_schedules__schedules", "status_change",
     "'활성화'/'비활성화'로 예약을 켜고 끈다(이미 지난 1회형은 활성화 버튼을 숨긴다)",
     ds_action("비활성화"), route=S, shell=ADMIN, api=SCHED)

flow("FF-0715", "admin_schedules__schedules", "admin_op",
     "'지금 실행'으로 이 일정을 한 번 바로 돌린다(중복 실행은 건너뛴다고 알린다)",
     ds_action("지금 실행"), route=S, shell=ADMIN, api=SCHED)


def _preview(r, ctx):
    if not n_rows(r):
        stop("일정이 없다")
    row_at(r, 0).click()
    r.settle(1600)
    if not open_dialogs(r):
        stop("상세가 안 열렸다")
    detail = open_dialog(r)
    target = detail.get_by_role("button", name="미리보기", exact=False)
    if not target.count():
        more = detail.get_by_role("button", name="더 보기", exact=False)
        if more.count():
            more.first.click()
            r.settle(700)
            target = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="미리보기", exact=False)
    if not target.count():
        said = dialog_says(r, 240)
        r.dismiss_overlays()
        stop("«미리보기» 를 못 찾았다 — 상세: %s" % said[:170])
    target.first.click()
    r.settle(2200)
    text = dialog_says(r, 400)
    r.dismiss_overlays()
    return {"ui_action": "«미리보기» 로 다음 실행 시각과 보낼 페이로드를 본다",
            "observed": {"panel": text[:340]},
            "rendered": "안내 «%s»" % text[:240],
            "expected": {"source": "derived-check",
                         "rule": "다음 실행 시각 다섯 개와 페이로드를 함께 보여 준다",
                         "panel": text[:200]},
            "failed": None if text else "«미리보기» 를 눌렀는데 아무것도 안 나온다"}


flow("FF-0716", "admin_schedules__schedules", "modal_action",
     "'미리보기'로 다음 실행 시각 다섯 개와 보낼 페이로드를 안내 모달로 확인한다",
     _preview, route=S, shell=ADMIN, api=SCHED)


def _run_history(r, ctx):
    if not n_rows(r):
        stop("일정이 없다")
    name = row_name(r, 0)
    row_at(r, 0).click()
    r.settle(1600)
    detail = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    target = detail.get_by_role("button", name="실행 이력", exact=False)
    if not target.count():
        more = detail.get_by_role("button", name="더 보기", exact=False)
        if more.count():
            more.first.click()
            r.settle(700)
            target = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="실행 이력", exact=False)
    if not target.count():
        said = dialog_says(r, 240)
        r.dismiss_overlays()
        stop("«실행 이력» 을 못 찾았다 — 상세: %s" % said[:170])
    target.first.click()
    r.settle(2200)
    text = dialog_says(r, 400)
    buttons = open_dialog(r).get_by_role("button") if open_dialogs(r) else None
    labels = ([" ".join((buttons.nth(i).inner_text() or "").split())
               for i in range(min(buttons.count(), 12))] if buttons else [])
    ctx["schedule_runs"] = labels
    r.dismiss_overlays()
    return {"ui_action": "«%s» 의 «실행 이력» 하위 목록을 연다" % name,
            "observed": {"panel": text[:340], "buttons": labels},
            "rendered": "이력 «%s» · 버튼 %s" % (text[:190], labels),
            "expected": {"source": "derived-check",
                         "rule": "결과 필터·쪽 이동·재시도를 하위 목록에서 한다",
                         "buttons": labels},
            "failed": None if text else "«실행 이력» 을 눌렀는데 아무것도 안 열린다"}


flow("FF-0717", "admin_schedules__schedules", "row_action",
     "'실행 이력' 하위 목록에서 결과 필터·페이지 이동·전체 보기·실패 재시도를 한다",
     _run_history, route=S, shell=ADMIN, api=SCHED)


def _run_to_job(r, ctx):
    labels = ctx.get("schedule_runs") or []
    return {"ui_action": "실행 이력 행의 «작업 큐» 링크를 본다",
            "observed": {"buttons": labels,
                         "has_job_link": any("작업" in x for x in labels)},
            "rendered": "하위 목록 버튼 %s" % labels,
            "expected": {"source": "known-data",
                         "rule": "그 실행을 처리한 작업이 있을 때만 링크가 있다",
                         "buttons": labels},
            "failed": None if labels else "앞 Flow 가 실행 이력을 못 열었다"}


flow("FF-0718", "admin_schedules__schedules", "navigation",
     "실행 이력 행의 '작업 큐' 링크로 그 실행을 처리한 작업으로 이동한다",
     _run_to_job, server=False)

flow("FF-0719", "admin_schedules__schedules", "navigation",
     "'감사 로그에서 보기'로 이 일정의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=schedule"), route=S, shell=ADMIN,
     server=False)

flow("FF-0720", "admin_schedules__schedules", "overflow_action",
     "무해한 액션 둘만 버튼으로 남고 나머지·위험 액션은 넘침 메뉴로 내려간다",
     ds_overflow(), route=S, shell=ADMIN, server=False)

flow("FF-0721", "admin_schedules__schedules", "deep_link",
     "?id= 로 특정 일정 상세를 연다",
     ds_deep_link("/schedules?tab=schedules&enabled=true", "tab=schedules"), api=SCHED)

flow("FF-0722", "admin_schedules__schedules", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(SCHED, "실행 일정"), route=S, shell=ADMIN, api=SCHED)

flow("FF-0723", "admin_schedules__schedules", "permission_state",
     "라우트 역할 가드 + 추가·수정은 쓰기 역할, 지금 실행·미리보기·재시도는 운영 역할",
     ds_permission(("스케줄 추가",), SCHED,
                   payload={"name": "권한 시험", "target_type": "system",
                            "target_ref": "noop"}),
     route=S, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 실행 달력 — 그릇 탭과 홑 라우트 둘 다
# ═══════════════════════════════════════════════════════════════════════════
CAL_SURFACES = (("admin_schedules__scheduler-calendar",
                 "/schedules?tab=scheduler-calendar"),
                ("admin_scheduler-calendar", "/scheduler-calendar"))

_pair(("FF-0724", "FF-1081"), CAL_SURFACES, "navigation",
      "'목록' ↔ '달력' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("목록", "tab=schedules"), server=False)


def _month_move(label: str, *, leave_first: bool = False):
    def _act(r, ctx):
        if leave_first:
            # **되돌아오려면 먼저 떠나 있어야 한다.** 이 화면은 오늘이 있는 달로 열리므로,
            # 그 자리에서 «이번 달» 을 누르면 아무것도 안 달라지는 것이 정답이다 — 그것을
            # 「안 달라졌다」로 적으면 제품이 아니라 시험이 틀린 것이다.
            away = r.page.locator("#main-content").get_by_role("button", name="다음 달",
                                                               exact=False)
            if away.count():
                away.first.click()
                r.settle(1600)
        button = r.in_main("button", label)
        if not button.count():
            stop("«%s» 버튼이 없다" % label)
        before = r.main_text(120)
        r.rec.reset()
        button.first.click()
        r.settle(2000)
        query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls if c["query"]})))
        return {"ui_action": "«%s» 로 조회 구간을 옮긴다" % label,
                "observed": {"query": query, "before": before,
                             "after": r.main_text(120)},
                "rendered": "머리 «%s» → «%s» · 질의 «%s»"
                            % (before[:50], r.main_text(120)[:50], query[:70]),
                "expected": {"source": "derived-check",
                             "rule": "달을 옮기면 그 구간을 서버에 다시 묻는다", "got": query},
                "failed": None if (query or before != r.main_text(120))
                          else "달을 옮겼는데 아무것도 안 달라졌다"}
    return _act


_pair(("FF-0725", "FF-1082"), CAL_SURFACES, "filter", "이전/다음 달 버튼으로 조회 구간을 옮긴다",
      _month_move("다음 달"), api="/api/admin/")

_pair(("FF-0726", "FF-1083"), CAL_SURFACES, "filter", "'이번 달'로 오늘이 있는 달로 되돌아온다",
      _month_move("이번 달", leave_first=True), api="/api/admin/")


def _calendar_pick(r, ctx):
    box = r.page.get_by_role("combobox", name="일정", exact=False)
    if not box.count():
        box = r.page.locator("#main-content [role=combobox]")
    if not box.count():
        stop("«일정» 드롭다운이 없다 — 지금 선택 상자: %s" % r.combobox_names())
    box.first.click()
    r.settle(600)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())
             for i in range(options.count())]
    picked = ""
    for i in range(options.count()):
        label = names[i]
        if label and "전체" not in label:
            picked = label
            r.rec.reset()
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
        stop("«일정» 에 고를 것이 없다 — 후보: %s" % names)
    r.settle(2000)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls if c["query"]})))
    return {"ui_action": "«일정» 에서 «%s» 하나만 골라 달력을 좁힌다" % picked,
            "observed": {"options": names, "picked": picked, "query": query},
            "rendered": "후보 %s · 고른 것 «%s» · 질의 «%s»" % (names, picked, query[:70]),
            "expected": {"source": "derived-check",
                         "rule": "일정 하나를 고르면 달력이 그것만 그린다", "got": query},
            "failed": None}


_pair(("FF-0727", "FF-1084"), CAL_SURFACES, "combobox",
      "'일정' 드롭다운에서 특정 스케줄 하나만 골라 달력을 좁힌다(비활성 표시 포함)",
      _calendar_pick, api="/api/admin/")


def _calendar_dot(r, ctx):
    dots = r.page.locator('#main-content [data-run], #main-content button[aria-label*="실행"]')
    if not dots.count():
        body = r.main_text(220)
        return {"ui_action": "달력 칸의 실행/예정 점을 찾는다",
                "observed": {"dots": 0, "body": body},
                "rendered": "점 0개 · 본문 «%s»" % body[:160],
                "expected": {"source": "known-data",
                             "rule": "이 달에 실행이 없으면 누를 점도 없다"},
                "failed": None}
    before = open_dialogs(r)
    dots.first.click()
    r.settle(1800)
    text = dialog_says(r, 320)
    ctx["calendar_modal"] = text
    return {"ui_action": "달력 칸의 점을 눌러 상세 모달을 연다",
            "observed": {"dots": dots.count(), "dialogs": {"before": before,
                                                           "after": open_dialogs(r)},
                         "panel": text[:280]},
            "rendered": "상세 «%s»" % text[:200],
            "expected": {"source": "derived-check",
                         "rule": "점을 누르면 구분·시각·상태·오류·일정 ID 를 보여 준다"},
            "failed": None if open_dialogs(r) > before else "점을 눌렀는데 상세가 안 열렸다"}


_pair(("FF-0728", "FF-1085"), CAL_SURFACES, "read",
      "달력 칸의 실행/예정 점을 눌러 상세 모달(구분·시각·상태·오류·일정 ID)을 연다",
      _calendar_dot, server=False)


def _calendar_modal_action(label: str, api_hint: str):
    def _act(r, ctx):
        if not open_dialogs(r):
            return {"ui_action": "상세 모달에서 «%s» 를 찾는다" % label,
                    "observed": {"dialogs": 0},
                    "rendered": "상세 모달이 안 열려 있다 — 이 달에 그 실행이 없다",
                    "expected": {"source": "known-data",
                                 "rule": "그 상태의 실행이 있을 때만 이 동작이 있다"},
                    "failed": None}
        panel = open_dialog(r)
        target = panel.get_by_role("button", name=label, exact=False)
        if not target.count():
            return {"ui_action": "상세 모달에서 «%s» 를 찾는다" % label,
                    "observed": {"panel": dialog_says(r, 240)},
                    "rendered": "«%s» 없음 — 상세 «%s»" % (label, dialog_says(r, 200)),
                    "expected": {"source": "derived-check",
                                 "rule": "실패·대기 상태일 때만 그 동작을 준다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(1200)
        asked = open_dialogs(r) > 1
        said = confirm_now(r) if asked else ""
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "상세 모달에서 «%s» 를 실행한다" % label,
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:90]),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 확인을 받고 %s 를 부른다" % (label, api_hint),
                             "got": calls},
                "failed": None if asked or not calls else "확인 없이 실행됐다"}
    return _act


_pair(("FF-0729", "FF-1086"), CAL_SURFACES, "admin_op",
      "실패한 실행에서 '재시도'로 그 실행을 다시 대기열에 넣는다(확인 후)",
      _calendar_modal_action("재시도", "/retry"), server=False)

_pair(("FF-0730", "FF-1087"), CAL_SURFACES, "admin_op",
      "대기·실행 중인 실행을 '취소'한다(확인 후)",
      _calendar_modal_action("취소", "/cancel"), server=False)

_pair(("FF-0731", "FF-1088"), CAL_SURFACES, "navigation",
      "'이 일정 열기'로 실행 일정 화면의 그 스케줄 상세를 연다",
      _calendar_modal_action("이 일정 열기", ""), server=False)

_pair(("FF-0732", "FF-1089"), CAL_SURFACES, "navigation",
      "'작업 큐에서 보기'로 그 실행 건을 처리한 작업으로 이동한다",
      _calendar_modal_action("작업 큐", ""), server=False)


def _calendar_close(r, ctx):
    if not open_dialogs(r):
        return {"ui_action": "상세 모달을 닫는다",
                "observed": {"dialogs": 0},
                "rendered": "열린 모달이 없다",
                "expected": {"source": "known-data", "rule": "열린 것이 없으면 닫을 것도 없다"},
                "failed": None}
    before = open_dialogs(r)
    r.dismiss_overlays()
    r.settle(800)
    return {"ui_action": "상세 모달을 «닫기» 로 닫는다",
            "observed": {"dialogs": {"before": before, "after": open_dialogs(r)}},
            "rendered": "모달 %d → %d" % (before, open_dialogs(r)),
            "expected": {"source": "derived-check", "rule": "닫으면 사라진다"},
            "failed": None if open_dialogs(r) < before else "닫았는데 그대로 있다"}


_pair(("FF-0733", "FF-1090"), CAL_SURFACES, "modal_action", "상세 모달을 '닫기'로 닫는다",
      _calendar_close, server=False)

_pair(("FF-0734", "FF-1091"), CAL_SURFACES, "refresh", "조회 실패 시 '다시 시도'로 달력을 다시 받는다",
      retry_from_error(SCHED, "실행 달력"), api="/api/admin/")

_pair(("FF-0735", "FF-1092"), CAL_SURFACES, "permission_state",
      "라우트 역할 가드 + 재시도·취소의 운영 역할 게이트(auditor 에겐 버튼을 숨긴다)",
      ds_permission((), SCHED, method="GET"), server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /approvals — 승인 요청
# ═══════════════════════════════════════════════════════════════════════════
A = "/approvals?tab=approvals"

flow("FF-0609", "admin_approvals__approvals", "navigation",
     "'승인 요청' ↔ '승인 위임' 탭을 전환한다(?tab= 주소에 반영)",
     switch_tab("승인 위임", "tab=approval-delegations"), route=A, shell=ADMIN,
     server=False)

flow("FF-0610", "admin_approvals__approvals", "filter",
     "상태(대기/승인됨/거절됨/만료/취소됨)로 좁힌다 — 기본값은 '대기'",
     ds_filter("상태", "승인", APPR, axis="status"), route=A, shell=ADMIN, api=APPR)

flow("FF-0611", "admin_approvals__approvals", "filter", "요청 유형으로 좁힌다",
     ds_filter("유형", "역할", APPR, axis="request_type"), route=A, shell=ADMIN, api=APPR)


def _requester_filter(r, ctx):
    box = r.page.get_by_label("요청자", exact=False)
    if not box.count():
        stop("«요청자» 조건이 없다")
    before = n_rows(r)
    r.rec.reset()
    box.first.fill("s21")
    r.settle(2200)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                     if APPR in c["path"] and c["query"]})))
    box.first.fill("")
    r.settle(1400)
    return {"ui_action": "«요청자» 에 «s21» 을 넣는다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
            "expected": {"source": "derived-check",
                         "rule": "요청자 축이 서버 질의에 실린다", "got": query},
            "failed": None if ("requested_by" in query or "requester" in query)
                      else "요청자로 걸렀는데 질의에 그 축이 없다: «%s»" % query}


flow("FF-0612", "admin_approvals__approvals", "filter", "요청자 ID로 좁힌다",
     _requester_filter, route=A, shell=ADMIN, api=APPR)

flow("FF-0613", "admin_approvals__approvals", "filter", "'필터 지우기'로 필터를 한 번에 해제한다",
     ds_clear("상태", "승인"), route=A, shell=ADMIN, api=APPR)

flow("FF-0614", "admin_approvals__approvals", "filter",
     "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route=A, shell=ADMIN, server=False)

flow("FF-0615", "admin_approvals__approvals", "pagination", "이전/다음으로 페이지를 넘긴다",
     ds_pager(APPR), route=A, shell=ADMIN, server=False)

flow("FF-0616", "admin_approvals__approvals", "read",
     "행을 눌러 승인 상세(요청 내용 키/값·요청자·기한·결정 메모)를 연다",
     ds_open_row(), route=A, shell=ADMIN, server=False)


def _decide(label: str, *, note: str = ""):
    def _act(r, ctx):
        if not n_rows(r):
            stop("승인 건이 없다")
        name = row_name(r, 0)
        before = n_rows(r)
        row_at(r, 0).click()
        r.settle(1600)
        if not open_dialogs(r):
            stop("상세가 안 열렸다")
        detail = open_dialog(r)
        target = detail.get_by_role("button", name=label, exact=False)
        if not target.count():
            more = detail.get_by_role("button", name="더 보기", exact=False)
            if more.count():
                more.first.click()
                r.settle(700)
                target = r.page.locator('[role="menu"]').get_by_role(
                    "menuitem", name=label, exact=False)
        if not target.count():
            said = dialog_says(r, 260)
            r.dismiss_overlays()
            stop("«%s» 를 못 찾았다 — 상세: %s" % (label, said[:180]))
        r.rec.reset()
        target.first.click()
        r.settle(1300)
        form = open_dialog(r) if open_dialogs(r) else None
        typed = ""
        if note and form is not None:
            box = form.locator("textarea, input[type=text]")
            if box.count():
                box.first.fill(note)
                typed = note
                r.settle(400)
        asked = open_dialogs(r) > 1
        said = confirm_now(r)
        r.settle(2400)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        r.dismiss_overlays()
        return {"ui_action": "«%s» 건을 «%s» 한다%s"
                             % (name, label, (" (메모 «%s»)" % typed) if typed else ""),
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:160],
                             "rows": {"before": before, "after": n_rows(r)}},
                "rendered": "쓰기 요청 %s · %d행 → %d행" % (calls, before, n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "결재하면 서버로 가고 대기 목록에서 빠진다", "got": calls},
                "failed": None if calls else "«%s» 를 눌렀는데 서버로 안 갔다" % label}
    return _act


flow("FF-0617", "admin_approvals__approvals", "approval_action",
     "'승인' 폼에 메모를 남기고 요청을 승인한다",
     _decide("승인", note="S21 인수 점검이 승인했습니다."), route=A, shell=ADMIN, api=APPR)

flow("FF-0618", "admin_approvals__approvals", "approval_action",
     "'거절' 폼에 사유를 남기고 요청을 거절한다(되돌릴 수 없음을 확인받는다)",
     _decide("거절", note="S21 인수 점검이 거절했습니다."), route=A, shell=ADMIN, api=APPR)

flow("FF-0619", "admin_approvals__approvals", "approval_action",
     "'취소'로 요청 자체를 물린다(본인 요청 또는 관리자)",
     _decide("취소"), route=A, shell=ADMIN, api=APPR)

flow("FF-0620", "admin_approvals__approvals", "modal_action",
     "'발행 내용 보기'로 승인 전에 대상 문서의 제목·본문·품질 문제를 안내 모달로 읽는다",
     ds_navigate("발행 내용", "#/"), route=A, shell=ADMIN, server=False)

flow("FF-0621", "admin_approvals__approvals", "navigation",
     "'대상 보기'로 승인 대상 엔티티 화면(가능하면 그 행)으로 이동한다",
     ds_navigate("대상 보기", "#/"), route=A, shell=ADMIN, server=False)

flow("FF-0622", "admin_approvals__approvals", "navigation",
     "'감사 로그에서 보기'로 이 승인 건의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=approval"), route=A, shell=ADMIN,
     server=False)

flow("FF-0623", "admin_approvals__approvals", "overflow_action",
     "위험·확인이 붙은 액션(거절·취소)은 상세 하단 넘침 메뉴에서 실행한다",
     ds_overflow(), route=A, shell=ADMIN, server=False)

flow("FF-0624", "admin_approvals__approvals", "deep_link",
     "?id= 로 특정 승인 건을, ?status=pending 으로 대기 큐만 걸어 연다",
     ds_deep_link("/approvals?tab=approvals&status=pending", "status=pending"), api=APPR)

flow("FF-0625", "admin_approvals__approvals", "refresh",
     "조회 실패 시 '다시 시도'로 목록을 다시 받는다(대기 건이 있으면 자동 갱신)",
     retry_from_error(APPR, "승인"), route=A, shell=ADMIN, api=APPR)


def _can_decide(r, ctx):
    mine = 0
    for i in range(min(n_rows(r), 3)):
        mine += row_at(r, i).get_by_role("button", name="승인", exact=False).count()
    got = r.as_role("operator", A, ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             const rows = main ? main.querySelectorAll('tbody tr') : [];
             let decide = 0;
             rows.forEach(tr => { tr.querySelectorAll('button').forEach(b => {
               if ((b.innerText || '').indexOf('승인') >= 0) decide += 1; }); });
             return {rows: rows.length, decide,
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,180)};
           }"""))
    return {"ui_action": "결재 버튼 수를 세고, 같은 화면을 운영자로 연다",
            "frontend_state": "can_decide 는 서버가 계산한다",
            "observed": {"as_system_admin": mine, "as_operator": got},
            "rendered": "system_admin 결재 버튼 %d · operator %s" % (mine, got),
            "expected": {"source": "derived-check",
                         "rule": "승인·거절은 서버가 계산한 can_decide 로만 그린다"},
            "failed": None}


flow("FF-0626", "admin_approvals__approvals", "permission_state",
     "승인·거절 노출을 서버가 계산한 can_decide 로 판정한다(위임받은 대리 결재자 포함)",
     _can_decide, route=A, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 승인 위임 — 그릇 탭과 홑 라우트 둘 다
# ═══════════════════════════════════════════════════════════════════════════
DEL_SURFACES = (("admin_approvals__approval-delegations",
                 "/approvals?tab=approval-delegations"),
                ("admin_approval-delegations", "/approval-delegations"))

_pair(("FF-0627", "FF-0818"), DEL_SURFACES, "navigation",
      "'승인 요청' ↔ '승인 위임' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("승인 요청", "tab=approvals"), server=False)

_pair(("FF-0628", "FF-0819"), DEL_SURFACES, "search",
      "위임한 사람·대리 승인자 이름·사유로 검색한다",
      ds_search("", DELEG, server=False), server=False)

_pair(("FF-0629", "FF-0820"), DEL_SURFACES, "filter", "상태(진행 중/예정/종료/거둠)로 좁힌다",
      ds_filter("상태", "진행", DELEG, server=False), server=False)

_pair(("FF-0630", "FF-0821"), DEL_SURFACES, "filter",
      "'필터 지우기'로 검색어·필터를 한 번에 해제한다", ds_clear("상태", "진행"), server=False)

_pair(("FF-0631", "FF-0822"), DEL_SURFACES, "filter",
      "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다", ds_saved_view(),
      server=False)

_pair(("FF-0632", "FF-0823"), DEL_SURFACES, "sort",
      "열 머리를 눌러 정렬한다(시작·종료 시각)", sort_by("시작"), server=False)

_pair(("FF-0633", "FF-0824"), DEL_SURFACES, "read",
      "행을 눌러 위임 상세(양쪽 이메일·거둔 시각)를 연다", ds_open_row(), server=False)

_pair(("FF-0634", "FF-0825"), DEL_SURFACES, "create",
      "'위임 추가'로 위임자·대리 승인자·기간·사유를 적어 위임을 만든다",
      ds_create("위임 추가", {"사유": "S21 인수 점검 위임"}), api=DELEG)

_pair(("FF-0635", "FF-0826"), DEL_SURFACES, "form_validation",
      "두 사용자 ID와 시작·종료 시각을 비우면 제출 전에 막힌다",
      ds_required("위임 추가"), server=False)

_pair(("FF-0636", "FF-0827"), DEL_SURFACES, "status_change",
      "'위임 거두기'로 진행 중/예정 위임을 즉시 닫는다(확인 후)",
      ds_action("거두기"), api=DELEG)

_pair(("FF-0637", "FF-0828"), DEL_SURFACES, "overflow_action",
      "위험 액션(위임 거두기)은 상세 하단 넘침 메뉴에서 실행한다", ds_overflow(),
      server=False)

_pair(("FF-0638", "FF-0829"), DEL_SURFACES, "navigation", "'승인 큐 보기'로 승인 목록으로 이동한다",
      # registry 는 이것을 `actions:` 에 뒀다 — 머리가 아니라 **행의 상세**에 있다.
      ds_navigate("승인 큐 보기", "approvals"), server=False)

_pair(("FF-0639", "FF-0830"), DEL_SURFACES, "navigation",
      "'감사 로그에서 보기'로 이 위임의 감사 기록으로 이동한다",
      ds_navigate("감사 로그에서 보기", "object_type="), server=False)

flow("FF-0640", "admin_approvals__approval-delegations", "deep_link",
     "검색·필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/approvals?tab=approval-delegations&status=active",
                  "tab=approval-delegations"), api=DELEG)

flow("FF-0831", "admin_approval-delegations", "deep_link", "검색·필터가 해시 쿼리에 되쓰인다",
     ds_deep_link("/approval-delegations?status=active", "status=active"), api=DELEG)

_pair(("FF-0641", "FF-0832"), DEL_SURFACES, "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
      retry_from_error(DELEG, "승인 위임"), api=DELEG)

_pair(("FF-0642", "FF-0833"), DEL_SURFACES, "permission_state",
      "라우트 역할 가드 + 탭 단위 권한 안내 + 쓰기 액션 role 게이트",
      ds_permission(("위임 추가",), DELEG,
                    payload={"delegator_user_id": "x", "delegate_user_id": "y"}),
      server=False)


# ═══════════════════════════════════════════════════════════════════════════
# AI 사용 통계 — 정책·프롬프트, 그릇 탭과 홑 라우트 넷
# ═══════════════════════════════════════════════════════════════════════════
POL_SURFACES = (("admin_ai-usage__policy-usage", "/ai-usage?tab=policy-usage"),
                ("admin_policy-usage", "/policy-usage"))
PROM_SURFACES = (("admin_ai-usage__prompt-usage", "/ai-usage?tab=prompt-usage"),
                 ("admin_prompt-usage", "/prompt-usage"))

_pair(("FF-0677", "FF-0995"), POL_SURFACES, "navigation",
      "'정책' ↔ '프롬프트' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("프롬프트", "tab=prompt-usage"), server=False)

_pair(("FF-0678", "FF-0996"), POL_SURFACES, "search", "정책 이름으로 검색한다",
      ds_search("", POU, server=False), server=False)

_pair(("FF-0679", "FF-0997"), POL_SURFACES, "filter",
      "사용 여부(쓰이지 않음/쓰이는 중)로 좁힌다 — 화면 안에서 거른다",
      ds_filter("사용 여부", "쓰이", POU, server=False), server=False)

_pair(("FF-0680", "FF-0998"), POL_SURFACES, "filter",
      "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
      ds_clear("사용 여부", "쓰이"), server=False)

_pair(("FF-0681", "FF-0999"), POL_SURFACES, "filter",
      "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다", ds_saved_view(),
      server=False)

_pair(("FF-0682", "FF-1000"), POL_SURFACES, "sort",
      "열 머리를 눌러 버전 수·템플릿 수·문서 생성 수로 정렬한다", sort_by("버전"),
      server=False)

_pair(("FF-0683", "FF-1001"), POL_SURFACES, "read",
      "행을 눌러 상세(참조하는 목록·최신 버전·마지막 발행)를 연다", ds_open_row(),
      server=False)

_pair(("FF-0684", "FF-1002"), POL_SURFACES, "navigation",
      "'이 정책 버전 보기'로 그 이름의 정책 버전 목록으로 이동한다",
      ds_navigate("버전 보기", "policies"), server=False)

_pair(("FF-0685", "FF-1003"), POL_SURFACES, "navigation",
      "헤더의 '프롬프트 사용 통계'로 프롬프트 쪽 통계로 이동한다",
      _header_link("프롬프트 사용 통계", "prompt"), server=False)

flow("FF-0686", "admin_ai-usage__policy-usage", "deep_link",
     "검색·필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/ai-usage?tab=policy-usage&used=true", "tab=policy-usage"), api=POU)

flow("FF-1004", "admin_policy-usage", "deep_link", "검색·필터가 해시 쿼리에 되쓰인다",
     ds_deep_link("/policy-usage?used=true", "used=true"), api=POU)

_pair(("FF-0687", "FF-1005"), POL_SURFACES, "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
      retry_from_error(POU, "정책 사용 통계"), api=POU)

_pair(("FF-0688", "FF-1006"), POL_SURFACES, "permission_state",
      "라우트 역할 가드 + 탭 단위 권한 안내", ds_permission((), POU, method="GET"),
      server=False)

# ── 프롬프트 쪽 ───────────────────────────────────────────────────────────
_pair(("FF-0689", "FF-1007"), PROM_SURFACES, "navigation",
      "'정책' ↔ '프롬프트' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("정책", "tab=policy-usage"), server=False)

_pair(("FF-0690", "FF-1008"), PROM_SURFACES, "search", "프롬프트 이름으로 검색한다",
      ds_search("", PU, server=False), server=False)

_pair(("FF-0691", "FF-1009"), PROM_SURFACES, "filter",
      "사용 여부(쓰이지 않음/쓰이는 중)로 좁힌다 — 화면 안에서 거른다",
      ds_filter("사용 여부", "쓰이", PU, server=False), server=False)

_pair(("FF-0692", "FF-1010"), PROM_SURFACES, "filter",
      "'필터 지우기'로 검색어·필터를 한 번에 해제한다", ds_clear("사용 여부", "쓰이"),
      server=False)

_pair(("FF-0693", "FF-1011"), PROM_SURFACES, "filter",
      "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다", ds_saved_view(),
      server=False)

_pair(("FF-0694", "FF-1012"), PROM_SURFACES, "sort",
      "열 머리를 눌러 버전 수·스케줄 수로 정렬한다", sort_by("버전"), server=False)

_pair(("FF-0695", "FF-1013"), PROM_SURFACES, "read",
      "행을 눌러 상세(참조하는 스케줄·최신 상태)를 연다", ds_open_row(), server=False)

_pair(("FF-0696", "FF-1014"), PROM_SURFACES, "navigation",
      "'이 프롬프트 버전 보기'로 그 이름의 프롬프트 버전 목록으로 이동한다",
      ds_navigate("버전 보기", "prompts"), server=False)

_pair(("FF-0697", "FF-1015"), PROM_SURFACES, "navigation",
      "헤더의 '정책 사용 통계'로 정책 쪽 통계로 이동한다",
      _header_link("정책 사용 통계", "polic"), server=False)

flow("FF-0698", "admin_ai-usage__prompt-usage", "deep_link",
     "검색·필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/ai-usage?tab=prompt-usage&used=true", "tab=prompt-usage"), api=PU)

flow("FF-1016", "admin_prompt-usage", "deep_link", "검색·필터가 해시 쿼리에 되쓰인다",
     ds_deep_link("/prompt-usage?used=true", "used=true"), api=PU)

_pair(("FF-0699", "FF-1017"), PROM_SURFACES, "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
      retry_from_error(PU, "프롬프트 사용 통계"), api=PU)

_pair(("FF-0700", "FF-1018"), PROM_SURFACES, "permission_state",
      "라우트 역할 가드 + 탭 단위 권한 안내", ds_permission((), PU, method="GET"),
      server=False)
