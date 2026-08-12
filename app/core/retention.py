"""Retention enforcement (spec §14.4 conversation/notification retention).

Deletes conversations (and their messages) and notifications older than the
effective retention settings. Runs periodically from the worker loop so the
admin-editable retention settings have a real effect.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.conversations.models import Conversation, Message
from app.core.db import batched
from app.notifications.models import Notification

logger = logging.getLogger(__name__)


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

    for batch in batched(old_ids):
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


def purge_old_sessions(db: Session, *, now: datetime, retention_days: int = 60) -> int:
    """만료·폐기된 세션 행을 정리한다 (CORE-02, `purge_old_jobs`와 같은 판단).

    **아직 살아 있는 세션은 나이와 무관하게 절대 안 지운다.** 지울 수 있는 행은 둘 중
    하나다:
      ① `revoked_at IS NOT NULL` — 로그아웃·강제 종료·`validate()`가 이미 만료를
         감지해 처리한 것.
      ② `revoked_at IS NULL` 이지만 `expires_at` 이 지난 것(RET-01R) — `validate()`의
         만료 감지는 **그 토큰이 다시 제시될 때만** 도는 지연 판정이라, 만료된 뒤
         아무도 그 세션으로 다시 접근하지 않으면(재로그인해 새 세션을 만들고 예전
         탭은 버리는 흔한 경우) `revoked_at` 이 영원히 안 찍혀 ①만으로는 절대
         정리되지 않는다.
    어느 쪽이든 "끝난 시각"(`revoked_at` 또는 `expires_at`) 기준으로 `retention_days`가
    지난 것만 지운다(당장은 `profiles`의 "최근 종료된 세션" 목록이 잠시 보여야 하므로
    즉시 지우지 않는다).
    """
    from app.auth.models import UserSession

    cutoff = now - timedelta(days=retention_days)
    result = db.execute(
        delete(UserSession).where(
            or_(
                and_(UserSession.revoked_at.is_not(None), UserSession.revoked_at < cutoff),
                and_(UserSession.revoked_at.is_(None), UserSession.expires_at < cutoff),
            )
        )
    )
    db.flush()
    return result.rowcount or 0


# 티켓이 Notion 에서 사라진 뒤 캐시 행을 붙들고 있는 기간 (0043).
#
# 왜 유예를 두는가: prune 은 "이번 조회에서 못 봤다" 만 안다. 그 이유가 진짜 삭제인지
# 한 회차 깜빡임인지 구별할 방법이 없어서, 즉시 지우면 깜빡임 한 번에 그 티켓의 댓글·첨부·
# 미push 본문이 **영구히** 사라진다(셋 다 Notion 에 없어 재동기화로 안 돌아온다).
#
# 왜 14일인가: 휴지통(기본 7일)보다 길게 잡는다. 휴지통은 **사람이 의도해서** 버린 것이고
# 이건 **시스템이 추측한** 것이라, 추측이 틀렸을 때 되돌릴 시간을 더 준다.
MISSING_TICKET_GRACE_DAYS = 14


def purge_missing_tickets(
    db: Session, *, now: datetime, grace_days: int = MISSING_TICKET_GRACE_DAYS
) -> int:
    """유예를 넘겨도 Notion 에 돌아오지 않은 티켓 캐시 행을 진짜로 지운다 (0043).

    여기서 일어나는 CASCADE(댓글·첨부 삭제)는 **의도된 정리**다 — 2주 동안 원본이 없었다면
    그건 깜빡임이 아니라 삭제다. 그 판단을 동기화 시점이 아니라 여기서 하는 것이 이 변경의
    전부다.

    `db.delete(row)` 로 **ORM 을 거쳐** 지운다. `delete()` 문 하나로 지우면 SQLite 의
    `ON DELETE CASCADE` 는 동작하지만 ORM 세션이 자식 상태를 모르는 채 남고, 이 저장소는
    같은 세션에서 이어서 다른 정리를 한다. 행 수가 작아(유예를 넘긴 것만) 비용도 무시할 만하다.
    """
    from app.tickets.models import TicketCache

    cutoff = now - timedelta(days=grace_days)
    rows = db.execute(
        select(TicketCache).where(
            TicketCache.notion_missing_at.is_not(None),
            TicketCache.notion_missing_at < cutoff,
        )
    ).scalars().all()
    for row in rows:
        db.delete(row)
    db.flush()
    if rows:
        logger.info("retention: Notion 에서 사라진 티켓 %d건을 유예(%d일) 뒤 삭제", len(rows), grace_days)
    return len(rows)


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


def purge_mail_history(db: Session, *, now: datetime, retention_days: int = 90) -> int:
    """끝난 메일 발송 기록을 정리한다 (9-9 P4).

    ``queued`` 는 절대 건드리지 않는다 - 워커가 아직 집지 않았을 뿐 살아 있는 작업이다.
    보낸 것과 실패한 것만 지운다. 실패 기록까지 지우는 것이 아깝게 느껴질 수 있지만, 그건
    "왜 안 왔나" 를 묻는 창(기본 90일)을 지나면 아무도 다시 보지 않는 값이고, 그대로 두면
    이 표만 무한히 자란다(`purge_old_jobs` 와 같은 판단).
    """
    from app.mail.models import MAIL_FAILED, MAIL_SENT, MAIL_UNCONFIGURED, MailDelivery

    cutoff = now - timedelta(days=retention_days)
    result = db.execute(
        delete(MailDelivery).where(
            MailDelivery.status.in_([MAIL_SENT, MAIL_FAILED, MAIL_UNCONFIGURED]),
            MailDelivery.created_at < cutoff,
        )
    )
    db.flush()
    return result.rowcount or 0


GAME_ROOM_RETENTION_DAYS = 7


def purge_old_game_rooms(db: Session, *, now: datetime, retention_days: int = GAME_ROOM_RETENTION_DAYS) -> int:
    """끝난 게임방과 그 멤버·이벤트 행을 정리한다 (RET-03/GM-04).

    `app/games/models.py` 모듈 docstring이 만들어질 때부터 이미 명시했다 — "게임 히스토리는
    남기지 않는다(§16.1): 방이 끝나고 정리 시간이 지나면 방·이벤트를 지운다(retention에서
    처리, 여기선 스키마만)." 하지만 retention.py에는 그 처리가 실제로 없었다 — `game_rooms`·
    `game_room_members`·`game_events` 세 표가 무기한 쌓이기만 했다(실측 15행, `closed_at`
    전부 채워짐 = 남아 있을 이유가 없는 행들).

    `closed_at IS NOT NULL`(끝난 방)만 대상이다 — 아직 열려 있는 방은 나이와 무관하게 절대
    안 지운다(`purge_old_sessions`와 같은 판단). GM-01이 고친 `cleanup_idle_rooms`가 유휴
    방을 이미 `closed_at`으로 닫아 두므로, 여기 못 미치는 "영원히 열린 채 방치된 방"은 없다.
    `disband_room`/`list_open_rooms`가 이미 `closed_at`을 "끝났다"의 유일한 근거로 쓴다
    (`status`가 아니라) — 여기서도 같은 근거를 쓴다.

    FK에 `ON DELETE CASCADE`가 없다(0019 마이그레이션은 순수 FK만 건다) — 자식(멤버·이벤트)을
    먼저 지운다(`purge_old_conversations`와 같은 순서).
    """
    from app.games.models import GameEvent, GameRoom, GameRoomMember

    cutoff = now - timedelta(days=retention_days)
    old_ids = [
        row[0]
        for row in db.execute(
            select(GameRoom.id).where(
                GameRoom.closed_at.is_not(None), GameRoom.closed_at < cutoff
            )
        ).all()
    ]
    if not old_ids:
        return 0
    for batch in batched(old_ids):
        batch = list(batch)
        db.execute(delete(GameEvent).where(GameEvent.room_id.in_(batch)))
        db.execute(delete(GameRoomMember).where(GameRoomMember.room_id.in_(batch)))
        db.execute(delete(GameRoom).where(GameRoom.id.in_(batch)))
    db.flush()
    return len(old_ids)


def purge_used_reset_tokens(db: Session, *, now: datetime) -> int:
    """다 쓴 비밀번호 재설정 토큰을 정리한다 (9-9 P4).

    만료된 지 한참 지난 행만 지운다 - 재사용 시도를 '이미 쓴 토큰' 으로 알아보려면 잠시는
    남아 있어야 한다(app/auth/reset_service.py 가 지우지 않고 표시만 하는 이유).
    """
    from app.auth.reset_service import purge_expired

    return purge_expired(db, now=now)


def run_retention(db: Session, *, now: datetime, settings_cache, outbound=None, settings=None) -> dict:
    values = settings_cache.current()
    conv_days = int(values.get("conversation_retention_days", 365))
    notif_days = int(values.get("notification_retention_days", 90))
    job_days = int(values.get("job_retention_days", 60))
    run_days = int(values.get("schedule_run_retention_days", 60))
    game_room_days = int(values.get("game_room_retention_days", GAME_ROOM_RETENTION_DAYS))
    result = {
        "conversations": purge_old_conversations(db, now=now, retention_days=conv_days),
        "notifications": purge_old_notifications(db, now=now, retention_days=notif_days),
        "job_attachments": strip_stale_job_attachments(db, now=now),
        # RET-03/GM-04: 끝난 게임방은 §16.1이 "히스토리를 남기지 않는다"고 이미 약속했다.
        "game_rooms": purge_old_game_rooms(db, now=now, retention_days=game_room_days),
        # Notion 에서 사라진 티켓의 캐시 행 — **유예를 넘긴 것만** 지운다(0043).
        # 동기화가 즉시 지우던 것을 여기로 옮겼다.
        "missing_tickets": purge_missing_tickets(db, now=now),
        "jobs": purge_old_jobs(db, now=now, retention_days=job_days),
        "schedule_runs": purge_old_schedule_runs(db, now=now, retention_days=run_days),
        "sessions": purge_old_sessions(db, now=now),
        # 메일 아웃박스와 재설정 토큰(9-9 P4). 둘 다 안 지우면 무한히 자라고, 토큰 쪽은
        # 다 쓴 비밀의 해시를 필요 이상으로 오래 들고 있게 된다.
        "mail_history": purge_mail_history(db, now=now, retention_days=notif_days),
        "reset_tokens": purge_used_reset_tokens(db, now=now),
    }
    # 도달할 수 없는 업로드 파일 (C7).
    #
    # ⚠️ `getattr` 로 읽는다. `settings` 는 여기서 **완전한 Settings 가 아닐 수 있다** -
    # 호출부 중에는 휴지통 정리에 필요한 것만 담은 최소 스텁을 넘기는 곳이 있고, 실제로
    # `settings.data_dir` 을 무조건 읽었다가 AttributeError 로 **정리 전체가 죽었다.**
    # 그 자리에서 죽으면 앞서 지운 것들의 커밋도 못 하고, 원인은 스택 트레이스에만 남는다.
    #
    # 경로를 모르면 **추측하지 않고 건너뛴다.** 파일을 지우는 일에서 경로를 추측하는 것은
    # 할 수 있는 가장 나쁜 선택이다. 건너뛴 사실은 결과에 남겨 사람이 볼 수 있게 한다.
    data_dir = getattr(settings, "data_dir", None) if settings is not None else None
    if data_dir is not None:
        result["orphan_uploads"] = sweep_orphan_uploads(db, data_dir=data_dir, now=now)
    else:
        result["orphan_uploads"] = {"skipped": "데이터 디렉터리를 알 수 없어 건너뜀"}
    # 휴지통 만료 정리는 노션 호출(archive)이 필요해 outbound/settings 가 주어질 때만 돈다.
    if outbound is not None and settings is not None:
        from app.trash import service as trash_service

        trash_days = int(values.get("trash_retention_days", 7))
        result["trash"] = trash_service.purge_expired(
            db, now=now, retention_days=trash_days, outbound=outbound, settings=settings
        )
    return result


# ── 고아 업로드 파일 청소 (C7) ────────────────────────────────────────────────
#
# 첨부의 DB 행은 부모가 사라질 때 CASCADE 로 지워지지만 **파일은 디스크에 남는다.**
# 아무도 도달할 수 없는 바이트가 영원히 쌓인다.
#
# 지우는 쪽이 위험하다는 것이 지금까지 안 지운 이유다(TicketAttachment docstring). 그래서
# 두 조건을 **함께** 건다:
#   ① DB 어디에서도 그 저장명을 참조하지 않는다
#   ② 파일이 유예 기간보다 오래됐다
# ②가 없으면 방금 저장했는데 아직 커밋되지 않은 행의 파일을 지운다 — 사용자가 올린 원본이
# 업로드 도중에 사라지는, 가장 나쁜 종류의 사고다.
ORPHAN_UPLOAD_GRACE_DAYS = 30


def _referenced_stored_names(db: Session) -> set[str]:
    """DB 가 아직 가리키고 있는 저장명 전부.

    한 종류라도 빠뜨리면 **살아 있는 첨부를 지운다.** 그래서 표를 여기 한 곳에 모으고,
    새 첨부 종류가 생기면 여기 추가하지 않는 한 테스트가 잡도록 해 둔다.
    """
    from app.board.models import PostAttachment
    from app.profiles.models import UserPreference
    from app.team_chat.models import ChatMessageImage
    from app.tickets.models import TicketAttachment

    names: set[str] = set()
    for model, column in (
        (TicketAttachment, "stored_name"),
        (PostAttachment, "stored_name"),
        (ChatMessageImage, "stored_name"),
        (UserPreference, "avatar_stored_name"),
    ):
        for value in db.execute(select(getattr(model, column))).scalars().all():
            if value:
                names.add(value)
    return names


def sweep_orphan_uploads(
    db: Session, *, data_dir, now: datetime, grace_days: int = ORPHAN_UPLOAD_GRACE_DAYS,
    dry_run: bool = False,
) -> dict:
    """도달할 수 없는 업로드 파일을 지운다. `dry_run` 이면 세기만 한다.

    실패를 조용히 넘기지 않는다 — 권한 문제로 한 파일도 못 지우는 상태가 되면 그 사실이
    보여야 한다(휴지통에서 겪은 H5 와 같은 실수를 반복하지 않는다).
    """
    from pathlib import Path

    root = Path(data_dir) / "uploads"
    if not root.is_dir():
        return {"scanned": 0, "removed": 0, "kept_young": 0, "failed": 0, "dry_run": dry_run}

    referenced = _referenced_stored_names(db)
    cutoff = now - timedelta(days=max(1, int(grace_days)))
    scanned = removed = kept_young = failed = 0
    freed_bytes = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        scanned += 1
        if path.name in referenced:
            continue
        try:
            stat = path.stat()
        except OSError:
            failed += 1
            continue
        # `now` 는 naive UTC(앱 규약)이고 mtime 은 epoch 초다. UTC 로 맞춰 비교한다 —
        # 로컬 시간으로 비교하면 KST 서버에서 9시간짜리 오차가 생겨 유예가 그만큼 짧아진다.
        modified = datetime.utcfromtimestamp(stat.st_mtime)
        if modified > cutoff:
            kept_young += 1
            continue
        if dry_run:
            removed += 1
            freed_bytes += stat.st_size
            continue
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("고아 업로드 파일을 지우지 못했습니다: %s (%s)", path.name, type(exc).__name__)
            failed += 1
            continue
        removed += 1
        freed_bytes += stat.st_size

    return {
        "scanned": scanned, "removed": removed, "kept_young": kept_young,
        "failed": failed, "freed_bytes": freed_bytes, "dry_run": dry_run,
    }
