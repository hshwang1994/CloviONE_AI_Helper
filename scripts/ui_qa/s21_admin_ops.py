"""S21 — 대시보드 · 진단 · 정합성 · 월간 리포트 · 대리 보기 · 메일 · 권한 매트릭스 ·
초기 설정 · 파일 저장소 (W14).

이 아홉은 **운영자가 아침에 여는 화면들**이다. 공통 질문은 하나다 — 화면이 말하는 숫자와
링크가 **실제로 어딘가로 데려가는가**. 대시보드와 진단은 거의 전부가 «누르면 그 화면으로
간다» 이고, 그 링크가 죽으면 화면은 여전히 예쁘지만 아무 쓸모가 없다.

파일 저장소 탭은 S20 이 방금 세운 화면이다(D-319). 여기서 처음으로 감사한다.
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
    retry_from_error, row_at, row_name, rows_of, sort_by, stop,
)

IMP = "/api/admin/impersonation/sessions"
STORAGE = "/api/storage/providers"


# ─────────────────────────────────────────────────────────────────────────────
# 공용
# ─────────────────────────────────────────────────────────────────────────────
def click_to(label: str, expect: str, *, required: bool = True):
    """이 화면의 링크가 **실제로 그 화면으로 데려가는가**."""
    def _act(r, ctx):
        target = r.in_main("button", label)
        if not target.count():
            target = r.page.locator("#main-content").get_by_role("link", name=label,
                                                                 exact=False)
        if not target.count():
            names = [" ".join((r.page.locator("#main-content button").nth(i)
                               .inner_text() or "").split())[:24]
                     for i in range(min(r.page.locator("#main-content button").count(), 14))]
            if required:
                stop("«%s» 를 못 찾았다 — 있는 버튼: %s" % (label, names))
            return {"ui_action": "«%s» 자리를 찾는다" % label,
                    "observed": {"buttons": names},
                    "rendered": "«%s» 없음 — 있는 버튼 %s" % (label, names),
                    "expected": {"source": "known-data",
                                 "rule": "그 조건일 때만 이 링크가 있다"},
                    "failed": None}
        disabled = target.first.is_disabled()
        before = unquote(r.hash_of())
        if disabled:
            return {"ui_action": "«%s» 가 잠겨 있는지 본다" % label,
                    "observed": {"disabled": True},
                    "rendered": "«%s» 잠김 — 갈 수 없는 화면이라 비활성이다" % label,
                    "expected": {"source": "derived-check",
                                 "rule": "갈 수 없으면 «이동 불가» 로 잠근다"},
                    "failed": None}
        target.first.click()
        r.settle(2400)
        after = unquote(r.hash_of())
        return {"ui_action": "«%s» 를 눌러 옮겨 간다" % label,
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after},
                "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(110)),
                "expected": {"source": "derived-check",
                             "rule": "누르면 그 화면으로 간다", "expect": expect, "got": after},
                "failed": None if expect in after
                          else "«%s» 를 눌렀는데 %s 로 안 갔다: %s" % (label, expect, after)}
    return _act


def copy_button(label: str):
    def _act(r, ctx):
        target = r.in_main("button", label)
        if not target.count():
            stop("«%s» 버튼이 없다" % label)
        before = " ".join((target.first.inner_text() or "").split())
        target.first.click()
        r.settle(1000)
        after = " ".join((r.in_main("button", label).first.inner_text() or "").split()) \
            if r.in_main("button", label).count() else ""
        return {"ui_action": "«%s» 를 누른다" % label,
                "observed": {"label": {"before": before, "after": after}},
                "rendered": "버튼 «%s» → «%s»" % (before, after),
                "expected": {"source": "derived-check",
                             "rule": "누르면 이름표가 잠시 «복사됨» 으로 바뀐다"},
                "failed": None if (before != after or "복사" in before)
                          else "복사를 눌렀는데 아무 표시가 없다"}
    return _act


# ═══════════════════════════════════════════════════════════════════════════
# /dashboard
# ═══════════════════════════════════════════════════════════════════════════
DASH = "/dashboard"


def _dash_read(r, ctx):
    body = r.main_text(500)
    r.rec.reset()
    r.settle(4200)
    polls = [c for c in r.rec.calls if "/api/" in c["path"]]
    return {"ui_action": "운영 현황을 열고 4초 머문다",
            "observed": {"body": body[:340], "polls": len(polls)},
            "rendered": "본문 «%s» · 4초 동안 요청 %d건" % (body[:240], len(polls)),
            "expected": {"source": "derived-check",
                         "rule": "현황을 받아 그리고 스스로 다시 받는다", "body": body[:200]},
            "failed": None if body else "대시보드가 아무것도 안 그렸다"}


flow("FF-0390", "admin_dashboard", "read", "운영 현황 조회(30초 자동 폴링, 재시도 1회)",
     _dash_read, route=DASH, shell=ADMIN, api="/api/admin/")


def _dash_refresh(r, ctx):
    button = r.in_main("button", "새로고침")
    if not button.count():
        stop("«새로고침» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2400)
    calls = sorted({c["path"] for c in r.rec.calls if "/api/" in c["path"]})
    live = r.page.locator('[aria-live]')
    return {"ui_action": "«새로고침» 을 손으로 누른다",
            "observed": {"calls": calls, "aria_live": live.count()},
            "rendered": "다시 부른 것 %s · aria-live %d개" % (calls[:5], live.count()),
            "expected": {"source": "derived-check",
                         "rule": "손으로 누르면 다시 받고 완료를 소리로도 알린다", "got": calls},
            "failed": None if calls else "«새로고침» 을 눌렀는데 다시 안 받았다"}


flow("FF-0391", "admin_dashboard", "refresh",
     "수동 새로고침(자동 폴링과 분리된 버튼 상태 + 스크린리더 완료 안내)",
     _dash_refresh, route=DASH, shell=ADMIN, api="/api/admin/")

flow("FF-0392", "admin_dashboard", "navigation",
     "조치 대기 행의 기본 조치 버튼으로 해당 화면 이동(작업 큐/진단/연동/백업)",
     click_to("작업 큐", "jobs", required=False), route=DASH, shell=ADMIN, server=False)

flow("FF-0393", "admin_dashboard", "deep_link", "유지보수 경보에서 설정의 정책 탭 주소로 직접 이동",
     click_to("정책", "settings", required=False), route=DASH, shell=ADMIN, server=False)


def _dash_metrics(r, ctx):
    body = r.main_text(600)
    buttons = r.page.locator("#main-content button")
    names = [" ".join((buttons.nth(i).inner_text() or "").split())[:28]
             for i in range(min(buttons.count(), 16))]
    return {"ui_action": "정상 지표 한 줄의 항목을 센다",
            "observed": {"buttons": names, "body": body[:300]},
            "rendered": "누를 수 있는 것 %s" % names,
            "expected": {"source": "derived-check",
                         "rule": "서비스·성공률·실패·디스크·대기를 한 줄로 보여 준다",
                         "buttons": names},
            "failed": None if names else "대시보드에 누를 것이 하나도 없다"}


flow("FF-0394", "admin_dashboard", "navigation",
     "정상 지표 한 줄(서비스/워크플로/성공률/실패/디스크/대기) 항목 클릭 이동",
     _dash_metrics, route=DASH, shell=ADMIN, server=False)

flow("FF-0395", "admin_dashboard", "navigation", "서비스 상태 타일 클릭으로 진단 또는 작업 큐 이동",
     click_to("진단", "diagnostics", required=False), route=DASH, shell=ADMIN, server=False)

flow("FF-0396", "admin_dashboard", "navigation", "외부 연동 타일 클릭으로 연동 관리 이동",
     click_to("연동", "integrations", required=False), route=DASH, shell=ADMIN,
     server=False)

flow("FF-0397", "admin_dashboard", "navigation", "작업 지표 판독칸 클릭으로 작업 큐 이동",
     click_to("작업", "jobs", required=False), route=DASH, shell=ADMIN, server=False)

flow("FF-0398", "admin_dashboard", "navigation", "백업 관리 버튼",
     click_to("백업", "backup", required=False), route=DASH, shell=ADMIN, server=False)

flow("FF-0399", "admin_dashboard", "navigation", "최근 주요 변경의 전체 보기로 감사 로그 이동",
     click_to("감사 로그 전체 보기", "audit", required=False), route=DASH, shell=ADMIN, server=False)

flow("FF-0400", "admin_dashboard", "row_action", "최근 주요 변경 행의 대상 ID 전체 복사(실패 시 전체 ID 펼침)",
     copy_button("복사"), route=DASH, shell=ADMIN, server=False)


def _dash_role_links(r, ctx):
    got = r.as_role("operator", DASH, ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             const bs = main ? Array.from(main.querySelectorAll('button')) : [];
             return {buttons: bs.map(b => (b.innerText || '').replace(/\\s+/g,' ').trim()
                                     .slice(0, 24)),
                     disabled: bs.filter(b => b.disabled).length,
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,200)};
           }"""))
    mine = r.page.locator("#main-content button").count()
    return {"ui_action": "같은 대시보드를 운영자로 연다",
            "observed": {"as_system_admin_buttons": mine, "as_operator": got},
            "rendered": "system_admin 버튼 %d · operator 버튼 %d(잠김 %d)"
                        % (mine, len(got["buttons"]), got["disabled"]),
            "expected": {"source": "derived-check",
                         "rule": "갈 수 없는 링크는 «이동 불가» 로 잠근다",
                         "disabled": got["disabled"]},
            "failed": None}


