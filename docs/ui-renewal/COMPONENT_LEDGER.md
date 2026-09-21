# 부품 대장 — 공통 컴포넌트 정본 · 소비처 · 예외

**정본(값)**: `design_handoff_clovirassist_ui/` — DECISIONS → README → RULES → ACCEPTANCE → GALLERY-FIXES
**정본(구현)**: `frontend/src/ui/**` Source
**구현 참고값**: `/kit` (`frontend/src/screens/dev/KitGallery.jsx`) — 실제 부품을 불러 쓴다
**결정**: `docs/DECISIONS.md` D-485(클로비 크기) · D-486(핸드오프 A 정본화) · D-487(보조 · 파괴 단추 테두리 · 다크 클로비 바탕)

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
| 페이지 동작 34 · 인라인 30 | `Button` | `ui/kit.jsx` | variant default(=secondary) · primary · ghost · danger · dangerConfirm, `size sm`, 라벨 한 줄 · 안 줄어듦 · `truncate` 만 말줄임, 보조 = 라이트 흰 면 + 경계선 · 다크 투명 면 + 강한 경계선, 파괴 = `error.line` 테두리 + `error.main` 글자(§0-17) | 83 | 버튼 | `handoff-kit-contract`, `long-text-contract`, `kit.test` |
| 알릴 사실(메시지 박스 1a) | `Callout` | `ui/kit.jsx` | 네 톤 같은 면 · 아이콘만 상태, 톤 이름 줄 없음, `compact` · `inline` · `bleed`, error=alert | 63 | 메시지 박스 | `kit.test`, `handoff-kit-contract` |
| 빈 상태 | `EmptyState` | `ui/kit.jsx` | layout page/card/region/inline, 클로비 page 132/112 · 판 72 · inline 없음(D-485) | 58 | 빈 상태와 오류 | `list-empty-two-faces`, `mascot-size-contract` |
| 조건 0건 / 자료 0건 | `ListEmptyState` | `ui/kit.jsx` | `filtered` 갈래 소유, 조건 지우기는 30 보조(§0-18 목록 판) | 7 | 이럴 때 이것 | `list-empty-two-faces` |
| 오류 상태 | `ErrorState` | `ui/kit.jsx` | layout 별 클로비(errorPage/errorRegion), 아이콘, 판 안 동작 30, 모르는 size/layout DEV 중지 | 61 | 빈 상태와 오류 | `kit.test`, `handoff-kit-contract` |
| 로딩 | `Skeleton` | `ui/kit.jsx` | kind section/table/chart/page | 61 | 빈 상태와 오류 | `skeleton-shapes` |
| 정해진 값(목록 밖) | `Badge` | `ui/kit.jsx` | 22 · 좌우 8 · R4 · 600 · 점 없음, 표 문맥에서는 점 + 낱말 | 53 | 배지와 태그와 점과 칩 | `badge-vs-tag` |
| 사람이 붙인 낱말 | `Tag` | `ui/kit.jsx` | 22 · R6 · 400 · 흰 면 + 테두리, 한 줄 말줄임 | 9 | 배지와 태그와 점과 칩 | `badge-vs-tag`, `long-text-contract` |
| 점 + 낱말(표 · 칸반 · 목록 행) | `DotLabel` | `ui/kit.jsx` | 7px 점 aria-hidden, 한 줄 · title, `size="caption"`(목록 행 · 카드 안 작은 글자 — 화면별 글자 덮어쓰기 대신) | 8 | 배지와 태그와 점과 칩 | `handoff-kit-contract` |
| 건수 미니 칩 | `CountChip` | `ui/kit.jsx` | 20 한 값, `compact` 18, `unread` Primary | 6 | 배지와 태그와 점과 칩 | `handoff-kit-contract` |
| 보기 전환 | `Segmented` | `ui/kit.jsx` | 34 = 28 + 3×2(선은 안쪽 그림자), roving tabindex + 화살표/Home/End | 8 | 세그먼티드 | `kit.test`, `handoff-kit-contract` |
| 데이터 표 | `DataTable` | `ui/kit.jsx` | 머리 40 · 행 ≥48 · `rowHeight=tall` ≥76 · 묶음 36 · 발 44, 제목만 왼쪽(머리 = 행), 빈 표 = EmptyState region, `placement` surface/card/plain · `list` · `selection` · `note`(§0-18 목록 판) | 25 | 데이터 표, 목록 화면 조합 | `column-types`, `datatable-*`, `list-surface` |
| 판 | `Card` | `ui/kit.jsx` | 여백 20, 판 안의 판은 여백까지 사라짐 | 54 | 모든 절 | `density-contract` |
| 표가 아닌 목록의 판 | `ListCard` | `ui/kit.jsx` | 자기 안을 자르지 않음(판 안 고정 머리). 표를 담는 목록은 쓰지 않는다 — `DataTable placement="surface"` | 1 | — | `kit.test` |
| 행 동작 | `RowActions` | `ui/kit.jsx` | ≤2 → 30 보조/파괴 단추(채움 없음), >2 → `OverflowMenu sm` 하나, `icon` 항목은 30 아이콘 단추, `data-row-actions` | 7 | 데이터 표, 목록 화면 조합 | `row-actions` |
| 제목 칸 | `TitleCell` | `ui/kit.jsx` | 링크색 `primary.dark` 600 한 줄 · 말줄임 · title, `onOpen` 단추 · `href` 앵커 · `link` 색만 · 셋 다 없으면 잉크 | 5 | 목록 화면 조합 | `list-surface`, `theme-link-contrast` |
| 선택 묶음 | `SelectionBar`(별칭 `BulkActions`) | `ui/kit.jsx`, `ui/bulkSelect.jsx` | role=toolbar 「일괄 작업」, 「N{단위} 선택」 · 일괄 동작 30 · 「해제」, 선택 0 이면 안 그림, `data-list-selection`(채움 하나는 이 묶음 몫) | 0(표가 그린다) | 목록 화면 조합 | `bulk-actions-toolbar-role`, `list-surface` |
| 구획 제목 | `SectionTitle` | `ui/kit.jsx` | 1.0625rem/700 + 설명 | 22 | 모든 절 | `heading-order` |
| 모달 | `Modal` | `ui/kit.jsx` | 제목 17/700 · 닫기 30 · 모서리 8 · 발 ActionFooter, `tone=danger` 표지 | 23 | 팝오버와 모달 | `modal-*`, `handoff-kit-contract` |
| 폼 모달 | `FormModal` | `ui/kit.jsx` | Modal + FormField | 11 | — | `form-*` |
| 카드 발 · 모달 발 | `ActionFooter` | `ui/kit.jsx` | 함몰면 + 위 실선, 오른쪽 정렬 gap 8, `extra` 왼쪽, 주인 하나(`data-action-footer`) | 10 | 팝오버와 모달, 폼 필드 | `handoff-kit-contract` |
| 확인 대화 | `useConfirm` | `ui/kit.jsx` | danger 는 표지 + 취소 기본 포커스 + dangerConfirm | 40 | 팝오버와 모달 | `handoff-kit-contract`, `kit.test` |
| 토스트 | `useToast` | `ui/kit.jsx` | 성공 · 정보만, 잉크 면(다크 함몰면), 모서리 8 | 50 | 빈 상태와 오류 | `toast-announce` |
| 팝오버 동작 목록 | `overflowMenuItems` | `ui/kit.jsx` | 32 항목, 파괴적만 error 글자 + 위 선 | 3 | 팝오버와 모달 | `kit.test` |
| 폼 칸 | `FormFieldCell` | `ui/kit.jsx` | 라벨 20 · 필드 36(바닥 — 칩이 접히면 자란다) · 도움말 auto, 오류가 도움말 자리 | 1 | 폼 필드 | `handoff-kit-contract`, `new-ticket-layout` |
| 속성 줄 | `MetaBar` | `ui/kit.jsx` | 키/값 | 5 | — | `metabar-hierarchy` |
| 페이지 머리 | `PageHeader` | `ui/kit.jsx` | 제목 28/700 + 설명 + 동작 34 | 34 | 머리 | `page-header-*` |
| 필터 바 그릇 | `FilterSurface` | `ui/FilterBar.jsx` | 판 없음 · 아래 실선 · 줄 칸 문맥 제공 | 16 | 검색과 필터 바 | `filter-row-width`, `handoff-kit-contract` |
| 필터 바 도구 줄 | `ToolbarRow` | `ui/FilterBar.jsx` | 검색 슬롯 320(직계), 좁으면 100% | 12 | 검색과 필터 바 | `handoff-kit-contract` |
| 필터 바 내용 줄 | `FilterRow` | `ui/FilterBar.jsx` | 검색 슬롯 320(직계), 위 정렬 | 10 | 검색과 필터 바 | `filter-row-width` |
| 필터 바 오른쪽 묶음 | `ToolbarEnd` | `ui/FilterBar.jsx` | 통째로 줄바꿈(nowrap · 안 줄어듦) | 5 | 검색과 필터 바 | — |
| 결과 수 | `ResultLine` | `ui/FilterBar.jsx` | 「전체 N건」(조건 없을 때) | 11 | 검색과 필터 바 | `filter-row-width` |
| 조건 칩 줄 | `FilterChips` | `ui/FilterBar.jsx` | 26 · 알약 · 틴트 · X | 2 | 검색과 필터 바 | `filter-row-width` |
| 조건 줄(둘째 줄) | `FilterConditionLine` | `ui/FilterBar.jsx` | 조건이 있을 때만 · 위 실선 · 「조건 N개, 결과 M건」 | 1 | 검색과 필터 바 | `handoff-kit-contract` |
| 필터 켬/끔 · 패널 열기 | `FilterToggle` | `ui/FilterBar.jsx` | 34 버튼, aria-pressed / aria-expanded, 눌림만 함몰면 | 6 | 검색과 필터 바 | `handoff-kit-contract` |
| 검색창 | `SearchBox` | `ui/filters.jsx` | 줄 칸 34, `layout=fill` 100% | 12 | 검색과 필터 바 | `handoff-kit-contract` |
| 닫힌 축 셀렉트 | `FilterSelect` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름, 값 한 줄 · title | 14 | 검색과 필터 바 | `filter-form-layout`, `long-text-contract` |
| 늘어나는 축 고르개 | `EntityCombobox` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름, 목록은 PickerOption, `myId` 맨 위 | 13 | 검색과 필터 바, 팝오버와 모달 | `entity-combobox*` |
| 자유 입력 필터 | `DebouncedTextField` | `ui/filters.jsx` | 줄 칸 34 + 접두 이름 | 4 | — | `filters.test` |
| 부서 필터 | `DepartmentFilter` | `ui/filters.jsx` | 경로 라벨 | 2 | — | `department-filter` |
| 회차 팀 문맥 | `TeamSelect` | `ui/filters.jsx` | 「전체」 없음, 후보 < 2 면 안 그림 | 2 | — | `work-board-team-context` |
| 검색 팝오버 항목 | `PickerOption` | `ui/filters.jsx` | 32 한 줄 · 체크 · title | 2 | 팝오버와 모달 | `handoff-kit-contract` |
| 사람 고르기 | `UserPicker` | `ui/UserPicker.jsx` | 아바타 22 + 이름 + 소속, (나) 표시 | 2 | 팝오버와 모달 | `pickers.test` |
| 프로젝트 고르기 | `ProjectPicker` | `ui/ProjectPicker.jsx` | 코드 보조 | 2 | — | `pickers.test` |
| 태그 고르기 | `TagPicker` | `ui/TagPicker.jsx` | renderTags 칩(원재료 호스트) | 3 | — | `tag-picker*` |
| 상태 요약 | `StatusSummaryCard` | `ui/StatusKpi.jsx` | 카드 하나 · 비율 바는 total 일 때만 · 값 하나 갈래 | 11 | 상태 요약 | `status-summary-card`, `handoff-kit-contract` |
| 독립 측정값 줄 | `StatusKpiStrip` | `ui/StatusKpi.jsx` | `note` 캡션 | 7 | 상태 요약 | `status-kpi-note` |
| 칸반 카드 | `TicketFace` | `ui/TicketFace.jsx` | 12/14 · 줄 8 · 발 위 실선, 우선순위와 신호 점 + 낱말 | 2 | 칸반 카드 | `ticket-signals`, `handoff-kit-contract` |
| 신호 표시 | `TicketSignals` | `ui/TicketSignals.jsx` | 기본 dot, 상세 머리 pill, 좁은 표 칸 mark | 4 | 칸반 카드 | `ticket-signals` |
| 사람 얼굴 | `UserAvatar` | `ui/UserAvatar.jsx` | xs 22 · inline 20 · sm 24 · md 30 · lg 40 · xl 72 | 12 | 데이터 표 | — |
| 사람 한 줄 | `PersonLine` | `ui/UserAvatar.jsx` | 얼굴 + 이름 말줄임 | 3 | — | — |
| 페이지 탭 | `TabShell` | `ui/TabShell.jsx` | 라우트 탭 | 3 | — | `settings-shell` |
| 설정 줄 | `SettingRow` | `ui/adminKit.jsx` | `compact` 한 줄 | 3 | 조작기의 상태 | — |
| 상태 줄 목록 | `StatusList` | `ui/adminKit.jsx` | 이름 + 슬롯 | 4 | — | — |
| 회의 갈래 칩 | `DiscussBucketRow` | `ui/DiscussBucket.jsx` | 알약 + StatusDot, tablist · roving tabindex | 1 | — | `sprint-meeting` |
| 티켓 미리보기 | `TicketPeek` | `screens/TicketPeek.jsx` | Modal md, 발 → ActionFooter(B) | 2 | — | `ticket-peek` |

