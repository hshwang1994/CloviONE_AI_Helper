"""개발자 월간 리포트 집계 유닛 테스트.

Notion 호출은 fake outbound 로 대체해(httpx 미사용) 파싱·집계·미설정 경로를 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.reports import notion_source
from app.reports.service import build_dev_monthly_report, month_range


class _Resp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeOutbound:
    """query_tasks_for_period 가 부르는 .post 만 흉내낸다."""

    def __init__(self, results=None, raise_exc=None, status_code=200):
        self._results = results or []
        self._raise = raise_exc
        self._status = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._raise is not None:
            raise self._raise
        return _Resp(self._status, {"results": self._results, "has_more": False})


def _ticket(*, tid, title, status, due, people, est, act, diff):
    props = {
        "제목": {"title": [{"plain_text": title}]},
        "진행상태": {"status": {"name": status}},
        "마감일": {"date": {"start": due}},
        "티켓 담당자": {"people": [{"id": pid} for pid in people]},
        "예상 WD": {"number": est},
        "실제 WD": {"number": act},
        "난이도": {"select": {"name": diff} if diff else None},
        "우선순위": {"select": None},
        "티켓 ID": {"unique_id": {"number": tid}},
    }
    return {"id": f"n{tid}", "url": f"https://notion/{tid}", "properties": props}


def _map(db, user, notion_id):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=STATUS_VERIFIED))
    db.commit()


def test_month_range_normal_and_december():
    assert month_range("2026-07") == ("2026-07-01", "2026-08-01")
    assert month_range("2026-12") == ("2026-12-01", "2027-01-01")


def test_month_range_rejects_bad_month():
    with pytest.raises(ValueError):
        month_range("2026-13")


def test_aggregates_by_developer_with_names_and_overdue(db, settings, make_user):
    dev = make_user(email="cs@goodmit.co.kr", display_name="김철수", role="admin")
    make_user(email="yh@goodmit.co.kr", display_name="이영희", role="admin")  # 티켓 없음
    _map(db, dev, "notion-cs")

    results = [
        _ticket(tid=1, title="완료건", status="완료", due="2026-07-01", people=["notion-cs"], est=3, act=3, diff="4"),
        _ticket(tid=2, title="지연건", status="진행", due="2026-07-05", people=["notion-cs"], est=2, act=None, diff="2"),
        _ticket(tid=3, title="무담당", status="계획", due="2026-07-30", people=[], est=1, act=None, diff="1"),
    ]
    outbound = _FakeOutbound(results=results)

    report = build_dev_monthly_report(
        db, outbound, settings, period="2026-07", today=date(2026, 7, 27)
    )

    assert report["team"] == {
        "total": 3, "done": 1, "in_progress": 1, "plan": 1, "cancel": 0,
        "overdue": 1, "est_done_total": 3.0, "est_all_total": 6.0,
    }
    assert report["unassigned"]["total"] == 1
    assert report["unassigned"]["plan"] == 1

    by_name = {r["name"]: r for r in report["developers"]}
    cs = by_name["김철수"]
    assert cs["done"] == 1 and cs["prog"] == 1 and cs["assigned"] == 2
    assert cs["est_done"] == 3.0 and cs["est_all"] == 5.0 and cs["act_done"] == 3.0
    assert cs["overdue"] == 1
    assert cs["completion_rate"] == 50
    assert cs["difficulty_avg"] == 3.0
    assert cs["has_tickets"] is True

    # 담당자별 상세 티켓 목록이 함께 온다(마감일 순).
    assert len(cs["tickets"]) == 2
    first = cs["tickets"][0]
    assert first["tid"] == 1 and first["title"] == "완료건" and first["status"] == "완료"
    assert first["est_wd"] == 3 and first["act_wd"] == 3 and first["difficulty"] == "4"
    assert first["due"] == "2026-07-01"
    assert cs["tickets"][1]["overdue"] is True  # 지연건

    # 티켓 없는 활성 사용자도 0으로 포함된다.
    yh = by_name["이영희"]
    assert yh["done"] == 0 and yh["assigned"] == 0 and yh["has_tickets"] is False and yh["tickets"] == []

    # Notion 필터가 이번 달 범위로 걸렸는지(요청 바디)도 확인한다.
    _, kwargs = outbound.calls[0]
    assert kwargs["allowlist"] == "services"
    assert kwargs["auth_type"] == "bearer"
    flt = kwargs["json"]["filter"]["and"]
    assert flt[0]["date"]["on_or_after"] == "2026-07-01"
    assert flt[1]["date"]["before"] == "2026-08-01"


def test_unmapped_assignee_falls_back_to_placeholder(db, settings, make_user):
    make_user(email="a@goodmit.co.kr", display_name="가나다", role="admin")
    results = [
        _ticket(tid=9, title="미매핑건", status="완료", due="2026-07-02", people=["notion-unknown"], est=2, act=2, diff="3"),
    ]
    report = build_dev_monthly_report(
        db, _FakeOutbound(results=results), settings, period="2026-07", today=date(2026, 7, 27)
    )
    by_name = {r["name"]: r for r in report["developers"]}
    assert "(미확인 담당자)" in by_name
    assert by_name["(미확인 담당자)"]["done"] == 1


def test_missing_token_raises_not_configured(db, settings):
    outbound = _FakeOutbound(raise_exc=FileNotFoundError("no such secret"))
    with pytest.raises(notion_source.NotionNotConfiguredError):
        build_dev_monthly_report(
            db, outbound, settings, period="2026-07", today=date(2026, 7, 27)
        )


def test_notion_401_maps_to_not_configured(db, settings):
    outbound = _FakeOutbound(results=[], status_code=401)
    with pytest.raises(notion_source.NotionNotConfiguredError):
        build_dev_monthly_report(
            db, outbound, settings, period="2026-07", today=date(2026, 7, 27)
        )
