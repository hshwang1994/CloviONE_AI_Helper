"""공지 배너 API (0033, PLAN Phase 6).

두 개의 라우터가 한 파일에 있다:
  * `admin_router` — `/api/admin/announcements` : 관리자가 만들고 고치고 끈다.
  * `user_router`  — `/api/announcements`       : 로그인한 누구나 자기에게 보일 공지를 읽고 닫는다.

둘 다 쓰기가 있으므로 **둘 다** `require_csrf` 를 라우터에 건다.
`GET` 은 `require_csrf` 가 스스로 건너뛴다(SAFE_METHODS).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.announcements import service
from app.announcements.models import (
    AUDIENCE_ALL,
    LEVEL_INFO,
    Announcement,
)
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_current_user, get_db, require_csrf, require_roles
from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.users.models import ROLE_USER, User

admin_router = APIRouter(
    prefix="/api/admin/announcements",
    tags=["admin-announcements"],
    dependencies=[Depends(require_csrf)],
)

user_router = APIRouter(
    prefix="/api/announcements",
    tags=["announcements"],
    dependencies=[Depends(require_csrf)],
)


class AnnouncementRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    level: str = Field(default=LEVEL_INFO, max_length=16)
    audience: str = Field(default=AUDIENCE_ALL, max_length=16)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active: bool = True
    dismissible: bool = True
    link_url: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)


class AnnouncementPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    level: str | None = Field(default=None, max_length=16)
    audience: str | None = Field(default=None, max_length=16)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active: bool | None = None
    dismissible: bool | None = None
    link_url: str | None = Field(default=None, max_length=500)
    link_label: str | None = Field(default=None, max_length=80)


def _naive(value: datetime | None) -> datetime | None:
    """타임존이 붙어 오면 UTC 로 바꿔 naive 로 저장한다(저장소 전역 규약).

    ## 이미 저장된 행은 손대지 않기로 했다 (F14)

    예전에는 관리 화면의 폼이 오프셋 없는 `datetime-local` 벽시계("2026-08-10T09:00")를
    그대로 보냈다. 이 함수는 규약대로 그것을 UTC 로 읽었으므로, KST 09:00 을 뜻한 공지가
    실제로는 KST 18:00 에 떴다. 변환은 **경계(화면)** 에서 하도록 고쳤다
    (frontend/src/lib/format.js 의 `kstLocalToApi`/`apiToKstLocal`).

    남은 행을 마이그레이션으로 9시간 당기지 **않는다**:

    1. **구분할 수 없다.** 이 엔드포인트는 오프셋이 붙은 값도 늘 올바르게 처리해 왔다
       (CLI, 스크립트, API 직접 호출). 어떤 행이 망가진 폼을 거쳤는지 저장된 값만 보고는
       알 수 없다 — 일괄 -9시간은 **올바르게 들어온 행을 새로 망가뜨린다.**
    2. 우리가 고치려는 피해와 그 새 피해의 크기가 같다(배너가 9시간 어긋나 뜬다). 다만
       하나는 이미 있는 것이고 하나는 우리가 만드는 것이다.
    3. 공지는 수명이 짧은 운영 배너이고 건수가 적다(수십 건). 고친 편집 폼이 이제 **참값을
       KST 로** 보여 주므로, 지금 살아 있는 공지는 관리자가 열어 한 번 저장하면 바로 맞는다.

    같은 판단이 승인 위임(app/approvals/router.py `_naive_utc`)에도 적용된다 — 같은 폼
    경계를 공유하므로 같은 이유로 기존 행을 건드리지 않는다.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    from datetime import timezone

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _get_or_404(db: Session, row_id: str) -> Announcement:
    row = db.get(Announcement, row_id)
    if row is None:
        raise NotFoundError("공지를 찾을 수 없습니다.")
    return row


