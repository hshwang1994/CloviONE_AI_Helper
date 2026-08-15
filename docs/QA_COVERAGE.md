# QA COVERAGE — 무엇이 아직 검증되지 않았는가

> 진입점은 [WORK_STATE.md](WORK_STATE.md). 발견한 문제는 [BACKLOG.md](BACKLOG.md).
>
> **"방문함"은 검증이 아니다.** 아래 7축을 전부 통과해야 검증 완료다.

## 검증 7축

| 축 | 기호 | 뜻 |
|---|---|---|
| 1 Chrome 화면 확인 | `S` | 실제 브라우저에서 렌더된 화면을 봤다(라이트·다크) |
| 2 실제 기능 실행 | `F` | 누르고·쓰고·저장하고·지웠다 |
| 3 API 확인 | `A` | 요청/응답을 직접 봤다 |
| 4 DB·데이터 흐름 | `D` | 저장된 값을 다시 읽어 확인했다 |
| 5 Console·Network | `C` | JS 오류·4xx/5xx·반복 요청을 확인했다 |
| 6 RBAC | `R` | 5역할 × 3스코프에서 메뉴·데이터 범위·API가 옳게 갈리는지 봤다 |
| 7 관련 화면 연동 | `L` | 저장한 것이 다른 화면·목록·배지·알림에 반영되는지 봤다 |
| 8 반응형·Theme | `V` | 8뷰포트 + 브레이크포인트 사이 + 라이트/다크 |

**표기**: `-` 미검증 · `~` 부분 · `O` 완료

**마지막 갱신**: 2026-08-15 — **§13 신설**: Product Audit Cycle `PA-20260812`이 드러낸 **축 자체의 공백 9개**
(`T1`~`T9`). 기존 12축이 전부 런타임 관찰 축이라 *"코드·저장소가 스스로 지켜야 하는 규약"* 과
*"배포본이 검증 대상과 같은가"* 를 보는 칸이 없었다. 그 전 갱신: 2026-08-11 (§12 QAH 하네스 1회차) · 2026-08-08 (사이클 0)

**검증 가능 상태가 됐다** — 사이클 0에서 막고 있던 것 3가지를 전부 치웠다:
- `QA-01` 서버가 HEAD가 아니던 것 → **배포 완료**(`DEPLOY_VERIFY_OK`, 해시 일치 확인)
- `QA-03` 하네스가 자체서명 HTTPS를 못 타던 것 → **`--insecure` 추가**. SSH 터널은 쓰지 않는다 —
  서버가 `COOKIE_SECURE=true`라 Playwright의 API 클라이언트가 http로는 세션 쿠키를 안 싣는다
  ([DECISIONS D-05a](DECISIONS.md))
- `QA-05` 역할이 1종뿐이던 것 → **`qa-user`/`qa-operator`/`qa-auditor`/`qa-admin` 생성**.
  서버 실계정 14개 중 12개가 `admin`이고 **`operator`·`auditor`는 0명**이라 역할 매트릭스를
  재현할 방법이 애초에 없었다

첫 실환경 캡처 `c1-admin`(role=admin, 70라우트 × 2테마 × 1920·3840, `--modals`)이 **완주했다**
— 272페이지. 아래 §1~§4의 라우트별 `S` 열은 **판독(눈으로 봄)** 기준이라 대부분 아직 `-`다.
캡처 자체는 70/73 전부 끝났으므로 PNG는 `dist/ui-qa-admin/c1-admin/` 에 있고 판독만 하면 된다.

---

## 0. 전체 요약

| 구분 | 라우트 | S(캡처) | S(판독) | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|
| 공개(로그인 전) | 4 | 1/4 | 0 | - | - | - | - | - | - | ~ |
| 사용자 콘솔 | 26 | **26/26** | 2 | - | - | - | - | - | - | ~ |
| 관리자(전용+registry) | 43 | **43/43** | 2 | - | - | - | - | - | - | ~ |
| **계** | **73** | **70/73** | **9** | 0 | ~ | 0 | 0 | **~** | 0 | ~ |

> `A`(API)와 `R`(RBAC)이 `0`에서 `~`로 올라갔다 — §6-1에 4역할 × 17엔드포인트 실측 매트릭스가 있다.

- **S(캡처)** = 하네스가 실서버에서 스크린샷을 남겼다. `c1-admin` 실행(role=admin, 70라우트 ×
  2테마 × 1920·3840). 미캡처 3개는 `/change-password`·`/forgot-password`·`/reset-password`(Jinja).
- **S(판독)** = 내가 그 PNG를 눈으로 보고 판정했다. **4/70뿐이다** — 나머지는 아직 안 봤다.
  본 4개에서만 `VIS-01`~`VIS-31` **31건**이 나왔고, **그 4개는 기계 검사 21종을 전부 통과했다.**
- **V(반응형·테마)**: `c1-admin` 완주(272페이지). **21검사 중 20개는 전 페이지 통과**,
  `tiny_text`만 **134 fail / 2 pass / 136 skip**(skip=1920, 검사가 폭 ≥2200에서만 돈다).
  즉 **1920 라이트·다크는 깨끗하고 3840은 SPA 전 화면이 실패**한다. 원인 두 줄까지 확정: `DS-32`.

**과거 실적과의 대조**: 2026-08-04 실행은 992페이지 fail 0이었다. 지금 4K가 전면 실패하므로
**그 사이에 회귀했다.** 같은 검사가 같은 화면을 두고 다른 답을 낸다는 것이 회귀의 정의다.

**모달은 실제로 검사됐고 통과했다(강점)**: `--modals`가 136페이지에서 **모달 512개를 실제로 열어**
7가지 기하 검사(푸터 위치·전폭 버튼·화면 밖·닫기 버튼 유무·닫힘 여부·반지름·폭 분산)를 전부
통과시켰다. `capture.py:370`의 `if modals:` 가드 덕에 **모달을 못 연 페이지는 통과로 세지 않는다**
— 즉 공허한 pass가 아니다. 모달 레이어의 기하는 믿어도 된다(내용·UX는 별개).

**이 표가 말하는 것**: 기계 검사(21종)는 "안 깨졌는가"만 본다. 정보 밀도·강조 수준·시선 흐름·
공간 활용·화면 간 불일치는 **판독(S)으로만** 잡히고, 기능 연결은 `F`~`L` 축으로만 잡힌다.
지금은 그 둘이 거의 비어 있다.

---

## 1. 공개 (로그인 전)

