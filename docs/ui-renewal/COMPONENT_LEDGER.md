# 부품 대장 — 공통 컴포넌트 정본 · 소비처 · 예외

**정본(값)**: `design_handoff_clovirassist_ui/` — DECISIONS → README → RULES → ACCEPTANCE → GALLERY-FIXES
**정본(구현)**: `frontend/src/ui/**` Source
**구현 참고값**: `/kit` (`frontend/src/screens/dev/KitGallery.jsx`) — 실제 부품을 불러 쓴다
**결정**: `docs/DECISIONS.md` D-485(클로비 크기) · D-486(핸드오프 A 정본화)

이 문서가 답하는 것 둘: **「이 모양을 어디서 고치나」**와 **「이 부품을 누가 쓰나」**. 부품마다
UI 의미 → 정본 컴포넌트/파일 → API · 상태 계약 → 소비처 전수 → 예외 → 갤러리 견본 → 시험을 잇는다.

> **정본은 핸드오프 문서다** (D-486, 2026-09-15). 예전 머리말 「정본은 갤러리다」(D-473~D-481)는
> 핸드오프가 뒤집었다. 갤러리는 A 정리 뒤의 구현 참고값이고, 문서와 어긋나면 부품을 고친다.
> 아래 §4 의 옛 「갤러리 확정」 표는 이력으로 남기되 뒤집힌 줄에 새 값을 적었다.

---

## 0. 정본 인벤토리와 소비처

소비처 수는 `frontend/src` 에서 그 이름을 `import` 해 쓰는 파일(시험 · 갤러리 · 정의 파일 제외)이다.
`0` 인 부품은 A 가 세우고 B 가 소비처를 붙이는 신설 부품이다. 표와 목록은 단계가 끝날 때마다 다시 뽑는다.