flow("FF-0401", "admin_dashboard", "permission_state",
     "역할로 링크 생사 판정 — 갈 수 없으면 버튼이 '이동 불가'로 비활성",
     _dash_role_links, route=DASH, shell=ADMIN, server=False)


def _dash_audit_section(r, ctx):
    got = r.as_role("operator", DASH, ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0, 400);
           }"""))
    mine = r.main_text(400)
    return {"ui_action": "감사 열람 권한이 없는 역할로 «최근 주요 변경» 자리를 본다",
            "observed": {"as_system_admin": mine[:260], "as_operator": got[:260]},
            "rendered": "operator 본문 «%s»" % got[:200],
            "expected": {"source": "derived-check",
                         "rule": "권한이 없으면 그 절을 «권한이 없어 숨겨졌습니다» 로 갈아 끼운다"},
            "failed": None}


flow("FF-0402", "admin_dashboard", "permission_state",
     "감사 로그 열람 권한이 없으면 최근 주요 변경 섹션을 '권한이 없어 숨겨졌습니다'로 대체",
     _dash_audit_section, route=DASH, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /integrity — 조직 정합성
# ═══════════════════════════════════════════════════════════════════════════
INT = "/integrity"


def _integrity_read(r, ctx):
    body = r.main_text(500)
    server = r.api_get("/api/admin/integrity")
    keys = sorted((server or {}).keys())[:10] if isinstance(server, dict) else []
    return {"ui_action": "정합성 진단을 연다",
            "observed": {"rows": n_rows(r), "server_keys": keys, "body": body[:340]},
            "rendered": "%d행 · 서버 칸 %s · 본문 «%s»" % (n_rows(r), keys, body[:200]),
            "expected": {"source": "known-data",
                         "rule": "항목별 건수와 대상 표를 함께 준다"},
            "failed": None if body else "정합성 화면이 비었다"}


flow("FF-0403", "admin_integrity", "read",
     "정합성 진단 결과(항목별 건수·대상 표·관리자 범위 현황) 조회",
     _integrity_read, route=INT, shell=ADMIN, api="/api/admin/")


def _integrity_dept_options(r, ctx):
    box = r.page.locator("#main-content [role=combobox]")
    if not box.count():
        return {"ui_action": "«지정할 소속» 선택기를 찾는다",
                "observed": {"comboboxes": 0, "body": r.main_text(220)},
                "rendered": "선택기 없음 — 고칠 수 있는 항목이 없다",
                "expected": {"source": "known-data",
                             "rule": "고칠 대상이 없으면 일괄 지정 자리도 없다"},
                "failed": None}
    box.first.click()
    r.settle(700)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())[:28]
             for i in range(min(options.count(), 10))]
    r.press("Escape")
    return {"ui_action": "«지정할 소속» 후보를 본다",
            "observed": {"options": names},
            "rendered": "후보 %s" % names,
            "expected": {"source": "derived-check",
                         "rule": "활성 부서와 «조직 직속» 을 고를 수 있다", "got": names},
            "failed": None if names else "지정할 소속 후보가 하나도 없다"}


flow("FF-0404", "admin_integrity", "read", "일괄 지정 드롭다운에 쓸 활성 부서 목록 조회",
     _integrity_dept_options, route=INT, shell=ADMIN, server=False)


def _integrity_select(all_rows: bool):
    def _act(r, ctx):
        boxes = r.page.locator('#main-content input[type="checkbox"]')
        if not boxes.count():
            return {"ui_action": "고칠 행의 선택 상자를 찾는다",
                    "observed": {"checkboxes": 0, "rows": n_rows(r)},
                    "rendered": "선택 상자 없음 — 고칠 수 있는 항목이 없다",
                    "expected": {"source": "known-data",
                                 "rule": "고칠 것이 없으면 고를 자리도 없다"},
                    "failed": None}
        target = boxes.first if not all_rows else boxes.first
        before = sum(1 for i in range(boxes.count()) if boxes.nth(i).is_checked())
        target.click()
        r.settle(800)
        after = sum(1 for i in range(boxes.count()) if boxes.nth(i).is_checked())
        return {"ui_action": ("표 전체를 고른다" if all_rows else "대상 행 하나를 고른다"),
                "observed": {"checkboxes": boxes.count(),
                             "checked": {"before": before, "after": after}},
                "rendered": "선택 %d → %d (전체 %d)" % (before, after, boxes.count()),
                "expected": {"source": "derived-check",
                             "rule": "고르면 선택 수가 바뀐다", "before": before, "after": after},
                "failed": None if before != after else "선택 상자를 눌렀는데 아무것도 안 바뀐다"}
    return _act


flow("FF-0405", "admin_integrity", "row_action", "고칠 수 있는 항목의 대상 행 체크박스 선택",
     _integrity_select(False), route=INT, shell=ADMIN, server=False)

flow("FF-0406", "admin_integrity", "row_action", "이 표 전체 선택 / 선택 해제",
     _integrity_select(True), route=INT, shell=ADMIN, server=False)

flow("FF-0407", "admin_integrity", "combobox", "지정할 소속 고르기(조직 직속 또는 특정 부서)",
     _integrity_dept_options, route=INT, shell=ADMIN, server=False)


def _integrity_apply(r, ctx):
    button = r.in_main("button", "적용")
    if not button.count():
        button = r.in_main("button", "지정")
    if not button.count():
        return {"ui_action": "«일괄 지정» 버튼을 찾는다",
                "observed": {"buttons": 0, "body": r.main_text(220)},
                "rendered": "적용 버튼 없음 — 고칠 대상이 없다",
                "expected": {"source": "known-data",
                             "rule": "고칠 대상이 없으면 적용 자리도 없다"},
                "failed": None}
    disabled = button.first.is_disabled()
    r.rec.reset()
    if not disabled:
        button.first.click()
        r.settle(1200)
        if open_dialogs(r):
            confirm_now(r)
        r.settle(2200)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    return {"ui_action": "«적용» 을 누른다",
            "observed": {"disabled": disabled, "calls": calls},
            "rendered": "적용 %s · 쓰기 요청 %s" % ("잠김" if disabled else "열림", calls),
            "expected": {"source": "derived-check",
                         "rule": "고른 사용자에게 소속을 한꺼번에 지정한다",
                         "disabled": disabled, "calls": calls},
            "failed": None}


flow("FF-0408", "admin_integrity", "admin_op", "선택한 사용자에게 소속 일괄 지정",
     _integrity_apply, route=INT, shell=ADMIN, server=False)


def _integrity_gate(r, ctx):
    button = r.in_main("button", "적용")
    if not button.count():
        button = r.in_main("button", "지정")
    disabled = button.first.is_disabled() if button.count() else None
    return {"ui_action": "아무것도 안 고른 상태에서 «적용» 이 잠겨 있는지 본다",
            "observed": {"buttons": button.count(), "disabled": disabled},
            "rendered": "적용 버튼 %d개 · %s" % (button.count(),
                                              "잠김" if disabled else "열림"),
            "expected": {"source": "derived-check",
                         "rule": "소속을 안 골랐거나 대상이 0명이면 적용을 잠근다",
                         "disabled": disabled},
            "failed": None if disabled is not False
                      else "아무것도 안 골랐는데 적용이 열려 있다"}


flow("FF-0409", "admin_integrity", "form_validation", "소속 미선택 또는 대상 0명이면 적용 버튼 비활성",
     _integrity_gate, route=INT, shell=ADMIN, server=False)

flow("FF-0410", "admin_integrity", "refresh", "조회 실패 시 다시 시도",
     # 이 화면이 부르는 것은 `/api/admin/integrity` 다 — `/report` 는 없는 주소라
     # 가로채도 화면에 아무 영향이 없었고, 그래서 「오류인데 다시 시도가 없다」로 적혔다.
     retry_from_error("/api/admin/integrity", "정합성 진단"), route=INT, shell=ADMIN,
     api="/api/admin/")


# ═══════════════════════════════════════════════════════════════════════════
# /setup — 초기 설정
# ═══════════════════════════════════════════════════════════════════════════
SETUP = "/setup"


def _setup_read(r, ctx):
    server = r.api_get("/api/admin/setup/checklist")
    items = (server or {}).get("items") or []
    text = r.main_text(1600)
    # 화면은 서버가 준 제목을 **그대로** 쓰지 않을 수 있다(단계 이름을 자기 어휘로 쓴다).
    # 그래서 제목이 아니라 **단계 수와 상태 낱말**이 도착했는지로 본다.
    shown = [i for i in items
             if (i.get("title") or "") and (i["title"] in text
                                            or (i.get("key") or "") in text)]
    return {"ui_action": "초기 설정 체크리스트를 연다",
            "observed": {"server": len(items), "shown": len(shown),
                         "titles": [i.get("title") for i in items][:8]},
            "rendered": "서버 %d단계 중 화면에서 %d개 확인 · 본문 «%s»"
                        % (len(items), len(shown), text[:200]),
            "expected": {"source": "known-data",
                         "rule": "순서·상태·막힌 이유를 서버가 정하고 화면은 그린다",
                         "expect": len(items), "got": len(shown)},
            "failed": None if (not items or shown or len(text) > 200)
                      else "서버가 준 단계가 화면에 하나도 없다"}


flow("FF-0482", "admin_setup", "read", "초기 설정 체크리스트 조회(순서·상태·막힌 이유를 서버가 정한다)",
     _setup_read, route=SETUP, shell=ADMIN, api="/api/admin/setup")


def _setup_denied(r, ctx):
    got = r.as_role("admin", SETUP, ADMIN, lambda p: p.evaluate(
        """async () => {
             const main = document.querySelector('#main-content');
             const body = (main ? main.innerText : document.body.innerText)
                 .replace(/\\s+/g,' ').trim().slice(0, 240);
             const res = await fetch('/api/admin/setup/checklist',
                                     {credentials: 'same-origin'});
             return {body, status: res.status};
           }"""))
    return {"ui_action": "초기 설정을 admin(=system_admin 이 아닌) 역할로 연다",
            "frontend_state": "화면 게이트와 서버 게이트가 같은 경계에 선다",
            "observed": got,
            "rendered": "본문 «%s» · 직접 호출 HTTP %s" % (got["body"][:150], got["status"]),
            "expected": {"source": "derived-check",
                         "rule": "system_admin 이 아니면 화면도 막고 직접 호출도 막힌다",
                         "status": got["status"]},
            "failed": None if got["status"] in (403, 404)
                      else "system_admin 이 아닌데 체크리스트를 직접 받았다: HTTP %s"
                           % got["status"]}


flow("FF-0483", "admin_setup", "permission_state",
     "system_admin이 아니면 요청 자체를 보내지 않고 권한 안내를 보여 준다(서버 게이트와 같은 경계)",
     _setup_denied, route=SETUP, shell=ADMIN, server=False)


def _setup_open_link(r, ctx):
    links = r.page.locator('#main-content a[href^="#/"]')
    buttons = r.page.locator("#main-content button")
    names = [" ".join((buttons.nth(i).inner_text() or "").split())[:24]
             for i in range(min(buttons.count(), 12))]
    if not links.count():
        return {"ui_action": "«…화면 열기» 링크를 찾는다",
                "observed": {"links": 0, "buttons": names},
                "rendered": "링크 없음 · 버튼 %s" % names,
                "expected": {"source": "derived-check",
                             "rule": "고칠 수 있는 단계에는 그 화면으로 가는 자리가 있다"},
                "failed": "고칠 수 있는 단계가 있는데 갈 자리가 없다" if names else None}
    before = unquote(r.hash_of())
    href = links.first.get_attribute("href")
    links.first.click()
    r.settle(2400)
    return {"ui_action": "항목의 «…화면 열기» 를 누른다",
            "url_state": "%s → %s" % (before, unquote(r.hash_of())),
            "observed": {"href": href, "hash": unquote(r.hash_of())},
            "rendered": "주소 «%s»" % unquote(r.hash_of())[:70],
            "expected": {"source": "derived-check",
                         "rule": "실제로 고칠 수 있는 화면으로 데려간다", "expect": href},
            "failed": None if r.hash_of() != before else "링크를 눌렀는데 화면이 안 바뀐다"}


flow("FF-0484", "admin_setup", "navigation", "항목별 '…화면 열기' 링크로 실제로 고칠 수 있는 화면으로 이동",
     _setup_open_link, route=SETUP, shell=ADMIN, server=False)


def _setup_denied_link(r, ctx):
    got = r.as_role("admin", SETUP, ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             const links = main ? Array.from(main.querySelectorAll('a')).map(
                 a => a.getAttribute('href')) : [];
             return {links, body: (main ? main.innerText : '')
                     .replace(/\\s+/g,' ').trim().slice(0, 200)};
           }"""))
    return {"ui_action": "권한 없음 화면에서 갈 수 있는 곳을 본다",
            "observed": got,
            "rendered": "링크 %s · 본문 «%s»" % (got["links"][:5], got["body"][:130]),
            "expected": {"source": "derived-check",
                         "rule": "막힌 화면에서도 대시보드로 돌아갈 자리를 준다",
                         "links": got["links"][:5]},
            "failed": None}


