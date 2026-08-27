# PLAN — ClovirAssist UI/UX 재설계와 업무 흐름 개선

> 원 지시서는 [`DIRECTIVE.md`](DIRECTIVE.md) 다. 이 파일은 그 지시서를 **검증 가능한 묶음**으로
> 쪼갠 정본이고, 지금 어디까지 왔는지는 [`WORK_STATE.md`](WORK_STATE.md) 가 적는다.
>
> 이 계획은 CLAUDE.md §7.0 의 **일반 개발**이다. S0~S22 의 Acceptance 축(Coverage · Functional
> Flow · Pilot · Capture · Evidence)은 이 계획의 Exit 조건이 아니다. 닫힌 그 계획의 원장은
> [`../ui-renewal/`](../ui-renewal/WORK_STATE.md) 이고 이 파일이 그것을 덮어쓰지 않는다.

## 0. 이 계획이 지키는 것 넷

1. **공통 원인은 공통 부품에서 고친다.** 화면별 CSS 값으로 증상을 덮지 않는다.
2. **시안은 정보 계층의 근거이고 픽셀의 근거가 아니다.** 공통 Shell · Sidebar · Header ·
   Typography · Spacing · Theme · Breadcrumb · Page Title · 우측 Primary Action 은 그대로 둔다.
3. **실제 Source 와 Domain Contract 가 시안보다 위다.** 시안에 있는 값을 만들기 위해 가짜
   데이터를 만들지 않는다.
4. **권한의 정본은 서버다.** 화면이 감춘 것을 서버가 허용하는 상태로 두지 않는다.

## 1. 어휘 확정 — Status 와 Signal 은 다른 축이다

**Workflow Status 여섯** (한 티켓은 정확히 하나를 갖는다):

`계획` · `진행 중` · `검증` · `완료` · `보류` · `취소`

**Signal 셋** (Status 와 독립이고, 동시에 여러 개가 켜질 수 있다):

| Signal | 어디서 오는가 |
|---|---|
| 이슈 있음 | 사람이 켜는 플래그 |
| 차단됨 | 사람이 켜는 플래그와 그 사유. `blocks` 관계에서 파생시키지 않는다 (D-349) |
| 지연 | `due_date` 와 종료 여부에서 **계산한다**. 저장하지 않는다 |

**`백로그`는 Status 가 아니라 위치다.** `sprint_id IS NULL` 인 활성 티켓이 백로그다.

### 지금 데이터와의 거리

현재 `app/work/workflow.py` 의 어휘는 `계획 · 이슈 · 진행 · 검증 · 완료 · 취소` 다. 차이는 둘이다.

- `진행` → 표시 이름만 `진행 중` 으로 바꾼다. 저장값(`key`)은 안 옮긴다.
- `이슈` → **일괄 치환하지 않는다.** 실제 `이슈` 티켓의 상태 변경 이력을 먼저 조사해
  「막혀서 멈춘 것」과 「그냥 진행 중인데 문제가 있는 것」을 가른 뒤 Migration 을 설계한다.
  그 조사 결과와 결정은 D-349 에 적는다.

## 2. 묶음 — 구현 → 표적 검증 → 다음 묶음

각 묶음은 독립으로 Commit 할 수 있는 단위다. 묶음마다 마지막에 표적 검증을 돌리고,
전량 회귀와 최종 캡처는 **G 가 끝난 뒤 한 번**만 돌린다(지시서 §27).

| 묶음 | 무엇을 하는가 | 원 요구 |
|---|---|---|
| **A** | 공통 계약 — Status/Signal · Filter · Table 정렬 · Detail 폭 · Callout · 관리자 Layout · 목록 상태 복원 · Avatar | 1·2·6·7·8·13·15·16·17·19·20·21 + Avatar |
| **B** | Ticket — 새 티켓 작성 도움 · Editor Toolbar · 예상 WD/마감 필수 · 담당자 변경 · Inline Status | 3·4·9·18 |
| **C** | Project — 목록 Summary 시각화 · 상세 Ticket 발생 추이/진행률/Health | 5·10·11 |
| **D** | Sprint Domain · Backlog · 작업 보드 · 스프린트 회의 | 12 + Backlog/Sprint 흐름 |
| **E** | Chat 재설계와 Chat 데이터 초기화 | 14 |
| **F** | Profile · 역할 UX · `변경 요구` 의미 확정 | 17·22 |
| **G** | Document 초기화와 Knowledge Workspace/Editor/Trash 재설계 | 23 |

## 3. 묶음별 Exit 조건

### A. 공통 계약

