# CLAUDE.md — ClovirAssist

> Claude Code가 이 저장소에서 세션을 시작할 때 읽는 최상위 실행 규칙이다.
> 과거 UI Renewal 문서와 과거 완료 기록은 정본이 아니다.
> 현재 Source, 현재 Git 상태, 현재 Tests, 현재 Runtime, 실제 Browser 결과를 기준으로 판단한다.
> 목표는 Area/Cycle/Batch 몇 개가 아니라 제품 전체를 실제로 완료하는 것이다.

## 0. 사용자 확정 Product Identity와 최우선 규칙

- Canonical Product Name은 `ClovirAssist`다.
- Canonical Technical Slug는 `clovirassist`다.
- Canonical Web Hostname은 `clovirassist.gooddi.lab`이다. 이 값에 임의로 `-ai` 등의 접두/접미사를 붙이지 않는다.
- Product Brand의 핵심 색상 계열은 Purple/Indigo다. White/Gray 중심의 Neutral 제품으로 바꾸지 않는다.
- Clovi는 ClovirAssist의 핵심 Brand Character다. 단순 장식 아이콘처럼 축소하거나 임의 이미지로 대체하지 않는다.
- 현재 Working Tree, Build Artifact, Runtime Config, Browser Title/Metadata, Deployment/Proxy/TLS 설정에서 Product Identity가 서로 다르게 남아 있지 않도록 전수조사한다.
- `rg -i "clovir"` 등으로 Product 관련 문자열을 전수 확인하고, Canonical Product Name/Slug 또는 의도적으로 유지해야 하는 공용 기술 Prefix가 아닌 Legacy Product Identity는 안전하게 Migration한다.
- Git History Rewrite는 이번 작업의 기본 범위가 아니지만 현재 Working Tree와 현재 배포 결과에는 Legacy Product Identity가 남아 있으면 안 된다.

## 1. 최우선 실행 원칙

- PROJECT 전체가 유일한 작업 단위다. Product Area, Wave, Cycle, Batch, Slice, Iteration은 조사/정리/병렬화용 라벨일 뿐 종료 단위가 아니다.
- 정상 종료 조건은 `PROJECT_COMPLETE`뿐이다. 실행 가능한 일이 남아 있으면 즉시 다음 작업으로 계속한다.
- commit, clean working tree, focused test green, build green, deploy green, 문서 갱신, recap, summary는 Stop Condition이 아니다.
- 사람 확인은 실제 MFA, 외부 승인, 접근 불가, 상충 요구, Production 파괴 위험처럼 사람이 반드시 필요한 경우에만 요청한다.
- 한 blocker가 있어도 독립적으로 가능한 작업은 계속한다.
- 현재 사용자의 명시적 작업 지시사항이 이 파일의 일반 규칙보다 우선한다.

## 2. 세션 시작과 Context 복구

세션 시작, `/compact` 이후, 장시간 작업 후 방향이 불확실할 때 다음 순서로 현재 상태를 복구한다.

1. 현재 사용자 지시사항 전체
2. Git status/diff/최근 의미 있는 commit
3. 실제 Router/Navigation/Source
4. 실제 API/Backend/DB wiring
5. 현재 Tests와 Static/Build Script
6. 현재 Runtime/Deploy/Nginx/TLS/Environment 설정
7. 실제 Browser와 Test Server 결과
8. 이번 작업에서 새로 만든 Control Artifact

과거 UI Renewal 관련 `docs/`는 사용자가 삭제했다. 삭제된 문서를 복구하거나 과거 PASS/Backlog/Progress를 현재 완료 근거로 사용하지 않는다.

현재 UI Renewal 작업에서 아래 파일이 없으면 이번 지시사항을 기준으로 새로 만든다.

- `docs/ui-renewal/REQUIREMENT_MATRIX.md`
- `docs/ui-renewal/ROUTE_COVERAGE.json`
- `docs/ui-renewal/WORK_STATE.md`

이 세 파일은 과거 History를 복원하기 위한 문서가 아니라 현재 작업의 누락 방지 Control Plane이다.

문서와 Source/Git/Test/Browser가 충돌하면 Source와 실제 검증 결과를 확인하고 문서를 정정한다.

## 3. Ultracode Workflow를 현재 UI Renewal의 Primary Workflow로 사용

