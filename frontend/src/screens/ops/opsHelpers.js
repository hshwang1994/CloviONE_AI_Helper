/* Ops 화면(진단/유지보수) 공용 순수 함수 + 상수 — JSX 없음. Diagnostics.jsx와 Maintenance.jsx가
 * 함께 쓴다(둘 다 같은 판정 임계값·같은 한국어 어휘를 써야 두 화면이 같은 사실을 다르게 말하지 않는다).
 * Dashboard.jsx도 이 모듈에서 되가져다 쓴다(DS-17) — 원래는 여기 있던 게 오히려 Dashboard.jsx
 * 쪽에 있어서, 이 파일이 화면 파일을 거꾸로 import하는 구조였다. */
import { toUTCDate } from "../../lib/format.js";
import { CONSOLE_WRITE_ROLES } from "../../lib/roles.js";

// 진단/유지보수 쓰기 권한(서버 RBAC와 일치). 프런트는 표시만 조정하고 판단은 서버가 한다.
// 값의 정본은 서버(app/core/authz.py)이고, 화면 쪽 사본은 lib/roles.js 한 곳이다(지시 21).
export const WRITE_ROLES = CONSOLE_WRITE_ROLES;
export const isWriteRole = (role) => role != null && WRITE_ROLES.includes(role);
// 쓰기 권한이 없을 때 버튼 옆에 남기는 이유 — 버튼을 숨기지 않는다(아래 Maintenance 주석 참고).
export const NO_WRITE_REASON = "관리자, 시스템 관리자만 바꿀 수 있습니다.";

/* 작업 백로그 줄에서 가는 곳 — 작업 큐를 **그 상태로 걸러서** 연다(작업 큐는 주소의 `status` 를 필터로 읽는다).
   대시보드 경보 행(`Dashboard.jsx` 의 `JOBS_FAILED_TO` · `JOBS_QUEUED_TO` · `ACTION_LABEL`)과 같은 곳 · 같은 이름이다 —
   두 화면이 같은 수에서 다른 곳으로 보내면 누른 사람은 전체 목록에서 그 작업을 다시 찾아야 한다. */
export const JOBS_BACKLOG_LINKS = {
  queued: { to: "/jobs?status=queued", label: "대기 작업 보기" },
  failed: { to: "/jobs?status=failed", label: "실패 작업 보기" },
};

