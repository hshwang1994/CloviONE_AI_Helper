# UI RENEWAL — Requirement Traceability (지시 56 Gate)

> 사용자 지시 **1~70 전부**에 대해 현재 문제 · 변경 내용 · 영향 범위 · 공통 변경 ·
> 검증 방법 · 완료 기준을 적는다. 생성 시 번호 누락과 빈 필드를 스크립트가 검사한다.
> Phase 정의는 계획서 `misty-honking-wirth.md` §3에 있다.

**항목 70개 · 빠진 번호 0건 · 빈 필드 0건 (생성 시 assert로 확인)**

---

## 1. 상단 알림 제거 · 종 단일 진입점 · 동기화 Scheduler 정책화

- **Phase**: P3-2, P4-1
- **현재 문제 / 조사 대상**: 전 라우트 상단에 전폭 빨간 장애 스트립(`Banners.jsx` CriticalStatusLine)과 헤더 `주의` 칩(`StatusNotices.jsx:246`). 동기화 주기는 env 상수라 관리자가 못 바꾼다.
- **변경할 기능 또는 UX**: 사용자 알림은 종 아이콘 단일 진입점으로. 스트립·칩 제거. 동기화 주기를 SettingSpec 정책으로 승격.
- **영향 범위**: `app/AppShell.jsx:805`(유일 마운트), `app/Banners.jsx`, `app/StatusNotices.jsx`, `app/worker_main.py:566-675`, `app/settings/registry.py`
- **필요한 공통 Component / 정책**: NotificationBell을 사용자 알림의 유일 진입점으로. SettingSpec 4종 신설(docs/tickets/projects/search 주기).
- **검증 방법**: 전 Route 캡처에 스트립 부재 확인. 정책 변경 후 워커가 새 주기로 도는지 실측. `banners.test.jsx`·`statusNotices.test.jsx` 재작성.
- **완료 판단 기준**: 일반 사용자 화면 어디에도 상시 상태 스트립이 없고, 관리자가 콘솔에서 동기화 주기를 바꿀 수 있다.

## 2. Dashboard 전면 개선 · Surface 위계 · AI 도우미 영역

- **Phase**: P1-3, P6
- **현재 문제 / 조사 대상**: 관리자 대시보드에 동일 흰 카드 8개+, KPI 3개 흰 박스, 하단 40% 공백. 사용자 홈은 흰 KPI 6개 중 4개가 `-`. `AI 도우미`가 본문과 같은 흰 카드.
- **변경할 기능 또는 UX**: KPI/상태/목록/활동/차트/작업 영역의 표현을 분리. 핵심·보조 지표 구분. Surface 위계 적용. AI 영역을 독립 보조 영역으로.
- **영향 범위**: `screens/Dashboard.jsx`, `screens/Home.jsx`, `screens/AssistantPanel.jsx`, `ui/adminKit.jsx`, `screens/Projects.jsx`, `screens/MyStats.jsx`
- **필요한 공통 Component / 정책**: Surface 토큰(P1-3), StatCard 대체 Summary 표현, Chart 공통 규칙
- **검증 방법**: Before/After 캡처 대조. 화면 하단 공백 비율 측정. `dashboard-render.test.jsx`·`home.test.jsx` 재작성.
- **완료 판단 기준**: 동일 형태 흰 카드 반복이 없고, 핵심 지표와 보조 지표가 시각적으로 구분되며, 하단 대형 공백이 사라진다.

## 3. Page Header · `?` 도움말 구조 공통화

- **Phase**: P2(PageHeader), P9-3
- **현재 문제 / 조사 대상**: `PageHeader`에 `?` 토글이 이미 있으나(`kit.jsx:1239-1250`) 화면 파일 102개 중 39개만 쓴다. 외부 연동·사용자에는 있고 OS와 서비스·메일 발송·사용자 홈에는 없다.
- **변경할 기능 또는 UX**: PageHeader가 맞는 Archetype에서 일관 적용. 제목/breadcrumb/도움말/부가설명/Action의 위치·간격 규칙화. 도움말 문구 재작성.
- **영향 범위**: `ui/kit.jsx::PageHeader`, `screens/DataScreen.jsx:677`, PageHeader 미사용 Route 전체
- **필요한 공통 Component / 정책**: PageHeader 재설계 + Archetype별 적용 판정표(지시 66)
- **검증 방법**: Inventory의 Route별 적용 여부 표로 확인. `crumb-root.test.jsx`·`datascreen-help-tone.test.jsx` 갱신.
- **완료 판단 기준**: PageHeader Archetype에 속한 Route 전부가 동일 구조를 갖고, 도움말 진입이 한 방식으로 통일된다.

## 4. Card/Section/Spacing/Typography 재설계

- **Phase**: P1-3, P2, P7-3
- **현재 문제 / 조사 대상**: `Card`가 55개 파일의 기본 컨테이너. radius 18 + shadow 고정. Sprint 화면은 4K에서 세로 14,082px.
- **변경할 기능 또는 UX**: Section/Panel/Card/Toolbar로 역할 분리. 카드가 불필요한 정보는 카드 제거. 고정 height·임의 margin 제거.
- **영향 범위**: `ui/kit.jsx::Card`, `ui/adminKit.jsx`, `ui/density.js`, `styles/screens.css`, 55개 소비 파일
- **필요한 공통 Component / 정책**: Surface 4종 분리 + Spacing/Typography 토큰
- **검증 방법**: `kit.test.jsx`·`density.test.jsx` 재작성. 대표 화면 세로 길이 측정.
- **완료 판단 기준**: 화면이 흰 사각형 나열로 보이지 않고, 카드 높이가 콘텐츠에 따라 결정된다.

## 5. 검색·필터 공통 시스템 재설계

- **Phase**: P2
- **현재 문제 / 조사 대상**: `FilterBarGrid` 4개 파일, `SearchBox` 5개, `FilterSelect` 1개, `SavedViews` 1개만 사용. 문서 화면은 검색+Select4+정렬이 한 줄, 즐겨찾기가 다음 줄, 카드/표 토글이 또 다음 줄.
- **변경할 기능 또는 UX**: 공통 Search/Filter Bar 패턴. 검색 우선 폭. 주요/보조 필터/정렬 위계. 프로젝트 등은 검색형 Combobox.
- **영향 범위**: `ui/FilterBar.jsx`, `ui/filters.jsx`, `screens/TicketFilterBar.jsx`, `screens/TeamDocs.jsx`, `screens/Board.jsx`, registry 23종
- **필요한 공통 Component / 정책**: SearchFilterBar 재설계 + Autocomplete Combobox
- **검증 방법**: `filter-bar-grid.test.jsx`·`datascreen-search.test.jsx` 재작성. 폭 변화 시 재배치 실측.
- **완료 판단 기준**: List Archetype Route 전부가 같은 필터 문법을 쓰고, 폭이 줄어도 자연 재배치된다.

## 6. Page Layout · Responsive 공통 구조

- **Phase**: P10-1, P10-2
- **현재 문제 / 조사 대상**: `CONTENT_MAX_WIDTH`가 3840px에서만 바인딩. 4K 스케일 레버가 root font-size(16→18→20px)에 의존. 상세 화면이 좌측으로 몰린다.
- **변경할 기능 또는 UX**: 공통 Page Container·Content Width·Grid·Breakpoint·padding 재설계. 고정 width/height·임의 margin 제거.
- **영향 범위**: `app/AppShell.jsx:791-824`, `ui/theme.js::CONTENT_MAX_WIDTH/BREAKPOINTS`, `styles/root.css`
- **필요한 공통 Component / 정책**: Breakpoint 단일 정책 + Content Width 정책
- **검증 방법**: 1366/1920/2560/3840 × zoom 80/100/125/150 캡처. `horizontal_overflow` 검사.
- **완료 판단 기준**: 어느 해상도·zoom에서도 한쪽 쏠림이 없고 페이지별 breakpoint가 없다.

## 7. 상세 화면 공통 Detail Layout

- **Phase**: P2(Detail), P7-1
- **현재 문제 / 조사 대상**: 티켓 상세가 본문+첨부(좌)/속성+댓글(우). 지시가 요구한 '상단 전폭 메타 + 본문/첨부·댓글'과 다르다. `density.test.jsx`가 grid 트랙 문자열을 고정.
- **변경할 기능 또는 UX**: 본문형 상세(Ticket/TeamDoc/BoardPost)에 상단 전폭 메타 + 본문 2fr / 첨부·댓글 1fr. 고정 px 금지.
- **영향 범위**: `screens/Ticket.jsx:53`, `screens/TeamDoc.jsx:51`, `screens/BoardPost.jsx`, `screens/TicketAttachments.jsx`, `screens/CommentThread.jsx`
- **필요한 공통 Component / 정책**: DetailLayout 공통 컴포넌트(단, 지시 66에 따라 강제 아님)
- **검증 방법**: 첨부·댓글이 데이터가 있는데 안 보이는 경우를 데이터 연결·조건부 렌더·권한까지 추적. `ticket-detail.test.jsx` 재작성.
- **완료 판단 기준**: 본문형 상세 3종이 같은 구조를 갖고, 첨부·댓글이 있으면 반드시 보인다.

