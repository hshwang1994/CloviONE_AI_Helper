/* Ops 화면(진단/유지보수) 공용 순수 함수 + 상수 — JSX 없음. Diagnostics.jsx와 Maintenance.jsx가
 * 함께 쓴다(둘 다 같은 판정 임계값·같은 한국어 어휘를 써야 두 화면이 같은 사실을 다르게 말하지 않는다).
 * Dashboard.jsx도 이 모듈에서 되가져다 쓴다(DS-17) — 원래는 여기 있던 게 오히려 Dashboard.jsx
 * 쪽에 있어서, 이 파일이 화면 파일을 거꾸로 import하는 구조였다. */
import { toUTCDate } from "../../lib/format.js";

// 진단/유지보수 쓰기 권한(서버 RBAC와 일치). 프런트는 표시만 조정하고 판단은 서버가 한다.
export const WRITE_ROLES = ["admin", "system_admin"];
export const isWriteRole = (role) => role != null && WRITE_ROLES.includes(role);
// 쓰기 권한이 없을 때 버튼 옆에 남기는 이유 — 버튼을 숨기지 않는다(아래 Maintenance 주석 참고).
export const NO_WRITE_REASON = "관리자, 시스템 관리자만 변경할 수 있습니다.";

// 진단 번들의 컴포넌트(하트비트) 키를 한국어로. '살아있는가'를 판단하는 핵심 신호.
export const COMP_LABELS = { web: "웹 서버", worker: "백그라운드 워커", scheduler: "스케줄러" };

export const SERVICE_LABELS = {
  web: "웹 서버", worker: "백그라운드 워커", scheduler: "스케줄러",
  n8n: "n8n 엔진", "clovirone-work-assistant": "업무 도우미",
  "claude-ticket-runner": "티켓 러너", "claude-request-interpreter": "요청 해석기",
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

// StatCard는 값을 크게(clamp 1.5~2.25rem) 낸다(ui/kit.jsx), 자리수가 늘면(작업 누적 총계 등) 천 단위
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

/* 연동 상태 맵 → 도넛 조각. Dashboard.jsx의 serviceMix()와 같은 일을 하지만 라벨이 다르다:
 * 이 화면은 헬스체크 이력이 없는 연동을 '미점검'이라 부른다(아래 카드 배지와 같은 말). 대시보드의
 * '응답 없음'을 그대로 가져오면 바로 옆 카드와 같은 연동을 다른 말로 부르게 된다. */
export function integrationMix(integrations) {
  const vals = Object.values(integrations || {}).map((it) => {
    const v = it || {};
    if (v.enabled === false) return "disabled";
    return !v.last_health || v.last_health === "unknown" ? "unknown" : v.last_health;
  });
  const count = (x) => vals.filter((v) => v === x).length;
  const up = count("up");
  const down = count("down");
  const unknown = count("unknown");
  const disabled = count("disabled");
  const other = vals.length - up - down - unknown - disabled;
  return [
    { label: "정상", value: up, color: "ok" },
    { label: "중단", value: down, color: "danger" },
    { label: "미점검", value: unknown, color: "warn" },
    { label: "비활성화", value: disabled, color: "neutral" },
    { label: "기타", value: other > 0 ? other : 0, color: "info" },
  ];
}

// 전체 상태 한 줄 판정 — 진단 화면 상단에 '정상/주의' 요약을 준다(타일을 다 훑지 않게).
// 반드시 아래 타일들과 '같은 임계값'으로 모든 신호(웹/워커/스케줄러·디스크·메모리·인증서·성공률·대기·미해결 실패·
// 외부 연동 상태·최근 백업 실패 여부)를 검사한다 — 어느 타일이라도 warn/danger면 '정상'이라 말하지 않는다
// (예전엔 disk/mem warn 밴드와 성공률·대기를 아예 빼먹어, 성공률 60%로 빨간 타일이 떠도 상단은 '시스템 정상'이라
// 거짓 안심시켰다; 외부 연동 중단도 마찬가지로 빠져 있어 '외부 연동' 섹션이 빨간 배지를 보여도 상단은 정상이라 했다).
export function healthVerdict(comps, disk, mem, certDays, jobs, integrations, backup) {
  // problems는 {msg, tone} 객체 배열이다 — 예전엔 문자열만 담아, 디스크 warn과 컴포넌트 down이
  // 동시에 나면 한 배너 안에서 둘 다 색·모양이 똑같아 어느 항목이 진짜 급한지 구분이 안 됐다.
  // dang()/warn()이 이미 그 순간의 심각도를 알고 있으므로 그 정보를 항목별로 함께 담아 아래
  // 렌더에서 줄마다 다른 톤 글리프를 붙인다.
  const problems = [];
  let danger = false;
  const warn = (msg) => { problems.push({ msg, tone: "warn" }); };
  const dang = (msg) => { problems.push({ msg, tone: "danger" }); danger = true; };
  Object.keys(comps).forEach((k) => {
    const v = comps[k];
    if (v && v !== "up") {
      const label = (COMP_LABELS[k] || k) + (v === "down" ? " 중단" : " 응답 없음");
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
  // 구분한다 — 여기서 둘 다 "인증서 만료됨"으로 뭉뚱그리면 StatCard 타일은 "오늘 만료"라고
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
  // 대기(전체 백로그): >0 warn (아래 타일과 동일)
  if (jobs.queued) warn("대기 작업 " + jobs.queued + "건");
  // 미해결 실패(전체): >0 danger (아래 타일과 동일)
  if (jobs.failed_open) dang("미해결 실패 작업 " + jobs.failed_open + "건");
  // 외부 연동: down(비활성 제외) — '외부 연동' 섹션 배지와 동일 기준,
  // Dashboard.jsx의 대시보드 상단 경보 기준과도 일치시킨다.
  Object.entries(integrations || {}).forEach(([name, v]) => {
    if (!v || v.enabled === false) return;
    // 'degraded'는 백엔드가 만들어내지 않는 값이라(models.py는 up/down/unknown만, writer도 up/down만
    // 기록) 죽은 분기였다 — 제거한다. 'unknown'(미점검)은 Dashboard.jsx 상단 경보와 동일하게 의도적으로
    // 세지 않는다: 갓 만든/시드된 연동은 첫 헬스체크 전까지 늘 unknown이라, 이를 '주의'로 올리면 정상
    // 설치가 상시 노란불이 된다(바로 아래 '외부 연동' 섹션에서 '미점검' 배지로 이미 드러난다).
    if (v.last_health === "down") dang(serviceLabel(name) + " 연동 중단");
  });
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
  if (!problems.length) return { tone: "success", problems, msg: "시스템 정상, 지금 확인이 필요한 항목이 없습니다." };
  // 다중 장애가 동시에 겹치면(문제가 여러 건) ', '로 이어붙인 한 줄 긴 문장은 훑어보기 어렵다 —
  // 요약 한 줄만 msg로 두고, 실제 항목은 (아래 렌더에서) 줄마다 나눠 보여준다.
  return { tone: danger ? "danger" : "warn", problems, msg: problems.length === 1 ? problems[0].msg : "주의 " + problems.length + "건" };
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
