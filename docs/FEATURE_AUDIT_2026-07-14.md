# FEATURE AUDIT — ClovirONE Web Assistant (2026-07-14)

전수 기능 감사 결과. **방법**: 21개 기능 도메인을 병렬 에이전트가 감사(백엔드 완성도·UI 배선·기능 준비상태·테스트 커버리지) → 발견된 문제를 **적대적 검증 에이전트가 재확인**(false alarm 제거). 총 42 에이전트. 각 항목의 file:line 증거는 감사 저널에 있음.

> **진행 상태(2026-07-14 P0 완료)**: 아래 실제 버그 중 P0 11건 수정 완료 + 회귀 테스트(394 green).
> chat 안전차단(할당), prompts/policies 409, notion stale 정리, jobs started_at, templates policy_id,
> backups 파일명 μs, chat 커서, settings N+1, 권한 버튼 게이팅(runners/integrations/workflows/backups).
> 러너 헬스 오탐은 시드(discovery.py) 수정 + **프로덕션 3개 통합 health_url 반영·검증(all up)**.
> 정적(브랜드·콜아웃·권한게이팅) 프로덕션 배포·해시검증 완료.
>
> **P1 완료(콘솔 쓰기 UI)**: 데이터주도 폼 프레임워크(create/edit/detail/form-action/sublist) 구축 +
> 전 섹션 배선 — Runners·Integrations·Workflows(생성/수정/상세), Prompt/Policy(생성/수정/상태전이
> draft→test→review→published/새버전/롤백), Templates(생성/수정/활성), Schedules(생성/수정/실행이력),
> **Jobs 섹션 신설**(재시도/취소), Documents(생성 폼), Notion(수동매핑/충돌해결), Approvals(상세/취소),
> Users(역할변경/세션조회), Notifications(읽음). 로컬 실검증(러너·프롬프트 생성, draft→test 전이).
> A의 HIGH ui-gap 19건 대부분 해소.
>
> **P2 완료**: prompt/policy diff 뷰어, Settings 이력/롤백/dry-run UI, schedule run 재시도(UI);
> 백엔드 spec 편차 — health stale→down, approvals 만료 표시, rollback 4곳 async→sync, ui_branding 채팅
> 제목 적용(§D 다수 해소). 정적 P2는 핫배포, 백엔드 P2는 전체 업그레이드 대기(Low·무마이그레이션).
> **잔여(선택)**: policies 규칙스키마 강제(런타임=n8n), audit 마스킹 심화, 500 응답 헤더, 죽은코드 정리, 테스트 보강.

## 요약 (Executive Summary)

- **백엔드: 사실상 완성 + 검수됨.** 21개 중 19개 도메인 `backend_status=complete` (policies·schedules만 partial). 인증·세션·RBAC·outbound 단일관문·job queue·백업 등 핵심 로직은 실제 구현 + 테스트 통과. 스텁 아님.
- **관리자 콘솔 UI: 대부분 "읽기 전용" — 이게 가장 큰 갭.** 20/21 도메인에서 `frontend_all_actions_wired="no"`. 백엔드엔 CRUD·수명주기가 다 있는데, 콘솔(sections.js)은 **목록 + 소수 액션만** 노출. 그래서 "페이지마다 뭘 할 수가 없다"는 체감이 **정확**함.
- **확정 결함 106건**(false alarm 제거 후): High 19 · Medium 24 · Low 62 · None 1.
  종류별: **ui-gap 56** · spec-deviation 21 · bug 11 · missing-feature 9 · needs-config 7 · stub 2.

> 정직한 고백: 이전 검수 루프는 **코드 결함**(정확성·보안·동시성)을 봤고 실제로 결함을 잡아 고쳤음. 브라우저 확인은 **빈 페이지 렌더**를 봤음. 하지만 **"백엔드의 모든 기능이 UI에 연결됐는가"(UI 완성도)는 감사하지 않았음.** 갭이 바로 거기임. 이건 제 검수의 명확한 빈틈이 맞음.

---

## A. 관리자 콘솔이 대부분 읽기 전용 (핵심 갭 — HIGH 다수)

백엔드엔 생성/수정/수명주기가 **완전 구현**돼 있으나 콘솔에 **버튼·폼이 없음**. 기능 영역별로:

| 영역 | 백엔드 | 콘솔 UI 현재 | 없는 것(HIGH) |
|---|---|---|---|
| Integrations | 완성(CRUD·config버전·rollback) | 목록 + 헬스체크/활성토글 | **등록·수정·상세·rollback 폼 없음** |
| Runners | 완성(CRUD·clone·health·test·circuit·rollback) | 빈 목록 + 새로고침 | **생성·수정·clone·버전rollback UI 없음** |
| Workflows | 완성(CRUD·test·버전) | 목록 | **생성·수정·rollback UI 없음** |
| Prompts | 완성(draft→published·diff·rollback) | 목록만 | **수명주기 UI 전무(발행·diff·rollback)** |
| Policies | partial(규칙스키마 미검증) | 목록만 | **수명주기 UI 전무** |
| Templates | 완성 | 목록만 | **생성·수정·활성/비활성 UI 없음** |
| Schedules | partial(일부 필드 미배선) | 빈 목록 | **생성·실행이력·재실행 UI 없음** |
| Documents | 완성(preview→approve→publish·품질게이트) | 목록만 | **문서생성 트리거·미리보기/실패사유 상세 없음** |
| Jobs | 완성(retry/cancel/browse API) | **콘솔 섹션 자체가 없음** | **Job 큐 관리 UI 전무** |
| Notifications | 완성(fan-out) | 관리자 목록 | **일반 사용자가 자기 알림 볼 UI 없음** |
| Notion 매핑 | 완성 | 재검증/해제만 | **수동매핑·충돌해결 버튼 없음** |

또한 HIGH **기능 버그 1건**(UI 아님):
- **chat: unmapped 안전차단 정규식이 "내 할당 티켓"을 놓침.** `_FIRST_PERSON` 정규식이 `내 (티켓|프로젝트|담당|업무|작업)`만 매칭 → 채팅 화면 **1번 퀵프롬프트 "내 할당 티켓 보기"**("할당"은 목록에 없음)가 1인칭 요청으로 인식 안 됨 → Notion 미매핑 사용자가 이 버튼을 눌러도 안전차단이 동작하지 않고 n8n으로 요청이 나감. (`app/notion_mapping/service.py:195`)

### A의 MEDIUM/LOW UI 갭 (발췌)
- users: **기존 사용자 역할 변경 UI 없음**(섹션은 광고하지만), 프로필/must_change 편집 없음, 세션 상세 조회 없음
- approvals: **승인자가 승인 대상 payload를 볼 수 없음**(무엇을 승인하는지 안 보임), 요청 취소 없음
- audit: before/after 변경 diff 저장되나 **볼 UI 없음**, 필터 4종(user/object/since/until) 미노출
- settings: dry-run·버전이력·rollback 미노출
- backups: 진단번들·복원안내 미노출, **system_admin 전용 버튼이 모든 read-role에게 보여 클릭 시 403**
- runners: enable/disable 버튼이 operator에게 보이지만 항상 403
- notifications: 읽음 처리·안읽음 카운트 미노출
- health: 진단번들 UI 없음

---

## B. 실제 버그 (11건 — 대부분 Low, 2건은 주목)

- **[HIGH] chat 안전차단 정규식 "내 할당 티켓" 누락** (위 A 참조)
- [Low] prompts·policies: **중복 이름 생성 시 409가 아니라 HTTP 500** 반환(이름당 버전 2개 이상일 때)
- [Low] runners: operator에게 enable/disable 버튼 보이나 항상 403 (권한 불일치 UX)
- [Low] backups: 파일명이 초 단위 → 같은 초에 2개 생성 시 충돌, 보존정리가 참조중 파일 unlink 가능
- [Low] notion: workflow 없음/비활성 시 verify가 **stale notion_user_id/source를 남김**
- [Low] jobs: retry_failed/cancel_queued가 `started_at`을 안 지움
- [Low] settings: effective_settings가 레지스트리 키마다 동일 쿼리 반복(N+1)
- [Low] templates: policy_id를 받아 저장하나 Policy 테이블 검증 안 함
- [Low] chat: `after` 커서 id가 미지일 때 전체 메시지 목록 반환
- [Low] approvals: 만료 승인이 60s sweep 전까지 pending으로 표시

