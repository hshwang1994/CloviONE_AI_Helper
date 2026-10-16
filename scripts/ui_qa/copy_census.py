"""문구 대장 (r23 W0b) — 사용자에게 보이는 한국어 문구를 **원본에서 전부** 모으고, 화면에 실제로 보인 글자와 맞춘다.

단어 몇 개를 grep 하는 것으로는 전수 검수가 아니다. 이 도구는 세 단계다:

  extract   원본 문구를 모은다 — 프런트 문자열 · JSX 글(`frontend/src`, 시험 제외), 서버 문자열(`app/**`, docstring · 로그 제외),
            메일 · HTML 틀. 추출기는 `scripts/check_user_text.py` 와 같은 것을 쓴다(주석 · docstring · 로그를 같은 규칙으로 뺀다).
            줄마다 파일:줄 · 원문(`${…}` 자리 보존) · 종류(속성 · 호출 이름에서 짐작) · 맥락(함수 · 컴포넌트)을 남긴다.
  map       `screen_ledger` 가 화면 · 상태마다 모은 「보인 글자」를 원본 줄에 붙인다 — 같은 글, 또는 `${…}` 를 자리 패턴으로 바꾼 틀.
            원본 줄마다 「보이는 화면 · 상태」가 생긴다. 원본이 없는 보인 글은 사용자 데이터인지 놓친 원본인지 가른다.
  report    판정 파일(`decisions/*.csv`)을 합쳐 대장 CSV 와 수를 낸다: 검토 · 변경 · 유지 · 보류 · 미검증 · 화면 밖.
            판정이 없는 줄은 「미검토」로 센다 — 0 이 아니면 대장은 끝나지 않았다.

    python -m scripts.ui_qa.copy_census extract
    python -m scripts.ui_qa.copy_census map --ledger dist/ui-qa/r23-before-text/ledger.json
    python -m scripts.ui_qa.copy_census sheet --domain user      # 판정할 줄을 영역별로 내보낸다
    python -m scripts.ui_qa.copy_census report --out docs/platform/EVIDENCE/ui/2026-10-16-copy-census.csv
    python -m scripts.ui_qa.copy_census --self-test
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_user_text as cut  # noqa: E402

WORK = ROOT / "dist" / "ui-qa" / "copy-census"
HANGUL = re.compile(r"[가-힣]")
PLACEHOLDER = re.compile(r"\$\{[^}]*\}")

# 판정 영역 — 나눠 맡는 단위. 파일 경로의 앞부분으로 정한다(먼저 맞는 것).
DOMAINS = (
    ("server", ("app/",)),
    ("admin", (
        "frontend/src/screens/Dashboard", "frontend/src/screens/ops/", "frontend/src/screens/Integrity",
        "frontend/src/screens/integrity/", "frontend/src/screens/mail/", "frontend/src/screens/ai/",
        "frontend/src/screens/settings/", "frontend/src/screens/setup/", "frontend/src/screens/SetupWizard",
        "frontend/src/screens/SystemOps", "frontend/src/screens/StorageProviders", "frontend/src/screens/Users",
        "frontend/src/screens/Offboarding", "frontend/src/screens/Org", "frontend/src/screens/org/",
        "frontend/src/screens/registry", "frontend/src/screens/data-screen/", "frontend/src/screens/DataScreen",
        "frontend/src/screens/DevReport", "frontend/src/screens/SchedulerCalendar", "frontend/src/screens/Settings",
        "frontend/src/screens/Ops", "frontend/src/screens/Maintenance",
    )),
    ("user", ("frontend/src/screens/",)),
    ("shell", ("frontend/src/app/", "frontend/src/lib/", "frontend/src/ui/", "frontend/src/")),
)

# 화면에 안 나오는 문구 — 근거를 같이 적는다(판정 「화면 밖」).
OFFSCREEN = (
    ("app/ai/prompts/", "모델에게 보내는 지시문이다(사람 화면이 아니다)."),
    ("app/ai/assistant/prompt", "모델에게 보내는 지시문이다(사람 화면이 아니다)."),
    ("app/cli/", "설치 · 운영 명령줄 출력이다(웹 화면이 아니다)."),
    ("app/migration/", "이관 도구 출력이다(웹 화면이 아니다)."),
    ("frontend/src/generated/", "생성 파일이다."),
)


def _domain(rel: str) -> str:
    for name, prefixes in DOMAINS:
        if any(rel.startswith(p) for p in prefixes):
            return name
    return "shell"


def _offscreen(rel: str) -> str:
    for prefix, why in OFFSCREEN:
        if rel.startswith(prefix):
            return why
    return ""


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def entry_key(rel: str, line: int, text: str) -> str:
    return hashlib.sha1(f"{rel}:{line}:{norm(text)}".encode("utf-8")).hexdigest()[:12]


# ── extract ───────────────────────────────────────────────────────────────────
_PROP = re.compile(r"([A-Za-z_$][\w$-]*)\s*(?:=\s*\{?\s*|:\s*\(?\s*)$")
_CALL = re.compile(r"([A-Za-z_$][\w$.]*)\s*\(\s*(?:[^()]*,\s*)?$")
_FUNC = re.compile(r"(?:function\s+([A-Z_a-z$][\w$]*)|(?:const|let)\s+([A-Z_a-z$][\w$]*)\s*=\s*(?:\([^)]*\)|[\w$]+)\s*=>)")

KIND_BY_NAME = {
    "title": "제목", "label": "라벨", "placeholder": "placeholder", "aria-label": "접근 이름", "ariaLabel": "접근 이름",
    "help": "도움말", "description": "도움말", "hint": "도움말", "note": "도움말", "situation": "빈 상태",
    "emptyTitle": "빈 상태", "emptyHelp": "빈 상태", "empty": "빈 상태", "emptySituation": "빈 상태",
    "filteredTitle": "빈 상태", "filteredHelp": "빈 상태", "toast": "알림", "confirm": "확인 창",
    "confirmLabel": "단추", "submitLabel": "단추", "moreLabel": "단추", "clearLabel": "단추", "retryLabel": "단추",
    "message": "메시지", "error": "오류", "question": "차트 질문", "toneLabel": "상태 낱말", "totalLabel": "합계 낱말",
    "deniedHelp": "권한 안내", "noun": "대상 낱말", "unit": "단위",
}


def _js_spans(stripped: str) -> list[tuple[int, int, str, bool]]:
    """`check_user_text._js_text_spans` 와 같은 규칙에 시작 위치와 「따옴표 안인가」를 더한다."""
    spans: list[tuple[int, int, str, bool]] = []
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
            spans.append((start_line, i, "".join(buf), True))
            i = j + 1
            continue
        if HANGUL.match(ch):
            k = i
            while k > 0 and stripped[k - 1] not in "<>{}\n\"'`;(),=":
                k -= 1
            j = i
            while j < n and stripped[j] not in "<>{}\n\"'`":
                j += 1
            spans.append((line, k, stripped[k:j], False))
            i = j
            continue
        i += 1
    return spans


def _js_entries(rel: str, raw: str) -> list[dict]:
    stripped = cut._strip_js_comments(raw)
    funcs = [(m.start(), m.group(1) or m.group(2)) for m in _FUNC.finditer(stripped)]
    raw_lines = raw.splitlines()
    out = []
    for line, start, text, quoted in _js_spans(stripped):
        if not HANGUL.search(text):
            continue
        before = stripped[max(0, start - 80):start]
        prop = _PROP.search(before.rstrip()) if quoted else None
        call = _CALL.search(before) if quoted else None
        name = (prop.group(1) if prop else "") or (call.group(1).split(".")[-1] if call else "")
        kind = KIND_BY_NAME.get(name, "JSX 글" if not quoted else "문자열")
        func = ""
        for pos, fname in funcs:
            if pos > start:
                break
            func = fname
        src = raw_lines[line - 1] if line <= len(raw_lines) else ""
        if "import.meta.env.DEV" in stripped[max(0, start - 600):start] and "throw new Error" in stripped[max(0, start - 200):start]:
            kind = "개발 모드 오류"
        out.append({"file": rel, "line": line, "text": norm(text), "kind": kind, "prop": name, "func": func,
                    "src": src.strip()[:200]})
    return out


def _py_entries(rel: str, source: str) -> list[dict]:
    doc = cut._python_docstring_lines(source)
    logs = cut._python_log_lines(source)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    defs = sorted(((n.lineno, n.end_lineno or n.lineno, n.name) for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))), key=lambda d: d[0])
    lines = source.splitlines()
    # 줄 · 칸 → 원문 위치. 파이썬 3.12 부터 f-문자열은 STRING 하나가 아니라 FSTRING_START · MIDDLE · END 토큰이라
    # 시작과 끝 위치로 원문을 잘라 한 문자열로 되살린다.
    offsets = [0]
    for ln in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(ln))

    def at(pos):
        return offsets[pos[0] - 1] + pos[1]

    literals = []
    fstart = getattr(tokenize, "FSTRING_START", None)
    fend = getattr(tokenize, "FSTRING_END", None)
    depth, begin = 0, None
    for tok in tokens:
        if fstart is not None and tok.type == fstart:
            if depth == 0:
                begin = tok.start
            depth += 1
        elif fend is not None and tok.type == fend:
            depth -= 1
            if depth == 0 and begin is not None:
                literals.append((begin, source[at(begin):at(tok.end)]))
        elif tok.type == tokenize.STRING and depth == 0:
            literals.append((tok.start, tok.string))
    out = []
    for start, literal in literals:
        if start[0] in doc or start[0] in logs:
            continue
        m = re.match(r"^([rRbBuUfF]{0,2})('''|\"\"\"|'|\")", literal)
        if not m:
            continue
        prefix, quote = m.group(1).lower(), m.group(2)
        body = literal[len(m.group(1)) + len(quote): -len(quote)]
        if "f" in prefix:
            body = re.sub(r"(?<!\{)\{([^{}]*)\}(?!\})", r"${\1}", body).replace("{{", "{").replace("}}", "}")
        if not HANGUL.search(body):
            continue
        line = start[0]
        src = lines[line - 1] if line <= len(lines) else ""
        func = ""
        for a, b, name in defs:
            if a <= line <= b:
                func = name
        kind = "서버 오류" if re.search(r"\braise\b|Error\(", src) else "서버 문자열"
        out.append({"file": rel, "line": line, "text": norm(body), "kind": kind, "prop": "", "func": func,
                    "src": src.strip()[:200]})
    return out


def _template_entries(rel: str, raw: str) -> list[dict]:
    out = []
    stripped = cut._strip_jinja_comments(raw)
    for idx, line in enumerate(stripped.splitlines(), start=1):
        text = norm(re.sub(r"<[^>]+>", " ", line))
        if HANGUL.search(text):
            out.append({"file": rel, "line": idx, "text": text, "kind": "메일 · HTML 틀", "prop": "", "func": "", "src": line.strip()[:200]})
    return out


def extract() -> Path:
    entries: list[dict] = []
    for path in sorted((ROOT / "frontend" / "src").rglob("*")):
        if path.suffix not in (".js", ".jsx") or ".test." in path.name or "test-helpers" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        entries += _js_entries(rel, path.read_text(encoding="utf-8", errors="replace"))
    for path in sorted((ROOT / "app").rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if "static" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix == ".py":
            entries += _py_entries(rel, path.read_text(encoding="utf-8", errors="replace"))
        elif path.suffix in (".j2", ".html"):
            entries += _template_entries(rel, path.read_text(encoding="utf-8", errors="replace"))
    for e in entries:
        e["key"] = entry_key(e["file"], e["line"], e["text"])
        e["domain"] = _domain(e["file"])
        e["offscreen"] = _offscreen(e["file"]) or ("개발 모드에서만 던지는 오류다." if e["kind"] == "개발 모드 오류" else "")
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "inventory.json"
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=0), encoding="utf-8")
    by = {}
    for e in entries:
        by[e["domain"]] = by.get(e["domain"], 0) + 1
    print(f"COPY_CENSUS_EXTRACT {len(entries)}줄 {by} → {out}")
    return out


# ── map ───────────────────────────────────────────────────────────────────────
def _matcher(text: str):
    """원본 한 줄 → 보인 글과 맞추는 함수. `${…}` 는 아무 값이 들어간 자리다. 한글이 두 자 안 되는 조각은 같을 때만 맞춘다."""
    if "${" in text:
        parts = PLACEHOLDER.split(text)
        literal = "".join(parts)
        if len(HANGUL.findall(literal)) < 2:
            return None
        rx = re.compile(".{0,80}?".join(re.escape(p) for p in parts))
        return lambda s: bool(rx.search(s))
    if len(HANGUL.findall(text)) < 2:
        return lambda s: s == text
    return lambda s: text in s


def map_ledgers(ledgers: list[Path]) -> Path:
    entries = json.loads((WORK / "inventory.json").read_text(encoding="utf-8"))
    shown: list[tuple[str, str, str]] = []   # (보인 글, 화면 번호, 화면 이름)
    for ledger in ledgers:
        data = json.loads(Path(ledger).read_text(encoding="utf-8"))
        for row in data.get("rows", []):
            for t in row.get("text", []) or []:
                shown.append((t["text"], row["id"], row["name"]))
    by_case: dict[str, list[str]] = {}
    for text, cid, _name in shown:
        by_case.setdefault(cid, []).append(text)
    blobs = {cid: "\n".join(sorted(set(texts))) for cid, texts in by_case.items()}
    names = {cid: name for _t, cid, name in shown}
    hits: dict[str, list[str]] = {}
    for e in entries:
        fn = _matcher(e["text"])
        if fn is None:
            continue
        lit = "".join(PLACEHOLDER.split(e["text"]))
        anchor = max((lit[i:i + 2] for i in range(len(lit) - 1)), key=len, default="")
        cases = []
        for cid, blob in blobs.items():
            if anchor and anchor not in blob:
                continue
            if any(fn(s) for s in blob.split("\n")):
                cases.append(cid)
        if cases:
            hits[e["key"]] = sorted(cases)
    matched_texts = set()
    for e in entries:
        if e["key"] in hits:
            matched_texts.add(e["text"])
    orphans: dict[str, set] = {}
    for text, cid, _ in shown:
        if not any(m in text for m in matched_texts if len(m) >= 4):
            orphans.setdefault(text, set()).add(cid)
    out = WORK / "map.json"
    out.write_text(json.dumps({"ledgers": [str(x) for x in ledgers], "hits": hits, "names": names,
                               "orphans": {k: sorted(v) for k, v in orphans.items()}}, ensure_ascii=False), encoding="utf-8")
    print(f"COPY_CENSUS_MAP 원본 {len(entries)}줄 중 화면에서 본 줄 {len(hits)} · 원본 못 찾은 보인 글 {len(orphans)} → {out}")
    return out


# ── sheet · report ────────────────────────────────────────────────────────────
SHEET_COLS = ["key", "domain", "file", "line", "kind", "prop", "func", "text", "screens", "seen",
              "decision", "after", "reason", "condition"]
DECISIONS = ("변경", "유지", "보류", "화면 밖")


def _load_map() -> dict:
    path = WORK / "map.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"hits": {}, "names": {}}


def sheet(domain: str) -> Path:
    """판정할 줄을 영역별 CSV 로 — 판정자는 decision · after · reason · condition 네 칸을 채운다."""
    entries = json.loads((WORK / "inventory.json").read_text(encoding="utf-8"))
    hits = _load_map().get("hits", {})
    rows = [e for e in entries if e["domain"] == domain]
    out = WORK / "sheets" / f"{domain}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLS)
        w.writeheader()
        for e in rows:
            screens = hits.get(e["key"], [])
            w.writerow({"key": e["key"], "domain": e["domain"], "file": e["file"], "line": e["line"], "kind": e["kind"],
                        "prop": e["prop"], "func": e["func"], "text": e["text"], "screens": " ".join(screens),
                        "seen": "Y" if screens else "N",
                        "decision": "화면 밖" if e.get("offscreen") else "", "after": "",
                        "reason": e.get("offscreen", ""), "condition": ""})
    print(f"COPY_CENSUS_SHEET {domain} {len(rows)}줄 → {out}")
    return out


def _decisions() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((WORK / "decisions").glob("*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("key"):
                    out[row["key"]] = row
    return out


def report(out_csv: Path | None) -> int:
    entries = json.loads((WORK / "inventory.json").read_text(encoding="utf-8"))
    mp = _load_map()
    hits, names = mp.get("hits", {}), mp.get("names", {})
    dec = _decisions()
    counts = {d: 0 for d in DECISIONS}
    counts.update({"미검토": 0, "변경·브라우저 확인": 0, "변경·브라우저 미검증": 0, "유지·브라우저 확인": 0, "유지·브라우저 미검증": 0})
    rows = []
    for e in entries:
        d = dec.get(e["key"], {})
        decision = (d.get("decision") or ("화면 밖" if e.get("offscreen") else "")).strip()
        if decision not in DECISIONS:
            decision = "미검토"
        counts[decision] = counts.get(decision, 0) + 1
        seen = hits.get(e["key"], [])
        if decision in ("변경", "유지"):
            counts[f"{decision}·브라우저 {'확인' if seen else '미검증'}"] += 1
        rows.append({
            "화면": " ".join(seen), "화면 이름": " · ".join(names.get(s, "") for s in seen[:6]),
            "종류": e["kind"], "소스 위치": f"{e['file']}:{e['line']}", "기존 문구": e["text"],
            "변경 후 문구": (d.get("after") or "").strip(), "판정": decision,
            "이유": (d.get("reason") or e.get("offscreen") or "").strip(),
            "기능 · 조회 조건": (d.get("condition") or "").strip(),
            "브라우저 확인": "화면에서 봄" if seen else "화면에서 못 봄",
        })
    if out_csv:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("COPY_CENSUS_REPORT 원본 %d줄 %s" % (len(entries), json.dumps(counts, ensure_ascii=False)))
    return 0 if counts["미검토"] == 0 else 1


def self_test() -> int:
    fails = []
    src = 'export function A(){ return <Box title="저장했습니다." help={`${n}건을 받았습니다.`}>검색 결과가 없습니다</Box>; }'
    got = {(e["kind"], e["text"]) for e in _js_entries("frontend/src/x.jsx", src)}
    for want in (("제목", "저장했습니다."), ("도움말", "${n}건을 받았습니다."), ("JSX 글", "검색 결과가 없습니다")):
        if want not in got:
            fails.append(f"JS 추출이 {want} 를 못 냈다: {got}")
    py = 'def f(n):\n    """설명은 빼야 한다."""\n    raise ValueError(f"참가자는 {n}명 이상이어야 합니다.")\n'
    pe = _py_entries("app/x.py", py)
    if [e["text"] for e in pe] != ["참가자는 ${n}명 이상이어야 합니다."] or pe[0]["kind"] != "서버 오류":
        fails.append(f"파이썬 추출이 틀렸다: {pe}")
    m = _matcher("${n}건을 받았습니다.")
    if not m("12건을 받았습니다.") or m("받았다"):
        fails.append("틀 맞추기가 틀렸다")
    short = _matcher("건")
    if short("12건을 받았습니다.") or not short("건"):
        fails.append("한 글자 조각은 같을 때만 맞춰야 한다")
    for f_ in fails:
        print("  -", f_)
    print("COPY_CENSUS_SELFTEST_" + ("OK" if not fails else "FAIL"))
    return 0 if not fails else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="문구 대장(r23)")
    ap.add_argument("command", nargs="?", choices=("extract", "map", "sheet", "report"))
    ap.add_argument("--ledger", nargs="*", default=[])
    ap.add_argument("--domain", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.command == "extract":
        extract()
        return 0
    if args.command == "map":
        map_ledgers([Path(x) for x in args.ledger])
        return 0
    if args.command == "sheet":
        for d in ([args.domain] if args.domain else [n for n, _ in DOMAINS]):
            sheet(d)
        return 0
    if args.command == "report":
        return report(Path(args.out) if args.out else None)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
