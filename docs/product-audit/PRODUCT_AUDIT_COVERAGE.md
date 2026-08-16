# PRODUCT AUDIT — COVERAGE (Surface × Axis)

> cycle_id=PA-20260816-100149-48671b72
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
| `U-HOME` 홈 (개인 대시보드) | `/me` | S | · | O | · | · | E | · | · | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | S |
| `U-SEARCH` 통합 검색 | `/search` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-MYTICKETS` 내 티켓 | `/my-tickets` | S | · | O | · | · | E | · | · | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `U-UNASSIGNED` 미할당 티켓 | `/unassigned` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-NEWTICKET` 새 티켓 | `/new-ticket` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-TICKET` 티켓 상세 | `/tickets/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-TEAMTICKETS` 팀 티켓 | `/team-tickets` | S | · | E | · | · | E | · | · | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-PROJECTS` 프로젝트 목록 | `/projects` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-PROJECT` 프로젝트 상세 | `/projects/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-SPRINT` 스프린트 회의 | `/sprint` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-CHAT` AI 도우미 대화 | `/chat` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-CHATROOMS` 채팅방 목록 | `/chat-rooms` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `U-CHATROOM` 채팅방 상세 | `/chat-rooms/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-BOARD` 자유게시판/기능 제안 | `/board, /ideas` | S | · | E | · | · | E | · | · | E | · | · | O | O | O | O | S | S | S | S | · | · | · | · | · | E | · |
| `U-BOARDPOST` 게시글 상세 | `/board/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-TEAMDOCS` 팀 문서 목록 | `/team-docs` | S | · | E | · | · | E | · | · | E | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `U-TEAMDOC` 팀 문서 상세 | `/team-docs/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-TRASH` 휴지통 | `/team-docs/trash` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-GAMES` 놀이 목록 | `/games` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-GAMEROOM` 게임방 | `/games/:id` | S | · | O | · | · | E | · | E | E | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-NOTIF` 알림 목록 | `/notifications` | S | · | O | · | · | E | · | · | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `U-PROFILE` 내 프로필 | `/profile` | S | · | O | · | · | E | · | · | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `U-MYSTATS` 내 업무량 | `/my-stats` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `U-ACTIVITY` 내 활동 | `/activity` | S | · | O | · | · | E | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |

## admin-console

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `A-DASH` 관리자 대시보드 | `/dashboard` | S | · | O | · | S | E | · | S | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | S |
| `A-USERS` 사용자 관리 | `/users` | S | · | E | · | S | E | · | E | E | · | · | O | O | O | O | S | S | S | S | · | · | · | · | · | E | S |
| `A-OFFBOARD` 온보딩/오프보딩 | `/offboarding` | S | S | O | S | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-SETTINGS` 설정 | `/settings` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-SETUP` 초기 설정 마법사 | `/setup` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-SYSTEM` 시스템 설정 | `/system` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-MAIL` 메일 발송 상태 | `/mail` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-NOTIONC` Notion 관리 | `/notion-console` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-LLMC` AI 관리 | `/llm-console` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-DIAG` 진단 | `/diagnostics` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-MAINT` 유지보수 | `/maintenance` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-DEVREP` 개발자 월간 리포트 | `/dev-report` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-SCHEDCAL` 실행 달력 | `/scheduler-calendar` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-ORG` 조직 콘솔(조직/부서/조직도) | `/organizations,/departments,/org-tree` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-JOBTITLES` 직책 관리 | `/job-titles` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-INTEG` 외부 연동 | `/integrations` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-RUNNERS` 러너 | `/runners` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-WORKFLOWS` 워크플로 | `/workflows` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-PROMPTS` 프롬프트 | `/prompts` | S | · | O | · | S | E | · | S | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `A-POLICIES` 정책 | `/policies` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-TEMPLATES` 템플릿 | `/templates` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-PROMPTUSE` 프롬프트 사용 통계 | `/prompt-usage` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-POLICYUSE` 정책 사용 통계 | `/policy-usage` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-SCHEDULES` 실행 일정 | `/schedules` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-DOCGEN` 문서 자동 생성 | `/documents` | S | S | O | S | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-JOBS` 작업 큐 | `/jobs` | S | · | O | · | S | E | · | S | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `A-APPROVALS` 승인 | `/approvals` | S | S | O | S | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-APPRDELEG` 승인 위임 | `/approval-delegations` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-AUDIT` 감사 로그 | `/audit` | S | · | E | · | S | E | · | S | E | · | · | O | O | O | O | S | S | S | · | · | · | · | · | · | E | · |
| `A-AUDITANOM` 감사 이상 징후 | `/audit-anomalies` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-RBAC` 권한 매트릭스 | `/rbac` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-IMPERSON` 대리 보기 | `/impersonation` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-NOTIONMAP` Notion 사용자 연결 | `/notion-mapping` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-BACKUP` 백업 | `/backup` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-RESTORE` 복구 리허설 | `/restore-drills` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-ANNOUNCE` 공지 배너 | `/announcements` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `A-QUOTAS` AI 사용 상한 | `/ai-quotas` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | S | · | · | · | · | · | E | · |
| `A-FLAGS` 기능 플래그 | `/feature-flags` | S | · | O | · | S | E | · | S | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | · | E | · |

