"""저장소 위생 검사 — stash/reflog/dangling 객체의 자격증명 탐지 (PA-RC-0003).

이 저장소의 실제 `stash@{0}`에서 TEST 서버 SSH/sudo 비밀번호가 평문으로 발견된 뒤 만든
검사다(`scripts/check_git_secrets.py`). 이 시험은 **격리된 임시 저장소**에서만 stash를
만들고 지운다 — 실제 저장소의 stash는 절대 건드리지 않는다(더미 문자열만 쓴다,
acceptance_criteria (2)).
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_git_secrets.py"
DUMMY_SECRET = "not-a-real-value-9f2c1d4e"  # 이 시험 전용 더미 — 절대 실제 값이 아니다


def _load():
    spec = importlib.util.spec_from_file_location("check_git_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    """격리된 임시 git 저장소 — 커밋 하나로 시작한다(stash는 기준 커밋이 필요)."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def test_clean_repo_passes(repo, capsys):
    mod = _load()
    assert mod.main(repo) == 0
    out = capsys.readouterr().out
    assert "GIT_SECRETS_OK" in out


def test_a_dummy_secret_in_stash_is_caught_and_never_printed(repo, capsys):
    """🔴 revert-to-verify — 더미 비밀을 stash에 담으면 실패하고, 값은 출력에 안 나온다."""
    mod = _load()

    (repo / "notes.md").write_text(
        f"- sudo password: `{DUMMY_SECRET}`\n", encoding="utf-8",
    )
    _git(repo, "stash", "push", "-u", "-m", "test stash with a dummy secret")

    assert mod.main(repo) == 1, "더미 비밀이 담긴 stash를 놓쳤다"
    captured = capsys.readouterr()
    assert DUMMY_SECRET not in captured.out, "검사 출력이 값 자체를 노출했다(acceptance_criteria 3 위반)"
    assert DUMMY_SECRET not in captured.err, "검사 출력이 값 자체를 노출했다(acceptance_criteria 3 위반)"
    assert "notes.md" in captured.err, "어느 파일에서 걸렸는지는 알려줘야 한다(값 없이)"

    # 정리 뒤에는 다시 통과한다 — 같은 검사, 같은 저장소, 원인만 사라진 상태.
    _git(repo, "stash", "drop")
    assert mod.main(repo) == 0, "stash를 지웠는데도 여전히 실패한다"


def test_safe_placeholder_in_stash_does_not_trigger(repo):
    """문서 안내용 자리표시자(예: '<비밀번호>')는 실제 값이 아니므로 걸리지 않는다."""
    mod = _load()
    (repo / "notes.md").write_text(
        "sudo password: `<비밀번호>`\n", encoding="utf-8",
    )
    _git(repo, "stash", "push", "-u", "-m", "test stash with a placeholder only")
    assert mod.main(repo) == 0, "자리표시자를 실값으로 오탐했다"


def test_secret_in_test_fixture_path_is_excluded(repo):
    """`tests/`·`.example` 같은 구조적 안전 경로는 값이 있어도(테스트 픽스처) 안 잡는다 —
    static_checks.sh의 기존 app/ 스캐너도 같은 이유로 test/example을 뺀다."""
    mod = _load()
    (repo / "tests").mkdir()
    (repo / "tests" / "fixtures.py").write_text(
        f'DEFAULT_TEST_PASSWORD = "{DUMMY_SECRET}"\n', encoding="utf-8",
    )
    _git(repo, "add", "tests")
    _git(repo, "stash", "push", "-u", "-m", "test stash touching tests/")
    assert mod.main(repo) == 0, "테스트 픽스처 경로를 실값 유출로 오탐했다"


def test_code_that_merely_references_a_token_variable_is_not_flagged(repo):
    """오탐 회귀(2026-08-16 실측) — 실제 저장소의 reflog-only 초기 import 커밋(f0efc52af4ec)을
    이 검사로 훑었더니 `token = new_session_token()`·`token_hash=hash_token(token)` 같은
    평범한 세션/토큰 처리 코드 약 50건이 "password-like assignment"로 오탐됐다. 전부
    app/core/sessions.py·app/auth/router.py·scripts/seed_admin.py 등 애초에 비밀번호를
    다루는 게 일인 모듈이었다 — 값이 아니라 코드였다. 따옴표 없이 식별자/호출/속성 접근으로
    이어지면 값이 아니라 참조라고 보고 뺀다(`CODE_REFERENCE_RE`). CLAUDE.md stash의 실제
    사고는 따옴표 없는 산문이라 값 뒤에 `(`나 `[`가 오지 않으므로 계속 잡힌다(다른 시험 참고)."""
    mod = _load()
    (repo / "auth_like.py").write_text(
        "token = new_session_token()\n"
        "token_hash=hash_token(token)\n"
        "password = generate_temp_password(user)\n",
        encoding="utf-8",
    )
    _git(repo, "add", "auth_like.py")
    _git(repo, "stash", "push", "-u", "-m", "test stash with ordinary token-handling code")
    assert mod.main(repo) == 0, "토큰/비밀번호를 다루는 평범한 코드를 실값 유출로 오탐했다"
