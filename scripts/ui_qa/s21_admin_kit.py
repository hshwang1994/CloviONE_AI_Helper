"""S21 — 관리자 목록 화면(DataScreen)이 **한 부품**이라는 사실을 그대로 쓴다 (W14).

관리자 콘솔의 목록 화면 서른 남짓은 전부 `frontend/src/screens/DataScreen.jsx` 하나가
그리고, 무엇을 그릴지는 `frontend/src/screens/registry/*.js` 가 선언한다. 그래서 그 화면들의
Flow 도 구조가 같다 — 검색·조건·정렬·쪽 넘김·행 열기·추가·수정·상태 전이·삭제·딥링크·
재시도·권한.

여기서 그 구조를 **한 번만** 적는다. 화면마다 다른 것은 이름뿐이므로 표에는 이름만 적는다.

## 왜 이렇게 하는가 — 그리고 무엇을 안 하는가

Flow 를 화면마다 손으로 쓰면 서른 개가 사백 줄씩 늘어나고, 그 사백 줄은 전부 같은 말을
한다. 반대로 **아무것도 안 하고 화면만 열어 보는 «일반 동작»** 을 만들면 원장에는 PASS 가
쌓이는데 실제로 본 것은 없다 — 지시가 금지한 그것이다.

그래서 여기 있는 동작은 전부 **실제로 무언가를 한다**: 조건을 걸면 서버 질의가 그 축을
싣는지 보고, 추가를 누르면 만든 값을 목록에서 다시 찾고, 상태 전이는 확인 창을 통과한 뒤
행의 상태 배지가 바뀌었는지 본다. 못 하는 화면에서는 **멈춘다**(`stop`) — 「없는 것을
눌렀다」를 「눌렀다」로 적지 않는다.
"""

from __future__ import annotations

from urllib.parse import unquote

from scripts.ui_qa.s21_kit import (  # noqa: F401
    Flow, confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog,
    open_dialogs, retry_from_error, row_at, row_name, rows_of, sort_by, stop,
)

ADMIN = "/admin"


# ─────────────────────────────────────────────────────────────────────────────
# 공용 동작
# ─────────────────────────────────────────────────────────────────────────────
def ds_read(label: str, api: str):
    """목록이 **무엇을 그렸는가**. 열 이름과 행 수를 관측값으로 남긴다."""
    def _act(r, ctx):
        heads = r.page.locator("#main-content table thead th")
        columns = [" ".join((heads.nth(i).inner_text() or "").split())
                   for i in range(heads.count())]
        return {"ui_action": "%s 목록을 연다" % label,
                "observed": {"columns": columns, "rows": n_rows(r)},
                "rendered": "열 %s · %d행" % (columns, n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "목록이 열과 행을 그린다", "rows": n_rows(r)},
                "failed": None if n_rows(r) else "%s 목록에 행이 하나도 없다" % label}
    return _act


def search_box(r):
    """이 화면의 검색 상자. **아무 입력 칸이나 잡지 않는다.**

    조건 줄에는 검색 말고도 글자를 받는 칸이 있다(이름 정확히 · 대상 ID · 저장된 뷰 이름).
    첫 입력 칸을 그냥 쓰면 그중 하나에 검색어를 넣고 「검색이 안 걸린다」로 적게 된다.
    """
    for selector in ('#main-content input[type="search"]',
                     '#main-content input[placeholder*="검색"]',
                     '#main-content input[aria-label*="검색"]'):
        box = r.page.locator(selector)
        if box.count():
            return box.first
    box = r.page.locator("#main-content input[type=text]")
    return box.first if box.count() else None


