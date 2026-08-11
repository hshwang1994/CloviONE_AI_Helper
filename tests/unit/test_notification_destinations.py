"""app/notifications/destinations.py::destination_for — 순수 함수 단위 시험.

APPR-01/NOTI-04R 계열 — 승인/스케줄/작업 큐/러너/사용자 알림이 서버가 이미 계산해 줄 수
있는 딥링크(각 화면이 이미 `onQuery`로 소비하는 `?id=`/`?job_id=`)를 못 받고 있었다. 화면 쪽
(`onQuery`) 검증은 프런트 registry 시험이 이미 하므로, 여기서는 백엔드 표
(`RELATED_DESTINATIONS`)가 그 다섯 유형을 실제로 계산해 주는지, 그리고 아직 준비 안 된
유형(schedule_run)은 여전히 null인지를 못박는다.

이 다섯 유형은 프런트에서도 role 게이트가 필요하다(수신자가 항상 관리 콘솔 role인 것은
아니다 — job_failed는 작업을 만든 사람 아무나에게, approval_decided는 승인을 요청한 사람
아무에게나 간다). 그 게이트는 순수 함수가 아니라 컴포넌트 로직(NotificationBell.jsx의
ROUTE_ROLES, registry/notifications.js의 reachableAdminTarget)이라 여기서는 다루지
않는다 — 이 파일은 "경로 문자열이 맞는가"만 본다.
"""

from __future__ import annotations

import pytest

from app.notifications.destinations import destination_for

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "object_type,object_id,expected",
    [
        ("approval", "a-1", "/approvals?id=a-1"),
        ("schedule", "s-1", "/schedules?id=s-1"),
        # job은 다른 셋과 파라미터 이름이 다르다(jobs.onQuery가 job_id를 본다) — 실수로
        # ?id=를 쓰면 조용히 무필터 전체 목록이 열리므로 이름 자체를 못박는다.
        ("job", "j-1", "/jobs?job_id=j-1"),
        ("runner", "r-1", "/runners?id=r-1"),
        ("user", "u-1", "/users?id=u-1"),
        # 기존(이번 변경 전부터 있던) 항목들도 회귀 방지로 같이 고정한다.
        ("chat_room", "c-1", "/chat-rooms/c-1"),
        ("chat_mention", "c-2", "/chat-rooms/c-2"),
        ("ticket", "t-1", "/tickets/t-1"),
        ("document", "d-1", "/team-docs/d-1"),
        ("board_post", "b-1", "/board/b-1"),
    ],
)
def test_known_types_resolve_to_their_screens_deep_link(object_type, object_id, expected):
    assert destination_for(object_type, object_id) == expected


@pytest.mark.parametrize("object_type", ["schedule_run", "unknown_type", None, ""])
def test_types_without_a_single_row_deep_link_stay_null(object_type):
    """schedule_run은 대상 화면(스케줄 실행 이력)에 id 딥링크(onQuery)가 아직 없다
    (destinations.py의 표 뒤 주석 참고) — 여기 넣으면 화면이 그 id를 조용히 무시하고
    무필터 목록만 연다."""
    assert destination_for(object_type, "some-id") is None


@pytest.mark.parametrize("object_type", ["approval", "schedule", "job", "runner", "user"])
def test_id_required_types_return_null_without_an_id(object_type):
    assert destination_for(object_type, None) is None
    assert destination_for(object_type, "") is None


@pytest.mark.parametrize("object_type", ["approval", "schedule", "job", "runner", "user"])
@pytest.mark.parametrize("bad_id", ["a/b", "a?b", "a#b", "a b", "a\\b"])
def test_ids_that_could_break_the_route_are_rejected(object_type, bad_id):
    """id는 서버가 만든 UUID여야 한다 — 그래도 경로를 깨뜨릴 문자는 통과시키지 않는다
    (이미 있던 규칙, 새 네 유형에도 그대로 적용됨을 못박는다)."""
    assert destination_for(object_type, bad_id) is None