## shell-cross

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `S-SHELL` AppShell / 사이드바 / 그룹 | `app/AppShell.jsx` | S | · | · | · | · | · | · | · | S | · | · | S | O | O | · | S | S | S | · | · | · | · | · | S | E | S |
| `S-TOPBAR` 상단바 / 세그먼트 탭 / 검색 | `app/AppShell.jsx, TopSearch` | S | · | · | · | · | · | · | · | S | · | · | S | O | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-PALETTE` 커맨드 팔레트 (Ctrl+K) | `app/CommandPalette.jsx` | S | S | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-BELL` 알림 벨 | `app/NotificationBell.jsx` | S | S | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-ASSIST` AI 도우미 드로어 / FAB | `app/AssistantDrawer.jsx` | S | O | · | · | · | · | · | · | S | · | · | O | O | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-BANNER` 전역 배너(공지/유지보수/셋업) | `app/Banners.jsx` | S | S | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-SCOPE` 관리 범위 표시줄 | `app/ScopeBar.jsx` | S | · | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | · | E | · |
| `S-USERMENU` 사용자 메뉴 / 테마 토글 | `app/UserMenu.jsx` | S | S | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-TOUR` 온보딩 투어 | `app/Tour.jsx` | S | · | · | · | · | · | · | · | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |
| `S-LOGIN` 로그인 / 핸드오프 / 비밀번호 재설정 | `/login, LoginHandoff` | S | · | O | O | · | · | · | · | S | · | · | O | O | O | O | S | S | S | · | · | · | · | · | S | E | S |
| `S-KIT` 공통 UI 키트 / 토큰 / 테마 | `ui/kit.jsx, ui/theme.js, styles/tokens.css` | S | S | · | · | S | · | · | S | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | S |
| `S-DATASCREEN` 설정 주도 데이터 화면 엔진 | `screens/DataScreen.jsx + registry/*` | S | · | · | · | S | · | · | S | S | · | · | S | S | · | · | S | S | S | · | · | · | · | · | S | E | · |

## platform

