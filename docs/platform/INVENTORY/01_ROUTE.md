# INVENTORY 01 — Route

**정본**: `docs/ui-renewal/ROUTE_COVERAGE.json` · 실제 Router Source (`frontend/src/**`)
**측정**: 2026-08-21 (`check_ui_renewal_coverage.py --stage plan` 출력)

## 측정

| 항목 | 값 |
|---|---|
| Surface 총계 (route/tab/widget/alias) | **93** |
| 그중 검증 대상 (route/tab/widget) | **89** — Functional Coverage 가 89개를 전부 담고 있다 |
| Wave 축 | 17 (`W0`~`W5` · `W5B` · `W6`~`W15`) — **W5B 이후는 동결** (D-207) |
| Router 형태 | React 18 + **HashRouter** |
| UI 요구사항 | 161건 (`REQUIREMENT_MATRIX.md`, 누락 0 · 기대 밖 0) |

## Route 집합이 바뀐다 — 이 목록은 곧 낡는다

이번 전환은 **Route 집합 자체를 바꾼다**. `MASTER_PLAN.md` §14.1 의 목표 IA 가 기준이고,
§14.2 의 「재작성 / 신설 / 유지」가 어느 Route 가 사라지고 생기는지를 지목한다.

| 사라지는 Route | 이유 |
|---|---|
| `/notion-mapping` · NotionConsole | Notion Runtime 소멸 |
| `/backup` `/restore-drills` 의 SQLite 모양 | PG Backup 으로 재작성 |
| `/sprint` 의 현재 형태 | 마감일 집계였다. 진짜 Sprint 엔티티로 교체 |
| 모든 `MirrorNotice` 소비처 (동기화 배너·"지금 동기화" 6곳) | **동기화 개념 자체가 사라진다** |

| 신설 Route (지금 0%) |
|---|
| Kanban Board · Backlog · Sprint · Knowledge Space · Folder 트리 · Ticket Relation UI · Project Member 관리 · AI 작업공간 |

## 미확인 항목과 Owner

| 미확인 | Owner | 내용 |
|---|---|---|
| ~~`read_jsx_routes()` 가 빈 결과에 FATAL 인가~~ | ~~S1~~ | **완료 (2026-08-21).** `SourceReadError` + `SOURCE_FLOOR`. 모든 `<Route` 를 리터럴·계산·index 로 분류하고 **미분류가 있으면 FATAL**. 실측 표본: User 28 · Admin 21(리다이렉트 4) |
| 새 IA 의 Route 집합 | **S18~S20** | Route 가 실제로 바뀔 때 Coverage 를 갱신한다. **지금 미리 열거하지 않는다.** 그때 `SOURCE_FLOOR` 도 함께 내린다 — 그 판단을 사람이 한 번 하게 만드는 것이 그 상수의 목적이다 |

## 주의

**Route 개편은 Coverage Gate 를 무력화할 수 있었다.** Gate 가 초록인 것과 Route 가 빠짐없이
검사된 것은 다른 말이다. **S1 이 그 경로를 막았고**(R4), 이제 Gate 는 대조 **전에** 표본 수를
먼저 찍는다: 「소스 리더 표본 — User Route 28 · Admin Route 21(리다이렉트 4) · TAB_GROUPS
5그릇/10탭 · 설정 탭 4 · 하네스 Route 84(별칭 4)」. 그 줄이 없으면 그 실행의 C1 결과는 없다.
