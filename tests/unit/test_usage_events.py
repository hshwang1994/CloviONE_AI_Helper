"""사용 이벤트 (0026) — 기록 자체와, **뜨거운 경로에 걸리지 않았다**는 보증.

계획서가 명시적으로 못박은 제약이 있다: `usage_events` 는 **저빈도 지점에만** 건다.
채팅 전송·폴링 경로에 걸면
  * 채팅 전송은 이미 INSERT + `event_seq` UPDATE 로 SAVEPOINT 재시도를 도는 가장 뜨거운
    쓰기 경로라, INSERT 를 하나 더 얹으면 병목을 가장 나쁜 자리에서 키운다;
  * 폴링 경로에 걸면 **읽기가 쓰기로 바뀌어** ETag/304 로 아낀 것을 그대로 되돌린다.

주석으로만 적어 두면 언젠가 누가 좋은 뜻으로 건다. 그래서 소스에서 직접 확인한다.
"""

from datetime import datetime
from pathlib import Path

import pytest

from app.observability.models import UsageEvent
from app.observability.service import (
    EVENT_AI_CALL,
    EVENT_LOGIN,
    EVENT_TICKET_CREATE,
    KNOWN_EVENTS,
    record_usage,
)

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 여기에 usage 기록을 걸면 안 되는 모듈들. 이유는 모듈 docstring 참조.
HOT_PATH_MODULES = (
    "app/team_chat/router.py",
    "app/team_chat/service.py",
    "app/games/router.py",
    "app/games/service.py",
    "app/notifications/router.py",
    "app/trash/router.py",
    "app/chat/router.py",
    "app/chat/service.py",
)


@pytest.mark.parametrize("relative", HOT_PATH_MODULES)
def test_hot_paths_do_not_record_usage_events(relative):
    """뜨거운 경로가 관측성 모듈을 import 하면 실패한다.

    import 를 보는 이유: 호출을 문법적으로 찾으려 들면 별칭·간접 호출로 새어 나간다.
    import 가 없으면 부를 방법도 없다(지연 import 도 같은 문자열이라 함께 걸린다).
    """
    source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
    assert "observability.service" not in source, (
        f"{relative} 가 usage 기록 모듈을 import 한다. 채팅 전송·폴링 경로에 기록을 걸면 "
        "읽기가 쓰기로 바뀌고 가장 뜨거운 쓰기 경로가 더 느려진다 "
        "(app/observability/service.py 의 규칙 참조)."
    )


def test_the_guard_above_is_not_vacuous():
    """위 검사가 헛돌지 않는다는 증명 — **실제로 거는 파일**에서는 그 문자열이 보인다.

    검사 대상 목록의 파일들이 우연히 전부 통과하는 것이 아니라, 문자열 자체가 판별력이
    있음을 보인다(예: 오타로 'observability.service' 가 아닌 것을 찾고 있었다면 여기서 걸린다).
    """
    wired = (PROJECT_ROOT / "app/auth/router.py").read_text(encoding="utf-8")
    assert "observability.service" in wired


def test_record_usage_writes_a_row(db):
    from app.org.constants import DEFAULT_ORG_ID

    row = record_usage(
        db, event=EVENT_LOGIN, user_id="u-1", org_id=DEFAULT_ORG_ID,
        object_type="user", object_id="u-1", meta={"via": "web"},
        now=datetime(2026, 8, 3, 9, 0, 0),
    )
    assert row is not None
    db.commit()

    from sqlalchemy import select

    saved = db.execute(select(UsageEvent)).scalars().all()
    assert len(saved) == 1
    assert saved[0].event == EVENT_LOGIN
    assert saved[0].user_id == "u-1"
    assert saved[0].meta_json == '{"via": "web"}'


def test_record_usage_never_raises(db):
    """통계 한 줄 때문에 사용자의 로그인이나 티켓 생성이 실패하면 안 된다."""
    # event 컬럼은 String(64) 이고 NOT NULL 이다. None 을 넣어 flush 를 깨뜨린다.
    result = record_usage(db, event=None)  # type: ignore[arg-type]
    assert result is None, "기록 실패가 예외로 새어 나갔다"
    db.rollback()


