# 실제품 재검수 및 재작업 실행계획 (REAUDIT)

<!-- 이 파일은 A~G 계획(PLAN.md)의 후속이 아니라 **별도 회차**다. PLAN.md 와
     WORK_STATE.md 본문은 이 문서가 덮어쓰지 않는다. 이 문서 하나만 읽고 구현을
     시작할 수 있게 쓴다 — 앞 대화를 모르는 세션이 정본으로 삼는 파일이다. -->

> 작성: 2026-08-27 · 근거: 배포 운영 서버 실브라우저 감사 + 운영 DB 읽기 전용 실측
> 앞 회차 정본은 [`PLAN.md`](PLAN.md) · [`WORK_STATE.md`](WORK_STATE.md),
> 공통 실행 규칙은 [`../../CLAUDE.md`](../../CLAUDE.md), 상위 정본은
> [`../platform/MASTER_PLAN.md`](../platform/MASTER_PLAN.md) 다.

---

## Context — 왜 이 작업을 하는가

앞 회차(A~G, `89b0caa6`…`3375ce50`)는 지시서 23개 요구를 구현하고 **RELEASE READY** 로
닫았다. 사용자가 배포된 제품을 직접 써 보고 그 판정을 취소했다. 이번 회차는 그 판정을
**실제 배포 서버에서 다시 검증**하고, 「기능이 있다」가 아니라 「쓸 수 있다」를 기준으로
다시 만든다. 추가로 사용자가 문서 도메인의 분류 축(프로젝트 / 폴더 / 기술 태그)이 무너진
것을 지적했고, 그 복구가 이번 범위의 절반이다.

**전제 정정 하나.** 앞 회차의 시험·캡처·QA 숫자는 틀리지 않았다 — 그것들이 **묻지 않은
질문**이 있었을 뿐이다. 시험은 「이 부품이 계약대로 그리는가」를 물었고, 사용자는
「이 화면으로 일을 할 수 있는가」를 물었다. 그래서 이 계획은 시험을 불신하지 않고
**시험이 안 보던 축**(실데이터 규모 · 회차 0건 · 2560 폭 · 도메인 축 혼선)을 겨눈다.

---

## 1. 왜 「RELEASE READY」 판단을 취소하는가

세 가지가 동시에 참이었다.

1. **QA 계정에 자료가 없었다.** 앞 회차 캡처(`dist/ui-qa/final-g`)는 `ui-qa@goodmit.co.kr`
   세션이다. 이 계정은 담당 티켓 0건이라 「내 티켓」이 **빈 화면으로 통과**했다. 실계정으로
   같은 화면을 열면 상태 알약이 「검…」으로 잘린다(§3 A3). 표가 없는 화면에서는 표의
   결함이 안 보인다.
2. **회차(Sprint)가 운영에 0건인데 아무도 그 상태로 화면을 안 봤다.** 판·백로그·회의 셋이
   전부 회차를 전제하는데 회차가 없으니 판은 전체 1,148건을 그리고 회의는 막다른 한 줄이
   된다(§3 A1·A2).
3. **2560 폭을 아무도 안 봤다.** 앞 QA 는 1366·1920 두 폭이다. 2560 에서 곁열 없는 상세는
   제목과 본문이 다른 축에 서고(§5 C1) 판의 빈 자리가 화면 절반이 된다.

「시험 PASS」와 「화면이 좋다」가 다른 것처럼, 「모든 라우트를 찍었다」와 「그 라우트를
쓸 수 있다」도 다르다.

---

## 2. 실제 브라우저 감사 — 방법과 증거

**대상**: 배포 운영 서버 `https://clovirassist.gooddi.lab` (10.100.64.71),
배포 커밋 `7c0a1a71` 계열, alembic head `0022_document_folders`.

| | 무엇 | 언제 |
|---|---|---|
| 실브라우저 | 사용자 실계정 Chrome 세션, **2560×1271**, Light·Dark | 2026-08-27 |
| 앱 API | 브라우저 세션의 `fetch` 로 실응답 확인 | 같음 |
| 운영 DB | ssh + `psql` **읽기 전용** SELECT | 같음 |
| 앞 회차 캡처 | `dist/ui-qa/final-g`·`final-g2` (1366·1920, 배포본) | 재사용 |

**직접 연 화면**: `/me` · `/my-tickets` · `/team-tickets` · `/work-board` · `/sprint` ·
`/projects` · `/projects/{id}` · `/knowledge` · `/knowledge/{id}` · `/chat-rooms` ·
`/board/{id}` · `/new-ticket` · `/tickets/{id}` · `/admin#/dashboard`.

### 2.1 운영 자료 실측 (이 숫자가 이번 계획의 근거다)

```
tickets 1,159 · projects 22 · sprints 0 · sprint_decisions 0
documents 111 · document_versions 167 · document_tags 106 · tags 19
knowledge_spaces 1 · folders 8 · document_attachments 54
document_relations 0 · document_comments 0 · documents.archived 0
chat_rooms 2 · chat_messages 0 · board_posts 5
users 26 (active 25 · 그중 24 가 admin_scope=global) · project_members 0 · org_units 2
```

- `GET /api/work/backlog` → **total 181** ( = 1,148 − 완료 936 − 취소 31 )
- `GET /api/work/board` 회차 미선택 → **1,148건 전부**, 완료 열은 200건에서 잘림
- `document_cache` 110행이지만 `project_names` · `project_external_ids` · `tech_tags` ·
  `category_names` · `type_names` 가 **전부 비어 있고** `work_field` 는 110건 모두 `기타`다.
  → **레거시 미러에서 프로젝트·기술 맥락을 복구할 수 없다.** 근거는 현재 태그·제목·본문뿐이다.
- `documents.legacy_page_id` 110/111 (Notion 계보는 살아 있다)
- 본문 길이 분포: 빈 문서 8 · 200자 미만 9 · 2,000자 미만 65 · 2,000자 이상 29

### 2.2 knowledge_spaces 단 하나

```
name=팀 문서 · slug=team-docs · owner_kind=organization
owner_dept_id=NULL · owner_project_id=NULL · confidential=false
```

111개 문서 전부가 이 하나에 들어 있다. **문서의 「업무 소속」 축이 물리적으로 존재하지 않는다.**

### 2.3 tags 19개의 실제 정체

| 종류 | 개수 | 값(문서 수) |
|---|---|---|
| 프로젝트 이름 | 8 | 인천국제공항공사[…] 11 · 포스코DX[…] 10 · KB국민카드[…] 5 · SK하이닉스[용인…] 4 · 스마일게이트홀딩스[…] 2 · 굿모닝아이텍[ClovirONE 2.0 제품 개발] 2 · 현대모비스[MDIP…] 1 · 암센터[NCDC…] 1 |
| 업무 분류(폴더와 같은 축) | 10 | 고객 프로젝트 28 · 제품 및 플랫폼 9 · 인프라 7 · 운영 유지보수 6 · 보안 컴플라이언스 5 · 배포 관리 4 · 지식 레퍼런스 4 · 자동화 엔지니어링 2 · 데이터 모니터링 1 · 행정 관리 1 |
| **실제 기술 태그** | **1** | `docker` 3 |

프로젝트 이름 8개는 `projects.name` 과 **글자까지 정확히 일치**한다 → 매핑에 추측이 필요 없다.

### 2.4 폴더 8개는 옳다 (문서 종류 축)

```
01. 회의록 25 · 02. 계획과 요구사항 23 · 03. 설계와 개발 11 · 04. 배포와 운영 18
05. 보안 점검 5 · 06. 지식 베이스 18 · 07. 교육 자료 5 · 99. 미분류 6   (합 111)
```

---

## 3. A. 기능 결함

| # | 화면 | 증상(실측) | 원인 | 사용자 영향 | 고칠 자리 | 서버 | 우선 |
|---|---|---|---|---|---|---|---|
| A1 | 작업 보드 | 회차 미선택 시 1,148건 · 완료 936건이 실행 판을 덮음 · 완료 열 200건 절단 | `app/work/service.py::board()` 이 `sprint_id` 없으면 조건을 안 검. 화면 기본값도 「전체」 | 판이 업무 도구가 아님 | `app/work/service.py::board`, `screens/WorkBoard.jsx` | ✅ | 🔴 |
| A2 | 스프린트 회의 | 회차 0건 → 「아직 만든 스프린트가 없습니다」 한 줄, **안내 문장조차 안 나옴** | `screens/Sprint.jsx:456` 이 `EmptyState` 에 **없는 prop `hint`** 를 넘김(`ui/kit.jsx::EmptyState` 는 `help/situation/prerequisite/steps/expected/action/relatedLink/art/size/layout` 만 받음) | 회의 기능 진입 불가 | `screens/Sprint.jsx`, `ui/kit.jsx` | — | 🔴 |
| A3 | 내 티켓 | 상태 알약이 「검…」「계…」로 잘림. 칸 126px 인데 알약 34.4px, 라벨 client 23 / scroll 27 | `ui/InlineEdit.jsx` 가 감싼 사슬(`span>button>.k-badge>label`)이 전부 `flex:0 1 auto` + `min-width:0` + `overflow:hidden`. 팀 티켓(InlineEdit 없음)은 안 잘림 | 상태를 못 읽음 | `ui/InlineEdit.jsx`, `ui/kit.jsx::Badge` | — | 🔴 |
| A4 | 내 티켓·팀 티켓 | 머리글 「예상 WD」·「실제 WD」 client 40 / scroll 49 로 잘림 | 열 최소 폭이 종류에서 안 나옴 | 열 뜻을 모름 | `ui/columnTypes.js`, `ui/TableHeaderCell.jsx` | — | 🟠 |
| A5 | 프로젝트 상세 | 탭 다섯(개요·WBS·마일스톤·티켓·주간 리포트)에 **문서가 없음** | 미구현 | 프로젝트 문서로 갈 길 없음 | `screens/Project.jsx` | ✅(질의 파라미터) | 🔴 |
| A6 | 문서 목록·상세 | 「공간」 열이 전 행 「팀 문서」 — 정보량 0. 프로젝트 표시 없음 | 공간이 1개 | 어느 프로젝트 문서인지 모름 | §11 전체 | ✅ | 🔴 |
| A7 | 채팅방·티켓 상세 | 참여자·담당자가 이름 텍스트뿐(아바타 없음) | `ui/UserAvatar.jsx` 가 목록·보드에만 배선 | 지시 6·17 미충족 | `screens/ChatRoomMembers.jsx`, `screens/Ticket.jsx` | — | 🟠 |
| A8 | 전 화면 | `blocked_reason` 이 API 로 오는데 **어느 화면도 안 씀** | 미배선 | 차단 이유를 못 봄 | `ui/TicketSignals.jsx`(Tooltip), `screens/Ticket.jsx` | — | 🟠 |
| A9 | 프로젝트 목록 | 행에 `a[href]` 0개 — 새 탭·가운데 클릭·주소 복사 불가 | 행 클릭이 `onClick` 만 | 링크 관용구 깨짐 | `ui/kit.jsx` DataTable 행 링크 계약 | — | 🟠 |
| A10 | 문서 목록 | 이관 문서 대부분 작성자 「-」 | 이관 시 작성자 미해석 | 문서 주인을 모름 | 표시 규칙(「작성자 미상」) | — | 🟡 |

