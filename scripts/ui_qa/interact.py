"""화면을 **눌러 본다** — 모달·팝업을 열어 검사한다 (0단계 #3).

## 왜 필요했나

QA 하네스는 클릭을 **한 번도 하지 않았다**:

    grep -c "page.click|\\.click(|get_by_role|locator(" scripts/ui_qa/capture.py  →  0

`capture.py` 는 `goto` → `wait_for_selector("#main-content")` → `evaluate` 뿐이다. 그런데
**모달은 버튼·행을 눌러야만 열린다.** 그래서 992페이지 × 13검사를 돌려도 모달은 단 한 번도
들어간 적이 없고, 관리자 상세 모달 28개가 전부 깨져 있는 채로 "100% 통과" 아래 살아남았다.
클릭이 없는 UI 검사는 첫 화면만 보는 검사다.

## 무엇을 누르나 — 그리고 무엇을 절대 안 누르나

라벨을 추측해서 고르지 않는다(그 방식으로 처음 시도했을 때 모달 2개밖에 못 열었다).
**보이는 버튼을 순서대로 눌러 보되**, 되돌릴 수 없거나 밖으로 나가는 것은 제외한다.
`DENY` 가 그 목록이고, 여기 빠진 낱말이 있으면 QA 가 운영 데이터를 지운다 —
**추가할 때는 넓게 잡는 편이 맞다.**

열린 모달은 검사하고 **반드시 닫는다**. 안 닫으면 다음 클릭이 뒤쪽 모달을 누른다.
"""

from __future__ import annotations

import re

# 절대 누르지 않는다. 되돌릴 수 없거나(삭제·파기) 남에게 영향이 가거나(전송·승인)
# 외부를 호출한다(동기화·실행). 넓게 잡는다 — QA 가 운영 데이터를 건드리는 것보다
# 모달 몇 개를 못 여는 편이 낫다.
DENY = re.compile(
    r"삭제|제거|지우|비우|파기|영구|해지|취소|중지|정지|차단|회수|반려|승인|거절|"
    r"로그아웃|초기화|복원|실행|시작|보내|전송|저장|적용|배포|동기화|재시도|"
    r"내보내기|가져오기|업로드|첨부|나가기|떠나|퇴장|파하|숨기|넘기|위임|"
    r"delete|remove|purge|revoke|logout|submit|send|run|deploy|sync"
)

# 무엇을 누를 후보로 볼 것인가.
#
# **본문 안(`#main-content`)만 본다.** 상단바에는 명령 팔레트·알림·사용자 메뉴가 있어서
# 화면과 무관하게 늘 먼저 잡힌다(처음 돌렸을 때 12화면에서 연 모달 4개가 전부 그것들이었다).
# 그리고 관리자 상세 드로어는 **행이 아니라 마지막 칸의 "상세" 버튼**이 연다
# (`ui/kit.jsx` 의 주석: "행은 표 의미를 유지하고, 상세 열기는 마지막 칸의 실제 button 이 담당").
# 행을 눌러도 안 열리므로 그 버튼을 명시적으로 후보에 넣는다.
MAIN = "#main-content"
OPENER_SELECTORS = (
    f"{MAIN} button:has-text('상세')",       # 관리자 28화면의 상세 드로어
    f"{MAIN} button",                        # 새로 만들기·추가·편집 …
    f"{MAIN} [role='button']",
)

