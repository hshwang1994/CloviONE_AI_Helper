# CLAUDE.md — ClovirAssist

> ClovirAssist Repository에서 Claude Code가 항상 따르는 공통 실행 규칙이다.
> 특정 프로젝트, Wave, Session, Migration의 상세 계획은 각 작업의 정본 문서가 담당한다.
> 문서와 Source/Git/Test/Runtime이 충돌하면 실제 상태를 확인하고 문서를 정정한다.

## 0. Product Identity

- Product Name: `ClovirAssist`
- Technical Slug: `clovirassist`
- Web Hostname: `clovirassist.gooddi.lab`
- Brand 핵심 색상은 Purple/Indigo다.
- Clovi는 핵심 Brand Character다.
- Product-owned Source/Config/Runtime/Browser/Deployment/TLS에 의도하지 않은 Legacy Identity를 남기지 않는다.
- Git History Rewrite는 별도 요구가 없는 한 기본 범위가 아니다.

## 1. 지시 우선순위와 작업 범위

우선순위:
1. 현재 사용자 지시
2. 현재 작업의 정본 Plan / WORK_STATE / Decision
3. 이 `CLAUDE.md`
4. 기타 문서와 과거 기록

- 사용자 지시가 이 파일보다 우선한다.
- 지정된 기능/Stage/Session/Work Packet/Wave 범위만 완전히 끝낸다.
- 범위 밖의 다음 작업을 임의로 시작하지 않는다.
- Commit/Test PASS 자체는 Stop Condition이 아니지만 지정 범위의 Exit 조건을 만족하면 정상 종료할 수 있다.
- 전체 프로젝트 자율 완료를 명시한 경우에만 다음 작업을 계속한다.
- 현재 변경이 만든 Regression은 후속 작업으로 넘기지 않는다.
- 범위 밖 Finding은 기록하고 적절한 Owner 작업으로 Routing한다.

## 2. 불필요한 정책과 사용자 Gate 금지

다음을 새로 만들지 않는다:
- Source/Plan에 없는 승인 절차
- 불필요한 ADR/운영 승인
- 내부 구현 결정을 위한 사용자 선택 Gate
- 자동화 가능한 작업의 수동 확인 단계
- 근거 없는 Governance/Compliance 절차
- 필요 이상으로 엄격한 자체 정책
- 가능성만으로 작업을 막는 보수적 제한

사람 확인은 Claude가 실제로 해결할 수 없는 외부 조건일 때만 요청한다.
예: MFA, 외부 승인, 접근 권한 자체 부재, 양립 불가능한 사용자 요구, 허가 범위를 넘는 되돌리기 어려운 Production 파괴 작업.

그 외 구현 방식, 구조, 파일 구성, 테스트, 리팩터링은 Source/Plan/Decision을 근거로 스스로 판단한다.
실제 Blocker인지 확인하지 않고 "정책상 불가"라고 판단하지 않는다.
기존 RBAC/Secret/CSRF 등 보안 통제를 약화해 우회하지 않는다.

## 3. 실행 전 Preflight

큰 조사나 구현 전에 다음만 짧게 확인한다:
- 작업 Repository와 Git 상태
- 작업 범위와 정본 문서
- 필요한 파일/Tool/Runtime/Network
- 필요한 계정/sudo/외부 서비스 접근
- 되돌리기 어려운 변경 여부

권한/환경 문제를 중간에 발견해 재작업이나 이상한 우회 구현을 만들지 않는 것이 목적이다.
정상적인 기존 경로로 해결 가능하면 사용자에게 되묻지 말고 진행한다.
랩 서버 SSH/sudo와 Notion 토큰은 `dist/ops/server.env`와 `var/secrets/`에 있다(gitignore). 파일이 있으면 읽고 묻지 않는다. 값을 tracked 파일·커밋·로그에 복사하지 않는다.
사람만 해결 가능한 실제 Blocker는 큰 구현 전에 보고한다.

## 4. Session 시작과 Context 복구

새 Session, `/compact`, 장시간 작업 후:
1. 현재 사용자 지시
2. Git status/diff/최근 관련 Commit
3. 현재 작업의 WORK_STATE
4. 필요한 Plan/Decision
5. 영향 Source/Test/Config
6. 필요한 경우 Runtime/Browser/Server

- Repository 전체를 매 Session 다시 조사하지 않는다.
- Source 지문이 같고 신뢰 가능한 Inventory/Evidence가 있으면 재사용한다.
- 같은 문서/로그를 이유 없이 반복해서 읽지 않는다.
- 대화 Context를 장기 기억의 정본으로 사용하지 않는다.

현재 플랫폼 전환 진입점:
- `docs/platform/WORK_STATE.md`

