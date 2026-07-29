"""로컬 파일 업로드 저장·검증 (팀 공간 첨부, 보안 §22).

원칙:
- **매직바이트로 형식을 판정**한다 — 선언된 Content-Type이나 사용자 확장자를 믿지 않는다.
- 저장명은 **서버가 만든 UUID + 판정된 확장자**다. 사용자 파일명은 표시용으로만 새니타이즈해
  보관하고 경로로 절대 쓰지 않는다(경로 traversal 원천 차단).
- 크기·개수 상한을 강제한다. 파일은 웹 루트 밖(data_dir/uploads/...)에 저장하고, 서빙은
  인증된 엔드포인트가 nosniff 헤더와 함께 한다(실행 불가).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.errors import ValidationAppError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS_PER_POST = 5

# 판정된 media_type → 저장 확장자.
_EXT_BY_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
ALLOWED_MEDIA_TYPES = frozenset(_EXT_BY_MEDIA)

# 서버 생성 저장명 패턴(서빙 시 방어적으로 재검증).
_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def sniff_media_type(head: bytes) -> str | None:
    """앞부분 바이트로 형식을 판정한다. 허용 목록 밖이면 None."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def sanitize_filename(name: str) -> str:
    """표시용 원본 파일명 정리 — 경로 구분자·제어문자·상위경로 토큰 제거, 길이 제한.

    반환값은 표시(다운로드 시 Content-Disposition)로만 쓴다. 절대 경로 구성에 쓰지 않는다.
    """
    if not name:
        return "file"
    # 경로 구분자 기준 마지막 요소만.
    base = name.replace("\\", "/").split("/")[-1]
    # 널바이트·제어문자 제거.
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '\r\n\t')
    # 상위경로 토큰 무력화.
    base = base.replace("..", "_").strip().strip(".")
    if not base:
        base = "file"
    return base[:200]


def _post_dir(data_dir: Path, post_id: str) -> Path:
    # post_id는 서버가 만든 UUID이며 라우터가 실제 존재하는 글에서 얻는다 — 그래도
    # 방어적으로 경로 구분자를 허용하지 않는다.
    safe_post = re.sub(r"[^0-9a-fA-F-]", "", post_id)
    return Path(data_dir) / "uploads" / "board" / safe_post


def save_upload(
    data_dir: Path, post_id: str, *, filename: str, content: bytes
) -> tuple[str, str, int, str]:
    """검증 후 파일을 저장한다.

    반환: (stored_name, media_type, size_bytes, display_filename).
    검증 실패는 ValidationAppError(422).
    """
    size = len(content)
    if size == 0:
        raise ValidationAppError("빈 파일은 올릴 수 없습니다.")
    if size > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationAppError(f"파일이 너무 큽니다. 최대 {mb}MB까지 올릴 수 있습니다.")

    media_type = sniff_media_type(content[:16])
    if media_type is None:
        raise ValidationAppError(
            "허용되지 않은 파일 형식입니다. 이미지(PNG·JPEG·GIF·WebP) 또는 PDF만 올릴 수 있습니다."
        )

    stored_name = f"{uuid.uuid4().hex}{_EXT_BY_MEDIA[media_type]}"
    target_dir = _post_dir(data_dir, post_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / stored_name).write_bytes(content)

    return stored_name, media_type, size, sanitize_filename(filename)


def attachment_path(data_dir: Path, post_id: str, stored_name: str) -> Path | None:
    """저장된 첨부의 실제 경로. 저장명이 서버 패턴에 맞고 파일이 실제로 있을 때만 반환."""
    if not _STORED_NAME_RE.match(stored_name or ""):
        return None
    path = _post_dir(data_dir, post_id) / stored_name
    # 최종 방어: 해석된 경로가 반드시 board 업로드 디렉터리 안이어야 한다.
    root = (Path(data_dir) / "uploads" / "board").resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None
