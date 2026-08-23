"""사용자 셀프서비스 티켓 조회 유닛 테스트.

Notion 호출은 fake outbound 로 대체(httpx 미사용). 정방향 매핑·담당자 필터·미할당 필터·배정 후보·
미매핑 처리를 검증한다.
"""

from __future__ import annotations


from app.notion_mapping.models import STATUS_UNMAPPED, STATUS_VERIFIED, UserNotionMapping
from app.tickets import service

import pytest

# 이 파일은 **Notion 저장소 구현체**를 시험한다 — 픽스처가 전부 가짜 Notion 서버다.
# 제품 기본 소스는 S14 부터 `native` 이므로 여기서 되돌려 놓는다. 안 되돌리면 이 시험들이
# 빈 결과 위에서 통과하거나(거짓 초록) 엉뚱한 오류로 죽는다.
#
# 이 표는 동시에 **Notion 을 걷어낼 때 다시 쓸 파일의 목록**이다. 여기서 지키는 성질
# (권한·소유·검증·본문 저장 순서)은 소스가 바뀌어도 그대로 지켜야 하는 것이고, 그 확인은
# 자체 DB 구현체 위에서 다시 서야 한다.
pytestmark = pytest.mark.notion_source


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeOutbound:
    """query_* 가 부르는 .post 만 흉내낸다. 마지막 요청 바디를 calls 에 남긴다."""

    def __init__(self, results=None):
        self._results = results or []
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Resp(200, {"results": self._results, "has_more": False})


def _ticket(*, tid, title, status, due, people, est=None, diff=None):
    return {
        "id": f"n{tid}",
        "url": f"https://notion/{tid}",
        "properties": {
            "제목": {"title": [{"plain_text": title}]},
            "진행상태": {"status": {"name": status}},
            "마감일": {"date": {"start": due}},
            "티켓 담당자": {"people": [{"id": pid} for pid in people]},
            "예상 WD": {"number": est},
            "실제 WD": {"number": None},
            "난이도": {"select": {"name": diff} if diff else None},
            "우선순위": {"select": None},
            "티켓 ID": {"unique_id": {"number": tid}},
        },
    }


def _map(db, user, notion_id, status=STATUS_VERIFIED):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=status))
    db.commit()


def test_my_notion_id_only_verified(db, make_user):
    u = make_user(email="a@goodmit.co.kr", display_name="가나다", role="user")
    assert service.my_notion_id(db, u) is None  # 매핑 없음
    _map(db, u, "notion-a", status=STATUS_UNMAPPED)
    assert service.my_notion_id(db, u) is None  # 미검증은 안 씀
    m = db.query(UserNotionMapping).filter_by(user_id=u.id).one()
    m.status = STATUS_VERIFIED
    db.commit()
    assert service.my_notion_id(db, u) == "notion-a"


def test_list_my_tickets_filters_by_my_notion_id(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    mate = make_user(email="mate@goodmit.co.kr", display_name="동료", role="user")
    _map(db, me, "notion-me")
    _map(db, mate, "notion-mate")
    # Notion 은 people contains 필터로 이미 내 것만 준다(fake 는 준 대로 반환).
    results = [
        _ticket(tid=1, title="내 완료", status="완료", due="2026-08-01", people=["notion-me"]),
        _ticket(tid=2, title="공동", status="진행", due="2026-08-02", people=["notion-me", "notion-mate"]),
    ]
    out = service.list_my_tickets(db, _FakeOutbound(results), settings, me)
    assert out["mapped"] is True
    assert [t["tid"] for t in out["tickets"]] == [1, 2]
    # 공동 담당 티켓의 담당자 이름이 해석된다.
    assert set(out["tickets"][1]["assignee_names"]) == {"나", "동료"}
    # 요청 필터가 people contains 내 notion id 인지 확인.
    outbound = _FakeOutbound(results)
    service.list_my_tickets(db, outbound, settings, me)
    flt = outbound.calls[0][1]["json"]["filter"]
    assert flt == {"property": "티켓 담당자", "people": {"contains": "notion-me"}}


def test_list_my_tickets_unmapped(db, settings, make_user):
    u = make_user(email="u@goodmit.co.kr", display_name="미매핑", role="user")
    outbound = _FakeOutbound([])
    out = service.list_my_tickets(db, outbound, settings, u)
    # total 은 서버 페이지네이션과 함께 들어왔다 - 매핑이 없으면 0건이 맞다.
    assert out == {"mapped": False, "tickets": [], "total": 0}
    assert outbound.calls == []  # 매핑 없으면 Notion 호출도 안 함


def test_list_unassigned_excludes_terminal(db, settings, make_user):
    results = [
        _ticket(tid=3, title="계획 미할당", status="계획", due="2026-08-05", people=[]),
        _ticket(tid=4, title="완료 미할당", status="완료", due="2026-08-06", people=[]),
        _ticket(tid=5, title="취소 미할당", status="취소", due="2026-08-07", people=[]),
    ]
    outbound = _FakeOutbound(results)
    tickets = service.list_unassigned_tickets(db, outbound, settings)
    assert [t["tid"] for t in tickets] == [3]  # 완료·취소 제외
    flt = outbound.calls[0][1]["json"]["filter"]
    assert flt == {"property": "티켓 담당자", "people": {"is_empty": True}}


def test_list_assignees_only_active_verified(db, make_user):
    a = make_user(email="a2@goodmit.co.kr", display_name="에이", role="user")
    b = make_user(email="b2@goodmit.co.kr", display_name="비", role="user")
    make_user(email="c2@goodmit.co.kr", display_name="씨(미매핑)", role="user")  # 매핑 없음
    _map(db, a, "notion-a2")
    _map(db, b, "notion-b2", status=STATUS_UNMAPPED)  # 미검증
    names = [x["display_name"] for x in service.list_assignees(db)]
    assert names == ["에이"]  # verified 매핑 있는 사람만
