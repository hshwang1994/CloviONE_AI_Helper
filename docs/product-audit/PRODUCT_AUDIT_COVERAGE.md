# PRODUCT AUDIT — COVERAGE (Surface × Axis)

> cycle_id=PA-20260812-171558-56c5befa
>
> 이 문서는 `var/product-audit/gen_coverage.py`가 `coverage_state.json`에서 생성한다.
> 손으로 고치지 않는다 — 상태를 바꾸려면 state를 고치고 다시 생성한다.
> 그래야 아래 기계 요약 블록이 표와 절대 어긋나지 않는다.

## 상태 기호

| 기호 | 뜻 |
|---|---|
| `·` | UNSEEN — 아직 안 봄. **반드시 이유가 있어야 한다** |
| `S` | STATIC_ONLY — 코드/문서만 읽었다. 실행으로 확인하지 않았다 |
| `O` | OBSERVED — 실제 산출물/응답/렌더 결과를 봤다 |
| `E` | EXECUTED — 이 축을 실제로 실행해 검증했다(테스트·요청·브라우저) |
| `B` | BLOCKED — 이 환경에서 확인 불가. 이유를 적었다 |
| `-` | NOT_APPLICABLE — 이 Surface에 그 축이 없다. 이유를 적었다 |

## 축

| 축 | 이름 | 축 | 이름 |
|---|---|---|---|
| **A** | Baseline/Inventory | **N** | Responsive/DPI |
| **B** | Product Intent/Contract | **O** | Light/Dark |
| **C** | Functional CRUD | **P** | UX Writing |
| **D** | Workflow end-to-end | **Q** | Terminology |
| **E** | FE/API/BE/DB consistency | **R** | Korean naturalness |
| **F** | RBAC/Scope/State | **S** | Performance |
| **G** | Integration | **T** | Observability |
| **H** | Negative/Edge | **U** | Security behavior |
| **I** | Recovery/Retry/Idempotency | **V** | Deploy/Config/Migration/Health |
| **J** | Concurrency | **W** | Timezone/Schedule/Expiry |
| **K** | AI/Runner/Job | **X** | Dead/Stub/Orphan |
| **L** | UI/UX (redesign lens) | **Y** | Regression gap |
| **M** | Accessibility | **Z** | Documentation drift |

## user-console

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `U-HOME` 홈 (개인 대시보드) | `/me` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-SEARCH` 통합 검색 | `/search` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-MYTICKETS` 내 티켓 | `/my-tickets` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-UNASSIGNED` 미할당 티켓 | `/unassigned` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-NEWTICKET` 새 티켓 | `/new-ticket` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-TICKET` 티켓 상세 | `/tickets/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-TEAMTICKETS` 팀 티켓 | `/team-tickets` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-PROJECTS` 프로젝트 목록 | `/projects` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-PROJECT` 프로젝트 상세 | `/projects/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-SPRINT` 스프린트 회의 | `/sprint` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-CHAT` AI 도우미 대화 | `/chat` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-CHATROOMS` 채팅방 목록 | `/chat-rooms` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-CHATROOM` 채팅방 상세 | `/chat-rooms/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-BOARD` 자유게시판/기능 제안 | `/board, /ideas` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-BOARDPOST` 게시글 상세 | `/board/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-TEAMDOCS` 팀 문서 목록 | `/team-docs` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-TEAMDOC` 팀 문서 상세 | `/team-docs/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-TRASH` 휴지통 | `/team-docs/trash` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-GAMES` 놀이 목록 | `/games` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-GAMEROOM` 게임방 | `/games/:id` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-NOTIF` 알림 목록 | `/notifications` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-PROFILE` 내 프로필 | `/profile` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-MYSTATS` 내 업무량 | `/my-stats` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `U-ACTIVITY` 내 활동 | `/activity` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |

## admin-console

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `A-DASH` 관리자 대시보드 | `/dashboard` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-USERS` 사용자 관리 | `/users` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-OFFBOARD` 온보딩/오프보딩 | `/offboarding` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-SETTINGS` 설정 | `/settings` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-SETUP` 초기 설정 마법사 | `/setup` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-SYSTEM` 시스템 설정 | `/system` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-MAIL` 메일 발송 상태 | `/mail` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-NOTIONC` Notion 관리 | `/notion-console` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-LLMC` AI 관리 | `/llm-console` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-DIAG` 진단 | `/diagnostics` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-MAINT` 유지보수 | `/maintenance` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-DEVREP` 개발자 월간 리포트 | `/dev-report` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-SCHEDCAL` 실행 달력 | `/scheduler-calendar` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-ORG` 조직 콘솔(조직/부서/조직도) | `/organizations,/departments,/org-tree` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-JOBTITLES` 직책 관리 | `/job-titles` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-INTEG` 외부 연동 | `/integrations` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-RUNNERS` 러너 | `/runners` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-WORKFLOWS` 워크플로 | `/workflows` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-PROMPTS` 프롬프트 | `/prompts` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-POLICIES` 정책 | `/policies` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-TEMPLATES` 템플릿 | `/templates` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-PROMPTUSE` 프롬프트 사용 통계 | `/prompt-usage` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-POLICYUSE` 정책 사용 통계 | `/policy-usage` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-SCHEDULES` 실행 일정 | `/schedules` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-DOCGEN` 문서 자동 생성 | `/documents` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-JOBS` 작업 큐 | `/jobs` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-APPROVALS` 승인 | `/approvals` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-APPRDELEG` 승인 위임 | `/approval-delegations` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-AUDIT` 감사 로그 | `/audit` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-AUDITANOM` 감사 이상 징후 | `/audit-anomalies` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-RBAC` 권한 매트릭스 | `/rbac` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-IMPERSON` 대리 보기 | `/impersonation` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-NOTIONMAP` Notion 사용자 연결 | `/notion-mapping` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-BACKUP` 백업 | `/backup` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-RESTORE` 복구 리허설 | `/restore-drills` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-ANNOUNCE` 공지 배너 | `/announcements` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-QUOTAS` AI 사용 상한 | `/ai-quotas` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `A-FLAGS` 기능 플래그 | `/feature-flags` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |

## shell-cross

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `S-SHELL` AppShell / 사이드바 / 그룹 | `app/AppShell.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-TOPBAR` 상단바 / 세그먼트 탭 / 검색 | `app/AppShell.jsx, TopSearch` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-PALETTE` 커맨드 팔레트 (Ctrl+K) | `app/CommandPalette.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-BELL` 알림 벨 | `app/NotificationBell.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-ASSIST` AI 도우미 드로어 / FAB | `app/AssistantDrawer.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-BANNER` 전역 배너(공지/유지보수/셋업) | `app/Banners.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-SCOPE` 관리 범위 표시줄 | `app/ScopeBar.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-USERMENU` 사용자 메뉴 / 테마 토글 | `app/UserMenu.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-TOUR` 온보딩 투어 | `app/Tour.jsx` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-LOGIN` 로그인 / 핸드오프 / 비밀번호 재설정 | `/login, LoginHandoff` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-KIT` 공통 UI 키트 / 토큰 / 테마 | `ui/kit.jsx, ui/theme.js, styles/tokens.css` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |
| `S-DATASCREEN` 설정 주도 데이터 화면 엔진 | `screens/DataScreen.jsx + registry/*` | S | · | · | · | · | · | · | · | · | · | · | S | · | · | · | S | S | · | · | · | · | · | · | · | · | · |

