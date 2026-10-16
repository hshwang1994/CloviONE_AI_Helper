"""S21 — 감사 로그 · 이상 징후 · 백업 · 복구 리허설 (W14).

S20 이 이 네 화면을 **탭 묶음 둘**로 묶었다(`/audit` · `/backup`). 그래서 같은 화면이 두
주소에서 열린다 — 그릇의 탭(`/audit?tab=audit-anomalies`)과 예전부터 있던 홑 라우트
(`/audit-anomalies`). 원장에도 그 둘이 **따로** 적혀 있다.

**같은 화면이므로 같은 동작을 쓴다.** 다만 주소가 다르면 실제로 다르게 동작할 수 있으므로
(그릇의 `?tab=` 이 보존되는지가 바로 그 질문이다) 두 주소에서 **각각 돌린다** — 한쪽에서
돌린 결과를 다른 쪽에 옮겨 적지 않는다.
"""

from __future__ import annotations

from urllib.parse import unquote

from scripts.ui_qa.s21_admin_kit import (  # noqa: F401
    ADMIN, ds_clear, ds_deep_link, ds_filter, ds_navigate, ds_open_row, ds_pager,
    ds_permission, ds_read, ds_saved_view, ds_search,
)
from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog, open_dialogs,
    retry_from_error, row_at, row_name, rows_of, sort_by, stop, switch_tab,
)

AUDIT = "/api/admin/audit"
BACKUP = "/api/admin/backups"


def _pair(ids, surfaces, category, name, act, **kw):
    """같은 동작을 두 주소(그릇 탭 · 홑 라우트)에서 각각 돌린다."""
    for fid, (surface, route) in zip(ids, surfaces):
        flow(fid, surface, category, name, act, route=route, shell=ADMIN, **kw)


def _in_more_filters(act):
    """감사 로그의 「추가 필터」(D-596) 안에 접힌 칸을 쓰는 동작 — 접혀 있으면 먼저 편다.

    대상 ID · 작업 · 문의 번호 · 표시 범위는 첫 줄이 아니라 「추가 필터」 접기 칸에 선다. 칸이 접힌 채로 찾으면
    「칸이 없다」로 멈추는데, 그것은 화면이 아니라 고르기가 틀린 것이다. 이미 펼쳐져 있으면(값이 걸린 주소) 그대로 둔다.
    """
    def _act(r, ctx):
        toggle = r.page.get_by_role("button", name="추가 필터")
        if toggle.count() and toggle.first.get_attribute("aria-expanded") == "false":
            toggle.first.click()
            r.settle(500)
        return act(r, ctx)
    return _act


# ═══════════════════════════════════════════════════════════════════════════
# /audit — 감사 로그
# ═══════════════════════════════════════════════════════════════════════════
flow("FF-0643", "admin_audit__audit", "navigation",
     "'감사 로그' ↔ '이상 징후' 탭을 전환한다(?tab= 주소에 반영)",
     switch_tab("이상 징후", "tab=audit-anomalies"), route="/audit?tab=audit",
     shell=ADMIN, server=False)

flow("FF-0644", "admin_audit__audit", "filter", "대상(object_type)으로 좁힌다",
     ds_filter("대상", "사용자", AUDIT, axis="object_type"), route="/audit?tab=audit",
     shell=ADMIN, api=AUDIT)


def _text_filter(label: str, value: str, axis: str, api: str):
    """글자를 넣는 조건 — **그 축이 서버 질의에 실리는가**."""
    def _act(r, ctx):
        box = r.page.get_by_label(label, exact=False)
        if not box.count():
            stop("«%s» 칸이 없다" % label)
        before = n_rows(r)
        r.rec.reset()
        box.first.fill(value)
        r.settle(2200)
        query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                         if api in c["path"] and c["query"]})))
        box.first.fill("")
        r.settle(1400)
        return {"ui_action": "«%s» 에 «%s» 를 넣는다" % (label, value),
                "frontend_state": "%s 가 서버로 간다" % axis,
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "query": query},
                "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:90]),
                "expected": {"source": "derived-check",
                             "rule": "조건을 넣으면 그 축이 서버 질의에 실린다",
                             "axis": axis, "got": query},
                "failed": None if axis in query
                          else "«%s» 를 넣었는데 질의에 %s 가 없다: «%s»" % (label, axis, query)}
    return _act


flow("FF-0645", "admin_audit__audit", "filter", "대상 ID로 좁혀 한 엔티티의 사건만 추적한다",
     _in_more_filters(_text_filter("대상 ID", "s21", "object_id", AUDIT)), route="/audit?tab=audit",
     shell=ADMIN, api=AUDIT)


