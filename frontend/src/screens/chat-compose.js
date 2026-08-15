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

// VIS-86과 같은 뿌리 — EMOJI_GROUPS의 각 글자를 고르는 버튼이 aria-label 없이 이모지
// 자체를 자식으로만 그려, 스크린리더가 그 글자를 못 읽으면(플랫폼/폰트에 따라 다르다)
// 아무것도 안 들린다. EMOJI_GROUPS(위)는 "유니코드 문자만" 계약을 시험이 고정하고 있어
// {emoji,label} 객체로 바꾸지 않고, 이름표만 별도로 둔다 — 발음이 아니라 표준 명칭이다
// (개인 해석이 아니라 이모지 자체가 무엇인지 말한다, BODY_EMOJIS처럼 "넣을 내용의 뜻"이
// 아니라 "이 그림이 무엇인가"인 이유는 이 피커는 문서 서식 도구가 아니라 범용 반응/표현
// 선택기라 고정된 하나의 용도가 없다).
export const EMOJI_LABELS = {
  "😀": "활짝 웃는 얼굴", "😄": "환하게 웃는 얼굴", "😊": "미소 짓는 얼굴", "🙂": "살짝 웃는 얼굴",
  "😉": "윙크하는 얼굴", "😍": "하트 눈 얼굴", "🤩": "반한 얼굴", "😎": "선글라스 쓴 얼굴",
  "🤔": "생각하는 얼굴", "😅": "식은땀 흘리며 웃는 얼굴", "😂": "눈물 흘리며 웃는 얼굴",
  "🥲": "미소 지으며 눈물짓는 얼굴", "😢": "우는 얼굴", "😭": "대성통곡하는 얼굴",
  "😤": "화나서 씩씩거리는 얼굴", "😱": "비명 지르는 얼굴", "🤯": "머리가 터진 얼굴",
  "😴": "잠자는 얼굴", "🤗": "포옹하는 얼굴", "🙃": "거꾸로 뒤집힌 얼굴",
  "👍": "엄지척", "👎": "엄지 아래", "👏": "박수", "🙏": "기도하는 손", "🙌": "만세",
  "👌": "오케이 손짓", "✌️": "브이", "🤝": "악수", "💪": "힘내기", "🫡": "경례하는 얼굴",
  "❤️": "하트", "🔥": "불꽃", "✨": "반짝임", "🎉": "축하 폭죽", "🎊": "색종이 폭죽",
  "💯": "백점", "✅": "완료 체크", "❌": "취소 표시", "⚠️": "경고", "❓": "물음표",
  "📌": "압정", "📝": "메모", "📅": "달력", "⏰": "알람 시계", "🚀": "로켓", "🐛": "버그",
  "🔧": "렌치", "📊": "막대 그래프", "📎": "클립", "💡": "전구", "☕": "커피", "🍚": "밥",
  "🥳": "파티하는 얼굴", "🏃": "달리는 사람", "🛠️": "공구", "🔍": "돋보기", "📣": "메가폰",
  "🗓️": "달력", "🧑‍💻": "개발자", "🤖": "로봇",
};

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
  if (!file) return "이미지를 읽지 못했습니다. 다시 시도해 주세요.";
  if (!file.size) return "빈 파일은 보낼 수 없습니다.";
  if (file.size > MAX_IMAGE_BYTES) {
    return `이미지가 너무 큽니다. 최대 ${MAX_IMAGE_BYTES / (1024 * 1024)}MB까지 보낼 수 있습니다.`;
  }
  return null;
}
