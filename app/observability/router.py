"""시스템 상태 — 사용자 화면 배너의 유일한 출처 (0033, PLAN Phase 6).

## 왜 사용자에게 보여 주는가

티켓 미러가 30분째 안 돌면 사용자 화면에는 **30분 전 목록이 아무 표시 없이** 떠 있다.
사용자는 "방금 만든 티켓이 왜 없지?"라고 생각하고 다시 만든다. 그래서 **사실 한 줄**을
담백하게 알려 준다: "지금 티켓 동기화가 늦습니다(마지막 갱신 12:30)."

## 사용자에게 말하지 않는 것

컴포넌트 이름·예외 메시지·스택·러너 URL 은 **내보내지 않는다**. 그건 운영자 화면의 몫이고,
일반 사용자에게는 무엇을 하라는 지시도 못 되면서 내부 구조만 노출한다. 그래서 응답이
역할에 따라 달라진다 — 운영자 이상이면 원인(`detail`)이 함께 온다.

## 폴링에 기록을 걸지 않는다

이 엔드포인트는 사용자 셸이 주기적으로 부른다. 그래서 **읽기만 한다** — `usage_events` 기록도,
카운터 증가도 없다(0026 규칙: 폴링 경로에 기록을 걸면 읽기가 쓰기가 된다).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import CONSOLE_READ_ROLES
from app.core.deps import get_current_user, get_db
from app.observability.models import (
    COMPONENT_DOCUMENTS,
    COMPONENT_TICKETS,
    SYNC_ERROR,
    SyncStatus,
)
from app.users.models import User

router = APIRouter(prefix="/api/system", tags=["system"])

# 사용자에게 보여 줄 컴포넌트와 그 한국어 이름. **여기 없는 컴포넌트는 사용자 배너에
# 나오지 않는다** — 검색 인덱스가 늦은 것은 사용자가 할 수 있는 일도, 알아야 할 일도 아니다.
USER_VISIBLE = {
    COMPONENT_TICKETS: "티켓",
    COMPONENT_DOCUMENTS: "문서",
}

# 얼마나 늦어야 '늦다'고 말하는가. 티켓 동기화 간격 기본이 180초라 그 몇 배를 넘겨야
# 실제 이상이다 — 임계값이 너무 낮으면 정상 운영 중에도 배너가 깜빡여 아무도 안 믿게 된다.
LATE_AFTER_SECONDS = 15 * 60
# 이보다 오래 멈추면 '늦음'이 아니라 '중단'이다.
STALLED_AFTER_SECONDS = 60 * 60

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_CRITICAL = "critical"


def _age_seconds(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    return (now - value).total_seconds()


def _notice_for(row: SyncStatus, label: str, now: datetime) -> dict | None:
    """한 컴포넌트의 사용자용 알림 한 줄. 정상이면 None."""
    age = _age_seconds(row.last_success_at, now)
    if age is None:
        # 한 번도 성공한 적이 없다. 워커가 아직 안 돌았거나 연동이 미설정이다 —
        # 둘 다 사용자가 "지금 목록이 비어 있는 이유"로 알아야 할 사실이다.
        if row.status == SYNC_ERROR:
            return {
                "id": f"sync.{row.component}",
                "level": LEVEL_WARNING,
                "message": f"{label} 동기화가 아직 한 번도 완료되지 않았습니다.",
                "since": None,
            }
        return None
    if age >= STALLED_AFTER_SECONDS:
        level, word = LEVEL_CRITICAL, "멈춰 있습니다"
    elif age >= LATE_AFTER_SECONDS:
        level, word = LEVEL_WARNING, "늦어지고 있습니다"
    elif row.status == SYNC_ERROR:
        level, word = LEVEL_INFO, "일시적으로 실패했습니다"
    else:
        return None
    minutes = int(age // 60)
    return {
        "id": f"sync.{row.component}",
        "level": level,
        "message": (
            f"지금 {label} 동기화가 {word}. "
            f"마지막으로 정상 갱신된 지 {minutes}분 지났습니다. 최근 변경이 아직 안 보일 수 있습니다."
        ),
        "since": row.last_success_at.isoformat() if row.last_success_at else None,
    }


def _runner_notice(db: Session, now: datetime) -> dict | None:
    """러너 헬스 → 사용자 한 줄. 어떤 러너인지, 왜 죽었는지는 말하지 않는다."""
    from app.runners.models import Runner

    rows = (
        db.execute(select(Runner).where(Runner.enabled.is_(True))).scalars().all()
    )
    if not rows:
        return None
    down = [r for r in rows if r.last_health_status == "down"]
    if not down:
        return None
    if len(down) == len(rows):
        return {
            "id": "runner.all_down",
            "level": LEVEL_CRITICAL,
            "message": "지금 자동화, AI 기능이 응답하지 않습니다. 복구 중이니 잠시 후 다시 시도해 주세요.",
            "since": max((r.last_health_at for r in down if r.last_health_at), default=None).isoformat()
            if any(r.last_health_at for r in down)
            else None,
        }
    return {
        "id": "runner.some_down",
        "level": LEVEL_WARNING,
        "message": "일부 자동화, AI 기능이 평소보다 느리거나 실패할 수 있습니다.",
        "since": None,
    }


@router.get("/status")
def system_status(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """사용자 화면 상태 배너의 원본. 정상이면 `notices` 가 빈 배열이다."""
    now = request.app.state.clock.now()
    rows = {
        r.component: r
        for r in db.execute(select(SyncStatus)).scalars().all()
    }
    notices: list[dict] = []
    for component, label in USER_VISIBLE.items():
        row = rows.get(component)
        if row is None:
            continue
        notice = _notice_for(row, label, now)
        if notice is not None:
            notices.append(notice)
    runner = _runner_notice(db, now)
    if runner is not None:
        notices.append(runner)
    # 최초 실행 셋업이 안 끝났다는 사실도 사용자가 "지금 목록이 비어 있는 이유" 로 알아야
    # 한다(9-3). 셋업이 안 끝났을 때 로그인을 막지 않기로 한 대신, 조용히 빈 목록을 주지
    # 않는다 — 그 침묵이 이 과제가 없애려는 상태다. 판정은 셋업 체크리스트 한 곳에서만
    # 오고(app/setup/checklist.py) 여기서는 그 결과를 이 화면의 알림 모양으로 옮긴다.
    from app.setup.checklist import setup_notice

    setup = setup_notice(
        db,
        request.app.state.settings,
        secrets=request.app.state.secret_provider,
        cache=request.app.state.settings_cache,
        for_admin=user.role in CONSOLE_READ_ROLES,
    )
    if setup is not None:
        notices.append(setup)

    body: dict = {
        "notices": notices,
        "checked_at": now.isoformat(),
        # 배너가 몇 초마다 다시 물어볼지 서버가 정한다 — 프런트에 숫자를 박아 두면
        # 부하를 줄이려 할 때 배포가 두 번 필요하다.
        "poll_seconds": 120,
    }
    # UB-25 재검토: 처음엔 이 필드를 죽은 코드로 보고 지우려 했다 — 지금 프런트 배너
    # (frontend/src/app/Banners.jsx)는 실제로 notices/poll_seconds만 읽는다. 그런데
    # tests/integration/test_admin_backlog.py::test_operators_get_component_detail이
    # 운영자 이상에게 이 필드가 실제 내용과 함께 오는 것을 이미 의도적으로 검증하고
    # 있었다 — "소비자가 없다"가 아니라 "프런트가 아직 안 쓴다"였다. 되돌린다(BACKLOG
    # 재정정, 실측 없이 지웠으면 이미 있는 테스트를 깨뜨릴 뻔했다).
    if user.role in CONSOLE_READ_ROLES:
        from app.observability.service import sync_status_view

        body["components"] = [sync_status_view(rows[c]) for c in sorted(rows)]
    return body


__all__ = ["router", "LATE_AFTER_SECONDS", "STALLED_AFTER_SECONDS", "USER_VISIBLE"]
