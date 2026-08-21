"""보존 정리가 **쓰기 락을 쥔 채 Notion 왕복을 하지 않는다** (S7).

예전 `purge_expired` 는 한 트랜잭션 안에서 `db.delete()` 와 Notion `archive` 를 번갈아 했다.
그러면 만료 항목 20개 × 느린 Notion 동안 **그 행들이 계속 잠겨 있다** — 같은 항목을 건드리는
요청이 전부 그 자리에 쌓인다.

그리고 이 정리는 아무 상태도 남기지 않아서 **원인을 찾을 단서가 없다** — 운영자는 산발적인
지연을 보고 다른 곳을 판다.

이 테스트는 "커밋했다" 를 보지 않는다. **그 시각에 다른 연결이 그 행을 실제로 잡을 수
있는지**를 본다 — 그게 사용자가 겪는 층이다.

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
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.retention import run_retention
from app.notifications.models import Notification
from app.trash import service
from app.trash.models import TRASH_TICKET

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _second_connection(db_url):
    """웹 프로세스 역할의 **두 번째 커넥션**.

    qa-contract-change: SQLite 는 첫 쓰기에서 DB 전체 쓰기 락을 잡았기 때문에 busy_timeout 0 하나로 프로브가 성립했다. PG 에는 그런 락이 없어(MVCC · 행 단위) 그대로 옮기면 무엇이든 통과하는 검사가 되므로, 같은 뜻을 갖는 FOR UPDATE NOWAIT 로 다시 썼다.
    즉시 실패" 를 만들었다. SQLite 는 첫 쓰기에서 **DB 전체 쓰기 락**을 잡았기 때문에 그
    """
    from app.core.db import normalize_database_url

    return create_engine(normalize_database_url(db_url))


def _try_lock_row(engine, table: str, row_id: str) -> str:
    """그 행을 **기다리지 않고** 잠가 본다. 상대가 쥐고 있으면 `locked: …` 를 돌려준다."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"SELECT 1 FROM {table} WHERE id = :id FOR UPDATE NOWAIT"),  # noqa: S608
                {"id": row_id},
            )
        return "ok"
    except OperationalError as exc:
        return f"locked: {exc.orig}"


def test_the_web_can_still_write_while_retention_talks_to_notion(
    db, db_url, app, make_user, monkeypatch
):
    web = _second_connection(db_url)
    attempts: list[str] = []

    def archive_and_check_the_lock(item, *, outbound, settings):
        """Notion 왕복을 흉내내면서, 바로 그 순간 그 항목 행이 잠겨 있는지 확인한다."""
        attempts.append(_try_lock_row(web, "trash_items", item.id))

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
    assert blocked == [], (
        f"Notion 왕복 중에 웹 쓰기가 막혔다({len(blocked)}/{len(attempts)}건): {blocked[0]}"
    )
    # 락을 놓은 것과 일을 안 한 것은 다르다 — 정리는 그대로 되어야 한다.
    assert result["purged"] == 3
    web.dispose()


def test_the_probe_itself_can_detect_a_held_lock(db, db_url, make_user):
    """위 테스트가 **무엇이든 통과시키는 검사**가 아님을 증명한다.

    쓰기 트랜잭션을 실제로 열어 두고 같은 프로브를 돌려 `locked` 가 나오는지 본다.
    이게 없으면 위 테스트는 "언제나 초록" 일 수 있고, 그러면 아무 뜻도 없다.
    """
    web = _second_connection(db_url)

    u = make_user(email="s7probe@goodmit.co.kr", display_name="프로브")
    item = service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id="lock-me",
                                 title="락", url=None, user=u, now=datetime(2026, 7, 1))
    # **먼저 커밋한다.** 커밋 안 한 INSERT 는 다른 트랜잭션에 안 보이므로
    # `FOR UPDATE NOWAIT` 가 «행이 없다» 로 그냥 성공해 프로브가 헛돈다.
    db.commit()
    # 이제 그 행을 잠근 채 커밋하지 않는다 = 예전 구조가 하던 그 상태.
    db.execute(text("UPDATE trash_items SET title = :t WHERE id = :id"),
               {"t": "잠금 중", "id": item.id})

    reason = _try_lock_row(web, "trash_items", item.id)
    assert reason != "ok", (
        "프로브가 잡혀 있는 잠금을 못 알아본다 — 위 시험은 아무것도 증명하지 못한다"
    )
    # **왜** 막혔는지까지 본다. `NOWAIT` 이 거절할 때의 SQLSTATE 는 `55P03` 이다 —
    # 다른 이유(연결 끊김·문법 오류)로 실패해도 문자열은 «locked» 로 시작할 수 있으므로,
    # 그것까지 통과시키면 프로브가 엉뚱한 고장을 «잠금» 으로 읽는다.
    assert "55P03" in reason or "lock" in reason.lower(), (
        f"막힌 이유가 잠금 대기가 아니다: {reason}"
    )
    db.rollback()
    web.dispose()