// 진단 번들의 컴포넌트(하트비트) 키와 외부 연동 키를 한국어로 — 두 화면(Dashboard.jsx/
// Diagnostics.jsx)이 같은 8개 서비스를 각자 다른 표(COMP_LABELS 따로, SERVICE_LABELS 따로)로
// 들고 있다가 서로 어긋날 수 있었다(PA-RC-0028 regression_risk c). 이제 한 표만 둔다 — 컴포넌트
// 4종(worker_conversational은 그 레인을 켠 적이 있는 설치에만 백엔드가 보낸다, app/health/
// service.py::build_dashboard)과 외부 연동 4종을 아래 serviceLabel()이 함께 조회한다.
export const SERVICE_LABELS = {
  web: "웹 서버", worker: "백그라운드 작업", scheduler: "예약 실행", worker_conversational: "대화형 작업",
  notion: "Notion",
};
// 연동(Integration)은 관리자가 자유 텍스트로 이름을 만들 수 있어(§ Integrations 화면) SERVICE_LABELS의
// 고정 8종 밖의 이름은 항상 존재할 수 있다 — 그런 이름을 그냥 원문 그대로 보이면 코드 냄새가 난다.
// kit.jsx의 statusText()와 같은 완화 규칙을 쓴다: 매핑에 없으면 raw passthrough 대신 snake/kebab을
// 사람이 읽는 형태로 다듬는다(완전한 한국어 번역은 아니어도 원시 식별자보다는 낫다).
export function serviceLabel(name) {
  if (SERVICE_LABELS[name]) return SERVICE_LABELS[name];
  const s = String(name || "");
  if (/^[a-z0-9]+([_-][a-z0-9]+)+$/i.test(s)) {
    return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return s;
}

/* ── 상태 어휘 다섯 ──────────────────────────────────────────────────────────
 *
 * 관리 화면이 말할 수 있는 상태는 **다섯 개뿐**이고, 그 다섯이 서로 다른 뜻이다.
 *
 *   ok     정상        지금 떠 있다
 *   warn   응답 없음   있어야 하는데 하트비트가 없다(재시작 직후 등)
 *   down   중단        실제로 죽었다 — 관리자가 조치할 일이다
 *   unset  미점검      한 번도 안 재 봤다. 「죽었다」가 아니다
 *   off    사용 안 함  운영자가 꺼 뒀다. 장애가 아니다
 *
 * 🔴 **Red 는 `down` 하나뿐이다.** 「사용 안 함」과 「미점검」을 빨갛게 칠하면 정상적으로
 * 돌고 있는 설치가 매일 장애처럼 보이고, 그러면 진짜 빨간 줄도 함께 안 읽힌다.
 *
 * 어휘를 여기 한 곳에 두는 이유는 실측된 결함 때문이다: 대시보드의 「외부 연동」 요약이
 * `v === "up"` 만 세는 동안 그 아래 배지는 `statusText()` 로 그려져서, 같은 줄이
 * 「정상」이라고 적혀 있는데 요약은 「정상 0 / 6」이라고 말하고 있었다. 세는 함수와
 * 그리는 함수가 다른 표를 보면 언제나 이렇게 갈라진다. */
export const SERVICE_STATE_LABEL = {
  ok: "정상", warn: "응답 없음", down: "중단", unset: "미점검", off: "사용 안 함",
};
/* 배지·타일이 쓰는 톤. `kit.jsx::Badge` 의 kind 어휘와 같은 낱말이다. */
export const SERVICE_STATE_KIND = {
  ok: "ok", warn: "warn", down: "danger", unset: "neutral", off: "neutral",
};

/** 필수 서비스(하트비트) 한 칸의 상태. `up`·`down`·`unknown`(app/health/service.py). */
export function componentState(raw) {
  if (raw === "up") return "ok";
  if (raw === "down") return "down";
  // 하트비트 행이 없거나 낡았다. 필수 서비스라 「없어도 되는 것」이 아니므로 주의로 본다.
  return "warn";
}

/** 외부 연동 한 칸의 상태. `{enabled, last_health, last_health_at}` 를 받는다.
 *
 * 꺼 둔 것이 가장 먼저다 — 꺼 둔 연동의 `last_health` 는 껐을 때의 값이 그대로 굳어
 * 있어서, 그 값을 먼저 보면 꺼 놓은 것이 「중단」으로 보인다.
 *
 * `unknown` 은 **한 번도 안 잰 것**이다(`last_health_status` 의 기본값). 방금 등록한
 * 연동은 첫 스윕 전까지 늘 이 상태라, 이것을 빨갛게 칠하면 등록하는 순간 장애가 뜬다. */
export function integrationState(entry) {
  const v = entry || {};
  if (v.enabled === false) return "off";
  const h = v.last_health;
  if (h === "up") return "ok";
  if (h === "down") return "down";
  return "unset";
}

/** 상태 문자열들을 세어 `{ok, warn, down, unset, off, total}` 로. */
export function countStates(states) {
  const out = { ok: 0, warn: 0, down: 0, unset: 0, off: 0, total: 0 };
  (Array.isArray(states) ? states : []).forEach((s) => {
    if (out[s] === undefined) return;
    out[s] += 1;
    out.total += 1;
  });
  return out;
}

/** 「정상 3 / 4」 한 줄. 세는 기준이 위 어휘와 같아야 배지와 요약이 안 갈라진다. */
export function upSummaryText(states) {
  const c = countStates(states);
  return `정상 ${c.ok} / ${c.total}`;
}

/* 저장소 한 줄 판정. `storage_health()`(app/storage/service.py)를 받는다.
 *
 * 저장소가 **하나도 없는 것**과 **있는데 못 쓰는 것**은 다른 사실이다. `operational_ok`
 * 는 `bool(operational) and all(writable)` 이라 둘 다 false 로 뭉개진다 — 여기서
 * providers 를 직접 보고 갈라 준다(없으면 미설정, 있는데 못 쓰면 중단). */
export function storageState(storage) {
  const s = storage || {};
  const providers = Array.isArray(s.providers) ? s.providers : [];
  const operational = providers.filter((p) => p && p.role === "operational" && p.enabled);
  if (!providers.length) return { state: "unset", detail: "저장소가 설정되지 않았습니다." };
  if (!operational.length) return { state: "unset", detail: "쓰고 있는 운영 저장소가 없습니다." };
  const broken = operational.filter((p) => !p.writable);
  if (broken.length) {
    return {
      state: "down",
      detail: `운영 저장소 ${broken.length}개에 쓸 수 없습니다.`,
    };
  }
  return { state: "ok", detail: `운영 저장소 ${operational.length}개가 정상입니다.` };
}

// 마지막 성공 백업 이후 이만큼 지나면 '오래됨' 경보를 띄운다, 성공/실패 이분법(마지막 백업 없음)만
// 보면, 몇 주째 계속 실패 중인데도 예전의 마지막 성공 기록이 남아 있어 조용히 '정상'처럼 보인다.
export const BACKUP_STALE_DAYS = 7;
export function daysSince(iso) {
  if (!iso) return null;
  // 백엔드는 naive-UTC(오프셋 없는) ISO 문자열을 보낸다(CLAUDE.md §2.9), `new Date(iso)`에 그대로
  // 넣으면 JS가 이를 '로컬 시각'으로 해석해, KST(UTC+9) 브라우저에선 실제 경과 시간보다 최대 9시간
  // 어긋난다. lib/format.js의 다른 모든 날짜 파서와 같은 방식으로 오프셋이 없으면 'Z'를 붙인다.
  const s = String(iso);
  const isoZ = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const t = new Date(isoZ).getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 86400000;
}

// VIS-107R — failed_open은 "미해결 실패 4건"처럼 개수만 말해서, 오늘 막 생긴 것인지
// 3주 전부터 방치된 것인지 화면만 봐서는 구분이 안 됐다(옆의 failed_24h는 24시간 창이라도
// 있는데 이 지표만 시간축이 없었다). 서버가 새로 주는 failed_open_oldest_at(가장 오래된
// 미해결 실패의 생성 시각, app/health/service.py)로 나이를 덧붙인다. 하루 미만이면
// "오늘"이라고 정직하게 말한다 — "0일 전"은 "방금"과 "그럭저럭 하루 지남"을 뭉갠다.
// 무엇이 오래됐는지 말한다(「가장 오래된 실패는 53일 전」) — 예전 「가장 오래된 것」은 무엇을 가리키는지 앞 낱말에 기댔다.
export function failedOpenAgeLabel(jobs) {
  const oldest = jobs && jobs.failed_open_oldest_at;
  if (!oldest) return "";
  const age = daysSince(oldest);
  if (age == null) return "";
  const days = Math.floor(age);
  return ", 가장 오래된 실패는 " + (days < 1 ? "오늘" : days + "일 전");
}

// 측정값 타일은 값을 크게 낸다(ui/StatusKpi.jsx::StatusKpiTile), 자리수가 늘면(작업 누적 총계 등) 천 단위
// 구분자 없이는 스캔하기 어렵다. 현재 단일 테넌트 규모에선 체감이 적지만 값이 자랄수록 필요해진다.
export function fmtNum(n) {
  return typeof n === "number" ? n.toLocaleString("ko-KR") : n;
}
// 평균 처리 시간이 1분을 넘으면 '187초' 같은 raw seconds 대신 분, 초로 보여준다, 크고 굵은 KPI
// 타일에서 큰 초 단위 값은 한눈에 스캔하기 어렵다(registry.js의 job 지연 표기와 같은 취지).
export function fmtProcessingTime(sec) {
  if (sec == null) return "-";
  // 초/분을 각각 반올림(이중 반올림)하면 59.6초가 '60초'로, 119.6초가 '1분 60초'로 오버플로할 수
  // 있다, 전체를 정수 초로 한 번만 반올림한 뒤 그 정수에서 분, 초를 나눈다.
  const total = Math.round(sec);
  if (total < 60) return total + "초";
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s ? m + "분 " + s + "초" : m + "분";
}

/* 흐른 시간(분) → 「45분」 · 「3시간 5분」 · 「53일 2시간」. 작업 큐의 「가장 오래된 대기」 칩과 「지연」 칸이 쓴다.
 *
 * 하루가 넘으면 분을 버리고 일과 시간만 말한다 — 「1274시간 20분」은 사람이 24로 나눠 봐야 「53일」로 읽힌다. 아래 단위가
 * 0이면 붙이지 않는다(「2시간 0분」이 아니라 「2시간」). 음수 · 숫자가 아닌 값은 0분으로 읽는다(시계가 어긋나도 「-3분」을 그리지 않는다). */
export function fmtElapsedMinutes(minutes) {
  const m = Math.max(0, Math.floor(Number(minutes) || 0));
  if (m < 60) return m + "분";
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? h + "시간 " + (m % 60) + "분" : h + "시간";
  const d = Math.floor(h / 24);
  return h % 24 ? d + "일 " + (h % 24) + "시간" : d + "일";
}

// 인증서 만료는 음수(이미 만료)일 수 있다, 숫자만 노출하지 않는다.
// days===0은 아직 유효(자정 전까지 남음)하므로 "만료됨"이 아니라 "오늘 만료"로 구분한다.
export function fmtCertDays(days) {
  if (days == null) return "-";
  if (days < 0) return "만료됨";
  return days === 0 ? "오늘 만료" : "D-" + days;
}

// 다운로드 파일명용 사람이 읽는 타임스탬프(YYYYMMDD-HHmm) — epoch ms는 판독 불가했다.
function fileStamp(d) {
  const p = (n) => String(n).padStart(2, "0");
  return "" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "-" + p(d.getHours()) + p(d.getMinutes());
}

// 파일명 타임스탬프는 '지금'이 아니라 번들이 실제로 수집된 시각(generated_at)에서 뽑는다 —
// 10:00에 수집해 10:30에 내려받으면 내용은 10:00인데 이름이 10:30이라 지원팀이 오독했다.
// generated_at은 tz 없는 naive UTC이므로 fmtDateTime과 동일하게 Z를 보정한 뒤 로컬(KST)로 표기한다.
export function bundleStamp(bundle) {
  const d = toUTCDate(bundle && bundle.generated_at);
  return d ? fileStamp(d) : fileStamp(new Date());
}

/* 최근 작업 오류(recent_job_errors)의 '언제'만 뽑아 균등 구간으로 센다 — 스파크라인용.
 *
 * 이 화면에서 유일하게 시계열이라 부를 수 있는 자료다(다른 값은 전부 '지금' 스냅샷 스칼라다).
 * 다만 서버가 주는 건 **가장 최근 실패 20건**뿐이라(app/health/service.py, limit 20) 이걸
 * '오류율 추세'라고 부르면 거짓말이 된다 — 그래서 화면 문구도 반드시 '최근 실패 N건의 발생
 * 분포'라고만 쓴다. 20건이 한 시간에 몰렸는지 두 달에 흩어져 있는지가 장애 대응에서 제일 먼저
 * 알고 싶은 것이고, 그건 이 자료만으로 정직하게 말할 수 있다.
 *
 * 3건 미만이거나 전부 같은 순간이면 null을 돌려준다 — 점 한둘로 그린 선은 없는 추세를 만든다.
 */
export function errorBuckets(errors, bins = 12) {
  const times = [];
  for (const e of (Array.isArray(errors) ? errors : [])) {
    const d = toUTCDate(e && e.at);
    if (d) times.push(d.getTime());
  }
  if (times.length < 3) return null;
  const from = Math.min(...times);
  const to = Math.max(...times);
  if (to === from) return null;
  const counts = new Array(bins).fill(0);
  for (const t of times) {
    // 마지막 구간에 max가 들어가도록 클램프한다(비율 1.0 → 인덱스 bins가 되어 배열 밖으로 나간다).
    const i = Math.min(bins - 1, Math.floor(((t - from) / (to - from)) * bins));
    counts[i] += 1;
  }
  return { counts, from, to, n: times.length };
}

// 전체 상태 한 줄 판정 — 진단 화면 상단에 '정상/주의' 요약을 준다(타일을 다 훑지 않게).
// 반드시 아래 타일들과 '같은 임계값'으로 모든 신호(웹/워커/스케줄러·디스크·메모리·인증서·성공률·대기·미해결 실패·
// 외부 연동 상태·최근 백업 실패 여부)를 검사한다 — 어느 타일이라도 warn/danger면 '정상'이라 말하지 않는다
// (예전엔 disk/mem warn 밴드와 성공률·대기를 아예 빼먹어, 성공률 60%로 빨간 타일이 떠도 상단은 '시스템 정상'이라
// 거짓 안심시켰다; 외부 연동 중단도 마찬가지로 빠져 있어 '외부 연동' 섹션이 빨간 배지를 보여도 상단은 정상이라 했다).
export function healthVerdict(comps, disk, mem, certDays, jobs, integrations, backup, storage) {
  // problems는 {msg, tone, link?} 객체 배열이다 — 예전엔 문자열만 담아, 디스크 warn과 컴포넌트 down이
  // 동시에 나면 한 배너 안에서 둘 다 색·모양이 똑같아 어느 항목이 진짜 급한지 구분이 안 됐다.
  // dang()/warn()이 이미 그 순간의 심각도를 알고 있으므로 그 정보를 항목별로 함께 담아 아래
  // 렌더에서 줄마다 다른 톤 글리프를 붙인다. `link` 는 그 줄에서 바로 갈 곳이다(작업 백로그 → 거른 작업 큐).
  const problems = [];
  let danger = false;
  const warn = (msg, link) => { problems.push({ msg, tone: "warn", ...(link ? { link } : null) }); };
  const dang = (msg, link) => { problems.push({ msg, tone: "danger", ...(link ? { link } : null) }); danger = true; };
  Object.keys(comps).forEach((k) => {
    const v = comps[k];
    if (v && v !== "up") {
      const label = serviceLabel(k) + (v === "down" ? " 중단" : " 응답 없음");
      if (v === "down") dang(label); else warn(label);
    }
  });
  // 디스크: >=85 danger / >=80 warn (아래 타일과 동일 — Dashboard.jsx의 warn 밴드(80)와도 일치시켜
  // 같은 수치가 화면마다 다른 심각도로 읽히지 않게 한다).
  if (disk.used_pct != null) {
    if (disk.used_pct >= 85) dang("디스크 " + disk.used_pct + "%");
    else if (disk.used_pct >= 80) warn("디스크 " + disk.used_pct + "%");
  }
  // 메모리: >=90 danger / >=80 warn (아래 타일과 동일)
  if (mem.used_pct != null) {
    if (mem.used_pct >= 90) dang("메모리 " + mem.used_pct + "%");
    else if (mem.used_pct >= 80) warn("메모리 " + mem.used_pct + "%");
  }
  // 인증서: 만료 danger / D-30 이내 warn (아래 타일과 동일)
  // days===0(오늘 만료, 자정 전까진 아직 유효)과 days<0(이미 만료)을 fmtCertDays()로 일관되게
  // 구분한다 — 여기서 둘 다 "인증서 만료됨"으로 뭉뚱그리면 판독 칸은 "오늘 만료"라고
  // 정확히 말하는데 이 상단 배너만 다르게 말해 서로 모순되는 문구가 동시에 뜬다.
  if (certDays != null) {
    if (certDays <= 0) dang("인증서 " + fmtCertDays(certDays));
    else if (certDays <= 30) warn("인증서 D-" + certDays);
  }
  // 성공률: <80 danger / <95 warn (아래 타일과 동일). 처리 건수가 0이면 성공률 타일이
  // '-'(무채색)이라 문제로 세지 않는다.
  if (jobs.success_rate_pct != null && jobs.total > 0) {
    if (jobs.success_rate_pct < 80) dang("성공률 " + jobs.success_rate_pct + "%");
    else if (jobs.success_rate_pct < 95) warn("성공률 " + jobs.success_rate_pct + "%");
  }
  // 대기(전체 백로그): >0 warn. 미해결 실패(전체): >0 danger.
  // 백로그 두 수는 **이 판정 목록 한 곳**이 말한다(D-501) — 아래 「작업 지표 (최근 24시간)」 줄에 같은 수가 「(전체)」
  // 타일로 또 섰는데, 24시간 창이 아닌 누계라 그 제목과도 맞지 않았다. 그 줄에서 바로 그 상태로 거른 작업 큐로 간다.
  if (jobs.queued) warn("대기 작업 " + jobs.queued + "건", JOBS_BACKLOG_LINKS.queued);
  if (jobs.failed_open) dang("미해결 실패 작업 " + jobs.failed_open + "건", JOBS_BACKLOG_LINKS.failed);
  /* 외부 연동: down(비활성·미점검 제외) — '외부 연동' 섹션 배지·대시보드 조치 목록과 같은 기준.
   *
   * 🔴 **위험이 아니라 주의다.** 예전에는 `dang()` 이라, 선택 구성요소 하나가 죽으면 필수
   * 서비스가 전부 멀쩡한데도 상단이 「위험」으로 붉어졌다. 운영 실측(2026-08-26)에서
   * 걷어낸 런타임을 가리키던 등록 행 넷이 정확히 그 화면을 만들었다 — 정상 제품이 매일
   * 장애로 보였고, 그 사이 진짜 빨간 줄이 섞여도 구별되지 않았다.
   *
   * 연동은 **바깥으로 나가는 선택 호출**이다. 죽으면 그 기능만 멈추고 제품은 돈다. 필수
   * 서비스(위 comps 루프)와 같은 등급으로 세지 않는다.
   *
   * 'unknown'(미점검)은 여전히 안 센다: 갓 등록한 연동은 첫 스윕 전까지 늘 그 값이라,
   * 주의로 올리면 등록하는 순간 노란불이 켜진다(섹션 배지가 '미점검'으로 이미 말한다). */
  Object.entries(integrations || {}).forEach(([name, v]) => {
    if (integrationState(v) !== "down") return;
    warn(serviceLabel(name) + " 연동 중단");
  });
  /* 저장소: 운영 저장소에 못 쓰면 첨부·업로드가 통째로 멈춘다 — 디스크 용량과 다른 결함이다
     (용량은 멀쩡한데 마운트가 빠지거나 소유권이 어긋난 경우). 「설정 안 됨」은 장애가 아니다. */
  if (storage) {
    const st = storageState(storage);
    if (st.state === "down") dang(st.detail);
    if (storage.warning) warn(storage.warning);
  }
  // 백업: 실패는 danger, '없음'·'오래됨'은 Dashboard.jsx(daysSince/BACKUP_STALE_DAYS)와 같은 기준으로
  // 상단 요약에도 반영한다 — 예전엔 last_backup_status==='failed'만 보고 null·stale은 지나쳐,
  // Dashboard는 '마지막 백업 없음/오래됨' 경보를 띄우는데 이 화면 상단만 '정상'이라 서로 어긋났다.
  if (backup) {
    if (backup.last_backup_status === "failed") dang("최근 백업 실패");
    else if (!backup.last_backup_at) warn("마지막 백업 없음");
    else {
      const age = daysSince(backup.last_backup_at);
      if (age != null && age > BACKUP_STALE_DAYS) {
        const label = "마지막 백업이 오래됨(" + Math.floor(age) + "일 전)";
        if (age > BACKUP_STALE_DAYS * 2) dang(label); else warn(label);
      }
    }
  }
  // 문제 없음은 중립(info) 'ⓘ'가 아니라 Dashboard.jsx의 all-clear 배너와 같은 성공(success) 색조로
  // 보인다 — 색만 맞춘 것이지 모양까지 같지는 않다(여기는 Callout의 테두리 상자, Dashboard는 배지가
  // 든 테두리 없는 줄). 여러 화면이 '지금 조치할 문제 없음'을 완전히 같은 컴포넌트로 그리려면
  // Callout 자체를 그쪽 마크업으로 바꿔야 하는 별도 작업이라 여기서는 색조 일치까지만 보장한다.
  if (!problems.length) return { tone: "success", problems, msg: "시스템이 정상이고 조치가 필요한 항목이 없습니다." };
  // 다중 장애가 동시에 겹치면(문제가 여러 건) ', '로 이어붙인 한 줄 긴 문장은 훑어보기 어렵다 —
  // 요약 한 줄만 msg로 두고, 실제 항목은 (아래 렌더에서) 줄마다 나눠 보여준다.
  // 🔴 요약은 심각도 하나를 대표로 세우지 않는다. 예전 「주의 5건」 아래에 「위험」 줄 둘이 섞여 있었다 — 제목이 아래 목록과
  // 다른 말을 했다. 전체는 「확인할 항목 N건」이고, 두 심각도가 섞이면 괄호 안에 갈라 말한다(같은 낱말 위험 · 주의, 줄마다의 표지와 같다).
  const dangerCount = problems.filter((p) => p.tone === "danger").length;
  const warnCount = problems.length - dangerCount;
  const summary = "확인할 항목 " + problems.length + "건"
    + (dangerCount && warnCount ? "(위험 " + dangerCount + "건, 주의 " + warnCount + "건)" : "");
  return { tone: danger ? "danger" : "warn", problems, msg: problems.length === 1 ? problems[0].msg : summary };
}

// 대상 ID를 8자로 줄여 보여줄 때, 줄였다는 시각적 신호(…)를 남긴다(Dashboard.jsx와 동일 규칙) —
// 그냥 잘라내면 '이게 전체 값'처럼 보여 그대로 다른 화면(감사 로그 필터 등)에 잘못 붙여넣기 쉽다.
export function shortId(id) {
  const s = String(id);
  return s.length > 8 ? s.slice(0, 8) + "…" : s;
}

// 클립보드 복사(비보안 컨텍스트·미지원 브라우저 폴백). 성공/실패를 반드시 알린다.
export function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => false);
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return Promise.resolve(ok); }
  catch (e) { return Promise.resolve(false); }
}