@admin_router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_announcements(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    active: bool | None = None,
    level: str | None = None,
) -> dict:
    stmt = select(Announcement)
    if active is not None:
        stmt = stmt.where(Announcement.active.is_(active))
    if level:
        stmt = stmt.where(Announcement.level == level)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Announcement.created_at.desc(), Announcement.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [service.view(r) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@admin_router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_announcement(
    request: Request,
    payload: AnnouncementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    service.validate(payload.level, payload.audience, payload.link_url)
    now = request.app.state.clock.now()
    row = Announcement(
        title=payload.title.strip(),
        body=payload.body or "",
        level=payload.level,
        audience=payload.audience,
        starts_at=_naive(payload.starts_at),
        ends_at=_naive(payload.ends_at),
        active=payload.active,
        dismissible=payload.dismissible,
        link_url=payload.link_url,
        link_label=payload.link_label,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    record_audit_from_request(
        request, db, action="announcement.create", object_type="announcement",
        object_id=row.id, after=service.view(row),
    )
    return service.view(row)


@admin_router.patch("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_announcement(
    request: Request,
    row_id: str,
    payload: AnnouncementPatch,
    db: Session = Depends(get_db),
) -> dict:
    row = _get_or_404(db, row_id)
    before = service.view(row)
    data = payload.model_dump(exclude_unset=True)
    # FN-40: title/body/level/audience 컬럼은 nullable=False 인데, 이 스키마는 부분 갱신을
    # 위해 넷 다 `str | None` 이다. Pydantic 은 Optional 필드의 None 값에 min_length 같은
    # 문자열 제약을 적용하지 않으므로, 클라이언트가 필드를 아예 안 보낸 것(exclude_unset 이
    # 걸러 준다)이 아니라 명시적으로 `null` 을 보내면 그대로 setattr 까지 내려가
    # IntegrityError(NOT NULL constraint) → 500 이 났다. POST 경로는 body 하나만
    # `payload.body or ""`(:152)로 이미 방어하고 있었다 - PATCH 는 넷 다 빠져 있었다.
    # body 는 POST 와 같은 규칙(빈 문자열이 유효한 값)으로 채우고, 나머지 셋은 빈 값이
    # 의미가 없으므로(제목 없는 공지·중요도 없는 공지는 말이 안 된다) 명확한 오류로 막는다.
    if "body" in data and data["body"] is None:
        data["body"] = ""
    for key, label in (("title", "제목"), ("level", "중요도"), ("audience", "대상")):
        if key in data and data[key] is None:
            raise ValidationAppError(f"{label}은(는) 비울 수 없습니다.")
    service.validate(
        data.get("level", row.level),
        data.get("audience", row.audience),
        # PATCH 는 부분 갱신이라 link_url 이 안 왔으면 기존 값을 검사한다. `exclude_unset`
        # 때문에 '안 보냄'과 'null 로 지움'이 구분되므로 sentinel 없이 get 으로 충분하다.
        data.get("link_url", row.link_url),
    )
    for key in ("title", "body", "level", "audience", "active", "dismissible", "link_url", "link_label"):
        if key in data:
            setattr(row, key, data[key])
    for key in ("starts_at", "ends_at"):
        if key in data:
            setattr(row, key, _naive(data[key]))
    row.updated_at = request.app.state.clock.now()
    db.flush()
    record_audit_from_request(
        request, db, action="announcement.update", object_type="announcement",
        object_id=row.id, before=before, after=service.view(row),
    )
    return service.view(row)


@admin_router.delete("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def delete_announcement(request: Request, row_id: str, db: Session = Depends(get_db)) -> dict:
    row = _get_or_404(db, row_id)
    before = service.view(row)
    db.delete(row)
    db.flush()
    record_audit_from_request(
        request, db, action="announcement.delete", object_type="announcement",
        object_id=row_id, before=before,
    )
    return {"ok": True}


# ── 사용자 쪽 ────────────────────────────────────────────────────────────────


@user_router.get("")
def my_announcements(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """지금 나에게 보여야 하는 공지. 닫은 것은 다시 나오지 않는다."""
    now = request.app.state.clock.now()
    items = service.active_for_user(
        db, user_id=user.id, is_admin_console=user.role != ROLE_USER, now=now
    )
    return {"items": items}


@user_router.post("/{row_id}/dismiss")
def dismiss_announcement(
    request: Request,
    row_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = _get_or_404(db, row_id)
    if not row.dismissible:
        # 닫을 수 없는 공지를 닫으려 하면 조용히 성공한 척하지 않는다 — 화면에서 버튼을
        # 숨겼더라도 서버가 규칙의 주인이다.
        from app.core.errors import ConflictError

        raise ConflictError("이 공지는 닫을 수 없습니다.")
    created = service.dismiss(
        db, announcement_id=row.id, user_id=user.id, now=request.app.state.clock.now()
    )
    return {"ok": True, "dismissed": created}
