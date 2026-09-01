import React from "react";

/* 여러 줄 입력칸의 **커서 자리**를 다루는 공용 부품.
 *
 * ## 왜 있는가 — 실제로 겪은 결함
 *
 * 포커스를 한 번도 안 준 `<textarea>` 의 `selectionStart` 는 `null` 이 아니라 **`0`** 이다.
 * 그 값을 「사용자가 맨 앞에 커서를 뒀다」로 읽으면 서식·이모지 단추가 전부 **글 맨 앞**에
 * 값을 꽂는다. 새 티켓 폼에서 특히 잘 터졌다 — 「작성 도움」 레일이 상태만 바꿔 설명을
 * 채우기 때문에 편집기는 포커스를 받은 적이 없고, 그 뒤 이모지를 고르면 `🎯## 배경` 이 되어
 * 마크다운 제목 파싱까지 깨진다.
 *
 * 채팅 컴포저는 이 함정을 이미 알고 방어하고 있었다(`screens/chat-compose.js` 의 옛 주석:
 * 「임의로 0을 쓰면 문장 앞에 끼어든다」). 문서 편집기(TipTap)는 `focus()` 를 먼저 주고 넣어
 * 애초에 안 겪는다. **「문서에서는 되는데 티켓에서는 안 된다」의 정확한 출처가 이것이다.**
 *
 * 그래서 규칙을 한 곳에 둔다. `ui/` 가 `screens/` 를 import 하는 역방향 의존을 만들지 않으려고
 * 여기(`lib/`)에 있고, `chat-compose.js` 는 이것을 그대로 다시 내보낸다.
 */

/** 커서 자리에 문자열을 끼워 넣는다. 반환: `{ text, caret }` — `caret` 은 삽입 뒤 커서 위치. */
export function insertAtCursor(text, insert, selStart, selEnd) {
  const src = typeof text === "string" ? text : "";
  const add = typeof insert === "string" ? insert : "";
  // 선택 위치를 모르면(포커스가 없던 경우) 맨 뒤에 붙인다 — 임의로 0을 쓰면 문장 앞에 끼어든다.
  const start = Number.isInteger(selStart) && selStart >= 0 && selStart <= src.length ? selStart : src.length;
  const end = Number.isInteger(selEnd) && selEnd >= start && selEnd <= src.length ? selEnd : start;
  return { text: src.slice(0, start) + add + src.slice(end), caret: start + add.length };
}

/** **마지막으로 알려진** 선택 위치를 기억한다.
 *
 * 🔴 `selectionStart` 를 그때그때 읽으면 안 된다 — 포커스가 없던 입력칸은 `0` 을 돌려주고,
 * 그 `0` 은 「모른다」와 「맨 앞」을 구별하지 못한다. 사용자가 실제로 그 칸을 만졌을 때만
 * 적어 두고, 한 번도 안 만졌으면 `null` 로 남긴다 — 그러면 `insertAtCursor` 가 맨 뒤로 보낸다.
 *
 * 반환하는 `handlers` 를 입력칸에 그대로 펼친다. `value` 가 바뀌면(다른 티켓을 열거나 폼이
 * 초기화되면) 기억을 버린다 — 옛 글의 좌표는 새 글에서 뜻이 없다.
 */
export function useCaretTracker(value) {
  const sel = React.useRef(null);
  const seen = React.useRef(value);
  if (seen.current !== value && sel.current == null) seen.current = value;
  const remember = React.useCallback((e) => {
    const el = e && e.target;
    if (!el || typeof el.selectionStart !== "number") return;
    sel.current = { start: el.selectionStart, end: el.selectionEnd };
  }, []);
  const reset = React.useCallback(() => { sel.current = null; }, []);
  const current = React.useCallback(() => sel.current, []);
  /* 프로그램이 커서를 옮긴 뒤 알려 주는 자리. `setSelectionRange` 는 `select` 이벤트를
     **안 낸다** — 이것이 없으면 연달아 두 번 넣을 때 두 번째가 첫 번째 자리로 되돌아간다. */
  const set = React.useCallback((start, end) => {
    sel.current = { start, end: end == null ? start : end };
  }, []);
  return {
    caret: current,
    set,
    reset,
    handlers: {
      onSelect: remember,
      onKeyUp: remember,
      onClick: remember,
      onFocus: remember,
    },
  };
}