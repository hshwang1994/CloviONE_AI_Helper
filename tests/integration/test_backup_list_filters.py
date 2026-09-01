"""백업·리허설 목록의 조건은 **서버가 건다** (2026-09-01).

두 목록은 상한에서 잘린다(최신 50건 · 최신 20건). 그런데 화면의 조건(「실패한 백업만」·
「실패한 리허설만」)이 `clientFilter` 라 **받아 온 것 안에서만** 걸렸다. 그래서 질문이
조용히 바뀌어 있었다:

    사람이 물은 것: 「실패한 백업이 있나」
    화면이 답한 것: 「최근 50건 안에 실패한 백업이 있나」

그 둘이 갈리는 순간(51번째 이후에 실패가 있는 설치) 화면은 「없다」라고 답하고, 그
사실을 말할 방법이 없었다 — 「필터에 안 걸림」과 「애초에 안 옴」이 화면에서 같아 보인다.
조건을 서버가 받으면 상한이 **그 조건 안에서** 최신 N건이 되어 질문에 실제로 답한다.

여기서 고정하는 것 셋:
  1) 상한 너머에 있는 실패도 조건을 걸면 나온다(이 파일의 핵심).
  2) 파일 여부(`file_state`)는 상태와 **다른 축**이다 — 따로 걸린다.
  3) 모르는 값은 400 이 아니라 **무시**다(옛 저장된 뷰 링크가 오류 화면이 되지 않게).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration


def _seed_backups(db, now, *, failures_at_the_bottom: int = 1, filler: int = 60):
    """오래된 실패 + 그 위를 덮는 최신 성공 행들. 실패가 상한(50) 밖으로 밀려난다."""
    from app.backups.models import (
        FILE_PRESENT,
        FILE_REMOVED,
        STATUS_FAILED,
        STATUS_VERIFIED,
        Backup,
    )

    rows = []
    for i in range(failures_at_the_bottom):
        rows.append(Backup(
            path=f"/var/backups/old-failed-{i}",
            status=STATUS_FAILED,
            file_state=FILE_PRESENT,
            created_at=now - timedelta(days=200 + i),
        ))
    for i in range(filler):
        rows.append(Backup(
            path=f"/var/backups/recent-ok-{i}",
            status=STATUS_VERIFIED,
            # 절반은 내려받은 뒤 서버에서 지운 것 — 「성공했다」와 「지금 되돌릴 수 있다」는
            # 다른 사실이고, 그 차이를 거를 수 있어야 한다.
            file_state=FILE_REMOVED if i % 2 else FILE_PRESENT,
            created_at=now - timedelta(hours=i + 1),
        ))
    db.add_all(rows)
    db.commit()


def test_failed_backup_below_the_cap_is_still_findable(client, login_as, db, fake_clock):
    now = fake_clock.now()
    _seed_backups(db, now)
    login_as("system_admin")

    # 조건 없이 열면 상한(50) 안에 최신 성공 행만 들어와 실패가 안 보인다 — 그게 이 결함이다.
    plain = client.get("/api/admin/backups")
    assert plain.status_code == 200, plain.text
    assert not [r for r in plain.json()["items"] if r["status"] == "failed"], (
        "표본을 잘못 심었다 — 실패 행이 상한 안에 들어와 있으면 이 시험이 아무것도 안 잰다"
    )

    filtered = client.get("/api/admin/backups?status=failed")
    assert filtered.status_code == 200, filtered.text
    items = filtered.json()["items"]
    assert items, "상한 너머의 실패한 백업을 조건으로도 못 찾는다"
    assert all(r["status"] == "failed" for r in items)


def test_file_state_is_a_separate_axis(client, login_as, db, fake_clock):
    now = fake_clock.now()
    _seed_backups(db, now)
    login_as("system_admin")

    removed = client.get("/api/admin/backups?file_state=removed")
    assert removed.status_code == 200, removed.text
    assert removed.json()["items"], "서버에서 지운 백업만 보는 조건이 아무것도 안 준다"
    assert all(r["file_state"] == "removed" for r in removed.json()["items"])

    both = client.get("/api/admin/backups?status=verified&file_state=present")
    assert both.status_code == 200, both.text
    assert all(
        r["status"] == "verified" and r["file_state"] == "present"
        for r in both.json()["items"]
    )


def test_unknown_filter_values_are_ignored_not_rejected(client, login_as, db, fake_clock):
    now = fake_clock.now()
    _seed_backups(db, now, filler=3)
    login_as("system_admin")

    resp = client.get("/api/admin/backups?status=made-up&file_state=nonsense")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"], "모르는 값을 조건으로 읽어 목록을 비웠다"


def test_failed_rehearsal_below_the_cap_is_still_findable(client, login_as, db, fake_clock):
    from app.backups.models import RestoreRehearsal

    now = fake_clock.now()
    rows = [RestoreRehearsal(
        source_label="오래된 실패",
        started_at=now - timedelta(days=300),
        finished_at=now - timedelta(days=300),
        ok=False,
    )]
    for i in range(25):
        rows.append(RestoreRehearsal(
            source_label=f"최근 통과 {i}",
            started_at=now - timedelta(hours=i + 1),
            finished_at=now - timedelta(hours=i + 1),
            ok=True,
        ))
    db.add_all(rows)
    db.commit()

    login_as("system_admin")
    plain = client.get("/api/admin/backups/rehearsals")
    assert plain.status_code == 200, plain.text
    assert not [r for r in plain.json()["items"] if not r["ok"]], (
        "표본을 잘못 심었다 — 실패 기록이 상한 안에 들어와 있다"
    )

    failed = client.get("/api/admin/backups/rehearsals?ok=false")
    assert failed.status_code == 200, failed.text
    items = failed.json()["items"]
    assert items, "「언제 마지막으로 실패했나」에 이 화면이 여전히 답하지 못한다"
    assert all(r["ok"] is False for r in items)
