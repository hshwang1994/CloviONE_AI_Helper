import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { Badge, Button, Skeleton, ErrorState, useToast, useConfirm, statusKind } from "../ui/kit.jsx";

// 티켓 우선순위 어휘 — 상태(status)는 kit.jsx의 Badge/STATUS_TEXT로 한국어+톤을 받지만, 러너가 보내는
// 우선순위 원시값(영문 등급·숫자 등급 모두 실제로 관측됨)은 그 매핑에 없어 그대로 화면에 새고 있었다.
// kit.jsx는 이 화면이 소유하지 않으므로 전역 STATUS_TEXT/STATUS_KIND를 늘리는 대신, 여기서 값을
// 한국어로 먼저 번역해 Badge에 이미 번역된 문자열 + 명시적 kind를 넘긴다(Badge는 kind가 오면 그것을
// 그대로 쓰고, value는 STATUS_TEXT에 없으면 원문 그대로 통과시키므로 이미 번역된 한국어 문자열이 그대로 보인다).
// 우선순위 어휘는 lib/priority.js로 옮겼다 — 티켓 화면 두 곳이 이 두 함수를 쓰려고
// 이 파일(1,205줄) 전체를 import하는 바람에 채팅을 지연 로딩으로 뺄 수 없었다.
// 기존 호출부 호환을 위해 여기서도 그대로 내보낸다.
export { priorityKo, priorityKind } from "../lib/priority.js";
import { priorityKo, priorityKind } from "../lib/priority.js";

// 마감일 정규화 — 날짜만(YYYY-MM-DD)이면 그대로, ISO 타임스탬프면 KST로 표시(영문/ISO 누출 방지).
function fmtDue(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  return fmtDateTime(s);
}

