import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime, toUTCDate, jobTypeKo, actionKo, objKo } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import {
  serviceLabel, fmtNum, fmtProcessingTime, daysSince, BACKUP_STALE_DAYS,
  DashSection, Note, StatusTile, STAT_GRID, SERVICE_GRID,
} from "./Dashboard.jsx";
import { SettingVersions } from "./Settings.jsx";
import { PageHeader, Card, Badge, Button, Callout, StatCard, Skeleton, ErrorState, EmptyState, useConfirm, useToast } from "../ui/kit.jsx";
import { Sparkline } from "../ui/charts/Sparkline.jsx";
import { Donut } from "../ui/charts/Donut.jsx";

// 진단/유지보수 쓰기 권한(서버 RBAC와 일치). 프런트는 표시만 조정하고 판단은 서버가 한다.
const WRITE_ROLES = ["admin", "system_admin"];
const isWriteRole = (role) => role != null && WRITE_ROLES.includes(role);
// 쓰기 권한이 없을 때 버튼 옆에 남기는 이유 — 버튼을 숨기지 않는다(아래 Maintenance 주석 참고).
const NO_WRITE_REASON = "관리자, 시스템 관리자만 변경할 수 있습니다.";

// 진단 번들의 컴포넌트(하트비트) 키를 한국어로. '살아있는가'를 판단하는 핵심 신호.
const COMP_LABELS = { web: "웹 서버", worker: "백그라운드 워커", scheduler: "스케줄러" };

