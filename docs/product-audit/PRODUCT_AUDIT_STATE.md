# PRODUCT AUDIT — STATE

> **이 Audit의 resume pointer다.** 새 invocation은 이 문서를 먼저 읽는다.
> cycle_id=PA-20260812-171558-56c5befa · baseline=`89ac9f16d42e8bd0bab8c4ca97b15d6563b03fde`
> baseline_branch=`ui/mui-migration`

## 0. 이 Cycle의 성격

이 저장소는 이미 14회차(WF1~WF14)의 구현 중심 작업을 거쳤고, `docs/BACKLOG.md`는 549KB,
`docs/WORK_STATE.md`는 248KB다. 즉 **"흔한 결함"은 대부분 닫혀 있다.** 그러므로 이번 Audit의
가치는 같은 각도로 한 번 더 훑는 데 있지 않고, **기존 Backlog 프로세스가 구조적으로 못 보던
층위**를 파는 데 있다.

이 판단의 근거(Round 0 실측, `PRODUCT_AUDIT_INVENTORY.md` §6):
정적 위생 스캔에서 naive datetime 0건, `innerHTML` 0건, `console.log` 0건, `TODO/FIXME` 0건,
bare `except` 0건, `async def` 라우트 핸들러 0건, 네이티브 `alert/confirm/prompt` 0건.
`httpx` 직접 import는 단일 관문 파일 자신 1건뿐. **음성 결과도 증거다.**

따라서 이번 Cycle의 무게중심은 다음 순서다.

1. **L/M/N/O/P/Q/R** — UI/UX·접근성·반응형·테마·UX Writing·용어·한국어. 프롬프트 6절이
   "현재 UI 보존은 목표가 아니다"라고 명시했고, Backlog 기반 구현은 이 축을 화면 단위
   버그로만 다뤄 왔다(공통 Root Cause로 병합된 적이 적다).
2. **D / E** — 개별 기능은 되는데 업무 흐름이 끊기는 곳, 그리고 같은 정책을 FE/API/BE/DB가
   서로 다르게 표현하는 곳.
3. **X / Z** — dead/stub/orphan, 그리고 549KB Backlog·248KB WORK_STATE의 문서 드리프트.
   (이 저장소는 "이미 고쳐졌는데 행만 안 갱신" 패턴을 WF11~WF14에서 반복해서 발견했다 —
   그 패턴 자체가 아직 수렴하지 않았다는 신호다.)
4. **B** — Feature Contract. 의도의 근거가 코드밖에 없는 기능이 얼마나 되는지 자체가 산출물이다.

## 1. 지금까지 확인한 사실 (Round 0 — Baseline/Inventory)

| 사실 | 근거 |
|---|---|
| API 엔드포인트 312개 / 42 모듈 | `var/product-audit/api_inventory.json` (스캐너: `scan_api.py`) |
| DB 테이블 69개, Alembic revision 57개 | 저장소 스캔 |
| 사용자 라우트 26 · 관리자 명시 라우트 18 · REGISTRY 화면 키 27 | `UserRoutes.jsx` / `AdminRoutes.jsx` / `screens/registry/*.js` |
| 화면 모듈 115개(비테스트) | `frontend/src/screens/**` |
| **MUI 마이그레이션은 화면 층위에서 완료됐다** | 렌더되는 화면 중 MUI/kit 밖에 남은 것 0개. `kit.jsx`(1146줄)는 MUI 위 얇은 래퍼(`@mui` import 31, export 26) |
| 로컬 dev 서버가 살아 있다 (`:8099`) | `GET /healthz` → `{"status":"ok","ticket_source":"notion_cache"}`, `GET /` → 303 → `/login?next=%2F` |
| `openapi.json`은 404 | 운영 하드닝으로 보이나 **의도 근거 미확인** — Feature Contract 후보 |
| CSP 실측 | `connect-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'` — CLAUDE.md §2 서술과 일치 |
| `.venv`는 Python **3.11.9** | CLAUDE.md §2는 "Python 3.12"라고 적는다 → Z축 후보 (경미) |

