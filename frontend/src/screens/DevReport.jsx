import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { useQueryState } from "../lib/useQueryState.js";
import {
  PageHeader, Card, Badge, Button, Callout, Skeleton, EmptyState, ErrorState, DataTable,
  Section, StatusDot,
} from "../ui/kit.jsx";
import { StatusSummaryCard } from "../ui/StatusKpi.jsx";
import { FilterBar } from "../ui/FilterBar.jsx";
import { FilterSelect } from "../ui/filters.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../ui/theme.js";
import { resolveChartColor } from "../ui/charts/base.jsx";

/* 고른 달은 **주소에** 둔다 (S15 · `lib/useQueryState.js`).
 *
 * 비어 있으면 「이번 달」이고, 그 달은 **서버가 정한다**(KST 오늘, 계획 3.7). 예전에는 브라우저
 * 시계로 이번 달을 만들어서, 한국 시간으로 1일 아침 9시 전에 연 사람은 서버의 「이번 달」과 다른
 * 달을 봤다. 주소에 값이 없으면 기간을 안 보내고, 서버가 응답에 싣는 달과 오늘(`period` · `today`)로
 * 선택지를 그린다. 이 저장소의 조건 상태는 `replace` 다. */
const DEV_REPORT_SPEC = { period: "" };

/** 'YYYY-MM' → 「2026년 3월」. 화면 설명이 지금 보고 있는 달을 그대로 말하게 한다. */
export function periodLabel(period) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(period || ""));
  return m ? `${m[1]}년 ${parseInt(m[2], 10)}월` : String(period || "");
}

// 연도 선택지 — 기준 연도(서버의 오늘)부터 과거 count년까지 내림차순.
function yearOptions(baseYear, count) {
  const y0 = parseInt(baseYear, 10);
  if (!y0) return [];
  const out = [];
  for (let i = 0; i < count; i += 1) out.push(y0 - i);
  return out;
}
// 월 선택지 — '01'~'12'.
const MONTH_VALUES = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

/* 상태 세그먼트의 순서와 색 — 상태 스택 막대(담당자별)와 그 범례(`StatusLegend`)가 **같은 표를 공유한다**.
 * 일곱 칸이고 합이 곧 담당이다(계획 3.7). 예전에는 보류와 기타가 없어서 막대의 합과 담당이 달랐다. */
const SEGS = [
  { key: "done", label: "완료", tone: "ok" },
  { key: "prog", label: "진행", tone: "brand" },
  { key: "verify", label: "검증", tone: "warn" },
  { key: "plan", label: "계획", tone: "neutral" },
  { key: "hold", label: "보류", tone: "info" },
  { key: "cancel", label: "취소", tone: "danger" },
  { key: "other", label: "기타", tone: "secondary" },
];

// 담당자 한 명의 상태 구성 스택 막대(SVG). 분모는 담당 수다 - 옆 칸의 수와 같은 합이다.
// aria-hidden이다 — 바로 옆 칸들이 상태별 수를 각각 숫자로 이미 보여준다.
function StatusBar({ d }) {
  const theme = useTheme();
  const total = SEGS.reduce((sum, seg) => sum + (d[seg.key] || 0), 0);
  let x = 0;
  const rects = [];
  if (total) {
    for (const seg of SEGS) {
      const n = d[seg.key];
      if (!n) continue;
      const w = (100 * n) / total;
      rects.push(<rect key={seg.key} x={x} y="0" width={w} height="12" fill={resolveChartColor(theme, seg.tone)} />);
      x += w;
    }
  }
  return (
    <Box
      component="svg" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true" focusable="false"
      sx={{ display: "block", width: "100%", height: "0.75rem", borderRadius: 1, overflow: "hidden" }}
    >
      <rect x="0" y="0" width="100" height="12" fill={theme.palette.divider} />
      {rects}
    </Box>
  );
}

/* 상태 막대의 범례 — 구획 제목 줄 오른쪽 끝에 한 줄로 선다. 점 옆 낱말이 뜻을 나르므로 색을 못 봐도
 * 막대 옆 칸의 수로 같은 것을 읽는다(WCAG 1.4.1). */
