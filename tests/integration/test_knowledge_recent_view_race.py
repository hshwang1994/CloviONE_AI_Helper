"""최근 열람 기록은 이미 성공한 본문 응답을 500 으로 만들면 안 된다.

실측(2026-08-15, 테스트 서버 Chrome E2E): 문서 상세 GET 이 본문을 성공적으로 받아 온
**뒤**, 마지막 줄인 최근 열람 기록의 「이미 있는 행 갱신」 분기에서 처리되지 않은 쓰기
충돌로 원시 500 이 났다. 「행이 아직 없어 새로 만드는」 분기에는 재시도 폴백이 있었는데,
훨씬 자주 타는 갱신 분기(같은 문서를 반복해서 보면 매번 이쪽이다)에는 없었다.

고친 뒤에는 두 분기가 하나의 재시도 루프를 쓴다. 예산을 다 써도 사용자에게 보여줄 409 가
없으므로(GET 의 부수효과다) 조용히 포기하고 본문 응답은 그대로 낸다.

S14 · C2 에서 이 축이 옛 미러의 page id 에서 정본 문서(`documents.id`)로 옮겨 왔다.
그래서 이 시험은 **실제 문서 행**을 만들어 둔다 — 가짜 id 로는 FK 가 막고, 그 막힘은
경합과 아무 상관이 없다.
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import OperationalError

from tests.fakes.pgerrors import serialization_failure

from app.knowledge import recent_views as rv
from app.knowledge.models import Document, DocumentRecentView, KnowledgeSpace

pytestmark = pytest.mark.integration

USER_ID = "u-race-viewer"


@pytest.fixture()
def document_id(db) -> str:
    space = KnowledgeSpace(
        name="경합 시험 공간", slug="race-space", owner_kind="organization",
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="경합 시험 문서")
    db.add(doc)
    db.commit()
    return doc.id


def _locked_error() -> OperationalError:
    return serialization_failure("UPDATE document_recent_views ...")


def test_record_creates_row_when_none_exists(db, document_id):
    now = datetime(2026, 8, 15, 12, 0, 0)
    rv.record(db, user_id=USER_ID, document_id=document_id, now=now)
    db.flush()

    row = db.query(DocumentRecentView).filter_by(
        user_id=USER_ID, document_id=document_id).one()
    assert row.viewed_at == now


def test_record_retries_then_succeeds_after_transient_conflicts(db, document_id, monkeypatch):
    """이미 있는 행을 갱신하는 분기(실측된 버그 지점)가 일시적 경합을 재시도로 넘긴다.

    실패 여부를 **바깥 재시도 루프가 몇 번째 시도인지**(backoff 호출 횟수)로 판단한다 —
    flush 호출 자체는 셀 수 없다: autoflush 가 다음 반복의 SELECT 앞에서 실패로 남은
    dirty 상태를 조용히 다시 플러시하려 들어 횟수가 어긋난다.
    """
    earlier = datetime(2026, 8, 15, 9, 0, 0)
    db.add(DocumentRecentView(user_id=USER_ID, document_id=document_id, viewed_at=earlier))
    db.commit()

    real_flush = db.flush
    retry_count = {"n": 0}

    def _track_backoff(attempt):
        retry_count["n"] = attempt + 1
        return 0.0

    def _fail_until_third_retry(*args, **kwargs):
        if retry_count["n"] < 3:
            raise _locked_error()
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", _fail_until_third_retry)
    monkeypatch.setattr(rv, "write_conflict_backoff", _track_backoff)
    monkeypatch.setattr(rv.time, "sleep", lambda _seconds: None)

    later = datetime(2026, 8, 15, 13, 0, 0)
    rv.record(db, user_id=USER_ID, document_id=document_id, now=later)

    assert retry_count["n"] == 3, f"3번 막혀야 4번째 시도에서 성공한다: {retry_count}"
    monkeypatch.undo()
    row = db.query(DocumentRecentView).filter_by(
        user_id=USER_ID, document_id=document_id).one()
    assert row.viewed_at == later, "재시도 끝에 실제로 갱신돼야 한다"


def test_record_gives_up_cleanly_after_exhausting_retries(db, document_id, monkeypatch):
    """예산을 다 쓰면 원시 500 대신 조용히 포기한다 — GET 의 부수효과라 사용자에게 보여줄
    409 대상 행동이 없다."""
    earlier = datetime(2026, 8, 15, 9, 0, 0)
    db.add(DocumentRecentView(user_id=USER_ID, document_id=document_id, viewed_at=earlier))
    db.commit()

    retry_count = {"n": 0}

    def _track_backoff(attempt):
        retry_count["n"] = attempt + 1
        return 0.0

    def _always_locked(*args, **kwargs):
        raise _locked_error()

    monkeypatch.setattr(db, "flush", _always_locked)
    monkeypatch.setattr(rv, "write_conflict_backoff", _track_backoff)
    monkeypatch.setattr(rv.time, "sleep", lambda _seconds: None)

    later = datetime(2026, 8, 15, 13, 0, 0)
    rv.record(db, user_id=USER_ID, document_id=document_id, now=later)  # 예외를 던지면 안 된다

    # 마지막 시도는 실패해도 backoff 를 안 부르고 바로 포기한다.
    assert retry_count["n"] == rv._RETRIES - 1, f"예산 직전까지만 backoff 를 부른다: {retry_count}"
    monkeypatch.undo()
    row = db.query(DocumentRecentView).filter_by(
        user_id=USER_ID, document_id=document_id).one()
    assert row.viewed_at == earlier, "끝내 실패했으니 값은 낡은 채로 남아야 한다"


def test_retry_budget_is_the_shared_default():
    """공용 기본값(10)을 그대로 쓰는지 못박는다."""
    from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES

    assert rv._RETRIES == DEFAULT_WRITE_CONFLICT_RETRIES == 10
