"""BKP-02: 복구 리허설이 DB 복원만 증명하고 첨부 파일까지는 증명하지 않았다.

`scripts/restore_rehearsal.py::check_attachment_files`가 board/team_chat/ticket/avatar
네 자원 각각의 (테이블, 네임스페이스, owner_id 컬럼, 저장명 컬럼) 매핑을 실제로 따라가
파일 존재를 확인하는지 — 있는 것은 통과, 없는 것은 정확히 짚어내는지 — 순수 함수 수준
(스크립트 전체를 실행하지 않고)에서 못 박는다.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.restore_rehearsal import check_attachment_files

pytestmark = pytest.mark.unit


def _make_db(tmp_path):
    db_path = tmp_path / "restored.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE board_attachments (post_id TEXT, stored_name TEXT);
        CREATE TABLE chat_message_images (room_id TEXT, stored_name TEXT);
        CREATE TABLE ticket_attachments (ticket_uid TEXT, stored_name TEXT);
        CREATE TABLE user_preferences (user_id TEXT, avatar_stored_name TEXT);
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_reports_nothing_missing_when_every_referenced_file_exists(tmp_path):
    db_path = _make_db(tmp_path)
    uploads = tmp_path / "uploads"
    conn = sqlite3.connect(str(db_path))
    conn.execute("insert into board_attachments values ('post-1', 'a.png')")
    conn.execute("insert into ticket_attachments values ('ticket-1', 'b.pdf')")
    conn.commit()
    conn.close()
    _touch(uploads / "board" / "post-1" / "a.png")
    _touch(uploads / "ticket" / "ticket-1" / "b.pdf")

    missing = check_attachment_files(db_path, uploads)
    assert missing == []


def test_flags_a_missing_file_per_attachment_kind(tmp_path):
    db_path = _make_db(tmp_path)
    uploads = tmp_path / "uploads"
    conn = sqlite3.connect(str(db_path))
    conn.execute("insert into board_attachments values ('post-1', 'present.png')")
    conn.execute("insert into board_attachments values ('post-2', 'gone.png')")  # 파일 없음
    conn.execute("insert into chat_message_images values ('room-1', 'chat-gone.png')")  # 파일 없음
    conn.execute("insert into ticket_attachments values ('ticket-1', 'ticket-gone.pdf')")  # 파일 없음
    conn.execute("insert into user_preferences values ('user-1', 'avatar-gone.png')")  # 파일 없음
    conn.execute("insert into user_preferences values ('user-2', NULL)")  # 아바타 없음 — 정상, 건드리지 않아야 함
    conn.commit()
    conn.close()
    _touch(uploads / "board" / "post-1" / "present.png")

    missing = check_attachment_files(db_path, uploads)
    assert len(missing) == 4, missing
    joined = "\n".join(missing)
    assert "gone.png" in joined and "post-2" in joined
    assert "chat-gone.png" in joined and "room-1" in joined
    assert "ticket-gone.pdf" in joined and "ticket-1" in joined
    assert "avatar-gone.png" in joined and "user-1" in joined
    # NULL 아바타(user-2)는 애초에 확인 대상이 아니다 — 잘못 짚으면 안 된다.
    assert "user-2" not in joined


def test_reports_a_missing_table_instead_of_silently_skipping_it(tmp_path):
    db_path = tmp_path / "partial.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE board_attachments (post_id TEXT, stored_name TEXT)")
    conn.commit()
    conn.close()
    # chat_message_images/ticket_attachments/user_preferences 테이블 자체가 없는 상태 —
    # (구버전 백업 등) 조용히 건너뛰지 않고 "조회 실패"로 보고해야 한다.

    missing = check_attachment_files(db_path, tmp_path / "uploads")
    failures = [m for m in missing if "조회 실패" in m]
    assert len(failures) == 3, missing
