"""권한 게이트가 막은 **쓰기**는 감사 로그에 남는다 (app/core/deps.py).

## 무엇이 문제였나

권한 거부·검증 실패·충돌은 감사 테이블에 한 줄도 안 남았다. 실패를 남기는 장치는
`app/core/audit.py::audit_failure_on_exception` 하나뿐이었고 그것을 쓰는 라우터는 셋이라,
감사되는 실패는 사실상 `user.login_failed` 뿐이었다.

그래서 두 가지가 동시에 거짓이 됐다.

  * 이상 징후의 「실패가 몰려 있습니다」 소견은 스스로 「권한 부족을 반복해 시도했거나」라고
    적어 두고도 이 제품에서는 그 사건을 볼 수 없었다.
  * 감사 화면의 「문의 번호(요청 ID)」 필터는 오류 화면이 사람에게 보여 준 그 번호로
    언제나 0건이었다 — 그 번호가 붙은 요청이 감사에 없기 때문이다.

권한 상승 시도는 사고 조사에서 가장 먼저 찾는 신호다. 그것이 안 남는 것보다, 안 남으면서
「잡고 있다」고 적어 둔 화면이 더 나쁘다.

## 무엇을 고정하는가

  * 막힌 **쓰기**(POST·PATCH·PUT·DELETE)는 `auth.denied` 행을 남긴다. 행위자·요청 ID·
    경로가 함께 남아야 조사에 쓸 수 있다.
  * 막힌 **읽기**(GET)는 남기지 않는다. 권한 없는 화면을 열어 보는 것은 흔한 일이고,
    그것까지 남기면 목록이 그 잡음으로 덮여 진짜 사건이 묻힌다.
  * 그 행은 이상 징후의 `failure_burst` 가 실제로 센다 — 그러지 못하면 위 소견 문구는
    여전히 거짓말이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog

pytestmark = [pytest.mark.security, pytest.mark.integration]

DENIED = "auth.denied"


def _denied_rows(db) -> list[AuditLog]:
    return list(
        db.execute(select(AuditLog).where(AuditLog.action == DENIED)).scalars().all()
    )


def test_a_refused_write_is_audited_with_actor_path_and_request_id(client, login_as, db):
    """운영자가 관리자 전용 쓰기를 시도해 403 을 받으면 그 시도가 감사에 남는다."""
    csrf = login_as("operator", email="denied-write-op@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    response = client.post(
        "/api/admin/job-titles", json={"name": "권한 없는 직책"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403, response.text
    request_id = response.json()["error"]["request_id"]

    db.expire_all()
    rows = _denied_rows(db)
    assert len(rows) == 1, f"막힌 쓰기가 감사에 안 남았다: {rows}"
    row = rows[0]
    assert row.result == "failure"
    assert row.user_id == me["id"]
    assert row.object_type == "auth"
    assert row.request_id == request_id, (
        "오류 화면이 보여 준 문의 번호로 그 요청을 찾을 수 없다"
    )
    assert "/api/admin/job-titles" in (row.after_json or "")
    assert "POST" in (row.after_json or "")


def test_a_refused_read_is_not_audited(client, login_as, db):
    """반례 — 권한 없는 **조회**는 남기지 않는다. 이 시험이 없으면 위 시험은
    「모든 403 을 남긴다」로도 통과하고, 그러면 감사 목록이 조회 거부로 덮인다."""
    csrf = login_as("operator", email="denied-read-op@goodmit.co.kr")
    del csrf

    for _ in range(3):
        assert client.get("/api/admin/audit").status_code == 403

    db.expire_all()
    assert _denied_rows(db) == [], "조회 거부가 감사 로그에 남았다"


def test_an_allowed_write_leaves_no_denial_row(client, login_as, db):
    """반례 — 통과한 쓰기는 거부 행을 만들지 않는다(게이트가 항상 기록하는 것이 아니다)."""
    csrf = login_as("system_admin", email="allowed-write-admin@goodmit.co.kr")

    response = client.post(
        "/api/admin/job-titles", json={"name": "정상 직책"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text

    db.expire_all()
    assert _denied_rows(db) == [], "정상 쓰기가 권한 거부로 기록됐다"


def test_repeated_refused_writes_show_up_as_a_failure_burst(client, login_as, db, fake_clock):
    """소견 문구가 약속한 그대로다 — 「권한 부족을 반복해 시도」가 실제로 잡힌다.

    `failure_burst` 임계값은 5건이라(app/audit/anomalies.py) 그보다 한 건 더 시도한다.
    """
    from app.audit.anomalies import FAILURE_BURST_THRESHOLD, detect

    csrf = login_as("operator", email="denied-burst-op@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    attempts = FAILURE_BURST_THRESHOLD + 1
    for i in range(attempts):
        r = client.post(
            "/api/admin/job-titles", json={"name": f"막힌 직책 {i}"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 403

    db.expire_all()
    assert len(_denied_rows(db)) == attempts

    result = detect(db, now=fake_clock.now(), actor_ids=None)
    burst = [
        f for f in result["findings"]
        if f["kind"] == "failure_burst" and f["actor_id"] == me["id"]
    ]
    assert burst, f"막힌 쓰기가 실패 급증으로 안 잡혔다: {result['findings']}"
    assert burst[0]["count"] == attempts
    assert all(DENIED in e for e in burst[0]["evidence"])


def test_a_flood_of_refused_writes_cannot_grow_the_audit_log_without_bound(
    client, login_as, db, fake_clock
):
    """거부 하나마다 커밋된 쓰기 하나 — 그것을 아무 상한 없이 두면 인증만 한 저권한 계정이
    혼자서 감사 표를 부풀린다. 관리 라우트에는 리미터가 없어(로그인·채팅·퀴즈·도우미 넷뿐)
    `POST /api/admin/job-titles` 반복만으로 초당 수백 행이 쌓였다. 그러면 이 기능이 만들려던
    신호가 스스로 묻힌다 — 감사 목록도 실패 급증 소견도 그 잡음으로 덮인다.

    상한은 **신호를 지우지 않는 선**이다: `failure_burst` 임계값(5)보다 넉넉히 위다.
    """
    from app.audit.anomalies import FAILURE_BURST_THRESHOLD, detect
    from app.core.deps import DENIED_WRITE_AUDIT_BURST

    csrf = login_as("operator", email="denied-flood-op@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    attempts = DENIED_WRITE_AUDIT_BURST * 5
    for i in range(attempts):
        r = client.post(
            "/api/admin/job-titles", json={"name": f"쏟아붓는 직책 {i}"},
            headers={"X-CSRF-Token": csrf},
        )
        # 상한은 **기록**만 묶는다 — 막는 것은 그대로다.
        assert r.status_code == 403, r.text

    db.expire_all()
    rows = _denied_rows(db)
    assert len(rows) < attempts, (
        f"거부 {attempts}건이 그대로 {len(rows)}행이 됐다 — 감사 표에 상한이 없다"
    )
    assert len(rows) >= FAILURE_BURST_THRESHOLD, (
        f"상한이 탐지에 필요한 신호까지 지웠다: {len(rows)}행"
    )

    # 그리고 그 신호는 여전히 소견으로 선다 — 묶은 것이지 삼킨 것이 아니다.
    burst = [
        f for f in detect(db, now=fake_clock.now(), actor_ids=None)["findings"]
        if f["kind"] == "failure_burst" and f["actor_id"] == me["id"]
    ]
    assert burst, "상한을 넣었더니 실패 급증이 안 잡힌다"
