# INVENTORY 08 — SQLite 결합 지점 (코드 레벨)

**정본**: `app/**` Source
**측정**: 2026-08-20 (Plan Mode) · **이행: 2026-08-21 (S2)**
**소유**: **S2 — 13항 전부 이행됨.**

스키마·데이터 실측은 [`05_DB.md`](05_DB.md). 이 문서는 **코드가 SQLite 를 어떻게 전제하고
있었는가**와 **그것을 어떻게 걷어냈는가**다.

## 13항 — 전부 닫혔다

| # | 자리 | 무엇을 했나 | 상태 |
|---|---|---|---|
| 1 | `app/core/db.py` PRAGMA 4종 · `check_same_thread` · `isolation_level=None` | 전부 삭제. `pool_size=5`/`max_overflow=10`/`pool_recycle`/`lock_timeout`/`statement_timeout` 을 실제 값으로 설정 | **완료** |
| 2 | `app/core/db.py` `exec_driver_sql("BEGIN")` | 삭제 — psycopg 가 관리한다 | **완료** |
| 3 | **`is_write_conflict()`** | **둘로 쪼갰다** — `is_serialization_conflict`(40001·40P01·55P03) / `is_unique_violation`(23505) + 관용구용 `is_insert_race`. **호출부 40곳 · 24모듈 전수 감사**(계획 추정 115/30 → 실측 40/24, D-221): **재시도 9 · insert-race 31**. FK·NOT NULL·CHECK 는 이제 **그대로 올라간다** | **완료 (R1 닫힘)** |
| 4 | `app/jobs/repository.py` claim | **`FOR UPDATE SKIP LOCKED`**. `strftime` 문자열 바인딩 → datetime 그대로(`claim_next`·`cancel_queued`) | **완료** |
| 5 | `rowid` 정렬 4곳 | `messages`·`ticket_comments`·`document_comments` 에 **`seq bigint GENERATED ALWAYS AS IDENTITY`** 추가 후 그것으로 정렬. `search_documents` 는 FTS5 조인이 통째로 사라져 불필요 | **완료** |
| 6 | `func.json_extract` 2곳 | `jsonb` + `->>`(`jobs/router.py`·`prompts/router.py`) | **완료** |
| 7 | `*_json` Text 컬럼 | **37개**(계획 27 → 실측 37) 전부 `JsonText`(저장 `jsonb`, 파이썬 문자열)로 이전. `approvals.request_payload_json` 의 정규화는 **jsonb 가 강제한다** — 규약을 문서로 약속하지 않는다 (D-215) | **완료** |
| 8 | `sqlite_where=` | **`postgresql_where=`**. 실제로는 **4개**다(0053 이 두 표에 건다, D-221) | **완료 (R2 닫힘)** |
| 9 | `LIKE` 대소문자 | `search/query.py` → `ILIKE`. `retention.py` 는 JSON 문자열 훑기 → `jsonb_path_exists`, `schedules/router.py` 는 문자열 조각 → `->>` 로 **더 정확해졌다**. 나머지 `.like()` 는 `func.lower()` 로 이미 대소문자 무관하거나(3곳) 생성 id 접두 일치라 구분이 옳다(2곳) | **완료** |
| 10 | 문자열 날짜 컬럼 | **S2 범위 아님** — 계획이 "새 도메인에서" 로 적었다. 도메인 재설계와 함께 S6·S7 | **소유가 정해졌다: `BACKLOG.md` P-14a (S7).** S6 은 안 했다 — 반씩 나눠 하면 같은 화면에서 문자열 비교와 날짜 비교가 섞인다 |
| 11 | **`VARCHAR(n)`** | `messages.message_id` `VARCHAR(64)` → **`VARCHAR(128)`** (D-214 의 계약상 최대 108). `jobs.message_id`(64)는 감사 결과 **넓힐 필요 없다** — `retry`/`regenerate` 가 `role != user` 를 거부하므로 사용자 메시지 id(≤64)만 들어온다 | **완료 (R7 닫힘)** |
| 12 | `app/backups/sqlite_backup.py` | **삭제.** `app/backups/pg_backup.py` 가 `pg_dump -Fc` + 체크섬 + `pg_restore --list` + **임시 DB 실복원**을 한다. 실복원을 못 하면 `structure_only` 로 **어디까지 봤는지 말한다** (D-204) | **완료** |
| 13 | `ID_BATCH_SIZE=500` 근거 주석 | PG 한계(**65535** 바인드 파라미터)로 정정. 500 을 유지하는 이유는 상한이 아니라 **계획 품질**이라고 적었다 | **완료** |

## 3번이 왜 가장 위험했나 (기록)

예전 `is_write_conflict()` 는 **모든 `IntegrityError` 를 재시도 대상**으로 봤다. SQLite 에서는
대체로 맞았다 — `database is locked` 가 진짜 일시적 상태였기 때문이다.

PG 에서는 **진짜 제약 위반(유니크 충돌·FK 위반)이 10회 재시도 후 503 「다시 시도」로 나간다.**
데이터 버그가 일시적 오류로 위장한다. 조용히 틀리는 종류의 실패다.

감사에서 실제로 갈린 자리 다섯은 **유니크 위반이 나올 수 없는 순수 UPDATE·요청 끝 커밋**이었다
(`core/deps.py` 요청 끝 커밋, `core/sessions.py` 부수효과 커밋, `notifications` 읽음 처리 셋).
거기서 `IntegrityError` 를 삼키면 그것이 바로 D-191 이 말한 위장이다 — 그 다섯은
`is_serialization_conflict` 로 좁혔다.

