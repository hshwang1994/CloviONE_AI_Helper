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

**마지막 갱신**: 2026-08-08 (사이클 0)

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
| `/forgot-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함. **FN-01(메일 UI 없음)과 직결** |
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
| `/api/admin/mail/status` | 403 | 200 | 200 | 200 | ⚠️ 권한은 맞으나 **부를 화면이 0개**(`FN-01`) |
| `/api/system/status` | 200 | 200 | 200 | 200 | 인증만 — 배너 알림용(의도) |

### 이 표가 드러낸 가장 중요한 것
**제품에 정책이 있는데 옆문이 그 정책을 무시한다.** `dev-monthly`는 같은 전사 집계를
`SENSITIVE_READ_ROLES`로 막아 **operator조차 403**인데, `weekly-digest`는 **아무 게이트가 없어
평범한 `user`에게도 같은 `team` 합계와 이름 붙은 상위 기여자를 준다.** 즉 이것은 "게이트를
깜빡했다"가 아니라 **명시적으로 정한 기밀 등급을 다른 경로가 무효화하는** 상태다.

나머지는 전부 설계대로다 — `auditor`가 `jobs`에서 빠지고 `impersonation/sessions`에 들어가는
비대칭까지 코드 의도와 일치한다. **RBAC 뼈대는 건강하고, 구멍은 위 두 개다.**

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
| 승인 → 위임 → 결재 → 알림 → 감사 | - | FN-11(위임자에게 버튼 없음)과 직결 |
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
