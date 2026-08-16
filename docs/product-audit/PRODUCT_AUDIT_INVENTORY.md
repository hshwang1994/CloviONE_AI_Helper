# PRODUCT AUDIT — SURFACE INVENTORY

> cycle_id=PA-20260816-120655-f103fb5b · baseline=70e264bf13110e7e61cdf96331bd92de48f2163d
>
> 이 문서는 `var/product-audit/gen_inventory.py`가 저장소를 실제로 훑어 생성한다.
> 숫자는 생성 시점의 실측이다 — 손으로 고치지 않는다.

## 0. 규모 실측

| 항목 | 수 | 근거 |
|---|---|---|
| API 엔드포인트 데코레이터 | 312 | `app/**/*.py`의 `@router.<method>(...)` |
| API 모듈 | 42 | 위와 같음 |
| DB 테이블(`__tablename__`) | 69 | `app/**/*.py` |
| Alembic revision | 57 | `alembic/versions/*.py` |
| 프런트 화면 모듈(비테스트) | 115 | `frontend/src/screens/**` |
| 사용자 콘솔 라우트 | 26 | `frontend/src/app/UserRoutes.jsx` |
| 관리자 콘솔 명시 라우트 | 18 | `frontend/src/app/AdminRoutes.jsx` |
| 관리자 REGISTRY 화면 키 | 27 | `frontend/src/screens/registry/*.js` |

## 1. HTTP 메서드 분포

| Method | 수 |
|---|---|
| POST | 146 |
| GET | 128 |
| PATCH | 16 |
| DELETE | 16 |
| PUT | 6 |

## 2. 모듈별 엔드포인트

| 모듈 | 엔드포인트 |
|---|---|
| `app/tickets` | 21 |
| `app/projects` | 20 |
| `app/games` | 18 |
| `app/board` | 17 |
| `app/team_chat` | 17 |
| `app/profiles` | 16 |
| `app/users` | 16 |
| `app/team_docs` | 15 |
| `app/schedules` | 12 |
| `app/runners` | 11 |
| `app/auth` | 9 |
| `app/chat` | 9 |
| `app/integrations` | 9 |
| `app/prompts` | 9 |
| `app/workflows` | 9 |
| `app/notion_mapping` | 7 |
| `app/templates` | 7 |
| `app/backups` | 6 |
| `app/notifications` | 6 |
| `app/org` | 6 |
| `app/approvals` | 5 |
| `app/jobs` | 5 |
| `app/offboarding` | 5 |
| `app/quotas` | 5 |
| `app/settings` | 5 |
| `app/trash` | 5 |
| `app/admin` | 4 |
| `app/assistant` | 4 |
| `app/documents` | 4 |
| `app/health` | 4 |
| `app/impersonation` | 4 |
| `app/notion_console` | 4 |
| `app/audit` | 3 |
| `app/llm_console` | 3 |
| `app/home` | 2 |
| `app/mail` | 2 |
| `app/search` | 2 |
| `app/sysops` | 2 |
| `app/observability` | 1 |
| `app/reports` | 1 |
| `app/setup` | 1 |
| `app/sprints` | 1 |

## 3. Surface 목록 (Coverage 매트릭스와 1:1)

### 사용자 콘솔 (24)

