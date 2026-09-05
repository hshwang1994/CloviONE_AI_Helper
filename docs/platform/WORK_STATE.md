# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-05** (관리자 화면 전수 UI/UX 정리 + 내 프로필 밀도 정돈 —
  D-452~D-458)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: 사용자가 「관리자 페이지 전체를 사용자 페이지 디자인 기준으로 정리하라 — 머리·
  도움말·검색/필터/동작 줄·표·모달·폼·타이포·탭·배지·빈 상태·정렬·간격·저정보 전폭 화면·
  밀도·스크롤·옛 UI 잔재」를 지시했다. **버그 수정·API·백엔드·데이터·권한·업무 로직·검증
  로직·동작 변경·새 기능·사용자 화면 디자인 변경은 금지**였고, 예외 하나를 사용자가 직접
  열었다: 「내 프로필 디자인도 같이」. 탭 화면은 「제목 고정, 탭은 아래」, 설정성 화면은
  「판 격자 유지, 밀도만 정돈」을 골랐다.

  기준은 사용자 화면이 실제로 쓰는 공통 구현이다(`PageHeader` 의 `?` · `FilterSurface` ·
  `ListCard`+`DataTable` · `EmptyState` · `Section`/`SubGroup` · `/new-ticket` 의 폼 판+레일 ·
  `/sprint` 의 `MetricStrip` · 폭은 셸이 소유). 다섯 패킷으로 나눠 각각 검증·커밋했다:
  ① 공유 층 — 탭 그릇 h1 고정 · 도움말은 `?` · 머리 동작 슬롯(`HeaderSlot.jsx`) · 「저장된
  뷰」 고아 줄 · 빈 상태의 절차 산문 → `?` · 키/값 줄 네 벌 → `DetailRow` · 죽은 CSS.
  ② 설정성 화면 — `/profile` + 설정 4탭이 `pairTracks`·`DetailRow`·`SettingRow` 한 어휘.
  ③ 마법사·목록성 손글 화면 — 초기 설정·오프보딩·일괄 작업 줄·조직 정합성.
  ④ 운영·보고서 — 진단·대시보드 「최근 주요 변경」·메일 발송·개발자 월간 리포트·달력·
  조직도/사용자의 리터럴.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다.
- deployed: **`e6df9272`** 그대로 — **이 회차는 배포하지 않았다**(범위 밖. 별도 지시 때
  `git archive` 로 보낸다 — 기억 파일 `deploy-needs-git-archive-over-ssh`).
- verification: 아래 「이번 회차가 잰 것」 절.
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306). 이 회차의 부분 캡처는
  `dist/ui-qa/admin-uiux-before/`(변경 전 · 49 라우트 × 3 뷰포트 × 2 테마) 와
  `dist/ui-qa/admin-uiux-after/`(변경 후 · 같은 라우트 × 4 뷰포트 × 2 테마) 이며 정본을
  안 옮긴다.
- ui_gate: 변화 없음.

## 무엇을 고쳤나

### 공유 층 (D-452 ~ D-456)

| 자리 | 무엇 |
|---|---|
| `ui/kit.jsx` | `PageHeader` 의 `tab` prop 삭제(h1 = 그릇 제목) · `helpId` 는 `useId` · `GuidanceBlock`(준비물/절차/기대 결과) · `DetailGrid`/`DetailRow`(키/값 줄의 정본) |
| `ui/HeaderSlot.jsx` (신설) | `HeaderActionsProvider`/`HeaderActionsHost`/`HeaderActions` — 탭 본문의 머리 동작이 그릇 머리로 간다(portal, 없으면 fallback) |
| `screens/data-screen/screenHelp.jsx` (신설) | `canOnboardFor`·`buildScreenHelp` — 단독·탭 양쪽의 도움말 정본 |
| `ui/TabShell.jsx` · `settings/SettingsShell.jsx` · `app/AdminRoutes.jsx` | 탭 정의에 `help`/`helpTone` · 그릇이 `?` 와 머리 동작을 그린다 · 달력 탭 도움말은 `SchedulerCalendar` 의 `Note` 에서 이관 |
| `screens/DataScreen.jsx` | embedded 안내 상자 제거 → `HeaderActions` · 「저장된 뷰」는 검색 있으면 `ToolbarEnd`, 없으면 `FilterActions` · 빈 상태는 `situation`/`action`/`relatedLink` 만 · 상세 모달은 `DetailRow` |
| `Users.jsx` · `columnHelpers.jsx` · `JsonBlock.jsx` · `registry/governance.js` | 자기 키/값 줄 → `DetailRow`(`KeyValueRow`·`.c-kv` 삭제) |
| `styles/screens.css` · `ui/kit.css` | 죽은 규칙 삭제(`.c-toolbar-*`·`.c-kv*`·`.msg-*`·`.docs-*`·`.devrep-*`·`.k-link`) · 인쇄 규칙은 `.c-body` 만 남긴다 |

