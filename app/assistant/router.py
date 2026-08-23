"""AI 도우미 심화 API — 오늘 브리핑 / 스탠드업 초안 / 주간 다이제스트 / 미할당 트리아지.

계약이 두 줄로 요약된다:
  1. **숫자는 항상 나온다.** 사실 층(facts.py)에는 LLM 이 없고, 러너 장애는 narrative 블록
     안에서 끝난다. `?narrate=true` 로 부르고 러너가 죽어 있어도 응답의 숫자 필드는 동일하다.
  2. **트리아지는 제안만 한다.** 응답에 `auto_assign: false` 가 박혀 있고, 이 라우터에는
     쓰기(POST/PATCH)가 하나도 없다.

전부 GET(조회 전용)이라 CSRF 는 필요 없다. 문장 생성은 기본 꺼짐이고(`narrate` 기본 false +
feature flag), 켠 경우에도 사용자별 레이트리밋을 지난다 — 러너/Claude 호출은 비싸다.

핸들러는 전부 동기 함수다(저장소 불변 §2).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.assistant import facts as facts_service
from app.assistant import narrate as narrate_service
from app.core.deps import get_current_user, get_db
from app.core.errors import RateLimitedError
from app.quotas import service as ai_quotas
from app.users.models import User

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _ctx(request: Request):
    state = request.app.state
    return (state.outbound_client, state.settings, state.repositories.tickets, state.clock.now())


def _with_narrative(
    request: Request, user: User, body: dict, *, want: bool, db: Session | None = None
) -> dict:
    """사실 dict 에 문장 블록만 덧붙인다 — 사실 필드는 절대 건드리지 않는다.

    이 함수가 실패해도 숫자가 사라지지 않는 이유가 여기 있다: 원본 dict 를 복사해 키 하나를
    더할 뿐이고, narrate() 는 예외를 던지지 않는다(narrate.py 상단 주석).
    """
    if not want:
        return {**body, "narrative": None}
    settings = request.app.state.settings
    # 꺼져 있으면 레이트리밋 토큰도 쓰지 않는다(호출이 아예 나가지 않으므로).
    if not narrate_service.is_enabled(settings):
        return {**body, "narrative": narrate_service.disabled_result()}
    limiter = request.app.state.assistant_ratelimiter
    key = f"assistant:{user.id}"
    if not limiter.allow(key):
        raise RateLimitedError(
            "요약 생성을 너무 자주 요청했습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=limiter.retry_after_seconds(key),
        )
    # AI 쿼터(0033) — 레이트리밋과 다른 것을 막는다. 레이트리밋은 '초당 몇 번'(폭주 방지),
    # 쿼터는 '하루/한 달에 몇 번'(비용 상한). 둘 다 있어야 "천천히 계속 쓰는" 소비를 잡는다.
    # 호출이 나가기 **전에** 보고, 나간 뒤에 센다 — 실패한 호출까지 상한을 깎으면 러너가
    # 죽은 날 사용자가 쿼터까지 잃는다.
    now = request.app.state.clock.now()

    def _call():
        return narrate_service.narrate(
            request.app.state.ai_gateway, settings,
            kind=body.get("kind", ""), facts=body,
            requester={"user_id": user.id, "display_name": user.display_name},
        )

    if db is None:
        return {**body, "narrative": _call()}

    # 확인과 기록 **사이에 AI 호출이 통째로 들어 있다** — 그 몇 초가 동시 요청 둘이 같은
    # 숫자를 읽는 창이었다 (Z15). 이제 한 사람의 판정은 한 번에 하나만 지난다.
    with ai_quotas.consume(
        db, user_id=user.id, org_id=getattr(user, "org_id", None),
        kind=ai_quotas.KIND_ASSISTANT_NARRATIVE, now=now,
    ) as slot:
        # DBTX: 아웃바운드(러너) 호출 앞에서 커밋해 스냅샷을 새로 뜬다. 이 잠금은
        # quota_lock.quota_guard(순수 프로세스 내 뮤텍스)가 지킨다 — DB 트랜잭션을
        # 열어 두는 것과 무관하다(consume.__init__ 참고), 그러니 여기서 커밋해도 Z15가
        # 막던 동시-소비 경합은 그대로 막힌다. 커밋 없이 느린 호출을 통과하면 아래
        # slot.record() 뒤의 커밋이 "database is locked"로 거부될 수 있다
        # (app/core/db.py의 "begin" 이벤트 주석, app/jobs/handlers/chat_message.py의
        # 실측 사고와 같은 근거) — enforce()가 이미 위 __enter__에서 판정을 끝냈으므로
        # 여기서 커밋해도 그 판정을 다시 열지 않는다.
        db.commit()
        narrative = _call()
        # 성공한 호출만 센다. narrate()는 예외를 던지지 않고 {"enabled","text","error"}를
        # 돌려주므로, 실제로 문장이 나온 경우(text 가 있고 error 가 없음)만 쿼터를 깎는다 —
        # 러너가 죽은 날 사용자가 아무것도 못 받고 상한만 잃으면 안 된다.
        if (narrative or {}).get("text") and not (narrative or {}).get("error"):
            slot.record()
            # UB-08: 잠금이 풀리기 전에 커밋한다(app/quotas/service.py의 consume 문서 참조).
            db.commit()
    return {**body, "narrative": narrative}


@router.get("/briefing")
def briefing(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    narrate: bool = Query(default=False, description="문장 요약까지 만들지 여부(기본 false)"),
):
    """오늘 브리핑 — 홈 '오늘'과 같은 숫자 + (선택) 한 문단 요약."""
    outbound, settings, repo, now = _ctx(request)
    body = facts_service.briefing_facts(db, outbound, settings, user, repo=repo, now=now)
    return _with_narrative(request, user, body, want=narrate, db=db)


@router.get("/standup")
def standup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    narrate: bool = Query(default=False),
):
    """스탠드업 초안 — 최근 끝낸 것 / 오늘 할 것 / 막힌 것 + (선택) 읽어 줄 수 있는 초안."""
    outbound, settings, repo, now = _ctx(request)
    body = facts_service.standup_facts(db, outbound, settings, user, repo=repo, now=now)
    return _with_narrative(request, user, body, want=narrate, db=db)


@router.get("/weekly-digest")
def weekly_digest(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    narrate: bool = Query(default=False),
):
    """주간 다이제스트 — 이번 스프린트 창의 팀 합계·내 몫·바뀐 문서/게시글 + (선택) 요약."""
    outbound, settings, repo, now = _ctx(request)
    body = facts_service.weekly_digest_facts(db, outbound, settings, user, repo=repo, now=now)
    return _with_narrative(request, user, body, want=narrate, db=db)


@router.get("/triage")
def triage(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """미할당 트리아지 **제안**. 아무것도 배정하지 않는다(`auto_assign: false`).

    문장 생성을 붙이지 않는다 — '이 티켓은 아무개에게' 라는 문장은 결정처럼 읽히고,
    그 순간 '제안만'이라는 계약이 화면에서 깨진다. 순서와 근거(부하 수)만 준다.
    """
    outbound, settings, repo, now = _ctx(request)
    return facts_service.triage_facts(db, outbound, settings, user, repo=repo, now=now)