## platform

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `P-AUTH` 인증 / 세션 / CSRF | `app/auth, app/core/sessions.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-RBAC` 역할 / 범위 / IDOR 경계 | `app/core/authz.py, scope.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-DB` DB 트랜잭션 / 무결성 / 동시성 | `app/core/db.py, alembic` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-JOBS` 작업 큐 / 워커 / 재시도 | `app/jobs, app/worker_main.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-AI` AI 대화 / 어시스턴트 / 쿼터 | `app/assistant, app/llm, app/quotas` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-RUNNER` Claude Runner 연동 | `runner/, app/runners` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-NOTION` Notion 연동 / 티켓 동기화 | `app/integrations, app/notion_*` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-N8N` n8n 워크플로 연동 | `app/workflows` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-MAIL` 메일 발송 | `app/mail` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-SEARCH` 검색 색인 | `app/search` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-BACKUP` 백업 / 복구 | `app/backups` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-AUDITLOG` 감사 로그 / 관측성 | `app/audit, app/observability` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-SCHED` 스케줄 / cron / 타임존 | `app/schedules, app/core/clock.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-DEPLOY` 배포 / 설정 / 헬스 | `deploy/, scripts/, app/health` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-FLAGS` 기능 플래그 | `app/core/feature_flags.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `P-UPLOAD` 첨부 / 업로드 / 스토리지 | `app/core/uploads.py` | S | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |

## UNSEEN / BLOCKED / NOT_APPLICABLE 사유

surface 단위 사유는 그 surface의 모든 UNSEEN 칸에 적용된다.

| 대상 | 사유 |
|---|---|
| `A-ANNOUNCE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-APPRDELEG` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-APPROVALS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-AUDIT` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-AUDITANOM` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-BACKUP` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-DASH` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-DEVREP` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-DIAG` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-DOCGEN` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-FLAGS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-IMPERSON` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-INTEG` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-JOBS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-JOBTITLES` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-LLMC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-MAIL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-MAINT` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-NOTIONC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-NOTIONMAP` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-OFFBOARD` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-ORG` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-POLICIES` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-POLICYUSE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-PROMPTS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-PROMPTUSE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-QUOTAS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-RBAC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-RESTORE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-RUNNERS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-SCHEDCAL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-SCHEDULES` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-SETTINGS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-SETUP` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-SYSTEM` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-TEMPLATES` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-USERS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `A-WORKFLOWS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-AI` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-AUDITLOG` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-AUTH` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-BACKUP` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-DB` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-DEPLOY` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-FLAGS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-JOBS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-MAIL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-N8N` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-NOTION` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-RBAC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-RUNNER` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-SCHED` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-SEARCH` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-UPLOAD` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-ASSIST` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-BANNER` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-BELL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-DATASCREEN` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-KIT` | L축: 토큰 계층(타이포/반지름/색/모션)을 실측 스캔으로 조사 완료(PA-RC-0001). 나머지 축은 Round 계획에 남아 있다. |
| `S-LOGIN` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-PALETTE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-SCOPE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-SHELL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-TOPBAR` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-TOUR` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-USERMENU` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-ACTIVITY` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-BOARD` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-BOARDPOST` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-CHAT` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-CHATROOM` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-CHATROOMS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-GAMEROOM` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-GAMES` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-HOME` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-MYSTATS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-MYTICKETS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-NEWTICKET` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-NOTIF` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-PROFILE` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-PROJECT` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-PROJECTS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-SEARCH` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-SPRINT` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-TEAMDOC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-TEAMDOCS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-TEAMTICKETS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-TICKET` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-TRASH` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `U-UNASSIGNED` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |

## Skill 적용 기록

| Skill 실제 이름 | 실제 경로 | 버전 | 이번 Cycle 적용 |
|---|---|---|---|
| `ui-ux-pro-max` | `.claude/skills/ui-ux-pro-max/SKILL.md` | (frontmatter에 version 없음) | L/M/N/O축 rubric — Round 2~ |
| `impeccable` | `.claude/skills/impeccable/SKILL.md` | 4.0.4 | L축 audit/critique 렌즈 — Round 2~ |
| `redesign-existing-projects` | `~/.claude/skills/redesign-existing-projects/SKILL.md` | (frontmatter에 version 없음) | L축 재설계 후보 도출 — Round 2~ (`.agents/skills/`가 아니라 사용자 스킬 경로로 이동해 있었다) |
| `ux-writing` | `~/.claude/skills/ux-writing/SKILL.md` | (frontmatter에 version 없음) | P축 — Round 3~ |
| `humanize-korean` | `~/.claude/plugins/cache/im-not-ai/humanize-korean/2.1.0/.claude/skills/humanize-korean/SKILL.md` | 2.1.0 | R축 — P축 뒤에 적용 |

    skill_gap: a11y-debugging — 미설치. 대체 방법=이 프롬프트 6절 내장 rubric + 코드 수준 aria/role/focus 정적 점검 + 기존 vitest a11y 계열 스위트(theme-focus-visible/route-change-focus/toast-announce 등) 실행. 신뢰도 영향=실제 스크린리더 낭독 순서와 대비비 실측은 못 한다 — M축 결론은 코드 근거까지만이고 색 대비는 토큰 값 계산으로 보완한다.
    skill_gap: frontend-design — 미설치(별도 스킬로는 없음). 대체 방법=ui-ux-pro-max + impeccable + redesign-existing-projects 세 개가 같은 축을 덮는다. 신뢰도 영향=없음으로 본다.
    skill_gap: chrome-devtools — 이 Audit Runner에는 브라우저 자동화 도구가 없다. 대체 방법=로컬 dev 서버(:8099) HTTP 응답 관찰 + vitest/jsdom 렌더 실행. 신뢰도 영향=실제 Chrome 렌더·콘솔·네트워크 관찰은 못 한다 — N/O축(고배율·실기기 렌더)은 코드 근거까지만이며 PHASE 2의 Chrome Whole-product E2E가 그 자리를 메운다.

## 이번 Cycle에서 각 상태가 실제로 뜻하는 것

- **A축 STATIC_ONLY** — 저장소 실측 스캔으로 Surface/엔드포인트/테이블/화면을 셌다. 실행 검증은 아니다.
- **L축 STATIC_ONLY** — 화면 전체에 대해 `fontSize`/`fontWeight`/`borderRadius`/하드코딩 색/빈·오류·로딩 상태 사용 여부를 코드로 전수 측정했다(`var/product-audit/scan_design.py`, `scan_states.py`). **개별 화면을 렌더해서 본 것은 아니다** — 프롬프트 6절 rubric 12항의 화면별 적용은 아직 남아 있다.
- **P/Q축 STATIC_ONLY** — 사용자 노출 한글 문자열 4,919회/2,847종을 전수 수집해 종결어미·용어·길이 분포를 측정했다(`scan_copy.py`). 화면에서 그 문구가 **어느 자리에** 뜨는지까지는 확인하지 않았다.

<!-- COVERAGE-SUMMARY
cycle_id=PA-20260812-171558-56c5befa
total_cells=2340
unseen=2028
unseen_without_reason=0
static_only=312
observed=0
executed=0
blocked=0
not_applicable=0
-->
