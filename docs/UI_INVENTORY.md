# UI INVENTORY — 전면 리뉴얼 착수 전 전수 조사 (지시 52)

> 소스에서 기계적으로 파생했다. 판단이 들어간 열은 Page Archetype 하나뿐이다.
> 기존 문서의 PASS 기록을 제외 사유로 쓰지 않는다 — 여기 있는 Route는 전부 이번 대상이다.

**규모**: Route 72개 · 비테스트 화면 파일 102개

---

## 1. 공용 컴포넌트 영향 반경

한 곳을 고치면 몇 개 파일이 함께 바뀌는가. 리뉴얼의 지렛대 순서다.

| 공용 export | 사용 파일 수 | 비고 |
|---|---:|---|
| `Button` | 61 |  |
| `Skeleton` | 57 |  |
| `Card` | 55 | 현재의 기본 컨테이너. 지시 2·4의 '흰 카드 반복' |
| `ErrorState` | 54 |  |
| `EmptyState` | 41 |  |
| `Badge` | 41 |  |
| `PageHeader` | 39 | 화면 파일 102개 중 39개만 쓴다 — 지시 3의 '어떤 페이지엔 있고 어떤 페이지엔 없다'가 여기서 나온다 |
| `Callout` | 35 | 큰 외곽선 Box. 지시 35가 지목한 그 컴포넌트 |
| `DataTable` | 17 | 지시 10. 정렬·페이지네이션 내장 없음 |
| `Modal` | 15 |  |
| `StatCard` | 13 | KPI 흰 상자. 지시 2 |
| `SectionTitle` | 6 |  |
| `Pager` | 6 | 페이지네이션이 DataTable 밖에 따로 있다(지시 10) |
| `BarSeries` | 6 |  |
| `FormModal` | 5 |  |
| `SearchBox` | 5 | 5개 파일만(지시 5) |
| `useRowSelection` | 5 |  |
| `MascotPose` | 5 | 사용자 확정 보존 대상(계획 §1.5.1) |
| `FilterBarGrid` | 4 | 검색·필터 공통 grid — 4개 파일만 쓴다. 나머지는 제각각(지시 5) |
| `BASELINE_TRACKS` | 4 | 목업 파생 grid 트랙. 계획 §1.6 폐기 대상과 연결 |
| `Donut` | 3 |  |
| `BodyEditor` | 2 |  |
| `EditableBody` | 2 |  |
| `LineSeries` | 2 |  |
| `FilterSelect` | 1 | 1개 파일만 |
| `SavedViews` | 1 | 1개 파일만 |
| `Sparkline` | 1 |  |

---

## 2. Route Inventory