| 라우트 | 화면 | S | F | A | D | C | R | L | V | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|
| `/login` | Jinja | - | - | - | - | - | - | - | - | ui_qa에 포함(`public_login`) |
| `/change-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |
| `/forgot-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함. ~~**FN-01(메일 UI 없음)과 직결**~~ — **2026-08-13 정정**: `FN-01`은 2026-08-11에 이미 닫혔다(`MailStatus.jsx` 신설, `frontend/src/screens/MailStatus.jsx` 존재 확인) — 이 행이 그 정정을 안 반영하고 있었다. 재설정 메일 발송 자체를 검증할 도구(`/mail` 화면의 "시험 메일 보내기")는 이제 있다, 다만 이 라우트 자체(`/forgot-password` 화면)의 ui_qa 캡처는 여전히 미포함 |
| `/reset-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |

## 2. 사용자 콘솔 (26)

> 아래 `S`는 **판독** 기준이다. 캡처는 26/26 전부 끝났다(`dist/ui-qa-admin/c1-admin/`).
> `ui_qa` 열의 "없음"이던 3개(`/projects`·`/projects/:id`·`/ideas`)는 이번에 추가돼 이제 전부 있다.

| 라우트 | 화면 | ui_qa | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|
| `/me` | Home | O | - | - | - | - | - | - | - | - |
| `/my-tickets` | MyTickets | O | - | - | - | - | - | - | - | - |
| `/unassigned` | Unassigned | O | - | - | - | - | - | - | - | - |
| `/new-ticket` | NewTicket | O | - | - | - | - | - | - | - | - |
| `/tickets/:id` | Ticket | O | - | - | - | - | - | - | - | - |
| `/team-tickets` | TeamTickets | O | - | - | - | - | - | - | - | - |
| `/projects` | Projects | O(신규) | - | - | - | - | - | - | - | - |
| `/projects/:id` | Project(+Metrics/Wbs/Weekly/Tickets) | O(신규) | - | - | - | - | - | - | - | - |
| `/sprint` | Sprint | O | - | - | - | - | - | - | - | - |
| `/chat` | Chat | O | - | - | - | - | - | - | - | - |
| `/chat-rooms` | ChatRooms | O | - | - | - | - | - | - | - | - |
| `/chat-rooms/:id` | ChatRoom | O | - | - | - | - | - | - | - | - |
| `/board` | Board | O | - | - | - | - | - | - | - | - |
| `/board/:id` | BoardPost | O | - | - | - | - | - | - | - | - |
| `/ideas` | IdeaBoard | O(신규) | - | - | - | - | - | - | - | - |
| `/team-docs` | TeamDocs | O | - | - | - | - | - | - | - | - |
| `/team-docs/trash` | Trash | O | - | - | - | - | - | - | - | - |
| `/team-docs/:id` | TeamDoc | O | - | - | - | - | - | - | - | - |
| `/games` | Games | O | - | - | - | - | - | - | - | - |
| `/games/:id` | GameRoom | O | - | - | - | - | - | - | - | - |
| `/notifications` | DataScreen | ~ | - | - | - | - | - | - | - | - |
| `/search` | Search | O(3상태) | - | - | - | - | - | - | - | - |
| `/profile` | Profile | O | - | - | - | - | - | - | - | - |
| `/my-stats` | MyStats | O | - | - | - | - | - | - | - | - |
| `/activity` | Activity | O | - | - | - | - | - | - | - | - |

## 3. 관리자 전용 화면 (16)

| 라우트 | 화면 | ui_qa | 최소 역할 | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/dashboard` | Dashboard(916줄) | O | operator | - | - | - | - | - | - | - | - |
| `/users` | Users | O | admin | - | - | - | - | - | - | - | - |
| `/offboarding` | Offboarding | O | admin | - | - | - | - | - | - | - | - |
| `/organizations` | OrgConsole | O | admin | - | - | - | - | - | - | - | - |
| `/departments` | OrgConsole | O | admin | - | - | - | - | - | - | - | - |
| `/org-tree` | OrgConsole | O | admin | - | - | - | - | - | - | - | - |
| `/settings` | Settings(822줄) | O | operator | - | - | - | - | - | - | - | - |
| `/diagnostics` | Ops/Diagnostics | O | admin | - | - | - | - | - | - | - | - |
| `/maintenance` | Ops/Maintenance | O | operator | - | - | - | - | - | - | - | - |
| `/dev-report` | DevReport | O | auditor | - | - | - | - | - | - | - | - |
| `/scheduler-calendar` | SchedulerCalendar | O | operator | - | - | - | - | - | - | - | - |
| `/system` | SystemOps(298줄) | O(신규) | system_admin | - | - | - | - | - | - | - | - |
| `/setup` | SetupWizard(232줄) | O(신규) | system_admin | - | - | - | - | - | - | - | - |
| `/notion-console` | NotionConsole(377줄) | O(신규) | system_admin | - | - | - | - | - | - | - | - |
| `/llm-console` | LlmConsole(354줄) | O(신규) | system_admin | - | - | - | - | - | - | - | - |
| `/search` | Search(공유) | O | — | - | - | - | - | - | - | - | - |

## 4. 관리자 registry — DataScreen 28키

전부 `S/F/A/D/C/R/L/V` 미검증. **28개 전부 열 폭 지정이 0건**(BACKLOG DS-06)이라 좁은 폭에서
제목이 세로로 무너질 수 있는데 아무도 실물로 확인하지 않았다.

| 도메인 파일 | 키 |
|---|---|
| `integrations.js` | integrations · runners · workflows |
| `authoring.js` | prompts · policies · templates · prompt-usage · policy-usage |
| `automation.js` | schedules · documents · jobs |
| `org.js` | organizations · departments · job-titles · org-tree · notion-mapping |
| `governance.js` | approvals · approval-delegations · audit · audit-anomalies · rbac · impersonation |
| `platform.js` | backup · restore-drills · announcements · ai-quotas · feature-flags |
| `notifications.js` | notifications |

ui_qa에 있는 것: 상세 드로어 3종(`integration-detail`, `runner-detail`, `job-detail`) 포함 대부분.
ui_qa에 **없는** registry 화면: 없음(키 기준). 단 **모달·드로어 내부는 `--modals`를 켜야만 들어간다.**

---

## 4-1. ⚠️ 이번 캡처의 데이터 한계 (다음 실행 전에 반드시 처리)

`qa-admin`에 **Notion 매핑이 없어** 티켓 계열 화면이 전부 "내 계정이 Notion 사용자와 연결되어 있지
않습니다" 빈 상태로 찍혔다 — `/my-tickets`·`/tickets/:id`·`/team-tickets`·`/unassigned` 및 홈·
스프린트·대시보드의 티켓 구역. **즉 티켓 화면의 '데이터 있는 상태'를 한 장도 못 찍었다.**

조치 둘 중 하나: (a) `qa-*` 계정에 Notion 사용자 연결을 붙인다(`#/notion-mapping`), 또는
(b) 매핑된 실계정으로 캡처를 한 번 더 돌린다. `scripts/ui_qa/README.md`가 이 제약을 이미
"커버리지를 지어내지 않는다"로 적어 뒀지만, **이번 실행 결과를 읽을 때 그 사실을 잊으면
"티켓 화면은 빈 상태가 정상"이라고 오판하게 된다.**

## 5. 상태 축 커버리지 (라우트와 직교)

| 상태 | 현황 |
|---|---|
| Empty | 미검증. 시드 데이터가 없어 재현 조건 자체를 안 만들었다 |
| Loading | 미검증 |
| Error | 미검증 |
| **Permission Denied** | 미검증. 단 이제 4역할 계정이 있어 **재현 가능해졌다** |
| 긴 텍스트 | 미검증 |
| 데이터 0건 | 미검증 |
| 데이터 대량 | 미검증(ticket_cache 1077행은 있으나 표별 대량 상태는 미확인) |
| 잘못된 입력 | 미검증 |

## 6. 역할 커버리지

| 역할 | 계정 | 상태 |
|---|---|---|
| system_admin | `hshwang@goodmit.co.kr`(실계정) | 서버 실계정 14개 중 유일 |
| admin | **`qa-admin@goodmit.co.kr`** | ✅ 생성·로그인 확인. `c1-admin` 캡처 272페이지를 이 계정으로 돌렸다 |
| operator | **`qa-operator@goodmit.co.kr`** | ✅ **68라우트 캡처 완료**(`c1-operator`). 권한 화면·사이드바 축소가 API 실측과 정확히 일치 |
| auditor | **`qa-auditor@goodmit.co.kr`** | ✅ 생성. 아직 실행 안 함 |
| user | **`qa-user@goodmit.co.kr`** | ✅ 생성. 아직 실행 안 함 |
| `admin_scope` dept/org/global | — | 전부 미검증. `SEC-01`·`UB-01`·`UA-02`가 여기서만 재현된다 |

