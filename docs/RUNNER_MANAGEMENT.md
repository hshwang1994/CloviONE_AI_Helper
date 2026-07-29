# RUNNER MANAGEMENT — Runner Registry (spec §15)

Runner는 로컬 HTTP 실행기(claude-ticket-runner 등 기존 서비스)를 플랫폼에서
**메타데이터로만** 관리하는 레지스트리다. 코드/프로세스는 건드리지 않는다.

## 할 수 있는 것 / 없는 것

| 가능 | 불가능 (설계상 제공하지 않음) |
|---|---|
| 등록/설정 수정/복제/활성·비활성 | Runner **코드 편집** |
| 헬스체크, 안전한 테스트 호출 | 서버 **shell 실행**, 프로세스 기동/중지 |
| 설정 버전 이력 조회·롤백 | allowlist 밖 URL로의 연결 |
| circuit breaker 상태 확인 | secret 값 조회 (상태만: configured/missing) |

## 필드 (`app/runners/models.py`)

| 필드 | 설명 |
|---|---|
| `name` | 고유 이름 (중복 거부) |
| `provider_type` | 실행기 유형 (예: `http_service`) |
| `base_url` / `health_url` | 호출/헬스 URL — **runners allowlist 검사** 통과 필수 |
| `auth_type` / `secret_ref` | `none` / `bearer` / `api_key_header` + secret 참조 이름 |
| `timeout_seconds` (기본 60) / `concurrency_limit` (기본 1) / `retry_policy` | 실행 정책 |
| `enabled` / `maintenance_state` | 활성 여부 / `normal`·`degraded`·`maintenance` |
| `capabilities`, `version`, `owner`, `tags`, `integration_id` | 메타데이터 |
| `last_health_status` / `last_health_at` / `config_version` | 상태 캐시 |
| `consecutive_failures` / `circuit_open_until` | circuit breaker 상태 |

## 생성은 Disabled가 기본 (spec §15.5)

`create_runner`는 요청에 `enabled: true`가 있어도 **무조건 `enabled=False`로 저장**한다.
절차: 등록 → 헬스체크/테스트로 확인 → 명시적으로 활성화. 실수로 미검증 실행기가
트래픽을 받는 것을 막는 안전장치다.

## 헬스체크와 테스트 (operator+)

- `POST /api/admin/runners/{id}/health` — `health_url`(없으면 `base_url`)에 GET,
  timeout 10s. HTTP <400이면 `up`. 결과는 `last_health_*`에 기록되고
  circuit breaker 카운터에도 반영된다
- `POST /api/admin/runners/{id}/test` — `{"ping": true, "test": true}` 고정 payload로
  POST (실제 업무 요청이 아님). `RunnerHttpProvider.test_request`

## Circuit Breaker (spec §15.6)

상수는 `app/runners/models.py`:

- `CIRCUIT_FAILURE_THRESHOLD = 5` — **연속 5회 실패** 시
  `maintenance_state=degraded` + `circuit_open_until = now + 300s`
- `CIRCUIT_COOLDOWN_SECONDS = 300` — 쿨다운 동안 `can_dispatch`가
  `circuit_open`으로 호출을 거부
- 쿨다운 경과 후 첫 **성공**이 발생하면: 실패 카운터 0, circuit 해제,
  degraded → normal **자동 복구**

`can_dispatch(runner, now)`의 거부 사유: `runner_disabled` /
`runner_maintenance`(수동 점검 상태) / `circuit_open`. 판단은 호출 직전마다 수행된다.

## 설정 변경 = 승인 대상 (spec §20)

`PATCH /api/admin/runners/{id}`(설정 변경)와 롤백은 승인 게이트를 지난다:
system_admin은 즉시 적용, admin은 202 + `runner.change_config` pending 승인 생성.
승인 실행기는 저장된 config를 `apply_runner_config`로 재실행한다 — 이때도
allowlist/이름 충돌 검증을 다시 통과해야 한다.

## 버전 관리와 롤백

- 생성/수정마다 전체 설정 스냅샷이 `config_versions`(object_type=`runner`)에 저장되고
  `config_version`이 1씩 증가한다
- `GET /api/admin/runners/{id}/versions` — 이력 조회 (스냅샷에는 secret **이름만** 존재)
- `POST /api/admin/runners/{id}/rollback` `{"version": N}` — 스냅샷을 현재 스키마로
  재검증한 뒤 일반 수정 경로로 적용. 즉 **롤백도 새 버전**이며 이력은 append-only
- `POST /api/admin/runners/{id}/clone` — 기존 설정을 새 이름으로 복제
  (복제본 역시 disabled로 생성)

## 권한

| 작업 | 역할 |
|---|---|
| 목록/상세/버전 조회 | operator, admin, system_admin, auditor |
| 헬스/테스트 | operator, admin, system_admin |
| 생성/수정/활성·비활성/복제/롤백 | admin, system_admin (수정·롤백은 승인 게이트) |

## 운영 팁

- degraded 상태를 발견하면: 대상 서비스 로그 확인 → 원인 해소 → 헬스체크 1회 성공으로
  자동 복구 확인. 강제로 열어두고 싶으면 `maintenance_state=maintenance`로 전환
- URL 변경 전 `/etc/clovirone-web-assistant/allowed-runners.json`에 새 host:port를
  먼저 추가해야 저장이 통과된다 (파일 저장 즉시 반영, 재시작 불필요)