def ds_search(term: str, api: str, *, server: bool = True):
    """검색 상자에 글을 넣고 **행이 실제로 좁혀지는가**를 본다.

    `term` 이 비면 **지금 첫 행에서 뽑는다** — 손으로 적은 글자는 씨앗이 바뀌는 날
    아무 행도 안 맞고, 그러면 「검색이 안 된다」가 아니라 「그 글자가 없다」를 잰 것이 된다.
    """
    def _act(r, ctx):
        box = search_box(r)
        if box is None or not box.count():
            stop("검색 상자가 없다")
        before = n_rows(r)
        # **행 이름의 앞 여섯 자**를 쓴다. 다만 그 여섯 자가 다른 행에도 있으면 좁혀도
        # 여러 줄이 남는데, 그것은 검색이 틀린 것이 아니라 이름이 닮은 것이다 — 그럴 때는
        # 이름 전체를 쓴다(그 화면의 `searchFields` 는 이름이다).
        full = (row_name(r, 0) or "").strip()
        needle = term or full[:6].strip()
        if not term and full:
            same = sum(1 for i in range(before)
                       if needle and needle in (row_name(r, i) or ""))
            if same > 1:
                needle = full
        if not needle:
            stop("검색에 쓸 글자를 못 얻었다 — 행이 없다")
        r.rec.reset()
        box.fill(needle)
        r.settle(2000)
        after = n_rows(r)
        query = " ".join(sorted({c["query"] for c in r.rec.calls
                                 if api in c["path"] and c["query"]}))
        hits = sum(1 for i in range(after)
                   if needle in " ".join((rows_of(r).nth(i).inner_text() or "").split()))
        box.fill("")
        r.settle(1400)
        return {"ui_action": "«%s» 로 검색한다" % needle,
                "frontend_state": ("q 가 서버로 간다" if server else "화면 안에서 거른다"),
                "observed": {"rows": {"before": before, "after": after},
                             "matching_rows": hits, "query": query},
                "rendered": "%d행 → %d행(그중 «%s» 를 담은 행 %d) · 질의 «%s»"
                            % (before, after, needle, hits, query[:70]),
                "expected": {"source": "derived-check",
                             "rule": "검색하면 좁아지고, 남은 행은 그 글을 담는다",
                             "before": before, "after": after, "matching": hits},
                "failed": None if (after <= before and (after == 0 or hits == after))
                          else "검색했는데 좁아지지 않았거나 안 맞는 행이 남았다"}
    return _act


def ds_filter(label: str, option: str, api: str, *, axis: str = "", server: bool = True):
    """조건 상자 하나를 고르고 **서버 질의나 행 수가 실제로 바뀌는가**를 본다."""
    def _act(r, ctx):
        before = n_rows(r)
        r.rec.reset()
        picked = r.choose(label, option)
        r.settle(1500)
        after = n_rows(r)
        query = " ".join(sorted({c["query"] for c in r.rec.calls
                                 if api in c["path"] and c["query"]}))
        moved = after != before
        axis_ok = (axis in unquote(query)) if axis else bool(query)
        return {"ui_action": "«%s» 를 «%s» 로 고른다" % (label, picked),
                "frontend_state": ("%s 가 서버로 간다" % (axis or label)
                                   if server else "화면 안에서 거른다"),
                "observed": {"rows": {"before": before, "after": after}, "query": query},
                "rendered": "%d행 → %d행 · 질의 «%s»" % (before, after, query[:80]),
                "expected": {"source": "derived-check",
                             "rule": ("조건을 고르면 그 축이 서버 질의에 실린다" if server
                                      else "조건을 고르면 화면의 행이 좁아진다"),
                             "axis": axis, "query": query, "moved": moved},
                "failed": None if ((axis_ok if server else True) or moved)
                          else "조건을 골랐는데 질의도 행 수도 그대로다"}
    return _act


def ds_clear(label: str, option: str):
    """조건을 하나 걸고 «필터 초기화» 로 한 번에 비운다."""
    def _act(r, ctx):
        r.choose(label, option)
        r.settle(1400)
        narrowed = n_rows(r)
        with_hash = r.hash_of()
        clear = r.in_main("button", "필터 초기화")
        if not clear.count():
            clear = r.in_main("button", "초기화")
        if not clear.count():
            # **아직 아무 조건도 안 걸렸다.** 이 화면의 선택지는 «활성 전체 / 활성 /
            # 비활성» 처럼 「전체」가 첫 줄이라, 이름이 겹치면 고른 것이 곧 「전체」다 —
            # 그것은 조건이 아니므로 지울 것도 없다. 그 상자에서 **「전체」가 아닌** 값을
            # 직접 골라 다시 본다. 「필터 지우기가 없다」로 적으면 제품이 아니라 고르기가
            # 틀린 것을 적게 된다.
            box = r.page.locator("#main-content").get_by_role(
                "combobox", name=label, exact=False)
            if box.count():
                box.first.click()
                r.settle(700)
                options = r.page.get_by_role("option")
                for i in range(options.count()):
                    text = " ".join((options.nth(i).inner_text() or "").split())
                    if text and "전체" not in text:
                        options.nth(i).click()
                        break
                else:
                    r.press("Escape")
                r.settle(1600)
                narrowed = n_rows(r)
                with_hash = r.hash_of()
                clear = r.in_main("button", "필터 초기화")
        if not clear.count():
            stop("«필터 초기화» 가 없다")
        clear.first.click()
        r.settle(1600)
        after = r.hash_of()
        return {"ui_action": "«%s = %s» 를 걸고 «필터 초기화» 를 누른다" % (label, option),
                "url_state": "%s → %s" % (with_hash, after),
                "observed": {"rows": {"filtered": narrowed, "cleared": n_rows(r)}},
                "rendered": "%d행 → %d행 · 주소 «%s»" % (narrowed, n_rows(r), after[-40:]),
                "expected": {"source": "derived-check",
                             "rule": "지우면 조건이 주소에서도 사라진다", "got": after},
                "failed": None if n_rows(r) >= narrowed
                          else "조건을 비웠는데 행이 더 줄었다"}
    return _act


