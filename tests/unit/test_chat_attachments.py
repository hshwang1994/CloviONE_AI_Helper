"""Image attachment validation (#34 Phase 2) — magic bytes, size, count, names view."""

import base64

import pytest

from app.chat.attachments import (
    MAX_ATTACHMENTS,
    attachment_names,
    validate_attachments,
)
from app.core.errors import ValidationAppError

pytestmark = pytest.mark.unit

# 1x1 transparent PNG — a real image so the magic check passes.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


def _att(**kw):
    base = {"filename": "shot.png", "media_type": "image/png", "data": PNG_B64}
    return {**base, **kw}


def test_valid_png_and_jpeg_pass():
    out = validate_attachments([_att(), _att(filename="err.jpg", media_type="image/jpeg", data=JPEG_B64)])
    assert [a["media_type"] for a in out] == ["image/png", "image/jpeg"]


def test_empty_and_none_return_empty():
    assert validate_attachments(None) == []
    assert validate_attachments([]) == []


def test_rejects_bad_media_type():
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(media_type="image/svg+xml")])
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(media_type="text/html")])


def test_rejects_magic_mismatch():
    # Claims JPEG but bytes are PNG → renamed-file smuggling must fail.
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(media_type="image/jpeg", data=PNG_B64)])
    # Claims PNG but bytes are arbitrary junk.
    junk = base64.b64encode(b"<script>alert(1)</script>").decode()
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(data=junk)])


def test_rejects_invalid_base64_and_empty_data():
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(data="!!!notbase64!!!")])
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(data="")])


def test_rejects_oversize_and_too_many():
    big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (3 * 1024 * 1024 + 10)).decode()
    with pytest.raises(ValidationAppError):
        validate_attachments([_att(data=big)])
    with pytest.raises(ValidationAppError):
        validate_attachments([_att()] * (MAX_ATTACHMENTS + 1))


def test_filename_sanitized():
    out = validate_attachments([_att(filename="../..\\evil<script>.png")])
    assert out[0]["filename"] == "image-1"  # unsafe name replaced, never echoed raw


def test_names_view_has_no_data():
    out = validate_attachments([_att()])
    names = attachment_names(out)
    assert names == [{"filename": "shot.png", "media_type": "image/png"}]
    assert "data" not in names[0]


def test_retention_strips_stale_terminal_job_attachments(tmp_path):
    """Never-retried failed jobs must lose their image bytes after the sweep window."""
    import json
    from datetime import datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.retention import strip_stale_job_attachments
    from app.jobs.models import Job
    from app.core.models_base import Base

    engine = create_engine(f"sqlite:///{tmp_path/'t.sqlite3'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 15, 12, 0, 0)
    with Session(engine) as db:
        payload = {"content": "x", "attachments": [
            {"filename": "a.png", "media_type": "image/png", "data": PNG_B64}]}
        old = Job(job_type="chat_message", status="failed",
                  payload_json=json.dumps(payload), available_at=now - timedelta(days=2),
                  created_at=now - timedelta(days=2), updated_at=now - timedelta(days=2))
        fresh = Job(job_type="chat_message", status="failed",
                    payload_json=json.dumps(payload), available_at=now,
                    created_at=now, updated_at=now)
        db.add_all([old, fresh]); db.flush()
        touched = strip_stale_job_attachments(db, now=now)
        assert touched == 1
        assert "data" not in json.loads(old.payload_json)["attachments"][0]
        assert json.loads(fresh.payload_json)["attachments"][0]["data"] == PNG_B64