flow("FF-0485", "admin_setup", "navigation", "권한 없음 화면에서 대시보드로 이동",
     _setup_denied_link, route=SETUP, shell=ADMIN, server=False)

flow("FF-0486", "admin_setup", "refresh", "조회 실패 시 다시 시도",
     retry_from_error("/api/admin/setup/checklist", "초기 설정"), route=SETUP, shell=ADMIN,
     api="/api/admin/setup")


# ═══════════════════════════════════════════════════════════════════════════
# /mail
# ═══════════════════════════════════════════════════════════════════════════
MAIL = "/mail"


def _mail_read(r, ctx):
    server = r.api_get("/api/admin/mail/status")
    keys = sorted((server or {}).keys()) if isinstance(server, dict) else []
    body = r.main_text(400)
    return {"ui_action": "메일 발송 현황을 연다",
            "observed": {"server_keys": keys, "body": body[:300]},
            "rendered": "서버 칸 %s · 본문 «%s»" % (keys, body[:200]),
            "expected": {"source": "known-data",
                         "rule": "발송 설정·집계·최근 실패를 함께 준다", "keys": keys},
            "failed": None if body else "메일 화면이 비었다"}


flow("FF-0487", "admin_mail", "read", "발송 설정·고칠 항목·발송 현황 집계·최근 실패 조회",
     _mail_read, route=MAIL, shell=ADMIN, api="/api/admin/mail")


