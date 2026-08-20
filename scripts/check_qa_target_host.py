# -*- coding: utf-8 -*-
"""QA 하네스가 **어느 제품을 치는가**.

## 왜 이 검사가 따로 있는가

`check_tenant_defaults.py` 는 「설치 산출물에 고객사 고유 식별자가 박혀 있는가」를 묻고,
그래서 `scripts/ui_qa/` 를 이유와 함께 면제한다 — 개발자가 자기 로컬에서 화면을 찍어 보는
도구는 설치처로 나가지 않는다. 그 판단은 지금도 맞다.

하지만 그 면제가 **다른 결함**을 가렸다. 제품 이름이 `ClovirAssist` 로 바뀌고 canonical
호스트가 `clovirassist.gooddi.lab` 이 된 뒤에도, 보조 프로브 14개가 각자 옛 호스트 문자열을
들고 있었다(W5 조사 F-W5D-129). 그중 `search_surfaces.py` 는 검색 3중 구조(상단바 · `/search`
· Ctrl+K)를 재는 **유일한** 프로브다 — 돌려도 canonical 호스트를 한 번도 치지 않았다.
«검사를 돌렸다» 와 «검사가 이 제품을 봤다» 는 다른 사실이다.

## 규칙

`scripts/ui_qa/**` 안에서 기본 대상 호스트는 `capture.DEFAULT_BASE_URL` 한 곳이 정한다.
어느 파일도 제품 호스트를 직접 문자열로 들지 않는다 — 정본과 사본이 있으면 갈라지는 날이 온다.
CLI 의 `--base-url` 로 다른 곳을 치는 것은 여전히 자유다(그것이 이 값의 용도다).
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QA_DIR = REPO_ROOT / "scripts" / "ui_qa"

# 정본이 사는 파일. 여기만 문자열을 들 수 있다.
SOURCE_OF_TRUTH = "capture.py"

# 제품 호스트로 읽히는 문자열. 로그인 예시 계정의 **이메일 도메인**(`@goodmit.co.kr` 등)은
# 대상이 아니다 — 이 정규식은 스킴이 붙은 주소만 본다.
HOST_RE = re.compile(r"https?://[A-Za-z0-9.-]*\.gooddi\.lab")


def main() -> int:
    # 콘솔이 cp949 면 한글 문장부호에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if not QA_DIR.is_dir():
        print("[SKIP] scripts/ui_qa 가 없다")
        return 0

    offenders: list[str] = []
    checked = 0
    for path in sorted(QA_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.name == SOURCE_OF_TRUTH:
            continue
        text = io.open(path, encoding="utf-8").read()
        checked += 1
        for m in HOST_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append("%s:%d  %s" % (rel, line, m.group(0)))

    # 정본 자체가 canonical 을 가리키는지도 함께 본다 — 한 곳으로 모아 놓고 그 한 곳이
    # 틀리면 14개가 한꺼번에 틀린다.
    truth = io.open(QA_DIR / SOURCE_OF_TRUTH, encoding="utf-8").read()
    m = re.search(r'DEFAULT_BASE_URL\s*=\s*os\.environ\.get\(\s*"UI_QA_BASE_URL"\s*,\s*"([^"]+)"', truth)
    if not m:
        print("[FAIL] scripts/ui_qa/capture.py 에 DEFAULT_BASE_URL 기본값이 없다")
        return 1
    if "clovirassist" not in m.group(1):
        print("[FAIL] 기본 대상이 canonical 이 아니다: %s" % m.group(1))
        return 1

    if offenders:
        print("[FAIL] QA 프로브가 대상 호스트를 직접 들고 있다 — `capture.DEFAULT_BASE_URL` 을 써라")
        for o in offenders:
            print("   ", o)
        return 1

    print("QA_TARGET_HOST_OK (%s · 파일 %d개 확인)" % (m.group(1), checked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
