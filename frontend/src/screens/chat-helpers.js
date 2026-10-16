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
 *
 * 답 안의 굵게 · 링크 · 티켓 키를 조각으로 나누는 일(`parseInline`)도 여기 있다 — 조각은 평범한 객체이고, 그것을 React 노드로
 * 바꾸는 일은 `chat/links.jsx::renderInline` 이 한다(D-569).
 */

import { trimUrlTail } from "./chat-text.js";

// ── 시각 표시 ───────────────────────────────────────────────────────────────

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
// 값의 근거: chat_message 잡은 max_attempts=3, 매 시도 모델 응답 상한 180초 + 백오프 → 정상적으로도
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

// 스레드 폴링 스케줄 — 연속 실패 횟수(fails)만 보고 다음 간격(ms)을 정한다.
// 실패가 쌓일수록 간격을 늘려(최대 5초) 죽은 서버를 촘촘히 두드리지 않는다.
// AI-11: 5회 연속 실패하면(약 20초, 백오프 포함) 예전엔 자동 재시도를 아예 멈췄다 — 배너의
// '새로고침' 버튼을 사람이 직접 눌러야만 재개됐다(서버가 그사이 돌아왔어도 화면은 영영
// 모른다). 완전히 멈추는 대신 POLL_RECOVERY_MS(20초)마다 조용히 한 번씩 다시 찔러본다 —
// 죽은 서버를 촘촘히 두드리지는 않으면서도, 살아나면 사람이 아무것도 안 눌러도 그 다음
// 확인에서 성공→pollFailRef 리셋→기본 간격으로 저절로 복귀한다.
// 이 계산을 함수로 뽑아 둔 이유는 하나다: 백오프와 회복 확인 지점은 이 화면의 핵심 방어선인데
// refetchInterval 콜백 안에 인라인으로 있으면 테스트가 가짜 타이머로 검증할 수가 없었다.
export const POLL_BASE_MS = 1500;
export const POLL_MAX_MS = 5000;
export const POLL_MAX_FAILURES = 5;
export const POLL_RECOVERY_MS = 20000;
export function pollDelayMs(fails) {
  const n = typeof fails === "number" && fails > 0 ? fails : 0;
  if (n >= POLL_MAX_FAILURES) return POLL_RECOVERY_MS;
  return n > 0 ? Math.min(POLL_BASE_MS * Math.pow(2, n), POLL_MAX_MS) : POLL_BASE_MS;
}

// ── 시작 예시·저장 키 ───────────────────────────────────────────────────────

/* 시작 예시 — 도우미가 **실제로 할 수 있는 일**만 적는다(D-535). 예전 목록은 티켓 만들기처럼 할 수 없는 일을 약속했다.
 * 누르면 입력 칸에 채운다(바로 보내지 않는다). 여섯 개를 지킨다 — 첫 화면 폭(46rem)에서 두 줄로 선다(WelcomeStatus.jsx).
 * 「내가 작성한 문서」와 「내가 담당하는 미완료 티켓」은 묻는 사람을 서버가 정하는 도구가 답한다(D-567). */
export const QUICK_PROMPTS = [
  "오늘 내가 할 일을 정리해 줘",
  "내가 담당하는 미완료 티켓을 알려 줘",
  "내가 처리할 승인 요청이 있는지 알려 줘",
  "내 프로젝트 진행 상황을 알려 줘",
  "휴가 신청 방법을 사내 문서에서 찾아 줘",
  "내가 작성한 문서가 몇 개야?",
];