필요할 때만 `docs/platform/MASTER_PLAN.md`, `docs/platform/BACKLOG.md`, `docs/platform/INSTALLATION.md`, `docs/platform/INVENTORY/`, `docs/DECISIONS.md`를 읽는다.
UI 관련 작업에서는 필요할 때 `docs/ui-renewal/` Control Artifact를 읽는다.
상세 계획과 진행 이력을 이 파일에 복제하지 않는다.

## 5. 작업 방식과 Work Packet

- Backlog를 한 건씩 기계적으로 닫지 않는다.
- 문제를 보면 같은 Pattern/Root Cause가 다른 Consumer에도 있는지 확인한다.
- 공통 원인이면 Shared Layer에서 수정하고, 다른 의미의 기능을 억지로 공통화하지 않는다.
- 큰 Stage/Wave는 독립 검증과 Commit이 가능한 의미 있는 Work Packet으로 나눌 수 있다.
- 파일/함수 하나 단위로 과도하게 쪼개지 않는다.
- Stage를 여러 Packet으로 나눠도 Stage Exit Gate는 마지막에 확인한다.
- 다음 작업의 성격이 크게 달라지거나 Context 가치가 낮아질 때 `/clear` 경계로 삼는다.

병렬 Agent 사용 시:
- 파일 Scope가 겹치지 않게 한다.
- Shared Foundation 동시 수정은 피한다.
- 최종 Coordinator가 Diff를 직접 확인한다.
- Subagent PASS 보고만으로 완료 판정하지 않는다.
- 새 함수/Component가 실제 호출 경로에 연결됐는지 확인한다.

## 6. 핵심 기술 불변 규칙

1. FastAPI/SQLAlchemy의 현재 Sync 일관성을 임의로 Async 전환하지 않는다.
2. 외부 HTTP 호출은 공용 Outbound Client 계약을 우선 사용한다.
3. Secret/Password/Token/Credential을 Git/Log/Fixture/Evidence/명령행에 평문 노출하지 않는다.
4. Session/RBAC/Authorization의 정본은 Server다.
5. Frontend Role Gate만으로 권한을 보장하지 않는다.
6. 서버 데이터를 무검증 `innerHTML` 등에 주입하지 않는다.
7. UTC 저장 계약을 유지한다.
8. DB Transaction/Retry/Lock/Conflict 계약을 우회하지 않는다.
9. CSRF/Session/Secret 보호를 기능 수정 때문에 약화하지 않는다.
10. unrelated Shared Service/외부 시스템을 임의로 파괴하지 않는다.

## 7. 테스트와 검증 실행 경제

기본 순서:
`Implementation → Targeted Test → Static/Contract → Related Integration → Impacted Flow/E2E → 필요한 Reviewer → Finding 수정 → 영향 범위 재검증 → Exit Gate`

- 필요한 검증은 반드시 한다.
- 같은 Source/Build에서 이미 PASS한 고비용 검증은 이유 없이 반복하지 않는다.
- Evidence 재사용 시 Source/Build 지문을 확인한다.
- Source 변경 후 변경 Domain → Integration → 영향 Flow 순으로 검증한다.
- 일부 실패하면 실패 Test/Route/Flow/Shard부터 재실행한다.
- 작은 변경마다 Full Regression을 반복하지 않는다.
- Shared Foundation/전역 계약 변경이면 필요한 상위 Regression을 수행한다.
- 비용 때문에 Security/Integrity/Permission 검증을 생략하지 않는다.
- 새 Probe/Harness는 Product 판정 전에 Known Good/Known Bad/Counterexample로 검증한다.

## 8. 반복 루프 방지

다음 상황에서 같은 접근을 계속 반복하지 않는다:
- 같은 명령/Test가 같은 이유로 두 번 이상 실패
- Source 변화 없이 같은 Probe/Capture/Reviewer 반복
- 새로운 사실 없이 동일 파일/로그 재독
- 같은 Finding을 표현만 바꿔 재등록
- 작은 수정마다 전체 Regression/Capture 재실행
- 범위 밖 문제 때문에 원래 작업이 끝나지 않음

같은 접근으로 두 번 실패하면 세 번째는 자동 반복하지 않는다.
Root Cause 가설, Test/Probe/Fixture, 기존 Evidence 재사용 가능성, 더 작은 재현 범위, 실제 Blocker 여부를 먼저 재판단한다.
새로운 정보나 Source 변화 없이 같은 행동만 반복되면 루프를 중단하고 접근을 바꾼다.

## 9. 문서와 상태

- WORK_STATE: 현재 위치와 다음 시작점
- MASTER PLAN: 전체 구조와 완료 조건
- BACKLOG: 남은 의미 있는 작업
- DECISIONS: 이후 구현에 영향을 주는 확정 결정
- INVENTORY: 실제 조사 결과
- Evidence/Coverage: 검증 증거

