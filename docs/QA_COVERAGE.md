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

**마지막 갱신**: 2026-08-15 — **§15 신설 + §0~§4 라우트별 `C`/`S`(판독)/`V` 갱신**: 같은 날
§14(T6 배포 확인 직후 690페이지 E2E) 이후에 돈 4회 추가 E2E(`converge-vis104-64-badge` ·
`converge-pa15-recheck` · `converge-pa15-4k` · `converge-sem02-remainder`, 71라우트 × 라이트/다크,
1920×1080 3회 + 3840×2160 1회 = 페이지 552장)를 근거로 `C`(Console·Network)를 69라우트(전체
71 중 시드 데이터 없어 건너뛴 2개 제외) 전부 `O`로 채웠다(`user_team-doc-detail` 1곳은 처음엔
`~`였으나 같은 날 `PA-15`로 근본 원인을 확정·수정하고 이후 3회 E2E 재확인해 `O`로 올림, §15-2).
`V`(반응형·테마)를 그 69라우트 전부 `~`(1920/3840×라이트다크만, 8뷰포트 매트릭스 전체는 아님)로
채웠다. 또 BACKLOG.md 전수 대조로 `S`(판독)를 라우트 62개에서 `O`로 올렸다(근거: §WF1 표 +
`###` 라우트별 절 + 팀 공간/신규 티켓 실조작 절). §3에 빠져 있던 `/mail` 행을 신설하고 §4를
프로즈만 있던 상태에서 §2/§3과 같은 라우트별 표로 처음 채웠다. 근거·방법론 전문은 §15.
**같은 날 나중에** 이 갱신이 `S`=`-`로 남겨 둔 9라우트 중 7개(관리자 전용/registry 화면)를
`Read`로 직접 판독해 `S`도 `O`로 마저 올렸다 — 관리자 축은 이제 **45/45 전부 판독 완료**고,
그 과정에서 실결함 1건(`PA-16`, DataTable 열 정의 문제)을 찾아 고쳤다(§15-5).
그 전 갱신: 2026-08-15 **§13 신설**(Product Audit Cycle `PA-20260812`이 드러낸 **축 자체의 공백 9개**,
`T1`~`T9`) · 2026-08-11 (§12 QAH 하네스 1회차) · 2026-08-08 (사이클 0)

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
| 공개(로그인 전) | 4 | 1/4 | 1 | - | - | - | ~ | - | - | ~ |
| 사용자 콘솔 | 26 | **26/26** | 23/25 | - | - | - | 22 O·1 ~·2 - | - | - | ~ |
| 관리자(전용+registry) | 45 | **45/45** | **45/45** | - | - | - | **45/45** | - | - | ~ |
| **계** | **75** | **72/75** | **69/75** | 0 | ~ | 0 | **~**(68 O·1 ~·2 -) | **~** | 0 | ~ |

> `A`(API)와 `R`(RBAC)이 `0`에서 `~`로 올라갔다 — §6-1에 4역할 × 17엔드포인트 실측 매트릭스가 있다.
>
> **2026-08-15 갱신 — 이 행의 `라우트`/`S(캡처)`/`S(판독)`/`C`/`V` 값은 §15 근거로 다시 세었다.**
> `라우트` 열은 각 절 표의 **실제 행 수**를 그대로 센 것이다. `관리자`가 43→45로 는 것은 ①
> 그동안 빠져 있던 `/mail` 행을 §3에 신설하고(`admin_mail`, `QAH-06` 참고) ② §4를 프로즈에서
> 라우트별 표(28행)로 바꾼 결과다(§3 17행 + §4 28행 = 45). `사용자 콘솔`의 `26`은 예전부터
> 있던 값을 그대로 뒀지만 §2의 실제 표는 **25행**이다(`/search`가 3상태를 한 행에 묶는다) —
> 그래서 `S(판독)`·`C`를 분모 25로 적었다. `계`의 `75`도 이 두 그대로 둔 값(공개 4 + 사용자
> 26 + 관리자 45)의 합이라 §2~§4 실제 표 행 수 합(1+25+17+28=71)과는 다르다 — 라우트 자체가
> 늘거나 준 것이 아니라 **집계 방식이 두 절에서 다른 pre-existing 상태를 그대로 이어받았다는
> 뜻**이다. 실제로 오늘 E2E가 새로 커버한 것은 정확히 **69라우트**(71 전체 − 시드 데이터 없어
> 건너뛴 `user_chat-room-detail`·`user_game-room` 2개)이고, **전부 `C`=`O`(클린)**다 —
> `user_team-doc-detail` 1곳은 처음 4회 조사 때는 `~`(실측이 엇갈림)였으나 같은 날 `PA-15`로
> 근본 원인(`team_docs/service.py::record_view`의 무방비 쓰기 재시도)을 확정·수정하고 이후
> 3회 E2E로 재확인해 `O`로 올렸다. 상세는 §15(특히 §15-2 끝의 "후속 확인").

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
| `/login` | Jinja | O | - | - | - | O | - | - | ~ | ui_qa에 포함(`public_login`). S: PA-07(다크 모드)·PA-12(대비) 실브라우저 측정. C: 2026-08-15 E2E 4회 전부 clean(§15). V: 1920/3840×라이트다크만(§15), 원래 8뷰포트 매트릭스는 아님 |
| `/change-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |
| `/forgot-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함. ~~**FN-01(메일 UI 없음)과 직결**~~ — **2026-08-13 정정**: `FN-01`은 2026-08-11에 이미 닫혔다(`MailStatus.jsx` 신설, `frontend/src/screens/MailStatus.jsx` 존재 확인) — 이 행이 그 정정을 안 반영하고 있었다. 재설정 메일 발송 자체를 검증할 도구(`/mail` 화면의 "시험 메일 보내기")는 이제 있다, 다만 이 라우트 자체(`/forgot-password` 화면)의 ui_qa 캡처는 여전히 미포함 |
| `/reset-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |

## 2. 사용자 콘솔 (26)

> 아래 `S`는 **판독** 기준이다. 캡처는 26/26 전부 끝났다(`dist/ui-qa-admin/c1-admin/`).
> `ui_qa` 열의 "없음"이던 3개(`/projects`·`/projects/:id`·`/ideas`)는 이번에 추가돼 이제 전부 있다.

| 라우트 | 화면 | ui_qa | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|
| `/me` | Home | O | O | - | - | - | O | - | - | ~ |
| `/my-tickets` | MyTickets | O | O | - | - | - | O | - | - | ~ |
| `/unassigned` | Unassigned | O | O | - | - | - | O | - | - | ~ |
| `/new-ticket` | NewTicket | O | O | - | - | - | O | - | - | ~ |
| `/tickets/:id` | Ticket | O | O | - | - | - | O | - | - | ~ |
| `/team-tickets` | TeamTickets | O | O | - | - | - | O | - | - | ~ |
| `/projects` | Projects | O(신규) | O | - | - | - | O | - | - | ~ |
| `/projects/:id` | Project(+Metrics/Wbs/Weekly/Tickets) | O(신규) | O | - | - | - | O | - | - | ~ |
| `/sprint` | Sprint | O | O | - | - | - | O | - | - | ~ |
| `/chat` | Chat | O | O | - | - | - | O | - | - | ~ |
| `/chat-rooms` | ChatRooms | O | O | - | - | - | O | - | - | ~ |
| `/chat-rooms/:id` | ChatRoom | O | - | - | - | - | - | - | - | - |
| `/board` | Board | O | O | - | - | - | O | - | - | ~ |
| `/board/:id` | BoardPost | O | O | - | - | - | O | - | - | ~ |
| `/ideas` | IdeaBoard | O(신규) | O | - | - | - | O | - | - | ~ |
| `/team-docs` | TeamDocs | O | O | - | - | - | O | - | - | ~ |
| `/team-docs/trash` | Trash | O | O | - | - | - | O | - | - | ~ |
| `/team-docs/:id` | TeamDoc | O | O | - | - | - | O | - | - | ~ |
| `/games` | Games | O | O | - | - | - | O | - | - | ~ |
| `/games/:id` | GameRoom | O | - | - | - | - | - | - | - | - |
| `/notifications` | DataScreen | ~ | O | - | - | - | O | - | - | ~ |
| `/search` | Search | O(3상태) | O | - | - | - | O | - | - | ~ |
| `/profile` | Profile | O | O | - | - | - | O | - | - | ~ |
| `/my-stats` | MyStats | O | O | - | - | - | O | - | - | ~ |
| `/activity` | Activity | O | O | - | - | - | O | - | - | ~ |

> **S/C/V 갱신(2026-08-15) 근거는 §15 참고.** `/chat-rooms/:id`·`/games/:id`는 시드 데이터가
> 없어 오늘 E2E 4회 전부 건너뛰었다(권한 문제 아님, §15) — `-` 유지. `/team-docs/:id`는 오늘
> 4회 중 1회(`converge-vis104-64-badge`, 라이트 1920)에서 `console_errors` 1건(500) 실측돼
> `C`를 `O`가 아니라 `~`로 뒀다(§15). `/notifications`는 이 표에서는 사용자 화면처럼 묶여
> 있지만 실제로는 `admin_notifications`(관리자 셸) 라우트와 같은 캡처를 공유한다 — 별도
> 사용자 셸 캡처는 없다.

## 3. 관리자 전용 화면 (17)

> 2026-08-15에 `/mail`(`MailStatus.jsx`, `admin_mail`) 행을 추가했다 — `QAH-06`(BACKLOG.md)이
> 기록한 대로 이 라우트는 2026-08-11까지 `scripts/ui_qa/routes.py`에 아예 등록이 안 돼 있어
> 어떤 캡처·표에도 없었다. 그래서 "16"이던 절 제목도 "17"로 바뀐다.

| 라우트 | 화면 | ui_qa | 최소 역할 | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/dashboard` | Dashboard(916줄) | O | operator | O | - | - | - | O | - | - | ~ |
| `/users` | Users | O | admin | O | - | - | - | O | - | - | ~ |
| `/offboarding` | Offboarding | O | admin | O | - | - | - | O | - | - | ~ |
| `/organizations` | OrgConsole | O | admin | O | - | - | - | O | - | - | ~ |
| `/departments` | OrgConsole | O | admin | O | - | - | - | O | - | - | ~ |
| `/org-tree` | OrgConsole | O | admin | O | - | - | - | O | - | - | ~ |
| `/settings` | Settings(822줄) | O | operator | O | - | - | - | O | - | - | ~ |
| `/diagnostics` | Ops/Diagnostics | O | admin | O | - | - | - | O | - | - | ~ |
| `/maintenance` | Ops/Maintenance | O | operator | O | - | - | - | O | - | - | ~ |
| `/dev-report` | DevReport | O | auditor | O | - | - | - | O | - | - | ~ |
| `/scheduler-calendar` | SchedulerCalendar | O | operator | O | - | - | - | O | - | - | ~ |
| `/mail` | MailStatus | O | operator | O | - | - | - | O | - | - | ~ |
| `/system` | SystemOps(298줄) | O(신규) | system_admin | O | - | - | - | O | - | - | ~ |
| `/setup` | SetupWizard(232줄) | O(신규) | system_admin | O | - | - | - | O | - | - | ~ |
| `/notion-console` | NotionConsole(377줄) | O(신규) | system_admin | O | - | - | - | O | - | - | ~ |
| `/llm-console` | LlmConsole(354줄) | O(신규) | system_admin | O | - | - | - | O | - | - | ~ |
| `/search` | Search(공유) | O | — | O | - | - | - | O | - | - | ~ |