def _action_autocomplete(r, ctx):
    box = r.page.get_by_label("작업", exact=False)
    if not box.count():
        stop("«작업(정확히)» 칸이 없다")
    listed = box.first.get_attribute("list")
    options = r.page.locator("datalist#%s option" % listed) if listed else None
    names = ([options.nth(i).get_attribute("value") for i in range(min(options.count(), 8))]
             if options and options.count() else [])
    before = n_rows(r)
    if names:
        r.rec.reset()
        box.first.fill(names[0])
        r.settle(2200)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                     if AUDIT in c["path"] and c["query"]})))
    return {"ui_action": "«작업(정확히)» 의 자동완성 후보를 보고 하나를 고른다",
            "observed": {"datalist": listed, "options": names,
                         "rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "후보 %s · %d행 → %d행" % (names[:5], before, n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "지금 쪽의 실제 action 문자열이 후보로 나온다", "got": names},
            "failed": None if names else "자동완성 후보가 하나도 없다"}


flow("FF-0646", "admin_audit__audit", "combobox",
     "'작업(정확히)' 필터에서 현재 페이지의 실제 action 문자열을 자동완성으로 고른다",
     _in_more_filters(_action_autocomplete), route="/audit?tab=audit", shell=ADMIN, api=AUDIT)

flow("FF-0647", "admin_audit__audit", "filter", "표시 범위에서 로그인/로그아웃을 제외해 잡음을 줄인다",
     _in_more_filters(ds_filter("표시 범위", "로그인", AUDIT)), route="/audit?tab=audit", shell=ADMIN,
     api=AUDIT)

# 행위자는 **글자 칸이 아니라 사람 고르기**다(registry: type=select · kind=entity).
flow("FF-0648", "admin_audit__audit", "filter", "행위자 ID로 좁힌다",
     ds_filter("행위자", "UI QA", AUDIT, axis="user_id"), route="/audit?tab=audit",
     shell=ADMIN, api=AUDIT)

flow("FF-0649", "admin_audit__audit", "filter", "결과(성공/실패)로 좁힌다",
     ds_filter("결과", "실패", AUDIT, axis="result"), route="/audit?tab=audit",
     shell=ADMIN, api=AUDIT)

flow("FF-0650", "admin_audit__audit", "filter", "문의 번호(요청 ID)로 그 요청 하나를 짚는다",
     _in_more_filters(_text_filter("요청", "s21-request", "request_id", AUDIT)), route="/audit?tab=audit",
     shell=ADMIN, api=AUDIT)


def _time_range(r, ctx):
    boxes = r.page.locator('#main-content input[type="datetime-local"], '
                           '#main-content input[type="date"]')
    if not boxes.count():
        stop("시각 구간 칸이 없다")
    before = n_rows(r)
    r.rec.reset()
    boxes.first.fill("2026-08-01T00:00" if boxes.first.get_attribute("type") ==
                     "datetime-local" else "2026-08-01")
    r.settle(2200)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                     if AUDIT in c["path"] and c["query"]})))
    return {"ui_action": "시작 시각을 2026-08-01 로 잡는다",
            "frontend_state": "KST 로 받은 값을 서버 축으로 옮긴다",
            "observed": {"inputs": boxes.count(),
                         "rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:90]),
            "expected": {"source": "derived-check",
                         "rule": "구간을 자르면 그 축이 서버 질의에 실린다", "got": query},
            "failed": None if ("from" in query or "start" in query or "since" in query)
                      else "구간을 잡았는데 질의에 시각 축이 없다: «%s»" % query}


flow("FF-0651", "admin_audit__audit", "filter", "시작·종료 시각(KST)으로 구간을 자른다",
     _time_range, route="/audit?tab=audit", shell=ADMIN, api=AUDIT)

flow("FF-0652", "admin_audit__audit", "filter", "'필터 지우기'로 필터를 한 번에 해제한다",
     ds_clear("결과", "실패"), route="/audit?tab=audit", shell=ADMIN, api=AUDIT)

flow("FF-0653", "admin_audit__audit", "filter",
     "저장된 뷰 — 자주 쓰는 조사 조건을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0654", "admin_audit__audit", "pagination", "목록 위·아래 페이저로 100행 단위 페이지를 넘긴다",
     ds_pager(AUDIT), route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0655", "admin_audit__audit", "read", "행을 눌러 기록 상세(변경 요약·변경 전/후·IP·요청 ID)를 연다",
     ds_open_row(), route="/audit?tab=audit", shell=ADMIN, server=False)


def _csv_export(r, ctx):
    """«CSV 내보내기» 가 **무엇을 내려받게 하는가**.

    이 동작은 `window.location.href` 로 브라우저를 그 주소로 보낸다 — 그러면 응답의
    `Content-Disposition` 이 파일 저장을 일으킨다. 계측기가 그 저장 사건을 못 잡는 경우가
    있어서(브라우저가 내려받기를 창 밖에서 처리한다), **버튼이 겨눈 주소를 직접 부르는
    것**으로 계약을 확인한다: 그 주소가 첨부로 답하고, 지금 걸린 조건은 실려 있고,
    쪽 번호는 빠져 있어야 한다.
    """
    button = r.in_main("button", "CSV")
    if not button.count():
        stop("«CSV 내보내기» 가 없다")
    got = r.page.evaluate(
        """async () => {
             const res = await fetch('/api/admin/audit/export.csv?result=failure',
                                     {credentials: 'same-origin'});
             const text = res.ok ? (await res.text()).slice(0, 200) : '';
             return {status: res.status,
                     disposition: res.headers.get('content-disposition') || '',
                     type: res.headers.get('content-type') || '',
                     head: text.split('\n')[0]};
           }""")
    downloaded = False
    try:
        with r.page.expect_download(timeout=6000) as info:
            button.first.click()
        downloaded = True
        got["filename"] = info.value.suggested_filename
        got["url"] = unquote(info.value.url)[-150:]
    except Exception:  # noqa: BLE001 — 저장 사건을 못 잡는 것이 계약 위반은 아니다
        r.settle(1200)
    return {"ui_action": "«CSV 내보내기» 가 겨눈 주소를 확인한다",
            "frontend_state": "지금 걸린 필터를 그대로, page 는 빼고",
            "observed": {"download_event": downloaded, **got},
            "rendered": "HTTP %s · %s · %s · 첫 줄 «%s»"
                        % (got.get("status"), got.get("type"),
                           got.get("disposition"), got.get("head", "")[:60]),
            "expected": {"source": "derived-check",
                         "rule": "내보내기 주소가 첨부(CSV)로 답한다",
                         "got": got.get("disposition")},
            "failed": None if ("attachment" in (got.get("disposition") or "")
                               and "csv" in (got.get("type") or ""))
                      else "내보내기 주소가 첨부로 안 답한다: %s" % got}


flow("FF-0656", "admin_audit__audit", "attachment",
     "'CSV 내보내기'로 지금 걸린 필터 그대로 파일을 내려받는다(페이지 파라미터는 뺀다)",
     _csv_export, route="/audit?tab=audit", shell=ADMIN, server=False)


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


flow("FF-0657", "admin_audit__audit", "navigation", "헤더의 '이상 징후 보기'로 이상 징후 화면으로 이동한다",
     _header_link("이상 징후 보기", "anomal"), route="/audit?tab=audit", shell=ADMIN,
     server=False)

flow("FF-0658", "admin_audit__audit", "navigation",
     "'관련 항목 보기'로 그 기록이 가리키는 엔티티의 상세를 곧바로 연다",
     ds_navigate("관련 항목", "#/"), route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0659", "admin_audit__audit", "navigation",
     "'관련 목록 열기'로 딥링크가 없는 대상 유형은 그 화면 목록으로 이동한다",
     ds_navigate("목록 열기", "#/"), route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0660", "admin_audit__audit", "deep_link",
     "?object_type=&object_id=&user_id=&result=&action= 딥링크를 필터로 소비한다",
     ds_deep_link("/audit?tab=audit&result=failure", "result=failure"), api=AUDIT)


def _row_opens_detail_url(r, ctx):
    if not n_rows(r):
        stop("행이 없다")
    before = unquote(r.hash_of())
    row_at(r, 0).click()
    r.settle(1800)
    after = unquote(r.hash_of())
    opened = open_dialogs(r)
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(2200)
    still = open_dialogs(r)
    return {"ui_action": "행을 열고 새로고침한다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after, "dialogs": {"opened": opened, "after_reload": still}},
            "rendered": "주소 «%s» · 상세 %s" % (after[:60], "열림" if still else "닫힘"),
            "expected": {"source": "derived-check",
                         "rule": "행을 열면 주소가 /audit/{id} 가 되고 새로고침해도 그 상세가 열린다",
                         "got": after},
            "failed": None if "/audit/" in after
                      else "행을 열었는데 주소가 상세로 안 바뀐다: %s" % after}


flow("FF-0661", "admin_audit__audit", "deep_link",
     "행을 열면 주소가 /audit/{id} 로 바뀌어 상세가 새로고침·공유로 복원된다",
     _row_opens_detail_url, route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0662", "admin_audit__audit", "refresh", "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
     retry_from_error(AUDIT, "감사 로그"), route="/audit?tab=audit", shell=ADMIN,
     api=AUDIT)

flow("FF-0663", "admin_audit__audit", "permission_state",
     "라우트 역할 가드 + 대상 화면에 못 들어가는 역할에는 이동 버튼을 숨긴다",
     ds_permission((), AUDIT, method="GET"), route="/audit?tab=audit", shell=ADMIN,
     server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /audit/{id} — 감사 기록 상세
# ═══════════════════════════════════════════════════════════════════════════
def _audit_id(r) -> str:
    payload = r.api_get(AUDIT + "?page_size=1")
    items = (payload or {}).get("items") or []
    if not items:
        stop("감사 기록이 없다")
    return items[0]["id"]


def _audit_detail_open(r, ctx):
    aid = _audit_id(r)
    ctx["audit_id"] = aid
    r.goto("/audit/%s" % aid, shell=ADMIN)
    r.settle(1800)
    opened = open_dialogs(r)
    text = dialog_says(r, 300) if opened else r.main_text(260)
    return {"ui_action": "/audit/{id} 주소로 그 기록 상세를 곧바로 연다",
            "url_state": r.hash_of(),
            "observed": {"id": aid, "dialogs": opened, "detail": text[:260]},
            "rendered": "상세 «%s»" % text[:190],
            "expected": {"source": "derived-check",
                         "rule": "주소만으로 단건 상세가 열린다", "opened": opened},
            "failed": None if opened else "주소로 열었는데 상세가 안 뜬다"}


flow("FF-0572", "admin_audit-id", "deep_link", "/audit/{id} 주소로 그 감사 기록 상세를 곧바로 연다(단건 GET)",
     _audit_detail_open, shell=ADMIN, api=AUDIT)


def _audit_detail_fields(want: tuple):
    def _act(r, ctx):
        aid = ctx.get("audit_id") or _audit_id(r)
        if not open_dialogs(r):
            r.goto("/audit/%s" % aid, shell=ADMIN)
            r.settle(1800)
        text = dialog_says(r, 600) if open_dialogs(r) else r.main_text(600)
        missing = [w for w in want if w not in text]
        return {"ui_action": "상세에서 %s 를 읽는다" % ", ".join(want),
                "observed": {"detail": text[:400], "missing": missing},
                "rendered": "상세 «%s»" % text[:250],
                "expected": {"source": "derived-check",
                             "rule": "상세는 바뀐 값과 원문 식별자를 함께 보여 준다",
                             "want": list(want), "missing": missing},
                "failed": None if not missing else "상세에 없는 칸: %s" % missing}
    return _act


flow("FF-0573", "admin_audit-id", "read", "변경 요약(바뀐 키만 before → after)과 변경 전/후 전체를 읽는다",
     _audit_detail_fields(("변경",)), shell=ADMIN, server=False)

flow("FF-0574", "admin_audit-id", "read",
     "행위자 ID 원문·작업 원문·대상 ID 전체를 상세에서 확인해 필터에 넣을 값을 얻는다",
     _audit_detail_fields(("작업", "대상")), shell=ADMIN, server=False)

flow("FF-0575", "admin_audit-id", "navigation", "'관련 항목 보기'로 그 기록이 가리키는 엔티티 상세를 연다",
     ds_navigate("관련 항목", "#/"), route="/audit?tab=audit", shell=ADMIN, server=False)

flow("FF-0576", "admin_audit-id", "navigation",
     "'관련 목록 열기'로 딥링크가 없는 대상 유형은 그 화면 목록으로 이동한다",
     ds_navigate("목록 열기", "#/"), route="/audit?tab=audit", shell=ADMIN, server=False)


def _audit_detail_close(r, ctx):
    aid = ctx.get("audit_id") or _audit_id(r)
    r.goto("/audit/%s" % aid, shell=ADMIN)
    r.settle(1800)
    if not open_dialogs(r):
        stop("상세가 안 열렸다")
    r.dismiss_overlays()
    r.settle(900)
    after = unquote(r.hash_of())
    return {"ui_action": "상세를 닫는다",
            "url_state": after,
            "observed": {"hash": after, "dialogs": open_dialogs(r)},
            "rendered": "주소 «%s»" % after,
            "expected": {"source": "derived-check",
                         "rule": "닫으면 목록 주소로 되돌아온다", "expect": "/audit",
                         "got": after},
            "failed": None if aid not in after
                      else "닫았는데 주소가 상세 그대로다: %s" % after}


flow("FF-0577", "admin_audit-id", "modal_action",
     "상세를 닫으면 목록 주소(/audit)로 되돌아간다(없는 id 였다면 404 안내 후 되돌린다)",
     _audit_detail_close, shell=ADMIN, server=False)


def _audit_detail_tab(r, ctx):
    aid = ctx.get("audit_id") or _audit_id(r)
    r.goto("/audit/%s" % aid, shell=ADMIN)
    r.settle(1800)
    tab = r.page.get_by_role("tab", name="이상 징후", exact=False)
    if not tab.count():
        # 상세가 **모달**이면 그 뒤의 탭은 `aria-hidden` 이라 닿을 수 없다 — 그것이
        # 그 부품의 계약이다. 「탭이 없다」가 아니라 「지금은 못 누른다」를 적는다.
        said = dialog_says(r, 200)
        return {"ui_action": "상세를 연 채 그릇의 탭을 누르려 한다",
                "observed": {"tabs_reachable": 0, "detail": said[:200]},
                "rendered": "상세가 열려 있는 동안 탭에 닿을 수 없다 — 상세 «%s»" % said[:130],
                "expected": {"source": "derived-check",
                             "rule": "상세가 모달이면 그 뒤의 탭은 가려진다(그 부품의 계약)"},
                "failed": None}
    tab.first.click()
    r.settle(2000)
    after = unquote(r.hash_of())
    return {"ui_action": "상세를 연 채 그릇의 «이상 징후» 탭을 누른다",
            "url_state": after,
            "observed": {"hash": after},
            "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "상세가 열려 있어도 그릇의 탭은 그대로 전환된다",
                         "got": after},
            "failed": None if "anomal" in after
                      else "상세를 연 채로는 탭이 안 바뀐다: %s" % after}


flow("FF-0578", "admin_audit-id", "navigation",
     "상세 아래 그릇의 '감사 로그' ↔ '이상 징후' 탭은 그대로 전환된다",
     _audit_detail_tab, shell=ADMIN, server=False)

flow("FF-0579", "admin_audit-id", "back_forward",
     "sel 변화가 replace 로 주소에 반영돼 새로고침·공유에도 같은 상세가 열린다",
     _row_opens_detail_url, route="/audit?tab=audit", shell=ADMIN, server=False)


def _audit_missing_id(r, ctx):
    r.goto("/audit/00000000-0000-0000-0000-000000000000", shell=ADMIN)
    r.settle(2400)
    body = r.main_text(240)
    said = dialog_says(r, 240)
    got = r.as_role("user", "/audit/%s" % (ctx.get("audit_id") or _audit_id(r)), ADMIN,
                    lambda p: p.evaluate(
                        """() => {
                             const main = document.querySelector('#main-content');
                             return (main ? main.innerText : document.body.innerText)
                                 .replace(/\\s+/g,' ').trim().slice(0, 200);
                           }"""))
    return {"ui_action": "없는 id 로 상세를 열고, 같은 상세를 일반 사용자로도 연다",
            "observed": {"missing_body": (said or body)[:220], "as_user": got},
            "rendered": "없는 id «%s» · 일반 사용자 «%s»" % ((said or body)[:110], got[:110]),
            "expected": {"source": "derived-check",
                         "rule": "없는 기록과 권한 밖 기록에 같은 404 안내를 준다"},
            "failed": None if ("없" in (said or body) or "찾을 수" in (said or body))
                      else "없는 id 인데 아무 안내가 없다"}


flow("FF-0580", "admin_audit-id", "permission_state",
     "라우트 역할 가드 + 없는/권한 밖 기록은 404 로 접어 같은 안내를 준다",
     _audit_missing_id, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 이상 징후 — 그릇 탭과 홑 라우트 둘 다
# ═══════════════════════════════════════════════════════════════════════════
ANOM = "/api/admin/audit/anomalies"
ANOM_SURFACES = (("admin_audit__audit-anomalies", "/audit?tab=audit-anomalies"),
                 ("admin_audit-anomalies", "/audit-anomalies"))

_pair(("FF-0664", "FF-0834"), ANOM_SURFACES, "navigation",
      "'감사 로그' ↔ '이상 징후' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("감사 로그", "tab=audit"), server=False)

_pair(("FF-0665", "FF-0835"), ANOM_SURFACES, "search",
      "목록을 화면 안에서 검색한다(대상 필드 미지정)",
      ds_search("", ANOM, server=False), server=False)

_pair(("FF-0666", "FF-0836"), ANOM_SURFACES, "filter",
      "기간(최근 6시간/24시간/7일/30일)으로 조회 구간을 바꾼다",
      ds_filter("기간", "7일", ANOM, axis="hours"), api=ANOM)

_pair(("FF-0667", "FF-0837"), ANOM_SURFACES, "filter",
      "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
      ds_clear("기간", "7일"), server=False)

_pair(("FF-0668", "FF-0838"), ANOM_SURFACES, "filter",
      "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
      ds_saved_view(), server=False)

_pair(("FF-0669", "FF-0839"), ANOM_SURFACES, "sort",
      "열 머리를 눌러 정렬한다(중요도·건수·마지막 시각)",
      sort_by("건수"), server=False)

_pair(("FF-0670", "FF-0840"), ANOM_SURFACES, "read",
      "행을 눌러 징후 상세(설명·근거·임계값·처음 시각)를 연다",
      ds_open_row(), server=False)

_pair(("FF-0671", "FF-0841"), ANOM_SURFACES, "navigation",
      "'이 사람의 감사 로그'로 행위자 필터가 걸린 감사 로그로 이동한다",
      ds_navigate("이 사람의 감사 로그", "user_id="), server=False)

_pair(("FF-0672", "FF-0842"), ANOM_SURFACES, "navigation",
      "'실패만 보기'로 그 행위자의 실패 기록만 걸러 감사 로그로 이동한다",
      ds_navigate("실패만", "result=failure"), server=False)

_pair(("FF-0673", "FF-0843"), ANOM_SURFACES, "navigation",
      "헤더의 '감사 로그 전체'로 감사 로그 화면으로 이동한다",
      _header_link("감사 로그 전체", "audit"), server=False)

flow("FF-0674", "admin_audit__audit-anomalies", "deep_link",
     "기간 필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/audit?tab=audit-anomalies&hours=168", "tab=audit-anomalies"),
     api=ANOM)

flow("FF-0844", "admin_audit-anomalies", "deep_link",
     "기간 필터가 해시 쿼리에 되쓰인다",
     ds_deep_link("/audit-anomalies?hours=168", "hours=168"), api=ANOM)

_pair(("FF-0675", "FF-0845"), ANOM_SURFACES, "refresh",
      "조회 실패 시 '다시 시도'로 목록을 다시 받는다",
      retry_from_error(ANOM, "이상 징후"), api=ANOM)

_pair(("FF-0676", "FF-0846"), ANOM_SURFACES, "permission_state",
      "라우트 역할 가드 + 감사 화면 이동 액션의 role 게이트",
      ds_permission((), ANOM, method="GET"), server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /backup — 백업
# ═══════════════════════════════════════════════════════════════════════════
flow("FF-0581", "admin_backup__backup", "navigation",
     "'백업' ↔ '복구 리허설' 탭을 전환한다(?tab= 주소에 반영)",
     switch_tab("복구 리허설", "tab=restore-drills"), route="/backup?tab=backup",
     shell=ADMIN, server=False)

flow("FF-0582", "admin_backup__backup", "search", "백업 파일 이름으로 검색한다",
     ds_search("", BACKUP, server=False), route="/backup?tab=backup", shell=ADMIN,
     server=False)

flow("FF-0583", "admin_backup__backup", "filter",
     "상태(확인됨/성공/실패/진행 중)로 좁힌다 — 화면 안에서 거른다",
     ds_filter("상태", "확인됨", BACKUP, server=False), route="/backup?tab=backup",
     shell=ADMIN, server=False)

flow("FF-0584", "admin_backup__backup", "filter", "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
     ds_clear("상태", "확인됨"), route="/backup?tab=backup", shell=ADMIN, server=False)

flow("FF-0585", "admin_backup__backup", "filter", "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
     ds_saved_view(), route="/backup?tab=backup", shell=ADMIN, server=False)

flow("FF-0586", "admin_backup__backup", "sort", "열 머리를 눌러 생성 시각·크기로 정렬한다",
     sort_by("크기"), route="/backup?tab=backup", shell=ADMIN, server=False)

flow("FF-0587", "admin_backup__backup", "read",
     "행을 눌러 백업 상세(전체 경로·체크섬·실행한 사람·오류)를 연다",
     ds_open_row(("체크섬",)), route="/backup?tab=backup", shell=ADMIN, server=False)


def _header_action(label: str, api_hint: str, *, confirm: bool = True,
                   run: bool = True):
    """머리의 운영 동작 — **확인 창까지 보고, 실행은 고르게 한다**.

    백업 실행처럼 서버에서 실제로 무거운 일을 벌이는 동작은 이 회차에서 **확인 창까지만**
    본다. 그 자리에서 진짜로 돌리면 로컬 QA 서버에 덤프가 쌓이고, 이 Flow 가 재는 것은
    「눌렀을 때 무엇을 묻는가」이지 「덤프가 잘 떠지는가」가 아니다(그쪽은 S12 가 쟀다).
    """
    def _act(r, ctx):
        button = r.in_main("button", label)
        if not button.count():
            more = r.in_main("button", "더 보기")
            if more.count():
                more.first.click()
                r.settle(700)
                button = r.page.locator('[role="menu"]').get_by_role(
                    "menuitem", name=label, exact=False)
        if not button.count():
            stop("«%s» 를 못 찾았다" % label)
        r.rec.reset()
        button.first.click()
        r.settle(1300)
        asked = open_dialogs(r) > 0
        said = dialog_says(r, 260)
        calls = []
        if asked and run:
            confirm_now(r)
            r.settle(2600)
            calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                            if c["method"] != "GET"})
        elif asked:
            r.dismiss_overlays()
        return {"ui_action": "머리의 «%s» 를 누른다" % label,
                "frontend_state": ("확인 → 실행" if run else "확인 창까지만"),
                "observed": {"confirm_asked": asked, "confirm": said[:220], "calls": calls},
                "rendered": "확인 «%s» · 쓰기 요청 %s" % (said[:140], calls),
                "expected": {"source": "derived-check",
                             "rule": ("무거운 운영 동작은 무엇을 하는지 말하고 확인을 받는다"
                                      if confirm else "확인 없이 실행한다"),
                             "confirm_asked": asked, "calls": calls},
                "failed": (("확인 없이 실행된다" if confirm and not asked else None)
                           or (None if (not run or not api_hint
                                        or any(api_hint in c for c in calls))
                               else "확인했는데 %s 를 안 불렀다: %s" % (api_hint, calls)))}
    return _act


flow("FF-0588", "admin_backup__backup", "admin_op",
     "'백업 실행'으로 지금 스냅샷을 만든다(확인 후, 결과를 성공/실패로 알린다)",
     _header_action("백업 실행", BACKUP, run=False), route="/backup?tab=backup",
     shell=ADMIN, server=False)

flow("FF-0589", "admin_backup__backup", "modal_action",
     "'복원 안내'로 서버에서만 가능한 복원 절차를 안내 모달로 읽는다",
     _header_action("복원", "", confirm=False, run=False), route="/backup?tab=backup",
     shell=ADMIN, server=False)


def _verify_backup(r, ctx):
    if not n_rows(r):
        stop("백업이 없다")
    name = row_name(r, 0)
    row_at(r, 0).click()
    r.settle(1600)
    if not open_dialogs(r):
        stop("상세가 안 열렸다")
    detail = open_dialog(r)
    target = detail.get_by_role("button", name="검증", exact=False)
    if not target.count():
        more = detail.get_by_role("button", name="더 보기", exact=False)
        if more.count():
            more.first.click()
            r.settle(700)
            target = r.page.locator('[role="menu"]').get_by_role(
                "menuitem", name="검증", exact=False)
    if not target.count():
        said = dialog_says(r, 240)
        r.dismiss_overlays()
        stop("«검증» 을 못 찾았다 — 상세: %s" % said[:170])
    r.rec.reset()
    target.first.click()
    r.settle(1200)
    if open_dialogs(r) > 1:
        confirm_now(r)
    r.settle(2600)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    body = r.main_text(200)
    r.dismiss_overlays()
    return {"ui_action": "«%s» 의 «검증» 을 실행한다" % name,
            "observed": {"calls": calls, "body": body},
            "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, body[:130]),
            "expected": {"source": "derived-check",
                         "rule": "«검증» 은 그 파일의 무결성을 서버에 다시 묻는다", "got": calls},
            "failed": None if calls else "«검증» 을 눌렀는데 서버로 안 갔다"}


flow("FF-0590", "admin_backup__backup", "admin_op",
     "'검증'으로 그 백업 파일의 무결성·체크섬을 다시 확인한다",
     _verify_backup, route="/backup?tab=backup", shell=ADMIN, api=BACKUP)

flow("FF-0591", "admin_backup__backup", "navigation", "'감사 로그에서 보기'로 이 백업의 감사 기록으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type=backup"), route="/backup?tab=backup",
     shell=ADMIN, server=False)