## 8. 티켓 Grid Inline Edit · Row Action · 새 티켓 · 작성 도움

- **Phase**: P2, P7-2
- **현재 문제 / 조사 대상**: Grid 행마다 `보기` 외곽선 버튼 반복. 상태·우선순위 Inline Edit 없음. 새 티켓 본문 툴바에 이모지 버튼 8개. 작성 도움 3항목이 지시와 다르다.
- **변경할 기능 또는 UX**: 상태·우선순위 Inline Edit. Row Action은 핵심 1개 + Overflow. 작성 도움을 배경및목적/완료기준/제약및주의사항으로 재작성. 이모지 툴바 제거.
- **영향 범위**: `screens/MyTickets.jsx`, `screens/TicketFilterBar.jsx`, `screens/TeamTickets.jsx`, `screens/ProjectTickets.jsx`, `ui/BodyEditor.jsx`
- **필요한 공통 Component / 정책**: InlineEdit 컴포넌트 + RowAction 패턴
- **검증 방법**: 변경/저장/실패/권한없음 4상태 테스트. `new-ticket-layout.test.jsx`·`tickets-list.test.jsx` 재작성.
- **완료 판단 기준**: 권한 있는 사용자가 목록에서 상태·우선순위를 바꿀 수 있고, 행 버튼이 반복되지 않는다.

## 9. Sprint 회의 전면 개선 · Burndown 재설계

- **Phase**: P7-3, P6
- **현재 문제 / 조사 대상**: 담당자 현황이 반복 흰 카드. Burndown이 단일 주황 선, 범례·이상선·축 단위 없음. Ticket Count와 WD 혼용. 티켓 수백 행. 4K 세로 14,082px.
- **변경할 기능 또는 UX**: 담당자별 비교 가능한 표현. 프로젝트 검색 + 티켓 필터. 실제 잔여 vs 이상 감소선 구분, 축·단위·범례·기간 명시. Sprint 운영 기준(Count vs WD) 정의.
- **영향 범위**: `screens/Sprint.jsx`, `screens/sprint-charts.js`, `ui/charts/LineSeries.jsx`
- **필요한 공통 Component / 정책**: Chart 공통 규칙 + Sprint 전용 데이터(P4-4)
- **검증 방법**: `sprint-redesign.test.jsx`·`sprint-charts.test.js` 재작성. 세로 길이 측정. 수백 행 렌더 성능.
- **완료 판단 기준**: 회의에서 실제 판단(누가 밀렸나·범위가 늘었나·언제 끝나나)이 화면에서 바로 읽힌다.

## 10. Data Grid/Table Design System

- **Phase**: P2(DataTable), P10-4
- **현재 문제 / 조사 대상**: `DataTable` 17개 파일 사용. 정렬·페이지네이션 내장 없음(`Pager` 별도 6개). 세로 괘선. 프로젝트 표 20행이 전부 동일 `진행` 알약, `부서 미지정` 반복.
- **변경할 기능 또는 UX**: 헤더/행높이/타이포/Hover/Selected/Checkbox/정렬/Pagination/Empty/Loading 통일. 세로 괘선 제거 + 행 리듬. 데이터 유형별 셀 렌더러.
- **영향 범위**: `ui/kit.jsx::DataTable`, `ui/Pager.jsx`, `ui/bulkSelect.jsx`, `styles/screens.css:366-382`(nth-child 열 너비)
- **필요한 공통 Component / 정책**: DataTable 재설계 + 셀 렌더러 사전 + Pagination 흡수
- **검증 방법**: 긴 제목·오류 메시지 주입(`hostile_data.py`). `kit.test.jsx` DataTable 블록 재작성.
- **완료 판단 기준**: 표가 Excel처럼 보이지 않고, 행 추적이 쉬우며, 긴 값에 레이아웃이 깨지지 않는다.

## 11. Button/Action/Status/Badge 시스템

- **Phase**: P1-3, P2
- **현재 문제 / 조사 대상**: `정상`·`활성`·`사용 중`·`미연결`·`아니요`·`전체 관리자`가 전부 같은 알약. Button 61개 파일. 티켓 상세에 채운 파랑·채운 빨강 버튼이 나란히.
- **변경할 기능 또는 UX**: Primary/Secondary/Tertiary/Destructive/Inline 역할 정의 + 4상태. Status/Category/Tag/Editable Value 구분. 단순 텍스트가 맞는 곳은 Badge 제거. 색만으로 상태 전달 금지.
- **영향 범위**: `ui/kit.jsx::Button/Badge/statusKind`, `styles/tokens.css` badge 토큰, 61개 소비 파일
- **필요한 공통 Component / 정책**: Button/Badge 토큰 + Status 이산 단계 정의(D-141 RAISE)
- **검증 방법**: `check_button_hierarchy.py` 확장. 대비 검사. `kit.test.jsx` 재작성.
- **완료 판단 기준**: 한 화면의 주요 Action이 한눈에 보이고, 서로 다른 의미의 값이 같은 알약으로 보이지 않는다.

## 12. Modal/Dialog/Popup 공통 구조

- **Phase**: P2(Modal), P8-4
- **현재 문제 / 조사 대상**: 사용자 상세 Modal 푸터에 버튼 8개 한 줄(`더보기` 포함, 파괴적 2개 포함).
- **변경할 기능 또는 UX**: Header/Body/Footer·Action 우선순위 통일. Action Group·Overflow. 위험 작업 시각·공간 분리. Body만 스크롤. Responsive 크기.
- **영향 범위**: `ui/kit.jsx::Modal/ModalFooter/FormModal`, `screens/Users.jsx`, `screens/DataScreen.jsx`
- **필요한 공통 Component / 정책**: Modal 재설계 + ActionGroup
- **검증 방법**: 긴 콘텐츠 주입. `users-detail.test.jsx`·`modal-unsaved-guard.test.jsx` 재작성.
- **완료 판단 기준**: Modal Action이 무질서하게 나열되지 않고, 위험 작업이 일반 작업과 구분된다.

## 13. Global Header · 로고

- **Phase**: P3-1
- **현재 문제 / 조사 대상**: AppBar가 보라 그라데이션(`AppShell.jsx:679-681`). `TopBrand` 폭이 `DRAWER_WIDTH`에 묶여 있다.
- **변경할 기능 또는 UX**: 그라데이션 제거. 로고 영역 축소를 Header 높이·Global Search·사용자 영역 균형과 함께 조정.
- **영향 범위**: `app/AppShell.jsx:668-764`, `app/TopBrand.jsx`, `ui/theme.js` brand palette
- **필요한 공통 Component / 정책**: Header 토큰 + 로고 크기 정책
- **검증 방법**: `topbar-baseline.test.jsx`를 Runtime 계약 검증으로 이관(§1.6). `usermenu-topbar-gradient-contrast.test.js` 재작성.
- **완료 판단 기준**: Header가 시각 중심을 과도하게 차지하지 않고 Sidebar·Main과 같은 언어를 쓴다.

## 14. Global Search Overlay 재설계

- **Phase**: P3-3
- **현재 문제 / 조사 대상**: `CommandPalette.jsx`가 공용 컴포넌트를 하나도 안 쓴다(전부 지역 구현). 흰 팝업 안 텍스트 리스트.
- **변경할 기능 또는 UX**: Overlay 크기/위치/Spacing/Typography/Result Group/Selected State 재설계. 결과 유형 구분. 동작(키보드·상태)은 이미 충분하므로 보존.
- **영향 범위**: `app/CommandPalette.jsx`, `app/TopSearch.jsx`, `lib/search.js`
- **필요한 공통 Component / 정책**: Overlay Surface + Result Group 표현
- **검증 방법**: `command-palette.test.jsx` 확장(키보드·Loading·Empty·Error 유지 확인).
- **완료 판단 기준**: 결과 유형이 즉시 구분되고 흰 팝업 텍스트 리스트에서 벗어난다.

## 15. 채팅방 UI 재설계

- **Phase**: P7-4
- **현재 문제 / 조사 대상**: 사용자 메시지가 보라/파랑 버블 우측 정렬, AI 응답은 좌측 평문. 전형적인 AI 제품 레이아웃.
- **변경할 기능 또는 UX**: 특정 AI 제품 연상 패턴 제거. 과도한 Bubble·이모지·아이콘·색 장식 제거. Portal의 Typography/Spacing/Button/Surface로 재설계.
- **영향 범위**: `screens/Chat.jsx`, `screens/chat/*`(7), `screens/ChatPane.jsx`, `screens/ChatBubbleText.jsx`, `screens/ChatRoom.jsx`, `app/AssistantDrawer.jsx`
- **필요한 공통 Component / 정책**: 메시지·작성·첨부·코드·표·Action 표현 규칙
- **검증 방법**: `chat-bubble.test.jsx`·`chat-card-chrome.test.jsx` 재작성.
- **완료 판단 기준**: Clovir Assist 자체 언어로 보이고, 사용자/AI 구분은 유지된다.

