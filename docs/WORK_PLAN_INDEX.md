# (사용 중지) MASTER PLAN — 이전 축의 전체 작업 마스터 계획

> ## ⚠️ 이 문서는 정본이 아니다 (2026-08-21, S0)
>
> **현재 정본 계획은 [`platform/MASTER_PLAN.md`](platform/MASTER_PLAN.md) 다.**
> 진입점은 [`platform/WORK_STATE.md`](platform/WORK_STATE.md),
> 큰 작업 단위는 [`platform/BACKLOG.md`](platform/BACKLOG.md),
> 실측 목록은 [`platform/INVENTORY/`](platform/INVENTORY/README.md),
> 설치 사양은 [`platform/INSTALLATION.md`](platform/INSTALLATION.md).
>
> 이 문서가 가리키던 `WORK_STATE.md` · `BACKLOG.md` · `QA_COVERAGE.md` · `BUILD_LOG.md` 는
> **더 이상 저장소에 없다.** 아래 내용은 2026-08-08 판이고, 그 뒤 제품이 **Notion/SQLite 폐기 ·
> PostgreSQL System of Record** 로 방향을 바꿨다(**D-187**). 남겨 두는 이유는 완료 기준과 사이클
> 순서의 의도가 여전히 읽을 값이 있어서지, 실행 계획이라서가 아니다.
>
> 설계 판단은 [DECISIONS.md](DECISIONS.md) — 현재 묶음은 **D-187~D-208**.
>
> **2026-08-08 전면 개정.** 이전 판(2026-08-03)은 "UI 재설계 + 저장된 계획 실행" 중심이었고
> 5일치 작업만큼 낡았다. 그 내용 중 살아 있는 것은 아래 §5에 흡수했다.

---

## 1. 목표

ClovirAssist를 **실제 상용 제품 완성도**로 올린다. 사용자가 알려준 문제를 고치는 것이 아니라,
제품 전체를 직접 분석해 문제를 스스로 발견하고 근본 원인을 고친다.

**완료 기준**: 제품을 처음부터 다시 훑었을 때 새로운 UI/UX 문제·기능 오류·연동 오류·권한 오류·
반응형 문제·누락 기능·불필요한 페이지·중복 구현을 거의 더 못 찾는 상태.
즉 **사용자가 계속 문제를 찾아 알려줘야 하는 상태에서 벗어나는 것**.

**전제 파기**: 기존 UI·공통 CSS·공통 컴포넌트·디자인 토큰·메뉴·페이지 구조·API가 올바르게 설계돼
있다는 전제를 두지 않는다. 공통 컴포넌트 자체가 계속 검증 대상이다.
**"안 깨지고 실행된다"는 정상 판정 근거가 아니다.**

---

## 2. 두 단계

| 단계 | 모델 | 하는 일 | 종료 조건 |
|---|---|---|---|
| **A. 전수조사** (지금) | Opus | 제품 전체를 반복 조사해 BACKLOG·계획을 실행 가능한 수준까지 완성. 제품 코드는 고치지 않는다 | 추가 전수조사를 해도 **새로운 큰 범주의 문제가 거의 안 나오는 상태**. 버그 0이 아니라 "무엇을 구현해야 하는지 충분히 발견됨" |
| **B. 구현** | Sonnet | BACKLOG를 사이클 단위로 일괄 수정 → 통합 테스트 → 배포 → 실환경 재검증 → 다음 사이클 | 사용자 중단 |

**단계 A에서 예외적으로 허용하는 작업**: HEAD 배포 · QA 하네스 보강 · QA 계정 생성 ·
worktree 정리 · 이 문서들 작성. (조사 자체를 가능하게 만드는 것)

---

## 3. 구현 사이클 순서 (단계 B)

근본 원인이 아래로 흐르는 순서다. 뒤집으면 두 번 일한다.

| 사이클 | 내용 | 왜 이 순서인가 | BACKLOG |
|---|---|---|---|
| **1. 디자인 시스템** | 토큰·Variant·Typography·Color·Card·반응형 규칙을 **의미로부터 재설계** | 모든 화면이 이것을 통과해 그려진다. AI 드로어 통합도 이 결과 위에서 해야 한다 | `DS-01`~`DS-31` |
| **2. AI 도우미** | 고장난 것(404·타임아웃 역전) → 아키텍처(스트리밍·중단·직렬화) → 기억·문맥 → 능력 → 프런트 통합 | 사용자가 한계를 지적한 영역. 프런트 통합이 사이클 1에 의존 | `AI-01`~`AI-50` |
| **3. 관리자 IA + 검색** | 업무 흐름 기준 재편, 검색 역할 분리 | 화면을 옮기므로 디자인 시스템이 먼저 서야 한다 | `IA-01`~`IA-05` |
| **4. 기능·데이터·권한 E2E** | 확정 실결함 + 미감사 모듈 전수조사 + 비정상 상태 | 화면이 안정된 뒤에 흐름을 본다 | `FN-*`, `SEC-*` |
| **5+. 전체 재순회** | 고친 곳만이 아니라 제품 전체를 처음부터 다시 | 새 문제가 계속 나오는 동안은 안 끝난 것 | — |

