import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime, actionKo, objKo } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { PageHeader, Card, Badge, StatCard, Skeleton, ErrorState, Button, Callout, useToast } from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { DashSection, StatusTile, Note, STAT_GRID, SERVICE_GRID, HEADLINE_GRID } from "../ui/adminKit.jsx";
import { serviceLabel, daysSince, BACKUP_STALE_DAYS, fmtNum, fmtProcessingTime, fmtCertDays, failedOpenAgeLabel } from "./ops/opsHelpers.js";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { Donut } from "../ui/charts/Donut.jsx";

/* 이 화면의 **모든 숫자**의 출처표는 docs/DASHBOARD_METRICS.md 에 있다.
 * 지표마다 (어느 질의에서 오는가 / 어떤 시점 기준인가 / 범위를 지나는가 / 0과 없음을
 * 구분하는가)를 적어 뒀다. 타일을 하나 더할 때 그 네 칸을 못 채우면 그 숫자는 아직
 * 화면에 올릴 준비가 안 된 것이다 — 기준을 설명할 수 없는 숫자는 결국 아무도 안 본다. */

// 대상 화면별로 접근 가능한 역할(서버 RBAC와 일치). 프런트는 표시만 조정하고 판단은 서버가 한다.
// 볼 수 없는 화면으로 보내면 403 막다른 길이 되므로, 링크는 역할에 맞을 때만 활성화한다.
const NAV_ROLES = {
  "/jobs": ["operator", "admin", "system_admin"], "/audit": ["admin", "system_admin", "auditor"], "/diagnostics": ["admin", "system_admin"], // 백업 조회(GET)는 백엔드가 READ_ROLES에 허용하고 App.jsx 라우트/NAV도 동일하게 열려 있다.
  // (백업 실행 등 쓰기 액션만 registry에서 system_admin으로 게이트, 조회 링크는 막다른 길이 아니다.)
  "/backup": ["operator", "admin", "system_admin", "auditor"], "/integrations": ["operator", "admin", "system_admin", "auditor"],
  // 유지보수 화면은 읽기 전용 역할(operator/auditor)에게도 열려 있다(AdminRoutes.jsx의 RequireRole과 동일).
  // 여기 적어 두지 않으면 canGo가 무조건 true를 주는데, 그 '통과'가 규칙을 확인한 결과인지
  // 목록에서 빠뜨린 결과인지 코드만 봐서는 구별되지 않는다.
  "/maintenance": ["operator", "admin", "system_admin", "auditor"],
};
export function canGo(path, role) {
  const allowed = NAV_ROLES[path];
  return !allowed || (role != null && allowed.includes(role));
}

// 대상 ID를 8자로 줄여 보여줄 때, 줄였다는 시각적 신호(…)를 남긴다 — 그냥 잘라내면 '이게 전체
// 값'처럼 보여 그대로 다른 화면(감사 로그 필터 등)에 잘못 붙여넣기 쉽다.
function shortId(id) {
  const s = String(id);
  return s.length > 8 ? s.slice(0, 8) + "…" : s;
}
function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
  return Promise.reject(new Error("copy unsupported"));
}

/* 서비스 상태 맵(정상/중단/응답 없음/비활성화) → 도넛 조각.
 * 연동이 열 개를 넘어가면 카드 열한 장을 눈으로 세는 것보다 '정상 8, 중단 1'이 훨씬 빠르다.
 * 백엔드가 실제로 기록하는 값은 up/down/unknown뿐이지만(app/integrations/models.py), 그 밖의
 * 값이 오면 조용히 사라지지 않도록 '기타'로 모은다 — 조각 합계는 항상 카드 수와 같아야 한다. */
export function serviceMix(services) {
  const vals = Object.values(services || {});
  const count = (fn) => vals.filter(fn).length;
  const up = count((v) => v === "up");
  const down = count((v) => v === "down");
  const unknown = count((v) => v === "unknown" || v == null);
  const disabled = count((v) => v === "disabled");
  const other = vals.length - up - down - unknown - disabled;
  return [
    { label: "정상", value: up, color: "ok" },
    { label: "중단", value: down, color: "danger" },
    { label: "응답 없음", value: unknown, color: "warn" },
    { label: "비활성화", value: disabled, color: "neutral" },
    { label: "기타", value: other > 0 ? other : 0, color: "info" },
  ];
}

/* 머리 지표 다섯 — **맨 위 한 줄에서 끝나는 질문들** (6단계, 기준 목업 구조).
 *
 * 예전에는 같은 값들이 여섯 구역에 흩어져 있어, "지금 괜찮은가" 를 알려면 화면을 끝까지
 * 스크롤하며 여섯 번 찾아야 했다. 운영 화면에서 그건 매일 반복되는 비용이다.
 *
 * **없는 지표를 지어내지 않는다.** 기준 목업의 다섯(러너 8/8·워크플로·성공률·지연 작업·
 * 디스크) 중 '러너 온라인' 에 해당하는 값을 우리는 러너 단위로 갖고 있지 않다 — 대신
 * 이미 계산하는 **서비스 정상/전체**를 쓴다. 같은 질문("전부 떠 있나")에 답하는 값이고,
 * 옆의 도넛과 같은 `serviceMix()` 를 쓰므로 **두 곳이 다른 말을 할 수 없다.**
 *
 * 아래 구역들을 지우지 않는다. 이 줄은 요약이고 그쪽이 상세다 — 여기서 이상한 값을 보면
 * 눌러서 그 구역/화면으로 내려간다(모든 타일에 이동 대상이 있다).
 */
export function headlineStats({ services, counts, jobs, disk, goto, jobsNote, diagTo, diagNote }) {
  const mix = serviceMix(services);
  const byLabel = Object.fromEntries(mix.map((m) => [m.label, m.value]));
  const total = mix.reduce((a, m) => a + m.value, 0);
  const down = byLabel["중단"] || 0;
  const rate = jobs.success_rate_pct;
  const usedPct = (disk || {}).used_pct;

  return [
    {
      key: "services",
      value: total ? `${byLabel["정상"] || 0} / ${total}` : "-",
      label: "서비스 정상",
      kind: down > 0 ? "danger" : total ? "ok" : undefined,
      to: null,
    },
    { key: "workflows", value: fmtNum((counts || {}).active_workflows), label: "활성 워크플로", to: "/workflows" },
    {
      key: "rate",
      value: rate != null ? rate + "%" : "-",
      label: "24시간 성공률" + jobsNote,
      kind: rate == null ? undefined : rate >= 95 ? "ok" : rate >= 80 ? "warn" : "danger",
      to: "/jobs",
    },
    {
      key: "failed",
      value: fmtNum(jobs.failed_open != null ? jobs.failed_open : 0),
      label: "미해결 실패 작업" + failedOpenAgeLabel(jobs) + jobsNote,
      kind: (jobs.failed_open || 0) > 0 ? "warn" : undefined,
      to: "/jobs",
    },
    {
      key: "disk",
      value: usedPct != null ? usedPct + "%" : "-",
      label: "디스크 사용" + diagNote,
      kind: usedPct == null ? undefined : usedPct >= 90 ? "danger" : usedPct >= 80 ? "warn" : undefined,
      to: diagTo,
    },
  ];
}


