"""S21 — registry 가 그리는 관리자 목록 화면들 (W14).

어휘는 `s21_admin_kit.py` 에 있다. 여기에는 **화면마다 다른 이름**만 적는다.

한 가지는 여기서 못 박는다: **없어진 기능의 Flow 는 되살리지 않는다.** 원장에 남아 있던
「러너 상세로 간다」(FF-1035) · 「이 정책을 쓰는 템플릿」(FF-0989) · 「유형(n8n/Notion)으로
좁힌다」(FF-0895)는 S11 과 S20 이 그 기능을 걷어서 지금 제품에 **없다**. 없는 것을 누르는
Flow 를 새로 만들면 원장이 제품과 다른 것을 말하게 된다(D-299 의 C1c 와 같은 규율).
"""

from __future__ import annotations

from scripts.ui_qa.s21_admin_kit import (  # noqa: F401
    ADMIN, ds_action, ds_clear, ds_create, ds_deep_link, ds_edit, ds_filter, ds_navigate,
    ds_open_row, ds_overflow, ds_pager, ds_permission, ds_read, ds_required, ds_saved_view,
    ds_search,
)
from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog, open_dialogs,
    retry_from_error, row_at, row_name, rows_of, sort_by, stop, switch_tab,
)

P = "/api/admin/prompts"


# ═══════════════════════════════════════════════════════════════════════════
# /prompts
# ═══════════════════════════════════════════════════════════════════════════
def _name_autocomplete(r, ctx):
    box = r.page.get_by_label("이름(정확히)", exact=False)
    if not box.count():
        box = r.page.locator("#main-content input[list]")
    if not box.count():
        stop("«이름(정확히)» 칸이 없다")
    listed = box.first.get_attribute("list")
    options = r.page.locator("datalist#%s option" % listed) if listed else None
    names = ([options.nth(i).get_attribute("value") for i in range(min(options.count(), 6))]
             if options and options.count() else [])
    before = n_rows(r)
    if names:
        box.first.fill(names[0])
        r.settle(1800)
    return {"ui_action": "«이름(정확히)» 의 자동완성 후보를 보고 하나를 고른다",
            "frontend_state": "datalist 가 지금 쪽의 이름으로 채워진다",
            "observed": {"datalist": listed, "options": names,
                         "rows": {"before": before, "after": n_rows(r)}},
            "rendered": "후보 %s · %d행 → %d행" % (names, before, n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "지금 쪽의 이름이 자동완성 후보로 나온다", "got": names},
            "failed": None if names else "자동완성 후보가 하나도 없다"}


flow("FF-1019", "admin_prompts", "combobox",
     "'이름(정확히)' 필터에서 현재 페이지의 프롬프트 이름을 자동완성으로 고른다",
     _name_autocomplete, route="/prompts", shell=ADMIN, api=P)

flow("FF-1020", "admin_prompts", "filter", "상태(초안/테스트/검토/발행됨/보관됨)로 좁힌다 — 기본값은 '발행됨'",
     ds_filter("상태", "초안", P, axis="status"), route="/prompts", shell=ADMIN, api=P)

flow("FF-1021", "admin_prompts", "filter", "'필터 지우기'로 필터를 한 번에 해제한다",
     ds_clear("상태", "초안"), route="/prompts", shell=ADMIN, api=P)