> 비밀번호는 `dist/ui-qa-*/credentials.json`(gitignore). 실행 시 역할마다 `--out-dir`을 따로 줘야
> `storage_state`가 안 섞인다. 서버 실계정 14개 중 **12개가 `admin`, `operator`·`auditor`는 0명**이라
> 이 계정들 없이는 역할 매트릭스를 재현할 방법이 애초에 없었다.

## 6-1. RBAC 실측 매트릭스 (2026-08-08, 배포 서버, 4역할 실제 로그인)

`qa-user`/`qa-operator`/`qa-auditor`/`qa-admin`으로 실제 로그인해 GET 응답 코드를 측정한 것이다.

| 엔드포인트 | user | operator | auditor | admin | 판정 |
|---|---|---|---|---|---|
| `/api/assistant/weekly-digest` | **200** | **200** | 200 | 200 | 🔴 **게이트 없음** — `BACKLOG UA-01` |
| `/api/sprint/summary` | **200** | **200** | 200 | 200 | 🔴 **게이트 없음** — `BACKLOG UA-02` |
| `/api/admin/reports/dev-monthly` | 403 | 403 | 200 | 200 | ✅ `SENSITIVE_READ` |
| `/api/admin/users` | 403 | 403 | 403 | 200 | ✅ `CONSOLE_WRITE` |
| `/api/admin/audit` | 403 | 403 | 200 | 200 | ✅ `SENSITIVE_READ` |
| `/api/admin/settings` | 403 | 200 | 200 | 200 | ✅ `CONSOLE_READ` |
| `/api/admin/jobs` | 403 | 200 | **403** | 200 | ✅ `OPS`(auditor 제외 의도) |
| `/api/admin/impersonation/sessions` | 403 | **403** | 200 | 200 | ✅ `SENSITIVE_READ` |
| `/api/admin/backups`·`rbac-matrix`·`announcements`·`ai-quotas`·`feature-flags`·`integrations`·`schedules` | 403 | 200 | 200 | 200 | ✅ `CONSOLE_READ` |
| `/api/admin/mail/status` | 403 | 200 | 200 | 200 | ✅ `CONSOLE_READ` — **2026-08-11 갱신**: `FN-01`이 `MailStatus.jsx` 신설로 닫혀, 이제 부를 화면도 있다 |
| `/api/system/status` | 200 | 200 | 200 | 200 | 인증만 — 배너 알림용(의도) |

### 이 표가 드러낸 가장 중요한 것
**제품에 정책이 있는데 옆문이 그 정책을 무시한다.** `dev-monthly`는 같은 전사 집계를
`SENSITIVE_READ_ROLES`로 막아 **operator조차 403**인데, `weekly-digest`는 **아무 게이트가 없어
평범한 `user`에게도 같은 `team` 합계와 이름 붙은 상위 기여자를 준다.** 즉 이것은 "게이트를
깜빡했다"가 아니라 **명시적으로 정한 기밀 등급을 다른 경로가 무효화하는** 상태다.

나머지는 전부 설계대로다 — `auditor`가 `jobs`에서 빠지고 `impersonation/sessions`에 들어가는
비대칭까지 코드 의도와 일치한다. **RBAC 뼈대는 건강하고, 구멍은 위 두 개다.**

## 6-2. RBAC 실측 — 이번 사이클 신규 UI (2026-08-11, 로컬 dev 서버, 3역할 실제 로그인)

배포 Blocker와 무관하게 로컬 dev DB에 uvicorn을 띄우고 `user`/`operator`/`system_admin`
3역할로 실제 로그인해 화면에서 직접 확인했다(자동화 하네스가 아니라 수동 Chrome 조작).
대상은 이번 사이클(FN-03/05/06/09/11/14, SEC-04/05)이 새로 만든 UI 요소 중 role 게이트가
있는 것들이다.

| 화면 요소 | user | operator | system_admin | 판정 |
|---|---|---|---|---|
| 검색 화면 "지금 재색인" 버튼 (FN-03b) | 안 보임 | **보임** | 보임 | ✅ `OPS_ROLES` 게이트가 실제로 걸린다 |
| `/ai-quotas`(AI 사용 상한) 화면 자체 | 접근 불가(홈으로 리다이렉트) | 미확인 | 보임(요약 카드 2개 포함, FN-05) | ✅ `CONSOLE_READ` 게이트 |
| `/notifications` 화면 자체 | **보임**(소유권 기반이라 role 무관) | 미확인 | 보임 | ✅ 의도대로 role-free |

**직접 확인 못 함(정직하게 남김)**: FN-03a(팀 티켓 배너)·FN-03c(알림 삭제 버튼 표시)·
FN-14·FN-06·FN-09·SEC-05(위임 종료일)는 이 로컬 dev DB에 해당 상태 데이터가 없어(활성
위임 없음, 알림 없음, 프로젝트 없음, 실패한 백업 없음, 휴지통 항목 없음) 화면에서 직접
못 눌러봤다 — 프런트 vitest(일부 revert-to-verify)로만 검증됨. `operator`로 AI 상한/알림
화면은 이번 라운드에서 안 열어봄(시간 배분상 검색 재색인의 operator 케이스만 확인).

## 7. 주요 End-to-End 흐름

| 흐름 | 상태 | 비고 |
|---|---|---|
| 권한: 역할 변경 → 메뉴 → 데이터 범위 → 기능 실행 → API | - | 계정 없어 미착수 |
| 알림: 발생 → 벨 배지 → 목록 → 딥링크 → 목적 화면 + 나브 하이라이트 | - | |
| 티켓: 생성(리치 본문·첨부) → 목록/상세/팀/미할당 → 프로젝트 → 알림 → 감사 | - | |
| 문서: Notion 매핑 → 목록/검색/필터 → 생성 → 상세 → 휴지통 → 복구 | - | |
| **AI: 채팅 → 실제 Notion 티켓 생성** | - | **한 번도 실물 검증된 적 없다**(BACKLOG AI-50) |
| AI: 연속 대화·History·Context·오류·재시도·새로고침·페이지이동 | - | |
| 백업 → 복구 리허설 → 복원 | - | |
| 승인 → 위임 → 결재 → 알림 → 감사 | ~ | **2026-08-11 갱신**: `FN-11`(위임자에게 버튼 없음) 구현완료 — `can_decide` 서버 판정 + revert-to-verify 보안 테스트 2건. 위임→결재까지의 전체 흐름을 실 브라우저로 끝까지 밟아 보진 않음(로컬 dev DB에 활성 위임 데이터 없음) |
| 스케줄 → 실행 → 작업큐 → 감사 | - | FN-13(역추적 불가)과 직결 |

---

## 8. 재실행 명령

```bash
# 서버를 겨눈 전체 매트릭스 (SSH 터널 필요 — QA-03)
ssh -N -L 8081:127.0.0.1:8080 cloviradmin@10.100.64.71 &
.venv/Scripts/python.exe -m scripts.ui_qa.run --label cN --modals \
    --base-url http://127.0.0.1:8081 --fail-on all
# 결과: dist/ui-qa/cN/{results.json, report.html, light|dark/<viewport>/<route>.png}

.venv/Scripts/python.exe -m scripts.ui_qa.run --list      # 라우트 목록
bash scripts/final_verify.sh                              # 전체 게이트
```

---

## 9. 이번 구간에 드러난 **커버리지 개념 자체의 결함** (2026-08-08)

세 가지는 표의 숫자가 올라가도 실제 커버리지가 안 올라가는 구조적 문제다. 다음 사이클은
이것부터 고치고 다시 센다.

### 9-1. 라우트 커버리지 × 역할 커버리지 (`QA-12`)