/* ────────────────────────────────────────────────────────────────────────────
 * 내 업무 구역 (8단계) — 이 화면은 지금까지 **운영 지표만** 있었다.
 *
 * 잡 큐·하트비트·디스크는 "서버가 괜찮은가"에 답하지만 "내가 지금 뭘 놓치고 있나"에는
 * 답하지 않는다. 그 답을 찾으려면 프로젝트·내 티켓·스프린트 화면을 따로 돌아야 했다.
 *
 * **새 계산을 만들지 않는다.** 숫자는 전부 서버가 기존 재료로 조립해서 준다
 * (GET /api/home/work-dashboard → app/home/work.py). 화면이 다시 세면 같은 사실이 두 벌이
 * 되고, 언젠가 서버와 화면이 다른 말을 한다.
 *
 * **질의를 따로 두는 이유**: 운영 지표(/api/admin/dashboard)와 소스가 다르다. 한 질의에
 * 묶으면 잡 큐가 죽은 날 내 업무도 함께 사라진다(§17.4 장애 격리). 30초 폴링도 안 건다 -
 * 마감일 기준 값이라 초 단위로 변하지 않는다.
 * ──────────────────────────────────────────────────────────────────────────── */

// 티켓 소스를 못 읽었을 때의 문구. **0 을 그리지 않는다** — '할 일이 없다'는 거짓말이 된다
// (Home.jsx 의 SprintProgress 가 같은 상황에 같은 결의 문장을 쓴다).
export const WORK_UNKNOWN = "티켓 소스를 읽지 못해 내 업무를 셀 수 없습니다.";

// 완료 추이의 기준. 소스에 '상태가 완료로 바뀐 시각'이 없다(app/projects/weekly.py 와
// app/sprints/burndown.py 가 같은 사정을 적어 뒀다). 없는 이력을 추정해 선을 그으면 그건
// 추이가 아니라 창작이라, 화면이 기준을 그대로 말한다.
export const TREND_BASIS = "완료는 마감일 기준입니다. 상태가 완료로 바뀐 시각은 소스에 없습니다.";