| Route | 콘솔 | 화면 파일 | 최소 권한 | Page Archetype |
|---|---|---|---|---|
| `/me` | user | `screens/Home.jsx` | user | Dashboard |
| `/my-tickets` | user | `screens/MyTickets.jsx` | user | List |
| `/unassigned` | user | `screens/MyTickets.jsx` | user | List |
| `/new-ticket` | user | `screens/MyTickets.jsx` | user | Form |
| `/tickets/:id` | user | `screens/Ticket.jsx` | user | Detail |
| `/team-tickets` | user | `screens/TeamTickets.jsx` | user | List |
| `/projects` | user | `screens/Projects.jsx` | user | List |
| `/projects/:id` | user | `screens/Project.jsx` | user | Detail(복합·탭 5) |
| `/sprint` | user | `screens/Sprint.jsx` | user | Workflow |
| `/chat` | user | `screens/Chat.jsx` | user | Console(대화) |
| `/chat-rooms` | user | `screens/ChatRooms.jsx` | user | List+Detail |
| `/chat-rooms/:id` | user | `screens/ChatRooms.jsx` | user | Console(대화) |
| `/board` | user | `screens/Board.jsx` | user | List |
| `/ideas` | user | `screens/Board.jsx` | user | List |
| `/board/:id` | user | `screens/BoardPost.jsx` | user | Detail |
| `/team-docs` | user | `screens/TeamDocs.jsx` | user | List |
| `/team-docs/trash` | user | `screens/Trash.jsx` | user | List |
| `/team-docs/:id` | user | `screens/TeamDoc.jsx` | user | Detail |
| `/games` | user | `screens/Games.jsx` | user | List |
| `/games/:id` | user | `screens/GameRoom.jsx` | user | Console(실시간) |
| `/notifications` | user | `screens/DataScreen.jsx` | user | List(registry) |
| `/my-approvals` | user | `screens/MyApprovals.jsx` | user | List |
| `/profile` | user | `screens/Profile.jsx` | user | Settings |
| `/my-stats` | user | `screens/MyStats.jsx` | user | Report |
| `/activity` | user | `screens/Activity.jsx` | user | List(피드) |
| `/my-display` | user | `screens/DisplaySettings.jsx` | user | Settings |
| `/search` | both | `screens/Search.jsx` | user | Result |
| `/dashboard` | admin | `screens/Dashboard.jsx` | (라우트 게이트 없음) | Dashboard |
| `/integrity` | admin | `screens/Integrity.jsx` | operator+ | Console(진단) |
| `/users` | admin | `screens/Users.jsx` | admin+ | List |
| `/users/:id` | admin | `screens/Users.jsx` | admin+ | Detail(Modal) |
| `/offboarding` | admin | `screens/Offboarding.jsx` | admin+ | Workflow |
| `/settings` | admin | `screens/settings/SettingsShell.jsx` | (탭별) | Settings(탭 4) |
| `/setup` | admin | `screens/SetupWizard.jsx` | system_admin | Workflow |
| `/mail` | admin | `screens/MailStatus.jsx` | operator+ | Console(운영) |
| `/diagnostics` | admin | `screens/ops/Diagnostics.jsx` | operator+ | Console(진단) |
| `/dev-report` | admin | `screens/DevReport.jsx` | admin/auditor | Report |
| `/scheduler-calendar` | admin | `screens/SchedulerCalendar.jsx` | operator+ | Report(달력) |
| `/org-tree` | admin | `screens/OrgConsole.jsx` | admin+ | Console(트리) |
| `/organizations` | admin | `screens/OrgConsole.jsx` | admin+ | Console(트리) |
| `/departments` | admin | `screens/OrgConsole.jsx` | admin+ | Console(트리) |
| `/departments/:id` | admin | `screens/OrgConsole.jsx` | admin+ | Console(트리) |
| `/system -> /settings?tab=os` | admin | `(redirect)` | - | Redirect |
| `/notion-console -> /settings?tab=integration` | admin | `(redirect)` | - | Redirect |
| `/llm-console -> /settings?tab=ai` | admin | `(redirect)` | - | Redirect |
| `/maintenance -> /settings?tab=policy` | admin | `(redirect)` | - | Redirect |
| `/integrations` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/runners` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/workflows` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/prompts` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/policies` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/templates` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/prompt-usage` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/policy-usage` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/schedules` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/documents` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/jobs` | admin | `screens/DataScreen.jsx` + `registry/*` | operator/admin | List(registry) |
| `/job-titles` | admin | `screens/DataScreen.jsx` + `registry/*` | admin+ | List(registry) |
| `/notion-mapping` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/approvals` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/approval-delegations` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/audit` | admin | `screens/DataScreen.jsx` + `registry/*` | admin/auditor | List(registry) |
| `/audit/:id` | admin | `screens/DataScreen.jsx` + `registry/*` | admin/auditor | List(registry) |
| `/audit-anomalies` | admin | `screens/DataScreen.jsx` + `registry/*` | admin/auditor | List(registry) |
| `/rbac` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/impersonation` | admin | `screens/DataScreen.jsx` + `registry/*` | admin/auditor | List(registry) |
| `/backup` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/restore-drills` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/announcements` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/ai-quotas` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/feature-flags` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |
| `/admin-notifications` | admin | `screens/DataScreen.jsx` + `registry/*` | operator+ | List(registry) |

---

## 3. 화면별 공용 컴포넌트 사용

| 화면 파일 | 줄 | 사용 중인 공용 컴포넌트 |
|---|---:|---|
| `app/AdminRoutes.jsx` | 215 | Card, EmptyState, ErrorState, Skeleton, Button |
| `app/App.jsx` | 132 | Card, Skeleton |
| `app/AppShell.jsx` | 859 | Card, ErrorState, Skeleton, Button |
| `app/AssistantDrawer.jsx` | 321 | Skeleton, Button, MascotPose |
| `app/Banners.jsx` | 116 | Button |
| `app/CommandPalette.jsx` | 275 | **(공용 미사용 — 전부 지역 구현)** |
| `app/LoginHandoff.jsx` | 154 | MascotPose |
| `app/NotificationBell.jsx` | 611 | EmptyState, ErrorState, Skeleton, Badge |
| `app/ScopeBar.jsx` | 174 | **(공용 미사용 — 전부 지역 구현)** |
| `app/StatusNotices.jsx` | 340 | EmptyState, Badge, Button |
| `app/TopBrand.jsx` | 63 | Button |
| `app/TopSearch.jsx` | 82 | **(공용 미사용 — 전부 지역 구현)** |
| `app/Tour.jsx` | 180 | Modal, Button |
| `app/UserMenu.jsx` | 213 | Button |
| `app/UserRoutes.jsx` | 143 | Card, EmptyState, ErrorState, Skeleton |
| `app/auth.jsx` | 49 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/Activity.jsx` | 187 | PageHeader, Card, EmptyState, ErrorState, Skeleton, Badge, Button, Pager |
| `screens/AssistantPanel.jsx` | 309 | SectionTitle, Card, EmptyState, ErrorState, Skeleton, Badge, Button, BarSeries |
| `screens/Board.jsx` | 617 | PageHeader, Card, DataTable, Modal, EmptyState, ErrorState, Skeleton, Badge, Button, SearchBox |
| `screens/BoardPost.jsx` | 627 | PageHeader, Card, Callout, ErrorState, Skeleton, Badge, Button |
| `screens/Chat.jsx` | 422 | PageHeader, Card, ErrorState, Skeleton, Button |
| `screens/ChatBubbleText.jsx` | 68 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/ChatPane.jsx` | 556 | EmptyState, ErrorState, Skeleton, Button |
| `screens/ChatRoom.jsx` | 179 | ErrorState, Skeleton, Button |
| `screens/ChatRoomMembers.jsx` | 290 | Modal, EmptyState, ErrorState, Skeleton, Button |
| `screens/ChatRooms.jsx` | 366 | PageHeader, Card, Modal, EmptyState, ErrorState, Skeleton, Button |
| `screens/CommentThread.jsx` | 206 | Card, ErrorState, Skeleton, Button |
| `screens/Dashboard.jsx` | 661 | PageHeader, Card, Callout, StatCard, ErrorState, Skeleton, Badge, Button, BarSeries |
| `screens/DataScreen.jsx` | 979 | PageHeader, Card, Callout, StatCard, DataTable, Modal, EmptyState, ErrorState, Skeleton, Button, FilterBarGrid, SearchBox, SavedViews |
| `screens/DevReport.jsx` | 380 | PageHeader, Card, Callout, StatCard, EmptyState, ErrorState, Skeleton, Badge, Button, BarSeries, Donut |
| `screens/DisplaySettings.jsx` | 28 | PageHeader |
| `screens/DocComments.jsx` | 25 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/GameRoom.jsx` | 124 | PageHeader, Card, ErrorState, Skeleton, Badge, Button |
| `screens/Games.jsx` | 443 | PageHeader, Card, Callout, Modal, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/Home.jsx` | 410 | PageHeader, SectionTitle, Card, StatCard, DataTable, EmptyState, ErrorState, Skeleton, Badge, Button, Donut |
| `screens/Integrity.jsx` | 241 | PageHeader, SectionTitle, Card, Callout, StatCard, DataTable, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/LlmConsole.jsx` | 376 | PageHeader, Card, Callout, ErrorState, Skeleton, Badge, Button |
| `screens/MailStatus.jsx` | 156 | PageHeader, Card, Callout, DataTable, ErrorState, Skeleton, Badge, Button |
| `screens/MyApprovals.jsx` | 161 | PageHeader, Card, DataTable, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/MyStats.jsx` | 306 | PageHeader, SectionTitle, Card, Callout, StatCard, DataTable, EmptyState, ErrorState, Skeleton, BarSeries, Donut, LineSeries |
| `screens/MyTickets.jsx` | 1189 | PageHeader, Card, Callout, Modal, EmptyState, ErrorState, Skeleton, Badge, Button, Pager, useRowSelection, BodyEditor, BASELINE_TRACKS |
| `screens/NotionConsole.jsx` | 416 | PageHeader, Card, Callout, FormModal, ErrorState, Skeleton, Badge, Button |
| `screens/Offboarding.jsx` | 564 | PageHeader, Card, Callout, DataTable, Modal, EmptyState, ErrorState, Skeleton, Badge, Button, useRowSelection |
| `screens/Ops.jsx` | 16 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/OrgConsole.jsx` | 94 | PageHeader, Callout |
| `screens/OrgTree.jsx` | 317 | Card, EmptyState, ErrorState, Skeleton, Badge, SearchBox |
| `screens/Profile.jsx` | 493 | PageHeader, SectionTitle, Card, Callout, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/Project.jsx` | 500 | PageHeader, Card, Callout, FormModal, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/ProjectMetrics.jsx` | 183 | Skeleton |
| `screens/ProjectTickets.jsx` | 116 | Card, Callout, EmptyState, ErrorState, Skeleton, Pager |
| `screens/ProjectWbs.jsx` | 153 | Card, Callout, EmptyState, Badge |
| `screens/ProjectWeekly.jsx` | 255 | Card, Callout, ErrorState, Skeleton, Badge, Button |
| `screens/Projects.jsx` | 346 | PageHeader, Card, Callout, StatCard, DataTable, FormModal, EmptyState, ErrorState, Skeleton, Badge, Button, Pager |
| `screens/SchedulerCalendar.jsx` | 477 | PageHeader, Card, Callout, DataTable, Modal, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/Search.jsx` | 282 | PageHeader, Card, EmptyState, ErrorState, Skeleton, Button |
| `screens/Settings.jsx` | 20 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/SetupWizard.jsx` | 241 | PageHeader, Card, Callout, EmptyState, ErrorState, Skeleton, Button |
| `screens/Sprint.jsx` | 540 | PageHeader, Card, Callout, StatCard, ErrorState, Skeleton, Button, BarSeries, LineSeries, BASELINE_TRACKS |
| `screens/SystemOps.jsx` | 302 | PageHeader, Card, Callout, FormModal, ErrorState, Skeleton, Badge, Button |
| `screens/TeamChatWidget.jsx` | 65 | Card, ErrorState, Skeleton |
| `screens/TeamDoc.jsx` | 380 | PageHeader, Card, Callout, ErrorState, Skeleton, Badge, Button, EditableBody, BASELINE_TRACKS |
| `screens/TeamDocs.jsx` | 625 | PageHeader, Card, Callout, DataTable, Modal, EmptyState, ErrorState, Skeleton, Badge, Button, FilterBarGrid, SearchBox, Pager, useRowSelection, BodyEditor |
| `screens/TeamTickets.jsx` | 167 | PageHeader, Card, Callout, ErrorState, Skeleton, Pager |
| `screens/Ticket.jsx` | 273 | PageHeader, Card, Callout, EmptyState, ErrorState, Skeleton, Badge, Button, BASELINE_TRACKS |
| `screens/TicketAttachments.jsx` | 316 | Card, Callout, Button |
| `screens/TicketBody.jsx` | 46 | EditableBody |
| `screens/TicketComments.jsx` | 30 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/TicketFilterBar.jsx` | 256 | Card, EmptyState, Button, FilterBarGrid, SearchBox, FilterSelect |
| `screens/Trash.jsx` | 224 | PageHeader, Card, StatCard, DataTable, EmptyState, ErrorState, Skeleton, Badge, Button, useRowSelection |
| `screens/Users.jsx` | 1116 | PageHeader, Card, Callout, DataTable, Modal, FormModal, EmptyState, ErrorState, Skeleton, Badge, Button, FilterBarGrid, useRowSelection |
| `screens/UsersBulk.jsx` | 257 | Card, Callout, DataTable, Modal, Badge, Button |
| `screens/WorkSummary.jsx` | 160 | Card, StatCard, ErrorState, Skeleton, BarSeries |
| `screens/chat/ConversationSidebar.jsx` | 227 | EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/chat/MessageThread.jsx` | 297 | Button |
| `screens/chat/ResultsRail.jsx` | 53 | EmptyState, MascotPose |
| `screens/chat/RichText.jsx` | 95 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/chat/TicketCard.jsx` | 155 | Badge, Button |
| `screens/chat/WelcomeStatus.jsx` | 61 | MascotPose |
| `screens/chat/links.jsx` | 79 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/data-screen/JsonBlock.jsx` | 32 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/data-screen/SubListDrawer.jsx` | 176 | Callout, DataTable, Modal, EmptyState, ErrorState, Skeleton, Button |
| `screens/data-screen/columnHelpers.jsx` | 94 | Badge |
| `screens/game-room/ChatPanel.jsx` | 81 | EmptyState, Button |
| `screens/game-room/GameStage.jsx` | 337 | Button |
| `screens/game-room/LadderBoard.jsx` | 99 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/game-room/MembersList.jsx` | 73 | Badge |
| `screens/game-room/RoomSidebar.jsx` | 31 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/game-room/RpsViews.jsx` | 141 | Badge |
| `screens/game-room/Scoreboard.jsx` | 30 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/game-room/StageShared.jsx` | 94 | MascotPose |
| `screens/ops/DiagnosticActions.jsx` | 24 | Button |
| `screens/ops/Diagnostics.jsx` | 318 | PageHeader, Card, Callout, StatCard, EmptyState, ErrorState, Skeleton, Badge |
| `screens/ops/JobQueuePanel.jsx` | 77 | Card, StatCard, Sparkline |
| `screens/ops/LogList.jsx` | 22 | **(공용 미사용 — 전부 지역 구현)** |
| `screens/ops/Maintenance.jsx` | 272 | PageHeader, SectionTitle, Card, Callout, ErrorState, Skeleton, Badge, Button |
| `screens/ops/ServiceStatusPanel.jsx` | 103 | Callout, StatCard, Badge |
| `screens/settings/AccentPicker.jsx` | 61 | Card |
| `screens/settings/SettingEditor.jsx` | 261 | Callout, Modal, Button |
| `screens/settings/SettingVersions.jsx` | 90 | Card, DataTable, Modal, EmptyState, ErrorState, Skeleton, Button |
| `screens/settings/SettingsMain.jsx` | 143 | PageHeader, Card, DataTable, EmptyState, ErrorState, Skeleton, Badge, Button |
| `screens/settings/SettingsShell.jsx` | 142 | PageHeader, Card, EmptyState, ErrorState, Skeleton, Button |
| `screens/settings/StructuredObjectFields.jsx` | 205 | Button |

---

## 4. 즉시 드러난 공백

**공용 컴포넌트를 하나도 쓰지 않는 화면 16개** — 전부 지역 구현이다:

- `screens/chat/links.jsx`
- `screens/chat/RichText.jsx`
- `screens/ChatBubbleText.jsx`
- `screens/data-screen/JsonBlock.jsx`
- `screens/DocComments.jsx`
- `screens/game-room/LadderBoard.jsx`
- `screens/game-room/RoomSidebar.jsx`
- `screens/game-room/Scoreboard.jsx`
- `screens/ops/LogList.jsx`
- `screens/Ops.jsx`
- `screens/Settings.jsx`
- `screens/TicketComments.jsx`
- `app/auth.jsx`
- `app/CommandPalette.jsx`
- `app/ScopeBar.jsx`
- `app/TopSearch.jsx`

**PageHeader**: 화면 파일 102개 중 39개만 사용.
어디가 Archetype상 정당한 생략이고 어디가 누락인지 P2에서 판정한다
(지시 66 — 집중형 화면에는 강제하지 않는다).

**검색·필터가 갈라져 있다**: `FilterBarGrid` 4 · `SearchBox` 5 · `FilterSelect` 1 · `SavedViews` 1.
List Archetype Route 수에 한참 못 미친다(지시 5).

**차트가 흩어져 있다**: `BarSeries` 6 · `Donut` 3 · `LineSeries` 2 · `Sparkline` 1. 공통 규칙 없음(지시 2·9·10).

**Callout이 35개 파일**에 퍼져 있다. 지시 35의 '모든 안내를 큰 Border Box로'가 여기서 나온다.
