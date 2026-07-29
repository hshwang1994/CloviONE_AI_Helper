# TEST SCENARIOS — 테스트 스위트 개요

## 실행 방법

```bash
.venv/Scripts/python -m pytest              # 기본: smoke 제외 전체 (pytest.ini addopts)
.venv/Scripts/python -m pytest -m security  # 마커 선택 실행
.venv/Scripts/python -m pytest tests/unit/test_scheduler_tick.py -k misfire
```

마커(`pytest.ini`): `unit`(빠른 격리), `integration`(app factory 대상 API 테스트),
`security`, `regression`(고정 결함 회귀), `smoke`(**라이브 인스턴스 필요 — 기본
deselect**).

## 테스트 인프라 (`tests/conftest.py`)

- **DB 전략**: 세션당 1회 `alembic upgrade head`로 템플릿 SQLite 파일 생성 →
  테스트마다 파일 복사. 마이그레이션이 매 실행 검증되면서도 빠르다.
  `:memory:`는 쓰지 않는다 — WAL·다중 커넥션 동작을 운영과 동일하게 유지
- **주입 페이크** (`tests/fakes/`): `FakeClock`(시간 제어),
  `FakeHTTP`(httpx transport 대체 — 실제 네트워크 없이 아웃바운드 검증).
  `create_app(settings, clock=..., outbound_transport=...)`로 주입

## 레이아웃과 핵심 시나리오

### tests/unit — 순수 로직

| 파일 | 검증 내용 |
|---|---|
| `test_password_policy.py` | 12자/3종 정책, 임시 비밀번호 생성 |
| `test_config.py` | Settings 환경변수 파싱 |
| `test_db_pragmas.py` | WAL/busy_timeout/foreign_keys PRAGMA 적용 |
| `test_secret_refs.py` | 참조 이름 검증, SecretValue 마스킹(repr/str/format=`***`) |
| `test_audit_masking.py` | password/secret/token/api_key 재귀 마스킹 |
| `test_jobs_repository.py` | enqueue/backoff(5·10·20s)/idempotency/stuck recovery |
| `test_cron.py` | preset, timezone(Asia/Seoul), **DST 전환** next-fire 계산 |
| `test_scheduler_tick.py` | due 평가, **misfire skip/run_once**, 동시성 skip, idempotency 키 |
| `test_runner_circuit.py` | **5회 연속 실패→degraded+300s open**, 성공 시 자동 복구 |
| `test_document_quality.py` | 빈 제목/짧은 본문/소스 0건/민감정보/notion 링크 게이트 |
| `test_sqlite_backup.py` | Backup API·체크섬·integrity_check·temp restore |

### tests/integration — API 레벨 (app factory + TestClient)

- **인증**: 로그인 성공/실패/잠금(`test_auth_login.py`), 비밀번호 변경 시 세션 회전·
  타 세션 폐기(`test_auth_change_password.py`, `test_auth_sessions.py`)
- **채팅**: 대화/메시지 CRUD·소유권(`test_chat_api.py`), 핸들러의 n8n 왕복·재시도
  (`test_chat_handler.py`), **미매핑 1인칭 요청 safe-refusal**(`test_chat_notion_refusal.py`)
- **Job 큐**: `test_job_claim_race.py` — **다중 스레드 동시 claim 경쟁에서 이중 claim
  0건** 증명, `test_worker.py` — run_once/sweep/on_failure/graceful 흐름
- **레지스트리**: integrations/runners/workflows API — disabled 생성 기본,
  버전/롤백, 도달성 테스트 (`test_*_api.py`)
- **콘텐츠**: prompts/policies 수명주기 전이·publish 자동 archive·diff·rollback,
  templates 참조 검증
- **스케줄**: 생성 검증, enable 승인 게이트(202), dry-run/run-now, run retry
  (`test_schedules_api.py`)
- **승인**: 생성→approve 실행/reject/만료/자기 승인 금지 (`test_approvals.py`)
- **문서**: generate→preview→품질 게이트→모드별 분기 (`test_documents_api.py`)
- **Notion 매핑**: verify 1건/0건/충돌, 수동 매핑/충돌 해결 (`test_notion_mapping.py`)
- **운영**: 유지보수 모드 차단·operator 통과(`test_maintenance_mode.py`),
  설정 dry-run/rollback(`test_settings_api.py`), 알림 소유권(`test_notifications.py`),
  대시보드·백업(`test_dashboard_backups.py`), 감사 조회(`test_audit_api.py`),
  에러 envelope 형식(`test_error_envelope.py`), 헤더/CSP(`test_middleware.py`),
  HTML 페이지 응답(`test_pages.py`), CLI 전 명령(`test_cli_user.py`),
  healthz/readyz(`test_health.py`)

### tests/security — 보안 강제 검증

| 파일 | 검증 내용 |
|---|---|
| `test_rbac_basics.py` / `test_admin_rbac.py` | 역할별 403 — user는 admin API 전면 거부, auditor는 읽기만 |
| `test_csrf.py` | 헤더 누락/불일치 변이 요청 403, 안전 메서드 면제 |
| `test_ssrf_allowlist.py` | host:port 불일치·scheme·userinfo 거부, **파일 없음=전면 거부** |
| `test_outbound_client.py` | **httpx import가 http_client뿐임을 정적 검사**, redirect 미추종, secret 주입 |
| `test_chat_security.py` | 타인 대화 접근 거부, requester 위조 불가(서버 세션 기준) |

### tests/regression / tests/smoke

- `regression/`: 고정된 결함의 재발 방지 테스트 수납처 (버그 수정 시 추가하는 규칙)
- `smoke/`: 배포된 라이브 인스턴스 대상 점검용 — 기본 실행에서 제외

## 커버리지 기대치

핵심 경계(인증/RBAC/CSRF/SSRF/큐/스케줄러/품질 게이트)는 유닛+통합 이중으로 덮는다.
새 기능 추가 시 최소한: 서비스 로직 unit + API happy/오류 경로 integration +
권한 거부 security 케이스 1개를 함께 커밋한다.