소비처 파일 목록:

- `Button`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `app/AssistantDrawer.jsx`, `app/Banners.jsx`, `app/NotificationBell.jsx`, `app/StatusNotices.jsx`, `app/TopBrand.jsx`, `app/Tour.jsx`, `app/UserMenu.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketFilterBar.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/MessageThread.jsx`, `screens/chat/TicketCard.jsx`, `screens/chat/WelcomeStatus.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/game-room/GameStage.jsx`, `screens/knowledge/TaxonomyManager.jsx`, `screens/ops/DiagnosticActions.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/settings/StructuredObjectFields.jsx`, `ui/BlockEditor.jsx`, `ui/DefaultAvatarPicker.jsx`, `ui/EditableBody.jsx`, `ui/FilterBar.jsx`, `ui/InfiniteScroll.jsx`, `ui/SavedViews.jsx`, `ui/TabShell.jsx`, `ui/bulkSelect.jsx`, `ui/columnFilter.jsx`
- `Callout`: `app/AssistantDrawer.jsx`, `app/Banners.jsx`, `app/CommandPalette.jsx`, `app/NotificationBell.jsx`, `app/ScopeBar.jsx`, `app/StatusNotices.jsx`, `app/UserMenu.jsx`, `screens/AiWorkspace.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/knowledge/NewDocumentModal.jsx`, `screens/knowledge/TaxonomyManager.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/StructuredObjectFields.jsx`, `ui/DocBody.jsx`, `ui/EditableBody.jsx`, `ui/SavedViews.jsx`
- `EmptyState`: `app/AdminRoutes.jsx`, `app/AssistantDrawer.jsx`, `app/CommandPalette.jsx`, `app/NotificationBell.jsx`, `app/StatusNotices.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectMetrics.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketFilterBar.jsx`, `screens/TicketHistory.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/ResultsRail.jsx`, `screens/chat/WelcomeStatus.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/JobQueuePanel.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `ui/DocBody.jsx`, `ui/TabShell.jsx`
- `ListEmptyState`: `screens/ChatRooms.jsx`, `screens/Knowledge.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Projects.jsx`, `screens/Trash.jsx`, `screens/chat/ConversationSidebar.jsx`
- `ErrorState`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `app/NotificationBell.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketHistory.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/WorkSummary.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `ui/TabShell.jsx`
- `Skeleton`: `app/AdminRoutes.jsx`, `app/App.jsx`, `app/AppShell.jsx`, `app/AssistantDrawer.jsx`, `app/NotificationBell.jsx`, `app/UserRoutes.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LegacyDocRedirect.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectMetrics.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketHistory.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/WorkSummary.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `ui/EditableBody.jsx`, `ui/TabShell.jsx`
- `Badge`: `app/NotificationBell.jsx`, `screens/Activity.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/Dashboard.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/chat/TicketCard.jsx`, `screens/data-screen/SummaryView.jsx`, `screens/data-screen/columnHelpers.jsx`, `screens/game-room/MembersList.jsx`, `screens/game-room/RpsViews.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/registry/authoring.js`, `screens/registry/governance.js`, `screens/registry/notifications.js`, `screens/registry/platform.js`, `screens/settings/SettingsMain.jsx`, `screens/ticket-meta.jsx`, `ui/SavedViews.jsx`, `ui/adminKit.jsx`, `ui/charts/BarSeries.jsx`
- `Tag`: `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/ProjectDocuments.jsx`, `screens/chat/MessageThread.jsx`, `screens/knowledge/documentColumns.jsx`, `screens/settings/SettingsMain.jsx`, `screens/settings/StructuredObjectFields.jsx`
- `DotLabel`: `screens/ChatRooms.jsx`, `screens/SetupWizard.jsx`, `screens/chat/TicketCard.jsx`, `screens/knowledge/documentColumns.jsx`, `ui/TicketFace.jsx`, `ui/TicketSignals.jsx`
- `Segmented`: `screens/Activity.jsx`, `screens/AssistantPanel.jsx`, `screens/Knowledge.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/Trash.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/TaxonomyManager.jsx`
- `DataTable`: `screens/Board.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectWbs.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/StorageProviders.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/JobQueuePanel.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`
- `Card`: `app/AdminRoutes.jsx`, `app/AppShell.jsx`, `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/OrgTree.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/SystemOps.jsx`, `screens/TeamChatWidget.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketHistory.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/game-room/ChatPanel.jsx`, `screens/game-room/MembersList.jsx`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/AccentPicker.jsx`, `screens/settings/SettingVersions.jsx`, `ui/TabShell.jsx`, `ui/TicketFace.jsx`
- `ListCard`: `screens/Activity.jsx`, `screens/Board.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/MailStatus.jsx`, `screens/Offboarding.jsx`, `screens/Projects.jsx`, `screens/StorageProviders.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/settings/SettingsMain.jsx`
- `SectionTitle`: `screens/AssistantPanel.jsx`, `screens/BoardPost.jsx`, `screens/CommentThread.jsx`, `screens/DevReport.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/LlmConsole.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectWbs.jsx`, `screens/ProjectWeekly.jsx`, `screens/Sprint.jsx`, `screens/TicketAttachments.jsx`, `screens/TicketHistory.jsx`, `screens/TicketPeek.jsx`, `screens/ops/Maintenance.jsx`, `screens/settings/AccentPicker.jsx`, `ui/EditableBody.jsx`, `ui/adminKit.jsx`
- `Modal`: `app/Tour.jsx`, `screens/Board.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/SchedulerCalendar.jsx`, `screens/SprintLifecycle.jsx`, `screens/TicketPeek.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/knowledge/NewDocumentModal.jsx`, `screens/knowledge/TaxonomyManager.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `ui/AvatarCropDialog.jsx`, `ui/DefaultAvatarPicker.jsx`, `ui/SavedViews.jsx`
- `FormModal`: `screens/AiWorkspace.jsx`, `screens/Knowledge.jsx`, `screens/Project.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/org/orgModals.jsx`
- `useConfirm`: `app/NotificationBell.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/ChatRooms.jsx`, `screens/CommentThread.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/useGameRoomController.js`, `screens/ops/Maintenance.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`, `screens/useChat.js`, `ui/EditableBody.jsx`, `ui/SavedViews.jsx`
- `useToast`: `app/NotificationBell.jsx`, `screens/AiWorkspace.jsx`, `screens/AssistantPanel.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/ChatRoom.jsx`, `screens/ChatRoomMembers.jsx`, `screens/CommentThread.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/Games.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/LlmConsole.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectWeekly.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/StorageProviders.jsx`, `screens/SystemOps.jsx`, `screens/Ticket.jsx`, `screens/TicketAttachments.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/chat/links.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/game-room/useGameRoomController.js`, `screens/ops/Diagnostics.jsx`, `screens/ops/Maintenance.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`, `screens/org/orgModals.jsx`, `screens/settings/SettingVersions.jsx`, `screens/settings/SettingsMain.jsx`, `screens/useChat.js`, `ui/EditableBody.jsx`, `ui/SavedViews.jsx`
- `MetaBar`: `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/Ticket.jsx`, `screens/TicketPeek.jsx`, `screens/data-screen/SummaryView.jsx`
- `PageHeader`: `screens/Activity.jsx`, `screens/AiWorkspace.jsx`, `screens/Board.jsx`, `screens/BoardPost.jsx`, `screens/Chat.jsx`, `screens/ChatRooms.jsx`, `screens/Dashboard.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/GameRoom.jsx`, `screens/Games.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/Knowledge.jsx`, `screens/KnowledgeDoc.jsx`, `screens/MailStatus.jsx`, `screens/MyApprovals.jsx`, `screens/MyStats.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Profile.jsx`, `screens/Project.jsx`, `screens/Projects.jsx`, `screens/Search.jsx`, `screens/SetupWizard.jsx`, `screens/Sprint.jsx`, `screens/TeamTickets.jsx`, `screens/Ticket.jsx`, `screens/Trash.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/ops/Diagnostics.jsx`, `ui/TabShell.jsx`
- `FilterSurface`: `screens/Activity.jsx`, `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/settings/SettingsMain.jsx`
- `ToolbarRow`: `screens/Activity.jsx`, `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Search.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/settings/SettingsMain.jsx`
- `FilterRow`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/data-screen/SubListDrawer.jsx`
- `ToolbarEnd`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/SchedulerCalendar.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/settings/SettingsMain.jsx`
- `ResultLine`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/Knowledge.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/ProjectDocuments.jsx`, `screens/ProjectTickets.jsx`, `screens/Projects.jsx`, `screens/Search.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`
- `FilterChips`: `screens/Board.jsx`, `screens/TicketFilterBar.jsx`
- `SearchBox`: `screens/Board.jsx`, `screens/ChatRooms.jsx`, `screens/DataScreen.jsx`, `screens/Offboarding.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/Search.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/chat/ConversationSidebar.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`
- `FilterSelect`: `screens/Board.jsx`, `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/OrgConsole.jsx`, `screens/Projects.jsx`, `screens/Sprint.jsx`, `screens/SprintLifecycle.jsx`, `screens/TicketFilterBar.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/WorkBoard.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `ui/columnFilter.jsx`
- `EntityCombobox`: `screens/DataScreen.jsx`, `screens/Integrity.jsx`, `screens/MyTickets.jsx`, `screens/Project.jsx`, `screens/SchedulerCalendar.jsx`, `screens/Sprint.jsx`, `screens/TicketFilterBar.jsx`, `screens/WorkBoard.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `ui/ProjectPicker.jsx`, `ui/UserPicker.jsx`, `ui/columnFilter.jsx`, `ui/kit.jsx`
- `DebouncedTextField`: `screens/DataScreen.jsx`, `screens/TicketFilterBar.jsx`, `screens/data-screen/SubListDrawer.jsx`, `ui/columnFilter.jsx`
- `DepartmentFilter`: `screens/Projects.jsx`, `screens/TeamTickets.jsx`
- `TeamSelect`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `PickerOption`: `screens/chat/peoplePicker.jsx`, `ui/UserPicker.jsx`
- `ProjectPicker`: `screens/KnowledgeDoc.jsx`, `screens/knowledge/NewDocumentModal.jsx`
- `TagPicker`: `screens/KnowledgeDoc.jsx`, `screens/knowledge/KnowledgeFilterBar.jsx`, `screens/knowledge/NewDocumentModal.jsx`
- `StatusSummaryCard`: `screens/DataScreen.jsx`, `screens/DevReport.jsx`, `screens/Home.jsx`, `screens/Integrity.jsx`, `screens/MailStatus.jsx`, `screens/MyStats.jsx`, `screens/Projects.jsx`, `screens/SchedulerCalendar.jsx`, `screens/SetupWizard.jsx`, `screens/data-screen/SummaryView.jsx`, `screens/ops/Diagnostics.jsx`
- `StatusKpiStrip`: `screens/OrgConsole.jsx`, `screens/Sprint.jsx`, `screens/data-screen/SummaryView.jsx`, `screens/ops/JobQueuePanel.jsx`, `screens/ops/ServiceStatusPanel.jsx`, `screens/org/DeptDetailPanel.jsx`, `screens/org/OrgDetailPanel.jsx`
- `TicketFace`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `TicketSignals`: `screens/MyTickets.jsx`, `screens/WorkBoard.jsx`, `screens/ticket-meta.jsx`, `ui/TicketFace.jsx`
- `UserAvatar`: `app/UserMenu.jsx`, `screens/Board.jsx`, `screens/ChatPane.jsx`, `screens/ChatRoomMembers.jsx`, `screens/KnowledgeDoc.jsx`, `screens/Profile.jsx`, `screens/ProjectDocuments.jsx`, `screens/Sprint.jsx`, `screens/chat/peoplePicker.jsx`, `screens/knowledge/documentColumns.jsx`, `screens/org/DeptDetailPanel.jsx`, `ui/UserPicker.jsx`
- `PersonLine`: `screens/MyTickets.jsx`, `screens/ticket-meta.jsx`, `ui/TicketFace.jsx`
- `TabShell`: `app/AdminRoutes.jsx`, `screens/Project.jsx`, `screens/settings/SettingsShell.jsx`
- `SettingRow`: `screens/Integrity.jsx`, `screens/Profile.jsx`, `screens/SystemOps.jsx`
- `StatusList`: `screens/Dashboard.jsx`, `screens/WorkSummary.jsx`, `screens/ops/Diagnostics.jsx`, `screens/ops/ServiceStatusPanel.jsx`
- `DiscussBucketRow`: `screens/Sprint.jsx`
- `TicketPeek`: `screens/Sprint.jsx`, `screens/WorkBoard.jsx`
- `CountChip`: `app/AppShell.jsx`, `app/StatusNotices.jsx`, `screens/ChatRooms.jsx`, `screens/Integrity.jsx`, `screens/Search.jsx`, `screens/Sprint.jsx`
- `ActionFooter`: `app/Tour.jsx`, `screens/DataScreen.jsx`, `screens/MyTickets.jsx`, `screens/Offboarding.jsx`, `screens/TicketPeek.jsx`, `screens/Users.jsx`, `screens/UsersBulk.jsx`, `screens/data-screen/SubListDrawer.jsx`, `screens/settings/SettingEditor.jsx`, `screens/settings/SettingVersions.jsx`
- `overflowMenuItems`: `app/UserMenu.jsx`, `screens/ChatPane.jsx`, `ui/SavedViews.jsx`
- `FormFieldCell`: `screens/MyTickets.jsx`
- `FilterConditionLine`: `screens/knowledge/KnowledgeFilterBar.jsx`
- `FilterToggle`: `screens/ProjectTickets.jsx`, `screens/Projects.jsx`, `screens/TeamTickets.jsx`, `screens/Users.jsx`, `screens/WorkBoard.jsx`, `screens/settings/SettingsMain.jsx`
- `UserPicker`: `screens/MyTickets.jsx`, `screens/Offboarding.jsx`

