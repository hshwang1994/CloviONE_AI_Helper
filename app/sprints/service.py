"""주간 스프린트 회의 도우미 — 집계·배분·계획을 한 화면 데이터로 조립(모델·마이그레이션 없음).

전부 기존 조회를 재사용한다: 완료 현황=app/reports 담당자별 집계(날짜 범위 버전 build_period_report),
배분=미할당 티켓, 계획=상태가 '계획'인 팀 티켓, 담당자별 리스트=같은 주 범위 티켓을 담당자로 묶은 것.
담당자별 생산성 집계는 팀 전원 공개(사용자 결정). 새 쓰기 없음 — 회의 중 배정/편집은 기존
/api/tickets 계약을 프런트가 그대로 쓴다.

성능: 주 범위 티켓은 **한 번만** 읽어 리포트 집계와 담당자별 리스트가 함께 쓴다(실시간 소스일 때
왕복이 그대로 비용이다). 티켓 소스가 로컬 미러면 이 화면 전체가 Notion 왕복 0회다.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.reports import service as reports_service
from app.tickets import service as tickets_service

STATUS_PLANNED = "계획"


def default_sprint_window(today: date) -> tuple[str, str]:
    """이번 주 월요일 ~ 다음 주 월요일(배타적). today 는 Asia/Seoul 기준 날짜여야 한다(주 판정)."""
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()


def _by_assignee(db: Session, period_tickets, developers: list[dict]) -> list[dict]:
    """담당자별 티켓 리스트 [{user_id, name, tickets[]}].

    카운트 표만으로는 "각자 뭘 끝냈고 뭘 하고 있는지"가 안 보인다 — 같은 주 범위 티켓을 담당자로
    묶어 제목·상태·마감까지 그대로 준다. 티켓 dict 는 목록 API 와 완전히 같은 모양이라 프런트가
    `id` 로 /tickets/:id 상세에 딥링크할 수 있다.

    묶는 키·순서는 developers 와 정확히 같다(표시 이름 기준, 완료순) — 어긋나면 같은 화면에서
    숫자와 목록이 다른 말을 한다. 다중 담당 티켓은 양쪽 담당자에 모두 들어간다(집계와 동일).
    """
    maps = reports_service.load_display_maps(db)
    views = tickets_service.ticket_views(db, period_tickets)
    by_name: dict[str, list[dict]] = {}
    for dto, view in zip(period_tickets, views):
        for aid in dto.assignee_ids:
            name = maps.id_to_name.get(aid, reports_service.UNKNOWN_ASSIGNEE_NAME)
            by_name.setdefault(name, []).append(view)
    return [
        {"user_id": d.get("user_id"), "name": d["name"], "tickets": by_name.get(d["name"], [])}
        for d in developers
    ]


def build_sprint_summary(
    db: Session, outbound, settings, *, start: str, end: str, today: date, repo=None
) -> dict:
    """스프린트 회의 한 판에 필요한 것: 담당자별 집계 + 담당자별 티켓 + 배분 대상(미할당) + 계획 티켓."""
    period_tickets = tickets_service.list_period_tickets(
        db, outbound, settings, start=start, end=end, repo=repo
    )
    report = reports_service.build_period_report(
        db, outbound, settings, start=start, end=end, today=today, tickets=period_tickets
    )
    unassigned = tickets_service.list_unassigned_tickets(
        db, outbound, settings, active_only=True, repo=repo
    )
    planned = [
        t for t in tickets_service.list_team_tickets(
            db, outbound, settings, active_only=False, repo=repo
        )
        if t.get("status") == STATUS_PLANNED
    ]
    return {
        "window": {"start": start, "end_exclusive": end},
        "team": report["team"],
        "developers": report["developers"],
        # 담당자별 티켓 리스트(회의 진행용). developers 와 같은 순서·같은 이름 키.
        "by_assignee": _by_assignee(db, period_tickets, report["developers"]),
        # 미할당은 계속 준다 — 미할당 티켓 화면과 겹쳐 보여도, 회의 중 그 자리에서 배정하는
        # 흐름이 이 값을 쓴다(빼면 기능이 사라지고 백엔드가 얻는 것은 없다).
        "unassigned": unassigned,
        "planned": planned,
    }