40곳 전부의 분류(파일·줄·함수·`except` 절)는 원장에 남겼다:
[`../EVIDENCE/S2/conflict_reclassification_audit.txt`](../EVIDENCE/S2/conflict_reclassification_audit.txt).

## `--workers 1` 잠금 해제 (D-192) — **해제됐다**

지금 워커를 못 늘리던 이유는 성능이 아니라 **방어가 프로세스 메모리 안에 있었기 때문**이다.

| 대상 | 어디로 갔나 |
|---|---|
| `login/chat/game_ai/assistant` rate limiter | **`rate_limit_buckets` 표** (token bucket, `INSERT … ON CONFLICT … RETURNING` 한 문장). 리미터는 **자기 트랜잭션에서 커밋**한다 — 요청 롤백이 토큰을 되감으면 방어가 꺼진다 (D-217) |
| `tickets/claim_lock.py` | `pg_try_advisory_xact_lock(NS_TICKET_CLAIM, hashtext(page_id))` |
| `quotas/quota_lock.py` | `pg_advisory_xact_lock(NS_QUOTA, hashtext(user_id))` + `lock_timeout` |
| `search/indexer.py` reindex · `tickets/router.py` sync · `notion_console` create | 전역 advisory lock (NS 3·4·5) |
| `SettingsCache` | 요청 길목(`get_db`)에서 **TTL 30초 갱신** |

잠금은 **잠금 전용 커넥션**에 건다 (D-216) — 요청 세션에 걸면 잠긴 구간 안의 `db.commit()`
하나가 잠금을 조용히 푼다.

**순서 규약을 지켰다: 저장소를 먼저 만들고 그 다음에 워커를 올렸다.**
`deploy/systemd/clovirone-web-assistant.service` 는 이제 `--workers 4` 이고, 그 주석이
「무엇을 옮겼기에 올릴 수 있게 됐는가」와 「`max_connections` 계산」을 함께 적고 있다.

## 계획에 없던 발견 — 모델/마이그레이션 어긋남

옛 체인이 만들고 안 지운 이름 **88개 중 10개가 모델에 없었다.** 기준선을 모델에서 생성하는
순간 그 열이 조용히 사라진다.

| 사라질 뻔한 것 | 사라지면 |
|---|---|
| `ux_prompts_published_dedup` · `ux_policies_published_dedup` · `ux_offboarding_runs_open_user` | 「같은 이름의 발행본이 둘」·「같은 사람의 열린 오프보딩이 둘」을 아무도 안 막는다 |
| `ix_jobs_claim` | 워커 claim 이 순차 스캔이 된다 — "큐가 밀린다" 로만 보인다 |
| `ix_notifications_user_unread` · `ix_board_posts_created_at` · `ix_conversations_updated_at` · `ix_schedule_runs_created_at` · `ix_audit_logs_object_id` · `ix_mail_deliveries_created_at` | **화면은 멀쩡하다.** 느려질 뿐이고 데이터가 쌓인 뒤에야 나타난다 |

**셋 다 오류를 내지 않는다.** 그래서 사람이 알아채는 경로가 없다.

처음 만든 검사가 이 중 여섯을 놓쳤다 — 좁은 정규식이 0041 의 「목록 변수를 도는」 형태를
못 봤다. 지금 검사는 문자열 리터럴 전수를 훑고, **찾은 이름이 60개 미만이면 스스로 실패한다**
(D-213: 빈 결과는 통과가 아니다).

열 개 다 모델에 올렸다. 지키는 것은
`tests/regression/test_baseline_carries_every_legacy_index.py` 와, 옛 왕복 시험을 다시 쓴
`tests/regression/test_migration_00*.py` 6개다. 상세는 D-221.

## `app/**` 밖에도 둘 있었다 — 도구가 안 따라왔다

13항은 `app/**` 을 본다. 그래서 마지막에 **실행 코드 전체**를 한 번 더 훑었다 — 주석과
설명 문장을 걷어내고 토큰만 보는 방식이다. 이 저장소는 「왜 이렇게 됐는가」를 주석에 많이
적어 두어서, `sqlite` 문자열만 세면 **129건**이 나오고 그중 진짜는 몇 건 없다.

| 자리 | 무엇이었나 | 무엇을 했나 |
|---|---|---|
| `deploy/00-precheck.sh` | `apt-get -s install … sqlite3 …` 를 모의하고 있었다. **사전 점검이 초록인데 설치가 패키지에서 죽는다** | 설치 스크립트가 실제로 까는 목록과 같게 맞췄다(`postgresql-client-16`·`rsync` 포함) + 왜 같아야 하는지 주석 |
| `scripts/restore_rehearsal.py` | 죽은 SQLite 구현 340줄이 이미 지운 `app.backups.sqlite_backup` 을 import 했다 | 지웠다. 다만 **첨부 확인(BKP-02)만 PG 로 옮겨 살렸다** — 저장소 종류를 안 타는 질문이라서다. 리허설 본체 이식은 계획대로 S12(P-23a) |

**남아 있고 남아 있어야 하는 것**도 셋이다. 「SQLite 의존 0」을 문자열 수로 세면 이 셋 때문에
틀린 결론이 나온다:

* `scripts/backup-cron.sh` 의 `database.sqlite` — **n8n 자기 DB** 다. 우리 것이 아니다
* `scripts/rollback-…sh` 의 `web.sqlite3` 검사 — **일부러 거부하려고** 보는 것이다
* `scripts/bench/*.py` — S1 이 운영 SQLite 를 실측할 때 쓴 도구다. 운영 데이터가 아직
  거기 있으므로 **S13·S14 가 그대로 쓴다**