## 16. 의미 없는 줄바꿈 · 고정 Layout 전수조사

- **Phase**: P9-3, P10-1
- **현재 문제 / 조사 대상**: 짧은 문장이 여러 줄로 나뉘거나 공간이 있는데 줄이 내려간다. `KO_WORD_BREAK`가 일부에만 적용.
- **변경할 기능 또는 UX**: Text Component 전체 조사. `<br>`·임의 Width/Height로 문장 맞추는 코드 제거. Container 기준 자연 wrapping.
- **영향 범위**: PageHeader/Help/Card Description/Chart Description/Form Help/Table Cell/Alert/EmptyState 전체
- **필요한 공통 Component / 정책**: `KO_WORD_BREAK` 전면 적용 + 텍스트 컨테이너 규칙
- **검증 방법**: `ko-wordbreak.test.jsx` 확장. 캡처에서 고아 줄 육안 확인.
- **완료 판단 기준**: 충분한 공간이 있는데 줄이 내려가는 문구가 없다.

## 17. Form/Input 공통 개선

- **Phase**: P2(Form)
- **현재 문제 / 조사 대상**: 새 티켓의 작은 Select 3개가 grid에 배치돼 우측이 빈다. `FormField`가 kit 밖에서 직접 쓰이지 않는다(FormModal 내부 전용).
- **변경할 기능 또는 UX**: Input/Textarea/Select/Autocomplete/DatePicker/Checkbox/Radio 크기·높이·Label·Helper·Error 통일. Label above input. 필수/선택/Validation 명확화.
- **영향 범위**: `ui/kit.jsx::FormField/FormModal`, `screens/MyTickets.jsx`(NewTicket), `screens/settings/*`, registry 폼 23종
- **필요한 공통 Component / 정책**: Form 토큰 + 필드 배치 규칙
- **검증 방법**: `form-field-server-error.test.jsx`·`users-field-limits.test.jsx` 재작성.
- **완료 판단 기준**: 폼이 중요도·입력 순서대로 배치되고 필수/오류가 즉시 이해된다.

## 18. Empty State 공통 개선

- **Phase**: P2(EmptyState), P6
- **현재 문제 / 조사 대상**: 내 티켓 빈 상태가 4K에서 세로 450px를 마스코트가 차지하고 번호 목록 설명이 이어진다.
- **변경할 기능 또는 UX**: Clovi는 유지(사용자 확정)하되 공간 채우기 용도 중단. 읽는 순서를 제목→다음 행동→보조 설명으로. 크기·비율·여백을 Design System이 결정.
- **영향 범위**: `ui/kit.jsx::EmptyState`, `lib/assets.js::ART`(13종), 41개 소비 파일
- **필요한 공통 Component / 정책**: EmptyState 재구성 + `size="compact"` 기본화
- **검증 방법**: 빈 상태 캡처 대조. `kit.test.jsx` EmptyState 블록 재작성.
- **완료 판단 기준**: 빈 화면에서 다음 행동이 먼저 읽히고, 일러스트가 화면을 지배하지 않는다.

## 19. Session 만료 · 인증 상태 처리

- **Phase**: P5-1
- **현재 문제 / 조사 대상**: `api.js:45-54`가 401에서 `["me"]`만 무효화하고 리다이렉트 없음. `minimal` 셸로 축소만 된다. SPA에 Return URL 없음. refresh 없음.
- **변경할 기능 또는 UX**: 공통 Authentication Layer에서 401 처리: 민감 Client State 정리 → 로그인 이동. Return URL(서버 `?next=` 규약과 통일). Redirect Loop 방지. 401/403 구분 유지.
- **영향 범위**: `lib/api.js`, `app/auth.jsx`, `app/App.jsx:105`, `app/AppShell.jsx:620-629`, `app/main.py:264-289`
- **필요한 공통 Component / 정책**: Auth Layer + Return URL 정책. 값은 `app/settings/registry.py::session_policy`가 정본.
- **검증 방법**: 401 후 이전 데이터 잔존 여부 확인. Loop 회귀 테스트. `auth-401-invalidates-me.test.jsx` 확장.
- **완료 판단 기준**: 세션 만료 시 이전 데이터가 남지 않고 로그인으로 이동하며, 403은 로그아웃시키지 않는다.

## 20. Loading/Error/Success Feedback 공통화

- **Phase**: P2, P5-4
- **현재 문제 / 조사 대상**: `Skeleton(lines)` 하나뿐. `Callout`이 35개 파일에서 큰 외곽선 Box로 모든 안내를 표현. 성공 Toast 남발.
- **변경할 기능 또는 UX**: 전체화면/Section/Table/Button 4종 Loading. Inline Notice/Section Notice/Warning/Critical Alert 위계. Toast/Inline/Form Error 역할 구분. Backend 원문 비노출.
- **영향 범위**: `ui/kit.jsx::Skeleton/Callout/ToastProvider/ErrorState`, 전 화면
- **필요한 공통 Component / 정책**: Loading 4종 + Feedback 위계
- **검증 방법**: `check_success_toast_labels.py` 확장. `toast-announce.test.jsx` 재작성.
- **완료 판단 기준**: 로딩 중 빈 화면이 없고, 참고와 조치필요가 같은 강도로 표현되지 않는다.

## 21. 권한 · Action UX 공통화

- **Phase**: P5-2
- **현재 문제 / 조사 대상**: 권한 판단이 8곳 이상 중복. 실제 불일치: `Dashboard.jsx:31-40`의 `/diagnostics`가 `[admin,system_admin]`인데 라우터는 operator 포함. 사라진 `/maintenance`를 아직 참조.
- **변경할 기능 또는 UX**: `SCREEN_ROLES` 단일 표로 수렴. 화면별 사본 제거. 권한 없으면 숨기거나 이유 표시. Disabled 방치 금지.
- **영향 범위**: `app/navConfig.js::SCREEN_ROLES`, `screens/Dashboard.jsx:31-40`, `app/AdminRoutes.jsx:151,155,156`, `app/NotificationBell.jsx:63-69`, `registry/shared.js:131-135`, `settings/settingsRegistry.js:52`, `ops/opsHelpers.js:8`
- **필요한 공통 Component / 정책**: 권한 단일 소스 + 표시 정책
- **검증 방법**: `rbac-matrix.test.jsx`·`nav-features.test.js` 확장. 역할별 캡처(`role_*` 라벨).
- **완료 판단 기준**: 같은 Action이 화면에 따라 다르게 보이는 불일치가 0건이고, 프런트 표시가 서버 판정과 일치한다.

## 22. UX Writing 전수조사

- **Phase**: P9-1
- **현재 문제 / 조사 대상**: 오류 문구 167건 중 회복 경로를 주는 것이 24건뿐이었다(PA-RC-0002). 개발자·내부 용어 노출.
- **변경할 기능 또는 UX**: `docs/UX_WRITING.md`를 정본으로 확장. Button Label/EmptyState/Help/Error/Confirm/Tooltip 문체·용어 통일. Scheduler·Queue·Worker 등 기술 용어 제거.
- **영향 범위**: 전 화면 사용자 노출 문자열, `docs/UX_WRITING.md`
- **필요한 공통 Component / 정책**: 표준 동사표 확장 + 금지 용어 목록
- **검증 방법**: `ux-writing-punctuation.test.js`·`ux-writing-verb-table.test.js`·`check_user_text.py` 확장.
- **완료 판단 기준**: 같은 개념이 화면마다 다른 이름으로 불리지 않고, 오류가 다음 행동을 알려준다.

## 23. 하드코딩 · 중복 UI 제거

- **Phase**: P1-1, P1-5, P2, P12-2
- **현재 문제 / 조사 대상**: 토큰이 4겹. 사이드바 색이 3중 정의(theme/tokens.css/AppShell 인라인 rgba)이고 실제로 그려지는 건 인라인. `global.css:40-121` 특이도 전쟁 블록. `screens.css:366-382` nth-child 열 너비.
- **변경할 기능 또는 UX**: 토큰 1곳 + 생성물. 인라인 리터럴 제거. 특이도 전쟁·nth-child·한국어 라벨 셀렉터 제거. `!important` 신규 금지.
- **영향 범위**: `ui/theme.js`, `styles/tokens.css`, `app/static/css/tokens.css`, `ui/density.js`, `styles/global.css`, `styles/screens.css`, `ui/kit.css`
- **필요한 공통 Component / 정책**: 토큰 생성기 + 드리프트 검사기
- **검증 방법**: `check_css_vars.py`·`check_typography_literals.py`. `find_dead_css.py`로 잔존 확인.
- **완료 판단 기준**: 동일 성격 값이 한 곳에서만 정의되고, 페이지별 하드코딩이 검사로 막힌다.

## 24. 상태 유지 · 화면 복귀