| UI 의미 | 정본 | 파일 | 계약 요지 | 소비처 수 | 갤러리 절 | 시험 |
|---|---|---|---|---|---|---|
| 페이지 동작 34 · 인라인 30 | `Button` | `ui/kit.jsx` | variant default(=secondary) · primary · ghost · danger · dangerConfirm, `size sm`, 라벨 한 줄 · 안 줄어듦 · `truncate` 만 말줄임 | 81 | 버튼 | `handoff-kit-contract`, `long-text-contract`, `kit.test` |
| 알릴 사실(메시지 박스 1a) | `Callout` | `ui/kit.jsx` | 네 톤 같은 면 · 아이콘만 상태, 톤 이름 줄 없음, `compact` · `inline` · `bleed`, error=alert | 38 | 메시지 박스 | `kit.test`, `handoff-kit-contract` |
| 빈 상태 | `EmptyState` | `ui/kit.jsx` | layout page/card/region/inline, 클로비 page 132/112 · 판 72 · inline 없음(D-485) | 50 | 빈 상태와 오류 | `list-empty-two-faces`, `mascot-size-contract` |
| 조건 0건 / 자료 0건 | `ListEmptyState` | `ui/kit.jsx` | `filtered` 갈래 소유 | 7 | 이럴 때 이것 | `list-empty-two-faces` |
| 오류 상태 | `ErrorState` | `ui/kit.jsx` | layout 별 클로비(errorPage/errorRegion), 아이콘, 판 안 동작 30, 모르는 size/layout DEV 중지 | 62 | 빈 상태와 오류 | `kit.test`, `handoff-kit-contract` |
| 로딩 | `Skeleton` | `ui/kit.jsx` | kind section/table/chart/page | 62 | 빈 상태와 오류 | `skeleton-shapes` |
| 정해진 값(목록 밖) | `Badge` | `ui/kit.jsx` | 22 · 좌우 8 · R4 · 600 · 점 없음, 표 문맥에서는 점 + 낱말 | 52 | 배지와 태그와 점과 칩 | `badge-vs-tag` |
| 사람이 붙인 낱말 | `Tag` | `ui/kit.jsx` | 22 · R6 · 400 · 흰 면 + 테두리, 한 줄 말줄임 | 4 | 배지와 태그와 점과 칩 | `badge-vs-tag`, `long-text-contract` |
| 점 + 낱말(표 · 칸반 · 목록 행) | `DotLabel` | `ui/kit.jsx` | 7px 점 aria-hidden, 한 줄 · title | 2 | 배지와 태그와 점과 칩 | `handoff-kit-contract` |
| 건수 미니 칩 | `CountChip` | `ui/kit.jsx` | 20 한 값, `compact` 18, `unread` Primary | 0 | 배지와 태그와 점과 칩 | `handoff-kit-contract` |
| 보기 전환 | `Segmented` | `ui/kit.jsx` | 34 = 28 + 3×2(선은 안쪽 그림자), roving tabindex + 화살표/Home/End | 2 | 세그먼티드 | `kit.test`, `handoff-kit-contract` |
| 데이터 표 | `DataTable` | `ui/kit.jsx` | 머리 40 · 행 ≥48 · `rowHeight=tall` ≥76 · 묶음 36 · 발 44, 제목만 왼쪽(머리 = 행), 빈 표 = EmptyState region | 22 | 데이터 표 | `column-types`, `datatable-*` |
| 판 | `Card` | `ui/kit.jsx` | 여백 20, 판 안의 판은 여백까지 사라짐 | 53 | 모든 절 | `density-contract` |
| 목록 판 | `ListCard` | `ui/kit.jsx` | 자기 안을 자르지 않음(sticky 머리) | 14 | — | `kit.test` |
| 구획 제목 | `SectionTitle` | `ui/kit.jsx` | 1.0625rem/700 + 설명 | 12 | 모든 절 | `heading-order` |
| 모달 | `Modal` | `ui/kit.jsx` | 제목 17/700 · 닫기 30 · 모서리 8 · 발 ActionFooter, `tone=danger` 표지 | 23 | 팝오버와 모달 | `modal-*`, `handoff-kit-contract` |
| 폼 모달 | `FormModal` | `ui/kit.jsx` | Modal + FormField | 11 | — | `form-*` |
| 카드 발 · 모달 발 | `ActionFooter` | `ui/kit.jsx` | 함몰면 + 위 실선, 오른쪽 정렬 gap 8, `extra` 왼쪽, 주인 하나(`data-action-footer`) | 0 | 팝오버와 모달, 폼 필드 | `handoff-kit-contract` |
| 확인 대화 | `useConfirm` | `ui/kit.jsx` | danger 는 표지 + 취소 기본 포커스 + dangerConfirm | 40 | 팝오버와 모달 | `handoff-kit-contract`, `kit.test` |
| 토스트 | `useToast` | `ui/kit.jsx` | 성공 · 정보만, 잉크 면(다크 함몰면), 모서리 8 | 54 | 빈 상태와 오류 | `toast-announce` |
| 팝오버 동작 목록 | `overflowMenuItems` | `ui/kit.jsx` | 32 항목, 파괴적만 error 글자 + 위 선 | 0 | 팝오버와 모달 | `kit.test` |
| 폼 칸 | `FormFieldCell` | `ui/kit.jsx` | 라벨 20 · 필드 36 · 도움말 auto, 오류가 도움말 자리 | 0 | 폼 필드 | `handoff-kit-contract` |
| 속성 줄 | `MetaBar` | `ui/kit.jsx` | 키/값 | 4 | — | `metabar-hierarchy` |
| 페이지 머리 | `PageHeader` | `ui/kit.jsx` | 제목 28/700 + 설명 + 동작 34 | 35 | 머리 | `page-header-*` |
| 필터 바 그릇 | `FilterSurface` | `ui/FilterBar.jsx` | 판 없음 · 아래 실선 · 줄 칸 문맥 제공 | 12 | 검색과 필터 바 | `filter-row-width`, `handoff-kit-contract` |
| 필터 바 도구 줄 | `ToolbarRow` | `ui/FilterBar.jsx` | 검색 슬롯 320(직계), 좁으면 100% | 10 | 검색과 필터 바 | `handoff-kit-contract` |
| 필터 바 내용 줄 | `FilterRow` | `ui/FilterBar.jsx` | 검색 슬롯 320(직계), 위 정렬 | 10 | 검색과 필터 바 | `filter-row-width` |
| 필터 바 오른쪽 묶음 | `ToolbarEnd` | `ui/FilterBar.jsx` | 통째로 줄바꿈(nowrap · 안 줄어듦) | 4 | 검색과 필터 바 | — |
| 결과 수 | `ResultLine` | `ui/FilterBar.jsx` | 「전체 N건」(조건 없을 때) | 8 | 검색과 필터 바 | `filter-row-width` |
| 조건 칩 줄 | `FilterChips` | `ui/FilterBar.jsx` | 26 · 알약 · 틴트 · X | 2 | 검색과 필터 바 | `filter-row-width` |
| 조건 줄(둘째 줄) | `FilterConditionLine` | `ui/FilterBar.jsx` | 조건이 있을 때만 · 위 실선 · 「조건 N개, 결과 M건」 | 0 | 검색과 필터 바 | `handoff-kit-contract` |
| 필터 켬/끔 · 패널 열기 | `FilterToggle` | `ui/FilterBar.jsx` | 34 버튼, aria-pressed / aria-expanded, 눌림만 함몰면 | 0 | 검색과 필터 바 | `handoff-kit-contract` |
| 검색창 | `SearchBox` | `ui/filters.jsx` | 줄 칸 34, `layout=fill` 100% | 9 | 검색과 필터 바 | `handoff-kit-contract` |
| 닫힌 축 셀렉트 | `FilterSelect` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름, 값 한 줄 · title | 11 | 검색과 필터 바 | `filter-form-layout`, `long-text-contract` |
| 늘어나는 축 고르개 | `EntityCombobox` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름, 목록은 PickerOption, `myId` 맨 위 | 13 | 검색과 필터 바, 팝오버와 모달 | `entity-combobox*` |
| 자유 입력 필터 | `DebouncedTextField` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름 | 3 | — | `filters.test` |
| 부서 필터 | `DepartmentFilter` | `ui/filters.jsx` | 경로 라벨 | 2 | — | `department-filter` |
| 회차 팀 문맥 | `TeamSelect` | `ui/filters.jsx` | 「전체」 없음, 후보 < 2 면 안 그림 | 2 | — | `work-board-team-context` |
| 검색 팝오버 항목 | `PickerOption` | `ui/filters.jsx` | 32 한 줄 · 체크 · title | 1 | 팝오버와 모달 | `handoff-kit-contract` |
| 사람 고르기 | `UserPicker` | `ui/UserPicker.jsx` | 아바타 22 + 이름 + 소속, (나) 표시 | 0 | 팝오버와 모달 | `pickers.test` |
| 프로젝트 고르기 | `ProjectPicker` | `ui/ProjectPicker.jsx` | 코드 보조 | 2 | — | `pickers.test` |
| 태그 고르기 | `TagPicker` | `ui/TagPicker.jsx` | renderTags 칩(원재료 호스트) | 3 | — | `tag-picker*` |
| 상태 요약 | `StatusSummaryCard` | `ui/StatusKpi.jsx` | 카드 하나 · 비율 바는 total 일 때만 · 값 하나 갈래 | 2 | 상태 요약 | `status-summary-card`, `handoff-kit-contract` |
| 독립 측정값 줄 | `StatusKpiStrip` | `ui/StatusKpi.jsx` | `note` 캡션 | 1 | 상태 요약 | `status-kpi-note` |
| 칸반 카드 | `TicketFace` | `ui/TicketFace.jsx` | 12/14 · 줄 8 · 발 위 실선, 우선순위와 신호 점 + 낱말 | 2 | 칸반 카드 | `ticket-signals`, `handoff-kit-contract` |
| 신호 표시 | `TicketSignals` | `ui/TicketSignals.jsx` | 기본 dot, 상세 머리 pill, 좁은 표 칸 mark | 4 | 칸반 카드 | `ticket-signals` |
| 사람 얼굴 | `UserAvatar` | `ui/UserAvatar.jsx` | xs 22 · inline 20 · sm 24 · md 30 · lg 40 · xl 72 | 11 | 데이터 표 | — |
| 사람 한 줄 | `PersonLine` | `ui/UserAvatar.jsx` | 얼굴 + 이름 말줄임 | 3 | — | — |
| 페이지 탭 | `TabShell` | `ui/TabShell.jsx` | 라우트 탭 | 1 | — | `settings-shell` |
| 설정 줄 | `SettingRow` | `ui/adminKit.jsx` | `compact` 한 줄 | 3 | 조작기의 상태 | — |
| 상태 줄 목록 | `StatusList` | `ui/adminKit.jsx` | 이름 + 슬롯 | 3 | — | — |
| 회의 갈래 칩 | `DiscussBucketRow` | `ui/DiscussBucket.jsx` | 알약 + StatusDot, tablist · roving tabindex | 1 | — | `sprint-meeting` |
| 티켓 미리보기 | `TicketPeek` | `screens/TicketPeek.jsx` | Modal md, 발 → ActionFooter(B) | 2 | — | `ticket-peek` |
| 판독 줄(걷을 대상) | `MetricStrip` | `ui/kit.jsx` | B 단계가 데이터 의미별로 흡수한 뒤 걷는다 | 14 | — | `kit.test` |

소비처 파일 목록:

