/* 「기간」 칸의 계산 (F4 · D-530) — 프리셋을 키 쌍으로, 키 쌍을 사람이 읽는 이름으로 바꾼다.
 *
 * 예전 목록 화면은 기간을 날짜 칸 둘(「시작일」 · 「종료일」)로 그렸다. 그 칸만 라벨이 위에 서고 높이가 36 이라 필터 줄에서 혼자
 * 어긋났고, 칩도 둘이라 하나만 지우면 반쪽 기간이 남았다. 기간은 칸 하나다 — 값은 지금 쓰는 키 쌍(`from`/`to` ·
 * `since`/`until`) 그대로 주소 · 저장된 뷰 · 서버로 가고, 칸과 칩은 그 쌍을 이름 하나로 부른다.
 *
 * 경계는 **KST 달력일**이다. 「오늘」은 서버가 쓰는 오늘과 같은 날이어야 하고(`app/ai/usage_router.py::_today`), 날짜만 보낸 값은
 * 서버가 KST 그날 00:00 ~ 다음날 00:00 으로 읽는다(`app/core/dates.py::parse_kst_boundary`). 그래서 브라우저 시간대를 쓰지
 * 않고 `lib/format.js` 의 KST 변환만 쓴다.
 *
 * 시각 프리셋(감사 로그의 시각 쌍)은 고른 순간의 절대 시각을 적는다 — 주소에 「최근 1시간」이라는 낱말을 싣지 않는다. 다시 열어
 * 보면 그 칸은 「10월 1일 13:05부터」처럼 실제로 걸린 시각을 말한다(시간이 흐른 뒤에도 「최근 1시간」이라 부르면 거짓이다).
 */
import { apiToKstLocal, fmtDayKo, kstDayKey } from "../lib/format.js";

/* 프리셋 이름 — 칸 · 칩 · 메뉴가 같은 표를 쓴다. */
export const PERIOD_PRESET_LABEL = Object.freeze({
  today: "오늘",
  "7d": "최근 7일",
  "30d": "최근 30일",
  thisMonth: "이번 달",
  lastMonth: "지난달",
  all: "전체",
  "1h": "최근 1시간",
  "24h": "최근 24시간",
});

/* 날짜 쌍과 시각 쌍의 기본 프리셋. 화면이 `presets` 로 다른 목록을 줄 수 있다(서버가 「전체」를 받지 않는 축 — AI 사용 통계). */
export const DATE_PRESETS = Object.freeze(["today", "7d", "30d", "thisMonth", "lastMonth", "all"]);
export const TIME_PRESETS = Object.freeze(["1h", "24h", "7d", "all"]);

const HOUR_MS = 3600 * 1000;
const DAY_KEY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** 지금의 KST 달력일(`YYYY-MM-DD`). `now` 는 `Date` 다. */
export function kstToday(now) {
  return kstDayKey((now || new Date()).toISOString());
}

/** `YYYY-MM-DD` 에 n 일을 더한다 — 달력 계산이라 UTC 자정에서 한다(시간대가 끼면 하루가 밀린다). */
export function addDays(dayKey, n) {
  const m = DAY_KEY.exec(String(dayKey || ""));
  if (!m) return "";
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + n));
  return d.toISOString().slice(0, 10);
}

function monthStart(dayKey) {
  return String(dayKey).slice(0, 8) + "01";
}

function previousMonth(dayKey) {
  const first = monthStart(dayKey);
  const lastOfPrev = addDays(first, -1);
  return { from: monthStart(lastOfPrev), to: lastOfPrev };
}

/** KST 벽시계(`YYYY-MM-DDTHH:mm`) — `datetime-local` 칸과 시각 쌍 필터가 쓰는 모양. */
export function kstLocal(date) {
  return apiToKstLocal(date.toISOString());
}

/**
 * 프리셋 하나 → 키 쌍 `{ from, to }`. 빈 문자열은 「그 끝을 열어 둔다」는 뜻이다.
 *   mode  "date"(날짜 쌍, KST 달력일) · "datetime"(시각 쌍, KST 벽시계)
 */
export function presetRange(preset, { mode = "date", now = new Date() } = {}) {
  if (preset === "all") return { from: "", to: "" };
  if (mode === "datetime") {
    const back = { "1h": HOUR_MS, "24h": 24 * HOUR_MS, "7d": 7 * 24 * HOUR_MS }[preset];
    if (!back) return null;
    return { from: kstLocal(new Date(now.getTime() - back)), to: "" };
  }
  const today = kstToday(now);
  switch (preset) {
    case "today": return { from: today, to: today };
    case "7d": return { from: addDays(today, -6), to: today };
    case "30d": return { from: addDays(today, -29), to: today };
    case "thisMonth": return { from: monthStart(today), to: today };
    case "lastMonth": return previousMonth(today);
    default: return null;
  }
}

