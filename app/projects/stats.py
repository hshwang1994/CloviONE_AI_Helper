"""프로젝트 진행률 · Health 캐시를 **언제** 다시 계산하는가 (계획 3.1).

## 무엇이 문제였나

`projects.progress_pct` · `health_score` 는 캐시다. 예전에는 배치 워커의 한 시간 주기 스윕만
그 캐시를 썼다. 그래서 새 프로젝트는 한 시간 동안 "아직 계산하지 않았습니다" 였고, 티켓을
끝내도 진행률이 한 시간 뒤에야 움직였다. 게다가 NULL 하나가 "계산 전" 과 "셀 작업이 없음"
을 함께 뜻해서 목록이 둘을 구별하지 못했다.

## 어떻게 고쳤나

- **계산 시점**: 티켓 · 관계 · 마일스톤 · 프로젝트 상태를 바꾸는 코드가 그 자리에서 영향을 받는
  프로젝트를 **표시만** 한다(`mark_projects`, `mark_ticket_rows`). 실제 계산은 세션이 커밋하기
  직전에 프로젝트마다 **한 번** 한다(`flush`). 티켓 50건을 한 번에 휴지통에 넣어도 프로젝트당
  계산은 한 번이고, 계산은 마지막 상태를 본다. ORM 이벤트로 "무엇이 바뀌었나" 를 추측하지
  않는다 - 표시는 언제나 명시적이다.
- **상태**: `stats_computed_at` 이 NULL 이면 계산 전(`pending`)이다. 계산했는데 값이 NULL 이면
  진행률은 `no_tasks`, Health 는 `unknown` 이다(`view`).
- 주기 스윕은 안전망으로 남는다(`app/projects/service.py::record_health_snapshots`) - 표시를
  빠뜨린 쓰기 경로가 있어도 다음 스윕이 따라잡는다.

계산이 실패해도 원래 쓰기(티켓 저장)는 커밋된다. 프로젝트마다 SAVEPOINT 를 잡고, 실패는 로그에
남긴 뒤 넘어간다 - 캐시 하나 때문에 사용자의 저장이 사라지면 안 된다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.models_base import split_names, utcnow

logger = logging.getLogger("app.projects.stats")

DIRTY_KEY = "project_stats_dirty"
NOW_KEY = "project_stats_now"
TZ_KEY = "project_stats_tz"
DEFAULT_TZ = "Asia/Seoul"

PROGRESS_PENDING = "pending"
PROGRESS_NO_TASKS = "no_tasks"
PROGRESS_COMPUTED = "computed"
HEALTH_PENDING = "pending"
HEALTH_UNKNOWN = "unknown"
HEALTH_SCORED = "scored"


def mark_projects(
    db: Session, project_ids: Iterable[str | None], *, now: datetime | None = None,
    tz: str | None = None,
) -> None:
    """이 프로젝트들의 캐시가 낡았다고 표시한다. 계산은 커밋 직전에 한다."""
    ids = {pid for pid in project_ids if pid}
    if not ids:
        return
    db.info.setdefault(DIRTY_KEY, set()).update(ids)
    if now is not None:
        db.info[NOW_KEY] = now
    if tz:
        db.info[TZ_KEY] = tz


def project_ids_for_ticket_rows(db: Session, rows: Iterable) -> set[str]:
    """티켓 행들이 속한 프로젝트 id. 새 축(`project_uid`)과 옛 축(`project_ids` 토큰)을 함께 본다.

    `repository.ticket_rows_for_project` 가 두 축으로 티켓을 모으므로 표시도 두 축을 봐야 한다.
    한 축만 보면 옛 축으로만 걸린 프로젝트는 영영 표시되지 않는다.
    """
    from app.projects.models import Project

    ids: set[str] = set()
    tokens: set[str] = set()
    for row in rows:
        if row is None:
            continue
        uid = getattr(row, "project_uid", None)
        if uid:
            ids.add(uid)
        tokens.update(split_names(getattr(row, "project_ids", None)))
    if tokens:
        found = db.execute(
            select(Project.id).where(Project.notion_page_id.in_(sorted(tokens)))
        ).scalars().all()
        ids.update(found)
    return ids


def mark_ticket_rows(
    db: Session, rows: Iterable, *, now: datetime | None = None, tz: str | None = None,
) -> None:
    mark_projects(db, project_ids_for_ticket_rows(db, list(rows)), now=now, tz=tz)


def local_today(now: datetime, tz: str = DEFAULT_TZ) -> str:
    return now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date().isoformat()


def flush(db: Session) -> int:
    """표시된 프로젝트를 한 번씩 다시 계산한다. 계산한 수를 돌려준다. 커밋하지 않는다."""
    ids = db.info.pop(DIRTY_KEY, None)
    now = db.info.pop(NOW_KEY, None) or utcnow()
    tz = db.info.pop(TZ_KEY, None) or DEFAULT_TZ
    if not ids:
        return 0
    from app.projects.models import Project
    from app.projects.service import recompute_stats

    today = local_today(now, tz)
    projects = db.execute(
        select(Project)
        .where(Project.id.in_(sorted(ids)), Project.archived_at.is_(None))
        .order_by(Project.id.asc())
    ).scalars().all()
    done = 0
    for project in projects:
        project_id = project.id
        try:
            with db.begin_nested():
                recompute_stats(db, project, today=today, now=now, tz=tz)
            done += 1
        except Exception:  # noqa: BLE001 - 캐시 때문에 사용자의 저장을 잃지 않는다
            logger.exception("프로젝트 진행률과 Health 재계산 실패 (다음 스윕이 다시 한다): %s", project_id)
    return done


@event.listens_for(Session, "before_commit")
def _flush_before_commit(session: Session) -> None:
    if session.info.get(DIRTY_KEY):
        flush(session)


@event.listens_for(Session, "after_rollback")
def _forget_after_rollback(session: Session) -> None:
    # 바깥 트랜잭션이 되돌려졌으면 표시한 변경도 사라졌다. 다음 커밋이 엉뚱한 계산을 하지 않게 지운다.
    for key in (DIRTY_KEY, NOW_KEY, TZ_KEY):
        session.info.pop(key, None)


def progress_state(pct, computed_at) -> str:
    if pct is not None:
        return PROGRESS_COMPUTED
    return PROGRESS_PENDING if computed_at is None else PROGRESS_NO_TASKS


def health_state(score, computed_at) -> str:
    if score is not None:
        return HEALTH_SCORED
    return HEALTH_PENDING if computed_at is None else HEALTH_UNKNOWN


def view(row) -> dict:
    """목록 · 상세 · 대시보드가 같은 모양으로 싣는 상태. 값과 상태를 따로 준다."""
    computed_at = getattr(row, "stats_computed_at", None)
    pct = getattr(row, "progress_pct", None)
    score = getattr(row, "health_score", None)
    return {
        "progress": {"pct": pct, "state": progress_state(pct, computed_at)},
        "health": {"score": score, "state": health_state(score, computed_at)},
        "stats_computed_at": computed_at.isoformat() if computed_at else None,
    }
