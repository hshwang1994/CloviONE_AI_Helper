"""최초 실행 셋업 체크리스트 API (9-3, P3).

## 왜 `CONSOLE_WRITE_ROLES` 가 아니라 `SYSTEM_ADMIN_ONLY` 인가

`app/sysops/router.py` 가 시스템 설정에 대해 적어 둔 근거가 여기에도 **그대로** 적용된다.
`CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고, 이 제품의 `admin` 은 부서 범위로 좁혀질 수
있다(`admin_scope="dept"`). 부서 관리자는 자기 부서 사람을 관리하는 사람이지 이 서버의
Notion 토큰이 있는지, TLS 인증서가 며칠 남았는지, 러너가 등록됐는지를 다루는 사람이 아니다.
여기 담긴 것은 조직 단위가 아니라 **설치 한 벌 전체**의 상태라 범위라는 개념 자체가 없다.
그래서 범위가 없는 역할만 통과시킨다.

덧붙여 이 응답은 "이 설치에서 무엇이 아직 비어 있는가" 를 한 화면에 모아 준다. 그건 공격
표면 지도이기도 하다 - 읽기 전용이라고 해서 넓게 열 이유가 없다.

## 왜 쓰기가 없는가

이 화면은 무엇이 남았는지 **말할 뿐** 대신 설정해 주지 않는다. 실제 변경은 이미 각자의
자리(조직, 부서, 설정, 연동, 러너, Notion 연결)에 있고 거기에는 검증과 감사와 되돌리기가
붙어 있다. 여기에 지름길을 하나 더 내면 그 세 가지가 없는 두 번째 쓰기 경로가 생긴다.

"다 봤음" 을 저장하는 버튼도 없다. 한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게
아무 도움이 안 되고, 남은 항목은 계속 보여야 한다(과제 요구 3).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.authz import SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_roles
from app.setup.checklist import build_setup_checklist

router = APIRouter(
    prefix="/api/admin/setup",
    tags=["admin-setup"],
    dependencies=[Depends(require_roles(*SYSTEM_ADMIN_ONLY))],
)


@router.get("/checklist")
def setup_checklist(request: Request, db: Session = Depends(get_db)) -> dict:
    """남은 셋업 항목. 전부 끝나도 200 이고 목록은 그대로 온다."""
    return build_setup_checklist(
        db,
        request.app.state.settings,
        secrets=request.app.state.secret_provider,
        cache=request.app.state.settings_cache,
        gateway=getattr(request.app.state, "ai_gateway", None),
    )


__all__ = ["router"]