> **S/C/V 갱신(2026-08-15) 근거는 §15 참고.** `/notion-console`·`/llm-console`·`/mail`은 오늘
> E2E에서 C(콘솔 오류 0건)·V(1920/3840 라이트다크)를 먼저 확보했고, 같은 날 나중에(7화면
> 시각 재점검 패스) `dist/ui-qa/converge-ai70/light/1920x1080/`의 스크린샷을 `Read`로 직접
> 판독해 `S`도 `O`로 올렸다 — `admin_notion-console`은 이미 알려진 `VIS-42`/`VIS-49`/`VIS-63`/
> `VIS-122` 클로비-FAB 겹침 가족과 같은 종류의 겹침이 한 곳 더 보였으나(마스코트가 "토큰"
> 주의 콜아웃 모서리를 살짝 덮음) 전담 세션으로 이미 의도적으로 미룬 것과 같은 사례라 새로
> 만들지 않았고, `admin_mail`은 실제 결함(`PA-16`, DataTable 열 정의의 무의미한 `render`가
> 말줄임을 깨 옆 열을 잘라 먹음)을 찾아 그 자리에서 고쳤다. `/system`·`/setup`은 이미 이전에
> 판독됐던 상태 그대로다. `/search`는 `user_search`/`user_search-results`/`user_search-empty`
> (사용자 셸)와 같은 컴포넌트를 공유한다 — 관리자 셸(`/admin#/search`) 자체의 독립된 캡처는
> 이번에도 없었다(공유 컴포넌트라는 전제로 값을 옮겨 적었을 뿐).

## 4. 관리자 registry — DataScreen 28키

`F/A/D/R/L`은 전부 미검증(아래 표에서도 `-`로 유지). **28개 전부 열 폭 지정이 0건**(BACKLOG
DS-06)이라 좁은 폭에서 제목이 세로로 무너질 수 있는데 아무도 실물로 확인하지 않았다.
`organizations`·`departments`·`org-tree`는 REGISTRY 키이지만 `OrgConsole`이 그려 **§3에 이미
행이 있다** — 아래 표에는 중복으로 안 넣는다(28키 - 3 + 상세 드로어 3종 = 28행).

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

> **2026-08-15 신설** — 이 절은 그동안 라우트별 `S/F/A/D/C/R/L/V` 행이 아예 없었다(위 두 표만
> 있었다). 오늘 2026-08-15 E2E 4회가 이 28라우트 전부를 캡처했고 BACKLOG.md 대조도 끝나서,
> §2/§3과 같은 형식의 표를 처음으로 채운다. 근거는 §15 참고.