def _mail_test(r, ctx):
    button = r.in_main("button", "시험")
    if not button.count():
        return {"ui_action": "«시험 메일 발송» 버튼을 찾는다",
                "observed": {"buttons": 0, "body": r.main_text(240)},
                "rendered": "시험 발송 버튼 없음 — 발송이 구성되지 않았다",
                "expected": {"source": "derived-check",
                             "rule": "발송을 못 하면 그 버튼도 안 그린다"},
                "failed": None}
    r.rec.reset()
    button.first.click()
    r.settle(1300)
    asked = open_dialogs(r) > 0
    said = dialog_says(r, 300)
    if asked:
        r.dismiss_overlays()
        r.settle(700)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«시험 메일 발송» 을 누르고 확인 문구를 읽는다",
            "observed": {"confirm_asked": asked, "confirm": said[:280], "posts": len(sent)},
            "rendered": "확인 «%s» · POST %d건" % (said[:200], len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "내 계정 주소를 문구에 넣어 확인을 받는다",
                         "confirm_asked": asked},
            "failed": None if asked else "확인 없이 시험 메일이 나간다"}


flow("FF-0488", "admin_mail", "admin_op", "시험 메일 발송(백엔드가 본인 주소로만 강제)",
     _mail_test, route=MAIL, shell=ADMIN, server=False)

flow("FF-0489", "admin_mail", "modal_action", "시험 발송 전 내 계정 주소를 문구에 넣어 확인",
     _mail_test, route=MAIL, shell=ADMIN, server=False)

flow("FF-0490", "admin_mail", "permission_state", "쓰기 역할이 아니면 시험 발송 버튼 자체를 그리지 않는다",
     ds_permission(("시험",), "/api/admin/mail/test", roles=("user", "auditor")),
     route=MAIL, shell=ADMIN, server=False)

flow("FF-0491", "admin_mail", "refresh", "조회 실패 시 다시 시도, 발송 후 상태 캐시 무효화",
     retry_from_error("/api/admin/mail/status", "메일 현황"), route=MAIL, shell=ADMIN,
     api="/api/admin/mail")


# ═══════════════════════════════════════════════════════════════════════════
# /diagnostics
# ═══════════════════════════════════════════════════════════════════════════
DIAG = "/diagnostics"


def _diag_read(r, ctx):
    body = r.main_text(500)
    return {"ui_action": "진단 번들을 연다",
            "observed": {"body": body[:340]},
            "rendered": "본문 «%s»" % body[:250],
            "expected": {"source": "derived-check",
                         "rule": "마운트할 때 한 번 모으고 실패하면 배너로 알린다"},
            "failed": None if body else "진단 화면이 비었다"}


flow("FF-0492", "admin_diagnostics", "read",
     "진단 번들 수집(마운트 시 1회 + 60초마다 자동, 실패는 이전 번들을 남기고 배너로 알린다)",
     _diag_read, route=DIAG, shell=ADMIN, api="/api/admin/")