- `계획 · 진행 중 · 검증 · 완료 · 보류 · 취소` 여섯이 Workflow Status 정본이고, `이슈`·`차단`·
  `지연` 은 Status 목록에 없다.
- 같은 의미가 My Tickets · Team Tickets · Ticket Detail · Home · Board · Sprint Meeting ·
  Search · Project Ticket 목록에서 **같은 Pill/Icon/Semantic Color** 로 선다.
- 행 전체를 상태색으로 칠하지 않는다. 위험이 아닌 값에 강한 Red 면을 쓰지 않는다.
- Project 화면의 Filter 가 My Tickets · Team Tickets 와 같은 `FilterSurface` 계약을 쓴다.
- 모든 DataTable 의 Header Label 이 가운데 정렬이고, Sort/Filter 아이콘이 그 가운데를
  밀지 않는다. Cell 정렬은 `columnTypes` 한 곳에서 나온다.
- Ticket Table 의 `추가` 열이 `생성 일자` 다.
- Aside 없는 상세 화면에서 본문이 Content 영역을 실제로 쓴다.
- `안내 · 주의 · 성공 · 오류` 네 종 Callout 이 한 부품에서 나온다.
- 관리자 화면이 `Breadcrumb → Title+Primary → 설명 → Callout → Filter → 본문` 순서를 지킨다.
- 목록 → 상세 → 수정 → 뒤로 에서 Scroll · Filter · Sort · Page · Group · Tab · Search ·
  Project/Sprint Context 가 살아 있다. 페이지별 전역변수를 쓰지 않는다.
- Avatar 가 한 부품에서 나오고 상단 사용자 · Chat · 담당자 · 댓글 · Board Card ·
  Sprint Meeting · Document 작성자 · Activity 에서 같은 Source 를 쓴다. 기본 Avatar 는
  사용자 id 를 Seed 로 안정 배정하고 외부 URL 에 의존하지 않는다. 업로드는 원형 Crop UI 를
  거치고 서버가 MIME·크기·EXIF 를 검사한 뒤 다시 인코딩한다.

### B. Ticket

- `새 티켓` 의 오른쪽 도움말이 `배경/문제 · 목표 · 작업 범위 · 완료 기준` 넷이고 각각 짧은
  실제 예시를 갖는다.
- Editor Toolbar 가 Renderer 가 실제 지원하는 것만 낸다. 리뉴얼 중 사라진 기능은 복구한다.
- 예상 WD 와 마감일이 **API Create Contract 에서** 필수다. 화면 표시만으로 끝내지 않는다.
- 일반 사용자가 자기 접근 범위 안에서 담당자를 바꿀 수 있고, 그 범위를 서버가 다시 판정한다.
- My Tickets 의 Grid 에서 상태를 바꿀 수 있고 실패하면 원복하고 이유를 말한다.

### C. Project

- 목록 Summary 의 진행률이 Progress Bar 를 갖고 Health 가 원형 시각화를 갖는다. Summary 를
  누르면 아래 목록이 그 조건으로 좁아진다.
- 상세가 `개요 → Ticket 발생 추이 → 진행률 → Health → 나머지` 순서다. 발생 추이는
  `created_at` 기준 날짜별 생성량이고 긴 기간은 Chart 안에서 좌우로 탐색한다. 페이지 전체에
  가로 스크롤을 만들지 않는다.

### D. Sprint · Backlog · Board · Sprint Meeting

- 티켓 생성 위치가 기본값을 정한다. 일반 `새 티켓` 은 백로그로, Board 의 Sprint Context 안
  추가는 그 Sprint 의 `계획` 으로 간다. 서버가 Project/Sprint 접근 권한을 다시 본다.
- `스프린트에 추가` 가 명시적 Action 이다. 상태를 손으로 `계획` 으로 바꾸는 것이 편입이 아니다.
- Board 상단에 Project Filter · Sprint Selector · Assignee Filter · 내 티켓만 · 차단만이 있다.
- 기본 실행 Column 은 `계획 · 진행 중 · 검증 · 완료` 다. `보류` 는 접힌 칸이고 `취소` 는
  기본 Board 에서 숨는다. Signal 때문에 카드를 다른 Column 으로 옮기지 않는다.
- Column 이 각자 굴러가고 Board 전체가 티켓 수만큼 아래로 자라지 않는다.
- 백로그 탭이 Filter · 검색 · 담당자 · 우선순위 · 난이도 · 예상 WD · 마감 · 정렬 · 빠른 수정 ·
  `스프린트에 추가` 를 갖는다.
- Sprint Meeting 이 여섯 물음에 답한다. 오늘 논의할 항목이 `지연 · 차단 · 미할당 · 마감 임박 ·
  범위 변경` 이고 각각 해당 티켓으로 간다. 회의 결정과 다음 Action 이 저장된다.
