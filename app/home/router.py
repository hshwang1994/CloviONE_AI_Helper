"""홈 '오늘' 커맨드 센터 + 업무 대시보드 API (조회 전용).

GET /api/home/today          — 로그인 사용자의 오늘 한 화면.
GET /api/home/work-dashboard — /dashboard 화면의 '내 업무' 구역(프로젝트·티켓·처리량).

상태를 바꾸지 않으므로 CSRF 불필요, 역할 게이트도 없다. 개인 값(티켓·알림)은 세션
사용자 기준이라 자동으로 본인 것만 나오고, 팀 값(프로젝트·마일스톤)은 **범위**가 좁힌다 —
역할이 아니라 범위가 답할 질문이기 때문이다(app/core/scope.py: 두 축은 직교한다).

핸들러는 동기 함수다(저장소 불변 §2: sync consistency). 안에서 하는 일은 로컬 SELECT
몇 번과 순수 집계뿐이라 스레드풀에서 짧게 끝난다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, get_principal
from app.core.scope import Principal
from app.home import service, work
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


@router.get("/work-dashboard")
def work_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    principal: Principal = Depends(get_principal),
):
    """차질 프로젝트 · 지연 마일스톤 · 내 미완료 · 이번 주 마감 · 최근 완료 추이.

    범위 판정은 `principal.scope` 하나가 `app/projects/repository.py::list_in_scope` 로
    들어간다 — 프로젝트 목록 화면과 **같은 조건**이다. 여기서 조건을 한 번 더 적으면 두
    벌이 되고, 갈라진 쪽이 "목록에는 없는데 대시보드에는 뜬다" 로 새어 나온다.

    '오늘'과 '이번 주'는 KST 달력일 기준이다(clock 은 naive UTC 를 준다). UTC 로 자르면
    월요일 오전 9시 이전에 여는 사람이 지난 주 화면을 본다.
    """
    return work.build_work_dashboard(
        db,
        request.app.state.outbound_client,
        request.app.state.settings,
        user,
        principal,
        repo=request.app.state.repositories.tickets,
        now=request.app.state.clock.now(),
    )