---

## 4. B. 사용 흐름 결함

- **B1 회차를 만드는 길이 한 곳뿐이다.** 「스프린트 추가」가 작업 보드에만 있고, 정작 회차가
  필요한 스프린트 회의·백로그에는 없다. 운영에 회차가 0건인 지금 이것이 곧 막다른 길이다.
- **B2 백로그 = 「완료·취소 아닌 전부」(181건)** 다. 회차가 없으니 판과 백로그가 사실상 같은
  집합이고, 「다음에 무엇을 할까」를 고르는 목록이 아니다.
- **B3 문서를 만들 때 프로젝트를 못 고른다.** 공간이 하나뿐이라 고를 것이 없다.
- **B4 프로젝트↔문서 왕복이 양방향 다 없다.**
- **B5 빈 상태 152곳 중 다음 행동(`action`)이 있는 곳이 17곳뿐이다.**
  (`grep -rn EmptyState frontend/src/screens frontend/src/app frontend/src/ui` 실측)
- **B6 태그를 고르는 자리가 둘이다** — 탐색기의 태그 단추 구름과 목록의 「태그」 셀렉트가
  서로 다른 UI 로 같은 일을 한다.
- **B7 폴더 줄마다 「삭제」가 상시 노출**인데 이름 바꾸기는 없다. 파괴 동작이 기본 노출이다.
- **B8 티켓 상세에 회차·백로그 맥락이 없다.** 「이 티켓이 이번 회차 것인가」를 상세에서 못 본다.

---

## 5. C. UI/UX 결함

- **C1 🔴 곁열 없는 상세에서 제목과 본문이 다른 축에 선다.** `ui/DetailLayout.jsx` solo 는
  `maxWidth: min(100%,46rem)` + `marginInline:auto` 로 가운데 세우는데, `PageHeader` 는 그
  바깥에서 폭 전체 왼쪽이다. 2560 에서 제목 x≈0, 본문 x≈820. (`/board/{id}` 실측)
- **C2 🔴 프로필에 기본 아바타 후보 30개(5스타일×6)가 통째로 깔린다.** 계정 판을 아바타
  격자가 지배하고 이름·이메일·역할은 그 아래로 밀린다.
- **C3 문서 상세 곁열의 「태그」가 태그 19개를 전부 단추로 깐다**(프로젝트 이름 포함).
- **C4 필터 첫 줄에 검색 상자 하나만 있어 한 줄이 통째로 낭비된다**(내 티켓·팀 티켓).
- **C5 「대분류」가 셀렉트가 아니라 맨 텍스트 입력**이라 옆 셀렉트들과 다르게 보인다.
- **C6 활성 필터 칩이 「종료 제외」 하나를 상태 칩 4개로 편다.** 「조건 1개」와 칩 4개가 어긋난다.
- **C7 프로젝트 목록 요약이 0 셋(완료·보류·계획)에 자리를 준다.** Health 도넛이 거의 빈 원,
  「지연 마일스톤 0」이 화면 1/3.
- **C8 프로젝트 상세 개요의 값 열이 1,200px 비어 있다.** 목표 문단만 450px 로 좁다.
- **C9 Health 판의 도넛이 1,300px 판 한가운데 홀로 서고 좌우가 통째로 빈다.**
- **C10 티켓 발생 추이가 막대 2개에 빈 축**이다(자료가 하루에 몰려 있다).
- **C11 티켓 상세 본문 판 아래가 화면 절반 비고**, 메타 줄에 우선순위·난이도·예상 WD·마감·
  생성일이 **하나도 없다**.
- **C12 문서 편집기 도구가 글자 단추 15개 한 줄**이다(아이콘·묶음 없음).
- **C13 문서 목록 제목 칸에 `doc_type` · 업무분류 태그 · 프로젝트 이름 태그가 똑같은 칩으로
  섞여 선다.** 세 축이 시각적으로 구별되지 않는다.
- **C14 문서 탐색기 폴더 목록이 2560 에서도 자체 스크롤(324/369)** 이고 태그 판이 아래로 밀린다.
- **C15 채팅방의 「메시지 없음」이 화면 맨 아래 붙고 위가 통째로 빈다.**
- **C16 관리자 대시보드가 경고 관용구를 둘 쓴다**(빨간 배너 + 「실패 작업 … 7 위험」 줄).
  「대상」 열에 UUID 앞머리가 그대로 보인다.
- **C17 관리자 화면에 짧은 설명이 없다**(사용자 화면에는 있다).
- **C18 프로필 「둘러보기」 판이 폭 전체를 쓰면서 내용은 왼쪽 1/4**. 알림 토글 20여 개가 한 목록.
- **C19 새 티켓 「작성 도움」이 넷이 아니라 여섯**이다. 「미리보기」가 빈 회색 띠로 남는다.
- **C20 「신호」 열이 거의 늘 비어 있는데 폭을 상시 차지한다.**

---

## 6. D. 데이터 규모 문제

| # | 자리 | 실측 | 처방 |
|---|---|---|---|
| D1 | 작업 보드 | 회차 미선택 1,148건 (완료 936) | §8 보드 계약 — 기본 `execution` 범위 |
| D2 | 백로그 | 181행을 쪽 없이 한 번에 **받아서** 그리고 그 위에 dnd-kit 끌기 | **서버 커서 페이징**(§8.5) + `@tanstack/react-virtual` + 「맨 위로/N번째로」 동작 |
| D3 | 보드 열 | 200건 절단(`BOARD_COLUMN_LIMIT`), 안내만 있고 더 볼 길 없음 | **서버 열 단위 커서 페이징**(§8.5) + 열 안 무한 스크롤 + 「더 보기」. 표시만 고치지 않는다 |
| D4 | 문서 목록 | 25행/쪽 × 5쪽, 제목 칸 본문 미리보기 200자+ | 미리보기 2줄 고정 · 가상 스크롤 |
| D5 | 태그 고르개 | 19개를 전량 단추로 깜(기술 태그 재구성 후 40~60개) | `TagPicker`(검색 · 다중 선택 · 사용 건수) |
| D6 | 프로젝트 목록 | 20/쪽, 21건 → 2쪽에 1건 | 쪽 크기 조정 또는 무한 스크롤 |
| D7 | 프로필 알림 | 20여 토글 한 목록 | 묶음 + 접기 |

---

## 7. 공통 Root Cause 일곱

| RC | 한 문장 | 이것이 만든 결함 |
|---|---|---|
| **RC1** | 회차(Sprint)가 실체로 안 쓰인다 — 운영 0건인데 판·백로그·회의 셋이 회차를 전제한다 | A1 A2 B1 B2 B8 D1 D2 |
| **RC2** | `EmptyState` 계약이 느슨하다 — 없는 prop 이 조용히 사라지고 다음 행동이 선택 사항이다 | A2 B5 C15 |
| **RC3** | 알약·칩이 flex 사슬에서 자기 내용보다 작게 줄어든다 | A3 A4 C20 |
| **RC4** | `PageHeader` 와 `DetailLayout` 이 축을 공유하지 않는다 | C1 C11 |
| **RC5** | 문서 도메인의 세 축(업무 소속·문서 종류·기술)이 한 축(태그)에 뭉쳐 있고, 소속 축은 아예 없다 | A5 A6 B3 B4 B6 C3 C13 D5 |
| **RC6** | 요약·표가 「0」과 「없음」을 값과 같은 무게로 그린다 | C7 C9 C20 |
| **RC7** | 아바타 계약이 일부 화면에만 배선됐다 | A7 A10 |

**이 일곱을 먼저 고치면 위 결함 대부분이 화면 수정 없이 따라 낫는다.**

---

## 8. Work Board / Sprint 최종 동작 (사용자 확정 2026-08-27)

### 8.1 범위 계약 — `scope`

`GET /api/work/board` 에 `scope` 를 새로 둔다. 기본은 `execution` 이다.

```
sprint     선택 회차에 담긴 티켓만.  sprint_id 필수
execution  회차 미선택. 종료 상태(완료·취소)를 뺀 것만 = 지금 자료로 181건
all        명시할 때만. 완료·취소 포함
```

- 진입 시 **오늘 날짜에 걸린 활성 회차**가 있으면 자동 선택 → `scope=sprint`.
- 활성 회차가 없으면 `scope=execution`.
- **전체 1,148건을 기본 칸반에 그리는 fallback 은 없앤다.** `all` 은 사용자가 토글을 켤 때만.
- 완료·취소는 열이 아니라 **토글/별도 보기**로 본다(보류는 지금처럼 접힌 칸).

### 8.2 맥락을 화면이 말한다

회차 미선택일 때 판 위에 한 문장을 세운다 —
「회차를 고르지 않아 **실행 중인 업무만** 보여 줍니다.」
회차가 0건이면 그 옆에 **「스프린트 만들기」를 강조 단추**로 둔다.