`system_admin` 전용 4화면(`/system`·`/setup`·`/notion-console`·`/llm-console`)을 `qa-admin`
(role=admin)으로 찍었더니 **4장 모두 권한 거부 화면**이었는데 하네스는 `ok`로 집계했고, 21개
검사도 그 거부 배너 기준으로 전부 통과했다. **화면이 아니라 배너를 검사한 것이다.**
`results.json`의 `route_inventory`에 `min_role`/`allowed_roles`가 이미 있으므로, 실행 계정이
볼 수 없는 라우트는 `ok`가 아니라 **`권한부족(미검사)`**로 표시해야 한다.

→ 이번에 `hshwang@`(system_admin)로 다시 찍어 `dist/ui-qa-sysadmin/`에 실화면을 확보했다.
   **그 4화면에서만 새 결함 18건**(`SYS-01`~`11`, `VIS-110`~`116`)이 나왔다.

### 9-2. 검사가 도는 뷰포트 ≠ 사용자가 있는 뷰포트 (`QA-10`·`QA-13`)

`tiny_text`는 폭 ≥2200, `narrow_main`은 ≥3840에서만 돈다. 1920 캡처의 요약표는
`통과 0 / 실패 0 / 건너뜀 67`로 나오는데 **요약만 보면 "문제 없음"으로 읽힌다.** 3840으로
같은 페이지를 다시 돌리면 **6/6 실패**한다(앱 셸의 `Ctrl K` 11px, 클로비 카드 10px — 둘 다
하드코딩 px라 `--clv-root-fs` 스케일을 안 따른다). **skip 과 pass 를 요약에서 구분해야 한다.**

### 9-3. AI 기능은 화면 축(`S`)으로 검증되지 않는다 (`AI-30`)

`/chat` 은 70라우트 캡처에서 매번 정상으로 찍혔다. 그런데 **실제로 두 턴을 이어서 물어보니**
11일 전 중단된 티켓 생성 모드가 무관한 질문을 납치했다. 캡처 몇 장을 더 찍어도 영원히 안 나온다.

**규칙**: AI 도우미·채팅·검색처럼 **상태를 갖는 기능은 `S`가 아니라 `F`+`D` 축에서만
검증된 것으로 친다.** 도구는 `scripts/ui_qa/ai_e2e.py`·`ai_probe.py`·`ai_verify.py`.
대조 실험(같은 문장, 문맥만 다름)이 원인을 가르는 데 결정적이었다 — 이 패턴을 재사용한다.

### 9-4. 새로 추가하는 축 — `U` (실사용 이력)

화면은 **기능이 없는 것**과 **아무도 안 쓴 것**을 똑같이 그린다. 프로덕션 DB 행 수로만
갈린다. 실측 결과 **12개 기능이 실행 이력 0**이었다(`USE-01`, BACKLOG 의 USE 절 참조):
승인 · 문서 자동 생성 · 스케줄 실행 · 오프보딩 · 메일 · 복구 리허설 · 대리 보기 ·
AI 사용 상한 · 공지 배너 · 주간 리포트 · 저장된 뷰 · 휴지통.

| 축 | 기호 | 뜻 |
|---|---|---|
| 9 실사용 이력 | `U` | 실환경에서 **한 번이라도 실제로 실행돼** 데이터가 남았는가 |

**`U`가 `-`인 기능은 다른 축이 아무리 `O`여도 신뢰하지 않는다.** 테스트와 화면은 있는데
실환경에서 한 번도 돌지 않은 코드이기 때문이다. 다음 사이클의 가장 큰 작업은
**이 12개를 실환경에서 한 번씩 끝까지 돌려 보는 것**이고, 그 자체가 발견 원천이 된다.

### 9-5. 하네스가 권한 거부를 "데이터 없음"으로 오보고 (`QA-11`)

`c1-auditor` 실행 메모: `admin_job-detail 건너뜀 — 표시할 데이터가 없어…(/api/admin/jobs)`.
실제로는 `auditor`가 `CONSOLE_OPS_ROLES`에 없어 **403**이다. 역할 매트릭스 실행에서 이 오분류는
**"이 역할이 못 본다"와 "기능에 행이 없다"를 구분 불가능하게 만든다** — 역할 조사에서 가장
알고 싶은 차이가 바로 그것이다.

### 9-6. 스크린샷으로 판정하면 안 되는 것 — `position: fixed` (2026-08-08)

`full_page=True` 스크린샷은 **`position: fixed` 요소를 뷰포트 좌표대로 캔버스에 한 번만 그린다.**
6,000px 짜리 페이지를 찍으면 떠 있는 마스코트가 캔버스 어딘가 한 곳에 찍히고, 그 자리에 우연히
있던 표 행의 버튼과 겹쳐 보인다. **사용자는 그 화면을 그렇게 보지 않는다.**

이 착시로 「클로비가 ~를 가린다」 계열 **7건을 잘못 기록했다가 전부 철회**했다(BACKLOG 정정 절).
살아 있는 DOM 으로 재니 60라우트 중 1건, 긴 표 8종 × 스크롤 4위치에서 **0건**이었다.

**하네스의 `fab_overlap` 검사는 내내 옳았다** — DOM 좌표를 재기 때문이다. 정확한 검사가 통과한
것을 PNG 를 근거로 반박했고, 틀린 쪽은 나였다.

**규칙**:
- 겹침·가림·클릭 가능성은 **살아 있는 DOM 좌표**로만 판정한다(`elementsFromPoint`).
  도구: `scripts/ui_qa/fab_occlusion.py`.
- PNG 로 판정해도 되는 것: 정보 밀도 · 여백 · 정렬 · 위계 · 색 · 빈 상태 · 문구 · 열 구성.
- PNG 로 판정하면 안 되는 것: `fixed`/`sticky` 겹침 · 스크롤 동작 · 호버·포커스 상태 ·
  실제 클릭 도달성.

---

## 10. 역할별 **정직한** 라우트 분모 (하네스 수정 후, 2026-08-08)

`Route.visible_to(role)` 로 계산한 값이다. **"70라우트 캡처 완료"는 `system_admin` 에서만 참이다.**

| 역할 | 도달 가능 | 권한부족(미검사) | 실제 캡처 |
|---|---|---|---|
| `user` | **27** | 43 | ✅ **25/27** (`dist/ui-qa-user2/c2-user`) — 나머지 2는 데이터 없음 |
| `operator` | 55 | 15 | 미실행 |
| `auditor` | 57 | 13 | `c1-auditor` 는 **수정 전** 실행이라 재실행 필요 |
| `admin` | 66 | 4 | `c1-admin` 은 **수정 전** 실행 — 4개가 거부 배너로 찍히고 `ok` 로 집계됐다 |
| `system_admin` | **70** | 0 | 4화면만 `c1-sysadmin` 으로 촬영 |

### `user` 실행 결과 — RBAC UI 는 **정확하다** (실측)

25페이지 전부에서:
- **권한 거부 화면 0건** — `visible_to` 가 허용한 라우트는 전부 실제 내용을 그렸다.
  즉 `routes.py` 의 `min_role`/`allowed_roles` 표가 **앱의 실제 게이팅과 일치한다.**
- **4xx/5xx 0건 · 콘솔 오류 0건 · 페이지 오류 0건.**
- 상세 2건은 새 문구로 정확히 구분됐다 — `user_chat-room-detail`·`user_game-room` →
  **"200, 항목 0건"**(권한 문제 아님). `qa-user` 는 채팅방이 없고 게임방은 전부 닫혔다
  (`GM-01`) — **사실과 일치**.

### 수정 전 실행은 어떻게 다루는가

`c1-admin`(272페이지)·`c1-auditor`(67페이지)는 **`QA-12` 수정 전**이라 요약의 `ok` 수를
그대로 믿으면 안 된다. **PNG 자체는 유효하므로 판독 자료로는 계속 쓴다** — 다만
`admin_system`·`admin_setup`·`admin_notion-console`·`admin_llm-console` 4장은
**권한 거부 배너**이고, 실화면은 `dist/ui-qa-sysadmin/c1-sysadmin/` 에 있다.