/**
 * 키 쌍이 어느 프리셋과 같은가 — 같으면 그 키, 아니면 null.
 *
 * 둘 다 비었으면 `emptyPreset`(서버가 빈 값을 무엇으로 읽는가 — 보통 「전체」, AI 사용 통계는 「최근 30일」)이다. 날짜 프리셋은
 * 오늘을 기준으로 다시 계산해 비교한다 — 어제 고른 「최근 7일」은 오늘의 「최근 7일」이 아니므로 맞지 않는다(그 칸은 날짜를
 * 말한다). 시각 프리셋은 시간이 흐르면 다시 맞출 수 없어 여기서는 맞추지 않는다(고른 순간은 아래 `rememberPreset` 이 기억한다).
 */
export function matchPreset({ from = "", to = "" } = {}, { mode = "date", presets, emptyPreset = "all", now = new Date() } = {}) {
  const list = presets || (mode === "datetime" ? TIME_PRESETS : DATE_PRESETS);
  if (!from && !to) return emptyPreset || null;
  if (mode === "datetime") return null;
  for (const key of list) {
    if (key === "all" || key === emptyPreset) continue;
    const r = presetRange(key, { mode, now });
    if (r && r.from === from && r.to === to) return key;
  }
  /* 빈 값이 서버 기본값인 축(「최근 30일」)은 그 기간을 손으로 적어도 같은 기간이다. */
  if (emptyPreset && emptyPreset !== "all") {
    const r = presetRange(emptyPreset, { mode, now });
    if (r && r.from === from && r.to === to) return emptyPreset;
  }
  return null;
}

/* 날짜 하나의 짧은 이름 — 올해면 「9월 2일」, 다른 해면 「2025년 9월 2일」. */
function dayText(dayKey, now) {
  const m = DAY_KEY.exec(String(dayKey || "").slice(0, 10));
  if (!m) return String(dayKey || "");
  const thisYear = kstToday(now).slice(0, 4);
  return (m[1] === thisYear ? "" : `${Number(m[1])}년 `) + fmtDayKo(m[0]);
}

/* 시각 하나의 짧은 이름 — 「10월 1일 13:05」. */
function momentText(local, now) {
  const s = String(local || "");
  const day = dayText(s.slice(0, 10), now);
  const time = /T(\d\d:\d\d)/.exec(s);
  return time ? `${day} ${time[1]}` : day;
}

/* 방금 고른 시각 프리셋 — 「최근 1시간」을 고르면 칸과 칩이 그 이름을 말한다. 값이 바뀌거나 새로 열면(주소에서 복원하면) 잊고
   절대 시각을 말한다. 프로세스 기억이라 저장하지 않는다. 몇 개만 둔다. */
const RECENT_PICKS = new Map();
const RECENT_PICKS_MAX = 16;

/** 프리셋을 고른 순간의 키 쌍을 기억한다(`PeriodFilter` 가 부른다). */
export function rememberPreset({ from = "", to = "" } = {}, key, mode = "date") {
  RECENT_PICKS.set(`${mode}|${from}|${to}`, key);
  while (RECENT_PICKS.size > RECENT_PICKS_MAX) RECENT_PICKS.delete(RECENT_PICKS.keys().next().value);
}

/** 기억한 프리셋을 잊는다(시험이 부른다). */
export function forgetPresets() {
  RECENT_PICKS.clear();
}

/**
 * 칸 · 칩이 부르는 기간 이름.
 *   emptyLabel  둘 다 비었을 때의 이름(서버 기본값) — 없으면 `emptyPreset` 의 이름
 */
export function periodLabel({ from = "", to = "" } = {}, opts = {}) {
  const { mode = "date", emptyLabel, emptyPreset = "all", now = new Date() } = opts;
  if (!from && !to) return emptyLabel || PERIOD_PRESET_LABEL[emptyPreset] || "전체";
  const recalled = mode === "datetime" ? RECENT_PICKS.get(`${mode}|${from}|${to}`) : null;
  if (recalled && PERIOD_PRESET_LABEL[recalled]) return PERIOD_PRESET_LABEL[recalled];
  const hit = matchPreset({ from, to }, { ...opts, mode, emptyPreset, now });
  if (hit && PERIOD_PRESET_LABEL[hit]) return PERIOD_PRESET_LABEL[hit];
  const one = mode === "datetime" ? (v) => momentText(v, now) : (v) => dayText(v, now);
  if (from && to) return from === to ? one(from) : `${one(from)} ~ ${one(to)}`;
  return from ? `${one(from)}부터` : `${one(to)}까지`;
}

/** 직접 고른 두 값이 기간으로 맞는가 — 시작이 끝보다 늦으면 문장을, 맞으면 빈 문자열을 돌려준다. */
export function periodProblem({ from = "", to = "" } = {}) {
  if (from && to && from > to) return "시작이 종료보다 늦습니다. 기간을 다시 선택하세요.";
  return "";
}
