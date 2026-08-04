#!/usr/bin/env python
"""사용자에게 보이는 문구에 가운뎃점(·)과 em 대시(—)가 없는지 검사한다.

## 왜 이 검사가 필요한가

사용자 지시(§8): "프로젝트 전체에서 `·`, `—` 문자를 사용하지 않기로 한 기존 기준을 지켜야
한다. 현재 코드, 화면 문구, 메뉴, 버튼, 안내 메시지와 샘플 데이터에서 해당 문자를 전수
조사하고 제거하거나 자연스러운 문장으로 수정하라."

한 번 훑고 끝내면 다음 화면에서 다시 새어 나간다. 그래서 검사로 고정한다.

## 왜 grep 이 아닌가

저장소 전체에 두 문자가 5,985개 있는데 **그중 5,157개(86%)가 코드 주석과 docstring** 이다.
이 저장소는 주석을 한국어로 길게 쓰는 관례가 있어서(그리고 그 관례 자체는 좋은 것이라
바꿀 이유가 없다) 단순 grep 은 오탐 5,157개를 낸다 — 아무도 안 보게 된다.

그래서 **주석 안인지 밖인지**만 정확히 가른다. 문자열 리터럴인지 JSX 텍스트인지까지 구분할
필요는 없다: 주석 밖에 있는 두 문자는 거의 전부 사용자에게 보이는 문구다.

## 일부러 남기는 글리프

문자 자체가 내용인 자리가 있다:
  - 권한 매트릭스의 '허용 안 됨' 표시(—)
  - 목록 글머리표(· )
  - 비밀번호 규칙의 '아직 충족 안 됨' 표시(· , ✓ 와 짝)
이런 줄에는 같은 줄에 `clovi-allow-glyph` 를 적어 둔다. 지우는 대신 **왜 남겼는지**가
코드에 남는다.

## 관례

scripts/check_css_vars.py, scripts/check_tracked_imports.py 와 같은 모양이다:
마지막 stdout 한 줄이 요약이고(성공 시 shell 이 `| tail -1` 로 쓴다), 실패면 종료 코드 1.
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
    # 검사가 없는 것과 같다(check_tracked_imports.py 와 같은 이유).
    _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

BANNED = {"·": "가운뎃점(·)", "—": "em 대시(—)"}
ALLOW_MARKER = "clovi-allow-glyph"

SKIP_PARTS = {
    "node_modules", ".git", ".claude", "dist", "var", ".venv", "__pycache__",
    # 빌드 산출물 — 편집 대상이 아니다. 소스를 고치고 다시 빌드하면 따라온다.
    "react",
    # 내부 문서. 사용자에게 보이지 않는다.
    "docs",
}


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _collect(patterns: list[tuple[str, str]]) -> list[Path]:
    out: list[Path] = []
    for root, pattern in patterns:
        base = ROOT / root
        if not base.exists():
            continue
        out.extend(p for p in base.rglob(pattern) if not _skip(p))
    return sorted(set(out))


# ── 파이썬: tokenize 로 주석을 걷어내고, ast 로 docstring 을 걷어낸다 ────────────

def _python_docstring_lines(source: str) -> set[int]:
    """docstring 이 차지하는 줄 번호 집합.

    docstring 은 문자열 리터럴이라 tokenize 로는 주석과 구분되지 않는다. 그런데 이 저장소의
    docstring 은 사용자에게 보이지 않는 설명문이라 대상이 아니다 — ast 로 따로 걷어낸다.
    """
    lines: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                lines.add(ln)
    return lines


def _python_hits(path: Path) -> list[tuple[int, str, str]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    doc_lines = _python_docstring_lines(source)
    hits: list[tuple[int, str, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return hits
    raw_lines = source.splitlines()
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type != tokenize.STRING:
            continue
        if tok.start[0] in doc_lines:
            continue
        for ch, label in BANNED.items():
            if ch in tok.string:
                line_no = tok.start[0]
                line = raw_lines[line_no - 1] if line_no <= len(raw_lines) else ""
                if ALLOW_MARKER in line:
                    continue
                hits.append((line_no, label, line.strip()))
    return hits


# ── 주석만 걷어내는 스캐너 (JS/JSX, Jinja, CSS) ────────────────────────────────

def _strip_js_comments(text: str) -> str:
    """`//` 와 `/* */` 를 공백으로 바꾼다(줄 번호는 보존).

    문자열 안의 `//`(예: URL)를 주석으로 오인하지 않도록 따옴표 상태를 추적한다.
    정규식 리터럴은 추적하지 않는다 — 이 저장소의 정규식에 두 문자가 들어간 적이 없고,
    잘못 추적하면 오히려 멀쩡한 코드를 주석으로 지운다.
    """
    out = list(text)
    i, n = 0, len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            for _ in range(2):
                if i < n:
                    out[i] = " "
                    i += 1
            continue
        i += 1
    return "".join(out)


def _strip_jinja_comments(text: str) -> str:
    def blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))
    return re.sub(r"\{#.*?#\}", blank, text, flags=re.S)


def _scan_stripped(path: Path, stripped: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(stripped.splitlines(), start=1):
        raw = raw_lines[idx - 1] if idx <= len(raw_lines) else ""
        if ALLOW_MARKER in raw:
            continue
        for ch, label in BANNED.items():
            if ch in line:
                hits.append((idx, label, raw.strip()))
                break
    return hits


def main() -> int:
    targets: list[tuple[Path, list[tuple[int, str, str]]]] = []

    for path in _collect([("frontend/src", "*.jsx"), ("frontend/src", "*.js")]):
        if path.name.endswith((".test.js", ".test.jsx")):
            continue
        targets.append((path, _scan_stripped(path, _strip_js_comments(
            path.read_text(encoding="utf-8", errors="replace")))))

    for path in _collect([("app", "*.py")]):
        targets.append((path, _python_hits(path)))

    for path in _collect([("app/templates_html", "*.html")]):
        targets.append((path, _scan_stripped(path, _strip_jinja_comments(
            path.read_text(encoding="utf-8", errors="replace")))))

    for path in _collect([("app/static/css", "*.css"), ("frontend/src", "*.css"),
                          ("app/static/js", "*.js")]):
        targets.append((path, _scan_stripped(path, _strip_js_comments(
            path.read_text(encoding="utf-8", errors="replace")))))

    offenders = [(p, hits) for p, hits in targets if hits]
    total = sum(len(h) for _, h in offenders)
    if offenders:
        print("[FAIL] 사용자에게 보이는 문구에 쓰지 않기로 한 문자가 있다:")
        print(f"       (일부러 남겨야 하면 같은 줄에 {ALLOW_MARKER} 를 적어 둔다)")
        for path, hits in offenders:
            rel = path.relative_to(ROOT).as_posix()
            for line_no, label, snippet in hits[:6]:
                print(f"  - {rel}:{line_no}  {label}  {snippet[:100]}")
            if len(hits) > 6:
                print(f"    … 이 파일에 {len(hits) - 6}건 더")
        print(f"USER_TEXT_FAILED ({total}건, {len(offenders)}개 파일)")
        return 1
    print(f"USER_TEXT_OK (검사 {len(targets)}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