| ID | Surface | 위치 |
|---|---|---|
| `U-HOME` | 홈 (개인 대시보드) | `/me` |
| `U-SEARCH` | 통합 검색 | `/search` |
| `U-MYTICKETS` | 내 티켓 | `/my-tickets` |
| `U-UNASSIGNED` | 미할당 티켓 | `/unassigned` |
| `U-NEWTICKET` | 새 티켓 | `/new-ticket` |
| `U-TICKET` | 티켓 상세 | `/tickets/:id` |
| `U-TEAMTICKETS` | 팀 티켓 | `/team-tickets` |
| `U-PROJECTS` | 프로젝트 목록 | `/projects` |
| `U-PROJECT` | 프로젝트 상세 | `/projects/:id` |
| `U-SPRINT` | 스프린트 회의 | `/sprint` |
| `U-CHAT` | AI 도우미 대화 | `/chat` |
| `U-CHATROOMS` | 채팅방 목록 | `/chat-rooms` |
| `U-CHATROOM` | 채팅방 상세 | `/chat-rooms/:id` |
| `U-BOARD` | 자유게시판/기능 제안 | `/board, /ideas` |
| `U-BOARDPOST` | 게시글 상세 | `/board/:id` |
| `U-TEAMDOCS` | 팀 문서 목록 | `/team-docs` |
| `U-TEAMDOC` | 팀 문서 상세 | `/team-docs/:id` |
| `U-TRASH` | 휴지통 | `/team-docs/trash` |
| `U-GAMES` | 놀이 목록 | `/games` |
| `U-GAMEROOM` | 게임방 | `/games/:id` |
| `U-NOTIF` | 알림 목록 | `/notifications` |
| `U-PROFILE` | 내 프로필 | `/profile` |
| `U-MYSTATS` | 내 업무량 | `/my-stats` |
| `U-ACTIVITY` | 내 활동 | `/activity` |

### 관리자 콘솔 (38)

| ID | Surface | 위치 |
|---|---|---|
| `A-DASH` | 관리자 대시보드 | `/dashboard` |
| `A-USERS` | 사용자 관리 | `/users` |
| `A-OFFBOARD` | 온보딩/오프보딩 | `/offboarding` |
| `A-SETTINGS` | 설정 | `/settings` |
| `A-SETUP` | 초기 설정 마법사 | `/setup` |
| `A-SYSTEM` | 시스템 설정 | `/system` |
| `A-MAIL` | 메일 발송 상태 | `/mail` |
| `A-NOTIONC` | Notion 관리 | `/notion-console` |
| `A-LLMC` | AI 관리 | `/llm-console` |
| `A-DIAG` | 진단 | `/diagnostics` |
| `A-MAINT` | 유지보수 | `/maintenance` |
| `A-DEVREP` | 개발자 월간 리포트 | `/dev-report` |
| `A-SCHEDCAL` | 실행 달력 | `/scheduler-calendar` |
| `A-ORG` | 조직 콘솔(조직/부서/조직도) | `/organizations,/departments,/org-tree` |
| `A-JOBTITLES` | 직책 관리 | `/job-titles` |
| `A-INTEG` | 외부 연동 | `/integrations` |
| `A-RUNNERS` | 러너 | `/runners` |
| `A-WORKFLOWS` | 워크플로 | `/workflows` |
| `A-PROMPTS` | 프롬프트 | `/prompts` |
| `A-POLICIES` | 정책 | `/policies` |
| `A-TEMPLATES` | 템플릿 | `/templates` |
| `A-PROMPTUSE` | 프롬프트 사용 통계 | `/prompt-usage` |
| `A-POLICYUSE` | 정책 사용 통계 | `/policy-usage` |
| `A-SCHEDULES` | 실행 일정 | `/schedules` |
| `A-DOCGEN` | 문서 자동 생성 | `/documents` |
| `A-JOBS` | 작업 큐 | `/jobs` |
| `A-APPROVALS` | 승인 | `/approvals` |
| `A-APPRDELEG` | 승인 위임 | `/approval-delegations` |
| `A-AUDIT` | 감사 로그 | `/audit` |
| `A-AUDITANOM` | 감사 이상 징후 | `/audit-anomalies` |
| `A-RBAC` | 권한 매트릭스 | `/rbac` |
| `A-IMPERSON` | 대리 보기 | `/impersonation` |
| `A-NOTIONMAP` | Notion 사용자 연결 | `/notion-mapping` |
| `A-BACKUP` | 백업 | `/backup` |
| `A-RESTORE` | 복구 리허설 | `/restore-drills` |
| `A-ANNOUNCE` | 공지 배너 | `/announcements` |
| `A-QUOTAS` | AI 사용 상한 | `/ai-quotas` |
| `A-FLAGS` | 기능 플래그 | `/feature-flags` |

