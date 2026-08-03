"""Build (and cache) a Playwright ``storage_state`` for a real logged-in session.

Without this every hash route just bounces to ``/login`` (app/core/deps.py
``PageAuthRequired`` -> app/main.py redirect), so the whole harness would only
ever screenshot the login page.

What it does, in order:

1. Reuse ``dist/ui-qa/storage_state.json`` if ``GET /api/me`` still answers 200
   with it (sessions have an idle timeout — app/core/config.py
   ``session_idle_timeout_seconds``).
2. Otherwise log in for real against the running server through the
   server-rendered ``/login`` form (app/auth/router.py + app/static/js/login.js).
3. If the account does not exist yet, create it with the project's own CLI —
   ``python -m app.cli.user_cli add`` — never by touching the DB directly.
   That CLI always sets ``must_change_password=True``, so the harness then
   completes the real ``/change-password`` flow (app/auth/router.py:508) to
   land on a stable password.

Credentials live in ``dist/ui-qa/credentials.json`` (dist/ is gitignored) and
are generated randomly on first use; override with the ``UI_QA_EMAIL`` /
``UI_QA_PASSWORD`` environment variables.
"""

from __future__ import annotations

import json
import os
import secrets
import string
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# app/core/config.py -> allowed_email_domains (default "goodmit.co.kr"); a user
# outside the allowed domain is rejected by app/users/service.py create_user.
DEFAULT_EMAIL = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
DEFAULT_NAME = os.environ.get("UI_QA_NAME", "UI QA")
# system_admin so that every RequireRole/SCREEN_ROLES gate in App.jsx passes and
# the /admin shell does not redirect us to the user console.
DEFAULT_ROLE = os.environ.get("UI_QA_ROLE", "system_admin")

LOGIN_TIMEOUT_MS = 20_000


class AuthError(RuntimeError):
    """The harness could not obtain a usable session — never silently ignored."""


