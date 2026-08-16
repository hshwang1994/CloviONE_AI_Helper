# PRODUCT AUDIT — STATE

> **이 Audit의 resume pointer다.** 새 invocation은 이 문서를 먼저 읽는다.
> cycle_id=PA-20260816-100149-48671b72 · baseline=`64ef571764bc8ee2ebac3628a4c1383dff2d9217`
> baseline_branch=`ui/mui-migration`
>
> 아래 §A가 **현재 Cycle**이다. §0부터는 이전 Cycle(`PA-20260812-171558-56c5befa`,
> baseline `89ac9f16`)의 기록이며 **증거로 보존**한다 — 그 Cycle의 완료 marker와
> Blind Re-Audit PASS는 이 Cycle의 완료 근거가 되지 못한다(CLAUDE.md §11-1).

---

# §A. 현재 Cycle — PA-20260816-100149-48671b72

## A-0. 이 Cycle의 성격

이전 Cycle 이후 **272 커밋**이 쌓였고, 그 Handoff 3건(`PA-RC-0001`·`0002`·`0003`)은
`IMPLEMENTATION_CONSUMED`로 닫힌 상태로 넘어왔다. `-ResetAudit`으로 새 Cycle이 열렸다.

이 Cycle의 무게중심은 **이전 Cycle이 스스로 밝힌 한계**다:
*"UNSEEN이 57%이고 브라우저로 실제 본 화면은 12/90 표면이다."*
즉 이전 Cycle의 수렴 근거는 Coverage가 아니라 Gate F였다. **그래서 이번엔 관측 폭부터 넓혔고,
넓히는 과정에서 이전 프로브의 방법 결함을 찾았다**(A-2).

## A-1. 이번 Cycle이 실제로 실행한 것

| Round | 축 | 결과 |
|---|---|---|
| 0 | 재접지 | 이전 Cycle 3개 RC를 **현재 HEAD에서 재측정** → 전부 닫힘 확인(기록을 믿지 않고 직접 실행) |
| 1 | C·L·M (전 라우트) | **60 라우트 실주행**(user 19 + admin 41, 이전 11개). `sweep_all.py` |
| 2 | M (접근성 구조) | 59 라우트 heading outline·label·landmark·tabindex·focus ring 계측. `probe_a11y.py` |
| 3 | 표본 검증 | 플래그된 요소의 **DOM 원본 확인** → 대형 오탐 1건 폐기. `verify_a11y.py`·`verify_select.py` |
| 4 | F (RBAC 행동) | 프런트 게이트 없는 화면 10개 × 역할 2개 실제 접근 + 대조군 3개. `probe_rbac_gate.py` |

## A-2. 이번 Cycle이 고친 **이전 Cycle의 관측 방법 결함** (가장 중요)

`probe_spa.py`는 Playwright의 `requestfailed`만 들었다. 그것은 **전송 계층 실패**만 발화하고
**HTTP 500은 전송이 성공한 교환**이라 발화하지 않는다. 즉 화면의 API가 전부 500을 뱉어도
*"실패 요청 (없음)"* 으로 보고된다. `sweep_all.py`는 `response` 이벤트에서 `status >= 400`을
**라우트별로 귀속**해 기록한다. 이전 Cycle의 "네트워크 깨끗함"은 이번 측정으로 **대체**한다.

## A-3. 현재 산출물

| 항목 | 값 |
|---|---|
| 신규 Finding | `PA-F-042` ~ `PA-F-047` |
| 신규 Root Cause | **`PA-RC-0012`**(Medium) — 제목 계층이 시각 API에 종속 |
| HANDOFF 블록 | **1건**(`PA-RC-0012`). `deferred_for_human_approval=0` |
| Coverage | 2340칸 · EXECUTED 158 · OBSERVED **205**(62→) · STATIC_ONLY **641**(784→) · UNSEEN 1336(전부 사유 있음) |
| 적용 Skill | `ui-ux-pro-max` **실제 호출** — `--domain ux` "Heading Hierarchy", `--domain web`/`--stack react` "Semantic HTML before ARIA" |
| Blind Re-Audit | **0 / 2** — 아직 안 함 |

### 이번 Cycle의 음성 결과 (이것도 산출물이다)

- **60 라우트 전부**: HTTP 4xx/5xx 0 · 콘솔 오류 0 · 실패 요청 0 · h1 정확히 1개 · overflow 0 (`PA-F-042`)
- **프런트 role gate 없는 10화면**: 백엔드와 **일치**한다 — operator/auditor 둘 다 정상 열람,
  대조군 3개는 정확히 거부. IDOR·bypass 아님 (`PA-F-045`)