### 셸 · 화면 공통 (12)

| ID | Surface | 위치 |
|---|---|---|
| `S-SHELL` | AppShell / 사이드바 / 그룹 | `app/AppShell.jsx` |
| `S-TOPBAR` | 상단바 / 세그먼트 탭 / 검색 | `app/AppShell.jsx, TopSearch` |
| `S-PALETTE` | 커맨드 팔레트 (Ctrl+K) | `app/CommandPalette.jsx` |
| `S-BELL` | 알림 벨 | `app/NotificationBell.jsx` |
| `S-ASSIST` | AI 도우미 드로어 / FAB | `app/AssistantDrawer.jsx` |
| `S-BANNER` | 전역 배너(공지/유지보수/셋업) | `app/Banners.jsx` |
| `S-SCOPE` | 관리 범위 표시줄 | `app/ScopeBar.jsx` |
| `S-USERMENU` | 사용자 메뉴 / 테마 토글 | `app/UserMenu.jsx` |
| `S-TOUR` | 온보딩 투어 | `app/Tour.jsx` |
| `S-LOGIN` | 로그인 / 핸드오프 / 비밀번호 재설정 | `/login, LoginHandoff` |
| `S-KIT` | 공통 UI 키트 / 토큰 / 테마 | `ui/kit.jsx, ui/theme.js, styles/tokens.css` |
| `S-DATASCREEN` | 설정 주도 데이터 화면 엔진 | `screens/DataScreen.jsx + registry/*` |

### 플랫폼 · 백엔드 · 운영 (16)

| ID | Surface | 위치 |
|---|---|---|
| `P-AUTH` | 인증 / 세션 / CSRF | `app/auth, app/core/sessions.py` |
| `P-RBAC` | 역할 / 범위 / IDOR 경계 | `app/core/authz.py, scope.py` |
| `P-DB` | DB 트랜잭션 / 무결성 / 동시성 | `app/core/db.py, alembic` |
| `P-JOBS` | 작업 큐 / 워커 / 재시도 | `app/jobs, app/worker_main.py` |
| `P-AI` | AI 대화 / 어시스턴트 / 쿼터 | `app/assistant, app/llm, app/quotas` |
| `P-RUNNER` | Claude Runner 연동 | `runner/, app/runners` |
| `P-NOTION` | Notion 연동 / 티켓 동기화 | `app/integrations, app/notion_*` |
| `P-N8N` | n8n 워크플로 연동 | `app/workflows` |
| `P-MAIL` | 메일 발송 | `app/mail` |
| `P-SEARCH` | 검색 색인 | `app/search` |
| `P-BACKUP` | 백업 / 복구 | `app/backups` |
| `P-AUDITLOG` | 감사 로그 / 관측성 | `app/audit, app/observability` |
| `P-SCHED` | 스케줄 / cron / 타임존 | `app/schedules, app/core/clock.py` |
| `P-DEPLOY` | 배포 / 설정 / 헬스 | `deploy/, scripts/, app/health` |
| `P-FLAGS` | 기능 플래그 | `app/core/feature_flags.py` |
| `P-UPLOAD` | 첨부 / 업로드 / 스토리지 | `app/core/uploads.py` |

## 4. 화면 모듈 크기 (상위 25 · 비테스트)

저장소 자체 규칙은 200~400줄 típ, 800 최대다(`~/.claude/rules/common/coding-style.md`).

