# ARCHITECTURE — 시스템 구조

ClovirONE Web Assistant는 기존 n8n 기반 AI 업무 도우미를 손상 없이 확장하는
사내 웹 플랫폼이다. FastAPI(sync 핸들러) + SQLAlchemy 2.0 + SQLite(WAL) 단일 서버
구성이며, 웹 프로세스와 백그라운드 Worker 프로세스 두 개로 동작한다.

## 프로세스 구성

| 프로세스 | 진입점 | 역할 |
|---|---|---|
| Web (uvicorn) | `app.main:create_app` (--factory) | HTTP API + HTML 페이지, 127.0.0.1:8080 |
| Worker | `python -m app.worker_main` | Job 큐 소비 + Scheduler tick + 승인 만료 스윕 + heartbeat |
| Nginx | `deploy/nginx/clovirone-web-assistant.conf` | 10.100.64.71:443 TLS 종단 → 127.0.0.1:8080 프록시 |

## App Factory

`app/main.py`의 `create_app(settings, clock, outbound_transport)`가 유일한 조립 지점이다.

- `settings`: `app.core.config.Settings` (pydantic-settings, 환경변수/web.env, spec §28)
- `clock`: `Clock` 인터페이스 — 테스트는 FakeClock으로 시간을 주입
- `outbound_transport`: httpx transport 주입 — 테스트는 FakeHTTP로 아웃바운드를 가로챔

factory는 `app.state`에 공유 자원을 올린다: engine/session_factory, `SessionService`,
로그인 `RateLimiter`(IP당 약 10회/분), `AllowlistRegistry`, `FileSecretReferenceProvider`,
`SettingsCache`, `OutboundClient`, Jinja2 templates. OpenAPI/docs 엔드포인트는 비활성.

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
├── audit/         # 감사 로그 조회
├── backups/       # SQLite 백업/검증
├── health/        # healthz/readyz + 대시보드/진단 번들
├── admin/         # /admin HTML 셸
└── cli/           # clovirone-user CLI (§29)
```

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

## 요청 흐름 (채팅 메시지)

1. 브라우저 → `POST /api/conversations/{id}/messages` (CSRF 헤더 + 세션 쿠키, 유지보수 gate 통과)
2. `chat/service.post_user_message`: 검증(길이 5000, client_message_id 형식/중복) → `Message` 저장
   → `jobs.repository.enqueue(job_type="chat_message", idempotency_key="chatmsg:<client_message_id>")`
3. 즉시 202-성 응답 — 브라우저는 메시지 목록을 폴링(backoff 1s→최대 5s)
4. Worker `run_once`: **원자적 claim** — `UPDATE jobs SET status='running' WHERE id=(SELECT ... LIMIT 1) RETURNING id`
5. `handlers/chat_message.py`: 미매핑 사용자의 1인칭 요청이면 safe-refusal 안내로 종료,
   아니면 `OutboundClient.post(n8n_work_assistant_url, allowlist="workflows")` 호출
6. 성공 시 assistant `Message` 저장, 실패 시 backoff 재시도(5s·10s·20s), 최종 실패 시
   `on_failure` 훅이 메시지를 `failed`로 표시 + 사용자 알림 생성

## 스케줄 흐름

Worker 루프의 tick 콜백으로 `SchedulerService.tick(now)`이 1초 간격으로 실행된다.
due Schedule마다: misfire 판정(grace 300s) → 동시 실행 정책 → `schedule_runs`에
`idempotency_key = "{schedule_id}:{scheduled_at}"` (UNIQUE) insert-first로 소유권 확보 →
`schedule_run` Job enqueue → `next_run_at` 전진. 상세는 `docs/SCHEDULER.md`.

## 데이터 모델 개요 (Alembic 0001–0013)

users, sessions, audit_logs, integrations, config_versions, jobs,
conversations, messages, runners, workflows, prompts, policies,
automation_templates, schedules, schedule_runs, approvals, notifications,
app_settings, document_generations, user_notion_mappings, backups, heartbeats.

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
