import { fmtDateTime } from "../lib/format.js";

// 우선순위 어휘는 lib/priority.js가 소유한다(티켓 화면 두 곳이 채팅과 무관하게 쓴다).
// 여기서 다시 내보내는 이유는 하나다 — 채팅 결과 카드가 이 두 함수를 쓰고, 이 화면의
// 헬퍼 테스트가 '채팅이 쓰는 어휘'로 함께 검증한다. 정의를 복제하지는 않는다.
export { priorityKo, priorityKind } from "../lib/priority.js";

/* AI 채팅(§6.5)의 순수 함수·상수 모듈 — JSX가 한 줄도 없다.
 *
 * 왜 나눴나: Chat.jsx 한 파일이 순수 함수 20여 개 + 리치텍스트 렌더러 + 폴링/쿼리 상태 +
 * 화면을 전부 담고 있었다(1,205줄). 테스트는 이 순수 함수들만 보는데 파일을 import하는 순간
 * react-query·MUI 키트까지 딸려 왔고, 화면 코드를 한 줄 고칠 때마다 그 무게가 함께 움직였다.
 *
 * 이 모듈의 계약: **JSX를 만들지 않는다.** linkifyText/RichText처럼 React 엘리먼트를 돌려주는
 * 것들은 Chat.jsx에 남는다 — 여기로 들어오면 이 파일이 다시 React에 묶여 분리한 의미가 없어진다.
 * 폴링/쿼리 상태는 useChat.js가 가져갔다.
 *
 * 동작은 한 줄도 바꾸지 않았다(순수 이동). chat-helpers.test.js의 47개 단언이 그 증거다.
 */

// ── 시각 표시 ───────────────────────────────────────────────────────────────

// 마감일 정규화 — 날짜만(YYYY-MM-DD)이면 그대로, ISO 타임스탬프면 KST로 표시(영문/ISO 누출 방지).
export function fmtDue(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  return fmtDateTime(s);
}

// 대화 목록용 짧은 시각 라벨 — 오늘이면 시:분, 아니면 월.일(사이드바 폭이 좁아 전체 날짜는 넘친다).
export function fmtShort(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const opts = sameDay ? { timeStyle: "short" } : { month: "numeric", day: "numeric" };
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", ...opts }).format(d);
}

// 대화 목록용 시:분만 — 같은 날 스레드에서 매 말풍선에 전체 날짜를 반복하면 소음이 된다.
export function fmtTime(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit" }).format(d);
}

// 스레드 안 날짜 구분선 — 대화는 여러 날에 걸칠 수 있는데(보관·이름변경으로 다시 여는 게 흔하다)
// 말풍선 라벨은 시:분만 보여줘, 사흘 전 15:23과 오늘 15:23이 구분되지 않았다. 날짜가 바뀌는 지점에만
// 가운데 칩(예: '2026년 7월 26일')을 끼워 넣는다. dayKeyKST는 KST 기준 하루 경계로 그룹을 나눈다.
export function dayKeyKST(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  // en-CA는 YYYY-MM-DD 형태라 하루 경계 비교에 안전하다(로캘 의존 형식이 아님).
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}
export function fmtDateSep(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric" }).format(d);
}

// ── 폴링·지연 판정 ──────────────────────────────────────────────────────────

// 처리 중 메시지가 이 시간(밀리초)을 넘겨도 답이 없으면 '지연'으로 보고 무한 폴링을 멈춘다.
// 값의 근거: chat_message 잡은 max_attempts=3, 매 시도 n8n_timeout 180초 + 백오프 → 정상적으로도
// 최대 약 9분 15초 걸린다(바닐라 POLL_MAX_WAIT_MS와 동일). 짧게 잡으면 살아 있는 작업을 '지연'으로
// 오인해 폴링을 끊고, 진행 중인 답이 실패처럼 보인다.
export const STALL_MS = 600000;

// 메시지 생성 시각(서버 UTC) 이후 경과 밀리초. 시간대 접미사가 없으면 UTC로 간주(fmtShort와 동일).
// sinceMs를 주면(수동 새로고침 기준선) 생성 시각과 그 중 더 늦은 쪽부터 다시 잰다 — created_at은
// 불변이라 그것만 쓰면 '새로고침'을 눌러도 그 즉시 다시 stalled로 재계산돼(§ 버그) 폴링이 재개되지
// 않는 막다른 길이 된다. 기준선을 이렇게 두면 새로고침 순간부터 새 STALL_MS 창이 시작된다.
export function msgAgeMs(m, sinceMs) {
  if (!m || !m.created_at) return 0;
  const s = String(m.created_at);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return 0;
  const base = sinceMs != null ? Math.max(t, sinceMs) : t;
  return Date.now() - base;
}