### Round 0에서 배운 방법론 교훈 (다음 invocation도 지켜라)

- **자작 스캐너의 첫 결과를 그대로 믿지 마라.** 이번에 두 번 걸렸다.
  1. `alert|confirm|prompt` 57건 → 전부 앱의 `useConfirm()` 오탐. 표본 4건을 눈으로 보고 폐기.
  2. `dangerouslySetInnerHTML` 2건 → 둘 다 "쓰지 않는다"는 **주석**.
- **`^\s*` + `re.M` 은 앞의 빈 줄까지 먹어서 인용 줄번호가 조용히 N줄 앞으로 밀린다.**
  실제로 `app/auth/router.py:210`을 208로 인용할 뻔했다. 스캐너는 `^[ \t]*`를 쓴다
  (`var/product-audit/scan_invariants.py` 주석 참조).

## 2. Coverage 현황

`PRODUCT_AUDIT_COVERAGE.md`의 기계 요약 블록이 정본이다. Round 0 종료 시점:
Surface 90개 × 축 26개 = **2340 cell**, A축 90칸 STATIC_ONLY, 나머지 2250칸 UNSEEN
(전부 surface 단위 사유 등록됨 — `unseen_without_reason=0`).

Coverage 문서와 Inventory 문서는 **손으로 고치지 않는다.**
`var/product-audit/{gen_coverage,gen_inventory,cov}.py`로 생성·갱신한다. 이렇게 한 이유는
요약 블록이 표와 어긋나면 Supervisor의 완료 Gate가 거부하는데, 손으로 관리하면 반드시
어긋나기 때문이다.

## 2-1. Round 진행 현황 (2026-08-15 회차에 추가된 것)

| Round | 축 | 결과 |
|---|---|---|
| 재접지 | 저장소 위생 | **`PA-RC-0003` (Critical)** — `stash@{0}` 평문 자격증명 |
| 2 | P (UX Writing) | `ux-writing` Skill 적용 → **`PA-F-011`**, `PA-RC-0002`를 High로 재분류 |
| 3 | Y (회귀 공백) | **프런트 전체 회귀 실행** — 253파일/1,718건 green. Y축 74칸 EXECUTED. 백엔드 `pytest tests/regression`은 이 회차에 완료 못 함 |
| 4 | L·M | `redesign-existing-projects` Skill 적용 → 해당 항목 대부분 통과, **`PA-RC-0004`(Low)** 신규 |
| 5 | W (타임존/스케줄) | **위반 0건** — 시계 주입 186회, 우회 0회, KST는 전부 허용 용도 |
| 5 | T (관측성) | **끊김 없음** — `request_id`가 응답 헤더·액세스 로그·감사 기록을 잇는다 |
| 6 | J (동시성) | **`PA-RC-0008`(High)** — race 테스트가 5회 중 2회 실패, 재시도 예산이 호출부마다 2/5/10/12 |
| 7 | Y (회귀) | **백엔드 2,903건 전부 통과**(청크 분할). `PA-RC-0009`를 High→Medium으로 자기 정정 |
| 8 | V (배포) | **`PA-RC-0007`(Med)** — TEST 서버가 131커밋 뒤처져 최종 Gate 무효 |
| 9 | D (업무 흐름) | 오프보딩·문서생성 **둘 다 닫혀 있다** → FC-07·FC-08 (UNKNOWN 2건 종결) |
| 10 | L/M/N/O (브라우저) | 화면 12개 실측. `PA-RC-0010`·`PA-RC-0011` 신규, `PA-F-028~031`. **중복 기준선 오류 정정**(prefix 41종/552행) |
| 11 | O/N/M (다크·배율·대비) | SPA 다크 **정상**(`PA-F-032`) · **175% 배율에서 `/users` overflow**(`PA-F-033`) · 대비 1~3차 실패(`PA-F-034`·`035`) · 신규 계정 첫 `/me`에 모달 2개(`PA-F-036`, UNKNOWN) |
| 12 | M (대비 4차) | **성공** — 227요소 판정, **미달 1건**(아바타 이니셜 3.41/4.5). 대비는 대체로 건강하다(`PA-F-037`) |
| 13 | L (재설계) | `ui-ux-pro-max`로 **`RD-1`~`RD-6` 확정**. `impeccable` 교차검증이 `RD-5` 진단을 교체 — 대시보드는 섹션 수가 아니라 **수치 20개가 전부 30px/800** 인 것이 문제 |
| 14 | C (기능 조작) | 목록 조작 실측 — 페이지네이션·검색·필터가 **URL 해시에 상태를 싣는다**(딥링크 성립). 정렬·`/audit` select는 선택자 한계로 **판정 보류**(단정 안 함). 마지막 미조사 축 종결 |
| 15 | S (성능/무제한 목록) | 후보 15건 **전부 판정**. 실제 결함 **1건**(`PA-F-040`, Low) — `/usage/stats`가 모든 프롬프트 버전을 전량 적재하고 삭제 경로가 0건이다. 12건은 상수/설정/스키마 상한으로 **오탐**, 1건은 기존 `UB-29` |

