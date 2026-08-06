"""도달할 수 없는 업로드 파일 청소 (C7).

## 왜 지금까지 안 지웠나

첨부의 DB 행은 부모가 사라질 때 CASCADE 로 지워지지만 **파일은 디스크에 남는다.**
지우는 쪽이 위험해서 일부러 두고 있었다 - 티켓이 잠깐 안 보였다가 다시 보이는 동기화
사고에서 사용자가 올린 원본이 사라지는 편이 훨씬 나쁘다.

## 그래서 두 조건을 함께 건다

  ① DB 어디에서도 그 저장명을 참조하지 않는다
  ② 파일이 유예 기간(30일)보다 오래됐다

②가 없으면 **방금 올렸는데 아직 커밋 안 된 행**의 파일을 지운다. 업로드 도중에 원본이
사라지는, 가장 나쁜 종류의 사고다. 그래서 아래 테스트가 그 경우를 따로 못박는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import os
import pytest

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 6, 9, 0, 0)


def _write(root, namespace, owner, name, *, age_days):
    path = root / "uploads" / namespace / owner
    path.mkdir(parents=True, exist_ok=True)
    target = path / name
    target.write_bytes(b"x" * 100)
    when = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(target, (when, when))
    return target


@pytest.fixture()
def world(db, settings, make_user):
    """참조되는 첨부 하나 + 고아 파일 둘(오래된 것/최근 것)."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.tickets.models import TicketAttachment, TicketCache

    user = make_user("sweep@goodmit.co.kr", role="user", display_name="올린사람")
    ticket = TicketCache(notion_page_id="page-keep", title="살아 있는 티켓", org_id=DEFAULT_ORG_ID)
    db.add(ticket)
    db.flush()
    db.add(TicketAttachment(
        ticket_uid=ticket.id, uploaded_by_user_id=user.id, filename="살아있음.png",
        stored_name="alive.png", media_type="image/png", size_bytes=100,
    ))
    db.commit()

    root = settings.data_dir
    alive = _write(root, "ticket", ticket.id, "alive.png", age_days=400)
    old_orphan = _write(root, "ticket", ticket.id, "orphan-old.png", age_days=400)
    young_orphan = _write(root, "ticket", ticket.id, "orphan-young.png", age_days=1)
    return {"alive": alive, "old": old_orphan, "young": young_orphan}


def _sweep(db, settings, **kw):
    from app.core.retention import sweep_orphan_uploads

    return sweep_orphan_uploads(db, data_dir=settings.data_dir, now=NOW, **kw)


def test_the_sample_has_all_three_kinds(db, settings, world):
    """오탐 방지 - 셋이 다 있어야 아래 검사들이 서로를 가른다."""
    assert world["alive"].exists() and world["old"].exists() and world["young"].exists()


def test_an_old_orphan_is_removed(db, settings, world):
    result = _sweep(db, settings)
    assert result["removed"] == 1, result
    assert not world["old"].exists(), "오래된 고아 파일이 안 지워졌다"


def test_a_referenced_file_is_never_touched(db, settings, world):
    """🔴 참조 판정이 한 종류라도 빠지면 **살아 있는 첨부를 지운다.**"""
    _sweep(db, settings)
    assert world["alive"].exists(), "DB 가 가리키는 파일을 지웠다"


def test_a_recent_orphan_is_kept(db, settings, world):
    """🔴 방금 올렸는데 아직 커밋 안 된 행의 파일을 지우면 업로드가 도중에 사라진다."""
    result = _sweep(db, settings)
    assert world["young"].exists(), "유예 기간 안의 파일을 지웠다"
    assert result["kept_young"] == 1, result


def test_a_dry_run_changes_nothing_but_still_counts(db, settings, world):
    """무엇을 지울지 먼저 보고 결정할 수 있어야 한다."""
    result = _sweep(db, settings, dry_run=True)
    assert result["removed"] == 1, result
    assert result["dry_run"] is True
    assert world["old"].exists(), "dry_run 인데 지웠다"


def test_every_attachment_kind_counts_as_a_reference(db, settings, make_user):
    """🔴 첨부 종류가 넷이다 - 하나라도 빠지면 그 종류가 통째로 지워진다.

    새 첨부 종류를 만드는 사람이 `_referenced_stored_names` 를 잊으면 여기서 걸린다.
    """
    from app.core.retention import _referenced_stored_names
    from app.board.models import PostAttachment
    from app.profiles.models import UserPreference
    from app.team_chat.models import ChatMessageImage
    from app.tickets.models import TicketAttachment

    import inspect

    source = inspect.getsource(_referenced_stored_names)
    for model in (TicketAttachment, PostAttachment, ChatMessageImage, UserPreference):
        assert model.__name__ in source, (
            f"{model.__name__} 이 참조 판정에서 빠졌다 - 그 종류의 첨부가 전부 지워진다"
        )


def test_a_missing_upload_root_is_not_an_error(db, settings):
    """업로드가 한 번도 없던 설치에서 정리가 터지면 안 된다."""
    result = _sweep(db, settings)
    assert result["removed"] == 0 and result["failed"] == 0, result


def test_a_settings_object_without_a_data_dir_skips_instead_of_crashing(db, settings):
    """🔴 정리 전체를 죽이지 않는다.

    `run_retention` 의 호출부 중에는 휴지통 정리에 필요한 것만 담은 **최소 스텁**을 넘기는
    곳이 있다. `settings.data_dir` 을 무조건 읽으면 거기서 AttributeError 가 나고,
    그 자리에서 죽으면 **앞서 지운 것들의 커밋도 못 한다.** 원인은 스택 트레이스에만 남는다.

    경로를 모를 때 추측해서 지우는 것은 있을 수 없으므로, 건너뛰되 **건너뛴 사실을 남긴다.**
    """
    from app.core.retention import run_retention

    class _Cache:
        def current(self):
            return {}

    result = run_retention(db, now=NOW, settings_cache=_Cache(), settings=object())
    assert "orphan_uploads" in result, result
    assert result["orphan_uploads"].get("skipped"), (
        f"건너뛴 사실이 결과에 안 남았다: {result['orphan_uploads']}"
    )


def test_a_real_settings_object_still_sweeps(db, settings, world):
    """오탐 방지 - 관대하게 만드느라 정상 경로까지 건너뛰면 기능이 사라진다."""
    from app.core.retention import run_retention

    class _Cache:
        def current(self):
            return {}

    result = run_retention(db, now=NOW, settings_cache=_Cache(), settings=settings)
    assert result["orphan_uploads"].get("skipped") is None, result["orphan_uploads"]
    assert result["orphan_uploads"]["removed"] == 1, result["orphan_uploads"]
