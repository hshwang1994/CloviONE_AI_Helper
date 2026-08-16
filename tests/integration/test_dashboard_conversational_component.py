"""D-118 — the dashboard's `components` dict only surfaces `worker_conversational`
for installs that have actually turned the lane on at some point. Most installs
never will (the setting defaults off) — showing a permanently-"응답 없음" tile for
a feature nobody enabled would be a false alarm on every fresh install/upgrade,
not an improvement in observability.
"""

import pytest

pytestmark = pytest.mark.integration


def test_dashboard_hides_the_conversational_tile_when_never_enabled(client, login_as):
    """The common case (today, every real install): flag off, no heartbeat ever
    written. The tile must not appear at all — not as 'down', not as 'unknown'."""
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    assert "worker_conversational" not in body["components"]
    # The pre-existing components are untouched by this change.
    assert set(body["components"]) == {"web", "worker", "scheduler"}


def test_dashboard_shows_the_conversational_tile_once_the_flag_is_on(client, login_as, settings):
    settings.worker_conversational_lane_enabled = True
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    # No heartbeat written yet in this test, so it reads the same as any other
    # component that has never beaten: "unknown", not a crash and not "up".
    assert body["components"]["worker_conversational"] == "unknown"


def test_dashboard_keeps_showing_the_tile_after_the_flag_is_turned_back_off(client, login_as, settings, db, fake_clock):
    """An operator who enabled the lane, saw it running, then disabled it again
    should still see that it exists and is now down — not have the tile silently
    vanish and lose the signal that something changed."""
    from app.health.service import write_heartbeat

    write_heartbeat(db, "worker_conversational", fake_clock.now())
    db.commit()

    settings.worker_conversational_lane_enabled = False
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    assert "worker_conversational" in body["components"]
