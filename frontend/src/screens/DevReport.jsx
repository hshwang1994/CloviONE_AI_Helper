import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { PageHeader, Card, Badge, Button, Callout, Skeleton, EmptyState, ErrorState, MetricStrip, DataTable, tableCellProps } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { Donut } from "../ui/charts/Donut.jsx";
import { resolveChartColor } from "../ui/charts/base.jsx";
import { Note } from "../ui/adminKit.jsx";

// 이번 달을 'YYYY-MM'으로. 리포트는 마감일 기준이라 월만 쓴다.
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// 연도 선택지 — 올해부터 과거 count년까지 내림차순.
function yearOptions(count) {
  const y0 = new Date().getFullYear();
  const out = [];
  for (let i = 0; i < count; i += 1) out.push(y0 - i);
  return out;
}
// 월 선택지 — '01'~'12'.
const MONTH_VALUES = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

/* 상태 세그먼트의 순서와 색 — 상태 스택 막대(담당자별)와 팀 도넛이 **같은 표를 공유한다**.
 * 예전에는 막대 색은 screens.css(.seg-done…)에, 범례 색은 또 다른 규칙(.devrep-legend i.done)에
 * 따로 적혀 있어서 한쪽만 고치면 같은 상태가 두 색으로 보였다. 색 어휘는 키트의 톤 이름
 * (ok/warn/danger/neutral)을 그대로 쓴다 — 배지·타일과 같은 말이라 나중에도 어긋나지 않는다. */
const SEGS = [
  { key: "done", label: "완료", tone: "ok" },
  { key: "prog", label: "진행", tone: "brand" },
  { key: "verify", label: "검증", tone: "warn" },
  { key: "plan", label: "계획", tone: "neutral" },
  { key: "cancel", label: "취소", tone: "danger" },
];

