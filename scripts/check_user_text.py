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

## 개발 내부 용어 (계획 5절)

사용자 지시: 개발 용어(Postfix, OpenDKIM, PKCE, OAuth transaction, password_ref, backend, worker, legacy, sync_status,
ai_usage_records, pairing token)는 일반 화면에 쓰지 않고 「기술 정보」 안에만 둔다. 「워커」 · 「백엔드」 같은 소리 옮김도
같은 말이다. 그래서 **한글이 든 사용자 문구**(프런트 문자열 · JSX 글, 서버 문자열, 메일 · HTML 틀)에 그 낱말이 있으면 실패다.

- 영문만 든 식별자 문자열(`"sync_status"` 같은 키)은 대상이 아니다 — 한글이 함께 있어야 사람에게 보이는 문장이다.
- 로그 호출의 인자(`logger.info(...)` 등)는 사람이 아니라 운영 기록이 읽으므로 뺀다. 시험 파일도 뺀다.
- 기술 정보 안처럼 일부러 남기는 줄에는 같은 줄에 `clovi-allow-term: 까닭` 을 적는다.
- `--self-test` 는 맞는 견본 · 틀린 견본으로 검사기 자신을 잰다(JSX 글 · 문자열 · 식별자 · 로그 · 표식).

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


# ── 개발 내부 용어 ────────────────────────────────────────────────────────────

TERM_ALLOW_MARKER = "clovi-allow-term"
HANGUL = re.compile(r"[가-힣]")
INTERNAL_TERMS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), name) for pattern, name in (
        (r"\bpostfix\b", "Postfix"), (r"\bopendkim\b", "OpenDKIM"), (r"\bpkce\b", "PKCE"),
        (r"oauth\s+transaction", "OAuth transaction"), (r"password_ref", "password_ref"),
        (r"\bbackend\b", "backend"), (r"\bworker\b", "worker"), (r"\blegacy\b", "legacy"),
        (r"\bsync_status\b", "sync_status"), (r"\bai_usage_records\b", "ai_usage_records"),
        (r"pairing\s+token", "pairing token"), (r"워커", "워커(worker)"), (r"백엔드", "백엔드(backend)"),
    )
)
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def _term_of(text: str) -> str | None:
    if not HANGUL.search(text):
        return None
    for rx, name in INTERNAL_TERMS:
        if rx.search(text):
            return name
    return None