flow("FF-1022", "admin_prompts", "filter", "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route="/prompts", shell=ADMIN, server=False)

flow("FF-1023", "admin_prompts", "pagination", "이전/다음으로 페이지를 넘긴다(500건 상한 경고와 함께)",
     ds_pager(P), route="/prompts", shell=ADMIN, server=False)

flow("FF-1024", "admin_prompts", "read", "행을 눌러 프롬프트 상세(지시문 내용·작성자·발행 시각)를 연다",
     ds_open_row(("프롬프트 ID",)), route="/prompts", shell=ADMIN, server=False)

flow("FF-1025", "admin_prompts", "create", "'프롬프트 추가'로 이름·용도·지시문을 적어 초안을 만든다",
     ds_create("프롬프트 추가",
               {"이름": "S21 점검 프롬프트", "프롬프트 내용": "이 글을 한 문장으로 요약해 주세요."}),
     route="/prompts", shell=ADMIN, api=P, cross=("/prompts?status=draft", ADMIN))

flow("FF-1026", "admin_prompts", "form_validation", "이름·프롬프트 내용을 비우면 제출 전에 막힌다",
     ds_required("프롬프트 추가"), route="/prompts", shell=ADMIN, server=False)

flow("FF-1027", "admin_prompts", "edit", "초안 상태일 때만 '수정'으로 내용·용도를 바꾼다",
     ds_edit("프롬프트 내용"), route="/prompts?status=draft", shell=ADMIN, api=P)

flow("FF-1028", "admin_prompts", "status_change",
     "'테스트로'·'검토로'·'초안으로 되돌리기'로 버전 상태를 옮긴다(확인 후)",
     ds_action("테스트로"), route="/prompts?status=draft", shell=ADMIN, api=P)

flow("FF-1029", "admin_prompts", "status_change",
     "'발행'으로 이 버전을 실사용으로 올린다(같은 이름의 이전 발행본은 자동 보관)",
     ds_action("검토로"), route="/prompts?status=", shell=ADMIN, api=P)

flow("FF-1030", "admin_prompts", "status_change", "'보관'으로 더 이상 쓰이지 않게 한다(확인 후)",
     ds_action("보관"), route="/prompts?status=", shell=ADMIN, api=P)

flow("FF-1031", "admin_prompts", "create", "'새 버전'으로 편집 가능한 초안을 만들고 그 자리에서 이어 편집한다",
     ds_action("새 버전", confirm=False), route="/prompts?status=", shell=ADMIN,
     api=P)


def _version_history(r, ctx):
    if not n_rows(r):
        stop("행이 없다")
    name = row_name(r, 0)
    row_at(r, 0).click()
    r.settle(1600)
    detail = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    target = detail.get_by_role("button", name="버전 기록", exact=False)
    if not target.count():
        more = detail.get_by_role("button", name="더 보기", exact=False)
        if more.count():
            more.first.click()
            r.settle(700)
            target = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="버전 기록", exact=False)
    if not target.count():
        said = dialog_says(r, 220)
        r.dismiss_overlays()
        stop("«버전 기록» 을 못 찾았다 — 상세: %s" % said[:170])
    target.first.click()
    r.settle(2000)
    text = dialog_says(r, 300)
    buttons = open_dialog(r).get_by_role("button") if open_dialogs(r) else None
    labels = ([" ".join((buttons.nth(i).inner_text() or "").split())
               for i in range(min(buttons.count(), 12))] if buttons else [])
    ctx["version_drawer"] = labels
    r.dismiss_overlays()
    return {"ui_action": "«%s» 의 «버전 기록» 하위 목록을 연다" % name,
            "observed": {"panel": text[:260], "buttons": labels},
            "rendered": "판 «%s» · 버튼 %s" % (text[:150], labels),
            "expected": {"source": "derived-check",
                         "rule": "버전 목록에서 롤백·비교·내용 보기를 실행할 수 있다",
                         "buttons": labels},
            "failed": None if text else "«버전 기록» 을 눌렀는데 아무것도 안 열린다"}


flow("FF-1032", "admin_prompts", "row_action",
     "'버전 기록' 하위 목록에서 롤백·버전 비교(diff)·내용 보기를 실행한다",
     _version_history, route="/prompts?status=", shell=ADMIN, api=P)


def _sublist_pager(r, ctx):
    labels = ctx.get("version_drawer") or []
    return {"ui_action": "«버전 기록» 하위 목록의 쪽 넘김 컨트롤을 본다",
            "observed": {"buttons": labels,
                         "has_pager": any("다음" in x or "이전" in x for x in labels)},
            "rendered": "하위 목록 버튼 %s" % labels,
            "expected": {"source": "known-data",
                         "rule": "판이 한 쪽에 다 들어가면 넘길 것이 없는 것이 맞다",
                         "buttons": labels},
            "failed": None if labels else "앞 Flow 가 하위 목록을 못 열었다"}


flow("FF-1033", "admin_prompts", "pagination", "'버전 기록' 하위 목록 자체를 페이지로 넘긴다",
     _sublist_pager, server=False)

flow("FF-1034", "admin_prompts", "overflow_action",
     "위험·확인이 붙은 액션(보관·롤백·상태 전이)은 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/prompts?status=", shell=ADMIN, server=False)

