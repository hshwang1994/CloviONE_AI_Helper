"""화면 · 상태 대장 (r23 W0a) — 69 화면과 추가 화면(EX)을 **상태 하나씩** 찍고, 보인 글자 · 조작 요소 · 겹침을 남긴다.

경로 캡처(`local_capture`)는 씨앗 그대로의 한 상태만 찍고, 상태 캡처(`state_capture`)는 몇 화면의 몇 상태만 찍는다. 이 하네스는
지시서의 69 화면 번호와 추가 화면 번호를 그대로 쓰는 **한 줄 = 화면 × 상태** 표(`CASES`)를 돈다. 줄마다:

  - 상태를 만든다 — 주소 조건, `page.route` 로 바꾼 응답(빈 목록 · 오류), 다른 역할 계정, 단추를 눌러 연 창
  - **상태 확인 셀렉터**가 화면에 섰는지 본다. 안 섰으면 그 줄은 「상태 못 만듦」이다(찍었다고 통과로 세지 않는다)
  - 폭 · 테마마다 PNG 를 남기고, 보인 글자(문구 대장 `copy_census.py map` 의 재료) · 조작 요소 · 겹침을 잰다

결과: `dist/ui-qa/<label>/<theme>/<viewport>/<id>.png` 와 `ledger.json`(줄 · 폭마다 상태 확인 · 콘솔 오류 · 가로 넘침 · 글자 ·
조작 요소 · 겹침). 고치거나 지우는 줄(`mutates`)은 로컬 임시 DB 에서만 돈다 — 랩(`--base-url`)에서는 건너뛴다.

    python -m scripts.ui_qa.screen_ledger --label r23-before --profile text
    python -m scripts.ui_qa.screen_ledger --label r23-before-visual --profile visual --ids 01 03 61
    python -m scripts.ui_qa.screen_ledger --label r23-lab --base-url https://clovirassist.goodmit.co.kr --profile quick
    python -m scripts.ui_qa.screen_ledger --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402

OUT_BASE = ROOT / "dist" / "ui-qa"
EMAIL, PASSWORD = "ui-qa@goodmit.co.kr", "Ui-Qa-Local-1!"
# 로컬 씨앗의 역할 계정(`local_server.seed`). 비밀번호는 씨앗과 같은 로컬 전용 값이다.
ROLE_ACCOUNTS = {
    "system_admin": EMAIL,
    "admin": "park.minjun@goodmit.co.kr",
    "operator": "kim.jihoon@goodmit.co.kr",
    "user": "lee.seoyeon@goodmit.co.kr",
}

_V = Viewport
# 묶음 — 같은 줄을 어떤 폭 · 테마로 찍을지. 글자 · 조작 요소는 폭에 따라 거의 같아서 `text` 는 둘만 찍는다.
PROFILES: dict[str, list[tuple[str, Viewport]]] = {
    "text": [("light", _V("1920x1080", 1920, 1080)), ("light", _V("390x844", 390, 844))],
    "quick": [("light", _V("1920x1080", 1920, 1080)), ("light", _V("1366x768", 1366, 768))],
    "visual": [
        ("light", _V("1920x1080", 1920, 1080)), ("light", _V("1366x768", 1366, 768)),
        ("light", _V("1024x768", 1024, 768)), ("light", _V("390x844", 390, 844)),
        ("dark", _V("1920x1080", 1920, 1080)), ("dark", _V("390x844", 390, 844)),
        # 125% 확대 — CSS 뷰포트가 1/1.25 로 줄고 픽셀 밀도가 1.25 다(`s22-zoom` 과 같은 방식).
        ("light", _V("1536x864@1.25x", 1536, 864, 1.25)), ("light", _V("1093x614@1.25x", 1093, 614, 1.25)),
    ],
    "low": [
        ("light", _V("1366x600", 1366, 600)), ("light", _V("1280x600", 1280, 600)),
        ("light", _V("1024x600", 1024, 600)), ("light", _V("390x500", 390, 500)),
    ],
}


@dataclass(frozen=True)
class Case:
    """한 줄 = 화면 × 상태."""

    id: str                 # 지시서 번호(01 ~ 69) 또는 EX-영역-번호
    name: str               # 화면 · 상태 이름(보고서의 「실제 페이지/상태」 칸)
    path: str               # 해시 경로. `{project}` 같은 자리는 실행 때 찾은 id 로 채운다
    console: str = "user"   # "user" · "admin" · "public"(서버 화면 — 해시가 아니라 경로)
    role: str = "system_admin"
    routes: tuple = ()      # (주소 패턴, "empty" | "error500" | "error403" | "error404")
    act: str = ""           # 상태를 만드는 동작 키(`ACTIONS`)
    check: str = "main"     # 이 셀렉터가 보여야 상태가 선 것이다
    mutates: bool = False   # 데이터를 바꾸는 줄 — 랩에서는 건너뛴다
    note: str = ""          # 보고서에 같이 적을 말(상태를 만드는 방법 등)


E = ".k-empty"                      # 빈 상태(띠 · 구획 · 화면 전체 모두)
BAND = "[data-empty-layout=band]"   # 표 안 한 줄 띠
DLG = "[role=dialog]"               # 열린 창(보이는 것만 센다 — `_visible`)
ERR = ".k-error, [data-list-state], [role=alert]"
# 목록이 선 상태 — 넓은 폭은 표, 좁은 폭(카드 보기)은 카드 묶음이다. 표만 보면 390 이 늘 「상태 못 만듦」이 된다.
# `[data-table-cards]` 는 r23 부터 표가 카드 보기에 다는 표지이고, 그 전 번들은 카드(이름 칸이 있는 판)로 알아본다.
LIST = ("table, [data-table-cards], "
        "main .MuiStack-root > .MuiPaper-outlined:has(.MuiTypography-caption)")
LIST_E = LIST + ", .k-empty"

# 메일 · 로컬 릴레이(직접 전달) 상태를 세우는 응답 바꾸기 셋(D-592) — 상태 · 설정 · 릴레이 보기.
MAIL_RELAY_ROUTES = (
    ("**/api/admin/mail/status*", "mail_relay_status"),
    ("**/api/admin/mail/settings", "mail_relay_settings"),
    ("**/api/admin/mail/relay", "mail_relay_view"),
)

# ── 지시서 69 화면 ─────────────────────────────────────────────────────────────
C69: list[Case] = [
    # 홈 업무 판(D-589 이후 「내 티켓」 구역 이름이 없어졌다 — 판 격자의 표지로 상태를 확인한다).
    Case("01", "홈", "/me", check="[data-testid=home-body-grid]"),
    Case("01-zero", "홈 · 티켓 0건", "/me", routes=(("**/api/home/today*", "empty_buckets"),), check=E),
    Case("02", "내 티켓 · 조건 0건", "/my-tickets?q=zzzz-none-r23", check=E),
    Case("02-default", "내 티켓 · 기본(종료 제외) 0건", "/my-tickets", routes=(("**/api/tickets/mine*", "empty"),), check=E),
    Case("02-all", "내 티켓 · 모든 상태 0건", "/my-tickets?all_status=1", routes=(("**/api/tickets/mine*", "empty"),), check=E),
    Case("03", "새 티켓", "/new-ticket", check="form, [data-form-section], main"),
    Case("03-invalid", "새 티켓 · 필수 칸 오류", "/new-ticket", act="submit_empty", check="[role=alert], .Mui-error"),
    Case("04", "내 티켓 · 데이터 목록", "/my-tickets?all_status=1", check=LIST),
    Case("05", "승인 · 처리할 승인", "/my-approvals?box=todo", check=LIST_E),
    Case("05-requested", "승인 · 내가 올린 요청", "/my-approvals?box=requested", check=LIST_E),
    Case("05-done", "승인 · 처리한 건", "/my-approvals?box=done", check=LIST_E),
    Case("06", "승인 · 0건", "/my-approvals?box=todo", routes=(("**/api/approvals/mine*", "empty"),), check=E),
    Case("06-deny", "승인 · 결재 권한 없음", "/my-approvals?box=todo", role="user", check=E),
    Case("07", "알림", "/notifications", check=LIST_E),
    Case("07-unread", "알림 · 안 읽음만", "/notifications?unread_only=1", check=LIST_E),
    Case("07-zero", "알림 · 0건", "/notifications", routes=(("**/api/notifications*", "empty"),), check=E),
    Case("08", "AI 도우미 · 새 대화", "/chat", check="main"),
    Case("09", "프로젝트 목록", "/projects", check=LIST),
    Case("09-zero", "프로젝트 · 조건 0건", "/projects?q=zzzz-none-r23", check=E),
    Case("10", "프로젝트 상세 · 개요", "/projects/{project}", check="[role=tabpanel], main"),
    Case("11", "프로젝트 상세 · WBS", "/projects/{project}?tab=wbs", check="[role=tabpanel]"),
    # 응답을 비우면 진행률(25%)이 빈 트리 옆에 남는다 — 실제로 티켓이 없는 프로젝트를 연다(로컬에서 만든 「[검증]」 프로젝트).
    Case("11-zero", "프로젝트 상세 · WBS 0건", "/projects/{project_empty}?tab=wbs", check=E),
    Case("12", "프로젝트 상세 · 마일스톤 0건", "/projects/{project}?tab=milestones",
         routes=(("**/api/projects/*/milestones*", "empty"),), check=E),
    Case("12-data", "프로젝트 상세 · 마일스톤", "/projects/{project}?tab=milestones", check="[role=tabpanel]"),
    Case("13", "프로젝트 상세 · 티켓", "/projects/{project}?tab=tickets", check="[role=tabpanel]"),
    Case("13-zero", "프로젝트 상세 · 티켓 조건 0건", "/projects/{project}?tab=tickets&q=zzzz-none-r23", check=E),
    Case("14", "프로젝트 상세 · 문서", "/projects/{project}?tab=documents", check="[role=tabpanel]"),
    Case("15", "프로젝트 상세 · 주간 리포트", "/projects/{project}?tab=weekly", check="[role=tabpanel]"),
    Case("15-edit", "프로젝트 상세 · 수정 창", "/projects/{project}", act="open_edit", check=DLG),
    Case("16", "팀 티켓", "/team-tickets", check=LIST_E),
    Case("16-zero", "팀 티켓 · 조건 0건", "/team-tickets?q=zzzz-none-r23", check=E),
    Case("17", "미할당 티켓", "/unassigned", check=LIST_E),
    Case("17-zero", "미할당 티켓 · 0건", "/unassigned", routes=(("**/api/tickets/unassigned*", "empty"),), check=E),
    Case("18", "작업 보드", "/work-board", check="main"),
    Case("18-backlog", "작업 보드 · 백로그", "/work-board?tab=backlog", check="main"),
    Case("19", "스프린트 회의 · 회차 고르기 전", "/sprint?{sprint_idle_q}", check=E),
    Case("19-none", "스프린트 회의 · 회차 없음", "/sprint?{sprint_none_q}", check=E),
    Case("20", "스프린트 회의 · 회차", "/sprint?{sprint_q}", check="main"),
    Case("20-empty", "스프린트 회의 · 담긴 티켓이 없는 회차", "/sprint?{sprint_q}",
         routes=(("**/api/work/sprints/*/meeting*", "empty_meeting"),), check="main",
         note="회의 응답의 집계 · 그림 · 논의 목록을 비운다(r23 #51)"),
    Case("21", "문서", "/knowledge", check=LIST_E),
    Case("22", "문서 휴지통 · 문서 0건", "/team-docs/trash?kind=document", routes=((re.compile(r"/api/trash\?"), "empty_trash_docs"),), check=E),
    Case("22-data", "문서 휴지통", "/team-docs/trash", check="main"),
    Case("23", "채팅방", "/chat-rooms/{chatroom}", check="main"),
    Case("24", "자유게시판 · 0건", "/board", routes=(("**/api/board/posts*", "empty"),), check=E),
    Case("24-filter", "자유게시판 · 조건 0건", "/board?q=zzzz-none-r23", check=E),
    Case("25", "기능 개선 제안", "/ideas", check=LIST_E),
    Case("26", "기능 개선 제안 · 상세", "/board/{idea}", check="main"),
    Case("27", "놀이 · 0건", "/games", routes=(("**/api/games/rooms", "empty"),), check=E),
    Case("27-data", "놀이 · 방 있음", "/games", check="main"),
    Case("28", "내 프로필", "/profile", check="main"),
    Case("29", "내 업무량", "/my-stats", check="main"),
    Case("30", "내 활동 · 전체", "/activity", check="main"),
    Case("31", "내 활동 · 내가 한 일", "/activity", act="activity_mine", check="main"),
    Case("32", "관리자 대시보드", "/dashboard", console="admin"),
    Case("33", "관리 알림", "/admin-notifications", console="admin", check=LIST_E),
    Case("34", "작업 큐", "/jobs", console="admin", check=LIST_E),
    Case("35", "진단", "/diagnostics", console="admin"),
]

C69 += [
    Case("36", "조직 정합성 · 첫 화면", "/integrity", console="admin", check="main"),
    Case("37", "조직 정합성 · 티켓 표", "/integrity?tab=tickets", console="admin", check="main"),
    Case("38", "조직 정합성 · 사람 탭", "/integrity?tab=people", console="admin", check="main"),
    Case("39", "조직 정합성 · 문제 없는 탭", "/integrity?tab=sprints", console="admin", check="main"),
    Case("40", "조직 정합성 · 관리자 범위", "/integrity?tab=admins", console="admin", check="main"),
    Case("41", "백업", "/backup", console="admin", check=LIST_E),
    Case("42", "백업 · 상세 창", "/backup", console="admin", act="open_first_row", check=DLG),
    Case("43", "메일 · 설정", "/mail?tab=settings", console="admin", check="[data-testid=mail-settings-form], main"),
    Case("43-relay", "메일 · 설정 · 로컬 릴레이 직접 전달", "/mail?tab=settings", console="admin", routes=MAIL_RELAY_ROUTES,
         check="[data-testid=relay-component]", note="이 PC 에는 릴레이가 없어 고정 응답(fixtures/relay_view.json)으로 세운다"),
    Case("43-relay-ro", "메일 · 설정 · 로컬 릴레이 읽기 전용(관리자)", "/mail?tab=settings", console="admin", role="admin",
         routes=MAIL_RELAY_ROUTES, check="[data-testid=mail-settings-readonly]"),
    Case("44", "메일 · 발송 기록", "/mail?tab=deliveries", console="admin", check=LIST_E),
    Case("45", "메일 · 알림 메일", "/mail?tab=notifications", console="admin", check="main"),
    Case("46", "설정 · 시스템 정책", "/settings", console="admin"),
    Case("47", "설정 · OS와 서비스", "/settings?tab=os", console="admin"),
    Case("48", "설정 · 파일 저장소", "/settings?tab=storage", console="admin"),
    Case("48-zero", "설정 · 파일 저장소 0건", "/settings?tab=storage", console="admin",
         routes=(("**/api/admin/storage/providers*", "empty"),), check=E),
    Case("49", "초기 설정", "/setup", console="admin", check="[data-testid=setup-checklist], main"),
    Case("50", "기능 플래그", "/feature-flags", console="admin", check=LIST_E),
    Case("51", "공지 배너 · 0건", "/announcements", console="admin", routes=(("**/api/admin/announcements*", "empty"),), check=E),
    Case("51-data", "공지 배너", "/announcements", console="admin", check=LIST_E),
    Case("52", "사용자 관리", "/users", console="admin", check=LIST),
    Case("53", "오프보딩", "/offboarding", console="admin", check="main"),
    Case("54", "조직 관리", "/organizations", console="admin", check="[data-workspace-pane], main"),
    Case("55", "직책 관리", "/job-titles", console="admin", check=LIST_E),
    Case("55-zero", "직책 관리 · 0건", "/job-titles", console="admin", routes=(("**/api/admin/job-titles*", "empty"),), check=E),
    Case("56", "권한 매트릭스", "/rbac", console="admin", check=LIST),
    Case("57", "관리자 승인 · 기본 조건", "/approvals", console="admin", check=LIST_E),
    Case("57-zero", "관리자 승인 · 0건", "/approvals", console="admin", routes=(("**/api/admin/approvals*", "empty"),), check=E),
    Case("58", "대리 보기", "/impersonation", console="admin", check=LIST_E),
    Case("58-zero", "대리 보기 · 0건", "/impersonation", console="admin", routes=(("**/api/admin/impersonation*", "empty"),), check=E),
    Case("59", "실행 일정 · 목록", "/schedules", console="admin", check=LIST_E),
    Case("60", "실행 일정 · 달력 0건", "/schedules?tab=scheduler-calendar", console="admin",
         # 달력의 빈 상태는 「일정이 하나도 없을 때」다(그 달에 실행이 없는 것만으로는 빈 격자다) — 일정 목록을 비운다.
         routes=((re.compile(r"/api/admin/schedules(\?|$)"), "empty"), ("**/api/admin/schedules/calendar*", "empty_calendar")), check=E),
    Case("60-data", "실행 일정 · 달력", "/schedules?tab=scheduler-calendar", console="admin", check="main"),
    Case("61", "AI 연결", "/ai-connection", console="admin", check="[data-testid=ai-connection-form], main"),
    Case("62", "AI 프롬프트", "/prompts", console="admin", check="main"),
    Case("63", "AI 정책", "/policies", console="admin", check="main"),
    Case("64", "AI 사용 한도 · 0건", "/ai-quotas", console="admin", routes=(("**/api/admin/ai-quotas*", "empty"),), check=E),
    Case("64-data", "AI 사용 한도", "/ai-quotas", console="admin", check="main"),
    Case("65", "AI 사용 통계", "/ai-usage", console="admin", check="main"),
    Case("66", "AI 사용 통계 · 호출 기록", "/ai-usage?tab=ai-usage-records", console="admin", check=LIST_E),
    Case("67", "감사 로그", "/audit", console="admin", check=LIST),
    Case("68", "감사 로그 · 조건 0건", "/audit?q=zzzz-none-r23", console="admin", check=E),
    Case("68-zero", "감사 로그 · 0건", "/audit", console="admin", routes=(("**/api/admin/audit*", "empty"),), check=E),
    Case("68-anomaly", "감사 로그 · 이상 징후", "/audit?tab=audit-anomalies", console="admin", check=LIST_E),
    Case("69", "개발자 월간 리포트", "/dev-report", console="admin"),
]

# ── 추가 화면(EX) — 화면 × 상태 한 줄씩. 게임방 여덟 종의 다섯 상태는 `games_e2e --states` 가 찍는다 ──────────
CEX: list[Case] = [
    Case("EX-T1", "티켓 상세", "/tickets/{ticket}", check="main h1, main"),
    Case("EX-T2", "티켓 수정 창", "/my-tickets?all_status=1", act="row_edit", check=DLG, note="목록 줄의 수정 단추"),
    Case("EX-T3", "티켓 삭제 확인", "/tickets/{ticket}", act="open_delete", check=DLG),
    Case("EX-T4", "티켓 없음", "/tickets/00000000-0000-0000-0000-000000000000", check=ERR),
    Case("EX-T5", "티켓 불러오기 오류", "/tickets/{ticket}", routes=(("**/api/tickets/*", "error500"),), check=ERR),
    Case("EX-D1", "문서 읽기", "/knowledge/{doc}", check="main"),
    Case("EX-D2", "새 문서 창", "/knowledge", act="doc_new", check=DLG),
    Case("EX-D3", "문서 분류 관리 창", "/knowledge", act="doc_categories", check=DLG),
    Case("EX-D4", "문서 삭제 확인", "/knowledge/{doc}", act="open_delete", check=DLG),
    Case("EX-D5", "문서 없음", "/knowledge/00000000-0000-0000-0000-000000000000", check=ERR),
    Case("EX-D6", "문서 목록 오류", "/knowledge", routes=(("**/api/knowledge/documents*", "error500"),), check=ERR),
    Case("EX-P1", "프로젝트 추가 창", "/projects", act="project_add", check=DLG),
    Case("EX-P2", "프로젝트 보관 확인", "/projects/{project}", act="project_archive", check=DLG),
    Case("EX-P3", "마일스톤 추가 창", "/projects/{project}?tab=milestones", act="milestone_add", check=DLG),
    Case("EX-P4", "마일스톤 삭제 확인", "/projects/{project}?tab=milestones", act="milestone_delete", check=DLG),
    Case("EX-P5", "프로젝트 없음", "/projects/00000000-0000-0000-0000-000000000000", check=ERR),
    Case("EX-P6", "프로젝트 목록 오류", "/projects", routes=(("**/api/projects*", "error500"),), check=ERR),
    Case("EX-B1", "자유게시판 글 상세", "/board/{post}", check="main"),
    Case("EX-B2", "자유게시판 글쓰기 창", "/board", act="board_write", check=DLG),
    Case("EX-B3", "게시글 삭제 확인", "/board/{post}", act="open_delete", check=DLG),
    Case("EX-B4", "게시글 없음", "/board/00000000-0000-0000-0000-000000000000", check=ERR),
    Case("EX-A1", "승인 · 승인 확인", "/my-approvals?box=todo", act="approval_confirm", check=DLG),
    Case("EX-C1", "채팅방 목록", "/chat-rooms", check="main"),
    # 팀 방과 전체 채팅은 늘 있어(`ensure_team_room`) 「방 0개」는 만들 수 없다 — 닿을 수 있는 빈 얼굴은 검색 0건이다.
    Case("EX-C2", "채팅방 목록 · 검색 0건", "/chat-rooms", act="chat_search_none", check=E),
    Case("EX-C3", "채팅방 · 새 그룹 창", "/chat-rooms", act="chat_new_group", check=DLG),
    Case("EX-C4", "채팅방 · 관리 창", "/chat-rooms/{chatroom}", act="chat_manage", check=DLG),
    Case("EX-C5", "채팅방 · 나가기 확인", "/chat-rooms/{chatroom}", act="chat_leave", check=DLG),
    Case("EX-C6", "AI 대화", "/chat/{conv}", check="main"),
    Case("EX-C7", "AI 대화 · 불러오기 오류", "/chat/{conv}", routes=(("**/api/conversations/*/messages*", "error500"),), check="main"),
    Case("EX-S1", "통합 검색 · 시작", "/search", check="main"),
    Case("EX-S2", "통합 검색 · 결과", "/search?q=%ED%9A%8C%EC%9D%98", check="main"),
    Case("EX-S3", "통합 검색 · 없음", "/search?q=zzzz-none-r23", check=E),
    Case("EX-S4", "문서에서 찾기 · 시작", "/ai", check="main"),
    Case("EX-S5", "문서에서 찾기 · 근거 없음", "/ai?q=zzzz-none-r23", check="main"),
    Case("EX-G0", "게임방 추가 창", "/games", act="game_add", check=DLG),
    Case("EX-AD1", "감사 로그 상세", "/audit/{audit}", console="admin", check="main"),
    Case("EX-AD2", "사용자 상세", "/users/{user}", console="admin", check="main"),
    Case("EX-AD3", "사용자 추가 창", "/users", console="admin", act="user_add", check=DLG),
    Case("EX-AD4", "부서 상세", "/departments/{dept}", console="admin", check="main"),
    Case("EX-AD5", "승인 위임 탭", "/approvals?tab=approval-delegations", console="admin", check="main"),
    Case("EX-AD6", "복구 리허설 탭", "/backup?tab=restore-drills", console="admin", check="main"),
    Case("EX-AD7", "작업 상세", "/jobs", console="admin", act="open_first_row", check=DLG),
    Case("EX-AD8", "공지 배너 추가 창", "/announcements", console="admin", act="registry_add", check=DLG),
    Case("EX-AD9", "직책 추가 창", "/job-titles", console="admin", act="registry_add", check=DLG),
    Case("EX-AD10", "실행 일정 추가 창", "/schedules", console="admin", act="registry_add", check=DLG),
    Case("EX-AD11", "사용 한도 추가 창", "/ai-quotas", console="admin", act="registry_add", check=DLG),
    Case("EX-AD12", "정책 추가 창", "/policies", console="admin", act="registry_add", check=DLG),
    Case("EX-UI1", "권한 없음 · 운영자가 사용자 관리", "/users", console="admin", role="operator", check=ERR + ", .k-empty"),
    Case("EX-UI2", "권한 없음 · 관리자가 초기 설정", "/setup", console="admin", role="admin", check=ERR + ", .k-empty"),
    Case("EX-UI3", "못 찾음 · 사용자 화면", "/zzzz-none-r23", check="main"),
    Case("EX-UI4", "못 찾음 · 관리자 화면", "/zzzz-none-r23", console="admin", check="main"),
    Case("EX-UI5", "클로비 패널", "/me", act="clovi_panel", check="[role=dialog], [role=complementary], aside"),
    Case("EX-UI6", "알림 종", "/me", act="bell_open", check="[role=dialog], [role=menu], [role=presentation]"),
    Case("EX-UI7", "명령 팔레트", "/me", act="palette_open", check=DLG),
    Case("EX-UI8", "사용자 메뉴", "/me", act="user_menu", check="[role=menu]"),
    Case("EX-UI9", "오픈소스 고지", "/me", act="oss_notice", check=DLG),
    Case("EX-UI10", "사용자 화면 · 일반 사용자", "/me", role="user", check="main"),
    Case("EX-UI11", "관리자 화면 · 운영자", "/dashboard", console="admin", role="operator", check="main"),
    Case("EX-SV1", "로그인", "/login", console="public", role="", check="form"),
    Case("EX-SV2", "로그인 · 틀린 비밀번호", "/login", console="public", role="", act="login_wrong", check="form"),
    Case("EX-SV3", "옛 문서 주소", "/team-docs/00000000-0000-0000-0000-000000000000", check="main"),
]

CASES: list[Case] = C69 + CEX


# ── 화면 안에서 재는 것 ────────────────────────────────────────────────────────
# 보인 글자 — 글 노드와, 안쪽에 덩어리 요소가 없는 요소의 글 전체(숫자가 끼어 쪼개진 문장을 한 줄로 다시 잇는다),
# 그리고 사람이 읽는 속성. 한글이 든 것만 모은다(영문 식별자 · 숫자는 문구가 아니다).
TEXT_JS = r"""
() => {
  const HANGUL = /[가-힣]/;
  const out = new Map();
  const vis = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const add = (text, kind, el) => {
    const t = (text || '').replace(/\s+/g, ' ').trim();
    if (!t || !HANGUL.test(t) || t.length > 400) return;
    const key = kind + '|' + t;
    if (!out.has(key)) out.set(key, { text: t, kind, tag: el ? el.tagName.toLowerCase() : '', role: el ? (el.getAttribute('role') || '') : '' });
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const p = node.parentElement;
    if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA'].includes(p.tagName)) continue;
    if (p.closest('[contenteditable=true], .ProseMirror, [data-user-content]')) continue;
    if (vis(p)) add(node.nodeValue, 'text', p);
  }
  const BLOCK = 'p,span,li,td,th,button,a,label,h1,h2,h3,h4,h5,h6,dt,dd,legend,option,[role=tab],[role=menuitem],[role=option],[role=status],[role=alert],[role=heading]';
  for (const el of document.querySelectorAll(BLOCK)) {
    if (!vis(el) || el.closest('[contenteditable=true], .ProseMirror, [data-user-content]')) continue;
    if (el.querySelector('div,p,ul,ol,table,section')) continue;
    add(el.innerText, 'block', el);
  }
  for (const el of document.querySelectorAll('[placeholder],[aria-label],[title],[alt],[aria-description]')) {
    if (!vis(el)) continue;
    for (const a of ['placeholder', 'aria-label', 'title', 'alt', 'aria-description']) {
      const v = el.getAttribute(a);
      if (v) add(v, a, el);
    }
  }
  return [...out.values()];
}
"""

# 조작 요소 — 역할 · 이름 · 비활성과 까닭 · 가림. 누르는 모양(cursor:pointer)인데 조작 역할이 없는 요소도 센다.
CONTROLS_JS = r"""
() => {
  const SEL = 'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [role=checkbox], [role=switch], [role=radio], [role=combobox], [role=menuitem], [role=option], [role=slider], [role=spinbutton]';
  const text = (id) => (document.getElementById(id) || {}).innerText || '';
  const items = [];
  for (const el of document.querySelectorAll(SEL)) {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (s.display === 'none' || s.visibility === 'hidden' || !(r.width > 0 && r.height > 0)) continue;
    // 접근성 트리 밖(aria-hidden 조상 · inert)은 조작 요소가 아니다 — MUI 선택 상자의 숨은 원본 입력(`MuiSelect-nativeInput`, 이름 없음 ·
    // 덮임)과 닫힌 서랍의 단추를 「이름 없는 입력」으로 셌다(r23 「후」 대장 192건).
    if (el.closest('[aria-hidden=true], [inert]')) continue;
    const tagRole = { A: 'link', BUTTON: 'button', SELECT: 'combobox', TEXTAREA: 'textbox', SUMMARY: 'button' }[el.tagName];
    const inputRole = el.tagName === 'INPUT' ? ({ checkbox: 'checkbox', radio: 'radio', range: 'slider' }[el.type] || 'textbox') : '';
    const role = el.getAttribute('role') || tagRole || inputRole || el.tagName.toLowerCase();
    const lb = el.getAttribute('aria-labelledby');
    let name = el.getAttribute('aria-label') || (lb ? lb.split(/\s+/).map(text).join(' ') : '')
      || (el.labels && el.labels[0] ? el.labels[0].innerText : '') || el.innerText || el.getAttribute('title')
      || el.getAttribute('placeholder') || '';
    name = name.replace(/\s+/g, ' ').trim().slice(0, 120);
    const disabled = !!el.disabled || el.getAttribute('aria-disabled') === 'true';
    let reason = '';
    if (disabled) {
      const d = el.getAttribute('aria-describedby');
      if (d) reason = d.split(/\s+/).map(text).join(' ').trim();
      const wrap = el.parentElement;
      if (!reason && wrap && wrap !== el) reason = wrap.getAttribute('aria-label') || wrap.getAttribute('title') || '';
      if (!reason) reason = el.getAttribute('title') || '';
    }
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    let covered = null;
    if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
      const top = document.elementFromPoint(cx, cy);
      covered = top ? !(el === top || el.contains(top) || top.contains(el)) : null;
    }
    items.push({ role, name, disabled, reason: reason.slice(0, 160), x: Math.round(r.left), y: Math.round(r.top),
      w: Math.round(r.width), h: Math.round(r.height), covered, tag: el.tagName.toLowerCase() });
  }
  const fakes = [];
  for (const el of document.querySelectorAll('body *')) {
    if (getComputedStyle(el).cursor !== 'pointer') continue;
    if (el.matches(SEL) || el.closest(SEL) || el.querySelector(SEL) || el.closest('label')) continue;
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    fakes.push({ tag: el.tagName.toLowerCase(), text: (el.innerText || '').trim().slice(0, 60), x: Math.round(r.left), y: Math.round(r.top) });
    if (fakes.length >= 40) break;
  }
  return { items, fakes };
}
"""

# 겹침 — 열린 창의 단추가 화면 밖인가 · 긴 창이 안에서 굴러가는가, 열린 메뉴가 화면 밖인가, 채팅 입력이 화면 안인가, 가로 넘침.
OVERLAP_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const outside = (r) => r.bottom > vh + 1 || r.top < -1 || r.right > vw + 1 || r.left < -1;
  // 닫힌 서랍(`inert` · `aria-hidden`)은 화면 밖으로 밀려 있어도 조작할 수 없다 — 단추가 화면 밖이라고 세지 않는다(AI 도우미 대화 목록 서랍).
  const dialogs = [...document.querySelectorAll('[role=dialog]')].filter(shown).filter((d) => !d.closest('[inert], [aria-hidden=true]')).map((d) => {
    const r = d.getBoundingClientRect();
    const btns = [...d.querySelectorAll('button')].filter(shown);
    const out = btns.filter((b) => outside(b.getBoundingClientRect())).map((b) => (b.innerText || b.getAttribute('aria-label') || '').trim());
    const scroller = [...d.querySelectorAll('*')].some((x) => x.scrollHeight > x.clientHeight + 2 && /(auto|scroll)/.test(getComputedStyle(x).overflowY));
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height), buttonsOutside: out, scrollable: scroller, taller: r.height > vh };
  });
  const popups = [...document.querySelectorAll('[role=menu],[role=listbox],[role=tooltip]')].filter(shown)
    .map((m) => ({ role: m.getAttribute('role'), outside: outside(m.getBoundingClientRect()) }));
  const chat = document.querySelector('[aria-label="메시지 입력"]');
  let chatInput = null;
  if (chat && shown(chat)) { const r = chat.getBoundingClientRect(); chatInput = { inView: r.top >= 0 && r.bottom <= vh, top: Math.round(r.top), bottom: Math.round(r.bottom) }; }
  return { dialogs, popups, chatInput, hOverflow: document.documentElement.scrollWidth > vw + 1, vw, vh };
}
"""

