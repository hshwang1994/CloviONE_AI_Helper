# ARCHITECTURE — 시스템 구조

ClovirONE Web Assistant는 기존 n8n 기반 AI 업무 도우미를 손상 없이 확장하는
사내 웹 플랫폼이다. FastAPI(sync 핸들러) + SQLAlchemy 2.0 + SQLite(WAL) 단일 서버
구성이며, 기본값은 웹 프로세스와 백그라운드 Worker 프로세스 두 개다. **D-118(2026-08-17)
이후로는 Worker가 하나의 레인(기존 동작, 기본값)이거나 배치/대화형 두 레인으로 나뉜
별도 프로세스 두 개(옵션, 기본 꺼짐)일 수 있다** — 아래 참고.

## 프로세스 구성

| 프로세스 | 진입점 | 역할 |
|---|---|---|
| Web (uvicorn) | `app.main:create_app` (--factory) | HTTP API + React SPA 셸 서빙, 127.0.0.1:8080 |
| Worker (배치 레인) | `python -m app.worker_main` (`--lane batch`, 기본값) | Job 큐 소비 + Scheduler tick(15개) + 승인 만료 스윕 + 보존 정리 + heartbeat. `worker_conversational_lane_enabled=true`면 `chat_message`/`llm_connection_test`는 이 레인이 클레임하지 않는다(아래 대화형 레인이 가져간다) |
| Worker (대화형 레인, 옵션) | `python -m app.worker_main --lane conversational` | `worker_conversational_lane_enabled=true`일 때만 리스를 잡고 실제로 동작(꺼져 있으면 유닛이 떠 있어도 즉시 정상 종료). `chat_message`/`llm_connection_test`만 처리, tick 콜백 0개, 스레드풀 동시성(`worker_conversational_concurrency`, 기본 3) — 배치 레인의 65분(3900초) 기본 stuck-job 타임아웃 대신 짧은 전용 타임아웃(`worker_conversational_running_timeout_seconds`, 기본 840초)을 쓴다. systemd 유닛은 `clovirone-web-worker-conversational.service`(배치는 `clovirone-web-worker.service`). 상세: `docs/DECISIONS.md` D-118~D-125, `app/jobs/lanes.py` |
| Nginx | `deploy/nginx/clovirone-web-assistant.conf` | 10.100.64.71:443 TLS 종단 → 127.0.0.1:8080 프록시 |

대화형 레인이 왜 있는가: 기본(단일 레인) 구성에서는 스케줄 실행 같은 장시간 배치
Job이 워커의 유일한 슬롯을 쥐고 있는 동안 전 사용자 채팅이 큐에서 대기해야 했다
(`jobs/repository.claim_next`가 `job_type` 우선순위 없는 순수 FIFO라서). 대화형 레인은
그 슬롯을 물리적으로 분리해, 배치 워커가 완전히 멈춰 있어도 채팅은 독립적으로
계속 처리되게 한다(TEST SERVER에서 배치 워커를 실제로 내린 채로 실측 확인함).

## App Factory

`app/main.py`의 `create_app(settings, clock, outbound_transport)`가 유일한 조립 지점이다.

- `settings`: `app.core.config.Settings` (pydantic-settings, 환경변수/web.env, spec §28)
- `clock`: `Clock` 인터페이스 — 테스트는 FakeClock으로 시간을 주입
- `outbound_transport`: httpx transport 주입 — 테스트는 FakeHTTP로 아웃바운드를 가로챔

factory는 `app.state`에 공유 자원을 올린다: engine/session_factory, `SessionService`,
로그인 `RateLimiter`(IP당 약 10회/분), `AllowlistRegistry`, `FileSecretReferenceProvider`,
`SettingsCache`, `OutboundClient`, Jinja2 templates. OpenAPI/docs 엔드포인트는 비활성.

## 프런트엔드

사용자/관리자 콘솔은 **React 18 + Vite SPA(HashRouter)**다. 소스는 `frontend/`,
빌드 산출물은 `app/static/react/`(index.html + assets)이며, `admin/router.py`가
`FileResponse`(no-store)로 SPA 셸을 서빙하고 인증은 이 라우트가 서버측에서 게이팅한다.
런타임 외부 CDN/폰트/네트워크는 CSP `script-src 'self'`로 금지 — npm은 빌드에만 쓴다.
`app/static/js`에는 login/change_password/theme 세 개만 남은 소규모 바닐라 JS다.

## 모듈 배치