---

## 0-1. 채팅 전용 시각 규격 (소유자 확정 — 공통 토큰으로 접지 않는다)

핸드오프 README §C · RULES §9 의 채팅 값은 공통 토큰의 가장 가까운 값으로 바꾸지 않는다(소유자, 2026-09-14):
상대 아바타 34 · 머리 참여자 스택 26 / −8 겹침 · 말풍선 모서리 12(연결 모서리 4) · 말풍선 최대 폭 68% ·
입력창 모서리 10 · 도구 / 보내기 30 · 목록 296 · 시각 글자 0.6875rem · 날짜 구분선 폭 28rem(UI 3차 C-6). 값은 `frontend/src/ui/chat.js::CHAT`
한 곳에 둔다 — 소비처: 채팅방 전부(`ChatRooms` 목록 폭 · `ChatRoom` 머리 스택 · `ChatPane` 말풍선 · 연결 모서리 · 최대 폭 ·
시각 · 입력 상자 · 도구), AI 도우미는 말풍선 모서리 · 입력 모서리 10 · 도구 30 · 입력 중 말풍선 12(P-26 · UI 3차 C-6). 날짜 구분선은 두 화면이
같은 부품(`ui/ChatDaySeparator.jsx`)이다. 글자 크기 리터럴 검사(`check_typography_literals.py`)는
`CHAT.*` 를 토큰 경로로 인정한다.

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
| `Chip` | `Badge` · `Tag` · `CountChip` · `FilterConditionLine` 조건 칩(Autocomplete `renderTags` 칩은 `TagPicker` 가 호스트 — 필터 바 줄 칸에서는 칩 대신 `RowSummary`) |
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
| `ui/FilterBar.jsx` | `Chip` | `FilterConditionLine` 조건 칩의 알맹이 | 정본 부품 자신이다 |
| `ui/TagPicker.jsx` | `Chip` | Autocomplete `renderTags` 선택 칩 | MUI Autocomplete 가 지우기 · 키보드 이동을 그 칩에 건다 |
| `screens/AiWorkspace.jsx` | `Chip` | 인용 번호(1, 2 …) | 건수도 사람이 붙인 낱말도 아닌 순번 표지다(계획 표 2) |
| `screens/Board.jsx` | `Chip` | 이모지 반응 토글(`aria-pressed` + 누른 수) | 누르면 켜고 끄는 반응이고 높이는 작은 단추(30)에 맞췄다(계획 표 2) |
| `app/NotificationBell.jsx` | `Badge` | MUI 배지로 종 아이콘 위에 네 상태(숫자 · 조용 · 오류 · 불러오는 중)를 겹친다 | 아이콘에 겹쳐 서는 표지라 칩 줄에 놓이지 않는다(계획 §0-11) |
| `app/AppShell.jsx` | `Button` | 사이드바 위 「사용자 · 관리자」 화면 전환 스위치(`ConsoleSwitch`) | 셸 반전 트랙(`sidebar.*` 토큰) 위의 이동 링크 둘(`aria-current`)이다 — 판 위 34 단추도, 보기 전환 `Segmented`(`tablist`)도 아니다 |
| `app/TopBrand.jsx` | `Button` | 상단바 브랜드 락업(홈으로) | 로고 그림이 곧 이름인 셸 링크라 테두리 · 높이를 가진 단추 어휘가 맞지 않는다 |
| `app/UserMenu.jsx` | `Button` · `Menu` | 상단바 이름 + 아바타 트리거와 그 팝오버 — 항목은 `overflowMenuItems` | 트리거가 셸 토큰 위 이름 + 아바타 알약이라 `OverflowMenu`(⋯ 아이콘)로 설 수 없고, 팝오버 머리에 내 소속 블록이 선다 |
| `ui/SavedViews.jsx` | `Badge` · `Menu` | 저장 안 한 필터 점 표지와 저장된 뷰 목록 — 저장 항목은 `overflowMenuItems` | 뷰 한 줄에 이름 · 조건 요약 · 지우기 단추가 함께 서서 라벨만 받는 항목 정본으로 설 수 없다. 점은 아이콘에 겹치는 표지다 |
| `screens/ChatPane.jsx` | `Menu` | 멘션 고르기(@ 도구가 여는 팝오버) — 항목은 `overflowMenuItems` | 트리거가 입력창 도구(@)라 `OverflowMenu`(⋯)로 설 수 없다 |
| `ui/columnFilter.jsx` | `Button` | 열 필터 팝오버의 「이 조건 지우기」 | `kit.jsx` → `TableHeaderCell` → `columnFilter` 순으로 불려 kit `Button` 을 가져오면 순환 import 가 된다 |
| `ui/InlineEdit.jsx` | `Menu` | 표 칸 인라인 편집의 값 목록(`role=option`) | 고르는 값 목록(listbox)이라 동작 메뉴 항목이 아니다(계획 §0-11 「InlineEdit listbox 는 B」) |
| `screens/dev/KitGallery.jsx` | `MenuList` | 열린 팝오버 항목 붙박이 견본 | 대조표가 실제 `overflowMenuItems` 를 열린 채로 세우는 틀이다 |
| `app/CommandPalette.jsx` | `Dialog` · `DialogContent` · `LinearProgress` | 명령 팔레트(Ctrl+K) 창과 찾는 중 줄 | 머리 · 발 · 제목이 없는 검색 창이라 모달 3단 계약과 다르다(계획 §0-11 대장 예외) |
| `app/LoginHandoff.jsx` | `LinearProgress` | 로그인 넘김 진행 줄 | 화면 전체가 넘어가는 동안의 진행 표시라 단추 `loading` 자리가 없다(계획 §0-11 대장 예외) |
| `screens/GameRoom.jsx` | `Paper` | 놀이방 진행 현황 줄(카운트다운 · 제출 현황) | 게임 무대는 판 · 표 · 폼과 다른 놀이 면이다(계획 표 2 「게임 무대 면 · 알약 — 대장 예외 묶음」) |
| `screens/game-room/GameStage.jsx` | `Paper` | 팀 결과 · 사다리 결과 · 숫자와 가위바위보 공개 타일(승자 강조 · 떠오르는 움직임) | 게임 무대 면이다(위와 같은 묶음) |
| `screens/game-room/RpsViews.jsx` | `Paper` | 가위바위보 선택 줄 · 대진 줄 | 게임 무대 면이다(위와 같은 묶음) |
| `screens/game-room/Scoreboard.jsx` | `Paper` | 순위 줄(자동 번호 · 점수) | 게임 무대 면이다(위와 같은 묶음) |
| `screens/game-room/StageShared.jsx` | `Paper` | 결과 무대(축하 그림 + 클로비) | 게임 무대 면이다(위와 같은 묶음) |

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
  허용한 치환 목록 밖이다. 새 티켓은 C(§0-14), 문서 목록은 D(§0-15), 채팅방은 E(§0-16) 에서 옮겼다.

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

## 0-9. 필터 바 — 칸 34 · 칸 안 이름 · 켬/끔 단추 (핸드오프 README §3 · RULES §3 · ACCEPTANCE D1~D4)

- **필터 바 안의 조건은 전부 줄 칸이다.** 게시판 정렬 · 카테고리 · 상태(칩 토글 줄이던 것 — 계획 P-20), 개발자 리포트
  연도 · 월, 감사 징후 시작 · 종료 시각(`datetime-local`), 하위 목록 서랍의 조건 줄이 `FilterSurface` 안의
  `FilterSelect` · `DebouncedTextField` 로 선다. 「전체」가 답이 아닌 축(정렬 · 연도 · 월)은 `FilterSelect noAllOption`.
  문서 목록의 태그 고르개(`TagPicker`)도 줄 안에서는 같은 칸이다(`useRowCell` · `PrefixLabel` 을 `filters.jsx` 와 같이 쓴다).
- **켬/끔은 `FilterToggle`(34 중립 단추, `aria-pressed`)** — 보관한 프로젝트 포함 · 완료, 취소 포함(팀 티켓 ·
  프로젝트 티켓 탭) · 보관된 계정 보기 · 기술 정보(설정 키) 보기 · 작업 보드의 내 티켓만 · 보류 펴기/접기 ·
  완료와 취소 보기/감추기(보호 화면 — 같은 라벨 · 같은 눌림 상태).
- **검색 칸** — 통합 검색은 필터 바의 검색 슬롯(320)에 제출 단추가 붙는다(`SearchBox immediate`: 제출형이라 글자마다
  값을 부모가 든다). 채팅방 목록(296)은 `SearchBox layout="fill" immediate`.
- **결과 줄** — UI 3차에서 목록 위 단독 결과 줄을 걷었다(§0-18). 화면이 쓰던 결과 문장은 목록 끝 줄로 옮겼고(프로젝트
  문서 탭 「총 N건 가운데 …」), 통합 검색의 결과 요약만 `ResultLine text` 로 남는다(조합 예외).
- 내 활동의 종류 고르기는 판 안 토글 단추 묶음에서 필터 바 위 `Segmented` 로 옮겼다(B-7 과 같은 줄).
- **남긴 자리**: `DateField`(MUI X 날짜 고르개)는 줄 칸 모양이 없다 — 지금 날짜 조건을 쓰는 목록 · 서랍이 없어(registry
  `type: "date"` 소비처 0) 부품을 넓히지 않았다. 사용자 일괄 지정 줄(`UsersBulk`)은 필터가 아니라 일괄 동작 줄이고
  「값」 칸이 고르기 전 자리표시자를 요구하는 폼 칸이라 B-8(폼 라벨)에서 본다.

## 0-10. 표 — DataTable 과 남긴 격자 (ACCEPTANCE E7)

- **옮긴 것**: `ops/LogList`(작업 큐의 최근 작업 오류 · 진단의 설치처 설정) → `DataTable`, 부품 파일은 소비처 0 이라
  걷었다. 프로젝트 WBS 의 「트리에 넣지 못한 작업」 → `DataTable`(작업 · 이유). 문장 열은 `overflow: "word"` 로
  줄을 바꾼다(말줄임으로 이유가 잘리지 않게).
- `DataTable empty="…"` 문자열은 A 에서 표가 스스로 `EmptyState region` 을 세우게 됐다 — 호출부를 바꿀 것이 없다
  (조직 정합성 관리자 표). UI 3차부터 목록 화면의 빈 상태는 `emptyState` 로 표에 넘겨 목록 판 안(여백 20)에 선다(프로젝트 · 휴지통 ·
  게시판 · 사용자 · 문서 · DataScreen 조건 0건). 조건 없이 화면 전체가 빈 자리만 판 밖 page 빈 상태다(§0-18 목록 판 조합).