- `Button`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `app/AssistantDrawer.jsx`, `app/Banners.jsx`, `app/StatusNotices.jsx`, `app/TopBrand.jsx`, `app/Tour.jsx`, `app/UserMenu.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketFilterBar.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/MessageThread.jsx`, `screens/chat/TicketCard.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/game-room/GameStage.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/knowledge/TaxonomyManager.jsx`, `screens/ops/DiagnosticActions.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/settings/SettingsShell.jsx`, `screens/settings/StructuredObjectFields.jsx`, `ui/DefaultAvatarPicker.jsx`, `ui/EditableBody.jsx`, `ui/FilterBar.jsx`, `ui/InfiniteScroll.jsx`, `ui/SavedViews.jsx`, `ui/TabShell.jsx`, `ui/bulkSelect.jsx`, `ui/columnFilter.jsx`
- `Callout`: `app/AssistantDrawer.jsx`, `app/Banners.jsx`, `app/StatusNotices.jsx`, `screens/AiWorkspace.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/SetupWizard.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketPeek.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/settings/SettingEditor.jsx`, `ui/DocBody.jsx`, `ui/EditableBody.jsx`
- `EmptyState`: `app/AdminRoutes.jsx`, `app/NotificationBell.jsx`, `app/StatusNotices.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWbs.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketFilterBar.jsx`, `screens/TicketHistory.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/ResultsRail.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/ops/Diagnostics.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/settings/SettingsShell.jsx`, `ui/TabShell.jsx`
- `ListEmptyState`: `screens/ChatRooms.jsx`, `screens/Knowledge.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Projects.jsx`, `screens/Trash.jsx`, `screens/chat/ConversationSidebar.jsx`
- `ErrorState`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `app/NotificationBell.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketHistory.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/WorkSummary.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/settings/SettingsShell.jsx`, `ui/TabShell.jsx`
- `Skeleton`: `app/AdminRoutes.jsx`, `app/App.jsx`, `app/AppShell.jsx`, `app/AssistantDrawer.jsx`, `app/NotificationBell.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectMetrics.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketHistory.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/WorkSummary.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/settings/SettingsShell.jsx`, `ui/EditableBody.jsx`, `ui/TabShell.jsx`
- `Badge`: `app/NotificationBell.jsx`, `app/StatusNotices.jsx`, `screens/Activity.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Dashboard.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/TicketCard.jsx`, `screens/data-screen/columnHelpers.jsx`, `screens/game-room/MembersList.jsx`, `screens/game-room/RpsViews.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/registry/authoring.js`, `screens/registry/governance.js`, `screens/registry/notifications.js`, `screens/registry/platform.js`, `screens/settings/SettingsMain.jsx`, `screens/ticket-meta.jsx`, `ui/SavedViews.jsx`, `ui/adminKit.jsx`, `ui/charts/BarSeries.jsx`
- `Tag`: `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/LlmConsole.jsx`, `screens/settings/SettingsMain.jsx`
- `DotLabel`: `ui/TicketFace.jsx`, `ui/TicketSignals.jsx`
- `Segmented`: `screens/AssistantPanel.jsx`, `screens/MyStats.jsx`
- `DataTable`: `screens/Board.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/ProjectDocuments.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/StorageProviders.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`
- `Card`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketHistory.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/AccentPicker.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsShell.jsx`, `ui/TabShell.jsx`, `ui/TicketFace.jsx`
- `ListCard`: `screens/Activity.jsx`, `screens/Board.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/MailStatus.jsx`, `screens/Offboarding.jsx`, `screens/Projects.jsx`, `screens/StorageProviders.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/settings/SettingsMain.jsx`
- `SectionTitle`: `screens/AssistantPanel.jsx`, `screens/DevReport.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/LlmConsole.jsx`, `screens/MyStats.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/TicketHistory.jsx`, `screens/ops/Maintenance.jsx`, `screens/settings/AccentPicker.jsx`, `ui/adminKit.jsx`
- `Modal`: `app/Tour.jsx`, `screens/Board.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/SchedulerCalendar.jsx`, `screens/SprintLifecycle.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/knowledge/NewDocumentModal.jsx`, `screens/knowledge/TaxonomyManager.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `ui/AvatarCropDialog.jsx`, `ui/DefaultAvatarPicker.jsx`, `ui/SavedViews.jsx`
- `FormModal`: `screens/AiWorkspace.jsx`, `screens/Knowledge.jsx`, `screens/Project.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/org/orgModals.jsx`
- `useConfirm`: `app/NotificationBell.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/useGameRoomController.js`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `screens/useChat.js`, `ui/EditableBody.jsx`, `ui/SavedViews.jsx`
- `useToast`: `app/Banners.jsx`, `app/NotificationBell.jsx`, `app/UserMenu.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/links.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/useGameRoomController.js`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/org/orgModals.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/useChat.js`, `ui/EditableBody.jsx`, `ui/SavedViews.jsx`
- `MetaBar`: `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/Ticket.jsx`, `screens/TicketPeek.jsx`
- `PageHeader`: `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatRooms.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/Projects.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/ops/Diagnostics.jsx`, `screens/settings/SettingsShell.jsx`, `ui/TabShell.jsx`
- `FilterSurface`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`
- `ToolbarRow`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/settings/SettingsMain.jsx`
- `FilterRow`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`
- `ToolbarEnd`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/SchedulerCalendar.jsx`, `screens/settings/SettingsMain.jsx`
- `ResultLine`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/Knowledge.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`
- `FilterChips`: `screens/TicketFilterBar.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`
- `SearchBox`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`
- `FilterSelect`: `screens/DataScreen.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `ui/columnFilter.jsx`
- `EntityCombobox`: `screens/DataScreen.jsx`, `screens/Integrity.jsx`, `screens/MyTickets.jsx`, `screens/Project.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `ui/ProjectPicker.jsx`, `ui/UserPicker.jsx`, `ui/columnFilter.jsx`, `ui/kit.jsx`
- `DebouncedTextField`: `screens/DataScreen.jsx`, `screens/TicketFilterBar.jsx`, `ui/columnFilter.jsx`
- `DepartmentFilter`: `screens/Projects.jsx`, `screens/TeamTickets.jsx`
- `TeamSelect`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `PickerOption`: `ui/UserPicker.jsx`
- `ProjectPicker`: `screens/KnowledgeDoc.jsx`, `screens/knowledge/NewDocumentModal.jsx`
- `TagPicker`: `screens/KnowledgeDoc.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/knowledge/NewDocumentModal.jsx`
- `StatusSummaryCard`: `screens/Home.jsx`, `screens/MyStats.jsx`
- `StatusKpiStrip`: `screens/Sprint.jsx`
- `TicketFace`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `TicketSignals`: `screens/MyTickets.jsx`, `screens/WorkBoard.jsx`, `screens/ticket-meta.jsx`, `ui/TicketFace.jsx`
- `UserAvatar`: `app/UserMenu.jsx`, `screens/Board.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoomMembers.jsx`, `screens/KnowledgeDoc.jsx`, `screens/Profile.jsx`, `screens/ProjectDocuments.jsx`, `screens/Sprint.jsx`, `screens/knowledge/documentColumns.jsx`, `screens/org/DeptDetailPanel.jsx`, `ui/UserPicker.jsx`
- `PersonLine`: `screens/MyTickets.jsx`, `screens/ticket-meta.jsx`, `ui/TicketFace.jsx`
- `TabShell`: `app/AdminRoutes.jsx`
- `SettingRow`: `screens/Integrity.jsx`, `screens/Profile.jsx`, `screens/SystemOps.jsx`
- `StatusList`: `screens/Dashboard.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/ServiceStatusPanel.jsx`
- `DiscussBucketRow`: `screens/Sprint.jsx`
- `TicketPeek`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `MetricStrip`: `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/MailStatus.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/SetupWizard.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/JobQueuePanel.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`

---

## 0-1. 채팅 전용 시각 규격 (소유자 확정 — 공통 토큰으로 접지 않는다)

핸드오프 README §C · RULES §9 의 채팅 값은 공통 토큰의 가장 가까운 값으로 바꾸지 않는다(소유자, 2026-09-14):
상대 아바타 34 · 머리 참여자 스택 26 / −8 겹침 · 말풍선 모서리 12(연결 모서리 4) · 말풍선 최대 폭 68% ·
입력창 모서리 10 · 도구 / 보내기 30 · 목록 296 · 시각 글자 0.6875rem. 값은 `frontend/src/ui/chat.js::CHAT`
한 곳에 두고 소비처가 생기는 회차가 더한다(지금은 AI 도우미 말풍선의 `bubbleRadius` 12).

## 0-2. 문서와 제품이 어긋난 자리 — 제품 동작을 보존한다

| 문서 | 제품 | 처리 |
|---|---|---|
| README 「채팅 Shift+Enter 줄바꿈(기존 동작)」 | 채팅방 입력은 한 줄(`ChatPane.jsx` `InputBase`) — 줄바꿈 없음 | 새로 만들지 않는다(E-2) |
| README §3 「작업 보드 상세 필터 기존 동작 유지」 | D-484 에서 상세 필터를 걷고 두 줄 필터 | 두 줄 필터 보존, 상세 필터 되살리지 않음 |

## 0-3. 클로비 크기 계약 (D-485)

`page` 132(화면 높이 ≤800 이면 112) · `card` / `region` / `compact` ≤72 · `inline` 없음. `MASCOT_PLACE` 의
`emptyPage` · `errorPage`(132/112) · `emptyCard` · `emptyRegion` · `emptyCompact` · `errorRegion`(72). 장식
삽화 `statsArt`(내 업무량 요약 타일, 84)는 빈 상태 계약 밖이다.

## 0-4. raw MUI 원재료 경계 (`scripts/check_kit_consumers.py` 의 판정 기준)

**A — 정본 wrapper 가 있다.** 화면이 직접 쓰면 실패, 아래 「예외」 표에 있을 때만 통과.

| 원재료 | 정본 |
|---|---|
| `Button` | kit `Button` |
| `Alert` | `Callout`(kit 안 폼 오류 줄 · 토스트 알맹이만 예외) |
| `Chip` | `Badge` · `Tag` · `CountChip` · `FilterChips`(Autocomplete `renderTags` 칩은 `TagPicker` 가 호스트) |
| `Dialog` · `DialogTitle` · `DialogContent` · `DialogActions` | `Modal` · `FormModal` · `useConfirm` |
| `Menu` · `MenuList` | `OverflowMenu` · `overflowMenuItems`(`TextField select` 안의 `MenuItem` 은 B) |
| `Tabs` · `Tab` | 보기 전환 `Segmented`, 페이지 탭 `TabShell` |
| `ToggleButton(Group)` | `Segmented` |
| `Table*` | `DataTable` |
| `Snackbar` | `ToastProvider` |
| `Paper` · `Card` · `CardContent` | `Card` · `ListCard` · `Surface` |
| `Autocomplete` | `EntityCombobox` · `UserPicker` · `ProjectPicker` · `TagPicker` |
| `Badge`(MUI) | `CountChip` |
| `Skeleton`(MUI) | kit `Skeleton` |

**B — 직접 써도 되는 기초 원재료.** 크기 · 색 · 모서리는 `theme.js` 중앙 override 만 쓰고 화면 전용 높이 ·
모서리 · 색 리터럴은 실패: `IconButton`(정사각형이라 폭도) · `Switch`(즉시 저장 설정만) · `Checkbox` ·
`Radio` · `TextField` · `InputBase` · `OutlinedInput` · `Popover`(패널형) · `Drawer`(셸 하우징) ·
`LinearProgress` · `CircularProgress` · `Slider`. 필터의 켬/끔에는 `FilterToggle`(A)을 쓴다.

### 예외 — 정본으로 대체하지 않는 자리

B 단계가 전수 흡수를 끝낸 뒤 남는 자리만 적는다. 형식은 검사기가 읽는다(`| 파일 | 원재료 | 이유 | 대체 불가 근거 |`).

| 파일 | 원재료 | 이유 | 대체 불가 근거 |
|---|---|---|---|
| `ui/FilterBar.jsx` | `Chip` | `FilterChips` 조건 칩의 알맹이 | 정본 부품 자신이다 |
| `ui/TagPicker.jsx` | `Chip` | Autocomplete `renderTags` 선택 칩 | MUI Autocomplete 가 지우기 · 키보드 이동을 그 칩에 건다 |
| `screens/AiWorkspace.jsx` | `Chip` | 인용 번호(1, 2 …) | 건수도 사람이 붙인 낱말도 아닌 순번 표지다(계획 표 2) |
| `screens/Board.jsx` | `Chip` | 이모지 반응 토글(`aria-pressed` + 누른 수) | 누르면 켜고 끄는 반응이고 높이는 작은 단추(30)에 맞췄다(계획 표 2) |
| `app/NotificationBell.jsx` | `Badge`(MUI) | 종 아이콘 위 네 상태(숫자 · 조용 · 오류 · 불러오는 중) | 아이콘에 겹쳐 서는 표지라 칩 줄에 놓이지 않는다(계획 §0-11) |

## 0-5. 카드 발 · 모달 발의 주인은 하나다

`ActionFooter` 가 면(`background.inset`) · 위 실선(`rule`) · 여백을 **한 요소**(`data-action-footer`)에서 그린다.
`Modal` 이 받은 `footer` 가 이미 발이면 감싸지 않고(바깥이 물러난다), 발 안의 발은 맨 줄로 선다.
`ModalBody` 는 위 선만 긋는다(아래 선은 발의 것). `kit_measure.py` 의 `footer_owner` 가 발마다 주인 수 1 을 잰다.

## 0-6. 건수 칩 갈래 · 표 행 높이

- `CountChip` 기본 **20 한 값**. `compact`(18)은 이름 붙은 갈래이고 쓰는 자리를 여기 적는다: (아직 없음).
- 표 행은 **최솟값**이다: 일반 행 `CONTROL.tableRow` 48, 두 줄 행 `rowHeight="tall"` → `CONTROL.tableRowTall`
  76. 내용이 더 필요하면 자라고 잘리거나 겹치지 않는다. 태그는 네 개 + 「+N」으로 줄 폭증을 막는다.

## 0-7. 실패는 그 자리의 메시지 박스다 — 토스트가 아니다 (핸드오프 RULES §1 · ACCEPTANCE I3)

- 토스트는 **잘 된 일**만 말한다. 저장 실패 · 권한 없음 · 되돌릴 수 없는 결과 · 다시 눌러야 하는 실패는 그 동작이
  속한 자리에 `Callout`(오류는 `danger` · `role="alert"`)로 남는다: 칸 오류는 그 칸의 도움말 자리, 모달 저장 실패는
  발 바로 위, 판 · 목록 동작은 그 판 · 목록 위, 머리 동작은 머리 바로 아래.
- 수명은 `lib/failure.js::failureText`(요청 여럿 중 **가장 나중에 보낸 요청**의 실패) · `latestMutation` 이 요청
  상태에서 읽는다 — 새 상태를 만들지 않는다. 손으로 부른 요청만 지역 상태다. 모달은 열 때 `reset()` 한다.
  시험: `lib/failure.test.js`, `screens/failure-inline-lifecycle.test.jsx`(칸 고치면 해제 · 재오픈 잔존 0 · 성공하면 해제).
- 세션 만료(401)는 `lib/sessionRedirect.js::expireSession` 하나 — 본문 자리가 `kit.jsx::SessionExpiredOutlet`
  (셸이 감싼다)에서 `ErrorState` 401 갈래로 바뀐 뒤 1.2초 뒤 로그인 화면으로 간다.
- 예외(토스트 유지): 보호 화면(`Profile` · `WorkBoard` · `Sprint` · `SprintLifecycle`)의 실패 토스트 — 계획 표 5가
  허용한 치환 목록 밖이다. 문서 목록(`Knowledge.jsx`)은 D, 새 티켓은 C, 채팅방(`ChatRoom` · `ChatRooms` ·
  `ChatPane` · `chat/links.jsx`)은 E 가 옮긴다.

## 0-8. 값을 표시하는 어휘 — 배지 · 태그 · 점+낱말 · 건수 칩 (핸드오프 RULES §2 · ACCEPTANCE F4~F7)

- **목록 그릇이 「여기는 목록이다」를 선언한다.** 표(`DataTable`)에 더해 `adminKit.jsx::StatusList` · `SettingRow` 가
  `FlatBadgeSurface` 를 두른다(대시보드 · 진단 · 서비스 상태 판의 「멈춤」이 줄 안에서 붉은 면으로 섰다). 손으로 만든
  목록은 그 목록이 두른다: 작업 보드 백로그 줄 · 프로젝트 WBS 나무 줄 · 주간 목록 · 마일스톤 목록 · 문서 변경 목록 ·
  게임방 참여자 · 대진표 · AI 도우미 결과 카드.
- **목록 밖(방 머리 · 카드 머리)의 정해진 축 값은 면 배지다** — 채팅방 머리의 방 종류는 `Badge emphasis="strong"`,
  방 목록 행의 방 종류는 `DotLabel`. 목록 행 안의 강조(설치 마법사 「지금 할 차례」)는 `DotLabel strong` 이다.
- **사람이 붙인 낱말은 `Tag`** — 문서 태그(문서 목록 · 프로젝트 문서) · 관계 이름 · 허용 이메일 도메인 · AI 도우미에서
  보낸 첨부 이름. `Tag` 는 전체 낱말을 `title` 로 든다(§0-3 말줄임 계약).
- **건수는 `CountChip`**: 사이드바 안 읽음(`AppShell` — 붉은 손 알약이던 것, 안 읽음 갈래라 Primary 채움) · 채팅방
  목록 행과 머리의 안 읽음 · 검색 결과 묶음 · 정합성 발견 건수 · 스프린트 회의록 레인 · 헤더 상태 단추의 합계.
- **누르는 제안은 30 단추다** — AI 도우미 첫 화면의 시작 예시 · 드로어 제안 · 스레드의 원탭 선택 · 휴지통 「24시간 내
  영구 삭제 N」. 칩 모양의 24~32 조작기는 버튼 높이 집합(34 · 30) 밖이다(ACCEPTANCE C1). 핸드오프에 「제안 칩」
  규격이 따로 없어 새 부품을 만들지 않고 kit `Button size="sm"` 으로 모았다.
- **시스템 안내 줄은 가운데 흐린 낱말이다** — 팀 채팅 · 게임방 채팅의 시스템 메시지와 AI 도우미 날짜 구분선이 같은
  글자(0.75rem · `text.secondary`)로 선다. 채팅방 시안의 날짜 구분선이 선 사이 낱말이라 면 칩을 두지 않는다.
- AI 도우미 결과 카드(`chat/TicketCard.jsx`)는 담당(정/부) · 진행 중 건수 · 여러 프로젝트처럼 칸반 카드에 없는 줄을
  나르므로 `TicketFace` 로 통째로 바꾸지 않고 **어휘만** 맞췄다: 상태 · 우선순위는 점 + 낱말, 프로젝트는 그 프로젝트
  색의 점 + 이름, 「+N」은 30 ghost 단추.
- `app/StatusNotices.jsx::StatusChip` → `StatusNoticeButton` 개명 — 상태를 좁히는 `ui/StatusKpi.jsx::StatusChip` 과
  이름이 같았다. MUI 칩 위 MUI 배지 겹침을 30 단추 + 건수 칩으로 옮겼다.

---

## 1. 신설한 부품

### `DataTable` 의 표 3종 (묶음 머리행 · 발 줄 · 높이)
- **파일**: `frontend/src/ui/kit.jsx` (`GroupHeaderRow` · `GroupHeaderMeta` · `TableFooterRow`)
- **대체**: `MyTickets.jsx::GroupedTickets` 의 자체 12열 표, `DevReport.jsx` 의 담당자 구분 행 표
- **소비 화면**: 내 티켓 · 팀 티켓 · 개발 리포트 · 문서 · 작업 보드(백로그 제외) · 부품 갤러리
- **규약값**: 머리 `CONTROL.tableHead` 40 · 행 `CONTROL.tableRow` 48 · 묶음 머리 36 ·
  발 `CONTROL.tableFooter` 44. 머리 면 `background.inset`, 머리 아래 선 `divider`,
  행 사이 선 `rule`. **실측**: 머리 아래 `#DCDFEC` y=1772, 행 48px, 묶음 행 36px, 행 선 `#E5E8F3`.

