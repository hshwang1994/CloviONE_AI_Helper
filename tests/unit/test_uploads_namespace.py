"""app/core/uploads 의 네임스페이스 경계 (PLAN §D-3).

`uploads/board/<post_id>` 하나로 굳어 있던 저장 경로를 `uploads/<namespace>/<owner_id>/` 로
일반화했다. **네임스페이스가 곧 접근 통제 경계**이므로, traversal 가드가 그 네임스페이스의
뿌리를 기준으로 동작하는지(=한 네임스페이스의 라우트가 다른 네임스페이스의 파일을 절대
집어 올 수 없는지)를 여기서 못 박는다.

owner_id 는 **서버가 만든 UUID** 다. 새니타이즈가 hex 와 하이픈만 남기므로 테스트도 실제와
같은 모양을 쓴다 — 'room-1' 같은 가짜 id 를 쓰면 새니타이즈 후 '-1' 이 되어 무엇을
검증하는지 알 수 없는 테스트가 된다.
"""

from __future__ import annotations

import pytest

from app.core import uploads
from app.core.errors import ValidationAppError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"\x00" * 32

POST_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
ROOM_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


def test_board_default_namespace_is_unchanged(tmp_path):
    """기본값은 그대로 board 다 — 게시판 호출부는 한 글자도 바뀌지 않는다."""
    stored, media, size, name = uploads.save_upload(
        tmp_path, POST_ID, filename="사진.png", content=PNG
    )
    assert media == "image/png" and size == len(PNG) and name == "사진.png"
    assert (tmp_path / "uploads" / "board" / POST_ID / stored).is_file()
    assert uploads.attachment_path(tmp_path, POST_ID, stored) is not None


def test_namespaces_are_separate_directories(tmp_path):
    stored, _, _, _ = uploads.save_upload(
        tmp_path, ROOM_ID, filename="a.png", content=PNG, namespace=uploads.NS_TEAM_CHAT
    )
    assert (tmp_path / "uploads" / "team_chat" / ROOM_ID / stored).is_file()
    assert not (tmp_path / "uploads" / "board" / ROOM_ID).exists()


def test_a_file_is_invisible_from_the_other_namespace(tmp_path):
    """게시판 라우트가 채팅 파일을 서빙하는 경로가 없다 — 이게 DM 사진 유출의 원천 차단이다."""
    stored, _, _, _ = uploads.save_upload(
        tmp_path, ROOM_ID, filename="a.png", content=PNG, namespace=uploads.NS_TEAM_CHAT
    )
    assert uploads.attachment_path(tmp_path, ROOM_ID, stored, namespace=uploads.NS_TEAM_CHAT) is not None
    # 같은 owner_id·저장명이라도 board 네임스페이스에서는 없다.
    assert uploads.attachment_path(tmp_path, ROOM_ID, stored, namespace=uploads.NS_BOARD) is None


def test_resolved_path_never_leaves_the_namespace_root(tmp_path):
    """owner_id 에 무엇이 들어와도 해석된 경로는 uploads/<namespace>/ 안이다."""
    root = (tmp_path / "uploads" / "team_chat").resolve()
    stored, _, _, _ = uploads.save_upload(
        tmp_path, ROOM_ID, filename="a.png", content=PNG, namespace=uploads.NS_TEAM_CHAT
    )
    for evil in ("../board/" + ROOM_ID, "..\\..\\" + ROOM_ID, ROOM_ID + "/../../etc", "/etc/passwd"):
        path = uploads.attachment_path(tmp_path, evil, stored, namespace=uploads.NS_TEAM_CHAT)
        if path is not None:
            # 새니타이즈로 다른 폴더명이 됐을 뿐 뿌리 밖으로 나가지 못한다.
            path.relative_to(root)  # ValueError 면 탈출 — 테스트 실패
        assert path is None or path.is_file()


def test_stored_name_must_match_the_server_pattern(tmp_path):
    uploads.save_upload(tmp_path, ROOM_ID, filename="a.png", content=PNG, namespace=uploads.NS_TEAM_CHAT)
    for evil in ("../../secret.txt", "a.png", "", "..", "/etc/passwd", "..%2f..%2fetc"):
        assert uploads.attachment_path(tmp_path, ROOM_ID, evil, namespace=uploads.NS_TEAM_CHAT) is None


def test_image_only_namespace_rejects_pdf(tmp_path):
    with pytest.raises(ValidationAppError):
        uploads.save_upload(
            tmp_path, ROOM_ID, filename="doc.pdf", content=PDF,
            namespace=uploads.NS_TEAM_CHAT, allowed_media_types=uploads.IMAGE_MEDIA_TYPES,
        )
    # 같은 바이트가 게시판(기본 허용 목록)에서는 통과한다 — 거절은 형식이 아니라 정책이다.
    stored, media, _, _ = uploads.save_upload(tmp_path, POST_ID, filename="doc.pdf", content=PDF)
    assert media == "application/pdf" and stored.endswith(".pdf")


def test_magic_bytes_beat_the_declared_extension(tmp_path):
    with pytest.raises(ValidationAppError):
        uploads.save_upload(
            tmp_path, ROOM_ID, filename="evil.png", content=b"<html>hi</html>",
            namespace=uploads.NS_TEAM_CHAT, allowed_media_types=uploads.IMAGE_MEDIA_TYPES,
        )


def test_an_invalid_namespace_is_a_programming_error_not_a_path(tmp_path):
    """네임스페이스에 사용자 입력이 닿을 길은 없다 — 닿으면 경로가 되기 전에 터진다."""
    for evil in ("../board", "Board", "team chat", "", "a/b"):
        with pytest.raises(ValueError):
            uploads.save_upload(tmp_path, POST_ID, filename="a.png", content=PNG, namespace=evil)