// 스레드 폴링 스케줄 — 연속 실패 횟수(fails)만 보고 다음 간격(ms)을 정한다. false면 자동 폴링 중단.
// 5회 연속 실패하면(약 20초, 백오프 포함) 자동 재시도를 멈춘다 — 배너의 '새로고침' 버튼으로
// 수동 재개할 수 있다. 실패가 쌓일수록 간격을 늘려(최대 5초) 죽은 서버를 촘촘히 두드리지 않는다.
// 이 계산을 함수로 뽑아 둔 이유는 하나다: 백오프와 포기 지점은 이 화면의 핵심 방어선인데
// refetchInterval 콜백 안에 인라인으로 있으면 테스트가 가짜 타이머로 검증할 수가 없었다.
export const POLL_BASE_MS = 1500;
export const POLL_MAX_MS = 5000;
export const POLL_MAX_FAILURES = 5;
export function pollDelayMs(fails) {
  const n = typeof fails === "number" && fails > 0 ? fails : 0;
  if (n >= POLL_MAX_FAILURES) return false;
  return n > 0 ? Math.min(POLL_BASE_MS * Math.pow(2, n), POLL_MAX_MS) : POLL_BASE_MS;
}

// ── 시작 예시·저장 키 ───────────────────────────────────────────────────────

// 시작 예시(빈 화면에서 눌러 바로 대화 시작). 바닐라의 추천 프롬프트를 React로 복원.
export const QUICK_PROMPTS = [
  "무엇을 할 수 있어?",
  "내가 만든 티켓 보여줘",
  "나에게 할당된 티켓 보여줘",
  // USER_GUIDE.md가 광고하는 '내 담당 프로젝트' 칩이 실제로는 빠져 있어(프로젝트 조회는 문서화된
  // 기능인데 시작 화면에서 발견할 길이 없었다) 복원한다.
  "내 담당 프로젝트 보여줘",
  "이번 주 마감인 티켓 알려줘",
  "진행 중인 티켓을 우선순위 순으로 요약해줘",
  "새 티켓 만들어줘",
];

export const CHAT_LAST_CONV_KEY = "chat.lastConversationId"; // 새로고침 후 열려 있던 대화 복원용(세션 한정)

/* 대화 목록이 '오버레이 서랍'에서 '상주하는 열'로 바뀌는 폭(px). MUI 테마의 xl과 같은 값이다.
 *
 * 왜 900(md)이 아니라 1536인가: 이 앱은 860px부터 전역 사이드바가 상주한다. md에서 대화 목록까지
 * 열로 세우면 1024·1152·1366 사내 장비에서 사이드바가 둘(284+304px) 서서 실제 대화 폭이 절반 아래로
 * 떨어진다 — 대화 목록을 전 폭에서 서랍으로 되돌린 것이 애초에 그 때문이었다. 폭이 진짜로 남을 때만
 * 세운다.
 *
 * 이 값을 상수로 둔 이유: 훅(matchMedia로 서랍의 inert·포커스 반환을 판단)과 화면(그리드 열 정의)이
 * 같은 경계를 봐야 한다. 두 곳에 숫자를 적으면 반드시 어긋나서, 열로 서 있는 목록이 inert가 되거나
 * 서랍이 열린 채 배경이 안 잠기는 상태가 생긴다.
 */
export const LIST_DOCK_PX = 1536;
export const LIST_DRAWER_MEDIA = `(max-width: ${LIST_DOCK_PX - 0.02}px)`;

// ── 첨부(이미지) ────────────────────────────────────────────────────────────

