"""성공 토스트 기본 문구 라벨 사전 회귀 방지 검사 (PA-RC-0025).

왜 필요한가: `DataScreen.jsx`의 `finishAction()`과 `SubListDrawer.jsx`의 `act()`는 액션이
`a.result(res)`로 자기만의 결과 메시지를 정의하지 않으면 `frontend/src/screens/data-screen/
successMessages.js`의 `ACTION_SUCCESS_MESSAGES` 사전에서 라벨로 문장을 찾는다(없으면
`GENERIC_SUCCESS_MESSAGE`로 떨어진다). 예전엔 두 곳 모두 `라벨 + " 완료"`로 문자열을 이어
붙였다 — "삭제" 액션이면 "삭제 완료"가 떴다. 명사형 배지처럼 읽히고 마침표도 없어
`docs/UX_WRITING.md` §2(문장형은 마침표)와 어긋났다.

라벨 텍스트를 기계적으로 이어 붙여 동사를 만드는 방식으로는 못 고친다 — "보관 복구"·"세션
해제"처럼 이미 명사 복합어인 라벨은 문자열 조작으로 자연스러운 문장이 안 나온다(이 저장소엔
실제로 그런 라벨이 있다, `UsersBulk.jsx`/`Users.jsx` — 이 검사·사전과는 별개의 자체 처리
경로다). 그래서 `ACTION_SUCCESS_MESSAGES`는 라벨마다 손으로 확인해 적은 사전이고, 이 검사는
`frontend/src/screens/registry/*.js`에 그 기본 경로를 타는(=`a.result`가 없는) 새 액션 라벨이
생기면 사전 등록을 빠뜨리지 않았는지 잡는다 — `check_typography_literals.py`(PA-RC-0001)·
`check_button_hierarchy.py`(PA-RC-0023)와 같은 이유로 같은 자리(줄 단위 정규식 + 문자열
인식 괄호 매칭, AST 없음)에 얹는다.

## 어떻게 "액션 객체"를 찾는가

registry 파일의 액션은 `actions:`/`headerActions:`/`rowActions:`/`rowAction:`이라는 이름의
키 아래에만 있지 않다 — `actions.js`의 `onoff()`/`activeToggle()`처럼 화살표 함수가 액션
배열을 **이름 없이 직접 반환**하는 공유 조각도 있다(예: `export const onoff = (...) => [
{ label: "활성화", ... }, ... ];`). 그래서 이 검사는 특정 키 이름을 찾지 않고, 파일 전체에서
`{ ... }` 객체 리터럴을 전부(중첩 포함, 재귀적으로) 찾아 **그 객체 자신의(중첩 자식이 아닌)**
키만 본다 — `label:`과 `path:`를 둘 다 own-key로 갖고 `result:`/`navigate:`/`download:`/
`info:`/`subList:`/`localInfo:`는 own-key로 갖지 않는 객체만 "기본 경로를 타는 액션"으로 친다
(각 필드가 이 판정에서 하는 역할은 `DataScreen.jsx`의 `runAction`/`runHeaderAction`/
`finishAction`, `SubListDrawer.jsx`의 `act()`를 실제로 추적해 정한 것이다 — 이 문서 하단
docstring이 아니라 그 두 파일이 정본이다).

"객체 자신의 키만" 판정은 문자열 리터럴을 건너뛰며 `{`/`[`/`}`/`]` 깊이를 세어, 깊이 1(그
객체 바로 안)보다 깊은 부분(중첩 객체·배열의 내용)은 지우고 남은 텍스트에만 정규식을 건다
— 그래야 `subList: { rowAction: { path: ... } }`처럼 중첩된 실제 액션(`rowAction`)의
`path:`가 **바깥 컨테이너 액션**(`label: "버전 기록"`, own-path 없음)의 것으로 잘못
합산되지 않는다. 완전한 JS 파서는 아니다(다른 두 검사와 동일한 한계) — 이 저장소의 액션
정의가 실제로 쓰는 모양(문자열 라벨, 화살표 함수, 블록 바디의 중첩 객체 리턴)만 다룬다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = ROOT / "frontend" / "src" / "screens" / "registry"
DICTIONARY_PATH = ROOT / "frontend" / "src" / "screens" / "data-screen" / "successMessages.js"

QUOTE_CHARS = ('"', "'", "`")
OPEN_BRACKETS = "{["
CLOSE_BRACKETS = "}]"

RX_LABEL = re.compile(r'\blabel\s*:\s*["\']([^"\']*)["\']')
EXCLUDE_KEYS = ("result", "navigate", "download", "info", "subList", "localInfo")
RX_EXCLUDE = {k: re.compile(r"\b" + k + r"\s*:") for k in EXCLUDE_KEYS}
RX_PATH_KEY = re.compile(r"\bpath\s*:")
RX_DICT_ENTRY = re.compile(r'^\s*["\']([^"\']+)["\']\s*:\s*["\']')


def _skip_string(text: str, i: int) -> int:
    """`text[i]`는 여는 인용부호( " ' ` )다. 백슬래시 이스케이프를 감안해 짝이 맞는 닫는
    인용부호 바로 다음 인덱스를 돌려준다. 문자열이 끝까지 안 닫히면(형식이 깨진 입력) 파일
    끝까지를 문자열로 친다 — 이 검사가 다룰 문제가 아니라 조용히 멈춘다."""
    quote = text[i]
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return n


def _find_matching_bracket(text: str, open_idx: int) -> int:
    """`text[open_idx]`는 `{` 또는 `[`다. 문자열 리터럴 내부를 건너뛰며 깊이를 세어 짝이
    맞는 닫는 괄호의 인덱스를 돌려준다. 짝이 안 맞으면(깨진 입력) -1."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c in QUOTE_CHARS:
            i = _skip_string(text, i)
            continue
        if c in OPEN_BRACKETS:
            depth += 1
        elif c in CLOSE_BRACKETS:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _iter_object_spans(text: str, start: int, end: int):
    """`text[start:end]` 구간에서 `{ ... }` 객체 리터럴을 전부(중첩 포함, 재귀) 찾아
    `(obj_start, obj_end)`(닫는 `}` 포함 인덱스) 쌍을 낸다. 문자열 리터럴은 건너뛴다."""
    i = start
    while i < end:
        c = text[i]
        if c in QUOTE_CHARS:
            i = _skip_string(text, i)
            continue
        if c == "{":
            close = _find_matching_bracket(text, i)
            if close == -1 or close >= end:
                return  # 짝이 안 맞음 — 더 스캔해도 신뢰할 수 없다.
            yield (i, close)
            # 이 객체 안쪽도 재귀적으로 훑는다(중첩 rowAction 등을 놓치지 않는다).
            yield from _iter_object_spans(text, i + 1, close)
            i = close + 1
            continue
        if c == "[":
            close = _find_matching_bracket(text, i)
            if close == -1 or close >= end:
                return
            # 배열 자체는 객체가 아니지만 그 안의 객체는 봐야 한다(actions: [ {...}, {...} ]).
            yield from _iter_object_spans(text, i + 1, close)
            i = close + 1
            continue
        i += 1


def _own_key_text(text: str, obj_start: int, obj_end: int) -> str:
    """`text[obj_start:obj_end]`(닫는 괄호 포함, `{`로 시작 `}`로 끝)의 **그 객체 자신의**
    키만 남긴 텍스트를 만든다 — 중첩된 `{...}`/`[...]`의 내용은 지운다(값 자체는 관심 대상이
    아니고, 그 안에 있는 `label:`/`path:` 같은 토큰이 이 객체의 own-key로 잘못 잡히는 것만
    막으면 된다). 문자열 리터럴 내용은 그대로 남긴다(라벨 값 추출에 필요하다)."""
    inner_start, inner_end = obj_start + 1, obj_end  # '{'와 짝지어진 '}' 사이
    out: list[str] = []
    depth = 0
    i = inner_start
    while i < inner_end:
        c = text[i]
        if c in QUOTE_CHARS:
            j = _skip_string(text, i)
            j = min(j, inner_end)
            if depth == 0:
                out.append(text[i:j])
            i = j
            continue
        if c in OPEN_BRACKETS:
            depth += 1
            i += 1
            continue
        if c in CLOSE_BRACKETS:
            depth -= 1
            i += 1
            continue
        if depth == 0:
            out.append(c)
        i += 1
    return "".join(out)


def _iter_default_path_labels(path: Path):
    """`path`(registry `.js` 파일 하나)에서 `label:`과 `path:`를 둘 다 own-key로 갖고
    `EXCLUDE_KEYS`는 하나도 own-key로 안 갖는 모든 객체를 찾아 `(lineno, label)`을 낸다."""
    text = path.read_text(encoding="utf-8")
    for obj_start, obj_end in _iter_object_spans(text, 0, len(text)):
        own = _own_key_text(text, obj_start, obj_end)
        if not RX_PATH_KEY.search(own):
            continue
        label_match = RX_LABEL.search(own)
        if not label_match:
            continue  # path는 있는데 라벨이 정적 문자열이 아니다 — 이 검사가 못 따라간다(미탐 허용).
        if any(rx.search(own) for rx in RX_EXCLUDE.values()):
            continue  # result/navigate/download/info/subList/localInfo 중 하나라도 있으면 이 기본 경로를 안 탄다.
        label = label_match.group(1).strip()
        if not label:
            continue
        lineno = text.count("\n", 0, obj_start) + 1
        yield lineno, label


def _iter_registry_files(registry_dir: Path):
    for p in sorted(registry_dir.rglob("*.js")):
        if ".test." in p.name:
            continue
        yield p


def _load_dictionary_keys(dictionary_path: Path) -> set[str] | None:
    """`successMessages.js`의 `ACTION_SUCCESS_MESSAGES = { "라벨": "문장", ... }` 블록에서
    키(라벨)만 뽑는다. 이 파일은 우리가 만들고 유지하는 단순한 flat 객체라(중첩 없음) 줄
    단위 정규식으로 충분하다 — registry 액션 객체처럼 중첩 파싱이 필요 없다.

    마커(`ACTION_SUCCESS_MESSAGES`)나 그 여는/닫는 중괄호를 못 찾으면(파일이 옮겨졌거나
    형식이 바뀐 실제 파싱 실패) `None`을 돌려준다 — 블록은 찾았는데 항목이 0개인 것(격리된
    시험이 빈 사전으로 "아무것도 안 걸려야 한다"를 확인할 때 쓰는 정상 입력)과 구별해야
    `main()`이 후자를 오탐으로 막지 않는다."""
    text = dictionary_path.read_text(encoding="utf-8")
    marker = "ACTION_SUCCESS_MESSAGES"
    idx = text.find(marker)
    if idx == -1:
        return None
    brace = text.find("{", idx)
    if brace == -1:
        return None
    close = _find_matching_bracket(text, brace)
    if close == -1:
        return None
    body = text[brace + 1 : close]
    keys: set[str] = set()
    for line in body.splitlines():
        m = RX_DICT_ENTRY.match(line)
        if m:
            keys.add(m.group(1))
    return keys


def main(registry_dir: Path | None = None, dictionary_path: Path | None = None) -> int:
    registry_dir = registry_dir or REGISTRY_DIR
    dictionary_path = dictionary_path or DICTIONARY_PATH

    dict_keys = _load_dictionary_keys(dictionary_path)
    if dict_keys is None:
        print(f"[FAIL] {dictionary_path}에서 ACTION_SUCCESS_MESSAGES 블록을 못 찾았다"
              " — 사전 파일이 옮겨졌거나 형식이 바뀌었다.", file=sys.stderr)
        return 1

    missing: list[str] = []
    seen_labels: set[str] = set()
    scanned_labels = 0
    for path in _iter_registry_files(registry_dir):
        rel = path.relative_to(registry_dir).as_posix()
        for lineno, label in _iter_default_path_labels(path):
            scanned_labels += 1
            seen_labels.add(label)
            if label not in dict_keys:
                missing.append(f"{rel}:{lineno}: label={label!r}")

    if missing:
        print("[FAIL] 기본 성공 토스트 경로(a.result 없음)를 타는 액션 라벨이 사전에 없다:", file=sys.stderr)
        for h in sorted(set(missing)):
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  frontend/src/screens/data-screen/successMessages.js의 ACTION_SUCCESS_MESSAGES에", file=sys.stderr)
        print("  이 라벨 → 문장형 성공 문구를 손으로 추가하라(라벨을 기계적으로 conjugate하지 않는다 —", file=sys.stderr)
        print("  PA-RC-0025). docs/UX_WRITING.md의 사전 사본도 함께 갱신한다.", file=sys.stderr)
        return 1

    print(
        f"SUCCESS_TOAST_LABELS_OK (기본 경로 라벨 {len(seen_labels)}종, "
        f"사전 항목 {len(dict_keys)}종, 객체 {scanned_labels}건 스캔)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