# 채팅 입력 칸에 초점을 준 뒤의 자리 — 390 × 500 은 가상 키보드가 열린 높이라 입력 칸을 누른 뒤에만 생긴다(계획 §3 W0a).
# 브라우저는 초점을 받은 칸을 화면 안으로 굴린다. 그래도 화면 밖이면(잘린 판 · 덮는 판) 진짜 결함이다.
# 초점 주기와 재기를 나눈다 — 이미 초점이 있는 칸에 다시 `focus()` 를 불러도 브라우저는 굴리지 않는다.
CHAT_FOCUS_JS = r"""
() => {
  window.scrollTo(0, 0);
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  const el = document.querySelector('[aria-label="메시지 입력"]');
  if (el) el.focus();
}
"""
CHAT_RECT_JS = r"""
() => {
  const el = document.querySelector('[aria-label="메시지 입력"]');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + Math.min(r.height / 2, 12);
  const inView = r.top >= 0 && r.bottom <= innerHeight && r.width > 0;
  const top = inView ? document.elementFromPoint(cx, cy) : null;
  const reachable = !!top && (top === el || el.contains(top) || top.contains(el));
  return { inView: inView && reachable, top: Math.round(r.top), bottom: Math.round(r.bottom), focused: document.activeElement === el };
}
"""

