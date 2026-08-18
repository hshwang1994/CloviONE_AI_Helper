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
from app.sprints.burndown import build_burndown
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


def _visible_ids(db: Session, viewer, scope=None):
    """이 사람에게 보이는 사용자 집합. 범위가 안 걸리면 `None`(= 제한 없음).

    UA-02: 예전엔 `scope.is_dept`일 때만 걸러 org 범위 관리자는 그대로 통과했다(원
    조건이 "부서 범위가 아니면 무제한"으로 읽혀, org 범위·설정오류로 인한 fail-closed
    빈 범위를 전부 놓쳤다). `visible_user_ids` 자신이 이미 전역일 때만 `None`을 주므로
    그 판정 하나로 충분하다 — 여기서 다시 종류를 따질 필요가 없다.
    """
    if viewer is None:
        return None
    from app.core.scope import visibility_scope, visible_user_ids

    return visible_user_ids(db, scope if scope is not None else visibility_scope(db, viewer))


# 부서 선택 판정은 **공용 모듈 하나**다 (0060 §32). 스프린트만 쓰던 시절에는 여기 있었는데,
# 프로젝트·문서·팀 티켓 목록도 같은 판정이 필요해지면서 갈라질 자리가 생겼다 — 그중 하나가
# 범위를 넓게 잡아도 화면은 정상으로 보인다(목록이 더 많이 나올 뿐이다).
from app.org.context import department_context  # noqa: E402  (재수출 — 기존 호출부 유지)


def build_sprint_summary(
    db: Session, outbound, settings, *, start: str, end: str, today: date, repo=None,
    viewer=None, department_id: str | None = None,
) -> dict:
    """스프린트 회의 한 판에 필요한 것: 담당자별 집계 + 담당자별 티켓 + 배분 대상(미할당) + 계획 티켓.

    `department_id` 는 **화면 Context** 다(§18) — "지금 어느 팀 스프린트를 보는가". 없으면
    보는 사람의 소속 부서, 그것도 없으면 조회 범위 전체다. 범위 검증은 서버가 한다
    (`department_context`) — 프런트 선택기만으로 막으면 API 한 번에 뚫린다.
    """
    context = department_context(db, viewer, department_id)
    scope = context["scope"]
    # `viewer` 를 주면 **그 사람의 팀**으로 좁힌다 (1순위 유출 #3). 예전에는 포탈 전체였다 -
    # 즉 담당자별 생산성이 전사 공개였다. 같은 성격의 `dev-monthly` 는 민감 역할 게이트 +
    # 범위를 둘 다 지나는데 이쪽은 role 게이트조차 없었다.
    period_tickets = tickets_service.drop_out_of_scope_dtos(
        db,
        tickets_service.list_period_tickets(
            db, outbound, settings, start=start, end=end, repo=repo
        ),
        viewer,
        scope,
    )
    # 담당자 목록도 좁힌다. `build_period_report` 는 **활성 사용자 전원**을 0건으로라도
    # 넣는데(월간 리포트가 "이 사람은 이번 달 한 건도 없다" 를 보여야 하므로), 스프린트가
    # 그걸 안 넘겨서 **남의 팀 사람이 이름과 함께 그대로 나왔다.** 티켓만 걸러도 명부는 샌다.
    # `dev-monthly` 는 이 인자를 이미 쓰고 있었다 — 두 화면이 같은 코어를 다르게 부르고 있었다.
    report = reports_service.build_period_report(
        db, outbound, settings, start=start, end=end, today=today, tickets=period_tickets,
        visible_user_ids=_visible_ids(db, viewer, scope),
    )
    # 배분 대상(미할당)도 **범위를 건다** (0060). 예전에는 "포탈 전용 버킷이라 좁히면
    # 회의가 불가능하다" 며 일부러 안 걸었는데, 그 예외 하나가 스프린트 화면을 전 포털
    # 미할당 티켓의 우회 열람 경로로 만들었다. 이제 미할당은 "프로젝트는 있고 담당자만
    # 없는 일" 이라 그 프로젝트를 볼 수 있는 팀이면 회의에서 그대로 배분할 수 있다 —
    # 좁혀도 대화가 가능하고, 오히려 남의 팀 일이 섞이지 않아 회의가 정확해진다.
    unassigned = tickets_service.list_unassigned_tickets(
        db, outbound, settings, active_only=True, repo=repo, viewer=viewer, scope=scope
    )
    planned = [
        t for t in tickets_service.list_team_tickets(
            db, outbound, settings, active_only=False, repo=repo, viewer=viewer, scope=scope
        )
        if t.get("status") == STATUS_PLANNED
    ]
    return {
        "window": {"start": start, "end_exclusive": end},
        # 화면이 "지금 어느 팀 스프린트인가" 를 말하고, 고를 수 있는 부서도 함께 준다 —
        # 선택지를 프런트가 스스로 계산하면 서버 검증과 갈라진다.
        "department": {"selected": context["selected"], "options": context["options"]},
        "team": report["team"],
        "developers": report["developers"],
        # 담당자별 티켓 리스트(회의 진행용). developers 와 같은 순서·같은 이름 키.
        "by_assignee": _by_assignee(db, period_tickets, report["developers"]),
        # 번다운(마감일 축) — 같은 티켓 목록을 한 번 더 읽지 않고 그대로 넘긴다.
        # 'WD 밸런스'는 새 필드가 아니다: developers[].est_all / est_done 이 이미 담당자별
        # 업무량이라 화면이 그것으로 막대를 그린다. 같은 숫자를 두 이름으로 내보내면
        # 언젠가 한쪽만 고쳐진다.
        "burndown": build_burndown(period_tickets, start=start, end=end),
        # 미할당은 계속 준다 — 미할당 티켓 화면과 겹쳐 보여도, 회의 중 그 자리에서 배정하는
        # 흐름이 이 값을 쓴다(빼면 기능이 사라지고 백엔드가 얻는 것은 없다).
        "unassigned": unassigned,
        "planned": planned,
    }
