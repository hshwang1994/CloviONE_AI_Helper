"""stage-static-update.sh는 정적 자산을 하나도 빠뜨리지 않아야 한다.

두 결함을 핀으로 잡는다:

1. **하드코딩된 기본 목록이 파일을 빠뜨렸다.** 기본값이 admin.css + sections.js + app.js
   세 개뿐이라 admin/common.js·topbar.css·theme.js·_wordmark 워드마크가 딸린 change_password.js
   같은 나중에 생긴 자산이 통째로 빠졌다. 더 나쁜 건, 배포 뒤 검증 루프가 **같은 목록**을 써서
   빠진 파일을 검증도 안 하고 통과시켰다는 것이다 — 스스로에게 합격점을 줬다. 목록을 손으로
   유지하는 한 새 파일이 생길 때마다 조용히 빠진다. 그래서 이제 app/static을 **탐색**한다.

2. **끝 줄이 하드 리프레시를 지시했다.** assets.py의 캐시 버스팅(파일 mtime·크기로 주소에
   지문을 붙임)이 그 지시를 무의미하게 만든다 — 파일이 바뀌면 주소가 바뀌어 브라우저가
   무조건 새로 받는다. 사용자에게 Ctrl+Shift+R을 부탁하는 것은 그 설계를 부정하는 말이고,
   CLAUDE.md가 명시적으로 하지 말라고 한 일이다.

바이너리 안전성도 함께 지킨다: 스크립트가 CRLF를 지우려고 모든 파일에 sed를 돌리는데,
img/의 PNG에 그걸 돌리면 바이트가 깨진다(실측: 13882 → 13881). '전부 배포'로 고치면서
이 함정을 밟으면 로고가 조용히 깨진다.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "stage-static-update.sh"
STATIC = ROOT / "app" / "static"


def _bash() -> str:
    for name in ("bash", "bash.exe"):
        p = shutil.which(name)
        if p:
            return p
    for guess in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if Path(guess).exists():
            return guess
    return ""


BASH = _bash()
requires_bash = pytest.mark.skipif(not BASH, reason="bash 없음 — 셸 스크립트 실행 불가")


def _all_static_relpaths() -> set:
    return {
        p.relative_to(ROOT).as_posix()
        for p in STATIC.rglob("*") if p.is_file()
    }


# 이 스크립트는 `app/static` 전 파일을 훑으며 파일마다 셸 하위 프로세스를 띄운다.
# **실측: 부하 없는 상태에서 2분 08초**(user 35s / sys 69s — 거의 전부 프로세스 생성 비용이다.
# Git-Bash 에서 fork 가 특히 비싸다). 예전 상한 120초는 그 아래로 아슬아슬하게 통과하던
# 값이라, 병렬 작업으로 머신이 조금만 바빠져도 **타임아웃으로 빨갛게 된다** — 실제로 그렇게
# 세 건이 한 번에 실패했고 로직에는 아무 문제가 없었다.
#
# 상한은 "얼마나 걸리는가" 가 아니라 "얼마나 걸리면 뭔가 잘못된 것인가" 로 잡는다.
# 실측의 2.5배를 준다. 스크립트 자체를 빠르게 만드는 것은 별건이다(파일마다 프로세스를 띄우지
# 않는 방식으로 바꿀 수 있다).
STAGE_TIMEOUT_SECONDS = 300

# 스크립트는 대상 서버와 주소를 env 로 받는다. 기본값을 두지 않기로 했기 때문이다 - 예전엔
# 최초 고객사의 계정@IP 가 기본값이라, 다른 설치처에서 인쇄된 scp 명령을 그대로 복사하면
# 남의 서버로 파일을 밀어 넣었다(scripts/check_tenant_defaults.py 가 그 재발을 막는다).
# 테스트는 스테이징 로직만 보므로 값은 아무거나 되지만, **주지 않으면 스크립트가 멈춘다.**
TENANT_ENV = {
    "SERVER": "deploy@10.0.0.10",
    "BASE_URL": "https://portal.example.internal",
}


@requires_bash
def test_default_run_stages_every_static_file(tmp_path):
    """인자 없이 돌렸을 때, app/static의 모든 파일이 스테이지 목록에 들어가야 한다."""
    out = tmp_path / "stage"
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=str(ROOT), env={**os.environ, "OUT": out.as_posix(), **TENANT_ENV},
        capture_output=True, text=True, encoding="utf-8", timeout=STAGE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, f"스크립트 실패:\n{proc.stdout}\n{proc.stderr}"

    listed = {
        line.strip() for line in proc.stdout.splitlines()
        if line.strip().startswith("app/static/")
    }
    missing = _all_static_relpaths() - listed
    assert not missing, (
        "기본 실행이 이 정적 파일들을 스테이지에서 빠뜨렸다:\n  "
        + "\n  ".join(sorted(missing))
        + "\n하드코딩 목록 대신 app/static을 탐색해야 새 파일도 안 빠진다."
    )


@requires_bash
def test_staged_payload_contains_every_static_file(tmp_path):
    """빠뜨린 파일을 검증 루프가 못 잡는 문제 — 실제 페이로드/체크섬에 전부 들어갔는지 본다."""
    out = tmp_path / "stage"
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=str(ROOT), env={**os.environ, "OUT": out.as_posix(), **TENANT_ENV},
        capture_output=True, text=True, encoding="utf-8", timeout=STAGE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, f"스크립트 실패:\n{proc.stdout}\n{proc.stderr}"

    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
    # sha256sum 줄: "<hash> *app/static/…"(바이너리) 또는 "<hash>  app/static/…"(텍스트).
    checksummed = {line.split()[-1].lstrip("*") for line in sums.splitlines() if line.strip()}
    missing = _all_static_relpaths() - checksummed
    assert not missing, (
        "SHA256SUMS.txt(=검증 루프가 쓰는 목록)가 이 파일들을 빠뜨렸다: "
        + ", ".join(sorted(missing))
        + " — 검증이 스스로를 통과시킨다."
    )


@requires_bash
def test_binary_assets_survive_staging_byte_for_byte(tmp_path):
    """바이너리는 스테이지를 거쳐도 바이트가 그대로여야 한다.

    문자열 검사(주석에 '.png'가 있나)는 깨진 스크립트도 통과시킨다 — 실제로 스테이지된
    페이로드의 바이트를 원본과 비교한다. sed로 CRLF를 지우면 PNG가 한 바이트 짧아진다.
    """
    binaries = [p for p in STATIC.rglob("*")
                if p.is_file() and p.suffix.lower() in {".png", ".ico", ".jpg", ".gif", ".woff", ".woff2"}]
    if not binaries:
        pytest.skip("app/static에 바이너리 자산이 없다")

    out = tmp_path / "stage"
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=str(ROOT), env={**os.environ, "OUT": out.as_posix(), **TENANT_ENV},
        capture_output=True, text=True, encoding="utf-8", timeout=STAGE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, f"스크립트 실패:\n{proc.stdout}\n{proc.stderr}"

    corrupted = []
    for b in binaries:
        rel = b.relative_to(ROOT).as_posix()
        staged = out / "payload" / rel
        if not staged.exists():
            corrupted.append(f"{rel} (스테이지에 없음)")
        elif staged.read_bytes() != b.read_bytes():
            corrupted.append(f"{rel} ({b.stat().st_size}B → {staged.stat().st_size}B)")
    assert not corrupted, (
        "바이너리 자산이 스테이지에서 바이트가 바뀌었다:\n  " + "\n  ".join(corrupted)
        + "\n텍스트만 CRLF 정규화하고 바이너리는 그대로 복사해야 한다."
    )


@requires_bash
def test_no_hard_refresh_instruction(tmp_path):
    """캐시 버스팅이 하드 리프레시 지시를 무효로 만든다. 사용자에게 새로고침을 부탁하지 않는다.

    검사 대상은 스크립트가 **사용자에게 출력하는 것**이다(소스 주석이 아니라). '왜 하드
    리프레시가 필요 없는지' 설명하는 주석까지 막으면 안 되므로, 실제 stdout을 본다.
    """
    out = tmp_path / "stage"
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=str(ROOT), env={**os.environ, "OUT": out.as_posix(), **TENANT_ENV},
        capture_output=True, text=True, encoding="utf-8", timeout=STAGE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, f"스크립트 실패:\n{proc.stdout}\n{proc.stderr}"
    printed = proc.stdout.lower()
    for banned in ("ctrl+shift+r", "hard-refresh", "하드 리프레시", "새로고침", "shift+refresh"):
        assert banned.lower() not in printed, (
            f"stage-static-update.sh가 출력에서 여전히 '{banned}'를 지시한다. "
            "assets.py의 지문 주소가 파일이 바뀌면 자동으로 바뀌므로 하드 리프레시는 불필요하고, "
            "CLAUDE.md는 사용자에게 새로고침을 부탁하지 말라고 명시한다."
        )
