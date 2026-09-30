"""개인정보 가리기와 응답 제한의 글자 처리 (계획 3.9, D-519).

## 무엇을 가리는가

  이메일            `[이메일]`
  휴대전화 · 유선    `[전화번호]` (010 · 011 · 016~019, 02 와 지역 번호, 070 · 050X, 15XX · 16XX · 18XX 대표 번호)
  주민등록번호       `[주민등록번호]` (생년월일 여섯 자리 + 성별 한 자리로 시작하는 일곱 자리, 외국인등록번호 포함)

고정 토큰으로 바꾼다 - 모델은 무엇이 가려졌는지 알지만 값은 모른다. 주민등록번호를 전화번호보다 먼저 가린다: 열세 자리
숫자 안에 전화번호 모양이 들어 있을 수 있다.

## 제품 밖 링크

`http(s)://` 로 시작하는 주소 가운데 제품 호스트가 아닌 것은 앞의 `https://` 를 떼어 누를 수 없는 글자로 바꾼다. 무엇을
가리켰는지는 남는다 - 지우면 답에서 사실이 빠진다.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

EMAIL_TOKEN = "[이메일]"
PHONE_TOKEN = "[전화번호]"
RRN_TOKEN = "[주민등록번호]"

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RRN = re.compile(r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\s?-?\s?[1-8]\d{6}(?!\d)")
_PHONE = re.compile(
    r"(?<!\d)(?:"
    r"01[016789][\s.\-]?\d{3,4}[\s.\-]?\d{4}"          # 휴대전화
    r"|0(?:2|[3-6][1-5])[\s.\-]?\d{3,4}[\s.\-]?\d{4}"   # 서울과 지역 번호
    r"|0(?:70|50[2-8])[\s.\-]?\d{3,4}[\s.\-]?\d{4}"     # 인터넷 전화, 안심 번호
    r"|1[568]\d{2}[\s.\-]?\d{4}"                       # 대표 번호
    r")(?!\d)"
)
_URL = re.compile(r"https?://[^\s<>\"'`)\]]+", re.IGNORECASE)


def mask(text: str, *, emails: bool, phones: bool, rrns: bool) -> tuple[str, int]:
    """(가린 글, 가린 개수)."""
    if not isinstance(text, str) or not text:
        return text, 0
    count = 0

    def _sub(pattern, token, value):
        nonlocal count
        value, n = pattern.subn(token, value)
        count += n
        return value

    if rrns:
        text = _sub(_RRN, RRN_TOKEN, text)
    if emails:
        text = _sub(_EMAIL, EMAIL_TOKEN, text)
    if phones:
        text = _sub(_PHONE, PHONE_TOKEN, text)
    return text, count


def neutralize_links(text: str, *, allowed_hosts: set[str]) -> tuple[str, int]:
    """제품 밖 링크의 앞머리(`https://`)를 떼어 누를 수 없게 한다. (바꾼 글, 바꾼 개수)."""
    if not isinstance(text, str) or not text:
        return text, 0
    count = 0

    def _one(match: re.Match) -> str:
        nonlocal count
        url = match.group(0)
        host = (urlsplit(url).hostname or "").lower()
        if host and host in allowed_hosts:
            return url
        count += 1
        return url.split("://", 1)[1]

    return _URL.sub(_one, text), count
