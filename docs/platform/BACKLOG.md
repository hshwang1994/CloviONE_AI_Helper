# BACKLOG — ClovirAssist 자체 데이터 플랫폼 전환

> **의미 있는 큰 작업 단위만 적는다. Micro Task 목록을 만들지 않는다.**
> 각 항목은 Session 하나가 스스로 끝낼 수 있는 크기이고, 종료는 [`MASTER_PLAN.md`](MASTER_PLAN.md)
> §9.0 종료 규약을 따른다. 진행 상태는 [`WORK_STATE.md`](WORK_STATE.md) 가 정본이다.
>
> 상태 값: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`(외부 원인만).
> **한 항목을 "일부 했다" 로 닫지 않는다** — 남은 것은 사유와 Owner Session 을 적어 이관한다 (E9).

**기록 시점**: 2026-08-21 (S0) · **갱신**: 2026-08-23 (S11 — P-21 DONE)

---

## Phase A — 기반

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-00** | Plan 을 Repository 지속 문서로 정착 | S0 | **DONE** | 다음 `/clear` 세션이 저장소 문서만으로 이어받을 수 있다 |
| **P-01** | Probe 8건 신뢰성 수정 — **빈 결과 FATAL화 포함** | S1 | **DONE** | 8건 전부 수정. Checker 5개가 `--self-test` 를 새로 갖고, `probe_selftest` 는 19 → **30 사례**(로직 11 추가) |
| **P-02** | **S1 결정에 필요한 미확인 항목만 확인** (확보된 Inventory 재조사 금지) | S1 | **DONE** | S1 소유 미확인 항목 넷(01·02·04·10 PROBE 계열 + 05·08 VARCHAR + 06 모델)이 전부 닫혔다. 전수 목록은 만들지 않았다 |
| **P-03** | PG 스택 성능 검증 — recall/지연/인덱스 파라미터/임베딩·리랭킹 모델 확정 | S1 | **DONE** | 실 PG16.15 + pgvector 0.6.0 + pg_trgm 1.6 에서 실측. **D-209~D-212** 에 기록 |
| **P-04** | `VARCHAR(n)` 실데이터 길이 감사 | S1 | **DONE** | 모델 선언 410 컬럼 감사. 초과 **1건**(`messages.message_id`)이고 대응은 «넓힌다» — 유니크 키의 일부라 절단이 불가능하다. 상세 `INVENTORY/05_DB.md` |
| **P-05** | **PostgreSQL Foundation** — 앱 고유 표 이식, 도메인 변경 없음 | S2 | **DONE** | 70 표 · 248 인덱스가 `0001_pg_baseline` 하나로 선다(D-189). 전 회귀 PG 통과 · **SQLite Runtime 의존 0**(`app/**` 에서 `sqlite3` import 0) |
| **P-06** | `is_write_conflict()` 재분류 + 호출부 전수 감사 | S2 | **DONE** | **40 호출부 · 24 모듈** 전수 감사(계획 추정 115/30 → 실측, D-221). **재시도 9 · insert-race 31**. **음성 테스트로 증명했다**: `tests/security/test_conflict_classification.py` 가 진짜 FK 위반(`23503`)을 실제 PG 에서 만들어 **어느 통에도 안 들어감**을 확인하고, 요청 끝 커밋이 유니크 위반을 503 으로 포장하지 않는 것까지 본다 (R1 닫힘) |
| **P-07** | 부분 유니크 · rowid 제거 · `jsonb` 이전 · `SKIP LOCKED` | S2 | **DONE** | 부분 유니크 **4개**(실측) `postgresql_where=` · `seq` identity 3표 · `jsonb` **37 컬럼** · claim 에 `FOR UPDATE SKIP LOCKED` (R2 닫힘) |
| **P-08** | 공유 rate-limit/lock 저장소 → **`--workers` 잠금 해제** | S2 | **DONE** | `rate_limit_buckets` 표 + advisory lock 5자리 + SettingsCache TTL. **저장소를 먼저 만들고** systemd 를 `--workers 4` 로 올렸다 (D-192·D-216·D-217) |
| **P-09** | Test Harness 2계층 재구성 + 동시성 테스트 재작성 | S2 | **DONE** | 기본=트랜잭션 되감기 · `@pytest.mark.real_db`=전용 DB(D-218). 계약이 바뀐 시험은 `qa-contract-replaced-by:`/`qa-contract-change:` 로 표시했고 `check_test_strength.py` 가 통과한다 (R3 닫힘) |
| **P-09a** | **`static_checks.sh` 가 지금 빨간불이다 — S2 가 만든 것이 아니다** | UI 축 | TODO | S1 이후 UI 커밋 둘이 남긴 것이고 S2 는 두 파일 다 안 건드렸다(증거: `git blame`). ① `4dd62181` 이 사용자 문구에 가운뎃점(·) **7건**을 넣었다(`Integrity.jsx`·`AccentPicker.jsx`·`Sprint.jsx`·registry 4곳) — 규약은 `clovi-allow-glyph` 를 같은 줄에 적거나 글자를 바꾸는 것. ② `dac17928` 이 `frontend/src/ui/theme.js`(토큰 정본)를 고치고 `node scripts/generate_design_tokens.mjs` 를 안 돌려 `tokens.css` 와 어긋났다. **둘 다 고칠 때까지 모든 Session 이 빨간 정적 검사를 본다**. ③ S5 가 **S4 잔여 둘**을 더 찾았다: `app/worker_main.py:815` 의 로그 문자열에 em 대시(—)(화면 문구가 아니라 서버 로그라 `clovi-allow-glyph` 한 줄이면 끝난다), 그리고 `tests/unit/test_deploy_wiring.py:543` 의 `subprocess.run(text=True)` 에 `encoding=` 이 없다(둘 다 `6909bb96`·`e7a5540a` 에서 왔다 — `git show HEAD:` 로 확인). **S5 는 자기가 넣은 16건을 전부 고쳤고 이 셋은 소유가 다르다**. ⑤ **S7 이 그중 하나를 고쳤다**: `WorkBoard.jsx` 의 「스프린트 만들기」→「스프린트 추가」(표준 동사표, S6 커밋에서 온 것). 같은 규칙의 한 단어라 라우팅보다 고치는 것이 쌌다 — **남은 셋은 그대로 P-09a 소유**다. ④ S6 이 프런트 시험 **셋**을 더 찾았다(전부 S6 이전 커밋에서 왔다 — `git log -L` 로 확인): `ko-wordbreak.test.jsx:179` 의 안 닫힌 JSX 주석(`dac17928`), `SettingVersions.jsx:75` 의 「변경」(표준 동사표는 「수정」, `c1bd9306`), `settings-coerce.test.jsx` 의 「검증 통과」 미표시. **S6 은 자기가 만든 것을 전부 고쳤고 이 셋은 소유가 다르다** |
| **P-09b** | **정의되지 않은 이름을 잡는 검사가 없다 — S2 가 그것 때문에 500 을 낼 뻔했다** | 플랫폼 축 | TODO | S2 가 `POST /api/tickets/sync` 의 잠금을 advisory lock 으로 바꾸면서 **import 를 빼먹었다.** 문법도 맞고 수집도 되므로 `compileall`·`pytest --collect-only` 다 초록이었고, **그 라우트를 실제로 부르는 시험 세 개**가 전 회귀 마지막 청크에서 빨간불을 내서야 드러났다. 그 시험이 없었으면 운영에서 500 이다. `pyflakes` 를 넣어 보니 전 저장소에 **F821 이 다섯 자리** 더 있다(아래 P-09c). 넣을 곳은 `scripts/static_checks.sh` 이고, `pyflakes` 를 개발 의존으로 올려야 한다 — S2 는 범위 밖이라 여기에 적어 둔다 |
| **P-09d** | **`static_checks.sh` 의 systemd 하드닝 검사가 주석에 걸려 통과한다** | 플랫폼 축 | TODO | `grep -q 'NoNewPrivileges=true'` 가 **파일 어디든** 그 글자를 찾는다. 특권 헬퍼 유닛은 실제로는 `NoNewPrivileges=false`(root 로 돌아야 한다)인데 **머리말 주석**에 그 문자열이 있어 초록이다 — 옛 유닛도 새 유닛도 같은 이유로 통과한다. 즉 이 검사는 지금 아무 유닛의 하드닝도 지키지 않는다. `[Service]` 절만 보고, 헬퍼는 「root 로 도는 대신 `ReadWritePaths` 가 좁다」를 확인하는 별도 규칙으로 나눠야 한다. S4 가 새 유닛 5종을 넣으며 발견했고 범위 밖이라 여기 적는다 |
| **P-09e** | **시험 하나가 stdin 때문에 영원히 막힌다 — 그리고 `timeout=` 이 그것을 못 푼다** | 플랫폼 축 | TODO | `tests/regression/test_stage_static_update.py` 가 `subprocess.run(capture_output=True, timeout=300)` 으로 셸 스크립트를 부른다. stdin 이 **안 닫힌 파이프**면(백그라운드 실행이 그렇다) 그 자식이 stdin 을 읽다 막히고, 파이썬의 `timeout=` 은 **손자 프로세스를 안 죽여** 파이프가 안 닫히므로 5분이 지나도 안 풀린다. 겉보기에는 pytest 가 한 자리에서 멈춘 것이고 **CPU 도 0** 이라 「오래 걸리는 시험」과 구별되지 않는다. S5 가 여기서 두 번 걸려 회귀를 두 번 버렸다. 임시 조치로 `scripts/run_full_regression.sh` 가 `< /dev/null` 을 붙인다 — **근본 조치는 시험이 `stdin=subprocess.DEVNULL` 을 넘기는 것**이고, 같은 모양이 저장소에 더 있는지(`capture_output=True` 로 셸을 부르는 자리) 함께 봐야 한다 |
| **P-09c** | 이미 있던 F821 다섯 자리 (S2 와 무관, `git blame` 확인) | 플랫폼 축 | TODO | **`app/tickets/service.py:1369` 의 `split_names` 가 진짜 결함이다** — 그 줄에 닿으면 `NameError` 다(`0a082f36`, 2026-08-07). 쓰는 곳은 `service.py` 인데 import 는 `models.py:35` 에 있고 거기서는 안 쓰인다. `service.py:144` 의 `ProjectVisibility` 는 문자열 주석이라 실행 중에는 안 터지지만 `get_type_hints()` 가 부른다(`0427fd8e`). `scripts/bench/quality.py:78` 의 `sess`, `scripts/ui_qa/approval_e2e.py:35·41` 의 `insecure` 는 S1 도구다(`18aef2de`). 안 쓰이는 import 22건도 함께 남아 있다 |
| **P-10** | Product Identity · Hostname · TLS | S3 | **DONE** | CN/SAN 이 `clovirassist.gooddi.lab` 로 일치하고 `ssl_verify_result=0` 이다 — **반례도 함께 남겼다**(기준점 없이 18 · 이름 다르면 1). `DEFAULT_VERIFY = True` 로 켰고, 자체서명이라 켜는 것만으로는 부족하다는 것이 이 세션의 발견이다(D-223): 신뢰 기준점을 `UI_QA_TLS_CA` 로 준다. **브라우저 프로브까지 켠 채 통과한다** — 실행 머신에 인증서를 설치하고 `NODE_EXTRA_CA_CERTS` 까지 채운 뒤다(P-10a) |
| **P-10a** | **브라우저 프로브의 신뢰 기준점** | S3 | **DONE** | 사용자가 인증서를 Windows CurrentUser\Root 에 설치했고, 그때서야 **기준점이 세 갈래**라는 것이 드러났다: Chromium 의 `page.goto` 는 운영체제 저장소, 파이썬 `ssl` 은 OpenSSL 기본, **Playwright 의 `context.request` 는 Node 번들 CA** 다. 셋째를 안 채우면 `page.goto` 만 200 이고 `_fetch_me` 가 조용히 None 이라 하네스가 TLS 를 한 마디도 안 하고 «인증을 인정하지 않습니다» 로 죽는다 — 실제로 그렇게 한 번 죽었다. `tls.py` 가 `NODE_EXTRA_CA_CERTS` 를 함께 심고, `run.py` 도 다른 18개와 같은 진입점을 쓴다. `--insecure` 없이 smoke 통과(억제 0건) · 반례로 `ERR_CERT_COMMON_NAME_INVALID` 확인 |
| **P-11** | **설치 · 배포 자동화 Foundation** — `deploy/install.sh` Stage 0~18 | S4 | **DONE** | LXD 리허설 **34항 전부 통과**(`EVIDENCE/S4/lxd_rehearsal.txt`): Clean 설치 · 재실행 무해 · `--inject-failure` 로 멈춘 Stage 번호·이름·사유가 표준 출력에 · rollback(체크섬 → 복원 → verify) · upgrade · uninstall/재설치 · **옛 slug 이전**(업로드·비밀이 따라오고 옛 경로·유닛·계정이 사라진다, R13). **실 커널 재부팅 복구**는 따로 했다 — `boot_id` 가 바뀐 것을 먼저 확인하고 수동 명령 0회로 전 유닛 복귀 (`EVIDENCE/S4/reboot_recovery.txt`). 결정 **D-225~D-229** |

## Phase B — 도메인

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-12** | Identity & Access — roles/permissions/org_units/resource_ownership | S5 | **DONE** | `permissions` 32 · `roles` 5(builtin) · `role_permissions` 107 · `user_roles` · `resource_grants` 가 `0002_identity_access` 로 선다. **다섯 역할의 뜻은 안 바뀌었다** — 옮긴 게이트 7종 × 5역할을 표와 실제 요청 양쪽에서 전수 대조했다(`test_builtin_role_equivalence.py`). `departments` → `org_units`(D-234) · auth Provider 분리(D-235). `resource_ownership` 은 **개념**으로 남기고 대신 D-193 의 빠져 있던 항 `Project Member` 를 실제 갈래로 넣었다(D-233) |
| **P-12a** | **결재 대리(`/api/admin/approval-delegations`) 범위 게이트** — S1 이 드러낸 결함 | S5 | **DONE** | 셋 다 `principal` 을 받는다. `list` 는 `delegation.apply_scope`, `revoke` 는 `get_scoped_or_404`(범위 밖 **404**), `create` 는 **위임자와 대리자 양쪽**이 범위 안이어야 한다 — 한쪽만 보면 내 부서 권한이 남으로 새거나 남의 권한이 내 부서로 들어온다. `check_scope_gates.py::KNOWN_GAPS` 는 이제 **비어 있고**, 검사가 「미해결 GAP 0건」을 찍는다 |
| **P-13** | `effective_visibility_clause` 단일화 — 목록·상세·Search·**AI** | S5 · S10 | **DONE** | 판정이 `app/authz/visibility.py` 한 곳이다. **규칙 하나가 SQL 절과 행 판정 두 표현을 함께 든다**(D-231) — 옛 상태는 공용 파일 안에서도 판정이 넷이었다(소속 2 · 열람 제한 2). `scripts/check_visibility_single_source.py`(자기검증 5사례)가 소비자 **6개**의 도달을 확인하고, `test_visibility_two_renderers_agree.py` 가 자원 3종 × 사람 5명을 진짜 행으로 대조한다. **AI 경로도 S10 이 같은 함수에 연결했다** — `app/ai/retrieval/service.py::visible_document_ids` 가 소비자 여섯 번째이고, `check_visibility_single_source.py` 가 그 도달을 확인한다. chunk 에 권한 컬럼이 없으므로(D-256) 그 질의가 **유일한 판정**이다 |
| **P-14** | Work Domain — Project Key · Ticket 3층 식별자 · 채번 · Relation · Workflow | S6 | **DONE** | `project_key_registry`(예약 `GIT`) · `ticket_cache` → `tickets`(D-238) · `seq`/`canonical_key`/`legacy_key` + BEFORE 트리거(D-236) · `project_ticket_counters` 채번(D-196) · `ticket_key_aliases` · `ticket_relations`(계층 정본, D-239) · `ticket_statuses` + `app/work/workflow.py`. **동시 12건에서 1..12 가 정확히 한 번씩**(반례 포함) · 롤백 시 미소비 · `GIT-142` 가 Key 변경 뒤에도 같은 티켓 · Exception 임의 배정 0. Project Key 20건은 **확정됐고**(D-243) `apply_confirmed()` 가 이름으로 잇는다 — 못 찾으면 배정하지 않는다. 재채번은 S13 이다(D-197) |
| **P-15** | Backlog · Sprint · Kanban · DnD 공통화 | S6 | **DONE** | `/api/work/board`·`/backlog`·`/sprints` + `sprints` 표 + `backlog_rank`(소수 순위, D-241). Drop 이 Status+Activity+Audit+`updated_at`+Notification 을 **한 트랜잭션**으로 처리하고(D-242), 실패를 주입해 다섯이 함께 사라지는지까지 본다. DnD 는 `frontend/src/ui/DragDrop.jsx` **한 부품**이고 키보드가 1급이다(스페이스로 집고 화살표로 옮긴다) |
| **P-14a** | **문자열 날짜 컬럼 → `date`/`timestamp`** (SQLite 실측 10번) | S7 | **DONE** | **16컬럼을 한 번에 옮겼다** — 달력일 11(`date`) · 시각 5(`timestamp`), `0005_real_dates`. 반씩 하면 더 나쁘다는 판단 그대로다: 티켓·프로젝트·문서가 같은 규약을 공유하고 동기화 파서·필터·리포트·번다운·홈 위젯이 전부 그 규약으로 비교한다. **화면 계약(ISO 문자열)은 안 바뀌었고** 경계는 `app/core/dates.py` 하나다. 옮기면서 조용한 결함 둘이 드러났다 — `_last_activity_on` 의 `isinstance(str)` 갈래(컬럼이 timestamp 가 되면 영영 거짓이라 「저쪽에서 만진 시각」이 버려진다)와 `projects/sync.py::_apply` 의 값 비교(문자열 vs date 는 영영 다르라서 매 회차 전 프로젝트의 `updated_at` 이 덮인다). 둘 다 오류를 안 낸다. 결정 **D-248** · 시험 `tests/regression/test_real_date_columns.py` |
| **P-16** | Knowledge Domain — Space · Folder · Document · **Block JSON 정본** · Version | S7 | TODO | Version diff/restore 동작 · Editor lazy load 후 번들 예산 유지 |
| **P-17** | File Storage Providers — Local/NFS/SMB | S8 | **DONE** | 실 NFS·실 SMB 각각 **16/16 PASS**([`EVIDENCE/S8/`](EVIDENCE/S8/README.md)) · 마운트를 실제로 뗀 상태에서 쓰기 거부 확인 · 실 재부팅 뒤 수동 명령 0회 복귀. 결정 **D-249~D-253** |

## Phase C — AI

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-18** | Model Gateway + Parsing/Indexing Pipeline + `index` worker lane | S9 | **DONE** | 생성 Adapter 를 끈 채로 **실 모델 17/17 PASS**([`EVIDENCE/S9/`](EVIDENCE/S9/README.md)) · 임베딩 모델까지 없어도 chunk 는 서고 벡터 칸만 NULL · injection 회귀 13건. 결정 **D-254~D-259** |
| **P-19** | 모델명 하드코딩 2곳 제거 (`app/llm/provider.py` · runner `assistant.py`) | S9 | **DONE** | 둘 다 제거. 비어 있으면 **설정 안 됨**이고(fail-closed) `build_argv()` 가 예외를 던진다. 임베딩 모델만 `app/ai/catalog.py` 에 있고 정적 검사가 그 파일만 면제한다 (**D-254**) |
| **P-20** | Hybrid Retrieval · **권한을 LIMIT 앞에** · Citation · AI 작업공간 · 생성 | S10 | **DONE** | 세 레인이 `effective_visibility_clause` 가 만든 후보 집합 안에서만 돈다 — 음성 시험 10건이 「답변에 안 나왔다」가 아니라 **모델에게 실제로 넘어간 문자열**을 본다. 권한 변경의 반영 지연은 **0**(chunk 를 한 줄도 안 다시 만든다, D-256). 인용은 `?block=` 까지 가고(D-263), 생성이 막혀도 검색·인용은 그대로 돈다. 가중치·상한은 실측으로 정했다(D-260·D-261). Re-rank 는 없다(D-212 · D-255) |
| **P-21** | n8n · 외부 Runner 3종 제거 | S11 | **DONE** | 다섯 포트 전부 **미청취**이고 `systemctl list-unit-files` 가 **0건**이다 — 정지만 하면 재부팅에 돌아오므로 유닛 파일까지 걷어냈다. Installer·backup-cron·validate script 의 n8n 흔적 **0**(`test_external_automation_removed.py` 가 회귀로 지킨다). 러너를 직접 부르던 기능 셋(채팅·대시보드 요약·AI 퀴즈)은 **Gateway 로 옮겼다**(D-266) — 그 김에 프롬프트 방어가 셋 다에 걸렸다. 표 넷과 컬럼 둘은 `0009` 가 내렸다(D-267). 원장 [`EVIDENCE/S11/`](EVIDENCE/S11/README.md) |

## Phase D — 운영 · 이관

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-22** | Backup / Restore 운영 | S12 | **DONE** | 백업 하나가 **세트**가 됐다 — 덤프 + 매니페스트 + `SHA256SUMS`(D-269). 매니페스트가 백업과 **함께 이동**하므로 낯선 서버에서도 스키마 판과 「무엇이 안 담겼는가」를 읽는다. 파생 넷은 **행만** 빠지고 누가 다시 만드는지가 함께 적힌다(D-270) — 그 정책이 실제로 `pg_dump` 인자까지 가는지를 시험과 리허설 5단계가 **양방향으로** 본다. 보존은 **개수와 나이 둘 다** 넘어야 지운다(D-271, 배포 스냅숏 보존도 함께 세웠다). 다운로드 뒤 서버 파일 삭제는 **사람이 답한 뒤에만**이고 다운로드는 `BACKUP_EXECUTE` 다(D-272). 실 PG + 실 `pg_dump` 에서 **8단계 전부 통과**했고 반례 셋으로 판정이 틀린 쪽으로도 움직이는 것을 보였다(D-273, 원장 [`EVIDENCE/S12/`](EVIDENCE/S12/README.md)) |
| **P-23** | Migration Tool + Dry Run (Notion + SQLite → 임시 PG) | S13 | TODO | 무결성 전항 0(또는 Exception 분류) · 길이 초과 0 · legacy/canonical 충돌 0 |
| **P-23a** | `scripts/restore_rehearsal.py` PG 이식 | S12 | **DONE** | 여덟 단계가 PG 기준으로 다시 섰다 — 앱 자신의 코드로 백업 → 앱 자신의 판정(`verified` 아니면 멈춘다) → **새 데이터베이스**로 복원 → 스키마 성질 대조(부분 유니크의 `WHERE` 원문 포함) → 표·행 수와 **정책** 대조 → `alembic_version` → **복원본으로 앱을 띄워 읽기 경로 13개 호출** → 첨부. 첨부 확인(BKP-02)은 다시 쓰지 않고 그대로 불렀다. 🔴 **첫 회차가 초록인데 인증 경로 11개가 401 이었다** — 판정을 「200 이 아니면 실패」로 고치고 그 회차를 반례로 남겼다(D-273). 하네스 자신도 Known Good/Known Bad/반례로 먼저 검증한다(`tests/regression/test_restore_rehearsal_probe.py`) |
| **P-33** | **세션 쿠키 이름에 옛 정체성이 남아 있다** (`clovirone_session`) | S14 | TODO | `app/core/sessions.py::SESSION_COOKIE_NAME`. 바꾸는 순간 **전원이 로그아웃**되므로 S4 가 건드리지 않았다(D-226). Cutover 는 어차피 세션이 끊기는 자리라 그때 함께 바꾼다. MASTER_PLAN §10-13 「Product-owned Artifact 에 Legacy Identity 잔존 없음」이 이 한 건을 본다 |
| **P-24** | **Cutover + Legacy 제거** (단독 Session) | S14 | TODO | Notion/SQLite Runtime 의존 **0** · Legacy 잔존 0 · Rollback 지점 문서화 |

## Phase E — UI Renewal 재개 (동결 해제)

| ID | 작업 | Session | 원 Wave | 상태 |
|---|---|---|---|---|
| **P-25** | Search/Filter **기능 정확성** — 새 PG Backend 대상 | S15 | W5B (REDEFINE) | **FROZEN** → S15 |
| **P-26** | Table / Grid / Metadata / Alignment + Chart | S16 | W6 | **FROZEN** → S16 |
| **P-27** | Empty / Loading / Error / Feedback + Clovi + Detail Metadata | S17 | W7 | **FROZEN** → S17 |
| **P-28** | Pilot Archetype 8종 — 새 IA 기준 | S18 | W8 (REDEFINE) | **FROZEN** → S18 |
| **P-29** | 나머지 User Route | S19 | W10 (REDEFINE) | **FROZEN** → S19 |
| **P-30** | Admin IA + Admin Console | S20 | W11+W12 | **FROZEN** → S20 |

> **W9 는 독립 항목으로 남기지 않는다** — 화면이 새로 만들어지므로 S6·S7 에 흡수되고,
> "수동 동기화 제거" 는 **동기화 개념 소멸로 자동 해소**된다 (D-207).

## Phase F — 최종

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-31** | Functional E2E 전수 (27범주 + Backlog/Sprint/Board/Space/Citation/Storage) | S21 | TODO | C11~C14 통과 · `exists:true` Flow 에 `NOT_AUDITED` 0 |
| **P-32** | Final Audit · **Full Capture(최초이자 유일)** · 설치 Acceptance 완주 | S22 | TODO | `MASTER_PLAN.md` §10 + CLAUDE.md §11 + `INSTALLATION.md` §8 전 단계 |

---

## 외부 결정 대기 — Backlog 항목이 아니다

이 셋은 **작업이 아니라 입력**이다. 어느 것도 Phase A~B 를 막지 않는다.
(20개 Project Key 는 2026-08-22 에 확정돼 목록에서 빠졌다 — D-243.)
상세는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §13.

| 항목 | 필요 시점 | 없을 때 |
|---|---|---|
| ~~20개 Project Key 명명~~ | ~~S6~~ | **해소 (2026-08-22)** — 초안표 그대로 확정(D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사본은 `PROJECT_KEYS.md`. 적용은 S13 이 적재 직후에 `apply_confirmed()` 로 한다 |
| GitLab Repository 주소·자격증명 | S4(권장) · S22(Acceptance) | Remote 중립 Installer + 오프라인 Bundle 로 진행 |
| 실 NFS/NAS 장비 정보 | ~~S8~~ (받으면 설정만) | **S8 은 시험 Storage 로 끝났다.** 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 — Application 수정은 없다(D-199) |
| 제품 Domain 밖 Notion DB 3종 이관 여부 | 언제든 | 기본값 = 이관하지 않음. Core Migration 은 무관하게 진행 |

---

## 승계된 UI Finding — 소유 Session 이 이미 있다

W5 종료 시점의 잔여 Finding 92건은 **전부 소유 Wave 가 붙어 있다**
(`docs/ui-renewal/WORK_STATE.md` 와 `ROUTE_COVERAGE.json` 이 정본).
Wave → Session 매핑은 위 Phase E 표를 따른다.

| 원 Wave | 건수 | 이관된 Session |
|---|---|---|
| W8 | 26 | S18 |
| W6 | 20 | S16 |
| W12 | 13 | S20 |
| W10 | 11 | S19 |
| W15 | 6 | S22 |
| W13 | 4 | **S3** (맨 앞으로 이동) |
| W14 | 4 | S21 |
| W9 | 4 | S6·S7 흡수 |
| W7 | 4 | S17 |

**이 목록을 여기서 개별 항목으로 다시 펼치지 않는다** — 원장은 `ROUTE_COVERAGE.json` 하나이고,
두 곳에 적으면 갈라진다.