현재 UI/UX 전면 재작업은 Claude Code의 Ultracode Dynamic Workflow를 적극 사용한다.

단일 Agent가 수 시간 동안 모든 조사, 구현, 검증을 혼자 수행하고 스스로 PASS를 선언하는 구조로 끝내지 않는다.

독립적으로 분리 가능한 작업은 Subagent/Workflow로 나눈다.

최소 역할은 다음 관점을 포함한다.

- Route/Source Inventory
- Brand/Design System
- Product UX/Content Architecture
- User Console
- Admin IA/Console
- Functional/E2E
- Visual Reviewer
- Requirement Reviewer

Discovery/Audit은 병렬화할 수 있다. Theme, Navigation, Shared Component처럼 충돌 위험이 큰 구현은 통합 순서를 정해서 적용한다.

Visual Reviewer와 Requirement Reviewer는 구현 담당과 분리한다. 구현 Agent가 자신의 결과를 근거 없이 완료 처리하지 않는다.

기존 `autonomous_runner.ps1` 또는 Supervisor가 Repository에 존재하더라도 현재 UI Renewal의 Design/Requirement 판단 정본이 아니다. 사용자가 명시적으로 Supervisor를 실행한 경우 세션 연속성을 위한 보조 수단으로만 사용하며, 삭제된 과거 Audit 문서나 과거 완료 상태를 다시 요구하거나 복구해서는 안 된다.

## 4. 프로젝트 핵심 기술 불변 규칙

실제 Repository 설정이 아래 내용과 다르면 Source/Config를 먼저 확인하되, 기존 검증된 핵심 계약을 임의로 깨지 않는다.

1. FastAPI/SQLAlchemy Sync 일관성을 유지한다. 임의의 Async 전환을 하지 않는다.
2. 외부 HTTP 호출은 프로젝트의 공용 Outbound Client 계약을 우선 사용한다.
3. Secret, Password, Token, Credential을 DB 응답, 로그, Git, tracked file, 명령행에 평문으로 남기지 않는다.
4. Session/RBAC/Authorization은 서버가 정본이다. Frontend role gate만으로 권한을 보장하지 않는다.
5. 서버 데이터를 `innerHTML` 등으로 무검증 주입하지 않는다.
6. UTC 저장 계약을 유지하고 표시/정책 시간대는 현재 프로젝트 기준을 따른다.
7. DB transaction, retry, lock/busy 분류 등 기존 데이터 무결성 계약을 우회하지 않는다.
8. UI/UX 변경을 이유로 보안 통제, RBAC, CSRF, Secret 보호를 약화하지 않는다.
9. unrelated shared service, 외부 Runner, Nginx 공용 설정을 현재 작업 때문에 임의로 파괴하지 않는다.

## 5. 작업 선택과 Root Cause 처리

Backlog 항목을 한 건씩 기계적으로 닫지 않는다.

문제 하나를 보면 Repository 전체에서 같은 Pattern과 Root Cause를 찾는다.

- UI 문제 → Shared Component + 모든 주요 Consumer
- Layout 문제 → Page Archetype + Container/Grid/Responsive 계약
- Brand 문제 → Theme/Token/Header/Sidebar/Primary/AI/Chart/State 전체
- Empty State 문제 → 동일 Empty Pattern을 쓰는 전체 Route
- RBAC 문제 → 동일 Permission/Scope/API 경로 전체
- API 오류 → 공통 Client/Error Contract
- DB 문제 → 동일 Transaction/Retry Pattern

주요 기능은 가능하면 다음 흐름까지 닫는다.

`Screen → Action → Network → API → Backend → DB/Data → Result → Related Screen → Reload/State → Permission/RBAC`

UI-only 수정, Backend-only 수정, 페이지가 열리기만 하는 검증은 완료가 아니다.

## 6. Frontend와 Product UX는 필수 완료 범위

Frontend와 실제 Product UX는 Backend/API/DB와 동일한 필수 범위다.

Token, Theme, CSS, Shared Primitive 정리만으로 Design 완료라고 하지 않는다.

각 Page의 실제 목적과 사용자가 해야 할 판단/행동을 기준으로 다음을 확인한다.

- Information Hierarchy
- Content Architecture
- Layout/Space Utilization
- Brand Identity
- Typography
- Density
- Search/Filter/Form
- Table/Grid
- Empty/Loading/Error/Permission
- Responsive/Zoom
- Accessibility/Keyboard/Focus
- 주요 Action과 Feedback