### 10-1. 4역할 실행 완료 (수정된 하네스, 2026-08-08) — **RBAC UI 는 정확하다**

| 역할 | 도달 가능 | 실제 캡처 | 권한부족(미검사) | 거부 화면 | 4xx/5xx | 실패 검사 |
|---|---|---|---|---|---|---|
| `user` | 27 | **25** | 43 | **0** | 0 | 없음 |
| `operator` | 55 | **53** | 15 | **0** | 0 | 없음 |
| `auditor` | 57 | **55** | 13 | **0** | 0 | 없음 |
| `admin` | 66 | **64** | 4 | **0** | 0 | 없음 |
| `system_admin` | 70 | 4(전용 화면만) | 0 | 0 | 0 | 없음 |

각 역할에서 **캡처 = 도달 가능 − 2** 인데, 그 2는 항상 `user_chat-room-detail`·`user_game-room`
이고 사유가 **"200, 항목 0건"**(권한 아님)으로 정확히 구분돼 있다. 실제로 그 계정들은
채팅방이 없고 게임방은 전부 닫혀 있다(`GM-01`) — **사실과 일치**.

**결론 두 가지**

1. **`routes.py` 의 `min_role`/`allowed_roles` 표가 앱의 실제 게이팅과 정확히 일치한다.**
   4역할 197페이지에서 **권한 거부 화면 0건** — 보인다고 판정한 라우트는 전부 실제 내용을
   그렸고, 못 본다고 판정한 라우트는 전부 실제로 막혀 있다.
2. **프런트 RBAC 는 4역할에서 결함이 없다.** 4xx/5xx 0건, 콘솔·페이지 오류 0건,
   자동 검사 실패 0건. (서버측 권한 결함 `SEC-01`·`UA-01`·`UA-02`·`UA-11` 은 **API 계층**
   문제이지 화면 게이팅 문제가 아니다 — 둘을 섞지 않는다.)

→ `R`(RBAC) 축을 **`~` 에서 `O`(화면 게이팅 한정)** 로 올린다. `A`(API 권한)는 별개로 남는다.

### 10-2. `V`(반응형) 실측 — **1024 가 최악이다** (2026-08-08)

밀도 높은 5화면 × 4폭(1366/1200/1024/768) = 20페이지.

| 폭 | `vertical_text_collapse` | `horizontal_overflow` | 판정 |
|---|---|---|---|
| 1366 | 0 | 0 | ✅ |
| 1200 | 1 (`/users` 셀 1개) | 0 | ⚠️ 경계 |
| **1024** | **16** (`/users`) | **3** (`/users` 표가 뷰포트 밖으로) | ❌ **사용 불가** |
| 768 | 5 (전부 상단바 「클로비」 라벨, 앱 셸) | 0 | ✅ 표는 **카드로 잘 전환됨** |

원인은 `kit.jsx:415` 의 전역 상수 `(max-width:899.95px)` 하나 — 900px 미만에서만 카드로
바뀐다. **1024 는 표를 유지하는데 본문 폭이 ~796px 뿐이다**(`RESP-01`·`RESP-02`).

**규칙**: 반응형 실행은 앞으로 **768 / 1024 / 1200 / 1366** 을 함께 돌린다. 기존 목록이
768 → 1366 으로 건너뛰어 **가장 심한 구간을 한 번도 보지 않았다**([D-34](DECISIONS.md)).

### 10-3. 새 축 `K` — 텍스트 대비(WCAG) (2026-08-08)

| 축 | 기호 | 뜻 |
|---|---|---|
| 10 텍스트 대비 | `K` | 실제 렌더된 전경/배경 색으로 WCAG AA(보통 4.5:1 · 큰 글자 3:1)를 만족하는가 |

`theme_applied`(다크 클래스가 붙었는가)는 **읽히는가**를 전혀 보지 않는다. 도구:
`scripts/ui_qa/contrast.py`. 8화면 × 2테마 실측 결과 — **라이트 6/8 무결점, 다크 8/8 위반**
(`CTR-01`~`05`).

**이 도구를 쓸 때 지켜야 할 것**: 배경이 **그라디언트**면 `backgroundColor` 로는 알 수 없다.
그냥 지나치면 상단바 흰 글씨가 흰 body 위로 계산돼 **1.07:1 위양성**이 쏟아진다(첫 판에 실제로
그랬다). 지금은 **판정을 포기하고 그 개수를 함께 보고**한다(화면당 34~50개). 따라서
보고되는 위반 수는 **하한선**이며, 상단바·그라디언트 영역은 **아직 미검증**이다.

### 10-4. 상태 축 실측 — Error / Loading (2026-08-08)

`§5 상태 축 커버리지` 에서 `Empty` 와 `Permission Denied` 만 채워져 있었다. 나머지를 **주입해서** 쟀다
(`scripts/ui_qa/failure_states.py`, 8화면 × 4모드).

| 상태 | 결과 |
|---|---|
| `Error(500)` | 8중 6이 실패를 말함, 4개는 「다시 시도」 제공 |
| `Error(네트워크 끊김)` | 500 과 동일 |
| **`Error(200+비JSON)`** | **8중 5 침묵 · 8중 8 재시도 없음 · 콘솔 오류 0건** ← 가장 나쁨 |
| `Loading` | `/team-docs` 는 **끝나지 않는 로딩**(스켈레톤 6 + 「불러오는 중…」) |

**가장 무거운 것**: 실패를 **「~가 없습니다」** 로 바꿔 말한다(`FAIL-01`) — `/my-tickets`·
`/projects`·`/chat`·`/users`. **빈 상태와 오류 상태를 분리해야 한다**([D-37](DECISIONS.md)).

**정정**: 기존 기록의 강점 "콘솔 오류 0건"은 **정상 경로에 한한 사실**이다. 실패 경로에서는
화면당 최대 5건(`FAIL-05`).

### 10-5. 상태 축 실측 — 긴 데이터 / 많은 데이터 / 이상한 문자 (2026-08-08)

`scripts/ui_qa/hostile_data.py` 로 응답을 갈아 끼워 4화면 × 3모드.

| 모드 | 결과 |
|---|---|
| `long` 긴 한글 + 줄바꿈 없는 긴 URL | ❌ **문서 폭이 뷰포트의 2~3.3배**(`/projects` 5,271/1600), 셀 **51×2,353px** |
| `many` 200행 | ✅ **완전 무결점** — 넘침 0 · 붕괴 0 · 3초 · JS 오류 0 |
| `weird` RTL·이모지·결합문자·제로폭·`<script>` | ⚠️ 셀 51×442px 붕괴 · **XSS 없음**(문자열로 렌더, JS 예외 0) |

**근본 원인은 `RESP-01` 과 같다** — 표에 열 폭 제약이 없다. 두 트리거 모두 셀 폭이
**51px** 로 측정됐다([D-40](DECISIONS.md)). 고칠 곳은 `DataTable` 한 곳이다.

### 10-6. 새 축 `B` — 키보드·포커스 (2026-08-08)

| 축 | 기호 | 뜻 |
|---|---|---|
| 11 키보드·포커스 | `B` | 탭으로 도달 가능한가 · **지금 어디인지 보이는가** · 순서가 시각 순서와 맞는가 |

도구: `scripts/ui_qa/keyboard.py`. 4화면 × 45탭 실측 —
**정지점 45개 중 38~45개가 `outline: 0px` + `boxShadow: none`**(`:focus-visible` 은 매칭됨).
유일한 표시인 12% 배경 틴트는 합성 후 대비 **1.05(라이트) / 1.45(다크)** = 기준 3:1 의 1/3.