function StatusLegend() {
  const theme = useTheme();
  return (
    <Box component="ul" aria-label="상태 구성 막대의 색" sx={{ listStyle: "none", m: 0, p: 0, display: "flex", flexWrap: "wrap", columnGap: 1.5, rowGap: 0.25 }}>
      {SEGS.map((seg) => (
        <Box component="li" key={seg.key} sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
          <StatusDot accent={resolveChartColor(theme, seg.tone)} />
          {seg.label}
        </Box>
      ))}
    </Box>
  );
}

function num(v) { return v == null ? "-" : v; }
// 0과 '-'는 옅게 — 숫자 벽에서 '값이 있는 칸'이 먼저 눈에 들어오게 한다.
function Zed({ children }) {
  return <Box component="span" sx={{ color: "text.disabled" }}>{children}</Box>;
}
function zed(v) { return v ? String(v) : <Zed>0</Zed>; }

/* 표 자리 — 판은 표가 그린다(`DataTable placement="surface"`, 조합 계약 C-3). 이 상자는 표의 바닥 폭과
 * 인쇄 규칙만 준다. 가로 스크롤은 표 자신의 상자 안에서만 일어난다. */
function TableWrap({ minWidth = "45rem", children }) {
  return (
    <Box sx={{ minWidth: 0, "& table": { minWidth }, "@media print": { "& .MuiTableContainer-root": { overflow: "visible" } } }}>
      {children}
    </Box>
  );
}

const STATE_KO = { inactive: "비활성", archived: "보관" };

/* 사람 이름 칸. 묶는 키는 이름이 아니라 **사람 id** 다(계획 3.7). 같은 이름이 두 줄이면 서버가
 * `ambiguous_name` 을 켜고, 화면은 이메일을 붙여 둘을 가른다. 비활성 · 보관 계정은 표식을 단다. */
export function devLabel(d) {
  if (!d) return "";
  return d.ambiguous_name && d.email ? `${d.name} (${d.email})` : d.name;
}

const devNameCol = {
  key: "name", label: "개발자", type: "name", minWidth: "10rem", rowName: (d) => devLabel(d),
  help: "티켓 담당자입니다. 같은 이름이 둘이면 이메일로 구별합니다.",
  render: (d) => (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
      <Box component="span" sx={{ fontWeight: d.has_tickets ? FONT_WEIGHT.bold : FONT_WEIGHT.regular,
                                  color: d.has_tickets ? "text.primary" : "text.secondary" }}>{devLabel(d)}</Box>
      {STATE_KO[d.state] ? <Badge value={STATE_KO[d.state]} kind="neutral" /> : null}
    </Box>
  ),
};

/* 표의 열 도움말은 **서버의 정의 문장**을 그대로 쓴다(`definitions`). 숫자를 계산한 쪽이 그 계산을
 * 말해야 둘이 갈라지지 않는다. */
function devSummaryColumns(defs) {
  return [
    devNameCol,
    { key: "_bar", label: "상태 구성", type: "text", minWidth: "14rem",
      help: "담당한 티켓의 상태 비율을 색 막대로 나타냅니다. 색은 이 표 위 범례와 같습니다.",
      render: (d) => <StatusBar d={d} /> },
    { key: "done", label: "완료", type: "count", help: "마감일이 이 달인 티켓 중 완료 상태인 티켓 수입니다.",
      render: (d) => <Box component="span" sx={{ color: "success.main", fontWeight: FONT_WEIGHT.bold }}>{d.done}</Box> },
    { key: "prog", label: "진행", type: "count", help: "진행 상태인 티켓 수입니다.", render: (d) => zed(d.prog) },
    { key: "verify", label: "검증", type: "count", help: "검증 상태인 티켓 수입니다.", render: (d) => zed(d.verify) },
    { key: "plan", label: "계획", type: "count", help: "아직 시작하지 않은 계획 상태 티켓 수입니다.", render: (d) => zed(d.plan) },
    { key: "hold", label: "보류", type: "count", help: "멈춰 둔 보류 상태 티켓 수입니다.", render: (d) => zed(d.hold) },
    { key: "cancel", label: "취소", type: "count", help: "취소된 티켓 수입니다.", render: (d) => zed(d.cancel) },
    { key: "other", label: "기타", type: "count", help: defs.other, render: (d) => zed(d.other) },
    { key: "assigned", label: "담당", type: "count", help: defs.assigned, render: (d) => zed(d.assigned) },
    { key: "completion_rate", label: "완료율", type: "percent", help: defs.completion_rate,
      render: (d) => (d.completion_rate == null ? <Zed>-</Zed> : d.completion_rate + "%") },
    { key: "overdue", label: "지연", type: "count", help: defs.overdue,
      render: (d) => (d.overdue > 0 ? <Badge value={d.overdue} kind="danger" /> : <Zed>0</Zed>) },
    { key: "_no_due", label: "마감 없음", type: "count", help: defs.no_due_open,
      render: (d) => zed(d.no_due ? d.no_due.open : 0) },
  ];
}

