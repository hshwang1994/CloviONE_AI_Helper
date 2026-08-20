# INVENTORY 11 — Test

**정본**: `tests/**` · `frontend/src/**/*.test.*` · `runner/claude-work-assistant/test_assistant.py`
**측정**: 2026-08-20
**상태**: ⚠️ **불일치 1건 미해결 — S1 이 실행으로 확정한다**

## 측정

| 대상 | 값 | 출처 |
|---|---|---|
| Backend | **2,837** | Plan Mode 실측 (2026-08-20) |
| Frontend | **2,409 PASS / 0 FAIL** (파일 322) | `docs/ui-renewal/WORK_STATE.md` — W5 종료 시 `npx vitest run` **실행 결과** |
| Runner | **293 PASS** | 동일 |

## ⚠️ 미해결 불일치 — 프런트 테스트 수

Plan Mode 산출물이 프런트 테스트 수를 **두 곳에서 다르게** 적었다.

| 자리 | 값 |
|---|---|
| Plan §17.1 (Inventory 절) | **1,987** |
| Plan §16.3 (W0~W5 자산 보존 절) | **2,409** |
| `docs/ui-renewal/WORK_STATE.md` — **실제 실행 출력** | **2,409 PASS / 0 FAIL, 파일 322** |

**S0 은 이것을 임의로 고르지 않는다.** 실행 출력이 있는 2,409 를 위 표에 적되 불일치를 남겨 둔다.
**S1 이 `cd frontend && npx vitest run` 을 한 번 돌려 확정하고 이 절을 지운다.**

(1,987 이 어느 시점의 값인지, 아니면 세는 단위가 달랐는지 — `test` 개수 대 `it` 개수, 또는
파일 수 대 케이스 수 — 는 지금 판단하지 않는다. **추정으로 숫자를 확정하지 않는다.**)

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

## 테스트 전략 (CLAUDE.md §9)

- 구현 중에는 Focused Test 를 자주, 전체 Regression 은 **Root Cause 묶음이 수렴한 뒤**
- 과거 Test 가 Legacy DOM/CSS/Visual 을 고정하고 있다면 **새 계약을 검증하도록 갱신**한다
- **Assertion 을 약화하거나 Test 를 삭제해서 PASS 시키지 않는다**
- **Test PASS 는 Visual PASS 와 같지 않다**

## 완성도 — S1 이 마저 할 것

1. **프런트 테스트 수 불일치를 실행으로 확정한다** (위 ⚠️ 절 제거)
2. backend 2,837 의 파일별/청크별 분포를 열거한다 — S2 가 어느 청크를 재작성하는지 알아야 한다
3. 재작성 대상 약 40개의 **정확한 파일 목록**을 확정한다 (지금은 glob 패턴뿐이다)
