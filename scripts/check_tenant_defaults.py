#!/usr/bin/env python
"""소스 기본값·설치 스크립트에 고객사 고유 식별자가 남아 있는지 검사한다.

## 왜 이 검사가 생겼는가

`app/core/config.py` 의 **기본값**에 개발 워크스페이스의 Notion DB id 두 개
(`262c5c5a…`, `55efc3c0…`)와 `allowed_email_domains="goodmit.co.kr"` 가 박혀 있었다.
호스트 `clovirone-ai.gooddi.lab` 은 설치·검증 스크립트와 nginx 설정에 박혀 있었다.

다른 고객사에 설치하면 **아무 설정 없이도 조용히 그 워크스페이스를 가리킨다.** 토큰이 없어
데이터가 새지는 않지만, 동작하지 않는 이유가 어디에도 안 뜬다 — 설치한 사람은 "연결은 됐는데
안 된다" 로 읽고 원인을 못 찾는다. 출시를 막을 만한 결함이다.

한 번 지우고 끝내면 다음 기능에서 다시 들어온다(그때는 "임시로" 라고 적힌 채로 들어온다).
그래서 검사로 고정한다.

## 무엇을 보는가

**실행되는 것**만 본다: 파이썬 소스(app/, scripts/), 셸 스크립트, nginx·systemd 설정,
env 예시 파일. 여기 남은 값은 설치처에서 그대로 동작에 쓰인다.

## 무엇을 일부러 안 보는가 (§EXEMPT)

문서·테스트 픽스처·샘플 데이터는 제외한다. 넣으면 오탐이 수백 줄 나오고, 소음이 나면
아무도 안 본다 — 그게 검사를 죽이는 가장 흔한 방법이다. 제외한 자리와 이유는 아래
`EXEMPT` 한 곳에 모아 뒀다. 새로 제외하려면 거기에 **이유를 적어야** 한다.

## 이 검사가 헛것이 아닌지 어떻게 아는가

기본값을 도로 넣어(`notion_tasks_database_id = "262c5c5a…"`) 실제로 실패하는 것을 봤다.
`tests/unit/test_tenant_defaults.py::test_check_tenant_defaults_script_catches_reintroduced_identifier`
가 그 성질을 고정한다 — `scan_text()` 에 오염된 내용을 직접 먹여 걸리는지 본다.

## 관례

scripts/check_css_vars.py, scripts/check_user_text.py 와 같은 모양이다: 마지막 stdout 한 줄이
요약이고(성공 시 shell 이 `| tail -1` 로 쓴다), 실패면 종료 코드 1.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    # Windows 기본 cp949 로는 아래 한국어 실패 메시지가 깨진다. 읽을 수 없는 실패 보고는
    # 검사가 없는 것과 같다(check_user_text.py 와 같은 이유).
    _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# 이 저장소가 실제로 흘린 고객사 식별자들. 값을 문자열로 들고 있어야 "없어졌다" 를 증명한다.
#
# ⚠️ 새 고객사 식별자를 여기 추가할 때는 **그 값이 왜 고객 고유값인지**를 같이 적어라.
# 일반 명사(예: 'notion')를 넣으면 오탐이 쏟아지고 검사는 그날로 죽는다.
PATTERNS: dict[str, str] = {
    # 개발 워크스페이스의 Notion "작업" 데이터베이스 id.
    r"262c5c5a568481fa9697ee5691cb558d": "노션 작업 DB id(개발 워크스페이스)",
    # 같은 워크스페이스의 "문서" 데이터베이스 id.
    r"55efc3c0b58341a5b8d17f31fc2b152c": "노션 문서 DB id(개발 워크스페이스)",
    # 최초 고객사의 회사 이메일 도메인.
    r"goodmit\.co\.kr": "고객사 이메일 도메인",
    # 최초 고객사 사내망 호스트명.
    r"clovirone-ai\.gooddi\.lab": "고객사 호스트명",
    # 그 호스트의 사설 IP. 설치 스크립트가 이 값으로 인증서를 만들고 방화벽을 연다.
    r"10\.100\.64\.71": "고객사 서버 IP",
}

COMPILED = {re.compile(p): label for p, label in PATTERNS.items()}

# 검사 대상. 설치처에서 **실행되는 것**만 본다.
SCAN_GLOBS: tuple[tuple[str, str], ...] = (
    ("app", "*.py"),
    ("scripts", "*.py"),
    ("scripts", "*.sh"),
    ("deploy", "*.sh"),
    ("deploy", "*.conf"),
    ("deploy", "*.service"),
    ("deploy", "*.timer"),
    ("deploy", "*.example"),
    ("deploy", "*.env-snippet"),
    ("frontend/src", "*.js"),
    ("frontend/src", "*.jsx"),
    ("config", "*.json"),
    ("alembic", "*.py"),
)

# 저장소 루트에 있어 glob 으로 안 걸리는 개별 파일.
SCAN_FILES: tuple[str, ...] = (
    ".env.example",
)

# 경로에 이 조각이 있으면 아예 안 읽는다(빌드 산출물·의존성·옛 작업 사본).
SKIP_PARTS = {
    "node_modules", ".git", ".claude", ".venv", "__pycache__", "dist", "var",
    # 빌드된 번들. 소스를 고치고 다시 빌드하면 따라온다 — 여기서 잡으면 같은 결함을
    # 두 번 보고하고, 번들을 손으로 고치라는 잘못된 지시가 된다.
    "react",
}

# ── EXEMPT: 일부러 검사하지 않는 자리 ────────────────────────────────────────
#
# **모든 예외는 여기 한 곳에 이유와 함께 둔다.** 파일 안에 주석으로 흩어 놓으면 나중에
# 왜 봐줬는지 아무도 모르고, 하나씩 늘어나다 검사가 빈 껍데기가 된다.
#
# 키는 저장소 루트 기준 상대 경로(슬래시 구분) **또는** `*` 로 시작하는 파일명 꼬리표.
# 값은 왜 봐주는지.
EXEMPT: dict[str, str] = {
    # 프런트 테스트. 화면 테스트는 실제로 보이는 이름·주소를 픽스처로 쓰는데, 그 안의
    # 도메인은 렌더 결과를 확인하려고 넣은 표본이지 설치처 설정이 아니다. tests/ 와 같은 이유.
    "*.test.js": "프런트 테스트 픽스처. 설치처에서 실행되지 않는다.",
    "*.test.jsx": "프런트 테스트 픽스처. 설치처에서 실행되지 않는다.",
    # 테스트 픽스처. 테스트 이메일을 전부 바꾸면 수백 줄 diff 가 나고 얻는 것이 없다 —
    # 테스트는 설치처에서 실행되지 않는다. (tests/ 는 SCAN_GLOBS 에 없어 이미 안 읽지만,
    # 왜 안 읽는지를 여기 적어 둔다.)
    "tests/": "테스트 픽스처. 설치처에서 실행되지 않는다.",
    # 내부 문서·운영 기록. 실제 있었던 설치를 서술하는 글이라 값을 지우면 기록이 거짓이 된다.
    "docs/": "내부 문서. 실제 설치 기록이라 값이 사실이다.",
    "CLAUDE.md": "내부 작업 지침. 실제 운영 서버를 가리키는 기록이다.",
    "README.md": "내부 문서. 실제 배포 현황 기록이다.",
    # 개발자 로컬 env. .gitignore 대상이라 배포되지 않는다.
    ".env": "로컬 개발 env. 커밋되지 않는다(.gitignore).",
    # UI QA 보조 스크립트. 개발자가 자기 로컬에서 화면을 찍어 보는 도구이며 설치 산출물이
    # 아니다. 안에 있는 도메인은 로그인용 예시 계정 주소다.
    "scripts/ui_qa/": "개발자 로컬 QA 도구. 설치 산출물이 아니다.",
    # 디자인 기준 스냅숏(정적 HTML). 과거 화면을 그대로 보존하는 참고 자료라 고치면
    # 비교 기준이 흔들린다.
    "design/": "디자인 기준 스냅숏. 과거 화면 보존이 목적이다.",
    # 검사기 자신. 찾을 값을 문자열로 들고 있어야 검사가 성립한다 - 자기 자신을 결함으로
    # 보고하면 이 검사는 영원히 빨간불이고, 그러면 아무도 안 켠다.
    "scripts/check_tenant_defaults.py": "검사기 자신. 찾을 값 목록이라 여기 있는 것이 정상이다.",
    # 같은 이유의 이웃. `check_qa_target_host.py` 의 `--self-test` 사례는 **찾아야 하는 모양**을
    # 그대로 들고 있어야 성립한다(옛 호스트·IP·이메일 도메인). 이 값들이 없으면 그 검사기는
    # 자기가 제대로 도는지 증명할 방법이 사라진다 — 그리고 증명 없는 초록이 12_PROBE 가
    # 기록한 여덟 가지 거짓 통과의 출발점이었다. 검사기이지 설치 산출물이 아니다.
    "scripts/check_qa_target_host.py": "검사기 자신. `--self-test` 반례라 여기 있는 것이 정상이다.",
}


def is_exempt(rel_path: str) -> bool:
    for key in EXEMPT:
        if key.startswith("*"):
            if rel_path.endswith(key[1:]):
                return True
        elif rel_path == key or rel_path.startswith(key):
            return True
    return False


def _python_comment_and_docstring_lines(text: str) -> set[int]:
    """주석과 docstring 이 차지하는 줄 번호 집합.

    이 저장소는 "왜" 를 한국어 주석으로 길게 남기는 관례가 있고(그게 좋은 관례라 바꿀 이유가
    없다), 그 설명문에는 **없앤 값이 무엇이었는지**가 그대로 등장한다
    (예: app/core/config.py 의 "예전엔 이 워크스페이스 DB id 가 박혀 있었다").
    설명문까지 잡으면 검사가 자기 자신의 근거를 결함이라고 보고한다 — 소음이 나면 아무도 안 본다.
    실행되는 것은 **주석 밖의 값**뿐이므로 거기만 본다(scripts/check_user_text.py 와 같은 기법).
    """
    lines: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                for ln in range(tok.start[0], tok.end[0] + 1):
                    lines.add(ln)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lines
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                lines.add(ln)
    return lines


def scan_text(rel_path: str, text: str) -> list[tuple[int, str, str]]:
    """(줄번호, 무엇인지, 그 줄) 목록. 걸린 것이 없으면 빈 목록.

    파일을 직접 읽지 않고 문자열을 받는다 — 테스트가 임시 파일 하나로 "검사가 눈을 뜨고
    있는지" 를 확인할 수 있게 하려고 이렇게 갈랐다.
    """
    skip = _python_comment_and_docstring_lines(text) if rel_path.endswith(".py") else set()
    hits: list[tuple[int, str, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if idx in skip:
            continue
        for pattern, label in COMPILED.items():
            if pattern.search(line):
                hits.append((idx, label, line.strip()))
                break
    return hits


def _targets() -> list[Path]:
    out: list[Path] = []
    for root, pattern in SCAN_GLOBS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob(pattern):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            out.append(path)
    for name in SCAN_FILES:
        path = ROOT / name
        if path.exists():
            out.append(path)
    return sorted(set(out))


def main() -> int:
    offenders: list[str] = []
    scanned = 0
    for path in _targets():
        rel = path.relative_to(ROOT).as_posix()
        if is_exempt(rel):
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, label, line in scan_text(rel, text):
            offenders.append(f"{rel}:{line_no}  {label}\n    {line}")

    if offenders:
        print("고객사 고유 식별자가 소스/설치 산출물에 남아 있다:")
        for item in offenders:
            print("  " + item)
        print("")
        print(
            "설치처마다 다른 값은 기본값으로 두지 않는다. 비우고 "
            "app/core/tenant_config.py 의 목록에 올려, 안 채웠을 때 진단이 말하게 하라."
        )
        print(f"TENANT_DEFAULTS_FAILED: {len(offenders)}건")
        return 1

    print(f"TENANT_DEFAULTS_OK: {scanned}개 파일에 고객사 고유 식별자 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