### `FlatBadgeSurface`
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 호출부 106곳이 각자 기억하던 「표 안에서는 면을 쓰지 않는다」 규칙
- **소비 화면**: `DataTable` 전체 · 홈 · AI 도우미 · 내 활동 · 조직도 · 부서 상세 · 부품 갤러리
- **규약값**: 치수 없음(문맥 제공자). 이 안의 `Badge` 는 `emphasis` 를 안 주면 면이 없다.
  호출부가 `emphasis="strong"` 으로 이길 수 있다.

### `Segmented`
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 홈 AI 도우미의 MUI 밑줄 `Tabs`, 내 업무량의 기간 셀렉트
- **소비 화면**: 홈(AI 도우미) · 내 업무량 · 부품 갤러리
- **규약값**: 바깥 `background.inset` + 1px `divider` **안쪽 그림자**(D-486 — 테두리였을 때 36px 로 섰다) +
  `RADIUS.sm`(6) + padding 3 + gap 2, 안쪽 `CONTROL.button - 6` = 28 · `RADIUS.sm - 2` = 4 · 선택 시
  `background.plate` + `SHADOW.raised`. roving tabindex + 화살표/Home/End. **실측**: 바깥 34px.

### `StatusSummaryCard` · `StatusChip` · `ZeroChip` · `RatioBar` · `StatusDot`
- **파일**: `frontend/src/ui/StatusKpi.jsx`
- **대체**: 작업 보드·회의의 `StatusKpiStrip` 카드 7~10장, 홈의 `MetricStrip` 판독 줄
- **소비 화면**: 홈 · 내 업무량 · 부품 갤러리 (`StatusKpiStrip` 은 회의가 `note` 캡션과 함께 쓴다.
  작업 보드는 2026-09-14 부터 요약 카드를 안 그린다 — D-484)

