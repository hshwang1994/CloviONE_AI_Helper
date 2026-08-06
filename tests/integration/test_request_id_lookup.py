"""오류의 상관 id 로 **그 요청을 실제로 찾을 수 있다** (Z8).

배관은 처음부터 다 있었다 — 미들웨어가 요청마다 id 를 만들어 전파하고 `X-Request-ID` 로
돌려주며, 오류 봉투에도 넣고, 감사 로그도 그 값을 저장한다. 그런데 **양 끝이 끊겨 있었다**:

  * 감사 화면은 그 값을 상세 패널에 **보여 주기만 하고 그것으로 찾을 수가 없었다**,
  * 프런트는 응답에서 그 값을 한 번도 읽지 않아 **어느 오류 화면에도 번호가 없었다**.

그래서 새벽 3시에 "화면이 안 나와요" 를 받으면 운영자에게 남는 단서는 경로와 상태 코드뿐이었다.
이 테스트는 서버 쪽 두 입구(목록·CSV)를 고정한다. 화면 쪽은 `kit.jsx` 의 '문의 번호' 다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

RID = "abc123def456abc123def456abc12345"


def _log(app, *, request_id, action="user.update"):
    from app.audit.models import AuditLog

    with app.state.session_factory() as db:
        db.add(AuditLog(action=action, object_type="user", object_id="u1",
                        result="success", request_id=request_id))
        db.commit()


def test_the_error_envelope_and_header_both_carry_the_id(client, login_as):
    """화면이 읽을 수 있게 **봉투와 헤더 둘 다**에 있어야 한다 —
    봉투를 만들기 전에 터지는 오류(프록시)는 본문이 없다."""
    login_as("admin")
    # 없는 경로를 쓴다 — 도메인 라우트는 픽스처(가짜 Notion) 때문에 200 이 날 수 있어
    # 이 테스트가 무엇을 재는지 흐려진다. 여기서 볼 것은 **오류 봉투에 id 가 실리는가** 다.
    r = client.get("/api/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers.get("X-Request-ID"), "응답 헤더에 요청 id 가 없다"
    assert (r.json().get("error") or {}).get("request_id"), "오류 봉투에 요청 id 가 없다"


def test_you_can_find_the_audit_row_by_that_id(client, login_as, app):
    login_as("system_admin")
    _log(app, request_id=RID)
    _log(app, request_id="ffffffffffffffffffffffffffffffff", action="user.create")

    body = client.get(f"/api/admin/audit?request_id={RID}").json()
    assert body["total"] == 1, f"문의 번호로 좁혀지지 않는다(total={body['total']})"
    assert body["items"][0]["request_id"] == RID


def test_the_csv_export_uses_the_same_filter(client, login_as, app):
    """목록과 CSV 의 필터 집합이 어긋나면 **화면에서 좁혀 놓고 내보낸 파일이 다른 데이터**가
    된다. 그 계약은 `audit/router.py` docstring 이 못박아 놨고, 새 필터를 목록에만 붙이면
    그 파일에서만 조용히 깨진다."""
    login_as("system_admin")
    _log(app, request_id=RID)
    _log(app, request_id="ffffffffffffffffffffffffffffffff", action="user.create")

    text = client.get(f"/api/admin/audit/export.csv?request_id={RID}").text
    assert RID in text
    assert "ffffffffffffffffffffffffffffffff" not in text, "CSV 가 필터를 무시하고 전체를 내보냈다"