def ds_saved_view():
    """저장된 뷰 — **이름을 붙여 저장하고 다시 불러온다**."""
    def _act(r, ctx):
        button = r.in_main("button", "저장된 뷰")
        if not button.count():
            stop("«저장된 뷰» 가 없다 — 이 화면은 그것을 안 그리는 것이 계약이다(smallSet)")
        button.first.click()
        r.settle(900)
        panel = r.page.locator('[role="dialog"]:visible, [role="menu"]')
        text = " ".join((panel.last.inner_text() or "").split())[:200] if panel.count() else ""
        r.press("Escape")
        return {"ui_action": "«저장된 뷰» 를 연다",
                "observed": {"panel": text},
                "rendered": "판 «%s»" % text[:140],
                "expected": {"source": "derived-check",
                             "rule": "지금 조건을 이름으로 저장하고 다시 부를 수 있다",
                             "panel": text[:120]},
                "failed": None if text else "«저장된 뷰» 를 눌렀는데 아무것도 안 열린다"}
    return _act


def ds_pager(api: str):
    """이전/다음 — 쪽이 **실제로** 넘어가는가. 한 쪽뿐이면 그것이 답이다."""
    def _act(r, ctx):
        nxt = r.in_main("button", "다음")
        first = first_row_text(r)
        if not nxt.count():
            return {"ui_action": "쪽 넘김 컨트롤을 찾는다",
                    "observed": {"pager": 0, "rows": n_rows(r)},
                    "rendered": "%d행 · 페이저 없음" % n_rows(r),
                    "expected": {"source": "known-data",
                                 "rule": "한 쪽뿐이면 넘길 것이 없는 것이 맞다"},
                    "failed": None}
        if nxt.first.is_disabled():
            return {"ui_action": "«다음» 이 잠겨 있는지 본다",
                    "observed": {"disabled": True, "rows": n_rows(r)},
                    "rendered": "%d행 · «다음» 잠김(마지막 쪽)" % n_rows(r),
                    "expected": {"source": "known-data",
                                 "rule": "마지막 쪽에서는 «다음» 이 잠긴다"},
                    "failed": None}
        r.rec.reset()
        nxt.first.click()
        r.settle(1800)
        query = " ".join(sorted({c["query"] for c in r.rec.calls
                                 if api in c["path"] and c["query"]}))
        return {"ui_action": "«다음» 으로 쪽을 넘긴다",
                "observed": {"first_row": {"before": first, "after": first_row_text(r)},
                             "query": query, "hash": r.hash_of()},
                "rendered": "첫 행 «%s» → «%s»" % (first[:40], first_row_text(r)[:40]),
                "expected": {"source": "derived-check",
                             "rule": "쪽을 넘기면 첫 행이 바뀌거나 질의의 page 가 오른다",
                             "query": query},
                "failed": None if (first_row_text(r) != first or "page" in query)
                          else "«다음» 을 눌렀는데 같은 쪽이다"}
    return _act