### `TicketPeek` · `useTicketPeek` (2026-09-14, D-483)
- **파일**: `frontend/src/screens/TicketPeek.jsx` · 속성 표 `screens/ticket-meta.jsx`
- **대체**: 카드 클릭 → 상세 이동. 작업 보드·스프린트 회의가 같은 창을 연다
- **소비 화면**: 작업 보드 · 스프린트 회의
- **규약값**: `Modal size="md"`. 속성 줄은 상세와 같은 `MetaBar`. 설명 앞 600자. 발 줄은
  회차 작업(secondary sm) · 빠른 수정 · 「티켓 상세 보기」(primary). 닫기는 창의 X 와 Esc 뿐이다.
  주소 `peek` 은 push, 닫기는 `-1`, 상세는 replace

### `DragItemActions` (2026-09-14, D-483)
- **파일**: `frontend/src/ui/DragDrop.jsx`
- **대체**: 끌 수 있는 카드 안에 단추를 두던 자리(없었다 — 카드 안 단추가 끌기·클릭으로 번졌다)
- **소비 화면**: 작업 보드(카드의 `OverflowMenu` · 백로그 줄의 「회차에 담기」)
- **규약값**: `inline-flex` · 포인터/마우스/터치/키/클릭 전파 차단

### `TeamSelect` (2026-09-14, D-482)
- **파일**: `frontend/src/ui/filters.jsx`
- **대체**: 작업 보드의 부서 필터(`DepartmentFilter`) 자리 — 필터가 아니라 **문맥**이다
- **소비 화면**: 작업 보드 · 스프린트 회의
- **규약값**: `EntityCombobox` · 라벨 「팀」 · 「전체」 없음 · 후보 < 2 면 안 그린다 · 라벨은 경로