### 8.3 스프린트를 만드는 자리 셋

작업 보드(지금) · **스프린트 회의 빈 상태** · **백로그 상단**.
회의 빈 상태는 `EmptyState`(`layout="page"`)로 다음 둘을 준다: 「스프린트 만들기」 ·
「백로그 보기」. `screens/Sprint.jsx:456` 의 `hint` prop 을 `help` + `action` 으로 고친다.

### 8.4 회차가 생긴 뒤의 회의 화면

지시서 §4 의 여섯 질문이 세로 순서다. 이미 구현되어 있으므로(`screens/Sprint.jsx`)
**빈 상태와 진입만 고치면 나머지는 그대로 산다.** 실제 회차를 하나 만들어 다음을 눈으로 확인한다:
Summary · Burndown · Health · Workload · 지연 · 차단 · 미할당 · 마감 임박 · Scope 변경 ·
Backlog 후보 · 편입 · Decision · Action Item.

### 8.5 열 상한 — **서버가 다음 자료를 실제로 내주는 계약까지 만든다**

🔴 **가상화로 끝내지 않는다.** `@tanstack/react-virtual` 은 **렌더링 최적화**이고, 지금
문제는 **서버가 열마다 200건에서 잘라 보낸다**는 것이다(`app/work/service.py`
`BOARD_COLUMN_LIMIT = 200`, `cards: by_status[key][:200]`). 안 그려서 빠른 것과 못 받아서
없는 것은 다른 문제다. **「N건 중 앞 200건」이라고 표시만 하고 나머지를 볼 수 없는 상태는
허용하지 않는다.**

#### 서버 계약 — 열 단위 커서 페이징

```
GET /api/work/board
    ... 기존 조건 + scope(§8.1)
    column_page_size (기본 50)
  → columns[].cards        첫 쪽
    columns[].total        **자르기 전에 센 값**
    columns[].next_cursor  더 있으면 커서, 없으면 null

GET /api/work/board/columns/{status_key}
    ... **같은 조건 전량**(project_id · sprint_id · assignee_user_id · mine ·
        blocked_only · scope) + cursor + limit
  → cards[] · next_cursor · total
```

- **커서는 keyset 이다** — 정렬 키(`board_rank` · `backlog_rank` · `created_at` · `id`)
  기준. `offset` 을 쓰면 카드가 움직이는 판에서 **건너뛴 카드와 중복 카드**가 생기고,
  그 어긋남은 오류를 안 낸다.
- **범위 절은 상한 앞에 건다**(D-202). `_visible_tickets_stmt` 를 지나지 않은 행이
  상한을 채우면 내 범위 결과가 한 건도 안 남는데 오류가 아니라서 아무도 신고하지 않는다.
- **요약은 SQL 집계로 센다.** 지금 `board()` 는 행을 전부 파이썬으로 끌어와 세는데
  (`scope=all` 이면 1,148행), 상태별 수는 `GROUP BY status` 한 번이면 된다. 신호 셋도 같다.
  「자르기 전에 센다」는 성질은 그대로 지키면서 메모리에서 행이 사라진다.
- **화면**: 열 안 무한 스크롤(끝에 닿으면 다음 쪽) + **「더 보기」 단추**를 함께 둔다 —
  키보드·스크린리더 사용자는 무한 스크롤에 닿을 수 없다. 열 머리에 「**N건 중 M건**」을
  적어 사용자가 자기가 전부를 보고 있는지 안다.
- **`BOARD_COLUMN_LIMIT` 는 없앤다.** 남겨 두면 「더 받기」가 그 값에서 다시 막힌다.

#### 백로그도 같다

- `GET /api/work/backlog` 는 지금 **181건을 한 번에** 낸다(`total` 만 있고 쪽이 없다).
  `limit` · `cursor` 를 같은 keyset 방식으로 넣는다.
- 끌기는 **받아 둔 범위 안에서만** 허용하고, 멀리 옮기는 것은 「맨 위로 / 맨 아래로 /
  N번째로」 동작으로 준다(181행에서 끌기만으로는 순서를 못 정한다). 그 동작은 서버의
  `move(before_id/after_id)` 대신 **목표 순위를 직접 주는 경로**가 필요하다 — 화면에 없는
  카드를 기준으로 before/after 를 만들 수 없기 때문이다.
- 문서 목록·알림 목록도 같은 원칙이다: **쪽/커서가 먼저이고 가상화는 그 위에 얹는다.**

### 8.6 바꾸지 않는 것

D-349 의 어휘(Workflow Status 여섯 · Signal 셋)와 `sprint_id IS NULL = 백로그` 정의,
`backlog_rank`/`board_rank` 두 컬럼, 신호가 카드를 옮기지 않는 규칙은 **그대로 둔다.**
`tests/security/test_sprint_scope.py` 의 범위 계약도 약화하지 않는다.

---

## 9. 고칠 공통 부품 (묶음 1의 뼈대)

| 파일 | 무엇을 |
|---|---|
| `frontend/src/ui/kit.jsx` | `EmptyState` — 모르는 prop 이면 개발 모드에서 실패, 「목록/판 전체가 빈 화면」은 `action` 필수. `MetricStrip` — 0 타일 정책. `Callout` — 관용구 하나로. `Badge` — `flex-shrink:0`, 라벨 최소 폭 |
| `frontend/src/ui/InlineEdit.jsx` | 감싸는 사슬이 알약을 줄이지 않게(`min-width:max-content`) |
| `frontend/src/ui/columnTypes.js` · `cells.jsx` · `TableHeaderCell.jsx` | 종류별 **최소 폭**, 머리글 잘림 금지, 「신호」 열은 값이 하나라도 있을 때만 |
| `frontend/src/ui/DetailLayout.jsx` | 머리글까지 같은 축에 세우는 `DetailPage` 래퍼 |
| `frontend/src/ui/FilterBar.jsx` · `filters.jsx` | 검색을 필터 줄과 한 줄로, 활성 칩을 **조건 단위**로 접기, `대분류` 를 셀렉트로 |
| `frontend/src/ui/UserAvatar.jsx` | 소비처 확대(채팅 참여자 · 티켓 담당자 · 댓글 · 활동) |
| `frontend/src/ui/DefaultAvatarPicker.jsx` | 인라인 격자 → **대화상자** |
| **신규** `frontend/src/ui/TagPicker.jsx` | MUI `Autocomplete` 기반 — 검색 · 다중 선택 · 새 태그 · 사용 건수 |
| **신규** `frontend/src/ui/VirtualRows.jsx` | `@tanstack/react-virtual` 얇은 감싸개(§15.1) |
| **신규** `frontend/src/ui/ProjectPicker.jsx` · `UserPicker.jsx` | 같은 `Autocomplete` 계약. `ui/filters.jsx::EntityCombobox` 를 이 위로 다시 세운다(§15.3) |
| **신규** `frontend/src/ui/charts/useEChart.js` | ECharts 얇은 훅 — init · setOption · ResizeObserver · dispose · MUI 테마 주입(§15.2) |
| `frontend/src/ui/charts/*` | `LineSeries` · `DateHistogram` · `Gauge` · `Donut` · `BarSeries` 를 **ECharts 로 다시 구현**. `ProgressBar` · `ProgressRows` · `Sparkline` 은 표시자로 남는다(§15.2) |
| `frontend/src/ui/BlockEditor.jsx` · `BodyEditor.jsx` | TipTap 확장 + **아이콘 툴바**. 두 편집기의 기능 집합을 한 표로 맞춘다(§15.4) |
| **신규** `frontend/src/ui/DateField.jsx` | `@mui/x-date-pickers` 감싸개. `LocalizationProvider` 는 셸 한 곳에만(§15.5) |
| `frontend/src/ui/AvatarCropDialog.jsx` | `react-easy-crop` 으로 다시 구현. 서버 `crop_*` 계약은 그대로(§15.6) |

---

## 10. 화면별 필요한 수정

**티켓 축** — `screens/MyTickets.jsx`(필터 한 줄화 · 활성 칩 · 상태 알약 · 열 폭) ·
`screens/TeamTickets.jsx`(같음 + 그룹 접기) · `screens/Ticket.jsx`(메타 줄에 우선순위 ·
난이도 · 예상 WD · 마감 · 생성일 · 회차, 담당자 아바타, `blocked_reason`, 본문 아래 빈 자리) ·
새 티켓 화면(작성 도움 4개로, 미리보기 상자 처리) · `screens/Unassigned`.

**프로젝트 축** — `screens/Projects.jsx`(요약 0 정책 · 도넛/막대 비율 · 행 링크화) ·
`screens/Project.jsx`(개요 값 열 폭 · Health 판 균형 · 추이 그림 빈 축 · **「문서」 탭 신설**) ·
`screens/ProjectMetrics.jsx`.

**보드/회차 축** — `screens/WorkBoard.jsx` · `screens/Sprint.jsx` · `app/work/service.py` ·
`app/work/router.py` · `app/work/schemas.py`.

**문서 축** — `screens/Knowledge.jsx` · `screens/KnowledgeDoc.jsx` · `app/knowledge/*`
(§11~§14).

**나머지** — `screens/ChatRoom(s).jsx` · `screens/ChatRoomMembers.jsx`(아바타 · 빈 상태 위치) ·
`screens/Profile.jsx`(아바타 고르개 대화상자화 · 둘러보기 판 · 알림 묶음) ·
`screens/BoardPost.jsx` · `screens/IdeaBoard`(C1 로 자동 해결) ·
`ui/adminKit.jsx` · `screens/Dashboard.jsx`(짧은 설명 · 경고 관용구 하나로 · UUID 노출).

---

## 11. Document — Project / Space / Folder / Technology Tag 최종 관계

**세 축을 이렇게 고정한다. 다시 섞지 않는다.**

```
Project / Space  = 이 문서가 어느 업무·고객·프로젝트의 것인가
Folder           = 이 문서가 어떤 종류·목적의 문서인가      (지금 8개 유지)
Tag              = 이 문서가 어떤 기술을 다루는가            (기술 전용)
```