function devWorkloadColumns(defs) {
  return [
    { ...devNameCol, help: "티켓 담당자입니다." },
    { key: "done", label: "완료", type: "count", help: "완료한 티켓 수입니다.", render: (d) => zed(d.done) },
    { key: "_active", label: "진행과 검증", type: "count", help: "진행과 검증 상태를 합한 티켓 수입니다.",
      render: (d) => zed((d.prog || 0) + (d.verify || 0)) },
    { key: "est_done", label: "완료 업무량", type: "number",
      help: "마감일이 이 달인 완료 티켓들의 예상 공수 합(인일)입니다.",
      render: (d) => <Box component="span" sx={{ color: "success.main", fontWeight: FONT_WEIGHT.bold }}>{d.est_done}</Box> },
    { key: "est_all", label: "맡은 업무량", type: "number",
      help: "맡은 티켓 전체(취소 제외, 아직 안 끝낸 것 포함)의 예상 공수 합(인일)입니다. 완료 업무량과의 차이가 남은 업무량입니다." },
    { key: "act_done", label: "실제 WD", type: "number",
      help: "완료한 티켓에 실제로 든 공수입니다. 담당자가 직접 입력해야 채워지는 값이라, 아무도 안 적었으면 '-'로 보입니다.",
      render: (d) => (d.act_done ? d.act_done : <Zed>-</Zed>) },
    { key: "act_per_done", label: "평균 실제WD/건", type: "number",
      help: "완료한 티켓 1건당 평균 실제 공수입니다. 실제 WD를 완료 건수로 나눈 값입니다.",
      render: (d) => (d.act_per_done == null ? <Zed>-</Zed> : d.act_per_done) },
    { key: "estimate_accuracy_pct", label: "예상 정확도", type: "percent", help: defs.estimate_accuracy_pct,
      render: (d) => (d.estimate_accuracy_pct == null ? <Zed>-</Zed> : d.estimate_accuracy_pct + "%") },
    { key: "difficulty_avg", label: "난이도 평균", type: "score",
      help: "맡은 티켓들의 난이도 평균입니다. 1에서 6까지이고 취소는 제외하며, 추정치입니다.",
      render: (d) => (d.difficulty_avg == null ? <Zed>-</Zed> : d.difficulty_avg) },
  ];
}

/* 이 달에 끝낸 일 — 완료일 축(계획 3.7). 마감일과 관계없이 끝낸 달에 센다. */
function devCompletedColumns(defs) {
  return [
    { ...devNameCol, help: "티켓 담당자입니다." },
    { key: "_c_done", label: "끝낸 일", type: "count", help: defs.completed_done,
      render: (d) => zed(d.completed ? d.completed.done : 0) },
    { key: "_c_late", label: "늦게 끝냄", type: "count", help: defs.late_done,
      render: (d) => {
        const n = d.completed ? d.completed.late_done : 0;
        return n > 0 ? <Badge value={n} kind="warn" /> : <Zed>0</Zed>;
      } },
    { key: "_c_est", label: "끝낸 일의 예상 WD", type: "number",
      help: "이 달에 끝낸 티켓들의 예상 공수 합(인일)입니다.",
      render: (d) => (d.completed && d.completed.est_done ? d.completed.est_done : <Zed>-</Zed>) },
    { key: "_c_act", label: "끝낸 일의 실제 WD", type: "number",
      help: "이 달에 끝낸 티켓들의 실제 공수 합(인일)입니다.",
      render: (d) => (d.completed && d.completed.act_done ? d.completed.act_done : <Zed>-</Zed>) },
  ];
}

/* 담당자별 상세 티켓 — 담당자 구분 행 하나 때문에 오래 `DataTable` 밖에 있었다. 지금은
 * 표가 그 줄을 갖는다(`groupOf`)이라 위 두 표와 같은 부품이고, 폭·정렬·자릿수도 같은
 * 어휘표(`columnTypes.js`)에서 나온다. */
