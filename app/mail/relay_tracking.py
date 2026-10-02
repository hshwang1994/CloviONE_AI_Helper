"""로컬 릴레이로 넘긴 메일의 바깥 전달 추적 (계획 M7, D-551 · D-555).

앱이 로컬 릴레이에 넘기면 발송 행은 「로컬 릴레이가 접수함」이다(`remote_status = queued`). 받는 쪽 서버가 받았는지는 릴레이만 안다.
배치 워커의 틱이 아직 끝나지 않은 행(queued · deferred)을 모아 특권 헬퍼에게 묻는다:

1. `mailrelay.queue` — 아직 큐에 있으면 미룸(지연 까닭이 있으면 그 단계)이거나 차례를 기다리는 중이다.
2. 큐를 떠난 행은 `mailrelay.log` 로 그 큐 id 의 마지막 결과를 읽는다 — 전달함(delivered) · 거부(bounced) · 시간 지남(expired).
3. 이틀이 지나도 결과를 못 찾으면 「모름」(unknown)으로 닫는다(로그가 회전됐거나 저널이 영속이 아닌 설치).

틱은 1분마다 돌고, 방금 넘긴 메일이 있으면 15초마다 돈다(시험 메일을 보낸 관리자가 결과를 기다린다). 헬퍼가 없거나 실패하면 이번
틱을 건너뛴다 - 행의 상태를 추측으로 바꾸지 않는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mail.labels import REMOTE_DEFERRED, REMOTE_QUEUED, REMOTE_UNKNOWN
from app.mail.models import MAIL_SENT, MailDelivery
from app.mail.relay_log import SAID_MAX, queue_state

logger = logging.getLogger("app.mail.relay_tracking")

TICK_SECONDS = 60
FAST_TICK_SECONDS = 15
RECENT = timedelta(minutes=3)
GIVE_UP_AFTER = timedelta(days=2)
BATCH = 200
LOG_CHUNK = 50
PENDING = (REMOTE_QUEUED, REMOTE_DEFERRED)


def pending_rows(db: Session, *, limit: int = BATCH) -> list[MailDelivery]:
    return list(db.execute(
        select(MailDelivery)
        .where(MailDelivery.status == MAIL_SENT, MailDelivery.remote_status.in_(PENDING),
               MailDelivery.relay_queue_id.is_not(None))
        .order_by(MailDelivery.sent_at)
        .limit(limit)
    ).scalars())


def _apply(row: MailDelivery, remote: str, stage: str | None, said: str | None, now: datetime) -> bool:
    changed = (row.remote_status, row.remote_stage, row.remote_detail) != (remote, stage, said)
    row.remote_status = remote
    row.remote_stage = stage
    row.remote_detail = (said or "")[:SAID_MAX] or None
    row.remote_checked_at = now
    if changed:
        row.updated_at = now
    return changed


def _epoch(value: datetime) -> int:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return int(aware.timestamp())


def track_once(db: Session, client, *, now: datetime) -> dict:
    """한 번 돈다. 돌려주는 값은 본 행 · 바꾼 행 수(시험과 로그가 쓴다)."""
    rows = pending_rows(db)
    if not rows:
        return {"checked": 0, "changed": 0}
    reply = client.call("mailrelay.queue", {})
    if not (reply.available and reply.ok):
        logger.info("로컬 릴레이 큐를 읽지 못해 이번 추적을 건너뜁니다: %s", reply.detail)
        return {"checked": 0, "changed": 0, "skipped": reply.detail}
    in_queue = {item.get("queue_id"): item for item in (reply.data or {}).get("items") or []}
    changed = 0
    gone: list[MailDelivery] = []
    for row in rows:
        item = in_queue.get(row.relay_queue_id)
        if item is not None:
            remote, stage, said = queue_state(item)
            changed += _apply(row, remote, stage, said, now)
        else:
            gone.append(row)
    for start in range(0, len(gone), LOG_CHUNK):
        chunk = gone[start:start + LOG_CHUNK]
        oldest = min((r.sent_at or now) for r in chunk) - timedelta(minutes=5)
        since = max(_epoch(oldest), _epoch(now - timedelta(days=13)))
        reply = client.call("mailrelay.log", {"queue_ids": sorted({r.relay_queue_id for r in chunk}), "since": since})
        results = ((reply.data or {}).get("results") or {}) if reply.available and reply.ok else None
        for row in chunk:
            found = (results or {}).get(row.relay_queue_id) or {}
            if found.get("status"):
                changed += _apply(row, found["status"], found.get("stage"), found.get("said"), now)
            elif results is not None and row.sent_at and now - row.sent_at > GIVE_UP_AFTER:
                changed += _apply(row, REMOTE_UNKNOWN, None, None, now)
            else:
                row.remote_checked_at = now
    db.flush()
    return {"checked": len(rows), "changed": changed}


def register_tick(worker, session_factory, *, client_factory=None) -> None:
    """배치 워커에 추적 틱을 단다(`app/worker_main.py`). 할 일이 없는 분에는 색인 질의 한 번이다."""
    last: list = [None]

    def relay_tracking_tick(now: datetime) -> None:
        with session_factory() as db:
            newest = db.execute(
                select(MailDelivery.sent_at)
                .where(MailDelivery.status == MAIL_SENT, MailDelivery.remote_status.in_(PENDING))
                .order_by(MailDelivery.sent_at.desc()).limit(1)
            ).scalar_one_or_none()
            if newest is None:
                return
            interval = FAST_TICK_SECONDS if now - newest < RECENT else TICK_SECONDS
            if last[0] is not None and (now - last[0]).total_seconds() < interval:
                return
            last[0] = now
            if client_factory is not None:
                client = client_factory()
            else:
                from app.sysops.client import SysopsClient

                client = SysopsClient()
            try:
                track_once(db, client, now=now)
                db.commit()
            except Exception:  # noqa: BLE001 - 추적이 워커 루프를 죽이지 않는다
                db.rollback()
                logger.exception("로컬 릴레이 바깥 전달 추적이 실패했습니다")

    worker.tick_callbacks.append(relay_tracking_tick)


def last_outcome(db: Session) -> dict | None:
    """상태 면의 「바깥 전달」 줄 — 가장 최근에 결과가 난 메일 하나(전달 · 거부 · 시간 지남 · 미룸)."""
    from app.mail.labels import REMOTE_BOUNCED, REMOTE_DELIVERED, REMOTE_EXPIRED, delivery_word

    row = db.execute(
        select(MailDelivery)
        .where(MailDelivery.remote_status.in_((REMOTE_DELIVERED, REMOTE_BOUNCED, REMOTE_EXPIRED, REMOTE_DEFERRED)))
        .order_by(MailDelivery.remote_checked_at.desc().nulls_last())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    from app.mail.relay_log import STAGE_SENTENCES

    return {
        "status": row.remote_status,
        "label": delivery_word(MAIL_SENT, mode="local_relay", remote_status=row.remote_status,
                               relay_delivery=row.relay_delivery),
        "sentence": STAGE_SENTENCES.get(row.remote_stage or "") if row.remote_status != REMOTE_DELIVERED else None,
        "at": row.remote_checked_at.isoformat() if row.remote_checked_at else None,
        "delivery_id": row.id,
    }