- **Phase**: P5-3
- **현재 문제 / 조사 대상**: 목록→상세→목록 복귀 시 검색/필터/정렬/페이지 유지 여부가 화면마다 다르다.
- **변경할 기능 또는 UX**: URL 상태를 정본으로 확장. 새 Session에서 유지할 Preference와 탐색 임시 State 구분. Back/Forward 자연 동작.
- **영향 범위**: `lib/useQueryState.js`, `ui/SavedViews.jsx`, List Archetype Route 전체
- **필요한 공통 Component / 정책**: URL 상태 규약 + Preference 분리
- **검증 방법**: `users-url-state.test.jsx`·`saved-views.test.jsx` 확장. 브라우저 Back/Forward 실측.
- **완료 판단 기준**: 목록으로 돌아오면 작업 맥락이 유지되고, 모든 State를 영구 저장하지는 않는다.

## 25. 접근성 · Keyboard

- **Phase**: P10-3
- **현재 문제 / 조사 대상**: Focus State·Modal Focus 이동·색 단독 상태 전달 여부가 화면마다 다르다.
- **변경할 기능 또는 UX**: Interactive Component 전체를 키보드만으로 사용 가능하게. Focus 명확. Modal Focus 이동·복귀. 색 단독 금지. 대비·Label 관계 검수.
- **영향 범위**: `ui/kit.jsx` 전체, `app/AppShell.jsx`, `app/CommandPalette.jsx`, `ui/theme.js` focus ring
- **필요한 공통 Component / 정책**: Focus 토큰 + 상태 비색 신호(D-141 RAISE)
- **검증 방법**: `ui_qa/keyboard.py`·`contrast.py`·`semantics.py`, `heading-order.test.jsx`, `theme-focus-visible.test.js`, `theme-link-contrast.test.js`
- **완료 판단 기준**: 키보드만으로 주요 Workflow가 완주되고, 색을 못 봐도 상태를 안다.

## 26. 성능 · 대용량 데이터

- **Phase**: P10-4
- **현재 문제 / 조사 대상**: Sprint 화면이 티켓 수백 행을 한 번에 렌더. Debounce 값이 `FILTER_DEBOUNCE_MS`와 `CommandPalette DEBOUNCE_MS 220`으로 분산.
- **변경할 기능 또는 UX**: Pagination/Virtualization/Server-side Search 검토. Debounce 공통 상수로 수렴. 불필요 Re-render·과도 Animation 억제.
- **영향 범위**: `screens/Sprint.jsx`, `ui/filters.jsx`, `app/CommandPalette.jsx`, `ui/kit.jsx::DataTable`
- **필요한 공통 Component / 정책**: Debounce 단일 상수 + 대량 렌더 정책
- **검증 방법**: 수백 행 렌더 시간 측정. `hostile_data.py`.
- **완료 판단 기준**: 데이터가 많아져도 UI가 급격히 느려지지 않고 Debounce 값이 한 곳에서 온다.

## 27. 최종 Visual Audit · 완료 기준

- **Phase**: P11, P12
- **현재 문제 / 조사 대상**: 기능 테스트 PASS를 완료로 보던 관행.
- **변경할 기능 또는 UX**: 구현 후 실제 Browser에서 사용자·관리자 주요 페이지 재확인. 18개 검증 항목. 대표 해상도 + Zoom.
- **영향 범위**: 전 Route
- **필요한 공통 Component / 정책**: Before/After 대조 절차
- **검증 방법**: P12-1의 7기준 + P12-4의 18항목. Impeccable detect.mjs + finish-reviewer, Taste Pre-Flight.
- **완료 판단 기준**: 기존 디자인과 거의 차이가 없거나 투박하면 미완료로 판정한다.

## 28. 이모지 · 장식 문자 전수 제거

- **Phase**: P9-2, P7-2
- **현재 문제 / 조사 대상**: 새 티켓 본문 툴바에 이모지 버튼 8개. 문서 제목 앞 자물쇠 이모지(`TeamDoc.jsx:305,340`, `TeamDocs.jsx:355,603`).
- **변경할 기능 또는 UX**: 이모지·장식 Unicode·불필요 특수기호 제거. 상태를 이모지로 표현하지 않는다. 텍스트 장식용 반복 문자 제거.
- **영향 범위**: `ui/BodyEditor.jsx`, `screens/TeamDoc.jsx`, `screens/TeamDocs.jsx`, 전 화면 사용자 노출 문자열
- **필요한 공통 Component / 정책**: `check_user_text.py`를 이모지·장식 기호로 확장
- **검증 방법**: 검사기 0건. 캡처 육안 확인.
- **완료 판단 기준**: 화면과 소스 어디에도 장식 목적 이모지·특수기호가 남지 않는다.

## 29. 문서 잠금 제거 · 문서 동기화 UX

- **Phase**: P4-1, P4-2
- **현재 문제 / 조사 대상**: **전제 정정**: 문서 잠금 기능은 존재하지 않는다. 자물쇠는 문서 열람 제한(`restricted`, SEC-10)의 이모지 표현이다. 사용자 확정: 이모지만 제거, 기능 유지.
- **변경할 기능 또는 UX**: 🔒 이모지 제거 후 Design System 표현으로. `restricted` 기능·권한·API·테스트는 그대로 유지. 사용자 문서 화면에서 `지금 동기화`를 기본 Action에서 내린다.
- **영향 범위**: `screens/TeamDoc.jsx`, `screens/TeamDocs.jsx:73-90,320-325`, `screens/MyTickets.jsx:655-673`. **유지**: `app/team_docs/service.py::doc_in_scope`, `POST /api/team-docs/{id}/restrict`, `tests/security/test_document_restricted_scope.py`
- **필요한 공통 Component / 정책**: 상태 표현 규칙(이모지 금지)
- **검증 방법**: `teamdoc.test.jsx`·`teamdocs-view.test.jsx` 갱신. 보안 테스트 11개는 그대로 통과해야 한다.
- **완료 판단 기준**: 자물쇠 이모지가 사라지고 열람 제한 기능과 권한은 손상 없이 동작한다.

## 30. 관리자 IA 전면 재구성

- **Phase**: P3-5
- **현재 문제 / 조사 대상**: 관리자 Sidebar 5그룹 36항목. 기능 1개 = 메뉴 1개 구조.
- **변경할 기능 또는 UX**: 36개 Route 각각에 유지/통합/Tab·View/이동/제거를 근거와 함께 결정. Domain→Page→(필요시)Tab 순. 모든 하위를 Tab으로 만들지 않는다.
- **영향 범위**: `app/navConfig.js::NAV`, `app/AdminRoutes.jsx`, `screens/registry/*`, `screens/settings/SettingsShell.jsx`
- **필요한 공통 Component / 정책**: IA 재설계 + Route redirect 호환
- **검증 방법**: Direct URL·Bookmark·Back/Forward/Refresh 실측. `nav-*.test.js`·`registry-area-matches-nav-group.test.js` 재작성.
- **완료 판단 기준**: 메뉴 이름만 보고 기능 위치를 예측할 수 있고, 기존 URL이 전부 살아 있다.

## 31. 관리자 전체 Design System 적용

- **Phase**: P8-1, P1-3
- **현재 문제 / 조사 대상**: 관리자 화면에 과도한 빈 공간·큰 흰 박스·버튼 나열·긴 설명문·불균형 Column Width.
- **변경할 기능 또는 UX**: 사용자 영역과 같은 Design Language. 단 Density는 한 단계 높게.
- **영향 범위**: 관리자 Route 46개 전체
- **필요한 공통 Component / 정책**: Density 2단(사용자/관리자)
- **검증 방법**: Before/After 대조. `admin-uiux.test.jsx` 재작성.
- **완료 판단 기준**: 관리자 화면이 별도 체계로 보이지 않으면서 정보 밀도가 더 높다.

## 32. 설정 페이지 UX 재설계

- **Phase**: P2(SettingRow), P8-2
- **현재 문제 / 조사 대상**: 시스템 정책이 읽기 전용 표 + `수정됨` 배지뿐. 편집 어포던스 불명. 설명에 `password_ref`·`cron`·`워커` 노출.
- **변경할 기능 또는 UX**: 설정 항목마다 현재 값/의미/변경 가능 여부/변경 방법/영향/적용 상태/검증. 읽기 전용은 Input처럼 보이지 않게.
- **영향 범위**: `screens/settings/SettingsMain.jsx`, `SettingEditor.jsx`, `SettingVersions.jsx`, `StructuredObjectFields.jsx`
- **필요한 공통 Component / 정책**: SettingRow 패턴 + 저장·적용 상태 모델
- **검증 방법**: `settings-save-flow.test.jsx`·`settings-editor-readonly.test.jsx` 재작성.
- **완료 판단 기준**: 설정 가능 값과 읽기 전용이 시각적으로 구분되고 변경 방법이 명확하다.

## 33. OS와 서비스 화면 재설계

