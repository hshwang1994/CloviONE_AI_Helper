"""홈 '오늘' 커맨드 센터 조립 — 결정적 집계, LLM 없음, 신규 저장소 없음.

세 층으로 나눠 두었다:
  aggregate.py  순수 함수(입력→출력). 서버 없이 값으로 고정된다.
  readers.py    기존 표를 다시 읽기만 하는 SELECT 모음(쓰기 0).
  service.py    이 파일 — 둘을 조립하고, 소스 장애를 표면별로 격리한다.

**Notion 왕복 0회가 목표다.** 티켓은 저장소 seam 을 한 번만 부르고(list_my_tickets →
repository.list_by_assignee), 미러가 채워져 있으면 그 한 번도 로컬 SELECT 다. 스프린트
진척은 같은 목록에서 마감일로 잘라 계산한다 — 창 범위를 다시 읽지 않는다(계획서의
"기존 리더 조합"을 문자 그대로 지킨다).

장애 격리(§17.4): 티켓 소스가 죽어도 알림·채팅·문서·게시판은 그대로 나온다. 티켓 블록만
configured/ok 플래그로 '왜 비었는지'를 말한다 — 화면 전체를 오류로 덮지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.home import aggregate, readers
from app.sprints.service import default_sprint_window
from app.tickets import service as tickets_service
from app.users.models import User


def local_today(settings, now: datetime) -> date:
    """표시·경계 판정 기준 날짜(불변 §9: Asia/Seoul). clock 은 naive UTC 를 준다.

    UTC 로 '오늘'을 판정하면 KST 09:00 이전에 날짜가 하루 밀려, 아침에 여는 사람이 어제
    화면을 본다 — 이 화면에서는 그게 곧 '오늘 마감'을 놓치는 일이다.
    """
    return now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()


def window_utc_bounds(settings, start: str, end: str) -> tuple[datetime, datetime]:
    """KST 달력일 창 [start, end) → DB 가 쓰는 **naive UTC** 경계.

    게시글 created_at 은 naive UTC 로 저장돼 있다. KST 날짜를 그대로 비교하면 UTC 자정
    경계가 KST 09:00 에 걸려 그 주의 앞 9시간이 지난 주로 새어 나간다(감사 화면에서
    이미 한 번 겪은 함정 — app/audit/router.py 주석 참조).
    """
    tz = ZoneInfo(settings.timezone)
    since = datetime.fromisoformat(start).replace(tzinfo=tz)
    until = datetime.fromisoformat(end).replace(tzinfo=tz)
    return (
        since.astimezone(timezone.utc).replace(tzinfo=None),
        until.astimezone(timezone.utc).replace(tzinfo=None),
    )


def utc_iso_bounds(settings, start: str, end: str) -> tuple[str, str]:
    """같은 창을 **문자열 비교용** naive UTC ISO 로. 변환은 위 함수 하나만 쓴다.

    왜 문자열이냐면 비교 대상이 datetime 이 아니기 때문이다. `document_cache.last_edited`
    는 Notion 이 준 'YYYY-MM-DDTHH:MM:SS.sssZ' **원문을 String 컬럼에 그대로** 담는다
    (app/team_docs/models.py). 그 컬럼을 datetime 과 비교하면 SQLite 는 조용히 아무 행도
    안 고르거나 엉뚱한 행을 고른다 - 화면에는 그럴듯한 숫자가 남아서 신고되지 않는다.

    ISO 는 자리수가 같은 접두사끼리 사전순 비교가 곧 시간순 비교라 파싱 없이 자를 수 있다.
    경계값('...T15:00:00')보다 소수 이하가 붙은 원문('...T15:00:00.000Z')이 사전순으로
    뒤라서, 시작은 포함하고 끝은 배타인 반열린 창이 문자열에서도 그대로 성립한다.

    변환을 여기 한 곳에 두는 이유는 M4 다: KST 달력일을 UTC 문자열과 그대로 비교하면
    KST 월요일 오전 9시간이 통째로 지난 주로 새어 나간다. 실제로 이 저장소의 주간
    다이제스트가 그 상태였다(`readers.documents_changed_between` 주석).
    """
    since, until = window_utc_bounds(settings, start, end)
    return since.isoformat(), until.isoformat()


def load_my_tickets(db: Session, outbound, settings, user: User, *, repo) -> dict:
    """내 티켓을 저장소 seam 으로 한 번 읽고, 실패를 응답 가능한 상태로 접는다.

    반환은 항상 같은 모양이다: {configured, ok, mapped, tickets, message?, error?}.
    예외를 밖으로 던지지 않는 이유는 홈이 티켓 하나 때문에 통째로 죽으면 안 되기 때문이다.
    (/api/tickets/mine 라우터가 하는 것과 같은 접기 — 어휘도 같은 값을 쓴다.)
    """
    try:
        result = tickets_service.list_my_tickets(db, outbound, settings, user, repo=repo)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "mapped": True,
                "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "mapped": True,
                "error": exc.message, "tickets": []}
    return {"configured": True, "ok": True, "mapped": bool(result.get("mapped")),
            "tickets": list(result.get("tickets") or [])}


def build_today(
    db: Session, outbound, settings, user: User, *, repo, now: datetime,
    item_limit: int = aggregate.DEFAULT_ITEM_LIMIT,
) -> dict:
    """홈 '오늘' 한 화면에 필요한 모든 숫자. 문장(LLM)은 여기 없다."""
    today = local_today(settings, now)
    today_iso = today.isoformat()
    start, end = default_sprint_window(today)

    state = load_my_tickets(db, outbound, settings, user, repo=repo)
    tickets = state["tickets"]
    ticket_block = {
        **{k: v for k, v in state.items() if k != "tickets"},
        **aggregate.bucket_my_tickets(tickets, today=today_iso, limit=item_limit),
    }
    # 티켓을 못 읽었으면 진척을 0으로 그리지 않는다 — 0건과 '모른다'는 다른 말이다.
    sprint = (
        aggregate.sprint_progress(tickets, start=start, end=end, today=today_iso)
        if state["ok"] and state["mapped"] else None
    )

    body = {
        "ok": True,
        "today": today_iso,
        "tickets": ticket_block,
        "sprint": sprint,
        "inbox": {
            "notifications_unread": readers.notifications_unread(db, user.id),
            "chat_unread": readers.chat_unread(db, user, config_dir=settings.config_dir),
        },
        "recent": {
            "documents": readers.recent_documents(db, limit=item_limit),
            "board": readers.recent_board_posts(db, limit=item_limit),
        },
    }
    # 미러로 답했을 때만 신선도를 싣는다(실시간 응답에 미러 상태를 실으면 거짓말이다).
    sync = tickets_service.sync_indicator(db, repo=repo)
    return {**body, "sync": sync} if sync else body