특히 큰 화면에서 콘텐츠가 좌측 상단에만 몰리고 나머지가 거대한 Blank Canvas로 남는 상태를 허용하지 않는다.

승인, Empty List, 놀이, 기능 개선 제안, Sprint 등 데이터가 적은 화면도 Page 전체가 완성된 제품처럼 보여야 한다.

Dashboard/Home은 KPI 숫자만 가로로 나열하고 White Rectangle을 반복하는 구조에서 끝내지 않는다.

Project는 `KPI + Filter + Table`이 최선인지 다시 판단한다.

Chat은 `좌측 목록 + 거대한 빈 대화 영역 + 입력창` 수준에서 끝내지 않는다.

Sprint는 데이터가 없을 때 거대한 빈 Chart Container를 유지하지 않는다.

일반 사용자 문서 화면에는 수동 동기화 Action과 내부 운영 중심 동기화 정보가 기본 노출되지 않아야 한다.

## 7. Brand와 Clovi

Purple/Indigo는 ClovirAssist의 사용자 확정 Brand Identity다.

다음 영역에서 실제 제품 정체성이 느껴지게 사용한다.

- Global Header
- Navigation/Selected State
- Primary Action
- AI 영역
- Key Metric/Highlight
- Chart/Data Highlight
- Focus/Interactive State

단순히 Logo만 Purple이고 나머지 제품 전체가 White/Gray가 되는 결과는 실패다.

Clovi는 용도에 맞는 Canonical Asset과 Pose를 사용한다.

CSS Box 크기가 아니라 실제 Browser에서 보이는 캐릭터의 얼굴, 표정, 존재감을 기준으로 검수한다. 투명 여백 때문에 실제 Character가 지나치게 작아 보이면 Asset framing 또는 Rendering 방식을 조정한다.

Empty State에서 작은 Clovi 하나만 놓고 화면 대부분을 비우는 방식으로 문제를 숨기지 않는다.

## 8. 누락 방지 Control Plane

현재 UI Renewal 작업에서는 다음 Control Artifact를 정본으로 유지한다.

### `docs/ui-renewal/REQUIREMENT_MATRIX.md`

모든 Requirement와 Sub Requirement에 다음을 연결한다.

- Requirement ID
- 영향 Route/Page
- 구현 위치
- 상태
- 검증 방법
- Evidence

### `docs/ui-renewal/ROUTE_COVERAGE.json`

Source 기준 사용자/관리자 전체 Route를 포함한다.

최소 필드:

- route
- archetype
- role
- states_checked
- visual_audit
- functional_audit
- responsive_audit
- before_capture
- after_capture
- status
- evidence

### `docs/ui-renewal/WORK_STATE.md`

현재 Wave, 완료 범위, 다음 작업, 실제 외부 Blocker만 기록한다. 긴 History를 누적하지 않는다.

Coverage 검사 Script를 유지하고 최소 다음을 FAIL 처리한다.

- Source Route가 Coverage에 없음
- UNKNOWN/TODO/NOT_AUDITED Route 존재
- Requirement Mapping 누락
- 완료인데 Evidence 없음
- Visual/Functional Audit 미수행
- 주요 Route Before/After 누락
- Critical/High Finding 잔존

## 9. 테스트 전략

구현 중에는 Focused Test를 자주 실행하고 전체 Regression은 의미 있는 Root Cause 묶음이 수렴한 뒤 통합 실행한다.

- Backend: unit/integration/API/security
- DB: transaction/integrity/concurrency/retry/migration
- Frontend: component/route/helper/interaction
- RBAC: allow/deny/scope negative case
- Shared UI: component + 대표 Consumer regression

과거 Test가 Legacy DOM/CSS/Visual을 고정하고 있다면 새 UX Contract를 검증하도록 갱신한다.

Assertion을 약화하거나 Test를 삭제해서 PASS시키지 않는다.

Test PASS는 Visual PASS와 동일하지 않다.

## 10. Whole-product 재감사

상당량 구현한 뒤 전체 Repository와 실제 Browser를 다시 감사한다.

Routes, Screens, Components, API, Backend, DB, RBAC, Admin/User Workflow, Design/UX, Responsive/Theme, Integrations, Operations, Tests, Coverage를 포함한다.

