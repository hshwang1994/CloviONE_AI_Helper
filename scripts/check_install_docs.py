#!/usr/bin/env python
"""설치 문서가 설치 스크립트가 실제로 받는 명령과 옵션만 쓰는가 (계획 3.17, D-522).

README 와 설치 상세 문서는 사람이 그대로 복사해 실행하는 명령을 담는다. 스크립트에서 옵션 이름이 바뀌었는데 문서가 옛
이름을 들고 있으면, 설치하는 사람은 첫 명령에서 「모르는 옵션」을 보고 멈춘다. 문서를 고치는 사람은 그 사실을 모른다.

## 무엇을 보는가

README.md 와 docs/platform/INSTALLATION.md 의 코드 블록과 인라인 코드에서 `install.sh <명령>` 과 `clovirassist <명령>` 을
찾는다. 그 명령이 스크립트가 아는 서브커맨드인지, 붙은 `--옵션` 이 스크립트의 도움말(usage)에 있는지 본다.

- 설치 명령의 서브커맨드와 옵션은 deploy/install.sh 의 서브커맨드 표와 usage() 가 정본이다.
- clovirassist 명령은 deploy/clovirassist-cli.sh 의 분기가 정본이다. 제품 도구(user, migrate 등)의 옵션은 그 도구가
  정하므로 여기서는 명령 이름만 본다.
- `<버전>` 이나 `[options]` 같은 자리 표시는 건너뛴다.

마지막 줄이 요약이고 실패면 종료 코드 1 이다(scripts/check_user_text.py 와 같은 관례).
`--selftest` 는 맞는 문장과 틀린 문장을 먹여 검사기가 둘을 가르는지 본다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "deploy" / "install.sh"
CLI = ROOT / "deploy" / "clovirassist-cli.sh"
DOCS = (ROOT / "README.md", ROOT / "docs" / "platform" / "INSTALLATION.md")

_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]+)`")
_INVOCATION = re.compile(r"(?:install\.sh|(?<![\w/.-])clovirassist)\s+([^|&;#]*)")


def installer_vocabulary(text: str) -> tuple[set[str], set[str]]:
    """설치 스크립트가 받는 서브커맨드와 옵션."""
    arm = text.split('case "$SUBCOMMAND" in', 1)[1].split("esac", 1)[0]
    subcommands = set(re.findall(r"^\s+([a-z|-]+)\) ;;", arm, flags=re.M)[0].split("|")) | {"app-cli"}
    usage = text.split("usage() {", 1)[1].split("\n}\n", 1)[0]
    options = set(re.findall(r"^\s+(--[a-z-]+)", usage, flags=re.M)) | {"--help"}
    return subcommands, options


def cli_vocabulary(text: str) -> set[str]:
    arms = text.split('case "$command" in', 1)[1].split("esac", 1)[0]
    names: set[str] = set()
    for label in re.findall(r"^\s+([a-z|-]+)\)", arms, flags=re.M):
        names.update(label.split("|"))
    return names


def snippets(doc: str) -> list[str]:
    out = [line for block in _FENCE.findall(doc) for line in block.splitlines()]
    prose = _FENCE.sub("", doc)
    out.extend(_INLINE.findall(prose))
    return out


def scan_text(doc: str, *, subcommands: set[str], options: set[str], cli_commands: set[str]) -> list[str]:
    problems: list[str] = []
    for snippet in snippets(doc):
        for match in _INVOCATION.finditer(snippet):
            # `<버전>` 과 `[options]` 는 자리 표시다.
            tokens = [t for t in match.group(1).split() if not t.startswith(("<", "["))]
            if not tokens:
                continue
            is_cli = not match.group(0).startswith("install.sh")
            head = tokens[0]
            if is_cli:
                if head.startswith("-"):
                    if head not in ("-h", "--help"):
                        problems.append(f"clovirassist 에 모르는 옵션: {snippet.strip()}")
                    continue
                if head not in cli_commands:
                    problems.append(f"clovirassist 가 모르는 명령 {head}: {snippet.strip()}")
                    continue
                if head not in subcommands:
                    continue  # 제품 도구의 옵션은 그 도구가 정한다.
            elif not head.startswith("-") and head not in subcommands:
                problems.append(f"install.sh 가 모르는 명령 {head}: {snippet.strip()}")
                continue
            for token in tokens:
                name = token.split("=", 1)[0]
                if name.startswith("--") and name not in options:
                    problems.append(f"설치 스크립트에 없는 옵션 {name}: {snippet.strip()}")
    return problems


def selftest() -> int:
    subcommands, options = {"install", "upgrade", "verify"}, {"--dns-name", "--release", "--help"}
    cli = {"install", "upgrade", "verify", "user"}
    good = "```bash\nsudo bash install.sh install --dns-name <host> --release v1.2.0\nsudo clovirassist user list --all\n```\n"
    bad = ("```bash\nsudo bash install.sh install --dns <host>\n```\n"
           "`sudo clovirassist upgrade --tag v1`\n`sudo clovirassist restart`\n`install.sh reinstall`\n")
    ok = not scan_text(good, subcommands=subcommands, options=options, cli_commands=cli)
    found = scan_text(bad, subcommands=subcommands, options=options, cli_commands=cli)
    if ok and len(found) == 4:
        print("SELFTEST_OK 맞는 문장 0건, 틀린 문장 4건을 가렸습니다")
        return 0
    print(f"SELFTEST_FAILED good_ok={ok} bad_found={found}")
    return 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    subcommands, options = installer_vocabulary(INSTALL.read_text(encoding="utf-8"))
    cli_commands = cli_vocabulary(CLI.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        checked += sum(1 for s in snippets(text) for _ in _INVOCATION.finditer(s))
        problems.extend(f"{doc.relative_to(ROOT).as_posix()}: {p}" for p in
                        scan_text(text, subcommands=subcommands, options=options, cli_commands=cli_commands))
    for problem in problems:
        print(problem)
    if problems:
        print(f"INSTALL_DOCS_FAILED 문서의 설치 명령 {checked}개 중 {len(problems)}개가 스크립트와 다릅니다")
        return 1
    if checked == 0:
        print("INSTALL_DOCS_FAILED 문서에서 설치 명령을 하나도 찾지 못했습니다(검사가 아무것도 보지 않았습니다)")
        return 1
    print(f"INSTALL_DOCS_OK 문서의 설치 명령 {checked}개가 스크립트가 받는 명령과 옵션만 씁니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
