# -*- coding: utf-8 -*-
"""QA 하네스의 TLS 검증 정책 — **한 곳에서** 정한다.

## 왜 이 파일이 생겼는가 (S1 · 12_PROBE #8)

보조 프로브 19개가 각자 이 두 줄을 들고 있었다:

    ssl._create_default_https_context = ssl._create_unverified_context
    ensure_session(browser, BASE, OUT, insecure=True, log=print)

그중 13개는 `--insecure` 같은 스위치조차 없이 `True` 를 **박아** 뒀다. 즉 이 하네스는
호스트명이 인증서와 어긋나도 **구조적으로 알 수 없는** 상태였다 — 제품 이름이 바뀌고
canonical 호스트가 `clovirassist.gooddi.lab` 이 된 뒤에도 프로브들이 옛 호스트를 그대로
치고 있었는데(F-W5D-129), TLS 검증이 꺼져 있으니 아무도 빨간 줄을 못 봤다.

「지금 못 켠다」와 「안 켤 것이다」는 다르다. S1 이 스위치를 만들었고, **S3 이 인증서를
`CN/SAN=clovirassist.gooddi.lab` 으로 재발급한 뒤 `DEFAULT_VERIFY = True` 로 켰다.**

## S3 이 켜면서 알게 된 것 — 재발급만으로는 켜지지 않는다

이 설치처의 인증서는 **자체서명**이다(공개 CA 가 서명한 것이 아니다). 그래서 이름을 바로
맞춰도 「이 인증서를 믿을 근거」가 클라이언트에 없다. 검증을 켜는 일은 두 가지를 함께
갖추는 것이다.

1. **이름이 맞을 것** — S3 이 서버에서 고쳤다.
2. **신뢰 기준점을 손에 쥘 것** — 그 인증서 자체가 기준점이다. S3 Exit 조건이
   `curl --cacert …` 로 쓰여 있는 이유가 이것이다. 기준점을 안 주면 `ssl_verify_result` 는
   0 이 될 수 없다.

그래서 이 파일은 기준점을 받을 자리(`UI_QA_TLS_CA`)를 함께 갖는다. 설치 스크립트가
인증서 사본을 `/home/cloviradmin/<DNS_NAME>.crt` 에 두는 것이 바로 이 용도다.

**브라우저는 이 값을 못 받는다.** Playwright 의 `new_context()` 에는 신뢰 기준점을 넣는
인자가 없고(`ignore_https_errors` 와 `client_certificates` 뿐이다), Chromium 은 운영체제의
신뢰 저장소를 본다. 즉 파이썬 쪽 요청은 이 파일이 책임지지만, 브라우저 쪽 검증을 켜려면
그 인증서를 실행 머신의 신뢰 저장소에 넣어야 한다. `describe()` 가 실행마다 이 사실을
한 줄로 말한다 — 말하지 않으면 「검증 켬」이라고 적힌 초록이 무엇을 검증했는지 알 수 없다.

## 켜는 법 (지금의 기본값)

`DEFAULT_VERIFY = True` 하나가 19개를 함께 켠다. 자체서명 설치처를 겨눌 때는 기준점을
함께 준다.

    UI_QA_TLS_CA=/path/to/clovirassist.gooddi.lab.crt python -m scripts.ui_qa.search_surfaces

## 끄는 법

    UI_QA_TLS_VERIFY=0 python -m scripts.ui_qa.search_surfaces      # 환경변수로
    python -m scripts.ui_qa.keyboard --insecure                     # 플래그가 있는 모듈은 플래그로
"""

from __future__ import annotations

import os
import ssl

ENV_VAR = "UI_QA_TLS_VERIFY"

# 자체서명 설치처의 신뢰 기준점(PEM 경로). 비어 있으면 시스템 기본 저장소만 쓴다.
CA_ENV_VAR = "UI_QA_TLS_CA"

# S3 에서 켰다. 인증서 이름이 어긋나면 이제 실행이 빨갛게 죽는다 — 그것이 목적이다.
DEFAULT_VERIFY = True

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def ca_file() -> str:
    """자체서명 설치처의 신뢰 기준점 경로. 없거나 파일이 아니면 빈 문자열이다.

    없는 경로를 조용히 무시하지 않고 빈 문자열로 떨어뜨린 뒤 `describe()` 가 말한다 —
    오타 난 경로를 준 실행이 「시스템 저장소로 검증했다」로 끝나면, 무엇을 믿고 통과했는지
    아무도 모른다.
    """
    raw = os.environ.get(CA_ENV_VAR, "").strip()
    if not raw:
        return ""
    return raw if os.path.isfile(raw) else ""