`app/` 아래 기능(도메인) 단위 모듈. 각 모듈은 필요에 따라
`router.py / service.py / repository.py / schemas.py / models.py`를 가진다.

```
app/
├── core/          # 횡단 인프라 (아래 표)
├── auth/          # 로그인/로그아웃/비밀번호 변경, UserSession 모델
├── users/         # 계정 CRUD + 서비스 계층 (web API와 CLI가 공유)
├── profiles/      # /api/me, /api/profile
├── chat/          # 대화/메시지 API, Job enqueue
├── conversations/ # Conversation/Message 모델
├── jobs/          # Job 큐 (repository=원자적 claim, worker=디스패치, handlers/)
├── schedules/     # Schedule/ScheduleRun, cron 평가, SchedulerService
├── approvals/     # 승인 워크플로 + 실행기(executor) 레지스트리
├── integrations/  # Integration Registry + discovery 시드
├── runners/       # Runner Registry + circuit breaker + HTTP Provider
├── workflows/     # n8n Workflow Registry + n8n Provider
├── prompts/       # Prompt/Policy 버전 수명주기 (공유 service)
├── templates/     # Automation Template
├── documents/     # 문서 자동화 (§19) + 품질 게이트
├── notion_mapping/# 이메일→Notion People 매핑 (§12)
├── notifications/ # 인앱 알림
├── settings/      # 설정 레지스트리(허용 목록) + 유지보수 모드 gate
├── org/           # 부서(Department) / 직책(JobTitle)
├── tickets/       # 티켓(요청) — 리치 본문, Notion write
├── team_docs/     # 문서 탭 — Notion "문서" DB 미러링/동기화 + 분류(taxonomy)
├── board/         # 자유게시판 — 글/댓글/반응/첨부(이미지·PDF)
├── games/         # 팀 공간 놀이 7종(폴링 실시간) + AI 퀴즈 생성(ai.py)
├── reports/       # 개발자 월간 리포트
├── audit/         # 감사 로그 조회
├── backups/       # SQLite 백업/검증
├── health/        # healthz/readyz + 대시보드/진단 번들
├── admin/         # 콘솔 셸(React 번들) FileResponse 서빙 + /admin 라우트 게이팅
└── cli/           # clovirone-user CLI (§29)

frontend/          # React 18 + Vite 소스(src/app, src/screens, src/ui, src/lib)
```

신규 모델은 `app/models_registry.py`에 임포트를 추가해 Alembic/메타데이터에 등록하고,
`main.py`에 `include_router` 한 줄을 더한다.

## core/ 인프라