- **표 접근성**: `th` 전부에 `scope` — WCAG 성공 기준 충족, `<caption>` 부재는 권고 수준 (`PA-F-044`)

### 이번 Cycle에 내가 저지른 오류 1건 (정정함)

`probe_a11y.py`가 *"59라우트 중 47개에 라벨 없는 입력"* 을 보고했다. **전부 오탐이었다** —
걸린 것은 MUI `<Select>`의 숨은 프록시 입력(`aria-hidden="true"`, `tabIndex=-1`, `opacity:0`)
이고 실제 접근성 이름은 형제 `div[role=combobox]`가 갖는다(`verify_select.py`로 확정).
내 `named()` 검사가 `aria-hidden`/`tabindex`를 안 봤다.
> **교훈은 이전 Cycle과 똑같다** — 집계 47을 세기 **전에** 표본 1개의 DOM을 열었어야 했다.
> 이 규칙을 지킨 덕분에 `PA-F-043`(진짜 결함)과 `PA-F-044`(오탐)를 갈라낼 수 있었다.

## A-4. 다음 조사 후보 (우선순위 순)

1. **F축 잔여 — 쓰기 액션.** `PA-F-045`는 **읽기만** 확인했다. `operator`가 ungated 10화면의
   `WRITE_ROLES` 액션을 눌렀을 때 403 막다른 길이 되는지 미측정.
2. **C축 — 실제 조작.** 이번 sweep은 **탐색만** 했다. 생성/수정/삭제·정렬·페이지네이션·
   대량 선택을 실제로 눌러 본 적이 없다(이전 Cycle도 "선택자 한계로 판정 보류").
3. **H/I축 — 부정 입력과 복구.** 빈 값·과길이·중복·없는 ID·삭제된 객체. 미측정.
4. **P/Q/R축 재측정.** `PA-RC-0002`가 100%로 닫혔으므로 **이번엔 다른 각도**로 — 존재하는
   문구가 아니라 **없어서 문제인 문구**(프롬프트 P축이 특별히 지목).
5. **상세 라우트 6개**(`/tickets/:id`·`/projects/:id`·`/board/:id`·`/team-docs/:id`·
   `/chat-rooms/:id`·`/games/:id`) — 이번 sweep은 정적 라우트만 걸었다.
6. **서버 렌더 4화면**의 heading/구조 — 이번 M축 측정은 SPA 전용이었다.
7. **Blind Re-Audit 2회** — 이전 Cycle이 쓴 진입점("신규 입사자 첫날"·"감사자 분기 점검")은
   **재사용하지 말 것**. 예: "인수인계받은 운영자가 장애 대응하는 날", "퇴사 처리를 끝까지 실행".

## A-5. 현재 Blocker

**없다.** 로컬 dev 서버(`:8099`) 가동 중, Playwright/Chromium 사용 가능, QA 계정
4역할(user·operator·auditor·system_admin) 전부 확보. 승인된 TEST 서버 SSH도 `ok`다.
`stash@{0}` 자격증명 **회전**만 내 권한 밖 외부 행위이며(REPORT §7-B), 저장소 코드로 닫을 수
있는 부분은 이전 Cycle의 `PA-RC-0003`으로 이미 닫혔다(`check_git_secrets.py` 배선 확인).

## A-6. 실행 방법 메모

```
.venv/Scripts/python var/product-audit/sweep_all.py        # 60라우트 + HTTP 4xx/5xx 귀속
.venv/Scripts/python var/product-audit/probe_a11y.py       # heading/label/landmark/focus
.venv/Scripts/python var/product-audit/verify_a11y.py      # 플래그 요소 DOM 원본 확인
.venv/Scripts/python var/product-audit/probe_rbac_gate.py  # 역할별 화면 접근
.venv/Scripts/python var/product-audit/gen_coverage.py     # COVERAGE 재생성(요약 블록 자동 일치)
.venv/Scripts/python var/product-audit/cov.py set "A-*" "C,L,M" OBSERVED
```
전부 로컬 `:8099`를 쓴다. QA 계정 비밀번호는 매 실행 새로 만들어 **stdin으로만** 넣는다(기록 안 함).

---

# §0~§6. 이전 Cycle 기록 (`PA-20260812-171558-56c5befa`) — 증거로 보존

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

