"""Circuit breaker behavior (spec §15.6)."""

import pytest

from app.runners.schemas import RunnerConfig
from app.runners.service import can_dispatch, create_runner, record_runner_result

pytestmark = pytest.mark.unit


@pytest.fixture()
def runner(db, settings, app):
    config = RunnerConfig(
        name="circuit-runner", base_url="http://127.0.0.1:8787", enabled=True
    )
    row = create_runner(
        db, config, allowlists=app.state.allowlists, created_by=None
    )
    row.enabled = True  # create_runner forces disabled; enable for dispatch tests
    db.commit()
    return row


def test_disabled_runner_cannot_dispatch(db, runner, fake_clock):
    runner.enabled = False
    allowed, reason = can_dispatch(runner, fake_clock.now())
    assert not allowed
    assert reason == "runner_disabled"


def test_failures_below_threshold_keep_dispatching(db, runner, fake_clock):
    now = fake_clock.now()
    for _ in range(4):
        record_runner_result(db, runner, success=False, now=now)
    assert runner.maintenance_state == "normal"
    assert can_dispatch(runner, now)[0]


def test_threshold_failures_open_circuit(db, runner, fake_clock):
    now = fake_clock.now()
    for _ in range(5):
        record_runner_result(db, runner, success=False, now=now)
    assert runner.maintenance_state == "degraded"
    allowed, reason = can_dispatch(runner, now)
    assert not allowed
    assert reason == "circuit_open"


def test_half_open_after_cooldown_and_recovery(db, runner, fake_clock):
    now = fake_clock.now()
    for _ in range(5):
        record_runner_result(db, runner, success=False, now=now)

    # Cooldown not yet elapsed → still blocked.
    fake_clock.advance(100)
    assert not can_dispatch(runner, fake_clock.now())[0]

    # After cooldown the circuit half-opens: dispatch attempts allowed.
    fake_clock.advance(201)
    assert can_dispatch(runner, fake_clock.now())[0]
    assert runner.maintenance_state == "degraded"  # until a success

    # A success closes the circuit and clears degraded state (자동 복구).
    record_runner_result(db, runner, success=True, now=fake_clock.now())
    assert runner.maintenance_state == "normal"
    assert runner.consecutive_failures == 0
    assert runner.circuit_open_until is None


def test_maintenance_state_blocks_dispatch(db, runner, fake_clock):
    runner.maintenance_state = "maintenance"
    allowed, reason = can_dispatch(runner, fake_clock.now())
    assert not allowed
    assert reason == "runner_maintenance"
