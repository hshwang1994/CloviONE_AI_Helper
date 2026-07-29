"""Retention enforcement (spec §14.4 conversation/notification retention).

Deletes conversations (and their messages) and notifications older than the
effective retention settings. Runs periodically from the worker loop so the
admin-editable retention settings have a real effect.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.conversations.models import Conversation, Message
from app.notifications.models import Notification

# SQLite caps host variables (default ~32766); an `id IN (...)` clause inlines
# one variable per id, so a huge backlog would blow the limit. Chunk deletes.
_ID_BATCH_SIZE = 500


def _batched(items: Sequence[str], size: int = _ID_BATCH_SIZE) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def purge_old_conversations(db: Session, *, now: datetime, retention_days: int) -> int:
    cutoff = now - timedelta(days=retention_days)
    old_ids = [
        row[0]
        for row in db.execute(
            select(Conversation.id).where(Conversation.updated_at < cutoff)
        ).all()
    ]
    if not old_ids:
        return 0
    # 보존기간 만료도 삭제다 — 대화 원문이 Job 큐에 남으면 만료가 아니다.
    from app.chat.service import purge_conversation_job_payloads

    for batch in _batched(old_ids):
        batch = list(batch)
        purge_conversation_job_payloads(db, batch)
        db.execute(delete(Message).where(Message.conversation_id.in_(batch)))
        db.execute(delete(Conversation).where(Conversation.id.in_(batch)))
    db.flush()
    return len(old_ids)


def purge_old_notifications(db: Session, *, now: datetime, retention_days: int) -> int:
    cutoff = now - timedelta(days=retention_days)
    result = db.execute(delete(Notification).where(Notification.created_at < cutoff))
    db.flush()
    return result.rowcount or 0


def purge_old_jobs(db: Session, *, now: datetime, retention_days: int = 60) -> int:
    """Delete terminal Job rows older than the cutoff (§21.6 큐 무한 성장 방지).

    Nothing references the jobs table by foreign key, so terminal rows
    (succeeded/failed/cancelled) can be removed once past retention. Queued and
    running jobs are always kept. Returns the number of rows deleted.
    """
    from app.jobs.models import (
        STATUS_CANCELLED,
        STATUS_FAILED,
        STATUS_SUCCEEDED,
        Job,
    )

    cutoff = now - timedelta(days=retention_days)
    result = db.execute(
        delete(Job).where(
            Job.status.in_([STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED]),
            Job.updated_at < cutoff,
        )
    )
    db.flush()
    return result.rowcount or 0


def purge_old_schedule_runs(db: Session, *, now: datetime, retention_days: int = 60) -> int:
    """Delete schedule_run history rows older than the cutoff (§21.14 이력 무한 성장 방지).

    Age is measured on created_at (the run's insertion time). Returns rows deleted.
    """
    from app.schedules.models import ScheduleRun

    cutoff = now - timedelta(days=retention_days)
    result = db.execute(delete(ScheduleRun).where(ScheduleRun.created_at < cutoff))
    db.flush()
    return result.rowcount or 0


def strip_stale_job_attachments(db: Session, *, now: datetime, max_age_hours: int = 24) -> int:
    """Purge image bytes lingering in terminal chat_message jobs (§13 확장 서버 미보관).

    Bytes stay only while a failed job might still be retried; anything terminal and
    older than the window is stripped to name stubs. Returns jobs touched.
    """
    import json

    from app.jobs.handlers.chat_message import strip_attachment_bytes
    from app.jobs.models import Job

    cutoff = now - timedelta(hours=max_age_hours)
    rows = (
        db.execute(
            select(Job).where(
                Job.job_type == "chat_message",
                Job.status.in_(["succeeded", "failed", "cancelled"]),
                Job.updated_at < cutoff,
                Job.payload_json.like('%"data"%'),
            )
        )
        .scalars()
        .all()
    )
    touched = 0
    for job in rows:
        try:
            payload = json.loads(job.payload_json)
        except (ValueError, TypeError):
            continue
        attachments = payload.get("attachments")
        if isinstance(attachments, list) and any(
            isinstance(a, dict) and a.get("data") and not a.get("stripped")
            for a in attachments
        ):
            strip_attachment_bytes(job, payload)
            touched += 1
    if touched:
        db.flush()
    return touched


def run_retention(db: Session, *, now: datetime, settings_cache) -> dict:
    values = settings_cache.current()
    conv_days = int(values.get("conversation_retention_days", 365))
    notif_days = int(values.get("notification_retention_days", 90))
    job_days = int(values.get("job_retention_days", 60))
    run_days = int(values.get("schedule_run_retention_days", 60))
    return {
        "conversations": purge_old_conversations(db, now=now, retention_days=conv_days),
        "notifications": purge_old_notifications(db, now=now, retention_days=notif_days),
        "job_attachments": strip_stale_job_attachments(db, now=now),
        "jobs": purge_old_jobs(db, now=now, retention_days=job_days),
        "schedule_runs": purge_old_schedule_runs(db, now=now, retention_days=run_days),
    }
