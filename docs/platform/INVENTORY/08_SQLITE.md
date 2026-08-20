# INVENTORY 08 — SQLite 결합 지점 (코드 레벨)

**정본**: `app/**` Source
**측정**: 2026-08-20 (Plan Mode)
**소유**: **S2** — 이 13항이 PostgreSQL Foundation 의 작업 목록이다.

스키마·데이터 실측은 [`05_DB.md`](05_DB.md). 이 문서는 **코드가 SQLite 를 어떻게 전제하고 있는가**다.

## 13항

| # | 자리 | 조치 | 위험 |
|---|---|---|---|
| 1 | `app/core/db.py:74-102` PRAGMA 4종 · `check_same_thread` · `isolation_level=None` | 삭제. `pool_size`/`max_overflow` 실제 설정 | 낮음 |
| 2 | `app/core/db.py:115-138` `exec_driver_sql("BEGIN")` | 삭제 (psycopg 가 관리) | 낮음 |
| 3 | **`app/core/db.py:154-180` `is_write_conflict()`** | **둘로 쪼갠다** — `is_serialization_conflict()`(40001·40P01·55P03 → 재시도) / 유니크 충돌은 "이미 있다"를 뜻하는 호출부(`jobs.enqueue` 등)에서 **국소 처리**. **115 호출부 · 30 모듈 전수 감사** | **최고 (R1)** |
| 4 | `app/jobs/repository.py:167-193` claim | **`SELECT … FOR UPDATE SKIP LOCKED`**. 문자열 `strftime` 바인딩(`:147-149`) 제거 → 진짜 `timestamp` | 높음 |
| 5 | `rowid` 정렬 4곳 — `chat/service.py:226,235` · `tickets/comments.py:116` · `team_docs/comments.py:112` · `search/service.py:65,153` | 해당 테이블에 **`seq bigint GENERATED ALWAYS AS IDENTITY`** 추가 후 `(created_at, seq)` 정렬. `chat_messages.seq` 기존 관용구와 일치 | 중간 |
| 6 | `func.json_extract` 2곳 — `jobs/router.py:148` · `prompts/router.py:350` | 컬럼을 **`jsonb`** 로 바꾸고 `->>` / GIN 인덱스 | 중간 |
| 7 | 27개 `*_json` Text 컬럼 | **`jsonb`** 이전. 단 **`approvals.request_payload_json` 은 유니크 키의 일부**라 정규화 직렬화 규약을 명시하거나 해시 컬럼으로 분리 | 중간 |
| 8 | `sqlite_where=` **3곳** | **`postgresql_where=`** — PG 에서 제대로 동작한다(오히려 개선) | **높음 (R2)** |
| 9 | `LIKE` 대소문자 3곳 — `search/query.py:94` · `retention.py:180` · `schedules/router.py:829` | PG `LIKE` 는 대소문자를 구분한다 → `ILIKE` 또는 `pg_trgm` 경로 | 중간 |
| 10 | 문자열 날짜 컬럼 — `due_date`·`starts_on`·`last_edited`·`week_of`·`sort_key` 등 | 새 도메인에서 **`date`/`timestamptz` 정식 타입**. 문자열 비교 관용구 제거 | 중간 |
| 11 | **`VARCHAR(n)`** — SQLite 는 무시, PG 는 강제 | **Migration 전 길이 감사 필수 (S1).** 13개 컬럼 | **높음 (R7)** |
| 12 | `app/backups/sqlite_backup.py` 전체 | `pg_dump -Fc` 기반 재작성 | 높음 |
| 13 | `ID_BATCH_SIZE=500` 근거 주석 | PG 한계(65535)로 정정 | 낮음 |

## 왜 3번이 가장 위험한가

현재 `is_write_conflict()` 는 **모든 `IntegrityError` 를 재시도 대상**으로 본다.
SQLite 에서는 그게 대체로 맞았다 — `database is locked` 가 진짜 일시적 상태였기 때문이다.

PG 에서는 다르다. **진짜 제약 위반(유니크 충돌·FK 위반)이 10회 재시도 후 503 "다시 시도" 로
나간다.** 데이터 버그가 일시적 오류로 위장한다. 이건 조용히 틀리는 종류의 실패다.

**음성 테스트로 증명한다**: 명백한 제약 위반이 **재시도 없이 즉시** 도메인 오류로 나오는가.

## `--workers 1` 잠금 (D-192)

지금 워커를 못 늘리는 이유는 성능이 아니라 **방어가 프로세스 메모리 안에 있기 때문**이다.
로그인 무차별 대입 제한 · 채팅 제한 · AI 퀴즈 제한이 전부 인메모리 카운터라 워커를 늘리면
**방어가 조용히 N배 약해진다**(systemd unit 주석에 명시돼 있다).

| 대상 | 이동 |
|---|---|
| `login/chat/game_ai/assistant` rate limiter | `rate_limit_buckets` 테이블 (token bucket, `UPDATE … RETURNING`) |
| `tickets/claim_lock.py` | `pg_advisory_xact_lock(hashtext(ticket_id))` |
| `quotas/quota_lock.py` | 동일 + `SELECT … FOR UPDATE` |
| `search/indexer.py` reindex lock · `tickets/router.py` sync lock · `notion_console` create lock | advisory lock (또는 **대상 제거**) |
| `SettingsCache` | web 에도 주기 갱신 또는 `LISTEN/NOTIFY` |

**순서 규약: 공유 저장소를 먼저 만들고 그 다음에 `--workers` 를 올린다.**

## 완성도 — S1 이 마저 할 것

- 11번(`VARCHAR(n)` 13개 컬럼) 길이 감사. 나머지 12항은 **S2 소유**다
- 3번의 **115 호출부 목록**을 미리 뽑아 두면 S2 가 빨라진다 (선택)