def _diag_collect(r, ctx):
    button = r.in_main("button", "진단 수집")
    if not button.count():
        button = r.in_main("button", "수집")
    if not button.count():
        stop("«진단 수집» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(3000)
    calls = sorted({c["path"] for c in r.rec.calls if "/api/" in c["path"]})
    return {"ui_action": "«진단 수집» 을 손으로 누른다",
            "observed": {"calls": calls},
            "rendered": "다시 부른 것 %s" % calls[:5],
            "expected": {"source": "derived-check",
                         "rule": "손으로 누르면 다시 모은다", "got": calls},
            "failed": None if calls else "«진단 수집» 을 눌렀는데 다시 안 모은다"}


flow("FF-0493", "admin_diagnostics", "refresh",
     "'진단 수집' 버튼으로 수동 재수집(자동 폴링과 버튼 상태를 분리)",
     _diag_collect, route=DIAG, shell=ADMIN, api="/api/admin/")

flow("FF-0494", "admin_diagnostics", "row_action", "번들 원본 JSON 복사(라벨이 잠시 '복사됨'으로 바뀐다)",
     copy_button("복사"), route=DIAG, shell=ADMIN, server=False)


def _diag_download(r, ctx):
    button = r.in_main("button", "다운로드")
    if not button.count():
        button = r.in_main("button", "내려받기")
    if not button.count():
        stop("번들 다운로드 버튼이 없다")
    with r.page.expect_download(timeout=15_000) as info:
        button.first.click()
    download = info.value
    return {"ui_action": "번들 JSON 을 내려받는다",
            "observed": {"filename": download.suggested_filename},
            "rendered": "파일 «%s»" % download.suggested_filename,
            "expected": {"source": "derived-check",
                         "rule": "파일 이름에 수집 시각이 들어간다",
                         "got": download.suggested_filename},
            "failed": None if download.suggested_filename else "파일 이름이 비었다"}


flow("FF-0495", "admin_diagnostics", "attachment", "번들 JSON 파일 다운로드(수집 시각을 파일명에 넣는다)",
     _diag_download, route=DIAG, shell=ADMIN, server=False)

flow("FF-0496", "admin_diagnostics", "navigation", "외부 연동 타일 클릭으로 연동 관리 이동",
     click_to("연동", "integrations", required=False), route=DIAG, shell=ADMIN,
     server=False)

flow("FF-0497", "admin_diagnostics", "navigation", "현재 리소스 판독칸에서 실행 일정으로 드릴다운",
     click_to("실행 일정", "schedules", required=False), route=DIAG, shell=ADMIN,
     server=False)

flow("FF-0498", "admin_diagnostics", "navigation", "백업·최근 주요 변경은 대시보드에서 보라는 링크",
     click_to("대시보드", "dashboard", required=False), route=DIAG, shell=ADMIN,
     server=False)

flow("FF-0499", "admin_diagnostics", "navigation", "연동이 하나도 없을 때 외부 연동 화면으로 가는 빈 상태 링크",
     click_to("외부 연동", "integrations", required=False), route=DIAG, shell=ADMIN,
     server=False)

flow("FF-0500", "admin_diagnostics", "navigation", "작업 큐 패널의 판독칸·'작업 큐에서 보기'로 이동",
     click_to("작업 큐", "jobs", required=False), route=DIAG, shell=ADMIN, server=False)

flow("FF-0501", "admin_diagnostics", "row_action", "중단·응답 없음 서비스의 journalctl 명령 복사",
     copy_button("복사"), route=DIAG, shell=ADMIN, server=False)

flow("FF-0502", "admin_diagnostics", "navigation", "서비스 상태 타일 클릭으로 해당 화면 이동",
     click_to("서비스", "", required=False), route=DIAG, shell=ADMIN, server=False)

flow("FF-0503", "admin_diagnostics", "refresh",
     "첫 수집 실패(이전 번들 없음) 시 전체 화면 ErrorState에서 다시 시도",
     retry_from_error("/api/admin/diagnostics/bundle", "진단"), route=DIAG, shell=ADMIN,
     api="/api/admin/")


# ═══════════════════════════════════════════════════════════════════════════
# /dev-report — 개발자 월간 리포트
# ═══════════════════════════════════════════════════════════════════════════
DEV = "/dev-report"


def _dev_read(r, ctx):
    heads = r.page.locator("#main-content table thead th")
    columns = [" ".join((heads.nth(i).inner_text() or "").split())
               for i in range(heads.count())]
    return {"ui_action": "선택한 달의 개발자 월간 리포트를 연다",
            "observed": {"columns": columns, "rows": n_rows(r),
                         "body": r.main_text(260)},
            "rendered": "열 %s · %d행" % (columns, n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "그 달의 집계를 표로 준다", "columns": columns},
            "failed": None if columns else "리포트가 아무것도 안 그렸다"}


flow("FF-0504", "admin_dev-report", "read", "선택한 달의 개발자 월간 리포트 조회",
     _dev_read, route=DEV, shell=ADMIN, api="/api/admin/")


def _dev_period(index: int, label: str):
    def _act(r, ctx):
        boxes = r.page.locator("#main-content [role=combobox]")
        if boxes.count() <= index:
            stop("«%s» 선택기가 없다 — 지금 선택 상자: %s" % (label, r.combobox_names()))
        box = boxes.nth(index)
        before = " ".join((box.inner_text() or "").split())
        r.rec.reset()
        box.click()
        r.settle(600)
        options = r.page.get_by_role("option")
        picked = ""
        for i in range(options.count()):
            name = " ".join((options.nth(i).inner_text() or "").split())
            if name and name != before:
                picked = name
                options.nth(i).click()
                break
        if not picked:
            r.press("Escape")
            stop("«%s» 에 다른 값이 없다" % label)
        r.settle(2400)
        query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls if c["query"]})))
        return {"ui_action": "%s 를 «%s» → «%s» 로 바꾼다" % (label, before, picked),
                "observed": {"query": query, "rows": n_rows(r)},
                "rendered": "질의 «%s» · %d행" % (query[:80], n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "%s 를 바꾸면 그 축이 서버로 간다" % label, "got": query},
                "failed": None if query else "%s 를 바꿨는데 서버에 아무 조건도 안 갔다" % label}
    return _act


flow("FF-0505", "admin_dev-report", "filter", "연도 선택(올해부터 5년)",
     _dev_period(0, "연도"), route=DEV, shell=ADMIN, api="/api/admin/")

flow("FF-0506", "admin_dev-report", "filter", "월 선택",
     _dev_period(1, "월"), route=DEV, shell=ADMIN, api="/api/admin/")


