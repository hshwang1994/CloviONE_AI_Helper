/* 팀 채팅 입력창(컴포저)의 순수 로직 — 이모지 표, 커서 삽입, 클립보드 이미지 추출.
 *
 * ChatPane.jsx 에서 떼어낸 이유는 두 가지다. (1) 이 셋은 DOM 없이 검증할 수 있는데 컴포넌트
 * 안에 있으면 렌더 하네스를 통해서만 만질 수 있다. (2) ChatPane 은 이미 폴링·말풍선·읽음
 * 처리를 지고 있어 더 키우면 한 파일이 채팅 전부가 된다.
 *
 * 이모지는 **유니코드 문자만** 쓴다 — 이미지 스프라이트나 외부 폰트를 쓰면 CSP
 * (default-src 'self')에 걸리고 오프라인 사내망에서 깨진다. 브라우저·OS가 이미 그리는 글자다.
 */

// 자주 쓰는 것 위주로 짧게. 길게 늘리면 피커가 스크롤 상자가 되고, 정작 쓰는 건 앞 20개다.
export const EMOJI_GROUPS = [
  {
    label: "표정",
    emojis: ["😀", "😄", "😊", "🙂", "😉", "😍", "🤩", "😎", "🤔", "😅",
             "😂", "🥲", "😢", "😭", "😤", "😱", "🤯", "😴", "🤗", "🙃"],
  },
  {
    label: "반응",
    emojis: ["👍", "👎", "👏", "🙏", "🙌", "👌", "✌️", "🤝", "💪", "🫡",
             "❤️", "🔥", "✨", "🎉", "🎊", "💯", "✅", "❌", "⚠️", "❓"],
  },
  {
    label: "업무",
    emojis: ["📌", "📝", "📅", "⏰", "🚀", "🐛", "🔧", "📊", "📎", "💡",
             "☕", "🍚", "🥳", "🏃", "🛠️", "🔍", "📣", "🗓️", "🧑‍💻", "🤖"],
  },
];

/** 커서 위치에 문자열을 끼워 넣는다. 반환: { text, caret } — caret 은 삽입 뒤 커서 위치. */
export function insertAtCursor(text, insert, selStart, selEnd) {
  const src = typeof text === "string" ? text : "";
  const add = typeof insert === "string" ? insert : "";
  // 선택 위치를 모르면(포커스가 없던 경우) 맨 뒤에 붙인다 — 임의로 0을 쓰면 문장 앞에 끼어든다.
  const start = Number.isInteger(selStart) && selStart >= 0 && selStart <= src.length ? selStart : src.length;
  const end = Number.isInteger(selEnd) && selEnd >= start && selEnd <= src.length ? selEnd : start;
  return { text: src.slice(0, start) + add + src.slice(end), caret: start + add.length };
}

/** 서버 uploads.IMAGE_MEDIA_TYPES 와 같은 목록 — 여기서 미리 걸러 헛된 업로드를 줄인다.
 *  판정은 어차피 서버가 매직바이트로 다시 한다(브라우저가 붙인 type 은 신뢰하지 않는다). */
export const PASTE_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

/** 서버 MAX_UPLOAD_BYTES(10MB)와 같은 값. 넘으면 올리기 전에 안내한다. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** 붙여넣기 이벤트의 clipboardData 에서 첫 이미지 파일을 꺼낸다. 없으면 null. */
export function imageFromClipboard(clipboardData) {
  const items = clipboardData && clipboardData.items;
  if (!items || !items.length) return null;
  for (let i = 0; i < items.length; i += 1) {
    const it = items[i];
    if (!it || it.kind !== "file") continue;
    if (!PASTE_IMAGE_TYPES.includes(it.type)) continue;
    const file = typeof it.getAsFile === "function" ? it.getAsFile() : null;
    if (file) return file;
  }
  return null;
}

/** 붙여넣은 이미지의 사전 검증. 통과하면 null, 아니면 사용자에게 보일 한국어 사유. */
export function imageRejectReason(file) {
  if (!file) return "이미지를 읽지 못했습니다.";
  if (!file.size) return "빈 파일은 보낼 수 없습니다.";
  if (file.size > MAX_IMAGE_BYTES) {
    return `이미지가 너무 큽니다. 최대 ${MAX_IMAGE_BYTES / (1024 * 1024)}MB까지 보낼 수 있습니다.`;
  }
  return null;
}