예: 프로젝트 `SK하이닉스 [용인 클러스터 대비]` · 폴더 `04. 배포와 운영` ·
태그 `Ansible` `Jenkins` `Redfish` `Linux`.

### 11.1 정본 구조 — 새 관계를 만들지 않는다

`documents.project_id` 를 **추가하지 않는다.** 프로젝트 소속의 정본은 기존 계약 그대로
`knowledge_spaces.owner_kind='project'` + `owner_project_id` 이고, 문서는 자기 공간의
가시성을 물려받는다(`app/authz/visibility.py::_knowledge_document_plan`).

**가시성 확인 완료** — 프로젝트 소유 공간은 「그 프로젝트가 보이는 사람」에게 보인다
(`_stored_ownership_rules` 의 `OWNER_PROJECT` 갈래 → `_project_id_subquery`).
운영 활성 사용자 25명 중 24명이 `admin_scope=global`(→ `_project_plan` 이 `unrestricted`),
나머지 1명(부서 범위 admin)도 `Project.dept_id in (...)` 으로 걸린다. 프로젝트 22개 전부
`dept_id` 가 채워져 있다. → **이동으로 문서를 못 보게 되는 사람은 없다.**
(`project_members` 는 0행이지만 전역 범위가 먼저 걸리므로 영향 없음.
**마이그레이션 직전에 이 사실을 다시 확인한다.**)

### 11.2 사용자에게 보이는 말

- 프로젝트 소유 공간의 이름은 **프로젝트 이름**이다. 화면은 「프로젝트」라고 부른다.
- 조직 공간(`팀 문서`)은 **「공통 문서」**로 보인다. 프로젝트가 없는 문서는 여기 남는다.
- **「공간」이라는 낱말을 일반 사용자 화면에 쓰지 않는다.** 관리 화면에서만 쓴다.

### 11.3 목록 열과 필터 축

목록 열: 즐겨찾기 / 제목 / **프로젝트** / 폴더 / **기술 태그** / 작성자 / 최종 수정 /
첨부·댓글 / 동작. 「공간」 열은 없앤다.

필터 축 넷을 **서로 다른 역할로** 둔다: **프로젝트** · **폴더** · **기술 태그(다중)** · 작성자
(+ 검색 · 즐겨찾기 · 정렬). 프로젝트와 기술 태그를 같은 필터 축으로 취급하지 않는다.

제목 칸의 칩은 **기술 태그만** 그린다. `doc_type` 은 칩이 아니라 폴더 열 옆의 보조 글자로
내린다(지금은 셋이 같은 칩으로 섞여 있다 — C13).

### 11.4 서버 변경

| API | 변경 |
|---|---|
| `GET /api/knowledge/documents` | `project_id`, `tags`(다중) 파라미터 추가. 응답 항목에 `project: {id, code, name} \| null` (공간 owner 에서 파생) |
| `POST /api/knowledge/documents` | `project_id` 를 받아 그 프로젝트의 공간을 **해석하거나 만든다**(권한 재검증). 화면이 `space_id` 를 직접 안 정해도 된다 |
| `POST /api/knowledge/documents/{id}/move` | `project_id` 를 받으면 공간 이동으로 해석 |
| `GET /api/knowledge/tags` | `document_count` 를 함께 낸다 |
| `GET /api/knowledge/spaces` | 이미 `owner_project_id` 를 낸다 — 그대로 |

프로젝트 상세의 문서 탭은 **새 엔드포인트를 만들지 않고** `/api/knowledge/documents?project_id=`
를 쓴다 — 권한 계약을 한 벌로 유지한다.

### 11.5 Folder 역할 유지

폴더는 문서 종류·목적 축이다. `Docker 폴더` · `VMware 폴더` 같은 **기술별 폴더를 만들지
않는다.** 기술 분류는 태그가 담당한다.

---

## 12. 기존 111개 Document 보존 원칙

1. **삭제 0.** `documents` 111 · `document_versions` 167 · `document_attachments` 54 ·
   `legacy_page_id` 110 전부 그대로 둔다.
2. 문서에 쓰는 칸은 **`space_id` 하나**다. `updated_at` 은 **안 건드린다** — 건드리면 111건이
   전부 「오늘 고친 문서」가 되어 「최근 수정」이 거짓말을 한다(D-352 가 `folder_id` 에서 같은
   판단을 했다).
3. 실행 전 스냅샷을 받고 위치를 기록한다. 실행 후 대조: 문서 111 · 판 167 · 첨부 54 ·
   폴더 배치 8묶음(25/23/11/18/5/18/5/6) 그대로.
4. 마이그레이션에 **downgrade 를 둔다**(전부 원래 조직 공간으로).
5. 근거가 확실하지 않은 문서는 **아무 프로젝트에도 안 넣는다.** 공통 문서로 남는다.
6. 실제 Binary(`files`)는 참조 구조 확인 없이 지우지 않는다.

---

## 13. Technology Tag 재구성과 기존 Project 성 Tag 정리

**순서를 지킨다. 기존 태그부터 지워서 `document_tags` 가 CASCADE 로 먼저 날아가게 하지 않는다.**

1. **111개 문서 분석** — 제목 + `document_versions.body_text`(본문 있는 103건) + 기존 태그 +
   `doc_type` + 폴더. 8건은 본문이 비어 있다.
2. **Canonical Technology Tag Set 생성** — 본문 근거가 있는 것만. 이 자료에서 실제로 보이는
   후보: VMware · vSphere · ESXi · VCF · NSX · Aria · Tanzu · Kubernetes · MicroK8s ·
   containerd · **Docker** · Jenkins · GitLab · Git · Ansible · Redfish · Linux · Rocky ·
   Ubuntu · Windows · Oracle · MariaDB · PostgreSQL · Redis · Nginx · Tomcat · Spring ·
   Java · Python · React · FastAPI · Cisco ACI · L4 · Palo Alto · KVM · GPU · AD/ADFS ·
   SSL/TLS · Cloud-init · LVM · TCP/IP · Prometheus · Grafana.
   **고정 목록이 아니다** — 근거 없는 것은 만들지 않는다.
3. **새 태그 생성** (마이그레이션 또는 `POST /api/knowledge/tags`).
4. **문서별 매핑** — 문자열 포함만으로 붙이지 않는다. 「그 문서가 그 기술을 실제로 다루는가」로
   판단한다. 한 문서에 여러 개 붙을 수 있다.
   예: `VMware VCF 자동화 운영 가이드` → VMware · VCF · Ansible · Python.
5. **매핑 검증** — 태그별 문서 수 · 문서별 태그 수 분포 · **사용 0건 태그 없음** ·
   근거 없는 태그 없음.
6. **기존 잘못된 연결 제거** — `document_tags` 에서 프로젝트성 8개 · 업무분류 10개의 연결을
   끊는다. **연결을 먼저 끊고** 태그를 나중에 지운다.
7. **안 쓰는 기존 태그 삭제** — 프로젝트성 8개는 **§14 의 프로젝트 연결이 실제로 만들어지고
   검증된 뒤에만** 지운다. 업무분류 10개는 폴더가 이미 같은 축을 담당하므로 지운다.
   `docker` 는 이름을 **`Docker`** 로 바로잡아 살린다(slug 도 함께 고친다 — 안 고치면 같은
   뜻의 태그가 하나 더 생긴다).

**프로젝트성 태그 → 프로젝트 매핑** (이름이 글자까지 일치한다. 추측 없음)

| 태그 | 프로젝트 코드 | 문서 |
|---|---|---|
| 인천국제공항공사 [클라우드 인프라 고도화] | HAASFT | 11 |
| 포스코DX [P-Cloud 2.0 포털 구축] | TMRWGY | 10 |
| KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경] | XDTBCC | 5 |
| SK하이닉스 [용인 클러스터 대비] | ZCYMPW | 4 |
| 스마일게이트홀딩스 [ClovirONE 2.0 포털 구축] | HSDFXZ | 2 |
| 굿모닝아이텍 [ClovirONE 2.0 제품 개발] | SNGZRK | 2 |
| 현대모비스 [MDIP 시스템 운영/개선] | RYPDYW | 1 |
| 암센터 [NCDC 데이터 분석 포털 구축] | EEQFAP | 1 |

---

## 14. Project ↔ Document 연결 복구

### 14.1 111개 문서의 프로젝트 재매핑 — 근거의 등급

```
1등급  기존 프로젝트성 태그 (8개 태그 · 문서 최대 36건)   → 그대로 매핑. 추측 0
2등급  제목의 고객·시스템 이름                             → 사람이 읽어 확인 후 매핑
       (예: 「인천공항공사 …」·「포스코DX …」·「하이닉스 …」·「MDIP …」·
        「국립암센터 …」·「한강홍수통제소」·「한국인터넷진흥원」·「NextHub/ERP」)
3등급  본문에만 나오는 이름                                 → 근거가 분명할 때만
근거 없음                                                  → 공통 문서로 남긴다
```

`document_cache` 는 도움이 안 된다 — `project_names`·`tech_tags` 가 전부 비어 있다(§2.1).

### 14.2 공간 생성 정책

- **프로젝트마다 미리 만들지 않는다.** 문서가 하나라도 붙는 프로젝트에만 공간을 만든다
  (그러지 않으면 탐색기에 빈 공간 22개가 선다).
- 공간 이름 = 프로젝트 이름, `slug` = 프로젝트 코드 소문자, `owner_kind='project'`,
  `owner_project_id` = 프로젝트 id, `confidential=false`.
- 새 문서에서 프로젝트를 골랐는데 공간이 없으면 **그때 만든다**(서버가).

### 14.3 양방향 진입

- **Project → Document**: 프로젝트 상세에 「문서」 탭.
  빈 상태에 「이 프로젝트 문서 만들기」.
- **Document → Project**: 문서 상세 머리와 곁열의 프로젝트 이름이 `#/projects/{id}` 링크.
- 문서 목록의 프로젝트 열도 같은 링크.