# 붙박이 판(fixed · sticky)이 조작 요소를 덮는가 — 맨 위와 맨 아래에서 잰다(새 티켓 · 메일 설정의 고정 저장 바).
COVER_JS = r"""
() => {
  const SEL = 'button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=checkbox], [role=switch], [role=combobox]';
  const pinned = (el) => { for (let n = el; n && n !== document.body; n = n.parentElement) { const p = getComputedStyle(n).position; if (p === 'fixed' || p === 'sticky') return n; } return null; };
  // 열린 모달이 있으면 그 안의 조작만 본다 — 모달 뒤가 막힌 것은 결함이 아니라 모달의 뜻이다.
  const shown = (m) => { const r = m.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(m).visibility !== 'hidden'; };
  const modals = [...document.querySelectorAll('[role=dialog][aria-modal=true], .MuiModal-root:not(.MuiModal-hidden)')].filter(shown);
  const scope = modals.length ? modals[modals.length - 1] : document;
  const scrollerOf = (el) => { for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const s = getComputedStyle(n); if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight + 1) return n; } return document.scrollingElement || document.documentElement; };
  const out = [];
  for (const el of scope.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (cx < 0 || cy < 0 || cx >= innerWidth || cy >= innerHeight) continue;
    const top = document.elementFromPoint(cx, cy);
    if (!top || el === top || el.contains(top) || top.contains(el)) continue;
    const pin = pinned(top);
    if (!pin || pin.contains(el)) continue;
    // 굴려서 드러낼 수 있으면 결함이 아니다 — 덮개가 위에 있으면 위로, 아래에 있으면 아래로 더 굴릴 수 있는가를 본다.
    // 끝까지 굴렸는데도 덮이는 것(고정 바가 본문 마지막 단추를 가림)만 남는다.
    const pr = pin.getBoundingClientRect();
    // 화면 높이의 60% 를 넘는 덮개는 고정 바가 아니라 옆 판(클로비 패널 같은 겹침 판)이다 — 판을 닫으면 드러난다. 판이 본문을
    // 밀어야 하는지는 PNG 판정이 맡는다(이 프로브는 고정 머리 · 발 · 저장 바만 본다).
    if (pr.height >= innerHeight * 0.6) continue;
    // 바가 화면 위쪽 절반에 있으면 머리 쪽 바다 — 위로 굴리면 드러난다. 아래쪽 절반이면 발 쪽 바다 — 아래로 굴리면 드러난다.
    // (덮인 요소와 바의 가운데를 견주면 둘이 크게 겹칠 때 위아래가 뒤집힌다 — 발 바가 마지막 줄을 반쯤 덮은 경우가 그랬다.)
    const above = (pr.top + pr.bottom) / 2 < innerHeight / 2;
    const sc = scrollerOf(el);
    // 굴릴 수 있는가는 가장 가까운 굴림 상자만이 아니라 조상 굴림 상자 전부(문서 포함)에서 본다 — 칸 안 굴림 상자(작업 보드의 칸)는
    // 맨 위인데 문서가 아래로 굴러 있어 첫 카드가 고정 머리 밑에 선 것을 「덮임」으로 셌다(r23 작업 보드 390, 위로 굴리면 드러난다).
    const scrollers = [];
    for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const st = getComputedStyle(n); if (/(auto|scroll)/.test(st.overflowY) && n.scrollHeight > n.clientHeight + 1) scrollers.push(n); }
    scrollers.push(document.scrollingElement || document.documentElement);
    const canUp = scrollers.some((x) => x.scrollTop > 0);
    const canDown = scrollers.some((x) => x.scrollTop + x.clientHeight < x.scrollHeight - 1);
    if ((above && canUp) || (!above && canDown)) continue;
    const rr = (x) => [Math.round(x.left), Math.round(x.top), Math.round(x.width), Math.round(x.height)];
    out.push({ name: (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 60), by: pin.tagName.toLowerCase() + (pin.className && typeof pin.className === 'string' ? '.' + pin.className.split(' ')[0] : ''),
               el: rr(r), pin: rr(pr), pos: getComputedStyle(pin).position, above,
               scroller: sc === (document.scrollingElement || document.documentElement) ? 'window' : (sc.tagName.toLowerCase() + (sc.getAttribute('data-scroll-root') !== null ? '[data-scroll-root]' : '')),
               scroll: [Math.round(sc.scrollTop), Math.round(sc.clientHeight), Math.round(sc.scrollHeight)] });
    if (out.length >= 20) break;
  }
  return out;
}
"""