| Surface | 위치 | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `P-AUTH` 인증 / 세션 / CSRF | `app/auth, app/core/sessions.py` | S | · | · | · | · | E | S | · | · | S | · | · | · | · | · | · | · | · | S | S | E | · | S | · | E | S |
| `P-RBAC` 역할 / 범위 / IDOR 경계 | `app/core/authz.py, scope.py` | S | · | · | · | · | E | S | · | · | S | · | · | · | · | · | · | · | · | S | S | E | · | S | · | E | S |
| `P-DB` DB 트랜잭션 / 무결성 / 동시성 | `app/core/db.py, alembic` | S | · | · | · | · | · | S | · | · | E | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-JOBS` 작업 큐 / 워커 / 재시도 | `app/jobs, app/worker_main.py` | S | · | · | · | · | · | S | · | S | S | S | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-AI` AI 대화 / 어시스턴트 / 쿼터 | `app/assistant, app/llm, app/quotas` | S | · | · | · | · | · | S | · | · | E | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-RUNNER` Claude Runner 연동 | `runner/, app/runners` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-NOTION` Notion 연동 / 티켓 동기화 | `app/integrations, app/notion_*` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-N8N` n8n 워크플로 연동 | `app/workflows` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-MAIL` 메일 발송 | `app/mail` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-SEARCH` 검색 색인 | `app/search` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-BACKUP` 백업 / 복구 | `app/backups` | S | · | · | · | · | · | S | · | S | S | S | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-AUDITLOG` 감사 로그 / 관측성 | `app/audit, app/observability` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-SCHED` 스케줄 / cron / 타임존 | `app/schedules, app/core/clock.py` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-DEPLOY` 배포 / 설정 / 헬스 | `deploy/, scripts/, app/health` | O | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | O | S | O | S | · | E | S |
| `P-FLAGS` 기능 플래그 | `app/core/feature_flags.py` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |
| `P-UPLOAD` 첨부 / 업로드 / 스토리지 | `app/core/uploads.py` | S | · | · | · | · | · | S | · | · | S | · | · | · | · | · | · | · | · | S | S | · | · | S | · | E | S |

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
| `P-DEPLOY` | U축: 저장소 위생(stash 자격증명)을 조사해 PA-RC-0003 확정. 배포 스크립트/health/롤백 경로(V축)는 Round 계획에 남아 있다. |
| `P-FLAGS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-JOBS` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-MAIL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-N8N` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-NOTION` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-RBAC` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-RUNNER` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-SCHED` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `P-SEARCH` | S축은 부분 조사다 — 무제한 목록 후보 15건 중 1건(team_chat messages)만 검증했고 나머지 14건은 미확인. FINDINGS 'S축 — 미결로 남긴다' 절 참조. |
| `P-UPLOAD` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-ASSIST` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-BANNER` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-BELL` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-DATASCREEN` | 아직 이번 Cycle에서 조사하지 않음 — Round 계획에 남아 있다(PRODUCT_AUDIT_STATE.md '다음 조사 후보'). |
| `S-KIT` | L축: 토큰 계층(타이포/반지름/색/모션)을 실측 스캔으로 조사 완료(PA-RC-0001). 나머지 축은 Round 계획에 남아 있다. |
| `S-LOGIN` | L/M/N/O/C 축을 실제 Chromium 151 로 관측했다(로컬 dev :8099). 나머지 축은 Round 계획에 남아 있다. |
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
| `ui-ux-pro-max` | `.claude/skills/ui-ux-pro-max` | scripts/search.py (ux/web/react 도메인) | L·M축. `--domain ux`가 준 **Heading Hierarchy**(Do: sequential h1-h6 / Don't: skip levels **or misuse for styling**, Severity Med)와 `--domain web`·`--stack react`의 **Use semantic HTML before ARIA**(Severity High)를 PA-RC-0012 판정 기준으로 사용. 이 규칙이 결함의 실패 모드(스타일 목적의 heading 오용)를 그대로 지목한다 |

    skill_gap: chrome-devtools — 미설치. 대체=Playwright + Chromium 직접 구동(sweep_all.py / probe_a11y.py). 신뢰도 영향: 없음에 가깝다 — DevTools 프로토콜로 얻을 콘솔·네트워크·DOM 계측을 Playwright 이벤트(response/console/pageerror/requestfailed)로 동등하게 얻었고, 이번 Cycle은 오히려 이전 Cycle이 놓쳤던 HTTP 4xx/5xx 응답까지 포착했다.
    skill_gap: a11y-debugging — 미설치. 대체=probe_a11y.py 로 heading outline·label 연결·landmark·positive tabindex·focus ring 을 브라우저에서 직접 계측. 신뢰도 영향: 자동 규칙 엔진(axe 등)이 주는 넓은 규칙 목록은 못 얻었다 — 이번에 판정한 것은 측정한 축뿐이고, 측정하지 않은 WCAG 항목은 COVERAGE 에서 M축 OBSERVED(=구조 계측)로만 표기하고 EXECUTED 로 올리지 않았다.

## 이번 Cycle에서 각 상태가 실제로 뜻하는 것

- **A축 STATIC_ONLY** — 저장소 실측 스캔으로 Surface/엔드포인트/테이블/화면을 셌다. 실행 검증은 아니다.
- **L축 STATIC_ONLY** — 화면 전체에 대해 `fontSize`/`fontWeight`/`borderRadius`/하드코딩 색/빈·오류·로딩 상태 사용 여부를 코드로 전수 측정했다(`var/product-audit/scan_design.py`, `scan_states.py`). **개별 화면을 렌더해서 본 것은 아니다** — 프롬프트 6절 rubric 12항의 화면별 적용은 아직 남아 있다.
- **P/Q축 STATIC_ONLY** — 사용자 노출 한글 문자열 4,919회/2,847종을 전수 수집해 종결어미·용어·길이 분포를 측정했다(`scan_copy.py`). 화면에서 그 문구가 **어느 자리에** 뜨는지까지는 확인하지 않았다.

## 실행 증거 (EXECUTED 칸의 근거)

**2026-08-15 프런트 전체 회귀 실행** — `cd frontend && npm test -- --run` → **테스트 파일 253개 전부 통과, 실패 0, exit 0, 111초**(로그: `var/product-audit/vitest.log`).

이 실행이 뒷받침하는 것과 아닌 것을 구분한다.
- **뒷받침한다**: 프런트 화면/셸의 기존 계약이 지금 이 워킹트리에서 실제로 성립한다(Y축 EXECUTED). 워킹트리에는 사용자의 미완성 변경 5개가 섞여 있는데 **그 상태에서도 253개가 전부 통과**했다.
- **뒷받침하지 않는다**: 테스트가 *충분한가*는 다른 질문이다. 통과는 '기존 계약이 안 깨졌다'만 말하고, PA-RC-0001·0002가 지적한 결함(토큰 미소비, 회복 경로 없는 오류 문구)은 **어떤 테스트도 검사하지 않기 때문에 통과한다.** 즉 이 green은 두 RC의 반증이 아니라 오히려 **회귀 공백의 증거**다.

## 실행 증거 2 — 백엔드

**2026-08-15 백엔드 회귀·보안 스위트 실행** (로그: `var/product-audit/pytest_regression.log`)

| 스위트 | 결과 |
|---|---|
| `pytest tests/regression` | **331건 전부 통과 · exit 0** |
| `pytest tests/security` | **498건 전부 통과 · exit 0** |

> **정직한 단서**: `-q` 출력에 요약 줄이 남지 않아 건수는 진행 표시의 점 개수로 셌다(4×72+43=331, 6×72+66=498). 판정의 근거는 개수가 아니라 **exit 0**이다 — pytest는 수집된 테스트가 하나라도 실패하면 0을 반환하지 않는다.
>
> 앞선 두 세션이 `docs/WORK_STATE.md`에 '백엔드 전체 회귀가 끝나지 않는다/멈춘 것 같다'고 남겼는데, **이번에 끝까지 돌려 확인한 결과 행(hang)이 아니라 그냥 오래 걸리는 것이었다.** 그 기록은 정정돼야 한다(Z축 항목).

이 실행이 뒷받침하는 것과 아닌 것:
- **뒷받침한다**: RBAC/scope/보안 경계(F·U축)의 기존 계약이 실제로 성립한다. 보안 스위트 498건이 실행 증거다.
- **뒷받침하지 않는다**: `PA-RC-0003`(stash 평문 자격증명)은 저장소 위생 문제라 어떤 테스트도 보지 않는다. 이 green과 무관하게 열려 있다.

## OBSERVED 칸의 근거와 그 한계

**2026-08-15 승인된 TEST 서버(`cloviradmin@10.100.64.71`) 실관측.** 서비스 3종 active · 앱 `127.0.0.1:8080`(uvicorn --workers 1) · nginx 443 · `/healthz` ok · `/readyz` ready · 미인증 루트 303→`/login`.

> **이 서버발 증거에는 단서가 붙는다.** 배포본은 **2026-08-10 빌드**이고 그 이후 `app/`·`frontend/`를 건드린 커밋이 **131개**다. 번들 asset 34개 중 내용 해시가 저장소와 같은 것은 **4개뿐**이다. 그러므로 이 서버에서 브라우저로 본 것은 **현재 코드가 아니라 08-10 빌드의 동작**이며, L/M/N/O축 결론을 현재 코드에 그대로 귀속시킬 수 없다. 상세는 `PA-RC-0007`.
>
> 이것이 `P-DEPLOY`만 OBSERVED이고 화면 surface들은 아직 OBSERVED가 아닌 이유다 — 낡은 빌드를 보고 현재 화면을 판정하면 그 Finding 자체가 틀린다.

## 동시성(J축) 실행 증거와 그 한계

`tests/integration` 의 race 계열 5개 파일을 실행했다 — `test_notion_mapping_get_or_create_race` · `test_prompt_create_new_version_race` · `test_quota_toctou` · `test_trash_move_race` · `test_health_snapshot_job`.

**결과: 통과가 아니다.** `test_prompt_create_new_version_race` 가 격리 실행 5회 중 **2회 실패**했다(`OperationalError: database is locked`, 처리되지 않고 500). 상세는 `PA-RC-0008`.

> **이 칸을 EXECUTED로 적는 이유**: 실제로 돌려서 결과를 얻었기 때문이다. EXECUTED는 '통과했다'가 아니라 '실행으로 확인했다'는 뜻이다.
>
> **race 테스트는 1회 실행으로 판정할 수 없다.** 이번 건도 약 60%는 통과했다 — 한 번만 돌렸다면 '이상 없음'으로 기록했을 것이다. 이 축의 후속 검증은 반드시 반복 실행으로 한다.

## Y축 — 전체 회귀의 실제 상태

**백엔드 2,903건 전부 실행·통과를 확인했다** (청크 분할 전경 실행, 2026-08-15).

| 디렉터리 | 테스트 | 실행 | 결과 |
|---|---:|---|---|
| `tests/regression` | 331 | 전경 단독 | EXIT=0 |
| `tests/security` | 498 | 전경 단독 | EXIT=0 |
| `tests/unit` | 761 | 전경 단독 | EXIT=0 |
| `tests/integration` | 1,313 | 전경 4청크 | 4청크 모두 EXIT=0 |
| 프런트 `npm test` | 1,718 | 단일 | 111초, 전부 통과 |

> **단일 호출로는 여전히 완주 못 한다**(45분+, 두 번 다 세션 경계에서 잘림). 청크로 나누면 각 10분 이내다. 상세와 정정 경위는 `PA-RC-0009`.
>
> **그래도 flaky 1건이 남는다** — `test_prompt_create_new_version_race`는 격리 5회 중 2회 실패인데 이번 chunk3에서는 통과했다. 그것이 flaky의 정의이고, **1회 green을 근거로 삼으면 안 된다는 실례**다(`PA-RC-0008`).

## 브라우저 관측 환경 (왜 로컬인가)

화면 OBSERVED 증거는 **로컬 dev 서버(`:8099`)** 에서 얻었다. TEST 서버(`10.100.64.71`)가 아니다.

이유는 `PA-RC-0007` 이다 — TEST 서버 배포본은 **2026-08-10 빌드**이고 그 뒤 `app/`·`frontend/` 커밋이 131개다. 거기서 화면을 보고 판정하면 **현재 코드가 아닌 것에 대한 Finding** 이 된다. 로컬은 현재 백엔드 + 2026-08-13 커밋 번들이라 훨씬 가깝다.

도구: Python Playwright + Chromium **151.0.7922.34** (실행 확인함). `skill_gap: chrome-devtools` 는 이제 **해소됐다** — 브라우저 관측이 실제로 가능하다.

> 다만 로컬도 완전한 현재가 아니다 — 번들은 마지막 빌드 커밋 시점이다.

**2026-08-15 갱신**: 인증 이후 화면도 관측했다 — SPA 화면 **12개**를 Chromium 151로 실측했고(`PA-F-028`~`033`, `036`~`038`), 다크·Windows 배율(125/150/175%)·WCAG 대비 227요소·목록 조작(페이지네이션·검색·필터)까지 포함한다. **다만 12/90 표면이라 전수는 아니다** — 나머지 화면의 L/M/N/O축은 여전히 코드 근거까지다.

## 인증 이후 화면 관측 (2026-08-15)

로컬 dev `:8099` + Chromium 151로 **로그인 이후 화면 11개**를 실측했다(사용자 6 + 관리자 5). QA 계정 2개를 dev DB에 **추가**했다(기존 데이터 무수정, 비밀번호는 메모리→stdin 전용).

**L/M/N/O를 OBSERVED로 올린 근거**: 화면별 렌더된 글자 크기·굵기·radius 분포, 제목 계층, 랜드마크, 콘솔/네트워크, 그리고 390~3840px 반응형을 실제로 측정했다.

> **한계 두 가지를 같이 적는다.**
> 1. **처음 반응형 검사가 1024px를 건너뛰었다** — 하필 `RESP-01`이 깨진다고 적어 둔 폭이다. 다시 재서 `/users`의 overflow를 확인했다(`PA-F-030`). **관측 폭을 고를 때 기존 Backlog가 지목한 폭을 먼저 넣어라.**
> 2. **번들은 2026-08-13 커밋 시점**이다. 그 이후 프런트 변경은 이 관측에 반영되지 않았다.

## 측정하려다 실패한 것 (CTR 대비)

**4차에서 성공했다.** 앞선 세 번의 실패와 각 원인은 `PA-F-034`·`PA-F-035`에 남겼다.

| 시도 | 방법 | 결과 |
|---|---|---|
| v1 | 계산 스타일로 조상의 불투명 배경 찾기 | 실패 — 그라데이션 통과, 화면당 8건 오탐 |
| v2 | 요소 스크린샷 최빈 색 2개를 fg/bg | 실패 — 그라데이션 위에선 최빈 2색이 배경의 인접 두 명암 |
| v3 | fg=CSS color, bg=fg에서 먼 최빈 픽셀 | 부분 — 판정률은 올랐으나 `/me`가 scrim 오염 + 공간 짝짓기 미검증 |
| **v4** | **오버레이 닫고 + 글자 bounding box 안에서만 배경 채집** | **성공 — 화면 4개 227요소 판정, 미달 1건** |

**결과: 대비는 대체로 건강하다.** 유일한 미달은 상단바 아바타 이니셜(3.41/4.5)이고 앱 셸이라 전 화면 공통이다. `DS-33`(배지 대비)과 같은 계열이라 새 RC 없이 그 행에 붙인다.

> **한계**: 후보 356 중 120은 글자 픽셀을 못 잡아 판정 제외했다(아주 작거나 아이콘 폰트거나 배경과 색이 겹침). '미달 1건'은 **판정 가능한 227개 기준**이며 전수가 아니다.
>
> **harness 오탐 정정**: '남은 backdrop 1'은 `opacity:0; visibility:hidden`인 드로어 backdrop 이었다 — 크기만 보고 세서 안 보이는 걸 남았다고 셌다. 측정은 가려지지 않았다.

## F축 — 행동으로 검증됨 (Blind pass 2)

`auditor` 역할 계정을 만들어 **세 계층이 같은 답을 내는지** 실제 요청으로 확인했다.

| 계층 | 결과 |
|---|---|
| 사이드바(보이는가) | 관리자 세그먼트에서 **29항목**, 차단 대상 8개는 **정확히 빠져 있다** |
| 라우트 게이트(직접 URL 진입) | 차단 대상 8개 **전부 차단**(h1 없음, 거부 표시, 0행) |
| **API(세션 쿠키 동반 직접 호출)** | `/api/admin/users` **403** · `/api/admin/offboarding` **403** · audit·backups·settings·dev-monthly **200** |

프롬프트 F축이 지목한 *"UI에서 버튼을 숨기는 것과 실제 API authorization을 구분한다"* 를 통과한다 — **버튼을 숨기는 것에 의존하지 않는다.** `FC-05`가 정적 대조로 주장한 것이 실제 요청으로 확인됐다.

## Z축 — 문서 드리프트 (이번 Cycle에 실제로 찾은 것)

Z축은 별도 Round 없이 다른 축을 파는 내내 나왔다. 확인된 드리프트:

| 발견 | 상세 |
|---|---|
| `PA-RC-0006` | `WORK_STATE`가 백엔드 회귀를 '진짜 행(hang)'이라 기록 — **사실이 아니다.** 그 오기록 때문에 세 사이클 동안 전체 회귀가 미검증으로 남았다 |
| `PA-RC-0011` | 실행 중인 제품 이름은 **ClovirAssist**(페이지 title·메일 제목·branding 기본값)인데 문서 13개는 **ClovirONE**이고 ClovirAssist는 0회 |
| `PA-F-038` | `RESP-03`(768 상단바 라벨 붕괴)이 재현되지 않는다 — 자기모순 행 후보 |
| `PA-F-030` | `RESP-04`의 수치가 낡았다 — 기록 180px/18% vs 실측 **264px/26%** |
| `PA-F-030` | `RESP-01`의 조건이 너무 넓다 — '관리자 표 화면' 전부가 아니라 **열 많은 표(`/users`)만** |
| Round 0 | `CLAUDE.md` §2는 Python **3.12**라 적는데 `.venv`는 **3.11.9** |
| 이 Audit 자신 | 내 중복 기준선도 틀렸었다(prefix 41종/552행을 DS/VIS/RN/IA만으로 셌다) — 같은 계열의 드리프트다 |

> 이 저장소는 `SEC-12/13`·`FN-02`·`RG-04`·`ADM-03`에서 '이미 고쳐졌는데 행만 안 갱신' 패턴을 반복해 찾아 왔다. **이번 Cycle에서도 같은 계열이 5건 더 나왔다** — 그 패턴은 아직 수렴하지 않았다.

## C축 — 목록 조작 실측 (읽기 전용)

필터·정렬·페이지네이션·검색을 **실제로 조작**했다(전부 GET 기반 읽기 전용 — 생성·수정·삭제·승인은 제품 상태를 바꾸므로 Auditor 범위 밖).

| 조작 | 결과 |
|---|---|
| 페이지네이션 `/audit` | `#/audit` → **`#/audit?page=2`**, 첫 행이 2026-08-15 → 2026-08-12로 바뀜 ✓ |
| 검색 `/unassigned` | `#/unassigned?q=%EC%84%A4%EA%B3%84`, **25행 → 2행** ✓ |
| 분류 필터 `/board` | `#/board?category=...`, 5행 → 0행(해당 분류 글이 없음) ✓ |

**목록 상태(page·q·category)가 일관되게 URL 해시에 실린다** — 딥링크가 성립한다. 이 제품이 알림 딥링크를 쓰는 것과 맞물리는 성질이다.

**나머지 화면의 C축이 `STATIC_ONLY`인 근거**: 관리자 화면 28개의 CRUD·필터·정렬은 **개별 화면이 아니라 설정으로 정의된다** — `screens/registry/actions.js`(`onoff`·`activeToggle`·`versionsAction`)와 도메인 파일 7개, 그리고 `DataScreen.jsx`(`filters` 24참조·`columns` 14·`headerActions` 7)를 읽었다. 즉 **엔진과 설정을 읽은 것**이지 화면 28개를 각각 조작한 것이 아니다. 사용자 콘솔 11화면은 Blind pass 1에서 버튼·표·빈 상태를 관측했다.

> **미검증(결함 아님, 확인 못 함)**: 열 머리글 **정렬**과 `/audit`의 select 필터는 내 범용 선택자로 변화를 만들지 못했다. 그 표가 정렬 불가일 수도, 별도 적용 동작이 필요할 수도 있다 — **판정하지 않는다.**

<!-- COVERAGE-SUMMARY
cycle_id=PA-20260816-100149-48671b72
total_cells=2340
unseen=1330
unseen_without_reason=0
static_only=611
observed=218
executed=181
blocked=0
not_applicable=0
-->