def _env() -> bool | None:
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return None


def verify_enabled(*, cli_insecure: bool = False, cli_verify: bool = False) -> bool:
    """이 실행이 인증서를 검증하는가.

    우선순위는 **명시가 이긴다**: CLI → 환경변수 → 기본값. 둘 다 명시하면 «검증» 이 이긴다 —
    보안 스위치는 애매할 때 켜지는 쪽이 맞다.
    """
    if cli_verify:
        return True
    if cli_insecure:
        return False
    env = _env()
    if env is not None:
        return env
    return DEFAULT_VERIFY


def insecure(*, cli_insecure: bool = False, cli_verify: bool = False) -> bool:
    """`ensure_session(..., insecure=)` · `new_context(..., insecure=)` 에 그대로 넘기는 값."""
    return not verify_enabled(cli_insecure=cli_insecure, cli_verify=cli_verify)


def apply_default_https_context(*, cli_insecure: bool = False,
                                cli_verify: bool = False) -> bool:
    """`urllib`/`http.client` 의 **프로세스 전역** 기본 컨텍스트를 정책에 맞춘다.

    검증을 켤 때 기준점(`UI_QA_TLS_CA`)이 주어져 있으면 그 인증서를 신뢰 목록에 얹은
    컨텍스트를 기본값으로 심는다. 자체서명 설치처에서 검증이 성립하는 유일한 방법이다.
    기준점이 없으면 전역을 **건드리지 않는다** — 파이썬 기본값이 이미 검증이다.
    끌 때만 예전과 같은 우회를 적용한다. 되돌리는 값을 반환하지 않는 이유는, 이 함수를 쓰는
    쪽이 전부 한 번 실행하고 끝나는 프로브이기 때문이다.

    반환값은 `insecure` — 호출부가 그대로 세션/컨텍스트에 넘길 수 있게 한다.
    """
    ins = insecure(cli_insecure=cli_insecure, cli_verify=cli_verify)
    if ins:
        ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001
        return ins
    ca = ca_file()
    if ca:
        def _verified_context(*_args, **_kwargs):
            return ssl.create_default_context(cafile=ca)
        ssl._create_default_https_context = _verified_context  # noqa: SLF001
    return ins


def add_arguments(parser) -> None:
    """`--insecure` / `--verify-tls` 를 붙인다. 두 이름을 한 곳에서 정한다."""
    parser.add_argument("--insecure", action="store_true",
                        help="인증서를 검증하지 않는다(자체서명 설치처)")
    parser.add_argument("--verify-tls", action="store_true",
                        help="인증서를 검증한다. 기본값은 %s" % ("검증" if DEFAULT_VERIFY else "미검증"))


def from_args(args) -> bool:
    """argparse 결과에서 `insecure` 를 뽑는다(플래그가 없으면 정책 기본값)."""
    return insecure(cli_insecure=bool(getattr(args, "insecure", False)),
                    cli_verify=bool(getattr(args, "verify_tls", False)))


def describe(*, cli_insecure: bool = False, cli_verify: bool = False) -> str:
    """실행 로그 한 줄. **무엇을 껐는지 말하지 않는 하네스는 껐다는 사실을 숨긴다.**

    켠 실행도 무엇을 믿고 켰는지 말해야 한다. 자체서명 설치처에서 기준점 없이 켜면
    파이썬 쪽 요청이 전부 실패하는데, 그때 화면에 「TLS 검증 켜짐」만 남으면 원인이
    인증서인지 서버인지 구별되지 않는다.
    """
    if not verify_enabled(cli_insecure=cli_insecure, cli_verify=cli_verify):
        return ("TLS 검증 꺼짐 — 호스트명이 인증서와 어긋나도 이 실행은 알 수 없다. "
                "켜려면 %s=1" % ENV_VAR)
    ca = ca_file()
    anchor = ("신뢰 기준점 %s" % ca) if ca else (
        "신뢰 기준점은 시스템 저장소뿐이다. 자체서명 설치처라면 %s 로 인증서를 준다" % CA_ENV_VAR)
    return ("TLS 검증 켜짐 (호스트명·체인 불일치가 실패로 나온다). %s. "
            "브라우저 쪽은 이 값을 못 받는다 — Chromium 은 운영체제 신뢰 저장소를 본다"
            % anchor)