export const MAX_ATTACH_BYTES = 3 * 1024 * 1024; // 서버 이미지 상한과 맞춤(개당 3MB)
export const MAX_TOTAL_ATTACH_BYTES = 6 * 1024 * 1024; // 서버 전체 상한과 맞춤(합계 6MB)
export const MAX_ATTACH_COUNT = 3; // 서버가 받는 이미지 최대 장수
// 서버가 실제로 허용하는 이미지 타입(app/chat/attachments.py ALLOWED_MEDIA_TYPES)만 받는다.
// accept="image/*"로 열어두면 HEIC/GIF/SVG가 통과했다가 서버 400으로 메시지 전체가 실패한다.
export const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

// base64 문자열의 디코드 바이트 수 추정(전체 첨부 용량을 서버 왕복 전에 검사하기 위함).
export function b64Bytes(data) {
  const s = String(data || "");
  const pad = s.endsWith("==") ? 2 : s.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor(s.length * 3 / 4) - pad);
}

// 캔버스로 재인코딩해 스크린샷을 작게 만든다(긴 변 ≤1568px, JPEG q0.85). 원본을 그대로
// 올리면 폰 사진·스샷은 대부분 3MB를 넘겨 서버 전에 거부됐다 — 축소 후 크기로 검사한다.
export function downscaleImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const MAX_EDGE = 1568;
      const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) { reject(new Error("이미지 인코딩에 실패했습니다.")); return; }
      ctx.drawImage(img, 0, 0, w, h);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
      const base64 = dataUrl.split(",")[1] || "";
      if (!base64) { reject(new Error("이미지 인코딩에 실패했습니다.")); return; }
      resolve({ media_type: "image/jpeg", data: base64 });
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("이미지를 읽을 수 없습니다.")); };
    img.src = url;
  });
}

/* ---------- 답변 본문의 구조(바닐라 chat.js parseBlocks/classifyLine 포팅) ----------
 * 러너(assistant.py)가 이미 쓰는 관례만 알아본다: "[머리글]"·"■ 머리글", "1. …"·"- …" 목록,
 * 윗 항목의 들여쓴 딸린 줄, 2줄 이상 이어지는 "키: 값" 표. 새 문법은 만들지 않는다.
 * 글자는 오직 JSX 텍스트 노드(textContent)로만 들어간다 — innerHTML 금지(CLAUDE.md §2). */
export const RE_HEAD_BRACKET = /^\[([^\]]{1,40})\]\s*(.*)$/;
export const RE_HEAD_BULLET = /^■\s*(.+)$/;
export const RE_ORDERED = /^(\d{1,3})\.\s+(.*)$/;
export const RE_UNORDERED = /^-\s+(.*)$/;
export const RE_SUBLINE = /^\s{2,}(\S.*)$/;
// 키는 짧다. 콜론이 든 평범한 문장을 표로 오해하지 않으려는 상한이다.
export const RE_KV = /^([^:\s][^:]{0,15}?)\s*:\s*(.*)$/;
// AI-34: 백틱 3개짜리 펜스 코드블록 시작/끝. 언어 태그(백틱3개+python 등)는 lang으로
// 잡되, 그 뒤에는 공백만 허용한다(코드 자체가 아니라 펜스 구분선으로만 본다).
// 정규식 리터럴에 백틱 문자를 그대로 3개 연속으로 적으면 scripts/check_user_text.py의
// 순수 문자 스캐너(따옴표 상태를 추적하되 정규식 리터럴은 모른다)가 백틱을 템플릿
// 리터럴 시작으로 오인해, 그 뒤로 파일 끝까지(또는 다음 백틱까지) 주석 제거가 멈춰
// 버린다(직접 겪음 — 아래쪽 무관한 주석들이 "사용자 문구"로 오탐됐다) — \x60(16진
// 문자 코드)로 우회한다.
export const RE_FENCE = /^\x60\x60\x60(\S*)\s*$/;

