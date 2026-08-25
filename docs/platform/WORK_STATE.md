# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (S19)
- phase: **E — UI Renewal 재개.** S19 가 W10 화면의 **제품 결함**을 닫았고 다음은 S20
- session: **S19 제품 축 완료 · 기능·시각 축 미측정.** W10 20 화면의 Flow 감사와 캡처는
  **안 했다** — 회차 도중 사용자가 Pilot·Capture·Coverage 실행 중단을 지시했고, 그때 만들던
  W10 Flow 표(`pilot_w10*.py`)와 하네스 확장은 **전부 되돌렸다**. 그래서 §9.1 의 S19 Exit
  (「각 화면 Functional Flow 가 최소 IN_PROGRESS」)는 **미충족**이고 소유는 그대로 W10 이다.
  다음은 **S20 — 관리자 IA + 관리자 콘솔 (요청 시)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S18 도 옮기지 않는다.** 이유는 S11~S17 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s18_commit: **`f1968a09`** — S18 본체(문서·원장·하네스·화면·시험)
- s19_commit: 아래 「S19 가 실제로 한 것」 절 참고 — 본체는 화면·공용 부품·문서다.
  **원장은 한 행만 바뀌었다**(`user_my-display` → 별칭). 나머지 W10 행은 `NOT_AUDITED` 그대로다