flow("FF-1036", "admin_prompts", "navigation", "'감사 로그에서 보기'로 이 프롬프트의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=prompts"), route="/prompts?status=",
     shell=ADMIN, server=False)


def _deep_link_id(api: str, base: str, key: str = "id"):
    """`?id=` 로 상세를 곧바로 연다 — 그 id 는 **서버에서** 받는다."""
    def _act(r, ctx):
        payload = r.api_get(api)
        items = (payload or {}).get("items") or []
        if not items:
            stop("행이 없다 — 딥링크로 열 대상이 없다")
        row_id = items[0]["id"]
        # **기준 주소를 지금 화면에서 읽지 않는다.** 앞 Flow 가 다른 화면으로 나가 있으면
        # 그 화면 주소에 `?id=` 를 붙이게 되고, 그러면 엉뚱한 화면을 열어 놓고 «상세가
        # 안 뜬다» 라고 적는다 — 실제로 감사 로그 화면에서 그 일이 두 번 일어났다.
        r.goto("%s?%s=%s" % (base, key, row_id), shell=ADMIN)
        r.settle(1800)
        opened = open_dialogs(r)
        text = dialog_says(r, 220) if opened else r.main_text(200)
        return {"ui_action": "?%s=<실제 id> 로 상세를 곧바로 연다" % key,
                "url_state": r.hash_of(),
                "observed": {"id": row_id, "dialogs": opened, "detail": text[:200]},
                "rendered": "상세 «%s»" % text[:150],
                "expected": {"source": "derived-check",
                             "rule": "주소만으로 그 항목의 상세가 열린다",
                             "id": row_id, "opened": opened},
                "failed": None if opened else "주소로 열었는데 상세가 안 뜬다"}
    return _act


flow("FF-1037", "admin_prompts", "deep_link", "?id= 로 특정 버전의 상세를 곧바로 연다",
     _deep_link_id(P + "?status=", "/prompts"), shell=ADMIN, api=P)

flow("FF-1038", "admin_prompts", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(P, "프롬프트 목록"), route="/prompts", shell=ADMIN, api=P)

flow("FF-1039", "admin_prompts", "permission_state",
     "라우트 역할 가드 + 추가·수정·상태 전이의 쓰기 역할 게이트",
     ds_permission(("프롬프트 추가",), P, payload={"name": "권한 시험", "content": "x"}),
     route="/prompts", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /policies
# ═══════════════════════════════════════════════════════════════════════════
POL = "/api/admin/policies"

flow("FF-0975", "admin_policies", "combobox",
     "'이름(정확히)' 필터에서 현재 페이지의 정책 이름을 자동완성으로 고른다",
     _name_autocomplete, route="/policies", shell=ADMIN, api=POL)

flow("FF-0976", "admin_policies", "filter", "상태로 좁힌다 — 기본값은 '발행됨'",
     ds_filter("상태", "초안", POL, axis="status"), route="/policies", shell=ADMIN, api=POL)

flow("FF-0977", "admin_policies", "filter", "'필터 지우기'로 필터를 한 번에 해제한다",
     ds_clear("상태", "초안"), route="/policies", shell=ADMIN, api=POL)

flow("FF-0979", "admin_policies", "pagination", "이전/다음으로 페이지를 넘긴다(500건 상한 경고와 함께)",
     ds_pager(POL), route="/policies", shell=ADMIN, server=False)

flow("FF-0980", "admin_policies", "read", "행을 눌러 정책 상세(규칙 JSON·작성자·발행 시각)를 연다",
     ds_open_row(), route="/policies", shell=ADMIN, server=False)

flow("FF-0981", "admin_policies", "create", "'정책 추가'로 이름·용도·규칙(JSON)을 적어 초안을 만든다",
     ds_create("정책 추가", {"이름": "S21 점검 정책", "규칙": '{"max_tokens": 100}'}),
     route="/policies", shell=ADMIN, api=POL, cross=("/policies?status=draft", ADMIN))

flow("FF-0982", "admin_policies", "form_validation",
     "이름·규칙(JSON)을 비우거나 JSON 형식이 틀리면 제출 전에 막힌다",
     ds_required("정책 추가"), route="/policies", shell=ADMIN, server=False)

flow("FF-0983", "admin_policies", "edit", "초안 상태일 때만 '수정'으로 규칙·용도를 바꾼다",
     ds_edit("용도"), route="/policies?status=draft", shell=ADMIN, api=POL)

flow("FF-0984", "admin_policies", "status_change",
     "'테스트로'·'검토로'·'초안으로 되돌리기'로 버전 상태를 옮긴다(확인 후)",
     ds_action("테스트로"), route="/policies?status=draft", shell=ADMIN, api=POL)

flow("FF-0985", "admin_policies", "status_change", "'발행'으로 이 버전을 실사용으로 올린다",
     ds_action("검토로"), route="/policies?status=", shell=ADMIN, api=POL)

flow("FF-0986", "admin_policies", "status_change", "'보관'으로 더 이상 쓰이지 않게 한다(확인 후)",
     ds_action("보관"), route="/policies?status=", shell=ADMIN, api=POL)

flow("FF-0987", "admin_policies", "create",
     "'새 버전'으로 지금 버전에서 편집 가능한 초안을 만들고 그 자리에서 이어 편집한다",
     ds_action("새 버전", confirm=False), route="/policies?status=", shell=ADMIN,
     api=POL)

flow("FF-0988", "admin_policies", "row_action",
     "'버전 기록' 하위 목록에서 롤백·버전 비교(diff)·내용 보기를 실행한다",
     _version_history, route="/policies?status=", shell=ADMIN, api=POL)

flow("FF-0990", "admin_policies", "overflow_action",
     "위험·확인이 붙은 액션(보관·롤백·상태 전이)은 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/policies?status=", shell=ADMIN, server=False)

flow("FF-0991", "admin_policies", "navigation", "'감사 로그에서 보기'로 이 정책의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=policies"), route="/policies?status=",
     shell=ADMIN, server=False)