// 창에 **포함되는** 마지막 날. 계약(end_exclusive)은 배타적 끝이 맞지만, 사람에게
// "08-03 ~ 08-10"이라고 보이면 08-10이 포함인지 매번 다시 생각해야 하고 반쯤은 틀리게 읽는다
// (app/projects/weekly.py::Week.last_day 가 서버에서 같은 판단을 기록한다).
export function lastDayOf(endExclusive) {
  if (!endExclusive) return null;
  const d = new Date(endExclusive + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return null;
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/* 목록 카드 하나(차질 프로젝트 / 지연 마일스톤 공용).
 * 비었을 때 문구를 받는 이유: '0건'과 '왜 0건인지'는 다른 정보다. */
function WorkList({ title, bucket, empty, renderItem }) {
  const items = (bucket && bucket.items) || [];
  const count = (bucket && bucket.count) || 0;
  return (
    <Card sx={{ p: 2.5 }}>
      <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>{title}</Typography>
      {items.length ? (
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
          {items.map((item) => (
            <Box component="li" key={item.key} sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
              {renderItem(item)}
            </Box>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">{empty}</Typography>
      )}
      {count > items.length ? (
        <Note>{items.length}건만 표시했습니다. 전체 {count}건은 프로젝트 화면에 있습니다.</Note>
      ) : null}
    </Card>
  );
}

export function WorkSection() {
  const nav = useNavigate();
  const q = useQuery({
    queryKey: ["home", "work-dashboard"],
    queryFn: () => api("/api/home/work-dashboard"),
    retry: 1,
    staleTime: 60 * 1000,
  });

  if (!q.data) {
    return (
      <DashSection title="내 업무">
        {q.isError
          ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
          : <Card><Skeleton lines={3} /></Card>}
      </DashSection>
    );
  }

  const d = q.data;
  const mine = d.mine;
  const projects = d.projects || {};
  const troubled = projects.troubled || { count: 0, items: [] };
  const overdueMs = (d.milestones || {}).overdue || { count: 0, items: [] };
  const win = d.window || {};
  const lastDay = lastDayOf(win.end_exclusive);
  const trend = d.completion_trend;

  return (
    <DashSection title="내 업무"
      action={<Link component="button" type="button" variant="body2" underline="hover"
        onClick={() => nav("/me")}>오늘 화면 열기 →</Link>}>
      {/* '이번 주'가 어느 주인지 화면이 스스로 말한다. 안 적으면 몇 주 뒤에 이 숫자가 어느
          주의 것이었는지 아무도 답할 수 없고, 기준을 모르는 숫자는 결국 안 믿게 된다. */}
      {win.start ? (
        <Note sx={{ mt: 0, mb: 1.5 }}>
          이번 주 {win.start} 부터 {lastDay} 까지 (Asia/Seoul 기준)
        </Note>
      ) : null}

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: HEADLINE_GRID }}>
        {/* 티켓 소스가 죽으면 이 세 장은 아예 안 그린다. '-'로 그려도 0으로 그려도 사용자는
            그것을 '없다'로 읽는다 — 아래 안내 문구가 이유를 대신 말한다. */}
        {mine ? (
          <>
            <StatCard value={fmtNum(mine.open)} label="내 미완료" onClick={() => nav("/my-tickets")} />
            <StatCard value={fmtNum(mine.due_this_week)} label="이번 주 마감"
              kind={mine.due_this_week ? "warn" : undefined} onClick={() => nav("/my-tickets")} />
            <StatCard value={fmtNum(mine.overdue)} label="지연 티켓"
              kind={mine.overdue ? "danger" : undefined} onClick={() => nav("/my-tickets")} />
          </>
        ) : null}
        <StatCard value={fmtNum(troubled.count)} label="차질 프로젝트"
          kind={troubled.count ? "danger" : undefined} onClick={() => nav("/projects")} />
        <StatCard value={fmtNum(overdueMs.count)} label="지연 마일스톤"
          kind={overdueMs.count ? "warn" : undefined} onClick={() => nav("/projects")} />
      </Box>
      {!mine ? <Note>{WORK_UNKNOWN}</Note> : null}
      {/* 차질 0건이 '다 건강하다'인지 '아무것도 안 쟀다'인지는 완전히 다른 사실이다. 서버가
          센 '못 잼' 건수를 그대로 말한다(0으로 뭉개면 화면에서 둘을 구별할 방법이 없다). */}
      {projects.unscored ? (
        <Note>아직 Health 를 계산하지 않은 프로젝트 {fmtNum(projects.unscored)}건은 이 판정에 들어가지 않았습니다.</Note>
      ) : null}
      {projects.truncated ? (
        <Note>프로젝트가 많아 일부만 훑었습니다. 합계가 전체와 다를 수 있습니다.</Note>
      ) : null}

      <Box sx={{ display: "grid", gap: 2, mt: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0,1fr))" } }}>
        <WorkList
          title="차질 프로젝트"
          bucket={{ count: troubled.count, items: (troubled.items || []).map((p) => ({ ...p, key: p.project_id })) }}
          empty="지금 차질로 판정된 프로젝트가 없습니다."
          renderItem={(p) => (
            <>
              <Link component="button" type="button" variant="body2" underline="hover"
                sx={{ textAlign: "left", fontWeight: FONT_WEIGHT.bold }}
                onClick={() => nav("/projects/" + p.project_id)}>
                {p.name}
              </Link>
              <Typography variant="caption" color="text.secondary">
                {(p.reasons || []).join(", ")}
                {p.health_score != null ? ", Health " + p.health_score + "점" : ""}
              </Typography>
            </>
          )}
        />
        <WorkList
          title="지연 마일스톤"
          bucket={{ count: overdueMs.count, items: (overdueMs.items || []).map((m) => ({ ...m, key: m.id })) }}
          empty="기한을 넘긴 마일스톤이 없습니다."
          renderItem={(m) => (
            <>
              <Link component="button" type="button" variant="body2" underline="hover"
                sx={{ textAlign: "left", fontWeight: FONT_WEIGHT.bold }}
                onClick={() => nav("/projects/" + m.project_id)}>
                {m.name}
              </Link>
              <Typography variant="caption" color="text.secondary">
                {m.project_name}, 기한 {m.due_on}
              </Typography>
            </>
          )}
        />
      </Box>

      {trend ? (
        <Box sx={{ mt: 2 }}>
          <Card sx={{ p: 2.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>최근 완료 추이</Typography>
            {/* 막대는 aria-hidden 이고 값은 항상 숫자로 함께 나간다(charts/base.jsx 규칙) —
                그림을 못 보는 사람도 같은 정보를 얻는다. */}
            <BarSeries
              items={trend.map((w) => ({
                label: w.week_of,
                value: w.done,
                color: w.done ? "success" : "neutral",
                note: w.assigned ? "마감 " + w.assigned + "건" : undefined,
              }))}
              unit="건" formatValue={fmtNum} emptyLabel="완료 추이를 만들 표본이 없습니다"
            />
            <Note>{TREND_BASIS}</Note>
          </Card>
        </Box>
      ) : null}
    </DashSection>
  );
}

export function Dashboard() {
  const nav = useNavigate();
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  // 운영 현황은 실시간성이 핵심이라 30초마다 자동 갱신(하트비트 stale 90초 창에 맞춤).
  // 폴링은 한 번 재시도해 순간 네트워크 끊김에 실시간 보드가 통째로 사라지지 않게 한다.
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api("/api/admin/dashboard"), retry: 1, refetchInterval: 30 * 1000 });
  const updated = q.dataUpdatedAt ? fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) : null;
  // 백그라운드 폴링은 매번 isFetching을 켜 버튼을 깜빡이게 하므로, 수동 새로고침만 버튼 상태로 반영한다.
  const [manualRefreshing, setManualRefreshing] = React.useState(false);
  // 수동 새로고침만 스크린리더에 완료를 알린다(30초 자동 폴링은 알리지 않는다 — 타임스탬프를
  // aria-live에서 뺀 것과 같은 이유로 소음이 된다). 갱신 시각을 문구에 담아 연속 새로고침도
  // 텍스트가 바뀌어 다시 낭독되게 한다.
  const [refreshAnnounce, setRefreshAnnounce] = React.useState("");
  React.useEffect(() => {
    if (q.isFetching) return;
    if (manualRefreshing) {
      setManualRefreshing(false);
      setRefreshAnnounce("대시보드를 갱신했습니다" + (q.dataUpdatedAt ? " (" + fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) + " 기준)" : "") + ".");
    }
  }, [q.isFetching]); // eslint-disable-line react-hooks/exhaustive-deps
  const onManualRefresh = () => { setManualRefreshing(true); q.refetch(); };
  // 마지막으로 성공한 데이터가 있으면 폴링 실패로 화면을 비우지 않고 계속 보여준다.
  const staleAfterError = q.isError && !!q.data;

  return (
    <Box className="c-screen">
      <PageHeader area="운영" title="대시보드" spot="assistant"
        actions={<>
          {/* 30초마다 갱신되는 비-조치성 타임스탬프에 aria-live를 달면 스크린리더 사용자에게
              "오후 3:45 기준", "오후 3:46 기준" ...이 탭을 열어 둔 내내 끊임없이 낭독된다 -
              실제로 주의가 필요한 알림(경보 섹션의 aria-live)과 달리 이건 끼어들 가치가 없다. */}
          {updated ? (
            <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
              {updated} 기준{staleAfterError ? ", 새로고침 실패" : ""}
            </Typography>
          ) : null}
          <Button variant="ghost" size="sm" disabled={manualRefreshing} onClick={onManualRefresh}>{manualRefreshing ? "새로고침 중…" : "새로고침"}</Button>
          {/* 수동 새로고침 완료만 조용히 알린다(자동 폴링은 제외, 위 타임스탬프 aria-live 제외와 같은 취지). */}
          <span className="sr-only" role="status" aria-live="polite">{refreshAnnounce}</span>
        </>} />
      {!q.data ? (
        // 데이터가 아직/전혀 없을 때: 오류면 ErrorState, 아니면 로딩 스켈레톤. (undefined를 본문에 넘겨 크래시하지 않게 한다.)
        // 실제 대시보드는 경보 줄 + 여러 지표 그리드 섹션으로 이루어져 있다, 카드 한 장짜리 평평한
        // 스켈레톤에서 그 구조로 바뀌면 레이아웃이 눈에 띄게 출렁인다. 대략적인 모양(경보 트랙 +
        // 표준 지표 그리드)만이라도 미리 잡아 세로 공간이 크게 튀지 않게 한다.
        q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <Box>
            {[0, 1].map((row) => (
              <Box key={row} sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID, mb: 4 }}>
                {Array.from({ length: row ? 4 : 2 }).map((_, i) => (
                  <Card key={i}><Skeleton lines={2} /></Card>
                ))}
              </Box>
            ))}
          </Box>
        )
      ) : (
        <DashboardBody d={q.data} nav={nav} role={role} stale={staleAfterError} />
      )}
      {/* 운영 지표 **아래**다. 급한 일(경보)이 먼저 눈에 들어와야 한다는 이 화면의 순서
          규칙을 그대로 따른다. 질의가 따로라 위쪽이 로딩·실패 중이어도 이 구역은 뜬다. */}
      <WorkSection />
    </Box>
  );
}