def _empty_buckets(data):
    """홈 묶음 응답의 칸(`{count, items}`)을 모두 0 건으로 — 「티켓 0건」 홈."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if isinstance(value, dict) and "count" in value and "items" in value:
                out[key] = {**value, "count": 0, "items": []}
            else:
                out[key] = _empty_buckets(value)
        return out
    if isinstance(data, list):
        return [_empty_buckets(v) for v in data]
    return data


def _empty_trash_docs(data):
    """휴지통 「문서」 탭 0건 — 목록과 그 탭의 수를 함께 0 으로(탭 수와 목록이 어긋나지 않게)."""
    from scripts.ui_qa.state_capture import _empty_lists

    out = _empty_lists(data)
    counts = dict(out.get("counts") or {})
    if counts:
        counts["document"] = 0
        counts["all"] = int(counts.get("ticket") or 0)
        out["counts"] = counts
    return out


def _mail_relay(kind: str):
    """메일 · 로컬 릴레이(직접 전달) 상태(D-592) — 이 PC 에는 특권 헬퍼와 릴레이가 없어 고정 응답(`fixtures/relay_view.json`)으로
    세운다. 상태 응답의 릴레이 줄 · 준비 점검 요약 · 건강 · 요약을 고정 응답과 맞춘다 — 한 상태 면이 「켜지지 않았습니다」와
    「동작 중」을 함께 보이지 않게(P17V). 설정 GET 은 방식만 로컬 릴레이로 바꾼다(저장은 하지 않는다 — 다른 줄을 건드리지 않는다)."""
    from scripts.ui_qa.state_capture import _fixed, _rewrite

    fx = json.loads((ROOT / "scripts" / "ui_qa" / "fixtures" / "relay_view.json").read_text(encoding="utf-8"))
    if kind == "mail_relay_view":
        return _fixed(fx["view"])
    if kind == "mail_relay_settings":
        def settings(data):
            data = dict(data)
            data["settings"] = {**(data.get("settings") or {}), "mode": "local_relay", "relay": fx["config"]}
            return data
        return _rewrite(settings)
    readiness = fx["view"]["readiness"]
    brief = {"checked_at": readiness.get("checked_at"), "delivery": readiness.get("delivery"), "stale": False,
             "checks": [{"key": c["key"], "label": c["label"], "state": c["state"]} for c in readiness.get("checks") or []]}

    def status(data):
        data = dict(data)
        data["relay"] = {**fx["status_relay"], "readiness": brief}
        data["summary"] = {**(data.get("summary") or {}), "mode": "local_relay", "relay": fx["config"]}
        data["health"] = {**(data.get("health") or {}), "state": "ok", "label": "정상", "kind": "ok",
                          "message": "메일 발송을 사용할 수 있습니다.", "stage": None, "failure_kind": None, "stages": []}
        data["problems"] = []
        return data
    return _rewrite(status)


def _empty_meeting(data):
    """스프린트 회의 응답에서 담긴 티켓을 모두 비운다 — 집계 0, 번다운 · 건강 · 업무량 없음, 논의 묶음 0건, 범위 추적 없음."""
    out = dict(data)
    if isinstance(out.get("summary"), dict):
        out["summary"] = {k: (0 if isinstance(v, (int, float)) else v) for k, v in out["summary"].items()}
    out["burndown"] = None
    out["health"] = None
    out["workload"] = None
    out["tickets"] = []
    if isinstance(out.get("discuss"), dict):
        out["discuss"] = {k: ({**v, "items": [], "total": 0} if isinstance(v, dict) else v) for k, v in out["discuss"].items()}
    if isinstance(out.get("scope"), dict):
        out["scope"] = {**out["scope"], "tracked": False, "added": 0, "removed": 0}
    return out


def _handler(kind: str):
    """`routes` 의 종류 → Playwright 처리기. 실제 응답을 받아 값만 고친다(모양이 서버와 어긋나지 않는다)."""
    from scripts.ui_qa.state_capture import _empty_lists, _rewrite

    if kind == "empty_meeting":
        return _rewrite(_empty_meeting)
    if kind.startswith("mail_relay_"):
        return _mail_relay(kind)
    if kind == "empty":
        return _rewrite(_empty_lists)
    if kind == "empty_buckets":
        return _rewrite(_empty_buckets)
    if kind == "empty_calendar":
        # 달력 응답은 `items`(실행) 말고 `schedules`(일정 목록)가 빈 상태를 정한다 — 둘 다 비워야 「일정이 하나도 없다」가 선다.
        return _rewrite(lambda d: {**_empty_lists(d), "schedules": []} if isinstance(d, dict) else d)
    if kind == "empty_trash_docs":
        return _rewrite(_empty_trash_docs)
    status = {"error500": 500, "error403": 403, "error404": 404}.get(kind)
    if status is None:
        raise ValueError(f"모르는 응답 바꾸기: {kind}")
    body = json.dumps({"error": {"code": "r23_probe", "message": f"시험용 {status} 응답입니다."}}, ensure_ascii=False)

    def handler(route):
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(status=status, body=body, content_type="application/json")
    return handler


# ── 상태를 만드는 동작 ─────────────────────────────────────────────────────────
def _click(page, names, roles=("button", "menuitem", "link", "tab", "radio"), scope=None, timeout=5000) -> str:
    """이름 정규식 중 처음 맞는 조작 요소를 누른다. 누른 것의 이름을 돌려준다(못 찾으면 예외 — 그 줄은 「상태 못 만듦」)."""
    root = scope or page
    for name in names:
        for role in roles:
            loc = root.get_by_role(role, name=re.compile(name))
            if loc.count():
                target = loc.first
                target.scroll_into_view_if_needed(timeout=timeout)
                target.click(timeout=timeout)
                return f"{role}:{name}"
    raise RuntimeError("누를 조작 요소를 찾지 못했습니다: " + " | ".join(names))


def _dialog(page, timeout=6000) -> None:
    # 숨은 `role=dialog` 가 먼저 있으면 첫 일치가 그것이라 기다림이 헛돈다 — 보이는 것만 기다린다(P17 실측).
    page.locator("[role=dialog]:visible").first.wait_for(timeout=timeout)


def _open_delete(page) -> None:
    try:
        _click(page, [r"^삭제$", r"^휴지통으로", r"삭제$"])
    except RuntimeError:
        _click(page, [r"더 보기", r"^문서 작업$", r"작업 더 보기", r"동작"])
        _click(page, [r"삭제", r"휴지통"], roles=("menuitem",))
    _dialog(page)


def _row_edit(page) -> None:
    # 첫 줄이 묶음 머리일 수 있고(내 티켓은 프로젝트로 묶는다) 좁은 폭은 표가 아니라 카드다 — 본문의 첫 「수정」을 누른다.
    main = page.locator("main")
    main.get_by_role("button", name=re.compile(r"^(수정|편집)$")).first.wait_for(timeout=8000)
    _click(page, [r"^수정$", r"^편집$"], roles=("button",), scope=main)
    _dialog(page)


def _first_row(page) -> None:
    # 넓은 폭은 표의 첫 줄, 좁은 폭(카드 보기)은 누를 수 있는 첫 카드(`tabindex=0`)다.
    row = page.locator("table tbody tr, [data-table-cards] > .MuiPaper-root[tabindex='0'], "
                       "main .MuiStack-root > .MuiPaper-outlined[tabindex='0']").first
    row.wait_for(timeout=8000)
    row.click()
    _dialog(page)


def _submit_empty(page) -> None:
    _click(page, [r"^티켓 추가$", r"^추가$"])
    page.wait_for_timeout(400)


def _chat_search_none(page) -> None:
    # 좁은 폭은 첫 방을 바로 연다 — 방 목록은 「목록」 뒤에 있다.
    box = page.get_by_placeholder(re.compile("채팅방 검색")).first
    if not box.is_visible():
        _click(page, [r"^목록$"], roles=("button",))
    box.fill("zzzz-none-r23")
    page.wait_for_timeout(700)


def _login_wrong(page) -> None:
    page.fill("input[type=email], input[name=email]", "nobody-r23@goodmit.co.kr")
    page.fill("input[type=password]", "wrong-password-r23")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)


def _oss_notice(page) -> None:
    ACTIONS["user_menu"](page)
    _click(page, [r"오픈소스"], roles=("menuitem", "button", "link"))
    _dialog(page)


ACTIONS = {
    "submit_empty": _submit_empty,
    "open_edit": lambda p: (_click(p, [r"^수정$"]), _dialog(p)),
    "open_first_row": _first_row,
    "row_edit": _row_edit,
    "open_delete": _open_delete,
    "activity_mine": lambda p: _click(p, [r"^내가 한 일"], roles=("tab", "radio", "button")),
    "doc_new": lambda p: (_click(p, [r"^새 문서$", r"^문서 추가$", r"^추가$"]), _dialog(p)),
    "doc_categories": lambda p: (_click(p, [r"분류 관리"]), _dialog(p)),
    "project_add": lambda p: (_click(p, [r"^프로젝트 추가$", r"^새 프로젝트$", r"^추가$"]), _dialog(p)),
    "milestone_delete": lambda p: (_click(p, [r"^마일스톤 삭제"]), _dialog(p)),
    "chat_search_none": lambda p: _chat_search_none(p),
    "project_archive": lambda p: (_click(p, [r"^보관$"]), _dialog(p)),
    "milestone_add": lambda p: (_click(p, [r"^마일스톤 추가$"]), _dialog(p)),
    "board_write": lambda p: (_click(p, [r"^글쓰기$", r"^게시글 추가$", r"^새 글$", r"^추가$"]), _dialog(p)),
    "approval_confirm": lambda p: (_click(p, [r"^승인$"]), _dialog(p)),
    "chat_new_group": lambda p: (_click(p, [r"새 그룹", r"채팅방 추가", r"그룹 추가"]), _dialog(p)),
    "chat_manage": lambda p: (_click(p, [r"^관리$"]), _dialog(p)),
    "chat_leave": lambda p: (_click(p, [r"^나가기$"]), _dialog(p)),
    "game_add": lambda p: (_click(p, [r"^게임방 추가$"]), _dialog(p)),
    "user_add": lambda p: (_click(p, [r"^사용자 추가$", r"^추가$", r"초대"]), _dialog(p)),
    "registry_add": lambda p: (_click(p, [r"추가$"]), _dialog(p)),
    "clovi_panel": lambda p: (_click(p, [r"^클로비"]), p.wait_for_timeout(600)),
    # 종은 키보드로 연다 — r23 전 번들은 숫자 배지가 종 가운데를 덮어 마우스 누름을 삼켰다(조작 대장에 따로 적는다).
    "bell_open": lambda p: (p.locator("header button[aria-label^='알림']").first.focus(), p.keyboard.press("Enter"),
                            p.wait_for_timeout(600)),
    "palette_open": lambda p: (p.keyboard.press("Control+k"), _dialog(p)),
    # 머리 오른쪽 사용자 단추 — 접근 이름이 「{이름} 메뉴」다(`app/UserMenu.jsx`).
    "user_menu": lambda p: (p.locator("header button[aria-haspopup=menu][aria-label$=' 메뉴']").first.click(),
                            p.wait_for_timeout(400)),
    "oss_notice": _oss_notice,
    "login_wrong": _login_wrong,
}


# ── 자리 채우기 — 상세 화면의 id ─────────────────────────────────────────────────
def _first(payload, pred=None):
    seq = payload
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "rows", "posts", "rooms", "tickets", "documents", "conversations", "sprints"):
            if isinstance(payload.get(key), list):
                seq = payload[key]
                break
    if not isinstance(seq, list):
        return None
    for item in seq:
        if isinstance(item, dict) and item.get("id") not in (None, "") and (pred is None or pred(item)):
            return item
    return None


def discover(get) -> dict:
    """`get(path) -> json|None` 로 상세 화면의 id 를 찾는다. 못 찾은 자리는 비워 둔다(그 줄은 「상태 못 만듦」)."""
    ids: dict[str, str] = {}

    def take(key, *paths, pred=None, field="id"):
        for path in paths:
            item = _first(get(path), pred)
            if item:
                ids[key] = str(item.get(field))
                return item
        return None

    take("project", "/api/projects", pred=lambda r: not str(r.get("name", "")).startswith("[검증]"))
    take("project_empty", "/api/projects", pred=lambda r: str(r.get("name", "")).startswith("[검증] 빈 프로젝트"))
    take("ticket", "/api/tickets/mine?all_status=1", "/api/tickets/team?active=false")
    take("doc", "/api/knowledge/documents")
    take("post", "/api/board/posts?kind=free")
    take("idea", "/api/board/posts?kind=idea")
    # 관리 · 나가기가 있는 방(1:1 · 전체 채팅에는 없다).
    take("chatroom", "/api/team-chat/rooms", pred=lambda r: r.get("kind") != "direct" and not r.get("is_global"))
    take("conv", "/api/conversations")
    take("user", "/api/admin/users")
    take("dept", "/api/admin/departments")
    take("audit", "/api/admin/audit")
    # 데이터가 선 회의를 찍으려면 **열린 회차**다(목록의 첫 회차는 다음 회차일 수 있다 — 예정 회차는 빈 판만 선다).
    sprint = take("sprint", "/api/work/sprints", pred=lambda r: bool(r.get("active"))) or take("sprint", "/api/work/sprints")
    if sprint and sprint.get("department_id"):
        ids["sprint_q"] = f"team={sprint['department_id']}&sprint={sprint['id']}"
    # 스프린트 회의의 두 빈 얼굴 — 회차는 있는데 열린 회차가 없는 팀(「회의할 회차를 고르세요.」, 열린 회차가 있으면 화면이
    # 그것을 스스로 고른다)과 회차가 하나도 없는 팀(「아직 만든 회차가 없습니다.」). 없는 회차 id 를 넣으면 404 화면이 된다.
    env = get("/api/work/sprints") or {}
    for opt in ((env.get("team") or {}).get("options") or []):
        tid = opt.get("id")
        if not tid:
            continue
        rows = (get(f"/api/work/sprints?department_id={tid}") or {}).get("sprints") or []
        if rows and not any(r.get("active") for r in rows):
            ids.setdefault("sprint_idle_q", f"team={tid}")
        if not rows:
            ids.setdefault("sprint_none_q", f"team={tid}")
    return ids


def fill(path: str, ids: dict) -> str | None:
    missing = [k for k in re.findall(r"\{(\w+)\}", path) if k not in ids]
    if missing:
        return None
    return re.sub(r"\{(\w+)\}", lambda m: ids[m.group(1)], path)


def _url(base: str, case: Case, path: str) -> str:
    if case.console == "public":
        return base.rstrip("/") + path
    shell = "/admin" if case.console == "admin" else "/"
    return f"{base.rstrip('/')}{shell}#{path}"


class Ledger:
    """줄마다 · 폭마다 찍고 잰다."""

    def __init__(self, browser, base: str, label: str, accounts: dict, profile: str, *, probes: bool, insecure: bool, lab: bool):
        self.browser, self.base, self.label = browser, base, label
        self.accounts = accounts            # role → (storage_state, user_id)
        self.views = PROFILES[profile]
        self.profile, self.probes, self.insecure, self.lab = profile, probes, insecure, lab
        self.out = OUT_BASE / label
        self.out.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict] = []
        self.merge = False                  # `--ids` 실행이면 기존 대장에 줄을 합친다(`write`)
        self.measure: dict[str, dict] = {}
        self._probe_js = None
        if probes:
            from scripts.ui_qa.composition_checks import COMPOSITION_CONTRACT, COMPOSITION_JS, expect_for
            from scripts.ui_qa.kit_measure import MEASURE_JS, _mascot_hfrac, contract_for
            from scripts.ui_qa.visual_probes import VISUAL_CONTRACT, VISUAL_JS
            self._probe_js = (MEASURE_JS, contract_for, _mascot_hfrac(), COMPOSITION_JS, COMPOSITION_CONTRACT, expect_for,
                              VISUAL_JS, VISUAL_CONTRACT)

    def run_case(self, case: Case, ids: dict) -> dict:
        row = {"id": case.id, "name": case.name, "role": case.role or "public", "path": case.path, "note": case.note, "views": []}
        path = fill(case.path, ids)
        if path is None:
            row["status"] = "state-missing"
            row["reason"] = "상세 id 를 찾지 못했습니다(씨앗에 그 자료가 없습니다)."
            self.rows.append(row)
            print(f"[ledger] {case.id:<9} 상태 못 만듦 — id 없음", flush=True)
            return row
        if self.lab and case.mutates:
            row["status"] = "skipped-lab"
            self.rows.append(row)
            return row
        if case.role and case.role not in self.accounts:
            row["status"] = "state-missing"
            row["reason"] = f"{case.role} 계정이 없습니다."
            self.rows.append(row)
            return row
        texts: dict[str, dict] = {}
        for theme, vp in self.views:
            view = self._shoot(case, path, theme, vp, texts)
            row["views"].append(view)
        oks = [v for v in row["views"] if v["state"] == "ok"]
        row["status"] = "ok" if len(oks) == len(row["views"]) else ("partial" if oks else "state-missing")
        row["text"] = sorted(texts.values(), key=lambda t: t["text"])
        self.rows.append(row)
        print(f"[ledger] {case.id:<9} {row['status']:<13} {case.name}", flush=True)
        return row

    def _shoot(self, case: Case, path: str, theme: str, vp: Viewport, texts: dict) -> dict:
        storage, user_id = self.accounts.get(case.role, (None, "")) if case.role else (None, "")
        view = {"theme": theme, "viewport": vp.name, "state": "error", "console": [], "png": ""}
        ctx = new_context(self.browser, storage_state=storage, user_id=user_id, theme=theme, viewport=vp, insecure=self.insecure)
        page = ctx.new_page()
        page.on("console", lambda m: view["console"].append(m.text[:300]) if m.type == "error" else None)
        page.on("pageerror", lambda e: view["console"].append(("pageerror: " + str(e))[:300]))
        try:
            for pattern, kind in case.routes:
                page.route(pattern, _handler(kind))
            page.goto(_url(self.base, case, path), wait_until="domcontentloaded", timeout=45000)
            page.locator("main, form, body").first.wait_for(timeout=20000)
            page.wait_for_timeout(900)
            if case.act:
                ACTIONS[case.act](page)
                page.wait_for_timeout(500)
            try:
                page.locator(case.check).filter(visible=True).first.wait_for(state="visible", timeout=9000)
                view["state"] = "ok"
            except Exception:  # noqa: BLE001 — 상태가 안 섰다: 찍되 통과로 세지 않는다
                view["state"] = "state-missing"
            page.mouse.move(0, 0)
            folder = self.out / theme / vp.name
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{case.id}.png"
            page.screenshot(path=str(folder / name), full_page=True)
            view["png"] = f"{theme}/{vp.name}/{name}"
            for t in page.evaluate(TEXT_JS):
                entry = texts.setdefault(t["kind"] + "|" + t["text"], {**t, "views": []})
                entry["views"].append(f"{theme}/{vp.name}")
            view["controls"] = page.evaluate(CONTROLS_JS)
            view["overlap"] = page.evaluate(OVERLAP_JS)
            view["cover_top"] = page.evaluate(COVER_JS)
            page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); document.querySelectorAll('main, [data-scroll-root]').forEach(e => { e.scrollTop = e.scrollHeight; }); }")
            page.wait_for_timeout(250)
            view["cover_bottom"] = page.evaluate(COVER_JS)
            if vp.name == "390x500" and (view["overlap"] or {}).get("chatInput"):
                page.evaluate(CHAT_FOCUS_JS)
                page.wait_for_timeout(300)   # 굴림이 끝난 뒤 잰다
                view["overlap"]["chatInputFocused"] = page.evaluate(CHAT_RECT_JS)
            if self._probe_js and theme == "light":
                self._run_probes(page, case, vp)
        except Exception as exc:  # noqa: BLE001 — 한 줄이 실패해도 나머지를 찍는다
            view["state"] = "state-missing"
            view["error"] = str(exc).splitlines()[0][:300]
            try:
                folder = self.out / theme / vp.name
                folder.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(folder / f"FAILED-{case.id}.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
        return view

    def _run_probes(self, page, case: Case, vp: Viewport) -> None:
        measure_js, contract_for, hfrac, comp_js, comp_contract, expect_for, visual_js, visual_contract = self._probe_js
        contract = contract_for(page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize) || 16"))
        result = page.evaluate(measure_js, {**contract, "scope": None, "mascotHfrac": hfrac})
        composed = page.evaluate(comp_js, {**comp_contract, "scope": None, "expect": expect_for(case.id)})
        if isinstance(composed, dict) and not composed.get("error"):
            result.update(composed)
        looked = page.evaluate(visual_js, {**visual_contract, "scope": None})
        if isinstance(looked, dict) and not looked.get("error"):
            result.update(looked)
        self.measure[f"{case.id}__light__{vp.name}"] = result

    def write(self) -> Path:
        summary = {
            "label": self.label, "base": self.base, "profile": self.profile, "lab": self.lab,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": {k: sum(1 for r in self.rows if r.get("status") == k)
                       for k in ("ok", "partial", "state-missing", "skipped-lab")},
            "rows": self.rows,
        }
        path = self.out / "ledger.json"
        # `--ids` 로 몇 줄만 다시 찍으면 같은 대장의 그 줄만 바꾼다 — 나머지 줄을 지우지 않는다(줄 순서는 표 순서).
        if self.merge and path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("profile") == self.profile:
                order = [c.id for c in C69 + CEX]
                by_id = {r["id"]: r for r in old.get("rows", [])}
                by_id.update({r["id"]: r for r in self.rows})
                rows = sorted(by_id.values(), key=lambda r: order.index(r["id"]) if r["id"] in order else len(order))
                summary["rows"] = rows
                summary["counts"] = {k: sum(1 for r in rows if r.get("status") == k)
                                     for k in ("ok", "partial", "state-missing", "skipped-lab")}
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        if self.measure:
            mdir = OUT_BASE / f"{self.label}-measure"
            mdir.mkdir(parents=True, exist_ok=True)
            mpath = mdir / "measure.json"
            pages = dict(self.measure)
            if self.merge and mpath.exists():
                pages = {**json.loads(mpath.read_text(encoding="utf-8")).get("pages", {}), **pages}
            mpath.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")
        return path


# ── 로그인 · 로컬 서버 ─────────────────────────────────────────────────────────
def login(browser, base: str, email: str, password: str, insecure: bool) -> tuple[dict, str]:
    ctx = browser.new_context(ignore_https_errors=insecure)
    try:
        res = ctx.request.post(base.rstrip("/") + "/login", data={"email": email, "password": password})
        if res.status != 200:
            raise RuntimeError(f"로그인 실패({email}): HTTP {res.status}")
        me = ctx.request.get(base.rstrip("/") + "/api/me")
        user_id = ""
        if me.ok:
            body = me.json()
            user_id = str((body.get("user") or body).get("id") or "") if isinstance(body, dict) else ""
        # 첫 방문 둘러보기 창이 홈을 덮지 않게 — 실제 사용자의 「둘러보기 끝냄」과 같은 상태로 둔다(`auth._dismiss_tour`).
        from scripts.ui_qa.auth import _dismiss_tour
        _dismiss_tour(ctx, base, print)
        return ctx.storage_state(), user_id
    finally:
        ctx.close()


def _select(ids: list[str]) -> list[Case]:
    if not ids:
        return list(CASES)
    picked = []
    for case in CASES:
        if any(case.id == x or case.id.startswith(x + "-") or (x.startswith("EX") and case.id.startswith(x)) for x in ids):
            picked.append(case)
    return picked


def _run_cases(browser, base, args, accounts, get) -> int:
    ledger = Ledger(browser, base, args.label, accounts, args.profile, probes=args.probes, insecure=args.insecure,
                    lab=bool(args.base_url))
    ledger.merge = bool(args.ids)
    ids = discover(get)
    print(f"[ledger] 찾은 id: {sorted(ids)}", flush=True)
    for case in _select(args.ids):
        ledger.run_case(case, ids)
    path = ledger.write()
    counts = json.loads(path.read_text(encoding="utf-8"))["counts"]
    print(f"SCREEN_LEDGER_DONE {counts} → {path}")
    return 0


def run_local(args) -> int:
    import httpx
    from playwright.sync_api import sync_playwright

    from app.core.clock import SystemClock
    from app.jobs.worker import Worker
    from app.worker_main import _bootstrap, build_handlers
    from scripts.ui_qa import local_server as ls
    from scripts.ui_qa.mail_sink import MailSink

    import logging

    # 접근 기록(줄마다 정적 자산 수십 줄)이 진행 줄을 덮는다 — 경고 이상만 남긴다.
    logging.getLogger("app.access").setLevel(logging.WARNING)
    workdir = Path(tempfile.mkdtemp(prefix="clovir-ledger-"))
    sink = MailSink(workdir / "inbox").start()
    url = ls.create_database()
    stop = threading.Event()
    server = None
    try:
        port = ls._free_port()
        base = f"http://127.0.0.1:{port}"
        settings = ls.build_settings(url, workdir).model_copy(update={"app_base_url": base})
        ls.seed(url, EMAIL, PASSWORD, settings)
        server, _ = ls.serve(settings, port)
        session_factory, wctx, _cache, _out = _bootstrap(settings, SystemClock())
        worker = Worker(session_factory, SystemClock(), build_handlers(), wctx, exclude_types=("chat_message",))

        def loop() -> None:
            while not stop.is_set():
                try:
                    if not worker.run_once():
                        time.sleep(0.2)
                except Exception as exc:  # noqa: BLE001
                    print("worker error:", exc)
                    time.sleep(0.5)

        threading.Thread(target=loop, daemon=True).start()
        api = httpx.Client(base_url=base, timeout=30)
        csrf = {"X-CSRF-Token": api.post("/login", json={"email": EMAIL, "password": PASSWORD}).json()["csrf_token"]}
        # 메일 화면에 실제 값이 서게 — 로컬 받는 쪽으로 외부 SMTP 를 맞추고 시험 메일 셋을 보낸다(임시 DB 라 지워진다).
        api.put("/api/admin/mail/settings", headers=csrf, json={
            "enabled": True, "host": "127.0.0.1", "port": sink.port, "security": "none", "from_address": "noreply@goodmit.co.kr",
            "from_name": "ClovirAssist", "username": "", "timeout_seconds": 10, "tls_verify": True, "ca_pem": "", "mode": "external"})
        for i in range(3):
            api.post("/api/admin/mail/test", json={"to": f"ledger-{i}@example.com"}, headers=csrf)
        # 티켓 · 마일스톤 · 문서가 하나도 없는 프로젝트(WBS 0건 같은 빈 탭을 응답 바꾸기 없이 찍는다).
        api.post("/api/projects", json={"name": "[검증] 빈 프로젝트"}, headers=csrf)
        time.sleep(3)

        def get(path):
            res = api.get(path)
            return res.json() if res.status_code == 200 else None

        with sync_playwright() as p:
            browser = p.chromium.launch()
            accounts = {role: login(browser, base, email, PASSWORD, False) for role, email in ROLE_ACCOUNTS.items()}
            code = _run_cases(browser, base, args, accounts, get)
            browser.close()
        return code
    finally:
        stop.set()
        if server is not None:
            server.should_exit = True
        sink.stop()
        ls.drop_database()


def run_remote(args) -> int:
    """랩 읽기 전용 — 자격은 `UI_QA_EMAIL` · `UI_QA_PASSWORD`(파이썬 래퍼가 `dist/ops/user.env` 에서 넣는다)."""
    from playwright.sync_api import sync_playwright

    email, password = os.environ.get("UI_QA_EMAIL", ""), os.environ.get("UI_QA_PASSWORD", "")
    if not email or not password:
        print("UI_QA_EMAIL · UI_QA_PASSWORD 가 없습니다.", file=sys.stderr)
        return 2
    with sync_playwright() as p:
        browser = p.chromium.launch()
        accounts = {"system_admin": login(browser, args.base_url, email, password, args.insecure)}
        ctx = browser.new_context(ignore_https_errors=args.insecure, storage_state=accounts["system_admin"][0])

        def get(path):
            res = ctx.request.get(args.base_url.rstrip("/") + path)
            return res.json() if res.ok else None

        code = _run_cases(browser, args.base_url, args, accounts, get)
        ctx.close()
        browser.close()
    return code


# ── 자기 시험 — 재는 것이 맞는 견본에서 조용하고 틀린 견본에서 잡는가 ───────────────────
_GOOD = """<!doctype html><html><body style="margin:0;font-family:sans-serif">
<main><h1>홈</h1><p>검색 결과 <b>3</b>건</p><button>저장</button><input aria-label="검색어" placeholder="제목 검색"></main></body></html>"""
_BAD = """<!doctype html><html><body style="margin:0;font-family:sans-serif;height:2000px">
<main><p>본문</p><div style="cursor:pointer">눌러 보세요</div>
<span aria-label="저장할 변경이 없습니다"><button disabled>저장</button></span>
<button style="position:absolute;top:1960px;left:400px">마지막 단추</button></main>
<div style="position:fixed;bottom:0;left:0;right:0;height:80px;background:#eee">고정 저장 바</div>
<div role="dialog" style="position:fixed;top:20px;left:20px;width:300px;height:900px;background:#fff">
  <p>긴 창</p><button style="position:absolute;bottom:10px">확인</button></div>