MODAL_PROBE = r"""
() => {
  // 보이는 것만 — 닫힌 채 붙어 있는 패널(keepMounted)을 열린 모달로 오인하지 않는다.
  const dlg = [...document.querySelectorAll('[role="dialog"]')].find((d) => {
    if (d.closest('[aria-hidden="true"]')) return false;
    const r = d.getBoundingClientRect();
    const cs = getComputedStyle(d);
    return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.display !== 'none';
  });
  if (!dlg) return null;
  const paper = dlg.closest('.MuiDialog-paper') || dlg;
  const cs = getComputedStyle(paper);
  const r = paper.getBoundingClientRect();
  const acts = paper.querySelector('.MuiDialogActions-root');

  // footer 가 DialogActions 밖이면 버튼이 dialog 의 flex 열 직계 자식이 되어
  // 전체폭 색띠로 쌓인다 — 사용자가 "모달 상태가 이상한데?" 라고 한 그 모양이다.
  const strayButtons = [...paper.children]
    .filter((c) => c.tagName === 'BUTTON')
    .map((b) => (b.textContent || '').trim().slice(0, 16));
  // **액션 버튼만** 본다. 예전에는 모달 안의 모든 버튼을 셌는데, 그러면 '1:1 대화 시작'
  // 처럼 **사람을 고르는 목록**의 행(전체폭이 맞는 디자인)이 결함으로 잡힌다.
  // 이 검사의 뜻은 "확정/취소 같은 **액션**이 전체폭 색띠로 쌓인다" 이다 — 본문 안의 목록은
  // 그 얘기가 아니다. 액션 영역 안 + paper 직계 자식(= DialogActions 를 안 쓴 경우)만 본다.
  const actionButtons = [
    ...(acts ? acts.querySelectorAll('button') : []),
    ...[...paper.children].filter((c) => c.tagName === 'BUTTON'),
  ];
  const fullWidth = actionButtons
    .filter((b) => b.getBoundingClientRect().width > r.width * 0.8)
    .map((b) => (b.textContent || '').trim().slice(0, 16));

  return {
    title: ((paper.querySelector('.MuiDialogTitle-root') || {}).textContent || '').trim().slice(0, 40),
    radius: Math.round(parseFloat(cs.borderTopLeftRadius) || 0),
    width: Math.round(r.width),
    height: Math.round(r.height),
    offscreen: r.top < -1 || r.bottom > innerHeight + 1,
    hasActions: !!acts,
    strayButtons,
    fullWidthButtons: fullWidth,
    hasCloseButton: !!paper.querySelector('[aria-label*="닫기"], [aria-label*="close" i]'),
    fieldCount: paper.querySelectorAll('input, select, textarea').length,
  };
}
"""


def _label(handle) -> str:
    try:
        return (handle.inner_text() or "").strip().replace("\n", " ")[:40]
    except Exception:  # noqa: BLE001 — DOM 이 바뀌어 사라진 요소
        return ""


def _dialog_open(page) -> bool:
    """**보이는** 대화상자가 있는가.

    존재 여부만 보면 안 된다. `keepMounted` 로 항상 붙어 있는 패널(AI 드로어)이 닫혀
    있어도 `[role="dialog"]` 로 잡혀서, 모달을 열지도 않은 화면이 "닫히지 않는 모달이
    있다" 로 보고된다. 실제로 그 오탐이 났다.
    """
    try:
        return page.evaluate("""() => {
          for (const d of document.querySelectorAll('[role="dialog"]')) {
            if (d.closest('[aria-hidden="true"]')) continue;
            const r = d.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) continue;
            const cs = getComputedStyle(d);
            if (cs.visibility === 'hidden' || cs.display === 'none') continue;
            return true;
          }
          return false;
        }""")
    except Exception:  # noqa: BLE001
        return False


def close_modal(page, timeout_ms: int = 2000) -> str:
    """열린 모달을 닫는다. 어떻게 닫혔는지 돌려준다(Esc 동작 여부가 M5 의 측정값이다)."""
    if not _dialog_open(page):
        return "이미 닫힘"
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(280)
        if not _dialog_open(page):
            return "Esc"
    except Exception:  # noqa: BLE001
        pass
    for sel in ('[aria-label*="닫기"]', '[aria-label*="close" i]',
                'button:has-text("취소")', 'button:has-text("닫기")'):
        try:
            btn = page.query_selector(sel)
            if btn:
                btn.click(timeout=timeout_ms)
                page.wait_for_timeout(240)
                if not _dialog_open(page):
                    return f"버튼 {sel}"
        except Exception:  # noqa: BLE001
            continue
    # 마지막 수단: 배경 클릭. 그래도 안 닫히면 라우트를 다시 열어 상태를 버린다.
    try:
        page.mouse.click(6, 6)
        page.wait_for_timeout(200)
    except Exception:  # noqa: BLE001
        pass
    return "닫히지 않음" if _dialog_open(page) else "배경 클릭"