---

## C. 설정 필요 — 정상 (신규 설치의 예상 상태, 결함 아님)

- chat 실제 응답 = n8n webhook 도달 필요
- documents 발행 = 운영자 n8n write 워크플로 필요
- notion 자동검증 = 예약 워크플로 `notion-user-mapping` 등록·활성 필요
- outbound = allowlist 항목 + secret 파일 provisioning 필요
- health 인증서 만료 모니터 = `tls_cert_path` 설정 필요
- 최초 system_admin = out-of-band 시드(설계상)
- 각종 레지스트리(runners/workflows/schedules) 빈 상태 = 관리자가 채움

---

## D. 스펙 편차 (21건 — 대부분 Low)

- integrations: **rollback 핸들러가 `async def`** → sync 일관성 불변식 위반
- health: 'web' 컴포넌트 liveness가 하드코딩(실제 heartbeat 아님), 메모리는 Linux 전용(/proc/meminfo), staleness가 'down' 아닌 'stale' 표기
- settings: `ui_branding`이 채팅 화면 제목이 아니라 로그인 페이지에만 적용
- runners: RunnerHttpProvider.invoke/test_request가 실제 dispatch 경로에 미연결
- schedules: spec §18.3 필드(prompt_id/runner_id/approval_policy/notification_policy) 미배선
- templates: 템플릿 레지스트리가 실행 경로에서 소비 안 됨(메타데이터 전용)
- policies: 규칙 스키마 미검증·미강제(일반 JSON object 체크만)
- chat: Help 카드가 별도 카드 타입으로 미렌더, 초기 퀵프롬프트 1개(프로젝트 티켓 조회) 누락
- core: 500 에러 응답에 CSP/X-Request-ID/Cache-Control 헤더 누락, body-size cap이 Content-Length 있을 때만 적용
- audit: 마스킹이 키 이름 기반만(비민감 키 값 안에 박힌 secret은 미마스킹)
- auth: SESSION_SECRET 미사용(dead config), rotate() dead code(재로그인이 기존 세션 미폐기)
- documents: 승인 발행이 검토본이 아니라 preview를 재생성해 발행
- backups: 실패 백업이 같은 요청 내에서 정리돼 목록에 안 나타남

---

## E. 스텁 / 죽은 코드 / 테스트 커버리지 갭

- [stub] documents: `EXAMPLE_TEMPLATE` 정의됐으나 미사용(dead code)
- [stub] **app/policies/ 는 빈 vestigial 패키지** — policies 도메인이 자체 모듈 구조가 없음
- 테스트 갭: UI↔백엔드 배선 완성도 검증 테스트 없음, notion 프론트 커버리지 0, 여러 에러 브랜치·retention·문서 발행 경로 미테스트

---

## 재정비 계획 (제안, 우선순위)

**P0 — 실제 버그 (작고 명확, 빠르게):**
- chat 안전차단 정규식에 "할당" 추가(내 할당 티켓 차단 복구)
- prompts/policies 중복이름 409, runners/backups 권한버튼 403 노출 정리, notion stale 정리, jobs started_at, backup 파일명 밀리초

**P1 — 관리자 콘솔 쓰기 UI 구축 (가장 큰 작업):** 데이터 주도 폼 프레임워크를 sections.js에 추가해 각 섹션에 생성/수정/수명주기/rollback/상세 모달을 배선. 우선순위: Runners·Integrations → Prompts/Policies/Templates 수명주기 → Schedules → Jobs 섹션 신설 → Documents → Notion 수동매핑/충돌 → Approvals 상세 → Users 역할변경.

**P2 — 스펙 편차:** integrations async→sync, policies 규칙스키마 검증, schedule 필드 배선, web heartbeat 실제화, ui_branding 채팅 제목 적용, 500 응답 헤더 등.

**P3 — 설정 문서화 + 테스트 보강:** C 항목을 운영 체크리스트로, UI 배선 테스트·미커버 경로 테스트 추가.

> 전 항목 file:line 증거: 감사 저널 `subagents/workflows/wf_a3209597-efa/journal.jsonl`.
