"""홈 '오늘' 커맨드 센터 API (조회 전용).

GET /api/home/today — 로그인 사용자의 오늘 한 화면. 상태를 바꾸지 않으므로 CSRF 불필요,
역할 게이트 없이 인증만(모든 값이 세션 사용자 기준이라 자동으로 본인 것만 나온다).

핸들러는 동기 함수다(저장소 불변 §2: sync consistency). 안에서 하는 일은 로컬 SELECT
몇 번과 순수 집계뿐이라 스레드풀에서 짧게 끝난다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.home import service
from app.users.models import User

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("/today")
def today(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """오늘 마감·지연·진행 중 + 안 읽은 알림/채팅 + 스프린트 내 몫 + 최근 문서·게시판.

    티켓 소스가 죽어도 200 이다 — tickets 블록만 configured/ok 로 이유를 말하고 나머지는
    그대로 나온다(§17.4 장애 격리).
    """
    return service.build_today(
        db,
        request.app.state.outbound_client,
        request.app.state.settings,
        user,
        repo=request.app.state.repositories.tickets,
        now=request.app.state.clock.now(),
    )