### 설정성 화면 (D-457 · D-458)

| 자리 | 무엇 |
|---|---|
| `ui/density.js` | `pairTracks(가중치)` · `FORM_FIELD_CONTAINER`/`FORM_FIELD_GRID`(컨테이너 질의 1·2·3열) |
| `ui/adminKit.jsx` | `SettingRow` 한 행 리듬(py 1 · 설명 caption) · `SettingList` 가 `sx` 를 받는다 |
| `Profile.jsx` · `settings/AccentPicker.jsx` | 계정 `DetailRow` · 알림/방해금지 `SettingRow` · 둘러보기는 계정 판 안 `SubGroup` · 강조색은 `SectionTitle`+토큰 |
| `settings/SettingsMain.jsx` · `ops/Maintenance.jsx` | 표는 `ListCard` · 유지보수는 `Section` 안 1.2:0.8 짝(모드 판 + 공지 판) |
| `SystemOps.jsx` · `StorageProviders.jsx` · `LlmConsole.jsx` | 1.15:0.85 짝 판 · 0건은 `EmptyState layout="page"` + 머리 동작 슬롯 · 폼 판 + 로그인 절차 레일(`FORM_FIELD_GRID`) |

### 마법사·목록성 손글 화면 (D-457 · D-458)

| 자리 | 무엇 |
|---|---|
| `SetupWizard.jsx` | 목록 판 + 요약 레일(문장 + `MetricStrip`) · 상태는 `Badge` · 설명 상수 하나 |
| `Offboarding.jsx` | `FilterSurface`/`SearchBox` + `ResultLine` + `ListCard` · 요약은 `Section` · 폼 판 + 「실행하면」 레일(`planLines` 를 확인 대화와 공유) · 상세는 `DetailRow` |
| `UsersBulk.jsx` | 일괄 작업 줄이 판을 벗고 `ToolbarRow` 둘 · 「일괄 지정」은 `FilterSelect` |
| `Integrity.jsx` (+ `integrity.test.jsx` 신설) | 0건 항목은 `SettingRow` 줄 · 건수 있는 항목만 판(`selectionColumn`) · 관리자 범위는 xl 부터 1.6:1 옆 |

### 운영·보고서

| 자리 | 무엇 |
|---|---|
| `ops/Diagnostics.jsx` · `ServiceStatusPanel.jsx` · `JobQueuePanel.jsx` | 수집 시각은 머리 캡션, 민감정보 안내는 `?` · 필수 서비스\|외부 연동 조건부 2열(`aside`·`pair`) · 안내 판 → `Note` + 링크 · 설치처 설정/최근 작업 오류는 괘선 구획 · 원본은 `TechDetail` + 함몰면 · 수집 전은 `EmptyState layout="page"` |
| `Dashboard.jsx` | 「최근 주요 변경」 손글 표 → `ListCard` + `DataTable`(복사 링크·`c-id-selectable` 유지) |
| `MailStatus.jsx` | 「최근 실패」 0건은 `EmptyState`(성공 그림), 있으면 `ListCard` |
| `DevReport.jsx` | 루트 `devrep` 클래스 제거 · 긴 문단 → 머리 `?` 와 구획 `help`(`PROSE_MAX_WIDTH`) · h2 셋 → `Section rule` · 표 상자 → `ListCard`(`minWidth: 0` — 격자 칸이 표 폭까지 늘어 1366 에서 가로로 밀리던 것) |
| `SchedulerCalendar.jsx` | 도구 줄 판 → `FilterSurface`/`ToolbarRow`/`ToolbarEnd` · 요약 판 → `MetricStrip` · 18px 제목 → `sectionTitle` |
| `OrgTree.jsx` · `Users.jsx` | 리터럴 폰트/포커스 링 → 토큰(`FONT_SIZE`·`palette.focusRing`) |

## 이번 회차가 잰 것

- **시험** — 단언은 지우지 않고 **더했다**(`check_test_strength.py`). 새 파일 하나
  (`screens/integrity.test.jsx` 4건, 반례 동반)와 덧붙인 시험: `app/admin-tab-groups.test.jsx`
  (h1 고정 · 머리 동작 슬롯 · `?` 도움말) · `settings/settings-shell.test.jsx` · `screens/
  datascreen.test.jsx`(절차가 `?` 에만, 역할 반례) · `screens/saved-views.test.jsx`(조건 줄 안/밖) ·
  `ui/kit.test.jsx`(`PageHeader`·`GuidanceBlock`·`DetailRow`) · `ui/density-contract.test.jsx`
  (`pairTracks`·`FORM_FIELD_GRID`). 패킷마다 영향 화면의 기존 시험 전부를 돌렸다(설정·프로필·
  마법사·오프보딩·일괄 작업·사용자 13파일·진단·대시보드·메일·리포트·달력·조직도) — 문구·aria·
  testid·data-* 를 그대로 둔 것이 회귀 방지의 전부였다.
