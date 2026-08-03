"""@멘션 파싱 — 메시지 본문에서 '누구를 불렀는지' 찾아낸다 (순수 함수, DB·외부 호출 없음).

왜 별도 모듈인가: 이 규칙은 DB 없이 검증할 수 있는데 service.py 안에 있으면 방·사용자·세션을
전부 세워야 한 줄을 시험할 수 있다. 그리고 **같은 규칙을 프런트도 알아야 한다**
(frontend/src/screens/chat-text.js 가 말풍선에서 같은 자리에 밑줄을 긋는다) — 규칙이 한쪽에만
글로 적혀 있으면 반드시 갈라진다. 두 구현이 같은 표(아래 규칙 1~4)를 보게 한다.

규칙:
  1. **경계**: `@` 앞이 영숫자·밑줄이면 멘션이 아니다. 이메일(`foo@goodmit.co.kr`)이 통째로
     '@goodmit…' 멘션으로 읽히는 것을 막는 유일한 장치다. 한글 앞의 `@`는 멘션으로 본다
     (한국어는 단어 사이에 공백이 없는 경우가 흔하고, 이메일 로컬파트는 한글이 아니다).
  2. **최장 일치**: 후보 이름을 길이 내림차순으로 시도한다. '김철'과 '김철수'가 함께 있을 때
     `@김철수`가 '김철'로 잘리면 엉뚱한 사람에게 알림이 간다.
  3. **정확 일치만**: 표시 이름과 글자 그대로 같아야 한다. 부분·유사 일치를 허용하면 '없는
     사람을 부른' 메시지가 조용히 아무에게도 안 가거나 엉뚱한 사람에게 간다.
  4. **등장 순서, 중복 제거**: 한 메시지에서 같은 사람을 여러 번 불러도 알림은 한 번이다.

이 함수는 '알림을 보낼지'를 정하지 않는다 — 보낸 사람 제외 같은 정책은 호출자(service)에 있다.
"""

from __future__ import annotations

import re

# 멘션으로 쓸 수 있는 표시 이름의 최대 길이. 이보다 긴 이름은 후보에서 뺀다(본문 전체를 훑는
# 최장 일치 비교가 무한정 길어지지 않게 하는 상한일 뿐, 그런 이름은 실제로 없다).
MAX_MENTION_NAME = 40

# '@' 바로 앞에 오면 멘션이 아닌 문자(영숫자·밑줄) — 이메일과 코드 조각을 걸러낸다.
_WORD_BEFORE = re.compile(r"[0-9A-Za-z_]")

# 한 메시지에서 검사하는 '@' 자리의 상한. 본문 2000자를 전부 '@'로 채우면 후보 수(전체 채팅은
# 전사 사용자 수)만큼의 비교가 그만큼 반복된다 — 한 번의 전송으로 만들 수 있는 일의 양에
# 천장을 둔다. 사람이 64명을 한 메시지에서 부르는 일은 없고, 있더라도 그건 멘션이 아니라 공지다.
MAX_AT_SIGNS = 64


def find_mentioned(body: str | None, names: dict[str, str]) -> list[str]:
    """`body` 안에서 불린 사람들의 user_id (등장 순, 중복 제거).

    `names` 는 표시 이름 → user_id 다. 같은 표시 이름이 두 사람이면 호출자가 이미 한 명으로
    좁혀 놓은 상태다(동명이인은 이름으로 부를 수 없다 — 그건 이 함수가 아니라 이름 체계의
    문제이고, 여기서 임의로 한 명을 고르면 '누가 받았는지 모르는 알림'이 된다).
    """
    text = body or ""
    if "@" not in text or not names:
        return []
    ordered = sorted(
        (n for n in names if n and len(n) <= MAX_MENTION_NAME), key=len, reverse=True
    )
    if not ordered:
        return []

    found: list[str] = []
    seen: set[str] = set()
    i = 0
    for _ in range(MAX_AT_SIGNS):
        i = text.find("@", i)
        if i < 0:
            break
        if i > 0 and _WORD_BEFORE.match(text[i - 1]):
            i += 1
            continue
        for name in ordered:
            if text.startswith(name, i + 1):
                uid = names[name]
                if uid not in seen:
                    seen.add(uid)
                    found.append(uid)
                i += 1 + len(name)
                break
        else:
            i += 1
    return found


def mention_preview(body: str | None, *, limit: int = 120) -> str:
    """알림 본문에 실을 한 줄 미리보기 — 줄바꿈을 없애고 길면 자른다.

    알림 목록은 한 줄짜리 행이라 줄바꿈이 그대로 들어가면 뒤 내용이 잘려 보인다.
    """
    text = " ".join((body or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