export const CHAT_LAST_CONV_KEY = "chat.lastConversationId"; // 새로고침 후 열려 있던 대화 복원용(세션 한정)

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
// 「[제목](경로)」로 시작하는 줄은 머리글이 아니라 링크다 — 닫는 괄호 바로 뒤가 여는 괄호면 머리글로 읽지 않는다(A8).
// 머리글 글에는 여는 괄호도 없다 — 「[[포스코DX] 부가서비스 가이드](/knowledge/…)」의 앞 「[포스코DX」를 머리글로 읽던 결함.
export const RE_HEAD_BRACKET = /^\[([^[\]]{1,40})\](?!\()\s*(.*)$/;
export const RE_HEAD_BULLET = /^■\s*(.+)$/;
// 마크다운 머리글(「# 제목」 ~ 「### 제목」). 서버의 형식 지시는 쓰지 말라고 하지만, 모델이 쓰면 글자 그대로 두지 않고 머리글로 그린다(A8).
// 끝의 「 ##」 닫기는 떼고, 「#제목」처럼 띄어 쓰지 않은 줄과 「####」 이상은 머리글이 아니다.
export const RE_HEAD_HASH = /^#{1,4}\s+(.+?)(?:\s+#+)?\s*$/;
export const RE_ORDERED = /^(\d{1,3})\.\s+(.*)$/;
// 글머리는 「-」 「*」 「•」 셋이다(모델이 셋 다 쓴다). 「**굵게**」로 시작하는 줄은 「*」 뒤가 공백이 아니라 목록이 아니다.
export const RE_UNORDERED = /^[-*\u2022]\s+(.*)$/;
// 인용(「> 글」) · 구분선(「---」 「***」 「___」) · 표 한 줄(「| 가 | 나 |」)과 표 머리 구분선(「|---|:---:|」).
export const RE_QUOTE = /^>\s?(.*)$/;
export const RE_RULE = /^\s*([-*_])(?:\s*\1){2,}\s*$/;
export const RE_TABLE_ROW = /^\s*\|(.+)\|\s*$/;
export const RE_TABLE_SEP = /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*(:?-{3,}:?\s*)?\|?\s*$/;
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

function tableCells(line) {
  const m = RE_TABLE_ROW.exec(line);
  return m ? m[1].split("|").map((c) => c.trim()) : null;
}

export function classifyLine(line) {
  if (!line.trim()) return { kind: "blank" };
  let m;
  const sub = RE_SUBLINE.exec(line);
  const body = sub ? sub[1] : line;   // 들여쓴 줄이면 들여쓰기를 뺀 알맹이
  // 들여쓴 목록 줄은 윗 항목의 딸린 목록이다(한 단까지) — 예전에는 맨 위 목록으로 펴졌다.
  if ((m = RE_ORDERED.exec(body))) return sub ? { kind: "item", marker: m[1] + ".", text: m[2], nested: true } : { kind: "item", marker: m[1] + ".", text: m[2] };
  if ((m = RE_UNORDERED.exec(body))) return sub ? { kind: "item", marker: "", text: m[1], nested: true } : { kind: "item", marker: "", text: m[1] };
  if (sub) return { kind: "sub", text: sub[1], raw: line };
  if (RE_RULE.test(line)) return { kind: "rule" };
  if (RE_TABLE_SEP.test(line) && line.includes("-")) return { kind: "tablesep" };
  if (tableCells(line)) return { kind: "tablerow", cells: tableCells(line), raw: line };
  if ((m = RE_QUOTE.exec(line))) return { kind: "quote", text: m[1] };
  if ((m = RE_HEAD_HASH.exec(line))) return { kind: "head", text: m[1], note: "" };
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
    if (c.kind === "rule") { cur = null; blocks.push({ kind: "rule" }); return; }
    if (c.kind === "quote") {
      if (!cur || cur.kind !== "quote") { cur = { kind: "quote", lines: [] }; blocks.push(cur); }
      cur.lines.push(c.text);
      return;
    }
    if (c.kind === "tablerow" || c.kind === "tablesep") {
      if (c.kind === "tablesep") {
        // 머리 구분선은 바로 앞 줄 하나가 표의 머리일 때만 표를 연다. 아니면 평범한 글이다.
        if (cur && cur.kind === "table" && cur.rows.length === 1 && !cur.head) { cur.head = cur.rows.shift(); return; }
        c = { kind: "text", text: line };
      } else {
        if (!cur || cur.kind !== "table") { cur = { kind: "table", head: null, rows: [], raw: [] }; blocks.push(cur); }
        cur.rows.push(c.cells);
        cur.raw.push(c.raw);
        return;
      }
    }
    if (c.kind === "item") {
      if (c.nested && cur && cur.kind === "list" && cur.items.length) {
        const parent = cur.items[cur.items.length - 1];
        (parent.children || (parent.children = [])).push({ marker: c.marker, text: c.text });
        return;
      }
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
  // 「| … |」 줄은 머리 구분선이 있어야 표다 — 구분선 없는 줄은 원래 글자 그대로 문단이다(잘못된 표는 글로 떨어진다).
  return blocks.map((b) => {
    if (b.kind === "kv" && b.rows.length < 2) return { kind: "para", lines: b.rows.map((r) => r.raw) };
    if (b.kind === "table" && !b.head) return { kind: "para", lines: b.raw };
    if (b.kind === "table") return { kind: "table", head: b.head, rows: b.rows };
    return b;
  });
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면 이전엔 죽은 평문으로만 보였다. 지금은
// 전부 PlainUrl(복사 버튼)로 낸다. 쪼개는 일은 아래 `plainSegments` 가 하고, 조각을 그리는
// linkifyText · renderInline 은 JSX를 돌려주므로 chat/links.jsx에 남는다.
export const URL_RE = /(https?:\/\/[^\s]+)/g;

// ── 답 안의 굵게 · 링크 · 티켓 키 (A8, D-569) ──────────────────────────────────
//
// 모델은 마크다운을 쓴다(「**굵게**」, 「[제목](/knowledge/…)」). 예전에는 그 글자가 말풍선에 그대로 보였다. 이제 조각으로 나눠
// 굵게는 굵게, 링크는 링크로 그린다. 링크에는 규칙이 하나 있다 — **그 답의 서버 출처와 같은 경로일 때만** 링크가 된다. 모델이
// `/knowledge/<지어낸 id>` 를 써도, 앱 안 경로 모양이 맞아도, 출처에 없으면 원래 글자 그대로 남는다. 링크가 가는 곳은 언제나
// 서버가 만든 출처의 경로다(모델이 붙인 `?block=` 값이 달라도 출처의 경로로 간다). 바깥 주소는 어느 경우에도 앵커가 아니다.

/* 「참고한 자료」와 답 안 링크가 받는 앱 안 경로 — 서버가 만든 출처의 모양이다(D-535 · D-538).
 * 「/」로 끝나는 갈래는 그 아래 경로를, 아닌 갈래는 그 경로 자체나 질의(`?`)가 붙은 것만 받는다 — `/sprints-x` 를 `/sprint` 로 읽지 않는다. */
export const SOURCE_ROUTE_PREFIXES = ["/knowledge/", "/tickets/", "/projects/", "/my-approvals", "/board/", "/sprint"];

/* 화면 길잡이 경로 — 서버의 `ROUTE_GUIDE`(`app/ai/assistant/turn.py`)가 모델에게 알려 주는 **화면 자체**의 경로다. 문서 · 티켓 같은 자료를
 * 가리키지 않아 지어낼 것이 없으므로, 그 답의 출처에 없어도 정확히 이 경로면 링크가 된다(질의 · 하위 경로는 받지 않는다). 예전에는
 * 「[사내 문서](/knowledge)」가 글자 그대로 보였다(랩 2026-10-15). 서버 목록과 같은지 `chat-helpers.test.js` 가 대조한다. */
export const GUIDE_ROUTES = new Set(["/new-ticket", "/my-tickets", "/my-approvals", "/knowledge", "/projects", "/notifications", "/sprint"]);

function routeHasPrefix(route, prefix) {
  if (prefix.endsWith("/")) return route.startsWith(prefix);
  return route === prefix || route.startsWith(prefix + "?");
}

/** 앱 안 출처 경로면 그 값, 아니면 null. 바깥 주소 · `//` 로 시작하는 값 · 허용 밖 경로는 버린다. */
export function safeSourceRoute(route) {
  if (typeof route !== "string" || !route.startsWith("/") || route.startsWith("//")) return null;
  return SOURCE_ROUTE_PREFIXES.some((prefix) => routeHasPrefix(route, prefix)) ? route : null;
}

/** 답 안에서 링크로 그릴 수 있는 경로 — 출처 모양이거나 화면 길잡이 경로와 정확히 같을 때. 그리는 쪽(`links.jsx`)이 한 번 더 본다
 *  (예전에는 출처 모양만 다시 봐서 해석은 된 길잡이 링크 「[사내 문서](/knowledge)」가 그릴 때 글로 떨어졌다). */
export function safeAnswerRoute(route) {
  if (typeof route === "string" && GUIDE_ROUTES.has(route)) return route;
  return safeSourceRoute(route);
}

/* 결과 블록의 「전체 목록 열기」가 받는 화면 — 서버가 만든 상대 경로(`app/ai/assistant/blocks.py::list_route`)를 이 접두로
 * 다시 본다. 그 밖의 값은 단추를 세우지 않는다. */
export const LIST_ROUTE_PREFIXES = ["/knowledge", "/my-tickets", "/team-tickets", "/unassigned", "/projects",
  "/my-approvals", "/notifications", "/activity"];

/** 「전체 목록 열기」 경로면 그 값, 아니면 null. */
export function safeListRoute(route) {
  if (typeof route !== "string" || !route.startsWith("/") || route.startsWith("//") || route.includes("://")) return null;
  return LIST_ROUTE_PREFIXES.some((prefix) => route === prefix || route.startsWith(prefix + "?")) ? route : null;
}

/** 경로에서 `block` 질의만 뗀다(문서의 문단 자리). 같은 문서를 가리키는지 볼 때 쓴다. */
export function stripBlock(route) {
  if (typeof route !== "string") return "";
  const q = route.indexOf("?");
  if (q < 0) return route;
  const kept = route.slice(q + 1).split("&").filter((p) => p && p !== "block" && !p.startsWith("block="));
  return kept.length ? route.slice(0, q) + "?" + kept.join("&") : route.slice(0, q);
}

/* 마크다운 링크 「[글](경로)」의 옛 꼴 — 글에 대괄호가 없을 때만 맞았다. 지금은 아래 `findLink` 가 괄호의 짝을 세어 읽는다
 * (「[[포스코DX] 부가서비스 가이드](/knowledge/…)」처럼 제목에 대괄호가 든 링크가 글자 그대로 남던 결함). 시험이 옛 꼴을 잰다. */
export const INLINE_LINK_RE = /\[([^[\]\n]{1,200})\]\(([^()\s]{1,500})\)/;
const LINK_ROUTE = /^[^()\s]{1,500}$/;

/** 글에서 가장 앞의 마크다운 링크 — 글(라벨)의 대괄호는 짝이 맞으면 받는다. `{index, end, label, route}` 또는 null.
 *  라벨은 1 ~ 200자이고 줄을 넘지 않으며, 경로에는 괄호와 공백이 없다. */
export function findLink(text) {
  const src = String(text || "");
  for (let i = src.indexOf("["); i >= 0; i = src.indexOf("[", i + 1)) {
    let depth = 0;
    let close = -1;
    for (let j = i; j < src.length && j - i <= 201; j += 1) {
      const ch = src[j];
      if (ch === "\n") break;
      if (ch === "[") depth += 1;
      else if (ch === "]") {
        depth -= 1;
        if (depth === 0) { close = j; break; }
      }
    }
    if (close < 0 || src[close + 1] !== "(") continue;
    const end = src.indexOf(")", close + 2);
    if (end < 0) continue;
    const label = src.slice(i + 1, close);
    const route = src.slice(close + 2, end);
    if (!label || label.length > 200 || !LINK_ROUTE.test(route)) continue;
    return { index: i, end: end + 1, label, route };
  }
  return null;
}

/* 인라인 코드 「\x60글\x60」 — 한 줄 안, 비지 않은 글. 안의 글은 해석하지 않는다(굵게 · 링크 없음). */
export const INLINE_CODE_RE = /\x60([^\x60\n]{1,300})\x60/;
/* 굵게 「**글**」 — 안의 글은 비지 않고, 앞뒤가 공백이나 별표가 아니며, 줄을 넘지 않는다. 가장 짧게 맞춘다(뒤 묶음도 `??` 로
 * 게으르게 — 아니면 「**a** 와 **b**」가 굵게 하나로 묶인다). */
export const BOLD_RE = /\*\*([^\s*](?:[^\n]*?[^\s*])??)\*\*/;
const BOLD_MARKS = /\*\*([^*\n]+)\*\*/g;

// 티켓 키는 글자 · 숫자 · 하이픈뿐이다. 그 모양만 받아 정규식 메타문자가 들어올 자리를 없앤다.
const KEY_SHAPE = /^[A-Za-z0-9-]{3,40}$/;
const KEY_CHAR = /[A-Za-z0-9-]/;

function mergeText(segments) {
  const out = [];
  for (const seg of segments) {
    if (!seg) continue;
    if (seg.t === "text") {
      if (!seg.text) continue;
      const prev = out[out.length - 1];
      if (prev && prev.t === "text") prev.text += seg.text;
      else out.push({ t: "text", text: seg.text });
      continue;
    }
    out.push(seg);
  }
  return out;
}

/* 글 속 티켓 키 → 조각. **그 답의 출처에 있는 키만**이다(D-538). 키 앞뒤가 글자 · 숫자 · 하이픈이면 키가 아니다 —
   「ABC-1」이 「ABC-12」 안에서 링크가 되지 않는다. */
function keySegments(text, keyLinks) {
  if (!text) return [];
  if (!keyLinks || !keyLinks.size) return [{ t: "text", text }];
  const keys = [...keyLinks.keys()].filter((k) => KEY_SHAPE.test(k)).sort((a, b) => b.length - a.length);
  if (!keys.length) return [{ t: "text", text }];
  const re = new RegExp("(" + keys.join("|") + ")(?![A-Za-z0-9-])", "g");
  const out = [];
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > 0 && KEY_CHAR.test(text[m.index - 1])) {
      re.lastIndex = m.index + 1;
      continue;
    }
    if (m.index > last) out.push({ t: "text", text: text.slice(last, m.index) });
    out.push({ t: "key", key: m[1], route: keyLinks.get(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ t: "text", text: text.slice(last) });
  return out;
}

/** 굵게와 링크가 없는 글 → 조각(글 · 바깥 주소 · 티켓 키). 주소 끝의 문장 부호와 남는 닫는 괄호는 주소에서 떼어 뒤 글에 붙인다
 *  (팀 채팅 말풍선과 같은 `trimUrlTail`). 바깥 주소는 `url` 조각이고 화면은 복사 단추로 그린다 — 앵커가 아니다. */
export function plainSegments(text, { keyLinks } = {}) {
  const parts = String(text == null ? "" : text).split(URL_RE);
  const out = [];
  let carry = "";
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const raw = trimUrlTail(part);
      carry = part.slice(raw.length);
      out.push({ t: "url", url: raw });
    } else {
      out.push(...keySegments(carry + part, keyLinks));
      carry = "";
    }
  });
  return mergeText(out);
}