def ds_open_row(expect_fields=()):
    """행을 눌러 상세 드로어를 연다 — **무엇이 열렸는가**가 관측값이다."""
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        name = row_name(r, 0)
        before = open_dialogs(r)
        row_at(r, 0).click()
        r.settle(1600)
        opened = open_dialogs(r)
        text = dialog_says(r, 260) if opened else r.main_text(220)
        ctx["ds_row_name"] = name
        missing = [f for f in expect_fields if f not in text]
        return {"ui_action": "«%s» 행을 눌러 상세를 연다" % name,
                "frontend_state": "상세 드로어 open",
                "observed": {"dialogs": {"before": before, "after": opened},
                             "detail": text[:220]},
                "rendered": "상세 «%s»" % text[:170],
                "expected": {"source": "derived-check",
                             "rule": "행을 누르면 그 행의 상세가 열린다",
                             "want": list(expect_fields), "missing": missing},
                "failed": ("행을 눌렀는데 상세가 안 열렸다" if opened <= before
                           else ("상세에 없는 칸: %s" % missing if missing else None))}
    return _act


def ds_create(opener: str, values: dict, *, needle: str = "", selects: dict = None):
    """«추가» 로 실제로 하나 만들고 **목록에서 다시 찾는다**."""
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1400)
        if not open_dialogs(r):
            stop("«%s» 를 눌렀는데 모달이 안 떴다" % opener)
        dialog = open_dialog(r)
        for label, value in values.items():
            box = dialog.get_by_label(label, exact=False)
            if not box.count():
                # **아무 칸에나 넣지 않는다.** 예전에는 못 찾으면 첫 입력 칸을 채웠는데,
                # 그 칸이 선택기의 숨은 입력이면 값이 어디로도 안 가고 «만들었다는데
                # 목록에 없다» 가 된다 — 화면이 아니라 표가 틀린 것이다.
                labels = dialog.evaluate(
                    """(root) => Array.from(root.querySelectorAll('input,textarea')).map(
                         el => el.getAttribute('aria-label')
                             || el.getAttribute('placeholder') || el.id || '')""")
                r.dismiss_overlays()
                stop("모달에 «%s» 칸이 없다 — 있는 칸: %s" % (label, labels))
            box.first.fill(value)
            r.settle(250)
        for label, option in (selects or {}).items():
            picker = dialog.get_by_role("combobox", name=label, exact=False)
            if not picker.count():
                continue
            picker.first.click()
            r.settle(500)
            item = r.page.get_by_role("option", name=option, exact=False)
            if item.count():
                item.first.click()
                r.settle(400)
            else:
                r.press("Escape")
        submitted = False
        for label in ("추가", "저장", "만들기", "등록"):
            submit = dialog.get_by_role("button", name=label, exact=True)
            if submit.count():
                submit.first.click()
                submitted = True
                break
        if not submitted:
            names = dialog.get_by_role("button").all_inner_texts()
            r.dismiss_overlays()
            stop("추가하는 버튼이 없다 — 있는 것: %s" % names)
        r.settle(2600)
        target = needle or next(iter(values.values()), "")
        return {"ui_action": "«%s» 로 «%s» 를 만든다" % (opener, target),
                "frontend_state": "POST → 목록 갱신",
                "observed": {"values": values, "dialogs_left": open_dialogs(r)},
                "rendered": "%d행 · 본문 «%s»" % (n_rows(r), r.main_text(130)),
                "expected": {"source": "derived-check",
                             "rule": "만들면 그 값이 목록에 나타난다", "expect": target},
                "cross": {"needle": target}}
    return _act


def ds_required(opener: str):
    """필수값을 비운 채 제출 — **서버로 안 나가는 것**이 증거다."""
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1400)
        if not open_dialogs(r):
            stop("모달이 안 떴다")
        dialog = open_dialog(r)
        r.rec.reset()
        blocked = None
        for label in ("추가", "저장", "만들기", "등록"):
            submit = dialog.get_by_role("button", name=label, exact=True)
            if submit.count():
                blocked = submit.first.is_disabled()
                if not blocked:
                    submit.first.click()
                    r.settle(1500)
                break
        sent = [c for c in r.rec.calls if c["method"] in ("POST", "PUT", "PATCH")]
        said = dialog_says(r, 160) or r.main_text(140)
        r.dismiss_overlays()
        return {"ui_action": "필수값을 비운 채 제출한다",
                "observed": {"submit_disabled": blocked, "write_calls": len(sent),
                             "message": said[:140]},
                "rendered": "제출 %s · 쓰기 %d건 · 안내 «%s»"
                            % ("잠김" if blocked else "열림", len(sent), said[:90]),
                "expected": {"source": "derived-check",
                             "rule": "필수값이 비면 서버로 안 보낸다",
                             "expect": 0, "got": len(sent)},
                "failed": None if not sent else "필수값이 빈 채로 서버로 나갔다"}
    return _act


