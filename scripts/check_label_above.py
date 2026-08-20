# -*- coding: utf-8 -*-
"""라벨이 **입력 칸 안으로 내려앉지** 않는가 (지시 17 · PLAN C2 · W5).

## 무엇이 문제였나

MUI 의 기본은 **떠 있는 라벨**이다 — 값이 없으면 입력 칸 안에 앉아 있다가 포커스하면 위로
올라가 테두리에 걸친다. 그 방식은 셋을 잃는다.

  · 훑을 수 없다. 값이 든 칸과 빈 칸의 라벨 위치가 달라 세로로 라벨을 따라 읽지 못한다.
  · 같은 줄에 선 컨트롤끼리 **기준선이 어긋난다** — 한쪽은 라벨이 안에 있고 한쪽은 위에 있다.
  · 한국어는 노치 폭 안에서 자주 잘린다.

실측(W5 조사 F-W5D-132, `dist/ui-qa/w4-after/light/1920x1080/user_new-ticket.png`): 한 폼 안에
「제목 *」은 입력 칸 **안**, 「진행상태」는 노치 **위**, 「예상 WD」는 라벨 없이 placeholder 만
있었다 — 세 종류가 동시에 보인다.

## 왜 정적 검사인가

계약 시험(`ui/form-label-above.test.jsx`)은 `FormField` **하나만** 렌더한다. 즉 이미 지키는
컴포넌트 위에서만 초록이고, kit 밖에서 손으로 만든 입력은 표본이 0이었다(F-W5D-133).
브라우저 프로브도 «그려진 것» 만 보므로 모달 안·권한 없는 폼·조건부 필드를 놓친다.
선언을 읽는 이 검사가 그 사각을 덮는다.

## 규칙

`<TextField label=...>` 에는 `InputLabelProps`(=`shrink` 를 든 것) 또는 `EMPTYABLE_SELECT`
전개가 **함께** 있어야 한다. 라벨을 아예 안 쓰고 `FieldLabel` 로 바깥에 그리는 것도 물론 통과다
(이 검사가 보는 것은 «label prop 을 쓰면서 떠 있게 두는 것» 하나다).
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("frontend/src/ui", "frontend/src/screens", "frontend/src/app")

OPEN_RE = re.compile(r"<TextField\b")
LABEL_RE = re.compile(r"(?<![A-Za-z])label=")
SHRINK_RE = re.compile(r"InputLabelProps|EMPTYABLE_SELECT")


def element_span(text: str, start: int) -> int | None:
    """`<TextField` 시작 위치에서 그 여는 태그가 끝나는 `>` 위치를 찾는다.

    JSX 는 정규식으로 못 자른다 — `sx={{ ... }}` 안에 `>` 가 들어간다(`"&:hover > *"`).
    중괄호 깊이를 세면서 깊이 0 의 `>` 를 찾는다. 문자열 안의 중괄호까지는 안 센다(이
    저장소의 JSX 에서 그런 형태가 나온 적이 없고, 세려면 파서를 들여야 한다).
    """
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            return i
        i += 1
    return None


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    offenders: list[str] = []
    checked = 0
    for rel in SCAN_DIRS:
        base = REPO_ROOT / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.jsx")):
            if ".test." in path.name:
                continue
            text = io.open(path, encoding="utf-8").read()
            for m in OPEN_RE.finditer(text):
                end = element_span(text, m.end())
                if end is None:
                    continue
                el = text[m.start():end]
                checked += 1
                if LABEL_RE.search(el) and not SHRINK_RE.search(el):
                    line = text.count("\n", 0, m.start()) + 1
                    offenders.append(
                        "%s:%d" % (path.relative_to(REPO_ROOT).as_posix(), line))

    if offenders:
        print("[FAIL] 라벨이 입력 칸 안으로 내려앉는 자리가 있다 "
              "(`InputLabelProps={{ shrink: true }}` 를 함께 주거나 `FieldLabel` 로 바깥에 그려라):")
        for o in offenders:
            print("   ", o)
        print("LABEL_ABOVE_FAILED (%d건 / TextField %d개)" % (len(offenders), checked))
        return 1

    print("LABEL_ABOVE_OK (TextField %d개 확인)" % checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
