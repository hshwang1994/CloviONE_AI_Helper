"""AI 도우미를 지금 쓸 수 있는가 — 화면(`/api/ai/status`)과 채팅 라우터가 같은 판정을 쓴다 (D-538).

  reason            뜻                                       화면
  no_permission     AI 사용 권한이 없다                       메뉴 · 서랍 단추를 숨긴다
  feature_off       AI 도우미 기능이 꺼져 있다                메뉴 · 서랍 단추를 숨긴다
  off               AI 사용(생성)이 꺼져 있다                 판 전체 「쓸 수 없음」 상태, 입력 막힘
  unconfigured      제공자 · 인증 · 모델이 비어 있다           같음
  blocked           연결이 막혔다(키 거부, 재로그인 필요)      같음

일시 장애는 막지 않는다 - 다음 호출이 다시 시도한다(차단기가 열린 30초만 런타임이 돌려보낸다). 「찾지 못함」은 여기 오지
않는다 - 그것은 도구가 0건을 돌려준 정상 답이다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

NOTICES = {
    "no_permission": "AI 도우미를 쓸 권한이 없습니다.",
    "feature_off": "AI 도우미가 비활성화되어 있습니다.",
    "off": "AI 사용이 비활성화되어 있어 지금은 답할 수 없습니다.",
    "unconfigured": "AI가 아직 연결되지 않았습니다.",
    "blocked": "AI 연결에 문제가 있어 지금은 답할 수 없습니다.",
}

MODE_TOOLS = "tools"
MODE_SEARCH_ONLY = "search_only"
MODE_UNKNOWN = "unknown"


def assistant_status(db: Session, *, runtime, user, settings_cache) -> dict:
    """``{available, reason, notice, mode, can_configure}``. 제공자에 붙지 않는다(저장된 상태만 읽는다)."""
    from app.ai.credentials import state as state_mod
    from app.authz import permissions as perms
    from app.authz.service import has_permission
    from app.core.feature_flags import db_flag
    from app.users.models import ROLE_SYSTEM_ADMIN

    info = runtime.status(db)
    if not has_permission(db, user, perms.AI_USE):
        reason = "no_permission"
    elif not db_flag(settings_cache, "chat_enabled"):
        reason = "feature_off"
    elif not info["generation_enabled"]:
        reason = "off"
    elif info["state"] == state_mod.STATE_UNCONFIGURED:
        reason = "unconfigured"
    elif info["blocking"]:
        reason = "blocked"
    else:
        reason = None
    tools = runtime.tools_capability(db)
    mode = {state_mod.TOOLS_OK: MODE_TOOLS, state_mod.TOOLS_UNSUPPORTED: MODE_SEARCH_ONLY}.get(tools, MODE_UNKNOWN)
    return {
        "available": reason is None,
        "reason": reason,
        "notice": NOTICES.get(reason) if reason else None,
        "mode": mode,
        # AI 연결 화면은 시스템 관리자만 연다 - 「AI 연결 열기」 링크를 줄 사람인가.
        "can_configure": getattr(user, "role", None) == ROLE_SYSTEM_ADMIN,
    }
