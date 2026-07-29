"""Chat image attachment validation (spec §13 확장 — #34 Phase 2 이미지).

Images ride the message POST as base64 and are passed through to n8n → runner for
vision analysis. They are NOT persisted on the platform (사용자 결정: 서버 미보관,
Notion에만 첨부) — only the transient job payload carries the bytes, and the worker
strips them after a successful handoff. The stored user message keeps names only.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from app.core.errors import ValidationAppError

MAX_ATTACHMENTS = 3
MAX_DECODED_BYTES = 3 * 1024 * 1024  # per image (client downscales first)
MAX_TOTAL_DECODED_BYTES = 6 * 1024 * 1024

ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}

_FILENAME_RE = re.compile(r"^[\w가-힣 .()\[\]-]{1,120}$")

# Magic-byte signatures — the declared media type must match the actual bytes so a
# renamed non-image (html/svg/executable) can never enter the pipeline.
_MAGIC = {
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


def validate_attachments(raw: list[Any] | None) -> list[dict[str, str]]:
    """Validate and normalize client attachments.

    Returns a new list of {filename, media_type, data(base64)} dicts.
    Raises ValidationAppError with a user-facing Korean message on any problem.
    """
    if not raw:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_ATTACHMENTS:
        raise ValidationAppError(f"이미지는 한 번에 최대 {MAX_ATTACHMENTS}장까지 첨부할 수 있습니다.")

    normalized: list[dict[str, str]] = []
    total = 0
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValidationAppError("첨부 형식이 올바르지 않습니다.")
        media_type = str(item.get("media_type") or "").strip().lower()
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ValidationAppError("PNG, JPEG, WebP 이미지만 첨부할 수 있습니다.")
        filename = str(item.get("filename") or f"image-{index}").strip()[:120]
        if not _FILENAME_RE.match(filename):
            filename = f"image-{index}"
        data = str(item.get("data") or "")
        if not data:
            raise ValidationAppError("첨부 이미지 데이터가 비어 있습니다.")
        try:
            decoded = base64.b64decode(data, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValidationAppError("이미지 인코딩(base64)이 올바르지 않습니다.") from exc
        if len(decoded) > MAX_DECODED_BYTES:
            raise ValidationAppError("이미지 한 장은 최대 3MB까지 첨부할 수 있습니다.")
        total += len(decoded)
        if total > MAX_TOTAL_DECODED_BYTES:
            raise ValidationAppError("첨부 이미지 전체 용량은 최대 6MB입니다.")
        if not _MAGIC[media_type](decoded):
            raise ValidationAppError("이미지 내용이 형식과 일치하지 않습니다. 실제 이미지 파일인지 확인해주세요.")
        normalized.append({"filename": filename, "media_type": media_type, "data": data})
    return normalized


def attachment_names(attachments: list[dict[str, str]]) -> list[dict[str, str]]:
    """Data-free view (filename + type only) for the stored message payload."""
    return [
        {"filename": a["filename"], "media_type": a["media_type"]} for a in attachments
    ]