- **정적 검사** `--scope dev` — 패킷마다. 잡힌 것 하나: 진단의 「연동이 등록되면」이 `Note`
  의 JSX 자식이 되면서 동사표 시험에 걸렸다(`등록` → `추가`). 나머지는 초록.
- **캡처** — `admin-uiux-before`(변경 전, 294장) / `admin-uiux-after`(변경 후, 4 뷰포트 × 2
  테마) + 패킷별 부분 캡처(`wp1-check`~`wp5-check`). 프로브 판정은 치명 0. PNG 를 직접
  열어 §20 목록(머리·도움말·검색·필터·동작·표·폼·모달·탭·배지·빈 상태·타이포·정렬·간격·
  폭·밀도·스크롤·불필요 UI)을 화면마다 봤다 — 발견해서 고친 것: 유지보수 새로고침 캡션이
  줄 가운데로 떠 있던 것 · 조직 정합성의 관리자 표가 1366 에서 잘리던 것(짝을 xl 부터로).
  변경 전후 프로브를 라우트별로 대조해 **새로 생긴** 판정만 골라 고쳤다: 리포트 표 판이 1366 에서
  가로로 밀림(`minWidth: 0`) · 「저장된 뷰」와 「필터 지우기」가 2560 에서 4.5px 갈림(같은 크기로) ·
  초기 설정 레일이 잉크 14% 빈 판(레일은 제 높이만) · 유지보수 짝의 본문/곁열 비 · 리포트의
  브랜드 색 부재(「새로고침」은 그대로 주 행동). 남긴 판정은 짧은 화면의 하단 공백
  (`dead_blank_region`)과 한쪽이 짧은 짝(`detail_side_imbalance` — 설정 OS 탭은 이 환경에
  도우미가 없어 서비스 목록이 비고, 초기 설정 레일은 본디 짧다)이며, 빈 판으로 채우지 않는다.
- **사용자 화면 무변경** — 변경 전 커밋(`99829347`)을 worktree 로 받아 같은 시드로 사용자
  라우트 32장을 찍고 픽셀 대조했다. 아바타·무작위 식별자·시각 말고는 **한 곳**만 다르다:
  `/notifications`(공용 `DataScreen`)의 「저장된 뷰」가 D-455 대로 조건 줄에 붙으면서 고아 줄
  하나가 사라졌다. 공유 층의 규칙이라 갈라 두지 않았다 — 사용자에게 그렇게 보고한다.
  `/profile` 은 지시대로 바뀐 화면이다.

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

이월 항목의 **정본은 [`BACKLOG.md`](BACKLOG.md)** 다.

- **P-85**(신규) — `AdminRoutes.jsx::ORG_CONSOLE_KEYS` 는 무용 상수다.
- **P-86**(신규) — `/audit` 의 h1 「감사 로그」와 첫 탭 라벨이 겹친다(문구 결정이라 범위 밖).
- **P-87**(신규) — `adminKit::Note` 를 사용자 화면이 쓰고, `MyTickets` 의 필드 격자가
  `FORM_FIELD_GRID` 와 같은 값이다(사용자 화면 무변경 원칙으로 안 건드렸다).
- **P-88**(신규) — `canOnboardFor` 가 `headerActions[].when` 을 무시한다(지금은 결과가 같다).
- 지시대로 **안 한 것**: 버그 수정 · 동작/문구 신설(도움말 이관은 문구 그대로. 유일한 예외는
  레일 제목 「실행하면」·「정리할 항목」·빈 상태 제목 셋과 초기 설정 요약의 「아래」 한 낱말) ·
  배포.
- **P-44 · P-54~P-56 · P-59 · P-61~P-84** — 그대로다.

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

## 완료

- **S0~S22** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover · Functional E2E ·
  Final Audit. 결정 D-187~D-334.
- **화면 고도화 · 대시보드 · 무한 스크롤 · 서버 필터/정렬 · 티켓 만들기 · 신호 축 ·
  3영역 재설계 · 카테고리 · 엑셀** ✅ — D-335~D-406.
- **작업 보드·스프린트 회의·문서 결함 전수 수정 + 429 근본 해소 ✅** — D-407~D-412.
- **3라운드 운영 실화면 재검수 ✅** — D-413~D-415. 배포 `c3c2e195`.
- **문서 기능 개편 + 외부 문서 정상화 ✅** — D-416~D-443. 배포 `ec9b8aca`.
- **휴지통 정상화 + 공유 링크 ✅** — D-444~D-451. 배포 `e6df9272`.
- **관리자 화면 전수 UI/UX 정리 + 내 프로필 — 코드 ✅ / 배포 ⬜** — 이번 회차, D-452~D-458.

## BLOCKERS

- 없음.
