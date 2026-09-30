"""설치 명령의 계약 (계획 3.17, D-522).

설치는 랩 서버에서 실측하지만(I3), 그 전에 여기서 잴 수 있는 것은 잰다. 셸 함수는 설치 스크립트에서 떼어 bash 로 실제로
돌린다(tests/unit/test_deploy_wiring.py 의 앞단 프록시 검사와 같은 방식). 나머지는 스크립트의 구조를 읽는다.

못박는 성질:
1. Ubuntu 24.04 만 받는다. 22.04 나 다른 배포판은 Stage 0 에서 멈춘다.
2. Release 묶음은 SHA256SUMS 의 자기 줄과 맞아야만 풀린다. 목록에 없거나, 파일이 바뀌었거나, 이름이 비슷하기만 하면 실패다.
3. 확인은 풀기보다 먼저다. 그리고 Release 받기는 Stage 0 안에 있어 아무것도 바꾸기 전에 끝난다.
4. --source 없이 돌리면 자리에 맞는 소스를 고른다. 저장소 밖에서 이 파일 하나만 돌리면 Release 다.
5. clovirassist 명령은 서브커맨드마다 맞는 곳으로 넘긴다. 제품 CLI 는 install.sh 의 app-cli 를 지나 서비스 계정으로 돈다.
6. 첫 관리자 설정 코드는 설치 로그에 쓰지 않는다. 콘솔에만 한 번 나온다.
7. 도움말에 없는 옵션을 받지 않는다(문서가 스크립트와 어긋나는 것을 막는 첫 겹).
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL = ROOT / "deploy" / "install.sh"
CLI = ROOT / "deploy" / "clovirassist-cli.sh"
GIT_BASH = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = shutil.which("bash") if not GIT_BASH.exists() else str(GIT_BASH)

needs_bash = pytest.mark.skipif(not BASH, reason="bash 없음 — 셸 함수를 실행할 수 없다")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _function(name: str) -> str:
    text = _text(INSTALL)
    head = f"{name}() {{"
    assert head in text, f"설치 스크립트에 {name} 가 없다"
    return head + text.split(head, 1)[1].split("\n}\n", 1)[0] + "\n}\n"


def _run(script: str, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-c", script, "check", *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd)


@needs_bash
@pytest.mark.parametrize("path", [INSTALL, CLI])
def test_the_scripts_parse(path):
    result = subprocess.run([BASH, "-n", str(path)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "\r" not in _text(path), f"{path.name} 에 CRLF 가 있다 - 서버의 bash 가 그 줄을 못 읽는다"


@needs_bash
@pytest.mark.parametrize(("os_id", "version", "ok"), [
    ("ubuntu", "24.04", True), ("ubuntu", "22.04", False), ("ubuntu", "24.10", False), ("debian", "12", False),
])
def test_only_ubuntu_2404_is_supported(os_id, version, ok):
    result = _run(_function("os_release_supported") + 'os_release_supported "$1" "$2"', os_id, version)
    assert (result.returncode == 0) is ok


def _release_dir(tmp_path: pathlib.Path, *, listed_name: str, content: bytes = b"product tree"):
    name = "clovirassist-1.2.0.tar.gz"
    (tmp_path / name).write_bytes(content)
    digest = hashlib.sha256(b"product tree").hexdigest()
    # sha256sum 의 두 모양: 글 모드는 `해시  이름`(공백 둘), 이진 모드는 `해시 *이름`(공백 하나와 별표).
    sep = " " if listed_name.startswith("*") else "  "
    (tmp_path / "SHA256SUMS").write_text(f"{digest}{sep}{listed_name}\n{'0' * 64}  install.sh\n", encoding="utf-8")
    return name


@needs_bash
@pytest.mark.parametrize(("listed", "content", "ok"), [
    ("clovirassist-1.2.0.tar.gz", b"product tree", True),
    ("*clovirassist-1.2.0.tar.gz", b"product tree", True),
    # 받는 중에 바뀌었거나 다른 파일이다.
    ("clovirassist-1.2.0.tar.gz", b"tampered tree", False),
    # 목록에 그 파일의 줄이 없다 - 확인한 것이 없다.
    ("clovirassist-1.1.0.tar.gz", b"product tree", False),
    # 이름을 정규식으로 맞추면 점이 아무 글자와 맞는다. 글자 그대로 비교해야 한다.
    ("clovirassist-1x2x0.tar.gz", b"product tree", False),
])
def test_the_release_checksum_must_match_its_own_line(tmp_path, listed, content, ok):
    name = _release_dir(tmp_path, listed_name=listed, content=content)
    result = _run(_function("verify_release_checksum") + 'verify_release_checksum "$1" "$2"', str(tmp_path), name)
    assert (result.returncode == 0) is ok, result.stderr


@needs_bash
def test_rollback_picks_the_latest_snapshot_not_a_helper_directory(tmp_path):
    """특권 도우미의 `sysops/` 는 글자라 이름순으로 스냅샷 뒤에 선다. 그것을 고르면 되돌리기가 멈춘다(I3 리허설 실측)."""
    for name in ("20260930-120000", "20260930-133345", "sysops", "manual-keep"):
        (tmp_path / name).mkdir()
    script = (
        'BACKUP_ROOT="$1"\n'
        + _text(INSTALL).split("SNAPSHOT_NAME_RE=", 1)[1].split("\n", 1)[0].join(["SNAPSHOT_NAME_RE=", "\n"])
        + _function("latest_snapshot") + "latest_snapshot"
    )
    result = _run(script, tmp_path.as_posix())
    assert result.stdout.strip().endswith("/20260930-133345"), result.stdout + result.stderr
    assert "ls -1d" not in _function("do_rollback"), "되돌리기가 다시 디렉터리 이름순으로 고른다"


def test_the_release_is_verified_before_it_is_unpacked_and_before_anything_changes():
    body = _function("fetch_release")
    assert body.index("verify_release_checksum") < body.index("tar -xzf"), "확인보다 풀기가 먼저다"
    assert "$APP_DIR" not in body, "Release 받기가 설치 자리를 건드린다 - Stage 3 전에는 바뀌는 것이 없어야 한다"
    preflight = _function("stage_0_preflight")
    assert "fetch_release" in preflight, "Release 받기가 Stage 0 밖에 있다"
    assert "os_release_supported" in preflight


@needs_bash
@pytest.mark.parametrize(("release_tag", "src_is_app", "app_has_git", "src_has_tree", "remembered", "expected"), [
    ("v1.2.0", False, False, False, "", "release"),
    ("", True, True, True, "", "git"),
    ("", True, False, True, "release", "release"),
    ("", True, False, True, "", "local"),
    ("", False, False, True, "", "local"),
    ("", False, False, False, "", "release"),
])
def test_the_source_kind_follows_where_the_script_runs(tmp_path, release_tag, src_is_app, app_has_git,
                                                       src_has_tree, remembered, expected):
    app_dir = tmp_path / "opt"
    app_dir.mkdir()
    src_dir = app_dir if src_is_app else tmp_path / "download"
    src_dir.mkdir(exist_ok=True)
    if app_has_git:
        (app_dir / ".git").mkdir()
    if src_has_tree:
        (src_dir / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    script = (
        f'RELEASE_TAG="{release_tag}"; APP_DIR="$1"; SRC_DIR="$2"\n'
        f'jq_get() {{ echo "{remembered}"; }}\n'
        + _function("resolve_source_kind") + "resolve_source_kind"
    )
    result = _run(script, app_dir.as_posix(), src_dir.as_posix())
    assert result.stdout.strip() == expected, result.stderr


@needs_bash
@pytest.mark.parametrize(("argv", "forwarded"), [
    (["install", "--release", "v1.2.0"], "install --release v1.2.0"),
    (["upgrade", "--release", "v1.3.0"], "upgrade --release v1.3.0"),
    (["rollback"], "rollback"),
    (["verify"], "verify"),
    (["version"], "version"),
    (["ai", "--download-model"], "ai --download-model"),
    (["user", "list"], "app-cli user_cli list"),
    (["migrate", "--help"], "app-cli migrate_cli --help"),
    (["storage-cli", "units"], "app-cli storage_cli units"),
    (["ai-cli", "status"], "app-cli ai_cli status"),
    (["first-admin-code"], "app-cli user_cli first-admin-code"),
])
def test_the_command_forwards_each_subcommand(tmp_path, argv, forwarded):
    fake = tmp_path / "deploy"
    fake.mkdir()
    (fake / "install.sh").write_text('#!/usr/bin/env bash\necho "$*"\n', encoding="utf-8", newline="\n")
    (fake / "install.sh").chmod(0o755)
    result = subprocess.run(
        [BASH, str(CLI), *argv], capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "CLOVIRASSIST_APP_DIR": tmp_path.as_posix()},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == forwarded


@needs_bash
def test_an_unknown_command_is_refused(tmp_path):
    fake = tmp_path / "deploy"
    fake.mkdir()
    (fake / "install.sh").write_text('#!/usr/bin/env bash\necho "$*"\n', encoding="utf-8", newline="\n")
    (fake / "install.sh").chmod(0o755)
    result = subprocess.run([BASH, str(CLI), "rm-rf"], capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "CLOVIRASSIST_APP_DIR": tmp_path.as_posix()})
    assert result.returncode == 64 and result.stdout.strip() == ""


def test_app_cli_takes_only_product_modules_that_exist():
    text = _text(INSTALL)
    arm = text.split("  app-cli)", 1)[1].split(";;\n  -h|--help)", 1)[0]
    modules = set(re.findall(r"\b(\w+_cli)\b", arm.split('case "$APP_CLI_MODULE" in', 1)[1].split("esac", 1)[0]))
    assert modules == {"user_cli", "migrate_cli", "storage_cli", "ai_cli"}
    for module in modules:
        assert (ROOT / "app" / "cli" / f"{module}.py").is_file(), f"없는 제품 CLI 로 넘긴다: {module}"
    assert "run_as_app" in arm, "제품 CLI 가 서비스 계정과 설치 환경으로 돌지 않는다"
    wrapper = set(re.findall(r"app-cli (\w+_cli)", _text(CLI)))
    assert wrapper == modules, "clovirassist 명령과 app-cli 가 아는 모듈이 다르다"


def test_the_first_admin_code_reaches_only_the_console():
    stage = _function("stage_10_seed")
    assert "first-admin-code" in stage
    code_lines = [ln for ln in stage.splitlines() if "FIRST_ADMIN_CODE" in ln]
    assert code_lines and not any(re.search(r"\b(say|log)\b", ln) for ln in code_lines), "코드가 설치 로그로 간다"
    printer = _function("print_first_admin_code")
    assert "say " not in printer and "log " not in printer, "코드를 찍는 함수가 설치 로그에도 쓴다"
    assert "user_cli add" not in stage, "서버 셸에서 계정을 만들라는 옛 안내가 남았다"


def test_the_command_is_installed_and_removed_with_the_product():
    assert "clovirassist-cli.sh" in _function("stage_13_units")
    assert 'rm -f "$CLI_BIN"' in _function("do_uninstall")
    assert "$CLI_BIN" in _function("do_verify")


def test_every_option_the_parser_takes_is_in_the_help():
    text = _text(INSTALL)
    loop = text.split("while [ $# -gt 0 ]; do", 1)[1].split("\ndone\n", 1)[0]
    parsed = set(re.findall(r"^\s+(--[a-z-]+)\)", loop, flags=re.M))
    parsed.discard("--target")  # rollback 의 대상 지정은 위치 인자로도 받는다. 도움말은 rollback 줄이 말한다.
    usage = _function("usage")
    missing = sorted(opt for opt in parsed if opt not in usage)
    assert not missing, f"도움말에 없는 옵션이다: {missing}"
    assert {"--release", "--release-base", "--download-model"} <= parsed