flow("FF-0992", "admin_policies", "deep_link", "?id= 로 특정 버전의 상세를 곧바로 연다",
     _deep_link_id(POL + "?status=", "/policies"), shell=ADMIN, api=POL)

flow("FF-0993", "admin_policies", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(POL, "정책 목록"), route="/policies", shell=ADMIN, api=POL)

flow("FF-0994", "admin_policies", "permission_state",
     "라우트 역할 가드 + 추가·수정·상태 전이의 쓰기 역할 게이트",
     ds_permission(("정책 추가",), POL, payload={"name": "권한 시험", "content_json": "{}"}),
     route="/policies", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /announcements
# ═══════════════════════════════════════════════════════════════════════════
ANN = "/api/admin/announcements"

flow("FF-0801", "admin_announcements", "search", "제목·내용으로 서버 검색한다(디바운스)",
     ds_search("", ANN), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0802", "admin_announcements", "filter", "사용/사용 안 함으로 좁힌다",
     ds_filter("사용", "사용 안 함", ANN, axis="active"), route="/announcements",
     shell=ADMIN, api=ANN)

flow("FF-0803", "admin_announcements", "filter", "중요도(안내/주의/긴급)로 좁힌다",
     ds_filter("중요도", "안내", ANN, axis="level"), route="/announcements", shell=ADMIN,
     api=ANN)

flow("FF-0804", "admin_announcements", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("중요도", "안내"), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0805", "admin_announcements", "filter", "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route="/announcements", shell=ADMIN, server=False)

flow("FF-0806", "admin_announcements", "pagination", "이전/다음으로 페이지를 넘긴다",
     ds_pager(ANN), route="/announcements", shell=ADMIN, server=False)

flow("FF-0807", "admin_announcements", "read", "행을 눌러 공지 상세(내용·닫기 허용·링크)를 연다",
     ds_open_row(), route="/announcements", shell=ADMIN, server=False)

flow("FF-0808", "admin_announcements", "create",
     "'공지 추가'로 제목·내용·중요도·대상·노출 기간을 정해 공지를 만든다",
     ds_create("공지 추가", {"제목": "S21 점검 공지", "내용": "인수 점검이 남긴 공지입니다."}),
     route="/announcements", shell=ADMIN, api=ANN, cross=("/announcements", ADMIN))

flow("FF-0809", "admin_announcements", "form_validation", "제목을 비우면 제출 전에 막힌다",
     ds_required("공지 추가"), route="/announcements", shell=ADMIN, server=False)

flow("FF-0810", "admin_announcements", "edit", "상세에서 '수정'으로 공지 내용·기간·링크를 바꾼다",
     ds_edit("내용"), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0811", "admin_announcements", "status_change",
     "'사용'/'사용 안 함'으로 공지를 올리거나 즉시 내린다",
     ds_action("사용 안 함"), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0812", "admin_announcements", "delete", "'삭제'로 공지를 되돌릴 수 없게 지운다(확인 후)",
     ds_action("삭제", expect_gone=True), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0813", "admin_announcements", "overflow_action",
     "위험·확인이 붙은 액션(사용 안 함·삭제)은 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/announcements", shell=ADMIN, server=False)

flow("FF-0814", "admin_announcements", "navigation", "'감사 로그에서 보기'로 이 공지의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=announcement"), route="/announcements",
     shell=ADMIN, server=False)