- deployed: **S15~S17 이 운영에 나갔다. S18 은 아직 안 나갔다** (2026-08-25 04:13, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · 스냅샷 `/var/backups/clovirassist/20260825-041314`.
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  배포본 번들 지문 `39187bca03b30bc3` 가 빌드한 것과 같다. 스모크 6화면(홈·내 티켓·티켓 상세·
  게시판·문서·채팅방)에서 **콘솔 오류 0 · 페이지 오류 0**. 되돌리려면
  `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260825-041314`
- ui_gate: `--stage plan` **PASS**(S19 도 `verify.py` 안에서 확인). `--stage wave` 는 S19 가
  **안 돌렸다** — W8 잔여를 여는 일이라 지시가 막았다. 아래는 **S18 이 남긴 그대로**다.
  `--stage wave`(**W8**) **FAILED (274건)**. S18 이 UI 축의
  CHECKPOINT 를 W8 로 올렸다. 실패 274건은 셋 다 **기록 형식**이고 화면 결함이 아니다 —
  ① 사슬의 서버 칸 243건(하네스가 `/openapi.json` 으로 핸들러 표를 만드는데 이 제품은 그
  경로를 안 연다) ② 조건 다섯 축이 아직 없는 화면 24건 ③ 화면 사슬 칸이 빈 Flow 7건.
  전부 **P-44** 다. `capture_labels.after` 는 `s17-after` 그대로다 — S18 이 캡처를 다시 안 찍었다.
  억제 하나는 칸반 레인의 균등 격자다(SUP-01, 만료 2026-10-20).
  그쪽 상세는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 `0016_document_axis_to_documents` 다. S18 도 스키마를
  안 건드렸다(프런트·백엔드 읽기 경로·QA 하네스·문서만)
- pilot: **258 Flow 중 252 PASS / 6 FAIL** (`dist/ui-qa/pilot/flows.json`). 실브라우저가
  조용한 결함 넷을 잡아 고쳤다 — `/me` 500(**D-302**) · 티켓 댓글 알림이 `NameError` 로
  통째로 죽어 담당자에게 한 건도 안 가던 것 · 조건이 붙은 주소가 그 조건을 잃던 것(**D-304**) ·
  QA 씨앗이 제품에 없는 상태 낱말을 심던 것. 결정 **D-299~D-305**

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 25 · 22 · **1,140**(컷오버 뒤 실사용자가 새로 만든 7건 포함) |
| 프로젝트 코드 | **22 / 22.** S13 에서 확정표에 없어 못 받던 둘도 받았다 |
| 문서 · 판 · 태그 · 문서 첨부 | 110 · 166 · 106(19종) · 54 |
| 티켓 댓글 · 티켓 첨부 | 336(이관 첫 회차가 0건 옮겼던 324건을 재이관이 채웠다) · 236 |
| 옛 이름 층 | **없다** — `tickets.legacy_key` · `ticket_key_aliases` · `project_key_registry` 를 `0012` 가 내렸다 |
| Notion 런타임 | **없다.** 모듈 열다섯을 지웠고, 런타임 SSRF 목록에 `api.notion.com` 이 **없다** |
| SQLite 런타임 | 없다. 옛 파일은 `/var/lib/clovirassist/web.sqlite3` 에 남아 있지만 제품이 못 연다 |

## S19 가 실제로 한 것

이번 회차가 답한 질문은 둘이다 — **열이 왜 겹쳤나**, 그리고 **빈 화면은 어디에 서야 하나.**

### 1. 🔴 배치 규칙이 둘이었고, 그래서 열이 겹쳤다 (D-308)

S16 이 열에게 «의미» 를 주면서 폭을 한 자리에서 파생하게 했다. 그 어휘의 「내용만큼」은
`SHRINK = "1%"` 인데 **그 값이 그 뜻이 되는 것은 `table-layout: auto` 에서뿐이다.** fixed
배치는 첫 행의 폭을 글자 그대로 읽고 `min-width` 를 무시한다 — 그런데 게시판·제안·휴지통이
그 둘을 함께 걸고 있었다.

실측(`/ideas`)에서 분류·상태·공감·조회·작성 다섯 열이 **1920 에서 15.6px**, 1440 에서
10.9px, 1200 에서 8.5px 로 섰다. 선언한 바닥값(72·80·64·136px)이 하나도 안 걸렸고 남은
폭은 제목과 작성자가 740px 씩 나눠 가졌다. 머리글은 그 15px **밖에** 그려져 옆 이름 위에
겹쳤고, 본문 값은 같은 15px **안에서** 잘려 아예 안 보였다 — 같은 칸이 두 규칙을 쓴 것이다.
폭이 화면 폭의 1% 라 **넓힐수록 더 어긋난다.**

고친 것 넷: 배치를 `auto` 하나로 내렸다 · 남는 폭을 갖는 열을 `title` 하나로 못 박았다
(`name` 은 내용 폭으로 내린다) · 머리글도 넘치면 자르고 전체는 `title` 로 남긴다 · 자르지도
접지도 않는 열도 넘치면 자른다. 같은 조건에서 다시 재면 제목 874 · 분류 75 · 상태 80 ·
공감 69 · 작성자 256 · 조회 69 · 작성 136px 이고 **넘침은 0** 이다.

### 2. 🔴 `page` 빈 화면은 선언만 있고 배선이 없었다 (D-309)

S17 이 `EmptyState` 에 자리 셋(`page`·`region`·`inline`)을 선언했는데 **`page` 를 아무
화면도 안 썼다.** 그래서 화면 전체가 빈 상태(승인·놀이·검색·옛 문서 주소·목록 0건)가 전부
`region` 으로 그려져, 큰 빈 화면의 왼쪽 위 구석에 작은 그림과 한 줄만 놓였다.

`page` 를 가운데 구성으로 세웠다 — 클로비 → 제목 → 짧은 설명 → (필요하면) 다음 행동을
위에서 아래로, 남은 높이(`min(30rem, 60vh)`) 안에서 가운데에. 그 높이가 마스코트 밴드의
분모라 그림이 컨테이너를 정하는 순환도 안 생긴다(D-294 와 같은 이유). 페이지 빈 상태 열
곳에 배선했고 **카드 안의 빈 상태(`/me` 의 넷 등)는 그대로 뒀다** — 거기서는 왼쪽 정렬이
그 카드의 다른 내용과 같은 축이다.

그리고 **상단 행동과 같은 일을 하는 CTA 는 안 그린다.** 반대로 「비었을 때만 상단 버튼을
감추는」 방식은 시험해 보고 버렸다 — 목록이 도착하는 순간 버튼이 손가락 밑에서 사라지고,
놀이 화면의 기존 시험 다섯이 실제로 그 창에서 클릭을 놓쳤다. 상단 행동은 데이터와 무관하게
늘 있고 빈 화면은 그것을 이름으로 가리킨다. 조건 때문에 0건인 갈래는 다르다 — «조건
지우기» 는 상단에 없는 다른 행동이라 그쪽이 CTA 를 갖는다.

### 3. 화면을 훑다 찾은 것 넷

* 🔴 **`/ai` 가 통째로 500 화면이었다**(D-311). 지식 공간 질의가 두 화면에 각자 있었고
  한쪽이 `{items:[…]}` 를 배열로 알고 `.map` 을 불렀다. 그 줄이 `FormModal` 의 `fields`
  안이라 **모달이 닫혀 있어도 매 렌더 계산됐고**, 공간이 하나라도 있으면 화면이 죽었다.
  공간이 없는 개발 환경에서는 `[]` 라 아무 일도 안 일어나므로 어떤 시험도 못 봤다.
* **설정 하나짜리 화면을 합쳤다**(D-310). 「내 화면 설정」(`/my-display`)은 강조색 하나뿐인데
  사이드바 항목도 `ROUTE_OWNER` 도 없어 **그 화면에서 사이드바 선택 표시가 사라졌고** 본문의
  70%가 비어 있었다. 「내 프로필」로 합치고 옛 주소는 리다이렉트로 남겼다.
* **내 활동 피드가 두 말투로 말했다**(D-312) — 「로그인했습니다」 바로 아래 「게시글을 만듦」.
* **`/my-stats` 안내문에 마크다운이 새어 나왔다** — 화면에 `**추세**` 가 그대로 보였다.

### 4. 남긴 것

**W10 20 화면의 Flow 감사와 캡처는 안 했다.** 회차 도중 사용자가 Pilot·Capture·Coverage
실행 중단을 지시했고, 그때 만들던 W10 Flow 표(`pilot_w10*.py` 173건)와 Pilot 하네스 확장은
**전부 되돌렸다** — 제품 변경과 무관하게 「W10 Pilot 을 만들기 위해서만」 있던 것이다.
그래서 §9.1 의 S19 Exit(「각 화면 Functional Flow 가 최소 IN_PROGRESS」)는 **미충족**이고
원장의 W10 20 행은 `NOT_AUDITED` 그대로다. 실제 라우트 변경을 반영한 원장 한 행만 고쳤다
(`user_my-display` → `state_variant · alias_of=user_profile`).

검증은 정본의 일상 경로다(`python scripts/verify.py`). 프런트 전량 **2,439 PASS / 8 FAIL** —
8건은 **전부 HEAD 에도 있는 기존 실패**이고, 같은 파일을 `git stash` 로 HEAD 에서 돌려
숫자를 대조했다. **S19 가 만든 회귀는 0** 이다. 그 8건은 **P-45~P-47** 로 등록했다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0`.
  결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 티켓에 번호가 붙고 그 번호가 영원히 같은 티켓을 가리킨다.
  결정 **D-236~D-243**(그중 Key 정책은 S14 가 대체했다).
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.
  결정 **D-249~D-253**.
- **S9 — AI Platform 1 (Gateway · Pipeline).** 모델이 계약 뒤로 들어가고 문서가 스스로
  색인된다. 결정 **D-254~D-259**.
- **S10 — AI Platform 2 (Retrieval · Citation · 생성).** 권한이 `LIMIT` 앞에 걸리고
  인용이 문단을 가리킨다. 결정 **D-260~D-264**.
- **S11 — n8n · 외부 Runner 제거.** 옛 AI 경로가 사라지고 채팅이 제품 안에서 답한다.
  결정 **D-265~D-268**, 원장 [`EVIDENCE/S11/`](EVIDENCE/S11/README.md).
- **S12 — Backup / Restore 운영.** 백업이 「되돌리면 앱이 돈다」를 증명한다.
  결정 **D-269~D-273**, 원장 [`EVIDENCE/S12/`](EVIDENCE/S12/README.md).
- **S13 — Migration Tool + Dry Run.** 옛 데이터가 새 스키마로 전부 건너가고 두 번 돌려도 같다.
  결정 **D-274~D-281**, 원장 [`EVIDENCE/S13/`](EVIDENCE/S13/README.md).
- **S14 — Cutover + Legacy 제거.** 위 절. 결정 **D-282~D-284**, 원장
  [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).
- **S15 — Search/Filter 기능 정확성.** 조건이 맞는지를 **두 구현의 대조**로 봤다 — 결함 여섯을
  뿌리에서 고쳤고 전부 오류를 안 내는 종류였다. 결정 **D-285~D-287**.
- **S16 — Table / Grid / Metadata / Alignment + Chart.** 열이 폭 대신 의미를 말한다.
  `numeric_alignment` 8건이 0 이 됐다. 결정 **D-288~D-293**.
- **S17 — Empty / Loading / Error / Feedback + Clovi + Detail Metadata.** 클로비가 박스가
  아니라 «보이는 크기» 로 서고, 값이 0 이면 화면이 접힌다. 결정 **D-294~D-298**.
- **S18 ◐ — Pilot Archetype 8종.** 기능 축만 닫았다 — Flow 258건을 실브라우저에서 눌러
  252 PASS / 6 FAIL, 원장을 두 방향으로 대조하게 했고(C1c) 조용한 결함 넷을 잡았다.
  캡처를 다시 안 찍어 17 화면은 `IN_PROGRESS` 이고 잔여는 **P-44** 다. 결정 **D-299~D-305**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ **끝났다.** Runtime 의존 0 이고 데이터도 전부 넘어갔다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ 런타임은 끝났다. **화면에는 잔재가 남아 있다**(P-41, S20) | S13 ✅ · S14 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — 그리고 S14 가 **실 데이터로 다시 증명**했다 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ · S14 ✅ |

**Identity 축도 닫혔다** — 호스트명·TLS(S3) · slug(S4) · 역할·권한(S5), 그리고 마지막 한 건인
세션 쿠키 이름을 S14 가 갈았다(P-33).

**UI 축은 W7 까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이었고 재개는 Phase E(S15~S20)다 (D-207).

## NEXT — 다음 시작점: S20 (요청 시)

**S20 = 관리자 IA + 관리자 콘솔** (W11 + W12).
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1,
Backlog 는 **P-30**.

S19 가 다음 Session 에게 넘기는 것 넷:

1. **W10 의 Flow 감사와 캡처가 안 끝났다.** 20 화면이 `NOT_AUDITED` 그대로이고 §9.1 의
   S19 Exit 는 미충족이다. 소유는 그대로 W10 이다(**P-29**). 회차 도중 만들던 W10 Flow 표와
   Pilot 하네스 확장은 지시에 따라 **전부 되돌렸으므로**, 다시 하려면 처음부터 세워야 한다.
2. **P-44(S18 잔여)는 그대로다.** S19 가 아무것도 안 건드렸다.
3. **HEAD 에 이미 있던 프런트 실패 8건**을 새 Finding 으로 등록했다 — `PATH_SEP` 미임포트로
   `/tickets/:id` 공유 범위 판이 죽는 것(**P-45**, 한 줄 import 다) · 표준 동사표 위반 셋
   (**P-46**) · `filter-chain-contract` 셋(**P-47**). 그리고 `verify.py` 의 정적 단계를 막는
   논리 테두리 하나(**P-49**, `TicketHistory.jsx`). 전부 S19 가 만들지 않았다.
4. **`scripts/verify.py` 의 vitest 단계가 Windows 에서 안 뜬다**(**P-48**). S19 는 지시에 따라
   하네스를 안 고치고 같은 명령을 손으로 돌렸다.

그리고 **범위 밖으로 넘긴 것**: 시험 강도 선언 미비(**P-38**, `verify.py` 의 정적 단계가 이것
하나로 계속 빨갛다) · 백엔드 회귀 넷(**P-39**) · 화면에 남은 Notion 잔재(**P-41**, S20) ·
`/dev-report` 의 빈 판(**P-42**, S20) · 값이 0 인 날의 판독값(**P-43**, S22).
