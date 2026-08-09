"""`get_page_auth` shares the same impersonation write-guard as
`get_current_auth` (CORE-08).

`get_current_auth`'s own docstring explains why the guard lives in one
shared dependency instead of on each router: a new call site that
duplicates the auth-loading logic instead of reusing it silently reopens
the write bypass it exists to close. `get_page_auth` did exactly that —
it duplicated `_load_auth` handling but left out both the write guard and
`request.state.actor`. Harmless today only because every current page
route built on it is a GET; this test proves the dependency itself is
safe for the first POST page route that gets built on it, rather than
relying on "no caller happens to trigger it yet."
"""

from __future__ import annotations

import pytest
from fastapi import Depends, Request

from app.core.deps import AuthContext, get_page_auth

pytestmark = pytest.mark.security


def _mount_write_probe(app):
    @app.post("/__test_page_write_probe")
    def _write_probe(auth: AuthContext = Depends(get_page_auth)):
        return {"ok": True}


def _mount_read_probe(app):
    @app.get("/__test_page_read_probe")
    def _read_probe(request: Request, auth: AuthContext = Depends(get_page_auth)):
        # request.state.actor는 감사 기록이 "누가 했는가"를 결정하는 값이다
        # (record_audit_from_request가 이걸 읽는다) — auth.actor가 아니라 여기서
        # 확인해야 CORE-08이 실제로 고친 지점(핸들러가 request.state에서 읽는 경로)을
        # 검증한다.
        return {"actor_id": getattr(request.state, "actor", None) and request.state.actor.id}

    return app


def test_page_auth_blocks_writes_while_impersonating(app, client, login_as, make_user):
    _mount_write_probe(app)
    target = make_user(email="page-auth-target@goodmit.co.kr", role="user")
    csrf = login_as("system_admin")
    started = client.post(
        "/api/admin/impersonation/start",
        json={"user_id": target.id, "reason": "CORE-08 probe"},
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 200, started.text

    r = client.post("/__test_page_write_probe")
    assert r.status_code == 403, (
        f"get_page_auth를 쓰는 POST 라우트가 임퍼소네이션 중 쓰기 차단을 안 받는다: {r.text}"
    )
    assert r.json()["error"]["code"] == "impersonation_read_only"


def test_page_auth_sets_request_state_actor_while_impersonating(
    app, client, login_as, make_user
):
    """`request.state.actor`가 없으면(빠뜨리면) 이 경로로 만들어질 미래의 감사 기록이
    대상자에게 귀속된다 — 행위자는 항상 관리자 자신이어야 한다."""
    _mount_read_probe(app)
    target = make_user(email="page-auth-actor-target@goodmit.co.kr", role="user")
    admin_csrf = login_as("system_admin")
    admin_id = client.get("/api/me").json()["user"]["id"]
    started = client.post(
        "/api/admin/impersonation/start",
        json={"user_id": target.id, "reason": "CORE-08 actor probe"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert started.status_code == 200, started.text

    r = client.get("/__test_page_read_probe")
    assert r.status_code == 200, r.text
    assert r.json()["actor_id"] == admin_id, (
        "임퍼소네이션 중 request.state.actor가 관리자 자신이 아니다 — 감사 귀속이 대상자로 샌다"
    )