flow("FF-0815", "admin_announcements", "deep_link", "검색·필터·페이지가 해시 쿼리에 되쓰여 링크로 복원된다",
     ds_deep_link("/announcements?level=info", "level=info"), api=ANN)

flow("FF-0816", "admin_announcements", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(ANN, "공지 목록"), route="/announcements", shell=ADMIN, api=ANN)

flow("FF-0817", "admin_announcements", "permission_state",
     "라우트 역할 가드 + 추가/수정/삭제의 쓰기 역할 게이트",
     ds_permission(("공지 추가",), ANN, payload={"title": "권한 시험", "body": "x"}),
     route="/announcements", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /ai-quotas
# ═══════════════════════════════════════════════════════════════════════════
Q = "/api/admin/ai-quotas"

flow("FF-0785", "admin_ai-quotas", "search", "대상 이름·이메일·메모로 목록을 검색한다",
     ds_search("", Q, server=False), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0786", "admin_ai-quotas", "filter", "범위(전체/사용자)로 좁힌다 — 화면 안에서 거른다",
     ds_filter("범위", "사용자", Q, server=False), route="/ai-quotas", shell=ADMIN,
     server=False)

flow("FF-0787", "admin_ai-quotas", "filter", "기간(하루/한 달)으로 좁힌다 — 화면 안에서 거른다",
     ds_filter("기간", "하루", Q, server=False), route="/ai-quotas", shell=ADMIN,
     server=False)

flow("FF-0788", "admin_ai-quotas", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("기간", "하루"), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0789", "admin_ai-quotas", "filter", "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0790", "admin_ai-quotas", "sort", "열 머리를 눌러 정렬한다(오름→내림→해제)",
     sort_by("초기화"), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0791", "admin_ai-quotas", "read", "행을 눌러 상한 상세(대상 이메일·메모·상태)를 연다",
     ds_open_row(), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0792", "admin_ai-quotas", "create",
     "'상한 추가'로 범위·기간·상한 횟수를 정해 새 상한을 만든다",
     # 목록에 **보이는 값**을 열쇠로 쓴다 — 메모는 열이 아니라서 목록에서 다시 못 찾는다.
     ds_create("상한 추가", {"상한": "137", "메모": "S21 점검 상한"},
               selects={"기간": "한 달"}, needle="137"),
     route="/ai-quotas", shell=ADMIN, api=Q, cross=("/ai-quotas", ADMIN))

flow("FF-0793", "admin_ai-quotas", "form_validation", "필수 항목(범위·기간·상한)을 비우면 제출 전에 막힌다",
     ds_required("상한 추가"), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0794", "admin_ai-quotas", "edit", "상세에서 '수정'으로 상한 횟수·메모를 바꾼다",
     ds_edit("메모"), route="/ai-quotas", shell=ADMIN, api=Q)

flow("FF-0795", "admin_ai-quotas", "delete", "'삭제'로 이 상한을 지운다(확인 후, 지우면 무제한이 된다)",
     ds_action("삭제", expect_gone=True), route="/ai-quotas", shell=ADMIN, api=Q)

flow("FF-0796", "admin_ai-quotas", "overflow_action",
     "위험·확인이 붙은 액션(삭제)은 상세 하단 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/ai-quotas", shell=ADMIN, server=False)

flow("FF-0797", "admin_ai-quotas", "navigation", "'감사 로그에서 보기'로 이 상한의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=ai_quota"), route="/ai-quotas",
     shell=ADMIN, server=False)