| 도메인 파일 | 라우트 | 화면 | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|
| `integrations.js` | `/integrations` | 외부 연동 | O | - | - | - | O | - | - | ~ |
| `integrations.js` | `/integrations?id=` | 외부 연동 상세(드로어) | O | - | - | - | O | - | - | ~ |
| `integrations.js` | `/runners` | 러너 | O | - | - | - | O | - | - | ~ |
| `integrations.js` | `/runners?id=` | 러너 상세(드로어) | O | - | - | - | O | - | - | ~ |
| `integrations.js` | `/workflows` | 워크플로 | O | - | - | - | O | - | - | ~ |
| `authoring.js` | `/prompts` | 프롬프트 | O | - | - | - | O | - | - | ~ |
| `authoring.js` | `/policies` | 정책 | O | - | - | - | O | - | - | ~ |
| `authoring.js` | `/templates` | 템플릿 | O | - | - | - | O | - | - | ~ |
| `authoring.js` | `/prompt-usage` | 프롬프트 사용 통계 | O | - | - | - | O | - | - | ~ |
| `authoring.js` | `/policy-usage` | 정책 사용 통계 | O | - | - | - | O | - | - | ~ |
| `automation.js` | `/schedules` | 실행 일정(스케줄) | O | - | - | - | O | - | - | ~ |
| `automation.js` | `/documents` | 문서 자동 생성 | O | - | - | - | O | - | - | ~ |
| `automation.js` | `/jobs` | 작업 큐 | O | - | - | - | O | - | - | ~ |
| `automation.js` | `/jobs?job_id=` | 작업 상세(드로어) | O | - | - | - | O | - | - | ~ |
| `org.js` | `/job-titles` | 직책 관리 | O | - | - | - | O | - | - | ~ |
| `org.js` | `/notion-mapping` | Notion 사용자 연결 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/approvals` | 승인 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/approval-delegations` | 승인 위임 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/audit` | 감사 로그 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/audit-anomalies` | 감사 이상 징후 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/rbac` | 권한 매트릭스 | O | - | - | - | O | - | - | ~ |
| `governance.js` | `/impersonation` | 임퍼소네이션(대리 보기) | O | - | - | - | O | - | - | ~ |
| `platform.js` | `/backup` | 백업 | O | - | - | - | O | - | - | ~ |
| `platform.js` | `/restore-drills` | 복구 리허설 | O | - | - | - | O | - | - | ~ |
| `platform.js` | `/announcements` | 공지 배너 | O | - | - | - | O | - | - | ~ |
| `platform.js` | `/ai-quotas` | AI 사용 상한 | O | - | - | - | O | - | - | ~ |
| `platform.js` | `/feature-flags` | 기능 플래그 | O | - | - | - | O | - | - | ~ |
| `notifications.js` | `/notifications` | 알림 | O | - | - | - | O | - | - | ~ |

> `workflows`·`prompts`·`policy-usage`·`job-titles` 4개는 오늘 E2E로 `C`/`V`를 먼저 확보했고,
> 같은 날 나중에(7화면 시각 재점검 패스) 스크린샷을 `Read`로 직접 판독해 `S`도 `O`로 올렸다 —
> 4개 다 표(각 3~5행)가 깨끗했고 새 결함은 없었다(§15).

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
| `T1` 타이포 토큰 소비 | 선언된 글자 크기/굵기/radius 토큰이 **실제로 소비되는가**(리터럴 잔존 수) | `S`(화면)·`K`(대비) 축은 "보기에 이상한가"만 본다. 스케일이 1px 연속체로 번져도 스크린샷은 통과한다 — 그래서 `fontSize` 리터럴 31종·278회가 **VIS 162건을 거치고도** 안 잡혔다(`PA-RC-0001`) | **검증완료(2026-08-16)** — 토큰 자체(`FONT_SIZE`/`FONT_WEIGHT`/`RADIUS`)는 `theme-baseline.test.js`가 고정. `scan_design.py`(표현식 단위 집계, 삼항연산자 안 리터럴도 잡음)로 남은 8종 장꼬리까지 전수 확인 — 아이콘/이모지/아바타 6곳은 구조적으로 자명해 대상 밖, 텍스트 7곳은 각 자리에 "왜 의도된 예외인지" 직접 주석(acceptance_criteria 1의 OR-조건 충족). 스캐너 사각지대에서 `OrgTree.jsx`의 진짜 미토큰화 1건(`fontWeight`/`fontSize` 둘 다 삼항연산자 안이라 이전 전수 정리가 놓침, 값 일치 확인 후 토큰 교체)도 발견·수정. `docs/BACKLOG.md` PA-01 7차 확장에 상세. **남은 것**: 장꼬리 값들의 "전용 토큰 신설 vs 예외 유지" 최종 설계 결정과 그에 따른 `static_checks.sh` 린트(acceptance_criteria 5)뿐 — 다음 세션 |
| `T2` 오류 문구 3요소 | 실패 문구가 `[무엇이 실패]·[왜]·[무엇을 하라]`를 주는가 | 화면별 시각·기능 축은 있으나 **문구 축이 없다.** 실패 문구 167건 중 회복 경로를 주는 것이 24건(14%)인 상태로 전 화면이 QA를 통과했다(`PA-RC-0002`) | **검증완료(2026-08-16)** — `docs/UX_WRITING.md`에 오류 2문장 패턴(실패+회복 절) 확정. 공용 진입점 `lib/api.js` 수정 뒤 5개 병렬 에이전트 + 직접 4라운드로 141건→63건, 그 뒤 **62건 전부를 file:line이 아니라 실제 소스 문맥으로 낱개 대조**(스캐너의 3대 사각지대 — 문자열 연결·형제 Button/Link·ErrorState/EmptyState 공용 컴포넌트 — 를 하나씩 확인)해 52건은 이미 충족/실패 서술 아님으로 재분류, 진짜 신규 수정은 2곳뿐(`SystemOps.jsx`·`useChat.js`, 신규 회귀 2건 + revert-to-verify), 남은 8건은 재시도 무의미/자동 재시도 중이라는 구체적 사유로 예외 등재. **최종 회복 절 비율 96~100%**(기준 90% 초과), `docs/BACKLOG.md` PA-02 5차 확장에 판정 근거 영구 기록(스캐너 자체는 `var/`라 gitignore 대상). 동사표 위반 검사는 여전히 미착수 |
| `T3` 용어 표준 준수 | 같은 개념에 같은 동사·같은 종결 규칙을 쓰는가 | 같은 문장이 마침표 유무로 **동시 존재**하는데 이를 보는 칸이 없었다(`PA-RC-0002`) | **부분** — `docs/UX_WRITING.md`에 마침표 규칙(문장형 O/라벨형 X) + 표준 동사표(추가/수정/삭제/비활성화/활성화/저장) 확정. 원 근거였던 "권한이 없습니다" 마침표 불일치는 재확인 결과 title(라벨)과 문장이 이미 규칙대로 올바르게 갈려 있어 **버그 아님**으로 재분류. **종결 규칙의 한 하위 축(문장 종결부 쉼표 이어붙이기)은 전수 수정 + 기계 검사로 승격**: kit.jsx 내부 6:5 불일치를 따라가 화면 20개·26곳에서 같은 쉼표-이어붙이기 패턴을 찾아 전부 마침표로 수정(`docs/BACKLOG.md` PA-02 상세), `frontend/src/ui/ux-writing-punctuation.test.js` + `static_checks.sh` 신규 step 두 독립 게이트로 회귀 고정(둘 다 revert-to-verify 확인). 동사표 위반 검사·기존 호출부 전면 정렬은 여전히 미착수 |
| `T4` 저장소 위생 | **stash · reflog · dangling 객체**에 자격증명·비밀이 없는가 | 기존 보안 검사는 **워킹트리와 커밋만** 본다. 평문 자격증명이 `stash@{0}` 안에 있는데 어떤 스캔도 그것을 못 봤다 — 이번 건이 정확히 그 사각지대로 들어왔다(`PA-RC-0003`) | **검사 도입됨(2026-08-16), 회전은 사람 조치 대기** — `scripts/check_git_secrets.py`(값 미출력, stash·reflog-only 커밋·dangling 3표면) 신설 + `static_checks.sh` 필수 단계 배선, 격리 저장소 revert-to-verify 회귀 4건. 켜자마자 `stash@{0}`가 의도대로 잡혀 지금 `static_checks.sh`는 **의도적으로 red**다(회전 전까지 계속 그래야 한다) — 회전은 저장소 밖 운영 행위라 이 축의 코드 구현 범위 밖(`docs/BACKLOG.md` SEC-20) |
| `T5` 입력 경계값 | 상한·하한·빈 값·**붙여넣기 초과** 입력을 화면이 막는가 | 화면별 기능 검증은 있으나 경계 입력을 보는 칸이 없어서, 공용 폼 경로를 쓰는 **관리자 화면 28개 전부**가 프런트 길이 제한 0건인 채로 통과했다(`PA-RC-0005`). 기존 `H`(Negative/Edge)와 함께 볼 것 | **검증완료(상한)** — `create:` 있는 등록 화면 13/13곳 전부 실제 배선 확인(FormField 렌더 + 붙여넣기 초과 토스트, revert-to-verify). `Users.jsx`(공용 경로 밖)·`feature-flags`(폼 자체 없음)는 이 메커니즘의 대상이 아니다. 하한·빈 값 축은 아직 별도 검증 없음 |
| `T6` 배포 revision 일치 | **검증 대상과 배포본이 같은 코드인가** | 이 축이 없어서 TEST 서버의 **5일·131커밋 드리프트**가 어떤 QA도 통과하지 않고 존재했다. 이 축이 비면 그 위에서 얻은 모든 E2E 결과의 의미가 사라진다 — 다른 모든 축의 **전제조건**이다(`PA-RC-0007`) | **검증완료(2026-08-15)** — 프런트엔드 재빌드 후 `upgrade-clovirone-web-assistant.sh`로 통합 배포, healthz/readyz + `BUILD_STAMP.json` 해시 + 실서빙 자산 해시 3중 확인(`docs/BACKLOG.md` PA-05). 이 재배포를 전제조건으로 삼아 §14의 Chrome E2E를 그 직후에 실행했다 |
| `T7` 동시성 반복 실행 | race 계열 테스트를 **N회 반복**해 통과하는가 | race 테스트는 1회 실행이 무의미한데(이번 결함도 60%는 통과했다) 현재 QA는 1회만 본다. 그래서 재시도 예산 결함이 오래 안 보였다(`PA-RC-0008`) | **검증완료** — race 계열 6개 파일(prompt/policy 새 버전, 승인 생성, notion 매핑 get-or-create, 쿼터 TOCTOU, 휴지통 이동, 헬스 스냅샷)을 20회 연속 반복 실행해 실패 0건 확인. `PA-RC-0009`가 이 절차를 `scripts/run_full_regression.sh`로 스크립트화함 |
| `T8` 스위트 건강 | Full Regression **완주 여부·소요 시간·비결정 테스트 목록** | 결과(green/red)만 보고 스위트 자체의 건강을 안 봤다. 그래서 *"45분 걸린다"* 가 *"행(hang)이다"* 로 **세 사이클 동안** 잘못 기록됐고 아무도 전체 회귀를 돌리지 않았다(`PA-RC-0009`) | **검증완료** — Audit의 4청크 전경 실행(2,903건 `EXIT=0`, 5회)에 이어 `scripts/run_full_regression.sh`로 **3회 연속** 배경 실행(30분26초·30분2초·32분7초, 전부 `EXIT=0`) — 완료 기준의 "1회 green이 아니라 반복 확인" 요구를 채움. `PA-03`이 지목한 flaky 테스트도 3연속 전부 통과해 재발 없음 확인. 절차는 `scripts/run_full_regression.sh` 자체로 문서화됨(4청크 분할 실행) |
| `T9` 서버 렌더 페이지 × 테마 | SPA **밖** 페이지(로그인·비밀번호 재설정)가 라이트/다크를 따르는가 | 기존 화면 축이 **React 라우트 중심**이라 SPA 밖 페이지가 통째로 빠져 있다. 그래서 "로그인 화면은 다크가 아예 안 켜진다"가 그대로 통과했다(`PA-RC-0010`) | **검증완료** — 4화면 Playwright 실측(`DECISIONS.md` D-74): `forgot-password`/`reset-password`는 다크 미지원이었으나 `tokens.css`의 `@media (prefers-color-scheme: dark)` 추가로 해결. `change-password`는 이미 `theme.js`로 지원 중이었음(grep만으로는 안 보였음). `login`은 `login.css`가 의도적으로 라이트 고정(히어로 설계 전제, `test_theme_on_all_authed_pages.py`로 고정) — 대상 아님, 그대로 유지 |

### 2026-08-16 갱신 — 축별 현재 상태 (구현 17커밋 이후 재측정)

| 축 | 상태 변화 | 근거 |
|---|---|---|
| `T1` 타이포 토큰 소비 | **미검증 → 대부분 충족(2026-08-16)** | `theme.js`에 `FONT_SIZE` 6단계 신설. 3대 클러스터(35곳) 전수 대조로 11곳 이전 + 24곳 정당한 예외 확인. 남은 것은 1~6회짜리 장꼬리 단일값 8종뿐 |
| `T2` 오류 문구 3요소 | **미검증 → 충족(2026-08-16)** | `docs/UX_WRITING.md` 신설 + 62건 전수 재검증(스캐너 사각지대 확인, 신규 수정 2곳 + 예외 등재 8곳). 회복 절 비율 96~100%로 기준 90% 초과, 축이 닫혔다 |
| `T3` 용어 표준 준수 | **미검증 → 검사 도입됨** | `static_checks.sh`에 표준 동사표·쉼표접속 린트 추가 |
| `T4` 저장소 위생 | **미검증 → 검사 도입됨(회전은 별개로 대기)** | `check_git_secrets.py` 신설로 탐지 공백 자체는 닫혔다. `stash@{0}`는 여전히 존재하고 검사가 그것을 정확히 잡아 `static_checks.sh`를 의도적으로 red로 유지한다 — 회전(사람 조치)이 끝나야 이 축이 green이 된다 |
| `T5` 입력 경계값 | **미검증 → 충족** | `lib/fieldLimits.js` + `FormField` `maxLength`/붙여넣기 초과 경고/글자수 표시 |
| `T6` 배포 revision 일치 | **불일치 → 일치 확인** | 배포본 `source_hash`가 HEAD 커밋본과 정확히 일치, `BUNDLE_FRESH_OK`. 드리프트 131커밋 → 0 |
| `T7` 동시성 반복 실행 | **미검증 → 충족** | race 테스트 **5회 연속 통과**(원래 약 40% 실패) |
| `T8` 스위트 건강 | **부분 → 충족** | `scripts/run_full_regression.sh` 신설, Full Regression 3연속 green(소요 시간 기록 포함) |
| `T9` 서버 렌더 페이지 × 테마 | **미검증 → 충족(단, 판정이 바뀌었다)** | 4화면 실측: `/forgot-password`·`/reset-password` 다크 적용 확인, `/login`은 **의도된 라이트 고정**(회귀 테스트가 계약으로 못박음), `/change-password`는 저장된 선택을 따름. 원 감사의 "로그인이 빠졌다"는 **오탐**이었다(`PA-F-041`) |

**새 축 하나를 추가한다.**

| 새 축 | 무엇을 보는가 | 왜 필요한가 | 상태 |
|---|---|---|---|
| `T10` 완료 재측정 | **"완료"로 기록된 항목을 그 항목 자신의 `acceptance_criteria`로 다시 재는가** | 이번 재검증에서 구현 기록과 실제가 **양쪽 방향으로** 어긋났다 — `PA-RC-0007`은 "보류"라 적혀 있었는데 이미 닫혀 있었고, `PA-RC-0002`는 "완전 종료"라 적혀 있었는데 기준 미달이었다. 어느 쪽도 악의가 아니라 **다시 재지 않은 것**이다 | **1회 수행함**(이 Audit, 2026-08-16). 정례화 필요 |

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

## 14. CLAUDE.md §10 Chrome Whole-product E2E — 실제 실행 (2026-08-15, label `post_20260815`)

T6(배포 revision 일치) 종료 직후, TEST 서버(`10.100.64.71`)에서 `scripts/ui_qa/run.py`로
71 라우트 × 2 테마 × 5 뷰포트(390×844 · 1366×768 · 1920×1080 · 3840×2160 · 1920×1080@2x)
= **690페이지** 실행. `system_admin` 권한 QA 계정, 실HTTPS(`--insecure`, 자체서명 인증서),
`--fail-on horizontal_overflow,console_errors,page_errors,auth_ok,theme_applied`.
소요 1,580초(26분20초), 690/690 완주(크래시·중단 없음).

### 결과 — 21개 자동 검사 축, 690페이지 기준 요약

| 축 | pass | fail | skip | 비고 |
|---|---|---|---|---|
| auth_ok | 690 | 0 | 0 | |
| theme_applied | 680 | 0 | 10 | 로그인(라이트 고정)만 skip |
| horizontal_overflow | 690 | 0 | 0 | |
| console_errors / page_errors | 690 | 0 | 0 | 둘 다 |
| broken_images / duplicate_ids | 690 | 0 | 0 | 둘 다 |
| tiny_text / narrow_main | 138 | 0 | 552 | 각각 뷰포트폭 ≥2200/≥3840 조건부(설계상 skip) |
| vertical_text_collapse / fab_overlap / image_cropped / rail_wider_than_prose | 690 | 0 | 0 | 넷 다 |
| **content_clipped** | 688 | **2** | 0 | `user_chat` 390×844 라이트/다크 — QA-15(하네스 오탐, 아래) |
| **contrast** | 677 | **13** | 0 | `public_login` 10조합 + `user_me` 3조합 — PA-12/PA-13(아래) |
| modal_* 7종 | 0 | 0 | 0 | 이번 라우트 세트에 열린 모달 캡처가 없어 미가동(설계상 — 별도 모달 전용 흐름 필요, 이 축의 공백으로 남긴다) |

690페이지 중 실제 결함으로 이어진 것은 **contrast 13건 + content_clipped 2건 = 15건**,
전부 개별 검토 결과 **딱 3개의 Root Cause**로 수렴했다(같은 색/같은 레이아웃 문제가
여러 뷰포트·테마 조합에서 반복 카운트됐을 뿐):

- **PA-12** 로그인 비밀번호 표시 버튼 대비 4.449:1 (10 페이지 전부 동일 — 로그인은 라이트
  고정이라 "다크 테마" 캡처도 같은 화면을 두 번 찍은 것)
- **PA-13** `/me` 동기화 캡션 대비 4.48:1 (라이트 3개 뷰포트 — 3840/1920@2x·다크는 다른
  배경 조합이라 안 걸림, 근본 원인은 동일)
- **QA-15** `content_clipped` 검사기가 `inert` 오프스크린 드로어를 오탐(제품 결함 아님,
  하네스 결함으로 재분류 — 실측 확인 절차는 `docs/BACKLOG.md` QA-15 참고)

세 건 전부 같은 날 수정·검증 완료(`docs/BACKLOG.md` PA-12/PA-13/QA-15). **미실행 재E2E**:
수정이 CSS 리터럴 2줄 + JSX 색 토큰 1줄 + 하네스 JS 1줄로 전부 국소적이고, 각 수정마다
WCAG 계산식으로 새 대비값을 미리 계산해 여유 있게(4.45→5.68, 4.48→5.99) 통과 확인했으며
관련 focused test(frontend 257파일/1,764건 + pytest 20건)가 green이라 재배포·재E2E 없이
결론 확정. 다음 통합 배포 때 이 화면들이 실제로 고쳐졌는지는 그 배포 뒤 E2E에서 자연히
재확인된다.

### 이 실행이 검증한 것 / 안 한 것

690페이지 스윕은 **정적 상태**(첫 로드 후 DOM 스냅샷) 기준이다. 모달 열기, 폼 제출,
페이지네이션·필터 조작 같은 **상호작용 이후 상태**는 이 실행의 21개 축이 보지 않는다
(`modal_*` 7종이 전부 0/0/0인 것이 그 증거) — `scripts/ui_qa/`의 `interact.py`·
`trash_e2e.py`·`approval_e2e.py`·`saved_view_e2e.py` 등 별도 상호작용 전용 스크립트가
이 갭을 메우도록 이미 존재하며, 이번 실행은 그것들을 포함하지 않았다. §7(주요
End-to-End 흐름)의 개별 시나리오가 그 축을 대신 커버한다.

---

## 15. 2026-08-15(§14 이후) 라우트별 `C`/`S`(판독)/`V` 갱신 — 추가 E2E 4회 + BACKLOG.md 전수 대조

§14의 690페이지 실행(`post_20260815`, T6 배포 확인 직후) **이후** 같은 날 저녁에 이어서 돈
4회의 추가 E2E와, `docs/BACKLOG.md`(3300여 줄) 전수 grep 대조를 근거로 §0~§4의 라우트별
`C`/`S`(판독)/`V` 셀을 갱신했다. `F`/`A`/`D`/`R`/`L`은 이번 갱신에서 **손대지 않았다** —
오늘 실행한 것은 페이지 로드뿐이고, 기능 실행·API payload 확인·DB 재확인·RBAC·화면 간 연동은
검증하지 않았기 때문이다.

### 15-1. 근거 파일 4개 — 정확한 경로와 pass/fail/skip

| 파일 | 라벨 | 시각(KST) | 테마×뷰포트 | 페이지 | 비고 |
|---|---|---|---|---|---|
| `dist/ui-qa/converge-vis104-64-badge/results.json` | `converge-vis104-64-badge` | 22:35:02–22:38:13 | 라이트·다크 × 1920×1080 | 138 | `console_errors` **1건 fail**(아래 15-2) |
| `dist/ui-qa/converge-pa15-recheck/results.json` | `converge-pa15-recheck` | 22:52:03–22:55:10 | 라이트·다크 × 1920×1080 | 138 | 전부 pass |
| `dist/ui-qa/converge-pa15-4k/results.json` | `converge-pa15-4k` | 22:55:22–22:59:11 | 라이트·다크 × 3840×2160 | 138 | 전부 pass(`tiny_text`/`narrow_main` 포함) |
| `dist/ui-qa/converge-sem02-remainder/results.json` | `converge-sem02-remainder` | 23:13:23–23:16:29 | 라이트·다크 × 1920×1080 | 138 | 전부 pass |

네 실행 모두 계정 `ui-qa@goodmit.co.kr`(role=`system_admin`), `base_url=https://clovirone-ai.gooddi.lab`,
`run.routes` 71개 동일. 4개 파일의 `pages[]`를 전부 순회해 `assertions`의 모든 축(`auth_ok`·
`theme_applied`·`horizontal_overflow`·`console_errors`·`page_errors`·`broken_images`·
`duplicate_ids`·`tiny_text`·`narrow_main`·`vertical_text_collapse`·`fab_overlap`·`image_cropped`·
`content_clipped`·`rail_wider_than_prose`·`contrast`)를 대조한 결과 **552페이지 중 fail은 정확히
1건**(아래). 즉 원 지시서가 말한 "4회 전부 0 console_errors"는 **3/4 회는 맞고 1/4 회는 틀렸다**
— 아래에서 그 1건을 숨기지 않고 그대로 남긴다.