/* 출처 경로들 → 「block 을 뗀 경로 → 서버가 준 경로」. 안전하지 않은 경로는 처음부터 넣지 않는다. */
function routeTargets(routeLinks) {
  const out = new Map();
  if (!routeLinks || typeof routeLinks[Symbol.iterator] !== "function") return out;
  for (const route of routeLinks) {
    const safe = safeSourceRoute(route);
    if (!safe) continue;
    const key = stripBlock(safe);
    if (!out.has(key)) out.set(key, safe);
  }
  return out;
}

function inlineSpans(text, targets, keyLinks, depth) {
  const out = [];
  let rest = text;
  while (rest) {
    const found = findLink(rest);
    const link = found ? { index: found.index, length: found.end - found.index, found } : null;
    const boldM = depth === 0 ? BOLD_RE.exec(rest) : null;
    const bold = boldM ? { index: boldM.index, length: boldM[0].length, inner: boldM[1] } : null;
    const codeM = INLINE_CODE_RE.exec(rest);
    const code = codeM ? { index: codeM.index, length: codeM[0].length, text: codeM[1] } : null;
    const m = [code, link, bold].filter(Boolean).sort((a, b) => a.index - b.index)[0];
    if (!m) {
      out.push(...plainSegments(rest, { keyLinks }));
      break;
    }
    if (m.index > 0) out.push(...plainSegments(rest.slice(0, m.index), { keyLinks }));
    if (m === code) {
      out.push({ t: "code", text: code.text });
    } else if (m === link) {
      const { label, route } = link.found;
      const safe = safeSourceRoute(route);
      const target = (safe ? targets.get(stripBlock(safe)) : undefined) || (GUIDE_ROUTES.has(route) ? route : undefined);
      if (target) out.push({ t: "link", route: target, label: label.replace(BOLD_MARKS, "$1") });
      else out.push(...plainSegments(rest.slice(m.index, m.index + m.length), { keyLinks }));   // 출처에도 길잡이에도 없는 링크 — 원래 글자 그대로
    } else {
      out.push({ t: "bold", children: inlineSpans(bold.inner, targets, keyLinks, depth + 1) });
    }
    rest = rest.slice(m.index + m.length);
  }
  return mergeText(out);
}

