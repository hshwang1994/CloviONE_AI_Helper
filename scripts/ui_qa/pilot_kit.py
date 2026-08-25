"""Pilot Flow 표가 쓰는 **어휘** (W8 · S18).

`FUNCTIONAL_COVERAGE.json` 의 Flow 는 235개다. 하나마다 함수를 손으로 쓰면 하네스 자체가
읽을 수 없는 물건이 된다 — 그래서 Flow 는 **표**로 적고 엔진(`pilot_e2e.py`)이 실행한다.
이 파일은 그 표가 쓰는 낱말을 모아 둔다.

## 한 줄이 무엇을 뜻하는가

    flow("FF-0002", "user_me", "filter", "지표 줄을 눌러 아래 표의 버킷을 바꾼다",
         act, route="/me", api="/api/home/today", server=False)

  * `route` — 이 Flow 를 시작할 화면. 비우면 앞 Flow 가 남긴 화면에서 이어 간다.
  * `shell` — `/`(사용자) 또는 `/admin`. 관리자 화면은 셸이 다르다.
  * `api` — 사슬에 실을 요청을 고르는 조각. 비우면 그 동작 중 오간 요청 전부를 본다.
  * `server` — 이 동작이 **서버를 부르는가**. `False` 면 요청이 없어도 실패가 아니다.
    모달 열기·탭 전환·클라이언트 검증이 그렇다. 이 칸을 함부로 `False` 로 두면 사슬의
    서버 칸이 조용히 비므로, 부르는 것이 맞는 동작은 반드시 `True` 로 둔다.
  * `act` — 실제 조작. `Runner` 를 받아 관측값을 돌려준다.

`act` 가 돌려주는 dict 의 칸은 전부 선택이다: `ui_action` · `frontend_state` · `url_state` ·
`rendered` · `observed` · `notes` · `screenshots` · `failed`. 엔진은 **관측한 칸만** 싣는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote
from typing import Callable


@dataclass(frozen=True)
class Flow:
    id: str
    surface: str
    category: str
    name: str
    act: Callable
    route: str = ""
    shell: str = "/"
    api: str = ""
    server: bool = True
    # **다른 화면에서도 보이는가** (C13). 쓰기 범주(create·delete·상태/우선순위/담당자
    # 변경·inline_edit)는 «한 화면이 200 이라고 완료가 아니다» 가 계약이라, 바꾼 값이
    # 다른 화면에도 도착했는지 본다. `("<해시>", "<셸>")` 이고, 볼 것이 없는 화면은
    # `("@reload", "")` — 문서를 새로 읽어 그 값이 **서버에 들어갔는지**를 본다.
    cross: tuple = ()
    tags: tuple[str, ...] = field(default_factory=tuple)


FLOWS: list[Flow] = []


def flow(*args, **kwargs) -> None:
    FLOWS.append(Flow(*args, **kwargs))


def same_query(want: str, got: str) -> bool:
    """주소 두 개가 같은 조건을 말하는가.

    브라우저는 한글 조건을 퍼센트 인코딩해 둔다(`status=진행` → `status=%EC%A7%84%ED%96%89`).
    날것으로 비교하면 «뒤로가기가 원래 조건으로 안 돌아왔다» 가 언제나 참이 된다.
    """
    return unquote(want).split("#")[-1] in unquote(got)


def row_title(r, index: int = 0, prefix: str = "업무") -> str:
    """표의 행 하나에서 **그 행을 가리키는 제목**을 뽑는다.

    C13 의 대조는 «그 행에 그 값이 있는가» 라, 행을 찾을 열쇠가 필요하다. 씨앗의 티켓
    제목은 «업무 07 — …» 꼴이라 앞 여섯 글자면 한 행을 가리킨다.
    """
    # **값이 있는 행만 센다.** 티켓 표는 프로젝트로 묶여서 `tbody` 안에 «인프라 정비 4건»
    # 짜리 머리글 줄이 섞인다. 그 줄을 «행» 으로 잡으면 이 함수가 묶음 이름을 돌려주고,
    # 그 이름으로 다른 화면에서 행을 찾으니 언제나 못 찾는다 — S21 이 여섯 Flow 에서
    # 「저장이 안 갔다」를 그 이유로 잘못 적었다.
    row = r.page.locator("table tbody tr:has(td)").nth(index)
    if not row.count():
        return ""
    text = " ".join((row.inner_text() or "").split())
    hit = re.search(r"%s\s*\d+" % re.escape(prefix), text)
    return hit.group(0) if hit else text[:20]


def unquote_hash(value: str) -> str:
    """퍼센트 인코딩을 푼 해시 — 조건을 눈으로도 비교할 수 있게."""
    return unquote(value or "")


def title_like(prefix: str):
    """«업무 07 …» 같은 **제목**만 잡는 이름 패턴.

    부분 문자열로 «업무» 를 찾으면 담당자 카드의 «업무량 6인일» 도 걸린다 — 실제로 그
    카드를 눌러 조건이 걸렸고 Flow 는 「상세로 안 갔다」로 죽었다.
    """
    return re.compile(r"^%s\s*\d" % re.escape(prefix))


def stop(message: str):
    """이 Flow 를 여기서 멈춘다 — 「없는 것을 눌렀다」를 「눌렀다」로 적지 않는다."""
    from scripts.ui_qa.pilot_e2e import Stop

    raise Stop(message)


# --------------------------------------------------------------------------- #
# 조작 — 표가 그대로 쓰는 것들
# --------------------------------------------------------------------------- #
def just_load(what: str):
    """화면을 열기만 한다 — `read` 범주의 기본형."""
    def _act(r, ctx):
        return {"ui_action": "%s 를 연다" % what,
                "rendered": "본문 «%s»" % r.main_text(120)}
    return _act


def click_then(selector: str, *, says: str = "", index: int = 0, shot: str = "",
               expect: str = ""):
    """무언가를 누른다. `expect` 를 주면 **누른 뒤 그것이 실제로 왔는지**까지 본다.

    `expect` 는 주소나 본문에 있어야 할 글이다. 안 주면 예전처럼 누르기만 한다 — 지표
    화면(`/me`·`/sprint`)의 Flow 는 「눌렀더니 화면이 바뀌었다」로는 통과할 수 없어서
    (C13) 그쪽 호출부는 이 값을 반드시 준다.
    """
    def _act(r, ctx):
        before = r.hash_of()
        label = r.click(selector, index=index)
        out = {"ui_action": says or ("«%s» 를 누른다" % label)}
        if shot:
            out["screenshots"] = [r.shot(shot)]
        if expect:
            here = r.hash_of()
            body = r.main_text(400)
            found = expect in unquote_hash(here) or expect in body
            out["observed"] = {"url": {"before": before, "after": here}, "expect": expect}
            out["rendered"] = "주소 «%s» · 본문 «%s»" % (here, r.main_text(90))
            out["expected"] = {"source": "derived-check",
                               "rule": "누른 뒤 «%s» 가 주소나 본문에 있다" % expect,
                               "expect": expect, "got": here}
            out["failed"] = None if found else "«%s» 를 눌렀는데 «%s» 가 없다" % (label, expect)
        return out
    return _act


def rows_showing(r, needle: str) -> int:
    """표의 행 가운데 그 글을 담은 행 수. 조건이 **실제로 걸렸는지** 세는 자리다."""
    if not needle:
        return 0
    return r.page.locator("table tbody tr").filter(has_text=needle).count()


def choose_then(combo: str, option: str, *, says: str = "", index: int = 0):
    """조건 상자 하나를 골라 **표가 실제로 줄었는지**까지 적는다.

    행 수만 적으면 「아무것도 안 걸리는 조건」이 통과한다 — 원래 그렇게 통과했다. 조건이
    지켜야 하는 것 둘을 함께 본다: 조건은 **결과를 넓히지 않고**, 남은 행에는 고른 값이
    보인다. 「전부 그 값이어야 한다」로 세지 않는 이유는 이 제품의 표에 **묶음 머리 행**이
    있기 때문이다(담당자별 묶음) — 그 행에는 값이 없는 것이 맞다.
    """
    def _act(r, ctx):
        before = r.rows()
        # 고르기 **전에** 그 값이 표에 보이던 행 수를 센다. 이것이 있어야 「값이 사라졌다」를
        # 「그 열이 애초에 없다」와 구별할 수 있다 — 열이 없으면 조건이 맞아도 0이다.
        shown_before = rows_showing(r, option)
        label = r.choose(combo, option, index=index)
        after = r.rows()
        matched = rows_showing(r, option)
        widened = after > before
        vanished = shown_before > 0 and after > 0 and matched == 0
        return {"ui_action": says or ("«%s» 에서 «%s» 를 고른다" % (combo, label)),
                "frontend_state": "%s=%s" % (combo, option),
                "observed": {"rows": {"before": before, "after": after},
                             "rows_showing_option": {"before": shown_before, "after": matched}},
                "rendered": "표 %d행 → %d행 · «%s» 가 보이는 행 %d → %d"
                            % (before, after, option, shown_before, matched),
                "expected": {"source": "derived-check",
                             "rule": "조건은 결과를 넓히지 않고, 그 값이 보이던 표라면 남은 행에도 보인다",
                             "option": option,
                             "rows": {"before": before, "after": after,
                                      "showing_before": shown_before, "showing_after": matched}},
                "failed": ("조건을 걸었는데 행이 늘었다(%d → %d)" % (before, after) if widened
                           else ("고르기 전에는 %d행에 보이던 «%s» 가 남은 %d행에는 하나도 없다"
                                 % (shown_before, option, after) if vanished else None))}
    return _act


def search_then(value: str, *, box: str = "", says: str = ""):
    def _act(r, ctx):
        before = r.rows()
        selector = box or 'input[type="search"], #main-content input[aria-label*="검색"]'
        shown_before = rows_showing(r, value)
        r.fill(selector, value)
        after = r.rows()
        matched = rows_showing(r, value)
        return {"ui_action": says or ("검색 상자에 «%s» 를 넣는다" % value),
                "frontend_state": "q=%s" % value,
                "observed": {"rows": {"before": before, "after": after},
                             "rows_showing_query": {"before": shown_before, "after": matched}},
                "rendered": "표 %d행 → %d행 · «%s» 가 보이는 행 %d → %d"
                            % (before, after, value, shown_before, matched),
                "expected": {"source": "derived-check",
                             "rule": "검색은 결과를 넓히지 않고, 그 글이 보이던 표라면 남은 행에도 보인다",
                             "query": value,
                             "rows": {"before": before, "after": after,
                                      "showing_before": shown_before, "showing_after": matched}},
                "failed": ("검색했는데 행이 늘었다(%d → %d)" % (before, after)
                           if after > before
                           else ("검색 전에는 %d행에 보이던 «%s» 가 남은 %d행에는 하나도 없다"
                                 % (shown_before, value, after)
                                 if shown_before > 0 and after > 0 and matched == 0 else None))}
    return _act


def primary_button(r):
    """지금 떠 있는 대화상자의 **주 버튼**. 이름이 아니라 자리로 겨눈다.

    이 제품의 모달은 자기 동작을 버튼 이름으로 말한다 — «저장» 도 있고 «수정» 도 있고
    «미리 보기를 먼저 하세요» 도 있다. 그것이 좋은 문구다(버튼이 무슨 일을 하는지
    말한다). 그런데 Flow 표가 이름으로 찾으면 화면마다 다른 이름을 다 알아야 하고,
    못 찾으면 **아무것도 안 누르고 조용히 넘어간다** — 실제로 그렇게 «저장했는데 요청이
    없었다» 가 나왔다. 자리는 하나다: 바닥 줄의 마지막 버튼.
    """
    panel = r.page.locator('[role="dialog"]').last
    footer = panel.locator(".k-footer-main button")
    if footer.count():
        return footer.last
    actions = panel.locator(".MuiDialogActions-root button")
    if actions.count():
        return actions.last
    stop("대화상자에 주 버튼이 없다")


def dialog_text(r, limit: int = 200) -> str:
    """지금 떠 있는 **마지막** 대화상자의 글.

    `.first` 를 읽으면 셸에 상시 떠 있는 대화상자(드로어·팔레트)를 읽어 빈 문자열이
    나온다 — 그러면 확인 문구를 읽는 Flow 가 전부 «문구가 없다» 로 죽는다.
    """
    panel = r.page.locator('[role="dialog"]')
    return " ".join((panel.last.inner_text() or "").split())[:limit] if panel.count() else ""


def typing_area(r, label: str):
    """여러 줄 입력 칸 하나. **보이지 않는 그림자 textarea 를 피한다.**

    MUI 의 `multiline` TextField 는 높이를 재려고 `aria-hidden` textarea 를 하나 더
    그린다. `.first`/`.last` 로 집으면 그것을 채우려다 30초를 기다리다 죽는다.
    """
    box = r.page.get_by_label(label, exact=False)
    if box.count():
        return box.first
    box = r.page.locator('#main-content textarea:not([aria-hidden="true"])')
    if not box.count():
        stop("입력 칸이 없다: %s" % label)
    return box.last


def dialogs(r) -> int:
    """지금 떠 있는 대화상자 수.

    **0 이 기준이 아니다.** 이 셸에는 항상 떠 있는 `role="dialog"` 요소가 하나 있어서
    (드로어·팔레트가 keepMounted 로 살아 있다), 「하나라도 있으면 열린 것」으로 세면
    아무것도 안 열려도 통과한다 — 실제로 그렇게 «열림 2 → 닫힘 1» 이 나왔다.
    그래서 판정은 언제나 **전후 차이**로 한다.
    """
    return r.page.locator('[role="dialog"]').count()


def open_row_modal(r, ctx, *, opener: str, index: int = 0):
    """버튼으로 모달을 연다 — 모달이 안 뜨면 그 자리에서 멈춘다."""
    before = dialogs(r)
    label = r.click(opener, index=index)
    if dialogs(r) <= before:
        stop("«%s» 를 눌렀는데 대화상자가 안 늘었다(%d개 그대로)" % (label, before))
    return label


def close_modal(r):
    """지금 떠 있는 **마지막** 대화상자를 닫는다.

    `.first` 를 잡으면 셸에 상시 떠 있는 대화상자를 붙들고, 그 안의 안 보이는 닫기
    버튼을 누르려다 30초를 기다린다 — 실제로 1:1 패널이 그렇게 시간 초과로 죽었다.
    """
    if not dialogs(r):
        return
    panel = r.page.locator('[role="dialog"]').last
    for finder in (lambda: panel.get_by_role("button", name="취소", exact=True),
                   lambda: panel.get_by_role("button", name="닫기", exact=True),
                   lambda: panel.get_by_label("닫기")):
        target = finder()
        if target.count():
            try:
                target.first.click(timeout=6000)
            except Exception:  # noqa: BLE001
                continue
            break
    else:
        r.press("Escape")
    r.settle(600)
    # dirty 확인 창이 뜨면 «버리기» 로 답한다 — 이 Flow 가 보려는 것은 그 창이 아니다.
    #
    # **대화상자 안에서만 찾는다.** 예전에는 페이지 전체에서 «확인» 을 찾았는데, 그러면
    # 확인 창이 안 떴을 때 화면 어딘가의 다른 «확인» 버튼을 눌러 버린다 — 닫으려던 모달
    # 대신 엉뚱한 것이 열리고, 다음 Flow 는 «열리거나 닫히지 않았다» 로 죽는다.
    still = r.page.locator('[role="dialog"]')
    if not still.count():
        return
    for label in ("버리고 닫기", "버리기", "예", "확인"):
        button = still.last.get_by_role("button", name=label)
        if button.count():
            button.first.click()
            r.settle(400)
            return


def modal_open_close(opener: str, *, index: int = 0):
    def _act(r, ctx):
        base = dialogs(r)
        open_row_modal(r, ctx, opener=opener, index=index)
        opened = dialogs(r)
        title = ""
        head = r.page.locator('[role="dialog"] .MuiDialogTitle-root')
        if head.count():
            title = " ".join((head.last.inner_text() or "").split())[:50]
        close_modal(r)
        closed = dialogs(r)
        return {"ui_action": "모달을 열고 닫는다",
                "frontend_state": "open=true → open=false",
                "observed": {"base": base, "opened": opened, "after_close": closed,
                             "title": title},
                "rendered": "«%s» 상시 %d · 열림 %d → 닫힘 %d" % (title, base, opened, closed),
                "expected": {"source": "derived-check",
                             "rule": "열면 대화상자가 하나 늘고, 닫으면 원래대로 돌아온다",
                             "dialogs": {"base": base, "opened": opened, "closed": closed}},
                "failed": None if (opened > base and closed <= base)
                          else "열리거나 닫히지 않았다"}
    return _act


def required_blocks_submit(opener: str, *, submit: str = "추가"):
    """필수값을 비운 채 제출 — **서버로 안 나가는 것**이 이 Flow 의 증거다."""
    def _act(r, ctx):
        open_row_modal(r, ctx, opener=opener)
        sent: list[str] = []
        r.page.on("request", lambda req: sent.append(req.url)
                  if req.method in ("POST", "PATCH", "PUT") else None)
        button = r.page.get_by_role("button", name=submit)
        disabled = bool(button.count()) and button.first.is_disabled()
        if button.count() and not disabled:
            button.first.click()
            r.settle(900)
        still = bool(r.page.locator('[role="dialog"]').count())
        close_modal(r)
        return {"ui_action": "필수값을 비운 채 «%s» 를 누른다" % submit,
                "frontend_state": "required 위반 → 제출 차단",
                "observed": {"writes": len(sent), "submit_disabled": disabled,
                             "dialog_still_open": still},
                "rendered": "제출 버튼 비활성 %s · 모달 유지 %s · 쓰기 요청 %d건"
                            % (disabled, still, len(sent)),
                "failed": None if (disabled or (still and not sent))
                          else "필수값이 비었는데 제출됐다"}
    return _act


def open_row(r, index: int = 0):
    """표의 행 하나를 연다 — **본문 칸**을 누른다.

    첫 칸이 선택 체크박스인 표가 있어서(사용자 목록), 「행 안의 첫 링크/버튼」을 누르면
    그 체크박스나 크기 0 인 요소를 눌러 30초를 기다리다 죽는다 — 실제로 네 Flow 가
    그렇게 시간 초과로 죽었다. 사람은 이름·이메일이 적힌 칸을 누른다.
    """
    row = r.page.locator("table tbody tr").nth(index)
    if not row.count():
        stop("표에 행이 없다")
    label = " ".join((row.inner_text() or "").split())[:50]
    # 목록마다 «행을 여는 것» 이 다르다: 링크인 표, 제목이 버튼인 표(내 티켓·홈),
    # 행 자체가 눌리는 표(관리자 목록). 셋을 순서대로 시도하고, 안 되면 **빨리** 진다 —
    # 기본 30초를 기다리면 실패 하나가 실행 전체를 늘어뜨린다.
    candidates = [
        row.locator("td a"),
        row.locator('td button:not([aria-label^="선택"]):not([aria-label^="수정"])'),
        row,
    ]
    for target in candidates:
        if not target.count():
            continue
        try:
            target.first.click(timeout=6000)
            r.settle(1500)
            return label
        except Exception:  # noqa: BLE001 — 다음 방법으로 넘어간다
            continue
    stop("행을 열 방법을 찾지 못했다: %s" % label)


def open_first_row(r, ctx):
    before = r.hash_of()
    label = open_row(r)
    return {"ui_action": "표의 첫 행 «%s» 을 연다" % label,
            "url_state": "%s → %s" % (before, r.hash_of()),
            "rendered": "본문 «%s»" % r.main_text(90)}


def pager(next_label: str = "다음"):
    """쪽 넘김 — 페이저가 없으면 **그 사실을 적는다**(한 쪽뿐이면 없는 것이 맞다)."""
    def _act(r, ctx):
        button = r.page.get_by_role("button", name=next_label)
        if not button.count() or button.first.is_disabled():
            return {"ui_action": "쪽을 넘긴다",
                    "notes": ["«%s» 가 없거나 비활성이다 — 이 데이터에서는 한 쪽뿐이다"
                              % next_label],
                    "rendered": "표 %d행 · 페이저 %s"
                                % (r.rows(), "없음" if not button.count() else "비활성")}
        before = r.hash_of()
        button.first.click()
        r.settle(1300)
        return {"ui_action": "«%s» 를 눌러 쪽을 넘긴다" % next_label,
                "url_state": "%s → %s" % (before, r.hash_of()),
                "rendered": "표 %d행" % r.rows()}
    return _act


def page_reset(combo: str, option: str, *, next_label: str = "다음"):
    """쪽을 넘긴 뒤 조건을 바꾼다 — **쪽이 1로 돌아가야 한다**.

    안 돌아가면 사용자는 「3쪽의 다른 조건」을 보게 되고, 그 화면은 대개 비어 있다. 그러면
    조건이 틀린 것인지 데이터가 없는 것인지 구별할 방법이 없다.
    """
    def _act(r, ctx):
        button = r.page.get_by_role("button", name=next_label)
        paged = bool(button.count()) and not button.first.is_disabled()
        if paged:
            button.first.click()
            r.settle(1300)
        before = unquote(r.hash_of())
        label = r.choose(combo, option)
        after = unquote(r.hash_of())
        reset = "page=" not in after
        return {"ui_action": ("쪽을 넘긴 뒤 «%s» 를 «%s» 로 바꾼다" % (combo, label)
                              if paged else "«%s» 를 «%s» 로 바꾼다(넘길 쪽이 없다)"
                              % (combo, label)),
                "frontend_state": "조건 변경 → page=1",
                "url_state": "%s → %s" % (before, after),
                "observed": {"paged": paged, "hash": {"before": before, "after": after}},
                "rendered": "주소 «%s» · 표 %d행" % (after, r.rows()),
                "expected": {"source": "derived-check",
                             "rule": "조건을 바꾸면 쪽이 1로 돌아간다(주소에 page 가 남지 않는다)",
                             "expect": "page= 없음", "got": after},
                "failed": None if reset else "조건을 바꿨는데 쪽이 그대로다: %s" % after}
    return _act


def no_page_axis(combo: str, option: str):
    """쪽이 **없는** 화면의 「쪽 초기화」 — 초기화할 쪽이 없다는 것이 답이다."""
    def _act(r, ctx):
        label = r.choose(combo, option)
        here = unquote(r.hash_of())
        pager_button = r.page.get_by_role("button", name="다음")
        return {"ui_action": "«%s» 를 «%s» 로 바꾼 뒤 주소와 페이저를 본다" % (combo, label),
                "frontend_state": "이 화면은 전량을 받아 화면에서 거른다 — 쪽이 없다",
                "url_state": "→ %s" % here,
                "observed": {"hash": here, "pager_buttons": pager_button.count()},
                "rendered": "주소 «%s» · 페이저 %d개" % (here, pager_button.count()),
                "expected": {"source": "derived-check",
                             "rule": "쪽이 없는 화면이라 조건을 바꿔도 주소에 page 가 안 붙는다",
                             "expect": "page= 없음", "got": here},
                "failed": None if "page=" not in here
                          else "쪽이 없는 화면인데 주소에 page 가 붙었다: %s" % here}
    return _act


def compound(first: tuple, second: tuple):
    """조건 둘을 **함께** 건다 — 더할수록 좁아지기만 해야 한다."""
    def _act(r, ctx):
        before = r.rows()
        one = r.choose(first[0], first[1])
        mid = r.rows()
        two = r.choose(second[0], second[1])
        after = r.rows()
        return {"ui_action": "«%s»=%s 와 «%s»=%s 를 함께 건다"
                             % (first[0], one, second[0], two),
                "frontend_state": "%s=%s & %s=%s" % (first[0], first[1], second[0], second[1]),
                "observed": {"rows": {"none": before, "one": mid, "both": after}},
                "rendered": "표 %d → %d → %d행" % (before, mid, after),
                "expected": {"source": "derived-check",
                             "rule": "조건을 더할수록 결과는 좁아지기만 한다",
                             "expect": "both <= one <= none",
                             "got": {"none": before, "one": mid, "both": after}},
                "failed": None if after <= mid <= before
                          else "조건을 더했는데 결과가 늘었다(%d → %d → %d)"
                               % (before, mid, after)}
    return _act


def retry_from_error(api_path: str, label: str):
    """오류 얼굴의 «다시 시도» — 서버를 실제로 끊어서 만든다.

    화면이 쓰는 경로만 503 으로 막고, 다시 시도를 누른 뒤 막은 것을 풀어 정상으로 돌아오는
    것까지 본다. 「오류 화면이 있다」가 아니라 **「그 버튼이 실제로 다시 부른다」** 가 이
    Flow 가 답해야 하는 질문이다.
    """
    def _act(r, ctx):
        pattern = "**" + api_path + "**"
        r.page.route(pattern, lambda route: route.fulfill(
            status=503, content_type="application/json",
            body='{"detail":"의도적으로 끊은 경로입니다."}'))
        try:
            r.page.reload(wait_until="domcontentloaded")
            r.page.wait_for_selector("#main-content", timeout=30_000)
            # 오류 얼굴은 **재시도가 끝난 뒤**에 나온다. 1.6초면 아직 「불러오는 중」인
            # 화면이 있어서, 그것을 «오류 얼굴이 없다» 로 적게 된다.
            r.settle(4000)
            face = r.main_text(90)
            retry = r.page.get_by_role("button", name="다시 시도")
            if not retry.count():
                stop("%s 가 503 인데 «다시 시도» 가 없다 — 얼굴: %s" % (api_path, face))
        finally:
            r.page.unroute(pattern)
        r.rec.reset()
        retry.first.click()
        r.settle(1800)
        return {"ui_action": "%s 를 503 으로 끊고 «다시 시도» 를 누른다" % label,
                "frontend_state": "isError=true → 재조회",
                "observed": {"error_face": face},
                "rendered": "오류 얼굴 «%s» → 복구 후 «%s»" % (face[:60], r.main_text(90)),
                "expected": {"source": "derived-check",
                             "rule": "503 이면 오류 얼굴과 «다시 시도» 가 나오고, 누르면 다시 부른다",
                             "blocked": api_path, "error_face": face[:80]}}
    return _act


def deep_link_survives_reload(hash_path: str, expect_in_url: str, *, shell: str = "/"):
    """조건을 주소에 실은 채 새로고침 — **화면이 그 조건을 다시 말하는가**."""
    def _act(r, ctx):
        r.goto(hash_path, shell=shell)
        first = r.rows()
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(1600)
        after = r.hash_of()
        return {"ui_action": "조건이 붙은 주소로 들어가 새로고침한다",
                "url_state": "%s (새로고침 뒤 %s)" % (hash_path, after),
                "observed": {"rows_before_reload": first, "rows_after": r.rows()},
                "rendered": "표 %d행 → %d행 · 본문 «%s»" % (first, r.rows(), r.main_text(70)),
                "failed": None if expect_in_url in unquote(after)
                          else "새로고침 뒤 주소에서 조건이 사라졌다: %s" % after}
    return _act


def hash_nav(r, hash_path: str, shell: str = "/") -> None:
    """문서를 다시 받지 **않고** 해시만 바꾼다.

    `goto` 는 같은 문서로 갈 때 새로 고친다(react-query 캐시가 Flow 사이로 새는 것을 막으려고
    그렇게 했다). 그런데 **뒤로가기를 재려면 기록이 쌓여야 한다** — 새로 고치면 그 기록이
    안 쌓이고, 그러면 「뒤로가기가 안 먹는다」가 화면이 아니라 표 때문에 나온다.
    """
    if shell and shell not in r.page.url.split("#")[0]:
        r.goto(hash_path, shell=shell)
        return
    r.page.evaluate("(h) => { window.location.hash = h; }", hash_path)
    r.settle(1700)


def back_forward(first: str, second: str, *, shell: str = "/"):
    """뒤로가기에서 **화면이 말하는 조건과 실제 질의가 같은가**."""
    def _act(r, ctx):
        r.goto(first, shell=shell)
        rows_first = r.rows()
        hash_nav(r, second, shell)
        rows_second = r.rows()
        # **여기서 기록을 지우지 않는다.** 뒤로가기는 캐시가 있으면 요청을 안 낼 수 있고
        # 그건 정상이다 — 그런데 앞의 두 이동이 낸 요청까지 지우면 사슬의 서버 칸이
        # 통째로 빈다. 이 Flow 가 답할 질문은 «주소와 결과가 같이 돌아오는가» 다.
        r.back()
        r.settle(1600)
        back_hash = r.hash_of()
        return {"ui_action": "%s → %s 로 간 뒤 뒤로가기" % (first, second),
                "url_state": "%s → %s → (뒤로) %s" % (first, second, back_hash),
                "observed": {"rows": {"first": rows_first, "second": rows_second,
                                      "after_back": r.rows()}},
                "rendered": "표 %d → %d → %d행" % (rows_first, rows_second, r.rows()),
                "expected": {"source": "derived-check",
                             "rule": "뒤로가기는 앞 화면의 조건을 그대로 되살린다",
                             "expect": first, "got": unquote_hash(back_hash),
                             "rows": {"first": rows_first, "after_back": r.rows()}},
                "failed": None if same_query(first, back_hash)
                          else "뒤로가기가 원래 조건으로 안 돌아왔다: %s" % back_hash}
    return _act


def input_box(r, box: str):
    """`label=…` 이면 라벨로, 아니면 CSS 로 찾는다.

    이 제품의 조건 텍스트 칸은 대개 `<label for>` 로 이름이 붙는다(MUI TextField) — 그런 칸은
    `input[aria-label=…]` 로는 하나도 안 잡힌다.
    """
    if box.startswith("label="):
        return r.page.get_by_label(box[6:], exact=False).first
    return r.page.locator(box).first


def race(box: str, quick: str, settled: str):
    """경합 — **늦게 온 응답이 최신 조건을 덮지 않는다.**

    빠르게 두 번 입력하고, 두 번째 조건만 화면에 남는지 본다. 첫 응답이 늦게 도착해
    이겨 버리면 사용자는 자기가 지운 조건의 결과를 보게 된다.
    """
    def _act(r, ctx):
        target = input_box(r, box)
        if not target.count():
            stop("입력 상자가 없다: %s" % box)
        target.fill(quick)
        r.page.wait_for_timeout(120)     # 디바운스보다 짧게 — 첫 요청이 날아가기 전에 덮는다
        target.fill(settled)
        r.settle(2200)
        value = target.input_value()
        return {"ui_action": "«%s» 를 넣자마자 «%s» 로 바꾼다" % (quick, settled),
                "frontend_state": "q=%s (마지막 입력)" % settled,
                "observed": {"input_value": value, "rows": r.rows()},
                "rendered": "입력 «%s» · 표 %d행" % (value, r.rows()),
                "expected": {"source": "derived-check",
                             "rule": "빠르게 두 번 입력하면 마지막 것만 남는다",
                             "expect": settled, "got": value},
                "failed": None if value == settled
                          else "늦게 온 응답이 입력을 «%s» 로 되돌렸다" % value}
    return _act


def cache_key(first: str, second: str, *, shell: str = "/"):
    """캐시 키 — **다른 조건이 같은 캐시를 재사용하지 않는다.**"""
    def _act(r, ctx):
        r.goto(first, shell=shell)
        a_rows, a_text = r.rows(), r.main_text(80)
        r.goto(second, shell=shell)
        b_rows, b_text = r.rows(), r.main_text(80)
        r.goto(first, shell=shell)
        again_rows = r.rows()
        return {"ui_action": "%s → %s → %s 로 오간다" % (first, second, first),
                "frontend_state": "queryKey 에 조건이 들어간다",
                "observed": {"rows": {"first": a_rows, "second": b_rows,
                                      "first_again": again_rows}},
                "rendered": "표 %d → %d → %d행" % (a_rows, b_rows, again_rows),
                "expected": {"source": "derived-check",
                             "rule": "다른 조건을 거쳤다 돌아와도 같은 조건은 같은 결과다",
                             "expect": a_rows, "got": again_rows,
                             "other": {"where": second, "rows": b_rows},
                             "text": {"first": a_text[:60], "second": b_text[:60]}},
                "failed": None if again_rows == a_rows
                          else "같은 조건으로 돌아왔는데 결과가 다르다(%d → %d)"
                               % (a_rows, again_rows)}
    return _act


def hidden_without_role(control: str, *, role: str = "user", kind: str = "button"):
    """권한이 없으면 **컨트롤 자체를 안 그린다** — 눌러 봐야 거절당하는 자리를 안 만든다."""
    def _act(r, ctx):
        here = r.hash_of()
        shell = "/admin" if "/admin" in r.page.url else "/"
        as_now = r.count_control(kind, control)
        as_other = r.as_role(role, here, shell, lambda p: p.get_by_role(
            kind, name=control, exact=False).count())
        landing = (getattr(r, "role_landing", {}) or {}).get(role) or {}
        blocked = landing.get("main_content") is False
        return {"ui_action": "같은 화면을 역할 %s 로 연다" % role,
                "frontend_state": "역할에 따른 렌더 분기",
                "observed": {"as_session_role": as_now, "as_%s" % role: as_other,
                             "landing": landing},
                "rendered": ("«%s» — 지금 역할 %d개 · %s 는 화면 자체가 안 열린다 «%s»"
                             % (control, as_now, role, landing.get("body", ""))
                             if blocked else
                             "«%s» — 지금 역할 %d개 · %s %d개"
                             % (control, as_now, role, as_other)),
                "expected": {"source": "derived-check",
                             "rule": "권한이 없으면 그 컨트롤이 없다 — 화면 자체가 안 열리면 더 강한 차단이다",
                             "as_session_role": as_now, "as_%s" % role: as_other,
                             "blocked": blocked},
                "failed": None if (as_now and (blocked or not as_other))
                          else "역할별 차이가 없다(지금 %d · %s %d)" % (as_now, role, as_other)}
    return _act


def read_main(p) -> str:
    """본문 글을 읽되, **본문이 없으면 그것도 관측이다**.

    `locator("#main-content").inner_text()` 는 그 자리가 없으면 30초를 기다리다 죽는다.
    그런데 관리자 화면을 일반 사용자로 열면 본문이 **아예 안 그려지는** 것이 정답이고,
    그 정답 위에서 하네스가 죽으면 기록에는 「측정 실패」가 남는다 — 제품의 가장 강한
    차단이 결함처럼 보인다. S18 의 실패 여섯 중 셋이 이 자리였다.
    """
    main = p.locator("#main-content")
    if not main.count():
        body = " ".join((p.evaluate("() => document.body.innerText || ''") or "").split())
        return "(본문 없음) " + body[:140]
    try:
        return " ".join((main.inner_text(timeout=5000) or "").split())[:140]
    except Exception:  # noqa: BLE001
        return "(본문을 못 읽었다)"


def blocked_route(hash_path: str, *, role: str = "user", shell: str = "/admin"):
    """이 역할에게는 **화면 자체가 안 열린다**. 열리면 그것이 권한 결함이다."""
    def _act(r, ctx):
        text = r.as_role(role, hash_path, shell, read_main)
        denied = any(w in text for w in ("권한", "찾을 수 없", "로그인", "본문 없음"))
        return {"ui_action": "역할 %s 로 %s 를 연다" % (role, hash_path),
                "frontend_state": "라우트 역할 가드",
                "observed": {"body": text},
                "rendered": "본문 «%s»" % text,
                "failed": None if denied else "역할 %s 에게 이 화면이 그대로 열렸다" % role}
    return _act


__all__ = [
    "Flow", "FLOWS", "flow", "stop", "json",
    "just_load", "click_then", "choose_then", "search_then",
    "open_row_modal", "close_modal", "modal_open_close", "required_blocks_submit",
    "open_first_row", "open_row", "pager", "retry_from_error", "deep_link_survives_reload",
    "dialog_text", "typing_area", "dialogs", "primary_button", "same_query", "title_like",
    "unquote_hash", "row_title", "rows_showing",
    "back_forward", "race", "cache_key", "hidden_without_role", "blocked_route",
    "page_reset", "no_page_axis", "compound", "hash_nav", "input_box",
]