### `DiscussBucket` 칩 (2026-09-14, D-484)
- **파일**: `frontend/src/ui/DiscussBucket.jsx`
- **대체**: 같은 이름의 큰 타일 여덟(격자 `DISCUSS_TILE_TRACK` 은 걷었다)
- **소비 화면**: 스프린트 회의
- **규약값**: `role="tab"` + roving tabindex 그대로. 알약 `RADIUS.pill` · px 10 · py 5 ·
  `bodySm`. 톤 점은 KPI 와 같은 `StatusDot` 7px(신호 셋만). 고른 칩은 `primary.soft` 면 + `brand.core` 선

### `Gauge` `centerSize="readout"` · `centerCaption` (2026-09-14, D-484)
- **파일**: `frontend/src/ui/charts/Gauge.jsx`
- **소비 화면**: 스프린트 회의(회차 건강 11rem · 두께 8)
- **규약값**: 덮개 `1fr auto 1fr` 격자. 판독값 `FONT_SIZE.pageTitle`, 캡션 `caption`
- **규약값**: 판 py 18 / px 20, 안쪽 줄 사이 12. 칩 `CONTROL.buttonSm` 30 · px 11 · gap 7 ·
  `RADIUS.sm`. 점 7px. 비율 바 8px `RADIUS.full`, 트랙 `background.sunken`.
  0건 칩은 점선. **실측**: 칩 30px, 전체 숫자 `FONT_SIZE.pageTitle` 28px.

### `ColumnSeries`
- **파일**: `frontend/src/ui/charts/ColumnSeries.jsx`
- **대체**: 내 업무량의 완료율 꺾은선(`LineSeries`)
- **소비 화면**: 내 업무량
- **규약값**: y축 트랙 40 · 격자 120 · 막대 최대 92(= 120 − 값 줄 28) · 격자선 `rule` ·
  막대 모서리 `4px 4px 0 0`. 한 칸에 막대 여럿(`bars`), 값 글자는 그중 하나 위에.

### `FoldMark` (접힘 삼각)
- **파일**: `frontend/src/screens/MyStats.jsx`
- **대체**: 없음(신설). 「주별로 펴기」가 글자만 떠 있던 자리
- **소비 화면**: 내 업무량
- **규약값**: 12x12 `clipPath` 삼각, `currentColor`, 펴짐에서 `rotate(90deg)`.
  **아직 공용 부품이 아니다** — 아래 §3 참고.

### `overflowMenuItems` (팝오버 항목 목록)
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: `OverflowMenu` 안에 인라인으로 있던 항목 렌더링. 컴포넌트가 아니라 **배열을
  돌려주는 함수**다 — MUI `MenuList` 가 자식을 훑어 키보드 이동을 붙이므로 하나로 감싸면
  화살표 키가 죽는다
- **소비 화면**: `OverflowMenu` 를 쓰는 전 화면 · 부품 갤러리(열린 상태 붙박이)
- **규약값**: 항목 `CONTROL.menuItem` 32 · `FONT_SIZE.bodySm` · 파괴적 항목만 `error.strong`
  글자 + 위 1px `divider` 로 갈림. **실측**: 32px, `#87242B`, 구분선 1px.

### `KitGallery`
- **파일**: `frontend/src/screens/dev/KitGallery.jsx` (라우트 `/kit`)
- **대체**: 없음(신설). 부품을 확인하려면 그 부품을 쓰는 화면을 하나씩 열어야 했다
- **소비 화면**: 자기 자신(개발용). 사이드바 항목 없음
- **규약값**: 없음 — **값을 한 줄도 안 적는 것이 이 화면의 계약**이다. 모든 견본이 실제 부품을
  `import` 한다. 예외는 hover 견본 둘로, 거기서도 값이 아니라 **토큰 이름**(`primary.dark` ·
  `action.hover` · `text.secondary`)을 부른다 — `:hover` 는 정지 화면에 존재할 수 없다.
- **절 13 개**: 버튼 · 버튼 크기 · 검색과 필터 바 · 세그먼티드 · 팝오버와 모달 · 칸반 카드 ·
  상태 요약 카드 · 데이터 표 · 배지와 태그 · 폼 필드 · 빈 상태 넷 · 메시지 박스 1a ·
  조작기의 상태. 시안 문서의 11 절과 순서가 같고, 세그먼티드와 「조작기의 상태」 둘만 추가다.

---

## 2. 규약을 옮긴 부품 (모양이 바뀐 기존 부품)

### `Callout` — 메시지 박스 1a
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: `AssistantDrawer.jsx` · `Banners.jsx` · `StatusNotices.jsx` 의 MUI `Alert` 직접 사용 셋,
  그리고 **톤 이름 줄**(안내 · 성공 · 주의 · 오류)
- **소비 화면**: 전 화면(호출부 67곳)
- **규약값**: 면 `background.inset` · 1px `divider` · `RADIUS.sm` · px 14 / py 12(compact 10/7) ·
  아이콘 `remPx(ICON.mark)` 16 + `mt 3px` · 격자 `auto minmax(0,1fr) auto`.
  네 톤이 **같은 면**을 쓰고 아이콘 색만 다르다. **실측**: 면 `#F5F6FB`, 한 줄 상자
  **49.25px**(py 12+12 · 줄상자 24 · 테두리 1+1), compact 36.14px.
- **톤 이름은 아이콘의 접근 이름으로 옮겼다.** 화면 글자로는 안 선다. 예전에는 그 낱말이
  제목 줄로 올라와 ① 한 줄 상자의 높이가 두 배(98px)가 되고 ② 제목 자리를 일반 낱말이
  차지해 진짜 제목을 넣을 곳이 없었다. 색 외 단서(WCAG 1.4.1)는 **모양 넷 + 접근 이름**이
  맡는다. `title` 을 주면 그때만 제목 줄이 선다.