- **Phase**: P8-3
- **현재 문제 / 조사 대상**: `변경` 영역이 기능명 외곽선 버튼 6개 나열. 서비스는 `재시작` 버튼 5개 우측 일렬. **데이터는 이미 백엔드에 있다**(`list_actions()`, `system.info`).
- **변경할 기능 또는 UX**: 각 설정을 이름·현재 값·설명·변경 Action이 연결된 Settings Pattern으로. 서비스는 이름·상태·마지막 확인·Action을 한 구조로. 재시작을 일반 설정과 같은 수준으로 취급하지 않는다.
- **영향 범위**: `screens/SystemOps.jsx`, `app/sysops/actions.py::list_actions`, `app/sysops/router.py`
- **필요한 공통 Component / 정책**: SettingRow + Action 위험도 등급
- **검증 방법**: `system-ops.test.jsx`·`system-ops-confirm.test.jsx` 재작성. TEST 서버 실제 실행(P11-7).
- **완료 판단 기준**: 버튼을 누르기 전에 현재 설정이 무엇인지 알 수 있다.

## 34. 설정 Modal · 시스템 변경 Workflow

- **Phase**: P8-4
- **현재 문제 / 조사 대상**: TLS 인증서 교체가 큰 Textarea 몇 개 + 적용 버튼.
- **변경할 기능 또는 UX**: 공통 Modal + 공통 Settings Workflow. 필드 목적·형식·Validation·현재 상태·적용 결과. 인증서/키 짝 검증을 입력 단계에서 안내. 민감 값 재노출 금지. 재시작 필요 사전 안내.
- **영향 범위**: `screens/SystemOps.jsx`, `app/sysops/actions_service.py::cert.install`
- **필요한 공통 Component / 정책**: Settings Workflow 공통화
- **검증 방법**: 실패 경로(짝 불일치·nginx -t 실패·롤백) 실측.
- **완료 판단 기준**: DNS/Hostname/Proxy/Timezone/TLS가 임시 Modal 반복 없이 한 Workflow를 쓴다.

## 35. Alert/Warning/Notice/Error 시스템

- **Phase**: P2(Feedback), P8-5
- **현재 문제 / 조사 대상**: `Callout` 35개 파일. 메일 발송에 주황 외곽선 Box 2개가 같은 원인을 반복. 전폭 Red/Orange Border.
- **변경할 기능 또는 UX**: Inline Notice/Section Notice/Warning/Critical Alert 위계. 참고와 조치필요 구분. 긴 기술 설명은 상세/진단으로 분리. Color 단독 금지. 전폭 Border를 기본형으로 쓰지 않는다.
- **영향 범위**: `ui/kit.jsx::Callout`, `screens/MailStatus.jsx`, `screens/NotionConsole.jsx`, `screens/LlmConsole.jsx`, 35개 소비 파일
- **필요한 공통 Component / 정책**: Feedback 4단계 위계
- **검증 방법**: 동일 원인 중복 표시 0건 확인. `kit.test.jsx` Callout 블록 재작성.
- **완료 판단 기준**: 무엇이 문제인지·어떤 영향인지·무엇을 해야 하는지가 위계에 맞게 읽힌다.

## 36. 내부 구현 정보 노출 제거

- **Phase**: P8-6
- **현재 문제 / 조사 대상**: 사용자 상세에 raw UUID. 시스템 정책 설명에 `password_ref`·`cron`·`워커`. 메일에 `smtp.enabled`·`(host)`·`(from_address)`. 연동에 `http://127.0.0.1:8788`.
- **변경할 기능 또는 UX**: 환경변수명·서버 경로·DB ID·Config Key·Raw Flag Key·CLI 방식·Secret 위치·Backend Error 원문·모듈명 전수 조사. 기술 정보는 권한자에게 `기술 정보`/`진단 정보`로 분리.
- **영향 범위**: 관리자 Route 46개, `app/health/service.py`(diagnostics bundle), `app/mail/service.py:207-217`
- **필요한 공통 Component / 정책**: 기술 정보 분리 패턴 + Secret 비노출(CLAUDE.md §3-3)
- **검증 방법**: 관리자 화면 문자열 전수 grep. 캡처 육안.
- **완료 판단 기준**: 일반 관리 화면에 Raw Key·경로·원문 오류가 남지 않는다.

## 37. 연동 설정 화면

- **Phase**: P8-7
- **현재 문제 / 조사 대상**: 연동 표에 `http://127.0.0.1:8788` 원시 주소가 주요 정보. `활성`·`정상` 두 알약이 같은 모양.
- **변경할 기능 또는 UX**: 연동 대상/연결 상태/필요 설정/마지막 정상 확인/연결 테스트/관리 Action 중심. Raw DB ID·Token 강조 금지. 서버 관리 값은 Form Input처럼 표시하지 않는다.
- **영향 범위**: `screens/NotionConsole.jsx`, `screens/registry/integrations.js`, `app/integrations/router.py`, `app/notion_console/router.py`
- **필요한 공통 Component / 정책**: Integration 카드 패턴 + Connection Test Feedback
- **검증 방법**: `notion-console.test.jsx` 재작성. 연결 테스트 성공/실패/Timeout 3경로.
- **완료 판단 기준**: 어떤 서비스가 연결되어 있고 정상인지 한눈에 파악된다.

## 38. AI 관리자 설정 화면

- **Phase**: P8-8
- **현재 문제 / 조사 대상**: 실행 파일 Path·CLI 방식·Timeout·동시 실행 수가 평면 나열.
- **변경할 기능 또는 UX**: AI 사용 여부/Provider·Backend 상태/Model/사용 제한/동시 처리 정책 중심. 실행 파일 Path 등 제거. 연결 테스트를 설정 Flow 안에서. Runbook은 분리.
- **영향 범위**: `screens/LlmConsole.jsx`, `app/llm_console/router.py`, `app/llm/provider.py::STATUS_*`
- **필요한 공통 Component / 정책**: SettingRow + 상태 표현
- **검증 방법**: `llm-console.test.jsx` 재작성. 연결 테스트 9개 상태값 매핑 확인.
- **완료 판단 기준**: 관리자가 무엇을 확인하고 설정해야 하는지 바로 안다.

## 39. 기능 플래그 구조 재검토

- **Phase**: P8-9
- **현재 문제 / 조사 대상**: **전제 정정**: 백엔드는 이미 건강하다. 11개 중 10개가 소비자를 갖고, 미사용 1개는 의도적으로 `has_consumer:false`로 표시된다. 남은 문제는 UI에 내부 Key가 그대로 노출되는 것.
- **변경할 기능 또는 UX**: 일반 관리자 기능인지 개발·운영 전용인지 판정. 사람이 이해할 이름·설명 기본, 내부 Key는 보조. 현재값/기본값/적용값/출처(파일 vs DB) 관계 표현. 변경 불가 Flag는 편집 가능처럼 보이지 않게.
- **영향 범위**: `screens/registry/platform.js`(feature-flags), `app/admin/feature_flags.py`, `app/core/feature_flags.py`
- **필요한 공통 Component / 정책**: 기술 정보 분리 패턴
- **검증 방법**: `feature-flags-detail-description.test.jsx` 재작성. DB 소유 키 409 경로 확인.
- **완료 판단 기준**: 내부 Key가 주 정보가 아니고 변경 가능 여부가 시각적으로 분명하다.

## 40. 메일 발송 관리 화면

- **Phase**: P8-10
- **현재 문제 / 조사 대상**: **전제 정정**: `backend_failed` 상태값은 없다. `종류` 열의 `backup_failed`는 알림 종류 키다. 실제 문제는 내부 키 노출 + `last_error` 원문(`f"{type(exc).__name__}: {exc}"`) 노출 + 원인 3중 반복 + Raw ISO Timestamp.
- **변경할 기능 또는 UX**: 발송 가능 여부→설정 상태→최근 성공/실패→필요 Action→최근 이력 흐름. 원인 반복 제거. 알림 종류 키를 이해 가능한 이름으로. Raw Error를 기술 정보로 내림. 공통 Date Formatter.
- **영향 범위**: `screens/MailStatus.jsx`, `app/mail/service.py:207-217,249-260`, `app/mail/router.py:45-51`, `app/mail/config.py::configuration_problems`
- **필요한 공통 Component / 정책**: Feedback 위계 + 기술 정보 분리 + `lib/format.js`
- **검증 방법**: `mail-status.test.jsx` 재작성. 미설정 상태 캡처.
- **완료 판단 기준**: 메일이 왜 안 나가는지 한 번만 말하고, 원문 오류가 기본 화면에 없다.

## 41. 통계 · 관리 페이지 통합 검토

- **Phase**: P3-5, P8-11
- **현재 문제 / 조사 대상**: `prompt-usage`·`policy-usage`·`ai-quotas`·`dev-report`가 각각 독립 Sidebar 메뉴.
- **변경할 기능 또는 UX**: 독립 페이지 유지가 맞는지 P3-5 IA 결정과 함께 판단. 더 큰 Context의 Tab/Section이 자연스러우면 통합.
- **영향 범위**: `screens/registry/authoring.js`, `screens/registry/platform.js`, `screens/DevReport.jsx`, `app/navConfig.js::NAV`
- **필요한 공통 Component / 정책**: IA 결정(P3-5)에 종속
- **검증 방법**: 통합 후 Direct URL 호환. 사용자가 위치를 예측하는지 확인.
- **완료 판단 기준**: 화면 수를 줄이는 것이 아니라 찾기 쉬워졌음을 근거로 판정한다.