/** 답 한 줄(또는 문단) → 조각 배열. 조각은 다섯 가지다:
 *    {t:"text", text} · {t:"bold", children:[조각]} · {t:"link", route, label} · {t:"key", key, route} · {t:"url", url}
 *  `routeLinks` 는 그 답의 출처 경로(Set 이나 배열 — `block` 이 붙어 있어도 된다), `keyLinks` 는 티켓 키 → 경로(Map)다.
 *  링크는 경로가 앱 안 출처 모양이고 `block` 을 뗀 값이 출처의 것과 같을 때만 서고, 가는 곳은 그 출처의 경로다. */
export function parseInline(text, { routeLinks, keyLinks } = {}) {
  return inlineSpans(String(text == null ? "" : text), routeTargets(routeLinks), keyLinks, 0);
}

// ── 도우미 답의 구조 (D-535) ─────────────────────────────────────────────────

/* 답 하나가 걸린 시간 — 서버가 잰 값(`structured.elapsed_ms`)만 보인다. 없으면 null 이다. */
export function elapsedLabel(structured) {
  const ms = structured && typeof structured.elapsed_ms === "number" ? structured.elapsed_ms : null;
  if (ms == null || ms < 0) return null;
  return (ms / 1000).toFixed(1) + "초";
}

/* 도우미가 「확인한 내용」 — 도구 이름(화면 낱말)과 검색어. 서버가 준 것만 옮긴다. */
export function checkedTools(structured) {
  const tools = structured && Array.isArray(structured.tools) ? structured.tools : [];
  return tools.filter((t) => t && typeof t.label === "string");
}