// 시각 표기 오탐 방지(step 10 #3, node로 재현 확인) — RE_KV는 첫 콜론만 보므로
// "시" 부분이 키에, "분" 부분이 값 머리에 걸린다. 예전엔 키가 **순수 숫자뿐**일 때만
// 막았다("09:00") — "오전 9:30에 회의"처럼 시 앞에 다른 말이 붙으면 못 잡아 2줄짜리
// 정의목록(dl)으로 잘못 렌더됐다. 키 끝이 시(0~23)로 끝나고 값 머리가 분(00~59)이면
// 시각으로 본다(줄 시작·공백·여는 괄호 뒤에 오는 숫자만 "시"로 본다 — "질문2"의 "2"처럼
// 글자 바로 뒤에 붙은 숫자는 시가 아니다).
const HOUR_TAIL = /(?:^|[\s(])([01]?\d|2[0-3])\s*$/;
const MINUTE_HEAD = /^([0-5]\d)(?!\d)/;

export function kvOf(line) {
  const m = RE_KV.exec(line);
  if (!m) return null;
  if (HOUR_TAIL.test(m[1]) && MINUTE_HEAD.test(m[2])) return null;  // "09:00", "오전 9:30" — 시각
  if (m[2].slice(0, 2) === "//") return null;  // "https://…" — URL 스킴
  return { kind: "kv", key: m[1], text: m[2], raw: line };
}

export function classifyLine(line) {
  if (!line.trim()) return { kind: "blank" };
  let m;
  const sub = RE_SUBLINE.exec(line);
  const body = sub ? sub[1] : line;   // 들여쓴 줄이면 들여쓰기를 뺀 알맹이
  if ((m = RE_ORDERED.exec(body))) return { kind: "item", marker: m[1] + ".", text: m[2] };
  if ((m = RE_UNORDERED.exec(body))) return { kind: "item", marker: "", text: m[1] };
  if (sub) return { kind: "sub", text: sub[1], raw: line };
  if ((m = RE_HEAD_BRACKET.exec(line))) return { kind: "head", text: m[1], note: m[2] };
  if ((m = RE_HEAD_BULLET.exec(line))) return { kind: "head", text: m[1], note: "" };
  return kvOf(line) || { kind: "text", text: line };
}

export function parseBlocks(source) {
  const blocks = [];
  let cur = null;   // 열린 목록/문단/키-값 블록. 빈 줄이 닫는다.
  // AI-34: 펜스 안 줄은 classifyLine에 절대 안 보낸다 — 예전엔 펜스 상태 자체가 없어서
  // 펜스 안의 "- foo"가 불릿으로, "def f(x):"가 정의목록(kv) 행으로 오분류됐다(자유형
  // LLM 응답에 코드 예시가 나올 때 실제로 겪는 경로 — claude_query()는 펜스를 막지 않는다).
  let fence = null;  // { lang, lines } — 열린 펜스 동안 원본 줄을 그대로 모은다.
  String(source || "").split(/\r\n?|\n/).forEach((line) => {
    if (fence) {
      if (RE_FENCE.test(line)) {
        blocks.push({ kind: "code", lang: fence.lang, text: fence.lines.join("\n") });
        fence = null;
      } else {
        fence.lines.push(line);
      }
      return;
    }
    const openFence = RE_FENCE.exec(line);
    if (openFence) {
      cur = null;
      fence = { lang: openFence[1] || "", lines: [] };
      return;
    }
    let c = classifyLine(line);
    if (c.kind === "blank") { cur = null; return; }
    if (c.kind === "head") { cur = null; blocks.push({ kind: "head", text: c.text, note: c.note }); return; }
    if (c.kind === "item") {
      if (!cur || cur.kind !== "list") { cur = { kind: "list", items: [] }; blocks.push(cur); }
      cur.items.push({ marker: c.marker, text: c.text, subs: [] });
      return;
    }
    if (c.kind === "sub") {
      if (cur && cur.kind === "list" && cur.items.length) { cur.items[cur.items.length - 1].subs.push(c.text); return; }
      c = { kind: "text", text: c.raw };   // 붙일 항목이 없으면 원본 그대로 평범한 줄
    }
    if (c.kind === "kv") {
      if (!cur || cur.kind !== "kv") { cur = { kind: "kv", rows: [] }; blocks.push(cur); }
      cur.rows.push({ key: c.key, text: c.text, raw: c.raw });
      return;
    }
    if (!cur || cur.kind !== "para") { cur = { kind: "para", lines: [] }; blocks.push(cur); }
    cur.lines.push(c.text);
  });
  // AI-34: 닫는 펜스(백틱 3개) 없이 입력이 끝나면(잘린 응답 등) 그때까지 모은 줄을
  // 잃지 않고 code 블록으로 낸다. 침묵 손실보다 낫다.
  if (fence) {
    blocks.push({ kind: "code", lang: fence.lang, text: fence.lines.join("\n") });
  }
  // "키: 값"처럼 생긴 줄 하나는 표가 아니라 문장이다("내 티켓: 총 25건"). 표는 2줄 이상일 때만.
  return blocks.map((b) => (b.kind === "kv" && b.rows.length < 2)
    ? { kind: "para", lines: b.rows.map((r) => r.raw) }
    : b);
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면(구조화된 notion_url/ticket.url 필드가 아니라
// 그냥 문장 중간의 참조 링크) 이전엔 죽은 평문으로만 보였다, 구조화 필드와 같은 safeNotion 게이트로
// <a>(허용 도메인)/PlainUrl(그 외, 복사 폴백) 처리한다. 실제로 쪼개 쓰는 linkifyText는 JSX를
// 돌려주므로 Chat.jsx에 남는다 — 이 모듈은 패턴만 소유한다.
export const URL_RE = /(https?:\/\/[^\s]+)/g;

// ── 러너 응답(structured) 정규화 ────────────────────────────────────────────

// 러너가 결과를 담는 여러 모양(배열/단일 객체/스칼라/undefined)을 카드용 '객체 배열'로 안전 변환.
// 배열이면 객체 원소만, 단일 객체면 1개짜리 배열, 그 외(스칼라·undefined)면 빈 배열.
export function objArray(v) {
  if (Array.isArray(v)) return v.filter((x) => x && typeof x === "object");
  return v && typeof v === "object" ? [v] : [];
}

// 프로젝트 이름을 결정적 색조(0~7)로, 같은 프로젝트가 어디서나 같은 색 점을 갖게(바닐라 projectTone).
export function projectTone(name) {
  const s = String(name || "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 8;
}

// projectTone(0~7)의 실제 색. screens.css의 .project-dot.tone-N과 **같은 값**이다 — 채팅 카드를
// MUI로 옮기면서 그 클래스를 더는 쓰지 않지만, 같은 프로젝트가 다른 화면에서 다른 색 점을 갖게
// 되면 '색으로 프로젝트를 알아본다'는 규칙 자체가 깨진다. 여기로 옮겨 값만 공유한다.
// 대비: WCAG 비텍스트(1.4.11, ≥3:1)를 라이트(#FFFFFF)·다크(#11182D) 표면 양쪽에 대해
// 직접 계산해 확인했다. 원래 주황(#F08C00)은 다크에서는 7.09지만 라이트에서 2.48로
// 기준 미달이었다(DS-30) — 두 표면 모두 통과하는 값(#C26A00, 라이트 3.92·다크 4.49)으로 교체.
export const PROJECT_TONE_COLORS = [
  "#E5484D", "#E8590C", "#C26A00", "#2F9E44",
  "#0CA678", "#1971C2", "#7048E8", "#C2255C",
];
export function projectToneColor(name) {
  return PROJECT_TONE_COLORS[projectTone(name)];
}

// 러너 티켓은 배열을 담는다(assignees: 이름 또는 {name} 객체, project_names 등). 어떤 모양이 와도
// 안전하게 사람 이름 문자열로 만든다. 스칼라·undefined도 안전.
export function peopleText(value) {
  if (Array.isArray(value)) {
    return value.map((p) => (typeof p === "string" ? p : (p && (p.name || p.email)) || "")).filter(Boolean).join(", ");
  }
  return typeof value === "string" ? value : "";
}

// 카드 번호("N번 상세"의 근거)는 본문 목록 번호와 반드시 같아야 한다, 어긋나면 번호를 안 붙인다.
export function pageNumberOrNull(value) {
  if (typeof value !== "number" || !isFinite(value) || Math.floor(value) !== value || value < 1) return null;
  return value;
}
export function bodyListStart(content) {
  const m = /^\s*(\d+)\.\s/m.exec(String(content || ""));
  return m ? pageNumberOrNull(Number(m[1])) : null;
}
export function ticketPageStart(structured, content) {
  if (!structured || typeof structured !== "object") return null;
  const ctx = structured.context;
  const claimed = pageNumberOrNull(structured.start_index);
  const carried = ctx && typeof ctx === "object" ? pageNumberOrNull(ctx.last_result_start) : null;
  const start = claimed !== null ? claimed : carried;
  if (start === null) return null;
  const bs = bodyListStart(content);
  if (bs !== null && bs !== start) return null;   // 본문 번호와 어긋나면 물려받은(잘못된) 값 — 버린다
  return start;
}

// 목록 응답은 같은 티켓을 본문과 카드에 두 번 낸다. 상세는 카드가 지므로 본문에서 항목 줄
// ("{번호}. …")과 거기 딸린 들여쓴 줄만 걷어낸다. 러너가 하는 말(요약·안내)은 한 줄도 안 지운다.
export function stripDuplicatedTicketLines(content) {
  const kept = [];
  let inItem = false;
  String(content).split("\n").forEach((line) => {
    if (/^\s*\d+\.\s/.test(line)) { inItem = true; return; }   // 항목 줄 — 카드가 대신 진다
    if (inItem && /^\s{2,}\S/.test(line)) return;              // 항목의 딸린 들여쓴 줄
    inItem = false;
    kept.push(line);
  });
  // 항목이 빠진 자리의 연속 빈 줄은 하나로 줄이고 앞뒤 빈 줄은 없앤다.
  const out = [];
  kept.forEach((line) => {
    if (!line.trim() && (!out.length || !out[out.length - 1].trim())) return;
    out.push(line);
  });
  while (out.length && !out[out.length - 1].trim()) out.pop();
  return out.join("\n");
}

/* 어시스턴트 메시지의 structured 페이로드를 '카드로 그릴 것들'로 정규화한다.
 *
 * 러너가 결과를 담는 모양이 여러 가지다(바닐라 renderStructured): 배열 tickets/projects/items/
 * results, 단일 객체 ticket/project, 그리고 문서 링크만 있는 notion_url/url. 어떤 모양(스칼라·
 * 배열·undefined)이 와도 objArray가 막는다.
 *
 * ticketsArr를 따로 돌려주는 이유: **본문의 번호 목록과 짝이 맞는 것은 tickets 배열뿐**이다
 * (ticketPageStart가 그 배열 기준으로 시작 번호를 낸다). 그 뒤에 이어붙는 단일 ticket 객체까지
 * 같이 순번을 매기면 본문에 없는 'N번' 라벨이 생겨 '상세' 버튼이 엉뚱한 항목을 가리킨다.
 *
 * 이 추출을 함수로 뽑은 실질적 이유: 초광폭(≥xxl)에서 카드가 말풍선 안이 아니라 오른쪽 컨텍스트
 * 레일에 그려진다 — 두 자리가 같은 규칙을 봐야 하는데, 인라인으로 두면 반드시 한쪽만 고쳐진다.
 */
export function structuredCards(m) {
  const st = (m && m.structured) || {};
  const ticketsArr = objArray(st.tickets);
  const tickets = [...ticketsArr, ...objArray(st.ticket)];
  const projects = [...objArray(st.projects), ...objArray(st.project)];
  const listItems = objArray(st.items);
  const results = objArray(st.results);
  // 카드가 하나도 없고 오직 Notion 링크만 있으면 '관련 문서' 링크 카드로 대체(allowlist 통과 시에만).
  const notionRaw = typeof st.notion_url === "string" ? st.notion_url : (typeof st.url === "string" ? st.url : "");
  const notionUrl = notionRaw && safeNotion(notionRaw) ? notionRaw : "";
  // allowlist에 걸린 문서 참조도 조용히 버리지 않는다 — 링크로는 못 열어도 카드 자체는 남겨서
  // "무언가 참조됐다"는 사실이 화면에서 사라지지 않게 한다(렌더 쪽에서 PlainUrl로 대체).
  const notionUnsafe = notionRaw && !notionUrl ? notionRaw : "";
  const hasCards = !!(tickets.length || projects.length || listItems.length || results.length);
  return {
    ticketsArr, tickets, projects, listItems, results,
    notionUrl, notionUnsafe, hasCards,
    // 레일에 무언가 그릴 게 있는가(카드 또는 문서 링크).
    hasAny: hasCards || !!notionUrl || !!notionUnsafe,
  };
}

// AI-08: 러너가 응답마다 structured.timing.{total_ms,ai_ms,...}을 돌려주고 플랫폼이 그대로
// 저장하는데(app/jobs/handlers/chat_message.py), 화면 어디서도 안 읽어 조용히 버려졌다.
// total_ms(요청 전체 처리 시간 — 사용자가 실제로 기다린 시간에 가장 가깝다)를 우선하고,
// 없으면 ai_ms(Claude 호출만의 시간)로 대신한다.
export function responseTimeLabel(m) {
  const timing = m && m.structured && m.structured.timing;
  const ms = timing && typeof timing.total_ms === "number" ? timing.total_ms
    : (timing && typeof timing.ai_ms === "number" ? timing.ai_ms : null);
  if (ms == null || ms < 0) return null;
  return (ms / 1000).toFixed(1) + "초";
}

// ── 전송·오류 ───────────────────────────────────────────────────────────────

// 서버가 요구하는 client_message_id(8~64자, 멱등키). 보안 컨텍스트면 UUID, 아니면 난수 폴백.
export function newClientMessageId() {
  if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
  return "m-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12);
}

// 429 응답 본문엔 서버가 이미 계산한 대기 시간(retry_after_seconds)이 있다(app/core/errors.py
// RateLimitedError) — 그걸 버리고 '잠시 후'로만 뭉뚱그리지 않고 그대로 보여준다.
export function rateLimitNoticeText(e) {
  const secs = e && e.body && e.body.error && e.body.error.retry_after_seconds;
  return typeof secs === "number" && secs > 0
    ? secs + "초 후 다시 시도하세요, 요청이 너무 잦습니다."
    : "요청이 너무 잦습니다. 잠시 후 다시 시도하세요.";
}

export const NOTION_HOSTS = ["notion.so", "www.notion.so", "notion.com", "app.notion.com"];
export function safeNotion(url) {
  try { const u = new URL(url); return u.protocol === "https:" && (NOTION_HOSTS.some((h) => u.hostname === h) || u.hostname.endsWith(".notion.site")); }
  catch (e) { return false; }
}

export function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => false);
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return Promise.resolve(ok); }
  catch (e) { return Promise.resolve(false); }
}

// ── 마스코트 단계 매핑 ──────────────────────────────────────────────────────

/* 대화 단계 → 마스코트 포즈(ui/Mascot.jsx의 MascotPose mode).
 *
 * 마스코트는 지금까지 순수 장식이었다 — 어느 화면에서든 항상 'listening' 한 포즈로 굳어 있어,
 * 상태를 전한다고 주장하면서 아무 상태도 전하지 않았다. 여기서 앱이 **실제로 있는** 상태만
 * 포즈로 옮긴다. 앱이 아닌 상태를 연출하지 않는 것이 이 함수의 유일한 규칙이다.
 *
 * 우선순위(위가 강함) — 동시에 참일 수 있어 순서가 곧 의미다:
 *   error      실패한 메시지가 있거나 점검·속도제한으로 막혔다(지금 사용자가 갇혀 있는 상태)
 *   thinking   요청이 날아갔고 아직 답이 없다(전송 중 / 서버가 처리 중)
 *   responding 답이 방금 도착했다(마지막 메시지가 어시스턴트) — 잠깐 말하는 포즈
 *   success    방금 도착한 답이 티켓·프로젝트 카드를 들고 왔다(무언가 실제로 처리됐다)
 *   listening  컴포저에 포커스가 있다(물어볼 준비)
 *   idle       그 외
 *
 * 주의: 'responding'과 'success'는 마지막 어시스턴트 메시지가 **막 도착했을 때만**(justAnswered)
 * 준다. 스크롤만 하고 있는 옛 대화에서 영원히 말하는 포즈로 떠 있으면 그것도 거짓말이다.
 */
export function mascotMode(s) {
  const st = s || {};
  if (st.failed || st.blocked) return "error";
  if (st.sending || st.awaitingReply || st.busy) return "thinking";
  if (st.justAnswered) return st.hasResult ? "success" : "responding";
  if (st.composerFocused) return "listening";
  return "idle";
}

/* 마스코트 옆 한 줄 상태 문구 — 포즈(그림)만으로 상태를 전하지 않는다. 색·움직임을 못 보는
 * 사용자에게도 같은 정보가 글자로 간다(마스코트 사양서 접근성 규칙, WCAG 1.4.1). */
export const MASCOT_PHASE_TEXT = {
  error: "문제가 있어 멈춰 있습니다.",
  thinking: "요청을 처리하고 있습니다.",
  responding: "답변이 도착했습니다.",
  success: "요청한 결과를 찾았습니다.",
  listening: "무엇이든 물어보세요.",
  idle: "대화를 시작해 보세요.",
};
