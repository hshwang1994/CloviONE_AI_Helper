# EXTENSION GUIDE — 확장 방법

이 문서는 코드베이스의 기존 패턴을 따라 기능을 추가하는 절차를 정리한다.
공통 원칙: 서비스 계층에 로직, 라우터는 얇게, 모든 변이는 감사 기록 + (설정형이면)
`config_versions` 스냅샷, 아웃바운드는 반드시 `OutboundClient`.

## 1. 새 모듈 추가 (router/service/repository/schemas/models)

1. `app/<모듈>/` 생성 — 기존 모듈(예: `app/runners/`)을 본보기로:
   - `models.py`: `Base, UUIDPrimaryKeyMixin, TimestampMixin`(`core/models_base`) 상속,
     상태 상수는 모듈 상단에 문자열 상수로
   - `schemas.py`: pydantic 요청/응답 모델 (경계 검증은 여기서)
   - `service.py`: 순수 로직 — `db: Session`을 인자로 받고 flush까지만
     (commit은 `get_db` 의존성이 담당)
   - `router.py`: `APIRouter(prefix="/api/admin/...", dependencies=[Depends(require_csrf)])`
     + 엔드포인트별 `require_roles(...)`. 읽기 READ_ROLES(operator+/auditor),
     쓰기 WRITE_ROLES(admin+) 관례 유지
2. `app/main.py`의 `create_app`에 `include_router` 추가
3. **모델을 Alembic이 보도록** `app/models_registry.py`에 import 추가
4. 마이그레이션 생성(아래 §6), integration 테스트 작성 (`tests/integration/test_<모듈>_api.py`)

## 2. Job 핸들러 추가

1. `app/jobs/handlers/<job_type>.py`:
   ```python
   def handle_my_job(db: Session, job: Job, ctx: WorkerContext) -> None:
       payload = parse_payload(job)          # 손상 payload → PermanentJobError
       ...                                    # 일시 오류는 RuntimeError → backoff 재시도
                                              # 영구 오류는 PermanentJobError → 즉시 failed
   def on_failure(db, job, ctx, error): ...   # 최종 실패 후 훅 (선택)
   handle_my_job.on_failure = on_failure
   ```
2. `app/worker_main.py`의 `build_handlers()` dict에 `"my_job": handle_my_job` 등록
3. enqueue는 `jobs.repository.enqueue(db, job_type="my_job", payload=..., now=...,
   idempotency_key=...)` — **중복 유입 가능성이 있으면 idempotency_key 필수**
4. 규칙: 핸들러 안에서 장기 상태 변경 전 `db.commit()`으로 claim 상태를 확정하는
   기존 패턴(chat_message 참조)을 따르고, 외부 호출은 `ctx.outbound_client`만 사용

## 3. Provider 구현 추가 (spec §7.3)

`app/core/providers.py`의 ABC(`RunnerProvider`, `WorkflowProvider`,
`IdentityProvider`, `NotificationProvider`, `DocumentProvider`,
`SecretReferenceProvider`) 중 하나를 구현한다.

- 예: Teams 알림 — `NotificationProvider.notify()` shape로 구현하고
  `notifications/service.notify_user`에서 인앱 저장과 함께 fan-out (spec §13.5)
- 예: 새 Runner 유형 — `runners/provider_http.py`처럼 invoke 전 `can_dispatch`,
  결과를 `record_runner_result`로 circuit breaker에 반영
- HTTP가 필요하면 생성자에서 `OutboundClient`를 받는다 — httpx 직접 import 금지
  (정적 테스트 `tests/security/test_outbound_client.py`가 실패한다)

## 4. 승인 실행기(approval executor) 추가

승인 대상 행위를 늘리려면 (`app/approvals/service.py`):

1. 실행기 작성 — 저장된 payload를 **일반 서비스 경로로** 재실행:
   ```python
   def _execute_my_action(db, approval, app_state): ...
   APPROVAL_EXECUTORS["my.request_type"] = _execute_my_action
   ```
   실행기 안에서 대상 존재/선행 조건을 재검증하고, 문제면 예외 → 트랜잭션 롤백
   (승인 상태 변화 없음)
2. 요청 지점(라우터)에서 게이트 적용:
   ```python
   if needs_approval(request.state.user):        # system_admin이 아니면
       approval = create_approval(db, request_type="my.request_type", ...)
       return JSONResponse(status_code=202, content={"status": "approval_pending", ...})
   # system_admin: 즉시 실행
   ```
3. `create_approval`은 등록되지 않은 request_type을 거부하므로 실행기 등록이 선행 조건

## 5. 설정 키 추가 (settings registry)

`app/settings/registry.py`의 `REGISTRY`에 `SettingSpec` 추가:

```python
SettingSpec("my_key", "int", 30, False, "설명", _positive_int(3600)),
```

- validator는 실패 시 `ValidationAppError` — dry-run과 적용 양쪽에서 실행된다
- `restart_required=True`면 UI에 "재시작 필요" 배지가 붙는다 (자동 재시작은 없음)
- **secret은 여기 넣지 않는다** — secret은 파일 참조(`secret_refs`) 체계로만
- 값 읽기는 `app.state.settings_cache.get(db, "my_key")` — 쓰기 시 캐시가 자동 무효화

## 6. 마이그레이션 추가

```bash
# 모델 수정 + models_registry 등록 후
.venv/Scripts/python -m alembic revision --autogenerate -m "add my_table"
# 생성된 alembic/versions/00xx_*.py 검토 — SQLite 제약(ALTER 제한) 확인
.venv/Scripts/python -m alembic upgrade head
```

관례: 파일명은 `00NN_<내용>.py` 연번, 마지막은 0013. downgrade도 작성한다.
테스트는 conftest가 매 세션 `alembic upgrade head`를 실행하므로 마이그레이션 자체가
전체 테스트에서 검증된다.

## 7. Postgres 전환 기준 (spec §7.4)

SQLite(WAL)는 현 규모(단일 서버, 소수 동시 사용자, 단일 worker)에 충분하다.
다음 신호가 나타나면 Postgres 전환을 계획한다:

- writer 경합 상시화 — `database is locked`/busy_timeout 대기가 정상 부하에서 반복
- **worker 수평 확장 필요** (여러 서버에서 claim 경쟁 — 현 claim SQL은 Postgres의
  `FOR UPDATE SKIP LOCKED`로 자연 이식)
- 웹 프로세스 다중화(멀티 노드)로 파일 DB 공유가 불가능해질 때
- DB 크기/감사 로그 증가로 온라인 백업·보존 정책이 SQLite 운영 한계를 넘을 때

이식 대비가 이미 코드에 있다: repository 계층이 SQL을 격리하고
(`chat/service.list_messages`의 rowid 정렬 주석 참조), 타임스탬프는 naive UTC 통일,
`database_url`만 바꾸면 engine이 구성된다. 전환 시 점검 목록: claim SQL의
RETURNING/SKIP LOCKED, rowid 의존 정렬, PRAGMA 이벤트 리스너 비활성, Alembic 재베이스.
