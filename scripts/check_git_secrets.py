"""저장소 위생 검사 — `.git` 내부(stash·reflog 전용 커밋·dangling 객체)에 남은 자격증명을
찾는다(PA-RC-0003).

왜 필요한가: `static_checks.sh`의 기존 "Secret / hardcoded-password scan"은 워킹트리와
HEAD 커밋만 본다. 그런데 `git stash`로 치운 변경이나, reset/amend로 브랜치에서는 사라졌지만
reflog가 살려 두고 있는 옛 커밋에는 그 검사가 닿지 않는다 — 실제로 이 저장소의
`stash@{0}`에 TEST 서버 SSH/sudo 비밀번호가 평문으로 담긴 채 발견됐다(2026-08-16).

**값을 출력하지 않는다.** 어느 stash/커밋/dangling 객체에서 걸렸는지, 어느 파일인지만
보고한다(CLAUDE.md §3-4) — 값을 찍는 검사는 그 자체로 새 유출 경로다.

세 표면을 훑는다:
  1) `git stash list`의 각 stash — `git stash show -p`로 diff 내용을 본다.
  2) reflog에만 남고 현재 어떤 브랜치에서도 reachable하지 않은 커밋 — reset/amend로
     "지워진 척"하지만 reflog 만료 전까지는 여전히 저장소 안에 있다.
  3) `git fsck --unreachable --no-reflog`가 내놓는 dangling 커밋/blob.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# 값이 붙은 자리만 잡는다(단순히 낱말이 언급된 문장은 잡지 않는다) — CLAUDE.md 자신의 규칙
# 문장("비밀번호를 stdin으로만 넘긴다" 등)이 오탐되지 않게 하려는 것이 목적이다.
CREDENTIAL_PATTERNS = [
    ("password-like assignment", re.compile(r'(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*[\'"]?[^\s\'"<>$]{8,}', re.IGNORECASE)),
    ("sshpass invocation", re.compile(r'sshpass\s+-p\S*\s+\S+', re.IGNORECASE)),
    ("private key header", re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----')),
    ("sudo -S with inline literal", re.compile(r'sudo\s+-S\S*[^\n$]{0,40}[\'"][^\s\'"$]{6,}[\'"]', re.IGNORECASE)),
]
# 문서의 안내용 자리표시자(예: '<비밀번호>', 'xxx', 'change-me')는 실제 값이 아니다.
SAFE_MARKERS = re.compile(r'(<[^>]*>|xxx+|change-?me|dummy|placeholder|example|여기에|자리표시자)', re.IGNORECASE)
# 구조적으로 실값이 아닌 파일류 — static_checks.sh의 기존 app/ 스캐너도 test/example을
# 같은 이유로 뺀다(코드 참고). 특정 커밋·stash를 콕 집어 빼는 것이 아니라 파일 종류
# 기준의 일반 규칙이라, "임시 예외" 금지 제약과 다른 층이다.
SAFE_PATH = re.compile(r'(\.example($|\.)|(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.(py|jsx?|tsx?)$|\.test\.(js|jsx|ts|tsx)$)', re.IGNORECASE)


def _run(args: list[str], cwd: Path) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    return r.stdout.decode("utf-8", errors="replace")


_DIFF_FILE_RE = re.compile(r'^\+\+\+ b/(.+)$')


def _scan_text(text: str) -> list[str]:
    """어느 파일·줄에서 걸렸는지 **경로와 줄 번호와 분류만** 돌려준다 — 줄 내용은 단 한 글자도
    포함하지 않는다(값 노출 방지). 이전 버전은 "줄 앞부분만" 잘라 돌려줬는데, 실제 사고 문장이
    "SSH password: `실값`"처럼 값이 줄 앞쪽에 오는 형태라 그 잘림 폭 안에 값이 그대로
    들어가 버렸다 — 위치 단서로 줄 내용 일부를 재구성하는 방식 자체가 안전하지 않다는
    뜻이라, 줄 내용을 아예 안 돌려주는 쪽으로 바꿨다. `git show`/`git stash show -p`의
    unified diff 헤더(`+++ b/path`)를 따라가며 지금 보는 줄이 어느 파일 소속인지 추적한다."""
    hits = []
    current_file = ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _DIFF_FILE_RE.match(line)
        if m:
            current_file = m.group(1)
            continue
        if current_file and SAFE_PATH.search(current_file):
            continue
        if SAFE_MARKERS.search(line):
            continue
        for label, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(line):
                where = current_file or "(unknown file)"
                hits.append(f"{where} line {lineno} ({label})")
                break
    return hits


def _stash_refs(repo: Path) -> list[str]:
    out = _run(["git", "stash", "list", "--format=%gd"], repo)
    return [ln for ln in out.splitlines() if ln.strip()]


def _reflog_only_commits(repo: Path) -> list[str]:
    """reflog에는 남아 있지만 지금 어떤 ref에서도 reachable하지 않은 커밋."""
    reflog_all = set(_run(["git", "rev-list", "--walk-reflogs", "--all"], repo).split())
    branch_all = set(_run(["git", "rev-list", "--all"], repo).split())
    return sorted(reflog_all - branch_all)


def _dangling_objects(repo: Path) -> list[tuple[str, str]]:
    """`(kind, sha)` 목록 — reflog로도 못 구하는 진짜 dangling 객체."""
    out = _run(["git", "fsck", "--unreachable", "--no-reflog"], repo)
    result = []
    for line in out.splitlines():
        # "dangling commit <sha>" / "dangling blob <sha>" 형식
        m = re.match(r"dangling (\w+) ([0-9a-f]{7,40})", line.strip())
        if m:
            result.append((m.group(1), m.group(2)))
    return result


def main(repo: Path | None = None) -> int:
    repo = repo or ROOT
    findings: list[str] = []

    for ref in _stash_refs(repo):
        diff = _run(["git", "stash", "show", "-p", "--include-untracked", ref], repo)
        for hit in _scan_text(diff):
            findings.append(f"stash {ref}: {hit}")

    for sha in _reflog_only_commits(repo):
        show = _run(["git", "show", sha], repo)
        for hit in _scan_text(show):
            findings.append(f"reflog-only commit {sha[:12]}: {hit}")

    for kind, sha in _dangling_objects(repo):
        content = _run(["git", "cat-file", "-p", sha], repo) if kind == "blob" else _run(["git", "show", sha], repo)
        for hit in _scan_text(content):
            findings.append(f"dangling {kind} {sha[:12]}: {hit}")

    if findings:
        print("[FAIL] .git 내부(stash/reflog/dangling)에서 자격증명으로 보이는 값이 발견됐다:", file=sys.stderr)
        print("       (아래는 객체와 위치뿐이다 — 값 자체는 이 검사가 출력하지 않는다, CLAUDE.md §3-4)", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  고치는 법: 그 자격증명을 회전한 뒤(운영 행위, 이 저장소 밖) 해당 stash/커밋을", file=sys.stderr)
        print("  git stash drop / git gc --prune=now 로 정리하라. 회전 전에 지우면 근거만 사라진다.", file=sys.stderr)
        return 1

    print(f"GIT_SECRETS_OK (stash {len(_stash_refs(repo))}개 · dangling {len(_dangling_objects(repo))}개 검사)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
