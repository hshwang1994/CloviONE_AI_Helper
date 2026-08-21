# BACKLOG — ClovirAssist 자체 데이터 플랫폼 전환

> **의미 있는 큰 작업 단위만 적는다. Micro Task 목록을 만들지 않는다.**
> 각 항목은 Session 하나가 스스로 끝낼 수 있는 크기이고, 종료는 [`MASTER_PLAN.md`](MASTER_PLAN.md)
> §9.0 종료 규약을 따른다. 진행 상태는 [`WORK_STATE.md`](WORK_STATE.md) 가 정본이다.
>
> 상태 값: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`(외부 원인만).
> **한 항목을 "일부 했다" 로 닫지 않는다** — 남은 것은 사유와 Owner Session 을 적어 이관한다 (E9).

**기록 시점**: 2026-08-21 (S0)

---

## Phase A — 기반

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-00** | Plan 을 Repository 지속 문서로 정착 | S0 | **DONE** | 다음 `/clear` 세션이 저장소 문서만으로 이어받을 수 있다 |
| **P-01** | Probe 8건 신뢰성 수정 — **빈 결과 FATAL화 포함** | S1 | TODO | 8건 전부 양방향 `--self-test` 를 갖고, 실패 시 아무것도 보고하지 않는다 |
| **P-02** | **S1 결정에 필요한 미확인 항목만 확인** (확보된 Inventory 재조사 금지) | S1 | TODO | S1 이 실제로 결정에 쓰는 값이 확인됐다. **상세 전수 목록은 이 항목의 완료 조건이 아니다** — Owner Session 이 필요할 때 갱신한다 |
| **P-03** | PG 스택 성능 검증 — recall/지연/인덱스 파라미터/임베딩·리랭킹 모델 확정 | S1 | TODO | 실측 수치와 확정 파라미터가 `DECISIONS.md` 에 기록. **Version 판정이 아니다**(D-188 확정) |
| **P-04** | `VARCHAR(n)` 13개 컬럼 실데이터 길이 감사 | S1 | TODO | 초과 건수와 대응(확장/절단/Exception)이 컬럼별로 결정됨 |
| **P-05** | **PostgreSQL Foundation** — 앱 고유 ~60 테이블 이식, 도메인 변경 없음 | S2 | TODO | `DATABASE_URL=postgresql://…` 로 전 회귀 통과 · **SQLite Runtime 의존 0** |
| **P-06** | `is_write_conflict()` 재분류 + 115 호출부 전수 감사 | S2 | TODO | 직렬화 실패만 재시도. 유니크 충돌은 호출부에서 국소 처리 + 음성 테스트 (R1) |
| **P-07** | 부분 유니크 3건 · rowid 제거 · `jsonb` 이전 · `SKIP LOCKED` | S2 | TODO | 각각 회귀 테스트 동반. `postgresql_where=` 가 실제로 부분 유니크임을 단언 (R2) |
| **P-08** | 공유 rate-limit/lock 저장소 → **`--workers` 잠금 해제** | S2 | TODO | **저장소를 먼저 만들고 그 다음에 워커를 올린다** (D-192) |
| **P-09** | Test Harness 2계층 재구성 + **동시성 테스트 약 40개 재작성** | S2 | TODO | PG 의미(행 잠금·`SKIP LOCKED`·직렬화 실패)를 단언. `qa-contract-replaced-by:` 사용 (R3) |
| **P-10** | Product Identity · Hostname · TLS | S3 | TODO | `openssl s_client` CN/SAN 일치 · `ssl_verify_result=0` · 프로브 TLS 검증 켠 채 통과 |
| **P-11** | **설치 · 배포 자동화 Foundation** — `deploy/install.sh` Stage 0~18 | S4 | TODO | LXD Clean 설치 성공 · 재실행 무해 · 실패 위치/원인 표시 · upgrade/rollback/uninstall 각 1회 · S4 범위 Reboot 복구 |

## Phase B — 도메인

| ID | 작업 | Session | 상태 | 완료의 정의 |
|---|---|---|---|---|
| **P-12** | Identity & Access — roles/permissions/org_units/resource_ownership | S5 | TODO | RBAC allow/deny/scope 음성 테스트 · 기존 5역할 동등성 회귀 |
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
| **P-32** | Final Audit · **Full Capture(최초이자 유일)** · 설치 Acceptance 완주 | S22 | TODO | `MASTER_PLAN.md` §10 + CLAUDE.md §13 20항 + `INSTALLATION.md` §8 전 단계 |

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