// 담당자 한 명의 상태 구성 스택 막대(SVG).
// aria-hidden이다 — 바로 옆 칸들이 완료/진행/검증/계획/취소 수를 각각 숫자로 이미 보여준다.
// 예전엔 이 막대에 다섯 숫자를 그대로 담은 aria-label이 붙어 있어 스크린리더가 같은 행을 두 번 읽었다.
function StatusBar({ d }) {
  const theme = useTheme();
  const total = d.done + d.prog + d.verify + d.plan + d.cancel;
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

function num(v) { return v == null ? "-" : v; }
// 0과 '-'는 옅게 — 숫자 벽에서 '값이 있는 칸'이 먼저 눈에 들어오게 한다.
function Zed({ children }) {
  return <Box component="span" sx={{ color: "text.disabled" }}>{children}</Box>;
}
function zed(v) { return v ? String(v) : <Zed>0</Zed>; }

/* 표 껍데기 — 가로 스크롤은 표 자신의 상자 안에서만 일어난다(페이지 전체가 가로로 밀리면
 * 4K QA의 horizontal_overflow에 걸린다). min-width는 rem이라 4K에서 함께 커진다.
 * devrep-tablewrap 클래스는 그대로 둔다 — screens.css의 인쇄 규칙이 이 이름을 본다.
 *
 * **이 상자는 이제 표를 직접 그리지 않는다.** 예전에는 여기서 `<Table>` 을 열고 화면이
 * `<Th>`·`<TableCell>` 을 손으로 적었다 — 그래서 이 화면의 열 폭·정렬·자릿수 규칙이
 * `DataTable` 의 것과 **따로** 살았고, 공용 계약을 고쳐도 여기는 안 따라왔다(C3 이 이
 * 파일을 이름으로 지목한 이유다). 지금은 안에 `DataTable` 이 들어온다. */
function TableWrap({ minWidth = "45rem", children }) {
  return (
    <Box className="devrep-tablewrap"
      sx={{
        overflowX: "auto", border: 1, borderColor: "divider", borderRadius: 2, bgcolor: "background.paper",
        "& table": { minWidth },
        "@media print": { border: 0, overflow: "visible" },
      }}>
      {children}
    </Box>
  );
}

/* 표 셋의 열 정의. **폭·정렬·자릿수는 여기서 안 적는다** — `type` 이 그것을 말하고
 * `columnTypes.js` 의 어휘표가 값을 준다. 여기 남는 것은 «무엇을 그리나»(render)와
 * «이 열이 무슨 뜻인가»(help)뿐이다. */
const devNameCol = {
  key: "name", label: "개발자", type: "name", rowName: (d) => d.name,
  help: "티켓 담당자입니다. 이름은 사용자 연결로 해석했습니다.",
  render: (d) => (
    <Box component="span" sx={{ fontWeight: d.has_tickets ? FONT_WEIGHT.bold : FONT_WEIGHT.regular,
                                color: d.has_tickets ? "text.primary" : "text.secondary" }}>{d.name}</Box>
  ),
};

const DEV_SUMMARY_COLUMNS = [
  devNameCol,
  { key: "_bar", label: "상태 구성", type: "text", minWidth: "14rem",
    help: "담당한 티켓의 상태 비율을 색 막대로 나타냅니다. 오른쪽 도넛의 범례와 같은 색입니다.",
    render: (d) => <StatusBar d={d} /> },
  { key: "done", label: "완료", type: "count", help: "이번 달 마감분 가운데 완료 상태인 티켓 수입니다.",
    render: (d) => <Box component="span" sx={{ color: "success.main", fontWeight: FONT_WEIGHT.bold }}>{d.done}</Box> },
  { key: "prog", label: "진행", type: "count", help: "진행 상태인 티켓 수입니다.", render: (d) => zed(d.prog) },
  { key: "verify", label: "검증", type: "count", help: "검증 상태인 티켓 수입니다.", render: (d) => zed(d.verify) },
  { key: "plan", label: "계획", type: "count", help: "아직 시작하지 않은 계획 상태 티켓 수입니다.", render: (d) => zed(d.plan) },
  { key: "cancel", label: "취소", type: "count", help: "취소된 티켓 수입니다.", render: (d) => zed(d.cancel) },
  { key: "assigned", label: "담당", type: "count",
    help: "이 사람에게 배정된 이번 달 마감 티켓 수입니다. 티켓 하나에 담당자가 둘이면 양쪽에 각각 셉니다.",
    render: (d) => zed(d.assigned) },
  { key: "completion_rate", label: "완료율", type: "percent",
    help: "담당한 일 가운데 완료한 비율입니다. 취소는 제외하며, 완료를 담당에서 취소를 뺀 수로 나눕니다.",
    render: (d) => (d.completion_rate == null ? <Zed>-</Zed> : d.completion_rate + "%") },
  { key: "overdue", label: "지연", type: "count", help: "마감일이 지났는데 아직 완료되지 않은 티켓 수입니다.",
    render: (d) => (d.overdue > 0 ? <Badge value={d.overdue} kind="danger" /> : <Zed>0</Zed>) },
];

const DEV_WORKLOAD_COLUMNS = [
  { ...devNameCol, help: "티켓 담당자입니다." },
  { key: "done", label: "완료", type: "count", help: "완료한 티켓 수입니다.", render: (d) => zed(d.done) },
  { key: "_active", label: "진행 중", type: "count", help: "진행과 검증을 합한 티켓 수입니다.",
    render: (d) => zed(d.prog + d.verify) },
  { key: "est_done", label: "완료 업무량", type: "number",
    help: "이번 달 완료한 티켓들의 예상 공수 합(인일). 예상 기준으로 이 사람이 이번 달에 끝낸 업무량입니다.",
    render: (d) => <Box component="span" sx={{ color: "success.main", fontWeight: FONT_WEIGHT.bold }}>{d.est_done}</Box> },
  { key: "est_all", label: "맡은 업무량", type: "number",
    help: "맡은 티켓 전체(취소 제외, 아직 안 끝낸 것 포함)의 예상 공수 합(인일). '완료 업무량'보다 크거나 같고, 둘의 차이가 남은 업무량입니다." },
  { key: "act_done", label: "실제 WD", type: "number",
    help: "완료한 티켓에 실제로 든 공수입니다. 담당자가 직접 입력해야 채워지는 값이라, 아무도 안 적었으면 0으로 집계돼 '-'로 보입니다(예상치로 대신 채우지 않습니다).",
    render: (d) => (d.act_done ? d.act_done : <Zed>-</Zed>) },
  { key: "_per", label: "평균 실제WD/건", type: "number",
    help: "이 사람이 완료한 티켓 1건당 평균 실제 공수입니다. 실제 WD를 완료 건수로 나눈 값이라, 티켓 크기가 다른 사람끼리 부담을 비교할 때 씁니다.",
    render: (d) => (d.done && d.act_done ? (d.act_done / d.done).toFixed(1) : <Zed>-</Zed>) },
  { key: "_accuracy", label: "예상 정확도", type: "percent",
    help: "완료 티켓의 실제 공수를 예상 공수로 나눈 비율입니다. 100%면 예상과 같고, 100%보다 크면 예상보다 오래 걸렸다는 뜻입니다(견적 정확도).",
    render: (d) => (d.est_done && d.act_done ? Math.round((100 * d.act_done) / d.est_done) + "%" : <Zed>-</Zed>) },
  { key: "difficulty_avg", label: "난이도 평균", type: "score",
    help: "맡은 티켓들의 난이도 평균입니다. 1에서 6까지이고 취소는 제외하며, 추정치입니다.",
    render: (d) => (d.difficulty_avg == null ? <Zed>-</Zed> : d.difficulty_avg) },
];

/* 담당자별 상세 티켓 — 담당자 구분 행이 있어서 `DataTable` 로 접을 수 없다. 그렇다고 폭·정렬
 * 규칙을 여기 다시 적지는 않는다: 열 정의를 만들고 `tableCellProps` 가 **공용 규칙**을 읽는다
 * (`MyTickets` 의 묶음 목록과 같은 처리). */
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

/* 개발자 월간 리포트 — 마감일이 그 달인 티켓을 담당자별로 묶어 보여준다.
 * KPI 타일과 상태 구성 도넛으로 요약을 먼저 주고, 표는 그 아래에 둔다. 담당자별 업무량은
 * 그림이 아니라 표가 말한다 — 그림과 표가 같은 숫자를 두 번 말하던 자리를 W6 이 정리했다.
 * 그림은 전부 ui/charts의 의존성 없는 SVG다(차트 라이브러리를 들이지 않는다 — 번들 예산). */
export function DevReport() {
  const [period, setPeriod] = useState(thisMonth());
  const query = useQuery({
    queryKey: ["dev-report", period],
    queryFn: () => api("/api/admin/reports/dev-monthly?period=" + encodeURIComponent(period)),
    retry: false,
  });
  const data = query.data;
  const ok = data && data.ok;
  const devs = ok ? data.developers : [];
  const withTickets = ok ? devs.filter((d) => d.has_tickets) : [];
  // 팀 상태 구성 — 백엔드가 티켓 단위(중복 없이)로 센 값이다. 다섯 상태에 속하지 않는 티켓이
  // 있으면(작업 DB에 새 상태가 생기는 경우) 조각 합이 total보다 작아진다, 그 차이를 '기타'로
  // 드러낸다 — 조용히 사라지면 도넛이 전체를 설명한다고 착각하게 된다.
  const team = ok ? data.team : null;
  const teamSegs = team ? (() => {
    const base = [
      { label: "완료", value: team.done, color: "ok" },
      { label: "진행 중", value: team.in_progress, color: "brand" },
      { label: "검증", value: team.verify, color: "warn" },
      { label: "계획", value: team.plan, color: "neutral" },
      { label: "취소", value: team.cancel, color: "danger" },
    ];
    const rest = team.total - base.reduce((s, b) => s + (b.value || 0), 0);
    return rest > 0 ? [...base, { label: "기타", value: rest, color: "info" }] : base;
  })() : [];

  return (
    <Box className="devrep c-screen"
      sx={{
        /* 자릿수 고정을 예전에는 **화면 전체**에 걸었다 — 산문과 라벨까지 고정폭 숫자를 쓰면
           «2026년 8월» 의 숫자 사이가 벌어진다. 이제 열이 자기 타입으로 말하고 그 열만
           고정한다(`columnTypes.js`). 표 밖의 지표 줄은 `MetricStrip` 이 자기 것을 건다. */
        // 인쇄: 카드 그림자는 회색 얼룩으로만 나오고, 섹션이 페이지 중간에서 잘리면 표 머리가 사라진다.
        "@media print": { "& .MuiPaper-root": { boxShadow: "none" }, "& section": { breakInside: "avoid" } },
      }}>
      <PageHeader area="자동화" title="개발자 월간 리포트" spot="sprint"
        actions={<Button variant="primary" onClick={() => query.refetch()}>새로고침</Button>} />

      <Box sx={{ mb: 3 }}>
        <Note sx={{ mt: 0 }}>
          마감일이 선택한 달인 티켓을 담당자별로 집계합니다. 각자 얼마나 일했는지는 완료 건수와 예상 WD로 보고, 지금 안고 있는 부담과 위험은 진행 중 업무와 지연으로 함께 봅니다. 예상 WD와 난이도는 티켓 내용을 바탕으로 추정한 값이고, 실제 WD는 완료한 담당자가 입력합니다.
        </Note>
      </Box>

      <Card className="devrep-noprint" sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap" }}>
          <TextField
            InputLabelProps={{ shrink: true }}
            id="devrep-year" select size="small" label="연도" value={period.slice(0, 4)}
            onChange={(e) => setPeriod(e.target.value + "-" + period.slice(5, 7))}
            sx={{ minWidth: "8rem" }}
          >
            {yearOptions(5).map((y) => <MenuItem key={y} value={String(y)}>{y}년</MenuItem>)}
          </TextField>
          <TextField
            InputLabelProps={{ shrink: true }}
            id="devrep-month" select size="small" label="월" value={period.slice(5, 7)}
            onChange={(e) => setPeriod(period.slice(0, 4) + "-" + e.target.value)}
            sx={{ minWidth: "7rem" }}
          >
            {MONTH_VALUES.map((m) => <MenuItem key={m} value={m}>{parseInt(m, 10)}월</MenuItem>)}
          </TextField>
          <Button onClick={() => window.print()}>인쇄하거나 PDF로 저장</Button>
        </Box>
      </Card>

      {query.isLoading ? (
        <Card><Skeleton lines={6} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : data && data.configured === false ? (
        // 이 갈래는 더 이상 안 열린다 — 티켓의 정본이 이 서버라 사람이 채워 넣을 접속
        // 설정이 없다(S14 · D-284). 응답 모양은 남아 있으므로 갈래도 남기되, 없어진
        // 절차를 안내하지는 않는다.
        <Card>
          <Callout tone="warn">
            지금은 리포트를 만들 수 없습니다. 잠시 뒤 새로고침해 보시고, 계속 같으면 관리자에게 문의하세요.
          </Callout>
        </Card>
      ) : data && ok === false ? (
        <ErrorState error={{ message: data.error || "리포트를 불러오지 못했습니다." }} onRetry={() => query.refetch()} />
      ) : ok ? (
        <>
          {/* 각 칸의 셋째 줄은 '이 숫자가 무엇을 센 것인지'다 — 정의가 사라지면 숫자를
              신뢰할 수 없다. 판독 줄이 값·라벨·각주 셋을 모두 모델링하므로 예전처럼 라벨
              자리에 두 줄을 밀어 넣지 않는다(KpiLabel 을 없앤 이유). */}
          <MetricStrip
            ariaLabel="팀 합계"
            sx={{ mb: 4 }}
            items={[
              { key: "done", kind: "ok", value: data.team.done + "건", label: "완료", primary: true,
                note: "취소를 뺀 기준 완료 " + data.team.est_done_total + "인일" },
              { key: "in_progress", value: data.team.in_progress + "건", label: "진행 중", note: "진행과 이슈 상태" },
              { key: "verify", value: data.team.verify + "건", label: "검증", note: "검토, 확인 단계" },
              { key: "plan", value: data.team.plan + "건", label: "계획", note: "아직 착수 전" },
              { key: "overdue", kind: data.team.overdue > 0 ? "danger" : undefined, value: data.team.overdue + "건",
                label: "지연", note: "마감이 지난 미완료" },
              { key: "unassigned", value: data.unassigned.total + "건", label: "담당자 없음",
                note: "담당자가 지정되지 않음" },
            ]}
          />

          <Box component="section" sx={{ mb: 4 }}>
            <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>개발자별 상세 ({data.period})</Typography>
            {devs.length === 0 ? (
              <Card>
                <EmptyState art="tickets" title="이 달에 집계할 담당자가 없습니다"
                  help="선택한 달에 마감일이 있는 티켓이 없거나, 앱에 활성 사용자가 추가되어 있지 않습니다."
                  situation="기간을 바꾸거나, 사용자 화면에서 담당자 계정이 활성 상태인지 확인하세요." />
              </Card>
            ) : (
              /* 폭이 아주 넓을 때(xxl 이상)만 도넛을 표 옆에 세운다 — 1366·1920에서 옆에 두면
                 열 열 개짜리 표가 눌려 가로 스크롤이 생긴다. 도넛의 범례가 곧 아래 스택 막대의
                 색 범례라, 따로 범례 줄을 두지 않는다(예전 .devrep-legend를 대신한다). */
              <Box sx={{ display: "grid", gap: 2, alignItems: "start", gridTemplateColumns: { xs: "1fr", xxl: "minmax(0,1fr) minmax(0,26rem)" } }}>
                <TableWrap minWidth="52rem">
                  <DataTable columns={DEV_SUMMARY_COLUMNS} rows={devs} rowKey={(d) => d.name} />
                </TableWrap>
                <Card sx={{ p: 2.5 }}>
                  <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1.5 }}>팀 상태 구성</Typography>
                  <Donut question="이 달 팀의 티켓이 어느 상태에 몰려 있는지 봅니다." segments={teamSegs} unit="건" centerLabel="티켓" emptyLabel="이 달에 집계된 티켓이 없습니다" />
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                    팀 합계는 티켓 단위로 셉니다. 담당자별 합계는 담당자가 둘인 티켓을 양쪽에 각각 세므로 이 합과 다를 수 있습니다.
                  </Typography>
                </Card>
              </Box>
            )}
          </Box>

          <Box component="section" sx={{ mb: 4 }}>
            <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>업무량 분석 (완료 업무량 기준)</Typography>
            {/* 🔴 여기 「담당자별 완료 업무량」 막대가 있었다. **바로 아래 표의 «완료 업무량»
                열이 같은 사람들의 같은 숫자**를 말한다 — 한 화면이 같은 것을 두 번 말하면
                읽는 사람은 둘이 다른 것이라고 읽는다(WorkSummary 가 「개수」와 「그 개수의
                목록」에서 이미 내린 판단과 같다). 게다가 막대는 완료 업무량이 0 인 사람을
                빼고 그리므로 **표와 명단이 달랐다** — 없는 차이를 만들던 자리다.
                비교가 필요하면 표의 그 열을 세로로 훑는 것이 정확하고, 표는 그 옆에 여덟
                열을 더 준다. */}
            <TableWrap minWidth="52rem">
              <DataTable columns={DEV_WORKLOAD_COLUMNS} rows={devs} rowKey={(d) => d.name} />
            </TableWrap>
          </Box>

          <Box sx={{ mb: 4 }}>
            <Note sx={{ mt: 0 }}>
              완료 건수와 완료 예상 WD는 그 사람이 이번 달에 실제로 마무리한 일의 양을 나타냅니다. 진행과 검증 건수가 많으면 지금 손에 쥔 일이 많다는 뜻이고, 지연 건수는 마감이 지났는데 아직 끝나지 않은 티켓입니다. 완료율은 담당한 일 가운데 끝낸 비율이며 취소는 제외합니다. 담당 건수가 적으면 완료율이 쉽게 높아지므로 담당 건수와 함께 보아야 공정합니다.
            </Note>
          </Box>

          <Box component="section" sx={{ mb: 4 }}>
            <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>담당자별 상세 티켓</Typography>
            {withTickets.length === 0 ? (
              <Card>
                <EmptyState art="tickets" title="이 달에 담당한 티켓이 있는 사람이 없습니다"
                  help="선택한 달에 마감일이 있는 티켓이 배정되면 여기에 담당자별로 묶여 표시됩니다." />
              </Card>
            ) : (
              /* 담당자별 상세 티켓은 담당자마다 구분 행을 둔 '하나의 표'로 그린다 — 표가 여러 개면
                 열 너비가 제각각이라 위치가 어긋난다. 한 표로 묶으면 모든 담당자의 열이 자동 정렬된다. */
              <TableWrap minWidth="56rem">
                <Table size="small">
                <TableHead>
                  <TableRow>
                    {DEV_TICKET_COLUMNS.map((c) => (
                      <TableCell key={c.key} scope="col" title={c.help || undefined} {...tableCellProps(c, { head: true })}>
                        {c.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {withTickets.flatMap((d) => [
                    <TableRow key={d.name + "::group"}>
                      <TableCell colSpan={DEV_TICKET_COLUMNS.length}
                        sx={{
                          bgcolor: (t) => t.palette.action.hover, fontWeight: FONT_WEIGHT.bold,
                          borderTop: 1, borderColor: "divider",
                        }}>
                        {d.name}
                        <Box component="span" sx={{ ml: 1.5, fontWeight: FONT_WEIGHT.regular, color: "text.secondary", fontSize: FONT_SIZE.bodySm }}>
                          완료 {d.done}건, 진행 중 {d.prog + d.verify}건, 완료 예상 WD {d.est_done}인일
                        </Box>
                      </TableCell>
                    </TableRow>,
                    /* 제목은 평문이다. 예전에는 옛 Notion 주소로 나가는 링크였는데, 정본이 이
                       서버로 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상 쓰지 않는 낡은
                       사본이다. 서버도 응답에서 `url` 을 걷었다. */
                    ...d.tickets.map((t) => (
                      <TableRow key={d.name + ":" + (t.tid || t.title) + ":" + t.status}>
                        {DEV_TICKET_COLUMNS.map((c) => (
                          <TableCell key={c.key} {...tableCellProps(c)}>
                            {c.render ? c.render(t) : (t[c.key] == null || t[c.key] === "" ? "-" : String(t[c.key]))}
                          </TableCell>
                        ))}
                      </TableRow>
                    )),
                  ])}
                </TableBody>
                </Table>
              </TableWrap>
            )}
          </Box>
        </>
      ) : null}
    </Box>
  );
}