/* 「찾지 못함」 답에 같이 보일 검색어(중복 없이). */
export function searchedWords(structured) {
  const seen = new Set();
  return checkedTools(structured)
    .map((t) => (typeof t.query === "string" ? t.query.trim() : ""))
    .filter((q) => q && !seen.has(q) && seen.add(q));
}

/* 「확인한 내용」 한 줄 뒤에 붙는 수 — 서버가 센 전체 수(`total`, 권한 안의 정확한 수)와 이번에 받은 수(`count`)다(D-567).
 * 전체가 더 많으면 「25건 중 8건」, 같으면 「8건」, 전체 수를 모르면(null) 아무것도 붙이지 않는다 — 모르는 수를 지어내지 않는다. */
export function toolCountLabel(tool) {
  const total = tool && typeof tool.total === "number" && Number.isFinite(tool.total) ? tool.total : null;
  if (total == null) return null;
  const count = typeof tool.count === "number" && Number.isFinite(tool.count) ? tool.count : 0;
  if (total > count) return `전체 ${total}건 중 ${count}건`;
  if (total === count && total > 0) return `전체 ${total}건`;
  return null;
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
    ? "요청이 너무 잦습니다. " + secs + "초 후 다시 시도하세요."
    : "요청이 너무 잦습니다. 잠시 후 다시 시도하세요.";
}