### `Badge` — 면을 가진 갈래
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 옛 `strong` 갈래(px 6 · `RADIUS.sm` · 0.875rem · 표지 점 포함)
- **소비 화면**: 전 화면
- **규약값**: 높이 22 · px 8 · `RADIUS.xs`(4) · `FONT_SIZE.micro` 0.75rem / 600 ·
  면과 글자는 `--badge-*` 세트. **면 갈래에는 표지 점이 없다.**
  면이 없는 갈래(표·목록)는 6px 점 + 낱말 그대로. **실측**: 22px, 면 `#E9EDF9`.

### `Tag` — 분류 알약
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 옛 태그(높이 20 · 배지와 **같은 옅은 면** · 테두리 없음 · 톤마다 다른 면)
- **소비 화면**: 문서 · 게시판 · 조직도 등 분류를 다는 전 화면
- **규약값**: 높이 `CONTROL.pill` 22 · px 8 · `RADIUS.sm` 6 · **흰 면 `background.paper` +
  1px `divider`** · `FONT_SIZE.micro` 0.75rem / **400**(D-486). 톤은 **글자만** 받는다.
  **실측**: 22px, `#FFFFFF`, 테두리 `#DCDFEC`, R6.
- 배지와 태그가 **면으로 갈린다**(확정 규약 §9). 예전에는 둘 다 옅은 면이라 한 줄에서
  「계획」 배지와 「Docker」 태그가 같은 부품으로 보였다. `badge-vs-tag.test.jsx` 가 계산된
  면과 테두리를 직접 잰다.

### `FilterChips` — 조건 칩
- **파일**: `frontend/src/ui/FilterBar.jsx` (`CONDITION_CHIP_SX`)
- **대체**: MUI `Chip` 기본 얼굴(중립 회색 필 · 30px · `RADIUS.sm`)
- **소비 화면**: 필터 바를 쓰는 전 목록 화면 · 부품 갤러리
- **규약값**: 높이 `CONTROL.chip` 26 · `RADIUS.full` · 면 `primary.light` · 글자 `primary.dark` ·
  1px `divider` · `FONT_SIZE.caption` 0.8125rem / 600.
  **실측**: 26px, 면 `#EFEDFA`, 글자 `#4742AB`, 모서리 999px.
- 면과 글자를 **강조색 파생**으로 둔다(`primary.light` = 강조색 10% + 판면). 고정 hex 를 쓰면
  보라 이외의 강조색에서 칩만 보라로 남는다. 같은 줄의 「필터 초기화」(30)와 높이가 **다른
  것이 의도**다 — 칩은 표지이고 그 옆은 단추다.

### `ErrorState` — 자리 축과 오류 표지
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 자리 축이 **아예 없던** 상태(호출부 87곳 전부가 전면 오류의 크기와 가운데 정렬)
- **소비 화면**: 전 화면. 지금 `layout="region"` 을 쓰는 곳은 부품 갤러리 하나다
- **규약값**: `layout` 은 `EmptyState` 와 같은 어휘(`page` 기본 · `region` · `card` · `inline`).
  `region` 은 왼쪽 정렬 · 위 정렬 · py 28 · 마스코트가 옆에 선다.
  제목 왼쪽에 `ICON.mark` 16 `error.main` 표지(접근 이름 「오류」), 그 아래 원인,
  그 아래 「다시 시도」와 `TechDetail` 접기, 마지막에 문의 번호.

### `SettingRow` — `compact` 갈래
- **파일**: `frontend/src/ui/adminKit.jsx`
- **대체**: 내 프로필의 자체 알림 줄(`py: 0.75` + 굵은 라벨)
- **소비 화면**: 내 프로필(알림 설정 · 방해금지). 관리자 줄은 옛 밀도 그대로
- **규약값**: 이름 `FONT_SIZE.bodySm` 0.875rem / 600 · 설명 `FONT_SIZE.micro` 0.75rem ·
  줄 **위** 1px `rule` · py 10 · gap 12 · **두 줄이 되지 않는다**(말줄임 + `title`).

### `SectionTitle` — 판 제목
- **파일**: `frontend/src/ui/kit.jsx` + `typography.sectionTitle`(`ui/theme.js`)
- **대체**: 옛 1.1875rem / 600
- **소비 화면**: 전 화면
- **규약값**: `FONT_SIZE.cardTitle` 1.0625rem / `FONT_WEIGHT.bold` 700 ·
  설명 `FONT_SIZE.caption` 0.8125rem `text.secondary`.

### `MuiSwitch` — 트랙 치수와 색
- **파일**: `frontend/src/ui/theme.js`
- **대체**: 옛 38x14 트랙 + MUI 기본 반투명 색
- **소비 화면**: 내 프로필(medium). 필터 스위치는 `size="small"` 로 따로 산다
- **규약값**: 트랙 34x20(폭 = 58 − 2x12, 높이 = 34 − 2x7) · 손잡이 흰색 16 · 안쪽 여백 2 ·
  켜짐 이동 14 · 켜짐 `primary.main` · 꺼짐 `dividerStrong`.
  **실측**: 켜짐 `#5A4FCF`, 꺼짐 `#BCC2D9`.

### `AccentPicker` 칩
- **파일**: `frontend/src/screens/settings/AccentPicker.jsx`
- **대체**: 옛 44px 높이 + 2px 테두리 칩
- **소비 화면**: 내 프로필
- **규약값**: `CONTROL.button` 34 · px 12 · `RADIUS.sm` · 색 동그라미 14 ·
  고른 것만 `background.inset` 면 + `primary.main` 테두리 + 체크.

### `UserAvatar` `xl`
- **파일**: `frontend/src/ui/UserAvatar.jsx`
- **대체**: 옛 96px
- **소비 화면**: 내 프로필 신원 머리
- **규약값**: 72px(`4.5rem`).

### 토큰 신설
- **파일**: `frontend/src/ui/theme.js`
- `CONTROL.tableHead/tableRow/tableGroupRow/tableFooter/tableCellDense` = 40/48/36/44/32
  (`tableRow` 는 오래 **정의만 있고 소비처가 0** 이었다 — 44에서 48로 옮기며 배선)
- `palette.rule` = light `#E5E8F3` / dark `#242A46` (`--color-rule`) — 판 **안쪽** 실선
- `ICON.mark` = 16 (다섯째 역할 슬롯)
- `SHADOW.*.raised` = light `0 1px 2px rgba(16,20,40,.10)`
- `FONT_SIZE.cardTitle` = 1.0625rem (여덟째 슬롯)
- `RADIUS.xs` = 4 (다섯째 슬롯)
- `CONTROL.pill` = 22 — 배지의 면 갈래와 태그가 **같은 값**으로 선다(둘은 면으로만 갈린다)
- `CONTROL.chip` = 26 — 조건 칩. 같은 줄의 글자 단추(30)보다 한 단 작다
- `CONTROL.menuItem` = 32 — 팝오버 항목 한 줄. MUI 기본은 48(dense 36)이다.
  `MuiMenuItem` 오버라이드는 `[breakpoints.up("sm")]` 안에서 **한 번 더** 적어야 한다 —
  MUI 의 기본 스타일이 그 미디어에서 `minHeight: auto` 로 되돌리고, 미디어 블록이 평범한
  선언보다 뒤에 실린다(실측: 한 번만 적었을 때 선언 32px / 계산값 0px)

