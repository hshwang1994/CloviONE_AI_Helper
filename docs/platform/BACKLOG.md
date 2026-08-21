# BACKLOG — ClovirAssist 자체 데이터 플랫폼 전환

> **의미 있는 큰 작업 단위만 적는다. Micro Task 목록을 만들지 않는다.**
> 각 항목은 Session 하나가 스스로 끝낼 수 있는 크기이고, 종료는 [`MASTER_PLAN.md`](MASTER_PLAN.md)
> §9.0 종료 규약을 따른다. 진행 상태는 [`WORK_STATE.md`](WORK_STATE.md) 가 정본이다.
>
> 상태 값: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`(외부 원인만).
> **한 항목을 "일부 했다" 로 닫지 않는다** — 남은 것은 사유와 Owner Session 을 적어 이관한다 (E9).

**기록 시점**: 2026-08-21 (S0) · **갱신**: 2026-08-21 (S1 — P-01~P-04 DONE)

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
| **P-09a** | **`static_checks.sh` 가 지금 빨간불이다 — S2 가 만든 것이 아니다** | UI 축 | TODO | S1 이후 UI 커밋 둘이 남긴 것이고 S2 는 두 파일 다 안 건드렸다(증거: `git blame`). ① `4dd62181` 이 사용자 문구에 가운뎃점(·) **7건**을 넣었다(`Integrity.jsx`·`AccentPicker.jsx`·`Sprint.jsx`·registry 4곳) — 규약은 `clovi-allow-glyph` 를 같은 줄에 적거나 글자를 바꾸는 것. ② `dac17928` 이 `frontend/src/ui/theme.js`(토큰 정본)를 고치고 `node scripts/generate_design_tokens.mjs` 를 안 돌려 `tokens.css` 와 어긋났다. **둘 다 고칠 때까지 모든 Session 이 빨간 정적 검사를 본다** |
| **P-09b** | **정의되지 않은 이름을 잡는 검사가 없다 — S2 가 그것 때문에 500 을 낼 뻔했다** | 플랫폼 축 | TODO | S2 가 `POST /api/tickets/sync` 의 잠금을 advisory lock 으로 바꾸면서 **import 를 빼먹었다.** 문법도 맞고 수집도 되므로 `compileall`·`pytest --collect-only` 다 초록이었고, **그 라우트를 실제로 부르는 시험 세 개**가 전 회귀 마지막 청크에서 빨간불을 내서야 드러났다. 그 시험이 없었으면 운영에서 500 이다. `pyflakes` 를 넣어 보니 전 저장소에 **F821 이 다섯 자리** 더 있다(아래 P-09c). 넣을 곳은 `scripts/static_checks.sh` 이고, `pyflakes` 를 개발 의존으로 올려야 한다 — S2 는 범위 밖이라 여기에 적어 둔다 |
| **P-09c** | 이미 있던 F821 다섯 자리 (S2 와 무관, `git blame` 확인) | 플랫폼 축 | TODO | **`app/tickets/service.py:1369` 의 `split_names` 가 진짜 결함이다** — 그 줄에 닿으면 `NameError` 다(`0a082f36`, 2026-08-07). 쓰는 곳은 `service.py` 인데 import 는 `models.py:35` 에 있고 거기서는 안 쓰인다. `service.py:144` 의 `ProjectVisibility` 는 문자열 주석이라 실행 중에는 안 터지지만 `get_type_hints()` 가 부른다(`0427fd8e`). `scripts/bench/quality.py:78` 의 `sess`, `scripts/ui_qa/approval_e2e.py:35·41` 의 `insecure` 는 S1 도구다(`18aef2de`). 안 쓰이는 import 22건도 함께 남아 있다 |
| **P-10** | Product Identity · Hostname · TLS | S3 | TODO | `openssl s_client` CN/SAN 일치 · `ssl_verify_result=0` · 프로브 TLS 검증 켠 채 통과. **S1 이 스위치를 만들어 뒀다** — `scripts/ui_qa/tls.py` 의 `DEFAULT_VERIFY = True` 한 줄이면 19개 프로브가 함께 켜진다 |
| **P-11** | **설치 · 배포 자동화 Foundation** — `deploy/install.sh` Stage 0~18 | S4 | TODO | LXD Clean 설치 성공 · 재실행 무해 · 실패 위치/원인 표시 · upgrade/rollback/uninstall 각 1회 · S4 범위 Reboot 복구 |

## Phase B — 도메인

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-12** | Identity & Access — roles/permissions/org_units/resource_ownership | S5 | TODO | RBAC allow/deny/scope 음성 테스트 · 기존 5역할 동등성 회귀 |
| **P-12a** | **결재 대리(`/api/admin/approval-delegations`) 범위 게이트** — S1 이 드러낸 결함 | S5 | TODO | `list`·`create`·`revoke` 셋이 `principal` 을 안 받아 **부서 범위 admin 이 남의 부서 결재 대리를 만들고 취소**할 수 있다. 같은 파일의 승인 큐는 이미 `visible_user_ids(db, principal.management)` 로 좁힌다. 고친 뒤 `check_scope_gates.py::KNOWN_GAPS` 에서 그 항목을 **지워야** 검사가 통과한다 |
| **P-13** | `effective_visibility_clause` 단일화 — 목록·상세·Search·**AI** | S5 | TODO | 넷이 **같은 함수**를 쓰는지 정적 검사로 증명 (D-194) |
| **P-14** | Work Domain — Project Key · Ticket 3층 식별자 · 채번 · Relation · Workflow | S6 | TODO | **동시 부하에서 중복 0 · 번호 연속 · 롤백 시 미소비** · `GIT-142` resolution |
| **P-15** | Backlog · Sprint · Kanban · DnD 공통화 | S6 | TODO | Drop 이 Status+Activity+Audit+Notification 을 한 트랜잭션으로 처리 |
| **P-16** | Knowledge Domain — Space · Folder · Document · **Block JSON 정본** · Version | S7 | TODO | Version diff/restore 동작 · Editor lazy load 후 번들 예산 유지 |
| **P-17** | File Storage Providers — Local/NFS/SMB | S8 | TODO | **16항 매트릭스를 NFS·SMB 각각에서 실행한 로그** · 미마운트 시 쓰기 거부 |

## Phase C — AI

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-18** | Model Gateway + Parsing/Indexing Pipeline + `index` worker lane | S9 | TODO | **생성 Adapter 비활성 상태에서** 파싱·색인·임베딩 정상 · injection 회귀 |
| **P-19** | 모델명 하드코딩 2곳 제거 (`app/llm/provider.py` · runner `assistant.py`) | S9 | TODO | 설정으로 일원화. 어디에도 모델명이 박혀 있지 않다 |
| **P-20** | Hybrid Retrieval · **권한을 LIMIT 앞에** · Re-rank · Citation · AI 작업공간 | S10 | TODO | **권한 없는 사용자 질의 시 Context 미포함을 음성 테스트로 증명** · Citation 클릭 이동 |
| **P-21** | n8n · 외부 Runner 3종 제거 | S11 | TODO | 5678/5679/8787/8788/8789 미청취 · Installer·backup-cron·validate script 에 n8n 흔적 0 |

## Phase D — 운영 · 이관

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-22** | Backup / Restore 운영 | S12 | TODO | 복원 후 **앱 기동 + 읽기 경로 호출** 통과. **파일 생성만으로 SUCCESS 안 됨** |
| **P-23** | Migration Tool + Dry Run (Notion + SQLite → 임시 PG) | S13 | TODO | 무결성 전항 0(또는 Exception 분류) · 길이 초과 0 · legacy/canonical 충돌 0 |
| **P-23a** | `scripts/restore_rehearsal.py` PG 이식 | S12 | TODO | 8단계 중 7단계(**복원본으로 앱을 띄워 읽기 경로 호출**)가 저장소에서 가장 정직한 검증 자산이다. S2 가 SQLite 전제를 깨뜨렸고 **조용히 통과하지 않도록 큰 소리로 멈추게** 해 뒀다 — 그 초록을 믿고 복원 계획을 세우는 것이 가장 나쁘다. **죽은 SQLite 구현 340줄은 지웠다**(이미 없는 `app.backups.sqlite_backup` 을 import 하고 있었다) — 되살리지 말고 PG 기준으로 다시 써라. 옛 구현은 `95a89189` 에 있다. 다만 **8단계 중 첨부 확인(BKP-02)은 살아 있다** — `check_attachment_files()` 는 이미 PG 위에서 돌고 시험도 그대로다. 다시 쓰지 말고 부르면 된다 |
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

이 넷은 **작업이 아니라 입력**이다. 어느 것도 Phase A~B 를 막지 않는다.
상세는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §13.

| 항목 | 필요 시점 | 없을 때 |
|---|---|---|
| 20개 Project Key 명명 | **S6** | S6 이 초안표를 만들어 확인을 받는다. **확정 전 재채번 없음** |
| GitLab Repository 주소·자격증명 | S4(권장) · S22(Acceptance) | Remote 중립 Installer + 오프라인 Bundle 로 진행 |
| 실 NFS/NAS 장비 정보 | S8(있으면 좋음) | 시험 Storage 로 실검증. 실 정보 수령 시 Configuration 만 변경 |
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
