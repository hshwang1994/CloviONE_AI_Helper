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

// 이번 달을 'YYYY-MM'으로. 리포트는 마감일 기준이라 월만 쓴다.
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/* 고른 달은 **주소에** 둔다 (S15 · `lib/useQueryState.js`).
 *
 * 예전에는 이 값이 컴포넌트 지역 상태에만 있었다 — 3월로 바꾸면 표는 3월을 보여 주는데
 * 주소는 `#/dev-report` 그대로였고, 새로고침하면 다시 이번 달이 됐다. 「3월 리포트 좀
 * 봐 달라」고 링크를 건네는 일이 아예 안 됐다(audit-10).
 *
 * 기본값을 빈 문자열로 두는 이유: 「이번 달」은 **여는 날짜에 따라 달라지는 값**이라
 * 스펙에 못 박을 수 없다. 비어 있으면 오늘 기준 이번 달이고, 달을 고르면 그때부터
 * 주소에 실린다. 이 저장소의 조건 상태는 `replace` 다 — 고르는 동안 히스토리가 쌓이면
 * 뒤로가기 한 번으로 이 화면을 벗어날 수 없다. */
const DEV_REPORT_SPEC = { period: "" };

/** 'YYYY-MM' → 「2026년 3월」. 화면 설명이 지금 보고 있는 달을 그대로 말하게 한다. */
export function periodLabel(period) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(period || ""));
  return m ? `${m[1]}년 ${parseInt(m[2], 10)}월` : String(period || "");
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

/* 상태 세그먼트의 순서와 색 — 상태 스택 막대(담당자별)와 그 범례(`StatusLegend`)가 **같은 표를 공유한다**.
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

/* 상태 막대의 범례 — 구획 제목 줄 오른쪽 끝에 한 줄로 선다. 예전에는 표 옆 도넛의 범례가 이 막대의 범례를 겸했다.
 * 도넛을 걷으면서(D-501) 범례만 남긴다 — 점 모양은 제품의 다른 색 표지(배지 · 상태 칩)와 같은 7px 점이고, 옆 낱말이
 * 뜻을 나르므로 색을 못 봐도 막대 옆 칸의 수로 같은 것을 읽는다(WCAG 1.4.1). */
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

/* 표 자리 — 판은 표가 그린다(`DataTable placement="surface"`, 조합 계약 C-3). 이 상자는 판이 아니라 표의 바닥 폭과
 * 인쇄 규칙만 준다. 가로 스크롤은 표 자신의 상자 안에서만 일어난다(페이지 전체가 가로로 밀리면 4K QA의
 * horizontal_overflow에 걸린다). min-width는 rem이라 4K에서 함께 커진다. 예전에는 이 화면만 테두리·모서리를 손으로
 * 적은 자기 상자였고, 그다음에는 `ListCard` 안에 한 번 더 굴러가는 상자를 두었다.
 *
 * **이 상자는 표를 직접 그리지 않는다.** 예전에는 여기서 `<Table>` 을 열고 화면이
 * `<Th>`·`<TableCell>` 을 손으로 적었다 — 그래서 이 화면의 열 폭·정렬·자릿수 규칙이
 * `DataTable` 의 것과 **따로** 살았고, 공용 계약을 고쳐도 여기는 안 따라왔다(C3 이 이
 * 파일을 이름으로 지목한 이유다). 지금은 표 셋 전부가 `DataTable` 이다 — 담당자별 상세
 * 티켓이 마지막까지 맨 `<Table>` 로 남아 있었는데, 그것을 붙잡고 있던 담당자 구분 행을
 * 이제 표가 `groupOf` 로 직접 그린다. */
