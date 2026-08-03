"""죽은 CSS 규칙을 지운다 (기본은 dry-run).

`find_dead_css.py` 가 '누가 안 쓰는가'를 알려 주면, 이 스크립트가 실제로 걷어낸다.
손으로 지우면 안 되는 이유는 콤마로 묶인 셀렉터다:

    .c-btn, .k-chip, button { … }      ← .k-chip 만 죽었다

규칙을 통째로 지우면 살아 있는 둘까지 죽고, 그대로 두면 죽은 것이 남는다.
셀렉터 목록에서 **죽은 조각만** 빼야 한다.

## 왜 '재조립'이 아니라 '구간 교체'인가

처음에는 CSS 를 파싱해 살아남은 규칙만 이어 붙이는 식으로 짰다가 버렸다. 두 가지가
드러났기 때문이다:
  - 규칙 앞 주석이 셀렉터에 딸려 들어가, 주석 안의 콤마에서 셀렉터가 쪼개졌다.
  - **제거 0건인데 파일 크기가 바뀌었다.** 왕복이 항등이 아니라는 뜻이고, 그러면
    "안 건드린 곳은 안 건드렸다"를 보장할 수 없다.
CSS 는 지워도 빌드가 안 깨지고 테스트도 안 깨진다. 조용히 어긋나는 것이 가장 나쁜
실패라, 도구가 항등을 보장하지 못하면 쓰면 안 된다.

그래서 지금은 **바뀌는 구간만 교체**한다. 손대지 않은 바이트는 정의상 그대로다.
`--selftest` 로 '아무것도 죽지 않았다'고 가정해 돌리면 출력이 입력과 바이트 동일해야
한다(그 자체를 검사로 넣어 뒀다).

안전 규칙:
  - 클래스를 하나도 참조하지 않는 셀렉터(`html`, `:root`, `*`, `#id`)는 건드리지 않는다.
  - 조각에 살아 있는 클래스가 하나라도 있으면 남긴다.
  - `@media` / `@supports` 안쪽도 같은 규칙으로 처리한다.
  - `@keyframes` 안의 `from`/`to`/`0%` 는 셀렉터가 아니므로 손대지 않는다.
  - 판정은 **소스 전체** 기준이다. 파일 단위로 보면 다른 CSS 에 선언된 클래스를
    죽은 것으로 오판한다.

사용법:
  .venv/Scripts/python.exe scripts/prune_dead_css.py             # 무엇을 지울지 보여주기만
  .venv/Scripts/python.exe scripts/prune_dead_css.py --selftest  # 항등 보장 확인
  .venv/Scripts/python.exe scripts/prune_dead_css.py --apply     # 실제로 지운다
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.find_dead_css import (  # noqa: E402
    CLASS_IN_SELECTOR,
    css_files,
    is_used,
    source_blob,
)

AT_RULE_WITH_BLOCK = re.compile(r"@(media|supports|container|layer)\b", re.I)
AT_KEYFRAMES = re.compile(r"@(-\w+-)?keyframes\b", re.I)
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def rules(css: str, offset: int = 0) -> list[tuple[int, int, int, int, str]]:
    """최상위 규칙들을 (프렐류드시작, 프렐류드끝, 본문시작, 규칙끝, 종류)로 돌려준다.

    문자열/주석 안의 중괄호에 속지 않게 상태를 들고 센다.
    """
    out = []
    depth = 0
    i = 0
    prelude_start = 0
    body_start = -1
    n = len(css)
    while i < n:
        ch = css[i]
        if ch == "/" and i + 1 < n and css[i + 1] == "*":
            end = css.find("*/", i + 2)
            i = (end + 2) if end != -1 else n
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            while i < n and css[i] != quote:
                i += 2 if css[i] == "\\" else 1
            i += 1
            continue
        if ch == "{":
            if depth == 0:
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                head = css[prelude_start:body_start - 1]
                kind = ("keyframes" if AT_KEYFRAMES.search(head)
                        else "nested" if AT_RULE_WITH_BLOCK.search(head)
                        else "rule")
                out.append((prelude_start + offset, body_start - 1 + offset,
                            body_start + offset, i + 1 + offset, kind))
                prelude_start = i + 1
        i += 1
    return out


def selector_edits(css: str, blob: str, offset: int = 0) -> list[tuple[int, int, str, list[str]]]:
    """(시작, 끝, 새 내용, 지워진 조각들) 목록. 끝에서부터 적용하면 된다."""
    edits: list[tuple[int, int, str, list[str]]] = []
    for ps, pe, bs, re_, kind in rules(css, offset):
        if kind == "keyframes":
            continue
        if kind == "nested":
            inner = css[bs - offset:re_ - offset - 1]
            edits += selector_edits(inner, blob, offset=bs)
            continue
        prelude = css[ps - offset:pe - offset]
        # 셀렉터만 본다 — 앞에 붙은 주석은 콤마를 품을 수 있어 그대로 두고 판정에서 뺀다.
        last_comment = prelude.rfind("*/")
        sel_start_rel = last_comment + 2 if last_comment != -1 else 0
        selector = prelude[sel_start_rel:]
        kept, dropped = [], []
        for part in selector.split(","):
            stripped = COMMENT.sub("", part).strip()
            if not stripped:
                continue
            classes = CLASS_IN_SELECTOR.findall(stripped)
            if not classes or any(is_used(c, blob) for c in classes):
                kept.append(part)
            else:
                dropped.append(stripped)
        if not dropped:
            continue
        if kept:
            # 셀렉터만 갈아 끼운다. 앞 주석과 규칙 본문은 손대지 않는다.
            edits.append((ps + sel_start_rel, pe, ",".join(kept), dropped))
        else:
            # 규칙 전체가 죽었다 — 앞 주석까지 함께 걷어낸다(그 규칙만 설명하던 글이다).
            edits.append((ps, re_, "", dropped))
    return edits


def apply_edits(css: str, edits: list[tuple[int, int, str, list[str]]]) -> str:
    for start, end, replacement, _ in sorted(edits, key=lambda e: e[0], reverse=True):
        css = css[:start] + replacement + css[end:]
    return css


def main() -> int:
    apply = "--apply" in sys.argv
    selftest = "--selftest" in sys.argv
    files = css_files()
    if not files:
        print("CSS 가 없다", file=sys.stderr)
        return 1

    if selftest:
        # '아무것도 죽지 않았다'고 가정하면 출력은 입력과 바이트 동일해야 한다.
        everything_alive = "\n".join(p.read_text(encoding="utf-8") for p in files)
        bad = 0
        for path in files:
            original = path.read_text(encoding="utf-8")
            out = apply_edits(original, selector_edits(original, everything_alive))
            same = out == original
            print(f"  {path.name:<16} {'항등' if same else '**달라졌다**'}")
            bad += 0 if same else 1
        print("\nSELFTEST_OK" if not bad else f"\nSELFTEST_FAILED ({bad}개 파일)")
        return 0 if not bad else 1

    blob = source_blob()
    total = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        edits = selector_edits(original, blob)
        dropped = [d for e in edits for d in e[3]]
        pruned = apply_edits(original, edits)
        total += len(dropped)
        print(f"{path.name:<16} 셀렉터 {len(dropped):>4}개 제거, "
              f"{len(original) - len(pruned):>6,} bytes 절감  "
              f"({len(original):,} → {len(pruned):,})")
        for d in dropped[:4]:
            print(f"    - {d[:88]}")
        if len(dropped) > 4:
            print(f"    … 외 {len(dropped) - 4}개")
        if apply:
            path.write_text(pruned, encoding="utf-8")

    print("")
    if apply:
        print(f"적용 완료 — 셀렉터 {total}개 제거. 빌드하고 QA 하네스로 화면을 확인하라.")
    else:
        print(f"dry-run — 셀렉터 {total}개가 제거 대상이다. 적용하려면 --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