flow("FF-0798", "admin_ai-quotas", "deep_link", "검색·필터·페이지가 해시 쿼리에 되쓰여 링크로 복원된다",
     ds_deep_link("/ai-quotas?period=day", "period=day"), api=Q)

flow("FF-0799", "admin_ai-quotas", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(Q, "AI 사용 상한"), route="/ai-quotas", shell=ADMIN, api=Q)

flow("FF-0800", "admin_ai-quotas", "permission_state",
     "라우트 역할 가드와 액션 role 게이트로 권한 없는 역할에는 안내/버튼 숨김",
     ds_permission(("상한 추가",), Q,
                   payload={"scope_type": "global", "period": "day", "max_calls": 1}),
     route="/ai-quotas", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /feature-flags
# ═══════════════════════════════════════════════════════════════════════════
FL = "/api/admin/feature-flags"

flow("FF-0865", "admin_feature-flags", "search", "플래그 이름·설명으로 검색한다",
     ds_search("", FL, server=False), route="/feature-flags", shell=ADMIN, server=False)

flow("FF-0866", "admin_feature-flags", "filter",
     "값의 주인(파일/설정 화면)으로 좁힌다 — 화면 안에서 거른다",
     ds_filter("값의 주인", "파일", FL, server=False), route="/feature-flags", shell=ADMIN,
     server=False)

flow("FF-0867", "admin_feature-flags", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("값의 주인", "파일"), route="/feature-flags", shell=ADMIN, server=False)

flow("FF-0869", "admin_feature-flags", "sort", "열 머리를 눌러 정렬한다(오름→내림→해제)",
     sort_by("현재"), route="/feature-flags", shell=ADMIN, server=False)

flow("FF-0870", "admin_feature-flags", "read",
     "행을 눌러 플래그 상세(전체 설명·기본값·읽는 코드 유무)를 연다",
     ds_open_row(), route="/feature-flags", shell=ADMIN, server=False)

flow("FF-0871", "admin_feature-flags", "settings_apply",
     "'활성화'로 파일 소유 플래그를 재시작 없이 켠다(확인 후)",
     ds_action("활성화"), route="/feature-flags", shell=ADMIN, api=FL)

flow("FF-0872", "admin_feature-flags", "settings_apply",
     "'비활성화'로 파일 소유 플래그를 끈다(확인 후, 쓰는 화면이 즉시 사라진다)",
     ds_action("비활성화"), route="/feature-flags", shell=ADMIN, api=FL)

flow("FF-0873", "admin_feature-flags", "overflow_action",
     "위험·확인이 붙은 액션(활성화·비활성화)은 상세 하단 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/feature-flags", shell=ADMIN, server=False)

flow("FF-0874", "admin_feature-flags", "navigation",
     "'설정 화면에서 열기'로 DB 소유 플래그를 바꿀 수 있는 설정 화면으로 보낸다",
     ds_navigate("설정 화면에서 열기", "settings"), route="/feature-flags", shell=ADMIN,
     server=False)

flow("FF-0875", "admin_feature-flags", "navigation", "'감사 로그에서 보기'로 이 플래그의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type="), route="/feature-flags",
     shell=ADMIN, server=False)

flow("FF-0876", "admin_feature-flags", "deep_link", "검색·필터가 해시 쿼리에 되쓰여 링크로 복원된다",
     ds_deep_link("/feature-flags?owner=file", "owner=file"), api=FL)

flow("FF-0877", "admin_feature-flags", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(FL, "기능 플래그"), route="/feature-flags", shell=ADMIN, api=FL)