function TableWrap({ minWidth = "45rem", children }) {
  return (
    /* `minWidth: 0` — 격자 칸(1fr = minmax(auto, 1fr)) 안에서 판이 표의 고유 폭까지 늘어나 1366 에서
       페이지가 가로로 밀렸다(실측: 판 오른쪽 끝 1466px). 판이 줄어들 수 있어야 안쪽 상자가 굴린다. */
    <Box sx={{ minWidth: 0, "& table": { minWidth }, "@media print": { "& .MuiTableContainer-root": { overflow: "visible" } } }}>
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
    help: "담당한 티켓의 상태 비율을 색 막대로 나타냅니다. 색은 이 표 위 범례와 같습니다.",
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

/* 개발자 월간 리포트 — 마감일이 그 달인 티켓을 담당자별로 묶어 보여준다.
 * 팀 합계 카드로 요약을 먼저 주고, 표는 그 아래에 둔다. 담당자별 업무량은
 * 그림이 아니라 표가 말한다 — 그림과 표가 같은 숫자를 두 번 말하던 자리를 W6 이 정리했고,
 * 합계 카드와 같은 수를 다시 그리던 팀 도넛은 D-501 이 걷었다. 남은 그림은 담당자별 상태 막대(의존성 없는 SVG)다. */
export function DevReport() {
  const [view, setView] = useQueryState(DEV_REPORT_SPEC);
  // 주소에 아무것도 없으면 「이번 달」이다 — 그 값은 여는 날짜에 달렸으므로 스펙이 아니라
  // 여기서 정한다(위 DEV_REPORT_SPEC 주석).
  const period = view.period || thisMonth();
  const setPeriod = (next) => setView({ period: next });
  const query = useQuery({
    queryKey: ["dev-report", period],
    queryFn: () => api("/api/admin/reports/dev-monthly?period=" + encodeURIComponent(period)),
    retry: false,
  });
  const data = query.data;
  const ok = data && data.ok;
  const devs = ok ? data.developers : [];
  const withTickets = ok ? devs.filter((d) => d.has_tickets) : [];
  /* 담당자별 상세는 **한 표 안에서** 담당자로 묶인다 — 그래서 행을 평평하게 편 뒤 각 행이
     자기 담당자를 들고 다닌다. 묶음 머리행에 붙는 요약(`_devNote`)은 그 사람의 값이라 행이
     아니라 담당자에 속하지만, 표가 보는 것은 행 하나뿐이므로 여기서 함께 실어 준다. */
  const detailRows = withTickets.flatMap((d) => (d.tickets || []).map((t) => ({
    ...t,
    _dev: d.name,
    _devNote: `완료 ${d.done}건, 진행 중 ${d.prog + d.verify}건, 완료 예상 WD ${d.est_done}인일`,
  })));
  // 팀 상태 구성 — 백엔드가 티켓 단위(중복 없이)로 센 값이다. 팀 합계 카드의 전체는 완료 · 진행 중 · 검증 · 계획의
  // 합이라 취소와 다섯 상태 밖의 티켓(작업 DB에 새 상태가 생기는 경우)은 거기 안 든다. 그 둘은 조용히 사라지지 않게
  // 카드의 정의 목록이 수로 말한다 — 예전에는 표 옆 도넛이 그 조각을 그렸다(D-501 로 걷었다).
  const team = ok ? data.team : null;
  const teamCancel = team ? (team.cancel || 0) : 0;
  const teamRest = team
    ? team.total - ((team.done || 0) + (team.in_progress || 0) + (team.verify || 0) + (team.plan || 0) + teamCancel)
    : 0;

  return (
    <Box className="c-screen"
      sx={{
        /* 자릿수 고정을 예전에는 **화면 전체**에 걸었다 — 산문과 라벨까지 고정폭 숫자를 쓰면
           «2026년 8월» 의 숫자 사이가 벌어진다. 이제 열이 자기 타입으로 말하고 그 열만
           고정한다(`columnTypes.js`). 표 밖의 팀 합계는 상태 요약 카드(`StatusSummaryCard`)가 자기 것을 건다. */
        // 인쇄: 카드 그림자는 회색 얼룩으로만 나오고, 섹션이 페이지 중간에서 잘리면 표 머리가 사라진다.
        "@media print": { "& .MuiPaper-root": { boxShadow: "none" }, "& section": { breakInside: "avoid" } },
      }}>
      {/* 사이드바가 이 화면을 「감사」 묶음에 두는데(navConfig.js) 빵부스러기는 「자동화」
          라고 말하고 있었다 — 그 이름의 묶음은 이제 「자동화와 연동」이고 이 화면은 거기
          없다. 같은 화면이 두 자리에 있다고 읽히던 자리다(S20). */}
      {/* 긴 설명은 제목 옆 `?` 다(D-453) — 예전에는 머리 아래 상시 문단이었다.
          🔴 「새로고침」은 채움이 아니다(D-501). 읽기 전용 보고서라 이 화면이 하라고 있는 일이 없다 — 다시 읽는 것은
          주 동작이 아니라 보조다. 예전에는 「브랜드 면을 남기려고」 이 단추를 채움으로 두었는데, 채움은 그 화면의 일을
          가리키는 표지라 할 일이 없는 화면에 세우면 그 표지가 거짓말을 한다. */}
      <PageHeader area="감사" title="개발자 월간 리포트"
        description={"마감일이 " + periodLabel(period) + "인 티켓을 담당자별로 모아 업무량과 위험을 봅니다."}
        help="마감일이 선택한 달인 티켓을 담당자별로 집계합니다. 각자 얼마나 일했는지는 완료 건수와 예상 WD로 보고, 지금 안고 있는 부담과 위험은 진행 중 업무와 지연으로 함께 봅니다. 예상 WD와 난이도는 티켓 내용을 바탕으로 추정한 값이고, 실제 WD는 완료한 담당자가 입력합니다."
        actions={<Button onClick={() => query.refetch()} disabled={query.isFetching} loading={query.isFetching}>새로고침</Button>} />

      {/* 🔴 이 줄은 테두리 있는 판이었고, 그 판이 1606×68 에 잉크 18% 로 서 있었다(P-42 ②). 작은 컨트롤 셋을
          화면 폭짜리 상자에 담으면 그 상자는 자기 폭을 설명하지 못한다. 조건 줄은 필터 바 한 벌이다 — 연도 · 월이
          칸이고, 되돌리는 일이 아니라 **동작**인 인쇄는 그 줄 오른쪽 끝 묶음이다(조합 계약 C-1). */}
      <FilterBar
        sx={{ "@media print": { display: "none" } }}
        end={<Button onClick={() => window.print()}>인쇄하거나 PDF로 저장</Button>}
      >
        {/* 연도 · 월은 필터 바의 칸이다 — 이름이 칸 안에 서는 34 칸이고(핸드오프 README §3), 「전체」가
            답이 아닌 축이라 빈 항목이 없다. 기간은 늘 걸려 있는 문맥이라 지울 조건 칩이 없다. */}
        <FilterSelect
          label="연도" value={period.slice(0, 4)} noAllOption
          onChange={(v) => setPeriod(v + "-" + period.slice(5, 7))}
          options={yearOptions(5).map((y) => ({ value: String(y), label: y + "년" }))}
        />
        <FilterSelect
          label="월" value={period.slice(5, 7)} noAllOption
          onChange={(v) => setPeriod(period.slice(0, 4) + "-" + v)}
          options={MONTH_VALUES.map((m) => ({ value: m, label: parseInt(m, 10) + "월" }))}
        />
      </FilterBar>

      {query.isLoading ? (
        <Card><Skeleton kind="chart" /></Card>
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
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
        <ErrorState layout="region" error={{ message: data.error || "리포트를 불러오지 못했습니다." }} onRetry={() => query.refetch()} />
      ) : ok ? (
        <>
          {/* 각 칸의 셋째 줄은 '이 숫자가 무엇을 센 것인지'다 — 정의가 사라지면 숫자를
              신뢰할 수 없다. 판독 줄이 값·라벨·각주 셋을 모두 모델링하므로 예전처럼 라벨
              자리에 두 줄을 밀어 넣지 않는다(KpiLabel 을 없앤 이유). */}
          {/* 팀 합계는 **구성**이다 — 완료 · 진행 중 · 검증 · 계획의 합이 전체이고, 지연 · 담당자 없음은 그 위의
              신호다. 상태 요약 카드 하나로 선다(계획 표 7 · 핸드오프 RULES §10). 칸마다 셋째 줄이던 정의는
              카드 아래 정의 목록으로 이어진다 — 정의가 사라지면 숫자를 믿을 수 없다. */}
          <StatusSummaryCard
            ariaLabel="팀 합계"
            sx={{ mb: 4 }}
            unit="건"
            total={data.team.done + data.team.in_progress + data.team.verify + data.team.plan}
            items={[
              { key: "done", kind: "ok", value: data.team.done, label: "완료" },
              { key: "in_progress", kind: "info", value: data.team.in_progress, label: "진행 중" },
              { key: "verify", kind: "warn", value: data.team.verify, label: "검증" },
              { key: "plan", kind: "neutral", value: data.team.plan, label: "계획" },
            ]}
            risks={[
              { key: "overdue", kind: "danger", value: data.team.overdue, label: "지연" },
              { key: "unassigned", kind: "warn", value: data.unassigned.total, label: "담당자 없음" },
            ]}
            notes={[
              { key: "done", label: "완료", text: "취소를 뺀 기준 완료 " + data.team.est_done_total + "인일" },
              { key: "in_progress", label: "진행 중", text: "진행과 이슈 상태" },
              { key: "verify", label: "검증", text: "검토, 확인 단계" },
              { key: "plan", label: "계획", text: "아직 착수 전" },
              { key: "overdue", label: "지연", text: "마감이 지난 미완료" },
              { key: "unassigned", label: "담당자 없음", text: "담당자가 지정되지 않음" },
              /* 합계에 안 드는 티켓 — 예전에는 표 옆 도넛만 이 조각을 그렸다(위 `teamCancel` 주석). */
              teamCancel > 0 ? { key: "cancel", label: "취소", text: teamCancel + "건은 합계에서 뺐습니다." } : null,
              teamRest > 0 ? { key: "rest", label: "기타", text: "다섯 상태 밖의 " + teamRest + "건은 합계에서 뺐습니다." } : null,
              /* 세는 단위 — 도넛 판의 각주였다. 합계 카드와 아래 담당자별 표의 수가 왜 다를 수 있는지를 그 수 옆에서 말한다. */
              { key: "unit", label: "세는 법", text: "팀 합계는 티켓 단위로 셉니다. 담당자별 합계는 담당자가 둘인 티켓을 양쪽에 각각 세므로 이 합과 다를 수 있습니다." },
            ]}
          />

          {/* 구획은 공용 `Section`(제목 + 괘선)이다 — 예전에는 h2 셋을 손으로 그렸다.
              🔴 여기 표 옆(좁은 화면에서는 아래)에 「팀 상태 구성」 도넛 판이 있었다. 도넛의 네 조각은 바로 위 팀 합계 카드가
              이미 말하는 수였고, 1920 에서는 표 아래 480px 판으로 서서 오른쪽 1,100px 가 비었다(D-501 — 한 사실은 한 곳).
              판을 걷고 그 판이 하던 두 일만 남긴다: 각주는 합계 카드의 정의 목록으로, 막대의 색 범례는 이 구획 제목 줄로. */}
          <Section titleAs="h2" title={`개발자별 상세 (${data.period})`} rule
            action={devs.length ? <StatusLegend /> : null}>
            {devs.length === 0 ? (
              <EmptyState art="tickets" title="이 달에 집계할 담당자가 없습니다"
                help="선택한 달에 마감일이 있는 티켓이 없거나, 앱에 활성 사용자가 추가되어 있지 않습니다."
                situation="기간을 바꾸거나, 사용자 화면에서 담당자 계정이 활성 상태인지 확인하세요." />
            ) : (
              <TableWrap minWidth="52rem">
                {/* 집계 표라 「받았다」는 건수를 말하지 않는다(`list={false}`) — 행은 받은 목록이 아니라 사람별 합이다. */}
                <DataTable placement="surface" list={false} columns={DEV_SUMMARY_COLUMNS} rows={devs} rowKey={(d) => d.name} />
              </TableWrap>
            )}
          </Section>

          {/* 열의 뜻을 푸는 문단은 제목 아래 도움말이다 — 예전에는 표 아래 떠 있는 문단이라 어느
              표를 설명하는지 다시 찾아야 했다. */}
          <Section titleAs="h2" title="업무량 분석 (완료 업무량 기준)" rule
            help={(
              /* 네 문장짜리 산문이라 `PROSE_MAX_WIDTH` 를 건다 — 1920 에서 한 줄이 1,600px 를 달리면 읽히지 않는다. */
              <Box component="span" sx={{ display: "block", maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK }}>
                완료 건수와 완료 예상 WD는 그 사람이 이번 달에 실제로 마무리한 일의 양을 나타냅니다. 진행과 검증 건수가 많으면 지금 손에 쥔 일이 많다는 뜻이고, 지연 건수는 마감이 지났는데 아직 끝나지 않은 티켓입니다. 완료율은 담당한 일 가운데 끝낸 비율이며 취소는 제외합니다. 담당 건수가 적으면 완료율이 쉽게 높아지므로 담당 건수와 함께 보아야 공정합니다.
              </Box>
            )}>
            {/* 🔴 여기 「담당자별 완료 업무량」 막대가 있었다. **바로 아래 표의 «완료 업무량»
                열이 같은 사람들의 같은 숫자**를 말한다 — 한 화면이 같은 것을 두 번 말하면
                읽는 사람은 둘이 다른 것이라고 읽는다(WorkSummary 가 「개수」와 「그 개수의
                목록」에서 이미 내린 판단과 같다). 게다가 막대는 완료 업무량이 0 인 사람을
                빼고 그리므로 **표와 명단이 달랐다** — 없는 차이를 만들던 자리다.
                비교가 필요하면 표의 그 열을 세로로 훑는 것이 정확하고, 표는 그 옆에 여덟
                열을 더 준다. */}
            <TableWrap minWidth="52rem">
              <DataTable placement="surface" list={false} columns={DEV_WORKLOAD_COLUMNS} rows={devs} rowKey={(d) => d.name} />
            </TableWrap>
          </Section>

          <Section titleAs="h2" title="담당자별 상세 티켓" rule>
            {withTickets.length === 0 ? (
              <EmptyState art="tickets" title="이 달에 담당한 티켓이 있는 사람이 없습니다"
                help="선택한 달에 마감일이 있는 티켓이 배정되면 여기에 담당자별로 묶여 표시됩니다." />
            ) : (
              /* 담당자별 상세 티켓은 담당자마다 구분 행을 둔 '하나의 표'로 그린다 — 표가 여러 개면
                 열 너비가 제각각이라 위치가 어긋난다. 한 표로 묶으면 모든 담당자의 열이 자동 정렬된다.
                 그 구분 행 하나 때문에 이 표만 `DataTable` 을 못 쓰고 자기 `<Table>` 을 그렸다.
                 지금은 표가 묶음 머리행을 갖는다(`groupOf`) — 위 두 표와 **같은 부품**이다.
                 제목은 평문이다: 예전에는 옛 Notion 주소로 나가는 링크였는데, 정본이 이 서버로
                 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상 쓰지 않는 낡은 사본이다. */
              <TableWrap minWidth="56rem">
                <DataTable
                  placement="surface"
                  columns={DEV_TICKET_COLUMNS}
                  rows={detailRows}
                  rowKey={(t) => t._dev + ":" + (t.tid || t.title) + ":" + t.status}
                  groupOf={(t) => ({ key: t._dev, label: t._dev, note: t._devNote })}
                />
              </TableWrap>
            )}
          </Section>
        </>
      ) : null}
    </Box>
  );
}