같은 내용을 여러 문서에 복제하지 않는다.
역할이 같은 새 문서를 만들지 않는다.
긴 History를 WORK_STATE에 누적하지 않는다.
Secret은 문서에 기록하지 않는다.

## 10. Domain별 추가 원칙

UI/UX:
- 실제 Page 목적, 정보 위계, 밀도, Responsive, Empty/Loading/Error, Keyboard/Focus를 본다.
- Test PASS와 Visual PASS를 같은 것으로 보지 않는다. 테마 객체·토큰만 바꾸고 브라우저가 받는 CSS에 안 넣지 않는다.
- Purple/Indigo Brand와 Clovi 역할을 유지한다.
- 한글 줄바꿈은 정적 CSS(`frontend/src/styles/root.css`)의 `keep-all`이다. `overflow-wrap: anywhere`로 덮지 않는다. JSON·UUID·코드만 글자 단위다.
- 짧은 화면 설명에 `70ch`를 걸지 않는다. 긴 산문만 `PROSE_MAX_WIDTH`.
- UI 문구에 `\n`/`<br>`를 넣지 않는다. 짧은 화면 설명·EmptyState·ErrorState 문구는 `COPY_LIMIT` 이하로 쓴다. 숫자를 직접 적지 않는다. 칸 폭은 `EMPTY_STATE_MAX_CH`/`ERROR_STATE_MAX_CH`이고, 글자 한도는 그 폭에서 계산된다.
- 본문 글꼴은 Pretendard(`--font-stack`)다. `global.css`에 시스템 글꼴을 다시 박지 않는다.
- 한국어(UI 문구·사용자에게 보이는 안내·코드 주석)는 아래처럼 쓴다.
  - 결론을 먼저 쓰고, 주어와 서술어가 있는 완전한 문장으로 끝낸다.
  - 조각 문장("한눈에.", "만 봅니다.", "고치기는 담당자만.")을 쓰지 않는다.
  - 번역투 나열("상태, 기간, 진행률을 한눈에")을 쓰지 않는다.
  - 권한·능력은 "할 수 있습니다"를 유지한다.
  - "해당", "이를 통해", "수행한다", "잇습니다" 같은 서류 말투·잘못된 동사를 쓰지 않는다.
  - 짧은 화면 설명도 한 문장으로 끝나게 한다. 예: "팀원과 자유롭게 이야기를 나눕니다."

Runtime/Deployment:
- 실제 Runtime/Config/Service/TLS를 확인한다.
- Canonical Hostname은 `clovirassist.gooddi.lab`이다.
- 테스트 서버라는 이유로 보안 계약을 약화하지 않는다.

DB/Migration/Storage:
- 필요한 범위에서 Transaction/Integrity/Concurrency/Migration/Rollback/Backup을 확인한다.
- Migration은 수량뿐 아니라 관계/중복/누락/변환 실패도 검증한다.
- Storage 미마운트 시 의도하지 않은 Local Write를 허용하지 않는다.

AI:
- 권한 없는 데이터가 Retrieval/Model Context에 들어가지 않게 한다.
- Permission Filter는 Context 생성 전에 적용한다.
- Prompt/Tool/External Content의 신뢰 경계를 유지한다.

## 11. 완료 판정

완료는 현재 요청의 Acceptance Condition 충족으로 판단한다.

확인:
- 요청 범위가 실제 구현됐는가
- 관련 Regression이 없는가
- 필요한 Test/Runtime/Browser/DB 검증이 끝났는가
- Security/Permission을 약화하지 않았는가
- 지속 문서가 현재 상태와 일치하는가
- 현재 변경으로 만든 미해결 Regression이 없는가

특정 Stage/Packet이 현재 범위면 그 Exit Gate를 만족한 시점이 정상 완료다.
전체 프로젝트 완료가 요청된 경우에만 전체 Product Acceptance를 완료 기준으로 사용한다.

## 12. 마지막 규칙

- 현재 사용자 지시 범위를 정확히 지킨다.
- 조사는 필요한 만큼 넓게, 수정은 Root Cause 단위로 한다.
- 이미 증명한 사실을 이유 없이 반복 검증하지 않는다.
- 문서보다 실제 Source와 검증 결과를 우선한다.
- 필요 없는 정책이나 사용자 승인 Gate를 만들지 않는다.
- 권한 문제를 이상한 우회 구현으로 숨기지 않는다.
- 같은 실패를 같은 방법으로 반복하지 않는다.
- 다음 작업을 임의로 시작하지 않는다.
- 현재 요청한 것을 완전히 끝낸다.
