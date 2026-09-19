"""화면 **상태**를 만들어 조합을 잰다 (UI 3차 · 조합 계약 C-7).

`run.py` 캡처와 `kit_measure` 는 화면을 **연 그대로** 잰다. 씨앗 데이터의 기본 상태에는 조건도,
다중 선택도, 고른 행도, 열린 팝오버도 없다 — 칩이 칸을 키우는 상태, 선택 발이 서는 상태, 열 필터가
열린 상태가 캡처에 한 번도 없었다. 지난 회차 G 게이트가 조합 결함을 못 본 이유가 그것이다.

이 하네스는 화면마다 사람이 실제로 만드는 상태를 만든 뒤 뷰포트 스크린샷을 찍고, 그 상태에서
`composition_checks.COMPOSITION_JS` 와 `kit_measure.MEASURE_JS` 를 잰다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness composition_states \\
        --viewports 1920x1080 1366x768 1200x900 --states-themes light dark --states-label compose-before

    # 한 상태만
    python -m scripts.ui_qa.local_capture --harness composition_states --states my-tickets.multi

    # 설치처(원격) — 쓰기가 생기는 상태(빈 폼 제출)는 건너뛴다. 대상은 `capture.DEFAULT_BASE_URL`
    # (`UI_QA_BASE_URL`)이 정한다 — 사용법 줄에 호스트를 적어 두면 이름이 바뀌는 날 옛 제품을 가리킨다.
    python -m scripts.ui_qa.composition_states --remote-safe \\
        --out-root dist/ui-qa-remote --auth-dir dist/ui-qa-remote/auth-states

`--label` · `--themes` 는 `local_capture` 가 먹는 이름이라 `--states-label` · `--states-themes` 를 쓴다.

## 지키는 것

- **누르지 않는 것.** 상태를 만드는 클릭은 명시한 선택자만 누른다(행 체크박스 · 열 필터 표지 · 고르개 ·
  행 「더 보기」). 저장 · 삭제 · 배정 같은 동작 단추는 `interact.DENY` 에 걸리는 낱말이면 누르지 않는다.
  빈 폼 제출은 클라이언트 검증이 서버 요청 전에 막는 자리만 쓰고(`MyTickets.jsx::NewTicket.submit`),
  원격에서는 그것도 하지 않는다(`--remote-safe`).
- **못 만든 상태는 통과가 아니다.** 선택자를 못 찾으면 그 상태를 `skipped` 로 이유와 함께 적고 표본 0 으로 센다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.composition_checks import (  # noqa: E402
    COMPOSITION_CHECKS, COMPOSITION_CONTRACT, COMPOSITION_JS, expect_for,
)

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"


class StateSkipped(RuntimeError):
    """상태를 만들 선택자를 못 찾았다 — 통과가 아니라 미실행이다."""


def _goto(page, base: str, hash_path: str, settle_ms: int) -> None:
    from scripts.ui_qa import capture as cap

    page.goto(f"{base.rstrip('/')}/#{hash_path}", wait_until="domcontentloaded", timeout=45_000)
    cap._settle(page, settle_ms=settle_ms, timeout_ms=45_000)
    page.mouse.move(0, 0)


def _first(page, selectors: list[str]):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _click(locator, what: str) -> None:
    """상태를 만드는 클릭 — 누르지 않는 낱말(`interact.DENY`)이 붙은 단추면 누르지 않고 상태를 건너뛴다."""
    from scripts.ui_qa import interact

    label = ((locator.get_attribute("aria-label") or "") + " " + (locator.inner_text() or "")).strip()
    if interact.DENY.search(label):
        raise StateSkipped(f"{what}: 누르지 않는 낱말이 붙은 단추다")
    locator.click()


def _api_json(page, base: str, path: str):
    try:
        response = page.context.request.get(f"{base.rstrip('/')}{path}", timeout=15_000)
        if response.status != 200:
            return None
        return response.json()
    except Exception:  # noqa: BLE001
        return None


def _rows_select(page, n: int) -> None:
    boxes = page.locator("#main-content tbody input[type=checkbox]")
    if boxes.count() < n:
        raise StateSkipped(f"행 체크박스가 {boxes.count()}개뿐이다")
    for i in range(n):
        boxes.nth(i).check()
    page.wait_for_timeout(300)


def _open_combobox(page, label: str) -> None:
    box = _first(page, [
        f"#main-content [data-filter-surface] input[aria-label='{label}']",
        f"#main-content input[aria-label='{label}']",
    ])
    if box is None:
        raise StateSkipped(f"«{label}» 고르개를 못 찾음")
    box.click()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(450)


def _pick_combobox(page, label: str, skip_all: bool = True) -> None:
    _open_combobox(page, label)
    options = page.locator("[role=listbox] [role=option]")
    if options.count() == 0:
        raise StateSkipped(f"«{label}» 후보가 없다")
    index = 0
    if skip_all and re.search(r"전체|고르세요", options.nth(0).inner_text() or ""):
        if options.count() < 2:
            raise StateSkipped(f"«{label}» 에 고를 후보가 없다(「전체」뿐)")
        index = 1
    options.nth(index).click()
    page.wait_for_timeout(900)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    # 고른 값이 칸에 섰는지 확인한다 — 조용히 안 먹은 고르기를 「그 상태를 만들었다」로 적지 않는다.
    picked = page.evaluate(
        """(name) => { const i = document.querySelector(`#main-content input[aria-label='${name}']`);
           if (!i) return false; const box = i.closest('.MuiInputBase-root');
           return !!(i.value || (box && box.querySelector('[data-row-value]'))); }""", label)
    if not picked:
        raise StateSkipped(f"«{label}» 고른 값이 칸에 서지 않았다")


# ── 상태 정의 ───────────────────────────────────────────────────────────────
# 각 함수는 (page, base, settle_ms) 를 받아 상태를 만들고 한 줄 메모를 돌려준다.

def st_my_tickets_default(page, base, settle):
    _goto(page, base, "/my-tickets", settle)
    return "기본 조건(종료 제외)"


def st_my_tickets_multi(page, base, settle):
    projects = (_api_json(page, base, "/api/tickets/projects") or {}).get("projects") or []
    meta = _api_json(page, base, "/api/tickets/meta") or {}
    ids = [p.get("id") for p in projects if p.get("id")][:2]
    priorities = [p for p in (meta.get("priorities") or []) if p][:1]
    if len(ids) < 2:
        raise StateSkipped("프로젝트가 둘 미만이다")
    query = "&".join([f"project_id={i}" for i in ids] + [f"priority={p}" for p in priorities])
    _goto(page, base, f"/my-tickets?{query}", settle)
    return f"프로젝트 {len(ids)} · 우선순위 {len(priorities)}"


def st_my_tickets_selected(page, base, settle):
    _goto(page, base, "/my-tickets", settle)
    _rows_select(page, 2)
    return "행 2개 선택"


def st_my_tickets_col_filter(page, base, settle):
    _goto(page, base, "/my-tickets", settle)
    opener = _first(page, ["#main-content thead [aria-label='상태 필터']", "#main-content thead [aria-label$=' 필터']"])
    if opener is None:
        raise StateSkipped("열 필터 표지를 못 찾음")
    _click(opener, "상태를 여는 단추")
    page.wait_for_timeout(450)
    return "상태 열 필터 팝오버 열림"


def st_my_tickets_project_open(page, base, settle):
    _goto(page, base, "/my-tickets", settle)
    _open_combobox(page, "프로젝트")
    return "프로젝트 고르개 열림"


def st_unassigned_hover(page, base, settle):
    _goto(page, base, "/unassigned", settle)
    row = _first(page, ["#main-content tbody tr:not([data-group-row])"])
    if row is None:
        raise StateSkipped("행이 없다")
    row.hover()
    page.wait_for_timeout(250)
    return "첫 행 hover"


def st_knowledge_default(page, base, settle):
    _goto(page, base, "/knowledge", settle)
    return "조건 없음"


def st_knowledge_tag_author(page, base, settle):
    _goto(page, base, "/knowledge", settle)
    # 조건 둘 — 프로젝트(사람이 고른 자리)와 태그(다중 선택 요약). 로컬 씨앗의 문서에는 작성자 후보가 없어
    # (목록 응답의 `authors` 가 비어 있다) 작성자 대신 프로젝트를 고른다. 이름은 옛 상태 이름을 그대로 둔다.
    _pick_combobox(page, "프로젝트")
    _pick_combobox(page, "태그", skip_all=False)
    return "프로젝트 + 태그"


def st_knowledge_sort_menu(page, base, settle):
    _goto(page, base, "/knowledge", settle)
    opener = _first(page, [
        "#main-content [data-filter-surface] [role=combobox]:has-text('정렬')",
        "#main-content [data-filter-surface] .MuiSelect-select:has-text('정렬')",
    ])
    if opener is None:
        raise StateSkipped("정렬 칸을 못 찾음")
    _click(opener, "상태를 여는 단추")
    page.wait_for_timeout(450)
    return "정렬 메뉴 열림"


def st_knowledge_row_menu(page, base, settle):
    _goto(page, base, "/knowledge", settle)
    opener = _first(page, ["#main-content tbody [aria-label$='더 보기']", "#main-content tbody [aria-haspopup='menu']"])
    if opener is None:
        raise StateSkipped("행 「더 보기」를 못 찾음")
    _click(opener, "상태를 여는 단추")
    page.wait_for_timeout(450)
    return "행 더 보기 메뉴 열림"


def st_knowledge_empty(page, base, settle):
    _goto(page, base, "/knowledge?q=zzqx-없는-검색어", settle)
    return "검색 결과 0건"


def st_new_ticket_empty(page, base, settle):
    _goto(page, base, "/new-ticket", settle)
    return "빈 폼"


def st_new_ticket_submit_error(page, base, settle):
    _goto(page, base, "/new-ticket", settle)
    button = _first(page, ["#main-content [data-action-footer] button:has-text('티켓 추가')", "#main-content button:has-text('티켓 추가')"])
    if button is None:
        raise StateSkipped("「티켓 추가」 단추를 못 찾음")
    # 제목이 비어 있으면 `NewTicket.submit` 이 서버 요청 전에 칸 오류로 멈춘다.
    title = page.locator("#main-content input").first
    if title.count() and (title.input_value() or "").strip():
        raise StateSkipped("제목이 비어 있지 않다 — 제출하면 서버로 간다")
    _click(button, "제출 단추")
    page.wait_for_timeout(500)
    return "빈 채 제출 → 칸 오류"


def st_new_ticket_scrolled(page, base, settle):
    _goto(page, base, "/new-ticket", settle)
    page.evaluate("() => window.scrollTo(0, Math.max(0, (document.documentElement.scrollHeight - innerHeight) / 2))")
    page.wait_for_timeout(300)
    return "중간 스크롤"


def st_new_ticket_project_picked(page, base, settle):
    _goto(page, base, "/new-ticket", settle)
    box = _first(page, ["#main-content input[aria-labelledby][role=combobox]", "#main-content [role=combobox]"])
    if box is None:
        raise StateSkipped("프로젝트 고르개를 못 찾음")
    box.click()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(450)
    options = page.locator("[role=listbox] [role=option]")
    if options.count() == 0:
        raise StateSkipped("프로젝트 후보가 없다")
    # 첫 후보는 「프로젝트 선택」(값 없음 자리, `EntityCombobox allLabel`)이다 — 그것을 누르면 아무것도 안 고른 채 「고름」으로 적혔다(P4 눈 대조).
    index = next((i for i in range(options.count())
                  if not re.search(r"프로젝트 선택|전체|고르세요", options.nth(i).inner_text() or "")), None)
    if index is None:
        raise StateSkipped("고를 프로젝트 후보가 없다(값 없음 자리뿐)")
    name = (options.nth(index).inner_text() or "").strip()
    options.nth(index).click()
    page.wait_for_timeout(700)
    shown = box.input_value() if box.evaluate("(el) => el.tagName === 'INPUT'") else (box.inner_text() or "")
    if not shown or re.search(r"프로젝트 선택", shown):
        raise StateSkipped("고른 프로젝트가 칸에 서지 않았다")
    return f"프로젝트 고름({name[:20]})"


def st_knowledge_doc_editing(page, base, settle):
    # 휴지통 밖 문서는 열면 곧바로 편집 중이다(`KnowledgeDoc.jsx` — 읽기 전용은 휴지통 문서뿐) — 누를 것이 없다.
    from scripts.ui_qa import capture as cap

    doc_id = cap._first_id(_api_json(page, base, "/api/knowledge/documents"))
    if not doc_id:
        raise StateSkipped("문서가 없다")
    _goto(page, base, f"/knowledge/{doc_id}", settle)
    if _first(page, ["#main-content [data-editor-box]"]) is None:
        raise StateSkipped("편집기 상자가 서지 않았다(휴지통 문서이거나 편집기 청크 실패)")
    return "문서 편집 중"


def st_knowledge_doc_trashed(page, base, settle):
    """휴지통 문서 화면 — 서버에는 아무것도 쓰지 않는다.

    로컬 씨앗의 휴지통 줄은 옛 미러(티켓 · 옛 문서)라 휴지통에 든 지식 문서가 없고, 문서를 휴지통으로 보내는 것은 쓰기다.
    그래서 이 페이지의 문서 응답에만 휴지통 표식(`archived` · `archived_at` · `archiver`)을 얹어 그 화면을 세운다
    (`KnowledgeDoc.jsx::trashed` 가 보는 값). 가로채기는 이 상태의 페이지에만 걸리고 페이지를 닫으면 걷힌다.
    """
    from scripts.ui_qa import capture as cap

    doc_id = cap._first_id(_api_json(page, base, "/api/knowledge/documents"))
    if not doc_id:
        raise StateSkipped("문서가 없다")

    def shape(route):
        response = route.fetch()
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            route.fulfill(response=response)
            return
        if isinstance(body, dict):
            body.update({"archived": True, "archived_at": "2026-09-01T09:00:00Z",
                         "archiver": {"display_name": "UI QA"}, "can_manage": True})
        route.fulfill(response=response, json=body)

    page.route(f"**/api/knowledge/documents/{doc_id}", shape)
    _goto(page, base, f"/knowledge/{doc_id}", settle)
    if _first(page, ["#main-content .k-callout"]) is None:
        raise StateSkipped("휴지통 안내 상자가 서지 않았다")
    return "휴지통 문서(응답 표식)"


def st_knowledge_taxonomy_template(page, base, settle):
    # 「분류 관리」 → 「틀」 → 「새 틀」 은 틀 판만 연다(저장 · 추가는 누르지 않는다).
    _goto(page, base, "/knowledge", settle)
    opener = _first(page, ["#main-content button:has-text('분류 관리')"])
    if opener is None:
        raise StateSkipped("「분류 관리」를 못 찾음")
    _click(opener, "창을 여는 단추")
    page.wait_for_timeout(500)
    tab = _first(page, [".MuiDialog-root [role=tab]:has-text('틀')"])
    if tab is None:
        raise StateSkipped("「틀」 탭을 못 찾음")
    tab.click()
    page.wait_for_timeout(400)
    new = _first(page, [".MuiDialog-root button:has-text('새 틀')"])
    if new is None:
        raise StateSkipped("「새 틀」을 못 찾음")
    _click(new, "틀 판을 여는 단추")
    page.wait_for_timeout(500)
    if _first(page, [".MuiDialog-root [data-action-footer='modal']"]) is None:
        raise StateSkipped("창 발이 서지 않았다")
    return "분류 관리 틀 판 열림"


def st_ticket_detail_body_editing(page, base, settle):
    # 「… 수정」은 편집 모드만 연다(`EditableBody.jsx::startEditing` — 서버 요청이 없다). 저장은 누르지 않는다.
    from scripts.ui_qa import capture as cap

    ticket_id = None
    for endpoint in ("/api/tickets/mine", "/api/tickets/team?active=false"):
        ticket_id = cap._first_id(_api_json(page, base, endpoint))
        if ticket_id:
            break
    if not ticket_id:
        raise StateSkipped("티켓이 없다")
    _goto(page, base, f"/tickets/{ticket_id}", settle)
    opener = _first(page, ["#main-content button:has-text('본문 수정')", "#main-content button:has-text('설명 수정')"])
    if opener is None:
        raise StateSkipped("본문 「수정」 단추를 못 찾음")
    _click(opener, "편집을 여는 단추")
    page.wait_for_timeout(900)
    if _first(page, ["#main-content [data-editor-box]"]) is None:
        raise StateSkipped("편집기 상자가 서지 않았다")
    return "티켓 본문 편집 중"


def st_settings_editor_open(page, base, settle):
    # 행 「수정」은 편집 모달만 연다(`SettingsMain.jsx` → `SettingEditor` — 서버 요청이 없다). 저장 · 미리 검증은 누르지 않는다.
    page.goto(f"{base.rstrip('/')}/admin#/settings", wait_until="domcontentloaded", timeout=45_000)
    from scripts.ui_qa import capture as cap

    cap._settle(page, settle_ms=settle, timeout_ms=45_000)
    opener = _first(page, ["#main-content tbody [data-row-actions] button:has-text('수정')"])
    if opener is None:
        raise StateSkipped("설정 행 「수정」을 못 찾음(쓰기 권한이 없거나 표가 비었다)")
    _click(opener, "편집 모달을 여는 단추")
    page.wait_for_timeout(700)
    if _first(page, [".MuiDialog-root [data-action-footer='modal']"]) is None:
        raise StateSkipped("편집 모달 발이 서지 않았다")
    return "설정 편집 모달 열림"


def st_scheduler_run_detail(page, base, settle):
    """예약 달력 실행 상세 창(실패한 실행) — 서버에는 아무것도 쓰지 않는다.

    로컬 씨앗의 달력에는 예정(planned)만 있고 실제 실행 기록이 없어 재시도 · 작업 큐 동작이 서는 창을 열 수 없고, 실행을 만드는 것은
    쓰기다. 그래서 이 페이지의 달력 응답에만 오늘 실패한 실행 하나를 얹고(켜진 일정이 없으면 일정도 하나) 그 점을 눌러 창을 연다
    (재시도 · 취소는 누르지 않는다). 가로채기는 이 상태의 페이지에만 걸린다.
    """
    import datetime as dt

    from scripts.ui_qa import capture as cap

    # 점의 글자에 누르지 않는 낱말(「실행」 같은 것)이 들면 `_click` 이 상태를 건너뛴다 — 이름은 그 낱말을 피한다.
    name = "UI QA 점검 일정"

    def shape(route):
        response = route.fetch()
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            route.fulfill(response=response)
            return
        if isinstance(body, dict):
            # 서버는 naive UTC 로 준다 — KST 오늘 09:00 이 UTC 오늘 00:00 이다.
            today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
            body["items"] = list(body.get("items") or []) + [{
                "kind": "run", "schedule_id": "ui-qa-schedule", "schedule_name": name, "occurs_at": f"{today}T00:00:00",
                "status": "failed", "run_id": "ui-qa-run", "error_message": "대상 서비스가 500 을 돌려주었습니다.",
            }]
            schedules = list(body.get("schedules") or [])
            if not any(s.get("enabled") for s in schedules if isinstance(s, dict)):
                schedules.append({"id": "ui-qa-schedule", "name": name, "enabled": True, "timezone": "Asia/Seoul"})
            body["schedules"] = schedules
        route.fulfill(response=response, json=body)

    page.route("**/api/admin/schedules/calendar*", shape)
    page.goto(f"{base.rstrip('/')}/admin#/scheduler-calendar", wait_until="domcontentloaded", timeout=45_000)
    cap._settle(page, settle_ms=settle, timeout_ms=45_000)
    dot = _first(page, [f"#main-content button[title*='{name}']"])
    if dot is None:
        raise StateSkipped("얹은 실행의 점을 못 찾음(달력이 서지 않았다)")
    _click(dot, "실행 점")
    page.wait_for_timeout(600)
    if _first(page, [".MuiDialog-root [data-action-footer='modal']"]) is None:
        raise StateSkipped("실행 상세 창 발이 서지 않았다")
    return "실행 상세 창(응답 표식 · 실패한 실행)"


def st_chat_manage_open(page, base, settle):
    # 방장인 그룹 방의 「관리」는 창만 연다(`ChatRoomMembers.jsx::ManageRoomModal` — 저장 · 초대는 누르지 않는다).
    rid = _room_of(page, base, "group")
    if not rid:
        raise StateSkipped("그룹 방이 없다")
    _goto(page, base, f"/chat-rooms/{rid}", settle)
    opener = _first(page, ["#main-content [data-room-head] button:has-text('관리')", "#main-content button:text-is('관리')"])
    if opener is None:
        raise StateSkipped("「관리」가 없다(방장이 아니다)")
    _click(opener, "관리 창을 여는 단추")
    page.wait_for_timeout(800)
    if _first(page, [".MuiDialog-root [data-form-scope]"]) is None:
        raise StateSkipped("관리 창의 입력 영역이 서지 않았다")
    return "채팅방 관리 창"


def _room_of(page, base, kind: str):
    payload = _api_json(page, base, "/api/team-chat/rooms") or {}
    # 응답은 `{"items": [...], "team": {...}, "global": {...}}` 다(`app/team_chat/router.py::list_rooms`).
    rooms = list(payload.get("items") or []) if isinstance(payload, dict) else list(payload or [])
    if isinstance(payload, dict) and payload.get("team"):
        rooms.append(payload["team"])
    for room in rooms:
        if room.get("kind") == kind and not room.get("is_global"):
            return room.get("id")
    return None


def st_chat_group(page, base, settle):
    rid = _room_of(page, base, "group")
    if not rid:
        raise StateSkipped("그룹 방이 없다")
    _goto(page, base, f"/chat-rooms/{rid}", settle)
    return "그룹 방"


def st_chat_direct(page, base, settle):
    rid = _room_of(page, base, "direct")
    if not rid:
        raise StateSkipped("1:1 방이 없다")
    _goto(page, base, f"/chat-rooms/{rid}", settle)
    return "1:1 방"


def st_chat_list_search_empty(page, base, settle):
    _goto(page, base, "/chat-rooms", settle)
    box = _first(page, ["#main-content input[type=search]", "#main-content input[placeholder*='검색']"])
    if box is None:
        raise StateSkipped("목록 검색을 못 찾음")
    box.fill("zzqx-없는-방")
    page.wait_for_timeout(700)
    return "목록 검색 0건"


def st_users_selected(page, base, settle):
    page.goto(f"{base.rstrip('/')}/admin#/users", wait_until="domcontentloaded", timeout=45_000)
    from scripts.ui_qa import capture as cap

    cap._settle(page, settle_ms=settle, timeout_ms=45_000)
    _rows_select(page, 2)
    return "사용자 2명 선택"


def st_trash_selected(page, base, settle):
    _goto(page, base, "/team-docs/trash", settle)
    _rows_select(page, 2)
    return "휴지통 2건 선택"


# (이름, 경로 id(기대 표), 함수, 원격에서도 되는가)
STATES = (
    ("my-tickets.default", "user_my-tickets", st_my_tickets_default, True),
    ("my-tickets.multi", "user_my-tickets", st_my_tickets_multi, True),
    ("my-tickets.selected", "user_my-tickets", st_my_tickets_selected, True),
    ("my-tickets.col-filter", "user_my-tickets", st_my_tickets_col_filter, True),
    ("my-tickets.project-open", "user_my-tickets", st_my_tickets_project_open, True),
    ("unassigned.hover", "user_unassigned", st_unassigned_hover, True),
    ("knowledge.default", "user_knowledge", st_knowledge_default, True),
    ("knowledge.tag-author", "user_knowledge", st_knowledge_tag_author, True),
    ("knowledge.sort-menu", "user_knowledge", st_knowledge_sort_menu, True),
    ("knowledge.row-menu", "user_knowledge", st_knowledge_row_menu, True),
    ("knowledge.empty", "user_knowledge", st_knowledge_empty, True),
    ("new-ticket.empty", "user_new-ticket", st_new_ticket_empty, True),
    ("new-ticket.submit-error", "user_new-ticket", st_new_ticket_submit_error, False),
    ("new-ticket.scrolled", "user_new-ticket", st_new_ticket_scrolled, True),
    ("new-ticket.project-picked", "user_new-ticket", st_new_ticket_project_picked, True),
    ("knowledge-doc.editing", "user_knowledge-doc", st_knowledge_doc_editing, True),
    ("knowledge-doc.trashed", "user_knowledge-doc", st_knowledge_doc_trashed, True),
    ("knowledge.taxonomy-template", "user_knowledge", st_knowledge_taxonomy_template, True),
    ("ticket-detail.body-editing", "user_ticket-detail", st_ticket_detail_body_editing, True),
    ("settings.editor-open", "admin_settings", st_settings_editor_open, True),
    ("chat.group", "user_chat-room-detail", st_chat_group, True),
    ("chat.direct", "user_chat-room-detail", st_chat_direct, True),
    ("chat.list-search-empty", "user_chat-rooms", st_chat_list_search_empty, True),
    ("chat.manage-open", "user_chat-room-detail", st_chat_manage_open, True),
    ("scheduler-calendar.run-detail", "admin_scheduler-calendar", st_scheduler_run_detail, True),
    ("users.selected", "admin_users", st_users_selected, True),
    ("trash.selected", "user_team-docs-trash", st_trash_selected, True),
)


def run(args) -> int:
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa import capture as cap, tls
    from scripts.ui_qa.auth import ensure_session
    from scripts.ui_qa.kit_measure import CONTRACT, MEASURE_JS, _mascot_hfrac

    base = (args.base_url or cap.DEFAULT_BASE_URL).rstrip("/")
    insecure = tls.apply_default_https_context()
    out_root = Path(args.out_root) if args.out_root else OUT_BASE
    out_dir = out_root / args.states_label
    shots = out_dir / "states"
    shots.mkdir(parents=True, exist_ok=True)
    auth_dir = Path(args.auth_dir) if args.auth_dir else OUT_BASE / "auth-states"
    wanted = set(args.states or [])
    states = [s for s in STATES if (not wanted or s[0] in wanted) and (s[3] or not args.remote_safe)]
    viewports = cap.resolve_viewports(args.viewports or ["1920x1080"])
    themes = args.states_themes or ["light"]
    hfrac = _mascot_hfrac()
    records: list[dict] = []
    totals = defaultdict(lambda: {"checked": 0, "failed": 0})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, auth_dir, insecure=insecure, log=print)
            for theme in themes:
                for viewport in viewports:
                    ctx = cap.new_context(browser, storage_state=session.storage_state, user_id=session.user_id,
                                          theme=theme, viewport=viewport, insecure=insecure)
                    try:
                        for name, route_id, fn, _remote in states:
                            page = ctx.new_page()
                            key = f"{name}__{theme}__{viewport.name}"
                            record = {"state": name, "route": route_id, "theme": theme, "viewport": viewport.name}
                            try:
                                record["note"] = fn(page, base, args.settle_ms)
                                shot = shots / theme / viewport.name / f"{name}.png"
                                shot.parent.mkdir(parents=True, exist_ok=True)
                                page.screenshot(path=str(shot), full_page=False)
                                record["shot"] = str(shot.relative_to(REPO_ROOT)).replace("\\", "/")
                                composed = page.evaluate(COMPOSITION_JS, {**COMPOSITION_CONTRACT, "scope": None,
                                                                          "expect": expect_for(route_id)})
                                parts = page.evaluate(MEASURE_JS, {**CONTRACT, "scope": None, "mascotHfrac": hfrac})
                                record["composition"] = composed
                                record["parts"] = {k: v for k, v in parts.items() if isinstance(v, dict) and "checked" in v}
                                fails = []
                                for check in COMPOSITION_CHECKS:
                                    got = composed.get(check) or {}
                                    totals[check]["checked"] += got.get("checked", 0)
                                    totals[check]["failed"] += got.get("failed", 0)
                                    if got.get("failed"):
                                        fails.append(check)
                                record["failed"] = fails
                                print(f"[states] {key:<52} " + (", ".join(fails) if fails else "ok"), flush=True)
                            except StateSkipped as exc:
                                record["skipped"] = str(exc)
                                print(f"[states] {key:<52} SKIPPED — {exc}", flush=True)
                            except Exception as exc:  # noqa: BLE001
                                record["error"] = f"{type(exc).__name__}: {exc}"[:300]
                                print(f"[states] {key:<52} ERROR — {record['error']}", flush=True)
                            finally:
                                page.close()
                            records.append(record)
                    finally:
                        ctx.close()
        finally:
            browser.close()
    (out_dir / "states.json").write_text(json.dumps(
        {"base": base, "contract": COMPOSITION_CONTRACT, "totals": totals, "records": records},
        ensure_ascii=False, indent=1), encoding="utf-8")
    skipped = [r for r in records if r.get("skipped") or r.get("error")]
    print("")
    print(f"{'조합 검사':<22} {'표본':>6} {'실패':>6}")
    for check in COMPOSITION_CHECKS:
        t = totals[check]
        print(f"{check:<22} {t['checked']:>6} {t['failed']:>6}")
    print(f"상태 {len(records)}개 · 못 만든 상태 {len(skipped)}개 · states.json: {out_dir / 'states.json'}")
    fail_on = args.fail_on or []
    failed = [c for c in fail_on if totals[c]["failed"]]
    blind = [c for c in fail_on if totals[c]["checked"] == 0]
    if failed:
        print("COMPOSITION_STATES_FAILED: " + ", ".join(failed))
        return 1
    if skipped and fail_on:
        print("COMPOSITION_STATES_INCOMPLETE (못 만든 상태): " + ", ".join(sorted({r['state'] for r in skipped})))
        return 2
    if blind:
        print("COMPOSITION_STATES_BLIND (표본 0): " + ", ".join(blind))
        return 2
    print("COMPOSITION_STATES_OK" + (f" (--fail-on {', '.join(fail_on)})" if fail_on else " (보고만)"))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="화면 상태를 만들어 조합을 잰다")
    ap.add_argument("--viewports", nargs="*", default=None)
    ap.add_argument("--routes", nargs="*", default=None, help="(local_capture 호환용 — 쓰지 않는다)")
    ap.add_argument("--states-themes", nargs="*", default=None)
    ap.add_argument("--states-label", default="composition-states")
    ap.add_argument("--states", nargs="*", default=None, help="이 상태만(예: my-tickets.multi)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--settle-ms", type=int, default=600)
    ap.add_argument("--remote-safe", action="store_true", help="쓰기가 생길 수 있는 상태를 건너뛴다")
    ap.add_argument("--out-root", default=None)
    ap.add_argument("--auth-dir", default=None)
    ap.add_argument("--fail-on", nargs="*", default=None)
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
