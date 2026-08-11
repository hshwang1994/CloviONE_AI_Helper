"""사용 이벤트 기록 + 동기화 상태 upsert (0026, PLAN Phase 4).

## 어디에 걸어도 되고 어디에 걸면 안 되는가 — 규칙

**걸어도 되는 곳(저빈도)**: 사람이 의도해서 하는, 세션당 몇 번 안 일어나는 행동.
로그인 성공, 티켓 생성, 문서 생성 요청 같은 것.

**절대 걸면 안 되는 곳**:
  * 채팅 전송(`app/team_chat`) — 이 앱에서 가장 뜨거운 쓰기 경로다. INSERT + `event_seq`
    UPDATE 로 SAVEPOINT 재시도까지 도는 곳에 INSERT 를 하나 더 얹는 것은 병목을 정확히
    가장 나쁜 자리에서 키우는 짓이다(계획 C9).
  * 폴링 경로(`/api/games/rooms` 3초, `/api/trash` 15초, `/api/notifications/unread-count`
    60초, 방 상태 1.2초) — 여기에 기록을 걸면 **읽기가 쓰기로 바뀐다**. ETag/304 로 아끼려던
    것을 그대로 되돌린다.

이 규칙은 `tests/unit/test_usage_events.py` 가 소스에서 직접 확인한다 — 뜨거운 모듈이 이
파일을 import 하면 테스트가 실패한다. 주석으로만 적어 두면 언젠가 누가 좋은 뜻으로 건다.

## 실패해도 요청을 죽이지 않는다

`record_usage` 는 예외를 밖으로 내보내지 않는다. 통계 한 줄을 못 남긴 것 때문에 사용자의
로그인이나 티켓 생성이 실패하면 안 된다 — 부가 기능이 본 기능보다 강해지는 전형적인 사고다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.observability.models import (
    SYNC_OK,
    SyncStatus,
    UsageEvent,
)

logger = logging.getLogger("app.observability")

# 이벤트 이름은 여기서만 만든다 — 문자열을 호출부에 흩어 두면 'auth.login' 과
# 'login' 이 같은 뜻으로 둘 다 쌓인다(집계가 조용히 반토막 난다).
EVENT_LOGIN = "auth.login"
EVENT_TICKET_CREATE = "ticket.create"
EVENT_DOCUMENT_GENERATE = "document.generate"
# app/quotas/service.py가 쓴다 — "여기서만 만든다"는 위 규칙대로 정본은 여기 하나다.
EVENT_AI_CALL = "ai.call"

# UB-25: 예전엔 이 집합이 어디서도 안 쓰여 "오타 누적 방지"라는 존재 이유가 이름뿐이었다
# (실제로 EVENT_AI_CALL이 quotas/service.py에 따로 정의돼 있었고 여기 목록엔 없었다 — 이
# 집합이 정말 강제됐다면 그 드리프트가 그 자리에서 바로 드러났을 것이다). record_usage()
# 안에서 검사한다.
KNOWN_EVENTS = frozenset({EVENT_LOGIN, EVENT_TICKET_CREATE, EVENT_DOCUMENT_GENERATE, EVENT_AI_CALL})


def record_usage(
    db: Session,
    *,
    event: str,
    user_id: str | None = None,
    org_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    meta: dict | None = None,
    now: datetime | None = None,
) -> UsageEvent | None:
    """사용 이벤트 한 줄. 실패해도 예외를 밖으로 내보내지 않는다(None 을 돌려준다).

    `db.commit()` 은 하지 않는다 — 부르는 쪽의 트랜잭션에 얹혀서, 본 작업이 롤백되면
    이 줄도 함께 사라지는 것이 맞다("실패한 티켓 생성"이 통계에 잡히면 안 된다).

    UB-18: `db.flush()` 가 실패하면(예: 저장 계층 문제) SQLAlchemy 세션은
    pending-rollback 상태가 된다 — `db.rollback()` 없이 그 세션으로 **다음 문장을 하나라도
    더** 실행하면(호출자의 나머지 로직, 또는 `get_db` 의 요청-끝 `db.commit()`) 전부
    `PendingRollbackError` 로 깨진다. "통계 한 줄 때문에 로그인·티켓 생성이 실패하면
    안 된다"는 이 함수의 존재 이유가 정확히 반대로 작동했었다 — 로그 실패가 본 작업까지
    끌고 내려갔다. `begin_nested()`(SAVEPOINT, `app/core/versioning.py` 등과 같은 패턴)로
    감싸면 실패해도 이 SAVEPOINT 만 롤백되고 호출자가 이미 세션에 올려 둔 다른 변경은
    그대로 남는다.
    """
    try:
        # UB-25: event 이름은 이 파일에서만 만든다는 규칙(위 모듈 docstring)을 이제 실제로
        # 강제한다 — 이 검사도 함수 전체를 감싸는 바깥 except에 잡히므로("실패해도 예외를
        # 밖으로 내보내지 않는다") 오타 하나가 호출자의 로그인·티켓 생성까지 끌고 내려가지
        # 않는다. 대신 로그에 남아 집계가 조용히 반토막 나는 것을 막는다.
        if event not in KNOWN_EVENTS:
            raise ValueError(f"알 수 없는 usage event: {event!r} (KNOWN_EVENTS에 없음)")
        row = UsageEvent(
            event=event,
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            meta_json=json.dumps(meta, ensure_ascii=False, sort_keys=True) if meta else None,
        )
        if org_id is not None:
            row.org_id = org_id
        if now is not None:
            row.created_at = now
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except Exception:
        logger.exception("usage event 기록 실패 (무시하고 계속한다): %s", event)
        return None


def upsert_sync_status(
    db: Session,
    component: str,
    *,
    status: str,
    now: datetime,
    item_count: int | None = None,
    truncated: bool | None = None,
    error: str | None = None,
    detail: dict | None = None,
) -> SyncStatus:
    """컴포넌트의 현재 동기화 상태를 갱신한다(없으면 만든다).

    `last_success_at` 은 status='ok' 일 때만 움직인다 — 실패해도 마지막 성공 시각이
    남아 있어야 배너가 "마지막으로 정상 동기화된 게 언제인지"를 말할 수 있다.
    실패 시 `item_count` 를 0으로 덮지 않는 이유도 같다(캐시는 여전히 그만큼 들고 있다).
    """
    row = db.get(SyncStatus, component)
    if row is None:
        row = SyncStatus(component=component)
        db.add(row)
    row.status = status
    row.last_run_at = now
    row.updated_at = now
    if status == SYNC_OK:
        row.last_success_at = now
    # 이번 회차가 할 말이 있으면 성공이든 실패든 그대로 나른다. 예전에는 status=='ok' 일 때
    # error 를 무조건 None 으로 덮어서, **성공했지만 경고가 있는 회차**(상한에 걸려 일부만
    # 받아온 truncated)가 미러에서 말을 잃었다 — 관리자 화면은 {status:"ok", error:null} 만
    # 보고 "정상"이라 읽었다. 할 말이 없을 때만(None) 옛 오류를 지운다.
    if error is not None:
        row.error = error[:2000]
    elif status == SYNC_OK:
        row.error = None
    if item_count is not None:
        row.item_count = item_count
    if truncated is not None:
        row.truncated = truncated
    if detail is not None:
        row.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    db.flush()
    return row


def sync_status_view(row: SyncStatus) -> dict:
    """운영자 이상에게 붙는 컴포넌트별 진단(app/observability/router.py::system_status).

    UB-25: `list_sync_status`(호출부 0, 삭제함)와 달리 이 함수는 실제로 쓰인다 —
    tests/integration/test_admin_backlog.py::test_operators_get_component_detail이
    운영자 이상 응답에 이 모양을 요구한다. `detail_json`은 의도적으로 안 뺀다(문제
    진단용 원시 상세라 일반 요약과 섞으면 오히려 읽기 어렵다 — 필요해지면 그때 추가).
    """
    return {
        "component": row.component,
        "status": row.status,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_success_at": (
            row.last_success_at.isoformat() if row.last_success_at else None
        ),
        "item_count": row.item_count,
        "truncated": row.truncated,
        "error": row.error,
    }


