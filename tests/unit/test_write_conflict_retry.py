"""PA-RC-0008 — SQLite 쓰기 경합 재시도 예산/지터를 여러 호출부가 공유한다.

## 왜 필요했나

`app/prompts/service.py::new_version_from`가 예산 5·지터 없이 재시도하다가 8-way
동시 "새 버전" 요청에서 40% 확률로 재시도를 소진해 처리 안 된 `OperationalError`를
그대로 500으로 흘렸다(PA-RC-0008 감사 실측). `app/auth/router.py`의 로그인 재시도만
유일하게 실측 검증된 값(10회 + 지터, 10-way 동시 로그인 스트레스 시험)이었다 — 그
값을 `app/core/db.py`로 승격해 여러 호출부가 공유한다.

재시도 **루프 구조**(SAVEPOINT 실패 후 rollback+재조회 / commit+재계산 / refresh)는
호출부마다 무엇을 다시 읽어야 하는지가 달라 하나로 묶지 않는다 — 여기서 공유하는
건 "몇 번, 얼마나 쉬는지"뿐이다.
"""

from __future__ import annotations

import pytest

from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, write_conflict_backoff

pytestmark = pytest.mark.unit


def test_the_shared_budget_matches_the_only_empirically_validated_value():
    """auth.py 로그인 재시도 스트레스 시험으로 정해진 값 — 임의로 바뀌면 그 근거가 깨진다."""
    assert DEFAULT_WRITE_CONFLICT_RETRIES == 10


@pytest.mark.parametrize("attempt", range(10))
def test_backoff_stays_within_the_tuned_bounds(attempt):
    for _ in range(20):
        wait = write_conflict_backoff(attempt)
        assert 0.01 * (attempt + 1) <= wait <= 0.05 * (attempt + 1), (attempt, wait)


def test_backoff_is_jittered_not_a_single_fixed_value():
    """🔴 지터 없이 상수 지연만 주면 여러 스레드가 계속 같은 타이밍에 다시 부딪힌다."""
    samples = {write_conflict_backoff(3) for _ in range(50)}
    assert len(samples) > 1, f"매번 같은 값이다: {samples}"


def test_games_append_event_retry_budget_is_the_shared_default():
    """PA-RC-0008 — 예전엔 이름 없는 상수 5, 지터 없음이었다."""
    from app.games.service import _APPEND_EVENT_RETRIES

    assert _APPEND_EVENT_RETRIES == DEFAULT_WRITE_CONFLICT_RETRIES == 10


def test_team_chat_seq_retry_budget_is_deliberately_above_the_shared_default():
    """PA-RC-0008 — 전체 채팅은 seq 경쟁이 특히 잦다고 관측돼 공용 기본값(10)보다
    일부러 크게(12) 남겨 뒀다."""
    from app.team_chat.service import _SEQ_RETRIES

    assert _SEQ_RETRIES == 12 > DEFAULT_WRITE_CONFLICT_RETRIES


def test_approvals_create_retry_budget_is_deliberately_above_the_shared_default():
    """PA-RC-0008 — 동시 승인 요청 경합이 관측상 더 잦아 공용 기본값(10)보다
    일부러 크게(12) 남겨 뒀다."""
    from app.approvals.service import _CREATE_RETRIES

    assert _CREATE_RETRIES == 12 > DEFAULT_WRITE_CONFLICT_RETRIES
