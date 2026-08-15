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

## 2-2. 현재 산출물 요약 (resume 시 여기부터 본다)

| 항목 | 값 |
|---|---|
| Root Cause | **11건** — Critical 1(`0003`) · High 3(`0001`,`0002`,`0008`) · Med 4(`0005`,`0007`,`0009`,`0010`) · Low 3(`0004`,`0006`,`0011`) |
| Finding | PA-F-001 ~ PA-F-027 |
| HANDOFF의 PA-RC 블록 | **8건** — 필수 27필드 자기검사 PASS. Low 3건은 승격 안 함 |
| Coverage | 2340칸 중 EXECUTED 158 · **OBSERVED 8** · STATIC_ONLY 644 · UNSEEN 1530(**전부 사유 있음**) |
| 실행 증거 | **백엔드 2,903건 전부 통과**(4청크) · 프런트 1,718건 통과 · **로그인 화면 실제 Chromium 151 관측** · race 1건 flaky(`0008`) |
| Blind Re-Audit | **0 / 2** — 아직 시작 안 함 |
| Backlog 승격 | **아직 안 함**(§11대로 수렴 후에) |
| `IMPLEMENTATION_REQUIRED` | **아직 안 만듦** |

> **이 회차의 가장 중요한 자기 정정**: `PA-RC-0009`를 처음 High(*"Full Regression green이
> 성립한 적 없다"*)로 썼다가, 스스로 제시한 처방(청크 분할 전경 실행)을 직접 돌려
> **백엔드 2,903건 전부 통과**를 확인하고 Medium으로 낮췄다.
> **다음 회차도 같은 기준을 지켜라** — 처방을 제시했으면 가능한 범위에서 그것을 직접 시험한다.

### AUDIT_COMPLETE까지 남은 일 (순서대로)

1. **인증 이후 SPA 화면을 브라우저로 관측** ← *다음 회차 1순위*
   Playwright + Chromium 151이 실제로 동작함을 확인했고 로그인 화면까지 실측했다
   (`var/product-audit/probe_login2.py`를 그대로 재사용할 수 있다).
   다음은 QA 계정을 만들어 로그인 후 SPA 화면의 L/M/N/O축을 본다.
   **이때 `ui-ux-pro-max`·`impeccable`을 적용한다** — 두 Skill이 아직 미적용인 이유는
   미설치가 아니라 **화면을 실제로 못 봤기 때문**이었고, 그 전제가 이제 풀렸다.
2. **미조사 축** — `C`(기능 CRUD/필터/정렬/페이지네이션) · `N`(반응형·배율) · `O`(라이트/다크,
   SPA 쪽) · `R`(한국어). `R`은 `PA-RC-0002` 문구 규칙이 확정된 뒤가 순서다(프롬프트 2절).
3. **S축 잔여** — 무제한 목록 후보 15건 중 1건만 검증했다. 나머지 14건 확인.
4. **Blind Re-Audit 2회 연속** — 기존 Finding 목록을 다시 읽는 것은 Blind Pass가 **아니다.**
   서로 다른 진입점으로 처음 보듯 조사한다. 제안 진입점:
   *"신규 입사자가 첫날 하는 일"* / *"감사자가 분기 점검에서 하는 일"* /
   *"운영자가 장애 났을 때 하는 일"*.
5. §11 Backlog 승격(**기존 549KB BACKLOG 전체와 중복 대조 필수**) +
   `QA_COVERAGE.md` 공백 반영 + `IMPLEMENTATION_REQUIRED` marker 생성.

### 실행 방법 메모 (다음 회차가 그대로 쓸 것)

- 백엔드 전체 회귀: **전경 + 청크**. `var/product-audit/chunk{1..4}.txt` +
  `tests/{unit,security,regression}` 각각 단독. 단일 호출은 45분+라 세션 경계를 못 넘는다.
- 브라우저: `.venv/Scripts/python var/product-audit/probe_login2.py` 형태. **로컬 `:8099`를 쓴다**
  — TEST 서버는 08-10 빌드라 화면 판정에 쓰면 안 된다(`PA-RC-0007`).

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
| 실제 브라우저 렌더·콘솔·네트워크 관찰 | **부분 완료.** Playwright + Chromium 151로 **로그인 화면 실측 완료**(`PA-RC-0010`). **인증 이후 SPA 화면은 미수행** — 다음 회차 1순위. TEST 서버가 아니라 로컬 `:8099`를 쓴다(`PA-RC-0007`) |
| 인증이 필요한 화면·API 실호출 | **BLOCKED 아님 · 미수행.** 프롬프트 7절이 QA 계정 생성을 허용한다. 로컬 dev 서버 `:8099` 살아 있음(`/readyz` 200). 위 1순위와 같은 작업이다 |
| 배포·재배포·롤백 실행 | **의도적으로 안 한다.** 자격증명 문제가 아니라 **역할 경계**다 — PHASE 2의 일이다 |
| `PA-RC-0003` 자격증명 회전·`stash drop` | **사람만 가능.** 되돌릴 수 없는 운영 결정이고, drop은 사람이 검토하기 전에 증거를 지우는 일이다 |
| 워킹트리의 사용자 미완성 변경 5개 | 건드리지 않는다(`AppShell.jsx`·`CommandPalette.jsx`·`command-palette.test.jsx`·`lib/recentNav.js`·`lib/recent-nav.test.js`). 이 파일들에 대한 판단은 미완성 변경 위에서 내려진 것일 수 있다 — REPORT §6에 한계로 기록 |

## 5. Blind Re-Audit 기록

아직 없음. (형식: `blind_pass=<회차> cycle_id=<Cycle> new_critical_high_categories=<정수> at=<ISO8601>`)

## 6. 2026-08-15 COLD 재접지에서 확인한 것

- 이전 회차의 Audit 문서 4종이 그대로 남아 있고 내용이 유효하다(`git ls-files` 로 추적 확인).
  Coverage 요약 블록도 표와 일치한다 — 이어서 진행했다.
- **`git stash@{0}` 에 TEST 서버 SSH/sudo 평문 비밀번호가 있다** → `PA-RC-0003`(Critical) 신규.
  추적 중인 `CLAUDE.md`(HEAD)와 워킹트리는 깨끗하다. 값을 문서·로그에 복제하지 않았다.
- `ux-writing` Skill을 **실제로 적용**해 `PA-F-011`(실패 문구의 85%가 회복 경로 없음, 3요소를
  갖춘 것 0건)을 도출했고, 그 결과 `PA-RC-0002`를 Medium → **High**로 재분류했다.
- 필수 문서 7종을 모두 만들었다(`FEATURE_CONTRACTS`·`HANDOFF`·`REPORT` 신규).