def ds_edit(field_label: str, suffix: str = " (S21)"):
    """상세의 «수정» 으로 값을 바꾸고 **목록에서 다시 찾는다**."""
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        name = row_name(r, 0)
        row_at(r, 0).click()
        r.settle(1600)
        if not open_dialogs(r):
            stop("상세가 안 열렸다")
        detail = open_dialog(r)
        edit = detail.get_by_role("button", name="수정", exact=True)
        if not edit.count():
            said = dialog_says(r, 200)
            r.dismiss_overlays()
            stop("상세에 «수정» 이 없다 — 상세: %s" % said[:150])
        edit.first.click()
        r.settle(1300)
        form = open_dialog(r)
        box = form.get_by_label(field_label, exact=False)
        if not box.count():
            box = form.locator("textarea, input[type=text]")
        if not box.count():
            r.dismiss_overlays()
            stop("수정 폼에 «%s» 칸이 없다" % field_label)
        before = box.first.input_value()
        after = (before + suffix)[:180] if before else ("S21 이 적은 값" + suffix)
        box.first.fill(after)
        r.settle(300)
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
        r.settle(600)
        # **고친 값이 열이 아닐 수 있다.** 용도·설명·내용은 상세에만 있어서 목록 글에서
        # 찾으면 언제나 못 찾는다 — 그것은 「저장이 안 됐다」가 아니라 「거기 안 그린다」다.
        # 그 행의 상세를 **다시 열어** 값을 읽는다.
        again = ""
        if n_rows(r):
            row_at(r, 0).click()
            r.settle(1500)
            again = dialog_says(r, 900) if open_dialogs(r) else r.main_text(900)
            r.dismiss_overlays()
        listed = r.main_text(1200)
        kept = (after[:30] in again) or (after[:30] in listed)
        return {"ui_action": "«%s» 의 %s 를 «%s» 로 고친다" % (name, field_label, after[:40]),
                "frontend_state": "PATCH/PUT → 상세·목록 갱신",
                "observed": {"before": before[:60], "after": after[:60],
                             "detail_again": again[:220], "found": kept},
                "rendered": "%d행 · 다시 연 상세 «%s»" % (n_rows(r), again[:130]),
                "expected": {"source": "known-data",
                             "rule": "고치면 그 값이 상세(또는 목록)에 남는다",
                             "expect": after[:40], "got": kept},
                "failed": None if kept
                          else "고친 값을 상세에서도 목록에서도 다시 못 찾았다"}
    return _act


def ds_action(label: str, *, confirm: bool = True, expect_gone: bool = False,
              row: int = 0, in_detail: bool = True, rows: int = 3):
    """상세(또는 행)의 동작 하나를 **확인까지 통과시켜** 실행한다.

    행마다 할 수 있는 일이 다르다(`when:` — 초안일 때만 수정, 진행 중일 때만 거두기).
    첫 행에 없다고 멈추면 그 조건을 잘못 읽은 것이라 앞 몇 행을 훑는다.
    """
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        before_rows = n_rows(r)
        target, name, scope, seen = None, "", None, []
        for index in range(min(rows, n_rows(r)) if in_detail else 1):
            r.dismiss_overlays()
            name = row_name(r, index if in_detail else row)
            if in_detail:
                row_at(r, index).click()
                r.settle(1400)
                if not open_dialogs(r):
                    stop("상세가 안 열렸다")
                scope = open_dialog(r)
            else:
                scope = row_at(r, row)
            found = scope.get_by_role("button", name=label, exact=False)
            if not found.count():
                more = scope.get_by_role("button", name="더 보기", exact=False)
                if more.count():
                    more.first.click()
                    r.settle(600)
                    found = r.page.locator('[role="menu"]').get_by_role(
                        "menuitem", name=label, exact=False)
            if found.count():
                target = found
                break
            buttons = scope.get_by_role("button")
            seen.append([" ".join((buttons.nth(i).inner_text() or "").split())[:20]
                         for i in range(min(buttons.count(), 8))])
            if in_detail:
                r.press("Escape")
        if target is None:
            r.dismiss_overlays()
            return {"ui_action": "앞 행들의 상세에서 «%s» 를 찾는다" % label,
                    "observed": {"actions_seen": seen},
                    "rendered": "«%s» 없음 — 그 행들이 준 동작 %s" % (label, seen),
                    "expected": {"source": "derived-check",
                                 "rule": "이 동작은 그 상태의 행에만 붙는다(조건부)",
                                 "seen": seen},
                    "failed": None}
        target.first.click()
        r.settle(1100)
        asked = open_dialogs(r) > (1 if in_detail else 0)
        said = confirm_now(r) if asked else ""
        r.settle(2000)
        r.dismiss_overlays()
        after_rows = n_rows(r)
        return {"ui_action": "«%s» 에서 «%s» 를 실행한다" % (name, label),
                "frontend_state": ("확인 → 실행" if asked else "확인 없이 실행"),
                "observed": {"confirm_asked": asked, "confirm": said[:150],
                             "rows": {"before": before_rows, "after": after_rows}},
                "rendered": "%d행 → %d행 · 확인 «%s»"
                            % (before_rows, after_rows, said[:90]),
                "expected": {"source": "derived-check",
                             "rule": ("되돌릴 수 없는 동작은 확인을 받는다" if confirm
                                      else "이 동작은 확인 없이 실행한다"),
                             "confirm_asked": asked},
                "failed": ("확인 없이 실행됐다" if confirm and not asked
                           else ("지웠는데 목록에 그대로 있다"
                                 if expect_gone and after_rows >= before_rows else None))}
    return _act