- 시각화는 실제 데이터로 계산하고 계산식을 문서에 고정한다. Health 를 장식으로 만들지 않는다.

### E. Chat

- Room List · Room Header · 참여자 · Message Area · Composer 구조다.
- 모든 메시지가 Avatar · 이름 · 날짜/시간을 갖는다. 자기 메시지도 Avatar 를 갖는다. 날짜가
  바뀌면 Day Separator 가 선다.
- Chat Domain 데이터만 초기화한다. 실행 전 Snapshot · 표 관계 · Row Count 를 기록한다.

### F. Profile · 역할

- `둘러보기` 가 개인 UI 설정보다 위에 있고 Avatar 기능이 `내 프로필` 에 있다.
- 역할 다섯의 설명이 실제 Permission 과 일치한다. 추측으로 새 의미를 만들지 않는다.
- `변경 요구` Checkbox 의 Backend Field 를 추적해서 이름을 실제 의미로 바꾸거나 제거한다.

### G. Document

- 현재 사용자 Document 데이터와 그 문서에서 파생된 DB 데이터를 비운다. User · Organization ·
  Project · Ticket · Storage Binary 는 건드리지 않는다. Notion 재이관은 이번 범위가 아니다.
- Document Main 이 Explorer(Space/Folder/즐겨찾기/최근/내 초안) + 밀도 있는 목록 + 필요한
  경우의 Right Rail 이다. 공통 PageShell 을 유지한다.
- `새 문서` 가 제목(필수) · Space(필수) · Folder · Tags · Template 를 받고 성공하면
  `/knowledge/{id}` 로 간다.
- Editor 가 Content 폭을 실제로 쓰고, Right Panel 이 문서 정보 · Tags · 관련 문서/Backlinks ·
  첨부 · 댓글을 든다. 좁은 화면에서는 Drawer/Tab 으로 내려간다.
- 서버에 있는데 화면이 없던 것을 배선한다 — Move · Archive · Version Detail · Relation ·
  Attachment · Space 생성/수정.
- Native Knowledge Trash 가 공통 휴지통 Layout 과 7일 정책을 그대로 쓰고 `archived` 를 되돌리는
  Restore API 를 갖는다. Legacy `team_docs` Trash 를 정본으로 쓰지 않는다.
- Search/AI 의 권한 계약은 그대로다. 권한 없는 문서와 Archived 문서는 후보에 안 들어간다.

## 4. 검증 방식

- 묶음 안에서는 `python scripts/verify.py` 의 표적 실행만 쓴다.
- 전량(`--full`)과 최종 Browser Capture 는 **G 이후 한 번**이다.
- Browser 확인은 1366 · 1920 · 2560 과 Light/Dark 를 대표로 본다.
- 데이터 삭제(Chat · Document)는 실행 전에 표 · FK · Row Count · Snapshot 위치를 기록한다.

## 5. 원 요구 1~23 이 어디로 갔는가

| # | 요구 | 묶음 |
|---|---|---|
| 1 | Status/Signal 분리와 표현 통일 | A |
| 2 | Project Filter 공통화 | A |
| 3 | 새 티켓 작성 도움 | B |
| 4 | Editor 기능 복구 · 예상 WD/마감 필수 | B |
| 5 | Project Summary 시각화 | C |
| 6 | 표 Header 가운데 정렬 | A |
| 7 | `추가` → `생성 일자` | A |
| 8 | Ticket/Document 상세 폭 | A |
| 9 | 일반 사용자 담당자 변경 | B |
| 10 | 진행률 Bar · Health Gauge | C |
| 11 | Project Ticket 생성 추이 | C |
| 12 | 작업 보드 · 스프린트 회의 재설계 | D |
| 13 | 열 정렬 규칙 | A |
| 14 | Chat 재설계와 데이터 삭제 | E |
| 15 | Ticket Status Color/Pill | A |
| 16 | 게시판/제안 상세 폭 | A |
| 17 | Profile 둘러보기 위치 | A·F |
| 18 | My Tickets Inline Status | B |
| 19 | 상세 복귀 시 목록 상태 복원 | A |
| 20 | 공통 안내/주의 | A |
| 21 | 관리자 공통 Layout | A |
| 22 | 역할 차이와 `변경 요구` | F |
| 23 | Document 초기화와 재설계 | G |
| + | 기본 Avatar 와 Crop 업로드 | A |
| + | Backlog 는 Status 가 아니다 | A·D |
| + | Sprint Domain 과 Board 연결 | D |