</body></html>"""


# 채팅 입력 칸 — 첫 화면 아래(초점을 주면 굴러 들어온다) · 끝까지 굴려도 붙박이 바가 덮는다(진짜 결함).
_CHAT_BELOW = """<body style="margin:0"><div style="height:700px">대화</div><textarea aria-label="메시지 입력"></textarea></body>"""
_CHAT_CLIPPED = """<body style="margin:0"><div style="height:700px">대화</div><textarea aria-label="메시지 입력"></textarea>
<footer style="position:fixed;left:0;right:0;bottom:0;height:120px;background:#223;z-index:5">바</footer></body>"""
# 굴리면 드러나는 덮임(고정 머리 아래로 지나간 줄)은 결함이 아니다 — 맞는 견본.
_SCROLLED = """<body style="margin:0"><header style="position:sticky;top:0;height:60px;background:#223;z-index:5">머리</header>
<main>""" + "".join(f'<p style="height:40px;margin:0"><button>줄 {i}</button></p>' for i in range(60)) + """</main></body>"""
# 모달 뒤의 조작은 일부러 막혀 있다 — 맞는 견본.
_MODAL = """<body><main><button>뒤 단추 하나</button><button>뒤 단추 둘</button></main>
<div role="dialog" aria-modal="true" style="position:fixed;inset:0;background:rgba(0,0,0,.4)">
<div style="margin:100px auto;width:300px;background:#fff"><button>확인</button></div></div></body>"""
# 카드 보기 목록(390)과, 이름 칸 없는 판(목록이 아님).
_CARDS = """<main><div class="MuiStack-root"><div class="MuiPaper-root MuiPaper-outlined">
<span class="MuiTypography-root MuiTypography-caption">제목</span><span>업무 01</span></div></div></main>"""
_NOT_CARDS = """<main><div class="MuiStack-root"><div class="MuiPaper-root MuiPaper-outlined"><span>안내</span></div></div></main>"""


def self_test() -> int:
    from playwright.sync_api import sync_playwright

    fails: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        page.set_content(_GOOD)
        texts = {t["text"] for t in page.evaluate(TEXT_JS)}
        if "검색 결과 3건" not in texts:
            fails.append("TEXT_JS: 숫자가 끼인 문장을 한 줄로 못 이었다")
        if "제목 검색" not in texts or "검색어" not in texts:
            fails.append("TEXT_JS: placeholder · aria-label 을 못 모았다")
        good = page.evaluate(CONTROLS_JS)
        if good["fakes"] or any(i["covered"] for i in good["items"]):
            fails.append(f"CONTROLS_JS: 맞는 견본에서 거짓 경보 {good}")
        if page.evaluate(COVER_JS) or page.evaluate(OVERLAP_JS)["dialogs"]:
            fails.append("COVER/OVERLAP: 맞는 견본에서 거짓 경보")
        page.set_content(_BAD)
        bad = page.evaluate(CONTROLS_JS)
        if not bad["fakes"]:
            fails.append("CONTROLS_JS: 누르는 모양의 가짜 조작 요소를 못 잡았다")
        dis = [i for i in bad["items"] if i["disabled"]]
        if not dis or not dis[0]["reason"]:
            fails.append("CONTROLS_JS: 비활성 단추의 까닭을 못 읽었다")
        # 진짜 결함은 «끝까지 굴려도» 고정 바가 문서의 마지막 단추를 덮는 것이다(바 높이만큼 아래 여백이 없다).
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        if not page.evaluate(COVER_JS):
            fails.append("COVER_JS: 끝까지 굴려도 고정 바가 덮는 마지막 단추를 못 잡았다")
        ov = page.evaluate(OVERLAP_JS)
        if not ov["dialogs"] or not ov["dialogs"][0]["buttonsOutside"]:
            fails.append("OVERLAP_JS: 화면 밖 확인 단추를 못 잡았다")
        page.set_content(_SCROLLED)
        page.evaluate("() => window.scrollTo(0, 400)")
        if page.evaluate(COVER_JS):
            fails.append("COVER_JS: 위로 굴리면 드러나는 줄을 덮임으로 셌다")
        page.set_content(_MODAL)
        if page.evaluate(COVER_JS):
            fails.append("COVER_JS: 모달 뒤의 단추를 덮임으로 셌다")
        page.set_viewport_size({"width": 390, "height": 500})
        page.set_content(_CHAT_BELOW)
        page.evaluate(CHAT_FOCUS_JS)
        page.wait_for_timeout(100)
        got = page.evaluate(CHAT_RECT_JS)
        if not (got and got["inView"] and got["focused"]):
            fails.append(f"CHAT_FOCUS_JS: 초점을 주면 굴러 들어오는 입력 칸을 화면 밖으로 셌다 {got}")
        page.set_content(_CHAT_CLIPPED)
        page.evaluate(CHAT_FOCUS_JS)
        page.wait_for_timeout(100)
        got = page.evaluate(CHAT_RECT_JS)
        if not got or got["inView"]:
            fails.append(f"CHAT_FOCUS_JS: 붙박이 바가 덮는 입력 칸을 화면 안으로 셌다 {got}")
        page.set_viewport_size({"width": 800, "height": 600})
        page.set_content(_CARDS)
        if not page.locator(LIST).count():
            fails.append("LIST: 카드 보기 목록을 못 알아봤다")
        page.set_content(_NOT_CARDS)
        if page.locator(LIST).count():
            fails.append("LIST: 이름 칸 없는 판을 목록으로 셌다")
        browser.close()
    for f in fails:
        print("  -", f)
    print("SCREEN_LEDGER_SELFTEST_" + ("OK" if not fails else "FAIL"))
    return 0 if not fails else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="화면 · 상태 대장(r23)")
    ap.add_argument("--label", default="r23-ledger")
    ap.add_argument("--profile", default="text", choices=sorted(PROFILES))
    ap.add_argument("--ids", nargs="*", default=[], help="화면 번호(01 · 61 · EX-T …) — 비우면 전부")
    ap.add_argument("--probes", action="store_true", help="kit_measure · 조합 · 시각 규율 프로브도 돈다(밝음만)")
    ap.add_argument("--base-url", default="", help="랩 읽기 전용 — 비우면 로컬 임시 서버")
    ap.add_argument("--insecure", action="store_true", help="자체 서명 인증서를 받는다(랩)")
    ap.add_argument("--ai-ready", action="store_true",
                    help="AI 를 켜고 답한 대화를 심은 씨앗(`UI_QA_AI_READY=1`) — AI 도우미 대화 줄(EX-C6 · C7)은 이것이 있어야 선다")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--list", action="store_true", help="줄 목록만 찍는다")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.list:
        for case in _select(args.ids):
            print(f"{case.id:<9} {case.role or 'public':<12} {case.console:<6} {case.path:<55} {case.name}")
        print(f"{len(_select(args.ids))}줄")
        return 0
    if args.ai_ready:
        os.environ["UI_QA_AI_READY"] = "1"
    return run_remote(args) if args.base_url else run_local(args)


if __name__ == "__main__":
    raise SystemExit(main())