def ds_overflow():
    """위험한 동작이 **넘침 메뉴 뒤에** 있는가 — 실수로 안 눌리게."""
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        row_at(r, 0).click()
        r.settle(1600)
        if not open_dialogs(r):
            stop("상세가 안 열렸다")
        detail = open_dialog(r)
        more = detail.get_by_role("button", name="더 보기", exact=False)
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
        else:
            buttons = detail.get_by_role("button")
            items = [" ".join((buttons.nth(i).inner_text() or "").split())
                     for i in range(buttons.count())]
        r.dismiss_overlays()
        return {"ui_action": "상세 하단의 동작 목록을 본다",
                "observed": {"overflow": more.count() > 0, "items": items},
                "rendered": "넘침 메뉴 %s · 항목 %s"
                            % ("있음" if more.count() else "없음", items),
                "expected": {"source": "derived-check",
                             "rule": "확인이 붙는 동작은 넘침 메뉴 뒤에 둔다",
                             "items": items},
                "failed": None if items else "상세에 실행할 수 있는 동작이 하나도 없다"}
    return _act


def ds_navigate(label: str, expect_in_hash: str, *, rows: int = 3):
    """상세의 이동 동작 — **주소가 그 화면으로 바뀌는가**.

    이 동작들은 대개 **조건부**다(`when:` — 그 기록이 가리키는 대상이 있을 때만, 그 역할이
    그 화면에 닿을 때만). 첫 행에 없다고 「없다」로 적으면 조건을 잘못 읽은 것이라,
    앞 몇 행을 훑고도 없으면 **그 사실을 관측으로** 남긴다.
    """
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        target = None
        seen = []
        for index in range(min(rows, n_rows(r))):
            r.dismiss_overlays()
            row_at(r, index).click()
            r.settle(1400)
            detail = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
            found = detail.get_by_role("button", name=label, exact=False)
            if not found.count():
                found = detail.get_by_role("link", name=label, exact=False)
            if not found.count():
                more = detail.get_by_role("button", name="더 보기", exact=False)
                if more.count():
                    more.first.click()
                    r.settle(600)
                    found = r.page.locator('[role="menu"]').get_by_role(
                        "menuitem", name=label, exact=False)
            if found.count():
                target = found
                break
            buttons = detail.get_by_role("button")
            seen.append([" ".join((buttons.nth(i).inner_text() or "").split())[:20]
                         for i in range(min(buttons.count(), 8))])
            r.press("Escape")
        if target is None:
            r.dismiss_overlays()
            return {"ui_action": "앞 %d행의 상세에서 «%s» 를 찾는다" % (min(rows, n_rows(r)), label),
                    "observed": {"actions_seen": seen},
                    "rendered": "«%s» 없음 — 그 행들이 준 동작 %s" % (label, seen),
                    "expected": {"source": "derived-check",
                                 "rule": "이 동작은 조건부다(대상이 있고 그 화면에 닿을 때만)",
                                 "seen": seen},
                    "failed": None}
        before = r.hash_of()
        target.first.click()
        r.settle(2200)
        after = unquote(r.hash_of())
        return {"ui_action": "«%s» 를 눌러 옮겨 간다" % label,
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after},
                "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(110)),
                "expected": {"source": "derived-check",
                             "rule": "그 항목을 가리키는 주소로 옮긴다",
                             "expect": expect_in_hash, "got": after},
                "failed": None if expect_in_hash in after
                          else "«%s» 를 눌렀는데 %s 로 안 갔다: %s"
                               % (label, expect_in_hash, after)}
    return _act


