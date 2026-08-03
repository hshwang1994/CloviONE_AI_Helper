/* 팀 채팅 말풍선의 본문 해석 — 링크와 @멘션을 조각으로 나눈다. **JSX를 만들지 않는다.**
 *
 * 이 파일이 존재하는 이유는 하나다: **말풍선 본문은 사용자가 친 글자**다. 여기서 한 번이라도
 * HTML로 취급하면 그 순간 저장형 XSS가 된다. 그래서 `dangerouslySetInnerHTML`을 쓰지 않고,
 * 문자열을 **조각 배열**로 쪼개 화면이 그것을 React 텍스트 노드로만 그린다. 글자는 절대
 * 마크업이 되지 않는다.
 *
 * 링크 규칙(세 겹으로 막는다):
 *   1. 정규식이 `http://` `https://` 로 시작하는 것만 잡는다 — `javascript:` `data:` `vbscript:`
 *      는 애초에 후보가 되지 않는다.
 *   2. 잡은 문자열을 `new URL()`로 다시 파싱해 **protocol이 정확히 http/https 인지** 확인한다.
 *      정규식만 믿지 않는 이유: 사람이 정규식을 넓히는 순간(예: 스킴 없는 도메인도 링크로)
 *      1번 방어가 조용히 사라지기 때문이다. 게이트는 파싱 결과에 걸어 둔다.
 *   3. 화면은 `rel="noopener noreferrer"`와 `target="_blank"`를 붙인다(opener 탈취 방지).
 *      그 값은 여기 상수로 두어 호출부가 빠뜨릴 수 없게 한다.
 *
 * 멘션 규칙은 서버(app/team_chat/mentions.py)와 **글자 그대로 같아야 한다** — 화면에 밑줄이
 * 그어졌는데 알림은 안 갔거나 그 반대면, 둘 중 하나는 거짓말이다:
 *   1. 경계  — `@` 앞이 영숫자·밑줄이면 멘션이 아니다(이메일 제외).
 *   2. 최장 일치 — '김철'과 '김철수'가 함께 있으면 긴 쪽이 이긴다.
 *   3. 정확 일치 — 아는 이름과 글자 그대로 같을 때만. 부분 일치는 없다.
 *   4. 아는 이름의 출처도 서버와 같다 — 전체 채팅은 디렉터리, 그 외는 그 방의 참여자.
 */

// 스킴이 붙은 절대 URL만. 공백·꺾쇠·따옴표는 URL의 끝으로 본다.
const URL_RE = /https?:\/\/[^\s<>"']+/iy;
const WORD_BEFORE = /[0-9A-Za-z_]/;

// 링크에 반드시 붙는 값. 새 창에서 열리는 링크에 noopener가 없으면 열린 문서가
// `window.opener`로 이 앱의 탭을 조작할 수 있다.
export const LINK_REL = "noopener noreferrer";
export const LINK_TARGET = "_blank";

// 문장 부호로 끝나는 URL은 그 부호를 URL에서 뺀다("자세히는 https://a.b/c." 의 마침표).
const TRAILING_PUNCT = ".,;:!?…\"'`";
const CLOSERS = { ")": "(", "]": "[", "}": "{" };

function trimUrlTail(raw) {
  let out = raw;
  for (;;) {
    const last = out.slice(-1);
    if (!last) break;
    if (TRAILING_PUNCT.indexOf(last) >= 0) { out = out.slice(0, -1); continue; }
    const open = CLOSERS[last];
    if (open) {
      // 균형이 맞는 괄호는 URL의 일부다(위키백과 주소가 실제로 그렇다). 남는 닫는 괄호만 뗀다.
      const opens = out.split(open).length - 1;
      const closes = out.split(last).length - 1;
      if (closes > opens) { out = out.slice(0, -1); continue; }
    }
    break;
  }
  return out;
}

/** 링크로 써도 되는 주소면 정규화된 문자열, 아니면 null. 스킴 화이트리스트는 여기 한 곳뿐이다. */
export function safeHref(raw) {
  let url;
  try {
    url = new URL(String(raw == null ? "" : raw));
  } catch (e) {
    return null;   // 상대 경로·빈 문자열·깨진 주소 — 링크로 만들지 않는다
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return url.href;
}

/* 본문을 조각 배열로. 조각은 셋 중 하나다:
 *   { kind: "text",    text }
 *   { kind: "link",    text, href }        href는 safeHref를 통과한 값만
 *   { kind: "mention", text, name }        text는 "@이름" 그대로(원문 보존)
 *
 * names: 아는 표시 이름 배열(또는 Set). 비어 있으면 멘션 조각은 만들어지지 않는다 —
 * 모르는 이름에 밑줄을 그으면 "알림이 갔다"고 오해하게 된다.
 */
export function tokenizeMessage(body, names) {
  const text = typeof body === "string" ? body : "";
  if (!text) return [];
  const known = (names instanceof Set ? [...names] : Array.isArray(names) ? names : [])
    .filter((n) => typeof n === "string" && n.length > 0)
    .sort((a, b) => b.length - a.length);   // 최장 일치

  const out = [];
  let buf = "";
  const flush = () => { if (buf) { out.push({ kind: "text", text: buf }); buf = ""; } };

  let i = 0;
  while (i < text.length) {
    const ch = text[i];

    if (ch === "@" && (i === 0 || !WORD_BEFORE.test(text[i - 1]))) {
      const hit = known.find((n) => text.startsWith(n, i + 1));
      if (hit) {
        flush();
        out.push({ kind: "mention", text: "@" + hit, name: hit });
        i += 1 + hit.length;
        continue;
      }
    }

    if (ch === "h" || ch === "H") {
      URL_RE.lastIndex = i;
      const m = URL_RE.exec(text);
      if (m) {
        const raw = trimUrlTail(m[0]);
        const href = safeHref(raw);
        if (href) {
          flush();
          out.push({ kind: "link", text: raw, href });
          i += raw.length;
          continue;
        }
      }
    }

    buf += ch;
    i += 1;
  }
  flush();
  return out;
}

/* 이 방에서 `@`로 부를 수 있는 이름들 — 서버와 같은 출처를 쓴다(전체 채팅=디렉터리, 그 외=참여자).
 *
 * `meId` 를 주면 그 사람을 뺀다. **두 쓰임의 목록이 다르기 때문에 선택 인자다**:
 *   * 고르기 버튼(컴포저) — 나를 뺀다. 자기를 부르면 서버가 알림을 만들지 않으므로 죽은 선택지다.
 *   * 말풍선 렌더 — 아무도 빼지 않는다. **남이 나를 부른 말**에도 강조가 붙어야 한다.
 * 이 둘을 한 목록으로 쓰면 내 이름만 강조가 안 되는, 설명할 수 없는 상태가 된다.
 */
export function mentionNames({ isGlobal, members, directory, meId }) {
  const rows = isGlobal ? (directory || []) : (members || []);
  const names = [];
  const seen = new Set();
  const dropped = new Set();
  rows.forEach((r) => {
    const name = String((r && (r.name || r.display_name)) || "").trim();
    const uid = r && r.user_id;
    if (!name || uid === meId) return;
    // 동명이인은 후보에서 뺀다 — 서버도 그렇게 한다(누가 받았는지 모르는 알림을 만들지 않는다).
    if (seen.has(name)) { dropped.add(name); return; }
    seen.add(name);
    names.push(name);
  });
  return names.filter((n) => !dropped.has(n));
}
