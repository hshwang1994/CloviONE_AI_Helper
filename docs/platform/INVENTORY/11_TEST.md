# INVENTORY 11 — Test

**정본**: `tests/**` · `frontend/src/**/*.test.*` · `runner/claude-work-assistant/test_assistant.py`
**측정**: 2026-08-20
**상태**: 확보. 프런트 수치는 **동일 Source 의 실행 Evidence 로 확정**됐다 (아래).

## 측정

| 대상 | 값 | 출처 |
|---|---|---|
| Backend | **2,837** | Plan Mode 실측 (2026-08-20) |
| Frontend | **2,409 PASS / 0 FAIL** (파일 322) | `docs/ui-renewal/WORK_STATE.md` — W5 종료 시 `npx vitest run` **실행 결과** |
| Runner | **293 PASS** | 동일 |

## 프런트 테스트 수 — 확정 근거 (재실행하지 않았다)

Plan Mode 산출물이 프런트 테스트 수를 두 곳에서 다르게 적었다: §17.1 이 **1,987**, §16.3 이 **2,409**.

**실행 Evidence 가 있는 쪽으로 확정한다 — 2,409.**

| 근거 | 값 |
|---|---|
| `docs/ui-renewal/WORK_STATE.md` — W5 종료 시 `npx vitest run` **실제 출력** | **2,409 PASS / 0 FAIL, 파일 322** |
| 그 출력의 Source 지문 | `60f8fafb` |
| `60f8fafb..HEAD` 의 `frontend/` diff | **0** — 같은 Source 다 |

같은 Source 에서 나온 신뢰 가능한 실행 결과가 이미 있으므로 **숫자를 정리하려고 Frontend
Regression 을 다시 돌리지 않는다**(D-208 E1). §17.1 의 1,987 은 Plan 초안의 낡은 값으로 본다.

프런트 테스트 수가 다시 문제가 되는 시점은 **Source 지문이 바뀐 뒤**이고, 그때는 어차피 그
Session 이 자기 이유로 `vitest run` 을 돌린다.

## Backend 회귀 구조

`scripts/run_full_regression.sh` 가 4청크로 돈다: **unit · regression · security · integration**.
W5 종료 시 **FULL_REGRESSION_OK**.

현재 Test DB 는 `alembic upgrade head` 로 **템플릿 파일**을 만들고 테스트마다 `shutil.copy` 한다
— **파일 DB 전용 기법이다.**

## 거짓 초록이 될 테스트 약 40개 (R3)

`*_race.py` · `*_write_conflict.py` · `*_lock.py` · `test_worker_lanes_two_processes.py` 계열은
**`database is locked` 문자열과 WAL 단일 writer 의미를 단언한다.**

PG 에서는 **행 잠금 · 직렬화 실패 · `SKIP LOCKED`** 를 단언해야 한다.
**지금 초록인 이 테스트들은 그대로 두면 거짓 초록이 된다** — 잠금 회귀를 못 잡는다.

→ **단순 이식이 아니라 재작성이다** (D-190, S2 소유).
`check_test_strength.py` 가 이 재작성을 "약화" 로 오판하지 않도록 **`qa-contract-replaced-by:`
규약**을 쓴다.

## Test DB 2계층 (D-190)

| 계층 | 방식 | 대상 |
|---|---|---|
| 기본 | 테스트당 트랜잭션 시작 → 종료 시 rollback | 2,837개 **대다수**. 가장 빠르다 |
| 실 DB 필요 | `CREATE DATABASE … TEMPLATE clovir_test_template` | 다중 연결/동시성 **약 40개** + migration 테스트 |

## `check_test_strength.py` 의 한계

**assertion 개수만 센다.** `toBe` → `toBeDefined` 로 바꿔도 통과한다.
기본 `--base HEAD` 라 **커밋된 약화는 영구히 안 보인다** → 기본 base 를 **직전 Session 커밋**으로
(`12_PROBE.md` 우선순위 5).

## 테스트 전략 (CLAUDE.md §7)

- 구현 중에는 Focused Test 를 자주, 전체 Regression 은 **Root Cause 묶음이 수렴한 뒤**
- 과거 Test 가 Legacy DOM/CSS/Visual 을 고정하고 있다면 **새 계약을 검증하도록 갱신**한다
- **Assertion 을 약화하거나 Test 를 삭제해서 PASS 시키지 않는다**
- **Test PASS 는 Visual PASS 와 같지 않다**

## 미확인 항목과 Owner

**S1 것은 없다.** 프런트 수치는 위에서 확정됐고, 나머지는 전부 소비 Session 이 자기 작업을 하면서
확인하는 편이 싸다.

| 미확인 | Owner | 언제 필요한가 |
|---|---|---|
| backend 2,837 의 파일별/청크별 분포 | **S2** | 어느 청크를 재작성하는지 정할 때. **미리 열거하지 않는다** |
| 재작성 대상 약 40개의 정확한 파일 목록 (지금은 glob 패턴) | **S2** | Test Harness 2계층 전환을 실제로 할 때 |
