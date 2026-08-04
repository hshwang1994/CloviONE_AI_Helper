"""Current-user profile endpoints (spec §13.6, §23.2) + 프로필 셀프서비스(계획서 Phase 6).

이 라우터의 모든 경로는 **세션 사용자 본인**의 것만 읽고 쓴다. 대상 id 를 받는 경로가
아바타 서빙 하나뿐이고 그것도 조회 전용이라, 스코프 필터가 필요한 표면이 없다.

`dependencies=[Depends(require_csrf)]` 를 라우터에 건다 — 안전 메서드(GET/HEAD/OPTIONS)는
require_csrf 가 즉시 통과시키므로 기존 조회 경로는 그대로이고, 앞으로 이 파일에 추가되는
쓰기 경로는 한 줄도 잊지 않고 보호된다(tests/security/test_csrf_coverage.py 가 이걸 고정한다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core import uploads
from app.core.audit import record_audit_from_request
from app.core.deps import (
    AuthContext,
    get_current_auth,
    get_current_user,
    get_db,
    require_csrf,
)
from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import MAX_PAGE_SIZE, PageParams
from app.profiles import activity as activity_mod
from app.profiles import service, stats
from app.profiles.schemas import PreferenceUpdate, SavedViewCreate, TourUpdate
from app.users.models import User

router = APIRouter(tags=["profiles"], dependencies=[Depends(require_csrf)])


def _avatar_url(pref, user_id: str) -> str | None:
    """아바타 URL. 변경 시각을 지문으로 붙여 브라우저 캐시가 옛 사진을 붙잡지 않게 한다.

    지문이 없으면 사진을 바꿔도 `private, max-age=300` 때문에 5분 동안 옛 사진이 보이고,
    사용자는 업로드가 실패한 줄 안다.
    """
    if pref is None or not pref.avatar_stored_name:
        return None
    stamp = int(pref.avatar_updated_at.timestamp()) if pref.avatar_updated_at else 0
    return f"/api/profile/avatar/{user_id}?v={stamp}"


@router.get("/api/me")
def me(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    user = auth.user
    pref = service.get_preference(db, user.id)
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
            "title": user.title,
            "must_change_password": user.must_change_password,
            # 셸(상단바 아바타)이 이 한 필드 때문에 별도 요청을 하지 않게 여기 싣는다.
            "avatar_url": _avatar_url(pref, user.id),
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

    pref = service.get_preference(db, user.id)
    return {
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "department": user.department,
        "title": user.title,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "active_session_count": active_sessions,
        "notion_mapping_status": mapping_status(db, user.id),
        "avatar_url": _avatar_url(pref, user.id),
    }


# ── 설정(알림·방해금지·투어) ─────────────────────────────────────────────────

@router.get("/api/me/preferences")
def get_preferences(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """내 설정 한 벌. 행이 없어도 기본값으로 **온전한 모양**을 돌려준다(생성하지 않는다).

    조회가 행을 만들면 한 번도 설정을 만진 적 없는 사용자가 화면을 여는 것만으로 행이
    생겨, '기본값을 쓰는 사람'과 '기본값을 골라 저장한 사람'을 구분할 수 없게 된다.
    """
    pref = service.get_preference(db, user.id)
    now = request.app.state.clock.now()
    tz = request.app.state.settings.timezone
    state = service.quiet_state(pref, now=now, timezone_name=tz)
    service.clear_expired_dnd(db, pref, state, now=now)
    return service.preference_view(
        pref, now=now, timezone_name=tz, avatar_url=_avatar_url(pref, user.id)
    )


@router.patch("/api/me/preferences")
def update_preferences(
    request: Request,
    payload: PreferenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = request.app.state.clock.now()
    tz = request.app.state.settings.timezone
    pref = service.ensure_preference(db, user.id, now=now)
    after = service.apply_preference_changes(
        db, pref, payload.model_dump(exclude_unset=True), now=now
    )
    # 설정 변경은 내 활동 피드에 남을 사건이다(activity.ACTION_SENTENCES 참조).
    record_audit_from_request(
        request, db, action="profile.preferences.update", object_type="user",
        object_id=user.id, after=after,
    )
    return service.preference_view(
        pref, now=now, timezone_name=tz, avatar_url=_avatar_url(pref, user.id)
    )


@router.post("/api/me/tour")
def update_tour(
    request: Request,
    payload: TourUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """투어를 끝냈다/건너뛰었다/다시 보겠다.

    **건너뛰기도 '봤다'로 기록한다.** 건너뛴 사람에게 다시 뜨면 그 사람은 두 번째로
    건너뛰고, 그 뒤로는 화면이 하는 말을 믿지 않게 된다.
    """
    action = (payload.action or "").strip()
    if action not in {"complete", "skip", "reset"}:
        raise ValidationAppError("action 은 complete, skip, reset 중 하나여야 합니다.")
    now = request.app.state.clock.now()
    pref = service.ensure_preference(db, user.id, now=now)
    if action == "reset":
        service.reset_tour(db, pref, now=now)
    else:
        service.mark_tour_seen(db, pref, skipped=(action == "skip"), now=now)
    return service.preference_view(
        pref, now=now, timezone_name=request.app.state.settings.timezone,
        avatar_url=_avatar_url(pref, user.id),
    )


# ── 아바타 ───────────────────────────────────────────────────────────────────

@router.post("/api/me/avatar")
def upload_avatar(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """프로필 사진 교체. 형식 판정은 **매직바이트**가 한다(app/core/uploads.py).

    새 업로드 경로를 만들지 않고 기존 네임스페이스 방식을 그대로 쓴다 — 크기 상한,
    traversal 가드, 서버 생성 저장명, 실행 불가 서빙이 이미 그 안에 있다.
    """
    # sync 핸들러에서는 UploadFile 의 내부 파일 객체를 직접 읽는다(await 불필요, 불변 §1).
    content = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    stored_name, media_type, size, _display = uploads.save_upload(
        request.app.state.settings.data_dir,
        user.id,
        filename=file.filename or "avatar",
        content=content,
        namespace=uploads.NS_AVATAR,
        # 프로필 사진에 PDF 를 허용할 이유가 없다 — 좁은 쪽이 항상 옳다.
        allowed_media_types=uploads.IMAGE_MEDIA_TYPES,
    )
    now = request.app.state.clock.now()
    pref = service.ensure_preference(db, user.id, now=now)
    old_name = pref.avatar_stored_name
    pref.avatar_stored_name = stored_name
    pref.avatar_media_type = media_type
    pref.avatar_updated_at = now
    pref.updated_at = now
    db.flush()
    # 예전 파일은 지운다. 남겨 두면 계정 하나가 업로드 횟수만큼 디스크를 먹고, 그 파일들은
    # 어디에서도 참조되지 않아 다시 찾을 방법도 없다.
    _unlink_avatar(request, user.id, old_name)
    record_audit_from_request(
        request, db, action="profile.avatar.update", object_type="user",
        object_id=user.id, after={"media_type": media_type, "size_bytes": size},
    )
    return {"ok": True, "avatar_url": _avatar_url(pref, user.id)}


@router.delete("/api/me/avatar")
def delete_avatar(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = request.app.state.clock.now()
    pref = service.get_preference(db, user.id)
    if pref is None or not pref.avatar_stored_name:
        # 이미 없는 것을 지우는 것은 성공이다(멱등) — 404 로 만들면 두 번 누른 사용자가
        # 있지도 않은 오류를 본다.
        return {"ok": True, "avatar_url": None}
    old_name = pref.avatar_stored_name
    pref.avatar_stored_name = None
    pref.avatar_media_type = None
    pref.avatar_updated_at = now
    pref.updated_at = now
    db.flush()
    _unlink_avatar(request, user.id, old_name)
    record_audit_from_request(
        request, db, action="profile.avatar.delete", object_type="user", object_id=user.id,
    )
    return {"ok": True, "avatar_url": None}


def _unlink_avatar(request: Request, user_id: str, stored_name: str | None) -> None:
    """옛 아바타 파일 삭제. 실패해도 요청을 깨뜨리지 않는다 — 사진은 이미 바뀌었고,
    남은 파일 하나 때문에 사용자에게 오류를 보일 이유가 없다."""
    if not stored_name:
        return
    path = uploads.attachment_path(
        request.app.state.settings.data_dir, user_id, stored_name,
        namespace=uploads.NS_AVATAR,
    )
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


@router.get("/api/profile/avatar/{user_id}")
def serve_avatar(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    _me: User = Depends(get_current_user),
):
    """로그인한 사람에게 그 계정의 프로필 사진을 준다.

    범위가 '전 직원'인 이유: 표시 이름·부서는 이미 사용자 명부(`/api/team-chat/directory`)와
    게시판·채팅에 전사 공개다. 사진만 좁히면 목록에서 이름 옆 사진이 뚫린 채로 보인다.
    사진이 없거나 계정이 보관됐으면 **404** 다(403 이면 계정 존재가 드러난다).
    """
    target = db.get(User, user_id)
    if target is None or target.archived_at is not None:
        raise NotFoundError("프로필 사진을 찾을 수 없습니다.")
    pref = service.get_preference(db, user_id)
    if pref is None or not pref.avatar_stored_name:
        raise NotFoundError("프로필 사진을 찾을 수 없습니다.")
    path = uploads.attachment_path(
        request.app.state.settings.data_dir, user_id, pref.avatar_stored_name,
        namespace=uploads.NS_AVATAR,
    )
    if path is None:
        raise NotFoundError("프로필 사진 파일을 찾을 수 없습니다.")
    # nosniff + inline. 서버가 판정·저장한 media_type 만 신뢰한다. 실행 불가.
    return FileResponse(
        str(path),
        media_type=pref.avatar_media_type or "application/octet-stream",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


# ── 내 세션 (보안) ───────────────────────────────────────────────────────────

@router.get("/api/me/sessions")
def my_sessions(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    return {"items": service.list_sessions(db, auth.user.id, current_session_id=auth.session.id)}


@router.post("/api/me/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """지금 이 세션만 남기고 내 나머지 세션을 전부 끊는다.

    **현재 세션을 남기는 것이 계약이다.** 전부 끊으면 누른 사람 자신이 즉시 튕겨나가고,
    그러면 '공용 PC 에 로그인해 두고 온 것 같다'는 상황에서 아무도 이 버튼을 못 누른다.
    끊긴 세션은 다음 요청에서 401 이 된다(SessionService.validate 가 revoked_at 을 본다).
    """
    count = request.app.state.session_service.revoke_all_for_user(
        db, auth.user.id, except_session_id=auth.session.id
    )
    record_audit_from_request(
        request, db, action="profile.sessions.revoke_others", object_type="session",
        object_id=auth.session.id, after={"revoked_count": count},
    )
    return {"ok": True, "revoked_count": count}


@router.delete("/api/me/sessions/{session_id}")
def revoke_one_session(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    """내 세션 한 건만 끊는다. 현재 세션은 여기서 끊을 수 없다 — 그건 로그아웃이고,
    이미 그 이름의 경로(`POST /logout`)가 쿠키 정리까지 함께 한다."""
    if session_id == auth.session.id:
        raise ValidationAppError(
            "지금 쓰고 있는 세션은 여기서 끊을 수 없습니다. 로그아웃을 사용하세요."
        )
    row = service.get_own_session(db, auth.user.id, session_id)
    request.app.state.session_service.revoke(db, row)
    db.flush()
    record_audit_from_request(
        request, db, action="profile.sessions.revoke", object_type="session",
        object_id=session_id,
    )
    return {"ok": True}


# ── 내 업무량 · 완료 통계 ────────────────────────────────────────────────────

@router.get("/api/me/stats")
def my_stats(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    months: int = Query(default=stats.DEFAULT_MONTHS, ge=1, le=24),
    weeks: int = Query(default=stats.DEFAULT_WEEKS, ge=1, le=12),
):
    """내 티켓 기준 업무량·완료 통계.

    티켓은 **저장소 seam 으로만** 읽는다(`app.state.repositories.tickets`). 홈이 쓰는
    로더를 그대로 재사용해 '내 티켓'의 정의(매핑·휴지통 제외)가 두 화면에서 갈라지지
    않게 한다. 소스가 죽어도 200 이고 `source.configured/ok/mapped` 로 이유를 말한다(§17.4).

    소스 상태를 `source` 아래로 **접어서** 싣는다. 최상위에 펼치면 그 블록의 `ok`(소스가
    살아 있는가)가 응답의 `ok`(요청이 처리됐는가)와 같은 이름으로 충돌해, 소스가 죽었을
    뿐인데 화면이 요청 자체가 실패한 줄 안다 — 실제로 그렇게 만들었다가 테스트에서 잡았다.
    """
    from app.home.service import load_my_tickets, local_today

    settings = request.app.state.settings
    now = request.app.state.clock.now()
    today = local_today(settings, now).isoformat()
    state = load_my_tickets(
        db, request.app.state.outbound_client, settings, user,
        repo=request.app.state.repositories.tickets,
    )
    tickets = state["tickets"]
    body = {
        "ok": True,
        "source": {k: v for k, v in state.items() if k != "tickets"},
        **stats.build_stats(tickets, today=today, months=months, weeks=weeks),
    }
    from app.tickets.service import sync_indicator

    sync = sync_indicator(db, repo=request.app.state.repositories.tickets)
    return {**body, "sync": sync} if sync else body


# ── 내 활동 피드 ─────────────────────────────────────────────────────────────

@router.get("/api/me/activity")
def my_activity(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: PageParams = Depends(),
    kind: str | None = Query(
        default=None,
        description="did(내가 한 일), happened(나에게 일어난 일), 비우면 전부",
    ),
):
    if kind not in (None, "", activity_mod.KIND_DID, activity_mod.KIND_HAPPENED):
        raise ValidationAppError("kind 는 did 또는 happened 여야 합니다.")
    result = activity_mod.build_feed(
        db, user.id, kind=kind, offset=page.offset, limit=min(page.page_size, MAX_PAGE_SIZE)
    )
    return {
        "items": result["items"],
        "total": result["total"],
        "page": page.page,
        "page_size": page.page_size,
    }


# ── 저장된 뷰 ────────────────────────────────────────────────────────────────

@router.get("/api/me/views")
def list_saved_views(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    screen_key: str | None = Query(default=None, max_length=64),
):
    rows = service.list_views(db, user.id, screen_key=screen_key)
    return {"items": [service.view_of(r) for r in rows]}


@router.post("/api/me/views")
def create_saved_view(
    request: Request,
    payload: SavedViewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = service.create_view(
        db, user.id,
        screen_key=payload.screen_key, name=payload.name, query=payload.query,
        overwrite=payload.overwrite, now=request.app.state.clock.now(),
    )
    return {"view": service.view_of(row)}


@router.delete("/api/me/views/{view_id}")
def delete_saved_view(
    view_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service.delete_view(db, user.id, view_id)
    return {"ok": True}
