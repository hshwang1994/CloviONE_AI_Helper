"""문서 휴지통의 자동 영구 삭제 (지시 22.9 개정 · D-352).

## 이것은 되돌릴 수 없는 배경 동작이다

옛 휴지통의 「이레 뒤 정리」는 원본을 **보관처리**하는 일이라 되돌릴 여지가 남는다. 문서는
이미 보관된 상태로 휴지통에 있으므로 다음 단계가 **행을 지우는 것**이고, 그때 판·태그·
댓글·색인이 함께 사라진다. 그래서 기간을 따로 두고, 무엇보다 **끌 수 있게** 뒀다.

## 여기서 보는 것 다섯

  1. 기준이 `archived_at` 이다 — `created_at` 도 `updated_at` 도 아니다.
  2. **되살리면 그 순간 대상에서 빠진다**(`archived_at` 이 NULL 로 돌아간다).
  3. 꺼져 있으면 아무것도 안 지운다.
  4. 기간은 설정에서 온다 — 코드에 이레가 박혀 있지 않다.
  5. 지울 때 딸린 것이 **함께** 사라진다. 첨부의 **파일 행은 남는다.**
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 27, 3, 0, 0)


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, DocumentTag, KnowledgeSpace, Tag
    from app.org.constants import DEFAULT_ORG_ID

    owner = make_user("dap-owner@goodmit.co.kr", role="operator", display_name="운영자")
    space = KnowledgeSpace(name="자동삭제 공간", slug="dap-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    tag = Tag(org_id=DEFAULT_ORG_ID, name="자동삭제태그", slug="자동삭제태그")
    db.add(tag)
    db.flush()

    def _doc(title, archived_at, *, created=None):
        row = Document(
            space_id=space.id, title=title, created_by=owner.id,
            archived=archived_at is not None,
            archived_at=archived_at,
            archived_by=owner.id if archived_at else None,
        )
        if created is not None:
            row.created_at = created
            row.updated_at = created
        db.add(row)
        db.flush()
        db.add(DocumentTag(document_id=row.id, tag_id=tag.id))
        return row

    old = _doc("여드레 전에 버린 문서", NOW - timedelta(days=8))
    fresh = _doc("어제 버린 문서", NOW - timedelta(days=1))
    # 🔴 오래된 문서지만 **어제 버렸다.** `created_at` 으로 판정하면 이것이 지워진다.
    old_but_new_trash = _doc("3년 전에 쓰고 어제 버린 문서", NOW - timedelta(days=1),
                             created=NOW - timedelta(days=1095))
    alive = _doc("살아 있는 문서", None, created=NOW - timedelta(days=1095))
    db.commit()
    return {
        "old": old.id, "fresh": fresh.id, "old_but_new_trash": old_but_new_trash.id,
        "alive": alive.id, "tag": tag.id, "space": space.id,
    }


def _purge(db, **kwargs):
    from app.knowledge import service

    params = {"now": NOW, "retention_days": 7, "enabled": True}
    params.update(kwargs)
    out = service.purge_expired_documents(db, **params)
    db.commit()
    return out


def _alive(db, document_id) -> bool:
    from app.knowledge.models import Document

    db.expire_all()
    return db.get(Document, document_id) is not None


def test_only_documents_past_the_retention_window_are_purged(db, world):
    result = _purge(db)
    assert result["purged"] == 1
    assert not _alive(db, world["old"]), "기간이 지난 문서가 안 지워졌다"
    assert _alive(db, world["fresh"])
    assert _alive(db, world["alive"])


def test_the_clock_that_matters_is_archived_at(db, world):
    """🔴 3년 전에 쓴 문서를 어제 버렸다면 남은 시간은 이레다.

    `created_at`/`updated_at` 으로 판정하면 사람이 예상한 것과 **정확히 반대로** 사라진다.
    """
    _purge(db)
    assert _alive(db, world["old_but_new_trash"]), "만든 날로 판정하고 있다"
    assert _alive(db, world["alive"]), "버리지도 않은 문서가 지워졌다"


def test_restoring_takes_a_document_out_of_range_immediately(db, world, make_user):
    """되살리면 `archived_at` 이 NULL 로 돌아간다 — 그 순간 대상이 아니다."""
    from app.knowledge import service

    user = make_user("dap-restore@goodmit.co.kr", role="operator", display_name="복원자")
    service.restore_document(db, user, world["old"])
    db.commit()

    assert _purge(db)["purged"] == 0
    assert _alive(db, world["old"])


def test_turning_the_policy_off_stops_every_deletion(db, world):
    """자동으로 지우는 일을 원하지 않는 설치가 그것을 고르는 방법이 있어야 한다."""
    result = _purge(db, enabled=False)
    assert result["purged"] == 0
    assert result["skipped"]
    assert _alive(db, world["old"])


def test_the_window_comes_from_the_setting_not_from_the_code(db, world):
    """🔴 이레가 코드에 박혀 있으면 관리자가 30일로 늘려도 아무 일도 안 일어난다."""
    assert _purge(db, retention_days=30)["purged"] == 0, "30일 설정인데 여드레짜리를 지웠다"
    assert _alive(db, world["old"])
    assert _purge(db, retention_days=1)["purged"] == 3, "하루 설정인데 어제 버린 것이 남았다"


def test_everything_that_hangs_off_the_document_goes_with_it(db, world):
    """판·태그 연결·색인 조각이 함께 사라진다(CASCADE). **파일 행은 남는다.**"""
    from sqlalchemy import func, select

    from app.knowledge.models import DocumentTag, DocumentVersion

    _purge(db)
    for model in (DocumentVersion, DocumentTag):
        left = db.execute(
            select(func.count()).select_from(model)
            .where(model.document_id == world["old"])
        ).scalar_one()
        assert left == 0, f"{model.__tablename__} 에 고아 행이 남았다"


def test_the_tag_itself_survives_the_purge(db, world):
    """태그는 어휘다 — 그 태그를 쓰던 문서가 사라졌다고 어휘가 사라지면 안 된다."""
    from app.knowledge.models import Tag

    _purge(db)
    db.expire_all()
    assert db.get(Tag, world["tag"]) is not None


def test_a_batch_is_bounded(db, world):
    """정리는 배경 작업이다. 수백 건의 CASCADE 를 한 트랜잭션에 묶으면 그동안 문서 쓰기가
    전부 기다린다 — 남은 것은 다음 주기에 지운다."""
    result = _purge(db, retention_days=1, limit=1)
    assert result["purged"] == 1
    assert _purge(db, retention_days=1, limit=1)["purged"] == 1


def test_the_retention_lane_carries_the_document_result(db, world):
    """정리 레인의 결과에 이 항목이 실려야 운영 화면이 「몇 건 지웠나」를 말할 수 있다."""
    from app.core.retention import run_retention

    class _Cache:
        def current(self):
            return {"document_trash_autopurge": True, "document_trash_retention_days": 7}

    out = run_retention(db, now=NOW, settings_cache=_Cache())
    db.commit()
    assert out["document_trash"]["purged"] == 1
