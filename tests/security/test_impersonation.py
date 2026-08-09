"""읽기 전용 임퍼소네이션 — **쓰기가 실제로 막히는가**를 고정한다 (0033, PLAN Phase 6).

## 왜 이 파일이 필요한가

"읽기 전용"은 화면에서 버튼을 숨겨서 지키는 것이 아니다. 숨긴 버튼은 fetch 한 줄이면
되살아나고, 그 순간 감사 로그에는 **대상 사용자가 한 것처럼 보이는 쓰기**가 남는다.
그래서 여기서는 세 가지를 소스가 아니라 **실제 응답**으로 확인한다:

  1. 임퍼소네이션 세션으로 부른 쓰기 라우트가 403 `impersonation_read_only` 를 낸다
     — 대표 라우트 몇 개가 아니라 **앱이 만든 쓰기 라우트 전수**를 의존성 그래프로 훑는다.
  2. 그동안 읽기는 대상의 눈으로 정상 동작한다(막기만 하면 기능이 없는 것과 같다).
  3. 시작·종료가 감사 로그와 기록 표에 남고, **행위자는 관리자**다(대상이 아니다).

`tests/security/test_csrf_coverage.py` 와 같은 방식으로 라우트를 열거하는 이유도 같다:
새 라우터를 만들면서 무언가를 빠뜨려도 아무 테스트가 빨개지지 않는 상황을 만들지 않기 위해서다.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

pytestmark = pytest.mark.security

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _start_impersonation(client, csrf, target_id, reason="지원 문의 확인"):
    return client.post(
        "/api/admin/impersonation/start",
        json={"user_id": target_id, "reason": reason},
        headers={"X-CSRF-Token": csrf},
    )


@pytest.fixture()
def impersonating(client, login_as, make_user):
    """system_admin 으로 로그인해 일반 사용자를 임퍼소네이션한 상태의 (client, csrf, target)."""
    target = make_user(email="target@goodmit.co.kr", role="user", display_name="대상 사용자")
    target_id = target.id
    csrf = login_as("system_admin")
    response = _start_impersonation(client, csrf, target_id)
    assert response.status_code == 200, response.text
    return client, csrf, target_id


def test_state_reports_impersonation(impersonating):
    client, _csrf, target_id = impersonating
    body = client.get("/api/admin/impersonation/state").json()
    assert body["impersonating"] is True
    assert body["target_id"] == target_id
    # 행위자는 관리자 그대로다 — 이게 무너지면 감사가 통째로 거짓이 된다.
    assert body["actor_name"] != body["target_name"]


def test_reads_are_served_as_the_target(impersonating):
    """읽기는 대상의 눈으로 동작한다. 막기만 하는 기능은 아무 쓸모가 없다."""
    client, _csrf, target_id = impersonating
    me = client.get("/api/me")
    assert me.status_code == 200, me.text
    body = me.json()["user"]
    assert body["id"] == target_id
    assert body["role"] == "user"


def test_every_write_route_is_blocked_while_impersonating(impersonating, app):
    """쓰기 라우트 **전수**가 막힌다 — 대표 몇 개만 확인하지 않는다.

    경로 파라미터에는 존재하지 않는 값을 넣는다. 차단이 조회보다 먼저 일어나야 하므로
    404 가 아니라 403 이 나와야 한다(먼저 조회하면 대상 존재 여부가 새기도 한다).
    """
    from app.core.deps import IMPERSONATION_ALLOWED_WRITES

    client, csrf, _target_id = impersonating
    checked = 0
    wrong: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods - SAFE_METHODS
        if not methods:
            continue
        if route.path in IMPERSONATION_ALLOWED_WRITES:
            continue
        # 세션이 생기기 전 경로 — 임퍼소네이션과 무관하다(인증 의존성이 아예 없어서
        # get_current_auth 의 읽기 전용 가드를 지나지 않는다). 이 목록은
        # tests/security/test_csrf_coverage.py 의 '인증 없는 쓰기 라우트' 목록과 같아야 한다.
        if route.path in ("/login", "/forgot-password", "/reset-password"):
            continue
        path = route.path
        for param in route.param_convertors:
            path = path.replace("{" + param + "}", "00000000-0000-0000-0000-000000000000")
        method = sorted(methods)[0]
        response = client.request(
            method, path, json={}, headers={"X-CSRF-Token": csrf}
        )
        checked += 1
        if response.status_code != 403 or response.json().get("error", {}).get("code") != "impersonation_read_only":
            wrong.append(f"{method} {route.path} → {response.status_code} {response.text[:120]}")
    assert checked > 100, f"쓰기 라우트가 {checked}개뿐이다 — 앱이 제대로 안 떴다"
    assert not wrong, (
        "임퍼소네이션 중인데 막히지 않은(또는 다른 이유로 거절된) 쓰기 라우트가 있다:\n  "
        + "\n  ".join(wrong)
    )


def test_blocked_writes_are_counted(impersonating):
    """막힌 시도는 세어 둔다 — 0이 아니면 감사가 알아야 할 사실이다."""
    client, csrf, _ = impersonating
    for _ in range(3):
        client.post(
            "/api/admin/departments", json={"name": "몰래 만든 부서"},
            headers={"X-CSRF-Token": csrf},
        )
    state = client.get("/api/admin/impersonation/state").json()
    assert state["blocked_write_count"] >= 3


def test_stop_is_allowed_and_restores_the_actor(impersonating, client):
    client, csrf, _ = impersonating
    stopped = client.post("/api/admin/impersonation/stop", headers={"X-CSRF-Token": csrf})
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["ended"] is True
    # 종료 후에는 다시 관리자 자신이고, 쓰기도 된다.
    me = client.get("/api/me").json()["user"]
    assert me["role"] == "system_admin"
    created = client.post(
        "/api/admin/departments", json={"name": "정상 부서"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code in (200, 201), created.text
    # 멱등: 이미 끝났으면 200 이되 ended=False.
    again = client.post("/api/admin/impersonation/stop", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200 and again.json()["ended"] is False


# UB-03: 로그아웃은 IMPERSONATION_ALLOWED_WRITES에 있는 지원되는 종료 경로인데,
# 예전엔 세션 토큰만 폐기하고 ImpersonationSession의 ended_at/ended_reason을 안 남겨
# `GET /sessions?active=true`가 그 임퍼소네이션을 무기한 "진행 중"으로 보여줬다.
def test_logging_out_while_impersonating_ends_the_impersonation_session(
    impersonating, client, login_as
):
    client, csrf, target_id = impersonating
    logged_out = client.post("/logout", headers={"X-CSRF-Token": csrf})
    assert logged_out.status_code == 200, logged_out.text

    login_as("system_admin")
    sessions = client.get("/api/admin/impersonation/sessions").json()["items"]
    row = next(s for s in sessions if s["target_user_id"] == target_id)
    assert row["active"] is False, "로그아웃해도 임퍼소네이션이 '진행 중'으로 남는다"
    assert row["ended_reason"] == "logout"

    stops = client.get("/api/admin/audit?action=impersonation.stop").json()["items"]
    assert stops, "로그아웃으로 끝난 임퍼소네이션에 impersonation.stop 감사 기록이 없다"
    assert stops[0]["after"]["ended_reason"] == "logout"


def test_audit_records_the_admin_not_the_target(client, login_as, make_user):
    """감사 로그를 **다시 읽어** 행위자가 관리자인지 확인한다."""
    target = make_user(email="audited@goodmit.co.kr", role="user")
    target_id, target_email = target.id, target.email
    csrf = login_as("system_admin")
    admin_me = client.get("/api/me").json()["user"]

    assert _start_impersonation(client, csrf, target_id).status_code == 200
    client.post("/api/admin/impersonation/stop", headers={"X-CSRF-Token": csrf})

    logs = client.get("/api/admin/audit?action=impersonation.start").json()["items"]
    assert logs, "impersonation.start 감사 기록이 없다"
    assert logs[0]["user_id"] == admin_me["id"], "감사 행위자가 관리자가 아니다"
    assert logs[0]["object_id"] == target_id
    assert logs[0]["after"]["target_email"] == target_email

    stops = client.get("/api/admin/audit?action=impersonation.stop").json()["items"]
    assert stops and stops[0]["user_id"] == admin_me["id"]

    sessions = client.get("/api/admin/impersonation/sessions").json()["items"]
    assert sessions and sessions[0]["target_user_id"] == target_id
    assert sessions[0]["active"] is False
    assert sessions[0]["ended_reason"] == "manual"


def test_cannot_impersonate_equal_or_higher_role(client, login_as, make_user):
    other_admin = make_user(email="other-admin@goodmit.co.kr", role="admin")
    other_id = other_admin.id
    csrf = login_as("admin")
    response = _start_impersonation(client, csrf, other_id)
    assert response.status_code == 403
    assert "권한" in response.json()["error"]["message"]


def test_operator_cannot_impersonate(client, login_as, make_user):
    target = make_user(email="t2@goodmit.co.kr", role="user")
    target_id = target.id
    csrf = login_as("operator")
    assert _start_impersonation(client, csrf, target_id).status_code == 403


def test_out_of_scope_target_is_404_not_403(client, login_as, make_user, db):
    """범위 밖 단건은 존재를 노출하지 않는다 — 403 이 아니라 404 다."""
    from sqlalchemy import select

    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT, User

    mine = Department(name="내 부서")
    theirs = Department(name="남의 부서")
    db.add_all([mine, theirs])
    db.flush()
    mine_id, theirs_id = mine.id, theirs.id
    db.commit()

    target = make_user(email="elsewhere@goodmit.co.kr", role="user")
    target_id = target.id
    csrf = login_as("admin", email="dept-admin@goodmit.co.kr")

    admin = db.execute(
        select(User).where(User.email == "dept-admin@goodmit.co.kr")
    ).scalar_one()
    admin.admin_scope = ADMIN_SCOPE_DEPT
    admin.scope_dept_id = mine_id
    other = db.get(User, target_id)
    other.department_id = theirs_id
    db.commit()

    response = _start_impersonation(client, csrf, target_id)
    assert response.status_code == 404, response.text


def test_admin_is_rate_limited_after_too_many_distinct_targets(client, login_as, make_user, fake_clock):
    """남용 방지 (H3-a): 같은 관리자가 짧은 시간 안에 서로 다른 사용자를 너무 많이
    대리 보기하면 막는다.

    허용치를 넘는 (허용치+1)번째 **새로운** 대상은 429 로 거절되고, 재시도 대기 시간을
    함께 돌려준다. 창이 지나면 다시 허용된다.
    """
    from app.impersonation.service import (
        IMPERSONATION_RATE_LIMIT_MAX_TARGETS,
        IMPERSONATION_RATE_LIMIT_WINDOW_SECONDS,
    )

    csrf = login_as("system_admin")
    targets = [
        make_user(email=f"rl-target-{i}@goodmit.co.kr", role="user").id
        for i in range(IMPERSONATION_RATE_LIMIT_MAX_TARGETS + 1)
    ]

    for target_id in targets[:-1]:
        started = _start_impersonation(client, csrf, target_id)
        assert started.status_code == 200, started.text
        stopped = client.post("/api/admin/impersonation/stop", headers={"X-CSRF-Token": csrf})
        assert stopped.status_code == 200, stopped.text

    blocked = _start_impersonation(client, csrf, targets[-1])
    assert blocked.status_code == 429, blocked.text
    body = blocked.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["retry_after_seconds"] >= 1

    # 창이 지나면 다시 허용된다.
    fake_clock.advance(IMPERSONATION_RATE_LIMIT_WINDOW_SECONDS + 1)
    reopened = _start_impersonation(client, csrf, targets[-1])
    assert reopened.status_code == 200, reopened.text


def test_reentering_an_already_seen_target_does_not_count_against_the_limit(
    client, login_as, make_user
):
    """같은 대상을 다시 보는 것은(재확인) 남용이 아니다 — 창 안에서 몇 번을 다시 들어가도
    막히지 않는다."""
    from app.impersonation.service import IMPERSONATION_RATE_LIMIT_MAX_TARGETS

    csrf = login_as("system_admin")
    target_id = make_user(email="repeat-target@goodmit.co.kr", role="user").id

    for _ in range(IMPERSONATION_RATE_LIMIT_MAX_TARGETS + 2):
        started = _start_impersonation(client, csrf, target_id)
        assert started.status_code == 200, started.text
        stopped = client.post("/api/admin/impersonation/stop", headers={"X-CSRF-Token": csrf})
        assert stopped.status_code == 200, stopped.text


def _backdate_impersonation_start(db, *, target_id, seconds_ago):
    """세션 자신의 유휴/절대 타임아웃(기본값 둘 다 MAX_DURATION_SECONDS와 같은 30분)을
    건드리지 않고 임퍼소네이션의 '시작 시각'만 과거로 민다 — 전역 시계를 30분 이상
    돌리면 세션 자체가 유휴 만료로 먼저 401이 되어 이 항목이 검증하려는 것(임퍼소네이션
    자신의 최대 지속 시간 판정)에 닿지도 못한다."""
    from datetime import timedelta

    from app.impersonation.models import ImpersonationSession

    row = db.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.target_user_id == target_id,
            ImpersonationSession.ended_at.is_(None),
        )
    ).scalar_one()
    row.started_at = row.started_at - timedelta(seconds=seconds_ago)
    db.commit()
    return row


# CORE-09: 최대 지속 시간(30분) 검사 — 이전엔 전혀 테스트되지 않았다.
def test_impersonation_auto_ends_after_max_duration(impersonating, client, db):
    from app.impersonation.service import MAX_DURATION_SECONDS

    client, _csrf, target_id = impersonating
    _backdate_impersonation_start(db, target_id=target_id, seconds_ago=MAX_DURATION_SECONDS + 1)

    me = client.get("/api/me").json()["user"]
    assert me["id"] != target_id, "30분이 지났는데도 여전히 대상의 눈으로 보인다"
    assert me["role"] == "system_admin", "관리자 자신의 세션으로 안 돌아왔다"


def test_max_duration_still_applies_when_the_session_lost_track_of_the_row(
    impersonating, client, db
):
    """CORE-09: `record.impersonation_id`가 비어 있으면(낡았거나 다른 경로로 지워졌거나)
    `row is not None and expired(...)`가 통째로 건너뛰어져, 최대 지속 시간 검사 자체가
    무력화됐다 — `imp_service.end()`가 이미 `active_for_session()` 폴백을 두는 바로
    그 불일치 상황이다. `_impersonated_auth`도 같은 폴백을 쓰게 고쳤다."""
    from app.auth.models import UserSession
    from app.impersonation.service import MAX_DURATION_SECONDS

    client, _csrf, target_id = impersonating
    row = db.execute(
        select(UserSession).where(UserSession.impersonated_user_id == target_id)
    ).scalar_one()
    row.impersonation_id = None  # 세션이 자기 임퍼소네이션 행에 대한 포인터를 잃은 상태
    db.commit()
    _backdate_impersonation_start(db, target_id=target_id, seconds_ago=MAX_DURATION_SECONDS + 1)

    me = client.get("/api/me").json()["user"]
    assert me["id"] != target_id, "포인터를 잃었다는 이유로 최대 지속 시간 검사를 건너뛴다"
    assert me["role"] == "system_admin"


def test_switching_target_while_impersonating_is_rejected(impersonating, make_user):
    """(H3-b) 이미 대리 보기 중이면 다른 사람으로 바로 전환할 수 없다 — 먼저 종료해야 한다.

    `/start` 자체가 쓰기 라우트라 `app/core/deps.py::IMPERSONATION_ALLOWED_WRITES` 의
    읽기 전용 가드(403 `impersonation_read_only`)에 service 층보다 먼저 걸린다 —
    `service.start()` 의 `session.impersonated_user_id` 검사(409)는 그 뒤의 방어선이다.
    이미 있던 동작이라 여기서는 회귀 테스트로만 고정한다.
    """
    client, csrf, _target_id = impersonating
    other = make_user(email="other-target@goodmit.co.kr", role="user")
    response = _start_impersonation(client, csrf, other.id)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "impersonation_read_only"


def test_write_exemptions_are_real_routes_and_stay_minimal(app):
    """예외 목록은 **살아 있는 경로 두 개**뿐이어야 한다.

    두 가지를 함께 본다:
      * 없어진 경로가 목록에 남아 있으면, 나중에 누가 그 경로를 다시 만드는 날
        아무도 모르게 열린 채로 태어난다(실제로 `/api/auth/logout` 이 그런 유령이었다).
      * 목록이 늘어나면 그만큼 읽기 전용이 아니게 된다 — 늘리려면 이 테스트를 고쳐야 하고,
        그 순간 사람이 한 번 더 생각하게 된다.
    """
    from app.core.deps import IMPERSONATION_ALLOWED_WRITES

    write_paths = {
        r.path
        for r in app.routes
        if isinstance(r, APIRoute) and (r.methods - SAFE_METHODS)
    }
    ghosts = sorted(IMPERSONATION_ALLOWED_WRITES - write_paths)
    assert not ghosts, (
        "임퍼소네이션 쓰기 예외 목록에 존재하지 않는 경로가 있다 — 그 경로가 다시 생기는 날 "
        f"조용히 열린다: {ghosts}"
    )
    assert IMPERSONATION_ALLOWED_WRITES == frozenset(
        {"/api/admin/impersonation/stop", "/logout"}
    ), (
        "임퍼소네이션 중에 허용되는 쓰기 경로가 달라졌다. 늘리는 것은 읽기 전용 보장을 "
        "그만큼 깎는 일이다 — 정말 필요한지 확인하고 이 목록도 함께 고쳐라."
    )