새로운 중대한 Root Cause 범주가 계속 나오면 아직 수렴하지 않은 것이다. 계속 수정한다.

## 11. TEST SERVER, Hostname, TLS

Canonical Browser URL은 `https://clovirassist.gooddi.lab`이다.

TEST SERVER의 실제 IP는 현재 Repository/Deployment/Runtime 설정에서 확인한다. 과거 기억으로 마지막 Octet을 하드코딩하지 않는다.

Hostname Migration 시 다음을 함께 검증한다.

- DNS/Host Mapping
- OS Hostname/FQDN이 실제로 필요한지 여부
- Nginx/Reverse Proxy `server_name`
- Application Base URL
- Allowed Host/Trusted Origin/CORS/CSRF
- Cookie Domain/Secure/SameSite
- WebSocket/SSE
- Redirect/Callback URL
- Browser E2E Target
- Generated Absolute URL
- Certificate 생성/설치/갱신 Script

TLS Certificate의 CN/SAN은 `clovirassist.gooddi.lab`과 일치해야 한다.

자체 서명 Trust Warning과 Hostname Mismatch를 동일한 문제로 취급하지 않는다.

실제 TLS Handshake에서 제공되는 Certificate도 확인한다.

## 12. Chrome Whole-product E2E

통합 배포 후 실제 Chrome 기반 Browser E2E를 수행한다.

Screenshot 존재나 Health 200만으로 완료 처리하지 않는다.

가능한 주요 Flow에서 다음을 확인한다.

`Screen → User Action → Network Request → API → Backend → DB/Data → UI Result → Related Screen → Reload → Permission/RBAC`

또한 다음 상태를 확인한다.

- Console error/warning
- Network 4xx/5xx
- Empty/Loading/Error/Retry
- Permission denied
- Long/Many data
- Navigation/deep-link/refresh/state retention
- Modal/Drawer/Form
- Keyboard/Focus
- Responsive/Zoom
- Light/Dark
- Brand Identity
- Clovi actual visual size

## 13. PROJECT_COMPLETE

다음 조건을 모두 만족하기 전에는 `PROJECT_COMPLETE`를 만들거나 전면 리뉴얼 완료라고 보고하지 않는다.

1. Source 기준 전체 Route가 Coverage에 존재
2. 전체 Route Visual Audit 완료
3. 주요 Workflow Functional Audit 완료
4. 모든 Requirement가 Matrix에 Mapping
5. UNKNOWN/TODO/NOT_AUDITED 0건
6. Critical/High Finding 0건
7. Purple/Indigo Brand Identity 실제 Browser 확인
8. Clovi Brand Character 검수 PASS
9. 주요 Page Before/After 독립 Visual Review PASS
10. 거대한 불필요 Blank Canvas 잔존 Route 0건
11. 일반 사용자 수동 문서 동기화 제거 확인
12. FHD/QHD/4K 및 주요 Zoom 검증
13. 401/403, Loading, Error, Permission, Long Text, Many Data 핵심 상태 검증
14. Backend/Frontend/Runner/Static/Build Regression PASS
15. Coverage Gate PASS
16. 독립 Visual Reviewer PASS
17. 독립 Requirement Reviewer PASS
18. `https://clovirassist.gooddi.lab` 기준 Browser E2E PASS
19. TLS Certificate CN/SAN Hostname 일치
20. 현재 Product-owned Source/Config/Artifact에 Legacy Product Identity 잔존 없음

외부 Secret 부재, MFA, 실제 외부 권한처럼 Claude가 해결할 수 없는 사항만 Blocker로 남길 수 있다.

코드가 많다, 오래 걸린다, 테스트가 많다, 기존 Component가 있다 등의 이유는 미완료 항목을 남기는 근거가 아니다.

## 14. 마지막 규칙

AREA를 끝내지 마라. CYCLE을 끝내지 마라. BACKLOG 몇 건을 끝내지 마라. 제품 전체를 끝내라.

조사는 넓게 하고 수정은 Root Cause 단위로 한다.

Frontend, Backend, DB, RBAC, UX, Brand, QA 모두 필수다.

Checkpoint 후 멈추지 않는다.

기능적으로 맞는 것과 제품이 실제로 좋아 보이는 것은 둘 다 통과해야 한다.