**두 라우트는 4회 전부 완전히 건너뛰었다**(시드 데이터 없음, 권한 문제 아님 — 각 파일의
`notes[]`에 동일하게 기록):
- `user_chat-room-detail` — `/api/team-chat/rooms` → 200, 항목 0건
- `user_game-room` — `/api/games/rooms` → 200, 항목 0건

이 둘은 `S`/`C`/`V` 어느 것도 이번에 `-`에서 바꾸지 않았다 — 지시서가 명시적으로 경고한 대로
"건너뜀"을 "커버됨"으로 잘못 표기하지 않기 위해서다.

### 15-2. 유일한 예외 — `user_team-doc-detail` (`C`를 `O`가 아니라 `~`로 둔 이유)

`converge-vis104-64-badge`(4회 중 **첫 번째** 실행)에서 `user_team-doc-detail`(라이트,
1920×1080) 1페이지가 `console_errors` 1건으로 fail했다:

```
"console_errors": {"status": "fail", "count": 1,
  "samples": ["Failed to load resource: the server responded with a status of 500 (Internal Server Error)"]}
```

같은 라우트의 나머지 7페이지(같은 실행의 다크 1920 + `pa15-recheck` 라이트/다크 1920 + `pa15-4k`
라이트/다크 3840 + `sem02-remainder` 라이트/다크 1920)는 **전부 pass**했다 — 특히 `pa15-recheck`는
같은 뷰포트·테마 조합을 **17분 뒤**에 다시 찍었는데 그때는 깨끗했다. 즉 **8번 중 7번은 깨끗하고
1번만 500이 실측됐다** — 결정론적 결함이 아니라 **일시적**(transient) 신호로 읽힌다. 그래서
이 라우트의 `C`는 `O`(클린 확정)가 아니라 `~`(부분 — 실측 증거가 섞여 있음)로 남긴다.

