"""AI 도우미 심화의 **결정적 사실 층** — 오늘 브리핑 / 스탠드업 초안 / 주간 다이제스트 / 트리아지.

계획서 Phase 5: *"먼저 결정적 집계 엔드포인트로 만들고 LLM 없이 테스트한 뒤 문장만 LLM에
맡긴다."* 이 파일에는 LLM 호출이 **한 줄도 없다**. 러너가 죽어도 여기서 나온 숫자는 그대로
화면에 뜬다(문장만 빠진다) — 그 성질을 tests/unit/test_assistant_facts.py 와
tests/integration/test_assistant_api.py 가 고정한다.

임베딩·벡터DB는 쓰지 않는다(계획서 명시). 여기서 하는 일은 이미 있는 표를 세는 것뿐이다.

티켓은 전부 저장소 seam(app/tickets/service)을 통해서만 읽는다. 미러가 채워져 있으면
아래 함수 어느 것도 Notion 을 왕복하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.home import aggregate, readers, service as home_service
from app.sprints.service import default_sprint_window
from app.tickets import service as tickets_service
from app.users.models import User

# 다이제스트·트리아지가 싣는 목록 길이. 사람이 회의에서 한 번에 읽을 수 있는 분량이다.
DIGEST_LIMIT = 5
TRIAGE_LIMIT = 10
CONTRIBUTOR_LIMIT = 5


def _window_for(settings, now: datetime) -> tuple[str, str, str]:
    """(오늘, 스프린트 시작, 스프린트 끝-배타) — 전부 Asia/Seoul 달력일 기준."""
    today = home_service.local_today(settings, now)
    start, end = default_sprint_window(today)
    return today.isoformat(), start, end


def briefing_facts(
    db: Session, outbound, settings, user: User, *, repo, now: datetime
) -> dict:
    """오늘 브리핑의 사실. 홈 '오늘'과 **같은 함수**로 만든다.

    두 벌로 만들면 브리핑 문장이 말하는 숫자와 홈 카드의 숫자가 언젠가 어긋난다 —
    사용자는 그걸 '둘 중 하나가 거짓말'로 받아들인다. 같은 build_today 를 쓴다.
    """
    return {"kind": "briefing", **home_service.build_today(
        db, outbound, settings, user, repo=repo, now=now, item_limit=DIGEST_LIMIT
    )}


def standup_facts(
    db: Session, outbound, settings, user: User, *, repo, now: datetime
) -> dict:
    """스탠드업 초안의 사실 3단(최근 끝낸 것 / 오늘 할 것 / 막힌 것).

    소스에 상태 전이 이력이 없어 '어제 완료'를 만들 수 없다 — 지어내지 않고 스프린트 창
    기준의 `recently_done` 을 낸다(aggregate.standup_sections 주석 참조).
    """
    today, start, end = _window_for(settings, now)
    state = home_service.load_my_tickets(db, outbound, settings, user, repo=repo)
    sections = aggregate.standup_sections(
        state["tickets"], today=today, start=start, end=end, limit=DIGEST_LIMIT
    )
    return {
        "kind": "standup",
        "today": today,
        "author": {"user_id": user.id, "display_name": user.display_name},
        "tickets": {k: v for k, v in state.items() if k != "tickets"},
        **sections,
    }


def _top_contributors(developers: list[dict]) -> list[dict]:
    """완료 건수 상위 기여자. build_period_report 가 이미 완료순으로 정렬해 준다."""
    return [
        {"user_id": d.get("user_id"), "name": d.get("name"),
         "done": d.get("done"), "assigned": d.get("assigned")}
        for d in developers if d.get("assigned")
    ][:CONTRIBUTOR_LIMIT]


def weekly_digest_facts(
    db: Session, outbound, settings, user: User, *, repo, now: datetime
) -> dict:
    """주간 다이제스트 — 이번 스프린트 창의 팀 합계 + 내 몫 + 그 주에 바뀐 문서·게시글.

    팀 합계는 기존 리포트 코어(build_period_report)를 그대로 쓴다. 같은 주의 티켓을 두 번
    읽지 않도록 목록을 한 번 읽어 리포트에 넘긴다(스프린트 요약이 하는 것과 같은 방식).

    이 엔드포인트는 (관리 콘솔의 `dev-monthly`와 달리) **전 사용자용 개인 다이제스트**라
    role 게이트를 걸 수 없다 — 그래서 대신 스프린트 요약(`sprints/service.py::
    build_sprint_summary`)과 같은 방식으로 **호출자의 범위**로 좁힌다(UA-01). 예전엔
    `visible_user_ids`를 안 넘겨 전사 팀 합계·상위 기여자 명단이 role=user 전원에게
    그대로 나갔다.
    """
    from app.core.scope import build_scope, visible_user_ids
    from app.reports import service as reports_service

    today, start, end = _window_for(settings, now)
    my_state = home_service.load_my_tickets(db, outbound, settings, user, repo=repo)
    mine = (
        aggregate.sprint_progress(my_state["tickets"], start=start, end=end, today=today)
        if my_state["ok"] and my_state["mapped"] else None
    )

    team = None
    contributors: list[dict] = []
    if my_state["configured"]:
        period = tickets_service.list_period_tickets(
            db, outbound, settings, start=start, end=end, repo=repo
        )
        report = reports_service.build_period_report(
            db, outbound, settings, start=start, end=end,
            today=datetime.fromisoformat(today).date(), tickets=period,
            visible_user_ids=visible_user_ids(db, build_scope(db, user)),
        )
        team = report["team"]
        contributors = _top_contributors(report["developers"])

    # 같은 KST 창을 **두 형식**으로 옮긴다. 게시글 created_at 은 naive UTC datetime 컬럼이고
    # 문서 last_edited 는 Notion 원문을 담은 String 컬럼이라, 한 창이 두 축으로 나가는 것이
    # 정상이다. 변환은 둘 다 home.service 한 곳을 지난다 — 여기서 직접 만들면 M4 가 되풀이된다
    # (KST 달력일을 UTC 문자열과 그대로 비교해 월요일 오전 9시간이 사라지던 결함).
    since_utc, until_utc = home_service.window_utc_bounds(settings, start, end)
    since_iso, until_iso = home_service.utc_iso_bounds(settings, start, end)
    return {
        "kind": "weekly_digest",
        "today": today,
        "window": {"start": start, "end_exclusive": end},
        "tickets": {k: v for k, v in my_state.items() if k != "tickets"},
        "mine": mine,
        "team": team,
        "top_contributors": contributors,
        "documents_changed": readers.documents_changed_between(
            db, since_iso, until_iso, limit=DIGEST_LIMIT
        ),
        "board": readers.board_posts_between(
            db, since_utc, until_utc, limit=DIGEST_LIMIT
        ),
    }


def triage_facts(
    db: Session, outbound, settings, user: User, *, repo, now: datetime
) -> dict:
    """미할당 트리아지 — **제안만 한다. 배정은 사람이 누른다.**

    응답에 `auto_assign: false` 를 명시적으로 싣는다. 나중에 누가 이 응답을 자동화에 물릴
    때 "이건 제안이다"가 계약에 적혀 있어야 한다(주석은 계약이 아니다).

    제안 담당자는 '지금 활성 담당 건수가 가장 적은 사람' 상위 3명이다 — 순수 카운트라
    설명 가능하고, 같은 입력이면 항상 같은 답이 나온다. LLM 도 임베딩도 쓰지 않는다.
    """
    today, _start, _end = _window_for(settings, now)
    base = {"kind": "triage", "today": today, "auto_assign": False,
            "items": [], "candidates": [], "total": 0}
    try:
        unassigned = tickets_service.list_unassigned_tickets(
            db, outbound, settings, active_only=True, repo=repo
        )
        team = tickets_service.list_team_tickets(
            db, outbound, settings, active_only=True, repo=repo
        )
    except NotionNotConfiguredError as exc:
        return {**base, "configured": False, "ok": False, "message": exc.message}
    except NotionQueryError as exc:
        return {**base, "configured": True, "ok": False, "error": exc.message}

    load = aggregate.assignee_load(team)
    candidates = readers.assignee_candidates(db)
    ordered = aggregate.triage_order(unassigned, today=today)
    suggested = aggregate.suggest_assignees(candidates, load)
    return {
        "kind": "triage",
        "today": today,
        # 계약: 이 엔드포인트는 아무것도 배정하지 않는다(계획서 "제안만, 자동 배정 금지").
        "auto_assign": False,
        "configured": True,
        "ok": True,
        "total": len(ordered),
        "items": [
            {**t, "overdue": aggregate.is_overdue(t, today),
             "priority_rank": aggregate.priority_rank(t.get("priority"))}
            for t in ordered[:TRIAGE_LIMIT]
        ],
        # 제안 담당자는 티켓별이 아니라 화면 전체에 한 벌만 준다 — 티켓마다 다른 사람을
        # 추천하는 척하려면 '누가 무엇을 잘하는가'를 알아야 하는데 그 데이터가 없다.
        "candidates": suggested,
    }