각 사이클은 **기능 하나 고칠 때마다 테스트·배포하지 않는다.** 한 사이클에 최대한 모아 공통 원인을
고치고, 통합 테스트 → 배포 → 실환경 전체 재검증을 한 번 한다.

---

## 4. 완료의 정의 — 7축 검증

**"방문함"도 "코드를 고쳤음"도 완료가 아니다.** [QA_COVERAGE.md](QA_COVERAGE.md)의 7축을 전부
통과해야 한다: Chrome 화면 → 실제 기능 실행 → API → DB·데이터 흐름 → Console·Network → RBAC →
관련 화면 연동 (+ 반응형·Theme).

문제를 발견하면 그 화면만 고치지 않고 **의무 역추적**한다:
`해당 화면 → 같은 컴포넌트를 쓰는 다른 화면 → 관련 CSS·레이아웃 → 연결된 기능 → API → DB → 권한
→ 다른 사용자/관리자 화면`

### 매 사이클 게이트
| 층 | 명령 | 기준 |
|---|---|---|
| 정적 | `bash scripts/static_checks.sh` | `STATIC_CHECKS_OK` |
| 백엔드 | `.venv/Scripts/python -m pytest` | 2512개 |
| 러너 | `RUNNER_TOKEN=test … pytest runner/claude-work-assistant/` | 263개 (**루트 pytest에 미포함**) |
| 프런트 | `cd frontend && npm test` | 172파일 |
| 전체 | `bash scripts/final_verify.sh` | `FINAL_VERIFY_OK` |
| 배포 | `BASE=… bash scripts/verify_deploy.sh` | `DEPLOY_VERIFY_OK` |
| 시각 | `ui_qa.run --label cN --modals --fail-on all` | 신규 fail 0 + **PNG 직접 판독** |
| 실브라우저 | Chrome MCP(연결 후) | JS/API 오류·반복요청 0 |

---

## 5. 이전 판에서 살아남은 항목

전부 [BACKLOG.md](BACKLOG.md)에 흡수했거나 아래에 남긴다.

**여전히 미검증(사람 확인 필요)** — 이전 §8이 "에이전트가 증명할 수 없다"고 적어 둔 것.
단계 B에서 실제 브라우저로 수행한다:
1. **실제 채팅 → 진짜 Notion 티켓 생성** e2e. 재전달 시 티켓이 **하나만** 생기는지 (BACKLOG `AI-50`, `AI-02`)
2. 실제 4K 패널에서 100%·150% 배율 양쪽
3. 다크모드가 재로그인 후 유지되는지(공용 PC에서 계정별로 갈리는지)
4. 관리자 화면군별 쓰기 액션 1개씩
5. 알림 딥링크 → 목적 화면 + 나브 하이라이트
6. 채팅 이미지 전송, 실패 후 재시도
7. 비밀번호 강제 변경 흐름

**n8n 쪽 변경이 필요한 미해결 2건** (`docs/RUNNER_HANDOFF.md`):
- n8n이 우리 `idempotency_key`를 읽지 않아 중복 방지가 n8n 휘발성 메모리에만 의존 → BACKLOG `AI-02`
- 사용자 재시도와 워커 재시도가 본문상 구분되지 않는다

**참조 문서**: 대규모 제품화는 `PRODUCTIZATION_ARCHITECTURE.md`, 미확정 아이디어는
`IDEAS_BACKLOG.md`, 구조적 한계는 `KNOWN_LIMITATIONS.md`, 기능별 상세는 `CLAUDE.md` §9 색인.

**이전 판의 [완료] 항목**(MUI 전환·4K 지원·DataScreen 통합·Phase 2c 문서 재분류·러너 조용한 실패
3건 제거 등)은 `BUILD_LOG.md`에 이력으로 남아 있다. 여기서 반복하지 않는다.

---

## 6. 지키는 것

**불변규칙은 [`CLAUDE.md`](../CLAUDE.md) §2가 정본**이다 — sync 핸들러 · `OutboundClient` 단일 관문 ·
secret 미노출 · 비밀번호 stdin 전용 · opaque 세션 · 서버측 RBAC · 불변성 · 작은 파일 · UTC 저장.
n8n(`:5678`)·러너(`:8787/8788/8789`)·기존 nginx vhost **무접촉**.

**보존할 강점(회귀시키지 말 것)**: rem 기반 4K 스케일 레버 하나(`--clv-root-fs` 16→18→20px) ·
중앙화된 `CONTENT_MAX_WIDTH` · `kit.FormModal` 폼 계약 · `charts/base.jsx`의 다크 대응 색 해석 ·
`StatCard`가 색만으로 심각도를 전하지 않는 것(WCAG 1.4.1) · `app/`에 `TODO/FIXME` **0건** ·
CSRF 커버리지 빈틈 없음 · 스코프 위반 시 403이 아닌 **404**(열거 방지) · 전체화면 채팅의 폴링
백오프·멱등키 재사용·고아 대화 정리·IME 가드 · baseline 파싱 가드 테스트 3종
(`theme-baseline` · `density` · `tokens-baseline`) · 정적 검사 21단계.
