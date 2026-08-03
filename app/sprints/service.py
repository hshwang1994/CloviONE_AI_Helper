"""주간 스프린트 회의 도우미 — 집계·배분·계획을 한 화면 데이터로 조립(모델·마이그레이션 없음).

전부 기존 조회를 재사용한다: 완료 현황=app/reports 담당자별 집계(날짜 범위 버전 build_period_report),
배분=미할당 티켓, 계획=상태가 '계획'인 팀 티켓. 담당자별 생산성 집계는 팀 전원 공개(사용자 결정).
새 쓰기 없음 — 회의 중 배정/편집은 기존 /api/tickets 계약을 프런트가 그대로 쓴다.
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


def build_sprint_summary(db: Session, outbound, settings, *, start: str, end: str, today: date) -> dict:
    """스프린트 회의 한 판에 필요한 것: 담당자별 완료/진행 집계 + 배분 대상(미할당) + 계획 티켓."""
    report = reports_service.build_period_report(db, outbound, settings, start=start, end=end, today=today)
    unassigned = tickets_service.list_unassigned_tickets(db, outbound, settings, active_only=True)
    planned = [
        t for t in tickets_service.list_team_tickets(db, outbound, settings, active_only=False)
        if t.get("status") == STATUS_PLANNED
    ]
    return {
        "window": {"start": start, "end_exclusive": end},
        "team": report["team"],
        "developers": report["developers"],
        "unassigned": unassigned,
        "planned": planned,
    }