## 2-2. 현재 산출물 요약 (resume 시 여기부터 본다)

| 항목 | 값 |
|---|---|
| Root Cause | **11건** — Critical 1(`0003`) · High 3(`0001`,`0002`,`0008`) · Med 4(`0005`,`0007`,`0009`,`0010`) · Low 3(`0004`,`0006`,`0011`) |
| Finding | PA-F-001 ~ **PA-F-040** + 재설계 후보 `RD-1`~`RD-6` |
| HANDOFF의 PA-RC 블록 | **8건** — 필수 27필드 자기검사 PASS. Low 3건은 승격 안 함 |
| Coverage | 2340칸 중 EXECUTED 158 · OBSERVED 62 · STATIC_ONLY **784** · UNSEEN 1336(**전부 사유 있음**, `unseen_without_reason=0`) · **Gate C: A~Z 26축 전부 반영됨** |
| 실행 증거 | **백엔드 2,903건 전부 통과**(4청크) · 프런트 1,718건 통과 · **Chromium 151로 화면 12개 실측** + 다크/배율/대비 probe · race 1건 flaky(`0008`) |
| Blind Re-Audit | **2 / 2 연속 clean** — pass 1(신규 입사자)·pass 2(감사자) 모두 새 Critical/High **0건**. §5에 기록 |
| Backlog 승격 | ✅ **완료(2026-08-15, commit `703f253`)** — 신규 7행 `PA-01`~`PA-07`, 기존 6행 갱신(`SEC-20`·`DS-05`·`DS-18`·`RESP-01`·`RESP-04`·`SEM-02`). `PA-RC-0003`은 `SEC-20`과 같은 자격증명이라 **중복 행 안 만들고 그 행을 확장**했다. `QA_COVERAGE.md` **§13** 신설(새 축 `T1`~`T9`). `DECISIONS.md`는 갱신 안 함(새로 확정된 정책/설계 결정 없음) |
| `IMPLEMENTATION_REQUIRED` | ✅ **생성됨** — `cycle_id`·`created_at`·`baseline_sha`·`handoff`·`root_causes=8`·`audit_commit` |