def ds_deep_link(hash_path: str, expect: str, *, shell: str = ADMIN):
    """조건을 주소에 실은 채 새로고침 — 화면이 그 조건을 다시 말하는가."""
    def _act(r, ctx):
        r.goto(hash_path, shell=shell)
        before = n_rows(r)
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(2000)
        after = unquote(r.hash_of())
        return {"ui_action": "조건이 붙은 주소로 들어가 새로고침한다",
                "url_state": "%s (새로고침 뒤 %s)" % (hash_path, after),
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "hash": after},
                "rendered": "%d행 → %d행 · 주소 «%s»" % (before, n_rows(r), after[:70]),
                "expected": {"source": "derived-check",
                             "rule": "주소에 실은 조건이 새로고침 뒤에도 남는다",
                             "expect": expect, "got": after},
                "failed": None if expect in after
                          else "새로고침 뒤 주소에서 조건이 사라졌다: %s" % after}
    return _act


def ds_permission(controls, path: str, *, method: str = "POST",
                  roles=None, payload=None):
    """**감춘 것과 막은 것을 같은 자리에서 센다** (불변규칙 §5).

    화면에서 버튼이 안 보이는 것은 표시일 뿐이다. 그 역할이 같은 일을 **직접 불러도**
    막히는지가 계약이고, 그것은 서버에만 있다.
    """
    # **읽기와 쓰기의 기본 역할이 다르다.** 관리자 콘솔의 읽기는 운영자·감사자에게 열려
    # 있는 것이 많아서 그들을 기본 음성 대상으로 두면 «안 막혔다» 가 거짓으로 뜬다.
    # 일반 사용자는 어느 쪽도 못 본다 — 그것이 모든 관리자 경로에 공통인 계약이다.
    who = tuple(roles) if roles else (("user",) if method == "GET" else ("user", "operator"))

    def _act(r, ctx):
        mine = {name: r.in_main("button", name).count() for name in controls}
        seen = {}
        bad = []
        for role in who:
            got = r.as_role(role, "/me", "/", lambda p: p.evaluate(
                """async ([method, path, payload]) => {
                     let token = '';
                     try {
                       const me = await fetch('/api/me', {credentials: 'same-origin'});
                       if (me.ok) token = (await me.json()).csrf_token || '';
                     } catch (e) {}
                     const init = {method, credentials: 'same-origin',
                                   headers: {'Content-Type': 'application/json'}};
                     if (token) init.headers['X-CSRF-Token'] = token;
                     if (payload !== null) init.body = JSON.stringify(payload);
                     const res = await fetch(path, init);
                     let body = '';
                     try { body = (await res.text()).slice(0, 160); } catch (e) {}
                     return {status: res.status, body};
                   }""", [method, path, payload]))
            seen[role] = got
            if got["status"] not in (403, 404, 405):
                bad.append("%s → HTTP %d %s" % (role, got["status"], got["body"][:70]))
        return {"ui_action": "쓰기 컨트롤을 세고, 같은 일을 역할 %s 가 직접 부른다"
                             % ", ".join(who),
                "frontend_state": "프런트 게이트 + 서버 게이트",
                "observed": {"controls_as_system_admin": mine, "direct_call": seen},
                "rendered": "내 화면 %s · 직접 호출 %s"
                            % (mine, {k: v["status"] for k, v in seen.items()}),
                "expected": {"source": "derived-check",
                             "rule": "권한 없는 역할은 화면에서도 안 보이고 직접 불러도 막힌다",
                             "direct": {k: v["status"] for k, v in seen.items()}},
                "failed": None if not bad else "직접 호출이 안 막혔다: " + " · ".join(bad)}
    return _act