- **남긴 격자**(표 모양이지만 표가 아닌 것): 작업 보드 백로그(계획 P-17 · D-473 — 끌어 옮기기 · 가상 목록 · 카드 줄),
  프로젝트 WBS 나무 줄(들여쓰기 트리), 예약 달력(달력 격자 `role=grid`), 게임 대진표, 채팅 방 목록 행.
- **행 초점 고리(G)**: `onRow` 가 있는 행은 Tab 으로 닿고 Enter 로 여는데, MUI `TableRow` 가 뿌리에 `outline: 0` 을 걸어 전역
  `:focus-visible` 고리를 지우고 있었다(계산 외곽선 `none 0px`). 표가 `tbody tr:focus-visible` 에 행 안쪽 2px 고리를 건다 —
  가로로 굴러가는 표 상자에 잘리지 않는다. 시험: `datatable-row-keyboard` 「표 행의 초점 고리」.
- **긴 데이터 예외(G 조사)**: `hostile_data long` 이 날짜 · 퍼센트 · 상태 칸에 200자 문장을 넣으면 사용자(문서폭 3242)와
  프로젝트(4504) 목록이 1920 · 1366 에서 가로로 넘친다(before 부터). 원천은 둘이다 — ① `render` 가 있는 `nowrap` 칸은
  알약 · 표지가 칸 중간에서 잘리지 않게 자르지 않는다(`kit.jsx::colCellSx`), ② 상태 배지는 자기 라벨보다 작아지지 않는다
  (A3 재검수). 날짜 · 상태 낱말은 실제로 그 길이가 될 수 없고 보통 데이터의 전 화면 캡처는 가로 넘침 0 이다. 둘을 뒤집으면
  실제 좁은 칸에서 알약이 잘리던 옛 결함이 돌아오므로 정책을 유지한다.

## 0-11. 요약 — 데이터의 뜻이 그릇을 정한다 (계획 표 7 · 핸드오프 README §7 · RULES §10)

- **합이 전체인 구성 → `StatusSummaryCard`**: 프로젝트 목록 구성(누르면 좁힘) · 개발자 리포트 팀 합계(신호 둘 +
  정의 목록 `notes` · 건수 낱말 `unit="건"`) · 조직 정합성 관리자 범위 · 메일 발송 현황(각주는 정의 목록) · 예약 달력
  이 구간 실행 · 설치 마법사 남은 항목.
- **서로 다른 측정값 → `StatusKpiStrip`**: 작업 큐 지표 · 시스템 리소스 · 조직 요약 · 조직/부서 상세 요약(각주는
  타일 `note`) · AI 상한 사용량(registry 기본).
- **값 하나 → 큰 숫자**(`StatusSummaryCard` 값 하나 갈래): 진단의 활성 스케줄(「스케줄에서 보기 →」 링크) · 알림 목록의
  안 읽음(DataScreen `unreadCountKey`).
- **속성 → `MetaBar`**: 백업 · 복구 리허설의 백업 일정(`summary.kind: "meta"`, 톤은 값 옆 배지).
- DataScreen 은 `screens/data-screen/SummaryView.jsx` 가 `summary.kind`(`status` · `strip` · `meta`)로 그린다. `status` 의
  카드는 `role`(`part` 부분 · `risk` 신호 · `measure` 구성 밖 측정값)을 준다 — 작업 큐는 상태 다섯이 부분, 실행 가능 ·
  최근 24시간 실패가 신호, 평균 처리 시간 · 가장 오래된 대기가 측정값이다.
- 대시보드의 판정 줄(`StatusBand`)은 메시지 박스(`Callout toneLabel`)다(계획 P-18) — 판정 낱말(위험 · 주의 · 정상)은 아이콘
  접근 이름이 말한다. 홈 「이번 주」의 프로젝트 축 줄은 `StatusList` · `StatusTile` 이다.
- **판독 줄(`MetricStrip`)은 걷었다**(계획 D) — 마지막 소비처였던 문서 목록의 요약 넷이 보기 전환 세그먼티드의 건수가 됐다(§0-15).
  부품이 지키던 계약은 이은 부품으로 옮겼다: 신호를 색만으로 말하지 않는다 · 누를 수 있는 칸만 버튼이고 눌림을 알린다 · 선택은
  면이 아니라 선이 말한다(`StatusKpiTile`, `kit.test`), 항목이 없으면 그릇을 남기지 않는다(`StatusKpiStrip`, `empty-data-unmount`),
  심각도 낱말은 대비 보강 잉크 · 한 줄(`Badge`, `theme-link-contrast`). 프로브: `kit_e2e` 의 판독 줄 검사를 걷고 FF-1400 은 상태 칩을
  누른다, `brand.py` 의 highlight 는 화면 선언(`data-brand-role="highlight"`)만 본다(큰 숫자는 핸드오프 규약상 잉크색이라 그 자리가
  아니다). 세그먼티드는 선택이 중립이라 `data-brand-role="none"` 을 선언한다(흰 칸을 「회색인 선택 자리」로 세지 않는다).
- 값 하나 카드의 심각도는 이름 앞 7px 점이다(`totalKind`) — 알림의 안 읽음이 남으면 주의 점. 숫자는 타일 줄처럼 잉크색이다.

## 0-12. 단추 · 탭 · 모달 발 · 팝오버 항목 · 사람 고르개 (핸드오프 RULES §3 · §8 · 계획 B-7)

- **페이지 탭 = `TabShell`**: 설정(`settings-tab-*` id 그대로, 본문 분기의 역할 검사도 그대로)과 프로젝트 상세
  (`idPrefix="project"`, 머리 동작은 `actions`). 두 화면이 탭 그릇 사본을 따로 들고 있었다. 프로젝트 상세의 모르는
  탭 값은 이제 주소도 개요로 정정된다(그릇 계약 2 — 보이는 결과는 전과 같은 개요).
- **보기 전환 = `Segmented`**: 내 승인 요청 · 분류 관리 · 휴지통 · 작업 보드(칸반/백로그) · 활동(B-4). 건수는 칸 안
  `count` 로 선다.
- **모달 발 = `ActionFooter`**: 티켓 미리보기(회차 작업 · 빠른 수정이 왼쪽, 「티켓 상세 보기」 오른쪽) · 둘러보기(진행
  점이 왼쪽, 발에 ghost 없음) · DataScreen 상세 · 하위 목록 서랍 · 오프보딩 실행 상세 · 설정 편집 · 설정 이력 ·
  사용자 셋 · 사용자 일괄. `.k-footer-*` 클래스와 그 CSS 는 걷었다.
- **팝오버 항목 = `overflowMenuItems`**: 사용자 메뉴(비밀번호 변경은 `href` 링크 항목, 로그아웃은 `tone:"danger"` 이고
  실패 문장이 남도록 닫지 않는다 — `onPick(item)`) · 저장된 뷰의 저장 항목 · 채팅방 멘션 고르기.
- **사람 고르개 = `UserPicker`**: 새 티켓 · 티켓 수정의 담당자(칩은 이름만 — 옵션 `tagLabel`, 전체 이름은 칩 `title`) ·
  오프보딩 후임(`describe` 로 이메일 · 부서, 비운 값은 「(후임 없음. 미할당으로)」). 모달 안에 펼쳐 둔 사람 목록(그룹
  초대 · 1:1 상대 · 멤버 초대)의 줄은 `PickerOption` 이다(`chat/peoplePicker.jsx::PersonPickRow`).
- **크기 리터럴 0**: 행 안 · 입력 도구 아이콘 단추는 테마의 작은 단추(30)다(대화 행 동작 · 보낼 첨부 제거 · AI 도우미
  첨부 도구 · 설정 도메인 제거). 스프린트 회의 결정 줄의 티켓 단추는 높이 덮어쓰기를 걷어 30 으로 선다(계획 표 5).
- 표 머리글 조작기(정렬 · 필터)는 `CONTROL.tableCellDense` 30 이다.
- 내 프로필 조용시간의 「시간 저장」은 입력칸(36) 높이로 늘어나 있었다(`alignSelf: stretch`) — 기본 단추 34 로 서고 윗선만
  맞춘다(G, 계획 표 5 「발 버튼 정렬」, ACCEPTANCE C1).

## 0-13. 판 · 판 제목 · 칸 이름 (핸드오프 RULES §6 · §7 · 계획 B-8 · §0-11)

- **MUI `Paper` 는 화면에서 걷었다.** 판은 `Card`(게시글 댓글 · 놀이방 채팅 · 참여자 · 놀이방 목록 · 퀴즈 문제),
  함몰면은 `Surface tone="inset"`(퀴즈 AI 문제 만들기), 판이 아닌 띠 · 알약 · 말풍선은 판 면 토큰을 쓰는 상자다
  (AI 도우미 대화 머리 띠 · 입력 띠 · 보낼 첨부 알약 · 말풍선 · 타이핑 말풍선 · 결과 카드(`data-result-card`) ·
  채팅방 입력 알약 — 채팅방 입력은 E 가 입력창 규격으로 다시 짠다). 대화 목록 검색은 검색 칸 정본(`SearchBox fill`)이다.
  남은 `Paper` 는 게임 무대 면뿐이다(위 예외 표).
- **판 제목 = `SectionTitle`**(1.0625rem/700 · 도움말 한 쌍 · 오른쪽 동작): 티켓 · 문서 댓글 · 티켓 첨부 · 본문 편집 머리 ·
  게시글 댓글 · 프로젝트 상세(마일스톤 · 개요 · 티켓 발생 추이 · 진행률 · Health) · WBS(트리 전체 진행률 · 트리에 넣지
  못한 작업) · 주간 리포트(이번 주 작업 · 마일스톤 · 요약) · 티켓 미리보기 설명 · 스프린트 회의 결정 레인(이름 · 도움말 ·
  건수 칩 — 계획 표 5). 이름 옆에 배지 · 건수 칩이 붙는 머리(조직 · 부서 상세, 통합 검색 묶음)는 판 제목 **글자
  갈래**(`variant="sectionTitle"`)만 쓴다. 판 안의 작은 묶음 이름(스탠드업 세 단 · Health 사유)은 판 제목이 아니다.
- **칸 이름은 칸 위다**(노치 라벨 없음). 손으로 만든 입력은 `FieldLabel` + `id`(select 는 `SelectProps.labelId`)로
  옮겼다 — 설정 구조 편집기 26 · 놀이방 만들기 9 · 티켓 수정 · 게시글 쓰기 · 문서 잇기 · 분류 · 제목 · 새 문서 · 분류 관리 ·
  CSV 붙여넣기 · 저장된 뷰 이름 · 오프보딩 메모 · AI 작업공간 질문 · 편집기 링크 · 회의 결정 내용. 키트 칸
  (`FilterSelect` · `DebouncedTextField` · `EntityCombobox` · `TagPicker` · `DateField`)은 줄 칸이 아닌 자리에서
  `label` 을 받으면 `filters.jsx::LABEL_ABOVE_SX` 로 이름을 칸 위 흐름에 세우고 노치 틈을 접는다(`FieldLabel` 과 같은
  글자 · 간격). 사용자 일괄 지정 줄은 도구 줄이라 줄 칸(34 · 칸 안 이름)이다. 새 티켓 폼은 C 에서 12칸 격자로 옮겼다(§0-14).
- **판 여백 리터럴 0**: AI 작업공간 인용 · 답 · 질문 판, 대시보드 불러오는 판, 예약 달력 판, 홈 팀 채팅 판은 판 규약값
  (`CARD_PADDING`)이고, 대시보드 운영 묶음 함몰면 · 진단 원문 함몰면은 토큰(`CARD_PADDING` · `TILE_PADDING`)이다.
- 남긴 것: 스프린트 회의의 촘촘한 줄 카드(논의 · 결정 줄 여백 10)는 보호 화면 표 5 허용 치환 밖이라 그대로다.

## 0-14. 새 티켓 폼 (핸드오프 RULES §7 · 계획 C · 표 8)

- **칸은 12칸 격자다**(`density.js::FORM_FIELD_GRID_12` + `fieldSpan` + `kit.jsx::FormFieldCell`). 차지는 표 8 그대로다 —
  제목 12/2 · 프로젝트 6/1 · 진행상태 · 우선순위 · 난이도 · 예상 WD · 마감일 3/1 · 담당자 3/2. 열 수는 칸 폭이 정한다.
  브라우저 실측(`kit_measure` `form_grids`): 1920 → 12칸(격자 937, 짧은 칸 219) · 1366 → 2칸(605) · 1200 → **12칸**(862, 짧은 칸 201).
  1200 은 UI 3차 P4 에서 바뀌었다 — 바깥 2열이 내용 폭 짝 트랙(§0-18 C-5)이 되어 레일이 폼 아래로 가고 폼이 본문 폭을 받는다. 그 전에는
  레일 옆 502 에서 1칸 8줄이었고(계획 표 8 의 「2칸 ~35rem」도 서지 않았다), 더 전에는 223px 두 칸으로 짜부라졌다.