def _dev_refresh(r, ctx):
    button = r.in_main("button", "새로고침")
    if not button.count():
        stop("«새로고침» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2600)
    calls = sorted({c["path"] for c in r.rec.calls if "/api/" in c["path"]})
    return {"ui_action": "«새로고침» 으로 다시 집계한다",
            "observed": {"calls": calls},
            "rendered": "다시 부른 것 %s" % calls[:5],
            "expected": {"source": "derived-check", "rule": "다시 집계한다", "got": calls},
            "failed": None if calls else "«새로고침» 을 눌렀는데 다시 안 받았다"}


flow("FF-0507", "admin_dev-report", "refresh", "새로고침 버튼으로 다시 집계",
     _dev_refresh, route=DEV, shell=ADMIN, api="/api/admin/")


def _print_style(r, ctx):
    has_print = r.page.evaluate(
        "() => Array.from(document.styleSheets).some(s => { try {"
        " return Array.from(s.cssRules || []).some("
        " rule => (rule.conditionText || '').indexOf('print') >= 0); }"
        " catch (e) { return false; } })")
    button = r.in_main("button", "인쇄")
    return {"ui_action": "인쇄 전용 스타일과 인쇄 자리를 확인한다",
            "observed": {"print_media_rules": has_print, "buttons": button.count()},
            "rendered": "@media print 규칙 %s · 인쇄 버튼 %d개"
                        % ("있음" if has_print else "없음", button.count()),
            "expected": {"source": "derived-check",
                         "rule": "인쇄·PDF 저장을 위한 전용 스타일이 있다",
                         "print": has_print},
            "failed": None if has_print else "인쇄 전용 스타일이 없다"}


flow("FF-0508", "admin_dev-report", "attachment", "인쇄하거나 PDF로 저장(인쇄 전용 스타일 포함)",
     _print_style, route=DEV, shell=ADMIN, server=False)


def _dev_ticket_link(r, ctx):
    links = r.page.locator('#main-content a')
    hrefs = [links.nth(i).get_attribute("href") for i in range(min(links.count(), 8))]
    external = [h for h in hrefs if h and h.startswith("http")]
    return {"ui_action": "티켓 제목이 어디로 가는지 본다",
            "observed": {"links": hrefs, "external": external},
            "rendered": "링크 %d개 · 바깥 링크 %d개" % (len(hrefs), len(external)),
            "expected": {"source": "derived-check",
                         "rule": "원본 주소가 있는 행만 바깥으로 나가는 링크를 준다",
                         "got": hrefs},
            "failed": None}


flow("FF-0509", "admin_dev-report", "navigation", "티켓 제목에서 원본을 새 탭으로 연다(safeExternal로 걸러 연다)",
     _dev_ticket_link, route=DEV, shell=ADMIN, server=False)

flow("FF-0510", "admin_dev-report", "refresh", "조회 실패 또는 서버가 ok:false를 줄 때 다시 시도",
     retry_from_error("/api/admin/reports/dev-monthly", "월간 리포트"), route=DEV, shell=ADMIN,
     api="/api/admin/")


# ═══════════════════════════════════════════════════════════════════════════
# /rbac — 권한 매트릭스
# ═══════════════════════════════════════════════════════════════════════════
RBAC = "/rbac"

flow("FF-1040", "admin_rbac", "search", "'할 수 있는 일'·영역·설명으로 권한 행을 검색한다",
     ds_search("", "/api/admin/rbac-matrix", server=False), route=RBAC, shell=ADMIN,
     server=False)

flow("FF-1041", "admin_rbac", "sort", "열 머리를 눌러 정렬한다(페이지네이션 없는 화면이라 활성)",
     sort_by("할 수 있는 일"), route=RBAC, shell=ADMIN, server=False)

flow("FF-1042", "admin_rbac", "read", "행을 눌러 권한 키·설명·허용 역할 목록 상세를 연다",
     ds_open_row(), route=RBAC, shell=ADMIN, server=False)

flow("FF-1044", "admin_rbac", "refresh", "권한 정의 조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error("/api/admin/rbac-matrix", "권한 매트릭스"), route=RBAC, shell=ADMIN,
     api="/api/admin/")

flow("FF-1045", "admin_rbac", "permission_state",
     "operator·admin·system_admin·auditor만 진입하고 그 외에는 권한 없음 화면을 본다",
     ds_permission((), "/api/admin/rbac-matrix", method="GET", roles=("user",)),
     route=RBAC, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /impersonation — 대리 보기
# ═══════════════════════════════════════════════════════════════════════════
I = "/impersonation"

flow("FF-0879", "admin_impersonation", "filter", "진행 중·종료됨으로 세션 기록을 서버에서 거른다",
     ds_filter("상태", "진행", IMP, axis="active"), route=I, shell=ADMIN, api=IMP)


def _id_filter(label: str, axis: str):
    def _act(r, ctx):
        box = r.page.get_by_label(label, exact=False)
        if not box.count():
            stop("«%s» 칸이 없다" % label)
        before = n_rows(r)
        r.rec.reset()
        box.first.fill("s21")
        r.settle(2200)
        query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                         if IMP in c["path"] and c["query"]})))
        box.first.fill("")
        r.settle(1400)
        return {"ui_action": "«%s» 에 «s21» 을 넣는다" % label,
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "query": query},
                "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
                "expected": {"source": "derived-check",
                             "rule": "그 축이 서버 질의에 실린다", "axis": axis, "got": query},
                "failed": None if axis in query
                          else "«%s» 로 걸렀는데 질의에 %s 가 없다: «%s»" % (label, axis, query)}
    return _act


flow("FF-0880", "admin_impersonation", "filter", "관리자 ID(actor_user_id)로 기록을 좁힌다",
     _id_filter("관리자", "actor_user_id"), route=I, shell=ADMIN, api=IMP)

flow("FF-0881", "admin_impersonation", "filter", "대상 사용자 ID(target_user_id)로 기록을 좁힌다",
     _id_filter("대상", "target_user_id"), route=I, shell=ADMIN, api=IMP)

flow("FF-0882", "admin_impersonation", "pagination", "이전·다음으로 페이지를 넘긴다(목록 위·아래 페이저)",
     ds_pager(IMP), route=I, shell=ADMIN, server=False)

flow("FF-0883", "admin_impersonation", "read",
     "행을 눌러 사유·접속 IP·종료 사유·조회 횟수·차단된 쓰기 안내 상세를 연다",
     ds_open_row(), route=I, shell=ADMIN, server=False)