@dataclass(frozen=True)
class QaSession:
    email: str
    user_id: str
    role: str
    display_name: str
    storage_state: str  # absolute path to storage_state.json

    def to_json(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# password + credential handling
# --------------------------------------------------------------------------- #
def _generate_password() -> str:
    """Satisfies the default policy (min_length=12, min_classes=3) with margin."""
    pools = (string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*-_=+")
    chars = [secrets.choice(p) for p in pools]
    alphabet = "".join(pools)
    chars += [secrets.choice(alphabet) for _ in range(12)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _load_credentials(path: Path) -> dict | None:
    env_password = os.environ.get("UI_QA_PASSWORD")
    if env_password:
        return {"email": DEFAULT_EMAIL, "password": env_password, "source": "env"}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("email") and data.get("password"):
            data.setdefault("source", "cache")
            return data
    return None


def _save_credentials(path: Path, email: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"email": email, "password": password}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# project CLI wrappers (never touch the DB directly)
# --------------------------------------------------------------------------- #
def _run_cli(args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "app.cli.user_cli", *args],
        cwd=str(REPO_ROOT), input=stdin_text, capture_output=True,
        text=True, encoding="utf-8", errors="replace", env=env, check=False,
    )


def _user_exists(email: str) -> bool:
    return _run_cli(["show", "--email", email]).returncode == 0


def _provision(email: str, initial_password: str, log) -> None:
    """Create the account, or reset it to a password we know.

    Both paths leave ``must_change_password=True`` (app/users/service.py
    create_user / admin_reset_password), which the caller resolves through the
    real /change-password screen.
    """
    if _user_exists(email):
        log(f"[auth] 기존 계정 발견 → 비밀번호 재설정: {email}")
        proc = _run_cli(["passwd", "--email", email, "--password-stdin"], initial_password + "\n")
    else:
        log(f"[auth] 계정 생성(user_cli add): {email} role={DEFAULT_ROLE}")
        proc = _run_cli(
            ["add", "--email", email, "--name", DEFAULT_NAME,
             "--role", DEFAULT_ROLE, "--password-stdin"],
            initial_password + "\n",
        )
    if proc.returncode != 0:
        raise AuthError(
            "user_cli 실패 (rc=%s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout.strip(), proc.stderr.strip())
        )
    log("[auth] " + (proc.stdout.strip().splitlines() or ["(no output)"])[0])


# --------------------------------------------------------------------------- #
# browser login
# --------------------------------------------------------------------------- #
def _submit_login(page, base_url: str, email: str, password: str) -> str:
    """Drive the real /login form. Returns the URL we landed on."""
    page.goto(f"{base_url.rstrip('/')}/login", wait_until="domcontentloaded",
              timeout=LOGIN_TIMEOUT_MS)
    page.wait_for_selector("#login-form", timeout=LOGIN_TIMEOUT_MS)
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#login-submit")
    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=LOGIN_TIMEOUT_MS)
    except Exception as exc:  # still on /login -> surface the form's own message
        message = ""
        try:
            message = (page.text_content("#login-error") or "").strip()
        except Exception:
            pass
        raise AuthError(f"로그인 실패: {message or exc}") from exc
    return page.url


def _complete_forced_change(page, base_url: str, current: str, new: str) -> None:
    """Finish the mandatory password change (app/templates_html/change_password.html)."""
    if "/change-password" not in page.url:
        page.goto(f"{base_url.rstrip('/')}/change-password",
                  wait_until="domcontentloaded", timeout=LOGIN_TIMEOUT_MS)
    page.wait_for_selector("#cp-form", timeout=LOGIN_TIMEOUT_MS)
    page.fill("#current-password", current)
    page.fill("#new-password", new)
    page.fill("#confirm-password", new)
    page.wait_for_function("() => !document.getElementById('cp-submit').disabled",
                           timeout=LOGIN_TIMEOUT_MS)
    page.click("#cp-submit")
    try:
        page.wait_for_url(lambda url: "/change-password" not in url, timeout=LOGIN_TIMEOUT_MS)
    except Exception as exc:
        message = ""
        try:
            message = (page.text_content("#cp-error") or "").strip()
        except Exception:
            pass
        raise AuthError(f"비밀번호 변경 실패: {message or exc}") from exc


def _fetch_me(context, base_url: str) -> dict | None:
    """GET /api/me with the context's cookies. None when unauthenticated."""
    try:
        response = context.request.get(f"{base_url.rstrip('/')}/api/me", timeout=LOGIN_TIMEOUT_MS)
    except Exception:
        return None
    if response.status != 200:
        return None
    try:
        return response.json().get("user")
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def ensure_session(browser, base_url: str, out_dir: Path, *, rebuild: bool = False,
                   log=print) -> QaSession:
    """Return a QaSession backed by a validated storage_state.json.

    ``out_dir`` is ``dist/ui-qa`` — the cache is shared across ``--label`` runs
    so a PRE and a POST run reuse the same account and the same session.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "storage_state.json"
    meta_path = out_dir / "session.json"
    creds_path = out_dir / "credentials.json"

    # 1. cached session still good?
    if not rebuild and state_path.exists() and meta_path.exists():
        context = browser.new_context(storage_state=str(state_path))
        try:
            user = _fetch_me(context, base_url)
        finally:
            context.close()
        if user:
            log(f"[auth] 캐시된 세션 재사용: {user['email']} (role={user['role']})")
            return QaSession(email=user["email"], user_id=user["id"], role=user["role"],
                             display_name=user.get("display_name") or "",
                             storage_state=str(state_path))
        log("[auth] 캐시된 세션 만료 → 재로그인")

    creds = _load_credentials(creds_path)
    email = (creds or {}).get("email") or DEFAULT_EMAIL
    password = (creds or {}).get("password")

    context = browser.new_context()
    page = context.new_page()
    try:
        logged_in = False
        if password:
            try:
                _submit_login(page, base_url, email, password)
                logged_in = True
                log(f"[auth] 저장된 비밀번호로 로그인 성공: {email}")
            except AuthError as exc:
                log(f"[auth] 저장된 비밀번호로 로그인 실패 ({exc}) → 계정 재프로비저닝")

        if not logged_in:
            initial = _generate_password()
            final = _generate_password()
            _provision(email, initial, log)
            _submit_login(page, base_url, email, initial)
            # user_cli always forces a first-login change; complete it for real.
            _complete_forced_change(page, base_url, initial, final)
            password = final
            _save_credentials(creds_path, email, final)
            log(f"[auth] 최초 로그인 + 비밀번호 변경 완료 → {creds_path}")

        user = _fetch_me(context, base_url)
        if not user:
            raise AuthError("로그인은 됐지만 /api/me가 인증을 인정하지 않습니다.")
        if user.get("must_change_password"):
            raise AuthError("계정이 여전히 비밀번호 변경 강제 상태입니다.")
        context.storage_state(path=str(state_path))
        session = QaSession(email=user["email"], user_id=user["id"], role=user["role"],
                            display_name=user.get("display_name") or "",
                            storage_state=str(state_path))
        meta_path.write_text(json.dumps(session.to_json(), ensure_ascii=False, indent=2),
                             encoding="utf-8")
        log(f"[auth] storage_state 저장: {state_path} (role={session.role})")
        return session
    finally:
        page.close()
        context.close()


def main(argv: list[str] | None = None) -> int:
    """``python -m scripts.ui_qa.auth`` — build/refresh the session on its own."""
    import argparse

    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="UI QA 세션(storage_state) 생성")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "dist" / "ui-qa"))
    parser.add_argument("--rebuild", action="store_true", help="캐시를 무시하고 다시 로그인")
    args = parser.parse_args(argv)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            session = ensure_session(browser, args.base_url, Path(args.out_dir),
                                     rebuild=args.rebuild)
        finally:
            browser.close()
    print(json.dumps(session.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