### 14.4 새 문서 / 수정 / 이동의 UX

사용자가 이해해야 하는 것은 셋뿐이다 — **어느 프로젝트 · 어느 폴더 · 어떤 기술 태그**.
「Space Ownership 구조를 알아야만 프로젝트 문서를 만들 수 있는」 UI 를 만들지 않는다.
이동 대화상자에서 프로젝트 바꾸기 = 공간 이동, 폴더 바꾸기 = 폴더 이동을 한 화면에서 한다.

---

## 15. 외부 Open Source Library — **실제 도입 목록** (정책 확정 2026-08-27)

**원칙이 바뀌었다.** 「검토한다」가 아니라 **「전문 영역에서는 실제로 쓴다」** 가 확정
요구다. 기존 자체 구현을 유지하는 것은 기본값이 아니다. 제품 수준에 미달한 영역은
검증된 라이브러리로 **다시 구현한다.** 기존 DOM 시험·QA 프로브가 깨지는 것은 라이브러리를
안 쓸 근거가 아니다 — **시험과 프로브를 새 계약에 맞춰 다시 쓴다**(§18.2).

구조는 이것 하나다: **MUI(디자인 시스템) + 전문 라이브러리.**
Ant Design · Bootstrap · shadcn 같은 **다른 전체 UI 프레임워크는 섞지 않는다.**

### 15.0 도입 확정 목록

| 영역 | 라이브러리 | 라이선스 | 어디에 |
|---|---|---|---|
| 목록·표 가상화 | **`@tanstack/react-virtual`** | MIT · 의존성 0 | 백로그 · 판 열 · 문서 목록 · 긴 설정/알림 목록 · 표 |
| 차트·대시보드 | **`echarts`** (core · SVG 렌더러 · 트리셰이킹) | Apache-2.0 | 번다운 · 발생 추이 · 게이지 · 도넛 · Workload · Scope 변경 |
| 검색·다중 선택 고르개 | **`@mui/material` `Autocomplete`** (이미 번들에 있다) | MIT | 기술 태그 · 프로젝트 · 사용자/담당자 · 공간 |
| 편집기 | **TipTap 확장** `extension-underline` · `extension-task-list` · `extension-task-item` · `extension-link` · `extension-placeholder` | MIT | 문서 편집기 · 티켓 본문 |
| 날짜 | **`@mui/x-date-pickers`** + **`dayjs`**(+`locale/ko`) | MIT | 마감일 · 회차 시작/종료 · 기간 필터 |
| 이미지 자르기 | **`react-easy-crop`** | MIT · 의존성 0 | 프로필 아바타 |

전부 **npm dependency** 로 들어가고 빌드 산출물에 포함된다(§16). 런타임 외부 호출은 0이다.

---

### 15.1 가상화 — `@tanstack/react-virtual`

MIT · 의존성 0 · ~5KB gz. 헤드리스라 DOM 과 스타일을 우리가 갖는다(MUI 와 안 싸운다).

🔴 **가상화는 렌더링 최적화다. 조회 상한의 해결책이 아니다.**
서버가 200건에서 잘라 보내는 자리에 가상화를 얹으면 **200건을 빠르게 그릴 뿐** 나머지
736건은 여전히 없다. 두 문제를 함께 푼다 — **서버 쪽/커서 계약이 먼저이고(§8.5)**
가상화는 그 위에 얹는다. 「N건 중 앞 200건」이라고 적어 두고 나머지를 못 보는 상태로
끝내지 않는다.

**실제 적용할 자리**

| 자리 | 지금 | 뒤 |
|---|---|---|
| `WorkBoard` 백로그 | 181행을 한 번에 **받아서** 그리고 그 위에 dnd-kit 끌기 | **서버 커서 페이징**(§8.5) + 가상 행. 끌기는 받아 둔 범위 안에서, 먼 이동은 「맨 위로 / 맨 아래로 / N번째로」 |
| `WorkBoard` 칸반 열 | **서버가** 열마다 200장에서 자름(`BOARD_COLUMN_LIMIT`) | **서버 열 단위 커서 페이징**(§8.5) + 열 안 가상 스크롤 + 「더 보기」. 열 머리에 「N건 중 M건」 |
| `Knowledge` 문서 목록 | 25행/쪽 × 5쪽 (서버 쪽은 이미 있다) | 쪽 크기를 키우고 가상 행 |
| `MyTickets`·`TeamTickets` 표 | 20행/쪽(181건이면 10쪽) | 쪽 크기 100 + 가상 행 |
| `Profile` 알림 설정 · `DataScreen` 긴 목록 | 20여 토글 한 목록 | 묶음 + 가상 행 |

**주의 셋 — 구현할 때 반드시 처리한다**

1. **dnd-kit 과 함께 쓸 때** 가상 창 밖의 항목은 DOM 에 없다. `SortableContext` 의 `items`
   는 **전체 id 배열**로 주고, 창 밖으로 끌 때는 가장자리 자동 스크롤을 켠다.
2. **브라우저 찾기(Ctrl+F)가 안 보이는 행을 못 찾는다.** 그래서 가상화한 목록에는
   **자체 검색이 반드시 함께** 있어야 한다(백로그·문서 목록에는 이미 있다).
3. **표의 접근성 의미를 안 깨뜨린다.** `GroupedTickets` 의 `<th scope="colgroup">` 그룹
   머리는 그대로 두고 그룹 **안쪽 행만** 가상화한다.

---

### 15.2 차트 — Apache ECharts (Recharts 와 비교한 뒤 고름)

**고른 것: `echarts`** — `echarts/core` 에서 필요한 차트·컴포넌트·**SVG 렌더러**만 가져온다.
React 감싸개는 `echarts-for-react` 대신 **저장소 안 얇은 훅**(`ui/charts/useEChart.js`,
init · setOption · ResizeObserver · dispose · 테마)으로 둔다 — 유지되지 않는 3rd party
감싸개에 기대지 않고, MUI 테마 토큰을 그대로 먹인다.

**왜 Recharts 가 아닌가 (네 가지, 전부 이 제품의 실제 요구다)**

1. **`dataZoom`.** 지시 §16 이 「긴 기간은 Chart 내부에서 좌우 탐색, 페이지에 가로 스크롤을
   만들지 않는다」를 요구한다. ECharts 는 `dataZoom`(휠 · 드래그 · 미니맵)이 기본이다.
   Recharts 는 `<Brush>` 하나뿐이고 휠 확대가 없다.
2. **게이지가 1급 차트다.** 회차 건강 · 프로젝트 Health 둘이 게이지다. Recharts 에는 게이지가
   없어 `RadialBarChart` 로 손수 만들어야 하는데, 그러면 「자체 SVG 를 전문 라이브러리로
   바꾼다」는 목적이 정작 그 두 그림에서 무너진다.
3. **SVG 렌더러를 골라야 DOM 이 읽힌다.** 이 저장소의 대비·마스코트·캡처 프로브가 DOM 을
   읽는다(`scripts/ui_qa/contrast.py` · `brand.py` · `mascot.py`). ECharts 기본은 Canvas 라
   그대로 쓰면 그 프로브가 그림을 **아예 못 본다.** 그래서 `SVGRenderer` 를 **명시적으로**
   고른다 — 이 선택을 안 하면 잃는 것이 무엇인지 여기 못 박아 둔다.
4. **자료 규모.** Scope 변경·Workload 는 회차가 커지면 계열이 수십 개가 된다. ECharts 는
   그 규모에서 안정적이고 `large` 모드가 있다.

**옮길 그림 여섯**

| 지금 (자체 SVG) | 뒤 (ECharts) | 쓰는 화면 |
|---|---|---|
| `charts/LineSeries.jsx` (267줄) | `line` + `dataZoom` (이상선 vs 실제선) | 회차 번다운 |
| `charts/DateHistogram.jsx` (128줄) | `bar` + `dataZoom` | 프로젝트 티켓 발생 추이 |
| `charts/Gauge.jsx` (85줄) | `gauge` | 회차 건강 · 프로젝트 Health |
| `charts/Donut.jsx` (141줄) | `pie`(doughnut) | Health 하위 분포 · 상태 분포 |
| `charts/BarSeries.jsx` (143줄) | `bar`(가로) | 담당자별 남은 WD · Workload |
| (없음 — 새로) | `bar` stacked 또는 area | 회차 Scope 변경 |

**남기는 셋과 그 근거** (지시 §8 형식)

- 영역: 「막대 하나 + 퍼센트」 표시자 — `charts/ProgressBar.jsx`(65줄) ·
  `charts/ProgressRows.jsx`(111줄) · `charts/Sparkline.jsx`(74줄)
- 검토한 라이브러리: ECharts(`gauge`/`bar` 단일 값) · Recharts(`RadialBar`) · MUI `LinearProgress`
- 안 쓰는 기술적 이유: **이것들은 차트가 아니라 셀·타일 안의 표시자**다. 프로젝트 목록은
  한 화면에 진행률 막대가 **행마다** 서고(21행), 표 셀 안 Sparkline 은 24px 높이다. ECharts 는
  그림 하나가 **인스턴스 하나 + ResizeObserver 하나**라, 한 화면에 수십 개를 띄우면 관측자와
  이벤트 루프 비용이 실측 가능하게 늘고 표 스크롤이 무거워진다. 라이브러리를 쓰는 이유
  (정확한 축 · 상호작용 · 확대)가 **하나도 적용되지 않는 자리**다.
- 기존 구현이 나은 구체적 근거: 표 셀 · 요약 타일 · 상세 세 자리에서 **같은 높이 계약**을
  쓰고(`ui/density.js`), 값이 없을 때 「아직 계산하지 않았습니다」로 갈아 끼우는 계약이 이미
  시험으로 고정돼 있다(`charts/progress-rows.test.jsx`). ECharts 로 옮기면 그 계약을 옵션
  객체로 다시 표현해야 하는데 **얻는 시각적 차이가 0**이다.
- **실제 Dashboard Visualization 다섯(선 · 히스토그램 · 게이지 · 도넛 · 막대)은 예외 없이
  ECharts 로 간다.** 위 셋만 표시자로 남는다.