| 줄 | 파일 | MUI import | kit import |
|---|---|---|---|
| 1146 | `frontend/src/ui/kit.jsx` | 30 | 0 |
| 1049 | `frontend/src/screens/MyTickets.jsx` | 19 | 1 |
| 981 | `frontend/src/screens/Users.jsx` | 10 | 1 |
| 826 | `frontend/src/screens/DataScreen.jsx` | 5 | 1 |
| 774 | `frontend/src/screens/Dashboard.jsx` | 4 | 2 |
| 693 | `frontend/src/app/AppShell.jsx` | 21 | 1 |
| 607 | `frontend/src/app/NotificationBell.jsx` | 8 | 1 |
| 597 | `frontend/src/screens/TeamDocs.jsx` | 7 | 1 |
| 591 | `frontend/src/screens/Board.jsx` | 5 | 1 |
| 589 | `frontend/src/screens/BoardPost.jsx` | 7 | 1 |
| 550 | `frontend/src/screens/ChatPane.jsx` | 12 | 1 |
| 531 | `frontend/src/screens/useChat.js` | 0 | 1 |
| 523 | `frontend/src/screens/Offboarding.jsx` | 8 | 1 |
| 520 | `frontend/src/ui/theme.js` | 1 | 0 |
| 509 | `frontend/src/screens/registry/governance.js` | 1 | 0 |
| 502 | `frontend/src/screens/Sprint.jsx` | 4 | 1 |
| 486 | `frontend/src/screens/Profile.jsx` | 7 | 1 |
| 479 | `frontend/src/screens/chat-helpers.js` | 0 | 0 |
| 458 | `frontend/src/screens/SchedulerCalendar.jsx` | 8 | 1 |
| 451 | `frontend/src/screens/Project.jsx` | 5 | 1 |
| 445 | `frontend/src/screens/registry/automation.js` | 0 | 0 |
| 443 | `frontend/src/screens/Games.jsx` | 9 | 1 |
| 419 | `frontend/src/screens/Home.jsx` | 6 | 1 |
| 413 | `frontend/src/screens/NotionConsole.jsx` | 3 | 1 |
| 393 | `frontend/src/screens/registry/authoring.js` | 0 | 0 |

## 5. 디자인 시스템 채택 실측

- 화면 모듈 115개 중 `@mui/*` 를 직접 들여오는 것 81개
- `ui/kit.jsx` / `ui/adminKit.jsx` 를 들여오는 것 70개
- 둘 다 69개, 둘 다 아닌 것 33개
- **둘 다 아닌 모듈은 전부 helper/config 모듈이고 시각 표면이 없다** — 즉 렌더되는 화면 중
  MUI 체계 밖에 남은 것은 0개다(2026-08-12 실측). `ui/kit.jsx`는 자체 구현이 아니라
  MUI 위의 얇은 래퍼다(`@mui` import 31개, export 26개).
- 비테스트 소스 전체의 인라인 `style={{...}}` 은 2건, `className=` 은 146건.

## 6. 정적 위생 스캔 결과 (CLAUDE.md §3 불변 규칙)

| 검사 | 결과 |
|---|---|
| FastAPI `async def` **라우트 핸들러** | **0건** — `async def` 15건은 예외 핸들러(`app/core/errors.py` 7)·미들웨어(`app/core/middleware.py` 3)·lifespan/exception_handler(`app/main.py` 1)와, `await request.json()` 이 필요해 어쩔 수 없이 코루틴인 body 추출 헬퍼 4개(`app/auth/router.py:210,230`, `app/auth/reset_router.py:72`, `app/schedules/router.py:657`). §3-1 준수 |
| `httpx` 직접 import | 1건 — `app/core/http_client.py` (단일 관문 그 자체, §3-2 준수) |
| naive `datetime.now()` / `utcnow()` | 0건 (§3-7 준수) |
| `.innerHTML =` | 0건 (§3-6 준수) |
| `dangerouslySetInnerHTML` | 2건 — 둘 다 "쓰지 않는다"고 적은 **주석** (실사용 0) |
| `window.alert/confirm/prompt` | 0건 — 57건 매치는 전부 앱의 `useConfirm()` 이었다 |
| `console.log/debug` | 0건 |
| `# TODO/FIXME/HACK/XXX` | 0건 |
| bare `except:` | 0건 |

> 위 6절은 **음성 결과도 증거다** — 흔한 결함 계열이 이미 닫혀 있으므로 이번 Audit은
> 제품/업무/UX 층위에서 파야 한다는 뜻이다.