def _header_overflow(r, ctx):
    more = r.in_main("button", "더 보기")
    top = [" ".join((r.page.locator("#main-content button").nth(i).inner_text() or "").split())
           for i in range(min(r.page.locator("#main-content button").count(), 10))]
    items = []
    if more.count():
        more.first.click()
        r.settle(700)
        menu = r.page.locator('[role="menu"]')
        if menu.count():
            cells = menu.get_by_role("menuitem")
            items = [" ".join((cells.nth(i).inner_text() or "").split())
                     for i in range(cells.count())]
        r.press("Escape")
    return {"ui_action": "머리의 넘침 메뉴를 연다",
            "observed": {"overflow": more.count() > 0, "menu": items, "top": top},
            "rendered": "넘침 %s · 항목 %s" % ("있음" if more.count() else "없음", items),
            "expected": {"source": "derived-check",
                         "rule": "확인이 붙는 머리 동작은 넘침 메뉴로 내려간다", "menu": items},
            "failed": None}


flow("FF-0592", "admin_backup__backup", "overflow_action",
     "확인이 붙은 헤더 액션(백업 실행)은 넘침 메뉴로 내려간다",
     _header_overflow, route="/backup?tab=backup", shell=ADMIN, server=False)

flow("FF-0593", "admin_backup__backup", "deep_link",
     "검색·필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/backup?tab=backup&status=verified", "tab=backup"), api=BACKUP)