> **이 회차의 가장 중요한 자기 정정**: `PA-RC-0009`를 처음 High(*"Full Regression green이
> 성립한 적 없다"*)로 썼다가, 스스로 제시한 처방(청크 분할 전경 실행)을 직접 돌려
> **백엔드 2,903건 전부 통과**를 확인하고 Medium으로 낮췄다.
> **다음 회차도 같은 기준을 지켜라** — 처방을 제시했으면 가능한 범위에서 그것을 직접 시험한다.

### AUDIT_COMPLETE까지 남은 일 (순서대로)

1. ~~인증 이후 SPA 화면 관측~~ → **완료(2026-08-15).** 화면 11개 실측, OBSERVED 53칸.
   재실행은 `.venv/Scripts/python var/product-audit/probe_spa.py` 한 줄이다 —
   QA 계정 2개(`audit-qa-user@`·`audit-qa-admin@`)가 dev DB에 이미 있고, 스크립트가 매 실행
   비밀번호를 새로 만들어 **stdin으로만** 넣는다(기록 안 함).
1-A. ~~`ui-ux-pro-max`·`impeccable` 적용~~ → **완료.** 재설계 후보 `RD-1`~`RD-6` 확정
   (`FINDINGS`의 '재설계 후보' 절). `impeccable` 교차검증이 `RD-5`의 진단을 바꿨다 —
   대시보드 문제는 섹션 수가 아니라 **수치 20개가 전부 30px/800으로 동일해 우선순위가 없다**는 것.
   핵심 Skill 5개 중 **4개 적용 완료**, `humanize-korean`만 순서상 보류(아래 2번).
1-B. ~~배율·다크~~ → **완료.** 125/150/175% 배율 측정(**175%에서 `/users` overflow — `PA-F-033`**),
   SPA 다크 정상 확인(`PA-F-032`).
1-C. ~~`CTR` 대비 재측정~~ → **완료(4차에서 성공).** 화면 4개 **227요소 판정, 미달 1건**
   (상단바 아바타 이니셜 3.41/4.5). 대비는 대체로 건강하다. `DS-33`과 같은 계열이라
   새 RC 없이 그 행에 붙였다. 스크립트: `var/product-audit/probe_contrast2.py`.
   **한계**: 후보 356 중 120은 글자 픽셀을 못 잡아 판정 제외 — 전수가 아니다.
1-D. ~~`RESP-03`~~ → **완료.** 768/1024/1280 세 폭에서 31.1×14px로 정상 — **재현 안 됨**
   (`PA-F-038`). 단 선택자 한계가 있어 '해결됨'으로 단정하지 않았다.
1-E. ~~`PA-F-036` 확인~~ → **완료 · 정정됨.** 모달 2개가 아니라 **AI 도우미 패널이 기본 열림**
   (비모달, backdrop 0). 남는 관측은 1920 폭에서 상시 크롬 724px(38%)와
   `role="dialog"`인데 비모달인 불일치(M축).
2. ~~`R`(한국어)~~ → **완료.** `humanize-korean` 탐지 적용 — **S1 고위험 번역투 지표 전부 0**,
   검출 88건은 전수 확인 후 오탐/정상으로 폐기(`PA-F-039`). R축은 깨끗하다.
   ~~`Z`(문서 드리프트)~~ → **완료.** 다른 축을 파는 내내 5건 발견(COVERAGE Z축 절).
   **남은 미조사 축: `C`(기능 CRUD/필터/정렬/페이지네이션) 하나뿐.**
3. ~~S축 잔여~~ → **완료.** 후보 15건 전부 판정(`FINDINGS`의 S축 절 표).
   실제 결함은 **1건뿐**(`PA-F-040`, Low — Handoff 승격 대상 아님). 판정 기준은
   *"`limit`이 있는가"* 가 아니라 **"이 집합이 무엇에 비례해 자라는가"** 였고,
   그 질문 하나가 12건을 걸러냈다.
4. ~~Blind Re-Audit~~ → **완료. Gate F 2/2 연속 clean.**
   pass 1 *"신규 입사자 첫날"*(0건) · pass 2 *"감사자 분기 점검"*(0건).
   pass 2는 `auditor` 역할로 **F축을 행동 검증**했다 — 화면·라우트·API 세 계층이 같은 답을 낸다.
5. ~~§11 Backlog 승격~~ → **완료(commit `703f253`).** 기존 552행 전체와 대조 후
   신규 7행 + 기존 6행 갱신, `QA_COVERAGE.md` §13(새 축 `T1`~`T9`), marker 생성.

**→ AUDIT_COMPLETE Gate 평가 단계에 진입했다.** 남은 것은 최종 문서 commit 과
Supervisor 기계 Gate 통과 확인뿐이다.

### 실행 방법 메모 (다음 회차가 그대로 쓸 것)

- 백엔드 전체 회귀: **전경 + 청크**. `var/product-audit/chunk{1..4}.txt` +
  `tests/{unit,security,regression}` 각각 단독. 단일 호출은 45분+라 세션 경계를 못 넘는다.
- 브라우저: `probe_login2.py`(로그인 화면·다크) / `probe_spa.py`(인증 이후 11화면).
  **로컬 `:8099`를 쓴다** — TEST 서버는 08-10 빌드라 화면 판정에 쓰면 안 된다(`PA-RC-0007`).
  `probe_spa.py`는 QA 계정 비밀번호를 매 실행 새로 만들어 stdin으로만 넣는다(기록 안 함).

## 3. 다음 조사 후보 (우선순위 순)

1. **Round 1 · L축 진입점**: `ui/theme.js`(520줄) + `styles/tokens.css`(366줄) +
   `ui/kit.jsx`(1146줄) + `AppShell.jsx`(693줄)를 2026 Enterprise SaaS 기준으로 평가.
   토큰·밀도·위계·모션이 실제 화면에서 어떻게 소비되는지까지 본다.
2. **Round 1 · L축 대표 화면**: `Dashboard.jsx`(774줄), `MyTickets.jsx`(1049줄),
   `Users.jsx`(981줄), `DataScreen.jsx`(826줄), `Home.jsx`, `ChatPane.jsx`(550줄).
   프롬프트 6절 rubric 12항을 적용하고, 재설계 후보는 "기능/데이터/권한/업무 흐름을
   바꾸는가"를 반드시 명시한다.
3. **Round 2 · P/Q/R축**: 사용자 문구 전수 수집(정규식으로 한글 리터럴 추출) →
   ux-writing 기준 적용 → 용어 일관성 → humanize-korean.
4. **Round 3 · D/E축**: 대표 업무 흐름 4~6개를 `화면→API→BE→DB→관련화면`으로 추적.
5. **Round 4 · X/Z축**: dead route/orphan API, 그리고 BACKLOG/QA_COVERAGE 자기모순 스캔.
6. **Round 5 · F/U/J/W축**: 기존 테스트가 실제로 계약을 검증하는지(Y축과 함께).
7. **Blind Re-Audit 2회** — 다른 진입점(예: "신규 입사자가 첫날 하는 일", "감사자가 분기
   점검에서 하는 일")으로 처음 보는 것처럼.

## 4. 현재 Blocker

**2026-08-15 COLD 재접지에서 이 표를 정정했다.** 이전 판은 "TEST 서버 접근 불가"라고 적었는데,
Supervisor가 이제 `test_server_ssh=ok` 와 승인된 sudo 자격증명 경로(환경변수 →
stdin 전용)를 주고 프롬프트 7절이 관측 권한을 명시한다. **즉 그 Blocker는 해소됐고, 남은 것은
Blocker가 아니라 '아직 안 한 일'이다.** 낡은 Blocker를 그대로 두면 다음 회차가 할 수 있는 일을
안 한다.

| 항목 | 상태 |
|---|---|
| 실제 브라우저 렌더·콘솔·네트워크 관찰 | **해소됨(2026-08-15).** Chromium 151로 **화면 12개 실측 완료** — 로그인(`PA-RC-0010`) + 인증 이후 11개(`PA-F-028~031`). TEST 서버가 아니라 로컬 `:8099`를 쓴다(`PA-RC-0007`). **잔여는 조건**이다: `RESP-03`·125~175% 배율·SPA 다크 모드·`CTR` 대비 |
| 인증이 필요한 화면·API 실호출 | **해소됨.** QA 계정 2개를 dev DB에 추가하고 강제 비밀번호 변경까지 통과해 SPA에 진입했다. 재실행은 `probe_spa.py` |
| 배포·재배포·롤백 실행 | **의도적으로 안 한다.** 자격증명 문제가 아니라 **역할 경계**다 — PHASE 2의 일이다 |
| `PA-RC-0003` 자격증명 회전·`stash drop` | **사람만 가능.** 되돌릴 수 없는 운영 결정이고, drop은 사람이 검토하기 전에 증거를 지우는 일이다 |
| 워킹트리의 사용자 미완성 변경 5개 | 건드리지 않는다(`AppShell.jsx`·`CommandPalette.jsx`·`command-palette.test.jsx`·`lib/recentNav.js`·`lib/recent-nav.test.js`). 이 파일들에 대한 판단은 미완성 변경 위에서 내려진 것일 수 있다 — REPORT §6에 한계로 기록 |

## 5. Blind Re-Audit 기록

blind_pass=1 cycle_id=PA-20260812-171558-56c5befa new_critical_high_categories=0 at=2026-08-15T12:54:24+09:00

### pass 1 — 진입점: **"신규 입사자가 첫날 하는 일"**

기존 Finding 목록을 보지 않고, **데이터가 하나도 없는 `user` 역할 계정**으로 첫 로그인부터
11개 화면을 순서대로 걸었다(`var/product-audit/blind1_newhire.py`, 결과 `blind1.json`).
"이 사람이 오늘 업무를 시작할 수 있는가"만 물었다.

**새 Critical/High 범주: 0건.**

| 관측 | 판정 |
|---|---|
| **전 화면(11/11)에 "초기 설정이 아직 끝나지 않았습니다 … 관리자에게 문의해 주세요" 배너** | **결함 아님 — 폐기.** `app/setup/checklist.py:123-141`이 `USER_VISIBLE_KEYS` 중 `state != DONE`인 항목이 있을 때만 띄우고, **역할에 따라 문구를 바꾼다**(관리자에겐 "초기 설정 화면에서 확인하세요"). 이 dev 인스턴스는 실제로 설정이 미완이라 **띄우는 것이 옳다.** 문구도 "~수 있습니다"로 단정하지 않는다 |
| `/my-tickets`·`/my-stats`가 **완전히 비어 있다** | **원인이 명확히 안내된다** — *"계정 연결이 없으면 어떤 티켓이 내 것인지 판단할 수 없어 목록을 불러올 수 없습니다"*, *"관리자에게 계정 연결을 요청하세요"*. `PA-RC-0002`가 센 **회복 경로를 갖춘 좋은 문구**의 실례다 |
| 그런데 **제품 안에 "요청"할 방법이 없다** | **신규 관측(Low, improvement)** — `app/notion_mapping/router.py`의 엔드포인트 7개가 전부 `CONSOLE_READ/WRITE_ROLES`다. 일반 사용자는 자기 매핑을 조회도 요청도 할 수 없고 `Profile.jsx:159`에서 상태 배지만 본다. **설계로서는 옳다**(외부 시스템 신원 매핑은 관리자 일이다). 빠진 것은 **"관리자에게 요청" 버튼 하나**뿐이고, 이 제품엔 이미 알림 체계가 있다 |
| `/projects` "프로젝트가 없습니다", `/my-stats` "아직 집계할 티켓이 없습니다" | 빈 상태 문구 정상 |
| 콘솔 오류 | **0건** |

**결론**: 신규 입사자는 팀 티켓·문서·게시판·채팅은 **첫날 바로 쓸 수 있고**, 개인 화면
(`/my-tickets`·`/my-stats`)만 관리자 연결을 기다린다. 그 사실이 화면에 정직하게 적혀 있다.
**새 Critical/High 없음.**

blind_pass=2 cycle_id=PA-20260812-171558-56c5befa new_critical_high_categories=0 at=2026-08-15T12:58:29+09:00

### pass 2 — 진입점: **"감사자가 분기 점검에서 하는 일"**

pass 1과 **역할도 workflow도 다르게** 잡았다 — 이 Cycle에서 한 번도 안 써 본 `auditor` 역할을
만들고, "시작하기"가 아니라 **"이력을 읽고 경계를 확인한다"** 는 일을 걸었다
(`var/product-audit/blind2_auditor.py`, 결과 `blind2.json`).
프롬프트 F축이 특별히 지목한 것 — *"UI에서 버튼을 숨기는 것과 실제 API authorization을
구분한다. direct URL/direct API"* — 를 **행동으로** 시험했다.

**새 Critical/High 범주: 0건.** 그리고 F축이 **행동으로 확인됐다.**

| 검사 | 결과 |
|---|---|
| 감사자가 써야 하는 화면 8개(`/audit`·`/audit-anomalies`·`/impersonation`·`/backup`·`/rbac`·`/dev-report`·`/maintenance`·`/announcements`) | **전부 정상 렌더 + 실데이터**(감사 로그 100행, 개발자 리포트 65행, 권한 매트릭스 13행 등) |
| 감사자가 못 써야 하는 화면 8개(`/users`·`/offboarding`·`/organizations`·`/job-titles`·`/system`·`/setup`·`/notion-console`·`/llm-console`)에 **직접 URL로 진입** | **8개 전부 차단**(`h1` 없음, 거부 표시, 0행) |
| **세션 쿠키를 들고 API 직접 호출** | `/api/admin/users` **403** · `/api/admin/offboarding` **403** · `/api/admin/audit` 200 · `/api/admin/backups` 200 · `/api/admin/settings` 200 · `/api/admin/reports/dev-monthly` 200 |
| 사이드바 필터링 | 관리자 세그먼트로 전환하면 **29개 항목**이 보이고, **차단 대상 8개는 정확히 빠져 있다** |

즉 **화면 게이트·라우트 게이트·API 게이트 셋이 모두 같은 답을 낸다.** `FC-05`(화면 역할 게이트)가
정적 대조로 주장한 것을 이번에 **실제 요청으로** 확인했다.

**조사 중 내 오탐 1건**: 처음에 *"감사자에게 관리자 메뉴가 하나도 안 보인다"* 로 읽었다.
사이드바를 `/#/me`(사용자 세그먼트)에서 읽고, 세그먼트 전환 탭을 `header` 안에서만 찾았기
때문이다. 실제로는 **사이드바 최상단(x=132, y=80)에 「관리자」 버튼**이 있고
(`AppShell.jsx:322-339`, *"사용자 지적 P2 — 왼쪽 트리 상단으로 옮겨라"*), 누르면
`/#/dashboard`로 전환된다. `App.jsx:46`의 `isUser = role === "user"` 조건상 `auditor`는
당연히 탭을 받는다. **결함 아님.**

## 완료 Gate A~G 평가 (2026-08-15, AUDIT_COMPLETE 직전)

프롬프트 12절의 Gate를 하나씩 근거와 함께 판정한다. *"문서 많이 씀"* 은 근거가 아니다.

| Gate | 요구 | 판정 | 근거 |
|---|---|---|---|
| **A** Inventory | 주요 Surface가 전부 inventory에 있고 **이유 없는 UNSEEN이 없다** | ✅ | 90표면 × 26축 = 2,340칸. `gen_coverage.py` 재생성 결과 `unseen_without_reason=0`. Inventory는 소스에서 기계 생성(`gen_inventory.py`) |
| **B** Intent | 주요 Feature가 Intent 근거와 confidence를 가진 Contract를 갖고, 모르는 것은 정직하게 UNKNOWN | ✅ | `FC-01`~`FC-08` 전부 confidence 기재. **UNKNOWN 3건은 지우지 않고 남겼다**(티켓 정본 정책 · 복구 리허설 성공 판정 기준 · n8n/Runner 실패 전파). 이 Cycle에 2건(오프보딩·문서생성)을 D축 추적으로 닫아 `FC-07`·`FC-08`이 됐다 |
| **C** Axis | 5절 A~Z 축이 전부 Coverage에 반영 | ✅ | 26축 전부. 마지막까지 비어 있던 `C`(기능 조작)·`S`(성능)를 Round 14·15에서 닫았다 |
| **D** Evidence | 정적 추정과 실행 증거가 **구분**되고, Confirmed/Strong에 재현/trace가 있으며, Finding이 Root Cause로 병합 | ✅ | Coverage가 `STATIC_ONLY`/`OBSERVED`/`EXECUTED`를 셀 단위로 구분한다. Handoff 8건의 근거: `0008` race 테스트 **실제 40% 실패 재현** · `0009` 2,903건 **실행** · `0007` 원격 mtime+asset 해시 **실측** · `0010`·`0001` **브라우저 실측** · `0003` stash 직접 확인 · `0002`·`0005` 소스 전수 스캔(주장 자체가 소스에 대한 것) |
| **E** Skill | 사용 가능한 Skill을 **실제로** 적용하고, 미설치는 skill_gap + 대체 방법 | ✅ | 핵심 5개 전부 적용(`ux-writing`→`PA-F-011` / `ui-ux-pro-max`→`RD-1`~`3` / `impeccable`→`RD-5` 진단 교체 / `redesign-existing-projects`→L·M축 / `humanize-korean`→`PA-F-039`). 순서(UX Writing → 한국어) 준수. 미설치 2건(`chrome-devtools`·`a11y-debugging`)은 `skill_gap`으로 기록하고 Playwright+Chromium 151 실측으로 대체 — 각 Handoff 블록의 `quality_rubric`에 쓴 자를 그대로 남겼다 |
| **F** Blind Re-Audit | 서로 다른 진입점으로 **2회 연속**, 둘 다 새 Critical/High 범주 0 | ✅ | pass 1 *"신규 입사자 첫날"* 0건 · pass 2 *"감사자 분기 점검"* 0건. pass 2는 `auditor` 역할로 **F축을 행동 검증**(화면·직접 URL·직접 API 세 계층이 같은 답) |
| **G** Handoff | REPORT 존재 · Confirmed/Strong이 BACKLOG에 **중복 없이** 반영 · PA-RC 블록 완전 · QA gap 반영 · marker 정확 | ✅ | commit `703f253`. 기존 552행 전체 대조 후 신규 7행 + 기존 6행 갱신. `PA-RC-0003`은 `SEC-20`과 같은 자격증명이라 **중복 행을 만들지 않고** 그 행을 확장. PA-RC 블록 8건 × 필수 27필드 자기검사 PASS. QA gap은 `QA_COVERAGE.md` §13 새 축 `T1`~`T9` |

**BLOCKED 없음.** `AUDIT_BLOCKED` 사유(사람/환경 때문에 끝내 막힌 필수 Coverage)에 해당하는 항목이 없다.

> **이 Gate 표가 숨기지 않는 것**: Coverage 2,340칸 중 **1,336칸(57%)이 여전히 UNSEEN**이다.
> Gate A가 요구하는 것은 *"UNSEEN이 없다"* 가 아니라 *"이유 없는 UNSEEN이 없다"* 이고 그것은 만족했지만,
> 이 Audit이 제품 전체를 실행으로 훑었다는 뜻은 아니다. 브라우저로 실제로 본 화면은 **12/90 표면**이다.
> 수렴의 근거는 Coverage 비율이 아니라 **Gate F** — 서로 다른 진입점의 blind pass 2회가
> 새 Critical/High를 하나도 못 찾았다는 사실이다.

## Gate F 상태: **2 / 2 연속 clean** — 두 pass 모두 새 Critical/High 0건.
## 6. 2026-08-15 COLD 재접지에서 확인한 것

- 이전 회차의 Audit 문서 4종이 그대로 남아 있고 내용이 유효하다(`git ls-files` 로 추적 확인).
  Coverage 요약 블록도 표와 일치한다 — 이어서 진행했다.
- **`git stash@{0}` 에 TEST 서버 SSH/sudo 평문 비밀번호가 있다** → `PA-RC-0003`(Critical) 신규.
  추적 중인 `CLAUDE.md`(HEAD)와 워킹트리는 깨끗하다. 값을 문서·로그에 복제하지 않았다.
- `ux-writing` Skill을 **실제로 적용**해 `PA-F-011`(실패 문구의 85%가 회복 경로 없음, 3요소를
  갖춘 것 0건)을 도출했고, 그 결과 `PA-RC-0002`를 Medium → **High**로 재분류했다.
- 필수 문서 7종을 모두 만들었다(`FEATURE_CONTRACTS`·`HANDOFF`·`REPORT` 신규).
