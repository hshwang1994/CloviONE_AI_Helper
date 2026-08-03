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
    row = record_usage(
        db, event=EVENT_LOGIN, user_id="u-1", org_id="org-1",
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


def test_event_names_come_from_one_place():
    """'auth.login' 과 'login' 이 같은 뜻으로 둘 다 쌓이면 집계가 조용히 반토막 난다."""
    assert EVENT_LOGIN in KNOWN_EVENTS
    assert EVENT_TICKET_CREATE in KNOWN_EVENTS
    assert all(name.count(".") == 1 for name in KNOWN_EVENTS), (
        f"이벤트 이름은 '<도메인>.<행동>' 형태여야 한다: {sorted(KNOWN_EVENTS)}"
    )


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
