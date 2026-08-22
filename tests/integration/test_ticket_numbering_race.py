"""티켓 채번 — **중복 0 · 번호 연속 · 롤백 시 미소비** (D-196 · U12 · MASTER_PLAN §9.3).

이 셋은 §9.3 이 「어떤 경우에도 면제되지 않는 검증」으로 못박은 항목이다. E1(지문이
같으면 인용)도 여기에는 적용되지 않는다.

## 이 시험이 헛돌지 않으려면

**두 요청이 실제로 겹쳐야** 한다. 순서대로 부르면 잠금이 하는 일이 없어도 번호가
연속으로 나오고, 시험은 아무것도 증명하지 못한 채 통과한다. 그래서:

  * 스레드마다 **자기 엔진·자기 커넥션**을 연다(전용 DB, D-190). 공유 DB 계층에서는
    세션들이 커넥션 하나를 나눠 써서 경합이 재현되지 않는다.
  * 모든 스레드를 `Barrier` 로 세워 두고 **동시에 출발**시킨다.
  * 마지막에 「반례가 실제로 잡히는가」를 확인한다 — 잠금 없이 읽고 쓰면 이 시험이
    빨개져야 한다. 그러지 않으면 이 파일은 초록 도장일 뿐이다.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from app.core.db import make_engine, make_session_factory

# 전용 DB 가 필요하다(D-190) — 다른 커넥션이 이 시험의 커밋을 봐야 한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

THREADS = 12
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PROJECT_ID = "22222222-2222-2222-2222-222222222222"


def _seed_projects(url: str) -> None:
    """Key 를 가진 프로젝트 둘. 두 번째는 **번호 공간이 따로**임을 보이는 데 쓴다.

    ORM 으로 만든다 — 원시 INSERT 는 모델 기본값(`notion_owner_ids` 등)을 안 채워서
    시험이 제품과 무관한 NOT NULL 위반으로 죽는다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project
    from app.work.models import KEY_ACTIVE, ProjectKeyRegistry

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            for pid, name, code in (
                (PROJECT_ID, "채번 프로젝트", "RACE"),
                (OTHER_PROJECT_ID, "다른 프로젝트", "OTHER"),
            ):
                db.add(
                    Project(id=pid, name=name, code=code, org_id=DEFAULT_ORG_ID)
                )
                db.add(
                    ProjectKeyRegistry(key=code, project_id=pid, state=KEY_ACTIVE)
                )
            db.commit()
    finally:
        engine.dispose()


def _allocate_and_insert(url: str, barrier: threading.Barrier, index: int) -> tuple[str, object]:
    """번호를 받아 티켓 한 건을 만든다 — **한 트랜잭션**이다.

    실제 생성 경로와 같은 모양이라야 한다. 번호만 받고 티켓을 안 만들면 유니크 제약이
    검증에 참여하지 않는다.
    """
    from app.work import numbering

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            barrier.wait(timeout=30)
            try:
                seq = numbering.allocate(db, PROJECT_ID)
                db.execute(
                    text(
                        "INSERT INTO tickets (id, title, project_uid, project_link, seq, "
                        "project_ids, project_names, assignee_notion_ids, source, "
                        "synced_at, org_id, created_at, updated_at, version) "
                        "VALUES (gen_random_uuid()::text, :title, :pid, 'ok', :seq, "
                        "'', '', '', 'native', now(), "
                        "'00000000-0000-0000-0000-00000000org1', now(), now(), 1)"
                    ),
                    {"title": f"경합 티켓 {index}", "pid": PROJECT_ID, "seq": seq},
                )
                db.commit()
                return ("ok", seq)
            except Exception as exc:  # noqa: BLE001 — 어떤 실패든 데이터가 안 망가졌는지가 관심사
                db.rollback()
                return ("error", type(exc).__name__)
    finally:
        engine.dispose()


def _read_rows(url: str) -> list[tuple]:
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT seq, canonical_key FROM tickets "
                        "WHERE project_uid = :pid ORDER BY seq"
                    ),
                    {"pid": PROJECT_ID},
                ).all()
            )
    finally:
        engine.dispose()


def test_concurrent_creation_never_duplicates_and_stays_contiguous(db_url):
    """12개가 동시에 들어와도 **1..12 가 정확히 한 번씩** 나온다.

    「중복 0」과 「번호 연속」을 한 시험에서 본다. 둘을 나누면 한쪽만 보는 시험이
    다른 쪽 결함에 초록을 찍는다 — 예를 들어 번호가 1,1,3,4… 면 중복만 보는 시험은
    잡지만 연속만 보는 시험은 개수가 맞아 통과한다.
    """
    _seed_projects(db_url)
    barrier = threading.Barrier(THREADS)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(
            pool.map(lambda i: _allocate_and_insert(db_url, barrier, i), range(THREADS))
        )

    failures = [r for r in results if r[0] != "ok"]
    assert not failures, f"동시 생성에서 실패가 나왔다: {failures}"

    seqs = sorted(r[1] for r in results)
    assert seqs == list(range(1, THREADS + 1)), f"번호가 1..{THREADS} 가 아니다: {seqs}"

    rows = _read_rows(db_url)
    assert [r[0] for r in rows] == list(range(1, THREADS + 1))
    # 표시 이름은 **트리거가** 만든다. 앱은 canonical_key 를 한 번도 쓰지 않았다.
    assert [r[1] for r in rows] == [f"RACE-{n}" for n in range(1, THREADS + 1)]


