"""개인 결재함 `GET /api/approvals/mine` (0060 §16).

## 왜 이 화면이 생겼는가

승인은 관리자 화면(`/api/admin/approvals`)에만 있었다. 그런데 결재 자체는 역할이 아니라
**위임**으로도 생긴다 — 관리 콘솔을 열 수 없는 사람이 결재자가 될 수 있다. 그 사람에게는
"당신에게 결재할 건이 있다" 를 보여 줄 자리가 아예 없었다.

## 이 파일이 못박는 것

  * **역할 게이트가 없다.** 일반 사용자가 200 을 받아야 한다. 403 이면 위임받은 사람이
    자기 결재함을 못 연다.
  * **세 칸이 서로 다른 것을 센다.** 처리할 것 / 내가 올린 것 / 내가 처리한 것.
  * **권한 없음과 할 일 없음을 구별한다.** 둘 다 빈 목록이지만 화면이 다른 문장을 써야 하고,
    그러려면 응답에 `can_decide` 가 있어야 한다.
  * **자기 요청은 자기 할 일 칸에 없다.** 눌러 봐야 거절당하는 줄이다.

⚠️ 이 파일이 없는 동안 실제로 **500** 이 나갔다: 정렬을 `Approval.created_at` 으로 걸었는데
그 표에는 그 열이 없다(`requested_at` 이다). 화면·배지 양쪽이 이 경로를 부르므로 로그인
직후 모든 사용자에게 오류가 났고, 어떤 시험도 이 경로를 부르지 않아 초록이었다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.approvals.models import APPROVAL_PENDING, Approval

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 5, 9, 0, 0)


_SEQ = iter(range(1, 1000))


def _mk(db, *, requested_by, approver_id=None, status=APPROVAL_PENDING, kind="user.role_change"):
    """승인 한 건.

    `object_id` 를 매번 다르게 준다 — pending 중복 방지 인덱스가
    `(request_type, object_id, request_payload_json)` 유일이라, 같은 값으로 두 건을 심으면
    표본을 만들다가 IntegrityError 로 죽는다(제품의 정상 동작이다).
    """
    row = Approval(
        request_type=kind,
        object_type="user",
        object_id=f"obj-{next(_SEQ)}",
        status=status,
        requested_by=requested_by,
        approver_id=approver_id,
        requested_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db, make_user):
    asker = make_user("ma-asker@goodmit.co.kr", role="user", display_name="요청자")
    boss = make_user("ma-boss@goodmit.co.kr", role="admin", display_name="결재자")
    db.commit()
    return {"asker": asker, "boss": boss}


def _mine(client, box=None):
    r = client.get("/api/approvals/mine", params={"box": box} if box else None)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_plain_user_can_open_their_own_inbox(client, login_as, world):
    """역할 게이트가 없어야 한다 — 위임받은 사람은 관리 콘솔을 못 연다."""
    login_as("user", email="ma-asker@goodmit.co.kr")
    body = _mine(client)
    assert body["can_decide"] is False
    assert body["items"] == []


def test_the_requested_box_holds_what_i_asked_for(client, login_as, db, world):
    _mk(db, requested_by=world["asker"].id)
    db.commit()

    login_as("user", email="ma-asker@goodmit.co.kr")
    assert _mine(client, "requested")["total"] == 1
    # 남이 올린 건은 내 '올린 것' 칸에 없다.
    login_as("admin", email="ma-boss@goodmit.co.kr")
    assert _mine(client, "requested")["total"] == 0


def test_the_todo_box_holds_what_i_can_decide(client, login_as, db, world):
    """결재 권한이 있는 사람의 할 일 칸 — 자기 요청은 빠진다."""
    _mk(db, requested_by=world["asker"].id)
    _mk(db, requested_by=world["boss"].id)   # 결재자가 스스로 올린 건
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    body = _mine(client, "todo")
    assert body["can_decide"] is True
    assert body["total"] == 1, (
        "자기 요청이 자기 할 일 칸에 들어갔다 — 눌러 봐야 거절당하는 줄이다"
    )


def test_the_done_box_holds_what_i_decided(client, login_as, db, world):
    _mk(db, requested_by=world["asker"].id, approver_id=world["boss"].id, status="approved")
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    assert _mine(client, "done")["total"] == 1
    login_as("user", email="ma-asker@goodmit.co.kr")
    assert _mine(client, "done")["total"] == 0


def test_paging_the_badge_query_does_not_explode(client, login_as, db, world):
    """배지는 `page_size=1` 로 총계만 묻는다 — 그 조합이 실제로 도는지 본다.

    이 한 줄이 없어서 정렬 열 오타(`created_at`, 없는 열)가 배포까지 갔다. 배지는 셸이
    부르므로 **로그인한 모든 사용자**가 500 을 봤다.
    """
    for _ in range(3):
        _mk(db, requested_by=world["asker"].id)
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    r = client.get("/api/approvals/mine", params={"box": "todo", "page_size": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3 and len(body["items"]) == 1


def test_the_list_is_ordered_newest_first(client, login_as, db, world):
    """id 가 UUID 라 정렬 열이 없으면 순서가 무작위다 — 최신이 위로 와야 한다."""
    old = _mk(db, requested_by=world["asker"].id)
    old.requested_at = datetime(2026, 1, 1, 0, 0, 0)
    new = _mk(db, requested_by=world["asker"].id)
    new.requested_at = datetime(2026, 8, 20, 0, 0, 0)
    db.commit()

    login_as("user", email="ma-asker@goodmit.co.kr")
    ids = [i["id"] for i in _mine(client, "requested")["items"]]
    assert ids == [new.id, old.id], f"최신 순이 아니다: {ids}"