- **필드 줄은 36 이 바닥이다**(`FIELD_ROWS` = `20 minmax(36, auto) auto`). 한 줄 칸은 그대로 36 이고, 담당자처럼 고른 칩이
  두 줄로 접히는 칸만 자라 아래 도움말과 겹치지 않는다. 라벨 줄이 20 고정이라 같은 줄의 입력칸 윗변은 같다. 소비처는
  `FormFieldCell`(새 티켓 · 갤러리)과 `Profile.jsx`(보호 화면 — 한 줄 칸만 있어 기하가 그대로다, `geometry_diff` 같음).
  핸드오프 RULES §7 의 「20 / 38 / auto」는 시안 HTML 의 칸(내용 36 + 테두리 1×2)이다. MUI 윤곽 칸은 테두리를 36 안에
  그리므로(윤곽선이 절대 위치) 필드 줄은 36 이고, ACCEPTANCE J1 「필드 36」과 같다(실측 `form_grids.fieldH` 36).
- **날짜 칸도 36 이다.** MUI X 날짜 입력(`MuiPickersOutlinedInput`)은 윤곽 입력과 다른 부품이라 `MuiOutlinedInput` 규칙을
  받지 않고 39 로 섰다(새 티켓 실측 — 같은 줄의 칸보다 3px 컸다). `theme.js` 가 높이 · 위아래 여백 · 모서리 · 면 · 포커스
  선을 윤곽 입력과 같은 값으로 준다(`theme-contract` 날짜 칸 단언). 소비처: `DateField`(새 티켓 · 티켓 수정 · 회의 결정 ·
  하위 목록 서랍 · 목록 날짜 필터)와 `FormField date`(프로젝트 · 회차 만들기와 고치기).
- **칸 이름은 칸 위 `FieldLabel`**(노치 라벨 0). select 는 `SelectProps.labelId`, 고르개(`EntityCombobox` · `UserPicker`)는
  `ariaLabelledBy` 로 이름을, 새 prop `ariaDescribedBy` 로 칸 밖 도움말 · 오류 줄을 가리킨다(가리킬 것이 없으면 키를 아예
  싣지 않는다 — `undefined` 를 실으면 MUI 가 도움말에서 이은 설명을 덮어 지운다). 날짜 칸은 라벨의 `for` 가 보이지 않는
  입력에만 닿으므로 `slotProps.input` 으로 날짜 조각 묶음(`role="group"`)에 이름과 도움말 줄을 잇는다.
- **검증은 칸 오류 줄이다**(토스트 4 → `FormFieldCell error`, 문구 그대로). 수정 모달과 같이 처음 걸린 하나만 말하고, 걸린
  칸으로 포커스를 옮기며(단추가 긴 폼 맨 아래라서다), 그 칸을 고치면 걷힌다. 입력의 `required` 는 그대로 둔다(폼에
  `noValidate` 를 걸지 않는다). **저장 실패**는 발 바로 위 `Callout danger compact`(`failureText` — 다시 보내면 걷힌다).
- **발은 `ActionFooter card sticky`**(Primary 「티켓 추가」 하나 · `loading`, 취소 없음 P-24). 긴 폼에서 화면 아래에 따라오고 오른쪽
  끝은 판 여백이다 — 예전 「FAB 여백」(`calc(CARD_PADDING + FAB_CLEARANCE)`)은 마스코트 FAB 이 PA-RC-0020 에서 걷힌 뒤에도 남아
  단추를 80px 안쪽에 세웠고, UI 3차 P4 에서 토큰과 소비처 셋과 함께 걷었다. 폼 안 안내 문장은 `Callout`(info)이다.
- **담당자**는 프로젝트를 고르기 전 꺼진 `UserPicker` 로 서고, 이유 문장(「프로젝트를 먼저 고르세요. …」 · 「배정할 수 있는
  사람이 없습니다. …」)은 칸 밖 도움말이 말한다. 후보를 부르는 동안은 고르개 한 줄 모양(`Skeleton lines={1}`)이다.
  질의 게이트 · 「나」 기본 칩 · 요청 본문은 그대로다. 고른 사람 칩이 서면 예시 글(「예: 김하나」)을 칩 옆에 겹쳐 세우지 않는다
  (`EntityCombobox` 다중 — 줄 칸 요약과 같은 규칙, UI 3차 P4 눈 대조에서 「UI QA ⊗ 예: 김하나」로 섰다).
- **첫 조회(프로젝트 · 메타)가 오는 동안은 폼 대신 폼 모양**(`Skeleton section`)이다. 느린 응답 실측에서 폼이 먼저 서서
  프로젝트 칸이 「선택할 수 있는 프로젝트가 없습니다」라고 말하고 로딩 표시가 0 이었다(`failure_states slow` 표시없음 →
  로딩표시).
- **작성 도움**은 판 하나 안의 목록(`li[data-writing-aid-item]`)이다. 항목은 읽을 것(절 이름 0.875rem/700 · 무엇을 적나
  0.8125rem · 예시 0.75rem 기울임)이고 누를 것은 줄마다 30 「넣기」 하나다. 넣은 절은 꺼지고 「✓」가 선다(접근 이름
  「…: 이미 넣었습니다」 그대로). 판 머리는 `SectionTitle help`, 묶음 이름 「더 적으면 좋은 항목」은 오른쪽 실선과 한 줄,
  AI 도우미 안내 문장은 `Callout`(문장 · 링크 그대로 — 시안의 「열기」 단추는 만들지 않는다). 손 카드의 12px 모서리
  리터럴 · `surface2` 면 · 반투명은 걷었다.
- 시험: `new-ticket-layout`(12 — 문턱별 열 수 · 칸 차지 · 실측 폭 대조 · 빈틈 · 칸 폭 하한 · 이름 · 도움말 · 오류 수명 ·
  저장 실패 상자), `new-ticket-writing-aid-contrast`(4), `new-ticket-assignee-picker`(제목 라벨 규칙),
  `new-ticket-load-failure`(+1 받는 중), `theme-contract`(+2 날짜 칸 두 테마).
  실측 프로브: `kit_measure` `form_field_rows`(같은 줄 입력칸 윗변 · 라벨 줄 1.25rem · 줄 빈틈 · 화면 순서 = DOM 순서).

## 0-15. 문서 목록 (핸드오프 README §B · ACCEPTANCE J2 · 계획 D)

- **보기 전환은 세그먼티드 하나**(`Segmented` 34 / 3 / 28, `ariaLabel="문서 보기"`)다 — 요약 판독 줄 넷(누르면 좁힘)과 필터 줄의
  「보기」 고르개가 같은 축을 두 자리에서 그리던 것을 합쳤다(O-1). 칸: 전체 문서 · 최근 24시간 · 즐겨찾기 · 내 초안(건수는
  서버 `workspace_summary` 그대로) · 최근 열람(건수 없음). 필터 바 **위**에 선다(RULES §0). 보기도 조건이라 칩 · 조건 수 ·
  「필터 지우기」 계약은 그대로다.
- **필터 바는 한 줄**: 검색 320 → 프로젝트 · 분류 · 태그 · 작성자(칸 안 이름 34) → 빈 공간 → `ToolbarEnd` 정렬. 조건이
  하나라도 걸리면 실선 뒤 **조건 줄**(`FilterConditionLine` — 「조건 N개, 결과 M건」 → 칩 → 「필터 지우기」)이 필터 바 안에
  선다(ACCEPTANCE D3). 목록 위 단독 「전체 N건」 줄은 없다 — UI 3차 C-1 이 걷었고(조건이 없을 때의 결과 수는 목록 판 발 「N건 중 M건을
  받았습니다.」가 말한다), 그래서 D3 이 「부분」이던 자리(조건 없는 화면의 면 밖 결과 줄)가 풀렸다. 줄 끝의 「필터 지우기」 글자 단추
  (`FilterActions`)는 조건 줄의 지우기로 합쳤다. 1920 은 한 줄이고, **1366 · 1200 은 두 줄로 접힌다** — 칸 폭 표(`ROW_KIND`: 검색 320 ·
  프로젝트 13rem · 분류 8~13rem · 태그 13rem · 작성자 13rem)의 합이 1,120px 이라 본문 1,070 · 904px 에 한 줄로 못 선다. 넘친 칸(작성자)이
  둘째 줄 왼쪽, 정렬 묶음이 둘째 줄 오른쪽 끝이다(UI 3차 P5 판단 — 칸 폭 계약을 흔들어 한 줄로 욱여넣지 않는다).
- **표 트랙** 별 48 · 제목 남는 폭(바닥 320) · 프로젝트 176 · 분류 148 · 작성자 130 · 최종 수정 132 · 첨부와 댓글 96 · 작업 64,
  행 바닥 76(`DataTable rowHeight="tall"`). 제목 칸은 제목 · 요약(두 줄 clamp) · 태그(`Tag` 넷 + 「+N」, 남은 태그 이름은
  「+N」의 `title`). 제목은 표 공통 제목 칸 `TitleCell link`(링크색 600 한 줄 · 말줄임 + `title`, UI 3차 P5)이고 행 열기는 표가 든다. 분류는 **점 + 낱말**(`DotLabel` 중립 — P-22), 작성자 얼굴 22(`UserAvatar xs`), 행 동작 30(`OverflowMenu sm`).
  좁을 때 접히는 열 순서(첨부와 댓글 → 최종 수정 → 작성자 → 분류)와 안내 한 줄은 그대로다.
- **실패는 그 자리**(표 6): 분류 관리 창의 추가 · 이름 고치기 · 지우기 · 틀 저장 실패는 그 창 발 위 `Callout`(창을 열 때
  지난 실패를 걷는다), 새 문서 만들기 실패는 그 창 발 위(프로젝트 상세와 같은 `error` 칸), 목록 줄의 별 · 휴지통으로 보내기
  실패는 목록 바로 위. 성공 토스트는 그대로다. 목록 줄 실패를 목록 판 안(발)으로 옮기지 않는다 — 발은 받은 건수와 선택 묶음의 자리이고,
  실패 상자는 필터 바 조합 검사가 면 밖 결과 · 칩으로 세지 않는 메시지 박스다(UI 3차 P5 판단).
- **분류 관리 창(`TaxonomyManager`)**: 발은 하나다 — 틀을 고치는 동안은 그 판의 취소 → 추가/저장, 아닐 때는 「닫기」(예전에는 몸 안 둘째 단추 줄 +
  창 발 「닫기」). 분류 · 태그 · 틀 줄의 수정 · 삭제는 `RowActions`(30 보조 · 파괴), 이름 고치기 줄의 취소는 보조다.
- **문서 상세**: 휴지통 안내 상자의 「복원」은 30 보조다(페이지 머리 「복원」이 채움 하나). 문서 잇기 창의 「잇기」는 고르기 전에도 꺼진 채 선다.
  댓글 쓰는 칸 · 고치는 칸은 입력 영역(`data-form-scope`)이라 「댓글 추가」 · 「저장」이 머리의 「저장」과 따로 센다(티켓 · 게시글 댓글도 같다).
- 남긴 것: 새 문서 · 기본 아바타 고르기 창의 취소가 적은 값을 묻지 않고 닫는 동작은 흐름 변경이라 이번 조합 회차에서 바꾸지 않는다.
- 시험: `knowledge-list`(보기 탭 · 필터 줄 순서 · 조건 줄 · 두 줄 행 · 태그 넷 + N · 실패 상자 둘),
  브라우저 게이트 `handoff-d1`(치명 4종 0 · 느린 응답 로딩 표시 · 긴 데이터 넘침 0 · `filter_e2e` 32 조합 통과).

---

## 0-16. 채팅방 (핸드오프 README §C · RULES §9 · 계획 E)

- **두 판**: 목록 판(`CHAT.listWidth` 296)과 대화 판이 판 틈(`GRID_GAP`)을 두고 선다. 좁으면(md 미만) 한 판만. 목록 행의 지금
  보는 방은 함몰면 + 왼쪽 레일(사이드바 활성 항목 어휘), 방 종류는 점 + 낱말, 안 읽음은 건수 칩 unread(B-3), 검색은
  `SearchBox fill`(B-4).