// 인증서 만료는 음수(이미 만료)일 수 있다, 숫자만 노출하지 않는다.
// days===0은 아직 유효(자정 전까지 남음)하므로 "만료됨"이 아니라 "오늘 만료"로 구분한다(Dashboard.jsx와 동일 규칙).
function fmtCertDays(days) {
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
function bundleStamp(bundle) {
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
function integrationMix(integrations) {
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
function healthVerdict(comps, disk, mem, certDays, jobs, integrations, backup) {
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
function shortId(id) {
  const s = String(id);
  return s.length > 8 ? s.slice(0, 8) + "…" : s;
}

// 클립보드 복사(비보안 컨텍스트·미지원 브라우저 폴백). 성공/실패를 반드시 알린다.
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, () => false);
  try { const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); const ok = document.execCommand("copy"); document.body.removeChild(ta); return Promise.resolve(ok); }
  catch (e) { return Promise.resolve(false); }
}

// 이력 목록(최근 작업 오류·최근 주요 변경)의 한 줄 — 시각 / 내용 / 대상 3열, 좁으면 한 열로 접힌다.
function LogRow({ when, what, children }) {
  return (
    <Box component="li"
      sx={{
        display: "grid", alignItems: "baseline", gap: { xs: 0.25, sm: 1.5 },
        gridTemplateColumns: { xs: "1fr", sm: "12rem minmax(0,1fr) auto" },
      }}>
      <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{when}</Typography>
      <Typography variant="body2" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{what}</Typography>
      {children}
    </Box>
  );
}
function LogList({ children }) {
  return <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>{children}</Box>;
}

/* 진단 — 진단 번들을 수집해 구조화해 보여준다(GET /api/admin/diagnostics/bundle).
 * 번들은 admin/system_admin만 조회할 수 있으므로 다른 역할에겐 수집 버튼을 감춘다. */
export function Diagnostics() {
  const toast = useToast();
  const nav = useNavigate();
  // 이 컴포넌트에 도달할 수 있는 역할은 이미 App.jsx의 라우트 가드(RequireRole roles=["admin",
  // "system_admin"])로 WRITE_ROLES와 정확히 같은 집합으로 제한된다 — 그래서 예전의 canCollect 분기
  // (역할 부족 안내문·수집 버튼 숨김·'눌러서 수집하세요' 폴백)는 이 화면에 도달한 시점엔 항상 참이라
  // 실행될 수 없는 죽은 코드였다. 역할 판정은 라우트 가드 한 곳에만 둔다.
  const q = useQuery({ queryKey: ["diag"], queryFn: () => api("/api/admin/diagnostics/bundle"), enabled: false, retry: false });
  // 재수집은 조용히 실패하면 안 된다 — 실패 시 토스트로 알리고, 이전 번들이 남아 있으면
  // 그것이 '지금' 값이 아님을 분명히 한다(아래 stale 배너). 수동 수집 성공만 완료 토스트를 띄운다
  // (자동/폴링 성공까지 알리면 시끄럽다).
  // 토스트는 refetch를 부른 각 caller(수동 버튼·60초 자동 폴링)마다 개별 .then()에서 판단하지 않고,
  // 쿼리 자체의 isFetching 전이(진행중→정지) 한 곳에서만 결정한다 — 안 그러면 수동 클릭과 자동 폴링이
  // 거의 같은 순간 겹칠 때 같은 실패에 토스트가 두 번 뜬다(react-query가 동시 refetch를 내부적으로
  // 하나의 요청으로 합쳐도, 각 호출자가 각자 .then()을 달면 둘 다 알림을 띄운다).
  const manualRef = React.useRef(false);
  const wasFetchingRef = React.useRef(false);
  const wasErrorRef = React.useRef(false); // 이미 오류 스트릭 중이면 자동 폴링 실패마다 같은 stale 토스트를 반복하지 않는다
  // 60초 자동 폴링도 q.isFetching을 켜므로, 버튼 disabled/라벨을 raw q.isFetching에 물리면 매분
  // '수집 중…'으로 깜빡이며 사용자가 시작하지도 않은 배경 조회 동안 주 버튼이 비활성화됐다 —
  // Dashboard.jsx의 manualRefreshing 패턴처럼 '수동 수집'만 버튼 상태로 반영한다.
  const [manualCollecting, setManualCollecting] = React.useState(false);
  React.useEffect(() => { if (!q.isFetching) setManualCollecting(false); }, [q.isFetching]);
  function collect(manual) {
    if (manual) { manualRef.current = true; setManualCollecting(true); }
    return q.refetch();
  }
  React.useEffect(() => {
    if (wasFetchingRef.current && !q.isFetching) {
      const wasManual = manualRef.current;
      manualRef.current = false;
      if (q.isError) {
        if (q.data) {
          // 자동 폴링(manual=false)이 계속 실패하는 동안엔(장애 지속) 매 60초마다 같은 배너를 반복
          // 토스트하지 않는다 — 오류 스트릭 진입 순간과, 사용자가 수동으로 다시 시도한 순간에만 알린다.
          if (wasManual || !wasErrorRef.current) toast("진단 갱신에 실패했습니다, 아래 값은 이전에 수집한 자료입니다.", "error");
        } else if (wasManual) toast("진단 수집에 실패했습니다.", "error");
        // 자동 수집(manual=false)이고 이전 번들도 없으면 전체화면 ErrorState가 이미 실패를 알리므로 토스트를 겹치지 않는다.
        wasErrorRef.current = true;
      } else {
        wasErrorRef.current = false;
        if (wasManual && q.data) toast("진단을 수집했습니다.", "success");
      }
    }
    wasFetchingRef.current = q.isFetching;
  }, [q.isFetching, q.isError, q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  // 마운트 시(또는 Dashboard 경보에서 넘어올 때) 자동 수집해 빈 화면 대신 최신 번들을 바로 보여준다.
  // 재방문 시에도 다시 수집하므로 캐시된 낡은 번들을 복사/다운로드하는 일을 막는다.
  React.useEffect(() => { collect(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Dashboard.jsx와 같은 이유로(운영 현황은 실시간성이 핵심) 60초마다 자동 재수집한다 — 활성 장애를
  // 조사하는 화면을 열어둔 채 지켜봐도 수치가 저절로 갱신되지 않아 계속 수동으로 눌러야 했다.
  // enabled:false 쿼리라 refetchInterval이 스스로 도는 대신, 여기서 주기적으로 collect(false)를 부른다.
  React.useEffect(() => {
    const t = setInterval(() => collect(false), 60 * 1000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [copied, setCopied] = React.useState("");
  const copiedTimerRef = React.useRef(null); // 연속 클릭 시 이전 타이머가 방금 세팅한 '복사됨'을 조기에 지우지 않도록
  // '복사'를 누르고 1.5초 안에 다른 화면으로 이동하면, 예약된 setCopied가 이미 언마운트된
  // 컴포넌트에 대고 실행된다 — 언마운트 시 남은 타이머를 반드시 지운다.
  React.useEffect(() => () => { if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current); }, []);
  const bundle = q.data || null;
  const text = bundle ? JSON.stringify(bundle, null, 2) : "";

  function doCopy() {
    copyText(text).then((ok) => {
      // 성공도 토스트로 알린다 — 버튼 라벨 변화만으론 스크린리더가 인지하지 못한다.
      if (ok) {
        setCopied("복사됨");
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(""), 1500);
        toast("복사됨", "success");
      }
      else toast("복사에 실패했습니다. 아래 원본을 직접 선택해 복사하세요.", "error");
    });
  }
  function doDownload() {
    try {
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "diagnostics-" + bundleStamp(bundle) + ".json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // 복사와 대칭으로 성공도 알린다 — 브라우저가 조용히 내려받는 경우 확인 신호가 없었다.
      toast("진단 번들을 내려받았습니다.", "success");
    } catch (e) { toast("다운로드에 실패했습니다.", "error"); }
  }

  const dash = (bundle && bundle.dashboard) || {};
  const disk = dash.disk || {};
  const mem = dash.memory || {};
  const comps = dash.components || {};
  const jobs24 = dash.jobs_24h || {};
  const jobErrors = (bundle && bundle.recent_job_errors) || [];
  const errorDist = errorBuckets(jobErrors);
  // 실제로 중단·응답 없음 상태인 컴포넌트의 systemd 유닛만 안내한다 — web과 worker/scheduler는
  // 서로 다른 유닛(clovirone-web-assistant.service / clovirone-web-worker.service)이라, 웹만 죽었을
  // 때 워커 로그를 보라고 하면 실제 장애 순간에 엉뚱한 곳을 가리키게 된다.
  const downComponentKeys = Object.keys(comps).filter((k) => comps[k] && comps[k] !== "up");
  const downUnits = Array.from(new Set(downComponentKeys.map((k) => (k === "web" ? "clovirone-web-assistant" : "clovirone-web-worker"))));
  // 번들은 down만이 아니라 전체 연동 상태(integrations)와 리소스 수(counts)를 담는다 -
  // 정상 연동 목록과 시스템 카운트를 숨기면 지원팀이 원본 JSON을 뒤져야 했다.
  const integrations = dash.integrations || {};
  const counts = dash.counts || {};
  // 번들은 actor 이름까지 해석한 '최근 주요 변경'(누가 role_change/backup.restore/rollback/approve 했나)을 담는데
  // 화면이 이걸 버려 지원팀이 원본 JSON을 뒤져야 했다, 대시보드와 같은 방식(actionKo/objKo)으로 구조화해 보여준다.
  const recentAudit = dash.recent_critical_audit || [];
  // 스펙 §14.7 'Integration Error Summary'용 integration_errors 필드는 build_diagnostic_bundle
  // (app/health/service.py)이 더 이상 응답에 내려주지 않는다, 이 화면 바로 위 '외부 연동' 섹션이
  // 이미 down/degraded 전 목록을 배지로 보여주므로, 존재하지 않는 필드를 읽어 항상 빈 배열이 되는
  // 죽은 요약 Callout은 만들지 않는다(백엔드가 이 필드를 되살리면 그때 다시 추가).

  return (
    <Box>
      <PageHeader area="운영" title="진단"
        actions={<>
          <Button variant="primary" onClick={() => collect(true)} disabled={manualCollecting}>{manualCollecting ? "수집 중…" : "진단 수집"}</Button>
          {/* '복사'↔'복사됨' 라벨 전환으로 버튼 폭이 바뀌어 옆 'JSON 다운로드' 버튼이 그때마다
              옆으로 밀리던 문제, 폭을 예약하는 래퍼로 감싼다(rem이라 4K에서 함께 커진다). */}
          {text ? (
            <>
              <Box sx={{ minWidth: "5.5rem", display: "inline-flex" }}>
                <Button onClick={doCopy} sx={{ width: "100%" }}>{copied || "복사"}</Button>
              </Box>
              <Button onClick={doDownload}>JSON 다운로드</Button>
            </>
          ) : null}
        </>} />
      {/* 스켈레톤은 최초 수집 때만, 재수집(refetch) 중에는 이전 번들을 그대로 두어 읽던 맥락이 사라지지 않게 한다.
          (재수집 진행은 헤더의 '수집 중…' 버튼 상태가 알려 준다.) */}
      {(q.isFetching && !bundle) ? <Card><Skeleton lines={4} /></Card>
        : (q.isError && !bundle) ? <ErrorState error={q.error} onRetry={() => collect(true)} />
        : bundle ? (
          <Box>
            {/* 재수집이 실패해도 이전 번들이 그대로 남으므로, 낡은 값을 최신처럼 보여주지 않도록 경고 배너를 띄운다. */}
            {q.isError ? <Box sx={{ mb: 3 }}><Callout tone="warn">진단 갱신에 실패했습니다, 아래 값은 {fmtDateTime(bundle.generated_at)}에 수집한 이전 자료입니다.</Callout></Box> : null}
            <Note sx={{ mt: 0, mb: 3 }}>수집 시각: {fmtDateTime(bundle.generated_at)}, 이 번들은 민감정보가 가려져 있어 지원팀에 그대로 전달해도 안전합니다.</Note>
            {/* 상태 요약(정상/주의)은 수집마다 바뀌므로 낭독되도록 라이브 영역으로 감싼다. */}
            {(() => {
              const hv = healthVerdict(comps, disk, mem, dash.cert_days_remaining, jobs24, integrations, dash);
              return (
                <Box sx={{ mb: 4 }} role="status" aria-live="polite">
                  <Callout tone={hv.tone}>
                    {hv.problems.length > 1 ? (
                      <>
                        <Box>{hv.msg}</Box>
                        <Box component="ul" sx={{ listStyle: "none", m: 0, mt: 0.75, p: 0, display: "grid", gap: 0.25 }}>
                          {hv.problems.map((p, i) => (
                            <Box component="li" key={i}
                              sx={{ display: "flex", alignItems: "baseline", gap: 0.75, color: p.tone === "danger" ? "error.main" : "warning.main" }}>
                              {/* 심각도를 색만으로 전하지 않는다(WCAG 1.4.1) — 짧은 글자 라벨을 함께 둔다. */}
                              <Box component="span" sx={{ flexShrink: 0, fontWeight: 800, fontSize: "0.75rem" }}>
                                {p.tone === "danger" ? "위험" : "주의"}
                              </Box>
                              {p.msg}
                            </Box>
                          ))}
                        </Box>
                      </>
                    ) : hv.msg}
                  </Callout>
                </Box>
              );
            })()}
            {/* 디스크, 메모리, 인증서가 모두 null이면(비-Linux 호스트, nginx TLS 종단 등) 섹션 자체를 숨긴다 -
                Dashboard.jsx의 규칙(§ '영구, 죽은 타일을 남기지 않는다')과 동일하게, 값이 없는 개별 타일도 숨긴다. */}
            {(disk.free_gb != null || disk.used_pct != null || mem.used_pct != null || dash.cert_days_remaining != null) ? (
              <DashSection title="시스템 리소스">
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
                  {/* Dashboard.jsx가 같은 필드(disk.free_gb)를 fmtNum()+단위-on-값으로 보여주는데
                      이 화면만 raw 숫자에 라벨 괄호 단위였다, 같은 표기 규칙으로 맞춘다. */}
                  {disk.free_gb != null ? <StatCard value={fmtNum(disk.free_gb) + "GB"} label="디스크 여유" /> : null}
                  {disk.used_pct != null ? (
                    <StatCard value={disk.used_pct + "%"} label="디스크 사용"
                      kind={disk.used_pct >= 85 ? "danger" : disk.used_pct >= 80 ? "warn" : undefined} />
                  ) : null}
                  {mem.used_pct != null ? (
                    <StatCard value={mem.used_pct + "%"} label="메모리 사용"
                      kind={mem.used_pct >= 90 ? "danger" : mem.used_pct >= 80 ? "warn" : undefined} />
                  ) : null}
                  {dash.cert_days_remaining != null ? (
                    <StatCard value={fmtCertDays(dash.cert_days_remaining)} label="인증서 만료"
                      kind={dash.cert_days_remaining <= 0 ? "danger" : dash.cert_days_remaining <= 30 ? "warn" : undefined} />
                  ) : null}
                </Box>
              </DashSection>
            ) : null}
            {/* build_dashboard()(app/health/service.py)는 components/counts/jobs_24h를 항상 고정된
                채워진 dict로 돌려준다, 이 Object.keys(...).length 가드는 기능적으로 결코 false가 될
                수 없다(사전 방어일 뿐). 실제 통제는 bundle 자체의 존재 여부다(위 !bundle 가드). */}
            {Object.keys(comps).length ? (
              <DashSection title="서비스 상태">
                {/* 중단·응답 없음을 빨간 배지로만 두면 조치할 곳이 없는 막다른 화면이 된다 — 다음 행동을 한 줄로 안내한다.
                    (스펙 §10: 임의 systemd 재시작 API는 제공하지 않으므로 로그 확인·담당자 재시작으로 안내한다.) */}
                {downUnits.length ? (() => {
                  // 장애 대응 중 그대로 터미널에 붙여 넣을 명령이다, 감사 로그 대상 ID와 같은 이유로
                  // (여기, Dashboard.jsx의 copyObjectId) hover 전용 선택이 아니라 눌러서 복사하는
                  // 버튼을 함께 준다.
                  const journalCmd = "journalctl -u " + downUnits.join(" -u ");
                  return (
                    <Box sx={{ mb: 2 }}>
                      <Callout tone="warn">
                        일부 서비스가 중단, 응답 없음 상태입니다. 웹에서 재시작하는 수단은 제공되지 않습니다, 서버 로그(예: <Box component="code" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{journalCmd}</Box>{" "}
                        <Link component="button" type="button" variant="body2" underline="hover" onClick={() => copyText(journalCmd).then((ok) => toast(ok ? "명령을 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}>복사</Link>
                        )를 확인하고 필요하면 담당자가 해당 서비스를 재시작하세요(저장소의 <Box component="code" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>docs/RUNBOOK.md</Box> 참고).
                      </Callout>
                    </Box>
                  );
                })() : null}
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: SERVICE_GRID }}>
                  {Object.keys(comps).map((k) => {
                    // 'unknown'(하트비트 없음/오래됨)도 상단 healthVerdict()가 이미 주의 대상으로 세는 문제다 -
                    // 배지를 무채색 그대로 두면 상단 '주의 N건' 배너와 이 타일의 심각도가 서로 어긋나 보인다.
                    const badgeKind = comps[k] === "unknown" ? "warn" : undefined;
                    // 바로 아래 '외부 연동' 카드는 클릭 가능한데 이 서비스 카드만 정적이라, 시각적으로
                    // 똑같은 두 그리드가 나란히 있어 죽은 카드를 눌러 보게 유도했다, 워커/스케줄러는
                    // Dashboard.jsx svcNav처럼 작업 큐(/jobs)로 드릴다운시킨다(웹은 드릴다운할 곳이 없어 정적 유지).
                    const dest = (k === "worker" || k === "scheduler") ? "/jobs" : null;
                    // 상단 healthVerdict() 배너, Dashboard.jsx 서비스 카드는 이 상태를 '응답 없음'이라
                    // 부른다, kit.jsx STATUS_TEXT는 'unknown'을 '알 수 없음'으로 옮겨, 같은 상태를
                    // 이 화면 안에서만 다른 한국어로 말하고 있었다(배너와 타일이 서로 모순).
                    return (
                      <StatusTile key={k} name={COMP_LABELS[k] || k}
                        onClick={dest ? () => nav(dest) : undefined}
                        ariaLabel={(COMP_LABELS[k] || k) + " 관련 작업 큐로 이동"}>
                        <Badge value={comps[k] === "unknown" ? "응답 없음" : comps[k]} kind={badgeKind} />
                      </StatusTile>
                    );
                  })}
                </Box>
              </DashSection>
            ) : null}
            <DashSection title="외부 연동">
              {/* down만이 아니라 전체 연동 상태를 보여준다, unknown도 드러나야 진단에 쓸모가 있다.
                  비활성 연동은 마지막 헬스값 대신 '비활성화'로 표기한다. */}
              {/* 서비스 이름은 대시보드와 같은 serviceLabel()로 표기해 두 화면이 같은 연동을 다르게 부르지 않게 한다.
                  활성인데 아직 헬스체크 이력이 없으면(last_health null) 무의미한 '알 수 없음' 대신 '미점검'으로 표시한다.
                  '서비스 상태'와 같은 '지금 이 순간' 스냅샷이라 바로 옆에 둔다, 이 페이지 자신이 선언한
                  '스냅샷 먼저, 이력 나중' 원칙(아래 '현재 리소스' 주석)을 이 섹션에도 실제로 지킨다. */}
              {Object.keys(integrations).length ? (
                <Box sx={{ display: "grid", gap: 2, alignItems: "start", gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) minmax(0, 24rem)" } }}>
                  <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: SERVICE_GRID }}>
                    {Object.keys(integrations).map((k) => {
                      const it = integrations[k] || {};
                      // last_health는 NOT NULL이라 'unknown'으로 채워져 온다(models.py), 'it.last_health ||'
                      // 폴백은 결코 타지 않아 갓 만든/미점검 연동이 '알 수 없음'으로 새고 있었다.
                      // 'unknown'(과 만일의 빈 값)을 명시적으로 '미점검'으로 표기한다.
                      const raw = it.last_health;
                      const val = it.enabled === false ? "disabled" : (!raw || raw === "unknown") ? "미점검" : raw;
                      // 다른 화면(Dashboard.jsx의 서비스 카드)과 같은 방식으로 클릭 가능한 카드로 만든다 -
                      // 이름, 상태 배지만 보여주고 조치할 곳이 없는 막다른 카드로 남기지 않는다.
                      return (
                        <StatusTile key={k} name={serviceLabel(k)} onClick={() => nav("/integrations")}
                          ariaLabel={serviceLabel(k) + " 연동 관리로 이동"}>
                          <Badge value={val} />
                        </StatusTile>
                      );
                    })}
                  </Box>
                  {/* 연동이 열 개를 넘는 배포에서는 카드를 하나씩 세는 것보다 구성비가 빠르다. */}
                  <Card sx={{ p: 2.5 }}>
                    <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>연동 상태 구성</Typography>
                    <Donut segments={integrationMix(integrations)} unit="개" centerLabel="연동" emptyLabel="연동 정보 없음" />
                  </Card>
                </Box>
              ) : (
                // dash.integrations(위 integrations)는 Integration 테이블 전 행을 무조건 담고(app/health/
                // service.py build_dashboard), integration_errors는 그중 down/degraded만 거른 부분집합이다 -
                // 그래서 integrations가 비어 있으면 그 부분집합도 항상 비어 있다. '등록된 연동은 없지만
                // 오류만 있는' 중간 분기는 절대 일어나지 않아 제거하고, 곧장 빈 상태로 간다.
                <Card>
                  <EmptyState title="등록된 외부 연동이 없습니다" help="‘외부 연동’ 관리 화면에서 서비스를 등록하면 여기에 상태가 표시됩니다."
                    art="search"
                    relatedLink={{ href: "#/integrations", label: "외부 연동으로 이동" }} />
                </Card>
              )}
            </DashSection>
            {/* '현재 리소스'는 '시스템 리소스', '서비스 상태'와 같은 '지금 이 순간' 스냅샷이라, 이전엔
                오류, 감사 이력(시간을 두고 훑는 섹션들) 사이에 끼어 있어 위쪽 두 섹션과 한눈에 묶여
                읽히지 않았다, 같은 성격의 섹션끼리 먼저 모아 두고, 이력성 섹션은 그 아래로 둔다. */}
            {Object.keys(counts).length ? (
              <DashSection title="현재 리소스">
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
                  {/* Dashboard.jsx의 동일한 인벤토리 타일과 똑같이 해당 레지스트리로 드릴다운한다 -
                      이 화면은 admin/system_admin 전용이라 세 화면 모두 항상 도달 가능하다(대시보드처럼
                      역할별 canGo 분기가 필요 없다). */}
                  <StatCard value={fmtNum(counts.active_workflows)} label="활성 워크플로" onClick={() => nav("/workflows")} />
                  <StatCard value={fmtNum(counts.active_schedules)} label="활성 스케줄" onClick={() => nav("/schedules")} />
                  <StatCard value={fmtNum(counts.runners)} label="등록된 러너" onClick={() => nav("/runners")} />
                </Box>
              </DashSection>
            ) : null}
            {Object.keys(jobs24).length ? (
              <DashSection title="작업 지표 (최근 24시간)">
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
                  <StatCard value={fmtNum(jobs24.total)} label="처리 요청" />
                  {/* Dashboard.jsx와 같은 지표, 분모는 24시간 내 종료된(성공, 실패, 취소) 작업만이며 아직
                      끝나지 않은 대기/실행 중 작업은 제외된다(app/health/service.py finished_24h). 라벨을
                      Dashboard.jsx와 동일하게 맞춰 같은 값이 화면마다 다른 의미로 읽히지 않게 한다. */}
                  <StatCard value={jobs24.success_rate_pct != null ? jobs24.success_rate_pct + "%" : "-"} label="성공률(종료 작업 대비)"
                    kind={jobs24.success_rate_pct == null ? undefined : jobs24.success_rate_pct >= 95 ? "ok" : jobs24.success_rate_pct >= 80 ? "warn" : "danger"} />
                  {/* raw seconds 대신 Dashboard.jsx의 fmtProcessingTime()을 그대로 재사용한다, 큰 초 값이
                      굵은 KPI 타일에서 스캔하기 어렵다는 이유로 Dashboard.jsx가 이미 고친 문제를 이
                      화면만 다시 겪고 있었다(같은 필드 avg_processing_seconds). */}
                  <StatCard value={fmtProcessingTime(jobs24.avg_processing_seconds)} label="평균 처리" />
                  {/* queued/failed_open은 24시간 창이 아니라 시점 백로그 누계다(백엔드가 시간 필터 없이 계산).
                      '24시간' 프레임과 섞여 오래된 백로그가 오늘 실패처럼 읽히던 문제, 라벨에 '(전체)'를 붙여 구분한다.
                      Dashboard의 동일 타일처럼 /jobs로 드릴다운해, 문제를 보여주기만 하고 조치할 곳이 없던 막다른
                      타일을 없앤다(이 화면은 admin/system_admin 전용이라 /jobs는 항상 도달 가능). */}
                  <StatCard value={fmtNum(jobs24.queued != null ? jobs24.queued : 0)} label="대기 중(전체)"
                    kind={jobs24.queued > 0 ? "warn" : undefined} onClick={() => nav("/jobs")} />
                  <StatCard value={fmtNum(jobs24.failed_open != null ? jobs24.failed_open : 0)} label="미해결 실패(전체)"
                    kind={jobs24.failed_open > 0 ? "danger" : undefined} onClick={() => nav("/jobs")} />
                </Box>
              </DashSection>
            ) : null}
            <DashSection title="백업">
              {/* 대시보드 백업 카드(Dashboard.jsx)와 동일하게 '백업 관리'로 이동할 수단을 준다 -
                  '마지막 백업: 없음'/실패를 보고도 조치할 곳이 없는 막다른 카드가 되지 않게 한다(백업 화면은 이 역할이 도달 가능). */}
              <Card sx={{ p: 2.5, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
                {/* component="div" — 안에 Badge(Chip은 <div>)가 들어간다(Dashboard.jsx 백업 카드와 같은 이유). */}
                <Typography component="div" variant="body2" sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
                  마지막 백업: {dash.last_backup_at ? fmtDateTime(dash.last_backup_at) : "없음"}
                  {dash.last_backup_status ? <Badge value={dash.last_backup_status} /> : null}
                  {/* Dashboard.jsx 백업 카드와 같은 나이 배지 — 성공 이력은 있지만 오래됐으면(계속 실패 중일 수
                      있음) 두 화면이 같은 임계값(BACKUP_STALE_DAYS)으로 같은 신호를 보이게 한다. */}
                  {(() => { const age = dash.last_backup_at ? daysSince(dash.last_backup_at) : null; return age != null && age > BACKUP_STALE_DAYS ? <Badge value={Math.floor(age) + "일 전"} kind={age > BACKUP_STALE_DAYS * 2 ? "danger" : "warn"} /> : null; })()}
                </Typography>
                <Button variant={dash.last_backup_at ? "default" : "primary"} size="sm" onClick={() => nav("/backup")}>백업 관리</Button>
              </Card>
            </DashSection>
            <DashSection title="최근 작업 오류"
              action={<Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/jobs")}>작업 큐에서 보기 →</Link>}>
              <Card>
                {jobErrors.length ? (
                  <>
                    {/* 20건이 한 시간에 몰렸는지 두 달에 흩어져 있는지는 목록만 훑어서는 안 보인다.
                        errorBuckets()가 3건 미만·같은 순간이면 null을 주므로, 없는 추세를 그리지 않는다. */}
                    {errorDist ? (
                      <Box sx={{ mb: 2.5 }}>
                        <Sparkline
                          points={errorDist.counts} color="error" height="3.5rem"
                          summary={"최근 실패 " + errorDist.n + "건의 발생 분포, "
                            + fmtDateTime(new Date(errorDist.from).toISOString()) + " ~ "
                            + fmtDateTime(new Date(errorDist.to).toISOString())
                            + " (전체 실패 추세가 아니라 이 목록에 담긴 건들의 분포입니다)"} />
                      </Box>
                    ) : null}
                    <LogList>
                      {/* 이 목록은 60초마다 자동 재수집돼 순서가 바뀔 수 있다 — 아래 '최근 주요 변경'
                          목록과 같은 이유로 index 대신 안정적인 합성 키를 쓴다(잡 id가 번들에 없어
                          시각+타입+인덱스로 최대한 안정화). */}
                      {jobErrors.map((e, i) => (
                        <LogRow key={e.at + "|" + e.job_type + "|" + i} when={fmtDateTime(e.at)} what={e.error || "-"}>
                          {/* 원시 영어 enum(chat_message 등)이 한글 콘솔에 새지 않게 한국어로 변환(미매핑은 원값 폴백). */}
                          <Typography variant="body2" color="text.secondary">{jobTypeKo(e.job_type)}</Typography>
                        </LogRow>
                      ))}
                    </LogList>
                  </>
                ) : <Note sx={{ mt: 0 }}>최근 실패한 작업이 없습니다.</Note>}
              </Card>
            </DashSection>
            {/* '최근 작업 오류'(위)와 짝인 섹션, 비었다고 화면에서 통째로 사라지면 '아직 안 불러왔나'와
                '실제로 최근 주요 변경이 없다'를 구분할 수 없다. 형제 섹션과 같은 방식으로 항상 렌더하고
                빈 목록엔 안심시키는 안내 문구를 둔다. */}
            {/* Dashboard.jsx의 동일 섹션, 바로 위 '최근 작업 오류' 섹션과 같은 방식으로 전체 감사
                로그(/audit)로 가는 딸린 링크를 준다, 이전엔 이 섹션만 더 볼 곳으로 가는 길이 없었다. */}
            <DashSection title="최근 주요 변경"
              action={<Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/audit")}>전체 보기 →</Link>}>
              <Card>
                {recentAudit.length ? (
                  <LogList>
                    {recentAudit.map((a) => (
                      <LogRow key={a.created_at + "|" + (a.object_id || "") + "|" + a.action}
                        when={fmtDateTime(a.created_at)}
                        what={actionKo(a.action) + " (" + (a.actor || "시스템") + ")"}>
                        {/* Dashboard.jsx의 동일 섹션과 같은 방식, title 툴팁은 터치, 스크린리더에서 안
                            뜨므로, 대상 ID가 있으면 눌러서 전체 값을 복사할 수 있는 버튼으로 둔다
                            (예전엔 여기만 비인터랙티브 <span>이라 8자로 잘린 ID를 다시 알아낼 방법이 없었다). */}
                        {a.object_id ? (
                          <Link component="button" type="button" variant="body2" underline="hover" color="text.secondary" title={a.object_id}
                            aria-label={objKo(a.object_type) + " 전체 ID 복사: " + a.object_id}
                            onClick={() => copyText(a.object_id).then((ok) => toast(ok ? "ID를 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}
                            sx={{ textAlign: "left" }}>
                            {objKo(a.object_type)}, {shortId(a.object_id)}
                          </Link>
                        ) : <Typography variant="body2" color="text.secondary">{objKo(a.object_type)}</Typography>}
                      </LogRow>
                    ))}
                  </LogList>
                ) : <Note sx={{ mt: 0 }}>최근 주요 변경 이력이 없습니다.</Note>}
              </Card>
            </DashSection>
            <DashSection title="원본 자료">
              {/* 다른 모든 섹션과 같은 Card로 감싸 원시 브라우저 기본 <details> 외형(카드 없음, 테두리 없음)이
                  이 페이지에서만 미완성처럼 보이던 문제를 없앤다. */}
              <Card>
                <details>
                  <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700, fontSize: "0.9375rem" }}>원본(JSON) 보기</Box>
                  <Box component="pre" aria-label="진단 번들 원본 JSON"
                    sx={{
                      m: 0, mt: 2, p: 2, whiteSpace: "pre-wrap", wordBreak: "break-word",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.75rem", lineHeight: 1.5,
                      maxHeight: "60vh", overflow: "auto", bgcolor: "background.default", borderRadius: 2,
                    }}>
                    {text}
                  </Box>
                </details>
              </Card>
            </DashSection>
          </Box>
        ) : q.isFetched ? (
          // 자동 수집 전 첫 프레임에 이 안내가 번쩍이던 문제, 아직 fetch 전이면(아래 폴백) 스켈레톤을 보여
          // '수집을 눌러라'는 안내가 앱이 이미 자동으로 하는 일을 지시하지 않게 한다.
          <Card><Note sx={{ mt: 0 }}>‘진단 수집’을 눌러 현재 시스템 상태(서비스 상태, 디스크, 메모리, 인증서, 작업 오류)를 확인하세요.</Note></Card>
        ) : <Card><Skeleton lines={4} /></Card>}
    </Box>
  );
}

/* 유지보수 — 유지보수 모드(maintenance_mode 설정)를 켜고 끈다. 켜면 사용자 쓰기 작업이 차단된다.
 * 사용자에게 보일 점검 공지(maintenance_message)도 여기서 확인·수정한다. 쓰기는 admin/system_admin.
 *
 * 이 화면은 operator/auditor(읽기 전용 역할)도 들어온다(App.jsx RequireRole). 그 역할에게 쓰기
 * 컨트롤을 **숨기지 않는다** — 보이되 비활성이고, 왜 비활성인지 옆에 글자로 남긴다. 숨기면
 * '이 앱엔 그런 기능이 없다'로 읽혀, 권한을 받으면 할 수 있는 일을 영영 모른 채로 지나간다. */
export function Maintenance() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const auth = useAuth();
  const canWrite = isWriteRole(auth.data && auth.data.role);
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/admin/settings"), retry: false });
  // 이 값(refetchOnWindowFocus:false·staleTime 30s)이 언제 것인지 안 보이면, 탭을 오래 열어 둔
  // 관리자가 30초 넘게 낡은 on/off 상태를 '지금'으로 오해할 수 있다 — Dashboard.jsx처럼 마지막
  // 갱신 시각을 옆에 남긴다.
  const updated = q.dataUpdatedAt ? fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) : null;
  // GET /api/admin/settings 응답은 {settings:{maintenance_mode:{value,...}}}로 한 겹 감싸져 있다.
  const settings = (q.data && q.data.settings) || {};
  const mm = settings.maintenance_mode || null;
  const on = mm ? (mm.value === true || mm.value === "true") : false;
  const serverMsg = settings.maintenance_message ? (settings.maintenance_message.value || "") : "";
  const [showVersions, setShowVersions] = React.useState(false);
  const [showModeVersions, setShowModeVersions] = React.useState(false); // 유지보수 모드 on/off 변경 기록
  // 초안은 서버 값으로 '지연 초기화'한다 — ['settings'] 캐시가 이미 따뜻할 때(설정 화면 방문 후·재방문)
  // ""로 초기화하면 seeding 이펙트 가드가 통과되지 않아 편집기가 빈 채로 뜨던 버그가 있었다.
  const [msg, setMsg] = React.useState(() => serverMsg);
  // 서버 값이 바뀔 때 로컬 초안을 덮어쓰되, 사용자가 편집 중(더티)이면 그대로 둔다 —
  // 다른 관리자가 공지를 바꾼 뒤 창 포커스로 refetch되면 작성 중이던 초안이 조용히 날아가던 문제.
  //
  // 갱신 함수 안에서 ref를 '읽으면' 안 된다. setMsg(fn)의 fn은 호출 시점이 아니라 **다음 렌더에서**
  // 실행되는데, 그때는 바로 아랫줄의 prevServerRef.current = serverMsg가 이미 끝난 뒤라
  // (prev === prevServerRef.current) 비교가 항상 거짓이 된다. 그래서 이 화면은 서버 공지를 한 번도
  // 초안에 싣지 못했다: 편집기는 늘 빈 채로 뜨고, 빈 초안 vs 서버 값 차이 때문에 '되돌리기'만
  // 항상 떠 있었으며, 관리자는 현재 공지 문구를 이 화면에서 볼 수 없었다(2026-08 QA 캡처로 확인).
  // 비교 기준값을 지역 const로 먼저 붙잡아 실행 시점과 무관하게 만든다.
  const prevServerRef = React.useRef(serverMsg);
  React.useEffect(() => {
    const prevServer = prevServerRef.current;
    prevServerRef.current = serverMsg;
    setMsg((prev) => (prev === prevServer ? serverMsg : prev));
  }, [serverMsg]);

  const toggle = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_mode", { method: "PUT", body: { value: val } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); toast("유지보수 모드를 변경했습니다.", "success"); },
    onError: (e) => toast(e.message, "error"),
  });
  const saveMsg = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_message", { method: "PUT", body: { value: val } }),
    // 저장 시작 시 이전 '미리 검증' 결과를 지운다 — 안 그러면 검증 통과 뒤 저장하면 이미 저장된
    // 값 옆에 낡은 '검증 통과' 배너가 계속 남고, 검증 없이 바로 저장해 실패하면 방금 실패와
    // 무관한 옛 검증 결과가 뒤섞여 어느 쪽이 지금 상태인지 알 수 없다.
    onMutate: () => { setMsgChecked(""); setMsgCheckErr(""); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); toast("점검 공지를 저장했습니다.", "success"); },
    // 실패는 사라지는 토스트만이 아니라 미리 검증 실패와 같은 자리에도 남긴다 —
    // 필드 바로 옆에 지속되는 이유를 남겨 토스트를 놓쳐도 원인을 알 수 있게 한다.
    onError: (e) => { setMsgCheckErr(e.message); toast(e.message, "error"); },
  });
  // Settings.jsx의 다른 설정들은 '미리 검증'(dry-run)을 제공하는데 이 두 키(같은 PUT 엔드포인트)만
  // 여기 전용 화면이라 그 수단이 없었다 — 같은 백엔드 능력을 여기서도 노출한다.
  const dryRunMsg = useMutation({
    mutationFn: (val) => api("/api/admin/settings/maintenance_message/dry-run", { method: "POST", body: { value: val } }), });
  const [msgChecked, setMsgChecked] = React.useState("");
  const [msgCheckErr, setMsgCheckErr] = React.useState("");
  async function onCheckMsg() {
    setMsgChecked(""); setMsgCheckErr("");
    try { await dryRunMsg.mutateAsync(msg); setMsgChecked("검증 통과, 저장할 수 있습니다."); }
    catch (e) { setMsgCheckErr(e.message); }
  }
  function changeMsg(next) { setMsg(next); setMsgChecked(""); setMsgCheckErr(""); }
  async function onToggle() {
    // confirm 문구가 실제로 적용될 전환과 어긋나면 안 된다, 예전엔 클릭 시점의(낡을 수 있는) on으로
    // 먼저 문구("켤까요?"/"끌까요?")를 만들고, 사용자가 확인을 누른 뒤에야 서버 최신값을 다시 조회해
    // 뒤집었다. 그 사이(대화상자가 열려 있던 몇 초) 다른 관리자가 이미 상태를 바꿨다면, 대화상자는
    // "켤까요?"라고 말해 놓고 실제로는 끄는(반대) 동작이 조용히 실행될 수 있었다, 대화상자를 열기
    // '전에' 먼저 최신 상태를 확인해, 그 값 하나로 문구와 실제 전환을 항상 일치시킨다.
    const fresh = await q.refetch();
    // refetch()는 실패해도 throw하지 않고 { isError: true, data: undefined }로 조용히 해결된다 -
    // 이 확인을 건너뛰면(예전 코드) 네트워크 blip 때 fresh.data가 undefined가 돼 freshOn이 클로저의
    // 낡은 on으로 폴백하면서도 사용자에게는 "최신 상태 확인"이 성공한 것처럼 그대로 진행됐다.
    if (fresh.isError) { toast("현재 상태를 확인하지 못해 변경을 취소했습니다. 다시 시도하세요.", "error"); return; }
    const freshMm = fresh.data && fresh.data.settings && fresh.data.settings.maintenance_mode;
    const freshOn = freshMm ? (freshMm.value === true || freshMm.value === "true") : on;
    const ok = await confirm(freshOn ? "유지보수 모드를 끌까요?" : "유지보수 모드를 켤까요? 사용자 쓰기가 차단됩니다.", { danger: !freshOn });
    if (!ok) return;
    toggle.mutate(!freshOn);
  }
  const dirty = msg !== serverMsg;
  // 비활성 버튼의 '왜'를 스크린리더에도 연결한다 — 눈으로는 옆 문장이 보이지만, 연결이 없으면
  // 보조기기는 '비활성 버튼'까지만 읽고 이유는 영영 읽지 않는다.
  const lockedDescribedBy = canWrite ? undefined : "maint-locked-reason";

  return (
    <Box>
      {/* 유지보수 모드는 다른 admin이 지금 이 순간 켜고/끌 수 있는 상태다, Diagnostics처럼 자동
          폴링을 걸진 않되(쓰기가 잦은 화면은 아니다), 최소한 수동 새로고침은 준다. QueryClient가
          refetchOnWindowFocus:false, staleTime 30s라 아무 조작도 없이 놔두면 30초 넘게 낡은 값이
          '지금 상태'처럼 보일 수 있었다(main.jsx). */}
      <PageHeader area="운영" title="유지보수"
        actions={<>
          {updated ? (
            <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
              {updated} 기준
            </Typography>
          ) : null}
          <Button size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>{q.isFetching ? "새로고침 중…" : "새로고침"}</Button>
        </>} />
      {/* TanStack Query v5에서 isLoading은 '최초' 로딩만 true다, 캐시된 데이터가 이미 있는 상태에서
          (예: 이 화면의 '새로고침' 버튼을 눌렀다가) 재조회가 실패하면 isLoading은 false, isError만
          true가 된다. 그걸 그대로 ErrorState로 바꿔치기하면 방금까지 보이던 켜짐/꺼짐 토글과 공지
          textarea가 통째로 사라진다, 캐시된 데이터가 하나도 없을 때만 전체화면 ErrorState를 쓴다. */}
      {(q.isLoading || (q.isError && !q.data)) ? (
        q.isLoading ? <Card><Skeleton lines={2} /></Card> : <ErrorState error={q.error} onRetry={() => q.refetch()} />
      )
        : (
          <Box>
            {/* 새로고침이 실패했지만 이전 값이 남아 있는 경우, 화면을 지우지 않고 낡았다는 사실만 알린다. */}
            {q.isError ? (
              <Box sx={{ mb: 3 }} role="status">
                <Callout tone="warn">
                  최신 상태를 불러오지 못했습니다, 아래 값은 이전에 불러온 자료입니다.{" "}
                  <Link component="button" type="button" variant="body2" underline="hover" onClick={() => q.refetch()}>다시 시도</Link>
                </Callout>
              </Box>
            ) : null}
            {/* 유지보수 모드가 켜져 있으면 사용자 쓰기가 차단되는 위험 상태다, 페이지 상단에 눈에 띄는 배너로 분명히 한다
                (현재 상태 배지만으론 이 화면에 돌아온 관리자가 한눈에 알기 어려웠다). */}
            {on ? <Box sx={{ mb: 3 }} role="status"><Callout tone="warn">현재 유지보수 모드가 켜져 있습니다, 사용자 쓰기(티켓 생성, 변경 등)가 차단되고 있습니다. 점검이 끝나면 아래에서 꺼 주세요.</Callout></Box> : null}
            <Card sx={{ p: 3, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 3, flexWrap: "wrap", mb: 4 }}>
              <Box sx={{ minWidth: 0, flex: "1 1 20rem" }}>
                <Typography component="div" sx={{ display: "flex", alignItems: "center", gap: 1, fontWeight: 750, mb: 1 }}>
                  현재 상태 <Badge value={on ? "maintenance" : "up"} />
                </Typography>
                <Note sx={{ mt: 0 }}>유지보수 모드를 켜면 사용자 쓰기 작업(티켓 생성, 변경 등)이 일시 차단됩니다. 점검이 끝나면 다시 끄세요.</Note>
                {/* 쓰기 권한이 없어 비활성인 이유 — 이 한 줄이 아래 두 버튼(모드 전환·공지 저장 계열)의
                    aria-describedby 대상이다. 버튼을 숨기는 대신 이유를 보여 준다. */}
                {!canWrite ? (
                  <Typography id="maint-locked-reason" variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    유지보수 모드 변경은 {NO_WRITE_REASON}
                  </Typography>
                ) : null}
                {/* 점검 공지에는 '버전 기록'이 있는데 정작 더 위험한(앱 전체 쓰기를 막는) 유지보수 모드
                    토글 자체는 누가 언제 켜고 껐는지 볼 곳이 없었다, 백엔드가 config_versions에 이미
                    기록하므로 같은 SettingVersions UI를 maintenance_mode에도 붙인다. */}
                <Box sx={{ mt: 1 }}>
                  <Button variant="ghost" size="sm" onClick={() => setShowModeVersions(true)}>변경 기록(켜고 끈 이력)</Button>
                </Box>
              </Box>
              <Button variant={on ? "primary" : "danger"} disabled={!canWrite || toggle.isPending} onClick={onToggle}
                aria-describedby={lockedDescribedBy}>
                {toggle.isPending ? "변경 중…" : on ? "유지보수 모드 끄기" : "유지보수 모드 켜기"}
              </Button>
            </Card>

            <DashSection title="점검 공지 (사용자에게 표시되는 안내)">
              <Card>
                <Note sx={{ mt: 0 }} id="maint-msg-desc">유지보수 모드가 켜져 있을 때 사용자가 보게 되는 안내 문구입니다.</Note>
                {/* 위쪽 유지보수 모드 토글 카드에만 '관리자, 시스템 관리자만' 안내가 붙어 있어, 이 섹션만
                    보는(특히 스크린리더) 사용자는 입력이 왜 잠겨 있는지 알 방법이 없었다, 여기도 남긴다. */}
                {!canWrite ? (
                  <Typography id="maint-msg-locked" variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                    점검 공지 수정은 {NO_WRITE_REASON}
                  </Typography>
                ) : null}
                {/* 공지는 사용자에게 보이는 산문이라 JSON 편집기용 monospace를 쓰지 않는다.
                    설명·유효성 힌트를 aria-describedby로 입력에 프로그래매틱하게 연결한다(이전엔 시각적으로만
                    인접해 있고 연결은 안 돼 있었다 — 이 필드가 켜지면 앱 전체 쓰기를 막는 공지라
                    스크린리더 사용자에게 특히 중요하다).
                    /maintenance는 operator, auditor(읽기 전용 역할)도 볼 수 있게 열려 있다(App.jsx
                    RequireRole), disabled는 그 방문자에게서 선택, 복사는 물론 탭/스크린리더 접근까지
                    막는다(네이티브 disabled 필드는 포커스 순서에서 빠진다). readOnly는 편집만 막고
                    선택, 복사, 포커스 이동은 그대로 허용한다. */}
                <TextField
                  multiline minRows={4} fullWidth value={msg}
                  error={canWrite && !msg.trim()}
                  onChange={(e) => { if (canWrite) changeMsg(e.target.value); }}
                  InputProps={{ readOnly: !canWrite }}
                  inputProps={{
                    "aria-label": "점검 공지",
                    "aria-describedby": "maint-msg-desc"
                      + (canWrite && !msg.trim() ? " maint-msg-help" : "")
                      + (!canWrite ? " maint-msg-locked" : ""),
                  }}
                />
                {canWrite && !msg.trim() ? (
                  <Typography id="maint-msg-help" variant="caption" color="error.main" sx={{ display: "block", mt: 0.5 }}>
                    공지 내용을 입력하세요. 빈 공지는 저장할 수 없습니다.
                  </Typography>
                ) : null}
                {msgChecked ? <Box sx={{ mt: 2 }} role="status"><Callout tone="success">{msgChecked}</Callout></Box> : null}
                {msgCheckErr ? (
                  <Typography role="alert" variant="body2" color="error.main" sx={{ mt: 2 }}>{msgCheckErr}</Typography>
                ) : null}
                {/* 폼 작업줄 — 앱 공통 우측 정렬. 쓰기 권한이 없어도 버튼을 지우지 않는다:
                    비활성 + 위의 이유 문구(aria-describedby)로 '있지만 지금은 못 누른다'를 그대로 보여 준다.
                    (예전엔 '미리 검증'만 canWrite일 때 렌더돼, 읽기 전용 역할에겐 그 기능의 존재 자체가 사라졌다.) */}
                <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, flexWrap: "wrap", mt: 2 }}>
                  <Button disabled={!canWrite || dryRunMsg.isPending} onClick={onCheckMsg} aria-describedby={lockedDescribedBy}>
                    {dryRunMsg.isPending ? "검증 중…" : "미리 검증"}
                  </Button>
                  <Button variant="primary" disabled={!canWrite || !dirty || !msg.trim() || saveMsg.isPending} onClick={() => saveMsg.mutate(msg)}
                    aria-describedby={lockedDescribedBy}>
                    {saveMsg.isPending ? "저장 중…" : "공지 저장"}
                  </Button>
                  {dirty ? <Button disabled={saveMsg.isPending} onClick={() => changeMsg(serverMsg)}>되돌리기</Button> : null}
                  {/* 다른 설정과 달리 점검 공지는 설정 표에서 제외돼 버전 기록, 롤백이 닿지 않았다, 여기서 같은 UI를 재사용해 제공한다. */}
                  <Button variant="ghost" onClick={() => setShowVersions(true)}>버전 기록</Button>
                </Box>
              </Card>
            </DashSection>
          </Box>
        )}
      {showVersions ? (
        <SettingVersions settingKey="maintenance_message" label="점검 공지" canWrite={canWrite}
          onClose={() => setShowVersions(false)} onRolledBack={() => setShowVersions(false)} />
      ) : null}
      {showModeVersions ? (
        <SettingVersions settingKey="maintenance_mode" label="유지보수 모드" canWrite={canWrite}
          onClose={() => setShowModeVersions(false)} onRolledBack={() => setShowModeVersions(false)} />
      ) : null}
    </Box>
  );
}
