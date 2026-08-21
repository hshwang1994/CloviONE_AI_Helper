"""D-75: `app/core/deps.py::get_db`의 요청-스코프 바깥 커밋(라우트 핸들러가 이미
성공적으로 반환한 뒤 실행되는 마지막 `db.commit()`)에는 재시도가 없었다. SAVEPOINT
재시도 계층(`app/core/db.py`)은 각 호출부 안의 커밋만 방어하고, 그 바깥의 이 마지막
커밋이 SQLite 쓰기 경합으로 실패하면 원시 `OperationalError`가 그대로 500으로 샜다.

여기서 확인하는 것은 재시도(커밋을 다시 부르면 이미 flush된 행이 rollback으로
사라진다 — 안전하게 재시도하려면 요청 전체를 다시 실행해야 하고, 이 커밋 지점은
그걸 하지 않는다)가 아니라 **분류**다: 쓰기 경합으로 실패했으면 원시 500 대신
`WriteUnavailableError`(503, 회복 안내 포함)로 바뀌는가, 무관한 `OperationalError`는
그대로 새는가, 그리고 라우트 자신의 로직이 던진 예외는 이 분류를 전혀 안 거치는가.

`get_db`는 평범한 제너레이터라 FastAPI/HTTP 스택 없이 직접 `next()`/`throw()`로
구동한다 — `test_session_touch_write_conflict.py` 하단의 `_commit_best_effort` 단위
시험과 같은 방식이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from tests.fakes.pgerrors import io_error, serialization_failure, unique_violation

from app.core.deps import get_db
from app.core.errors import WriteUnavailableError

pytestmark = pytest.mark.unit


def _fake_lock_error() -> OperationalError:
    """재시도해야 하는 경합 — PG 의 `40001 serialization_failure` 다.

    qa-contract-change: SQLite 의 database is locked 문자열을 흉내 내던 가짜 예외를 PG 의 SQLSTATE 40001 로 바꿨다. PG 에서 재시도 판정 기준은 메시지가 아니라 SQLSTATE 이므로, 문자열만 두면 제품이 아니라 가짜 예외 때문에 실패한다.
        """
    return serialization_failure("COMMIT")


def _fake_disk_error() -> OperationalError:
    return io_error("COMMIT")


def _fake_integrity_error() -> IntegrityError:
    """진짜 유니크 위반. **503 으로 포장되면 안 된다**(D-191).

    요청 끝 커밋에서 유니크 위반이 났다는 것은 그 라우트가 같은 행을 두 번 만들려
    했다는 뜻이다 — "잠시 후 다시 시도해 주세요" 로 감싸면 다시 해도 같은 결과인데
    사용자는 계속 재시도하고, 로그에는 진짜 원인이 안 남는다.
    """
    return unique_violation("INSERT INTO x", constraint="x_y_key")


class _FakeDb:
    def __init__(self, commit_exc: BaseException | None = None) -> None:
        self._commit_exc = commit_exc
        self.commit_calls = 0
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.commit_calls += 1
        if self._commit_exc is not None:
            raise self._commit_exc

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _FakeRequestState:
    request_id = "test-request-id"


class _FakeAppState:
    def __init__(self, fake_db: _FakeDb) -> None:
        self.session_factory = lambda: fake_db


class _FakeApp:
    def __init__(self, fake_db: _FakeDb) -> None:
        self.state = _FakeAppState(fake_db)


class _FakeRequest:
    def __init__(self, fake_db: _FakeDb) -> None:
        self.app = _FakeApp(fake_db)
        self.state = _FakeRequestState()


def test_outer_commit_write_conflict_becomes_clean_503_not_raw_500():
    fake_db = _FakeDb(commit_exc=_fake_lock_error())
    gen = get_db(_FakeRequest(fake_db))
    db = next(gen)
    assert db is fake_db

    with pytest.raises(WriteUnavailableError) as excinfo:
        next(gen)  # 핸들러가 정상 반환한 뒤 자리 — get_db 자신의 db.commit()을 친다
    assert excinfo.value.status_code == 503
    assert fake_db.commit_calls == 1, "재시도하지 않는다 — 분류만 한다(D-75)"
    assert fake_db.rolled_back
    assert fake_db.closed


def test_outer_commit_unrelated_operational_error_still_raises_raw():
    """디스크 오류 등 쓰기 경합이 아닌 것까지 조용히 503으로 뭉개면 안 된다."""
    exc = _fake_disk_error()
    fake_db = _FakeDb(commit_exc=exc)
    gen = get_db(_FakeRequest(fake_db))
    next(gen)

    with pytest.raises(OperationalError) as excinfo:
        next(gen)
    assert excinfo.value is exc
    assert fake_db.rolled_back
    assert fake_db.closed


def test_handler_own_integrity_error_is_not_reclassified_as_write_unavailable():
    """라우트 핸들러 자신이 던진 예외는 get_db의 커밋 분류를 전혀 안 거친다 —
    (yield 블록 자체의 실패는 else 절이 아니라 바깥 except Exception이 잡는다)."""
    fake_db = _FakeDb()  # commit_exc 없음 — 이 경로에서는 commit()이 호출되면 안 된다
    gen = get_db(_FakeRequest(fake_db))
    next(gen)

    handler_exc = _fake_integrity_error()
    with pytest.raises(IntegrityError) as excinfo:
        gen.throw(handler_exc)
    assert excinfo.value is handler_exc
    assert fake_db.commit_calls == 0, "핸들러가 이미 실패했으면 커밋을 시도하면 안 된다"
    assert fake_db.rolled_back
    assert fake_db.closed


def test_clean_request_commits_once_and_closes():
    fake_db = _FakeDb()
    gen = get_db(_FakeRequest(fake_db))
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    assert fake_db.commit_calls == 1
    assert not fake_db.rolled_back
    assert fake_db.closed