- **방 머리 세 묶음**(`[data-room-head]`, UI 3차 C-6 에서 두 줄 이름표로): ① 이름표 — 1줄 제목(판 제목 글자 갈래 `sectionTitle`, 말줄임 +
  전체 이름표) + 종류 배지, 2줄 「참여자 N명, 보는 중 M명」(0.75rem muted, 문구 그대로 · `MemberSummary`) ② 얼굴 스택(`MemberFaces` — 26 · −8,
  둘레 판 색 2px, 최대 8 + 「+N」 — 이름표 「외 N명」) ③ 동작 단추 34(관리 · 숨기기 · 나가기 · 방 파하기, 서버 플래그 그대로). 예전에는 요약이
  제목 줄 오른쪽에 한 줄로 서서 다섯 조각이 한 줄을 다퉜다. 줄은 묶음 단위로 접히고 동작 묶음 안은 접히지 않는다. 얼굴마다 이름과
  접속 상태(「이 대화 보는 중」 · 「자리 비움」)를 이름표로 든다 — 예전 한 줄의 이름 · 접속 점이 들던 사실이다. 목록 검색줄과
  높이를 맞추던 빈 자리는 판이 둘로 갈리며 걷었다.
- **스레드**(`ChatPane`): 상대는 왼쪽 — 묶음 첫 줄에 얼굴 34 · 이름 700 · 소속 muted, 함몰면 + 테두리 말풍선(모서리 12, 묶음 첫
  말풍선의 시작 모서리 4). 나는 오른쪽 — Primary 면 흰 글자(`ChatBubbleText mine`), 얼굴 · 이름 없음, 묶음 마지막 말풍선의 끝
  모서리 4. 말풍선은 `fit-content` 이고 묶음은 줄 폭 68% 에서 멈춘다. 시각은 말풍선 밖 0.6875rem(`CHAT.timeText`, 전체 시각
  `title`) — 이어지는 줄도 자기 시각을 늘 보인다. 날짜 구분선은 1px 실선(`rule`) + 0.75rem/600, 스레드 가운데 28rem 폭(`ChatDaySeparator`).
  **대화는 위에서부터 쌓인다**(UI 3차 C-6 — 소유자 결정 「위 정렬 + 입력창 바닥」, RULES §9 · ACCEPTANCE J3 의 「아래 정렬」을 뒤집는다):
  판은 화면 아래까지(`PAGE_FILL_HEIGHT`, 높이 고정 판)이고 로그가 남는 높이를 다 먹으며(상한 45rem 걷음) 짧은 방은 마지막 말과 입력창 사이가
  빈다. 첫 진입 · 새 메시지에 맨 아래로 굴리는 규칙은 그대로다. 아래 정렬은 제품 화면 밖 `compact`(홈 위젯)만 남는다. 1:1 읽음(내 마지막 말) ·
  멘션 강조 줄 · 내 말 지우기 · 이미지 말풍선 · 폴링 · 읽음 커서는 그대로다.
- **입력**: 스레드 아래 1px 실선(`rule`, 판 가장자리까지) **도킹 영역**(`data-chat-dock`, 입력 영역 표식 `data-form-scope`) 안에 1px 테두리 ·
  모서리 10 의 상자 하나 — 위 글 줄, 아래 도구 줄(이모지 · 언급, 30)과 오른쪽 끝 보내기(30 채움, 그림 + 접근 이름 「보내기」, 보내는 중
  `loading`). 보내기 실패 · 폴링 끊김 상자는 도킹 영역 안 입력 위다(폴링 끊김의 「다시 시도」는 30 보조). Enter 보내기 · 한글 조합 중 보내지 않음 · Ctrl+V 이미지는 그대로다. Shift+Enter
  줄바꿈은 제품에 없어 만들지 않았다(§0-2).
- **실패는 그 자리**(표 6): 보내기 실패 → 입력 위 상자(초안은 남는다), 나가기 · 파하기 · 숨기기 실패 → 방 머리 바로 아래 상자,
  새 그룹 · 1:1 시작 실패 → 그 창 발 위 상자(창을 열 때 걷는다), AI 도우미 본문 주소 복사 실패 → 그 주소 바로 뒤 한 줄
  (`role="alert"`). 잘 된 일(나갔습니다 · 주소를 복사했습니다)은 토스트 그대로다.
- 시험: `chat-bubble`(+2 말풍선 규격), `chatpane`(+2 입력 상자 · 보내기 실패), `chat-message-identity`(내 말 · 이어지는 말 — 계약 이동),
  `chatroom-scroll-layout`(머리 세 묶음 — 계약 이동), `chatroom-manage`(얼굴 스택 — 계약 이동), `chatroom-actions`(+1 머리 동작 실패),
  `chatrooms-two-panels`(신규 4), `chat/links`(+1 복사 실패 한 줄).
- 목록 판 머리 「대화」는 건수 칩과 동작이 붙는 판 머리라 판 제목 글자 갈래(`variant="sectionTitle"` 1.0625rem/700, §0-13)다 —
  E 가 판을 가르면서 옛 `FONT_SIZE.sectionTitle`(1.1875rem)을 남겨 둔 것을 G 의 전수 검색이 잡았다.
- **UI 3차 C-6 에서 바뀐 것**: 목록 판 머리는 「대화」 + 방 수(0.75rem muted) + 안 읽음 칩이고, 「1:1」 · 「새 그룹」은 페이지 머리 동작 34 보조다
  (보내기가 이 화면의 채움). 목록 행 시각은 `fmtListStamp`(이레 안 상대, 그 뒤 「8월 24일」, 해가 다르면 해 포함 · 전체 시각 `title`). 판 안 가는 선은
  `rule` 하나(목록 머리 · 검색 줄 · 행 사이 · 방 머리 · 도킹 선), 사람 고르기 목록 모서리는 입력칸 토큰 6, 참여자 관리 줄의 접속 점은 `StatusDot`.
  목록 행의 활성 레일은 강조색 그대로다 — 판 안 선택이라 사이드바의 어두운 셸 전용 레일 색과 다르다(판단 기록).
- **AI 도우미(`/chat`)**: 판 높이 `PAGE_FILL_HEIGHT`, 입력 모서리 10 · 첨부 도구 30(글리프 20, 모서리 6) · 입력 중 말풍선 12 · 날짜 구분선 공통 부품,
  「새 대화」 · 「맨 아래로」는 보조(맨 아래로는 떠 있는 그림자 overlay 만 든다), 안내 상자 동작(새로고침 · 다시 시도 · 닫기)은 30 보조. 열 폭 · 말풍선
  최대 폭(P-26)은 그대로다. 남은 것: 1366×768 에서 환영 영역이 스레드 칸보다 높아 맨 아래로 굴린 채 서서 클로비 윗부분이 잘린다(기존 — 스크롤
  고정 동작이라 이번 조합 회차에서 바꾸지 않는다).

## 0-17. 다크 모드 (핸드오프 README 다크 모드 절 · RULES §13 · ACCEPTANCE K1~K5 · 계획 F · D-487)

- **K1 원재료 색 0**: A 시작(`4a1e1bfb`) 뒤 바꾼 `frontend/src` 파일 130개(시험 · `theme.js` · `tokens.css` 제외)에서 16진 색은
  주석과 토큰 정의 파일(`ui/projectTone.js` — `theme.js` 와 같은 부류, 계획 T15)에만 있다.