## 42. 관리자 기능 동작 전수검증

- **Phase**: P4-3, P11
- **현재 문제 / 조사 대상**: 표시되지만 동작하지 않는 Button, 저장해도 반영 안 되는 기능, Frontend만 바뀌는 기능의 존재 여부가 미확인.
- **변경할 기능 또는 UX**: 관리자 주요 Action·설정 전수 확인. 필요한 것은 End-to-End 수정, 불필요 Legacy는 의존성 확인 후 제거. 디자인상 불필요해 보인다는 이유만으로 제거하지 않는다.
- **영향 범위**: 관리자 Route 46개 + 대응 API 전체
- **필요한 공통 Component / 정책**: -
- **검증 방법**: TEST 서버에서 실제 실행(P11-7 프로토콜). Backend 상태 재확인.
- **완료 판단 기준**: 동작하지 않는 관리자 기능이 남아 있지 않다.

## 43. Action 위험도 · 실행 패턴 공통화

- **Phase**: P8-12
- **현재 문제 / 조사 대상**: 서비스 재시작이 일반 Button과 같은 시각 수준.
- **변경할 기능 또는 UX**: 단순 조회/일반 설정 변경/서비스 영향 가능/Destructive 구분. Confirm은 실제 위험에만. 실행 중 중복 클릭 방지 + 진행 표시. 성공·실패 후 Backend 상태 재확인.
- **영향 범위**: `screens/SystemOps.jsx`, `screens/ops/Maintenance.jsx`, `screens/Users.jsx`, `screens/DataScreen.jsx`, `registry/actions.js`
- **필요한 공통 Component / 정책**: Action 위험도 등급 + 실행 상태 패턴
- **검증 방법**: `system-ops-confirm.test.jsx` 확장. P11-7 프로토콜.
- **완료 판단 기준**: 위험도가 시각적으로 구분되고 실행 후 UI와 실제 상태가 일치한다.

## 44. 관리자 설명 구조 단순화

- **Phase**: P8-13, P9-1
- **현재 문제 / 조사 대상**: Page Description·Alert·Helper Text가 같은 내용을 반복.
- **변경할 기능 또는 UX**: 설명은 필요한 위치에 필요한 만큼만. 페이지 상단은 목적을 짧게. 설정 항목은 선택에 필요한 것만. Runbook 수준 내용을 설정 화면에 길게 두지 않는다.
- **영향 범위**: 관리자 Route 46개
- **필요한 공통 Component / 정책**: 설명 배치 규칙
- **검증 방법**: `settings-description-dedup.test.jsx`를 전 화면으로 확장.
- **완료 판단 기준**: 같은 내용이 세 곳에서 반복되지 않는다.

## 45. 저장/수정/적용 상태 일관성

- **Phase**: P2, P8-2
- **현재 문제 / 조사 대상**: `저장`·`수정`·`적용`·`변경`·`재시작`의 의미가 페이지마다 다르다. **백엔드 근거는 이미 있다**(`SettingSpec.restart_required`).
- **변경할 기능 또는 UX**: 공통 상태 모델: 수정됨/저장됨(미적용)/즉시 적용됨/재시작 필요/적용 실패. 변경사항 없을 때 저장 버튼 동작 통일. 재시작 필요를 변경 과정에서 미리 안내.
- **영향 범위**: `screens/settings/*`, `screens/SystemOps.jsx`, `app/settings/registry.py::SettingSpec.restart_required`
- **필요한 공통 Component / 정책**: 저장·적용 상태 모델
- **검증 방법**: `settings-save-flow.test.jsx` 재작성. 재시작 필요 키 실측.
- **완료 판단 기준**: 저장 후 언제 반영되는지 사용자가 항상 안다.

## 46. 관리자 Navigation · 현재 위치 인지

- **Phase**: P3-7
- **현재 문제 / 조사 대상**: Sidebar Active/Page Header/Tab State가 서로 모순될 수 있다. Tab 이동 시 Layout이 튄다.
- **변경할 기능 또는 UX**: 상위 영역/현재 Page·Tab/Section 관계를 명확히. 세 표시가 모순되지 않게. 상위 Context 유지가 나으면 Page Title을 Tab 이름으로 교체하지 않는다.
- **영향 범위**: `app/AppShell.jsx`, `app/navConfig.js::activeNavPath/ROUTE_OWNER/groupForPath`, `screens/settings/SettingsShell.jsx`
- **필요한 공통 Component / 정책**: Active State 단일 표현(D-141 RAISE)
- **검증 방법**: `nav-active.test.js`·`crumb-root.test.jsx` 확장. Direct URL·Refresh·Back/Forward 실측.
- **완료 판단 기준**: 어느 관리 영역에 있는지 항상 알 수 있고 새로고침 후에도 유지된다.

## 47. 관리자 UI 최종 Audit

- **Phase**: P12-5
- **현재 문제 / 조사 대상**: 관리자 전용 검수 기준이 없었다.
- **변경할 기능 또는 UX**: Sidebar 이해도/기능 분산/Raw Key 잔존/설정 가능·읽기 전용 구분/Action 위험도/저장·적용 일치/컴포넌트 제각각/이모지 잔존/주요 Action End-to-End 동작 확인.
- **영향 범위**: 관리자 Route 46개
- **필요한 공통 Component / 정책**: -
- **검증 방법**: P12-5 체크리스트 + 실제 Browser 실행.
- **완료 판단 기준**: 디자인이 개선되었어도 동작하지 않거나 목적 불명한 관리자 기능이 남으면 미완료.

## 48. Sidebar/Navigation UI 재설계

- **Phase**: P3-4
- **현재 문제 / 조사 대상**: 다크 네이비 `#1B2447` raw hex 리터럴. 큰 알약형 active 그라데이션. 색 3중 정의. 아이콘 중복 사용(`ticket` 3회, `docs` 3회, `policy` 3회, `report` 3회).
- **변경할 기능 또는 UX**: Active 표현 재검토. Group Title/Parent/Child/선택 위계 분리. 펼침과 선택 혼동 제거. 아이콘은 탐색에 도움될 때만. Spacing/Weight/Indent/Hover/Focus 재설계. 폭 조정.
- **영향 범위**: `app/AppShell.jsx:232-442,766-789`, `app/navIcons.js`, `styles/tokens.css` sidebar 토큰
- **필요한 공통 Component / 정책**: Navigation Design System(사용자·관리자 공용)
- **검증 방법**: `sidebar-*.test.jsx` 5종 재작성. `tokens-baseline.test.js`를 Runtime 계약으로 이관.
- **완료 판단 기준**: Navigation이 과도하게 무겁지 않고, 펼침과 선택이 구분되며, 두 콘솔이 같은 언어를 쓴다.

## 49. Skill 적용 원칙

- **Phase**: §0, P0-1, P12-3
- **현재 문제 / 조사 대상**: 필수 Skill 3종의 설치·호출 가능 여부 확인 필요. `taste`라는 이름의 Skill은 없다.
- **변경할 기능 또는 UX**: UI/UX Pro Max·Impeccable·design-taste-frontend(tasteskill)를 실제 호출하고 적용 범위를 판단해 사용.
- **영향 범위**: -
- **필요한 공통 Component / 정책**: -
- **검증 방법**: §0에 호출 근거 기록. P12-3에서 재적용.
- **완료 판단 기준**: 세 Skill이 실제로 호출되었고 적용 범위 판단이 기록되어 있다.

## 50. 기능 보존과 UI 보존 분리

- **Phase**: §2, 전 Phase
- **현재 문제 / 조사 대상**: '기능 유지'를 이유로 현재 Component·Layout을 유지하려는 경향.
- **변경할 기능 또는 UX**: 보존 대상은 기능·데이터·권한·보안 통제·업무 흐름. Component/DOM/CSS Selector/Layout/Card 형태/Sidebar 형태/Chart 구현/Library/Component 이름/Visual Pattern은 보존 대상이 아니다.
- **영향 범위**: 전 Phase
- **필요한 공통 Component / 정책**: -
- **검증 방법**: P12-1 Before/After 7기준.
- **완료 판단 기준**: 기능은 그대로인데 시각 시스템은 실질적으로 교체되었다.

## 51. 관리자 IA 판단 기준

- **Phase**: P3-5
- **현재 문제 / 조사 대상**: 8개 영역을 정답으로 오해할 위험. 기존 Shell이 IA를 결정할 위험.
- **변경할 기능 또는 UX**: Domain→Page→(필요시)Tab/View/Section 순. 모든 하위를 Tab으로 만들지 않는다. 서로 다른 Resource를 같은 Domain이라는 이유로 합치지 않는다. 기존 코드 구조와 RBAC이 IA를 결정하지 않는다.
- **영향 범위**: `app/navConfig.js::NAV`, `screens/settings/SettingsShell.jsx`
- **필요한 공통 Component / 정책**: IA 먼저, Shell은 그 다음
- **검증 방법**: Tab 과다 여부 확인. 업무 기준 위치 예측 가능성 확인.
- **완료 판단 기준**: 각 Route에 유지/통합/Tab/이동/제거 결정과 근거가 있고, Tab이 과다하지 않다.