**테마·글꼴** — ECharts 옵션의 `textStyle.fontFamily` 에 `--font-stack`(Pretendard)을 넣고
색은 `ui/charts/chart-color` 팔레트에서 온다. **외부 글꼴·외부 테마 파일을 받지 않는다.**
Light/Dark 는 MUI 테마 토큰을 옵션에 주입해 전환한다.

---

### 15.3 고르개 — MUI `Autocomplete` 기반 전문 부품 셋

단순 `Select` 나 단추 나열을 쓰지 않는다. **이미 번들에 있는** MUI `Autocomplete` 로 만든다
(새 의존성 0, MUI 테마·접근성·키보드 계약을 그대로 물려받는다).

| 부품 | 필수 기능 |
|---|---|
| **`ui/TagPicker.jsx`** | 검색 · **다중 선택** · 선택 Chip · **새 태그 생성**(`freeSolo` + `filterOptions` 로 「"X" 만들기」 항목) · **옵션마다 사용 문서 수** · 삭제 전 영향 건수 |
| **`ui/ProjectPicker.jsx`** | 검색(이름·코드) · 단일 선택 · 코드 보조 표시 |
| **`ui/UserPicker.jsx`** | 검색 · 단일/다중 · **아바타 + 이름 + 부서** · 서버가 좁힌 후보만 |

`ui/filters.jsx::EntityCombobox` 는 이 셋 위로 다시 세운다 — 지금 화면마다 다른 고르개가
서는 것(C5 · B6)이 여기서 사라진다.
옵션이 수백 개가 되는 자리(사용자·프로젝트)는 `ListboxComponent` 에
`@tanstack/react-virtual` 을 끼운다(MUI 공식 권장 패턴).

---

### 15.4 편집기 — TipTap 확장을 **실제로** 쓰고, 서버 스키마를 넓힌다

**지금 서버가 아는 것** (`app/knowledge/blocks.py` 실측):

```
BLOCK_NODES   paragraph · heading · bulletList · orderedList · blockquote
              codeBlock · horizontalRule · image · table
NESTED_NODES  listItem · tableRow · tableHeader · tableCell
INLINE_NODES  text · hardBreak · mention
MARKS         bold · italic · strike · code · link
```

**없는 것: `underline` 마크와 `taskList`/`taskItem` 노드.** 앞 회차가 밑줄·체크 목록 단추를
안 넣은 이유가 이것이다(버튼을 두면 사용자가 쓰고 저장했다가 다시 열었을 때 사라진다).
**이번에는 스키마를 넓힌다.**

1. **서버** `app/knowledge/blocks.py`
   - `MARKS` 에 `underline` 추가
   - `BLOCK_NODES` 에 `taskList`, `NESTED_NODES` 에 `taskItem` 추가
   - `NODE_PARENTS["taskItem"] = {"taskList"}` · `NODE_CHILDREN["taskList"] = {"taskItem"}`
   - `taskItem.attrs.checked` 를 bool 로 검증
   - 마크다운 파생(`_markdown`)에 `- [ ]` / `- [x]`, 밑줄은 `<u>…</u>`
   - 텍스트 파생(`_text`)도 함께
   - **기존 문서 167판은 안 건드린다** — 넓히기만 하는 변경이라 데이터 마이그레이션이 없다
2. **프런트** `@tiptap/extension-underline` · `@tiptap/extension-task-list` ·
   `@tiptap/extension-task-item` · `@tiptap/extension-link` · `@tiptap/extension-placeholder`
3. **툴바를 다시 만든다** — 글자 단추 15개 한 줄(C12)을 **아이콘 + 묶음**으로.
   `@mui/icons-material` 은 이미 있다.

```
서식    Bold · Italic · Underline · Strike · Code
문단    Heading 1~3 · Quote · Code Block · Divider
목록    Bullet · Numbered · Checklist
삽입    Link · Table · Image/첨부 · Emoji · Mention(@사용자 · 티켓 · 문서)
실행    Undo · Redo
```

4. **티켓 본문 편집기(`ui/BodyEditor.jsx`, 마크다운)와 문서 편집기(`ui/BlockEditor.jsx`,
   TipTap)의 기능 집합을 한 표로 맞춘다.** 지금은 티켓 쪽에만 체크 목록이 있어 같은 제품에서
   두 편집기가 다른 것을 할 줄 안다.

---

### 15.5 날짜 — `@mui/x-date-pickers` + `dayjs`

- **`@mui/x-date-pickers`**(MIT, Community) + **`dayjs`**(~7KB gz) + `dayjs/locale/ko`.
  이 저장소 프런트에는 지금 **날짜 라이브러리가 아예 없다**(`lib/format.js` 자체 구현).
  `date-fns` 보다 작고 MUI 어댑터(`AdapterDayjs`)가 공식이다.
- **`DateRangePicker` 는 Pro(상용)라 안 쓴다** — 시작/종료 `DatePicker` 둘로 낸다.
- 적용: 새 티켓 마감일 · 티켓 수정 · **스프린트 만들기(시작일·종료일)** · 기간 필터.
- `LocalizationProvider` 는 셸 한 곳에만 둔다. 저장 값은 지금과 같은 **ISO 날짜 문자열**이라
  서버 계약이 안 바뀐다. UTC 저장 계약도 안 건드린다.
- 고르개 청크는 **지연 로드**한다.

---

### 15.6 이미지 자르기 — `react-easy-crop`

- MIT · 의존성 0 · ~15KB gz. 원본 표시 · **원형 마스크** · 드래그 · **휠/핀치 확대** · 회전 ·
  `croppedAreaPixels` 출력.
- 지금 `ui/AvatarCropDialog.jsx`(174줄)는 포인터 드래그 + **슬라이더 확대만** 있고
  **핀치 확대가 없다.** 지시 §6 의 「모바일에서도 기본적인 이동/확대」를 라이브러리가 그대로
  만족한다.
- **서버 계약은 그대로 둔다** — `crop_x` · `crop_y` · `crop_zoom` 세 값과 서버 재인코딩
  (EXIF 회전 · WebP · 메타데이터 제거) 경로를 안 건드리고, `croppedAreaPixels` 를 그 세 값으로
  환산해서 보낸다.

---

### 15.7 안 넣는 것 — `@mui/x-data-grid` (지시 §8 형식)

- **영역**: 대용량 Table
- **검토한 라이브러리**: `@mui/x-data-grid`(Community, MIT) · `@mui/x-data-grid-pro` ·
  `@mui/x-data-grid-premium` · TanStack Table
- **사용하지 못하는 기술적 이유 둘**
  1. **행 그룹핑이 Premium(상용)이다.** 지금 목록 둘이 접히는 그룹 머리행을 쓴다 —
     내 티켓은 프로젝트별, 팀 티켓은 담당자별(`screens/MyTickets.jsx::GroupedTickets`).
     그 머리는 `<th scope="colgroup">` 이라 스크린리더가 「이 아래 행들은 이 그룹」이라고
     읽는다. DataGrid **Community 에는 row grouping 이 없고**, Pro/Premium 은 상용 라이선스라
     폐쇄망 온프레미스 제품에 넣을 수 없다. 갈아타면 **오늘 있는 기능을 잃는다.**
  2. **정렬·필터의 정본이 서버다.** 이 제품은 서버가 전체 결과 순서를 지킨다(`5d7c5192`).
     DataGrid 로 옮기면 열 머리글 계약(`ui/TableHeaderCell.jsx` 의 `1fr auto 1fr` 가운데 정렬)과
     열 종류 계약(`ui/columnTypes.js`), 좁은 화면 열 접기(`planColumnCollapse`)를 전부
     `colDef`/`renderHeader` 로 다시 써야 하는데, **그 대가로 얻는 것이 가상화 하나**다.
     그 하나는 §15.1 이 이미 준다.
- **기존 구현이 라이브러리보다 나은 구체적 근거**: 그룹 접기 · colgroup 접근성 · 서버 정렬
  계약 · 열 자동 접기 넷이 이미 제품 계약이고, DataGrid Community 에는 앞의 둘이 아예 없다.
- TanStack Table 도 같은 이유로 안 쓴다 — 헤드리스라 위 넷을 우리가 다시 만들어야 하는데
  그것이 지금의 `DataTable` 이다. 가상화만 `@tanstack/react-virtual` 로 **부분 도입**한다.

---

### 15.8 번들 영향 (초기 예산 gzip **280KB** · CSS 120KB — `scripts/check_bundle_size.sh`)

| 라이브러리 | 청크 | 대략 |
|---|---|---|
| `@tanstack/react-virtual` | 진입 가능(작다) | ~5KB gz |
| `echarts` (core + line/bar/pie/gauge + grid/tooltip/legend/dataZoom + **SVGRenderer**) | **지연** | ~60KB gz |
| `@mui/x-date-pickers` + `dayjs` + `locale/ko` | **지연** | ~25KB gz |
| `react-easy-crop` | **지연**(대화상자) | ~15KB gz |
| TipTap 확장 넷 | 이미 지연인 편집기 청크 | ~8KB gz |

**진입 번들에 들어가는 것은 `@tanstack/react-virtual` 하나**다. 나머지는 전부 지연 청크라
초기 예산 280KB 는 그대로 지킨다. `check_bundle_size.sh` 가 이것을 매번 잰다.
숫자는 **추정이고, 도입 뒤 실측으로 이 표를 고친다.**

---

## 16. Offline / 폐쇄망 패키징 조건

- 서버는 **npm 을 안 돈다.** 빌드 산출물이 `app/static/react/assets/` 에 **커밋**되어 있고
  (`git ls-files app/static/react` → 46개) `deploy/install.sh` 가 그것을 그대로 배포한다.
- 새 npm 의존성은 넷을 **함께** 한다:
  ① 개발 기기에서 `npm install` ② `npm run build`
  ③ `app/static/react/**` 산출물 커밋 ④ `frontend/package.json` + `package-lock.json` 커밋.