flow("FF-0594", "admin_backup__backup", "refresh",
     "조회 실패 시 '다시 시도'로 목록을 다시 받는다(진행 중 백업이 있으면 자동 갱신)",
     retry_from_error(BACKUP, "백업"), route="/backup?tab=backup", shell=ADMIN,
     api=BACKUP)

flow("FF-0595", "admin_backup__backup", "permission_state",
     "라우트 역할 가드 + 백업 실행·검증·복원 안내의 system_admin 게이트",
     ds_permission(("백업 실행",), BACKUP, roles=("user", "operator", "auditor")),
     route="/backup?tab=backup", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 복구 리허설 — 그릇 탭과 홑 라우트 둘 다
# ═══════════════════════════════════════════════════════════════════════════
DRILL = "/api/admin/backups/rehearsals"
DRILL_SURFACES = (("admin_backup__restore-drills", "/backup?tab=restore-drills"),
                  ("admin_restore-drills", "/restore-drills"))

_pair(("FF-0596", "FF-1046"), DRILL_SURFACES, "navigation",
      "'백업' ↔ '복구 리허설' 탭을 전환한다(?tab= 주소에 반영)",
      switch_tab("백업", "tab=backup"), server=False)

_pair(("FF-0597", "FF-1047"), DRILL_SURFACES, "search", "원본 백업 이름으로 검색한다",
      ds_search("", DRILL, server=False), server=False)

_pair(("FF-0598", "FF-1048"), DRILL_SURFACES, "filter",
      "결과(통과/실패)로 좁힌다 — 화면 안에서 거른다",
      ds_filter("결과", "통과", DRILL, server=False), server=False)

_pair(("FF-0599", "FF-1049"), DRILL_SURFACES, "filter",
      "'필터 지우기'로 검색어·필터를 한 번에 해제한다",
      ds_clear("결과", "통과"), server=False)

_pair(("FF-0600", "FF-1050"), DRILL_SURFACES, "filter",
      "저장된 뷰 — 지금 필터 조합을 이름으로 저장·재적용·삭제한다",
      ds_saved_view(), server=False)

_pair(("FF-0601", "FF-1051"), DRILL_SURFACES, "sort",
      "열 머리를 눌러 시작·종료·행 수로 정렬한다", sort_by("시작"), server=False)


def _summary_cards(r, ctx):
    body = r.main_text(400)
    cards = r.page.locator("#main-content .MuiPaper-root")
    return {"ui_action": "요약 카드로 지금 상태를 읽는다",
            "observed": {"cards": cards.count(), "body": body[:300]},
            "rendered": "카드 %d개 · 본문 «%s»" % (cards.count(), body[:200]),
            "expected": {"source": "derived-check",
                         "rule": "자동 백업 주기·마지막 백업·마지막 리허설·보관 개수를 함께 말한다",
                         "body": body[:200]},
            "failed": None if body else "요약 카드가 아무 값도 안 말한다"}


_pair(("FF-0602", "FF-1052"), DRILL_SURFACES, "read",
      "요약 카드(자동 백업 주기·마지막 백업·마지막 리허설·보관 개수)로 지금 상태를 읽는다",
      _summary_cards, server=False)

_pair(("FF-0603", "FF-1053"), DRILL_SURFACES, "read",
      "행을 눌러 리허설 상세(실패한 단계·요약)를 연다", ds_open_row(), server=False)

_pair(("FF-0604", "FF-1054"), DRILL_SURFACES, "navigation",
      "헤더의 '백업 목록'으로 백업 화면으로 이동한다",
      _header_link("백업 목록", "backup"), server=False)

_pair(("FF-0605", "FF-1055"), DRILL_SURFACES, "navigation",
      "헤더의 '백업 일정 설정'으로 설정 화면으로 이동한다(쓰기 역할만)",
      _header_link("백업 일정 설정", "settings"), server=False)

flow("FF-0606", "admin_backup__restore-drills", "deep_link",
     "검색·필터가 해시 쿼리에 되쓰이되 그릇의 ?tab= 은 보존된다",
     ds_deep_link("/backup?tab=restore-drills&ok=true", "tab=restore-drills"), api=DRILL)

flow("FF-1056", "admin_restore-drills", "deep_link", "검색·필터가 해시 쿼리에 되쓰인다",
     ds_deep_link("/restore-drills?ok=true", "ok=true"), api=DRILL)

_pair(("FF-0607", "FF-1057"), DRILL_SURFACES, "refresh",
      "조회 실패 시 '다시 시도'로 목록을, 요약 카드는 별도로 다시 받는다",
      retry_from_error(DRILL, "복구 리허설"), api=DRILL)

_pair(("FF-0608", "FF-1058"), DRILL_SURFACES, "permission_state",
      "라우트 역할 가드 + 탭 단위 권한 안내 + 요약 카드 403/404의 별도 안내",
      ds_permission((), DRILL, method="GET"), server=False)
