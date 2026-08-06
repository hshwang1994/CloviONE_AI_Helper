"""Maintenance-mode request gate (spec §14.5).

When maintenance mode is on, regular users' new requests are blocked with a
503 notice; operator and above pass through so admins can keep operating.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.deps import SAFE_METHODS, get_current_user, get_db
from app.core.errors import AppError
from app.settings.service import is_maintenance_mode, maintenance_message
from app.users.models import ROLE_USER


class MaintenanceModeError(AppError):
    status_code = 503
    code = "maintenance_mode"
    default_message = "현재 시스템 점검 중입니다."


def block_if_maintenance(
    request: Request, user=Depends(get_current_user), db=Depends(get_db)
):
    """사용자 내용 쓰기를 막는다. operator+ 는 통과(spec §14.5).

    **읽기는 막지 않는다.** 그래서 `APIRouter(dependencies=[...])` 로 라우터 전체에 걸어도
    안전하다 — 라우트마다 손으로 붙이면 새 라우트에서 빠뜨리게 되고, 그게 정확히 이 게이트가
    쓰기 라우트 171개 중 **2개에만** 걸려 있던 이유다(둘 다 AI 채팅). 화면은 그동안
    "티켓 생성, 변경 등이 차단됩니다" 라고 말하고 있었다 — 하필 안 막히던 것을 예로 들면서.
    `core/deps.py` 의 임퍼소네이션 가드도 같은 관용(안전 메서드 조기 반환)을 쓴다.
    커버리지는 `tests/security/test_maintenance_coverage.py` 가 의존성 그래프로 지킨다.
    """
    if request.method in SAFE_METHODS:
        return
    if user.role != ROLE_USER:
        return
    cache = request.app.state.settings_cache
    if is_maintenance_mode(db, cache):
        raise MaintenanceModeError(maintenance_message(db, cache))