def test_record_usage_failure_does_not_poison_other_pending_changes_in_the_session(db):
    """UB-18: `flush()` 실패가 SAVEPOINT 없이 그대로 세션을 pending-rollback 상태로
    만들면, 호출자가 이미 같은 세션에 올려 둔(아직 커밋 안 된) **관련 없는 다른 변경**
    까지 이후 아무 작업에서나 `PendingRollbackError`로 함께 끌고 내려간다 — "통계 한 줄
    때문에 로그인·티켓 생성이 실패하면 안 된다"는 이 함수의 존재 이유와 정반대다.
    """
    # 호출자가 이미 세션에 올려 둔, 아직 커밋 안 된 다른 변경(본 작업의 일부를 흉내).
    other = UsageEvent(event=EVENT_LOGIN, user_id="u-other")
    db.add(other)
    db.flush()

    # 실패하는 기록 — event=None 은 NOT NULL 위반으로 flush 를 깨뜨린다(위 시험과 동일).
    result = record_usage(db, event=None)  # type: ignore[arg-type]
    assert result is None

    # 고쳐지기 전이었다면 여기서(수동 rollback 없이) PendingRollbackError 가 났다 —
    # 세션이 실패 이후에도 그대로 쓸 수 있어야 한다.
    db.commit()

    from sqlalchemy import select

    saved = db.execute(select(UsageEvent)).scalars().all()
    assert any(r.id == other.id for r in saved), (
        "실패한 usage 기록이 같은 세션의 다른 pending 변경까지 함께 사라지게 했다"
    )


def test_event_names_come_from_one_place():
    """'auth.login' 과 'login' 이 같은 뜻으로 둘 다 쌓이면 집계가 조용히 반토막 난다."""
    assert EVENT_LOGIN in KNOWN_EVENTS
    assert EVENT_TICKET_CREATE in KNOWN_EVENTS
    assert all(name.count(".") == 1 for name in KNOWN_EVENTS), (
        f"이벤트 이름은 '<도메인>.<행동>' 형태여야 한다: {sorted(KNOWN_EVENTS)}"
    )


def test_ai_call_event_is_known():
    """UB-25: EVENT_AI_CALL이 예전엔 app/quotas/service.py에 따로 정의돼 있어 이
    KNOWN_EVENTS 집합엔 없었다 — "여기서만 만든다"는 규칙이 실제로는 안 지켜지고 있었다."""
    assert EVENT_AI_CALL in KNOWN_EVENTS


def test_quotas_imports_the_same_event_constant_not_a_duplicate():
    """정본이 하나임을 값이 아니라 **정의가 하나**임으로 확인한다 — 문자열만 같으면
    두 곳에서 각자 정의해도 우연히 통과하지만, 그러면 한쪽만 고쳐도 다시 갈라진다."""
    from app.quotas import service as quotas_service

    assert quotas_service.EVENT_AI_CALL is EVENT_AI_CALL


def test_record_usage_rejects_unknown_event_names(db):
    """UB-25: KNOWN_EVENTS 검사를 실제로 강제한다 — 그래도 예외는 밖으로 안 샌다
    (test_record_usage_never_raises와 같은 계약), 로그로만 남는다."""
    from sqlalchemy import select

    result = record_usage(db, event="totally.unknown.event")
    assert result is None, "모르는 이벤트 이름이 조용히 저장됐다"
    db.rollback()
    saved = db.execute(select(UsageEvent)).scalars().all()
    assert saved == [], "모르는 이벤트 이름이 usage_events에 그대로 남았다"


def test_login_records_a_usage_event(client, login_as):
    """실제로 걸려 있는지 — 로그인 한 번에 정확히 한 줄."""
    from sqlalchemy import select

    login_as("user")
    with client.app.state.session_factory() as session:
        rows = session.execute(
            select(UsageEvent).where(UsageEvent.event == EVENT_LOGIN)
        ).scalars().all()
    assert len(rows) == 1, f"로그인 사용 이벤트가 {len(rows)}줄 남았다"
    assert rows[0].user_id is not None


def test_polling_does_not_add_usage_rows(client, login_as):
    """폴링을 여러 번 해도 usage_events 는 자라지 않아야 한다(읽기가 쓰기가 되지 않는다)."""
    from sqlalchemy import func, select

    login_as("user")
    with client.app.state.session_factory() as session:
        before = session.execute(select(func.count()).select_from(UsageEvent)).scalar_one()

    for _ in range(5):
        client.get("/api/notifications/unread-count")
        client.get("/api/games/rooms")
        client.get("/api/trash")

    with client.app.state.session_factory() as session:
        after = session.execute(select(func.count()).select_from(UsageEvent)).scalar_one()
    assert after == before, "폴링이 usage_events 행을 늘렸다"
