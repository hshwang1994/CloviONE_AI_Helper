"""Current-user profile endpoints (spec §13.6, §23.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.deps import AuthContext, get_current_auth, get_current_user, get_db
from app.users.models import User

router = APIRouter(tags=["profiles"])


@router.get("/api/me")
def me(auth: AuthContext = Depends(get_current_auth)):
    user = auth.user
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
            "title": user.title,
            "must_change_password": user.must_change_password,
        },
        "csrf_token": auth.session.csrf_token,
    }


@router.get("/api/profile")
def profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active_sessions = db.execute(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ).scalar_one()
    from app.notion_mapping.service import mapping_status

    return {
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "department": user.department,
        "title": user.title,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "active_session_count": active_sessions,
        "notion_mapping_status": mapping_status(db, user.id),
    }
