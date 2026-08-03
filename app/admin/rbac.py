"""권한 매트릭스 조회 API (Phase 6 — 관리자 백로그).

**이 라우터는 계산을 하지 않는다.** 표 전체가 `app/core/authz.py::rbac_matrix()` 에서 나오고,
그 함수는 같은 파일의 그룹 상수만 읽는다. 여기서 역할을 한 줄이라도 다시 나열하는 순간
"규칙을 한 곳에서 고치면 전부 반영된다"가 깨진다 — authz.py 가 생긴 이유가 바로 그것이다.

읽기 전용이라 `CONSOLE_READ_ROLES` 다: 운영자와 감사자도 '내가 무엇을 할 수 있는지'를 볼 수
있어야 한다. 이 응답에는 어떤 사용자 데이터도 들어 있지 않다(규칙 표 그 자체다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.authz import CONSOLE_READ_ROLES, rbac_matrix
from app.core.deps import require_roles

router = APIRouter(
    prefix="/api/admin/rbac-matrix",
    tags=["admin-rbac"],
    dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))],
)


@router.get("")
def get_rbac_matrix() -> dict:
    return rbac_matrix()