// 대화 목록용 짧은 시각 라벨 — 오늘이면 시:분, 아니면 월.일(사이드바 폭이 좁아 전체 날짜는 넘친다).
function fmtShort(v) {
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
function fmtTime(v) {
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
function dayKeyKST(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  // en-CA는 YYYY-MM-DD 형태라 하루 경계 비교에 안전하다(로캘 의존 형식이 아님).
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}
function fmtDateSep(v) {
  if (v == null || v === "") return "";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric" }).format(d);
}

// 처리 중 메시지가 이 시간(밀리초)을 넘겨도 답이 없으면 '지연'으로 보고 무한 폴링을 멈춘다.
// 값의 근거: chat_message 잡은 max_attempts=3, 매 시도 n8n_timeout 180초 + 백오프 → 정상적으로도
// 최대 약 9분 15초 걸린다(바닐라 POLL_MAX_WAIT_MS와 동일). 짧게 잡으면 살아 있는 작업을 '지연'으로
// 오인해 폴링을 끊고, 진행 중인 답이 실패처럼 보인다.
const STALL_MS = 600000;
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

// 시작 예시(빈 화면에서 눌러 바로 대화 시작). 바닐라의 추천 프롬프트를 React로 복원.
const QUICK_PROMPTS = [
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

const CHAT_LAST_CONV_KEY = "chat.lastConversationId"; // 새로고침 후 열려 있던 대화 복원용(세션 한정)
const MAX_ATTACH_BYTES = 3 * 1024 * 1024; // 서버 이미지 상한과 맞춤(개당 3MB)
const MAX_TOTAL_ATTACH_BYTES = 6 * 1024 * 1024; // 서버 전체 상한과 맞춤(합계 6MB)
const MAX_ATTACH_COUNT = 3; // 서버가 받는 이미지 최대 장수
// 서버가 실제로 허용하는 이미지 타입(app/chat/attachments.py ALLOWED_MEDIA_TYPES)만 받는다.
// accept="image/*"로 열어두면 HEIC/GIF/SVG가 통과했다가 서버 400으로 메시지 전체가 실패한다.
const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
// base64 문자열의 디코드 바이트 수 추정(전체 첨부 용량을 서버 왕복 전에 검사하기 위함).
function b64Bytes(data) {
  const s = String(data || "");
  const pad = s.endsWith("==") ? 2 : s.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor(s.length * 3 / 4) - pad);
}
// 캔버스로 재인코딩해 스크린샷을 작게 만든다(긴 변 ≤1568px, JPEG q0.85). 원본을 그대로
// 올리면 폰 사진·스샷은 대부분 3MB를 넘겨 서버 전에 거부됐다 — 축소 후 크기로 검사한다.
function downscaleImage(file) {
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
const RE_HEAD_BRACKET = /^\[([^\]]{1,40})\]\s*(.*)$/;
const RE_HEAD_BULLET = /^■\s*(.+)$/;
const RE_ORDERED = /^(\d{1,3})\.\s+(.*)$/;
const RE_UNORDERED = /^-\s+(.*)$/;
const RE_SUBLINE = /^\s{2,}(\S.*)$/;
// 키는 짧다. 콜론이 든 평범한 문장을 표로 오해하지 않으려는 상한이다.
const RE_KV = /^([^:\s][^:]{0,15}?)\s*:\s*(.*)$/;

function kvOf(line) {
  const m = RE_KV.exec(line);
  if (!m) return null;
  if (/^\d+$/.test(m[1])) return null;         // "09:00" — 시각
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
  String(source || "").split(/\r\n?|\n/).forEach((line) => {
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
  // "키: 값"처럼 생긴 줄 하나는 표가 아니라 문장이다("내 티켓: 총 25건"). 표는 2줄 이상일 때만.
  return blocks.map((b) => (b.kind === "kv" && b.rows.length < 2)
    ? { kind: "para", lines: b.rows.map((r) => r.raw) }
    : b);
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면(구조화된 notion_url/ticket.url 필드가 아니라
// 그냥 문장 중간의 참조 링크) 이전엔 죽은 평문으로만 보였다, 구조화 필드와 같은 safeNotion 게이트로
// <a>(허용 도메인)/PlainUrl(그 외, 복사 폴백) 처리한다. textContent만 쓴다(innerHTML 아님, CLAUDE.md §2).
const URL_RE = /(https?:\/\/[^\s]+)/g;
function linkifyText(text, keyBase) {
  const s = String(text == null ? "" : text);
  const parts = s.split(URL_RE);
  if (parts.length === 1) return s;
  return parts.map((part, i) => (i % 2 === 1)
    ? (safeNotion(part)
        ? <a key={keyBase + "-u" + i} className="chat-card-link" href={part} target="_blank" rel="noreferrer noopener">{part}<span aria-hidden="true"> ↗</span><span className="sr-only"> (새 탭에서 열림)</span></a>
        : <PlainUrl key={keyBase + "-u" + i} url={part} />)
    : part);
}

/* 리치 텍스트, parseBlocks 결과를 msg-h/msg-list/msg-kv/msg-p로 렌더한다(textContent 전용). */
function RichText({ text }) {
  return (
    <>
      {parseBlocks(text).map((b, bi) => {
        if (b.kind === "head") {
          return <h4 className="msg-h" key={bi}>{b.text}{b.note ? <span className="msg-h-note"> {b.note}</span> : null}</h4>;
        }
        if (b.kind === "list") {
          return (
            <ul className="msg-list" role="list" key={bi}>
              {b.items.map((it, ii) => (
                <li className={it.marker ? "msg-li" : "msg-li dash"} key={ii}>
                  {it.marker ? <span className="msg-li-no">{it.marker}</span> : null}
                  <span className="msg-li-text">{linkifyText(it.text, "li" + bi + "-" + ii)}</span>
                  {it.subs.map((s, si) => <span className="msg-li-sub" key={si}>{linkifyText(s, "li" + bi + "-" + ii + "-s" + si)}</span>)}
                </li>
              ))}
            </ul>
          );
        }
        if (b.kind === "kv") {
          return (
            <dl className="msg-kv" key={bi}>
              {b.rows.map((r, ri) => (
                <div className="msg-kv-row" key={ri}>
                  <dt className="msg-kv-k">{r.key}</dt>
                  <dd className="msg-kv-v">{linkifyText(r.text, "kv" + bi + "-" + ri)}</dd>
                </div>
              ))}
            </dl>
          );
        }
        return <p className="msg-p" key={bi}>{linkifyText(b.lines.join("\n"), "p" + bi)}</p>;
      })}
    </>
  );
}

// 러너가 결과를 담는 여러 모양(배열/단일 객체/스칼라/undefined)을 카드용 '객체 배열'로 안전 변환.
// 배열이면 객체 원소만, 단일 객체면 1개짜리 배열, 그 외(스칼라·undefined)면 빈 배열.
function objArray(v) {
  if (Array.isArray(v)) return v.filter((x) => x && typeof x === "object");
  return v && typeof v === "object" ? [v] : [];
}

// 프로젝트 이름을 결정적 색조(0~7)로, 같은 프로젝트가 어디서나 같은 색 점을 갖게(바닐라 projectTone).
function projectTone(name) {
  const s = String(name || "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 8;
}

// 러너 티켓은 배열을 담는다(assignees: 이름 또는 {name} 객체, project_names 등). 어떤 모양이 와도
// 안전하게 사람 이름 문자열로 만든다. 스칼라·undefined도 안전.
function peopleText(value) {
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

/* AI 채팅(§6.5) React 전환 — 대화 목록 + 메시지 스레드 + 입력창. 사용자/AI 구분, 티켓 결과
 * 카드(파란 선 아님), 선택 버튼, 처리 중 표시, 자동 스크롤(읽는 중 멈춤)+새 메시지 점프,
 * 오류/재시도, 복사. 기존 채팅 API 사용(대화·메시지 CRUD, processing_status 폴링). */

// 서버가 요구하는 client_message_id(8~64자, 멱등키). 보안 컨텍스트면 UUID, 아니면 난수 폴백.
export function newClientMessageId() {
  if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
  return "m-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12);
}

// 429 응답 본문엔 서버가 이미 계산한 대기 시간(retry_after_seconds)이 있다(app/core/errors.py
// RateLimitedError) — 그걸 버리고 '잠시 후'로만 뭉뚱그리지 않고 그대로 보여준다.
function rateLimitNoticeText(e) {
  const secs = e && e.body && e.body.error && e.body.error.retry_after_seconds;
  return typeof secs === "number" && secs > 0
    ? secs + "초 후 다시 시도하세요, 요청이 너무 잦습니다."
    : "요청이 너무 잦습니다. 잠시 후 다시 시도하세요.";
}

const NOTION_HOSTS = ["notion.so", "www.notion.so", "notion.com", "app.notion.com"];
export function safeNotion(url) {
  try { const u = new URL(url); return u.protocol === "https:" && (NOTION_HOSTS.some((h) => u.hostname === h) || u.hostname.endsWith(".notion.site")); }
  catch (e) { return false; }
}
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => false);
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return Promise.resolve(ok); }
  catch (e) { return Promise.resolve(false); }
}

// allowlist에 걸려 링크로 열 수 없는 외부 URL, 죽은 텍스트처럼 보이지 않도록 클릭하면 주소를
// 복사하는 버튼으로 렌더한다(TicketCard, 관련 문서 폴백에서 공유).
function PlainUrl({ url }) {
  const toast = useToast();
  return (
    <button type="button" className="chat-card-plain" title="외부 링크는 열 수 없습니다, 눌러서 주소를 복사합니다."
      onClick={() => copyText(url).then((ok) => toast(ok ? "주소를 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}>
      {url}
    </button>
  );
}

function TicketCard({ t, index, onChoose, isTicket = true, sending }) {
  const [showAllProjects, setShowAllProjects] = useState(false);
  const url = t.url || t.notion_url || t.link;
  // 담당자, 정/부는 배열(이름 또는 {name})이 올 수 있다, peopleText로 어떤 모양이든 안전하게.
  // "미할당" 폴백은 진짜 티켓(단일 담당자 개념이 있는)에만 붙인다, 프로젝트/결과/일반 항목 카드는
  // 애초에 단일 담당자 개념이 없어 항상 '담당자: 미할당'을 보여주면 없는 데이터를 있는 것처럼 오도한다.
  const assigneeRaw = peopleText(t.assignees) || (typeof t.assignee === "string" ? t.assignee : "");
  const assignee = assigneeRaw || (isTicket ? "미할당" : "");
  const primary = peopleText(t.primary_names || t.primary);
  const secondary = peopleText(t.secondary_names || t.secondary);
  const projects = Array.isArray(t.project_names)
    ? t.project_names.filter(Boolean)
    : (typeof t.project === "string" && t.project ? [t.project] : []);
  const openTickets = typeof t.open_tickets === "number" ? t.open_tickets + "건" : "";
  const priority = typeof t.priority === "string" || typeof t.priority === "number" ? t.priority : "";
  const due = t.due_date || t.deadline;
  const title = t.title || t.name || t.subject || (isTicket ? "티켓" : "(제목 없음)");
  // 순번(N.)은 오직 '상세' 원탭이 실제로 동작하는(cardChoose가 살아 있는, 즉 마지막 어시스턴트
  // 메시지의) 카드에만 붙인다, 스크롤해 올라간 옛 카드까지 번호를 달면, 더는 안 눌리는 버튼을
  // 여전히 클릭 가능한 것처럼 훈련시킨 그 번호 라벨이 계속 남아 사용자를 오도한다.
  const prefix = typeof index === "number" && onChoose ? index + ". " : (t.number ? "#" + t.number + ", " : "");
  // 상태 톤을 카드에도 얹어(왼쪽 색 띠) 배지뿐 아니라 카드 단위로 상태가 한눈에 읽히게 한다.
  // 진짜 티켓(상태 개념이 있는)에만, 프로젝트/일반 항목 카드엔 상태 띠를 붙이지 않는다.
  const statusCls = isTicket && t.status ? " chat-card--" + statusKind(t.status) : "";
  return (
    <div className={"chat-card" + statusCls}>
      <div className="chat-card-title">{prefix}{title}</div>
      {t.status ? <div className="chat-card-row"><span className="k">상태</span><Badge value={t.status} /></div> : null}
      {assignee ? <div className="chat-card-row"><span className="k">담당자</span><span>{assignee}</span></div> : null}
      {primary ? <div className="chat-card-row"><span className="k">담당자(정)</span><span>{primary}</span></div> : null}
      {secondary ? <div className="chat-card-row"><span className="k">담당자(부)</span><span>{secondary}</span></div> : null}
      {openTickets ? <div className="chat-card-row"><span className="k">진행 중</span><span>{openTickets}</span></div> : null}
      {priority !== "" ? <div className="chat-card-row"><span className="k">우선순위</span><Badge value={priorityKo(priority)} kind={priorityKind(priority)} /></div> : null}
      {due ? <div className="chat-card-row"><span className="k">마감</span><span>{fmtDue(due)}</span></div> : null}
      {projects.length ? (
        <div className="chat-card-row"><span className="k">프로젝트</span>
          <span className="chat-chips">
            {(showAllProjects ? projects : projects.slice(0, 3)).map((p, i) => <span className="chat-chip" key={i}><span className={"project-dot tone-" + projectTone(p)} aria-hidden="true"></span>{String(p)}</span>)}
            {/* 예전엔 4개 이상이면 나머지가 아무 표시 없이 조용히 잘렸다 — choices의 '+N개 더 보기'와
                같은 패턴으로, 숨겨진 개수를 알리고 눌러서 펼칠 수 있게 한다. */}
            {!showAllProjects && projects.length > 3 ? (
              <button type="button" className="chat-chip chat-chip-more" onClick={() => setShowAllProjects(true)}>+{projects.length - 3}</button>
            ) : null}
          </span>
        </div>
      ) : null}
      {url || (typeof index === "number" && onChoose) ? (
        <div className="chat-card-actions">
          {url ? (safeNotion(url)
            ? <a className="chat-card-link" href={url} target="_blank" rel="noreferrer noopener">Notion에서 열기 <span aria-hidden="true">↗</span><span className="sr-only"> (새 탭에서 열림)</span></a>
            : <PlainUrl url={url} />) : null}
          {typeof index === "number" && onChoose ? (
            <button type="button" className="chat-card-btn" disabled={sending} onClick={() => onChoose(index + "번 상세 보여줘")}>상세</button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Message({ m, onChoose, onRetry, sending, retrying, isLast }) {
  const st = m.structured || {};
  // 러너가 결과를 담는 여러 모양을 모두 카드로 낸다(바닐라 renderStructured): 배열 tickets/projects/
  // items/results, 단일 객체 ticket/project. 어떤 모양(스칼라·배열·undefined)이 와도 objArray가 방어한다.
  // tickets 배열만 본문의 번호 목록과 짝이 맞는다(ticketPageStart가 그 배열 기준으로 시작 번호를 낸다) —
  // 단일 ticket 객체까지 같이 순번을 매기면 본문에 없는 'N번' 라벨이 생겨 '상세' 버튼이 엉뚱한 항목을 가리킨다.
  const ticketsArr = objArray(st.tickets);
  const singularTicket = objArray(st.ticket);
  const tickets = [...ticketsArr, ...singularTicket];
  const projects = [...objArray(st.projects), ...objArray(st.project)];
  const listItems = objArray(st.items);
  const results = objArray(st.results);
  // 카드가 하나도 없고 오직 Notion 링크만 있으면 '관련 문서' 링크 카드로 대체(allowlist 통과 시에만).
  const notionRaw = typeof st.notion_url === "string" ? st.notion_url : (typeof st.url === "string" ? st.url : "");
  const notionUrl = notionRaw && safeNotion(notionRaw) ? notionRaw : "";
  // allowlist에 걸린 문서 참조도 조용히 버리지 않는다 — 링크로는 못 열어도 카드 자체는 남겨서
  // "무언가 참조됐다"는 사실이 화면에서 사라지지 않게 한다(아래 렌더에서 PlainUrl로 대체).
  const notionUnsafe = notionRaw && !notionUrl ? notionRaw : "";
  const hasCards = tickets.length || projects.length || listItems.length || results.length;
  const choices = Array.isArray(st.choices) ? st.choices : [];
  const attachments = Array.isArray(st.attachments) ? st.attachments : [];
  const errorNotice = !!st.error_notice; // 오류 안내 말풍선엔 '복사'를 붙이지 않는다.
  const processing = m.processing_status === "pending" || m.processing_status === "processing";
  const failed = m.processing_status === "failed";
  const [copied, setCopied] = useState("");
  const [showAllChoices, setShowAllChoices] = useState(false);
  const isAssistant = m.role === "assistant";
  const rawContent = m.content || "";
  // 카드 번호는 반드시 원본 본문(다듬기 전)으로 대조해 매긴다.
  const startNo = isAssistant ? ticketPageStart(st, rawContent) : null;
  // 목록 응답은 티켓을 본문+카드에 두 번 낸다 — 본문의 항목 줄을 걷어내 카드가 상세를 지게 한다.
  // 예전엔 이 제거를 raw st.start_index로 게이트했는데, 카드 번호는 ticketPageStart(context.
  // last_result_start까지 물려받음)로 매겨져, start_index가 없고 context만 있는 응답에선 카드엔
  // 'N번 상세' 버튼이 붙는데 본문 항목은 그대로 남아 이중 표시가 됐다 — 번호와 제거를 같은
  // 출처(startNo)로 통일한다.
  const content = (isAssistant && tickets.length > 1 && startNo !== null && /^\s*\d+\.\s/m.test(rawContent))
    ? stripDuplicatedTicketLines(rawContent)
    : rawContent;
  const showChoices = isLast && isAssistant && !processing && choices.length > 0;
  // 카드의 '상세'도 선택 버튼과 같은 이유로 마지막 어시스턴트 메시지에서만 활성화한다, 스크롤해
  // 올라가 옛 목록의 '상세'를 누르면 'N번 상세'가 지금 맥락의 엉뚱한 티켓을 가리킨다(오작동).
  const cardChoose = isLast ? onChoose : undefined;
  return (
    <div className={"chat-msg chat-msg--" + m.role}>
      <div className="chat-bubble">
        {/* 화자 구분은 색/정렬(CSS)뿐이라 스크린리더엔 안 들린다, 텍스트로도 알린다. */}
        <span className="sr-only">{m.role === "user" ? "나: " : "도우미: "}</span>
        {/* 어시스턴트 답은 머리글, 목록, 키-값으로 구조화(textContent 전용). 사용자 글은 친 그대로. */}
        {content ? (isAssistant ? <RichText text={content} /> : <p className="chat-p">{content}</p>) : null}
        {attachments.length ? (
          <div className="chat-attach-row">
            {/* 서버는 이미지 바이트를 저장하지 않는다(app/chat/service.py) — 전송 후엔 파일명 칩만 남고
                실제 이미지는 다시 볼 수 없다. 전송 전 썸네일 미리보기와 달라지는 지점을 title로 알린다. */}
            {attachments.map((name, i) => (
              <span className="chat-attach-chip" key={i} title="전송 후 이미지 원본은 저장되지 않습니다, 파일 이름만 남습니다.">{typeof name === "string" ? name : (name && name.filename) || "첨부"}</span>
            ))}
          </div>
        ) : null}
        {/* title 툴팁은 hover 전용이라 모바일/터치에선 아예 안 뜬다, 전송 전 미리보기(chat-attach-caveat)와
            같은 이유로, 보낸 메시지에도 항상 보이는 캡션을 둔다. */}
        {attachments.length ? <p className="k-field-help chat-attach-caveat">전송 후 이미지 원본은 저장되지 않습니다, 파일 이름만 남습니다.</p> : null}
        {/* 순번(index)은 본문 목록과 짝이 맞는 tickets 배열분에만 붙인다, 그 뒤에 이어붙은 단일 ticket은
            번호 없이(비순번) 렌더해, 본문에 없는 'N번' 라벨과 어긋난 '상세' 클릭을 막는다. */}
        {tickets.length ? <div className="chat-cards">{tickets.map((t, i) => <TicketCard t={t} key={i} index={startNo !== null && i < ticketsArr.length ? startNo + i : undefined} onChoose={cardChoose} isTicket sending={sending} />)}</div> : null}
        {/* projects/listItems/results는 본문 번호 목록과 대응하는 개념이 없다, index를 안 주므로
            TicketCard의 '상세' 원탭 버튼도 뜨지 않는다(onChoose는 그 버튼에만 쓰이므로 함께 뺀다). */}
        {projects.length ? <div className="chat-cards">{projects.map((t, i) => <TicketCard t={t} key={i} isTicket={false} sending={sending} />)}</div> : null}
        {listItems.length ? <div className="chat-cards">{listItems.map((t, i) => <TicketCard t={t} key={i} isTicket={false} sending={sending} />)}</div> : null}
        {results.length ? <div className="chat-cards">{results.map((t, i) => <TicketCard t={t} key={i} isTicket={false} sending={sending} />)}</div> : null}
        {!hasCards && (notionUrl || notionUnsafe) ? (
          <div className="chat-cards">
            <div className="chat-card">
              <div className="chat-card-title">관련 문서</div>
              <div className="chat-card-actions">
                {notionUrl
                  ? <a className="chat-card-link" href={notionUrl} target="_blank" rel="noreferrer noopener">Notion에서 열기 <span aria-hidden="true">↗</span><span className="sr-only"> (새 탭에서 열림)</span></a>
                  : <PlainUrl url={notionUnsafe} />}
              </div>
            </div>
          </div>
        ) : null}
        {/* 이 자리에 있던 '어시스턴트 메시지 자체가 처리 중'일 때의 점 표시는 죽은 코드였다, 백엔드는
            어시스턴트 role의 Message를 항상 processing_status=done으로만 만든다(chat_message.py). 처리
            중 대기 표시는 아래(스레드 레벨) awaitingReply의 별도 타이핑 말풍선이 이미 전담한다. */}
        {/* assistant_rejected는 서버가 "다시 시도해도 똑같이 실패한다"고 이미 분류해 준 경우다
            (app/jobs/handlers/chat_message.py on_failure), assistant_timeout/assistant_error와 같은
            '눌러볼 만한' 링크로 보이면, 이미 안 될 걸 아는데도 계속 누르게 만든다. */}
        {failed ? (m.error_code === "assistant_rejected" ? (
          <div className="chat-fail">처리하지 못했습니다, 다시 시도해도 같은 결과가 나올 가능성이 높습니다. 질문을 다르게 표현해 새로 물어보세요.</div>
        ) : (
          <div className="chat-fail">처리하지 못했습니다. <button type="button" className="chat-linkbtn" disabled={retrying} onClick={() => { if (!retrying) onRetry(m); }}>{retrying ? "재시도 중…" : "다시 시도"}</button></div>
        )) : null}
      </div>
      {/* 원탭 선택은 가장 최근 어시스턴트 메시지에만. 옛 미리보기의 '등록해줘'가 살아 있으면
          스크롤해 올라가 눌렀을 때 지나간 맥락의 작업을 보낼 수 있다(오작동). */}
      {showChoices ? (
        <div className="chat-choices">
          {(showAllChoices ? choices : choices.slice(0, 6)).map((c, i) => c && c.send ? (
            <button type="button" className="chat-choice" key={i} disabled={sending} onClick={() => onChoose(c.send)}>{c.label || c.send}</button>
          ) : null)}
          {/* 7개 이상은 예전엔 조용히 잘려 나갔다 — '더 있다'는 사실만 알리고 실제로 꺼내 볼 방법은
              없었다. 이제 눌러서 나머지를 펼칠 수 있다. */}
          {!showAllChoices && choices.length > 6 ? (
            <button type="button" className="chat-linkbtn" onClick={() => setShowAllChoices(true)}>+{choices.length - 6}개 더 보기</button>
          ) : null}
        </div>
      ) : null}
      {m.role === "assistant" && m.content && !processing && !errorNotice ? (
        <>
          <button type="button" className="chat-copy" onClick={() => copyText(m.content).then((ok) => { setCopied(ok ? "복사됨" : "복사 실패"); setTimeout(() => setCopied(""), 1500); })}>
            {copied || "복사"}
          </button>
          {/* 복사 결과는 버튼 라벨만 바뀌어 스크린리더가 못 듣는다, 라이브 영역으로도 알린다. */}
          <span className="sr-only" role="status" aria-live="polite">{copied}</span>
        </>
      ) : null}
      {/* 시각 라벨은 말풍선, 액션(선택 버튼, 복사) 뭉치 뒤 맨 끝에 둔다, 예전엔 말풍선과 선택 버튼
          사이에 끼어 있어 복사 버튼이 메시지에서 멀찍이 떨어지고, 시각이 버블→액션 묶음을 갈랐다. */}
      {m.created_at ? <span className="k-field-help chat-msg-time">{fmtTime(m.created_at)}</span> : null}
    </div>
  );
}

/* 시작 예시 칩, 누르면 그 문장으로 바로 대화를 시작한다(빈 화면 막다른 길 방지). */
function QuickPrompts({ onPick, busy }) {
  return (
    <div className="chat-suggest" role="group" aria-label="시작 예시">
      {QUICK_PROMPTS.map((p, i) => (
        <button type="button" key={i} className="chat-suggest-chip" disabled={busy} onClick={() => onPick(p)}>{p}</button>
      ))}
    </div>
  );
}

/* 대화 목록 항목 — 호버 시 이름 변경(✎, 인라인)·삭제(🗑). 빈 '새 대화'가 쌓여도 정리 가능. */
function ConvItem({ c, active, onOpen, onRename, onDelete, onArchive }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(c.title || "");
  // 이전엔 mutation 결과와 무관하게 setEditing(false)를 먼저 불러 입력을 닫았다 — PATCH가 실패하면
  // (422·네트워크 오류·409 등) 입력창이 조용히 닫히고 사이드바가 옛 제목으로 되돌아가, 사용자가 방금
  // 친 내용이 사라져도 눈에 잘 안 띄는 토스트 하나로만 알렸다. onRename이 돌려주는 프라미스가 성공할
  // 때만 편집 모드를 닫고, 실패하면 입력을 그대로 열어 둬 재시도/복사할 수 있게 한다.
  function commit() {
    const t = val.trim();
    if (!t || t === (c.title || "")) { setEditing(false); return; }
    Promise.resolve(onRename(t)).then(() => setEditing(false)).catch(() => {});
  }
  if (editing) {
    return (
      <div className="chat-conv-row is-editing">
        <input className="chat-conv-input" value={val} autoFocus maxLength={200} aria-label={"이름 변경: " + (c.title || "새 대화")}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") { setEditing(false); setVal(c.title || ""); } }}
          onBlur={commit} />
      </div>
    );
  }
  return (
    <div className={"chat-conv-row" + (active ? " is-active" : "") + (c.archived ? " is-archived" : "")}>
      <button type="button" className="chat-conv-open" onClick={onOpen}>{c.title || "새 대화"}</button>
      {/* 보관됨은 호버 아이콘(↩)만으로는 쉼 상태에서 구분되지 않는다, 항상 보이는 태그로 표시한다. */}
      {c.archived ? <Badge value="archived" /> : null}
      {c.updated_at ? <span className="k-field-help chat-conv-time">{fmtShort(c.updated_at)}</span> : null}
      <span className="chat-conv-actions">
        {/* 목록에 같은 버튼이 대화 수만큼 있어서, '삭제'만으로는 스크린리더 사용자가 어느 대화의
            삭제 버튼인지 알 수 없다, 대화 제목을 라벨에 포함한다. */}
        <button type="button" className="chat-conv-act" aria-label={"이름 변경: " + (c.title || "새 대화")} title="이름 변경" onClick={() => { setVal(c.title || ""); setEditing(true); }}>✎</button>
        <button type="button" className="chat-conv-act" aria-label={(c.archived ? "보관 해제: " : "보관: ") + (c.title || "새 대화")} title={c.archived ? "보관 해제" : "보관"} onClick={() => onArchive(!c.archived)}>{c.archived ? "↩" : "🗄"}</button>
        <button type="button" className="chat-conv-act" aria-label={"대화 삭제: " + (c.title || "새 대화")} title="삭제" onClick={onDelete}>🗑</button>
      </span>
    </div>
  );
}

export function Chat() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [cid, setCid] = useState(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState([]); // 전송 대기 첨부(이미지)
  const [sideOpen, setSideOpen] = useState(false); // 모바일 대화목록 드로어
  const [convFilter, setConvFilter] = useState(""); // 대화 목록 제목 검색(클라이언트측 — 전체 목록은 이미 불러와 있음)
  const [showArchived, setShowArchived] = useState(false); // 보관된 대화 보기
  const [composingNew, setComposingNew] = useState(false); // '새 대화' 클릭 후 첫 메시지 전까지 실제 생성을 미룸
  const [stick, setStick] = useState(true);
  const [resumedAt, setResumedAt] = useState(0); // 스톨 복구 '새로고침'이 눌린 시각(폴링 재시작 기준선)
  const [isMobile, setIsMobile] = useState(false); // 모바일 폭이면 닫힌 대화 드로어를 inert 처리
  // 유지보수 모드가 켜져 있으면 서버가 전송/재시도를 503(maintenance_mode)으로 막는다(app/settings/gate.py) —
  // 이전엔 그 사실이 8초짜리 토스트 하나로만 스쳐 지나가 새 요청이 다시 시도해도 같은 이유로 계속
  // 막히는 원인을 사용자가 알 길이 없었다. 지속되는 배너로 남겨 컴포저를 잠근 이유를 계속 보여준다.
  const [maintenanceNotice, setMaintenanceNotice] = useState(null);
  // 429(속도 제한)도 유지보수 배너와 같은 이유로 지속 배너를 쓴다 — 예전엔 사라지는 토스트뿐이라
  // 계속 재시도하는 사용자는 컴포저가 왜 막혀 있는지 매번 놓쳤다. 서버가 계산해 준 대기 시간을
  // 그대로 보여준다(RateLimitedError.retry_after_seconds).
  const [rateLimitNotice, setRateLimitNotice] = useState(null);
  const bodyRef = useRef(null);
  const fileRef = useRef(null);
  const textareaRef = useRef(null);
  const asideRef = useRef(null); // 모바일 드로어 열릴 때 포커스를 옮길 대상(a11y)
  const sideToggleRef = useRef(null); // 드로어를 닫을 때 포커스를 되돌릴 트리거 버튼(a11y)
  const sendingRef = useRef(false); // doSend 재진입(이중 제출) 방지 — 생성→전송 창 포함
  const pickFilesRef = useRef(null); // 붙여넣기 리스너가 항상 최신 pickFiles를 부르도록
  const draftMsgIdRef = useRef(null); // 작성 중인 초안의 멱등키 — 전송 실패 후 재전송에 같은 키를 재사용
  const retryingRef = useRef(null); // 재시도 이중 클릭 방지 — retry.isPending은 다음 렌더까지 반영이 늦어(비동기), 그 사이 두 번 클릭하면 중복 요청이 나간다
  const cidRef = useRef(null); // pickFiles의 비동기 인코딩이 끝난 시점의 '지금' cid를 읽기 위한 라이브 참조
  useEffect(() => { cidRef.current = cid; }, [cid]);
  // 컴포저 textarea 자동 높이 — text가 바뀔 때마다(첫 글자·붙여넣기·초안 복구·전송 후 비움 포함)
  // 같은 기준으로 다시 계산한다. 예전엔 onChange 인라인 + 여러 rAF에 흩어져 있어, 빈 입력창(rows=1)과
  // 첫 입력 사이에 높이가 튀어 보였다. useLayoutEffect라 페인트 전에 확정돼 깜빡임이 없다.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);
  const pollFailRef = useRef(0); // 스레드 폴링 연속 실패 횟수(백오프·중단 판단용)
  // 이전 대화(A)에서 쌓인 연속 실패 횟수가 새로 연 대화(B)로 그대로 넘어오면, B의 첫 폴링이 단
  // 한 번만 실패해도(일시적 blip) 이미 5 이상인 카운터 때문에 refetchInterval이 즉시 자동 폴링을
  // 멈춰 버린다 — 대화를 바꿀 때마다 카운터를 새로 시작한다.
  useEffect(() => { pollFailRef.current = 0; }, [cid]);

  const convs = useQuery({
    queryKey: ["conversations", showArchived],
    queryFn: () => api("/api/conversations" + (showArchived ? "?include_archived=true" : "")),
    retry: false,
  });
  const thread = useQuery({
    queryKey: ["messages", cid],
    // 연속 폴링 실패 횟수를 추적한다(성공하면 0으로 리셋) — 아래 refetchInterval이 이 값으로
    // 백오프하거나 완전히 멈춘다. 워커/네트워크가 살아 있는 정상 실패(간헐적 5xx 등)와, 죽은
    // 서버에 무한히 재시도하는 것을 구분한다(바닐라 chat.js의 POLL_MAX_FAILURES와 같은 취지).
    queryFn: async () => {
      try {
        const res = await api("/api/conversations/" + cid + "/messages");
        pollFailRef.current = 0;
        return res;
      } catch (e) {
        pollFailRef.current += 1;
        throw e;
      }
    },
    enabled: !!cid,
    retry: false,
    refetchInterval: (q) => {
      const items = q.state.data && q.state.data.items;
      if (!Array.isArray(items) || !items.length) return false;
      const busy = items.some((m) => m.processing_status === "pending" || m.processing_status === "processing");
      // 답변이 폴링 사이에 도착해 "처리 중" 상태를 못 보고 지나칠 수 있다. 마지막이 사용자
      // 메시지면(아직 어시스턴트 답이 없음) 계속 폴링해 답변이 뜰 때까지 UI를 갱신한다.
      const last = items[items.length - 1];
      const awaitingReply = last && last.role === "user" && last.processing_status !== "failed";
      // 워커가 죽어 메시지가 'processing'에 얼어붙으면 영원히 폴링하던 문제 — 지연이 임계값을
      // 넘으면 자동 폴링을 멈춘다(사용자는 '새로고침'으로 수동 갱신).
      const inflight = busy ? [...items].reverse().find((m) => m.processing_status === "pending" || m.processing_status === "processing") : (awaitingReply ? last : null);
      if (inflight && msgAgeMs(inflight, resumedAt) > STALL_MS) return false;
      if (!(busy || awaitingReply)) return false;
      // 5회 연속 실패하면(약 20초, 백오프 포함) 자동 재시도를 멈춘다 — chat-poll-warn 배너의
      // '새로고침' 버튼으로 수동 재개할 수 있다. 실패가 쌓일수록 간격을 늘려(최대 5초) 죽은
      // 서버를 상대로 촘촘히 재시도하지 않는다.
      if (pollFailRef.current >= 5) return false;
      return pollFailRef.current > 0 ? Math.min(1500 * Math.pow(2, pollFailRef.current), 5000) : 1500;
    },
  });
  const items = (thread.data && thread.data.items) || [];
  // 스레드 전체를 aria-live로 감싸면 1.5초 폴링마다 대화가 통째로 다시 낭독된다.
  // 스레드에서 aria-live를 걷어내고, '처리 중' 같은 일시 상태만 작은 라이브 영역에서 알린다.
  const rawBusy = items.some((m) => m.processing_status === "pending" || m.processing_status === "processing");
  // 마지막이 사용자 메시지면(아직 어시스턴트 답 없음) 왼쪽에 어시스턴트 타이핑 말풍선을 띄운다.
  const lastMsg = items.length ? items[items.length - 1] : null;
  const rawAwaitingReply = !!lastMsg && lastMsg.role === "user" && lastMsg.processing_status !== "failed";
  // 처리 중 메시지가 임계 시간을 넘겼는지(폴링 중단·지연 안내에 사용).
  const inflightMsg = rawBusy ? [...items].reverse().find((m) => m.processing_status === "pending" || m.processing_status === "processing") : (rawAwaitingReply ? lastMsg : null);
  const stalled = !!inflightMsg && msgAgeMs(inflightMsg, resumedAt) > STALL_MS;
  // 지연이 STALL_MS를 넘기면 컴포저를 영구히 잠그지 않는다 — stalled 메시지는 busy/awaitingReply
  // 판정에서 제외해, '새로고침'을 누르지 않아도 사용자가 새 메시지를 작성·전송할 수 있게 한다
  // (이전엔 응답이 영영 오지 않으면 컴포저가 다시는 안 열리는 막다른 상태가 됐다).
  const busy = rawBusy && !stalled;
  const awaitingReply = rawAwaitingReply && !stalled;
  // 현재 대화 제목(모바일에선 드로어가 닫혀 어느 대화인지 모른다) — 목록 캐시 우선, 없으면 스레드 응답.
  const activeConv = ((convs.data && convs.data.items) || []).find((c) => c.id === cid);
  const activeTitle = (activeConv && activeConv.title) || (thread.data && thread.data.conversation && thread.data.conversation.title) || "새 대화";
  // 도착한 답변을 스크린리더에 한 번 알린다(스레드 자체엔 aria-live를 두지 않아 폴링마다 재낭독되지 않음).
  const answerAnnounce = (!busy && !awaitingReply && lastMsg && lastMsg.role === "assistant" && lastMsg.content && lastMsg.processing_status !== "failed") ? "답변이 도착했습니다." : "";

  const send = useMutation({
    // client_message_id는 서버가 필수로 요구한다(멱등·중복 방지). 8~64자. 첨부는 있을 때만.
    mutationFn: ({ id, content, clientMessageId, attachments }) => api("/api/conversations/" + id + "/messages", { method: "POST", body: { content, client_message_id: clientMessageId, attachments: attachments && attachments.length ? attachments : undefined } }),
    // 낙관적 에코 — 보낸 메시지를 서버 왕복 전에 즉시 스레드에 띄운다(빈 화면 체감 제거).
    // 진행 중 폴링이 낙관적 항목을 덮어쓰지 않도록 cancelQueries로 먼저 멈춘다.
    onMutate: async ({ id, content, clientMessageId, attachments }) => {
      await qc.cancelQueries({ queryKey: ["messages", id] });
      const prev = qc.getQueryData(["messages", id]);
      const echo = {
        id: "tmp-" + clientMessageId, role: "user",
        // 서버는 이미지만 있고 본문이 빈 전송을 "(이미지 첨부)" 플레이스홀더로 치환해 저장한다
        // (app/chat/service.py). 낙관적 에코가 빈 content를 그대로 쓰면 <Message>가 <p>를 아예 안 그려
        // 첨부 칩만 남았다가, 후속 무효화로 서버 값이 오는 순간 말풍선에 문구가 갑자기 나타나는
        // 눈에 띄는 깜빡임이 생긴다 — 처음부터 서버와 같은 문구로 에코한다.
        content: content || (attachments && attachments.length ? "(이미지 첨부)" : content),
        processing_status: "done",
        structured: attachments && attachments.length ? { attachments: attachments.map((a) => a.filename) } : undefined,
      };
      qc.setQueryData(["messages", id], (old) => ({ ...(old || {}), items: [...((old && old.items) || []), echo] }));
      return { prev, id };
    },
    onError: (_e, _vars, ctx) => { if (ctx) qc.setQueryData(["messages", ctx.id], ctx.prev); },
    // 새 대화의 첫 메시지는 cid 상태가 아직 반영 전이라 closure의 cid가 낡을 수 있다.
    // 변이 변수의 id로 무효화해 정확한 스레드를 갱신한다.
    onSuccess: (_d, vars) => { qc.invalidateQueries({ queryKey: ["messages", vars.id] }); qc.invalidateQueries({ queryKey: ["conversations"] }); },
  });
  const renameConv = useMutation({
    mutationFn: ({ id, title }) => api("/api/conversations/" + id, { method: "PATCH", body: { title } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
    onError: (e) => toast(e.message || "이름을 바꾸지 못했습니다.", "error"),
  });
  const archiveConv = useMutation({
    mutationFn: ({ id, archived }) => api("/api/conversations/" + id, { method: "PATCH", body: { archived } }),
    // 현재 목록 캐시에서 즉시 반영한다. 그렇지 않으면 방금 보관한 대화가 stale 캐시에 남아
    // 자동 선택 이펙트가 그것을 다시 열어(보이지 않는 대화에 입력하는) 막다른 길이 된다.
    onSuccess: (_d, vars) => {
      // 지금 열려 있던 대화가 보관되면 그 대화용 초안(글+첨부)도 함께 비운다 — 안 그러면 뒤이어
      // 자동 선택된 다른 대화(또는 빈 화면)에 이 대화의 초안이 그대로 남아 엉뚱한 곳에 전송될 수 있다.
      if (vars.archived && vars.id === cid) { setCid(null); clearDraft(); }
      qc.setQueryData(["conversations", showArchived], (old) => {
        if (!old || !Array.isArray(old.items)) return old;
        if (!showArchived && vars.archived) return { ...old, items: old.items.filter((c) => c.id !== vars.id) };
        return { ...old, items: old.items.map((c) => (c.id === vars.id ? { ...c, archived: vars.archived } : c)) };
      });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (e) => toast(e.message || "보관 상태를 바꾸지 못했습니다.", "error"),
  });
  const deleteConv = useMutation({
    mutationFn: (id) => api("/api/conversations/" + id, { method: "DELETE", body: {} }),
    // 삭제한 행을 캐시에서 곧바로 제거한다(단순 invalidate만 하면 refetch 전까지 stale 목록이
    // 남아 자동 선택 이펙트가 방금 삭제한 대화를 다시 열어 404 '대화를 찾을 수 없습니다'로 갇힌다).
    onSuccess: (_d, id) => {
      // 삭제한 대화가 지금 열려 있던 대화면 그 초안도 함께 비운다(보관과 동일한 이유 — 위 archiveConv 참고).
      if (id === cid) { setCid(null); clearDraft(); }
      qc.setQueryData(["conversations", showArchived], (old) =>
        old && Array.isArray(old.items) ? { ...old, items: old.items.filter((c) => c.id !== id) } : old);
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (e) => toast(e.message || "삭제하지 못했습니다.", "error"),
  });

  async function pickFiles(fileList) {
    // 인코딩(downscaleImage)은 비동기라 그 사이 사용자가 다른 대화로 전환할 수 있다 — 시작 시점의
    // cid를 남겨 두고, 끝날 때 지금 cid(cidRef, 라이브 참조)와 다르면 결과를 버린다. 안 그러면
    // A 대화에서 고른 이미지가 뒤늦게 B 대화의 컴포저에 나타나 엉뚱한 곳으로 전송될 수 있다.
    const startCid = cid;
    const files = Array.from(fileList || []);
    // 서버 상한(개당 3MB·합계 6MB·최대 3장·PNG/JPEG/WebP)을 왕복 전에 검사하되, 크기 검사는
    // 반드시 축소 뒤에 한다 — 폰 사진·스샷은 원본이 3MB를 쉽게 넘지만 축소하면 대부분 통과한다.
    const next = [...pending];   // 로컬 스냅숏(상태는 마지막에 한 번만 갱신 — 불변성 유지)
    let total = next.reduce((n, a) => n + b64Bytes(a.data), 0);
    // 거절 사유를 모아 한 번에 알린다 — 3장을 한꺼번에 넣으면 개별 토스트가 겹쳐 쌓이던 문제(바닐라처럼 통합).
    const badType = [], tooBig = [], failed = [];
    let hitCount = false, hitTotal = false;
    for (const f of files) {
      if (!ALLOWED_IMAGE_TYPES.includes(f.type)) { badType.push(f.name || "이미지"); continue; }
      if (next.length >= MAX_ATTACH_COUNT) { hitCount = true; break; }
      try {
        const enc = await downscaleImage(f);
        const bytes = b64Bytes(enc.data);
        if (bytes > MAX_ATTACH_BYTES) { tooBig.push(f.name || "이미지"); continue; }
        if (total + bytes > MAX_TOTAL_ATTACH_BYTES) { hitTotal = true; break; }
        next.push({ filename: (f.name || "capture.jpg").slice(0, 120), media_type: enc.media_type, data: enc.data });
        total += bytes;
      } catch (e) { failed.push(f.name || "이미지"); }
    }
    if (fileRef.current) fileRef.current.value = "";
    if (cidRef.current !== startCid) return;   // 인코딩 도중 다른 대화로 전환됨 — 이 결과는 버린다
    setPending(next);
    const reasons = [];
    if (badType.length) reasons.push("PNG, JPEG, WebP 이미지만 첨부할 수 있습니다(" + badType.join(", ") + ")");
    if (tooBig.length) reasons.push("축소 후에도 3MB를 넘어 제외(" + tooBig.join(", ") + ")");
    if (hitCount) reasons.push("이미지는 최대 " + MAX_ATTACH_COUNT + "장까지 첨부할 수 있습니다");
    if (hitTotal) reasons.push("첨부 이미지 전체 용량은 6MB를 넘을 수 없습니다");
    if (failed.length) reasons.push("처리하지 못한 이미지(" + failed.join(", ") + ")");
    if (reasons.length) toast(reasons.join(", "), "error");
  }
  pickFilesRef.current = pickFiles;
  // 재시도는 전용 엔드포인트로 같은 메시지를 다시 처리한다(새 메시지 생성·첨부 유실 방지).
  // conversationId는 클릭 시점의 cid를 변수로 함께 넘긴다 — onSuccess의 클로저 cid를 그대로 쓰면
  // (send 뮤테이션이 겪었던 것과 같은 문제) 재시도가 진행되는 사이 사용자가 다른 대화로 전환했을 때
  // 엉뚱한 대화의 캐시를 무효화한다(vars로 넘긴 값은 요청 시점 그대로 남는다 — send의 vars.id와 동일 패턴).
  const retry = useMutation({
    mutationFn: ({ messageId }) => api("/api/messages/" + messageId + "/retry", { method: "POST", body: {} }),
    onSuccess: (_d, vars) => { qc.invalidateQueries({ queryKey: ["messages", vars.conversationId] }); qc.invalidateQueries({ queryKey: ["conversations"] }); },
    onError: (e) => {
      // 세션 만료(401)면 다른 모든 401 경로(doSend·FormModal·DataScreen·Users)와 동일하게 로그인으로
      // 보낸다 — 예전엔 이 분기가 없어 '다시 시도' 중 세션이 끊기면 토스트만 뜨고 복구 경로가 없었다.
      if (e && e.status === 401) { window.location.href = "/login"; return; }
      if (e && e.status === 503 && e.body && e.body.error && e.body.error.code === "maintenance_mode") {
        setMaintenanceNotice((e.body.error && e.body.error.message) || "시스템 점검 중에는 새 요청이 차단됩니다. 잠시 후 다시 시도하세요.");
        return;
      }
      if (e && e.status === 429) { setRateLimitNotice(rateLimitNoticeText(e)); return; }
      toast(e.message || "다시 시도하지 못했습니다.", "error");
    },
    onSettled: () => { retryingRef.current = null; },
  });
  // 클릭 즉시(동기적으로) 같은 메시지의 재시도를 막는다 — retry.isPending은 다음 렌더까지 반영이
  // 늦어(비동기 React 상태), 그 창 안에 두 번 클릭하면 같은 메시지에 중복 재시도 요청이 나간다.
  function doRetry(m) {
    if (retryingRef.current === m.id) return;
    retryingRef.current = m.id;
    retry.mutate({ messageId: m.id, conversationId: cid });
  }
  const createConv = useMutation({
    mutationFn: () => api("/api/conversations", { method: "POST", body: {} }),
    onSuccess: (d) => { const id = d.conversation ? d.conversation.id : d.id; setCid(id); qc.invalidateQueries({ queryKey: ["conversations"] }); },
    // onError 토스트는 두지 않는다 — doSend의 catch가 이미 한 번 알린다(이중 토스트 방지).
  });

  // 새로고침 후에도 보던 대화를 이어서 연다 — 그냥 items[0](최신순 맨 위)을 열면, 최근에 손댄 적
  // 없는 옛 대화를 읽던 사용자가 새로고침 때마다 엉뚱한(가장 최근에 '바뀐') 대화로 튕겨나간다.
  // sessionStorage에 남겨 둔 id가 아직 목록에 있으면 그걸 열고, 없으면(삭제·다른 세션) items[0]로 폴백한다.
  useEffect(() => {
    if (!cid && !composingNew && convs.data && convs.data.items && convs.data.items.length) {
      let restoreId = null;
      try { restoreId = window.sessionStorage.getItem(CHAT_LAST_CONV_KEY); } catch (e) { /* 비보안 컨텍스트 등 */ }
      const found = restoreId && convs.data.items.find((c) => c.id === restoreId);
      setCid(found ? found.id : convs.data.items[0].id);
      // 대화 복원 직후 컴포저에 포커스를 둔다 — 키보드 사용자가 매번 직접 클릭해 들어가지 않아도 되게.
      textareaRef.current && textareaRef.current.focus();
    }
  }, [convs.data, cid, composingNew]);

  // 현재 열린 대화 id를 남겨 새로고침 후 복원에 쓴다(위 이펙트). 대화가 없으면(새 대화 작성 중 등) 지운다.
  useEffect(() => {
    try {
      if (cid) window.sessionStorage.setItem(CHAT_LAST_CONV_KEY, cid);
      else window.sessionStorage.removeItem(CHAT_LAST_CONV_KEY);
    } catch (e) { /* 비보안 컨텍스트 등 — 복원은 best-effort */ }
  }, [cid]);

  // 모바일 대화목록 드로어는 Esc로도 닫히게 한다(백드롭 탭 외 키보드 탈출구 제공).
  useEffect(() => {
    if (!sideOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") closeSideDrawer(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sideOpen]);

  // 모바일에서 드로어가 열리면 포커스를 그 안으로 옮긴다(열기 전엔 배경의 ☰ 버튼에 있었다) —
  // 데스크톱 닫힘 상태에만 inert를 걸던 것과 짝을 맞춰, 모바일 열림 상태에선 배경(chat-main-col)을
  // inert 처리하고, 닫을 때는 트리거 버튼으로 포커스를 되돌린다(closeSideDrawer).
  useEffect(() => {
    if (!isMobile || !sideOpen) return;
    const el = asideRef.current;
    const first = el && el.querySelector("button, [href], input, [tabindex]:not([tabindex='-1'])");
    if (first) first.focus();
  }, [isMobile, sideOpen]);
  function closeSideDrawer() {
    setSideOpen(false);
    if (isMobile) requestAnimationFrame(() => { sideToggleRef.current && sideToggleRef.current.focus(); });
  }

  // 모바일 폭 감지 — 닫힌 대화 드로어는 화면 밖으로 밀려 있을 뿐 DOM에 남아 있어 키보드/스크린리더가
  // 여전히 도달한다. 모바일이고 드로어가 닫혀 있으면 aside를 inert 처리한다.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const on = () => setIsMobile(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // 스샷 붙여넣기(Ctrl+V) — 클립보드의 이미지 파일을 컴포저로 바로 넣는다(가장 자연스러운 첨부).
  useEffect(() => {
    const onPaste = (e) => {
      if (!e.clipboardData || !e.clipboardData.files || !e.clipboardData.files.length) return;
      const imgs = [];
      for (let i = 0; i < e.clipboardData.files.length; i++) {
        const f = e.clipboardData.files[i];
        if (f.type && f.type.indexOf("image/") === 0) imgs.push(f);
      }
      if (imgs.length && pickFilesRef.current) { e.preventDefault(); pickFilesRef.current(imgs); }
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, []);

  useEffect(() => {
    if (stick && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [items, stick]);

  function onScroll() {
    const el = bodyRef.current;
    if (!el) return;
    setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  }

  // 대화를 바꾸거나 새 대화를 시작할 때 컴포저 초안을 비운다 — 초안(글+첨부)이 전역이라, 안 비우면
  // A 대화용으로 쓰던 초안이 B 대화(또는 새 대화)로 따라와 실수로 엉뚱한 곳에 전송될 수 있다.
  function clearDraft() {
    setText(""); setPending([]);
    draftMsgIdRef.current = null;   // 새 스레드의 첫 메시지는 새 멱등키를 쓰게 초기화
    setResumedAt(0);   // 스톨 복구 기준선도 새 스레드 기준으로 초기화(다른 대화의 낡은 기준선이 새지 않게)
    // .chat-body는 대화를 바꿔도 리마운트되지 않는 같은 DOM 노드다 — 이전 대화에서 스크롤을 올려
    // stick=false가 된 채로 남아 있으면, 다음에 여는 대화(짧든 길든)가 맨 위에 멈춰 보인다.
    // 대화를 바꿀 때마다 '맨 아래 고정'을 다시 기본값으로 되돌린다.
    setStick(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  // 시작 예시 칩은 즉시 전송하지 않고 컴포저에 채운다(USER_GUIDE.md가 문서화한 동작) — 사용자가
  // 문장을 고치거나 맥락을 더할 기회 없이 바로 새 대화로 전송돼 버리던 문제.
  function prefillFromPrompt(p) {
    setText(p);   // 높이 자동조정은 text 변화에 반응하는 useLayoutEffect가 담당한다.
    requestAnimationFrame(() => { textareaRef.current && textareaRef.current.focus(); });
  }

  async function doSend(content) {
    if (sendingRef.current) return;   // 이중 제출 방지(생성→전송 사이 창 포함)
    const value = (content != null ? content : text).trim();
    const fromComposer = content == null;
    const atts = fromComposer ? pending : [];
    // 어시스턴트가 아직 이번 턴을 처리 중이면(busy/awaitingReply) 컴포저에서 새 메시지를 못 보내게 막는다 —
    // 안 막으면 겹치는 러너 작업이 생겨 맥락이 뒤섞인 답이 나온다. 선택 버튼/카드 '상세'(fromComposer=false)는
    // 그 턴에 한정된 원탭이라 sending(=send.isPending) 하나로 충분히 막혀 있어 그대로 둔다.
    if ((!value && !atts.length) || send.isPending) return;
    // 컴포저 placeholder는 'Enter 전송'을 약속하지만, 답변이 오는 동안 textarea 자체는 계속
    // 활성 상태라 키보드 사용자가 Send 버튼의 disabled 상태를 못 보고 조용히 씹히는 Enter를
    // 칠 수 있었다 — 여기서 이유를 한 줄로 알린다.
    // 이 가드는 컴포저뿐 아니라 선택 버튼·카드 '상세'(fromComposer=false)에도 적용한다 — 안 그러면
    // 재시도로 다른 메시지가 'pending'인 동안에도 선택/카드 클릭이 겹치는 러너 작업을 만들어 낼 수 있다.
    if (busy || awaitingReply) { toast("답변을 기다리는 중입니다."); return; }
    if (fromComposer && maintenanceNotice) { toast("시스템 점검 중에는 새 요청을 보낼 수 없습니다."); return; }
    if (fromComposer && rateLimitNotice) { toast("요청이 너무 잦습니다. 잠시 후 다시 시도하세요."); return; }
    sendingRef.current = true;
    if (fromComposer) {
      setText(""); setPending([]);   // 낙관적 비우기 — 실패하면 복구
      // 자동 확장된 textarea 높이를 되돌린다(안 하면 전송 후 빈 입력창이 계속 커진 채 남는다).
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }
    setStick(true);
    // 컴포저 초안은 초안당 하나의 멱등키를 쓴다 — 응답이 유실돼 재전송할 때 같은 키를 재사용해야
    // 서버 dedup(client_message_id)이 동작해 이중 기록/이중 쓰기(WRITE)를 막는다. 성공해야 새 키를 발급.
    const clientMessageId = fromComposer
      ? (draftMsgIdRef.current || (draftMsgIdRef.current = newClientMessageId()))
      : newClientMessageId();
    let createdId = null;   // 이번 전송을 위해 방금 생성한 대화 id(첫 전송 실패 시 정리 대상)
    try {
      let id = cid;
      if (!id) { const d = await createConv.mutateAsync(); id = d.conversation ? d.conversation.id : d.id; createdId = id; }
      setComposingNew(false);
      await send.mutateAsync({ id, content: value, clientMessageId, attachments: atts });
      if (fromComposer) draftMsgIdRef.current = null;   // 확정 성공 후에만 초안 키를 비운다
      // 새 대화가 방금 생성된 경우, 컴포저에 포커스를 되돌려 곧바로 이어 입력할 수 있게 한다.
      if (fromComposer) textareaRef.current && textareaRef.current.focus();
    } catch (e) {
      // 세션 만료(401)는 다른 화면(ErrorState)과 같은 로그인 복구 동작으로 통일한다 — 8초 뒤
      // 사라지는 토스트 하나에만 기대면, 대화 중 세션이 끊긴 사용자는 무엇이 잘못됐는지 놓치기 쉽다.
      if (e && e.status === 401) { window.location.href = "/login"; return; }
      // 첫 전송(대화를 방금 만든 경우)이 실패하면 메시지 0개짜리 '새 대화'가 목록에 남아 어지럽힌다 —
      // 조용히 정리한다(초안은 아래에서 컴포저에 복구하므로 같은 내용으로 곧바로 다시 보낼 수 있다).
      // deleteConv 뮤테이션은 쓰지 않는다 — 그 onSuccess가 clearDraft()로 방금 복구한 초안을 지운다.
      if (createdId) {
        const orphan = createdId;
        setCid(null);
        qc.setQueryData(["conversations", showArchived], (old) =>
          old && Array.isArray(old.items) ? { ...old, items: old.items.filter((c) => c.id !== orphan) } : old);
        api("/api/conversations/" + orphan, { method: "DELETE", body: {} }).then(
          () => qc.invalidateQueries({ queryKey: ["conversations"] }), () => {});
      }
      if (fromComposer) {
        setText(value); setPending(atts);   // 입력, 첨부 복구(유실 방지), 높이는 useLayoutEffect가 다시 계산.
      }
      // 유지보수 모드 차단(503)은 사라지는 토스트 대신 지속 배너로 알리고 컴포저를 잠근다, 아래
      // 배너의 '다시 시도' 버튼을 눌러야만 다시 입력할 수 있다(다음 요청도 여전히 막혀 있으면 배너가
      // 다시 뜬다).
      if (e && e.status === 503 && e.body && e.body.error && e.body.error.code === "maintenance_mode") {
        setMaintenanceNotice((e.body.error && e.body.error.message) || "시스템 점검 중에는 새 요청이 차단됩니다. 잠시 후 다시 시도하세요.");
      } else if (e && e.status === 429) {
        setRateLimitNotice(rateLimitNoticeText(e));
      } else {
        toast(e.message || "메시지를 보내지 못했습니다.", "error");
      }
    } finally {
      sendingRef.current = false;
    }
  }

  return (
    <div className={"chat-layout" + (sideOpen ? " side-open" : "")}>
      <aside className="chat-side" id="chat-conv-drawer" ref={asideRef} {...(!sideOpen ? { inert: "", "aria-hidden": "true" } : {})}>
        <Button variant="primary" onClick={() => { clearDraft(); setComposingNew(true); setCid(null); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}>+ 새 대화</Button>
        <label className="k-check"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> 보관된 대화 보기</label>
        {/* 대화가 쌓일수록 스크롤만으로 찾기 어렵다 — 이미 불러온 전체 목록을 제목 부분일치로
            클라이언트에서만 좁힌다(백엔드 변경 불필요). */}
        {((convs.data && convs.data.items) || []).length > 0 ? (
          <input type="search" className="c-search chat-conv-filter" placeholder="대화 제목 검색"
            value={convFilter} onChange={(e) => setConvFilter(e.target.value)} aria-label="대화 목록 검색" />
        ) : null}
        <div className="chat-conv-list">
          {convs.isLoading ? <Skeleton lines={4} />
            : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
            : !((convs.data && convs.data.items) || []).length
              ? <div className="k-field-help">{showArchived ? "보관된 대화가 없습니다." : "아직 대화가 없습니다, '+ 새 대화'로 시작하세요."}</div>
              : (() => {
                  const q = convFilter.trim().toLowerCase();
                  const filtered = q ? convs.data.items.filter((c) => (c.title || "새 대화").toLowerCase().includes(q)) : convs.data.items;
                  return filtered.length ? filtered.map((c) => (
                    <ConvItem key={c.id} c={c} active={c.id === cid} onOpen={() => { if (c.id !== cid) clearDraft(); setCid(c.id); setComposingNew(false); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}
                      onRename={(title) => renameConv.mutateAsync({ id: c.id, title })}
                      onArchive={(archived) => archiveConv.mutate({ id: c.id, archived })}
                      onDelete={async () => { if (await confirm("이 대화를 삭제할까요? 되돌릴 수 없습니다.", { danger: true })) deleteConv.mutate(c.id); }} />
                  )) : <div className="k-field-help">검색 결과가 없습니다.</div>;
                })()}
        </div>
      </aside>
      {sideOpen ? <div className="chat-side-backdrop" onClick={closeSideDrawer} aria-hidden="true" /> : null}
      <section className="chat-main-col" {...(sideOpen ? { inert: "", "aria-hidden": "true" } : {})}>
        <div className="chat-topbar">
          {/* 관리자 셸의 c-hamburger(App.jsx)와 같은 방식으로 aria-expanded/aria-controls를 실제
              토글 상태에 맞춘다, 이전엔 '열기' 전용 편도 트리거라 열린 뒤에도 라벨, 상태가 안 바뀌었다. */}
          <button type="button" ref={sideToggleRef} className="chat-side-toggle" aria-controls="chat-conv-drawer" aria-expanded={sideOpen}
            aria-label={sideOpen ? "대화 목록 닫기" : "대화 목록 열기"}
            onClick={() => (sideOpen ? closeSideDrawer() : setSideOpen(true))}>{sideOpen ? "✕ 닫기" : "☰ 대화 목록"}</button>
          {/* cid가 없어도(첫 방문, 새 대화 시작 직후) 빈 막대 대신 화면 이름을 보여준다. */}
          <h1 className="chat-title">{cid ? activeTitle : "채팅"}</h1>
        </div>
        <div className="sr-only" role="status" aria-live="polite">{busy ? "답변을 처리하고 있습니다." : ""}</div>
        <div className="sr-only" role="status" aria-live="polite">{answerAnnounce}</div>
        <div className="chat-body" ref={bodyRef} onScroll={onScroll}>
          {!cid ? (
            // 대화 목록 조회가 실패/로딩 중이면 환영 화면 대신 그 상태를 보여준다, 모바일에선 사이드바가
            // 닫힌 드로어 안에 있어 그 안의 오류/재시도가 안 보이므로, 여기(본문)에도 같은 신호가 있어야 한다.
            convs.isLoading ? <div className="chat-loading"><Skeleton lines={3} /></div>
            : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
            : (
              // 아이콘 글리프는 앱의 다른 곳(kit.jsx EmptyState)과 시각적 통일감을 주려는 장식일
              // 뿐이라 aria-hidden, 스크린리더는 뒤이은 제목 텍스트만 읽는다.
              <div className="chat-welcome"><h2>무엇을 도와드릴까요?</h2>
                <p>대화 한 줄이면 티켓 생성, 조회, 요약까지 처리합니다. 아래 예시를 눌러 바로 시작해 보세요.</p>
                <QuickPrompts onPick={prefillFromPrompt} busy={send.isPending || createConv.isPending} /></div>
            )
          ) : thread.isLoading ? <div className="chat-loading"><Skeleton lines={3} /></div>
            : thread.isError && !items.length ? <ErrorState error={thread.error} onRetry={() => thread.refetch()} />
            : items.length === 0 ? <div className="chat-welcome"><h2>새 대화</h2>
                <p>아래에 메시지를 입력하거나, 예시를 눌러 시작하세요.</p>
                <QuickPrompts onPick={prefillFromPrompt} busy={send.isPending || createConv.isPending} /></div>
            : (<>
                {/* 폴링이 일시 실패해도 읽던 메시지를 지우지 않는다, 작은 안내만 띄우고 스레드는 유지. */}
                {thread.isError ? (
                  <div className="chat-poll-warn" role="status">연결이 잠시 끊겼습니다. <button type="button" className="chat-linkbtn" onClick={() => thread.refetch()}>새로고침</button></div>
                ) : null}
                {/* retrying은 이 메시지가 지금 재시도 중인지만 본다(retry.variables) — 뮤테이션의
                    전역 isPending을 그대로 쓰면 스레드의 다른 실패 메시지의 '다시 시도'까지 함께
                    잠겨(과잉 제한), 서로 무관한 재시도를 막는 문제가 있었다. */}
                {/* sending은 이 화면의 선택 버튼·카드 '상세'를 눌러도 되는지를 결정한다 — 전송/대화
                    생성 중뿐 아니라, 스레드 어딘가가 busy/awaitingReply(다른 메시지가 재시도 등으로
                    아직 처리 중)이거나 재시도가 진행 중일 때도 함께 잠가 겹치는 러너 작업을 막는다. */}
                {items.map((m, i) => {
                  // 앞 메시지와 KST 기준 날짜가 다르면(또는 첫 메시지면) 그 앞에 날짜 구분선을 끼운다.
                  const prev = i > 0 ? items[i - 1] : null;
                  const dk = dayKeyKST(m.created_at);
                  const showSep = !!dk && (!prev || dayKeyKST(prev.created_at) !== dk);
                  return (
                    <React.Fragment key={m.id}>
                      {showSep ? <div className="chat-date-sep" role="separator" aria-label={fmtDateSep(m.created_at)}><span>{fmtDateSep(m.created_at)}</span></div> : null}
                      <Message m={m} onChoose={doSend} onRetry={doRetry} sending={send.isPending || createConv.isPending || busy || awaitingReply || !!retryingRef.current} retrying={retryingRef.current === m.id} isLast={i === items.length - 1} />
                    </React.Fragment>
                  );
                })}
                {/* 답변 대기 중이면 왼쪽에 어시스턴트 타이핑 말풍선(사용자 말풍선 안이 아니라). awaitingReply
                    자체가 이미 stalled를 제외하므로(위) 별도 조건이 필요 없다. */}
                {awaitingReply ? (
                  <div className="chat-msg chat-msg--assistant">
                    <div className="chat-bubble">
                      <span className="sr-only">도우미: 답변을 작성하고 있습니다.</span>
                      <span className="chat-thinking"><span></span><span></span><span></span></span>
                    </div>
                  </div>
                ) : null}
                {/* 응답이 임계 시간을 넘겨 지연되면 무한 대기 대신 수동 새로고침을 제공한다. 새로고침은 단순
                    재조회가 아니라 폴링 재시작 기준선(resumedAt)도 지금 시각으로 옮긴다, 안 그러면 created_at이
                    그대로라 재조회 직후 다시 즉시 stalled로 재계산돼 자동 폴링이 재개되지 않는 막다른 길이 된다. */}
                {stalled ? (
                  <div className="chat-msg chat-msg--assistant">
                    <div className="chat-bubble">
                      <div className="chat-fail">응답이 지연되고 있습니다. <button type="button" className="chat-linkbtn" onClick={() => { setResumedAt(Date.now()); thread.refetch(); }}>새로고침</button></div>
                    </div>
                  </div>
                ) : null}
              </>)}
          {/* .chat-body(스크롤 컨테이너) 안에 두고 CSS로 그 안에서만 절대 위치를 잡는다, 예전엔
              .chat-main-col 기준(컴포저 바로 위 고정 거리)이라, 여러 줄 초안+첨부 미리보기+글자 수로
              컴포저가 커지면 이 버튼이 컴포저 안/뒤로 파묻혔다. 스크롤 영역 자체에 붙이면 컴포저
              높이와 무관하게 항상 그 위에 뜬다. */}
          {!stick ? <button type="button" className="jump-latest" onClick={() => { setStick(true); }}>맨 아래로 ↓</button> : null}
        </div>
        {/* 초광폭(4K)에서 상단 topbar는 전폭 구분선인데 컴포저만 1000px 폭 카드로 떠 좌우에 페이지
            배경 여백이 생겨 미완성처럼 보였다, 전폭 배경 띠(band, 카드색+상단 테두리)로 감싸고, 안쪽 내용만 1000px로 가운데 정렬해 topbar가 콘텐츠를 감싸는 방식과 맞춘다. */}
        <div className="chat-composer-band">
        {/* 첨부 미리보기, 글자 수, 입력창을 본문과 같은 폭으로 가운데 정렬한다(초광폭에서 어긋나던 문제). */}
        <div className="chat-composer-wrap">
        {pending.length ? (
          <>
            <div className="chat-attach-row">
              {pending.map((a, i) => (
                <span className="chat-attach-chip" key={i}>
                  {/* 보낼 이미지를 텍스트 칩이 아니라 실제 썸네일로 확인시킨다(로컬 data URL). */}
                  <img src={"data:" + (a.media_type || "image/png") + ";base64," + a.data} alt="" height={28} />
                  {a.filename}
                  <button type="button" className="chat-attach-x" aria-label="첨부 제거" onClick={() => setPending((p) => p.filter((_, j) => j !== i))}>✕</button>
                </span>
              ))}
            </div>
            {/* hover-only title 툴팁은 모바일/터치에서 아예 안 보인다, 전송 전에 눈에 보이는 문장으로도 알린다. */}
            <p className="k-field-help chat-attach-caveat">전송 후에는 이미지 원본이 저장되지 않습니다, 파일 이름만 남습니다.</p>
          </>
        ) : null}
        {/* 글자 수는 입력이 있으면 늘 옅게 보여준다 — 상한이 갑자기 닥치지 않게(바닐라도 항상 표시).
            textarea의 maxLength={5000}은 UTF-16 코드 유닛 기준이라, 서로게이트 쌍(이모지 등)이 섞이면
            Array.from(코드 포인트) 기준 길이는 실제 입력 가능 한도보다 작게 세어져 두 숫자가 어긋난다 —
            text.length(코드 유닛)로 맞춘다. */}
        {text.length > 0 ? <div className="k-field-help chat-counter">{text.length}/5000</div> : null}
        {/* 유지보수 모드 차단 안내, chat-poll-warn과 같은 지속 배너 패턴(사라지는 토스트 하나에만
            기대지 않는다). '다시 시도'를 눌러야 컴포저 잠금이 풀린다(§ 위 doSend 주석). */}
        {maintenanceNotice ? (
          <div className="chat-poll-warn" role="status">{maintenanceNotice} <button type="button" className="chat-linkbtn" onClick={() => setMaintenanceNotice(null)}>다시 시도</button></div>
        ) : null}
        {rateLimitNotice ? (
          <div className="chat-poll-warn" role="status">{rateLimitNotice} <button type="button" className="chat-linkbtn" onClick={() => setRateLimitNotice(null)}>닫기</button></div>
        ) : null}
        {/* 답변을 기다리는 동안 textarea는 계속 활성이라(placeholder는 'Enter 전송'을 약속) 입력이
            막혔다는 신호가 없어, Enter를 쳐도 사라지는 토스트로만 알렸다, 유지보수, 속도제한 배너처럼
            지속되는 수동 힌트를 컴포저 위에 둔다. */}
        {(busy || awaitingReply) && !maintenanceNotice && !rateLimitNotice ? (
          <p className="k-field-help chat-await-hint" role="status">답변을 기다리는 중입니다, 답변이 도착하면 다시 입력할 수 있습니다.</p>
        ) : null}
        <footer className="chat-composer">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple className="chat-file-input" aria-hidden="true" tabIndex={-1} onChange={(e) => pickFiles(e.target.files)} />
          {/* Send와 같은 '어시스턴트가 아직 작업 중' 가드를 쓴다, 이전엔 이 버튼만 그 상태에서도
              눌려, 첨부를 골라도 어차피 이번 턴엔 보낼 수 없는데 활성으로 보였다. */}
          <button type="button" className="chat-attach-btn" aria-label="이미지 첨부" title="이미지 첨부(PNG, JPEG, WebP)"
            disabled={send.isPending || createConv.isPending || busy || awaitingReply || !!maintenanceNotice || !!rateLimitNotice}
            onClick={() => fileRef.current && fileRef.current.click()}>📎</button>
          <textarea ref={textareaRef} className="chat-input" rows={1} value={text} maxLength={5000} aria-label="메시지 입력"
            placeholder="메시지를 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)" disabled={!!maintenanceNotice || !!rateLimitNotice}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); } }} />
          <Button variant="primary" onClick={() => doSend()} disabled={send.isPending || createConv.isPending || busy || awaitingReply || !!maintenanceNotice || !!rateLimitNotice || (!text.trim() && !pending.length)}>전송</Button>
        </footer>
        </div>
        </div>
      </section>
    </div>
  );
}