function DashboardBody({ d, nav, role, stale }) {
  const toast = useToast();
  // 대상 ID는 title(hover) 툴팁으로만 전체 값을 보여줬다 — 터치 기기·스크린리더는 title이 안 뜬다.
  // 짧은 대상 표기를 눌러 전체 ID를 클립보드로 복사할 수 있게 해, 그 값을 다른 화면(감사 로그 검색 등)에
  // 붙여넣어야 하는 실제 필요를 hover 없이도 채운다.
  // 복사가 실패하면(비보안 컨텍스트 등) 이전엔 토스트만 뜨고 전체 ID를 볼 방법이 없었다(짧은 표기 +
  // hover 전용 title뿐) — 실패한 행의 전체 ID를 Users.jsx d.id와 같은 c-id-selectable(수동 선택-복사)
  // 스팬으로 펼쳐 보여준다.
  const [revealedId, setRevealedId] = React.useState(null);
  function copyObjectId(id) {
    copyToClipboard(id).then(
      () => { setRevealedId(null); toast("ID를 복사했습니다.", "success"); },
      () => { setRevealedId(id); toast("복사를 지원하지 않는 환경입니다. 아래에 전체 ID를 펼쳤습니다.", "info"); }
    );
  }
  const jobs = d.jobs_24h || {};
  const disk = d.disk || {};
  const mem = d.memory || {};
  // 링크는 볼 수 있는 역할에게만 건다(없으면 클릭 불가 카드로 남겨 정보는 유지).
  const goto = (path) => (canGo(path, role) ? () => nav(path) : undefined);
  // 운영자가 지금 확인해야 할 것(§6.1), 문제 있는 항목만 우선.
  const alerts = [];
  // 진단(/diagnostics)은 admin/system_admin만 들어간다, operator/auditor에게 '진단으로' 링크를 걸면 막다른 길이 된다.
  // 볼 수 있으면 진단으로, 아니면 도달 가능한 대체 화면으로 보낸다(없으면 클릭 불가 정보 카드로 남겨 경보 자체는 유지).
  const diagTo = canGo("/diagnostics", role) ? "/diagnostics" : undefined;
  // 워커/스케줄러 문제는 큐 정체로 이어지므로, 진단을 못 보는 역할은 작업 큐(/jobs)로 안내한다.
  const procTo = diagTo || (canGo("/jobs", role) ? "/jobs" : undefined);
  // 디스크/메모리/인증서 경보는 진단(/diagnostics) 외에 도달 가능한 대체 화면이 없다, 진단을 못 보는
  // 역할에겐 클릭 불가 카드가 되므로, 다음 행동을 라벨에 짧게 덧붙여 막다른 길로 남기지 않는다.
  const diagNote = diagTo ? "" : ", 관리자 문의";
  // 작업(/jobs) 경보도 같은 이유로 도달 불가 역할(auditor)에겐 다음 행동을 안내한다, 안 그러면
  // diagNote가 붙는 형제 경보 옆에서 이 타일만 아무 설명 없는 클릭 불가 막다른 카드가 된다.
  const jobsTo = canGo("/jobs", role) ? "/jobs" : undefined;
  const jobsNote = jobsTo ? "" : ", 관리자 문의";
  const procNote = procTo ? "" : ", 관리자 문의";
  {/* jobs.total/succeeded는 이미 fmtNum()으로 천 단위 구분자를 붙이는데(아래 '작업 지표' 섹션), 바로
      이 경보 타일과 '현재 큐 상태' 타일의 같은 종류 수치(failed_open/queued)만 raw로 새고 있었다 -
      정작 사건이 몰려 자릿수가 커지는 순간(장애 중)에 가장 스캔하기 어려워지는 값이다. */}
  // 유지보수 모드는 이 앱에서 blast-radius가 가장 큰 운영 상태다 — 켜져 있는 동안 일반
  // 사용자의 **모든 쓰기가 막힌다**(app/settings/gate.py::block_if_maintenance).
  // 서버는 이 사실을 매 폴링마다 payload에 실어 보내면서(app/health/service.py의 "maintenance"
  // 필드, 주석은 "화면이 상단 배너/경보로 띄운다"고 적어 두었다) 화면이 그것을 한 번도 읽지
  // 않았다 — 그래서 점검 중에도 이 화면은 초록색 "지금 조치가 필요한 문제가 없습니다."를
  // 띄웠다. 운영자는 그 배너를 보고 사용자 신고("저장이 안 돼요")를 장애로 오해한다.
  // 맨 앞에 넣는다: 다른 경보들의 원인이 이것일 수 있다(작업이 안 쌓이는 이유 등).
  if (d.maintenance) alerts.push({ src: "maintenance", label: "유지보수 모드", value: "활성", kind: "danger", to: canGo("/maintenance", role) ? "/maintenance" : undefined });
  if (jobs.failed_open) alerts.push({ src: "job:failed", label: "실패 작업" + failedOpenAgeLabel(jobs) + jobsNote, value: fmtNum(jobs.failed_open), kind: "danger", to: jobsTo });
  if (jobs.queued) alerts.push({ src: "job:queued", label: "대기 작업" + jobsNote, value: fmtNum(jobs.queued), kind: "warn", to: jobsTo });
  // 단위(%)는 라벨 괄호가 아니라 값에 붙인다(자원 타일과 동일한 표기), '성공률 낮음(%)' 위 '45'는 어색했다.
  // success_rate_pct의 분모는 최근 24시간에 '종료된'(성공+실패+취소) 작업만이다, 아직 끝나지 않은
  // queued/running 작업은 분모에서 제외된다(app/health/service.py finished_24h). 접수만 몰린 순간에는
  // 이 값이 영향받지 않는다.
  // 아래 KPI 타일은 80~94.9%를 warn(주황)으로, 95%↑를 ok로 칠하는데 이 상단 경보는
  // 예전엔 <80(danger)만 반영해 '85% 성공률'이 타일에선 '주의'인데 경보 줄엔 아예 안 뜨는 모순이
  // 있었다 — 디스크/메모리 경보와 같은 if/else-if danger·warn 2단 구조로 맞춘다.
  if (jobs.success_rate_pct != null && jobs.total > 0 && jobs.success_rate_pct < 80)
    alerts.push({ src: "job:rate", label: "성공률 낮음(종료 작업 대비)" + jobsNote, value: jobs.success_rate_pct + "%", kind: "danger", to: jobsTo });
  else if (jobs.success_rate_pct != null && jobs.total > 0 && jobs.success_rate_pct < 95)
    alerts.push({ src: "job:rate", label: "성공률 저하(종료 작업 대비)" + jobsNote, value: jobs.success_rate_pct + "%", kind: "warn", to: jobsTo });
  // 워커/스케줄러가 죽으면 큐가 비어 있어도 작업이 멈춘다 — 하트비트 stale를 최상단 경보로.
  // 'down'(중단)은 danger, 'unknown'(응답 없음, 재시작 직후 등)은 warn으로 구분해 서비스 카드와 심각도를 맞춘다.
  const comps = d.components || {};
  if (comps.worker && comps.worker !== "up")
    alerts.push({ src: "comp:worker", label: "워커" + procNote, value: comps.worker === "down" ? "중단" : "응답 없음", kind: comps.worker === "down" ? "danger" : "warn", to: procTo });
  if (comps.scheduler && comps.scheduler !== "up")
    alerts.push({ src: "comp:scheduler", label: "스케줄러" + procNote, value: comps.scheduler === "down" ? "중단" : "응답 없음", kind: comps.scheduler === "down" ? "danger" : "warn", to: procTo });
  // 핵심 연동(n8n·Notion·러너 등)이 down/degraded면 큐가 비어 있어도 업무가 멈춘다 — 서비스 상태 배지로만
  // 두지 않고 상단 경보로 올린다(비활성 연동은 제외). enabled!==false인 것만.
  // src에 "integ:"+원본 이름(표시 라벨이 아니라)을 태그한다 — 연동 이름이 컴포넌트 라벨('워커' 등)과
  // 우연히 같아도(관리자가 그렇게 이름 붙인 경우) label만으로 만든 key와 달리 출처가 겹치지 않는다.
  // app/integrations/models.py는 HEALTH_UP/HEALTH_DOWN/HEALTH_UNKNOWN만 정의하고, 유일한
  // writer(run_health_check)도 up/down만 기록한다 — 'degraded'는 백엔드가 실제로 만들어낼 수 없는
  // 값이라 그 분기는 죽은 코드였다(제거). 실제로 저하 판정이 생기면 그때 다시 추가한다.
  Object.entries(d.integrations || {}).forEach(([name, v]) => {
    if (v && v.enabled !== false && v.last_health === "down")
      alerts.push({ src: "integ:" + name, label: serviceLabel(name), value: "중단", kind: "danger", to: "/integrations" });
  });
  if (d.cert_days_remaining != null && d.cert_days_remaining <= 30)
    alerts.push({ src: "cert", label: "인증서 만료" + diagNote, value: fmtCertDays(d.cert_days_remaining), kind: d.cert_days_remaining <= 0 ? "danger" : "warn", to: diagTo });
  // '마지막 백업 없음'은 백업을 실제로 '실행할 수 있는' 역할(system_admin)에게만 경보로 띄운다.
  // 백업 화면은 operator/admin/auditor도 조회는 가능하지만 실행은 system_admin 전용이므로, 도달 가능성이 아니라
  // 실행 권한으로 게이트한다 — 조치할 수 없는 빨간 경보를 상시 띄우면 실제 경보에 둔감해진다(캔 액트 없는 경보는 계약 위반).
  if (!d.last_backup_at && role === "system_admin") alerts.push({ src: "backup", label: "마지막 백업", value: "없음", kind: "danger", to: "/backup" });
  // 마지막 성공 백업은 있지만 그 이후로 한참 지났으면(예: 계속 실패 중) 조용한 '정상'으로 보이던
  // 문제 — 자원 타일의 80/90% warn 기준과 같은 취지로, 여기도 나이 기준 경보를 둔다.
  const backupAgeDays = d.last_backup_at ? daysSince(d.last_backup_at) : null;
  if (backupAgeDays != null && backupAgeDays > BACKUP_STALE_DAYS && role === "system_admin")
    alerts.push({ src: "backup-stale", label: "마지막 백업이 오래됨", value: Math.floor(backupAgeDays) + "일 전", kind: backupAgeDays > BACKUP_STALE_DAYS * 2 ? "danger" : "warn", to: "/backup" });
  // 아래 시스템 리소스 타일은 80%부터 warn(주의) 색을 칠하는데, 이 상단 경보 묶음은 85%(디스크)·
  // 90%(메모리)의 danger만 반영해 같은 수치를 두고 타일과 경보가 서로 다른 말을 하고 있었다 —
  // 타일의 warn 기준을 그대로 여기도 반영한다.
  if (disk.used_pct != null && disk.used_pct >= 85)
    alerts.push({ src: "disk", label: "디스크 사용" + diagNote, value: disk.used_pct + "%", kind: "danger", to: diagTo });
  else if (disk.used_pct != null && disk.used_pct >= 80)
    alerts.push({ src: "disk", label: "디스크 사용" + diagNote, value: disk.used_pct + "%", kind: "warn", to: diagTo });
  // 메모리 고갈도 디스크만큼 급하다 — 자원 타일만 빨갛게 칠하고 경보엔 없어 '이상 없음' 오배너가 뜨던 문제.
  if (mem.used_pct != null && mem.used_pct >= 90)
    alerts.push({ src: "mem", label: "메모리 사용" + diagNote, value: mem.used_pct + "%", kind: "danger", to: diagTo });
  else if (mem.used_pct != null && mem.used_pct >= 80)
    alerts.push({ src: "mem", label: "메모리 사용" + diagNote, value: mem.used_pct + "%", kind: "warn", to: diagTo });

  // 불변성(§7): 제자리 수정 대신 새 객체로 구성한다.
  // 비활성화된 연동은 마지막 헬스 상태(예: 'up')를 그대로 두면 꺼져 있는데 '정상'으로 보인다 —
  // enabled===false면 상태 대신 '비활성화'로 표시한다.
  // 연동 이름이 핵심 컴포넌트 키(web/worker/scheduler)와 우연히 겹치면 그 연동의 상태가 실제
  // 하트비트를 조용히 덮어써 버린다 — 겹치는 이름에는 접미사를 붙여 절대 가리지 않게 한다.
  const integrationEntries = Object.entries(d.integrations || {}).map(([k, v]) => {
    const key = (k in comps) ? k + "(연동)" : k;
    return [key, (v && v.enabled === false) ? "disabled" : (v || {}).last_health];
  });
  const services = { ...comps, ...Object.fromEntries(integrationEntries) };
  // 서비스 카드의 이동 대상(정상 카드는 이동할 곳이 없으면 클릭 불가). 워커/스케줄러는 상단 경보와
  // 동일하게 진단을 못 보는 역할이면 작업 큐(/jobs)로 대체한다 — 예전엔 여기만 /diagnostics만
  // 제공해, 같은 '워커 중단' 사실이 상단 경보에선 클릭 가능한데 이 타일에선 죽어 보였다.
  function svcNav(k) {
    if (k === "web") return undefined;
    if (k === "worker" || k === "scheduler") return procTo ? goto(procTo) : undefined;
    return goto("/integrations");
  }
  // services의 키는 위에서 충돌 방지를 위해 "(연동)" 접미사가 붙을 수 있다(예: "worker(연동)") —
  // SERVICE_LABELS는 그 접미 붙은 키를 모르므로 그대로 조회하면 항상 못 찾아 원시 영문 키가
  // ('worker(연동)') 그대로 화면에 샜다. 원래 이름(접미사를 뗀 키)으로 먼저 찾고, 붙어 있던
  // 접미사만 번역된 라벨 뒤에 다시 붙인다.
  function svcLabel(k) {
    const suffixed = k.endsWith("(연동)");
    const base = suffixed ? k.slice(0, -"(연동)".length) : k;
    return serviceLabel(base) + (suffixed ? "(연동)" : "");
  }
  // 상단 경보 그리드가 danger를 앞으로 정렬하듯, 서비스 카드도 문제(중단)·응답 없음을
  // 먼저 보여준다 — 연동이 많은 배포에서 '중단' 카드가 정상 카드들 아래로 밀려 스크롤해야 찾던 문제.
  // 같은 등급 안에서는 원래 삽입 순서(web/worker/scheduler 먼저)가 안정 정렬로 유지된다.
  const svcRank = (k) => { const v = services[k]; return v === "down" ? 0 : (v === "unknown" || v == null) ? 1 : 2; };
  const serviceKeys = Object.keys(services).sort((a, b) => svcRank(a) - svcRank(b));

  return (
    <Box>
      {/* 백그라운드 폴링이 실패해 캐시된 값이 남았을 때(staleAfterError), 헤더의 작은 접미 문구만으론
          운영자가 낡은 수치를 계속 최신처럼 읽기 쉽다, 눈에 띄는 경고 배너로 올린다. */}
      {/* 폴링 실패로 값이 낡았다는 사실 자체가 스크린리더에도 알려져야 한다, Callout 자체엔
          role/aria-live가 없어 이 배너가 나타나는 순간이 SR 사용자에게 조용히 지나갔다. */}
      {stale ? <Box sx={{ mb: 3 }} role="status" aria-live="polite"><Callout tone="warn">실시간 갱신이 실패했습니다. 표시된 값이 최신이 아닐 수 있습니다. 새로고침해 주세요.</Callout></Box> : null}
      {/* aria-live 래퍼 자체는 항상 마운트된 채로 두고 안의 자식(경보 묶음 ↔ all-clear)만 바꾼다 -
          예전엔 aria-live가 <section> 안쪽에 있어, 경보가 전부 사라지고 all-clear로 바뀌는 순간
          그 live region 엘리먼트 자체가 통째로 언마운트돼 전환 자체를 SR이 놓칠 수 있었다. */}
      {/* 머리 지표 — 경보보다 **아래**다. 급한 일(경보)이 먼저 눈에 들어와야 한다.
          기준 목업도 빨간 경보 배너 → 지표 다섯 순서다. */}
      <Box aria-live="polite">
        {alerts.length ? (
          <DashSection title="확인이 필요한 항목">
            {/* 타일은 색, 글리프로 심각도를 구분하지만, 좁은 화면에서 스크롤 없이 처음 1~2개만 보이면
                danger가 코드 순서상 warn보다 뒤에 있을 때 가장 급한 항목을 놓칠 수 있다 -
                danger를 항상 앞으로 정렬한다(불변성: sort 전에 배열을 복사). */}
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
              {[...alerts].sort((a, b) => (a.kind === "danger" ? 0 : 1) - (b.kind === "danger" ? 0 : 1)).map((a) => (
                // 안정 key(출처 태그 a.src), 폴링마다 경보 집합이 바뀔 때 index key는 DOM을 재사용해
                // aria-live 영역이 바뀌지 않은 내용을 잘못 낭독하거나 onClick이 어긋날 수 있다. label만
                // 쓰면 컴포넌트 경보('워커')와 그와 같은 이름을 쓰는 연동 경보가 같은 key로 충돌할 수
                // 있어(React 경고 또는 항목 하나가 조용히 사라짐), 출처가 겹치지 않는 src로 키를 잡는다.
                <StatCard key={a.src} value={a.value} label={a.label} kind={a.kind}
                  onClick={a.to ? goto(a.to) : undefined} />
              ))}
            </Box>
          </DashSection>
        ) : (
          <Paper
            variant="outlined"
            sx={{
              display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.5, mb: 4,
              borderColor: "success.main", bgcolor: (t) => t.palette.action.hover,
            }}
          >
            <Badge value="up" />
            <Typography variant="body2">지금 조치가 필요한 문제가 없습니다.</Typography>
          </Paper>
        )}
      </Box>

      <DashSection title="지금 상태">
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: HEADLINE_GRID }}>
          {headlineStats({ services, counts: d.counts, jobs, disk, jobsNote, diagTo, diagNote }).map((t) => (
            <StatCard key={t.key} value={t.value} label={t.label} kind={t.kind}
              onClick={t.to && canGo(t.to, role) ? goto(t.to) : undefined} />
          ))}
        </Box>
        <Note>이 줄은 요약입니다. 값을 누르면 그 화면으로 내려가고, 자세한 항목은 아래 구역에 있습니다.</Note>
      </DashSection>

      <DashSection title="서비스 상태">
        {/* 넓은 화면에서는 카드 격자 옆에 상태 구성 도넛을 세운다 — 연동이 열 개를 넘는 배포에서
            카드를 하나씩 세는 대신 '정상 8 / 중단 1'을 한눈에 읽게 한다. 좁은 화면에서는 아래로 접힌다. */}
        <Box sx={{ display: "grid", gap: 2, alignItems: "start", gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) minmax(0, 24rem)" } }}>
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: SERVICE_GRID }}>
            {serviceKeys.map((k) => {
              const onClick = svcNav(k);
              // 워커/스케줄러가 'unknown'(하트비트 없음)이면 상단 경보와 심각도를 맞춰 warn으로 물들인다.
              // (기본 배지는 unknown을 무채색으로 그려 카드에선 무해하게 보였다.)
              const unknownComp = (k in comps && services[k] === "unknown");
              const badgeKind = unknownComp ? "warn" : undefined;
              // 같은 상태를 상단 경보는 '응답 없음', 배지는 '알 수 없음'으로 달리 불러 혼란을 줬다, 경보 문구로 통일한다.
              return (
                <StatusTile key={k} name={svcLabel(k)} onClick={onClick} ariaLabel={svcLabel(k) + " 상세 열기"}>
                  <Badge value={unknownComp ? "응답 없음" : services[k]} kind={badgeKind} />
                </StatusTile>
              );
            })}
          </Box>
          <Card sx={{ p: 2.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>상태 구성</Typography>
            <Donut segments={serviceMix(services)} unit="개" centerLabel="서비스" emptyLabel="서비스 정보 없음" />
          </Card>
        </Box>
      </DashSection>

      <DashSection title="작업 지표 (최근 24시간)">
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
          {/* 바로 아래 '현재 큐 상태', '인벤토리' 타일은 모두 클릭해 해당 목록으로 드릴다운하는데
              이 24시간 집계 타일만 예외적으로 죽은 채였다, 같은 화면(볼 수 있는 역할에게만)으로
              연결해 시각적으로 동일한 타일 그룹의 상호작용을 통일한다. */}
          {/* auditor는 /jobs에 못 들어가 goto('/jobs')가 undefined다, '현재 큐 상태', 리소스 타일과
              같은 이유(jobsNote)를 붙여, 클릭 불가 타일이 아무 설명 없는 막다른 카드로 보이지 않게 한다. */}
          <StatCard value={fmtNum(jobs.total)} label={"처리 요청" + jobsNote} onClick={goto("/jobs")} />
          {/* 서버는 이 값(jobs_24h.succeeded)을 매 폴링마다 이미 계산해 내려주는데(app/health/service.py)
              화면 어디에도 쓰이지 않고 버려지고 있었다, 옆 성공률 타일의 분자를 그대로 보여준다. */}
          <StatCard value={fmtNum(jobs.succeeded)} label={"성공" + jobsNote} onClick={goto("/jobs")} />
          <StatCard value={jobs.success_rate_pct != null ? jobs.success_rate_pct + "%" : "-"} label={"성공률(종료 작업 대비)" + jobsNote}
            kind={jobs.success_rate_pct == null ? undefined : jobs.success_rate_pct >= 95 ? "ok" : jobs.success_rate_pct >= 80 ? "warn" : "danger"}
            onClick={goto("/jobs")} />
          {/* 단위는 라벨 괄호가 아니라 값에 붙인다, 성공률/디스크/메모리 타일과 같은 표기 규칙
              (위 주석 '성공률 낮음(%) 위 45는 어색했다' 참고). */}
          <StatCard value={fmtProcessingTime(jobs.avg_processing_seconds)} label={"평균 처리" + jobsNote} onClick={goto("/jobs")} />
        </Box>
        {/* 성공률의 분모는 최근 24시간에 '종료된'(성공, 실패, 취소) 작업만이다, 아직 끝나지 않은
            대기, 실행 중 작업은 분모에서 제외된다. */}
        {/* 이 네 값에는 시계열이 없다(백엔드가 24시간 집계 스칼라만 내려준다 — app/health/service.py).
            없는 추세선을 그리면 한 점을 선으로 잇는 거짓말이 되므로 여기는 숫자로 둔다. */}
        <Note>성공률은 최근 24시간에 종료(성공, 실패, 취소)된 작업 대비이며, 아직 끝나지 않은 대기, 실행 중 작업은 분모에서 제외됩니다.</Note>
      </DashSection>

      <DashSection title="현재 큐 상태">
        {/* queued/failed_open은 24시간 창이 아니라 '지금'의 큐 깊이, 미해결 실패다(서버가 시간 필터 없이 계산).
            24시간 지표와 섞으면 며칠 전 실패가 최근 것처럼 읽혀 오해를 부른다, 별도 '현재 큐' 묶음으로 분리한다.
            failed_open 자체엔 여전히 시간축이 없었다(VIS-107R) — "미해결 실패 4건"이 방금 생긴 것인지
            3주 방치된 것인지 구분이 안 됐다. failedOpenAgeLabel이 가장 오래된 것의 나이를 덧붙인다. */}
        <Box sx={{ display: "grid", gap: 2, alignItems: "start", gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) minmax(0, 24rem)" } }}>
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))" } }}>
            {/* 대기·실패 작업 수는 0이어도 항상 노출해 '큐 비었음/실패 없음'을 확인할 수 있게 한다(스펙 §14.1). */}
            {/* 심각도(빨강/노랑)는 상단 '확인이 필요한 항목' 경보가 이미 담당하므로 여기선 중복 강조하지 않는다. */}
            {/* 인벤토리 타일처럼 0이어도 항상 /jobs로 드릴다운한다 — 값에 따라 클릭 가능/불가가 갈리면(예전 >0 가드)
                같은 타일이 상황에 따라 죽어 보여 혼란스러웠다. 빈 목록으로 가도 해당 화면이 EmptyState를 보여 무해하다. */}
            {/* 위 '확인이 필요한 항목' 경보 타일과 같은 이유 안내(jobsNote)를 붙인다, 안 그러면 이
                쌍둥이 수치가 이 섹션에서만 아무 설명 없이 클릭 불가 카드로 보인다(예: auditor 역할). */}
            <StatCard value={fmtNum(jobs.queued != null ? jobs.queued : 0)} label={"대기 작업" + jobsNote} onClick={goto("/jobs")} />
            <StatCard value={fmtNum(jobs.failed_open != null ? jobs.failed_open : 0)} label={"미해결 실패 작업" + failedOpenAgeLabel(jobs) + jobsNote} onClick={goto("/jobs")} />
          </Box>
          {/* 두 수치의 '비율'은 숫자 두 개만 봐서는 안 잡힌다 — 대기 1,200건 옆의 실패 3건과
              대기 3건 옆의 실패 12건은 대응이 완전히 다른데 타일만 보면 똑같이 보인다. */}
          <Card sx={{ p: 2.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>미처리 작업 구성</Typography>
            <BarSeries
              items={[
                { label: "대기", value: jobs.queued != null ? jobs.queued : 0, color: jobs.queued ? "warn" : "neutral" },
                { label: "미해결 실패", value: jobs.failed_open != null ? jobs.failed_open : 0, color: jobs.failed_open ? "danger" : "neutral" },
              ]}
              unit="건" formatValue={fmtNum} emptyLabel="큐 정보를 불러오지 못했습니다"
            />
          </Card>
        </Box>
      </DashSection>

      <DashSection title="인벤토리">
        {/* 인벤토리(이동 가능한 개체 수)와 시스템 리소스(인프라 건강)는 성격이 다르다 -
            한 묶음에 섞으면 스캔이 어려워 별도 섹션으로 나눈다. */}
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
          {/* 자원 수 타일도 큐 타일처럼 해당 레지스트리로 드릴다운한다(볼 수 있는 역할에게만 클릭 가능). */}
          <StatCard value={fmtNum((d.counts || {}).active_workflows)} label="활성 워크플로" onClick={goto("/workflows")} />
          <StatCard value={fmtNum((d.counts || {}).active_schedules)} label="활성 스케줄" onClick={goto("/schedules")} />
          <StatCard value={fmtNum((d.counts || {}).runners)} label="추가된 러너" onClick={goto("/runners")} />
        </Box>
      </DashSection>

      {/* 디스크, 메모리, 인증서가 모두 null이면(비-Linux 호스트, nginx TLS 종단 등) 섹션 자체를 숨긴다 -
          영구 '-' 죽은 타일/빈 섹션을 남기지 않는다. */}
      {(disk.free_gb != null || disk.used_pct != null || mem.used_pct != null || d.cert_days_remaining != null) ? (
        <DashSection title="시스템 리소스">
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
            {/* 디스크 정보가 없으면(disk_usage OSError 등 전부 null) 메모리, 인증서 타일과 같은 규칙으로 숨긴다 -
                영구 '-' 죽은 타일을 남기지 않는다. 디스크도 메모리처럼 %, 경고색을 함께 보여 준다. */}
            {/* 이 값들이 이미 위 경보 타일에서 diagTo로 클릭 가능한 것과 동일한 드릴다운을 여기도 제공한다 -
                안 그러면 같은 수치가 경보에선 클릭 가능, 여기선 죽은 타일로 보여 일관성이 깨진다. */}
            {/* 단위는 라벨 괄호가 아니라 값에 붙인다, 이 섹션의 나머지(사용률, 초 등)와 같은 표기 규칙. */}
            {/* 여유 용량만 보여주면 규모 감이 없다('80% 사용'이 500GB 중인지 20GB 중인지 모른다) -
                서버가 매 폴링에 함께 주는 total_gb로 '여유 / 전체'를 보여준다(값이 없으면 여유만).
                diagNote는 이웃 '디스크 사용' 타일과 통일, 진단을 못 보는 역할에게 클릭 불가 사유를 남긴다. */}
            {disk.free_gb != null ? <StatCard value={disk.total_gb != null ? fmtNum(disk.free_gb) + " / " + fmtNum(disk.total_gb) + "GB" : fmtNum(disk.free_gb) + "GB"} label={"디스크 여유" + diagNote} onClick={diagTo ? goto(diagTo) : undefined} /> : null}
            {disk.used_pct != null ? (
              <StatCard value={disk.used_pct + "%"} label={"디스크 사용" + diagNote}
                kind={disk.used_pct >= 85 ? "danger" : disk.used_pct >= 80 ? "warn" : undefined}
                onClick={diagTo ? goto(diagTo) : undefined} />
            ) : null}
            {/* 메모리 데이터가 없으면(비-Linux 호스트 등 used_pct=null) 인증서 타일과 동일하게 숨긴다 -
                영구 '-' 죽은 타일을 남기지 않는다(인접 타일과 null 처리 규칙을 맞춘다). */}
            {mem.used_pct != null ? (
              <StatCard value={mem.used_pct + "%"} label={"메모리 사용" + diagNote}
                kind={mem.used_pct >= 90 ? "danger" : mem.used_pct >= 80 ? "warn" : undefined}
                onClick={diagTo ? goto(diagTo) : undefined} />
            ) : null}
            {/* 인증서 경로가 없으면(nginx TLS 종단) cert_days_remaining이 null, 영구 '-' 타일 대신 숨긴다. */}
            {d.cert_days_remaining != null ? (
              <StatCard value={fmtCertDays(d.cert_days_remaining)} label={"인증서 만료" + diagNote}
                kind={d.cert_days_remaining <= 0 ? "danger" : d.cert_days_remaining <= 30 ? "warn" : undefined}
                onClick={diagTo ? goto(diagTo) : undefined} />
            ) : null}
          </Box>
        </DashSection>
      ) : null}

      <DashSection title="백업">
        <Card sx={{ p: 2.5, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
          {/* component="div" — 안에 Badge(Chip은 <div>)가 들어간다. 기본 <p>로 두면 React가
              validateDOMNesting 오류를 콘솔에 찍고, QA 하네스의 console_errors 검사에 걸린다. */}
          <Typography component="div" variant="body2" sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
            마지막 백업: {d.last_backup_at ? fmtDateTime(d.last_backup_at) : "없음"}
            {d.last_backup_status ? <Badge value={d.last_backup_status} /> : null}
            {/* 성공 이력은 있지만 그 이후로 오래 지났으면(계속 실패 중일 수 있음) 여기서도 나이를 알린다 —
                위 상단 경보(backup-stale)와 같은 임계값. */}
            {backupAgeDays != null && backupAgeDays > BACKUP_STALE_DAYS
              ? <Badge value={Math.floor(backupAgeDays) + "일 전"} kind={backupAgeDays > BACKUP_STALE_DAYS * 2 ? "danger" : "warn"} />
              : null}
          </Typography>
          <Button variant={d.last_backup_at ? "default" : "primary"} size="sm"
            disabled={!canGo("/backup", role)} onClick={goto("/backup")}>
            {d.last_backup_at ? "백업 관리" : "백업 관리로 이동"}
          </Button>
        </Card>
      </DashSection>

      {(d.recent_critical_audit || []).length ? (
        <DashSection title="최근 주요 변경"
          action={canGo("/audit", role)
            ? <Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/audit")}>전체 보기 →</Link>
            : null}>
          <Card>
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
              {d.recent_critical_audit.map((a) => (
                // 안정 key, 30초 폴링마다 새 항목이 앞에 붙으므로 index key는 행을 위치로 재사용해 어긋난다.
                <Box component="li" key={a.created_at + "|" + (a.object_id || "") + "|" + a.action}
                  sx={{
                    display: "grid", alignItems: "baseline", gap: { xs: 0.25, sm: 1.5 },
                    gridTemplateColumns: { xs: "1fr", sm: "12rem minmax(0,1fr) auto" },
                  }}>
                  <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{fmtDateTime(a.created_at)}</Typography>
                  <Typography variant="body2" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{actionKo(a.action)} ({a.actor || "시스템"})</Typography>
                  {/* 줄인 ID엔 …을 붙여 '전체 값'처럼 보이지 않게 하고, 대상 ID가 있으면 눌러서 복사할
                      수 있게 한다(title 툴팁은 터치, 스크린리더에서 안 보인다, 탭 가능한 대안). */}
                  {a.object_id ? (
                    <>
                      <Link component="button" type="button" variant="body2" underline="hover" color="text.secondary" title={a.object_id}
                        aria-label={objKo(a.object_type) + " 전체 ID 복사: " + a.object_id}
                        onClick={() => copyObjectId(a.object_id)}
                        sx={{ textAlign: "left" }}>
                        {objKo(a.object_type)}, {shortId(a.object_id)}
                      </Link>
                      {revealedId === a.object_id ? (
                        <Typography className="c-id-selectable" variant="caption" color="text.secondary" tabIndex={0}
                          sx={{ gridColumn: "1 / -1", wordBreak: "break-all", userSelect: "all" }}>
                          {a.object_id}
                        </Typography>
                      ) : null}
                    </>
                  ) : <Typography variant="body2" color="text.secondary">{objKo(a.object_type)}</Typography>}
                </Box>
              ))}
            </Box>
          </Card>
        </DashSection>
      ) : (
        // 최근 주요 변경이 비어 보이는 두 경우(실제로 없음 / 권한이 없어 서버가 아예 안 내려줌)를
        // 구분해준다, 안 그러면 감사 로그 열람 권한이 없는 역할은 '아무 변경도 없었다'로 오해한다.
        !canGo("/audit", role) ? (
          <DashSection title="최근 주요 변경">
            <Note sx={{ mt: 0 }}>감사 로그 열람 권한이 없어 숨겨졌습니다.</Note>
          </DashSection>
        ) : (
          // 권한은 있고 정말로 아무 일도 없었던 경우(조용한 기간), null을 그대로 두면 이 섹션이
          // '고장/누락'인지 '평온함'인지 구분되지 않는다. 위 all-clear 배너와 같은 결로 명시한다.
          <DashSection title="최근 주요 변경">
            <Note sx={{ mt: 0 }}>최근 주요 변경 이력이 없습니다.</Note>
          </DashSection>
        )
      )}
    </Box>
  );
}
