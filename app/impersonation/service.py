"""임퍼소네이션 시작·종료·조회 (0033, PLAN Phase 6).

## 규칙 세 가지 — 이 파일이 지키는 전부

1. **쓰기 금지.** 임퍼소네이션 세션으로는 어떤 상태도 바꿀 수 없다. 강제 지점은
   `app/core/deps.py::get_current_auth` 한 곳이다(모든 인증 라우트가 그곳을 지난다).
   여기 service 층은 "시작/종료"만 다룬다.
2. **감사 필수.** 시작과 종료 둘 다 `impersonation_sessions` 행 + `audit_logs` 줄을 남긴다.
   기록에 실패하면 시작 자체가 실패한다(기록 없는 임퍼소네이션은 존재하면 안 된다).
3. **권한을 넘어설 수 없다.** 자기보다 높은 역할은 흉내 낼 수 없고, 자기 범위 밖 사용자는
   403 이 아니라 **404** 다(`app/core/scope.py` 모듈 docstring — 존재 노출 방지).

## 왜 '대상의 세션'을 새로 만들지 않는가

대상 사용자로 로그인한 것처럼 새 세션을 발급하면, 그 세션은 대상 본인의 세션과 구분되지
않는다 — 즉 로그가 "대상이 했다"로 남고, 대상이 '내 다른 세션 로그아웃'을 눌러도 관리자
세션이 함께 끊긴다(혹은 안 끊긴다). 그래서 **관리자 자신의 세션 행에 표식만 붙인다**:
`impersonated_user_id` 가 있으면 그 요청은 대상의 눈으로 읽되, 행위자는 여전히 관리자다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, RateLimitedError
from app.core.scope import Scope, scope_allows_user
from app.impersonation.models import (
    END_MANUAL,
    ImpersonationSession,
)
from app.users.models import ROLE_SYSTEM_ADMIN, User, role_rank

# 임퍼소네이션 최대 지속 시간. 넘으면 다음 요청에서 자동 종료된다 — 관리자가 창을 닫고
# 잊어버린 세션이 8시간짜리 절대 만료까지 남의 화면을 열어 두는 상황을 막는다.
MAX_DURATION_SECONDS = 30 * 60

# ── 남용 방지: 짧은 시간에 서로 다른 대상을 훑어보는 패턴 (H3) ──────────────────────
#
# 값을 여기 상수로 뺀다(app/core/config.py 의 "매직 넘버를 이름 붙은 값으로" 관례를
# 따른다 — MAX_DURATION_SECONDS 도 같은 자리에 같은 방식으로 있다). Settings 클래스에
# 넣지 않은 이유: 이 파일이 이미 그 관례를 쓰고 있고, 이 상수들은 이 모듈의 판정
# 로직에서만 읽힌다(다른 라우터가 참조할 이유가 없다).
#
# 창(WINDOW) 안에서 **새로운(그 창에서 아직 안 본)** 대상이 이 개수를 넘으면 막는다.
# 이미 그 창 안에서 시작한 적 있는 대상을 다시 여는 것은 세지 않는다 — 지원 업무는
# 흔히 같은 계정을 여러 번 드나든다(문의 확인 → 종료 → 재확인). 반대로 짧은 시간에
# 서로 다른 여러 계정을 잇달아 여는 것은 지원 업무로는 드물고, 계정을 훑어보는
# 남용(또는 탈취된 관리자 계정의 정찰) 패턴에 해당한다.
IMPERSONATION_RATE_LIMIT_MAX_TARGETS = 3
IMPERSONATION_RATE_LIMIT_WINDOW_SECONDS = 10 * 60


def can_impersonate(actor: User, target: User) -> tuple[bool, str]:
    """(가능한가, 안 되는 이유). 이유는 그대로 사용자에게 보여도 되는 문장이다."""
    if actor.id == target.id:
        return False, "자기 자신은 임퍼소네이션할 수 없습니다."
    if not target.active or target.archived_at is not None:
        return False, "비활성 또는 보관된 계정은 임퍼소네이션할 수 없습니다."
    # 자기보다 강한 역할을 흉내 내면 읽기 전용이라도 권한 상승이다(그 역할만 보이는 화면을
    # 읽게 된다). system_admin 은 누구든 볼 수 있고, 그 밖에는 자기 순위 이하만 가능하다.
    if actor.role != ROLE_SYSTEM_ADMIN and role_rank(target.role) >= role_rank(actor.role):
        return False, "자신과 같거나 더 높은 권한의 계정은 임퍼소네이션할 수 없습니다."
    return True, ""


def _recent_distinct_targets(
    db: Session, *, actor_id: str, since: datetime
) -> dict[str, datetime]:
    """actor_id 가 since 이후 시작한 대리 보기의 **대상별 최초 시작 시각**.

    같은 대상을 여러 번 시작했으면 그중 가장 이른 시각만 남긴다 — 창이 언제 풀려
    새 대상을 다시 허용할지 계산하려면(재시도 대기 시간) 가장 오래된 진입 시각이
    필요하다. 종료 여부는 보지 않는다: 이미 끝난 세션도 '그 시간에 그 대상을
    열었다'는 사실 자체가 남용 판정의 재료이기 때문이다.
    """
    rows = db.execute(
        select(ImpersonationSession.target_user_id, ImpersonationSession.started_at)
        .where(
            ImpersonationSession.actor_user_id == actor_id,
            ImpersonationSession.started_at >= since,
        )
        .order_by(ImpersonationSession.started_at.asc())
    ).all()
    seen: dict[str, datetime] = {}
    for target_id, started_at in rows:
        seen.setdefault(target_id, started_at)
    return seen


def _check_distinct_target_rate_limit(
    db: Session, *, actor: User, target: User, now: datetime
) -> None:
    """새로운 대상이면, 창 안에서 이미 본 대상 수가 한도 미만일 때만 통과시킨다."""
    window_start = now - timedelta(seconds=IMPERSONATION_RATE_LIMIT_WINDOW_SECONDS)
    recent = _recent_distinct_targets(db, actor_id=actor.id, since=window_start)
    if target.id in recent or len(recent) < IMPERSONATION_RATE_LIMIT_MAX_TARGETS:
        return
    oldest = min(recent.values())
    retry_after = IMPERSONATION_RATE_LIMIT_WINDOW_SECONDS - (now - oldest).total_seconds()
    raise RateLimitedError(
        "짧은 시간 안에 너무 많은 사용자를 대리 보기했습니다. 잠시 후 다시 시도하세요.",
        retry_after_seconds=max(retry_after, 1.0),
    )


def active_for_session(db: Session, session_id: str) -> ImpersonationSession | None:
    return db.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.session_id == session_id,
            ImpersonationSession.ended_at.is_(None),
        )
    ).scalar_one_or_none()


def start(
    db: Session,
    *,
    actor: User,
    target: User,
    session: UserSession,
    scope: Scope,
    now: datetime,
    reason: str | None = None,
    client_ip: str | None = None,
) -> ImpersonationSession:
    """임퍼소네이션 시작. 실패는 전부 예외로 나간다(조용히 성공한 척하지 않는다)."""
    # 범위 밖은 존재하지 않는 것과 똑같이 404 — 남의 부서 id 를 찍어 보며 조직도를
    # 열거하는 경로를 막는다(app/core/scope.py 모듈 docstring).
    if not scope_allows_user(scope, target):
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    allowed, why = can_impersonate(actor, target)
    if not allowed:
        raise ForbiddenError(why)
    if session.impersonated_user_id:
        raise ConflictError("이미 임퍼소네이션 중입니다. 먼저 종료해 주세요.")
    # 남용 방지 (H3-a): 짧은 시간에 서로 다른 대상을 훑어보는 패턴을 막는다.
    # 스코프·권한 판정 뒤, 실제로 행을 만들기 전에 확인한다 — 통과 못 할 시도까지
    # 한도에 넣지 않는다(안 그러면 접근 불가 사용자에 대한 반복 시도로 정상적인
    # 임퍼소네이션이 막히는 결과가 된다).
    _check_distinct_target_rate_limit(db, actor=actor, target=target, now=now)

    row = ImpersonationSession(
        actor_user_id=actor.id,
        target_user_id=target.id,
        session_id=session.id,
        reason=(reason or "").strip()[:500] or None,
        client_ip=client_ip,
        started_at=now,
    )
    db.add(row)
    db.flush()
    session.impersonated_user_id = target.id
    session.impersonation_id = row.id
    db.flush()
    return row


def end(
    db: Session,
    *,
    session: UserSession,
    now: datetime,
    reason: str = END_MANUAL,
) -> ImpersonationSession | None:
    """임퍼소네이션 종료. 이미 끝나 있으면 None(멱등)."""
    row = None
    if session.impersonation_id:
        row = db.get(ImpersonationSession, session.impersonation_id)
    if row is None:
        row = active_for_session(db, session.id)
    session.impersonated_user_id = None
    session.impersonation_id = None
    if row is None or row.ended_at is not None:
        db.flush()
        return None
    row.ended_at = now
    row.ended_reason = reason
    db.flush()
    return row


def expired(row: ImpersonationSession, now: datetime) -> bool:
    return (now - row.started_at).total_seconds() > MAX_DURATION_SECONDS


def view(row: ImpersonationSession, names: dict[str, dict[str, str]] | None = None) -> dict:
    names = names or {}
    actor = names.get(row.actor_user_id, {})
    target = names.get(row.target_user_id, {})
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "actor_name": actor.get("display_name"),
        "actor_email": actor.get("email"),
        "target_user_id": row.target_user_id,
        "target_name": target.get("display_name"),
        "target_email": target.get("email"),
        "reason": row.reason,
        "client_ip": row.client_ip,
        "started_at": row.started_at.isoformat(),
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "ended_reason": row.ended_reason,
        "active": row.ended_at is None,
        "read_count": row.read_count,
        "blocked_write_count": row.blocked_write_count,
    }


def resolve_names(db: Session, ids) -> dict[str, dict[str, str]]:
    """id → {display_name, email}. 조인 대신 한 번의 IN 조회(저장소 관례)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(tuple(wanted)))
    ).all()
    return {r[0]: {"display_name": r[1], "email": r[2]} for r in rows}