---

## 3. 아직 흡수하지 못한 자체 구현

| 자리 | 파일 | 왜 남았나 | 처리 |
|---|---|---|---|
| 작업 보드 **백로그** 격자 | `screens/WorkBoard.jsx` | 끌어서 순서를 바꾼다. `DataTable` 에 끌기 개념이 없고, `rowWrapper` 로 감싸면 드래그와 60vh 가상화가 함께 깨진다(갈림길 A에서 소유자가 **끌기 우선**으로 확정) | 열 어휘와 치수만 표와 맞춘다. 흡수는 안 한다 |
| 접힘 삼각 `FoldMark` | `screens/MyStats.jsx` | 소비처가 아직 한 곳이다. 둘째 소비처가 생기는 날 `kit.jsx` 로 올린다 | 그때 승격 |
| 신원 사실 줄 `FactLine` · `Dot` | `screens/Profile.jsx` | 같은 이유. 「라벨 없이 값만 잇는 줄」은 상세 화면에도 쓸 자리가 있지만 아직 안 썼다 | 그때 승격 |
| 폼 고정 트랙 `FIELD_ROWS` | `screens/Profile.jsx` | 폼 규약(라벨 20 · 필드 `CONTROL.input` · 도움말 auto)의 첫 소비처다. **5-4 새 티켓**이 같은 트랙을 쓰므로 그때 공용으로 올린다 | 5-4에서 승격 |
| `Chat.jsx` 의 MUI `Alert` | `screens/Chat.jsx` | 메시지 박스 흡수 회차의 범위 밖이었다(채팅은 5-6) | 5-6에서 `Callout` 으로 |
| `kit.jsx` 안의 `MuiAlert` 둘 | `ui/kit.jsx:3351` · `:3458` | 폼 오류 줄과 토스트 알맹이다. 메시지 박스와 **다른 부품**이고 각자 자기 계약이 있다 | 흡수 대상 아님 |
| `StatusKpiStrip` | `ui/StatusKpi.jsx` | 회의 화면이 쓴다 — 세 칸(전체·완료·진행 중)에 「회차 전체의 숫자입니다」 캡션(`note`)을 단 **읽는 줄**이다. `StatusSummaryCard` 는 부분·위험을 함께 말하는 카드라 그 자리에 맞지 않는다(2026-09-14 판단, D-484) | 유지 |
| `ErrorState` 의 판 안 호출부 | 전 화면(87곳) | 자리 축(`layout`)은 생겼지만 기본값은 `page` 다 — 87곳을 한 회차에 뒤집지 않는다. 삼항 형태(`? <ErrorState`)가 31곳이고 그 대부분이 판·패널 안이다 | 화면 회차마다 그 화면 것을 `region` 으로 옮긴다 |
| 모달 머리와 발 | `ui/kit.jsx::ModalHeader` · `ModalFooter` | 제목이 `FONT_SIZE.sectionTitle` 19px / 800 이라 판 제목 규약(1.0625rem / 700)과 두 단 어긋난다. 발 줄은 면도 위 실선도 없다 | 아래 §4 D-11 · D-12 |
| 칸반 카드의 신호 어휘 | `ui/TicketFace.jsx` | 신호를 `variant="mark"`(아이콘만)로 그리고, 우선순위 `긴급` 만 면 있는 배지가 된다 — 한 카드 안에서 어휘가 갈린다 | 아래 §4 D-14 · D-15 |

---

## 4. 갤러리와 시안이 어긋난 자리 (실측)

(이력) 이 절은 「정본은 갤러리다」 시절의 대조표다. 핸드오프가 뒤집은 줄은 취소선 뒤에 새 값을 적었다(D-486).

### 확정 — 시안과 다르지만 갤러리가 맞다 (2026-09-08)

| # | 자리 | 시안 | 확정값 | 근거 |
|---|---|---|---|---|
| D-1 | 인라인 버튼 높이 | 28 | **30** (`CONTROL.buttonSm`) | 표 행이 버튼에 끌려 커지지 않게 정한 값이고 제품 전체가 그 값으로 선다 |
| D-5 | 상태 요약 카드의 전체 숫자 | 1.5rem | **1.75rem** (`FONT_SIZE.pageTitle`) | 그 카드를 지배하는 숫자 하나다 |
| D-6 | 검색창 폭 | 320 고정 | ~~`flex 1 1 20rem` · 최대 32rem~~ → **320 고정(필터 바 검색 슬롯)** | D-486 이 뒤집었다. 좁은 부모는 `layout="fill"` 100%, 1200 에서는 오른쪽 묶음이 통째로 줄바꿈 |
| D-8 | 필터 바 그릇 | `#F5F6FB` 함몰 판 | **판 없음** | 컨트롤이 왼쪽 절반만 쓰는데 판이 전폭이면 빈 판이 된다(지시 80). `FilterBar.jsx` 머리 주석이 실측 근거다 |
| D-9 | 빈 상태와 오류의 마스코트 | 없음 | **표지 크기로 옆에** | 핸드오프 README §10. 시안 문서 두 곳이 서로 달랐고 README 가 맞다 |
| D-10 | 판 제목 | 1.1875rem / 600 | **1.0625rem / 700** (`FONT_SIZE.cardTitle`) | 실측 17px / 700. 시안의 화면 카드도 같은 값이고 대조표 문서만 옛 값을 썼다 |

### 미처리 — 아직 판단이 안 났다

| # | 자리 | 시안 | 실측 | 판단 |
|---|---|---|---|---|
| D-11 | 모달 제목 | 1.0625rem / 700 | ~~19px / 800~~ → **1.0625rem / 700** | 처리(D-486) |
| D-12 | 모달 발 줄 | 면 `#F5F6FB` + 위 1px, 취소는 흰 면 + 테두리 34 | → **`ActionFooter`: 함몰면 + 위 실선, 취소 default** | 처리(D-486) |
| D-13 | 모달 닫기 | 28 | **30** (`CONTROL.buttonSm`) | 인라인 30 을 유지하기로 한 결정과 같은 값이다 |
| D-16 | 모달 모서리 | 10 | ~~14~~ → **8** (`RADIUS.md`) | 핸드오프 D-13 — 떠 있는 셋이 카드와 같은 8. `RADIUS.lg` 걷음 |
| D-17 | 팝오버 모서리 | 8 | ~~14~~ → **8** | 같은 이유 |
| D-14 | 칸반 신호 | 점 + 낱말 | ~~아이콘만~~ → **점 + 낱말**(`variant="dot"` 기본) | 처리(D-486) |
| D-15 | 칸반 우선순위 | 점 + 낱말 | ~~긴급만 면 배지~~ → **점 + 낱말**(`DotLabel`, 긴급은 600) | 처리(D-486) |
| D-18 | 칸반 카드 여백 | 12 14, 줄 사이 8, 발 위 1px | → **12/14 · 줄 8 · 발 위 실선** | 처리(D-486) |
| D-19 | 태그 굵기 | 400 | ~~500~~ → **400** | 처리(D-486) |
| D-20 | 조건 칩 글자색 | `#4038B8` | **`#4742AB`** (`primary.dark`) | 강조색 파생이라 사용자 강조색을 따라간다. 고정 hex 로 안 되돌린다 |