const DEV_TICKET_COLUMNS = [
  { key: "key", label: "번호", type: "identifier", help: "티켓 이름입니다(프로젝트 코드와 순번).",
    render: (t) => t.key || "-" },
  { key: "title", label: "제목", type: "title", minWidth: "14rem", rowName: (t) => t.title },
  { key: "status", label: "상태", type: "status", help: "티켓의 진행 상태입니다.",
    render: (t) => <Badge value={t.status || "-"} /> },
  { key: "due", label: "마감일", type: "date", help: "티켓 마감일입니다.", render: (t) => t.due || "-" },
  { key: "priority", label: "우선순위", type: "status", help: "티켓 우선순위입니다(높음, 중간, 낮음).",
    render: (t) => t.priority || "-" },
  { key: "difficulty", label: "난이도", type: "score", help: "티켓 난이도입니다(1에서 6까지, 추정치).",
    render: (t) => num(t.difficulty) },
  { key: "est_wd", label: "예상 WD", type: "number", help: "이 티켓의 예상 공수입니다(인일, 추정치).",
    render: (t) => num(t.est_wd) },
  { key: "act_wd", label: "실제 WD", type: "number",
    help: "이 티켓에 실제로 든 공수입니다. 담당자 입력값이며 현재는 추정치입니다.",
    render: (t) => (t.act_wd == null ? <Zed>-</Zed> : t.act_wd) },
  { key: "overdue", label: "지연", type: "status", help: "마감일이 지났는데 완료되지 않은 티켓을 표시합니다.",
    render: (t) => (t.overdue ? <Badge value="지연" kind="danger" /> : "") },
];

/* 개발자 월간 리포트 — 마감일이 그 달인 티켓을 담당자별로 묶어 보여 주고(마감일 축), 그 달에 끝낸 일을
 * 끝낸 날짜로 따로 센다(완료일 축, 계획 3.7). 숫자는 전부 서버가 계산한다 - 화면은 나누지도 반올림하지도
 * 않는다. 팀 합계 카드로 요약을 먼저 주고, 표는 그 아래에 둔다. */