- **이번에 들어가는 의존성**(§15) — 전부 npm 으로 들어가고 빌드 산출물에 포함된다:
  `@tanstack/react-virtual` · `echarts` · `@mui/x-date-pickers` · `dayjs` · `react-easy-crop` ·
  `@tiptap/extension-underline` · `@tiptap/extension-task-list` · `@tiptap/extension-task-item` ·
  `@tiptap/extension-link` · `@tiptap/extension-placeholder`.
  라이선스는 MIT(ECharts 만 Apache-2.0)이고 **런타임에 아무것도 받아오지 않는다.**
  ECharts 는 `SVGRenderer` 를 명시적으로 고르고, 글꼴은 옵션의 `textStyle.fontFamily` 에
  `--font-stack`(Pretendard)을 넣는다 — **외부 테마 JSON·외부 글꼴을 받지 않는다.**
  `dayjs` 로케일은 `dayjs/locale/ko` 를 **정적 import** 한다(동적 경로 금지 — 번들에서 빠진다).
- **런타임 외부 의존 0**: CDN · Google Fonts · 외부 JS/CSS · 외부 아바타 API · 외부 이미지
  URL · SaaS API 금지. 글꼴은 `pretendard` npm 패키지에서 번들된다. 아바타는 DiceBear 를
  **브라우저 안에서** 그린다(D-350).
- 게이트는 이미 있다: `scripts/static_checks.sh` 의 외부 URL 검사(255행 근처) ·
  `scripts/check_bundle_fresh.py` · `scripts/check_bundle_size.sh`.
  **진입 번들 예산 280KB** 를 넘기지 않는다 — 새 부품은 지연 청크로 받는다.
- 인터넷을 끊은 상태에서도 기능과 디자인이 같아야 한다.

---

## 17. 구현 순서 — **묶음 둘**

Phase 를 늘리지 않는다. 공통 원인을 먼저 고치고, 그것을 쓰는 화면을 **한 번에** 고친다.
묶음 경계는 관리 문서를 만들기 위한 것이 아니라 **커밋 경계**일 뿐이다. 한 회차로 붙여도 된다.

### 묶음 1 — 공통 부품 + 티켓 / 프로젝트 / 보드 / 회차

0. **의존성 도입과 감싸개 셋**(§15) —
   `npm i @tanstack/react-virtual echarts @mui/x-date-pickers dayjs react-easy-crop`
   `npm i @tiptap/extension-underline @tiptap/extension-task-list @tiptap/extension-task-item @tiptap/extension-link @tiptap/extension-placeholder`
   → `ui/VirtualRows.jsx` · `ui/charts/useEChart.js` · `ui/DateField.jsx` 를 먼저 세운다.
   `package-lock.json` 을 함께 커밋하고 `check_bundle_size.sh` 로 예산을 확인한다.
1. **공통 부품**(§9) — `EmptyState` 계약 · `Badge`/`InlineEdit` 알약 · `columnTypes` 최소 폭 ·
   `DetailLayout`+`PageHeader` 축 · `FilterBar` 한 줄화와 활성 칩 · `MetricStrip` 0 정책 ·
   `UserAvatar` 소비처 확대 · `VirtualRows`.
2. **서버**: `app/work/service.py::board()` 에 `scope`(§8.1) · **열 단위 커서 페이징과
   `GET /api/work/board/columns/{status_key}`**(§8.5) · `backlog()` 커서 페이징 ·
   요약을 SQL 집계로 · `BOARD_COLUMN_LIMIT` 제거 · `router.py`/`schemas.py` ·
   `GET /api/work/sprints` 에 활성 회차 표시.
   **이 단계가 3~6단계보다 먼저다** — 화면이 없는 자료를 예쁘게 그릴 수는 없다.
3. **화면**: `WorkBoard.jsx`(자동 선택 · 맥락 문장 · 완료 토글 · 열 안내 · 백로그 가상
   스크롤과 순서 동작) · `Sprint.jsx`(빈 상태 두 행동 · 만들기) ·
   `MyTickets`/`TeamTickets`/`Unassigned` · `Ticket.jsx` · 새 티켓 ·
   `Projects.jsx`/`Project.jsx`/`ProjectMetrics.jsx`.
4. **차트를 ECharts 로 옮긴다**(§15.2) — 번다운 · 티켓 발생 추이 · 회차 건강 ·
   프로젝트 Health · 담당자 Workload · Scope 변경. 「이 그림이 답하는 업무 질문」 계약은
   감싸개가 그대로 들고, 시험을 option 객체 기준으로 다시 쓴다(§18.2).
5. **날짜 고르개**(§15.5) — 새 티켓 마감일 · 티켓 수정 · **스프린트 만들기(시작·종료)**.
6. **가상화**(§15.1) — 백로그 · 판 열 · 티켓 표. dnd-kit 공존 주의 셋을 지킨다.
7. **실제 회차를 하나 만들어** 회의 화면 전 구간을 눈으로 확인한다(§8.4).
8. Targeted 검증(§18) → 커밋.

### 묶음 2 — 문서/지식 + 채팅 / 프로필 / 관리자

1. **서버·도메인**(§11.4): 공간 생성 정책 · `documents` 질의에 `project_id`·`tags` ·
   응답의 `project` · 생성/이동의 `project_id` · `tags` 의 `document_count`.
2. **마이그레이션 둘** (`0023`, `0024`):
   - `0023` 프로젝트 공간 생성 + 문서 `space_id` 재배치
     (downgrade 있음, `updated_at` 불변, §12 대조)
   - `0024` 기술 태그 생성 + 매핑 + 잘못된 연결 제거 + 안 쓰는 태그 삭제 (§13 순서 그대로)
3. **화면**: `Knowledge.jsx`(탐색기 · 프로젝트/폴더/태그/작성자 네 축 · 목록 열 · `TagPicker`) ·
   `KnowledgeDoc.jsx`(프로젝트 맥락 · 태그 판 · 편집기 도구 · 곁열 · 본문 아래 빈 자리) ·
   새 문서 대화상자(프로젝트 → 폴더 → 기술 태그 → 틀) · 이동 대화상자 ·
   `Project.jsx` 「문서」 탭 · 휴지통.
4. **편집기**(§15.4) — 서버 `blocks.py` 스키마를 `underline`·`taskList`/`taskItem` 까지
   넓히고, TipTap 확장을 붙이고, 툴바를 아이콘 + 묶음으로 다시 만든다. 티켓 편집기와
   기능 집합을 맞춘다.
5. **고르개**(§15.3) — `TagPicker`(검색 · 다중 선택 · Chip · 새 태그 · 사용 건수)를
   문서 목록 필터 · 새 문서 · 문서 상세 곁열 세 곳에 같은 부품으로 건다.
6. **가상화**(§15.1) — 문서 목록 · 알림 설정.
7. **나머지 화면**: 채팅(아바타 · 빈 상태 자리) · 프로필(**`react-easy-crop` 아바타
   대화상자** · 기본 아바타 고르개 대화상자화 · 둘러보기 판 · 알림 묶음) ·
   관리자(짧은 설명 · 경고 관용구 하나 · UUID 노출).
8. Targeted 검증(§18) → 커밋.

---

## 18. Targeted 검증 범위

### 18.1 실행

일상 명령은 `python scripts/verify.py`(변경 파일에 매핑된 시험 + `static --scope dev`),
실패만 다시 돌릴 때 `--failed`. **작은 수정마다 전량을 열지 않는다**(CLAUDE.md §7).
Windows 에서 파이썬은 `.venv/Scripts/python.exe` 다.

**새로 써야 하는 시험 — 결함마다 반례로 먼저 확인한다**

| 시험 | 무엇을 고정하나 |
|---|---|
| `ui/inline-edit-badge-width` | 상태 알약이 자기 라벨보다 작아지지 않는다(A3). 되돌린 코드로 깨지는 것을 확인 |
| `ui/column-header-not-clipped` | 「예상 WD」 머리글이 안 잘린다(A4) |
| `ui/empty-state-unknown-prop` | `EmptyState` 에 모르는 prop 을 주면 개발 모드에서 실패한다(A2 · RC2) |
| `ui/detail-axis` | 곁열 없는 상세에서 제목과 본문이 **같은 왼쪽 모서리**에서 시작한다(C1) |
| `work/board-scope` | `scope` 기본이 `execution` 이고 완료·취소가 안 들어온다. `all` 은 명시할 때만(A1) |
| `work/board-active-sprint` | 활성 회차가 있으면 자동 선택된다 |
| `work/board-column-paging` | 열의 `total` 이 200을 넘을 때 **다음 쪽을 실제로 받아 온다**. 커서를 끝까지 따라가면 받은 카드 수 == `total`, **중복 0 · 누락 0** |
| `work/board-cursor-stability` | 페이징 도중 카드가 움직여도 건너뛴 카드·중복 카드가 안 생긴다(keyset) |
| `work/backlog-paging` | 백로그도 커서로 끝까지 받아진다. 「N번째로」 이동이 화면에 없는 카드 기준에서도 동작한다 |
| `security/board-paging-scope` | 다음 쪽 요청도 **범위 절을 상한 앞에** 건다(D-202) — 남의 프로젝트 카드가 커서로 새어 나오지 않는다 |
| `tests/security/test_sprint_scope.py` | (기존) 회차 범위 계약이 안 약해졌다 |
| `knowledge/document-project` | 목록·상세가 프로젝트를 낸다. `project_id` 필터가 공간 소유로 좁힌다 |
| `knowledge/tag-axis` | 프로젝트 이름이 태그로 안 남는다. 사용 0건 태그가 없다 |
| `security/knowledge-visibility` | 공간 이동 뒤에도 권한 없는 문서가 목록·검색·AI 후보에 안 들어온다 |
| `migration 0023/0024` | 문서 111 · 판 167 · 첨부 54 유실 0, `updated_at` 불변, downgrade 왕복 |

**어떤 경우에도 면제되지 않는 것**(CLAUDE.md §9.3): 권한·RBAC 음성 · 채번 동시성 ·
Migration 무결성 · Backup 복원 · Storage 매트릭스 · Reboot 복귀 · Secret · CSRF ·
Prompt Injection.