def _js_text_spans(stripped: str) -> list[tuple[int, str]]:
    """주석을 걷은 JS/JSX 에서 사람에게 보일 수 있는 글 — 문자열 리터럴의 내용과, 따옴표 밖의 한글 구간(JSX 글).

    이 저장소는 식별자에 한글을 쓰지 않으므로 따옴표 밖의 한글은 JSX 글이다. 그 구간은 태그 · 중괄호 경계(`< > { }`)까지다.
    """
    spans: list[tuple[int, str]] = []
    i, n, line = 0, len(stripped), 1
    while i < n:
        ch = stripped[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in "\"'`":
            start_line, j, buf = line, i + 1, []
            while j < n and stripped[j] != ch:
                if stripped[j] == "\\":
                    buf.append(stripped[j:j + 2])
                    j += 2
                    continue
                if stripped[j] == "\n":
                    if ch != "`":
                        break
                    line += 1
                buf.append(stripped[j])
                j += 1
            spans.append((start_line, "".join(buf)))
            i = j + 1
            continue
        if HANGUL.match(ch):
            k = i
            while k > 0 and stripped[k - 1] not in "<>{}\n\"'`;(),=":
                k -= 1
            j = i
            while j < n and stripped[j] not in "<>{}\n\"'`":
                j += 1
            spans.append((line, stripped[k:j]))
            i = j
            continue
        i += 1
    return spans


def _js_term_hits(raw: str) -> list[tuple[int, str, str]]:
    raw_lines = raw.splitlines()
    hits: list[tuple[int, str, str]] = []
    for line_no, span in _js_text_spans(_strip_js_comments(raw)):
        name = _term_of(span)
        if not name:
            continue
        line = raw_lines[line_no - 1] if line_no <= len(raw_lines) else span
        if TERM_ALLOW_MARKER in line:
            continue
        hits.append((line_no, name, line.strip()))
    return hits


def _python_log_lines(source: str) -> set[int]:
    """로그 호출(`logger.info(...)` · `log.warning(...)` · `logging.error(...)`)이 차지하는 줄 — 그 인자는 운영 기록이다."""
    lines: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS):
            continue
        owner = node.func.value
        name = owner.id if isinstance(owner, ast.Name) else (owner.attr if isinstance(owner, ast.Attribute) else "")
        if "log" in name.lower():
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _python_term_hits(source: str) -> list[tuple[int, str, str]]:
    doc_lines = _python_docstring_lines(source)
    log_lines = _python_log_lines(source)
    raw_lines = source.splitlines()
    hits: list[tuple[int, str, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return hits
    for tok in tokens:
        if tok.type != tokenize.STRING or tok.start[0] in doc_lines or tok.start[0] in log_lines:
            continue
        name = _term_of(tok.string)
        if not name:
            continue
        line = raw_lines[tok.start[0] - 1] if tok.start[0] <= len(raw_lines) else ""
        if TERM_ALLOW_MARKER in line:
            continue
        hits.append((tok.start[0], name, line.strip()))
    return hits


def _template_term_hits(raw: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    raw_lines = raw.splitlines()
    for idx, line in enumerate(_strip_jinja_comments(raw).splitlines(), start=1):
        name = _term_of(line)
        if name and TERM_ALLOW_MARKER not in raw_lines[idx - 1]:
            hits.append((idx, name, raw_lines[idx - 1].strip()))
    return hits


def term_targets() -> list[tuple[Path, list[tuple[int, str, str]]]]:
    out: list[tuple[Path, list[tuple[int, str, str]]]] = []
    for path in _collect([("frontend/src", "*.jsx"), ("frontend/src", "*.js")]):
        if path.name.endswith((".test.js", ".test.jsx")):
            continue
        out.append((path, _js_term_hits(path.read_text(encoding="utf-8", errors="replace"))))
    for path in _collect([("app", "*.py")]):
        out.append((path, _python_term_hits(path.read_text(encoding="utf-8", errors="replace"))))
    for path in _collect([("app", "*.j2"), ("app/templates_html", "*.html")]):
        out.append((path, _template_term_hits(path.read_text(encoding="utf-8", errors="replace"))))
    return out


def self_test() -> int:
    """맞는 견본은 하나도 걸리면 안 되고 틀린 견본은 전부 걸려야 한다."""
    bad_js = [
        'const A = () => <Typography>워커가 응답하지 않습니다.</Typography>;',
        'toast("백엔드 오류로 저장하지 못했습니다.");',
        'const msg = `Postfix 를 다시 시작합니다.`;',
        'const help = "legacy 정책은 숨겼습니다.";',
    ]
    good_js = [
        'const workerStatus = "상태";',
        'const key = "sync_status";',
        'const A = () => <TechDetail>{raw}</TechDetail>;',
        'const note = "기술 정보: worker 큐"; // clovi-allow-term: 기술 정보 접기 안의 원문',
        '// 워커가 응답하지 않으면 다시 시도한다',
    ]
    bad_py = ['raise ValidationAppError("password_ref 는 고칠 수 없습니다.")\n', 'MESSAGE = "백그라운드 worker 가 멈췄습니다."\n']
    good_py = ['logger.info("워커 리스를 잡았다: %s", owner)\n', 'logger.warning(\n    "다른 워커가 이미 돌고 있다"\n)\n', 'KEY = "ai_usage_records"\n']
    problems: list[str] = []
    for src in bad_js:
        if not _js_term_hits(src):
            problems.append(f"틀린 견본을 못 잡음(JS): {src}")
    for src in good_js:
        if _js_term_hits(src):
            problems.append(f"맞는 견본을 잘못 잡음(JS): {src}")
    for src in bad_py:
        if not _python_term_hits(src):
            problems.append(f"틀린 견본을 못 잡음(PY): {src.strip()}")
    for src in good_py:
        if _python_term_hits(src):
            problems.append(f"맞는 견본을 잘못 잡음(PY): {src.strip()}")
    if _template_term_hits("<p>{# 워커 #}메일 서버가 접수했습니다.</p>\n") or not _template_term_hits("<p>OpenDKIM 이 서명했습니다.</p>\n"):
        problems.append("틀 견본 판정이 틀림")
    if problems:
        for p in problems:
            print(f"  - {p}")
        print("USER_TEXT_SELF_TEST_FAILED")
        return 1
    print(f"USER_TEXT_SELF_TEST_OK (틀린 견본 {len(bad_js) + len(bad_py) + 1}개 전부 잡음, 맞는 견본 {len(good_js) + len(good_py) + 1}개 오탐 0)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
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
    terms = term_targets()
    term_offenders = [(p, hits) for p, hits in terms if hits]
    term_total = sum(len(h) for _, h in term_offenders)
    if offenders:
        print("[FAIL] 사용자에게 보이는 문구에 쓰지 않기로 한 문자가 있다:")
        print(f"       (일부러 남겨야 하면 같은 줄에 {ALLOW_MARKER} 를 적어 둔다)")
        for path, hits in offenders:
            rel = path.relative_to(ROOT).as_posix()
            for line_no, label, snippet in hits[:6]:
                print(f"  - {rel}:{line_no}  {label}  {snippet[:100]}")
            if len(hits) > 6:
                print(f"    … 이 파일에 {len(hits) - 6}건 더")
    if term_offenders:
        print("[FAIL] 사용자에게 보이는 문구에 개발 내부 용어가 있다(계획 5절 — 기술 정보 안에만 둔다):")
        print(f"       (일부러 남겨야 하면 같은 줄에 {TERM_ALLOW_MARKER}: 까닭 을 적어 둔다)")
        for path, hits in term_offenders:
            rel = path.relative_to(ROOT).as_posix()
            for line_no, label, snippet in hits[:6]:
                print(f"  - {rel}:{line_no}  {label}  {snippet[:100]}")
            if len(hits) > 6:
                print(f"    … 이 파일에 {len(hits) - 6}건 더")
    if offenders or term_offenders:
        print(f"USER_TEXT_FAILED (글리프 {total}건 · 내부 용어 {term_total}건)")
        return 1
    print(f"USER_TEXT_OK (검사 {len(targets)}개 파일 · 내부 용어 {len(terms)}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