**이 도구를 쓸 때**: 알파 틴트는 **배경 위에 합성한 뒤** 재야 한다([D-42](DECISIONS.md)).
그리고 "표시 없음" 을 보고하기 전에 `:focus-visible` 매칭 여부와 실제 `outlineWidth` 를
요소별로 덤프해 **위양성이 아님을 확인**한다(이번에 확인했다).

### 10-7. 새 축 `S2` — 접근성 시맨틱 (2026-08-08) — **강점**

| 축 | 기호 | 뜻 |
|---|---|---|
| 12 접근성 시맨틱 | `S2` | 제목 계층 · 랜드마크 · 버튼·입력 접근명 · `th[scope]` · `alt` |

도구: `scripts/ui_qa/semantics.py`. 8화면 실측 — `h1` **8/8** · 랜드마크 **8/8** ·
**이름 없는 버튼 0건(최대 125개 중)** · `alt` 없음 **0건** · `th[scope]` **100%**(10/10·7/7·7/7) ·
콤보박스 `aria-labelledby` **5/5**. → 이 축은 `O` 로 올린다.

실결함 2건만: `SEM-01`(「상세 보기」 100개 동명) · `SEM-02`(`/me` h1→h3).

**이 도구를 쓸 때**: `opacity:0` 요소를 걸러라. MUI 는 Select 마다 숨은
`MuiSelect-nativeInput` 을 만들고, 그것을 세면 **라벨 없는 입력 14건이 위양성으로 나온다**
(첫 실행에서 실제로 그랬다, [D-44](DECISIONS.md)).

---

## 11. 축 최종 상태 (인계 시점, 2026-08-09)

| 축 | 기호 | 상태 | 근거 |
|---|---|---|---|
| Chrome 화면 | `S` | **O** | 66/70 판독(내 26 + 워크플로 40) + 4K 128페이지 + 다크 |
| 실제 기능 실행 | `F` | **~** | 승인·복구 리허설·저장된 뷰·오프보딩·공지 배너·AI 쿼터·AI 대화·중첩 모달·**휴지통(문서 trash→list→restore, 2026-08-12)** 실행. 문서 생성·스케줄은 D-21/DGEN-02로 보류 |
| API | `A` | **O** | 4역할 197페이지 + 지연 실측 + 실패 주입 |
| DB·데이터 흐름 | `D` | **O** | 프로덕션 74표 집계 · 승인/리허설/저장된뷰 왕복 확인 |
| Console·Network | `C` | **O** | 정상 경로 0건 확인 + **실패 경로에서 화면당 최대 5건**(`FAIL-05`) |
| RBAC | `R` | **O**(화면 게이팅) | 4역할 197페이지, 거부 화면 0 · 역할 표가 앱과 일치 |
| 화면 간 반영 | `L` | **~** | 복구 리허설 3단계 확인 + `WF2` 무효화 8건 조사 + `WF7-L01`(승인→users/integrations/runners/schedules/documents 5화면 무효화, 2026-08-11) + `WF11-L01`(문서·게시판 편집→home 「최근 문서/글」 위젯 무효화, `document-views.js` 신설, 2026-08-12) + WF44(2026-08-13, 아래 "남은 큰 공백 3개"의 3번 항목) — Board/Ideas 댓글·반응·상태변경 3계열 + `board-mine` 최초 배선, Projects→Dashboard(`invalidateProject()`+home), Users/부서/직책/조직→티켓 담당자 후보(`crossScreenKeys.js`) 구현완료(`CACHE-01`/`02`/`03` 전부). Settings/Feature-flags/Announcements/Offboarding은 무결함 재확인. 전수는 아직 아님 — 남은 표본 8+3건을 넘는 전체 화면 쌍 점검만 남음 |
| 반응형·Theme | `V` | **O** | 768/1024/1200/1366/1920/3840 × 라이트·다크 |
| **실사용 이력** | `U` | **~** | 12기능 중 9 확인(전부 정상 — 저장된 뷰·대리 보기·복구 리허설·승인·메일·오프보딩·공지 배너·AI 쿼터·**휴지통**[2026-08-12, 합성 문서로 안전하게 왕복]). 남은 3기능(문서 생성·스케줄·주간 리포트)은 D-21/DGEN-02로 실행 보류(원인 규명됨) — `U`축은 이 셋을 빼면 사실상 완료 |
| **텍스트 대비** | `K` | **O** | 8화면(자동, 비-그라디언트 34~50요소/화면) + 상단바 그라디언트 전체(수동 실측, WF7-K01) |
| **키보드·포커스** | `B` | **O** | 4화면 × 45탭 + 합성 대비 계산 |
| **접근성 시맨틱** | `S2` | **O** | 8화면. **강점** — 이름 없는 버튼 0/125 · `th[scope]` 100% |

**남은 큰 공백 3개**
1. `U` — 2026-08-11 WF7 후속으로 오프보딩·공지 배너·AI 쿼터 3종, **2026-08-12에 휴지통**을
   로컬 dev 서버에서 실행 완료(전부 정상, `docs/BACKLOG.md` §OFFB·ANN·QUOTA + "휴지통 왕복
   실행 완료" — 휴지통은 새 문서 생성[Notion 쓰기]도 기존 실문서를 건드리는 것도 아니라
   합성 문서 1건으로 안전하게 왕복시켰다). 남은 것은 여전히 의도적 보류 둘뿐이다 —
   문서 생성(`DGEN-02`, 이 설치에 적합한 워크플로 자체가 없다) · 스케줄·주간 리포트
   (D-21, 실고객 Notion 워크스페이스 보호).
2. `K` — ~~그라디언트 배경 위 텍스트(상단바 전체)는 아직 아무도 재지 못했다~~ → WF7-K01(2026-08-11)에서 직접 계산으로 종결.
   `UserMenu`(계정 이름)가 78% 부근 최악 지점에서 AA 미달이던 것을 배경 없이 방치하고 있어 실결함으로 확인·수정함.
   같은 상단바의 `NotificationBell`(배지 자체 불투명 배경)·`TopBrand`(텍스트 아닌 SVG)·`TopSearch`(자체 반투명
   오버레이 + 실제 위치가 위험 구간 밖)는 점검 결과 결함 아님. 사이드바 그라디언트는 이전에 이미 측정·통과
   (`styles/tokens.css` sidebar-text/sidebar-muted 주석). 남은 그라디언트 표면(로그인 화면 등)이 있다면 이후 라운드에서.