- **K3 단추** — 보조와 파괴 단추의 면 · 테두리를 핸드오프 값으로 옮겼다(`kit.jsx::Button`). 보조: 라이트 흰 면 + `divider`
  #DCDFEC, hover 함몰면 + `dividerStrong` #BCC2D9 / 다크 투명 면 + `dividerStrong` #333B5E, hover 함몰면 #1C2136. 파괴: 라이트 흰 면 +
  `error.line` #E6B0AC + `error.main` #B3261E, hover `error.bg` #FAEBEC / 다크 투명 면 + #5F3330 + #FF8A80, hover #2E1A18. 비활성은
  `theme.js` 규칙(함몰면 · `line` · `disabledControlInk` #4B5478) 그대로다.
  예전 규칙(W4 R-11)은 테두리에 비텍스트 3:1 하한을 걸어 `text.faint` · 불투명 `error.main` 을 썼다. 글자 라벨이 단추를 알리므로
  테두리는 WCAG 1.4.11 의 대상이 아니고 핸드오프가 옅은 경계선으로 정했다. R-11 이 막던 두 역전은 계속 막는다 — 본문 잉크
  테두리(17:1)로 돌아가지 않고, 파괴 테두리가 중립보다 흐리지 않다(판 위 라이트 1.88 대 1.33 · 다크 1.68 대 1.62).
  시험 계약 이동: `kit.test.jsx` 「버튼 강도」(두 테마 계산값), `scripts/ui_qa/kit_e2e.py` 버튼 판정(토큰 값 + 파괴 ≥ 중립).
- **K4 클로비 바탕** — 빈 상태 · 오류 상태 그림은 밝은 바탕 기준 자산이라 다크에서는 함몰면 위에 놓는다(README 다크 모드 절 ·
  RULES §13 · 다크 시안 「빈 상태」). `kit.jsx::mascotGroundSx` 가 그림이 서는 `EmptyState` · `ErrorState` 상자에 다크에서만 함몰면 ·
  모서리 6 · 안쪽 선(그림자)을 칠한다. 여백은 두 모드가 같고(RULES §13 「치수 동일」), 라이트 · 그림 없는 빈 상태 · 좁은 자리는
  칠하지 않는다. 필터 · 반전은 쓰지 않는다. 시험: `handoff-kit-contract` 「다크 모드 — 빈 상태 · 오류 상태 그림의 바탕」.
  계획 F 의 표는 「마스코트 필터 0」만 적었고 이 규칙을 빠뜨렸다 — F 실측으로 더했다.
- **실측 하네스** `scripts/ui_qa/dark_colors.py`(맞는 견본 · 틀린 견본 자기 검사 `--selftest`): 판 면 · 판 테두리 · 함몰면 ·
  본문/보조 잉크 · 보조/파괴/비활성 단추 · 클로비 `filter` · `mix-blend-mode` · 빈 상태 그림 바탕 · 상태 점과 메시지 박스 아이콘(판 위 3:1) · 내 말풍선
  글자 대비(4.5:1)를 브라우저 계산값으로 센다. 표본 0 은 「미측정」이다.
- **예외(하네스가 따로 센다)**: 보호 화면 내 업무량 요약 카드의 「남은 일 · 취소」 범례 점은 비율 막대 조각과 같은 중립 선색
  (`dividerStrong`, 다크 판 위 1.62:1 · 라이트 1.8:1)이다. 화면이 「색은 완료 하나만」으로 정한 기존 설계이고 점은 `aria-hidden`
  이라 뜻은 낱말이 나른다. 보호 화면 치환 목록 밖이라 두었다.

## 0-18. 조합 — 부품 사이의 관계 (UI 3차 · 조합 계약 C-1 ~ C-7 · D-488 ~ D-494)

부품 치수가 전부 맞아도 조합이 화면마다 다르면 제품은 갤러리와 다르게 읽힌다. 이 절은 **부품 사이의 관계**를 적는다.
실측 잣대는 `scripts/ui_qa/composition_checks.py`(브라우저 · 11종)와 `scripts/check_composition.py`(소스 · 7규칙)다.

### 필터 바 조합 (C-1 · C-2)

- **`FilterBar`(`ui/FilterBar.jsx`)가 목록 화면 탐색 줄의 한 벌이다.** 한 줄 = 검색(20rem 슬롯) → 내용 필터 칸 → 빈 공간 →
  `end`(정렬 · 보기 · 켬/끔 · 저장된 뷰), 아래 1px 실선. 조건 칩이 하나라도 있으면 같은 면 안 둘째 줄이 `FilterConditionLine` 이다:
  「조건 N개, 결과 M건」(N = 칩 수) → 칩(`data-condition-chip`) → 지우기(`data-filter-clear`, 기존 낱말) → 덧붙는 글자 단추(「전체 보기」).
- **모든 조건은 칩을 가진다.** 검색어 · 요약 카드로 켠 조건(프로젝트 「Health 하위」 · 「지연 마일스톤」) · 밖에서 넘어온 조건
  (팀 티켓 부서 · 사용자 부서) · registry 기본값(승인 대기 · 게시됨)도 칩이다. 문서의 프로젝트는 사람이 고른 자리일 때만 조건이다
  (프로젝트가 하나뿐인 조직에서 화면이 스스로 연 자리는 조건이 아니다 — D-388 을 잇는다).
- **목록 위 단독 「전체 N건」 줄 · 면 밖 칩 줄 · 줄 끝 `FilterActions` 지우기를 걷었다.** 결과 수는 조건이 걸리면 조건 줄이,
  늘 목록 판 발(「N건 중 M건을 받았습니다.」)이 말한다.
- 소비처(16): `TicketFilterBar`(내 티켓 · 미할당 · 팀 티켓 — 「완료, 취소 포함」은 `end`) · `KnowledgeFilterBar` · 게시판 · 아이디어 ·
  `DataScreen`(registry 19 화면, 저장된 뷰는 늘 `end`) · 하위 목록 서랍(`divider=false`) · 프로젝트 · 사용자 · 조직 콘솔 · 오프보딩 대상 ·
  개발자 리포트(인쇄는 `end`) · 설정(기술 정보 보기 `end`) · 프로젝트 티켓 탭(`end`). 내 활동의 종류 고르기는 칸이 없는 줄이라
  필터 바 없이 `Segmented` 하나로 선다. 프로젝트 문서 탭의 「새 문서」는 탭 그릇 머리(`HeaderActions`)로 올렸다.
- **칸 해부 하나(C-2)**: 셀렉트 · 자동완성 단일/다중 · 자유 입력 · 태그 모두 34 칸, 접두 이름 들여쓰기 14 · 접두-값 6 · 값 잉크 600
  (`data-prefix-label` · `data-row-value`). 다중 선택은 칸 안 칩 대신 `RowSummary` 한 줄 요약. 폭은 `ROW_KIND`(Entity · 태그 13rem ·
  열거 8~13rem · 자유 입력 = 이름 + 값 자리 6rem(11rem 바닥, 24rem 상한 — 이름이 긴 감사 「작업」 칸에서 친 글자가 보이게) · 날짜 11rem ·
  날짜시각 18rem)이고 줄의 남는 폭을 먹지 않는다.
- 갤러리 「검색과 필터 바」 절의 견본 셋이 조합 부품 그대로다(조건 없음 한 줄 · 조건 여럿 + 다중 선택 요약 · 1200 좁은 판).

### 목록 판 조합 (C-3 · C-4)

- **`DataTable placement` 가 표의 자리를 정한다.** `surface` = 목록 화면의 주 목록: 판이 곧 표 상자(여백 0 · 1px 테두리 · 모서리 8,
  `data-list-surface`)이고 머리 40 이 판 윗변 · 좌우 가장자리에 붙는다. 머리 면은 고정 머리여도 함몰면이다(예전에는 고정 머리를 켠 표만
  흰 줄). `card` = 제목 있는 판 안 보조 표: 좌우를 판 여백만큼 거슬러 가장자리까지 편다(아래는 판 여백으로 둔다 — 음수 아래 여백은 뒤 줄을
  끌어올려 겹친다). `plain`(기본) = 모달 · 서랍 · 보호 화면(홈 · 내 업무량)의 표, 판을 그리지 않는다.
- **발(`data-list-footer`, 최소 44)은 판 안 마지막 줄이고 표 상자 밖이다** — 넓은 표를 가로로 굴려도 제자리다. 왼쪽 = 받은 건수 문장
  (`list` 가 있으면 그 수, 없으면 받은 행 수, 두 줄 미만이면 안 그림) · 숨긴 열 안내 · 뺀 열 안내 · `note`, 오른쪽 = 선택 묶음
  (`SelectionBar`) · 「더 보기」(30 보조). 그릴 것이 없으면 발이 없다. `note` 만 주면 그 문장이 발 문장이다(프로젝트 문서 「총 N건 가운데 …」 ·
  오프보딩 대상 「N명 중 M명을 보여 줍니다」). `list={false}` 는 건수를 말하지 않는 목록이다(대시보드 최근 변경 · 작업 큐 최근 오류 같은
  미리보기, 개발 리포트 집계 표, 진단 설치처 점검표).
- **surface 발은 긴 목록에서 화면 아래에 따라온다**(`position: sticky; bottom: 0`). 그래서 무한 스크롤 센티널은 발 안이 아니라 표 끝 흐름에
  선다(`data-list-sentinel` — 발 안에 두면 늘 보이는 자리라 자동 로딩이 멈추지 않는다). 발이 서 있는 동안 문서 스크롤 여백 아래를 발 높이 + 8
  만큼 비워 Tab 초점이 발에 가리지 않는다(`GlobalStyles scroll-padding-bottom`, keyboard 하네스 「가림」 0). 전체 쪽 캡처(fullPage)는 뷰포트를
  늘리지 않아 따라오는 발이 첫 화면 아래 끝 자리에 찍힌다 — 스크린샷의 그 겹침은 캡처 방식이고, 목록 끝의 제자리는 비어 보인다.
- **논리는 `listFooter.js::useListFooter` 한 벌이다** — 센티널 · 무성장 가드 · 자동 상한 · 받은 건수 문장. 판 밖 목록의 옛 모양
  `ListFooter` 도 같은 논리를 쓴다(작업 보드 백로그 · 내 활동 · 서랍 안 하위 목록).
- **행 동작은 `RowActions` 다(C-4)** — 30 보조/파괴, 셋 이상이면 「더 보기」 하나. 「나에게 배정」(미할당) · 「복원」(휴지통) · 「승인」(승인)이
  행마다 채움이던 것을 걷었다. 조건 0건의 지우기(`ListEmptyState` · 사용자 · DataScreen)와 빈 목록의 만들기(사용자 · 프로젝트 문서)도 30
  보조다 — 화면의 채움은 머리 동작 하나다. 일괄 동작의 채움(사용자 「적용」)은 선택 묶음 안 하나다.
- **제목 칸은 `TitleCell` 이다** — 티켓 · 휴지통(문서는 새 탭 앵커) · 게시판 · 프로젝트 · 프로젝트 문서. 이름 열이 제목인 관리 표는 그 열을
  `type: "title"` 로 둔다(설정 「항목명」). 게시판 카테고리 · 고정 표지와 설정 「재시작 필요」는 표 안 점 + 낱말(`DotLabel`)이다.
- **머리 표지(`TableHeaderCell`)**: 정렬 표지는 정렬 단추 안 이름 뒤 4px 의 16 글리프(↕ → ↑/↓), 필터 표지는 조건이 걸리는 열에만 서는 표지
  폭 단추(누르는 높이 30). 활성 열은 이름이 잉크, 표지가 `primary.dark` 다. 둘째 표지는 앞 표지에서 잰다(`table_head_glyph` 사슬).
- 소비처 surface: 내 티켓 · 미할당(설명 → 머리 description, 일괄 → 발) · 팀 티켓 · 프로젝트 티켓 · 문서 · 게시판 · 아이디어 · DataScreen
  (registry 화면 전부, 조건 없이 정말 빈 화면만 page 빈 상태) · 프로젝트 · 사용자(일괄 줄 → 발 선택 묶음, 실패 줄은 목록 위) · 휴지통 ·
  승인 · 오프보딩(대상 · 보유 티켓 · 실행 결과 · 실행 이력) · 프로젝트 문서 · 설정 · 저장소 · 대시보드 최근 변경 · 조직 정합성 관리자 범위 ·
  메일 실패 · 개발 리포트 셋 · 진단 설치처 · 작업 큐 최근 오류. card(3): 조직 정합성 항목 · WBS 미배치 · 갤러리 데이터 표 절.
  plain: 모달 · 서랍 표(설정 버전 기록은 판을 걷었다) · 홈 · 내 업무량 · 스프린트 회의(보호).
- **남긴 자리**: 조직 정합성 항목의 소속 지정 줄은 발의 선택 묶음이 아니다 — 선택 0건에도 서는 지정 폼이고, 적용한 뒤 선택을 비워도 건너뛴
  사람을 말하는 상자를 들고 있어야 한다(R5-04 · `integrity.test`). 선택이 없으면 비는 발 오른쪽 칸과 뜻이 달라 판 안 표 아래 줄로 둔다.
- 갤러리 「목록 화면 조합」 절(판이 아닌 절 — 목록 판이 판 안의 판이 되지 않게)이 필터 바 + 목록 판(선택 한 줄 · 머리 표지 · 행 동작 둘 ·
  발)의 맞는 견본이고, 「데이터 표」 절이 판 안 보조 표(card) 견본이다.

### 판 · 편집기 · 판 발 조합 (C-5)

- **내용 폭 짝 트랙(`density.js::contentPairTracks` + `CONTENT_PAIR_CONTAINER`)** — 주 판 + 보조 레일 화면의 2열은 본문이 받은 폭이 정한다
  (본문 칸 64rem 컨테이너 질의). 실측: 1366 → 본문 1070px(66.9rem) 2열, 1200 → 904px(56.5rem) 1열이고 레일이 판 아래로 간다. 사이드바를 접으면
  같은 뷰포트에서도 본문 폭을 따른다. 소비처: 새 티켓 · LLM 콘솔 · 오프보딩(대상을 고른 뒤). 뷰포트 `pairTracks`(lg)는 그대로다 — 내 프로필
  (보호) · 조직 정합성 · 시스템 운영 · 점검 · **초기 설정**. 초기 설정은 옮겼다가 되돌렸다: 1200 에서 1열이 되면 「남은 항목」 요약이 목록 아래
  1,000px 밖으로 내려가 첫 화면에서 사라진다(목록 칸은 543px 에서도 읽힌다).
- **화면 아래까지 서는 판(`PAGE_FILL_HEIGHT` = `calc(100vh - 12rem)`)** — 판 윗변 161(상단바 + 본문 열 위 여백 + 설명 없는 페이지 머리) + 본문 열
  아래 여백 32. 채팅방이 쓰던 13rem 은 판 아래가 47px 비었다. 새 티켓 두 판은 이 값을 **바닥**으로 쓰고(md 이상 `minHeight`,
  `data-page-fill="grow"`), 레일에는 바닥을 따로 걸지 않는다 — 2열에서는 격자 stretch 가 폼 판에 맞추고, 1열에서는 내용 높이다. 채팅방 판은 높이
  고정이다(`data-page-fill=""`). `page_fill` 검사가 둘을 가른다(판 아래 캔버스가 빔 · 높이 고정 판이 화면을 넘음).
- **폼 판 발 = `ActionFooter card sticky`** — 판이 넘침을 자르지 않고(MUI Card 뿌리의 `overflow: hidden` 을 푼다) 판 안 마지막 줄이 긴 폼에서 화면
  아래에 따라온다. 아래 모서리는 판 안쪽 반경이다. 발이 서 있는 동안 문서 `scroll-padding-bottom` 이 발 높이(34 + 24) + 8 이라 Tab 초점이 발에
  가리지 않는다(`StickyBottomPadding` — 목록 판 발과 같은 부품, keyboard 1366 틀린 상태 가림 19 → 0).
- **편집기 상자(`BlockEditor`)** — 편집 중인 편집기는 상자 하나다: 1px 테두리 · 모서리 6 안에 도구 줄(함몰면 + 아래 실선 · 도구 30 · 묶음 사이 세로선)과
  본문(바닥 240). 되돌리기 · 다시 실행은 남는 폭을 먹는 칸의 오른쪽 끝이라 도구 줄이 두 줄로 접혀도(1366 새 티켓 605px) 그 줄 오른쪽 끝에 선다.
  `fill` 이면 본문이 판의 남는 높이를 채운다(새 티켓). 소비처: 새 티켓 · 문서 편집 · 티켓 본문 수정(`EditableBody`). 읽기 전용은 상자가 없다.
- **판 발은 판 바닥이다(`Card`)** — 마지막 줄이 `ActionFooter placement="card"` 인 판은 세로 흐름이 되고 본문이 한 상자(`data-card-body`)로 묶여
  남는 높이를 먹는다. 짝 격자(stretch)에서 늘어난 판의 발이 판 가운데에 뜨지 않고 바닥에 서서 짝 판의 발과 한 줄이다(점검 두 판 실측: 발이 109px
  어긋났다). 본문 상자 안은 예전과 같은 보통 흐름이다.
- **손으로 짠 발 → `ActionFooter card`**: LLM 콘솔(연결 테스트는 왼쪽 칸, 되돌리기 → 저장) · 오프보딩 실행(파괴 확정) · 점검 두 곳(변경 기록 ·
  버전 기록은 왼쪽 칸 보조 — 카드 발에 글자 단추를 두지 않는다). **발 순서**(보조 → 확정이 오른쪽 끝): 오프보딩 실행 상세 모달 · 설정 편집 모달
  (취소 → 저장, 이력 · 미리 검증은 왼쪽 칸).
- **본문 수정 판 발(`EditableBody`)**: 티켓 본문을 고치는 동안 취소 → 저장은 판 제목 오른쪽(30)이 아니라 판 발(`ActionFooter card sticky`, 34)이다 —
  긴 본문에서 저장이 화면 위로 사라지지 않고 따라온다. 저장 실패 상자는 발 바로 위다. 티켓 상세 본문 판은 넘침을 자르지 않는다(sticky).
- **입력 영역 표식(`data-form-scope`)**: 화면의 채움 하나(C-4)는 입력 영역마다 제 몫이 있다 — 댓글 쓰는 칸 · 고치는 칸(티켓 · 문서 · 게시글)이
  표식을 들고, 판 발(`data-action-footer`) · 선택 발(`data-list-selection`)은 표식 없이 제 몫이다. `primary_budget` 이 그 표식으로 센다.
- **머리 줄 동작은 34 보조다**: 티켓 상세 · 게시글 「목록」(글자 단추였다), 대시보드 「새로고침」(글자 30 이었다), 통합 검색 「지금 재색인」(P4).
- **FAB 여백을 걷었다**: `theme.js::FAB_CLEARANCE` 와 소비처 셋(새 티켓 발 오른쪽 여백 · 통합 검색 결과 격자 오른쪽 여백 · 놀이방 사이드바 높이).
  마스코트 FAB 은 PA-RC-0020 에서 이미 걷혔다. 통합 검색 「지금 재색인」은 페이지 머리 동작이라 34 다.
- **검사 교정(P4)**: `oversized_empty_surface`(권고) — 입력 자리가 면의 절반 이상인 상자는 빈 면이 아니다(새 티켓 1200 빈 편집기 상자 860×283 이 잡혔다,
  작은 입력 하나를 품은 큰 빈 판은 여전히 잡힌다). `footer_owner` — 발 안 단추 · 입력은 면의 주인이 아니다(LLM 콘솔 꺼진 「되돌리기」가 함몰면과 같은
  색이라 주인 둘로 셌다). 조합 검사의 rem 치수(판 여백 · 칸 · 행 단추 · 머리 표지 · 발 · 편집기)는 루트 글자 크기 비율로 잰다(2560 · 3840 루트 18 · 20px).

### 글자 단추 자리 · 조사 부록 발견 처리 (P7)

- **글자 단추(ghost)는 목록 안 부수 동작의 자리다**(핸드오프 RULES §3 — 조건 지우기 · 더 보기 · 선택 해제 · 댓글 · 첨부 · 메시지 줄 동작 ·
  팝오버 목록 머리와 끝 · 달력 「오늘」 · 폼 안 입력 방식 전환). 메시지 박스 · 발 · 판 머리 · 페이지 머리 동작에는 두지 않는다 — 소스 규칙
  `ghost-slot` 이 잡는다. 옮긴 자리: AI 도우미 서랍의 메시지 박스 둘(「다시 시도」 · 「닫기」, 전체 화면은 P6 에서 옮겼다) · 알림함 부분 실패
  「다시 불러오기」 · 상태 알림 줄 「닫기」 둘과 「자세히 보기」 → 30 보조, 문서 첨부 판 머리 「파일 올리기」 → 30 보조(「문서 잇기」와 같다),
  프로젝트 개요 판 머리 「보관」 → 30 파괴 보조(되돌릴 수 없는 일이고 확인 창이 따른다 — registry 의 「보관」과 같은 갈래).
- **예약 달력 실행 상세 창** — 몸 안 단추 줄(「재시도」 · 「이 일정 열기」 채움 둘, 글자 단추 「닫기」)을 창 발 하나로 옮겼다: 왼쪽 칸 = 옮겨 가는 동작
  (이 일정 열기 · 작업 큐에서 보기, 보조), 오른쪽 = 닫기(보조) → 확정(실패한 실행의 재시도 채움, 대기 · 실행 중의 실행 취소 파괴 보조). 확정은
  실행 상태 · 권한에 따라 하나만 선다. 창 안 항목 표는 `plain` 그대로다.
- **채팅방 관리 창** — 이름 구획과 초대 구획이 따로 확정하는 입력 영역이라 표식(`data-form-scope`)을 하나씩 든다. 채움은 영역마다 하나(「저장」 ·
  「초대」)이고 창 발은 닫기(보조) 하나다.
- **조직 관리 상세 판 머리** — 조직 · 부서 판의 「수정」이 채움이라 페이지 머리 「부서 추가」와 화면 채움이 둘이었다(P3 에 넘긴 실측이 남아 있었고,
  P7 전 경로 `kit_measure` 가 조직 관리 · 부서 · 부서 상세 · 조직도 네 경로에서 다시 잡았다). 판 머리 동작(옮겨 가는 링크 · 활성/비활성 · 삭제 ·
  수정)은 전부 30 보조다 — 링크의 글자 단추도 걷었다.
- **DataScreen 정말 빈 화면의 만드는 단추** — 머리의 주 동작(「추가」 또는 `primary` 머리 액션)과 같은 일을 하는 30 보조다. 예전에는 같은 이름의
  채움이 머리와 빈 상태에 둘 섰다(대리 보기 「대리 보기 시작」 — registry 화면 중 씨앗이 빈 화면이 잡혔다).
- **죽은 코드 · 옛 주석**: `selectionColumn` 의 `className: "k-col-check"`(읽는 곳과 CSS 가 없다), 내 티켓 · 미할당 목록 동작 상자의 `sx mb`
  (아래 화면 리듬 규칙에 늘 져서 그려진 적이 없다)를 걷었다. `FilterActions` 띠는 px 36 → 필터 칸과 같은 rem 34 다(루트 18 · 20px 에서 칸과
  어긋났다). `ui/chat.js` 소비처 주석 · `Chat.jsx` flush 주석 · `TicketFilterBar.jsx` 스프린트 주석을 지금 코드대로 고쳤다.
- **이미 풀린 발견**: `.c-list-card` 죽은 규칙(P3 걷음), `.k-bulkactions` 오른쪽 여백과 빈 `actions` 의 `.k-page-actions` 빈 줄(P3 — 선택 묶음이
  목록 판 발로 옮겨 가 페이지 머리에 빈 동작을 넘기는 화면이 없다), 프로젝트 목록의 판 밖 발(P3), `NEW_TICKET_GRID` 사본 · LLM 콘솔 · 오프보딩
  손 발(P4), 채팅 세부 전부(P6 — 지역 점 · 줄 모서리 · 날짜선 두 벌 · 「새 대화」 · 「맨 아래로」 · 방 제목 글자 정의).
- **남긴 것과 이유**:
  - `.c-screen > .k-callout { margin-bottom: 16px }`(`styles/screens.css`)는 둔다. 화면 직계 메시지 박스의 세로 리듬(페이지 머리 · 필터 면과 같은
    16)이고 DataScreen 설명 상자가 이 값으로 선다. 화면 직계 상자에는 sx 여백을 따로 주지 않는다.
  - 표 행 체크박스(`SelectCheckbox`)는 브라우저 기본 상자 16px + 강조색이다. 시안의 15px · 모서리 3 은 부품 치수 항목이고 폼의 MUI 체크박스와 한 번에
    옮겨야 두 벌이 안 된다 — 조합 계약 밖이라 이번 회차에 흔들지 않는다.
  - 날짜 필터 `DateField` 의 줄 모양 갈래는 registry 소비처가 0 이다(하위 목록 창만 쓴다). 소비처가 생기면 `filter_cell_anatomy` 가 잰다.
  - `editorSurfaceWidthSx` 80rem 상한은 본문 72rem 안에서 걸리지 않는다 — 넓은 본문 칸이 생길 때의 안전 상한이라 둔다.
  - 새 문서 · 기본 아바타 고르기 창의 취소가 dirty 확인을 건너뛴다 — 흐름 변경이라 조합 회차 범위 밖이다.
  - 회차 닫기 확인 창에 `dangerConfirm` · 취소 기본 초점이 없다 — 보호 화면(작업 보드 · 스프린트 회의)의 확인 창이라 기록만 한다.
  - `TicketFilterBar.jsx::matchesTicketFilters` · `SPRINT_FIELDS` 는 스프린트 회의가 두 줄 필터로 옮긴 뒤(18c67683) 화면 소비처가 없다 —
    `ticket-filters.test.jsx` 가 한 쌍의 계약을 고정하고 있어 시험과 함께 걷는 일은 이 회차에서 하지 않는다.
  - **홈(`/me`)의 빈 계정 상태** — 티켓이 하나도 없는 계정에서 「오늘 마감 0건」 판의 빈 상태가 판 가운데 정렬이고(`empty_layout`),
    페이지 머리 「새 티켓」과 빈 상태 「미할당 티켓 보기」가 채움 둘이다(`primary_budget`). 배포된 설치처의 QA 계정이 비어 있어 처음
    드러났다 — 씨앗에는 티켓이 있어 로컬 측정에서는 이 상태가 서지 않는다. 홈은 보호 화면이라 공통 부품 치환만 허용되고, 빈 상태의
    구성(가운데 · 채움 CTA)은 그 화면의 레이아웃 결정이다. 다음 보호 화면 회차의 자리로 남긴다.

### 조합 예외 — 낱개 부품을 화면이 직접 조립하는 자리

형식은 `scripts/check_composition.py` 가 읽는다(`| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |`). 적혀 있는데 더는 안 걸리면 죽은 예외로 실패한다.

| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |
|---|---|---|---|
| `screens/Search.jsx` | `filter-parts` | 통합 검색의 제출형 검색 줄과 결과 요약 문장(`ResultLine text`) | 조건을 거는 목록이 아니라 제출해야 결과가 서는 검색이라 조건 줄 · 칩이 없다 |
| `screens/SchedulerCalendar.jsx` | `filter-parts` | 예약 달력 도구 줄(구간 이동 · 보기) | 달력 격자의 이동 도구라 조건 칸이 없다 |
| `screens/dev/KitGallery.jsx` | `filter-parts` | 「이럴 때 이것」 절의 필터 칩 · 상태 칩 나란히 견본(`FilterConditionLine` 낱개) | 갤러리는 정본 부품을 낱개로 세워 어휘를 대조하는 카탈로그다 — 조합 견본은 「검색과 필터 바」 절이 `FilterBar` 로 세운다 |
| `screens/WorkBoard.jsx` | `list-footer` | 작업 보드 백로그의 목록 끝 줄(`ListFooter`) | 백로그는 표가 아니라 끌어 옮기는 카드 줄 가상 목록이다(D-473) — 목록 판(`DataTable`)에 담을 표가 없다 |
| `screens/Activity.jsx` | `list-footer` | 내 활동의 날짜 묶음 목록 끝 줄(`ListFooter`) | 표가 아니라 날짜 머리(고정)와 활동 행을 쌓는 목록이다 — 목록 판 발은 표의 발이다 |
| `screens/data-screen/SubListDrawer.jsx` | `list-footer` | 하위 목록 창(모달 본문)의 목록 끝 줄(`ListFooter root="auto"`) | 모달 본문이 스크롤 창이라 센티널의 root 를 그 본문으로 넘기는 자리이고, 모달 안 표는 판이 없는 `plain` 이다 — 목록 판 발은 판의 마지막 줄이다. 검사기가 주석 뒤 JSX 를 못 읽어 P0 ~ P6 동안 보이지 않던 자리다(P7 에서 훑개를 고치며 드러났다) |
| `screens/Home.jsx` | `card-wrapped-table` | 홈 「내 할 일」 판 안의 핵심 열 표(`placement` plain) | 보호 화면 — 판의 탭 · 제목 · 높이 예산이 레이아웃이라 공통 부품 치환만 한다. 판 안 보조 표로 가장자리까지 펴면 보호 화면 기하가 바뀐다 |
| `screens/MyStats.jsx` | `card-wrapped-table` | 내 업무량 판 안의 표(`placement` plain) | 보호 화면 · 홈과 같은 이유 |
| `screens/knowledge/documentColumns.jsx` | `table-tag` | 문서 목록 제목 칸의 문서 태그(최대 넷 + 「+N」) | 태그는 사람이 붙인 낱말이라 흰 면 + 1px 테두리의 `Tag` 다(핸드오프 RULES §2 · 문서 시안 표 안 태그 · ACCEPTANCE J2). 표 안 점 + 낱말은 정해진 축 값의 규칙이다 |
| `screens/ProjectDocuments.jsx` | `table-tag` | 프로젝트 문서 탭 제목 칸의 문서 태그 | 문서 목록과 같은 이유 |
| `screens/dev/KitGallery.jsx` | `table-tag` | 데이터 표 절 문서 견본의 태그 | 문서 목록 조합 그대로를 세운 견본이다 — 문서 목록과 같은 이유 |

## 1. 신설한 부품

### `DataTable` 의 표 3종 (묶음 머리행 · 발 줄 · 높이)
- **파일**: `frontend/src/ui/kit.jsx` (`GroupHeaderRow` · `GroupHeaderMeta` · 발은 UI 3차에서 표 안 `TableFooterRow` 를 걷고 판 안
  마지막 줄 `ListFootBar` 로 옮겼다 — §0-18 목록 판 조합)
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
- `CONTROL.tableHead/tableRow/tableGroupRow/tableFooter/tableCellDense` = 40/48/36/44/30
  (`tableCellDense` 는 표 머리 조작기 높이다. 32 였으나 핸드오프 B-7 에서 작은 단추와 같은 30 으로 내렸다 — 단추 높이는 두 단계뿐이다)
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
| 폼 고정 트랙 `FIELD_ROWS` | `ui/kit.jsx` | 핸드오프 A 에서 키트로 올렸고(`FormFieldCell`), 새 티켓(C)이 둘째 소비처다 | 승격 완료(§0-14) |
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