flow("FF-0878", "admin_feature-flags", "permission_state", "라우트 역할 가드 + 켜기/끄기의 쓰기 역할 게이트",
     ds_permission((), FL + "/game_ai_enabled", method="PATCH", payload={"value": True}),
     route="/feature-flags", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /integrations
# ═══════════════════════════════════════════════════════════════════════════
IN = "/api/admin/integrations"

flow("FF-0894", "admin_integrations", "search", "목록을 화면 안에서 검색한다(대상 필드 미지정)",
     ds_search("", IN, server=False), route="/integrations", shell=ADMIN, server=False)

flow("FF-0896", "admin_integrations", "filter", "활성/비활성으로 좁힌다",
     ds_filter("활성", "활성", IN, server=False), route="/integrations", shell=ADMIN,
     server=False)

flow("FF-0897", "admin_integrations", "filter", "상태 확인(정상/중단/미확인)으로 좁힌다",
     ds_filter("상태 확인", "정상", IN, server=False), route="/integrations", shell=ADMIN,
     server=False)

flow("FF-0898", "admin_integrations", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("활성", "활성"), route="/integrations", shell=ADMIN, server=False)

flow("FF-0900", "admin_integrations", "sort", "열 머리를 눌러 정렬한다(오름→내림→해제)",
     sort_by("마지막 확인"), route="/integrations", shell=ADMIN, server=False)

flow("FF-0901", "admin_integrations", "read", "행을 눌러 연동 상세(주소·인증·인증 정보 상태)를 연다",
     ds_open_row(), route="/integrations", shell=ADMIN, server=False)

flow("FF-0902", "admin_integrations", "create",
     "'외부 연동 추가'로 이름·서버 주소·인증을 정해 연동을 만든다",
     # 주소는 **SSRF 허용 목록 안**이어야 한다(config/allowed-services.json). 목록 밖
     # 주소를 넣으면 서버가 옳게 거절하고, 그러면 이 Flow 는 만들기가 아니라 거절을 잰다.
     ds_create("외부 연동 추가",
               {"이름": "S21 점검 연동", "서버 주소": "https://api.anthropic.com/s21"}),
     route="/integrations", shell=ADMIN, api=IN, cross=("/integrations", ADMIN))

flow("FF-0903", "admin_integrations", "form_validation", "이름·서버 주소를 비우면 제출 전에 막힌다",
     ds_required("외부 연동 추가"), route="/integrations", shell=ADMIN, server=False)

flow("FF-0904", "admin_integrations", "edit", "상세에서 '수정'으로 주소·인증·설명을 바꾼다(바뀐 필드만 보낸다)",
     ds_edit("설명"), route="/integrations", shell=ADMIN, api=IN)

flow("FF-0905", "admin_integrations", "status_change",
     "'활성화'/'비활성화'로 이 연동을 쓰는 호출을 열고 막는다(확인 후)",
     ds_action("비활성화"), route="/integrations", shell=ADMIN, api=IN)

flow("FF-0906", "admin_integrations", "admin_op",
     "'헬스체크'로 지금 통하는지 확인하고 실제로 찌른 주소까지 알린다",
     ds_action("상태 확인", confirm=False), route="/integrations", shell=ADMIN, api=IN)

flow("FF-0907", "admin_integrations", "row_action",
     "'버전 기록' 하위 목록에서 스냅샷 값을 보고 그 버전으로 롤백한다(확인 후)",
     _version_history, route="/integrations", shell=ADMIN, api=IN)

flow("FF-0908", "admin_integrations", "overflow_action",
     "위험·확인이 붙은 액션(비활성화·롤백)은 넘침 메뉴에서 실행한다",
     ds_overflow(), route="/integrations", shell=ADMIN, server=False)

flow("FF-0909", "admin_integrations", "navigation", "'감사 로그에서 보기'로 이 연동의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type="), route="/integrations",
     shell=ADMIN, server=False)

flow("FF-0910", "admin_integrations", "deep_link", "?id= 로 특정 연동의 상세를 곧바로 연다",
     _deep_link_id(IN, "/integrations"), shell=ADMIN, api=IN)

flow("FF-0911", "admin_integrations", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(IN, "외부 연동"), route="/integrations", shell=ADMIN, api=IN)