3. `L` — 전수 무효화 매트릭스는 없다(`WF2` 가 8건을 표본으로 봤을 뿐). 2026-08-12에 `WF11-L01`
   (문서·게시판 → home 위젯)을 추가로 닫았다. 같은 날 이어서 팀 채팅(`team-chat-rooms`)·
   게임방을 조사했으나 **결함이 아니었다** — 사이드바 배지·홈 위젯 둘 다 명시적 무효화 대신
   같은 queryKey를 여러 화면이 함께 구독하는 폴링(react-query의 "옵저버 중 가장 짧은 간격"
   특성, `AppShell.jsx::useNavBadges` 주석에 그 설계 의도가 이미 적혀 있다) + `VIS-160`(같은
   배치에서 `Home.jsx`에 `refetchInterval` 추가)으로 이미 30~60초 안에 스스로 새로고침된다 —
   무효화가 "빠진" 게 아니라 애초에 그 방식을 안 쓰기로 한 설계다. 같은 날 이어서 알림
   3원(벨·팝오버·전체 화면)도 확인 — **이미 완전히 통합돼 있었다**: `notification-keys.js`
   가 `unread`/`list`/`screen` 전부 `["noti", ...]` 한 뿌리로 두고 `invalidateNotifications()`
   하나로 셋 다 갱신하며, `notification-keys.test.js`(4건, 그중 하나는 "네 번째 네임스페이스가
   생기지 않는다"는 정적 회귀 가드)가 이미 이 계약을 고정해 뒀다 — 재확인만 하고 코드 변경
   없음. **2026-08-13(WF44 배경 조사)**: 남은 bespoke 화면(Board/Ideas·Projects·Users·
   Settings류·Offboarding)을 배경 Explore 에이전트로 마저 훑어 진짜 공백 2건을 확정했다 —
   - **Board/Ideas(진짜 공백)**: 게시글 CRUD·핀·삭제는 `["board"]`+`["home"]`을 정상
     무효화하지만, `BoardPost.jsx`의 댓글 작성/수정/삭제(`CommentComposer`·`CommentItem`)와
     `Board.jsx`의 반응 토글(`Reactions`)·아이디어 상태 변경(`IdeaStatusBar`) 셋은
     `invalidateQueries` 없이 상세 화면 자체의 로컬 refetch만 한다 — 목록의 `comment_count`/
     `idea_status`/`like_count`(아이디어 보드 기본 정렬 기준) 열과 `Home.jsx` "최근 글"
     위젯의 댓글 수가 반영 안 된다. 별도로 `Home.jsx`의 `MyBoardStats`(`["board-mine"]`,
     "받은 댓글" 등)는 게시글 생성/수정/핀/삭제를 포함해 **어떤 mutation도 무효화하지
     않는** 더 넓은 공백.
   - **Projects → Dashboard(진짜 공백)**: `project-queries.js::invalidateProject()`(모든
     프로젝트/마일스톤 쓰기 훅이 공유)가 `["projects",...]`만 무효화하고 `["home"]`을 안
     건드려, `Dashboard.jsx`의 `WorkSection`(`["home","work-dashboard"]`, `staleTime:
     60000`)이 그리는 "차질 프로젝트"/"지연 마일스톤"이 최대 60초+(탭을 안 벗어나면
     그 이상) stale해진다. 반대 방향(`ticket-views.js`의 `TICKET_VIEW_KEYS`가 이미
     `"projects"`를 포함해 티켓 변경은 프로젝트 캐시에 닿음)은 이미 돼 있어 이 한
     방향만 빠졌다.
   - **Users → 티켓 담당자 후보(사소한 공백)**: 부서/직책/조직 개명은 이미 `Users.jsx::
     refresh()`로 무효화되지만 `["tickets"]`는 빠져 있어, `ticket-options.js::
     useAssigneeOptions`(`["tickets","assignees"]`, `staleTime: 60000`)가 다른 탭에
     열린 티켓 생성/수정 모달에서 최대 60초간 옛 이름을 보여줄 수 있다 — 영향이 좁아
     (감사 로그·티켓 상세 자체는 서버 조인이라 매 요청 최신) 우선순위 낮음.
   - **무결함 재확인**: Settings/Feature-flags/Announcements 소비처는 전부 리터럴
     `["settings"]` 한 키를 공유해 저장 시 함께 갱신되고(Feature-flags는 애초에
     클라이언트 캐시가 없다), Offboarding은 실행·취소 둘 다 `invalidateTicketViews(qc,
     {refetchType:"all"})`로 이미 광범위하게 무효화한다.
   **같은 날(WF44) 구현완료(3건 전부)**: Board/Ideas — 댓글 작성/삭제(`comment_count`
   변화)에 `["board"]`+`["home"]`+`["board-mine"]`, 반응 토글에 `["board"]`(`like_count`),
   상태 변경에 `["board"]`(`idea_status`) 추가. 댓글 수정은 집계가 안 바뀌어 의도적으로
   그대로 둠. `["board-mine"]`은 게시글 작성·삭제(`post_count`)에도 추가 — 이 키는 이제
   처음으로 무효화되는 mutation을 갖는다. Projects → Dashboard — `invalidateProject()`에
   `["home"]` 한 줄. Users/부서/직책/조직 → 티켓 담당자 후보 — `crossScreenKeys.js`의
   `departments`/`organizations`에 `["tickets"]` 추가, `job-titles`는 항목 자체가 없어
   신설(`app/tickets/service.py::list_assignees`가 담당자 후보에 부서·직책·조직을 함께
   싣는다, 사용자 지시 2026-08-04). `BACKLOG.md`의 `CACHE-01`/`02`/`03` 참고, 신규 시험
   10건, 프런트 전체 회귀(241파일/1597건) green. 다음 후보는 전수 매트릭스 자체(표본을
   넘는 화면 쌍 전체 점검) 하나만 남았다.

---

## 12. QAH 하네스 1회차 — 68라우트 전수 자동 검사 (2026-08-11, 로컬 dev 서버)

`scripts/ui_qa/run.py` 전체 실행: **68라우트 × 라이트/다크 × 3뷰포트(1366×768 포함, 4K는
`tiny_text`만) = 408페이지**, 21+1개 기계 검사 축 전부. §11의 `S`/`F`/`A`/`D`/`L`/`U`(사람이
직접 보고 조작하는 축)는 이 실행이 갱신하지 않는다 — 이 실행이 갱신하는 것은 `C`(console_errors)와
`V`(반응형·테마: `vertical_text_collapse`·`tiny_text`·`contrast`) 뿐이다. §11의 `V: O`,
`K: ~`는 **8~9화면 표본** 기준이었다 — 이번은 **68/68 라우트 전수**라 표본을 대체한다.

| 검사 | 결과 | 상태 |
|---|---|---|
| `console_errors` | 408페이지 중 2건(1페이지, `admin_offboarding` 다크 1366×768)만 fail | ✅ [QAH-01](BACKLOG.md)로 원인 확정(세션 부수효과 커밋의 SQLite 쓰기충돌) + 수정 완료 |
| `vertical_text_collapse` | 408페이지 중 2건(admin_dashboard 라이트·다크) | ✅ [QAH-02](BACKLOG.md) 수정 완료 |
| `contrast`(WCAG AA) | 408페이지 중 343개(**68/68 라우트**)가 최소 1건 fail. 표본 519건 | 🟡 [QAH-03](BACKLOG.md) 부분 완료 — 표본 90%(466/519)를 차지하는 두 지배적 패턴(`a.MuiButtonBase-root`·`span.MuiBox-root`)은 공유 theme 수준에서 수정. 나머지 소수 패턴(53/519)도 수정 완료, `button.password-toggle`(로그인 화면, 6건)은 승인된 디자인 베이스라인 고정 계약으로 의도적 보류. **2026-08-13 정정 — 이 표본(라우트당 5건 상한, 408페이지)이 놓친 진짜 공백이 하나 더 있다**: [QAH-05](BACKLOG.md)(Low, 미착수) — 같은 raw `primary.main` 직접 사용 패턴이 `Board.jsx`·게임방 5개 파일(`GameStage`·`LadderBoard`·`MembersList`·`Scoreboard`·`StageShared`) 총 7곳에 더 있다. 게임방은 하네스 라우트 목록에 없고(라운드가 비어 있으면 캡처가 그 UI를 못 찍는다, `GM-01`) 실측 대비값도 아직 없다 |
| `tiny_text`(3840×2160) | 사용자 콘솔 66/66 화면 fail(같은 원인 1개, `Mascot.jsx` 사이드바 힌트) | ✅ [QAH-04](BACKLOG.md) 수정 완료 |
| 나머지 17+1개 축 | 전부 통과(0 fail) | 재확인 불필요 |

**아직 이 실행이 못 채운 것**: 위 표는 **자동 검사가 잡을 수 있는 것만**이다. 이번 실행은 §11의
`U`(실사용 이력)·`K`(그라디언트 대비, 자동 검사가 판정 불가한 34~50요소/화면)·`L`(화면 간 반영
전수)의 공백을 메우지 않는다 — 그 셋은 여전히 사람이 봐야 한다.

**재실행 명령**: `.venv/Scripts/python -m scripts.ui_qa.run`(로컬 dev, `/readyz` 200 필요) —
결과는 `dist/ui-qa/session<날짜>/{results.json, report.html}`.

---

## 13. Product Audit Cycle `PA-20260812` 이 드러낸 **축 자체의 공백** (2026-08-15)

전수 Product Audit(`docs/product-audit/`)이 찾은 Root Cause 8건 중 **8건 전부**가
"기존 QA 축 어디에도 이것을 보는 칸이 없다"는 공통 사유를 갖고 있었다.
즉 이 결함들은 QA를 **통과한** 것이 아니라 **QA의 시야 밖에 있었다.**
아래 9개 칸이 기존 §11 축 표에 없던 것이다.

| 새 축 | 무엇을 보는가 | 왜 필요한가 (어떤 결함이 이 공백으로 들어왔나) | 상태 |
|---|---|---|---|
| `T1` 타이포 토큰 소비 | 선언된 글자 크기/굵기/radius 토큰이 **실제로 소비되는가**(리터럴 잔존 수) | `S`(화면)·`K`(대비) 축은 "보기에 이상한가"만 본다. 스케일이 1px 연속체로 번져도 스크린샷은 통과한다 — 그래서 `fontSize` 리터럴 31종·278회가 **VIS 162건을 거치고도** 안 잡혔다(`PA-RC-0001`) | **미검증** |
| `T2` 오류 문구 3요소 | 실패 문구가 `[무엇이 실패]·[왜]·[무엇을 하라]`를 주는가 | 화면별 시각·기능 축은 있으나 **문구 축이 없다.** 실패 문구 167건 중 회복 경로를 주는 것이 24건(14%)인 상태로 전 화면이 QA를 통과했다(`PA-RC-0002`) | **미검증** |
| `T3` 용어 표준 준수 | 같은 개념에 같은 동사·같은 종결 규칙을 쓰는가 | 같은 문장이 마침표 유무로 **동시 존재**하는데 이를 보는 칸이 없었다(`PA-RC-0002`) | **미검증** |
| `T4` 저장소 위생 | **stash · reflog · dangling 객체**에 자격증명·비밀이 없는가 | 기존 보안 검사는 **워킹트리와 커밋만** 본다. 평문 자격증명이 `stash@{0}` 안에 있는데 어떤 스캔도 그것을 못 봤다 — 이번 건이 정확히 그 사각지대로 들어왔다(`PA-RC-0003`) | **미검증** |
| `T5` 입력 경계값 | 상한·하한·빈 값·**붙여넣기 초과** 입력을 화면이 막는가 | 화면별 기능 검증은 있으나 경계 입력을 보는 칸이 없어서, 공용 폼 경로를 쓰는 **관리자 화면 28개 전부**가 프런트 길이 제한 0건인 채로 통과했다(`PA-RC-0005`). 기존 `H`(Negative/Edge)와 함께 볼 것 | **부분 검증** — 상한(maxLength) 축은 등록 화면 6/13곳(`prompts`·`policies`·`templates`·`departments`·`job-titles`·`organizations`)에서 실제 배선 확인(FormField 렌더 + 붙여넣기 초과 토스트, revert-to-verify). 나머지 화면은 `app/core/field_limits.py::FORM_SCHEMAS` 매핑만 추가하면 자동 적용(코드 확장은 이미 끝남). 하한·빈 값 축은 아직 별도 검증 없음 |
| `T6` 배포 revision 일치 | **검증 대상과 배포본이 같은 코드인가** | 이 축이 없어서 TEST 서버의 **5일·131커밋 드리프트**가 어떤 QA도 통과하지 않고 존재했다. 이 축이 비면 그 위에서 얻은 모든 E2E 결과의 의미가 사라진다 — 다른 모든 축의 **전제조건**이다(`PA-RC-0007`) | **미검증 — 현재 불일치 확인됨** |
| `T7` 동시성 반복 실행 | race 계열 테스트를 **N회 반복**해 통과하는가 | race 테스트는 1회 실행이 무의미한데(이번 결함도 60%는 통과했다) 현재 QA는 1회만 본다. 그래서 재시도 예산 결함이 오래 안 보였다(`PA-RC-0008`) | **검증완료** — race 계열 6개 파일(prompt/policy 새 버전, 승인 생성, notion 매핑 get-or-create, 쿼터 TOCTOU, 휴지통 이동, 헬스 스냅샷)을 20회 연속 반복 실행해 실패 0건 확인. `PA-RC-0009`가 이 절차를 `scripts/run_full_regression.sh`로 스크립트화함 |
| `T8` 스위트 건강 | Full Regression **완주 여부·소요 시간·비결정 테스트 목록** | 결과(green/red)만 보고 스위트 자체의 건강을 안 봤다. 그래서 *"45분 걸린다"* 가 *"행(hang)이다"* 로 **세 사이클 동안** 잘못 기록됐고 아무도 전체 회귀를 돌리지 않았다(`PA-RC-0009`) | **부분** — Audit이 4청크 전경 실행으로 2,903건 전부 `EXIT=0` 확인(5회). 절차 문서화·flaky 제거는 남음 |
| `T9` 서버 렌더 페이지 × 테마 | SPA **밖** 페이지(로그인·비밀번호 재설정)가 라이트/다크를 따르는가 | 기존 화면 축이 **React 라우트 중심**이라 SPA 밖 페이지가 통째로 빠져 있다. 그래서 "로그인 화면은 다크가 아예 안 켜진다"가 그대로 통과했다(`PA-RC-0010`) | **검증완료** — 4화면 Playwright 실측(`DECISIONS.md` D-74): `forgot-password`/`reset-password`는 다크 미지원이었으나 `tokens.css`의 `@media (prefers-color-scheme: dark)` 추가로 해결. `change-password`는 이미 `theme.js`로 지원 중이었음(grep만으로는 안 보였음). `login`은 `login.css`가 의도적으로 라이트 고정(히어로 설계 전제, `test_theme_on_all_authed_pages.py`로 고정) — 대상 아님, 그대로 유지 |

### 이 표가 드러낸 것

기존 축 12개(`S`·`F`·`A`·`D`·`C`·`R`·`L`·`V`·`U`·`K`·`B`·`S2`)는 전부
**"화면·요청·역할"** 이라는 런타임 관찰 축이다. 반면 위 9개 중 6개(`T1`·`T2`·`T3`·`T4`·`T7`·`T8`)는
**소스·저장소·테스트 스위트 자체를 보는 축**이다. 즉 이 QA 모델에는
*"실행해서 보이는 것"* 축만 있고 *"코드·저장소가 스스로 지켜야 하는 규약"* 축이 없었다.

`T6`(배포 revision 일치)은 성격이 또 다르다 — **다른 모든 축의 전제조건**이다.
이것이 어긋나 있으면 나머지 11개 축의 `O` 표시가 전부 "낡은 빌드에 대한 O"가 된다.
`CLAUDE.md` §10의 Chrome Whole-product E2E를 돌리기 **전에** 이 축부터 닫아야 한다.

**재실행 근거**: 각 축의 측정 방법과 현재 수치는 `docs/product-audit/PRODUCT_AUDIT_HANDOFF.md`
의 해당 `PA-RC-*` 블록 `acceptance_criteria`/`required_tests` 필드에 있고,
스캐너는 `var/product-audit/scan_*.py`·`probe_*.py`로 보존돼 있다(그대로 재실행 가능).
