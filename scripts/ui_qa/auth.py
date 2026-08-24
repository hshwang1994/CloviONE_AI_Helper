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
from urllib.parse import urlsplit

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
        return {"email": DEFAULT_EMAIL, "password": env_password, "source": "env",
                "role": os.environ.get("UI_QA_ROLE") or None}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("email") and data.get("password"):
            data.setdefault("source", "cache")
            return data
    return None


def _save_credentials(path: Path, email: str, password: str, role: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"email": email, "password": password, "role": role},
                   ensure_ascii=False, indent=2),
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


def is_local_target(base_url: str) -> bool:
    """겨누는 서버가 **이 저장소의 DB 를 쓰는** 로컬 서버인가."""
    host = (urlsplit(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", ""}


def _provision(email: str, initial_password: str, log, *, base_url: str, role: str) -> None:
    """Create the account, or reset it to a password we know.

    Both paths leave ``must_change_password=True`` (app/users/service.py
    create_user / admin_reset_password), which the caller resolves through the
    real /change-password screen.

    🔴 **원격 서버를 겨눌 때는 절대 하지 않는다.** `user_cli` 는 `cwd=REPO_ROOT` 로 돌아
    **이 저장소의 로컬 SQLite** 를 고친다. 원격 대상에 대고 부르면 로컬 DB 에 계정을 만들고
    rc=0 을 돌려주므로 하네스가 **"계정 생성 → 생성됨"** 이라고 보고한 뒤 원격 로그인에서
    실패한다 — 아무것도 안 하고 성공을 보고하는 최악의 실패다(실제로 `qa-user`·`qa-auditor`
    실행이 이렇게 죽었고, 그 사이 로컬 개발 DB 에 QA 계정이 쌓였다).
    원격에서는 사람이 서버에서 직접 만들어야 한다.
    """
    if not is_local_target(base_url):
        raise AuthError(
            f"원격 대상({base_url})에는 계정을 만들 수 없습니다 — `user_cli` 는 로컬 DB 만 고칩니다.\n"
            f"서버에서 직접 실행하세요:\n"
            # 🔴 이 안내가 **옛 slug** 를 부르고 있었다(`clovirone-web` ·
            # `/opt/clovirone-web-assistant`). S3·S4 가 제품 정체성을 옮긴 뒤로 그 경로는
            # 서버에 없다 — 안내를 그대로 따라 하면 «그런 사용자가 없습니다» 로 끝난다.
            # 실행 자리는 `/opt/clovirassist` 이고, `user_cli` 는 서비스 환경(DATABASE_URL 등)
            # 없이는 DB 에 못 붙으므로 그것까지 함께 적는다.
            f"  ssh <server> \"cd /opt/clovirassist && sudo -u clovirassist \\\n"
            f"    env \\$(sudo grep -E '^(DATABASE_URL|APP_ENV|SECRETS_DIR|DATA_DIR)=' \\\n"
            f"      /etc/clovirassist/clovirassist.env | tr '\\\\n' ' ') \\\n"
            f"    venv/bin/python -m app.cli.user_cli passwd --email {email}\"\n"
            f"  (비밀번호는 stdin 으로만 넘어간다. 계정이 보관 상태면 먼저 `unarchive` 다.)\n"
            f"그런 다음 UI_QA_EMAIL / UI_QA_PASSWORD 로 다시 실행하세요."
        )
    if _user_exists(email):
        log(f"[auth] 기존 계정 발견 → 비밀번호 재설정: {email}")
        # `passwd` 에는 `add` 와 달리 --password-stdin 플래그가 없다. --temp 를 주지 않으면
        # **항상** stdin 에서 읽는다(app/cli/user_cli.py::cmd_passwd). 없는 플래그를 붙이면
        # argparse 가 rc=2 로 죽고 하네스는 "세션을 만들지 못했습니다"로만 끝난다 —
        # 저장된 세션이 만료되는 순간 전 라우트 캡처가 통째로 막혔다.
        proc = _run_cli(["passwd", "--email", email], initial_password + "\n")
    else:
        log(f"[auth] 계정 생성(user_cli add): {email} role={role}")
        proc = _run_cli(
            ["add", "--email", email, "--name", DEFAULT_NAME,
             "--role", role, "--password-stdin"],
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


def _dismiss_tour(context, base_url: str, log) -> None:
    """VIS-32: `scripts/ui_qa/*.py` 전체에 `tour` 참조가 0건이었다 — QA 계정의
    `tour_completed_at`이 영영 안 채워져 캡처마다 온보딩 모달이 홈을 덮었고, 그 뒤에
    깔린 실제 화면은 하네스가 한 번도 검사하지 못했다(21종 기계 검사는 전부 통과했는데도).
    `POST /api/me/tour`(app/profiles/router.py)는 멱등이라(재요청해도 그냥 같은 상태를
    다시 쓴다) 캐시된 세션 재사용 경로에서도 매번 불러도 무해하다. CSRF 토큰은 이 호출
    전용으로 `/api/me`에서 새로 받는다(`app/profiles/router.py::me`의 응답 최상위
    `csrf_token` — `_fetch_me`가 돌려주는 `user` 서브트리 밖에 있어 따로 읽는다).
    """
    try:
        me_response = context.request.get(f"{base_url.rstrip('/')}/api/me", timeout=LOGIN_TIMEOUT_MS)
        csrf_token = me_response.json().get("csrf_token") if me_response.status == 200 else None
        if not csrf_token:
            log("[auth] 투어 해제 건너뜀(csrf_token을 못 읽음) — 캡처에 온보딩 모달이 남을 수 있음")
            return
        response = context.request.post(
            f"{base_url.rstrip('/')}/api/me/tour",
            data={"action": "complete"},
            headers={"X-CSRF-Token": csrf_token},
            timeout=LOGIN_TIMEOUT_MS,
        )
        if response.status != 200:
            log(f"[auth] 투어 해제 실패(status={response.status}) — 캡처에 온보딩 모달이 남을 수 있음")
    except Exception as exc:  # noqa: BLE001 — 캡처 자체를 막을 이유는 아니다, 경고만 남긴다
        log(f"[auth] 투어 해제 요청 실패({exc}) — 캡처에 온보딩 모달이 남을 수 있음")


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def ensure_session(browser, base_url: str, out_dir: Path, *, rebuild: bool = False,
                   log=print, insecure: bool = False, role: str | None = None) -> QaSession:
    """Return a QaSession backed by a validated storage_state.json.

    ``out_dir`` is ``dist/ui-qa`` — the cache is shared across ``--label`` runs
    so a PRE and a POST run reuse the same account and the same session.

    ``role`` (QA-05) lets a caller target a role other than the default
    ``system_admin`` — needed to actually exercise menu visibility/403 dead
    ends for lower-privileged roles (``Route.visible_to`` in ``routes.py``
    already has the metadata for this; nothing had ever driven it with a
    non-default role). Defaults to ``DEFAULT_ROLE`` when omitted, so every
    existing caller (the ``verify_pa_rc_*.py`` scripts, a plain ``run.py``
    invocation) behaves exactly as before. A non-default role gets its own
    email (``ui-qa-<role>@...``) so it provisions a distinct, stable account
    instead of fighting over the same one — pass a role-scoped ``out_dir``
    too (``run.py`` does) so its session cache doesn't collide with another
    role's either. Either way, a cache whose actual role doesn't match what
    was asked for is treated as invalid rather than silently returned.
    """
    resolved_role = role or DEFAULT_ROLE
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "storage_state.json"
    meta_path = out_dir / "session.json"
    creds_path = out_dir / "credentials.json"

    # 1. cached session still good?
    if not rebuild and state_path.exists() and meta_path.exists():
        context = browser.new_context(storage_state=str(state_path),
                                      ignore_https_errors=insecure)
        try:
            user = _fetch_me(context, base_url)
            if user:
                _dismiss_tour(context, base_url, log)
        finally:
            context.close()
        if user and user["role"] != resolved_role:
            log(f"[auth] 캐시된 세션의 역할이 다름(요청 {resolved_role}, 캐시 {user['role']}) → 재로그인")
            user = None
        if user:
            log(f"[auth] 캐시된 세션 재사용: {user['email']} (role={user['role']})")
            return QaSession(email=user["email"], user_id=user["id"], role=user["role"],
                             display_name=user.get("display_name") or "",
                             storage_state=str(state_path))
        log("[auth] 캐시된 세션 만료 → 재로그인")

    creds = _load_credentials(creds_path)
    default_email = DEFAULT_EMAIL if resolved_role == DEFAULT_ROLE else f"ui-qa-{resolved_role}@goodmit.co.kr"
    # 위 세션 캐시와 같은 이유의 안전장치: 이 out_dir에 다른 역할(또는 UI_QA_PASSWORD로
    # DEFAULT_EMAIL을 강제한 이전 실행)의 자격증명이 남아 있으면 이번에 요청한 역할과 다른
    # 계정으로 조용히 로그인하게 된다 — 이메일이 이번 역할의 기대값과 다르면 버린다.
    # `role` 을 선언한 자격증명은 이름 규칙을 면제한다 — 실제 계정(Notion 매핑이 있는)으로
    # 찍어야 `내 …` 화면에 실데이터가 나오는데, 그런 계정의 이메일은 `ui-qa-…` 규칙과 다르다.
    # 선언이 없으면 예전 그대로 이름으로 판정한다.
    declared_role = (creds or {}).get("role")
    if creds and declared_role and declared_role != resolved_role:
        log(f"[auth] 자격증명이 선언한 역할({declared_role})이 요청 역할({resolved_role})과 다름 → 새로 프로비저닝")
        creds = None
    elif creds and not declared_role and creds.get("email") and creds["email"] != default_email:
        log(f"[auth] 캐시된 자격증명({creds['email']})이 요청 역할({resolved_role})과 안 맞음 → 새로 프로비저닝")
        creds = None
    email = (creds or {}).get("email") or default_email
    password = (creds or {}).get("password")

    context = browser.new_context(ignore_https_errors=insecure)
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
            _provision(email, initial, log, base_url=base_url, role=resolved_role)
            _submit_login(page, base_url, email, initial)
            # user_cli always forces a first-login change; complete it for real.
            _complete_forced_change(page, base_url, initial, final)
            password = final
            _save_credentials(creds_path, email, final, resolved_role)
            log(f"[auth] 최초 로그인 + 비밀번호 변경 완료 → {creds_path}")

        user = _fetch_me(context, base_url)
        if not user:
            raise AuthError("로그인은 됐지만 /api/me가 인증을 인정하지 않습니다.")
        if user.get("must_change_password"):
            # 여기서 그냥 죽으면 **원격 서버를 겨눈 실행이 통째로 불가능하다.**
            #
            # 강제 변경 해제는 지금까지 `_provision` 경로에만 있었다. 그 경로는 로컬
            # `python -m app.cli.user_cli` 를 부르므로 **로컬 DB 에만 통한다.** 서버를 겨눌 때는
            # 계정을 서버에서 미리 만들어 두고 UI_QA_EMAIL/UI_QA_PASSWORD 로 로그인하는데,
            # `user_cli add` 도 `passwd` 도 항상 must_change_password=True 로 남기기 때문에
            # (app/users/service.py) 로그인은 되지만 여기서 예외로 끝났다.
            #
            # 로그인에 성공했다는 것은 현재 비밀번호를 알고 있다는 뜻이므로, 실제 화면으로
            # 변경을 끝내면 된다 — 프로비저닝 경로가 하던 것과 같은 일이다.
            if not password:
                raise AuthError(
                    "계정이 비밀번호 변경 강제 상태인데 현재 비밀번호를 모릅니다"
                    "(캐시된 세션만 있고 자격증명이 없음). --rebuild-auth 로 다시 시도하세요.")
            changed = _generate_password()
            log(f"[auth] 계정이 비밀번호 변경 강제 상태 → 변경 화면에서 해제: {email}")
            _complete_forced_change(page, base_url, password, changed)
            password = changed
            _save_credentials(creds_path, email, changed, resolved_role)
            user = _fetch_me(context, base_url)
            if not user:
                raise AuthError("비밀번호는 바꿨는데 /api/me가 인증을 인정하지 않습니다.")
            if user.get("must_change_password"):
                raise AuthError("비밀번호를 바꿨는데도 강제 변경 상태가 풀리지 않았습니다.")
        _dismiss_tour(context, base_url, log)
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
    parser.add_argument("--role", default=None,
                        help=f"기본 {DEFAULT_ROLE} — 다른 역할(user/operator/auditor/admin)로 "
                             "세션을 만든다(QA-05)")
    args = parser.parse_args(argv)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            session = ensure_session(browser, args.base_url, Path(args.out_dir),
                                     rebuild=args.rebuild, role=args.role)
        finally:
            browser.close()
    print(json.dumps(session.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
