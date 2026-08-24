"""보존 정책 — **개수 바닥과 나이 바닥을 둘 다** 지키는가 (S12 · P-22).

## 왜 바닥이 둘인가

옛 백업 cron 이 배포 스냅숏에서 겪은 실패가 출발점이다: 개수로만 자르면
**배포가 잦은 날 하루 만에 일주일치 복원 지점이 증발한다**(배포 N번 = 그날 슬롯 N개 소모).
그 스크립트는 「개수가 아니라 나이로」로 고쳤는데, 나이로만 자르면 반대쪽이 열린다 —
하루에 수백 번 도는 사고에서 디스크가 찬다.

그래서 제품 쪽 보존은 **둘 다** 건다. 지우려면 두 관문을 모두 통과해야 한다.

각 축을 **따로** 시험하는 이유: 한 시험에서 둘을 함께 보면 실패했을 때 어느 바닥이
안 걸렸는지 메시지가 말해 주지 못한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.backups.models import (
    FILE_PRESENT,
    FILE_REMOVED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_VERIFIED,
    Backup,
)
from app.backups.service import apply_retention

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 23, 12, 0, 0)


def _add(db, tmp_path, *, days_old: int, status: str = STATUS_VERIFIED,
         file_state: str = FILE_PRESENT, name: str | None = None) -> Backup:
    """실제 파일이 있는 백업 행 하나. 보존이 **파일까지** 지우는지 봐야 하므로 만든다."""
    created = NOW - timedelta(days=days_old, seconds=1)
    target = tmp_path / (name or f"backup-{days_old}d-{status}-{file_state}")
    target.mkdir(parents=True, exist_ok=True)
    (target / "database.dump").write_bytes(b"PGDMP fake")
    row = Backup(
        backup_type="pg_dump", path=str(target), status=status,
        file_state=file_state, created_at=created,
    )
    db.add(row)
    db.flush()
    return row


def _ids(db) -> set[str]:
    return {row.id for row in db.query(Backup).all()}


def test_count_floor_alone_does_not_delete_a_young_backup(db, tmp_path):
    """🔴 개수를 넘겨도 **어리면 안 지운다.** 이것이 옛 백업 cron 이 겪은 그 실패다."""
    rows = [_add(db, tmp_path, days_old=0, name=f"backup-young-{i}") for i in range(5)]
    db.commit()

    apply_retention(db, keep=2, keep_days=7, now=NOW)
    db.commit()

    assert _ids(db) == {r.id for r in rows}, "오늘 만든 백업이 개수 때문에 지워졌다"


def test_age_floor_alone_does_not_delete_within_the_count_window(db, tmp_path):
    """반대쪽 반례 — 오래됐어도 **최근 keep 개 안이면 남는다.**

    이 검사가 없으면 「나이만 본다」 구현도 위 시험을 통과한다.
    """
    rows = [_add(db, tmp_path, days_old=30 + i, name=f"backup-old-{i}") for i in range(3)]
    db.commit()

    apply_retention(db, keep=5, keep_days=7, now=NOW)
    db.commit()

    assert _ids(db) == {r.id for r in rows}, "보관 개수 안에 있는데 나이 때문에 지워졌다"


def test_both_floors_crossed_deletes_the_set_and_its_files(db, tmp_path):
    """둘 다 넘으면 지운다 — 그리고 **디스크의 세트까지** 치운다."""
    survivors = [_add(db, tmp_path, days_old=1 + i, name=f"backup-keep-{i}") for i in range(2)]
    doomed = _add(db, tmp_path, days_old=40, name="backup-doomed")
    doomed_path = doomed.path
    db.commit()

    removed = apply_retention(db, keep=2, keep_days=7, now=NOW)
    db.commit()

    assert removed == 1
    assert _ids(db) == {r.id for r in survivors}
    from pathlib import Path

    assert not Path(doomed_path).exists(), "행만 지우고 디스크에 세트를 남겼다"


def test_removed_file_rows_do_not_occupy_the_count_window(db, tmp_path):
    """파일이 이미 없는 행은 **복원 지점이 아니다.**

    개수 바닥을 그 행에 내주면, 실제로 되돌릴 수 있는 백업이 대신 밀려난다.
    """
    ghost = _add(db, tmp_path, days_old=0, file_state=FILE_REMOVED, name="backup-ghost")
    real = _add(db, tmp_path, days_old=0, name="backup-real")
    db.commit()

    apply_retention(db, keep=1, keep_days=7, now=NOW)
    db.commit()

    ids = _ids(db)
    assert real.id in ids
    assert ghost.id in ids, "어린 행은 나이 바닥이 막아야 한다(개수와 무관하게)"


def test_running_and_latest_failed_are_spared_even_when_both_floors_are_crossed(db, tmp_path):
    """진행 중인 백업은 파일을 쓰는 중이고, 마지막 실패는 장애 추적에 필요하다."""
    running = _add(db, tmp_path, days_old=99, status=STATUS_RUNNING, name="backup-running")
    failed = _add(db, tmp_path, days_old=98, status=STATUS_FAILED, name="backup-failed-new")
    older_failed = _add(db, tmp_path, days_old=99, status=STATUS_FAILED, name="backup-failed-old")
    db.commit()

    apply_retention(db, keep=0, keep_days=0, now=NOW)
    db.commit()

    ids = _ids(db)
    assert running.id in ids
    assert failed.id in ids, "가장 최근 실패까지 지우면 왜 실패했는지 볼 수 없다"
    assert older_failed.id not in ids, "실패가 무한히 쌓이면 목록이 그것으로 채워진다"


def test_zero_keep_days_is_an_explicit_choice_not_a_missing_value(db, tmp_path):
    """🔴 `keep_days=0` 은 「개수만으로 자른다」를 **고른** 값이다.

    `int(config.get("keep_days") or 7)` 처럼 쓰면 0 이 falsy 라 조용히 7 이 된다 —
    관리자가 고른 값과 실제 동작이 달라지고, 그 차이는 아무 오류도 안 낸다.
    """
    from app.backups.service import retention_from_config

    assert retention_from_config({"keep": 2, "keep_days": 0})["keep_days"] == 0
    assert retention_from_config({"keep": 2})["keep_days"] == 7