def open_modals(page, *, limit: int = 8, settle_ms: int = 420) -> list[dict]:
    """현재 화면에서 열 수 있는 모달을 차례로 열어 검사한다.

    각 항목: `{opener, probe, closedBy}`. 아무것도 안 열리면 빈 목록이다 —
    그것도 결과다(그 화면에는 모달이 없다).
    """
    found: list[dict] = []

    # 이미 열려 있는 것(온보딩 투어 등)을 먼저 치운다. 남아 있으면 뒤의 클릭이 전부
    # 그 안에서 일어나고, 검사 결과는 "화면에 모달이 하나뿐" 이 된다.
    if _dialog_open(page):
        close_modal(page)

    openers = []
    seen_handles = set()
    for sel in OPENER_SELECTORS:
        try:
            for h in page.query_selector_all(sel):
                key = id(h)
                if key not in seen_handles:
                    seen_handles.add(key)
                    openers.append(h)
        except Exception:  # noqa: BLE001
            continue
    if not openers:
        return found

    seen_titles: set[str] = set()
    for handle in openers:
        if len(found) >= limit:
            break
        label = _label(handle)
        if not label or DENY.search(label):
            continue
        try:
            if not handle.is_visible() or not handle.is_enabled():
                continue
            handle.click(timeout=1800)
            page.wait_for_timeout(settle_ms)
        except Exception:  # noqa: BLE001 — 화면 밖이거나 사라진 요소. 다음으로.
            continue

        probe = None
        try:
            probe = page.evaluate(MODAL_PROBE)
        except Exception:  # noqa: BLE001
            probe = None

        if not probe:
            # 모달이 아니라 라우트 이동이었을 수 있다. 다음 클릭이 엉뚱한 화면에서
            # 일어나지 않도록 여기서 멈춘다 — 호출측이 라우트를 다시 연다.
            continue

        key = probe.get("title") or f"무제-{len(found)}"
        if key in seen_titles:
            close_modal(page)
            continue
        seen_titles.add(key)
        closed_by = close_modal(page)
        found.append({"opener": label, "probe": probe, "closedBy": closed_by})
        if closed_by == "닫히지 않음":
            break  # 더 눌러 봐야 뒤쪽 모달만 건드린다
    return found


def classify_modals(modals: list[dict]) -> dict:
    """모달 검사 결과 → 하네스의 assertion 모양.

    기준(목업)의 카드 반지름이 18px 이므로 모달도 그 언저리여야 한다. 지금 35px 인 것은
    `shape.borderRadius:14` 에 `sx={{borderRadius:2.5}}` 가 곱해진 결과다.
    """
    out: dict[str, dict] = {}

    def fail(name: str, hits: list[str], note: str) -> None:
        # 통과했을 때 결함 설명을 그대로 두면 리포트에서 "pass — 모달이 뷰포트 밖으로 넘친다"
        # 처럼 읽혀 정반대로 해석된다. 통과는 통과라고 쓴다.
        out[name] = {
            "status": "fail" if hits else "pass",
            "count": len(hits),
            "note": (note + " — " + "; ".join(hits[:4])) if hits
                    else f"이상 없음 (모달 {len(modals)}개 확인)",
        }

    stray = [f"{m['opener']}({', '.join(m['probe']['strayButtons'])})"
             for m in modals if m["probe"]["strayButtons"]]
    fail("modal_footer_outside_actions", stray,
         "footer 가 MuiDialogActions 밖이라 버튼이 전체폭 색띠로 쌓인다")

    wide = [f"{m['opener']}({', '.join(m['probe']['fullWidthButtons'])})"
            for m in modals if m["probe"]["fullWidthButtons"]]
    fail("modal_full_width_buttons", wide, "모달 버튼이 전체폭이다")

    off = [m["opener"] for m in modals if m["probe"]["offscreen"]]
    fail("modal_offscreen", off, "모달이 뷰포트 밖으로 넘친다")

    no_close = [m["opener"] for m in modals
                if not m["probe"]["hasCloseButton"] and not m["probe"]["hasActions"]]
    fail("modal_no_close", no_close, "닫는 방법이 화면에 없다(× 도 액션 영역도 없음)")

    stuck = [m["opener"] for m in modals if m["closedBy"] == "닫히지 않음"]
    fail("modal_cannot_close", stuck, "어떤 방법으로도 닫히지 않는다")

    radii = sorted({m["probe"]["radius"] for m in modals})
    out["modal_radius"] = {
        "status": "fail" if any(r > 20 for r in radii) else "pass",
        "count": sum(1 for m in modals if m["probe"]["radius"] > 20),
        "note": f"모달 라운드 {radii} (기준 카드 18px)",
    }

    widths = sorted({m["probe"]["width"] for m in modals})
    out["modal_width_spread"] = {
        "status": "fail" if len(widths) > 4 else "pass",
        "count": len(widths),
        "note": f"모달 폭이 {len(widths)}가지: {widths}",
    }
    return out
