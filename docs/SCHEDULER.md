# SCHEDULER — 스케줄 실행 (spec §18)

별도 데몬이 아니라 **Worker 프로세스 안**에서 동작한다: worker 루프의 tick 콜백으로
`SchedulerService.tick(now)`이 최대 1초 간격으로 호출된다 (`app/worker_main.py`).
tick은 순수 로직(sleep 없음)이라 테스트가 FakeClock으로 결정적으로 구동한다.

## 스케줄 유형

| 유형 | 정의 | 동작 |
|---|---|---|
| `cron` | `cron_expression` (5필드) + timezone | cronsim으로 다음 실행 시각 계산 |
| `once` | `run_at` (미래 시각 필수) | 1회 실행 후 자동 비활성 (`next_run_at=None`) |

**Preset** (`app/schedules/cron.py`): `daily`=`0 9 * * *`, `weekly`=`0 9 * * 1`(월요일),
`monthly`=`0 9 1 * *` — 생성 시 preset을 주면 cron_expression으로 변환된다.

## Timezone (spec §18.3)

DB의 모든 시각은 naive UTC. cron 평가만 스케줄의 timezone(기본 **Asia/Seoul**,
ZoneInfo 검증)으로 수행한다: UTC → 로컬 변환 → cronsim next → UTC로 환원.
DST 전환은 cronsim이 처리한다 (`tests/unit/test_cron.py`에 DST 케이스).

## 대상 (target)

- `workflow`: Workflow Registry의 id — 존재 검증. 실행 시 `payload_template`을
  그대로 webhook에 전달. **write + approval_required workflow는 자동 실행 거부**
- `system`: 내장 대상 (`noop`만) — dry-run·헬스 검증용

## Misfire 정책 (spec §18.4)

due 시각을 **grace 300초**(`DEFAULT_MISFIRE_GRACE_SECONDS`) 넘겨 발견하면
(서버 다운타임 등) misfire로 처리한다:

- `skip` (기본): 해당 occurrence를 `skipped`(사유 `misfire_skip`) run으로 기록만 하고
  다음 시각으로 전진
- `run_once`: **catch-up 1회만** 지금 실행 — 놓친 여러 회는 버린다
- Run All Missed는 **의도적으로 미구현** (기본 금지, spec §18.4)

## 동시 실행 정책 (spec §18.5)

- `skip` (기본): 같은 스케줄의 run이 `queued`/`running`이면 이번 occurrence를
  `skipped`(사유 `concurrent_run_active`)로 기록하고 전진
- `allow`: 중첩 허용

## 중복 실행 방지 (idempotency)

이중 방어:

1. `schedule_runs.idempotency_key = "{schedule_id}:{scheduled_at:%Y%m%d%H%M%S}"` —
   **UNIQUE 제약 + insert-first**: run 행을 먼저 insert하고, IntegrityError면 다른
   인스턴스가 이미 소유한 것이므로 조용히 물러난다 (`create_run_and_enqueue`)
2. Job 큐 자체의 idempotency_key `"schedrun:{key}"` — 같은 run의 Job 중복 enqueue 차단

수동 실행(run-now)은 키가 `manual:{schedule_id}:{timestamp}`라 정기 occurrence와
충돌하지 않는다.

## 실행 흐름

tick → due 스케줄 조회(enabled + next_run_at ≤ now) → misfire/동시성 판정 →
run insert + `schedule_run` Job enqueue → `last_run_at`/`next_run_at` 갱신.
Job은 worker가 claim해 `handlers/schedule_run.py`가 실행: run을 `running`으로,
provider 호출, 성공 시 `succeeded` + `response_summary`(2000자 절단).

## 재시도

- Job 레벨: `retry_policy.max_attempts`(1~10로 clamp, 기본 3) — 일시 오류는
  backoff(5s·10s·20s)로 자동 재시도. 최종 실패 시 run은 `failed`가 되고
  **스케줄 소유자에게 알림**(`schedule_failed`)이 간다
- 수동: `POST /api/admin/schedules/runs/{run_id}/retry` (operator+) —
  failed run만, 새 idempotency 키로 재큐

## 생성 → 활성화 절차

1. `POST /api/admin/schedules` (admin+) — 검증: 이름 중복, cron/preset 유효성,
   timezone, target 존재, start/end 정합. **항상 enabled=false로 생성**
2. `POST .../dry-run` (operator+) — payload 미리보기 + 다음 3회 실행 시각(UTC).
   실행은 하지 않는다
3. `POST .../enable` — **승인 대상** (spec §20): system_admin은 즉시(이때
   next_run_at 계산), 그 외 admin은 202 + `schedule.enable` 승인 생성.
   승인 실행기가 같은 검증(once의 과거 시각 거부 포함)을 수행한다
4. `POST .../run-now` (operator+) — 즉시 1회 실행 (body `{"dry_run": true}`면
   dry-run과 동일). `POST .../disable`은 즉시 비활성(승인 불요)

`end_at`이 지나면 자동 비활성. 활성 상태에서 정의를 수정(PUT)하면 next_run_at이
새 정의로 재계산된다.

## Workflow로 전달되는 표준 payload

스케줄의 `payload_template`(JSON 객체)이 **그대로** workflow webhook의 본문이 된다 —
스케줄러가 필드를 추가하지 않으므로, workflow가 기대하는 계약을 template에 완성해
넣어야 한다. 문서 자동화용 표준 payload 예시는 `docs/DOCUMENT_AUTOMATION.md` 참조.
run 이력에는 요청 payload(`request_payload_json`)와 응답 요약이 보존된다.
