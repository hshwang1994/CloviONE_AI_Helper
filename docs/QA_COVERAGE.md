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

첫 실환경 캡처(`c1-admin`, role=admin, 70라우트 × 2테마 × 1920·3840, `--modals`)가 **진행 중**이다.
아래 표의 `S`/`V`는 그 결과가 나오면 채운다. 나머지 축(`F`·`A`·`D`·`C`·`L`·`R`)은 그 다음이다.

---

## 0. 전체 요약

| 구분 | 라우트 수 | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|
| 공개(로그인 전) | 4 | - | - | - | - | - | - | - | - |
| 사용자 콘솔 | 25 | - | - | - | - | - | - | - | - |
| 관리자 전용 화면 | 16 | - | - | - | - | - | - | - | - |
| 관리자 registry(DataScreen) | 28 | - | - | - | - | - | - | - | - |
| **계** | **73** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |

**기존 자동 검사 실적**(참고, 위 7축을 대체하지 않음): `scripts/ui_qa`가 2026-08-04에
62라우트 × 2테마 × 8뷰포트 = 992페이지를 21검사로 돌려 fail 0. 단 **MUI 작업·감사 라운드 8~14
이전**이고, 그 검사는 "안 깨졌는가"(overflow·콘솔오류·깨진이미지·중복id·세로붕괴 등)만 본다 —
정보 밀도·강조 수준·시선 흐름·공간 활용·화면 간 불일치는 판정하지 않는다.

---

## 1. 공개 (로그인 전)

| 라우트 | 화면 | S | F | A | D | C | R | L | V | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|
| `/login` | Jinja | - | - | - | - | - | - | - | - | ui_qa에 포함(`public_login`) |
| `/change-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |
| `/forgot-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함. **FN-01(메일 UI 없음)과 직결** |
| `/reset-password` | Jinja | - | - | - | - | - | - | - | - | ui_qa 미포함 |

## 2. 사용자 콘솔 (25)

| 라우트 | 화면 | ui_qa | S | F | A | D | C | R | L | V |
|---|---|---|---|---|---|---|---|---|---|---|
| `/me` | Home | O | - | - | - | - | - | - | - | - |
| `/my-tickets` | MyTickets | O | - | - | - | - | - | - | - | - |
| `/unassigned` | Unassigned | O | - | - | - | - | - | - | - | - |
| `/new-ticket` | NewTicket | O | - | - | - | - | - | - | - | - |
| `/tickets/:id` | Ticket | O | - | - | - | - | - | - | - | - |
| `/team-tickets` | TeamTickets | O | - | - | - | - | - | - | - | - |
| `/projects` | Projects | **없음** | - | - | - | - | - | - | - | - |
| `/projects/:id` | Project(+Metrics/Wbs/Weekly/Tickets) | **없음** | - | - | - | - | - | - | - | - |
| `/sprint` | Sprint | O | - | - | - | - | - | - | - | - |
| `/chat` | Chat | O | - | - | - | - | - | - | - | - |
| `/chat-rooms` | ChatRooms | O | - | - | - | - | - | - | - | - |
| `/chat-rooms/:id` | ChatRoom | O | - | - | - | - | - | - | - | - |
| `/board` | Board | O | - | - | - | - | - | - | - | - |
| `/board/:id` | BoardPost | O | - | - | - | - | - | - | - | - |
| `/ideas` | IdeaBoard | **없음** | - | - | - | - | - | - | - | - |
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
| `/system` | SystemOps(298줄) | **없음** | system_admin | - | - | - | - | - | - | - | - |
| `/setup` | SetupWizard(232줄) | **없음** | system_admin | - | - | - | - | - | - | - | - |
| `/notion-console` | NotionConsole(377줄) | **없음** | system_admin | - | - | - | - | - | - | - | - |
| `/llm-console` | LlmConsole(354줄) | **없음** | system_admin | - | - | - | - | - | - | - | - |
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

## 5. 상태 축 커버리지 (라우트와 직교)

| 상태 | 현황 |
|---|---|
| Empty | 미검증. 시드 데이터가 없어 재현 조건 자체를 안 만들었다 |
| Loading | 미검증 |
| Error | 미검증 |
| **Permission Denied** | 미검증. QA 계정이 system_admin 1종뿐이라 **재현 불가**였다 |
| 긴 텍스트 | 미검증 |
| 데이터 0건 | 미검증 |
| 데이터 대량 | 미검증(ticket_cache 1077행은 있으나 표별 대량 상태는 미확인) |
| 잘못된 입력 | 미검증 |

## 6. 역할 커버리지

| 역할 | 계정 | 상태 |
|---|---|---|
| system_admin | `ui-qa@goodmit.co.kr`(하네스 자동 생성), `hshwang@goodmit.co.kr` | 하네스가 쓰던 유일한 역할 |
| admin | — | **계정 없음** → 생성 예정 `qa-admin@` |
| operator | — | **계정 없음** → 생성 예정 `qa-operator@` |
| auditor | — | **계정 없음** → 생성 예정 `qa-auditor@` |
| user | — | **계정 없음** → 생성 예정 `qa-user@` |
| `admin_scope` dept/org/global | — | 전부 미검증 |

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