## 52. Route/Archetype/Component Inventory 재수행

- **Phase**: P0-2, P0-5
- **현재 문제 / 조사 대상**: 기존 Audit 문서의 PASS 기록에 의존할 위험.
- **변경할 기능 또는 UX**: Route 73개 전수 Inventory(목적·Workflow·권한·Archetype·공용 컴포넌트·지역 구현·상태). Empty/Loading/Error/Permission/Long text/Many data 상태 확인.
- **영향 범위**: 전 Route
- **필요한 공통 Component / 정책**: -
- **검증 방법**: `docs/UI_INVENTORY.md` 생성 완료. `failure_states.py`·`hostile_data.py`.
- **완료 판단 기준**: Route 73개와 화면 파일 102개가 빠짐없이 분류되어 있다.

## 53. Design Direction 성급한 고정 금지

- **Phase**: §2, P0-1
- **현재 문제 / 조사 대상**: AI가 고른 방향을 사용자 확정으로 기록할 위험.
- **변경할 기능 또는 UX**: PRODUCT.md → concept-seed → 방향 결정 → 근거 기록. 사용자 확정사항은 §1.5에만.
- **영향 범위**: `PRODUCT.md`, `docs/DECISIONS.md` D-141
- **필요한 공통 Component / 정책**: -
- **검증 방법**: D-141에 절차·후보 7개·챌린저 판정·RAISE 기록 완료.
- **완료 판단 기준**: 방향과 근거가 기록되어 있고 사용자 확정사항과 구분되어 있다.

## 54. Baseline/Test/Selector/Library를 제약으로 쓰지 않기

- **Phase**: §1.6, P1-2, P6
- **현재 문제 / 조사 대상**: `design/baseline/preview-standalone.html`이 4개 파서 테스트의 시각 정본. 304개 테스트 중 상당수가 옛 DOM/CSS 고정.
- **변경할 기능 또는 UX**: 목업 폐기. 테스트를 Runtime 계약 검증으로 이관 후 재작성(삭제·약화 금지). Chart 구현 방식 재평가. Selector·Export·Route도 같은 기준.
- **영향 범위**: `design/baseline/*`, `ui/baselineTokens.js`, 파서 테스트 4종, `scripts/ui_qa/baseline.py`, `ui/charts/*`
- **필요한 공통 Component / 정책**: 검증 구조 이관
- **검증 방법**: 이관 후 잔존 참조 0건 검사.
- **완료 판단 기준**: 새 디자인이 옛 구조에 맞춰지지 않았고 테스트는 새 계약을 검증한다.

## 55. 보안·권한 범위와 UI 기능 제거 구분

- **Phase**: P3-2, P4-2, P4-3, P5-1, P5-2
- **현재 문제 / 조사 대상**: '문서 잠금 제거'가 열람 제한까지 지울 위험. 'Legacy 제거'가 실사용 기능을 지울 위험.
- **변경할 기능 또는 UX**: 잠금과 열람 권한은 별개. RBAC·Authorization·접근 정책·Secret 보호·인증 정책을 UI 개선을 이유로 축소하지 않는다. Legacy 제거는 Consumer·API·데이터·운영 의존성 확인 후. 불명확하면 통제 유지.
- **영향 범위**: `app/team_docs/service.py`, `app/core/authz.py`, `app/core/deps.py`, `app/impersonation/*`
- **필요한 공통 Component / 정책**: -
- **검증 방법**: 보안 테스트 전체가 그대로 통과해야 한다.
- **완료 판단 기준**: 보안 통제가 하나도 줄지 않았다.

## 56. 계획 완전성 · Traceability Gate

- **Phase**: P0-3
- **현재 문제 / 조사 대상**: 요구사항 번호와 Phase만 연결하고 내용이 없을 위험.
- **변경할 기능 또는 UX**: 지시 1~70 전부에 현재 문제/변경 내용/영향 범위/공통 변경/검증 방법/완료 기준을 적는다.
- **영향 범위**: 이 문서
- **필요한 공통 Component / 정책**: -
- **검증 방법**: 빠진 번호 0건·내용 없는 번호 0건·없는 Phase 참조 0건을 스크립트가 확인.
- **완료 판단 기준**: 70개 항목 전부가 6개 필드를 채우고 있다.

## 57. 과도한 추상화 방지

- **Phase**: P2, P12-2
- **현재 문제 / 조사 대상**: 공통화 자체가 목적이 될 위험. Boolean prop 누적.
- **변경할 기능 또는 UX**: 실제 반복되는 Visual Rule·Interaction·Behavior만 공통화. 목적이 다른 것을 모양이 비슷하다고 합치지 않는다. 공통 Primitive와 목적별 Component 분리.
- **영향 범위**: `ui/kit.jsx` 전체
- **필요한 공통 Component / 정책**: -
- **검증 방법**: Migration 후 미사용 Legacy Component·CSS·Selector·Token 정리.
- **완료 판단 기준**: 하나의 컴포넌트가 여러 역할을 겸하지 않고, 같은 역할이 복제되어 있지도 않다.

## 58. 사용자 Navigation도 감사 대상

- **Phase**: P3-6
- **현재 문제 / 조사 대상**: 사용자 Sidebar 4그룹 18항목을 유지로 미리 확정할 위험.
- **변경할 기능 또는 UX**: 업무 흐름·사용 빈도·탐색 비용 기준 재검토. 적절하면 유지, 아니면 기능·권한 보존하며 조정.
- **영향 범위**: `app/navConfig.js::USER_NAV`, `USER_SEG_PATHS`
- **필요한 공통 Component / 정책**: Navigation Design System 공용
- **검증 방법**: `user-segment-routes.test.js`·`nav-ia-taxonomy.test.js` 갱신.
- **완료 판단 기준**: 사용자 Navigation이 조사 결과에 근거해 유지 또는 조정되었다.

## 59. 구현 방식·기술 선택을 사전에 고정하지 않기

- **Phase**: §2.1, P1-2, P1-4, P6
- **현재 문제 / 조사 대상**: 기존 구현이 있다는 이유로 유지 결정할 위험.
- **변경할 기능 또는 UX**: Chart·Grid·Search·Modal·Form·Navigation·CSS Architecture·Theme·Component API를 각각 조사. Visual Quality·접근성·Responsive·Interaction·유지보수성·성능·일관성으로 판단.
- **영향 범위**: `ui/charts/*`, `ui/kit.jsx`, `ui/theme.js`, `package.json`
- **필요한 공통 Component / 정책**: -
- **검증 방법**: 각 결정의 근거를 `DECISIONS.md`에 기록.
- **완료 판단 기준**: '테스트가 있어서'·'이미 있어서'가 유지 근거로 쓰이지 않았다.

## 60. 최종 Visual QA · IA QA 강화

- **Phase**: P12-1, P12-2, P12-6
- **현재 문제 / 조사 대상**: Route가 렌더되고 테스트가 PASS하는 것만 확인할 위험.
- **변경할 기능 또는 UX**: Before/After 비교로 Visual System이 실질 교체되었는지 확인. Dashboard를 한 가지 Pattern으로 재획일화하지 않는다. IA는 항목 수가 아니라 찾기 쉬움으로 판정.
- **영향 범위**: 전 Route
- **필요한 공통 Component / 정책**: -
- **검증 방법**: P12-1 7기준. Empty/Loading/Error/Permission/Long text/Many data 상태에서도 확인.
- **완료 판단 기준**: Color/Border/Radius만 바뀐 결과는 완료로 처리하지 않는다.

## 61. 명명된 화면으로 범위 한정 금지

- **Phase**: P0-2, P7-5, P8-14
- **현재 문제 / 조사 대상**: 지시에 이름이 적힌 화면만 고칠 위험.
- **변경할 기능 또는 UX**: 사용자·관리자 영역 전체가 대상. 동일·유사 목적/구조/Component/Pattern을 쓰는 화면을 함께 조사. 지시에 없는 문제도 Root Cause를 판단해 함께 개선.
- **영향 범위**: Route 73개 전체
- **필요한 공통 Component / 정책**: -
- **검증 방법**: Inventory 기준 Route별 적용 여부 확인.
- **완료 판단 기준**: 이름이 언급되지 않은 화면에도 새 Design System이 적용되었다.

## 62. 정보 완전성 · 기능 능동 개선