**근거 없이 넘기지 않고 코드까지 확인했다**: `/team-docs/:id`를 열면 `app/team_docs/service.py`의
"최근 열람" 기록 경로(약 335~340줄, `DocumentRecentView`)가 `db.begin_nested()`(SAVEPOINT) 안에서
쓰기를 한다 — 즉 이 화면은 겉보기엔 GET이지만 실제로는 매번 쓰기를 유발한다. `docs/BACKLOG.md`의
`PA-14`(§PA, 2026-08-15 같은 날)가 정확히 이 계열의 증상을 문서화하고 있다: `app/core/deps.py::get_db`의
**요청-스코프 바깥 commit**(라우트 핸들러가 성공 반환한 *다음* 마지막 `db.commit()`)이 쓰기 경합에
걸리면 재시도 없이 원시 500을 던지던 D-75 갭을, 2026-08-15에 **분류만**(원시 500 → 503
`WriteUnavailableError`) 부분적으로 닫았다 — 재시도 자체는 아직 구현되지 않았다. 더 오래된 선례로
`QAH-01`(BACKLOG.md, 2026-08-11 구현완료)도 같은 모양(세션 `last_seen_at` 터치 쓰기가 SQLite
쓰기충돌로 500을 냄, `admin_offboarding`에서 실측)이었다. **이것은 확정 진단이 아니라 정황
근거다** — 서버 로그로 22:35~22:38 구간의 실제 스택트레이스를 직접 대조하지 않았고, PA-14의
수정이 이 4회 E2E 중 어느 시점에 실제로 배포돼 있었는지도 확인하지 않았다. 다음에 이 라우트를
다시 볼 사람은 (a) 서버 로그에서 해당 시각 500 스택트레이스를 찾아 `get_db` 바깥 커밋인지
확인하고 (b) 재현되면 `PA-14`가 미룬 "요청 전체 재실행" 재시도를 이 계열 전체에 적용할지
판단하면 된다. **이번 세션은 QA_COVERAGE 갱신 범위를 넘는 근본 원인 수정에는 착수하지 않았다.**

**후속 확인(같은 날, 2026-08-15) — 위 "정황 근거"가 그새 확정 진단 + 수정완료로 바뀌었다.**
이 에이전트가 조사하는 동안 Main Agent가 **같은 문제를 서버 `journalctl`로 직접 재현**했다 —
정확히 이 실행(`converge-vis104-64-badge`, 22:35경)의 `request_id=2b6ef8757dd0a4396510d72630ab57b4`
스택트레이스를 찾아 `sqlite3.OperationalError: database is locked`가 **`get_db` 바깥 커밋이 아니라
`app/team_docs/service.py::record_view`의 "이미 있는 행 갱신" 분기 자체**(SAVEPOINT도 재시도도
없던 자리)에서 났음을 확정했다(`PA-15`, `docs/BACKLOG.md`). 두 분기(신규/갱신)를 공용 재시도
유틸로 통합해 고치고 재배포한 뒤, **이후 3회의 독립된 전체 E2E**(`converge-pa15-recheck`·
`converge-vis50-verify`·`converge-ai70`, 마지막은 이 갱신 이후에 도 한 번 더 138페이지 전체
재실행)에서 이 라우트를 포함해 `console_errors` 0건을 확인했다. 즉 "일시적 신호"가 아니라
**부하 의존적이지만 결정론적인 실제 버그였고, 지금은 고쳐졌다** — 위 표의 `C`를 `O`로 올렸다.
이 절의 조사 서술 자체는 방법론이 정확했으므로(파일·함수까지 정확히 짚었다) 지우지 않고
그대로 둔다.