| 파일 | 책임 |
|---|---|
| `config.py` | `Settings` — spec §28 환경변수 (n8n URL, 세션 TTL, 잠금 정책 등) |
| `db.py` | engine/session factory. SQLite PRAGMA: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL`. DB 타임스탬프는 naive UTC |
| `security.py` | Argon2id 해시, 비밀번호 정책(12자+3종), 토큰 생성, SHA-256 토큰 해시 |
| `sessions.py` | 세션 생성/검증/회전/폐기 — idle 30분, absolute 8시간 |
| `deps.py` | FastAPI 의존성: `get_db`, 인증(`get_current_user`), RBAC(`require_roles`), CSRF(`require_csrf`), 클라이언트 IP |
| `allowlist.py` | SSRF 허용 목록 3종 (services/runners/workflows JSON, host:port 정확 일치, mtime 캐시) |
| `http_client.py` | `OutboundClient` — **app/에서 httpx를 import하는 유일한 모듈** (정적 테스트로 강제). 호출 시점 allowlist 검사, redirect 금지, secret 주입 |
| `secret_refs.py` | 파일 기반 Secret 참조 — DB에는 이름만, 값은 `secrets_dir` 파일 |
| `versioning.py` | `config_versions` 스냅샷 — 레지스트리/설정의 전체 JSON 스냅샷 + 롤백 소재 |
| `audit.py` | 감사 기록 + 민감 키 마스킹(password/secret/token/credential/api_key → `***`) |
| `middleware.py` | request ID, CSP 등 보안 헤더, access log, 256KB body 제한 |
| `errors.py` | `{"error":{code,message,request_id,details}}` 표준 에러 envelope |
| `providers.py` | Provider 추상 인터페이스 (spec §7.3, 아래 확장 지점) |
| `notion_blocks.py` | `markdown_to_blocks` — 문서/티켓 본문(마크다운)을 Notion 블록으로 변환 |
| `feature_flags.py` | 기능 플래그(예: `game_ai_enabled`) 로드/평가 |

## 요청 흐름 (채팅 메시지)

1. 브라우저 → `POST /api/conversations/{id}/messages` (CSRF 헤더 + 세션 쿠키, 유지보수 gate 통과)
2. `chat/service.post_user_message`: 검증(길이 5000, client_message_id 형식/중복) → `Message` 저장
   → `jobs.repository.enqueue(job_type="chat_message", idempotency_key="chatmsg:<client_message_id>")`
3. 즉시 202-성 응답 — 브라우저는 메시지 목록을 폴링(backoff 1s→최대 5s)
4. Worker `run_once`: **원자적 claim** — `UPDATE jobs SET status='running' WHERE id=(SELECT ... LIMIT 1) RETURNING id`.
   대화형 레인이 켜져 있으면 이 claim을 배치 워커가 아니라 대화형 워커가 수행한다(위 참고)
5. `handlers/chat_message.py`: 미매핑 사용자의 1인칭 요청이면 safe-refusal 안내로 종료,
   아니면 `OutboundClient.post(n8n_work_assistant_url, allowlist="workflows")` 호출
6. 성공 시 assistant `Message` 저장, 실패 시 backoff 재시도(5s·10s·20s), 최종 실패 시
   `on_failure` 훅이 메시지를 `failed`로 표시 + 사용자 알림 생성

## 스케줄 흐름

Worker 루프의 tick 콜백으로 `SchedulerService.tick(now)`이 1초 간격으로 실행된다.
due Schedule마다: misfire 판정(grace 300s) → 동시 실행 정책 → `schedule_runs`에
`idempotency_key = "{schedule_id}:{scheduled_at}"` (UNIQUE) insert-first로 소유권 확보 →
`schedule_run` Job enqueue → `next_run_at` 전진. 상세는 `docs/SCHEDULER.md`.

## 게임 AI 퀴즈 흐름

실시간 퀴즈의 문제 생성은 러너의 전용 엔드포인트에 위임한다(불변: 임의 shell 실행 금지).
`app/games/ai.py`의 `generate_quiz`가 `OutboundClient.post(settings.game_runner_url,
allowlist="runners")`로 러너 `/v1/assistant/quiz`(`http://127.0.0.1:8789`)를 호출한다 —
redirect 금지, SSRF allowlist 검사, 러너 토큰은 `secrets_dir/<game_runner_token_ref>`
파일로만 주입(평문 미노출). `game_ai_enabled` 플래그는 기본 OFF(다크런치)이며, 꺼져 있으면
정적 문제로 폴백한다.

## 데이터 모델 개요 (Alembic 0001–0019)

users, sessions, audit_logs, integrations, config_versions, jobs,
conversations, messages, runners, workflows, prompts, policies,
automation_templates, schedules, schedule_runs, approvals, notifications,
app_settings, document_generations, user_notion_mappings, backups, heartbeats.

이후 확장분: 0014 `users.archived_at`(soft delete), 0015 부서/직책(departments,
job_titles + users 배정), 0016 자유게시판(board), 0017 문서 탭(team_docs),
0018 문서 분류(doc_taxonomy), 0019 놀이(games).

공통 패턴: UUID PK 문자열, naive UTC 타임스탬프, JSON 컬럼은 `*_json` TEXT.
변경 이력은 두 축 — `config_versions`(설정형 객체 스냅샷)와 행 단위 버전
(prompts/policies는 name+version UNIQUE로 published 내용을 절대 덮어쓰지 않음).

## 확장 지점 (Provider 인터페이스, spec §7.3)

`app/core/providers.py`의 ABC를 구현해 교체/추가한다.

| 인터페이스 | 초기 구현 |
|---|---|
| `RunnerProvider` | `runners/provider_http.py` (Local HTTP Runner) |
| `WorkflowProvider` | `workflows/provider_n8n.py` (n8n Webhook) |
| `IdentityProvider` | 로컬 계정 (auth 내장) |
| `NotificationProvider` | 인앱 알림 (`notifications/service.py`) — Email/Teams는 동일 shape로 fan-out 예정 |
| `DocumentProvider` | Notion-via-n8n (documents + document_generate handler) |
| `SecretReferenceProvider` | `core/secret_refs.FileSecretReferenceProvider` |

새 모듈/핸들러/실행기 추가 절차는 `docs/EXTENSION_GUIDE.md` 참조.