### 18.2 시험·QA 프로브를 **새 계약에 맞춰 다시 쓴다**

라이브러리를 넣으면 DOM 이 바뀐다. **그것은 라이브러리를 안 쓸 근거가 아니라 시험을
다시 쓸 이유다**(정책 §7). 다만 **성질은 그대로 옮긴다** — 시험을 지우는 것이 아니라
재는 대상을 바꾼다.

| 지금 시험 | 재는 것(지금) | 재는 것(뒤) |
|---|---|---|
| `charts/chart-question.test.js` | 자체 SVG 감싸개의 질문 줄 | **감싸개 DOM 그대로** — 안 바뀐다 |
| `charts/chart-color.test.js` · `series-palette.test.jsx` | SVG `fill` 속성 | `setOption` 에 들어간 **option 객체의 색**(순수 값이라 jsdom 없이 잰다) |
| `charts/donut-empty-state-height.test.jsx` | 빈 자료에서 판 높이 | 감싸개의 빈 상태 · 높이 계약(안 바뀐다) |
| `charts/line-series-null-x.test.jsx` | x 가 null 인 점을 안 그림 | option `series.data` 에 그 점이 없다 |
| `charts/progress-rows.test.jsx` | 표시자 DOM | **안 바뀐다**(ProgressRows 는 남는다 · §15.2) |

- ECharts 시험은 **option 객체를 겨눈다.** 감싸개가 `onOption` 을 부르게 두면 jsdom 에서
  캔버스/SVG 렌더 없이 순수 값으로 잰다 — 그림을 렌더해서 픽셀을 재는 시험은 안 만든다.
- **가상화한 목록의 QA 프로브**는 「그려진 행 수」로 판정하던 자리를 **「총 건수 표시」와
  「스크롤 뒤 마지막 행이 온전히 보인다」**로 바꾼다(`scripts/ui_qa/assertions.py`).
  안 바꾸면 가상화가 「행이 사라졌다」로 오탐된다.
- **표 프로브(열 머리글 가운데 정렬 · 열 종류)는 그대로 산다** — `DataTable` 을 안 갈아탄다
  (§15.7).
- 편집기 시험 둘(`ui/body-editor-no-emoji.test.jsx` · `block-editor-media.test.jsx`)은
  새 툴바 구성으로 다시 쓴다. **왕복 시험을 새로 둔다**: 밑줄·체크 목록이 든 문서를
  저장 → 다시 열기 → **같은 노드가 살아 있다**(§15.4 의 스키마 확장이 실제로 걸렸는지).
- 새 시험: `ui/tag-picker`(검색 · 다중 선택 · 새 태그 · 사용 건수) ·
  `ui/date-field`(ISO 문자열 왕복 · KST 경계) · `ui/virtual-rows`(총 건수 · 마지막 행).

---

## 19. 마지막 Full Regression / Browser Audit / 배포

**전체 구현이 끝난 뒤에만, 각각 1회.**

```
1) python scripts/verify.py --full          # 정적 전량 + 백엔드 청크 회귀 + vitest 전량
   또는  bash scripts/static_checks.sh --scope full  +  bash scripts/run_full_regression.sh
2) 마이그레이션 리허설 — 운영 스냅샷 사본에 0023·0024 를 적용하고 §12 의 수치로 대조
3) 배포 — deploy/install.sh upgrade --source local --yes   (스냅샷 경로 기록)
4) Final Browser Audit — 배포본을 실계정 세션으로, 1366 · 1920 · 2560, Light · Dark
   대표 화면: /me · /my-tickets · /team-tickets · /work-board(회차 있음/없음) · /sprint ·
   /projects · /projects/{id}(문서 탭 포함) · /knowledge · /knowledge/{id} · /chat-rooms ·
   /board/{id} · /new-ticket · /tickets/{id} · /profile · /team-docs/trash · /admin#/dashboard
5) 거기서 나온 실제 결함을 **한 번에 모아** 고치고 **직접 영향만** 재검증한다
6) 비파괴 스모크 — /healthz · /readyz · TLS 검증 0
7) 정본 갱신 — 이 파일 · docs/ui-redesign/WORK_STATE.md · docs/DECISIONS.md(D-353~), 커밋
```

QA 숫자를 맞추려고 제품 코드를 왜곡하지 않는다. 부분 캡처가 전량 원장(`s22-final`)을
덮지 않는다(D-306).

---

## 20. 완료 기준

**기능**
- [ ] 작업 보드 기본이 실행 업무만이고, 전체 1,148건 fallback 이 없다
- [ ] 활성 회차가 있으면 자동 선택되고, 없으면 맥락 문장과 「스프린트 만들기」가 보인다
- [ ] 스프린트 회의 빈 상태에서 회차를 만들 수 있고, 만든 뒤 §8.4 전 구간이 실제로 동작한다
- [ ] **판의 어느 열이든 끝까지 볼 수 있다** — 서버가 다음 쪽을 실제로 내주고, 열 머리가
      「N건 중 M건」을 말하며, 커서를 끝까지 따라가면 받은 수 == `total`(중복 0 · 누락 0).
      「앞의 200건만 보여 줍니다」로 끝나는 자리가 **하나도 없다**
- [ ] 백로그·문서 목록·알림 목록도 서버 쪽/커서로 끝까지 받아진다
- [ ] 상태 알약과 표 머리글이 1366·1920·2560 어디서도 안 잘린다
- [ ] 프로젝트 상세에서 그 프로젝트 문서로, 문서에서 프로젝트로 갈 수 있다

**문서**
- [ ] 문서 111 · 판 167 · 첨부 54 유실 0, `updated_at` 불변
- [ ] Project / Folder / Technology Tag 세 축이 목록·상세·필터·생성에서 **따로** 보인다
- [ ] 프로젝트 이름이 태그로 남아 있지 않다
- [ ] 사용 0건 태그가 없고, 근거 없는 태그가 붙어 있지 않다
- [ ] 태그 검색·추가·이름 바꾸기·삭제·사용 건수가 실제로 동작한다
- [ ] 새 문서에서 프로젝트·폴더·기술 태그를 고를 수 있고 「공간」을 몰라도 된다

**라이브러리**(§15)
- [ ] 백로그 · 판 열 · 문서 목록 · 긴 설정 목록이 `@tanstack/react-virtual` 로 그려진다
      (**서버 쪽/커서 계약이 먼저 서 있고** 그 위에 얹혔다 — 가상화만으로 끝내지 않았다)
- [ ] 번다운 · 발생 추이 · 게이지 · 도넛 · Workload · Scope 변경이 **ECharts** 다
      (`SVGRenderer` · dataZoom · MUI 테마 주입 · Light/Dark 전환)
- [ ] 기술 태그 · 프로젝트 · 담당자가 `Autocomplete` 고르개다(단순 Select · 단추 나열 0)
- [ ] 편집기 툴바가 아이콘 + 묶음이고, **밑줄과 체크 목록이 저장 뒤 다시 열어도 살아 있다**
- [ ] 마감일 · 회차 기간이 `@mui/x-date-pickers` 다(native `input[type=date]` 잔재 0)
- [ ] 아바타 자르기가 `react-easy-crop` 이고 모바일 핀치 확대가 된다
- [ ] `package.json` · `package-lock.json` · `app/static/react/**` 가 함께 커밋됐다
- [ ] 라이브러리를 안 쓴 전문 영역이 §15.2·§15.7 형식으로 기록돼 있다

**품질**
- [ ] 목록·판 전체가 빈 화면에 다음 행동이 있다
- [ ] 같은 상태가 제품 전체에서 같은 색·알약·이름이다
- [ ] 1366 · 1920 · 2560 × Light · Dark 에서 가로 넘침 0, 잘린 글자 0, 의미 없는 큰 빈 자리 없음
- [ ] 런타임 외부 인터넷 의존 0 (정적 검사 통과)
- [ ] 진입 번들 예산 280KB 이내
- [ ] 이번 변경이 만든 Regression 0 · Security/Permission 약화 0
- [ ] 정본(이 파일 · `WORK_STATE.md` · `../DECISIONS.md`)이 실제 상태와 일치

---

## 부록 — 다음 세션이 처음 읽을 파일

```
docs/ui-redesign/REAUDIT_PLAN.md      ← 이 문서 (이번 회차 정본)
CLAUDE.md                              ← 공통 실행 규칙
docs/ui-redesign/WORK_STATE.md         ← 앞 회차(A~G)가 무엇을 했는지
docs/platform/WORK_STATE.md            ← 플랫폼 축 현재 위치
frontend/src/ui/kit.jsx                ← 공통 부품 정본
frontend/src/ui/columnTypes.js         ← 열 정렬·종류 계약
frontend/src/ui/DetailLayout.jsx       ← 상세 폭 계약
frontend/src/ui/InlineEdit.jsx         ← A3 의 자리
frontend/src/ui/charts/                ← ECharts 로 옮길 그림 여섯 (§15.2)
frontend/src/ui/BlockEditor.jsx        ← 문서 편집기 (TipTap)
frontend/src/ui/BodyEditor.jsx         ← 티켓 본문 편집기 (마크다운)
frontend/src/ui/AvatarCropDialog.jsx   ← react-easy-crop 으로 교체 (§15.6)
app/knowledge/blocks.py                ← 편집기 저장 스키마 (underline·taskList 확장)
frontend/package.json                  ← 의존성 도입 지점
scripts/check_bundle_size.sh           ← 초기 gzip 280KB 예산
frontend/src/screens/WorkBoard.jsx     ← 보드·백로그
frontend/src/screens/Sprint.jsx        ← 회의
frontend/src/screens/Knowledge.jsx     ← 문서 작업공간
frontend/src/screens/KnowledgeDoc.jsx  ← 문서 상세·편집기
app/work/service.py                    ← board()·backlog()
app/knowledge/router.py                ← 문서 API 전량
app/authz/visibility.py                ← 공간·문서 가시성 계약 (바꾸지 않는다)
```
