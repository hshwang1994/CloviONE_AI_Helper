"""Injection, traversal, and open-redirect checks (spec §31.10)."""

import pytest

pytestmark = pytest.mark.security


def test_sql_injection_in_user_search_is_safe(client, login_as, make_user):
    make_user("legit@goodmit.co.kr", display_name="정상 사용자")
    csrf = login_as("admin")
    # Classic injection payloads via the search param — parameterized queries
    # must treat these as literal strings, never execute them.
    for payload in ["' OR '1'='1", "'; DROP TABLE users;--", "%' UNION SELECT * FROM users--"]:
        r = client.get("/api/admin/users", params={"q": payload}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200
        # Injection must not leak all users; the odd string matches nothing.
        assert r.json()["total"] == 0
    # Table still intact.
    r = client.get("/api/admin/users", headers={"X-CSRF-Token": csrf})
    assert r.json()["total"] >= 1


def test_sql_injection_in_audit_filter_is_safe(client, login_as):
    login_as("auditor")
    r = client.get("/api/admin/audit", params={"action": "' OR 1=1--"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_static_path_traversal_blocked(client):
    # StaticFiles must not serve files outside the static dir.
    for attack in [
        "/static/../main.py",
        "/static/..%2f..%2fmain.py",
        "/static/....//....//app/main.py",
    ]:
        r = client.get(attack)
        assert r.status_code in (400, 404), f"{attack} -> {r.status_code}"
        assert "create_app" not in r.text


def test_secret_ref_path_traversal_rejected(settings):
    from app.core.secret_refs import FileSecretReferenceProvider, InvalidSecretRefError

    provider = FileSecretReferenceProvider(settings.secrets_dir)
    for evil in ["../../../etc/passwd", "..\\..\\windows\\system32", "/etc/shadow"]:
        with pytest.raises(InvalidSecretRefError):
            provider.get(evil)


def test_no_open_redirect_on_login_page(client, login_as):
    # The app never honors a user-supplied redirect target; already-authed users
    # go to "/" only, unauthenticated page access goes to "/login" only.
    login_as("user")
    r = client.get("/login?next=https://evil.example.com", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"  # not the attacker URL


def test_page_auth_redirect_is_fixed_target(client):
    # The PageAuthRequired handler (app/main.py) derives its own ?next= from the
    # REQUEST'S PATH ONLY ("/") — it never reads or forwards a caller-supplied
    # "next" query param, so an attacker-controlled "?next=https://evil..." on
    # the original request has no effect on where the eventual post-login
    # redirect points (still validated same-origin-relative in auth/router.py).
    r = client.get("/?next=https://evil.example.com", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2F"


def test_safe_next_path_rejects_backslash_bypass():
    # CWE-601: browsers treat a leading "/\" exactly like "//" when resolving a
    # relative URL against an http(s) origin (WHATWG URL special-scheme parsing),
    # so "/\evil.example.com" is a protocol-relative open redirect that a naive
    # "startswith('//')" check misses entirely.
    from app.core.urls import safe_next_path

    for evil in ["/\\evil.example.com", "/\\/evil.example.com", "//evil.example.com"]:
        assert safe_next_path(evil) is None
    assert safe_next_path("/dashboard") == "/dashboard"


def test_login_get_rejects_backslash_bypass_next(client):
    r = client.get("/login?next=%2F%5Cevil.example.com", follow_redirects=False)
    assert r.status_code == 200
    assert "evil.example.com" not in r.text
