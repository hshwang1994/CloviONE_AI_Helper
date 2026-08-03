"""프로필 셀프서비스 서비스 층 — 설정·아바타·세션·저장된 뷰.

라우터가 얇게 유지되도록 여기서 조회·검증·상태 전이를 한다. 순수 규칙(방해금지 판정,
알림 유형 검증)은 `prefs.py` 에 있고 이 파일은 DB 와 그 규칙을 잇기만 한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.profiles import prefs
from app.profiles.models import SavedView, UserPreference

# 저장된 뷰의 상한. 목록이 길어지면 고르는 일 자체가 필터링이 되어 버린다.
MAX_SAVED_VIEWS_PER_SCREEN = 20
MAX_QUERY_LENGTH = 1024

# 방해금지를 한 번에 걸 수 있는 최대 시간(분). 그보다 길게 걸고 싶으면 조용시간을 쓴다 —
# '무한 조용'을 실수로 눌러 두고 잊어버리는 것이 이 기능의 가장 흔한 실패다.
MAX_DND_MINUTES = 24 * 60


def get_preference(db: Session, user_id: str) -> UserPreference | None:
    return db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()


def ensure_preference(db: Session, user_id: str, *, now: datetime) -> UserPreference:
    """행이 없으면 만든다. 마이그레이션 백필 대신 첫 사용 시점에 만드는 이유는
    0032 docstring 참조 — 없어도 되는 값이라 없는 상태가 정상이다."""
    row = get_preference(db, user_id)
    if row is not None:
        return row
    row = UserPreference(user_id=user_id, created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    return row


def quiet_state(pref: UserPreference | None, *, now: datetime, timezone_name: str):
    """지금 배지를 조용히 할지. 설정이 없으면(=행이 없으면) 조용하지 않다."""
    if pref is None:
        return prefs.QuietState(quiet=False)
    return prefs.evaluate_quiet(
        dnd_enabled=bool(pref.dnd_enabled),
        dnd_until=pref.dnd_until,
        quiet_hours_enabled=bool(pref.quiet_hours_enabled),
        quiet_start=pref.quiet_start,
        quiet_end=pref.quiet_end,
        now=now,
        timezone_name=timezone_name,
    )


def clear_expired_dnd(db: Session, pref: UserPreference | None, state, *, now: datetime) -> None:
    """`dnd_until` 이 지났으면 상태를 실제로 정리한다.

    판정만 하고 두면 화면이 "방해금지 켜짐(만료됨)" 같은 모순된 상태를 계속 그린다 —
    사용자가 껐는데도 켜져 보이는 것과 같은 혼란이다.
    """
    if pref is None or not state.expired:
        return
    pref.dnd_enabled = False
    pref.dnd_until = None
    pref.updated_at = now
    db.flush()


def preference_view(
    pref: UserPreference | None, *, now: datetime, timezone_name: str, avatar_url: str | None
) -> dict:
    """설정 화면과 셸이 함께 쓰는 응답 모양. 설정이 없어도 **기본값으로 온전한 모양**을 낸다."""
    state = quiet_state(pref, now=now, timezone_name=timezone_name)
    muted = prefs.parse_muted(pref.muted_types if pref else "")
    seen_version = pref.tour_seen_version if pref else 0
    return {
        "avatar": {
            "url": avatar_url,
            "updated_at": (
                pref.avatar_updated_at.isoformat()
                if pref and pref.avatar_updated_at else None
            ),
        },
        "notifications": {
            "muted_types": muted,
            "catalog": prefs.notification_type_catalog(),
            "unmutable": sorted(prefs.UNMUTABLE_TYPES),
        },
        "dnd": {
            # 사용자가 켜 둔 상태(설정) — 지금 조용한지(quiet)와 다르다. 조용시간은
            # 켜 두었어도 낮에는 조용하지 않다.
            "enabled": bool(pref.dnd_enabled) if pref else False,
            "until": pref.dnd_until.isoformat() if pref and pref.dnd_until else None,
            "quiet_hours_enabled": bool(pref.quiet_hours_enabled) if pref else False,
            "quiet_start": pref.quiet_start if pref else "22:00",
            "quiet_end": pref.quiet_end if pref else "08:00",
            "quiet_now": state.quiet,
            "reason": state.reason,
            "max_minutes": MAX_DND_MINUTES,
        },
        "tour": {
            "version": prefs.TOUR_VERSION,
            "seen_version": seen_version,
            # 서버가 판정한다 — 브라우저 저장소에 두면 다른 PC 에서 다시 뜨고,
            # 시크릿 창에서도 다시 뜬다.
            "show": seen_version < prefs.TOUR_VERSION,
            "skipped": bool(pref.tour_skipped) if pref else False,
            "completed_at": (
                pref.tour_completed_at.isoformat()
                if pref and pref.tour_completed_at else None
            ),
        },
    }


def apply_preference_changes(
    db: Session, pref: UserPreference, changes: dict, *, now: datetime
) -> dict:
    """부분 갱신. 준 키만 바꾼다(PATCH 의미). 반환값은 감사 로그에 남길 after 스냅숏."""
    after: dict = {}

    if "muted_types" in changes and changes["muted_types"] is not None:
        valid, rejected = prefs.validate_muted(changes["muted_types"])
        if rejected:
            raise ValidationAppError(
                "알 수 없는 알림 유형입니다: " + ", ".join(sorted(rejected))
            )
        pref.muted_types = prefs.serialize_muted(valid)
        after["muted_types"] = valid

    if "dnd_enabled" in changes and changes["dnd_enabled"] is not None:
        pref.dnd_enabled = bool(changes["dnd_enabled"])
        after["dnd_enabled"] = pref.dnd_enabled
        if not pref.dnd_enabled:
            pref.dnd_until = None

    if "dnd_minutes" in changes and changes["dnd_minutes"] is not None:
        minutes = int(changes["dnd_minutes"])
        if minutes <= 0:
            pref.dnd_until = None
        elif minutes > MAX_DND_MINUTES:
            raise ValidationAppError(
                f"방해금지는 한 번에 최대 {MAX_DND_MINUTES // 60}시간까지 걸 수 있습니다."
            )
        else:
            from datetime import timedelta

            pref.dnd_until = now + timedelta(minutes=minutes)
        after["dnd_until"] = pref.dnd_until.isoformat() if pref.dnd_until else None

    if "quiet_hours_enabled" in changes and changes["quiet_hours_enabled"] is not None:
        pref.quiet_hours_enabled = bool(changes["quiet_hours_enabled"])
        after["quiet_hours_enabled"] = pref.quiet_hours_enabled

    for key in ("quiet_start", "quiet_end"):
        value = changes.get(key)
        if value is None:
            continue
        if prefs.parse_hhmm(value) is None:
            raise ValidationAppError("시간은 'HH:MM' 형식이어야 합니다(예: 22:00).")
        setattr(pref, key, value)
        after[key] = value

    if pref.quiet_hours_enabled and pref.quiet_start == pref.quiet_end:
        # 길이 0 창을 켜 두면 화면은 '조용시간 켜짐'인데 실제로는 한 번도 조용하지 않다.
        raise ValidationAppError("조용시간의 시작과 종료가 같습니다. 다른 시각을 고르세요.")

    pref.updated_at = now
    db.flush()
    return after


def mark_tour_seen(
    db: Session, pref: UserPreference, *, skipped: bool, now: datetime
) -> None:
    """투어를 끝냈거나 건너뛰었다. 둘 다 '다시 안 뜬다'로 귀결된다.

    건너뛴 사람에게 다시 뜨면 그 사람은 두 번째로 건너뛰고, 세 번째부터는 화면을 신뢰하지
    않게 된다 — 그래서 두 경로 모두 같은 버전을 저장한다.
    """
    pref.tour_seen_version = prefs.TOUR_VERSION
    pref.tour_skipped = bool(skipped)
    pref.tour_completed_at = now
    pref.updated_at = now
    db.flush()


def reset_tour(db: Session, pref: UserPreference, *, now: datetime) -> None:
    """사용자가 스스로 '둘러보기 다시 보기'를 골랐을 때. 서버가 지운 것이 아니다."""
    pref.tour_seen_version = 0
    pref.tour_skipped = False
    pref.tour_completed_at = None
    pref.updated_at = now
    db.flush()


# ── 세션 ─────────────────────────────────────────────────────────────────────

def list_sessions(db: Session, user_id: str, *, current_session_id: str) -> list[dict]:
    """내 살아 있는 세션 목록. 토큰 해시는 절대 나가지 않는다.

    '현재 세션'을 표시하는 것이 이 화면의 핵심이다 — 어느 줄이 지금 보고 있는 창인지
    모르면 사용자는 무서워서 아무것도 못 끊는다.
    """
    rows = (
        db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc())
        ).scalars().all()
    )
    return [
        {
            "id": row.id,
            "current": row.id == current_session_id,
            "created_at": row.created_at.isoformat(),
            "last_seen_at": row.last_seen_at.isoformat(),
            "expires_at": row.expires_at.isoformat(),
            "client_ip": row.client_ip,
            "user_agent": row.user_agent,
        }
        for row in rows
    ]


def get_own_session(db: Session, user_id: str, session_id: str) -> UserSession:
    """내 세션 한 건. 남의 세션 id 를 넣으면 **404**다(403 이면 존재가 드러난다)."""
    row = db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("세션을 찾을 수 없습니다.")
    return row


# ── 저장된 뷰 ─────────────────────────────────────────────────────────────────

def normalize_query(raw: str | None) -> str:
    """저장할 쿼리 문자열 정리. 앞의 '?' 를 떼고 길이를 제한한다.

    값을 해석하지 않는 것이 이 설계의 핵심이다 — 화면의 필터 정의가 바뀌어도 저장된 뷰를
    마이그레이션할 필요가 없다(0032 docstring). 대신 길이만 막는다.
    """
    query = (raw or "").strip()
    if query.startswith("?"):
        query = query[1:]
    if len(query) > MAX_QUERY_LENGTH:
        raise ValidationAppError("필터가 너무 깁니다. 조건을 줄여 주세요.")
    return query


def normalize_name(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        raise ValidationAppError("뷰 이름을 입력하세요.")
    if len(name) > 80:
        raise ValidationAppError("뷰 이름은 80자까지입니다.")
    return name


def normalize_screen_key(raw: str | None) -> str:
    key = (raw or "").strip()
    if not key or len(key) > 64:
        raise ValidationAppError("화면 키가 올바르지 않습니다.")
    return key


def list_views(db: Session, user_id: str, *, screen_key: str | None = None) -> list[SavedView]:
    stmt = select(SavedView).where(SavedView.user_id == user_id)
    if screen_key:
        stmt = stmt.where(SavedView.screen_key == screen_key)
    return list(
        db.execute(stmt.order_by(SavedView.screen_key, SavedView.name)).scalars().all()
    )


def view_of(row: SavedView) -> dict:
    return {
        "id": row.id,
        "screen_key": row.screen_key,
        "name": row.name,
        "query": row.query,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def create_view(
    db: Session, user_id: str, *, screen_key: str, name: str, query: str,
    overwrite: bool = False, now: datetime,
) -> SavedView:
    screen_key = normalize_screen_key(screen_key)
    name = normalize_name(name)
    query = normalize_query(query)

    existing = db.execute(
        select(SavedView).where(
            SavedView.user_id == user_id,
            SavedView.screen_key == screen_key,
            SavedView.name == name,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not overwrite:
            # 조용히 덮어쓰지 않는다 — 같은 이름을 다시 쓴 사람이 '덮어쓰기'를 의도했는지
            # '새로 만들기'를 의도했는지는 화면이 물어봐야 알 수 있다.
            raise ConflictError("같은 이름의 뷰가 이미 있습니다. 덮어쓸까요?")
        existing.query = query
        existing.updated_at = now
        db.flush()
        return existing

    count = len(list_views(db, user_id, screen_key=screen_key))
    if count >= MAX_SAVED_VIEWS_PER_SCREEN:
        raise ValidationAppError(
            f"한 화면에 저장할 수 있는 뷰는 {MAX_SAVED_VIEWS_PER_SCREEN}개까지입니다."
        )

    row = SavedView(
        user_id=user_id, screen_key=screen_key, name=name, query=query,
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def delete_view(db: Session, user_id: str, view_id: str) -> None:
    row = db.execute(
        select(SavedView).where(SavedView.id == view_id, SavedView.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("저장된 뷰를 찾을 수 없습니다.")
    db.delete(row)
    db.flush()
