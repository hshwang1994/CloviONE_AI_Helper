"""UB-07: 공지 닫기(dismiss)의 check-then-insert 경합이 500을 낸다.

`app/announcements/service.py::dismiss()`는 "이미 닫았는가"를 SELECT로 확인한 뒤
없으면 INSERT한다 — 그 사이는 잠기지 않은 창이다. 탭 두 개(또는 더블클릭)가 거의 동시에
같은 공지를 닫으면 둘 다 SELECT에서 "없음"을 보고 둘 다 INSERT를 시도한다.
`uq_announcement_dismissal`(announcement_id, user_id) UNIQUE 제약에 걸린 쪽이
잡히지 않은 `IntegrityError`로 500이 됐다 — docstring이 약속한 "멱등"(이미 닫았으면
False)과 정반대로 두 번째 요청이 사용자에게 오류로 보였다.

이 시험은 `tests/integration/test_quota_toctou.py`의 `Barrier` 기법을 그대로 쓴다 —
두 진짜 스레드(각자 독립 세션)를 실제 경합 지점에 맞춰 세운다. **바리어가 두 개
필요하다**: SELECT 시점에서 한 번(둘 다 "없음"을 보게), `flush()`(INSERT) 시점에서
한 번 더(그 SELECT 이후 스레드 스케줄링이 한쪽을 훨씬 앞서가게 둬 버리면 — 실제로
1차 시도에서 그렇게 됐다 — 한쪽이 이미 커밋을 끝낸 뒤에야 다른 쪽이 INSERT를 시도해
그 SELECT가 뒤늦게 진짜 상태를 다시 보고 조용히 False를 반환할 뿐, 진짜 경합이
전혀 재현되지 않는다). 잠들기(sleep)로 맞추면 느리고 흔들린다.
"""

from __future__ import annotations

import threading
from datetime import datetime

import pytest
from sqlalchemy import Select

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 3, 9, 0, 0)


@pytest.fixture()
def announcement(db):
    from app.announcements.models import Announcement

    row = Announcement(
        title="공지", body="본문", level="info", audience="all",
        active=True, dismissible=True, created_by=None,
        created_at=NOW, updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def test_two_concurrent_dismisses_of_the_same_announcement_do_not_500(
    app, db, make_user, announcement, monkeypatch
):
    from app.announcements import service as announcements

    user = make_user("racer@goodmit.co.kr", role="user", display_name="레이서")

    select_barrier = threading.Barrier(2)
    flush_barrier = threading.Barrier(2)
    race_active = threading.Event()  # 두 워커가 도는 동안만 바리어를 건다 —
    # 안 그러면 시험 끝의 검증 SELECT(같은 테이블을 본다)까지 걸려 혼자 타임아웃을 먹는다.
    from sqlalchemy.orm import Session as OrmSession

    real_execute = OrmSession.execute
    real_flush = OrmSession.flush

    def barriered_execute(self, statement, *args, **kwargs):
        # dismiss()의 "이미 닫았는가" SELECT만 붙잡는다 — 둘 다 "없음"을 본 뒤에야
        # 다음 단계(flush)로 넘어가게 한다.
        if race_active.is_set() and isinstance(statement, Select) and "announcement_dismissals" in str(statement):
            try:
                select_barrier.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass
        return real_execute(self, statement, *args, **kwargs)

    def barriered_flush(self, *args, **kwargs):
        # 두 스레드 모두 SELECT를 마친 뒤에도, 스케줄링이 한쪽을 훨씬 앞서가게 두면
        # (실측: 실제로 그랬다) 한쪽이 이미 INSERT+commit을 끝낸 뒤에야 다른 쪽이
        # flush를 시도해 SQLite 쓰기 잠금 대기 자체가 사라진다 — 여기서 한 번 더
        # 맞춰야 두 INSERT가 실제로 겹친다(하나는 쓰기 잠금을 기다리게 된다).
        if race_active.is_set():
            try:
                flush_barrier.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass
        return real_flush(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "execute", barriered_execute)
    monkeypatch.setattr(OrmSession, "flush", barriered_flush)

    outcomes: list[tuple[str, object]] = []
    lock = threading.Lock()

    def worker():
        session = app.state.session_factory()
        try:
            result = announcements.dismiss(
                session, announcement_id=announcement.id, user_id=user.id, now=NOW,
            )
            session.commit()
            outcome = ("ok", result)
        except Exception as exc:  # noqa: BLE001 — 실패 형태 자체를 검증해야 한다
            session.rollback()
            outcome = ("error", type(exc).__name__)
        finally:
            session.close()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    race_active.set()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    race_active.clear()

    assert all(kind == "ok" for kind, _ in outcomes), (
        f"경합이 잡히지 않은 예외로 새어나갔다(500이 됐다는 뜻): {outcomes}"
    )
    assert sorted(v for _, v in outcomes) == [False, True], (
        f"멱등이어야 한다 — 하나는 True(실제로 닫음), 하나는 False(이미 닫힘)만 나와야 한다: {outcomes}"
    )

    from sqlalchemy import func, select

    from app.announcements.models import AnnouncementDismissal

    db.expire_all()
    count = db.execute(
        select(func.count()).select_from(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == announcement.id,
            AnnouncementDismissal.user_id == user.id,
        )
    ).scalar_one()
    assert count == 1, f"닫힘 행이 중복 저장됐다: {count}건"
