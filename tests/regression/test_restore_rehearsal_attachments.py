"""BKP-02: 복구 리허설이 DB 복원만 증명하고 첨부 파일까지는 증명하지 않았다.

`scripts/restore_rehearsal.py::check_attachment_files` 가 board/team_chat/ticket/avatar
네 자원 각각의 (표, 네임스페이스, owner_id 칸, 저장명 칸) 매핑을 실제로 따라가 파일 존재를
확인하는지 — 있는 것은 통과, 없는 것은 정확히 짚어내는지 — 순수 함수 수준에서 못 박는다.

qa-contract-change: 저장소가 PostgreSQL 로 바뀌어(D-187) 시험이 만들던 임시 sqlite 파일 자리를 전용 DB 안의 격리된 스키마가 대신한다. 확인하는 계약(네 자원 전수·NULL 은 건드리지 않음·표가 없으면 조용히 건너뛰지 않음)은 그대로이고, PG 에서만 생기는 함정 하나를 더 못 박았다.

**PG 에서 새로 생긴 함정**: 문장 하나가 실패하면 트랜잭션 전체가 중단 상태가 되어 다음
조회부터 `25P02` 로 줄줄이 실패한다. 그러면 표 하나가 없을 뿐인데 나머지도 「조회 실패」로
보고돼 진짜 원인이 묻힌다. 아래 마지막 시험이 그것을 막는다 — 멀쩡한 표를 일부러 마지막에
두고, 앞의 셋이 없어도 그것이 끝까지 읽히는지 본다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db import make_engine
from scripts.restore_rehearsal import check_attachment_files

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 표를 직접 만들고 지우기 때문에
# 공유 DB 를 쓰면 같은 시간에 도는 다른 시험의 스키마를 흔든다.
pytestmark = [pytest.mark.unit, pytest.mark.real_db]

SCHEMA = "bkp02"

_ALL_TABLES = """
    CREATE TABLE board_attachments (post_id TEXT, stored_name TEXT);
    CREATE TABLE chat_message_images (room_id TEXT, stored_name TEXT);
    CREATE TABLE ticket_attachments (ticket_uid TEXT, stored_name TEXT);
    CREATE TABLE user_preferences (user_id TEXT, avatar_stored_name TEXT);
"""


@pytest.fixture()
def conn(db_url):
    """네 표만 보이는 **격리된 스키마** 위의 커넥션.

    `search_path` 에 `public` 을 넣지 않는 것이 핵심이다. 넣으면 이름이 실제 제품 표로
    풀려서, 「표가 없을 때」 시험이 아무것도 확인하지 못한다.
    """
    engine = make_engine(db_url)
    with engine.connect() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        c.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        c.execute(text(f"SET search_path TO {SCHEMA}"))
        c.commit()
        yield c
    engine.dispose()


def _create_all(conn):
    for stmt in filter(None, (s.strip() for s in _ALL_TABLES.split(";"))):
        conn.execute(text(stmt))
    conn.commit()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_reports_nothing_missing_when_every_referenced_file_exists(conn, tmp_path):
    _create_all(conn)
    uploads = tmp_path / "uploads"
    conn.execute(text("insert into board_attachments values ('post-1', 'a.png')"))
    conn.execute(text("insert into ticket_attachments values ('ticket-1', 'b.pdf')"))
    conn.commit()
    _touch(uploads / "board" / "post-1" / "a.png")
    _touch(uploads / "ticket" / "ticket-1" / "b.pdf")

    missing = check_attachment_files(conn, uploads)
    assert missing == []


def test_flags_a_missing_file_per_attachment_kind(conn, tmp_path):
    _create_all(conn)
    uploads = tmp_path / "uploads"
    conn.execute(text("insert into board_attachments values ('post-1', 'present.png')"))
    conn.execute(text("insert into board_attachments values ('post-2', 'gone.png')"))
    conn.execute(text("insert into chat_message_images values ('room-1', 'chat-gone.png')"))
    conn.execute(text("insert into ticket_attachments values ('ticket-1', 'ticket-gone.pdf')"))
    conn.execute(text("insert into user_preferences values ('user-1', 'avatar-gone.png')"))
    # 아바타가 없는 사람 — 정상이므로 건드리지 않아야 한다.
    conn.execute(text("insert into user_preferences values ('user-2', NULL)"))
    conn.commit()
    _touch(uploads / "board" / "post-1" / "present.png")

    missing = check_attachment_files(conn, uploads)
    assert len(missing) == 4, missing
    joined = "\n".join(missing)
    assert "gone.png" in joined and "post-2" in joined
    assert "chat-gone.png" in joined and "room-1" in joined
    assert "ticket-gone.pdf" in joined and "ticket-1" in joined
    assert "avatar-gone.png" in joined and "user-1" in joined
    assert "user-2" not in joined


def test_reports_a_missing_table_instead_of_silently_skipping_it(conn, tmp_path):
    """구버전 백업처럼 표 자체가 없을 때, 조용히 건너뛰지 않고 **정확히 셋**을 짚는다.

    **있는 표를 일부러 마지막에 둔다**(`user_preferences` — `ATTACHMENT_CHECKS` 의 네 번째).
    앞의 셋이 없는 상태에서 그것을 무사히 읽어내는지가 이 시험의 전부다. PG 는 실패한 문장
    하나로 트랜잭션을 중단시키므로, 조회를 savepoint 로 감싸지 않으면 첫 실패 뒤 **멀쩡한
    표까지** 함께 죽어 넷이 된다. 그러면 사람은 백업이 통째로 깨진 줄 안다.

    앞에 두면 이 시험은 아무것도 증명하지 못한다 — 어느 쪽이든 셋이 나온다.
    """
    conn.execute(text("CREATE TABLE user_preferences (user_id TEXT, avatar_stored_name TEXT)"))
    conn.execute(text("insert into user_preferences values ('user-1', 'avatar.png')"))
    conn.commit()
    _touch(tmp_path / "uploads" / "avatar" / "user-1" / "avatar.png")

    missing = check_attachment_files(conn, tmp_path / "uploads")
    failures = [m for m in missing if "조회 실패" in m]
    assert len(failures) == 3, missing
    # 있는 표는 끝까지 읽혔다 — 실패 목록에도, 「파일 없음」 목록에도 없다.
    assert missing == failures
    assert "user_preferences" not in "\n".join(failures)
