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

from pathlib import Path

import pytest

from app.core import uploads
from app.core.errors import StorageUnavailableError, ValidationAppError

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


# ── 다운로드 파일명 (Z13) ──────────────────────────────────────────────────────
# 세 첨부 라우트가 `Content-Disposition: inline` 만 보내고 원본 표시명을 한 번도 싣지 않았다.
# 이름은 DB 에 있고 살균 함수까지 있었는데(주석이 "다운로드 시 Content-Disposition 표시용"
# 이라 적고 있다) 아무도 안 썼다. 운영 실측(2026-08-05) 첨부 2건은 둘 다 한글 파일명이다 —
# 저장하면 UUID 이름에 확장자 없는 파일이 떨어졌다.

from app.core.uploads import content_disposition  # noqa: E402


def test_korean_filename_survives_as_rfc5987():
    header = content_disposition("스크린샷 2026-08-05 092127.png")

    # 옛 클라이언트용 ASCII 폴백 — 확장자는 살아 있어야 한다(그래야 열린다).
    assert 'filename="' in header
    assert ".png" in header
    # 요즘 브라우저가 쓰는 진짜 이름.
    assert "filename*=UTF-8''" in header
    assert "%EC%8A%A4%ED%81%AC%EB%A6%B0%EC%83%B7" in header  # '스크린샷'


def test_header_is_latin1_encodable():
    """HTTP 헤더는 latin-1 이다. 한글을 그대로 넣으면 응답 자체가 터진다."""
    header = content_disposition("보고서_2026년_1분기.pdf")
    header.encode("latin-1")  # 여기서 UnicodeEncodeError 가 나면 실패


def test_quotes_and_backslashes_cannot_break_the_header():
    """헤더 문법을 깨뜨리는 문자가 파일명에 있어도 구조가 유지된다."""
    header = content_disposition('evil".png')
    assert header.count('"') == 2  # filename="..." 의 여닫는 따옴표뿐


def test_attachment_disposition_is_available_for_downloads():
    assert content_disposition("a.pdf", inline=False).startswith("attachment;")
    assert content_disposition("a.pdf").startswith("inline;")


def test_empty_name_falls_back():
    header = content_disposition("")
    assert 'filename="file"' in header


# ── 디스크 쓰기 실패 (OPS-05) ──────────────────────────────────────────────────
# save_upload의 mkdir/write_bytes는 예전엔 try/except가 없어 디스크 풀·권한 드리프트
# 같은 OSError가 그대로 안 잡힌 500(raw 스택트레이스 노출)으로 샜다. 이제
# StorageUnavailableError(503, 원인 미노출 메시지)로 번역된다 — 실제 서버 없이도
# Path.mkdir/write_bytes를 몽키패치해 검증할 수 있다.


def test_mkdir_failure_becomes_storage_unavailable_error(tmp_path, monkeypatch):
    def _boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", _boom)
    with pytest.raises(StorageUnavailableError) as exc_info:
        uploads.save_upload(tmp_path, POST_ID, filename="a.png", content=PNG)
    # 원인(OSError 원문·경로)이 사용자 메시지에 새지 않는다.
    assert "disk full" not in exc_info.value.message
    assert str(tmp_path) not in exc_info.value.message
    assert exc_info.value.status_code == 503


def test_write_bytes_failure_becomes_storage_unavailable_error(tmp_path, monkeypatch):
    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "write_bytes", _boom)
    with pytest.raises(StorageUnavailableError) as exc_info:
        uploads.save_upload(tmp_path, POST_ID, filename="a.png", content=PNG)
    assert "permission denied" not in exc_info.value.message
    assert exc_info.value.status_code == 503
