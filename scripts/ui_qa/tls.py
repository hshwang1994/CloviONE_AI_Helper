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

「지금 못 켠다」와 「안 켤 것이다」는 다르다. 지금 켜면 옛 CN/SAN 자체서명 인증서 때문에
전부 빨갛다 — 그건 인증서 문제이지 하네스 문제가 아니다. 그래서 **S1 은 스위치를 만들고,
S3 이 인증서를 재발급한 뒤 그 스위치를 켠다**(S3 Exit 조건: `openssl s_client` CN/SAN 일치 ·
`ssl_verify_result=0`).

## 켜는 법

    UI_QA_TLS_VERIFY=1 python -m scripts.ui_qa.search_surfaces      # 환경변수로
    python -m scripts.ui_qa.keyboard --verify-tls                   # 플래그가 있는 모듈은 플래그로

## 끄는 법 (지금의 기본값)

`DEFAULT_VERIFY = False`. S3 이 이 한 줄을 `True` 로 바꾸면 19개가 한꺼번에 켜진다 —
그것이 이 파일의 존재 이유다. 파일 19개를 다시 편집할 일은 없다.
"""

from __future__ import annotations

import os
import ssl

ENV_VAR = "UI_QA_TLS_VERIFY"

# 🔴 **S3 이 여기를 `True` 로 바꾼다.** 그 전에는 옛 호스트명 인증서 때문에 전부 빨갛다.
DEFAULT_VERIFY = False

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


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

    검증을 켤 때는 전역을 **건드리지 않는다** — 파이썬 기본값이 이미 검증이다.
    끌 때만 예전과 같은 우회를 적용한다. 되돌리는 값을 반환하지 않는 이유는, 이 함수를 쓰는
    쪽이 전부 한 번 실행하고 끝나는 프로브이기 때문이다.

    반환값은 `insecure` — 호출부가 그대로 세션/컨텍스트에 넘길 수 있게 한다.
    """
    ins = insecure(cli_insecure=cli_insecure, cli_verify=cli_verify)
    if ins:
        ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001
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
    """실행 로그 한 줄. **무엇을 껐는지 말하지 않는 하네스는 껐다는 사실을 숨긴다.**"""
    if verify_enabled(cli_insecure=cli_insecure, cli_verify=cli_verify):
        return "TLS 검증 켜짐 (호스트명·체인 불일치가 실패로 나온다)"
    return ("TLS 검증 꺼짐 — 호스트명이 인증서와 어긋나도 이 실행은 알 수 없다. "
            "켜려면 %s=1 (S3 에서 기본값이 켜진다)" % ENV_VAR)