### 15-3. `V`(반응형·테마) — 무엇을 커버했고 무엇을 안 했는가

4회 실행이 실제로 돈 뷰포트는 **1920×1080**(3회, 라이트+다크)과 **3840×2160**(1회, 라이트+다크)
**둘뿐**이다. §1 축 정의(8번, "8뷰포트 + 브레이크포인트 사이 + 라이트/다크")나 §10-2가 쓴
768/1024/1200/1366 계열, §14가 쓴 390×844(모바일)·1920×1080@2x는 **오늘 이 4회에 포함되지
않았다**. 그래서 오늘 커버된 69라우트 전부 `V`를 `O`가 아니라 **`~`**로만 올렸다 — §11 관례상
`V: O`는 6개 폭(768/1024/1200/1366/1920/3840) × 라이트다크를 뜻했는데 오늘 증거는 그중 2개
폭뿐이라 그 기준에 못 미친다.

참고로 `admin_users`·`admin_audit`·`admin_jobs`·`user_my-tickets`·`admin_integrations` 5개는
**과거**(BACKLOG.md `## RESP`, 2026-08-08) 768/1024/1200/1366 실측이 이미 있다 — 오늘 것과
합치면 이 5개만 6개 폭 중 4개(768/1024/1200/1366+1920/3840 중 오늘 몫)를 갖는 셈이지만, 이번
갱신에서는 셀 값을 이 5개만 다르게 표기하지 않았다(다른 69개와 같은 `~`) — 오늘 이 세션이
직접 확인한 것은 1920/3840뿐이고, 옛 RESP 데이터를 다시 열어 같은 페이지인지 재확인하지 않았기
때문이다. 필요하면 다음 세션이 그 5개만 별도로 승격할 수 있다.

### 15-4. `S`(판독) — 방법론과 라우트별 근거

**방법**: `docs/BACKLOG.md` 전체에서 (a) `### <경로>` 형태의 라우트 전용 절 헤더, (b) 워크플로
조사(`WF1` 등)가 그 자체의 화면별 표에서 정확히 이 하네스의 route id(`user_X`/`admin_X`) 형식으로
행을 낸 경우, 두 가지를 근거로 삼았다 — 둘 다 "누군가 그 화면의 실제 렌더 결과를 보고 구체적
결함/확인 사항을 적었다"는 것이 원문에서 확인되는 경우만 카운트했고, 다른 주제의 표에 라우트
이름이 스치듯 인용된 경우(예: RBAC API 매트릭스, `user_id`/`admin_scope` 같은 필드명과의 우연한
문자열 일치)는 **제외**했다. **62/71 라우트**에서 이 기준을 만족하는 근거를 찾아 `S`를 `-`→`O`로
올렸다. 나머지 9개는 실제로 찾지 못한 **진짜 공백**이다(15-5).

<details>
<summary>라우트별 근거 전문 (펼치기) — 62개, BACKLOG.md 줄 번호는 이 갱신 시점 기준</summary>

**그룹 A — `###` 라우트 전용 절 (25개)**

| 라우트 | BACKLOG.md 절 |
|---|---|
| `user_me` | `/me` 사용자 홈 (L512) |
| `user_my-tickets` | 4K(3840×2160) 실측 — `/my-tickets` 빈 상태 (L775) |
| `user_project-detail` | `/projects/:id` 프로젝트 상세 (L543) |
| `user_projects` | `/projects` (L482) |
| `user_sprint` | `/sprint` 스프린트 회의 (L734) + 브레이크포인트 '사이' 실측(VIS-73, L706) |
| `user_chat` | `/chat` AI 도우미 빈 상태 (L826) + 4K 다크 판독 (L2504) + Chrome 실브라우저 확인 (L724) |
| `user_board` | `/board` 자유게시판 (L1873) + 팀 공간 3화면 실조작 (L604) |
| `user_team-docs` | `/team-docs` 문서 (L792) + Chrome 실브라우저 확인 (L724) |
| `user_ticket-detail` | `/tickets/:id` 티켓 상세 (L1363) |
| `user_games` | `/games` 놀이 (L1400) + 팀 공간 3화면 실조작 (L604) |
| `admin_dashboard` | `/dashboard` 관리자 대시보드 (L814) + 4K 다크 판독 (L2484) |
| `admin_users` | `/users` 사용자 관리 (L802) + 반응형 실측 (L1904) |
| `admin_diagnostics` | `/diagnostics` 진단 (L523) |
| `admin_dev-report` | `/dev-report` 개발자 월간 리포트 (L563) |
| `admin_audit` | `/audit` 감사 로그 (L745) + 반응형 실측 (L1904) |
| `admin_settings` | `/settings` 설정 (L761) |
| `admin_setup` | `/setup` 초기 설정 (L1028) |
| `admin_system` | `/system` 시스템 설정 (L1036) |
| `admin_jobs` | `/jobs` 작업 큐 (L1199) + 반응형 실측 (L1904) |
| `admin_scheduler-calendar` | `/scheduler-calendar` 실행 달력 (L1211) |
| `admin_rbac` | `/rbac` 권한 매트릭스 (L1221) |
| `admin_notifications` | `/notifications` + 지표 카드 줄바꿈 (L1618) + 알림 딥링크 실조작 (L657) |
| `admin_restore-drills` | `/restore-drills` (L1701) |
| `admin_integrations` | `/integrations` 외부 연동 (L1885) + 반응형 실측 (L1904) |
| `admin_schedules` | `/schedules`(관리자 DataScreen 대표) (L499) |

**그룹 B — `WF1`(미판독 화면 40개 병렬 판독, L2195-2394)의 화면별 표 행 — 35개.** 이 워크플로의
"High 7건"(L2218-2229) 표와 "채택 항목 전문(화면별 압축)"(L2340-2380) 표가 정확히 이 하네스의
route id를 행으로 써서 각 화면의 구체적 결함/확인을 적었다: `admin_ai-quotas` · `admin_announcements`
· `admin_approval-delegations` · `admin_approvals` · `admin_audit-anomalies` · `admin_backup` ·
`admin_departments` · `admin_documents` · `admin_feature-flags` · `admin_impersonation` ·
`admin_integration-detail` · `admin_job-detail` · `admin_maintenance` · `admin_notion-mapping` ·
`admin_offboarding` · `admin_org-tree` · `admin_organizations` · `admin_policies` ·
`admin_prompt-usage` · `admin_runner-detail` · `admin_runners` · `admin_templates` ·
`user_activity` · `user_board-post` · `user_ideas` · `user_my-stats` · `user_new-ticket` ·
`user_profile` · `user_search` · `user_search-empty` · `user_search-results` ·
`user_team-doc-detail`(SEC-10 자격증명 노출 발견이 바로 이 화면) · `user_team-docs-trash` ·
`user_team-tickets` · `user_unassigned`. 그중 `admin_job-detail`은 "작업 큐 상세 모달
실조작"(L593)에서, `user_new-ticket`은 "새 티켓 폼 실조작"(L628)에서 한 번 더 확인된다.

**그룹 C — 팀 공간 3화면 실조작(L604-613)**: `user_chat-rooms`(VIS-90이 지목한 빈 상태 품질
비교가 `/chat-rooms`를 직접 대상으로 한다).

**그룹 D — 로그인 화면 실브라우저 측정**: `public_login` — `PA-07`(다크 모드 미지원 확인,
BACKLOG.md L3317) + `PA-12`(비밀번호 표시 버튼 대비 4.449:1 실측, L3322). 둘 다 Chromium으로
실제 렌더된 로그인 페이지를 측정한 결과라 "판독"의 정의(실제 브라우저에서 렌더된 화면을 봤다)를
만족한다고 판단했다 — 다만 이 둘은 화면을 눈으로 "읽고 서술"한 VIS류 기록이 아니라 계산된
대비값·다크 클래스 유무를 측정한 기록이라는 점에서 그룹 A/B와 성격이 약간 다르다는 것을
밝혀 둔다.

</details>

### 15-5. 손대지 않고 남긴 진짜 공백 (원래 `S` = `-`였던 9라우트)

BACKLOG.md 전체에서 찾지 못했다 — 캡처는 있지만(§4의 신규 표에서 `C`는 `O`) 아무도 그 PNG를
서술한 기록이 없었다:

