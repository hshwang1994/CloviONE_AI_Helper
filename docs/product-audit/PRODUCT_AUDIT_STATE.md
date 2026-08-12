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

| Blocker | 상태 |
|---|---|
| 승인된 TEST SERVER(`10.100.64.X`) 배포·실환경 확인 | **이 Audit의 범위 밖.** 자격증명을 비대화형으로 쓰지 않는다(프롬프트 7절). PHASE 2 담당 |
| 실제 Chrome 렌더/콘솔/네트워크 관찰 | 이 Runner에 브라우저 자동화 도구 없음 → `skill_gap: chrome-devtools` 로 기록. N/O/M축 결론은 코드 근거까지 |
| 인증이 필요한 로컬 API 실호출 | 자격증명 없음. 기존 pytest 스위트(TestClient)를 실행 증거로 쓴다 |

## 5. Blind Re-Audit 기록

아직 없음. (형식: `blind_pass=<회차> cycle_id=<Cycle> new_critical_high_categories=<정수> at=<ISO8601>`)
