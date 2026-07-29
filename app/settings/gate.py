"""Maintenance-mode request gate (spec §14.5).

When maintenance mode is on, regular users' new requests are blocked with a
503 notice; operator and above pass through so admins can keep operating.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.deps import get_current_user, get_db
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
    """Attach to user-facing write endpoints. operator+ bypass (spec §14.5)."""
    if user.role != ROLE_USER:
        return
    cache = request.app.state.settings_cache
    if is_maintenance_mode(db, cache):
        raise MaintenanceModeError(maintenance_message(db, cache))