- **Phase**: P4-4, P6, P7-3
- **현재 문제 / 조사 대상**: 현재 정보를 재배치만 할 위험.
- **변경할 기능 또는 UX**: 각 Page가 지원해야 하는 판단·행동을 먼저 정의하고 빠진 정보/상태/비교/Trend/Context/Action 조사. 기존 데이터로 제공 가능하면 Backend/API까지 End-to-End 구현.
- **영향 범위**: `screens/Dashboard.jsx`, `screens/Home.jsx`, `screens/Sprint.jsx`, `app/home/*`, `app/reports/*`, `app/projects/*`
- **필요한 공통 Component / 정책**: 필요 시 신규 API
- **검증 방법**: 추가 정보의 출처·권한·Empty·Loading·Error·Responsive·접근성·테스트 완성도 확인.
- **완료 판단 기준**: 장식용 KPI 없이, 행동으로 연결되는 정보가 추가되었다.

## 63. Layout뿐 아니라 IA·Content Architecture 재검수

- **Phase**: P6, P10-2, P0-2
- **현재 문제 / 조사 대상**: Width/Height/Grid/Spacing만 볼 위험.
- **변경할 기능 또는 UX**: 읽는 순서·중요도 배치·관련 정보 근접·무관 정보 분리·Action 거리·정보 과부족·중복 표시를 Page 단위로 판단. 빈 공간이 Layout 문제인지 정보 누락인지 구분. Card/Table/Chart/List/Timeline 중 적합한 표현 재선택.
- **영향 범위**: 전 Route
- **필요한 공통 Component / 정책**: -
- **검증 방법**: 넓은 화면에서 공간을 실제로 쓰는지 확인(양쪽 빈 공간·의미 없는 카드 확대 금지).
- **완료 판단 기준**: 각 화면이 정렬만 개선된 것이 아니라 정보 구조와 Interaction까지 함께 개선되었다.

## 64. preview-standalone.html 폐기 · 검증 구조 이관

- **Phase**: §1.6, P1-2
- **현재 문제 / 조사 대상**: 목업이 시각 정본. **실측 확인**: 제품 Runtime Consumer 없음. 읽는 주체는 vitest 파서 4종(`baselineTokens.js`)과 `scripts/ui_qa/baseline.py`뿐. 그 외 '정본' 선언 주석 12곳.
- **변경할 기능 또는 UX**: 새 Baseline으로 다시 쓰지 않고 제거. 테스트를 Runtime Theme/Token/Component Contract 또는 Browser Rendering 검증으로 교체. `baseline.py`는 방법론 유지·기준만 교체. 주석 정리.
- **영향 범위**: `design/baseline/*`, `ui/baselineTokens.js`, `ui/theme-baseline.test.js`, `styles/tokens-baseline.test.js`, `ui/density.test.jsx`, `app/topbar-baseline.test.jsx`, `scripts/ui_qa/baseline.py`, `tests/regression/test_login_visual_contract.py`, `ui/density.js`
- **필요한 공통 Component / 정책**: Runtime 계약 검증 구조
- **검증 방법**: 이관 후 잔존 참조 0건을 `static_checks.sh`가 검사.
- **완료 판단 기준**: 목업 파일이 저장소에서 사라지고, 같은 목적을 실제 제품 UI가 검증한다.

## 65. Direction 확정 전 세부 Visual Token 고정 금지

- **Phase**: §2.1, §2.3, P0-1, P1-3
- **현재 문제 / 조사 대상**: 계획서가 Surface 4단·중립1+강조1·type ratio·motion 150~250ms를 확정처럼 적을 위험.
- **변경할 기능 또는 UX**: Surface 단계 수/Color 구조/Radius/Typography Scale/Motion Duration/Shadow 단계/Nav Active 표현을 P0 전에 고정하지 않는다. 브랜드 색을 UI 강조색으로 사전 고정하지 않는다.
- **영향 범위**: `ui/theme.js`, `styles/tokens.css`, D-141
- **필요한 공통 Component / 정책**: P0 결과 → P1 Token 순서
- **검증 방법**: P0 결과와 P1 Token이 모순되지 않는지 대조.
- **완료 판단 기준**: P1의 모든 토큰 값이 D-141 방향 계약에서 파생되었음을 설명할 수 있다.

## 66. 공통 Component를 Archetype에 맞게 적용

- **Phase**: P2, P7-1
- **현재 문제 / 조사 대상**: '전 Route 필수'가 집중형 화면에 불필요한 구조를 강제할 위험.
- **변경할 기능 또는 UX**: PageHeader/DetailLayout/SearchFilterBar/DataTable/Settings Pattern을 Page 목적과 Archetype에 적합할 때 사용. 로그인·Full-screen Workflow·Chat·Game에 Page Header·Breadcrumb·도움말·Section 강제 금지. Detail 2:1은 본문형에만.
- **영향 범위**: `ui/kit.jsx::PageHeader`, `screens/Chat.jsx`, `screens/GameRoom.jsx`, `screens/Project.jsx`, `screens/ChatRooms.jsx`, `screens/Users.jsx`
- **필요한 공통 Component / 정책**: Archetype별 적용 판정표(`docs/UI_INVENTORY.md` §2)
- **검증 방법**: Archetype별 캡처 확인.
- **완료 판단 기준**: 공통 Design Language는 전 화면이 공유하되 Layout은 Archetype에 맞다.

## 67. Global Notification과 Operational Status 구분

- **Phase**: P3-2
- **현재 문제 / 조사 대상**: 헤더 Legacy 제거가 관리자 운영 상태 정보까지 지울 위험.
- **변경할 기능 또는 UX**: 사용자 알림은 종 단일 진입점. 그러나 Portal 상태 표시·관리자 Operational Status·서비스 Health·장애·조치 필요 정보는 유지하고 적절한 관리 화면에서 다시 제공. 네 가지를 다른 것으로 취급.
- **영향 범위**: `app/Banners.jsx`, `app/StatusNotices.jsx`, `app/observability/router.py:129-185`(components[], LATE/STALLED 임계), `screens/Dashboard.jsx`, `screens/ops/Diagnostics.jsx`
- **필요한 공통 Component / 정책**: Feedback 위계 + 관리자 상태 표현
- **검증 방법**: `GET /api/system/status`의 `components[]`가 관리자 화면에서 보이는지 확인. `statusNotices.test.jsx` 재작성.
- **완료 판단 기준**: 사용자 화면은 조용해지고 관리자는 필요한 상태 정보를 잃지 않는다.

## 68. 위험 Action E2E는 상태 복구까지 포함

- **Phase**: P11(7단계)
- **현재 문제 / 조사 대상**: 성공 응답 확인만으로 검증을 끝낼 위험. TEST 서버 상태를 망가뜨릴 위험.
- **변경할 기능 또는 UX**: 실행 전 상태 기록 → Network·API·Backend·실제 시스템·UI 5중 일치 확인 → 원상복구 + 복구 확인 → 불가역은 Fixture → 순서 설계 → 계획 후 수행.
- **영향 범위**: `app/sysops/*`(service.control·cert.install·dns/hostname/ntp/proxy/timezone), `app/users/*`, `app/settings/*`, `app/integrations/*`, `app/offboarding/*`
- **필요한 공통 Component / 정책**: 위험 Action 검증 프로토콜
- **검증 방법**: 각 Action의 사전 상태·사후 상태·복구 결과를 기록.
- **완료 판단 기준**: 위험 Action이 실제로 동작함을 증명했고 환경이 원상태로 돌아왔다.

## 69. 계획의 구현안은 후보

- **Phase**: §2.4
- **현재 문제 / 조사 대상**: 계획 문장을 그대로 구현하려고 잘못된 구조를 유지할 위험.
- **변경할 기능 또는 UX**: 파일명·Component명·Library 유지·Component 제거·Layout·Token 구조는 구현 후보. 더 적절한 방법이 확인되면 바꾸되 목적·기능·데이터·권한·보안·업무 흐름은 임의 변경하지 않는다. 요구사항과 완료 기준은 축소 불가.
- **영향 범위**: 전 Phase
- **필요한 공통 Component / 정책**: -
- **검증 방법**: 변경 시 근거를 `DECISIONS.md`에, 갱신을 이 문서에 반영.
- **완료 판단 기준**: 수단 변경이 근거와 함께 기록되어 있고 요구사항은 하나도 줄지 않았다.

## 70. 기능 재사용 ≠ Visual 재사용

- **Phase**: §1.4, P12-1
- **현재 문제 / 조사 대상**: '이미 잘 되어 있어 보존'이 Visual까지 보존으로 새어나갈 위험. 계획서 초안이 실제로 이 오류를 냈다.
- **변경할 기능 또는 UX**: 재사용 대상은 기능·Interaction Logic·접근성 처리·데이터 처리·검증된 기술 구조뿐. PageHeader·CommandPalette·DataTable·FormModal·ErrorState·Search·Navigation도 Visual Audit 대상. 유지하려면 새로 설계한 결과와 비교한 근거 필요.
- **영향 범위**: `ui/kit.jsx` 전체, `app/CommandPalette.jsx`, `app/AppShell.jsx`, `ui/Pager.jsx`, `ui/filters.jsx`
- **필요한 공통 Component / 정책**: -
- **검증 방법**: P12-1의 Before/After 7기준.
- **완료 판단 기준**: '익숙함·이미 구현·테스트 존재·현재도 동작·MUI 기본'이 유지 근거로 쓰이지 않았다.