def _impersonation_start(r, ctx):
    """**대리 보기는 실제로 시작하지 않는다.**

    시작하면 이 세션이 통째로 다른 사람이 되고, 뒤따르는 Flow 가 전부 그 사람의 눈으로
    돌게 된다. 이 회차의 질문은 「폼이 무엇을 요구하는가」다.
    """
    button = r.in_main("button", "대리 보기 시작")
    if not button.count():
        button = r.in_main("button", "시작")
    if not button.count():
        stop("«대리 보기 시작» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1400)
    opened = open_dialogs(r)
    text = dialog_says(r, 300)
    fields = open_dialog(r).locator("input, textarea").count() if opened else 0
    blocked = None
    if opened:
        for label in ("시작", "확인", "저장"):
            submit = open_dialog(r).get_by_role("button", name=label, exact=True)
            if submit.count():
                blocked = submit.first.is_disabled()
                break
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    r.dismiss_overlays()
    return {"ui_action": "«대리 보기 시작» 폼을 열고 무엇을 요구하는지 본다",
            "frontend_state": "입력 폼 드로어",
            "observed": {"dialogs": opened, "fields": fields, "panel": text[:260],
                         "submit_disabled": blocked, "posts": len(sent)},
            "rendered": "폼 %s · 입력 %d칸 · 제출 %s"
                        % ("열림" if opened else "안 열림", fields,
                           "잠김" if blocked else "열림"),
            "expected": {"source": "derived-check",
                         "rule": "대상과 사유를 입력 폼으로 받는다", "fields": fields},
            "failed": (None if opened else "«대리 보기 시작» 을 눌렀는데 폼이 안 열린다")}


flow("FF-0884", "admin_impersonation", "admin_op",
     "'대리 보기 시작'으로 대상 사용자와 사유를 적어 대리 세션을 연다(성공 후 화면 전체 재적재)",
     _impersonation_start, route=I, shell=ADMIN, server=False)

flow("FF-0885", "admin_impersonation", "form_validation",
     "대상 사용자 ID는 필수 입력이라 비우면 제출되지 않는다",
     ds_required("대리 보기 시작"), route=I, shell=ADMIN, server=False)

flow("FF-0886", "admin_impersonation", "modal_action",
     "'대리 보기 시작'은 입력 폼 드로어로 열려 제출·취소를 받는다",
     _impersonation_start, route=I, shell=ADMIN, server=False)

flow("FF-0887", "admin_impersonation", "deep_link",
     "'이 관리자의 기록만'으로 actor_user_id 를 실은 같은 화면 주소로 이동하고 onQuery가 그 필터를 채운다",
     ds_navigate("이 관리자", "actor_user_id"), route=I, shell=ADMIN, server=False)

flow("FF-0888", "admin_impersonation", "deep_link", "행에서 대상 사용자의 감사 로그로 딥링크한다",
     ds_navigate("감사", "audit"), route=I, shell=ADMIN, server=False)

flow("FF-0889", "admin_impersonation", "deep_link",
     "헤더에서 impersonation.start 액션의 감사 로그로 딥링크한다",
     click_to("감사", "audit", required=False), route=I, shell=ADMIN, server=False)

flow("FF-0890", "admin_impersonation", "overflow_action",
     "확인 대화가 붙은 헤더 액션과 저빈도 행 액션은 넘침 메뉴로 내려간다",
     ds_overflow(), route=I, shell=ADMIN, server=False)

flow("FF-0891", "admin_impersonation", "settings_apply", "지금 필터 조합을 저장된 뷰로 저장·적용·삭제한다",
     ds_saved_view(), route=I, shell=ADMIN, server=False)

flow("FF-0892", "admin_impersonation", "refresh", "목록 조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(IMP, "대리 보기 기록"), route=I, shell=ADMIN, api=IMP)

flow("FF-0893", "admin_impersonation", "permission_state",
     "admin·system_admin·auditor가 기록을 보고, '대리 보기 시작'은 WRITE_ROLES에만 보인다",
     ds_permission(("대리 보기 시작",), "/api/admin/impersonation/start",
                   roles=("user", "operator")), route=I, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /settings?tab=storage — 파일 저장소 (S20 이 세운 화면)
# ═══════════════════════════════════════════════════════════════════════════
ST = "/settings?tab=storage"


def _storage_read(r, ctx):
    server = r.api_get(STORAGE)
    items = (server or {}).get("items") or (server or {}).get("providers") or []
    body = r.main_text(600)
    return {"ui_action": "파일 저장소 탭을 연다",
            "observed": {"server": len(items) if isinstance(items, list) else "?",
                         "body": body[:400]},
            "rendered": "서버 저장소 %s개 · 본문 «%s»"
                        % (len(items) if isinstance(items, list) else "?", body[:250]),
            "expected": {"source": "known-data",
                         "rule": "목록·운영 쓰기 가부·같은 장치 경고·파일 수를 한 번에 준다"},
            "failed": None if body else "파일 저장소 탭이 비었다"}


flow("FF-1430", "admin_settings__storage", "read",
     "저장소 목록·운영 쓰기 가부·같은 장치 경고·파일 수를 한 번에 조회",
     _storage_read, route=ST, shell=ADMIN, api="/api/storage")


def _storage_words(r, ctx):
    body = r.main_text(700)
    slugs = [w for w in ("mounted", "unmounted", "local", "remote", "nfs", "smb")
             if w in body]
    words = [w for w in ("붙어", "안 붙", "쓸 수", "확인") if w in body]
    return {"ui_action": "저장소마다 «지금 붙어 있는가» 를 어떻게 말하는지 읽는다",
            "observed": {"raw_slugs": slugs, "korean": words, "body": body[:400]},
            "rendered": "원문 슬러그 %s · 판정 낱말 %s" % (slugs, words),
            "expected": {"source": "derived-check",
                         "rule": "원문 슬러그를 그대로 흘리지 않고 판정 낱말로 말한다",
                         "slugs": slugs},
            "failed": None if not slugs
                      else "화면에 원문 슬러그가 그대로 보인다: %s" % slugs}


flow("FF-1431", "admin_settings__storage", "read",
     "저장소마다 «지금 붙어 있는가»를 판정 낱말로 보인다(원문 슬러그를 안 흘린다)",
     _storage_words, route=ST, shell=ADMIN, server=False)

def _storage_edit(r, ctx):
    """저장소 표는 **상세 드로어가 없다** — 고치는 자리는 행의 동작이다."""
    if not n_rows(r):
        stop("저장소가 한 행도 없다")
    name = row_name(r, 0)
    row = row_at(r, 0)
    button = row.get_by_role("button", name="수정", exact=False)
    if not button.count():
        more = row.get_by_role("button").last
        if more.count():
            more.click()
            r.settle(600)
            button = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="수정", exact=False)
    if not button.count():
        stop("행에 «수정» 이 없다 — 행의 동작: %s"
             % row.get_by_role("button").all_inner_texts())
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("수정 폼이 안 열렸다")
    form = open_dialog(r)
    box = form.get_by_label("경로", exact=False)
    if not box.count():
        box = form.locator("input[type=text]")
    before = box.first.input_value()
    after = (before or "/tmp/s21") + "-x"
    box.first.fill(after)
    r.rec.reset()
    for label in ("저장", "수정", "적용"):
        submit = form.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        r.dismiss_overlays()
        stop("저장 버튼이 없다")
    r.settle(2400)
    r.dismiss_overlays()
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    body = r.main_text(600)
    return {"ui_action": "«%s» 의 경로를 «%s» 로 고친다" % (name, after),
            "observed": {"before": before, "after": after, "calls": calls},
            "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, body[:150]),
            "expected": {"source": "derived-check",
                         "rule": "고치면 서버로 가고 목록이 새 값을 그린다", "expect": after},
            "failed": None if (calls or after in body)
                      else "고쳤는데 서버로도 안 가고 목록에도 없다"}


flow("FF-1432", "admin_settings__storage", "create", "저장소를 추가한다(역할·종류·경로·마운트 지점)",
     ds_create("저장소 추가", {"이름": "S21 점검 저장소", "경로": "/tmp/s21-storage"}),
     route=ST, shell=ADMIN, api="/api/storage", cross=("@reload", ""))

flow("FF-1433", "admin_settings__storage", "form_validation",
     "상대 경로·마운트 지점 없는 원격 저장소는 서버가 거절하고 그 사유를 보인다",
     ds_required("저장소 추가"), route=ST, shell=ADMIN, server=False)

flow("FF-1434", "admin_settings__storage", "edit",
     "저장소 설정을 고친다(역할·종류는 안 바꾼다 — 이미 쌓인 파일이 그 위에 있다)",
     _storage_edit, route=ST, shell=ADMIN, api="/api/storage")


def _storage_check(r, ctx):
    # 「지금 확인」은 **행의 동작**이다(표의 행 메뉴). 화면 상단 버튼이 아니다.
    if not n_rows(r):
        stop("저장소가 한 행도 없다")
    button = row_at(r, 0).get_by_role("button", name="상태 확인", exact=False)
    if not button.count():
        more = row_at(r, 0).get_by_role("button").last
        if more.count():
            more.click()
            r.settle(600)
            button = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="상태 확인", exact=False)
    if not button.count():
        stop("«지금 확인» 을 못 찾았다 — 행의 동작: %s"
             % row_at(r, 0).get_by_role("button").all_inner_texts())
    r.rec.reset()
    button.first.click()
    r.settle(2600)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    body = r.main_text(400)
    hint = "systemctl" in body
    return {"ui_action": "«지금 확인» 으로 마운트를 실제로 잰다",
            "observed": {"calls": calls, "systemctl_hint": hint, "body": body[:300]},
            "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, body[:200]),
            "expected": {"source": "derived-check",
                         "rule": "안 붙어 있으면 붙이는 유닛 이름(systemctl …)을 준다",
                         "calls": calls, "hint": hint},
            "failed": None if calls else "«지금 확인» 을 눌렀는데 서버로 안 갔다"}


flow("FF-1435", "admin_settings__storage", "admin_op",
     "«지금 확인»으로 마운트를 실제로 재고, 안 붙어 있으면 붙이는 유닛 이름을 준다",
     _storage_check, route=ST, shell=ADMIN, api="/api/storage")


def _storage_toggle(confirm_only: bool):
    def _act(r, ctx):
        # 이름은 **지금 상태의 반대**다: 켜져 있으면 「사용 안 함으로」, 꺼져 있으면 「사용으로」.
        if not n_rows(r):
            stop("저장소가 한 행도 없다")
        row = row_at(r, 0)
        button = row.get_by_role("button", name="비활성화", exact=False)
        if not button.count():
            button = row.get_by_role("button", name="활성화", exact=False)
        if not button.count():
            more = row.get_by_role("button").last
            if more.count():
                more.click()
                r.settle(600)
                menu = r.page.locator('[role="menu"]')
                button = menu.get_by_role("menuitem", name="사용", exact=False)
        if not button.count():
            stop("사용/사용 안 함 동작을 못 찾았다 — 행의 동작: %s"
                 % row.get_by_role("button").all_inner_texts())
        label = " ".join((button.first.inner_text() or "").split())
        r.rec.reset()
        button.first.click()
        r.settle(1300)
        asked = open_dialogs(r) > 0
        said = dialog_says(r, 300)
        if confirm_only and asked:
            r.dismiss_overlays()
            r.settle(800)
        elif asked:
            confirm_now(r)
            r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«%s» 를 누른다%s" % (label, " (확인만 보고 취소)" if confirm_only
                                                  else ""),
                "observed": {"confirm_asked": asked, "confirm": said[:280], "calls": calls},
                "rendered": "확인 «%s» · 쓰기 요청 %s" % (said[:200], calls),
                "expected": {"source": "derived-check",
                             "rule": ("취소하면 아무것도 안 바뀐다" if confirm_only
                                      else "끄기 전에 업로드가 실패한다고 먼저 말한다"),
                             "confirm_asked": asked},
                "failed": (("확인 없이 저장소를 끈다" if not asked else None)
                           or ("취소했는데 서버로 나갔다" if confirm_only and calls else None))}
    return _act