export function DevReport() {
  const [view, setView] = useQueryState(DEV_REPORT_SPEC);
  const asked = view.period || "";
  const query = useQuery({
    queryKey: ["dev-report", asked || "current"],
    queryFn: () => api("/api/admin/reports/dev-monthly" + (asked ? "?period=" + encodeURIComponent(asked) : "")),
    retry: false,
  });
  const data = query.data;
  const ok = data && data.ok;
  // 보고 있는 달 — 고른 달이 있으면 그것, 없으면 서버가 정한 이번 달이다.
  const period = asked || (data && data.period) || "";
  const baseYear = ((data && data.today) || period).slice(0, 4);
  const setPeriod = (next) => setView({ period: next });
  const defs = (ok && data.definitions) || {};
  const devs = ok ? data.developers : [];
  const withTickets = ok ? devs.filter((d) => d.has_tickets) : [];
  const withCompleted = ok ? devs.filter((d) => d.completed && d.completed.done) : [];
  const devKey = (d) => d.user_id || "unknown";
  /* 담당자별 상세는 **한 표 안에서** 담당자로 묶인다 — 행을 평평하게 편 뒤 각 행이 자기 담당자를 들고
     다닌다. 묶음 키는 사람 id 다(같은 이름의 두 사람이 한 묶음이 되지 않게). */
  const detailRows = withTickets.flatMap((d) => (d.tickets || []).map((t) => ({
    ...t,
    _devKey: devKey(d),
    _devLabel: devLabel(d),
    _devNote: `완료 ${d.done}건, 진행과 검증 ${(d.prog || 0) + (d.verify || 0)}건, 완료 예상 WD ${d.est_done}인일`,
  })));
  const team = ok ? data.team : null;
  const completedTeam = ok && data.completed ? data.completed.team : null;
  const unknownDate = ok && data.completed ? data.completed.unknown_date : null;
  const noDueTeam = ok && data.no_due ? data.no_due.team.open : 0;

  return (
    <Box className="c-screen"
      sx={{
        // 인쇄: 카드 그림자는 회색 얼룩으로만 나오고, 섹션이 페이지 중간에서 잘리면 표 머리가 사라진다.
        "@media print": { "& .MuiPaper-root": { boxShadow: "none" }, "& section": { breakInside: "avoid" } },
      }}>
      <PageHeader area="감사" title="개발자 월간 리포트"
        description={period ? "마감일이 " + periodLabel(period) + "인 티켓을 담당자별로 모아 업무량과 위험을 봅니다." : "마감일이 이 달인 티켓을 담당자별로 모아 업무량과 위험을 봅니다."}
        help="마감일이 선택한 달인 티켓을 담당자별로 집계합니다. 그 달에 끝낸 일은 끝낸 날짜로 따로 셉니다. 사람은 이름이 아니라 계정으로 묶으므로 같은 이름의 두 사람은 두 줄로 보입니다. 예상 WD와 난이도는 추정한 값이고, 실제 WD는 완료한 담당자가 입력합니다."
        actions={<Button onClick={() => query.refetch()} disabled={query.isFetching} loading={query.isFetching}>새로고침</Button>} />

      <FilterBar
        sx={{ "@media print": { display: "none" } }}
        end={<Button onClick={() => window.print()}>인쇄하거나 PDF로 저장</Button>}
      >
        <FilterSelect
          label="연도" value={period.slice(0, 4)} noAllOption disabled={!period}
          onChange={(v) => setPeriod(v + "-" + period.slice(5, 7))}
          options={yearOptions(baseYear, 5).map((y) => ({ value: String(y), label: y + "년" }))}
        />
        <FilterSelect
          label="월" value={period.slice(5, 7)} noAllOption disabled={!period}
          onChange={(v) => setPeriod(period.slice(0, 4) + "-" + v)}
          options={MONTH_VALUES.map((m) => ({ value: m, label: parseInt(m, 10) + "월" }))}
        />
      </FilterBar>

      {query.isLoading ? (
        <Card><Skeleton kind="chart" /></Card>
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : data && data.configured === false ? (
        <Card>
          <Callout tone="warn">
            지금은 리포트를 만들 수 없습니다. 잠시 뒤 새로고침해 보시고, 계속 같으면 관리자에게 문의하세요.
          </Callout>
        </Card>
      ) : data && ok === false ? (
        <ErrorState layout="region" error={{ message: data.error || "리포트를 불러오지 못했습니다." }} onRetry={() => query.refetch()} />
      ) : ok ? (
        <>
          {/* 팀 합계는 **구성**이다 — 완료 · 진행 중 · 검증 · 계획 · 보류(· 기타)의 합이 전체이고, 취소는 할 일이
              아니라서 합계 밖에 둔다(완료율 분모와 같은 선). 지연 · 담당자 없음은 그 위의 신호다. */}
          <StatusSummaryCard
            ariaLabel="팀 합계"
            sx={{ mb: 4 }}
            unit="건"
            total={team.total - team.cancel}
            items={[
              { key: "done", kind: "ok", value: team.done, label: "완료" },
              { key: "in_progress", kind: "info", value: team.in_progress, label: "진행 중" },
              { key: "verify", kind: "warn", value: team.verify, label: "검증" },
              { key: "plan", kind: "neutral", value: team.plan, label: "계획" },
              { key: "hold", kind: "neutral", value: team.hold, label: "보류" },
              team.other ? { key: "other", kind: "neutral", value: team.other, label: "기타" } : null,
            ]}
            risks={[
              { key: "overdue", kind: "danger", value: team.overdue, label: "지연" },
              { key: "unassigned", kind: "warn", value: data.unassigned.total, label: "담당자 없음" },
            ]}
            notes={[
              { key: "done", label: "완료", text: "완료 예상 WD " + team.est_done_total + "인일" + (team.completion_rate != null ? ", 완료율 " + team.completion_rate + "%" : "") },
              { key: "in_progress", label: "진행 중", text: "지금 하고 있는 일" },
              { key: "verify", label: "검증", text: "검토와 확인 단계" },
              { key: "plan", label: "계획", text: "아직 착수 전" },
              { key: "hold", label: "보류", text: "멈춰 둔 일" },
              { key: "overdue", label: "지연", text: "마감이 지난 미완료" },
              { key: "unassigned", label: "담당자 없음", text: "담당자가 지정되지 않음" },
              team.cancel > 0 ? { key: "cancel", label: "취소", text: team.cancel + "건은 합계에서 뺐습니다." } : null,
              noDueTeam > 0 ? { key: "no_due", label: "마감 없음", text: "마감일이 없는 열린 티켓 " + noDueTeam + "건은 지금 기준으로 따로 셉니다." } : null,
              { key: "unit", label: "세는 법", text: "팀 합계는 티켓 단위로 셉니다. 담당자별 합계는 담당자가 둘인 티켓을 양쪽에 각각 세므로 이 합과 다를 수 있습니다." },
            ]}
          />

          <Section titleAs="h2" title={`개발자별 상세 (${data.period})`} rule
            action={devs.length ? <StatusLegend /> : null}>
            {devs.length === 0 ? (
              <EmptyState art="tickets" title="이 달에 집계할 담당자가 없습니다"
                help="선택한 달에 마감일이 있는 티켓이 없거나, 활성 사용자가 없습니다."
                situation="기간을 바꾸거나, 사용자 화면에서 담당자 계정이 활성 상태인지 확인하세요." />
            ) : (
              <TableWrap minWidth="60rem">
                {/* 집계 표라 「받았다」는 건수를 말하지 않는다(`list={false}`) — 행은 받은 목록이 아니라 사람별 합이다. */}
                <DataTable placement="surface" list={false} columns={devSummaryColumns(defs)} rows={devs} rowKey={devKey} />
              </TableWrap>
            )}
          </Section>

          <Section titleAs="h2" title="업무량 분석 (완료 업무량 기준)" rule
            help={(
              <Box component="span" sx={{ display: "block", maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK }}>
                완료 건수와 완료 예상 WD는 마감일이 이 달인 일 가운데 마무리한 양입니다. 진행과 검증 건수가 많으면 지금 손에 쥔 일이 많다는 뜻입니다. 담당 건수가 적으면 완료율이 쉽게 높아지므로 담당 건수와 함께 보아야 공정합니다.
              </Box>
            )}>
            <TableWrap minWidth="52rem">
              <DataTable placement="surface" list={false} columns={devWorkloadColumns(defs)} rows={devs} rowKey={devKey} />
            </TableWrap>
          </Section>

          <Section titleAs="h2" title={`이 달에 끝낸 일 (${data.period})`} rule
            help={(
              <Box component="span" sx={{ display: "block", maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK }}>
                {defs.completed_done} {completedTeam ? "팀 전체로는 " + completedTeam.done + "건을 끝냈고, 그중 " + completedTeam.late_done + "건은 마감일보다 늦게 끝냈습니다." : ""}
              </Box>
            )}>
            {unknownDate ? (
              <Callout tone="info" sx={{ mb: 1.5 }}>
                {"끝낸 날짜를 모르는 완료 티켓 " + unknownDate + "건은 이 표에 들어가지 않았습니다. 이관한 데이터에 끝낸 날짜가 없기 때문입니다."}
              </Callout>
            ) : null}
            {withCompleted.length === 0 ? (
              <EmptyState art="tickets" title="이 달에 끝낸 일이 없습니다"
                help="끝낸 날짜가 이 달인 완료 티켓이 생기면 여기에 담당자별로 보입니다." />
            ) : (
              <TableWrap minWidth="40rem">
                <DataTable placement="surface" list={false} columns={devCompletedColumns(defs)} rows={withCompleted} rowKey={devKey} />
              </TableWrap>
            )}
          </Section>

          <Section titleAs="h2" title="담당자별 상세 티켓" rule>
            {withTickets.length === 0 ? (
              <EmptyState art="tickets" title="이 달에 담당한 티켓이 있는 사람이 없습니다"
                help="선택한 달에 마감일이 있는 티켓이 배정되면 여기에 담당자별로 묶여 표시됩니다." />
            ) : (
              <TableWrap minWidth="56rem">
                <DataTable
                  placement="surface"
                  columns={DEV_TICKET_COLUMNS}
                  rows={detailRows}
                  rowKey={(t) => t._devKey + ":" + (t.uid || t.tid || t.title)}
                  groupOf={(t) => ({ key: t._devKey, label: t._devLabel, note: t._devNote })}
                />
              </TableWrap>
            )}
          </Section>
        </>
      ) : null}
    </Box>
  );
}
