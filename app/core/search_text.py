"""검색 대조 규칙 하나 — 질의와 대상 **양쪽**을 같은 규칙으로 접는다 (D-495).

## 무엇이 문제였나

「현황 제외」라는 제목을 「현황제외」로 치면 아무것도 안 나왔다. 문자열 검색이 자리마다 따로
구현돼 있었고(백엔드 열두 곳), 질의는 앞뒤 공백을 걷었지만 **대상 쪽 공백을 걷는 곳이 없었다.**
여덟 곳은 `%`·`_` 도 막지 않아서, 게시판·문서·사용자 검색창에 `%` 한 글자를 치면 전 행이
나왔다. 한쪽만 고치면 고친 것이 아니라 어긋나는 방향만 바뀐다 — 그래서 규칙을 여기 한 곳에
두고 질의와 대상이 **같은 함수**를 지나게 한다.

## 두 형태 — 표시형과 대조형

  * **표시형**(`normalize_query`) — NFC · 앞뒤 공백 제거 · 연속 공백 한 칸 · 100자 상한.
    화면과 주소에 다시 싣는 값이다. 사람이 친 글을 알아볼 수 있게 남겨야 하므로 대소문자와
    낱말 사이 공백을 지우지 않는다.
  * **대조형**(`fold`) — NFKC → `İ`→`i` → `lower` → `ς`→`σ` → 공백·제로폭·소프트 하이픈 삭제.
    대조에만 쓰고 화면에 내보내지 않는다. 「ClovirONE」·「clovirone」·「ＣＬＯＶＩＲＯＮＥ」이
    같은 값이 되고, 「현황 제외」와 「현황제외」가 같은 값이 된다.

`casefold` 가 아니라 `lower` 인 이유: PostgreSQL 에는 casefold 가 없고, `ß`→`ss` 처럼 글자
수가 바뀌는 접기는 한쪽 구현에만 있으면 양쪽이 갈라진다. `İ` 와 `ς` 를 따로 바꾸는 이유는
파이썬 `lower` 가 그 둘에서만 PG 의 `lower` 와 다른 답을 내기 때문이다.

## 의미를 바꾸는 퍼지는 넣지 않는다

오타 허용·형태소·자모 분해 같은 접기는 **다른 낱말을 같은 낱말로 만든다.** 여기서 지우는
것은 화면에서 눈에 안 보이거나(공백·제로폭) 같은 글자의 다른 표기(전각·호환 문자·대소문자)
뿐이다. 찾는 말의 뜻은 그대로다.

## SQL 쪽 짝

`search_fold(text)`(alembic `0030_search_fold`)가 이 파일의 `fold` 와 같은 값을 낸다. 공용
말뭉치 `tests/fixtures/search_fold_corpus.json` 이 세 구현(파이썬 · SQL · 프런트)을 한 표로
잰다. 규칙을 바꾸는 날에는 `FOLD_VERSION` 을 올리고 SQL 함수와 생성 열을 새 마이그레이션으로
다시 만든다 — 한쪽만 바꾸면 이미 접혀 저장된 값과 새 질의가 조용히 어긋난다.

## 이 모듈이 `app/core` 에 있는 이유

채팅·게시판·티켓 같은 뜨거운 경로도 이 규칙을 쓴다. 그 경로들은 `app.search` 를 import 하지
않는다(`tests/unit/test_search_no_hot_path.py`) — 검색 색인 쪽이 딸려 들어오면 안 되기 때문이다.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from sqlalchemy import Text, func, or_

#: 접기 규칙의 판. SQL 함수 주석(`COMMENT ON FUNCTION`)에도 같은 판이 적혀 있다.
FOLD_VERSION = 1

#: 대상 쪽 접기를 맡는 SQL 함수 이름(alembic `0030_search_fold`).
SQL_FUNCTION = "search_fold"

#: 사람이 검색창에 칠 만한 길이의 상한. 긴 문자열은 결과를 좁히지 못하고 비용만 키운다.
MAX_QUERY_CHARS = 100

#: 트라이그램 인덱스가 받을 수 있는 최소 길이(대조형 기준). 더 짧으면 전량 스캔이 된다.
MIN_TRGM_CHARS = 3

#: 대조형에서 지우는 코드포인트 — 공백류 · 제로폭 · 소프트 하이픈 · BOM · NUL.
#:
#: 목록을 손으로 적는다. PG 정규식의 `\s` 는 로케일에 따라 답이 달라서, 같은 규칙을 두
#: 언어로 옮길 때 기댈 수 없다. U+3000 이나 U+2002 같은 공백은 여기 없어도 되는데, NFKC 가
#: 먼저 보통 공백(U+0020)으로 바꿔 놓기 때문이다. NUL 은 PG 의 text 가 담지 못하는
#: 글자라 파이썬 쪽에만 뜻이 있다.
STRIP_CODEPOINTS: frozenset[int] = frozenset((
    0x0000,
    *range(0x0009, 0x000D + 1),
    *range(0x001C, 0x0020 + 1),
    0x0085, 0x00A0, 0x00AD, 0x1680, 0x2028, 0x2029,
    *range(0x200B, 0x200F + 1),
    0x2060, 0xFEFF,
))

#: LIKE 패턴의 escape 문자. SQL 쪽 `ESCAPE '\'` 와 짝이다.
LIKE_ESCAPE = "\\"

_STRIP_TABLE = {codepoint: None for codepoint in STRIP_CODEPOINTS}


def normalize_query(raw: str | None) -> str:
    """표시형 — NFC · 앞뒤 공백 제거 · 연속 공백 한 칸 · 상한. 화면과 주소가 이 값을 쓴다.

    글자 수를 세기 **전에** NFC 로 맞춘다. macOS 에서 온 NFD 두 글자는 코드포인트로 여섯이라,
    정규화 전에 세면 상한과 길이 판정이 표기에 따라 달라진다.
    """
    text = unicodedata.normalize("NFC", str(raw or ""))
    return " ".join(text.split())[:MAX_QUERY_CHARS]


def fold(text: str | None) -> str:
    """대조형 — 질의와 대상이 **같은 이 함수**를 지난다. SQL 의 `search_fold()` 와 같은 값이다.

    순서가 규칙의 일부다. NFKC 가 먼저여야 전각 공백·호환 문자가 보통 글자가 된 뒤에 지워지고,
    `İ` 를 `lower` 보다 먼저 바꿔야 파이썬이 `i` 뒤에 결합 점(U+0307)을 붙이지 않는다.
    """
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace("\u0130", "i").lower().replace("\u03c2", "\u03c3")
    return value.translate(_STRIP_TABLE)


def escape_like(text: str) -> str:
    """LIKE 메타문자를 글자로 만든다. 백엔드에서 escape 를 하는 곳은 **여기 하나**다.

    `\\` 를 먼저 바꾼다. 나중에 바꾸면 `%` 앞에 붙여 둔 escape 까지 두 번 바뀌어, `%` 하나가
    든 질의가 조용히 전 행에 걸린다.
    """
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def like_pattern(folded: str) -> str:
    """접힌 바늘 하나를 부분일치 패턴(`%…%`)으로 감싼다. escape 는 여기서 한다."""
    return f"%{escape_like(folded)}%"


def pattern_for(raw: str | None) -> str | None:
    """사람이 친 검색어 → 대조 패턴. **접은 뒤 비면 `None`** 이다.

    `None` 은 「거를 것이 없다」는 뜻이다. 빈 바늘로 패턴을 만들면 `LIKE '%%'` 가 되어 전 행에
    걸리는데, 그것은 조건을 버린 것과 같은 결과를 조건을 건 것처럼 보이게 만든다. 제로폭 공백
    하나만 붙여 넣은 검색창이 그 길로 간다.
    """
    needle = fold(normalize_query(raw))
    return like_pattern(needle) if needle else None


def like_folded(column, pattern: str, *, stored: bool = False):
    """컬럼 하나에 대조 패턴을 건다. 대상도 **같은 규칙으로 접힌 값**과 비교한다.

    `stored=True` 는 이미 접혀 저장된 생성 열(`search_documents.title_fold` 같은)을 뜻한다.
    그때는 다시 접지 않는다 — 생성 열 위의 GIN 트라이그램 인덱스가 이 모양을 받는다. 작은 표는
    질의 때 `search_fold(col)` 을 계산한다.

    `ILIKE` 가 아니라 `LIKE` 인 이유: 양쪽이 이미 소문자라 대소문자를 한 번 더 무시할 일이 없다.
    """
    target = column if stored else getattr(func, SQL_FUNCTION)(column, type_=Text)
    return target.like(pattern, escape=LIKE_ESCAPE)


def contains_folded(columns: Iterable, raw: str | None, *, stored: bool = False):
    """여러 컬럼 중 하나라도 검색어를 담고 있는가. **바늘이 없으면 `None`** 이다.

    부르는 쪽은 `if clause is not None:` 으로 건다. 빈 조건(`or_()`)을 돌려주지 않는 이유는
    그것이 SQLAlchemy 판마다 참·거짓으로 다르게 읽혀 왔기 때문이다 — 「거를 것이 없다」는
    조건을 아예 안 거는 것으로 말한다.
    """
    targets = tuple(columns)
    if not targets:
        raise ValueError("검색할 컬럼이 하나도 없습니다.")
    pattern = pattern_for(raw)
    if pattern is None:
        return None
    return or_(*(like_folded(column, pattern, stored=stored) for column in targets))


def matches_folded(haystack: str | None, raw: str | None) -> bool:
    """파이썬 쪽 짝 — `contains_folded` 가 SQL 로 내는 답을 값 하나에 대고 낸다.

    바늘이 없으면 참이다. `contains_folded` 가 `None`(거르지 않는다)을 돌려주는 것과 같은 뜻이라,
    두 경로가 같은 검색어에 같은 행을 남긴다.
    """
    needle = fold(normalize_query(raw))
    if not needle:
        return True
    return needle in fold(haystack)


# ── 사람이 쓴 질문 → 찾을 낱말 (D-536) ─────────────────────────────────────────
#
# 검색창은 기억나는 구절을 받는다 — 「스프린트 회의록」. AI 에게는 사람이 **문장**을 쓴다 — 「연차 신청은 어떻게 하나요?」,
# 「인프라 정비 관련 문서 찾아줘」. 검색창 규칙(접은 질의 한 덩이 · 낱말이 모두 3자 이상이면 낱말별 AND)으로는 그 문장이 0건이다:
# 2자 낱말(「연차」)이 AND 조합을 끄고, 조사 · 어미(「신청은」 · 「하나요」)와 부탁 말(「찾아줘」)이 통짜 가지와 FTS 의 AND 를
# 깬다. 그래서 AI 검색과 도우미의 검색 도구만 질문에서 낱말을 뽑아 **OR 로** 찾고 맞은 낱말 수로 순위를 매긴다. 통합 검색 화면은
# 그대로다 — 그쪽 AND 는 기억나는 구절에 맞고, 바꾸는 것은 따로 정할 일이다.
#
# 형태소 분석기를 쓰지 않는다(폐쇄망 설치 · 사전 판 관리). 아래 표는 **뜻을 바꾸지 않는 쪽으로만** 걷는다: 조사는 걷고 남는 어간이
# 2자 이상일 때만 걷는다 — 「회의」의 「의」, 「휴가」의 「가」를 조사로 읽어 한 글자만 남기지 않는다. 낱말은 `[0-9a-z가-힣]` 만
# 남는다 — FTS 질의 문법(`& | ! : * ( )`)과 LIKE 메타문자(`% _ \`)가 낱말에 들어갈 길이 없다.

#: 모델에 그대로 가는 질문의 상한. 표시형(`MAX_QUERY_CHARS`)과 따로다 — 질문을 100자로 자르면 뒤의 조건이 모델에 안 간다.
MAX_QUESTION_CHARS = 5000

#: 질문 하나에서 뽑는 낱말 수의 상한. 낱말마다 LIKE 가지가 하나씩 붙는다(2자 낱말은 인덱스를 못 탄다). 라틴 · 한글 혼합
#: 토큰을 나눈 조각도 이 수에 든다(D-568) — 예전 여섯으로는 「SK하이닉스 프로젝트 진행 작업」이 조각 둘에 뒤 낱말을 잃었다.
MAX_KEYWORDS = 8

#: 낱말 끝에서 걷는 조사와 꾸미는 어미(「결재할」 · 「변경된」 · 「마감인」) — 긴 것부터 맞춘다.
KEYWORD_PARTICLES: tuple[str, ...] = (
    "에서는", "에게서", "으로는", "에서", "으로", "에게", "한테", "까지", "부터", "처럼", "보다", "에는", "하는", "되는",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "와", "과", "로", "할", "한", "된", "인",
)

#: 문장 끝의 부탁 · 물음. 낱말 전체가 이것이면 걷고, 낱말 끝이 이것이면 떼어 낸다(남는 어간이 2자 이상일 때).
KEYWORD_TAILS: tuple[str, ...] = (
    "해주세요", "알려주세요", "찾아주세요", "보여주세요", "해줘", "알려줘", "찾아줘", "보여줘", "주세요",
    "하나요", "인가요", "할까요", "있나요", "되나요", "뭐예요", "뭐야",
)

#: 찾는 대상이 아니라 문장을 잇는 말 — 낱말째 걷는다(조사를 걷기 전과 뒤 둘 다 본다).
KEYWORD_STOPWORDS: frozenset[str] = frozenset((
    "관련", "관한", "대한", "대해", "대해서", "문서", "자료", "내용", "정보", "좀", "혹시", "사내", "방법",
    "어떻게", "무엇", "뭐", "뭔가", "언제", "어디", "어디서", "누가", "누구", "왜", "어느", "무슨",
    "알려", "찾아", "보여", "주세요", "있는", "있어", "있나", "하는", "됐어", "없어", "해서",
    "내", "내가", "제가", "나는", "저는", "우리", "이번", "지금", "그", "것", "거", "수", "때", "중",
    "그리고", "그런데", "하지만", "또는", "및", "또",
))

_KEYWORD_TOKEN = re.compile(r"[0-9a-z가-힣]+")
#: 혼합 토큰의 글자 갈래 — 한글 덩이와 라틴 · 숫자 덩이(D-568).
_SCRIPT_RUN = re.compile(r"[가-힣]+|[0-9a-z]+")


def normalize_question(raw: str | None) -> str:
    """모델에 가는 질문 — NFC · 앞뒤 공백 제거 · 연속 공백 한 칸 · `MAX_QUESTION_CHARS` 상한. 표시형과 달리 100자로 자르지 않는다."""
    text = unicodedata.normalize("NFC", str(raw or ""))
    return " ".join(text.split())[:MAX_QUESTION_CHARS]


def _strip_tail(word: str, tails: tuple[str, ...]) -> str | None:
    """`word` 끝의 꼬리 하나를 걷는다. 낱말 전체가 꼬리면 None(버린다), 걷고 남는 것이 2자 미만이면 그대로 둔다."""
    for tail in tails:
        if word == tail:
            return None
        if word.endswith(tail) and len(word) - len(tail) >= 2:
            return word[: -len(tail)]
    return word


def _clean_word(token: str) -> str | None:
    """토큰 하나 → 낱말(꼬리 · 조사를 걷은 것). 버릴 토큰이면 None."""
    if token in KEYWORD_STOPWORDS:
        return None
    word = _strip_tail(token, KEYWORD_TAILS)
    if word is None or word in KEYWORD_STOPWORDS:
        return None
    stripped = _strip_tail(word, KEYWORD_PARTICLES)
    if stripped is not None:
        word = stripped
    if word in KEYWORD_STOPWORDS or len(word) < 2:
        return None
    return word


def _script_parts(word: str) -> tuple[str, ...]:
    """라틴 · 숫자와 한글이 붙은 낱말의 조각 — 한글 덩이 먼저, 그다음 라틴 · 숫자 덩이(D-568).

    「sk하이닉스」 → 「하이닉스」, 「sk」. 문서가 「SK 하이닉스」로 띄어 쓰면 전문검색 레인은 그 둘을 다른 어절로 보고, 문서가
    「하이닉스」만 쓰면 통째 낱말이 안 걸린다 — 그래서 통째 낱말 뒤에 조각을 함께 건다. 한 글자 조각은 버린다(전 행에 걸린다).
    """
    runs = _SCRIPT_RUN.findall(word)
    if len(runs) < 2:
        return ()
    hangul = [r for r in runs if "가" <= r[0] <= "힣"]
    latin = [r for r in runs if not ("가" <= r[0] <= "힣")]
    return tuple(r for r in (*hangul, *latin) if len(r) >= 2)


def keywords(raw: str | None, *, limit: int = MAX_KEYWORDS, split_mixed: bool = True) -> tuple[str, ...]:
    """사람이 쓴 질문 → 찾을 낱말(순서대로, 중복 없이, 2자 이상, 최대 `limit` 개).

    「인프라 정비 관련 문서 찾아줘」 → `("인프라", "정비")`, 「연차 신청은 어떻게 하나요?」 → `("연차", "신청")`.
    낱말은 NFKC · 소문자 · `[0-9a-z가-힣]` 뿐이다(FTS 질의 문법과 LIKE 메타문자가 들어갈 수 없다).

    ``split_mixed`` 이면 라틴 · 한글이 붙은 낱말 뒤에 그 조각을 함께 낸다 — 「SK하이닉스 프로젝트」 →
    `("sk하이닉스", "하이닉스", "sk", "프로젝트")`(D-568). 조각도 불용어 · 길이 규칙을 똑같이 지난다. 이 함수를 쓰는 곳은 AI 검색과
    도우미의 검색 도구뿐이다 — 통합 검색 화면(`match="all"`)은 낱말을 뽑지 않는다(P-123).
    """
    text = unicodedata.normalize("NFKC", str(raw or "")).replace("İ", "i").lower()
    out: list[str] = []

    def add(word: str | None) -> bool:
        if word and word not in out:
            out.append(word)
        return len(out) >= limit

    for token in _KEYWORD_TOKEN.findall(text):
        word = _clean_word(token)
        if word is None:
            continue
        if add(word):
            break
        if split_mixed and any(add(part) for part in _script_parts(word) if _clean_word(part) == part):
            break
    return tuple(out)