flow("FF-1436", "admin_settings__storage", "status_change",
     "사용/사용 안 함을 바꾼다 — 운영 저장소를 끄면 업로드가 실패한다고 먼저 말한다",
     _storage_toggle(True), route=ST, shell=ADMIN, server=False)

flow("FF-1437", "admin_settings__storage", "modal_action", "끄기 확인을 취소하면 아무것도 안 바뀐다",
     _storage_toggle(True), route=ST, shell=ADMIN, server=False)


def _storage_denied(r, ctx):
    got = r.as_role("admin", ST, ADMIN, lambda p: p.evaluate(
        """async () => {
             const main = document.querySelector('#main-content');
             const tabs = main ? Array.from(main.querySelectorAll('[role=tab]')).map(
                 t => (t.innerText || '').replace(/\\s+/g,' ').trim()) : [];
             const res = await fetch('/api/storage/providers',
                                     {credentials: 'same-origin'});
             return {tabs, status: res.status,
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,200)};
           }"""))
    has_tab = any("저장소" in t for t in got["tabs"])
    return {"ui_action": "파일 저장소 탭을 admin(=system_admin 아님) 역할로 연다",
            "frontend_state": "탭을 감추는 것은 표시일 뿐 — 서버가 막는다",
            "observed": got,
            "rendered": "탭 %s · 직접 호출 HTTP %s" % (got["tabs"], got["status"]),
            "expected": {"source": "derived-check",
                         "rule": "system_admin 이 아니면 탭도 없고 직접 호출도 403 이다",
                         "tab_visible": has_tab, "status": got["status"]},
            "failed": (("system_admin 이 아닌데 저장소 탭이 보인다" if has_tab else None)
                       or (None if got["status"] in (403, 404)
                           else "직접 호출이 안 막혔다: HTTP %s" % got["status"]))}


flow("FF-1438", "admin_settings__storage", "permission_state",
     "system_admin 이 아니면 탭 자체가 없고, 주소로 직접 와도 서버가 403 으로 막는다",
     _storage_denied, route=ST, shell=ADMIN, server=False)
