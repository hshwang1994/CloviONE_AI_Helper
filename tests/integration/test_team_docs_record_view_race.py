"""team_docs.service.record_view — 문서 상세 GET의 부수효과(최근 열람 기록)가
`database is locked` 하나로 이미 성공한 본문 응답 전체를 500으로 만들면 안 된다.

실측(2026-08-15, TEST SERVER Chrome E2E): `GET /api/team-docs/{id}`가 Notion에서
본문을 성공적으로 받아 온 **뒤**, 마지막 줄인 `record_view`의 "이미 있는 행 갱신"
분기(`existing.viewed_at = now; db.flush()`)에서 처리 안 된
`sqlite3.OperationalError: database is locked`로 원시 500이 났다(request_id
2b6ef8757dd0a4396510d72630ab57b4, journalctl 확인). "행이 아직 없어 새로 만드는"
분기는 PA-RC-0008 관용대로 한 번은 재시도 폴백이 있었는데, 훨씬 자주 타는 "이미 있는
행 갱신" 분기(같은 문서를 반복해서 보면 매번 이쪽이다)에는 애초에 없었다.

고친 뒤에는 두 분기를 하나의 재시도 루프로 합쳐 같은 예산(`DEFAULT_WRITE_CONFLICT_
RETRIES`)을 쓴다. approvals/prompts류(사용자가 직접 일으킨 쓰기)와 다르게, 이건 GET의
부수효과라 예산을 다 써도 사용자에게 보여줄 409가 없다 — 조용히 포기하고 본문 응답은
그대로 낸다(호출부인 router.py가 이미 그렇게 가정하고 반환값을 안 본다).

날짜는 전부 naive UTC다 — 이 저장소의 실제 시각 소스(`SystemClock.now()`)가
`datetime.now(timezone.utc).replace(tzinfo=None)`이고, SQLite `DateTime` 컬럼도
tzinfo를 왕복시키지 않는다.
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import OperationalError

from tests.fakes.pgerrors import serialization_failure

from app.team_docs import service as svc
from app.team_docs.models import DocumentRecentView

pytestmark = pytest.mark.integration

USER_ID = "u-race-viewer"
PAGE_ID = "page-race-1234"


def _locked_error() -> OperationalError:
    # is_write_conflict()가 sqlite_errorcode 우선, 없으면 메시지로 판정한다(app/core/db.py) —
    # 진짜 SQLite 예외를 스레드로 재현하는 대신, 그 메시지 판정 경로를 그대로 태운다.
    return serialization_failure("UPDATE document_recent_views ...")


def test_record_view_creates_row_when_none_exists(db):
    now = datetime(2026, 8, 15, 12, 0, 0)
    svc.record_view(db, user_id=USER_ID, page_id=PAGE_ID, now=now)
    db.flush()

    row = db.query(DocumentRecentView).filter_by(user_id=USER_ID, notion_page_id=PAGE_ID).one()
    assert row.viewed_at == now


def test_record_view_retries_then_succeeds_after_transient_conflicts(db, monkeypatch):
    """이미 있는 행을 갱신하는 분기(실측된 버그 지점)가 일시적 경합을 재시도로 넘긴다.

    실패 여부를 **바깥 재시도 루프가 실제로 몇 번째 시도인지**(write_conflict_backoff 호출
    횟수)로 판단한다 — db.flush 호출 자체를 셀 수 없다: SQLAlchemy autoflush가 다음
    반복의 `find_recent`(SELECT) 앞에서 이전에 실패로 남은 dirty 상태를 조용히 다시
    플러시하려 들어, 내가 명시적으로 부른 횟수와 실제 호출 횟수가 어긋난다(직접 확인 —
    순진하게 flush 호출 수를 셌더니 3 실패+성공 시나리오가 4가 아니라 5로 나왔다).
    """
    earlier = datetime(2026, 8, 15, 9, 0, 0)
    db.add(DocumentRecentView(user_id=USER_ID, notion_page_id=PAGE_ID, viewed_at=earlier))
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
    monkeypatch.setattr(svc, "write_conflict_backoff", _track_backoff)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)  # 재시도 결과만 본다 — 실제로 자면 느려진다

    later = datetime(2026, 8, 15, 13, 0, 0)
    svc.record_view(db, user_id=USER_ID, page_id=PAGE_ID, now=later)

    assert retry_count["n"] == 3, f"3번 막혀야(=backoff 3번 호출) 4번째 시도에서 성공한다: {retry_count}"
    monkeypatch.undo()
    row = db.query(DocumentRecentView).filter_by(user_id=USER_ID, notion_page_id=PAGE_ID).one()
    assert row.viewed_at == later, "재시도 끝에 실제로 갱신돼야 한다(값이 낡은 채로 조용히 넘어가면 안 된다)"


def test_record_view_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """PA-RC-0008과 같은 원칙 — 예산을 다 쓰면 원시 500(처리 안 된 OperationalError) 대신
    조용히 포기한다(사용자에게 보여줄 409 대상 행동이 없는 GET 부수효과라서 approvals/
    prompts류와는 다르게 고른 소진 처리다 — service.record_view의 docstring 참고)."""
    earlier = datetime(2026, 8, 15, 9, 0, 0)
    db.add(DocumentRecentView(user_id=USER_ID, notion_page_id=PAGE_ID, viewed_at=earlier))
    db.commit()

    retry_count = {"n": 0}

    def _track_backoff(attempt):
        retry_count["n"] = attempt + 1
        return 0.0

    def _always_locked(*args, **kwargs):
        raise _locked_error()

    monkeypatch.setattr(db, "flush", _always_locked)
    monkeypatch.setattr(svc, "write_conflict_backoff", _track_backoff)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)

    later = datetime(2026, 8, 15, 13, 0, 0)
    svc.record_view(db, user_id=USER_ID, page_id=PAGE_ID, now=later)  # 예외를 던지면 안 된다

    # 예산 10 중 마지막 시도는 실패해도 backoff를 안 부르고 바로 포기한다(코드 참고) — 9번만 부른다.
    assert retry_count["n"] == svc._RECORD_VIEW_RETRIES - 1, f"예산 직전까지만 backoff를 부른다: {retry_count}"
    monkeypatch.undo()
    row = db.query(DocumentRecentView).filter_by(user_id=USER_ID, notion_page_id=PAGE_ID).one()
    assert row.viewed_at == earlier, "끝내 실패했으니 값은 낡은 채로 남아야 한다(지어내면 안 된다)"


def test_record_view_retry_budget_is_the_shared_default():
    """PA-RC-0008의 공용 기본값(10, auth.py 로그인 재시도 실측)을 그대로 쓰는지 못박는다."""
    from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES

    assert svc._RECORD_VIEW_RETRIES == DEFAULT_WRITE_CONFLICT_RETRIES == 10