- `admin_workflows`·`admin_prompts`·`admin_policy-usage`·`admin_job-titles` — 흥미롭게도
  같은 파일(`authoring.js`/`automation.js`/`org.js`)의 형제 화면(`policies`·`prompt-usage`·
  `notion-mapping` 등)은 판독 기록이 있는데 이 넷만 없었다 — 표본이 화면군 단위가 아니라
  개별 화면 단위로 골라졌다는 뜻으로 읽힌다.
- `admin_notion-console`·`admin_llm-console`·`admin_mail` — system_admin 전용/등록 누락
  이력이 있는 화면들이라(`QAH-06`), 캡처 자체가 늦게 합류했고 아직 아무도 판독하지 않았었다.
- `user_chat-room-detail`·`user_game-room` — 시드 데이터가 없어 **오늘도 과거에도** 한 번도
  캡처된 적이 없다(캡처가 없으니 판독도 원천적으로 불가능하다).

**같은 날 나중에(7화면 시각 재점검 패스) 위 7개를 전부 `Read`로 직접 판독했다** —
`dist/ui-qa/converge-ai70/light/1920x1080/`의 스크린샷을 화면당 1장씩 열어 실제로 봤다. 6개는
깨끗했다(`admin_notion-console`은 이미 알려진 클로비-FAB 겹침 가족과 같은 종류라 새로 만들지
않음). `admin_mail`에서는 실제 결함을 하나 찾아 그 자리에서 고쳤다 — "최근 실패" 표의 "오류"
열이 `DataTable` 열 정의에 무의미한 `render`를 달고 있어 공용 말줄임 보호에서 빠졌고, 그 결과
표 폭을 혼자 다 먹어 옆의 진짜 중요한 "발생"(시각) 열이 `2026-0...`로 잘렸다(`PA-16`,
BACKLOG.md). 같은 검색으로 저장소 전체에서 같은 패턴 3곳을 더 찾아(`Offboarding.jsx`의
부서/직책/실행자 열) 함께 고쳤다. 7개 다 §3/§4 표의 `S`를 `O`로 올렸다.

남은 진짜 공백은 `user_chat-room-detail`·`user_game-room` **2개뿐**이다 — 시드 데이터가 없어
캡처 자체가 없고, 캡처가 없으니 판독도 원천적으로 불가능하다. 없는 근거를 있다고 하지 않고
`-` 그대로 뒀다.

### 15-6. 라우트 매핑이 애매했던 것 (그대로 결정하지 않고 남김)

- **`/search`(§2 사용자 콘솔, §3 관리자 "공유")** — ui_qa 라우트는 `user_search`/
  `user_search-results`/`user_search-empty` 셋뿐이고, 관리자 셸(`/admin#/search`)을 별도로
  캡처하는 route id는 하네스에 없다. §3의 `search(공유)` 행은 오늘 갱신에서 `user_search` 계열의
  값을 그대로 옮겨 적었다 — **컴포넌트가 같으니 콘솔 오류 여부는 같을 것**이라는 가정이지,
  관리자 셸에서 독립적으로 재확인한 것이 아니다.
- **`/notifications`(§2 사용자 콘솔)** — 이 표에서는 사용자 화면처럼 분류돼 있지만 `routes.py`
  주석대로 실제로는 `admin_notifications`(관리자 셸) 하나뿐인 라우트다. §2의 이 행과 §4의
  `notifications.js` 행은 **같은 캡처를 가리키는 두 개의 표 항목**이다.
- **§0 요약표의 "라우트" 합계(75)** — §2~§4 표의 실제 행 수 합은 71(1+25+17+28)인데 §0은
  기존 관례(사용자 콘솔을 26으로 표기하던 것)를 그대로 이어받고 관리자만 이번에 45로
  고쳐서 합이 어긋난다. 의도적으로 라우트를 새로 늘리거나 줄인 것이 아니라 **두 절이 원래부터
  다른 집계 기준(행 수 vs 개념적 route id 수)을 쓰고 있었다**는 뜻이다 — §0의 각주에 그대로
  적어 뒀다.

### 15-7. 재현 명령

```bash
# 위 4개 결과 파일을 직접 다시 요약하려면:
.venv/Scripts/python -c "
import json
for f in ['dist/ui-qa/converge-vis104-64-badge/results.json',
          'dist/ui-qa/converge-pa15-recheck/results.json',
          'dist/ui-qa/converge-pa15-4k/results.json',
          'dist/ui-qa/converge-sem02-remainder/results.json']:
    d = json.load(open(f, encoding='utf-8'))
    print(f, d['run']['label'], d['run']['themes'], d['run']['viewports'],
          {k: v for k, v in d['summary'].items() if v['fail']})
"
```

## 16. AI 채팅 신규 기능(재생성·삭제·피드백·전체 복사) + AI-16 러너 미러 삭제 (2026-08-16)

`AI-36`/`AI-68`(채팅 UX 기능 완성도 일부)와 `AI-16`(대화 삭제 시 러너 미러 정리)을 같은
연속 구간에서 구현했다. `dist/verify_chat_features_e2e.py`로 실제 Chrome(Playwright) E2E를
**두 차례** 실행했다: 1차(DBTX-02+SEC-38 통합 배포 직후)에서 채팅 전송 자체는 정상화됐지만
재생성이 **새로운, 별개의** 결함(`AI-71`, `message_id` 충돌)으로 실패하는 것을 직접 잡았다.
`AI-71`을 고치고 재배포한 뒤 2차 E2E에서 **9개 확인 중 8개 통과** — 유일한 실패는 `RESP-01`
(아래 별도 기록, 채팅 기능과 무관한 기존 항목).

| 기능 | 백엔드 | 프런트 | 테스트 근거 | Chrome E2E |
|---|---|---|---|---|
| 답변 재생성 | `POST /api/messages/{id}/regenerate` | `Chat.jsx`/`AssistantDrawer.jsx`의 재생성 아이콘(마지막 답변에만) | `test_chat_message_actions.py` 4건 + `message-thread-actions.test.jsx` 5건 + 신규 `test_chat_handler.py::test_regenerate_after_a_first_attempt_success_does_not_collide_with_the_old_reply`(실워커로 끝까지 확인) | **통과(2026-08-16, 2차)** — 1차 E2E가 `AI-71`을 발견 → 수정+재배포 → 2차 E2E에서 실제 새 답변 도착 확인(스크린샷: 2.9초만에 진짜 LLM 응답, `05_resp01_users_1024.png` 이전 `03_regenerated.png`) |
| 메시지 삭제 | `DELETE /api/messages/{id}` | 삭제 아이콘(양 화자) + `useConfirm()` 확인 대화상자 | `test_chat_message_actions.py` 4건 + `message-thread-actions.test.jsx` 4건, revert-to-verify(soft-delete 필터) | **통과(2026-08-16)** — 확인 대화상자 노출, 확인 클릭 후 실제로 메시지 수 감소까지 실측 |
| 피드백(👍/👎) | `PATCH /api/messages/{id}/feedback` | 어시스턴트 메시지의 피드백 아이콘 2개 | `test_chat_message_actions.py` 3건 + `message-thread-actions.test.jsx` 4건 | **통과(2026-08-16)** — 버튼 노출 + 클릭 후 `aria-pressed=true` 전환 실측 |
| 대화 전체 복사 | 해당 없음(순수 클라이언트) | `Chat.jsx` 헤더의 복사 아이콘 | 백엔드 없음 — `formatConversationText` 자체는 프런트 단위 시험 없음(단순 순수 함수, 리스크 낮다고 판단해 생략) | **부분 통과(2026-08-16)** — 버튼 노출만 확인, 클립보드 내용까지는 미확인(headless 브라우저 클립보드 권한 제약으로 이번 스크립트 범위 밖) |
| AI-16 러너 미러 삭제 | 러너 `POST /v1/assistant/context/delete` + 플랫폼 `notify_runner_conversation_deleted` | 해당 없음(대화 삭제 버튼은 기존 UI 그대로) | 러너 4건 + 플랫폼 6건, 양쪽 revert-to-verify. DBTX-02 후속으로 `delete_conversation`도 커밋 순서 수정(D-85) | **부분 검증 — 클릭까지 완주하지 못함, 다만 다른 근거는 충분히 강함.** `dist/verify_chat_features_e2e.py`로 대화 목록 서랍(`Chat.jsx`, 접히면 `inert`)을 열고 "대화 삭제: <제목>" 버튼까지는 찾았으나, 그 뒤 실제 클릭이 "Element is not visible"로 매번 실패(드로어 전개 애니메이션/행별 hover-reveal 타이밍으로 추정 — Playwright 스크립트 쪽 문제로 판단, 제품 결함 정황 없음). 시간 대비 실익이 낮다고 판단해 이 스크립트로는 더 안 판다. 대신: ① 같은 스크립트가 **메시지 삭제**(같은 확인 대화상자 UI 패턴)는 실제 클릭으로 이미 통과 ② 러너가 3.59.0으로 배포되고 healthz 200 확인됨 ③ `notify_runner_conversation_deleted`/`delete_conversation` 양쪽 코드 경로가 이미 10건의 단위/통합 시험 + revert-to-verify로 커버됨 — 이 셋을 근거로 낮은 잔여 위험으로 판단. 완전한 클릭 스루 확인은 다음 세션에서 스크립트를 고치거나(예: 서랍 전개 완료를 `waitForSelector`로 명시적으로 기다림) API 직접 호출 뒤 러너 로그 대조로 대체 가능 |

