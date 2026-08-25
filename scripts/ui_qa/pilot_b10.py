"""B10 Settings — `/settings` 그릇과 세 탭 (W8 · S18).

이 원형이 답해야 하는 것: **바꿀 값과 그 값의 출처가 한 줄에 있는가**, 그리고 위험한
변경 앞에 확인이 서는가. 설정은 되돌리기 어려운 쓰기가 많은 화면이라, 이 표는 확인
문구를 **읽고 취소**한다 — 파일럿 점검이 운영 값을 바꾸지 않는다.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    back_forward, blocked_route, cache_key, click_then, close_modal, dialog_text, dialogs,
    flow, modal_open_close, open_row_modal, retry_from_error, stop, unquote_hash,
)

ADMIN = "/admin"


# ═══════════════════════════════════════════════════════════════════════════
# 그릇 — /settings
# ═══════════════════════════════════════════════════════════════════════════
def _tabs(r, ctx):
    tabs = r.page.locator('#main-content [role="tab"]')
    labels = [" ".join((tabs.nth(i).inner_text() or "").split()) for i in range(tabs.count())]
    before = r.hash_of()
    if tabs.count() > 1:
        tabs.nth(1).click()
        r.settle(1300)
    return {"ui_action": "탭을 옮긴다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"tabs": labels},
            "rendered": "탭 %s · 주소 «%s»" % (labels, r.hash_of()),
            "failed": None if "tab=" in r.hash_of()
                      else "탭을 옮겼는데 주소에 안 실렸다: %s" % r.hash_of()}


flow("FF-0477", "admin_settings", "navigation",
     "탭 전환(시스템 정책 / OS와 서비스 동작 / AI) — 주소의 ?tab=에 반영",
     _tabs, route="/settings", shell=ADMIN, server=False)


def _unknown_tab(r, ctx):
    r.goto("/settings?tab=존재하지않는탭", shell=ADMIN)
    r.settle(1200)
    corrected = r.hash_of()
    r.back()
    r.settle(1200)
    return {"ui_action": "모르는 탭 값으로 들어간다",
            "url_state": "/settings?tab=존재하지않는탭 → %s" % corrected,
            "frontend_state": "unknownTab → policy 로 replace",
            "observed": {"corrected": corrected, "after_back": r.hash_of()},
            "rendered": "정정된 주소 «%s» · 뒤로가기 뒤 «%s»" % (corrected, r.hash_of()),
            "failed": None if "존재하지않는탭" not in corrected
                      else "모르는 탭 값이 주소에 그대로 남았다"}


flow("FF-0478", "admin_settings", "deep_link",
     "?tab= 로 특정 탭 직접 진입, 모르는 값은 조용히 policy로 정정(히스토리 없이 replace)",
     _unknown_tab, shell=ADMIN, server=False)


def _role_denied_tab(r, ctx):
    seen = r.as_role("operator", "/settings?tab=os", ADMIN, lambda p: {
        "body": " ".join((p.locator("#main-content").inner_text() or "").split())[:160],
        "hash": p.url.split("#", 1)[-1],
    })
    denied = "권한" in seen.get("body", "")
    return {"ui_action": "system_admin 이 아닌 역할로 ?tab=os 로 들어간다",
            "frontend_state": "roleDenied → 주소는 그대로, 권한 없음 명시",
            "observed": seen,
            "rendered": "본문 «%s» · 주소 «%s»" % (seen.get("body"), seen.get("hash")),
            "failed": None if denied
                      else "권한이 없는데 첫 탭으로 조용히 떨어뜨렸거나 그대로 보여 준다"}


flow("FF-0479", "admin_settings", "permission_state",
     "system_admin이 아니면 탭 3개를 숨기고, 옛 주소로 들어오면 첫 탭으로 떨어뜨리지 않고 권한 없음을 명시",
     _role_denied_tab, route="/settings", shell=ADMIN, server=False)


def _session_expired(r, ctx):
    """열어 둔 화면에서 **세션이 끊겼을 때** 무엇을 보여 주는가.

    문서를 **다시 받지 않는다.** 새로 고치면 서버가 문서 요청 자체를 로그인으로 돌려보내니,
    그건 「이미 로그인 화면」이지 이 Flow 가 묻는 상황이 아니다. 실제로 그렇게 재면 앱이
    뜨지도 않은 «불러오는 중…» 을 읽고 그것을 제품 결함으로 적게 된다.

    앱이 떠 있는 채로 API 가 401 을 돌려주게 만들고, 화면 안에서 한 번 움직인다. 그러면
    `auth.jsx` 의 `onUnauthorized` 가 `["me"]` 를 다시 묻고 그것도 401 이라 `isError` 가
    켜진다 — 그 상태에서 화면이 무엇을 말하는지가 이 Flow 의 답이다.
    """
    def _deny(route):
        route.fulfill(status=401, content_type="application/json",
                      body='{"detail":"세션이 만료됐습니다."}')

    # 끊는 것은 **둘**이다. `/api/me` 하나만 끊으면 이미 받아 둔 값이 그대로 살아 있어
    # 아무 일도 안 일어나고(그 쿼리는 스스로 다시 묻지 않는다), 반대로 API 전부를 끊으면
    # 화면마다의 재시도가 겹쳐 그 폭풍이 화면을 덮는다. 실제 세션 만료의 모양은 그 사이다:
    # **어떤 API 하나가 401 을 내고**, 그것이 `onUnauthorized` 를 통해 `["me"]` 를 다시 묻게
    # 하고, 그 재질의도 401 이라 «만료» 가 확정된다(`auth.jsx` 의 같은 주석).
    patterns = ("**/api/me", "**/api/admin/settings**")
    for pattern in patterns:
        r.page.route(pattern, _deny)
    body, where = "", ""
    try:
        # 링크를 «누르지» 않는다 — 셸의 건너뛰기 링크처럼 안 보이는 앵커를 잡으면 30초를
        # 기다린다. 해시만 바꾸면 문서를 다시 받지 않고 라우터만 움직인다.
        r.page.evaluate("() => { window.location.hash = '#/settings'; }")
        r.settle(2000)
        # **문구를 기다린다.** `innerText` 를 폴링하면 다시 그리는 중간을 찍어 빈 문자열을
        # 읽고, 그것을 「화면이 아무 말도 안 한다」로 적게 된다 — 실제로 그렇게 같은 화면이
        # 실행마다 다른 답을 냈다. 기다리는 일은 Playwright 가 옳게 한다.
        seen = r.page.get_by_text("세션이 만료되었습니다", exact=False)
        try:
            seen.first.wait_for(state="visible", timeout=25_000)
        except Exception:  # noqa: BLE001 — 안 나오면 그 사실이 답이다
            pass
        try:
            body = " ".join(
                (r.page.locator("body").inner_text(timeout=5000) or "").split())[:220]
            where = r.page.url
        except Exception:  # noqa: BLE001
            body = ""
    finally:
        for pattern in patterns:
            r.page.unroute(pattern)
    shot = r.shot("ff0480-session-expired")
    denied = "권한이 없습니다" in body and "세션" not in body
    return {"ui_action": "앱이 떠 있는 채로 API 가 401 을 돌려주게 만든다",
            "frontend_state": "onUnauthorized → me 재질의 401 → auth.isError",
            "observed": {"body": body, "url": where},
            "screenshots": [shot],
            "rendered": "본문 «%s»" % body,
            "expected": {"source": "derived-check",
                         "rule": "세션 만료는 «권한 없음» 과 다르게, 다시 로그인할 길과 함께 말한다",
                         "expect": "로그인 또는 세션", "got": body[:120]},
            "failed": None if ("로그인" in body or "세션" in body)
                      else ("401 을 «권한이 없습니다» 로 오판했다: %s" % body if denied
                            else "세션이 끊겼는데 화면이 아무 말도 하지 않는다: «%s»" % body)}


flow("FF-0480", "admin_settings", "permission_state",
     "세션 만료(401)는 권한 없음과 구분해 재로그인 경로가 있는 ErrorState를 먼저 보여 준다",
     _session_expired, route="/settings", shell=ADMIN, api="/api/me")


def _denied_cta(r, ctx):
    seen = r.as_role("operator", "/settings?tab=ai", ADMIN, lambda p: {
        "links": [(" ".join((p.get_by_role("link").nth(i).inner_text() or "").split()))
                  for i in range(min(p.get_by_role("link").count(), 6))],
    })
    return {"ui_action": "권한 없음 화면의 다음 행동을 본다",
            "observed": seen,
            "rendered": "링크 %s" % seen.get("links"),
            "failed": None if any("대시보드" in x for x in seen.get("links", []))
                      else "권한 없음 화면에 갈 곳이 없다"}


flow("FF-0481", "admin_settings", "navigation", "권한 없음 화면에서 대시보드로 이동",
     _denied_cta, route="/settings", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 탭 — 시스템 정책
# ═══════════════════════════════════════════════════════════════════════════
def _policy_read(r, ctx):
    heads = r.page.locator("table thead th")
    labels = [" ".join((heads.nth(i).inner_text() or "").split()) for i in range(heads.count())]
    return {"ui_action": "시스템 정책 탭을 연다",
            "observed": {"columns": labels, "rows": r.rows()},
            "rendered": "열 %s · %d행" % (labels, r.rows()),
            "failed": None if r.rows() else "설정 표가 비었다"}


flow("FF-0736", "admin_settings__policy", "read",
     "설정 표 조회(유지보수 키와 전용 화면 키는 제외)",
     _policy_read, route="/settings?tab=policy", shell=ADMIN, api="/api/admin/settings")


def _setting_editor(r, ctx):
    open_row_modal(r, ctx, opener="button=수정")
    text = dialog_text(r)
    panel = r.page.locator('[role="dialog"]').last
    save = panel.get_by_role("button", name="저장")
    disabled = save.first.is_disabled() if save.count() else None
    close_modal(r)
    return {"ui_action": "«수정» 으로 값 편집 드로어를 연다",
            "observed": {"panel": text, "save_disabled_when_unchanged": disabled},
            "rendered": "패널 «%s» · 변경 없을 때 저장 %s"
                        % (text, "비활성" if disabled else "활성"),
            "failed": None if text else "편집 드로어가 비었다"}


flow("FF-0737", "admin_settings__policy", "row_action",
     "행 클릭 또는 '수정' 버튼으로 값 편집 드로어 열기",
     _setting_editor, route="/settings?tab=policy", shell=ADMIN, server=False)
flow("FF-0739", "admin_settings__policy", "settings_apply",
     "설정 값 저장(변경이 없으면 저장 버튼 비활성)",
     _setting_editor, route="/settings?tab=policy", shell=ADMIN, server=False)


def _tech_toggle(r, ctx):
    before = r.page.locator("table thead th").count()
    box = r.page.get_by_role("checkbox", name="기술 정보", exact=False)
    if not box.count():
        box = r.page.get_by_label("기술 정보", exact=False)
    if not box.count():
        stop("«기술 정보 보기» 토글이 없다")
    box.first.click()
    r.settle(900)
    after = r.page.locator("table thead th").count()
    return {"ui_action": "«기술 정보(설정 키) 보기» 를 켠다",
            "frontend_state": "showKeys=true",
            "observed": {"columns": {"before": before, "after": after}},
            "rendered": "열 %d개 → %d개" % (before, after),
            "failed": None if after > before else "켰는데 열이 안 늘었다"}


flow("FF-0738", "admin_settings__policy", "filter",
     "'기술 정보(설정 키) 보기' 토글로 원시 키 열을 넣고 뺀다",
     _tech_toggle, route="/settings?tab=policy", shell=ADMIN, server=False)


def _dry_run(r, ctx):
    button = r.page.get_by_role("button", name="미리 검증")
    if not button.count():
        stop("«미리 검증» 이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1800)
    calls = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«미리 검증» 을 누른다",
            "frontend_state": "dry-run",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "failed": None if calls else "미리 검증 요청이 없었다"}


flow("FF-0740", "admin_settings__policy", "admin_op", "저장 전 미리 검증(dry-run)",
     _dry_run, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _policy_validation(r, ctx):
    open_row_modal(r, ctx, opener="button=수정")
    panel = r.page.locator('[role="dialog"]').last
    # **칸 종류에 맞는 잘못된 값**을 넣는다. 숫자 칸에 글자를 넣으면 브라우저가 아예
    # 거부해서(«Cannot type text into input[type=number]») 제품이 아니라 하네스가 죽는다.
    text_box = panel.locator('input[type=text], textarea:not([aria-hidden="true"])')
    number_box = panel.locator("input[type=number]")
    if text_box.count():
        text_box.first.fill("!!!잘못된 값!!!")
    elif number_box.count():
        number_box.first.fill("999999999999")
    else:
        close_modal(r)
        stop("값 입력칸이 없다")
    r.settle(600)
    sent: list[str] = []
    r.page.on("request", lambda req: sent.append(req.url)
              if req.method in ("PATCH", "PUT", "POST") else None)
    save = r.page.get_by_role("button", name="저장")
    disabled = save.first.is_disabled() if save.count() else None
    if save.count() and not disabled:
        save.first.click()
        r.settle(1000)
    message = ""
    helper = panel.locator(".MuiFormHelperText-root, [role='alert']")
    if helper.count():
        message = " ".join((helper.first.inner_text() or "").split())[:110]
    still = bool(r.page.locator('[role="dialog"]').count())
    close_modal(r)
    return {"ui_action": "값 자리에 형식이 틀린 값을 넣고 저장한다",
            "observed": {"writes": len(sent), "message": message, "disabled": disabled},
            "rendered": "모달 유지 %s · 안내 «%s» · 쓰기 %d건" % (still, message, len(sent)),
            "failed": None if (disabled or still) else "형식이 틀렸는데 그대로 저장됐다"}


flow("FF-0741", "admin_settings__policy", "form_validation",
     "타입·정수 범위·JSON 형식·비밀번호/세션 정책·도메인 모양을 서버 왕복 전에 한국어로 잡는다",
     _policy_validation, route="/settings?tab=policy", shell=ADMIN, server=False)


def _json_mode(r, ctx):
    # 전환은 **표시 방법만** 바꾼다 — 저장된 값은 그대로여야 한다. 그것을 뒤에서 다시
    # 확인하려면 지금 그 줄이 무엇이었는지 적어 둬야 한다.
    first = r.page.locator("table tbody tr").first
    before_row = " ".join((first.inner_text() or "").split())[:40] if first.count() else ""
    open_row_modal(r, ctx, opener="button=수정")
    panel = r.page.locator('[role="dialog"]').last
    toggle = panel.get_by_role("button", name="JSON", exact=False)
    present = bool(toggle.count())
    text = ""
    if present:
        toggle.first.click()
        r.settle(700)
        text = dialog_text(r, 140)
    close_modal(r)
    return {"ui_action": "구조화 입력 ↔ JSON 직접 수정을 전환한다",
            "observed": {"toggle_present": present, "panel": text, "row_before": before_row},
            "rendered": "전환 %s · 패널 «%s»" % ("있음" if present else "없음", text),
            "cross": {"needle": before_row} if before_row else {},
            "notes": [] if present else ["이 설정 키는 구조화 입력이 아니라 전환이 없다"]}


flow("FF-0742", "admin_settings__policy", "inline_edit",
     "구조화된 입력 ↔ JSON 직접 수정(고급) 전환 — JSON이 깨져 있으면 되돌아가지 못하게 막는다",
     _json_mode, route="/settings?tab=policy", shell=ADMIN, server=False,
     cross=("@reload", ""))

flow("FF-0743", "admin_settings__policy", "modal_action",
     "보안 완화(도메인 제한 해제·비밀번호 정책 약화) 저장 직전 확인",
     _setting_editor, route="/settings?tab=policy", shell=ADMIN, server=False)


def _dirty_guard(r, ctx):
    open_row_modal(r, ctx, opener="button=수정")
    panel = r.page.locator('[role="dialog"]').last
    # 칸 종류에 맞는 값을 넣는다 — 숫자 칸에 글자를 넣으면 브라우저가 거부해서 제품이
    # 아니라 표가 죽는다(`_policy_validation` 의 같은 주석).
    text_box = panel.locator('input[type=text], textarea:not([aria-hidden="true"])')
    number_box = panel.locator("input[type=number]")
    if text_box.count():
        text_box.first.fill("변경함")
    elif number_box.count():
        number_box.first.fill("42")
    r.settle(400)
    r.press("Escape")
    r.settle(700)
    asked = bool(r.page.locator('[role="dialog"]').last
                 .get_by_role("button", name="닫기").count())
    close_modal(r)
    return {"ui_action": "값을 바꾼 채 Esc 를 누른다",
            "observed": {"confirm_shown": asked},
            "rendered": "확인 창 %s" % ("떴다" if asked else "안 떴다"),
            "failed": None if asked else "바꾼 값이 남았는데 그냥 닫혔다"}


flow("FF-0744", "admin_settings__policy", "modal_action",
     "미저장 변경 상태로 닫으려 하면 확인, 저장 중에는 닫기 자체를 막는다",
     _dirty_guard, route="/settings?tab=policy", shell=ADMIN, server=False)


def _versions(r, ctx):
    button = r.page.get_by_role("button", name="버전 기록")
    if not button.count():
        stop("«버전 기록» 이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1800)
    text = dialog_text(r)
    calls = [c for c in r.rec.calls if c["method"] == "GET"]
    close_modal(r)
    return {"ui_action": "«버전 기록» 을 연다",
            "observed": {"panel": text,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "패널 «%s»" % text,
            "failed": None if text else "버전 기록 패널이 비었다"}


flow("FF-0745", "admin_settings__policy", "read", "설정 값 버전 기록 조회",
     _versions, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")
flow("FF-0746", "admin_settings__policy", "admin_op",
     "이 버전으로 롤백(롤백도 보안 완화면 같은 확인을 거친다)",
     _versions, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _maintenance_toggle(r, ctx):
    button = r.in_main("button", "유지보수 모드")
    if not button.count():
        stop("유지보수 모드 토글이 없다")
    label = " ".join((button.first.inner_text() or "").split())[:40]
    r.rec.reset()
    button.first.click()
    r.settle(1200)
    text = dialog_text(r)
    cancel = r.page.get_by_role("button", name="취소")
    if cancel.count():
        cancel.first.click()
        r.settle(600)
    reads = [c for c in r.rec.calls if c["method"] == "GET"]
    writes = [c for c in r.rec.calls if c["method"] in ("POST", "PATCH")]
    return {"ui_action": "«%s» 를 누르고 확인 문구를 읽은 뒤 취소한다" % label,
            "frontend_state": "확인 직전 서버 최신 상태를 다시 읽는다",
            "observed": {"confirm": text, "reads_before_confirm": len(reads),
                         "writes_before_confirm": len(writes), "label": label},
            "rendered": "확인 문구 «%s»" % text,
            # 취소했으니 **아무것도 안 바뀐 것**이 계약이다 — 새로 읽었을 때 버튼 이름이
            # 그대로면 유지보수 모드도 그대로다(켜졌다면 이름이 반대로 바뀐다).
            "cross": {"needle": label} if label else {},
            "failed": None if (text and not writes)
                      else "확인 문구가 없거나 확인 전에 이미 바꿨다"}


flow("FF-0747", "admin_settings__policy", "status_change", "유지보수 모드 켜고 끄기",
     _maintenance_toggle, route="/settings?tab=policy", shell=ADMIN, api="/api/admin",
     cross=("@reload", ""))
flow("FF-0748", "admin_settings__policy", "modal_action",
     "전환 직전 서버 최신 상태를 다시 읽어 확인 문구와 실제 전환을 일치시킨다",
     _maintenance_toggle, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _notice_save(r, ctx):
    area = r.page.get_by_label("점검 공지", exact=False)
    if not area.count():
        area = r.page.locator("#main-content textarea").last
    if not area.count():
        stop("점검 공지 칸이 없다")
    area.first.fill("S18 파일럿 점검 공지입니다.")
    r.settle(500)
    r.rec.reset()
    save = r.page.get_by_role("button", name="공지 저장")
    if not save.count():
        stop("«공지 저장» 이 없다")
    save.first.click()
    r.settle(1800)
    calls = [c for c in r.rec.calls if c["method"] in ("POST", "PATCH", "PUT")]
    return {"ui_action": "점검 공지를 쓰고 저장한다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "failed": None if calls else "공지 저장 요청이 없었다"}


flow("FF-0749", "admin_settings__policy", "settings_apply", "점검 공지 저장",
     _notice_save, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _notice_dry_run(r, ctx):
    button = r.page.get_by_role("button", name="미리 검증")
    if not button.count():
        stop("«미리 검증» 이 없다")
    r.rec.reset()
    button.last.click()
    r.settle(1800)
    calls = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "점검 공지 «미리 검증» 을 누른다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "failed": None if calls else "미리 검증 요청이 없었다"}


flow("FF-0750", "admin_settings__policy", "admin_op", "점검 공지 미리 검증",
     _notice_dry_run, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _empty_notice(r, ctx):
    area = r.page.get_by_label("점검 공지", exact=False)
    if not area.count():
        area = r.page.locator("#main-content textarea").last
    area.first.fill("")
    r.settle(600)
    sent: list[str] = []
    r.page.on("request", lambda req: sent.append(req.url)
              if req.method in ("POST", "PATCH", "PUT") else None)
    save = r.page.get_by_role("button", name="공지 저장")
    disabled = save.first.is_disabled() if save.count() else None
    if save.count() and not disabled:
        save.first.click()
        r.settle(1000)
    message = ""
    helper = r.page.locator("#main-content .MuiFormHelperText-root")
    if helper.count():
        message = " ".join((helper.last.inner_text() or "").split())[:110]
    return {"ui_action": "공지를 비우고 저장한다",
            "observed": {"writes": len(sent), "message": message, "disabled": disabled},
            "rendered": "저장 %s · 안내 «%s» · 쓰기 %d건"
                        % ("비활성" if disabled else "활성", message, len(sent)),
            "failed": None if (disabled or message)
                      else "빈 공지를 막지도, 이유를 말하지도 않는다"}


flow("FF-0751", "admin_settings__policy", "form_validation",
     "빈 공지는 저장할 수 없고 그 이유를 칸 아래에 남긴다",
     _empty_notice, route="/settings?tab=policy", shell=ADMIN, server=False)


def _notice_revert(r, ctx):
    area = r.page.get_by_label("점검 공지", exact=False)
    if not area.count():
        area = r.page.locator("#main-content textarea").last
    area.first.fill("되돌리기 확인용 초안")
    r.settle(500)
    button = r.page.get_by_role("button", name="되돌리기")
    if not button.count():
        stop("«되돌리기» 가 없다")
    button.first.click()
    r.settle(1200)
    return {"ui_action": "초안을 쓴 뒤 «되돌리기» 를 누른다",
            "observed": {"value": area.first.input_value()[:60]},
            "rendered": "칸 값 «%s»" % area.first.input_value()[:60],
            "failed": None if "되돌리기 확인용" not in area.first.input_value()
                      else "되돌렸는데 초안이 그대로다"}


flow("FF-0752", "admin_settings__policy", "edit", "공지 초안 되돌리기(서버 값으로 복구)",
     _notice_revert, route="/settings?tab=policy", shell=ADMIN, server=False)

flow("FF-0753", "admin_settings__policy", "read",
     "유지보수 모드 켜고 끈 이력·점검 공지 버전 기록 열기",
     click_then("button=변경 기록"), route="/settings?tab=policy", shell=ADMIN,
     api="/api/admin")


def _refresh_state(r, ctx):
    button = r.page.get_by_role("button", name="새로고침")
    if not button.count():
        stop("«새로고침» 이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1600)
    calls = [c for c in r.rec.calls if c["method"] == "GET"]
    return {"ui_action": "«새로고침» 을 누른다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "failed": None if calls else "새로고침이 아무것도 안 불렀다"}


flow("FF-0754", "admin_settings__policy", "refresh", "유지보수 상태 수동 새로고침(갱신 시각 표시)",
     _refresh_state, route="/settings?tab=policy", shell=ADMIN, api="/api/admin")


def _readonly_role(r, ctx):
    seen = r.as_role("auditor", "/settings?tab=policy", ADMIN, lambda p: {
        "edit_buttons": p.get_by_role("button", name="수정").count(),
        "disabled": p.locator("#main-content button:disabled").count(),
        "described": p.locator("#main-content [aria-describedby]").count(),
    })
    return {"ui_action": "읽기 전용 역할로 같은 탭을 연다",
            "frontend_state": "canWrite=false → 숨기지 않고 비활성 + 사유",
            "observed": seen,
            "rendered": "«수정» %d개 · 비활성 %d개 · 사유 연결 %d개"
                        % (seen.get("edit_buttons", 0), seen.get("disabled", 0),
                           seen.get("described", 0)),
            "failed": None if seen.get("disabled", 0)
                      else "쓰기 권한이 없는데 비활성 컨트롤이 하나도 없다"}


flow("FF-0755", "admin_settings__policy", "permission_state",
     "쓰기 권한이 없으면 컨트롤을 숨기지 않고 비활성 + 사유를 aria-describedby로 잇는다",
     _readonly_role, route="/settings?tab=policy", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 탭 — OS와 서비스 동작
# ═══════════════════════════════════════════════════════════════════════════
def _os_read(r, ctx):
    sections = r.page.locator("#main-content h2, #main-content h3")
    labels = [" ".join((sections.nth(i).inner_text() or "").split())
              for i in range(min(sections.count(), 8))]
    return {"ui_action": "OS와 서비스 동작 탭을 연다",
            "observed": {"sections": labels},
            "rendered": "구역 %s · 본문 «%s»" % (labels, r.main_text(110)),
            "failed": None if labels else "구역이 하나도 없다"}


flow("FF-0756", "admin_settings__os", "read",
     "시스템 정보·서비스 상태·도우미가 아는 동작 목록 조회",
     _os_read, route="/settings?tab=os", shell=ADMIN, api="/api/admin")


def _os_form(r, ctx):
    button = r.in_main("button", "수정")
    if not button.count():
        stop("«수정» 이 없다")
    if button.first.is_disabled():
        return {"ui_action": "항목별 변경 폼을 연다",
                "frontend_state": "도우미가 없어 변경이 잠겨 있다",
                "observed": {"disabled": True, "body": r.main_text(160)},
                "rendered": "«수정» 이 비활성이다 — 이 환경에는 시스템 설정 도우미가 없다",
                "expected": {"source": "derived-check",
                             "rule": "도우미가 없으면 변경 폼을 열 수 없다(FF-0763 과 같은 사실)",
                             "disabled": True},
                "notes": ["폼을 열 수 없는 것이 이 환경의 정답이다"]}
    button.first.click()
    r.settle(900)
    text = dialog_text(r)
    dialog = r.page.locator('[role="dialog"]').last
    fields = dialog.locator("input, select, textarea").count() if dialog.count() else 0
    close_modal(r)
    return {"ui_action": "항목별 변경 폼을 연다",
            "observed": {"panel": text, "fields": fields},
            "rendered": "폼 «%s» · 칸 %d개" % (text, fields),
            "failed": None if fields else "변경 폼에 입력 칸이 없다"}


flow("FF-0757", "admin_settings__os", "settings_apply",
     "항목별 변경 폼 제출(타임존·NTP·호스트 이름/FQDN·DNS·프록시·인증서)",
     _os_form, route="/settings?tab=os", shell=ADMIN, server=False)
flow("FF-0758", "admin_settings__os", "form_validation",
     "폼 필드의 required와 showIf(사용 체크가 켜졌을 때만 서버·주소·예외 칸이 나온다)",
     _os_form, route="/settings?tab=os", shell=ADMIN, server=False)


def _cert_confirm(r, ctx):
    button = r.in_main("button", "교체")
    if not button.count():
        stop("«교체» 가 없다")
    if button.first.is_disabled():
        return {"ui_action": "«교체» 상태를 본다",
                "frontend_state": "도우미가 없어 잠겨 있다",
                "observed": {"disabled": True},
                "rendered": "«교체» 가 비활성이다 — 누를 수 없으니 확인 창도 없다",
                "expected": {"source": "derived-check",
                             "rule": "도우미가 없으면 인증서 교체를 시작할 수 없다",
                             "disabled": True},
                "notes": ["이 환경에는 시스템 설정 도우미가 없다"]}
    r.rec.reset()
    button.first.click()
    r.settle(900)
    text = dialog_text(r)
    close_modal(r)
    writes = [c for c in r.rec.calls if c["method"] in ("POST", "PUT")]
    return {"ui_action": "«교체» 를 누르고 확인 문구를 읽은 뒤 닫는다",
            "observed": {"confirm": text, "writes_before_confirm": len(writes)},
            "rendered": "확인 문구 «%s»" % text,
            "failed": None if not writes else "확인 전에 이미 보냈다"}


flow("FF-0759", "admin_settings__os", "modal_action",
     "TLS 인증서 교체 전 확인(검사 실패 시 원복한다는 사실을 명시)",
     _cert_confirm, route="/settings?tab=os", shell=ADMIN, server=False)


def _service_restart(r, ctx):
    button = r.in_main("button", "재시작")
    if not button.count():
        menu = r.page.get_by_label("더 보기")
        if menu.count():
            menu.first.click()
            r.settle(500)
            button = r.page.get_by_role("menuitem", name="재시작")
    if not button.count():
        return {"ui_action": "«재시작» 을 찾는다",
                "notes": ["이 환경에는 관리 대상 서비스가 없어 재시작 버튼이 없다"],
                "rendered": "본문 «%s»" % r.main_text(110)}
    r.rec.reset()
    button.first.click()
    r.settle(900)
    text = dialog_text(r)
    close_modal(r)
    writes = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«재시작» 을 누르고 확인 문구를 읽은 뒤 닫는다",
            "observed": {"confirm": text, "writes_before_confirm": len(writes)},
            "rendered": "확인 문구 «%s»" % text,
            "failed": None if not writes else "확인 전에 이미 재시작을 보냈다"}


flow("FF-0760", "admin_settings__os", "admin_op", "관리 대상 서비스 재시작",
     _service_restart, route="/settings?tab=os", shell=ADMIN, server=False)
flow("FF-0761", "admin_settings__os", "modal_action", "재시작 전 '그 기능이 잠시 멈춘다' 확인",
     _service_restart, route="/settings?tab=os", shell=ADMIN, server=False)
flow("FF-0762", "admin_settings__os", "overflow_action",
     "실행 중 서비스의 재시작은 넘침 메뉴로 내리고, 멈춰 있으면 버튼으로 꺼낸다",
     _service_restart, route="/settings?tab=os", shell=ADMIN, server=False)


def _helper_absent(r, ctx):
    body = r.main_text(200)
    disabled = r.page.locator("#main-content button:disabled").count()
    return {"ui_action": "도우미가 없을 때 화면이 무엇을 말하는지 본다",
            "observed": {"body": body, "disabled_controls": disabled},
            "rendered": "본문 «%s» · 비활성 컨트롤 %d개" % (body, disabled),
            "failed": None if body else "이유를 말하는 문장이 없다"}


flow("FF-0763", "admin_settings__os", "permission_state",
     "시스템 설정 도우미가 없으면 값도 못 읽고 변경 버튼도 비활성 + 무엇을 해야 하는지 안내",
     _helper_absent, route="/settings?tab=os", shell=ADMIN, server=False)

flow("FF-0764", "admin_settings__os", "refresh",
     "조회 실패 시 다시 시도, 실행 후에는 상태를 항상 다시 읽는다",
     retry_from_error("/api/admin/system", "OS 설정"), route="/settings?tab=os",
     shell=ADMIN, api="/api/admin")


# ═══════════════════════════════════════════════════════════════════════════
# 탭 — AI
# ═══════════════════════════════════════════════════════════════════════════
def _ai_effective(r, ctx):
    panel = r.page.locator('[data-testid="llm-effective"]')
    if not panel.count():
        stop("«지금 적용 중인 값» 이 없다")
    text = " ".join((panel.first.inner_text() or "").split())[:200]
    return {"ui_action": "AI 탭을 연다",
            "observed": {"effective": text},
            "rendered": "지금 적용 중인 값 «%s»" % text,
            "failed": None if text else "적용 중인 값이 비었다"}


flow("FF-0776", "admin_settings__ai", "read",
     "지금 적용 중인 값·한도·연결 확인 여부·로그인 안내 조회",
     _ai_effective, route="/settings?tab=ai", shell=ADMIN, api="/api/admin")


def _ai_saved(r, ctx):
    grid = r.page.locator('[data-testid="llm-settings-grid"]')
    fields = grid.locator("input, [role=combobox]").count() if grid.count() else 0
    return {"ui_action": "저장된 설정 값을 받는다",
            "observed": {"fields": fields},
            "rendered": "설정 칸 %d개" % fields,
            "failed": None if fields else "설정 칸이 하나도 없다"}


flow("FF-0777", "admin_settings__ai", "read",
     "저장된 설정 값 조회(다른 설정 화면과 같은 캐시 키를 공유)",
     _ai_saved, route="/settings?tab=ai", shell=ADMIN, api="/api/admin")


def _ai_draft(r, ctx):
    box = r.page.get_by_label("모델", exact=False)
    if not box.count():
        stop("«모델» 칸이 없다")
    before = box.first.input_value()
    box.first.fill("s18-pilot-model")
    r.settle(600)
    save = r.page.get_by_role("button", name="저장")
    revert = r.page.get_by_role("button", name="되돌리기")
    return {"ui_action": "«모델» 을 초안으로 바꾼다",
            "frontend_state": "draft.llm_model=s18-pilot-model",
            "observed": {"before": before,
                         "save_enabled": bool(save.count()) and not save.first.is_disabled(),
                         "revert_enabled": bool(revert.count()) and not revert.first.is_disabled()},
            "rendered": "칸 «%s» → «s18-pilot-model»" % before,
            # **초안은 초안이다.** 저장을 안 눌렀으니 새로 읽으면 그 값이 없어야 한다 —
            # 이 대조가 「초안(draft)」이라는 낱말이 지키는 유일한 계약이다.
            "cross": {"absent": "s18-pilot-model"},
            "failed": None if (save.count() and not save.first.is_disabled())
                      else "초안이 생겼는데 저장이 비활성이다"}


flow("FF-0778", "admin_settings__ai", "inline_edit",
     "사용 여부·백엔드·모델·제한 시간·동시 실행 수·실행 파일을 초안(draft)으로 편집",
     _ai_draft, route="/settings?tab=ai", shell=ADMIN, server=False,
     cross=("@reload", ""))


def _ai_save(r, ctx):
    box = r.page.get_by_label("모델", exact=False)
    box.first.fill("s18-pilot-model")
    r.settle(600)
    r.rec.reset()
    save = r.page.get_by_role("button", name="저장")
    save.first.click()
    r.settle(2000)
    calls = [c for c in r.rec.calls if c["method"] in ("POST", "PATCH", "PUT")]
    return {"ui_action": "초안을 저장한다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:4]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "failed": None if calls else "저장했는데 요청이 없었다"}


flow("FF-0779", "admin_settings__ai", "settings_apply",
     "바뀐 키만 순서대로 저장하고, 실패한 필드 값은 초안에 그대로 남긴다",
     _ai_save, route="/settings?tab=ai", shell=ADMIN, api="/api/admin")


def _ai_revert(r, ctx):
    box = r.page.get_by_label("모델", exact=False)
    box.first.fill("버릴 초안")
    r.settle(600)
    revert = r.page.get_by_role("button", name="되돌리기")
    if not revert.count():
        stop("«되돌리기» 가 없다")
    revert.first.click()
    r.settle(1200)
    return {"ui_action": "«되돌리기» 로 초안을 버린다",
            "observed": {"value": box.first.input_value()},
            "rendered": "칸 «%s»" % box.first.input_value(),
            "failed": None if box.first.input_value() != "버릴 초안"
                      else "되돌렸는데 초안이 그대로다"}


flow("FF-0780", "admin_settings__ai", "edit", "되돌리기(초안 전체 폐기)",
     _ai_revert, route="/settings?tab=ai", shell=ADMIN, server=False)


def _ai_no_draft(r, ctx):
    save = r.page.get_by_role("button", name="저장")
    revert = r.page.get_by_role("button", name="되돌리기")
    save_disabled = save.first.is_disabled() if save.count() else None
    revert_disabled = revert.first.is_disabled() if revert.count() else None
    return {"ui_action": "아무것도 안 바꾼 상태에서 저장·되돌리기를 본다",
            "observed": {"save_disabled": save_disabled, "revert_disabled": revert_disabled},
            "rendered": "저장 %s · 되돌리기 %s"
                        % ("비활성" if save_disabled else "활성",
                           "비활성" if revert_disabled else "활성"),
            "failed": None if (save_disabled and revert_disabled)
                      else "초안이 없는데 저장·되돌리기가 눌린다"}


flow("FF-0781", "admin_settings__ai", "form_validation", "초안이 없으면 저장·되돌리기가 비활성",
     _ai_no_draft, route="/settings?tab=ai", shell=ADMIN, server=False)


def _ai_test(r, ctx):
    button = r.page.get_by_role("button", name="연결 테스트")
    if not button.count():
        stop("«연결 테스트» 가 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2500)
    posts = [c for c in r.rec.calls if c["method"] == "POST"]
    gets = [c for c in r.rec.calls if c["method"] == "GET" and "job" in c["path"]]
    return {"ui_action": "«연결 테스트» 를 누른다",
            "frontend_state": "작업 큐에 맡기고 결과만 되묻는다",
            "observed": {"posts": [(c["path"], c["status"]) for c in posts][:2],
                         "polls": len(gets)},
            "rendered": "POST %d건 · 결과 조회 %d회 · 본문 «%s»"
                        % (len(posts), len(gets), r.main_text(120)),
            "failed": None if posts else "테스트 요청이 안 나갔다"}


flow("FF-0782", "admin_settings__ai", "admin_op",
     "연결 테스트를 작업 큐에 맡긴다(웹 요청에서 기다리지 않는다)",
     _ai_test, route="/settings?tab=ai", shell=ADMIN, api="/api/admin")
flow("FF-0783", "admin_settings__ai", "read",
     "테스트 잡 결과를 끝날 때까지만 2초 간격으로 다시 묻는다",
     _ai_test, route="/settings?tab=ai", shell=ADMIN, api="/api/admin")

flow("FF-0784", "admin_settings__ai", "refresh", "조회 실패 시 다시 시도",
     retry_from_error("/api/admin/llm", "AI 설정"), route="/settings?tab=ai",
     shell=ADMIN, api="/api/admin")


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
#
# 이 화면의 «조건» 은 목록 질의가 아니라 **표시 방법**이다(기술 정보 열 토글). 그래서 다섯
# 축의 답도 그 성격을 따른다 — 쪽이 없고, 주소에 실리는 것은 탭 하나뿐이다. 「없다」를
# 확인하는 것도 확인이다: 없다고 적어 두면 다음 사람이 그 자리를 다시 뒤지지 않는다.
def _policy_axis(name: str, says: str, check):
    def _act(r, ctx):
        return check(r, ctx, name, says)
    return _act


def _tech_toggle_twice(r, ctx):
    """토글을 빠르게 두 번 눌러도 **마지막 상태만** 남는다(경합)."""
    box = r.page.get_by_role("checkbox", name="기술 정보", exact=False)
    if not box.count():
        box = r.page.get_by_label("기술 정보", exact=False)
    if not box.count():
        stop("«기술 정보 보기» 토글이 없다")
    first_cols = r.page.locator("table thead th").count()
    box.first.click()
    r.page.wait_for_timeout(120)
    box.first.click()
    r.settle(1200)
    after = r.page.locator("table thead th").count()
    return {"ui_action": "기술 정보 토글을 빠르게 두 번 누른다",
            "frontend_state": "showKeys=false (마지막 입력)",
            "observed": {"columns": {"before": first_cols, "after": after}},
            "rendered": "열 %d개 → %d개" % (first_cols, after),
            "expected": {"source": "derived-check",
                         "rule": "빠르게 두 번 눌러도 마지막 상태만 남는다",
                         "expect": first_cols, "got": after},
            "failed": None if after == first_cols
                      else "두 번 눌렀는데 원래대로 안 돌아왔다(%d → %d)" % (first_cols, after)}


def _policy_no_page(r, ctx):
    """설정 표는 전량을 한 번에 받는다 — 쪽이 없고 주소에 `page=` 가 안 붙는다."""
    rows = r.rows()
    here = unquote_hash(r.hash_of())
    pager_button = r.page.get_by_role("button", name="다음")
    return {"ui_action": "설정 표의 주소와 페이저를 본다",
            "frontend_state": "설정 표는 전량을 한 번에 받는다",
            "observed": {"rows": rows, "hash": here, "pager_buttons": pager_button.count()},
            "rendered": "표 %d행 · 주소 «%s» · 페이저 %d개" % (rows, here, pager_button.count()),
            "expected": {"source": "derived-check",
                         "rule": "쪽이 없는 화면이라 주소에 page 가 안 붙는다",
                         "expect": "page= 없음", "got": here},
            "failed": None if "page=" not in here
                      else "쪽이 없는 화면인데 주소에 page 가 붙었다: %s" % here}


def _policy_compound(r, ctx):
    """표시 조건(기술 정보 열)과 그릇 조건(`?tab=`)이 **서로를 덮지 않는다**."""
    before = r.page.locator("table thead th").count()
    box = r.page.get_by_role("checkbox", name="기술 정보", exact=False)
    if not box.count():
        box = r.page.get_by_label("기술 정보", exact=False)
    if not box.count():
        stop("«기술 정보 보기» 토글이 없다")
    box.first.click()
    r.settle(1000)
    widened = r.page.locator("table thead th").count()
    here = unquote_hash(r.hash_of())
    return {"ui_action": "기술 정보 열을 켠 채 주소를 본다",
            "frontend_state": "showKeys=true & tab=policy",
            "observed": {"columns": {"before": before, "after": widened}, "hash": here},
            "rendered": "열 %d개 → %d개 · 주소 «%s»" % (before, widened, here),
            "expected": {"source": "derived-check",
                         "rule": "표시 조건을 켜도 그릇 조건(tab)은 그대로다",
                         "expect": "tab=policy", "got": here},
            "failed": None if (widened > before and "tab=policy" in here)
                      else "열이 안 늘었거나 탭 조건이 사라졌다(%d → %d · %s)"
                           % (before, widened, here)}


flow("FF-1420", "admin_settings__policy", "filter",
     "복합 — 표시 조건(기술 정보 열)과 그릇 조건(tab)이 서로를 덮지 않는다",
     _policy_compound, route="/settings?tab=policy", shell=ADMIN, server=False)
flow("FF-1421", "admin_settings__policy", "filter",
     "쪽 초기화가 필요 없다 — 설정 표는 전량을 한 번에 받는다",
     _policy_no_page, route="/settings?tab=policy", shell=ADMIN, server=False)
flow("FF-1422", "admin_settings__policy", "filter",
     "토글을 빠르게 두 번 눌러도 마지막 상태만 남는다(경합)",
     _tech_toggle_twice, route="/settings?tab=policy", shell=ADMIN, server=False)
flow("FF-1423", "admin_settings__policy", "filter",
     "탭을 오가도 각 탭이 자기 것을 말한다(캐시 키)",
     cache_key("/settings?tab=policy", "/settings?tab=ai", shell=ADMIN),
     shell=ADMIN, api="/api/admin")
flow("FF-1424", "admin_settings__policy", "filter",
     "뒤로가기가 앞 탭의 조건으로 돌아온다",
     back_forward("/settings?tab=policy", "/settings?tab=ai", shell=ADMIN),
     shell=ADMIN, api="/api/admin")
