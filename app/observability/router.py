"""시스템 상태 — 사용자 화면 배너의 유일한 출처 (0033, PLAN Phase 6).

## 지금 여기서 나오는 것은 셋업 알림 하나다

예전에는 티켓·문서 미러가 늦으면 "지금 티켓 동기화가 늦습니다" 를 사용자에게 말했다.
그 미러가 없어졌다 — 티켓·문서·프로젝트의 정본이 이 서버다. 쓰는 코드가 사라진 뒤에도
판정만 남아 있으면 `sync_status` 의 마지막 성공 시각이 매일 조금씩 더 낡아져 **모든 화면에
영원히 붙는 critical 배너**가 된다. 실제로 그렇게 됐고(운영 실측으로 문서 3.8일·티켓
4.5시간), 그 배너는 정보가 아니라 거짓말이다. 그래서 미러 신선도 알림을 걷었다.

남은 `search`·`project_health` 행은 애초에 사용자 배너가 아니다 — 검색 인덱스가 늦은 것은
사용자가 할 수 있는 일도, 알아야 할 일도 아니다. 운영자 이상에게만 `components` 로 나간다.

## 사용자에게 말하지 않는 것

컴포넌트 이름·예외 메시지·스택·러너 URL 은 **내보내지 않는다**. 그건 운영자 화면의 몫이고,
일반 사용자에게는 무엇을 하라는 지시도 못 되면서 내부 구조만 노출한다. 그래서 응답이
역할에 따라 달라진다 — 운영자 이상이면 원인(`detail`)이 함께 온다.

## 폴링에 기록을 걸지 않는다

이 엔드포인트는 사용자 셸이 주기적으로 부른다. 그래서 **읽기만 한다** — `usage_events` 기록도,
카운터 증가도 없다(0026 규칙: 폴링 경로에 기록을 걸면 읽기가 쓰기가 된다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import CONSOLE_READ_ROLES
from app.core.deps import get_current_user, get_db
from app.observability.models import SyncStatus
from app.users.models import User

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """사용자 화면 상태 배너의 원본. 정상이면 `notices` 가 빈 배열이다."""
    now = request.app.state.clock.now()
    notices: list[dict] = []
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
        gateway=getattr(request.app.state, "ai_gateway", None),
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

        rows = {r.component: r for r in db.execute(select(SyncStatus)).scalars().all()}
        body["components"] = [sync_status_view(rows[c]) for c in sorted(rows)]
    return body


__all__ = ["router"]