### 16-1. 콘솔 오류

두 차례 E2E 모두 `콘솔 오류 없음` 체크 통과(0건) — 새 버튼들이 콘솔 경고/오류 없이 렌더된다.

### 16-2. 1차 E2E가 실제로 잡은 결함 (AI-71, 이후 수정+재배포+재검증 완료)

재생성 버튼을 눌렀을 때 40초 안에 새 답변이 오지 않았다. 서버 로그 직접 확인 결과 n8n은
실제로 좋은 답변을 만들어 돌려줬는데 저장이 `IntegrityError: UNIQUE constraint failed:
messages.conversation_id, messages.message_id`로 거부되고 있었다 — DBTX-02와는 다른,
새로 발견된 결함이다. 상세: `docs/BACKLOG.md` AI-71, `docs/DECISIONS.md` D-89.

### 16-3. 2차 E2E의 유일한 실패 — RESP-01(채팅과 무관, 기존 미해결 항목)

이번 스크립트에 겸사겸사 추가한 `/users` 1024px 가로 넘침 재측정(`RESP-01`)이 여전히
실패한다(`scrollWidth=1123 clientWidth=1024, overflow=99px` — HOST-01/02/03의 `DataTable`
열 폭 기본값 수정 이후에도 그대로). 이 채팅 기능들과는 무관한, 이미 알려진 별도 항목이라
같이 고치지 않았다 — 상세는 `docs/BACKLOG.md` RESP-01.


---

## Product Audit Cycle `PA-20260816-120655-f103fb5b` — L축 Deep Design Audit이 드러낸 검증 공백

이 Cycle은 D-75가 신설한 L축(Deep Design Audit)을 처음 수행했고, 그 과정에서 **기존 QA가 재는
축 자체가 없던 것들**을 찾았다. 아래는 결함이 아니라 **검증 공백**이다 — 결함은
`BACKLOG.md` §PA2와 `docs/product-audit/PRODUCT_AUDIT_HANDOFF.md`에 있다.

| # | 공백 | 왜 지금까지 안 잡혔나 | 이번에 어떻게 쟀나 |
|---|---|---|---|
| 1 | **전 라우트 공통 셸 높이 예산** — 배너가 첫 화면의 몇 %를 먹는지 재는 검사가 없다 | 화면별 QA는 각 화면이 "열리는가"를 보지 검사 대상에 셸의 고정 비용이 들어가지 않는다. 26라우트 전부 동일한 값이라 **한 화면만 봐서는 이상해 보이지 않는다** | `probe_shell.py` — `[role=alert]` 중 `h1`보다 위에 있는 것들의 `y` 범위와 `h1`의 `y` |
| 2 | **125/150/175% Windows 배율** | `RESP-01`이 175%를 이미 알고 있었으나(그래서 이번 관측은 재확인) **정기 검사로는 돌지 않는다** — 6개 뷰포트를 매번 재는 절차가 없다 | `design_capture2.py` viewports[] — 6조건에서 `scrollWidth > clientWidth` |
| 3 | **넓은 폭의 본문 상한(max-width)** | 반응형 검사가 전부 "좁아지면 깨지는가"만 본다. **넓어지면 늘어나는가**는 아무도 안 봤다 — QHD/4K에서 활용률이 86.3 → 88.3 → 91.1%로 계속 오른다 | 같은 뷰포트 계측의 `main` 폭 / 뷰포트 폭 |
| 4 | **고정 요소와 본문 컨트롤의 겹침** | 시각 검사로는 놓치기 쉽고(겹쳐 보여도 위인지 아래인지 모른다) 자동 접근성 검사도 이 축을 안 본다 | `verify_fab.py` — 겹침 중심점에서 `document.elementFromPoint()` 히트테스트 |
| 5 | **테마별 대비 수치 기준** | 기존 O축이 "다크로 바뀌는가"만 확인한다. **바뀐 뒤 읽히는가**는 기준이 없었다 | `verify_dark.py` — 토글 후 두 테마 대비 계산(그라디언트 배경은 판정 제외) |
| 6 | **`prefers-color-scheme` 초기값** | 축 자체가 없었다. OS 다크 사용자가 첫 화면에서 무엇을 보는지 아무도 재지 않았다 | `color_scheme=dark` 컨텍스트로 로그인해 토글 전 `body` 배경 확인 |
| 7 | **화면당 기본 동작(primary) 존재/개수** | 버튼이 "있는가"는 재도 **위계**는 안 잰다. 그래서 primary 0개인 화면 14개와 primary 3개인 상세 모달이 동시에 존재해도 통과했다 | `design_capture*.py` — `MuiButton-contained` 개수 |
| 8 | **파괴적 동작의 시각 구분** | 확인 절차는 검증하나 **강조가 기본 동작과 같은지**는 안 본다. `/departments` 상세의 「삭제」가 「수정」과 같은 채운 버튼이다 | 상세 모달의 버튼 variant 수집 |
| 9 | **행 클릭 상세의 키보드 도달** | 행 「상세」 버튼이 있어서 지금은 문제가 없다. **`PA-RC-0023`이 그 버튼을 없애면 이 축이 즉시 필요해진다** — 없애기 전에 먼저 세워야 한다 | 아직 안 쟀다. 착수 전 필수 |
| 10 | **관리자 상세의 딥링크·새로고침·뒤로가기** | 관리자에 `:id` 라우트가 **없어서** 검증 대상이 아니었다. 사용자 콘솔은 검증돼 있다(`PA-F-052`) | `design_capture2.py` detail[] — 행 클릭 후 `urlBefore == urlAfter` |
| 11 | **미등록 URL 폴백 동작** | 축이 없었다. `/users/<uuid>`가 9초 뒤 대시보드로 조용히 가는 것을 이번에 처음 봤다 | `design_capture2.py` states[] — 350ms/9s 시계열 |
| 12 | **대시보드 정보 중복** | "지표가 보이는가"만 보고 **같은 수치가 몇 번 나오는가**는 안 본다. `3`이 3구역, `42.6%`·`0`이 각 2구역 | `probe_shell.py` dup 스캔 — (값, 라벨) 쌍 집계 |
| 13 | **Q축(같은 개념 = 같은 용어)** | 축 자체가 QA_COVERAGE에 없다. 어시스턴트만 이번에 쟀고(이름 4종) **나머지 개념은 미조사** | 육안 + 스크린샷 대조 |

### 이 공백들을 닫는 순서

`PA-RC-0016`~`0024` 구현이 `required_tests`에서 1~8·10~12를 회귀 검사로 편입하도록 계약돼 있다.
**9번은 예외로 선행 조건**이다 — 행 「상세」 버튼을 없애기 전에 키보드 도달 축을 먼저 세우지
않으면 접근성 회귀를 만들고도 못 잡는다. 13번은 다음 Audit Round의 대상이다.

### 이번 Cycle이 쓴 프로브 (재사용 가능)

```
var/product-audit/design_capture.py    # 레이아웃·타입 스케일·색 표면·CTA 수 + 스크린샷
var/product-audit/design_capture2.py   # 상세·모달·빈/오류/로딩 상태 + 6개 뷰포트/배율
var/product-audit/probe_shell.py       # 배너 높이·본문 시작 위치·중복 지표
var/product-audit/verify_nav.py        # 내비 스크롤 체인 + 클릭 도달
var/product-audit/verify_fab.py        # FAB elementFromPoint 히트테스트
var/product-audit/verify_dark.py       # 테마 토글 후 대비(그라디언트 배경 제외)
```

**스크린샷은 `var/product-audit/shots/`에 있고, 생성만 하고 넘어가면 이 축을 한 것이 아니다** —
`Read` 도구로 실제로 열어서 판정해야 한다. 이번 Cycle이 찾은 것 중 카드 40장·안내 4문단·
다크 흰 모달·배지 3열은 전부 **계측 수치가 아니라 화면을 보고** 나왔다.