## 2026-08-16 회차 — Gate 거부 해소 + Handoff 소비 재검증

Supervisor가 직전 `AUDIT_COMPLETE`를 3가지 이유로 거부했다. 셋 다 해소했고,
그 과정에서 **Handoff가 이미 대부분 소비됐다**는 것을 발견해 재검증까지 수행했다.

### 거부 사유 해소

| 사유 | 해소 |
|---|---|
| allowlist 밖 dirty(`node_modules/`, `BUILD_STAMP.json`) | **내가 만든 것이 아니다.** Supervisor가 이번 invocation 시작 시 `cycle.json`의 `foreignDirty`에 두 경로를 이미 등록했다(RUN CONTEXT의 `pre_existing_dirty_paths`와 일치). 건드리지 않았다. 내 `gate_check.py`가 목록을 하드코딩하고 있어 `cycle.json`을 읽도록 고쳤다 — 하드코딩은 Cycle 상태가 바뀔 때 조용히 어긋난다 |
| `HANDOFF-SUMMARY`에 `deferred_for_human_approval` 없음 | 이 charter 판에서 새로 요구된 블록이다. `actionable_root_causes=3` · `redesign_root_causes=1` · `deferred_for_human_approval=0`으로 추가 |
| Handoff에 사람에게 미루는 표현 | `PA-RC-0003`을 **구현 가능한 Root Cause로 재정의**했다 — "저장소 보안 검사가 `.git` 내부(stash/reflog/dangling)를 안 본다". 자격증명 회전 자체는 내 권한 밖 외부 행위라 `REPORT` §7-B "외부 제약"에 사실만 적었다. 즉 *"사람이 할 때까지 아무것도 못 한다"* 가 아니라 **검사를 먼저 켜서 그 조치가 실제로 일어나게 만드는 쪽**을 택했다 |

### Handoff 소비 재검증 (이번 회차의 실질 작업)

구현 Phase가 17커밋을 진행했다. **"완료"라는 기록을 믿지 않고** 각 RC를 그 자신의
`acceptance_criteria`로 다시 쟀다. 결과: **8건 중 4건 닫힘 · 1건 철회 · 3건 열림.**

| RC | 결과 |
|---|---|
| `PA-RC-0005`·`0007`·`0008`·`0009` | ✅ 닫힘. 특히 `0008`은 **race 테스트 5회 연속 통과**로 실행 확인(원래 약 40% 실패) |
| `PA-RC-0010` | ❌ **철회 — 내 오탐이었다** |
| `PA-RC-0001`·`0002`·`0003` | 열림(각각 잔여 범위가 명확) |

### 이번 회차에 내가 저지른 오류 3건 (전부 정정함)

1. **`PA-RC-0010` 자체가 오탐이었다.** `/login`의 라이트 고정은 빠뜨린 것이 아니라
   회귀 테스트(`test_login_page_does_not_theme_itself`)와 `login.css`의 `color-scheme: light`
   선언이 못박은 **의도된 설계**다. 나는 `templates_html`과 `tokens.css`만 보고
   **그 화면이 실제로 읽는 `login.css`를 열지 않았다.**
2. **그 정정도 틀렸다.** `/login` 하나만 다시 재고 *"수정이 무효하니 되돌려라"* 라고 적었다.
   4화면을 전부 재니 `/forgot-password`·`/reset-password`에서는 **다크가 실제로 켜진다** —
   구조적 주장은 옳았고 구현 Phase의 판단이 정확했다. 되돌리라는 지시를 철회했다.
3. **`PA-RC-0001`을 잘못 깎아내렸다.** *"리터럴 285회·44종으로 늘었다"* 고 적었는데,
   `fontSize:` 출현을 세면서 **토큰 참조 206회와 아이콘 크기 27회까지 리터럴로 계산**했다.
   실제로는 이 RC의 핵심 처방(일급 타이포 API)이 적용됐고 소비도 진행 중이다.

> **관통하는 교훈**: 셋 다 *"패턴이 몇 번 걸렸는가"* 만 세고 *"무엇이 걸렸는가"* 를 안 본 것이다.
> 이 Audit이 Cycle 내내 13번 경계해 온 바로 그 실수를, 재검증 단계에서 3번 더 했다.
> **표본 하나로 세운 결론은 표본 하나로 뒤집으면 안 된다** — 원 주장이 "전체"였으면 정정도 전체를 재야 한다.

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