flow("FF-0912", "admin_integrations", "permission_state",
     "라우트 역할 가드 + 인증 옵션이 역할에 따라 좁아지는 생성 폼",
     ds_permission(("외부 연동 추가",), IN,
                   payload={"name": "권한 시험", "base_url": "https://example.invalid"}),
     route="/integrations", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /admin-notifications
# ═══════════════════════════════════════════════════════════════════════════
NOTI = "/api/notifications"

flow("FF-1175", "admin_admin-notifications", "read", "관리 알림 목록을 audience=admin 으로 조회한다",
     ds_read("관리 알림", NOTI), route="/admin-notifications", shell=ADMIN, api=NOTI)


def _unread_only(r, ctx):
    before = n_rows(r)
    r.rec.reset()
    # 이 화면의 「안 읽음만」은 **«읽음 상태» 선택기의 값**이다(registry: unread_only).
    r.choose("읽음 상태", "안 읽음만")
    r.settle(1800)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if NOTI in c["path"] and c["query"]}))
    return {"ui_action": "«안 읽음만» 을 켠다",
            "frontend_state": "unread 축이 붙는다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:70]),
            "expected": {"source": "derived-check",
                         "rule": "안 읽음만 켜면 그 축이 서버로 가거나 행이 좁아진다",
                         "query": query},
            "failed": None if ("unread" in query or n_rows(r) < before)
                      else "«안 읽음만» 을 켰는데 아무 변화가 없다"}


flow("FF-1176", "admin_admin-notifications", "filter", "'안 읽음만'으로 목록을 좁힌다",
     _unread_only, route="/admin-notifications", shell=ADMIN, api=NOTI)

flow("FF-1177", "admin_admin-notifications", "pagination", "페이지를 앞뒤로 넘긴다",
     ds_pager(NOTI), route="/admin-notifications", shell=ADMIN, server=False)

flow("FF-1178", "admin_admin-notifications", "row_action", "행을 눌러 상세 드로어를 연다",
     ds_open_row(), route="/admin-notifications", shell=ADMIN, server=False)

flow("FF-1179", "admin_admin-notifications", "notification_action", "알림 하나를 읽음 처리한다",
     ds_action("읽음", confirm=False), route="/admin-notifications", shell=ADMIN, api=NOTI)

flow("FF-1180", "admin_admin-notifications", "notification_action",
     "안 읽음이 있을 때만 '모두 읽음'을 노출하고 확인 후 일괄 처리한다",
     ds_action("모두 읽음", in_detail=False), route="/admin-notifications", shell=ADMIN,
     api=NOTI)

flow("FF-1181", "admin_admin-notifications", "delete", "알림을 확인 후 삭제한다",
     ds_action("삭제", expect_gone=True), route="/admin-notifications", shell=ADMIN,
     api=NOTI)

flow("FF-1182", "admin_admin-notifications", "navigation",
     "'관련 항목 보기'로 서버가 계산한 목적지로 이동한다",
     ds_navigate("관련 항목", "#/"), route="/admin-notifications", shell=ADMIN, server=False)


def _link_role_gate(r, ctx):
    """역할이 **실제로 닿는 화면일 때만** 이동 동작을 준다."""
    if not n_rows(r):
        stop("행이 없다")
    row_at(r, 0).click()
    r.settle(1600)
    detail = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    buttons = detail.get_by_role("button")
    mine = [" ".join((buttons.nth(i).inner_text() or "").split())
            for i in range(min(buttons.count(), 12))]
    r.dismiss_overlays()
    got = r.as_role("operator", "/admin-notifications", ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return {rows: main ? main.querySelectorAll('tbody tr').length : 0,
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,180)};
           }"""))
    return {"ui_action": "상세의 이동 동작을 세고, 같은 화면을 운영자로 연다",
            "observed": {"as_system_admin": mine, "as_operator": got},
            "rendered": "system_admin 동작 %s · operator 본문 «%s»" % (mine, got["body"][:110]),
            "expected": {"source": "derived-check",
                         "rule": "닿을 수 없는 화면으로 가는 동작은 그 역할에게 안 준다"},
            "failed": None}


flow("FF-1183", "admin_admin-notifications", "permission_state",
     "역할이 실제로 닿는 화면일 때만 이동 액션을 준다",
     _link_role_gate, route="/admin-notifications", shell=ADMIN, server=False)

flow("FF-1184", "admin_admin-notifications", "deep_link", "?id= 로 특정 알림 상세를 바로 연다",
     _deep_link_id(NOTI + "?audience=admin", "/admin-notifications"),
     shell=ADMIN, api=NOTI)

flow("FF-1185", "admin_admin-notifications", "refresh", "조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(NOTI, "관리 알림"), route="/admin-notifications", shell=ADMIN,
     api=NOTI)
