"""CLI tests (spec §29) — run the real module in a subprocess against the test DB."""

import os
import subprocess
import sys

import pytest

from tests.conftest import PROJECT_ROOT

pytestmark = pytest.mark.integration


def run_cli(db_path, *args, stdin: str | None = None):
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "SESSION_SECRET": "cli-test-secret",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-m", "app.cli.user_cli", *args],
        cwd=PROJECT_ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def test_cli_add_prints_temp_password_once(db_path):
    result = run_cli(
        db_path, "add", "--email", "cli-user@goodmit.co.kr", "--name", "CLI사용자"
    )
    assert result.returncode == 0, result.stderr
    assert "temp_password:" in result.stdout
    assert "cli-user@goodmit.co.kr" in result.stdout


def test_cli_add_duplicate_fails_with_message(db_path):
    assert run_cli(db_path, "add", "--email", "dup@goodmit.co.kr", "--name", "중복").returncode == 0
    result = run_cli(db_path, "add", "--email", "dup@goodmit.co.kr", "--name", "중복")
    assert result.returncode == 1
    assert "이미 등록된 이메일" in result.stderr


def test_cli_list_and_show(db_path):
    run_cli(db_path, "add", "--email", "shown@goodmit.co.kr", "--name", "표시됨", "--role", "operator")
    listed = run_cli(db_path, "list")
    assert "shown@goodmit.co.kr" in listed.stdout
    shown = run_cli(db_path, "show", "--email", "shown@goodmit.co.kr")
    assert "role: operator" in shown.stdout


def test_cli_password_stdin_never_argv(db_path):
    result = run_cli(
        db_path,
        "add", "--email", "stdinpw@goodmit.co.kr", "--name", "표준입력",
        "--password-stdin",
        stdin="Cli-Chosen-Pass-1!\n",
    )
    assert result.returncode == 0, result.stderr
    assert "temp_password" not in result.stdout


def test_cli_set_role_guards_last_system_admin(db_path):
    run_cli(db_path, "add", "--email", "onlyadmin@goodmit.co.kr", "--name", "유일관리자", "--role", "system_admin")
    result = run_cli(db_path, "set-role", "--email", "onlyadmin@goodmit.co.kr", "--role", "user")
    assert result.returncode == 1
    assert "마지막 system_admin" in result.stderr


def test_cli_disable_guards_last_system_admin(db_path):
    run_cli(db_path, "add", "--email", "solo@goodmit.co.kr", "--name", "단독", "--role", "system_admin")
    result = run_cli(db_path, "disable", "--email", "solo@goodmit.co.kr")
    assert result.returncode == 1


def test_cli_passwd_temp_resets(db_path):
    run_cli(db_path, "add", "--email", "pwreset@goodmit.co.kr", "--name", "재설정")
    result = run_cli(db_path, "passwd", "--email", "pwreset@goodmit.co.kr", "--temp")
    assert result.returncode == 0
    assert "temp_password:" in result.stdout
