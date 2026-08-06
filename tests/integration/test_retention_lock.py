"""보존 정리가 **쓰기 락을 쥔 채 Notion 왕복을 하지 않는다** (S7).

예전 `purge_expired` 는 한 트랜잭션 안에서 `db.delete()` 와 Notion `archive` 를 번갈아 했다.
SQLite 는 첫 쓰기 문장에서 **DB 전체 쓰기 락**을 잡고 커밋까지 놓지 않는다(WAL 이어도 쓰기는
하나다). 그래서 만료 항목 20개 × 느린 Notion 이면 그동안 **웹의 모든 쓰기가
`database is locked` 500** 이 된다. 한 시간에 한 번, 몇 분간.

그리고 이 정리는 아무 상태도 남기지 않아서 **원인을 찾을 단서가 없다** — 운영자는 산발적인
500 을 보고 다른 곳을 판다.

이 테스트는 "커밋했다" 를 보지 않는다. **그 시각에 다른 연결이 실제로 쓸 수 있는지**를 본다 —
그게 사용자가 겪는 층이다. `EngineOptions.busy_timeout_ms` 가 이 목적으로 이미 파라미터화돼
있다(`app/core/db.py` 주석: "짧게 주면 잠금 경합을 테스트에서 재현할 수 있다").

⚠️ **`purge_expired` 만 따로 부르면 이 결함이 재현되지 않는다.** `db.delete()` 는
`autoflush=False` 라 루프 도는 동안 SQL 을 내보내지 않고, 마지막 `flush()` 에서야 쓰기 락을
잡는다. 락을 쥐는 것은 **그 앞에 있는 정리들**이다 — `run_retention` 은 대화·알림·잡·
스케줄이력을 `db.execute(delete(...))` + `flush()` 로 **즉시** 지운 다음 휴지통 단계로 간다.
그래서 이 테스트는 반드시 **`run_retention` 층**에서 재야 한다.
(처음에 `purge_expired` 만 부르는 테스트를 썼다가, 예전 구조로 되돌려도 통과하는 것을 보고
헛것임을 확인했다. 검사를 만들 때마다 결함을 재도입해 봐야 하는 이유가 이것이다.)
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.db import EngineOptions, make_engine
from app.core.retention import run_retention
from app.notifications.models import Notification
from app.trash import service
from app.trash.models import TRASH_TICKET

pytestmark = pytest.mark.integration


def _second_connection(db_path):
    """웹 프로세스 역할. busy_timeout 0 → 락이 잡혀 있으면 **즉시** 실패한다."""
    return make_engine(
        f"sqlite:///{db_path.as_posix()}",
        EngineOptions(busy_timeout_ms=0, pool_pre_ping=False),
    )


def test_the_web_can_still_write_while_retention_talks_to_notion(
    db, db_path, app, make_user, monkeypatch
):
    web = _second_connection(db_path)
    attempts: list[str] = []

    def archive_and_check_the_lock(item, *, outbound, settings):
        """Notion 왕복을 흉내내면서, 바로 그 순간 웹이 쓸 수 있는지 확인한다."""
        try:
            with web.begin() as conn:
                conn.execute(text("CREATE TABLE IF NOT EXISTS s7_probe (id INTEGER)"))
                conn.execute(text("INSERT INTO s7_probe (id) VALUES (1)"))
            attempts.append("ok")
        except OperationalError as exc:
            attempts.append(f"locked: {exc.orig}")

    monkeypatch.setattr(service, "_archive_notion", archive_and_check_the_lock)

    u = make_user(email="s7@goodmit.co.kr", display_name="보존")
    base = datetime(2026, 7, 29)
    for i in range(3):
        service.move_to_trash(
            db, item_type=TRASH_TICKET, notion_page_id=f"old-{i}", title=f"오래됨{i}",
            url=None, user=u, now=base - timedelta(days=30),
        )
    # 휴지통 단계 **앞에서 실제 DELETE 가 나가게** 만든다 — 락을 잡는 것이 이쪽이다.
    # (알림은 `db.execute(delete(...))` + `flush()` 로 즉시 지워진다.)
    db.add(Notification(user_id=u.id, type="job_failed", title="낡은 알림", body="",
                        created_at=base - timedelta(days=400)))
    db.commit()

    result = run_retention(
        db, now=base, settings_cache=app.state.settings_cache,
        outbound=object(), settings=object(),
    )["trash"]
    db.commit()

    assert attempts, "Notion 호출이 한 번도 안 일어났다 — 이 테스트의 전제가 깨졌다"
    blocked = [a for a in attempts if a != "ok"]
    assert not blocked, (
        f"Notion 왕복 중에 웹 쓰기가 막혔다({len(blocked)}/{len(attempts)}건): {blocked[0]}"
    )
    # 락을 놓은 것과 일을 안 한 것은 다르다 — 정리는 그대로 되어야 한다.
    assert result["purged"] == 3
    web.dispose()


def test_the_probe_itself_can_detect_a_held_lock(db, db_path, make_user):
    """위 테스트가 **무엇이든 통과시키는 검사**가 아님을 증명한다.

    쓰기 트랜잭션을 실제로 열어 두고 같은 프로브를 돌려 `locked` 가 나오는지 본다.
    이게 없으면 위 테스트는 "언제나 초록" 일 수 있고, 그러면 아무 뜻도 없다.
    """
    web = _second_connection(db_path)

    u = make_user(email="s7probe@goodmit.co.kr", display_name="프로브")
    service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="lock-me",
                          title="락", url=None, user=u, now=datetime(2026, 7, 1))
    db.flush()   # 쓰기 락을 잡되 커밋하지 않는다 = 예전 구조가 하던 그 상태

    with pytest.raises(OperationalError) as caught:
        with web.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS s7_probe2 (id INTEGER)"))
    assert "locked" in str(caught.value.orig).lower()
    db.rollback()
    web.dispose()
