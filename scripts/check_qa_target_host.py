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

## S1 에서 막은 것 둘

1. **디렉터리가 없으면 `[SKIP]` 하고 종료 코드 0 을 줬다.** fail-open 이다 — 하네스를 옮기거나
   지우면 이 검사는 «통과» 를 찍는다. 검사 대상이 없는 것과 위반이 없는 것은 다른 사실이고,
   종료 코드가 같으면 그 둘을 구별할 수 없다. 이제 **fail-closed** 다.
2. **IP 로 박은 대상은 정규식이 못 봤다.** `HOST_RE` 가 `*.gooddi.lab` 만 봤으므로
   `https://10.100.64.71` 처럼 IP·포트로 박아 두면 그대로 통과했다. 되돌이 주소
   (`127.0.0.1`·`localhost`·`::1`)는 **대상이 아니다** — 로컬 서버를 치는 것이 이 하네스의
   정상 용법이고, 그것까지 잡으면 검사가 소음이 되어 꺼진다.

## 그리고 TLS 정책도 여기서 본다 (12_PROBE #8)

호스트명이 인증서와 어긋나도 **검증이 꺼져 있으면 아무도 못 본다.** 「어느 제품을 치는가」와
「그게 정말 그 제품인지 확인하는가」는 같은 축의 앞뒤다 — 19개 프로브가 옛 호스트를 치면서도
조용했던 이유가 정확히 그것이다.

그래서 `scripts/ui_qa/**` 어느 파일도 TLS 우회를 **직접 들지 않는다**. 정책은
`scripts/ui_qa/tls.py` 하나가 정하고, S3 이 인증서를 재발급한 뒤 거기 `DEFAULT_VERIFY` 를
켠다. 파라미터로 받아 넘기는 것(`insecure=insecure`)은 대상이 아니다 — 그건 정책을 **쓰는**
쪽이고, 금지되는 것은 정책을 **박는** 쪽이다.
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

# IP·포트로 박은 대상. 되돌이 주소는 뺀다 — 로컬 서버를 치는 것은 이 하네스의 정상 용법이다.
IP_RE = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?")
LOOPBACK = ("127.", "0.0.0.0")

# TLS 우회를 **박아 둔** 자리. 정책 파일(`tls.py`)만 이 두 형태를 가질 수 있다.
TLS_RES = (
    re.compile(r"\binsecure\s*=\s*True\b"),
    re.compile(r"_create_default_https_context\s*=\s*ssl\._create_unverified_context"),
)
TLS_POLICY_FILE = "tls.py"


def scan(text: str, rel: str) -> list[str]:
    """이 파일이 **대상 호스트나 TLS 정책을 직접 들고 있는** 자리."""
    out: list[str] = []
    for m in HOST_RE.finditer(text):
        out.append("%s:%d  %s" % (rel, text.count("\n", 0, m.start()) + 1, m.group(0)))
    for m in IP_RE.finditer(text):
        if m.group(1).startswith(LOOPBACK):
            continue
        out.append("%s:%d  %s" % (rel, text.count("\n", 0, m.start()) + 1, m.group(0)))
    if not rel.endswith(TLS_POLICY_FILE):
        for rx in TLS_RES:
            for m in rx.finditer(text):
                out.append("%s:%d  %s — TLS 정본은 scripts/ui_qa/tls.py 하나다"
                           % (rel, text.count("\n", 0, m.start()) + 1, m.group(0)))
    return out


SELF_TEST_CASES = [
    # (소스, 걸려야 하는가, 무엇을 지키는 사례인가)
    ('BASE = "https://clovirone-ai.gooddi.lab"', True, "옛 제품 호스트를 직접 든 자리"),
    ('BASE = "https://clovirassist.gooddi.lab"', True,
     "canonical 이라도 사본은 사본이다 — 정본은 capture.DEFAULT_BASE_URL 하나뿐이다"),
    ('BASE = "https://10.100.64.71"', True, "IP 로 박은 대상 — 예전 정규식이 못 봤다"),
    ('BASE = "https://10.100.64.71:8443/#/"', True, "포트가 붙어도 같다"),
    ('BASE = os.environ.get("X", "http://127.0.0.1:8080")', False,
     "되돌이 주소는 정상 용법 — 위양성이면 검사가 소음이 되어 꺼진다"),
    ('host in {"localhost", "127.0.0.1", "::1", ""}', False, "되돌이 판정 코드 자체"),
    ('EMAIL = "admin@goodmit.co.kr"', False, "스킴이 없는 이메일 도메인은 대상이 아니다"),
    ('s = ensure_session(b, BASE, OUT, insecure=True, log=print)', True,
     "TLS 우회를 박은 자리 — 19개 프로브가 이 모양이었고 호스트 불일치가 구조적으로 안 보였다"),
    ('ssl._create_default_https_context = ssl._create_unverified_context', True,
     "전역 컨텍스트 우회도 정책 파일 밖에서는 금지다"),
    ('s = ensure_session(b, BASE, OUT, insecure=insecure, log=print)', False,
     "정책을 **쓰는** 것은 정상이다 — 금지되는 것은 정책을 **박는** 것이다"),
    ('ctx = ssl._create_unverified_context() if insecure else None', False,
     "파라미터로 갈리는 자리(capture/run)는 이미 스위치가 있다"),
]


def self_test() -> int:
    bad = []
    for src, should_flag, why in SELF_TEST_CASES:
        hits = scan(src, "<self-test>")
        if bool(hits) != should_flag:
            bad.append("%s: 기대 %s / 실제 %s"
                       % (why, "검출" if should_flag else "통과", "검출" if hits else "통과"))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print("  -", line)
        return 1
    print("[OK ] QA_TARGET_HOST_SELF_TEST_OK (사례 %d개, 검출·위양성 양방향)"
          % len(SELF_TEST_CASES))
    return 0


def main() -> int:
    # 콘솔이 cp949 면 한글 문장부호에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1
    if not QA_DIR.is_dir():
        # fail-closed. 「검사 대상이 없다」를 「위반이 없다」로 바꾸지 않는다.
        print("[FAIL] scripts/ui_qa 가 없다 — 이 검사는 대상 없이 통과할 수 없다")
        return 1

    offenders: list[str] = []
    checked = 0
    for path in sorted(QA_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.name == SOURCE_OF_TRUTH:
            continue
        text = io.open(path, encoding="utf-8").read()
        checked += 1
        offenders += scan(text, rel)

    if checked == 0:
        print("[FAIL] scripts/ui_qa 에서 검사할 파일을 하나도 못 찾았다 — 표본 0 은 통과가 아니다")
        return 1

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