def test_rollback_does_not_consume_a_number(db_url):
    """실패한 요청은 번호를 **가져가지 않는다.**

    PostgreSQL `SEQUENCE` 였다면 여기서 구멍이 생긴다 — 롤백해도 번호를 안 되돌리기
    때문이다. 그것이 D-196 이 `ON CONFLICT DO UPDATE` 를 고른 이유의 전부다.
    """
    from app.work import numbering

    _seed_projects(db_url)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            first = numbering.allocate(db, PROJECT_ID)
            db.commit()
        assert first == 1

        with factory() as db:
            burned = numbering.allocate(db, PROJECT_ID)
            assert burned == 2
            db.rollback()

        with factory() as db:
            after = numbering.allocate(db, PROJECT_ID)
            db.commit()
        assert after == 2, f"롤백된 번호가 소비됐다 — 다음 번호가 {after} 다"

        with factory() as db:
            assert numbering.peek(db, PROJECT_ID) == 2
    finally:
        engine.dispose()


def test_numbering_spaces_are_per_project(db_url):
    """프로젝트가 다르면 **번호 공간도 다르다.** 둘 다 1 번부터 시작한다.

    전역 번호였다면 `<KEY>-<SEQ>` 가 프로젝트 안에서 띄엄띄엄해지고, 사람이 "우리
    프로젝트 3번" 이라고 말할 수 없게 된다.
    """
    from app.work import numbering

    _seed_projects(db_url)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            assert numbering.allocate(db, PROJECT_ID) == 1
            assert numbering.allocate(db, OTHER_PROJECT_ID) == 1
            assert numbering.allocate(db, PROJECT_ID) == 2
            db.commit()
    finally:
        engine.dispose()


def test_a_naive_counter_would_fail_this_test(db_url):
    """**반례** — 잠금 없이 「읽고 +1 해서 쓰는」 방식이면 이 시험이 잡는다.

    D-213 의 규약이다: 검출기가 실제로 무언가를 잡는지 먼저 보인다. 이것이 없으면
    위 세 시험이 「경합이 안 일어나서」 통과하는 상태와 구별되지 않는다.
    """
    _seed_projects(db_url)
    barrier = threading.Barrier(THREADS)

    def naive(_i: int):
        engine = make_engine(db_url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                # 읽기: 다른 트랜잭션의 미커밋 증가가 안 보인다 — 그것이 결함의 씨앗이다.
                current = db.execute(
                    text(
                        "SELECT COALESCE(MAX(seq), 0) FROM tickets WHERE project_uid = :pid"
                    ),
                    {"pid": PROJECT_ID},
                ).scalar_one()
                barrier.wait(timeout=30)
                try:
                    db.execute(
                        text(
                            "INSERT INTO tickets (id, title, project_uid, project_link, seq, "
                            "project_ids, project_names, assignee_notion_ids, source, "
                            "synced_at, org_id, created_at, updated_at, version) "
                            "VALUES (gen_random_uuid()::text, '반례', :pid, 'ok', :seq, "
                            "'', '', '', 'native', now(), "
                            "'00000000-0000-0000-0000-00000000org1', now(), now(), 1)"
                        ),
                        {"pid": PROJECT_ID, "seq": current + 1},
                    )
                    db.commit()
                    return "ok"
                except Exception:  # noqa: BLE001
                    db.rollback()
                    return "conflict"
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        outcomes = list(pool.map(naive, range(THREADS)))

    # 순진한 방식은 같은 번호를 여러 번 만들려 하고, **유니크 인덱스가 그것을 거절한다.**
    # 즉 이 판에서는 경합이 실제로 일어난다 — 위 시험들이 우연히 통과한 것이 아니다.
    assert outcomes.count("conflict") > 0, (
        "잠금 없는 방식이 한 건도 안 부딪혔다 — 이 시험판에서는 경합이 재현되지 않는다. "
        "위 세 시험은 아무것도 증명하지 못한 상태다"
    )
    rows = _read_rows(db_url)
    assert len({r[0] for r in rows}) == len(rows), "유니크 인덱스가 중복을 막지 못했다"


def test_seed_counters_matches_existing_numbers(db_url):
    """S13 이 적재를 끝낸 직후 카운터를 맞추는 자리 — `last_seq = MAX(seq)`.

    여기가 한 칸 어긋나면 첫 신규 티켓이 마지막 기존 티켓과 같은 번호를 받는다.
    **낮추지 않는다**는 성질도 함께 본다.
    """
    from app.work import numbering

    _seed_projects(db_url)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            for n in (1, 2, 7):
                db.execute(
                    text(
                        "INSERT INTO tickets (id, title, project_uid, project_link, seq, "
                        "project_ids, project_names, assignee_notion_ids, source, "
                        "synced_at, org_id, created_at, updated_at, version) "
                        "VALUES (gen_random_uuid()::text, :t, :pid, 'ok', :seq, "
                        "'', '', '', 'native', now(), "
                        "'00000000-0000-0000-0000-00000000org1', now(), now(), 1)"
                    ),
                    {"t": f"기존 {n}", "pid": PROJECT_ID, "seq": n},
                )
            db.commit()

            numbering.seed_counters(db)
            db.commit()
            assert numbering.peek(db, PROJECT_ID) == 7
            assert numbering.allocate(db, PROJECT_ID) == 8
            db.commit()

            # 티켓이 지워져 MAX 가 내려가도 카운터는 안 내려간다 — 외부 식별자는
            # 삭제 후에도 재사용하지 않는다(§5.2).
            db.execute(
                text("DELETE FROM tickets WHERE project_uid = :pid AND seq >= 7"),
                {"pid": PROJECT_ID},
            )
            db.commit()
            numbering.seed_counters(db)
            db.commit()
            assert numbering.peek(db, PROJECT_ID) == 8
    finally:
        engine.dispose()