/* 여기 허용 호스트 목록과 그것을 보는 게이트 함수가 있었다. 모델이 낸 문장 속 URL 중
 * notion.so 계열만 진짜 앵커로 열어 주고 나머지는 복사 버튼으로 내렸다.
 *
 * 그 특혜의 근거가 없어졌다. 문서와 티켓의 정본이 이 서버로 넘어왔으므로 그 주소가 여는
 * 것은 우리가 더 이상 쓰지 않는 낡은 사본이고, 그 한 호스트만 「믿을 수 있다」고 대우할
 * 이유가 없다. 지금은 **어떤 외부 주소도 앵커로 만들지 않는다**(links.jsx 의 `PlainUrl`
 * 복사 버튼). 열 수 있는 곳을 줄이는 방향이라 예전보다 안전하다.
 */

export function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => false);
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return Promise.resolve(ok); }
  catch (e) { return Promise.resolve(false); }
}

// AI-68: 대화 전체 복사 — 메시지 단위 복사(위 copyText)만 있고 대화 통째 내보내기가 없던
// 것 중 가장 값싼 조각(내보내기 파일 형식·공유 링크는 더 큰 설계가 필요해 범위 밖으로
// 남긴다, docs/BACKLOG.md AI-68 참고). 구조화 카드(티켓 등)는 본문에 이미 목록으로도
// 나온 텍스트라 굳이 다시 펼치지 않는다 — 순수 대화 텍스트만 담는다.
export function formatConversationText(items) {
  return (items || [])
    .filter((m) => m.content)
    .map((m) => (m.role === "user" ? "나" : "도우미") + ": " + m.content)
    .join("\n\n");
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
  idle: "질문을 입력해 대화를 시작하세요.",
};

/** 머리 클로비 옆 한 줄. 쓸 수 없으면 그 사실을, 대화가 오간 뒤 쉬는 때는 「이어서 물어보세요.」를, 나머지는 단계 문구를 말한다 —
 *  이미 답이 오간 대화 옆에 「대화를 시작해 보세요.」가 서면 어색했다(P17V 상태 캡처). */
export function mascotStatusText({ mode, unavailable = false, hasMessages = false } = {}) {
  if (unavailable) return "지금은 답할 수 없습니다.";
  if (mode === "idle" && hasMessages) return "이어서 물어보세요.";
  return MASCOT_PHASE_TEXT[mode] || MASCOT_PHASE_TEXT.idle;
}
