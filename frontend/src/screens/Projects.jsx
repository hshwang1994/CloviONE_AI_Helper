import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import {
  ListEmptyState,
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, FormModal,
  ListCard, MetricStrip, PageHeader, Skeleton, useToast,
} from "../ui/kit.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { DepartmentFilter } from "../ui/filters.jsx";
import { FilterActions, FilterRow, FilterSurface, ResultLine, ToolbarRow } from "../ui/FilterBar.jsx";
import { SearchBox } from "../ui/filters.jsx";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { Gauge } from "../ui/charts/Gauge.jsx";
import { ProgressBar } from "../ui/charts/ProgressBar.jsx";
import { useCreateProject, useDeptNames, useProjectDashboard, useProjectList } from "./project-queries.js";
import {
  NO_HEALTH_CACHE, NO_PROGRESS_CACHE, PROJECT_FORM_FIELDS, PROJECT_STATUS_KO,
  PROJECT_WRITE_ROLES, deptLabel, percentText, periodText,
} from "./project-format.js";
import { DateCell } from "../ui/cells.jsx";
import { toggleSort } from "../ui/TableHeaderCell.jsx";
import { useListMemory } from "../lib/listReturn.js";

/* 프로젝트 목록 — **요약 + 표**.
 *
 * ## 왜 카드 격자가 아니라 표인가 (사용자 지시)
 *
 * 카드 격자는 한 화면에 6~8건이 들어가고, 같은 항목(기간, 진행률, Health)이 카드마다 다른
 * 세로 위치에 놓여 **행끼리 비교가 안 된다.** 사용자가 지적한 것이 정확히 그것이다:
 * "저렇게 카드로 보여 주면 어떻게 보라는 것이냐". 표는 열이 고정이라 눈이 세로로 훑는다.
 *
 * ## 정렬은 서버가 한다
 *
 * `app/projects/router.py::list_projects` 가 `sort`/`order` 를 받는다. 화면 기본은
 * 이름 오름차순이고, 같은 이름이면 id 로 순서를 고정한다. 헤더를 누르면 그 질의만
 * 바뀐다. 지금 페이지 20건만 화면에서 바꾸지 않는다.
 *
 * ## 요약을 화면에서 세지 않는 이유
 *
 * 같은 함정의 다른 얼굴이다. 목록은 20건씩 잘려 오므로 `items` 를 세면 "총 22건인데 요약은
 * 20건 기준" 이 된다. 집계는 서버가 별도 경로(`/api/projects/dashboard`)에서 자르지 않은
 * 표본으로 한다.
 *
 * ## 조건은 주소에 둔다
 *
 * 티켓 화면과 같은 결론이다(`lib/useQueryState.js`): 필터를 `useState` 에만 두면 상세를 보고
 * 돌아왔을 때 풀리고, 새로고침과 링크 공유도 안 된다.
 */

// `dept` 는 부서 필터 (0060 §32). 주소에 두는 이유는 나머지 조건과 같다 — 상세를 보고
// 돌아왔을 때 풀리면 안 되고, 링크로 "A-1 팀 프로젝트" 를 공유할 수 있어야 한다.
/* `status` · `trouble` · `overdue` 는 **요약 줄을 누르면 켜지는 조건**이다 (지시 15).
 * 주소에 실리므로 뒤로 갔다 와도, 링크로 건네도 같은 목록이 선다. */
/* 쪽 번호는 여기 없다 — 목록은 쪽을 넘기지 않고 묶음을 이어 받는다. 정렬은 조건이라 남는다. */
const PROJECT_SPEC = {
  q: "", archived: false, dept: "", status: "", trouble: false, overdue: false,
  sort: "name", order: "asc",
};


/** 화면 상태 → 서버 질의. 기본값은 안 싣는다(주소도 질의도 깨끗해야 조건이 눈에 보인다). */
export function projectListQuery(filters) {
  const p = new URLSearchParams();
  if (filters.archived) p.set("include_archived", "true");
  // 검색은 티켓·게시판과 **같은 이름의 조건**이다(`q`). 화면마다 다른 키를 쓰면 공용
  // 탐색 줄이 화면별 번역표를 갖게 된다.
  if (filters.q) p.set("q", filters.q);
  if (filters.status) p.set("status", filters.status);
  if (filters.trouble) p.set("trouble", "true");
  // 주소 키(`overdue`)와 API 키(`overdue_milestones`)가 다르다 — 옮겨 적는 자리는 여기 하나다.
  if (filters.overdue) p.set("overdue_milestones", "true");
  // 주소 키(`dept`)와 API 키(`department_id`)가 다르다 — 옮겨 적는 자리는 여기 하나다.
  if (filters.dept) p.set("department_id", filters.dept);
  if (filters.sort && (filters.sort !== "name" || filters.order !== "asc")) {
    p.set("sort", filters.sort);
    p.set("order", filters.order || "asc");
  }
  /* 쪽 파라미터는 여기서 안 붙인다 — 그것은 「무엇을 거를까」가 아니라 「얼마씩 받을까」이고,
     목록 훅이 묶음마다 스스로 붙인다(`project-queries.js::useProjectList`). */
  return p;
}

/* 구성 칸 넷. 서버가 세는 상태 어휘와 **같은 키**다(`app/projects/models.py::PROJECT_STATUSES`) —
 * 그 키가 곧 목록을 좁히는 조건이라, 화면이 이름을 새로 지으면 눌러도 아무것도 안 걸러진다. */
const STATUS_TILES = [
  ["active", "진행"],
  ["done", "완료"],
  ["on_hold", "보류"],
  ["planned", "계획"],
];

/* 요약의 한 칸. **판이 아니다** — 캔버스 위에 서고 실선이 이웃과 가른다(`MetricStrip` 과
 * 같은 위계). 누를 수 있으면 버튼이 되고, 켜져 있으면 앞머리 레일이 그 사실을 말한다
 * (D-289: 이 제품은 선택을 면이 아니라 잉크와 레일로 말한다). */
/** 선택을 말하는 앞머리 레일의 색. 켜져 있으면 강조색, 아니면 구분선이다(D-289). */
function railColor(theme, active) {
  return active ? theme.palette.primary.main : theme.palette.divider;
}

function SummaryPanel({ label, active, onClick, actionLabel, children }) {
  const clickable = !!onClick;
  return (
    <Box
      component={clickable ? "button" : "div"}
      type={clickable ? "button" : undefined}
      onClick={onClick}
      aria-pressed={clickable ? !!active : undefined}
      aria-label={clickable ? actionLabel || label : undefined}
      data-brand-role={clickable && active ? "selected-state" : undefined}
      /* 시험이 「이 값과 이 각주가 **같은 칸**에 있다」를 짚는 자리. 자식 순서로 짚으면
         안쪽 배치를 조금만 바꿔도 시험이 조용히 빈 문자열끼리 비교하며 통과한다. */
      data-summary-panel={label}
      sx={(t) => ({
        textAlign: "left", font: "inherit", color: "inherit", bgcolor: "transparent",
        border: 0, borderRadius: 0, px: 2, py: 1.5, minWidth: 0,
        display: "grid", gap: 0.75, alignContent: "start",
        cursor: clickable ? "pointer" : "default",
        borderInlineStartStyle: "solid",
        borderInlineStartWidth: "2px",
        /* 논리 테두리는 MUI 가 안 펴 준다 — style·width·color 셋을 따로, 색은 **해석된
           값**으로 적는다(F-W2R-01). 삼항을 여기 직접 쓰면 값이 식별자로 시작하지 않아
           `check_logical_border_props.py` 가 「선언만 있고 안 그려진다」로 읽는다. */
        borderInlineStartColor: railColor(t, active),
        "&:hover": clickable ? { bgcolor: t.palette.background.inset } : undefined,
        "&:focus-visible": { outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 },
      })}
    >
      <Typography variant="body2" color="text.secondary" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
        {label}
      </Typography>
      {children}
    </Box>
  );
}

/* 가장 오래 지난 마일스톤 셋. 「3건」만 말하면 그것을 본 사람이 할 수 있는 일이 없다 —
 * 어느 것이 얼마나 지났는지가 곧 할 일 목록이다.
 *
 * 기준일은 **서버가 준 것**을 쓴다(`d.today`). 브라우저에서 오늘을 구하면 KST 09:00
 * 이전에 하루 밀린 「지연 일수」를 그린다(§불변 9). */
function OverdueBars({ items, today }) {
  const rows = (Array.isArray(items) ? items : [])
    .map((m) => ({ ...m, late: daysBetween(m.due_on, today) }))
    .filter((m) => typeof m.late === "number")
    .sort((a, b) => b.late - a.late)
    .slice(0, 3);
  if (!rows.length) return null;
  const worst = rows[0].late || 1;
  return (
    <BarSeries
      /* 그림마다 «이 그림이 답하는 업무 질문» 을 적는다(W6). 이 자리는 「6건」이라는 수
         옆에 서는 그림이라, 그 수를 본 사람이 다음에 할 일이 무엇인지를 말해야 한다. */
      question="가장 오래 밀린 마일스톤이 무엇인지 봅니다."
      items={rows.map((m) => ({
        // 가운뎃점을 안 쓴다(`scripts/check_user_text.py`) — 화면 문구의 구분자는 여백이다.
        label: m.project_name ? `${m.project_name} ${m.name}` : m.name,
        value: m.late,
        note: `${m.late}일 지남`,
        color: "warning",
      }))}
      max={worst}
      unit="일"
    />
  );
}

/** 'YYYY-MM-DD' 두 개의 날짜 차이(일). 못 읽으면 `null` — 지어내지 않는다. */
function daysBetween(from, to) {
  const a = Date.parse(String(from || "") + "T00:00:00Z");
  const b = Date.parse(String(to || "") + "T00:00:00Z");
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return Math.round((b - a) / 86400000);
}

/* 요약 줄. **숫자는 응답을 그대로 쓴다** - 여기서 더하거나 빼면 서버가 센 것과 갈라진다.
 *
 * 못 잰 것을 함께 말하는 것이 이 줄의 계약이다. "Health 하위 0건" 이 '다 건강하다' 인지
 * '아무것도 안 쟀다' 인지는 완전히 다른 사실이고, 안 말하면 화면이 조용히 후자를 전자처럼
 * 보이게 한다(app/projects/service.py::project_dashboard). */
function Summary({ query, filters, onFilter }) {
  if (query.isPending) return <Card><Skeleton lines={3} /></Card>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const d = query.data || {};
  // PA-RC-0018 direction 4(0 지표 규칙): 프로젝트가 0건이면 여덟 타일 전부가 0/-다 —
  // 빈 상태 위에 값 없는 카드 벽을 먼저 그리는 대신, 아래 EmptyState 하나로만 말한다.
  // 이 total은 서버 집계(project_dashboard)라 목록 화면의 보관 필터와 무관하게 항상
  // 전체 기준이다(위 주석 "요약을 화면에서 세지 않는 이유" 참고) — 필터로 화면에 0건이
  // 보여도 조직에 프로젝트가 있으면 이 요약은 그대로 뜬다.
  if (!d.total) return null;
  const status = d.by_status || {};
  const progress = d.progress || {};
  const health = d.health || {};
  const trouble = health.trouble || {};
  const overdue = (d.milestones || {}).overdue || {};
  const avg = percentText(progress.average_pct);
  // 재 본 프로젝트 수. 안 잰 것을 분모에 넣으면 아무것도 안 잰 조직이 가장 건강해 보인다.
  const scored = Math.max(0, (d.total || 0) - (health.unscored || 0));

  /* 지표를 성격으로 **두 묶음**으로 나눈다 (지시 2).
   *
   * 예전에는 타일 여덟 장이 한 격자에 깔렸고, 프로젝트가 적으면 그중 다섯이 `0`/`-` 라
   * 화면 절반을 "값이 없다"는 사실이 차지했다. 여덟 개가 같은 무게로 보이니 무엇이 핵심인지도
   * 알 수 없었다.
   *
   *   1) 구성 — 전체가 지배 판독값이고 상태별 넷이 그 옆에 붙는다. 합이 전체가 되는 관계다.
   *   2) 진행과 위험 — 성격이 다르다. 조치가 필요한지 보는 줄이라 따로 둔다.
   */
  return (
    <Box sx={{ mb: 2.5, display: "grid", gap: 1.5 }}>
      {/* 구성 칸은 **누르면 목록이 그 상태로 좁아진다** (지시 15). 같은 칸을 다시 누르면
          조건이 풀린다 — 조건을 켜는 자리와 끄는 자리가 다르면 사용자는 끄는 법을 못 찾는다. */}
      <MetricStrip
        ariaLabel="프로젝트 구성"
        items={[
          { key: "total", value: d.total, label: "전체", primary: true,
            active: !filters.status && !filters.trouble && !filters.overdue,
            onClick: () => onFilter({ status: "", trouble: false, overdue: false }) },
          ...STATUS_TILES.map(([key, label]) => ({
            key, value: status[key], label,
            active: filters.status === key,
            onClick: () => onFilter({ status: filters.status === key ? "" : key, trouble: false, overdue: false }),
          })),
        ]}
      />
      {/* 진행과 위험 — **숫자만 나열하지 않는다** (지시 15).
          평균 진행률은 막대가, Health 는 원이 그 값을 그린다. 셋 다 성격이 달라서 한
          판독 줄에 밀어 넣으면 무엇이 조치를 요구하는 값인지 안 보인다. */}
      <Box
        sx={{
          display: "grid", gap: 1.5,
          gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
          alignItems: "stretch",
        }}
      >
        <SummaryPanel label="평균 진행률">
          <Typography sx={{ fontSize: FONT_SIZE.readout, fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.15 }}>
            {avg || "-"}
          </Typography>
          <ProgressBar
            percent={typeof progress.average_pct === "number" ? progress.average_pct : null}
            revealKey={progress.average_pct}
          />
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            {"계산이 끝난 " + (progress.counted || 0) + "건만 셌습니다"
              + (progress.not_counted ? ", " + progress.not_counted + "건은 아직 계산하지 않았습니다" : "") + "."}
          </Typography>
        </SummaryPanel>

        <SummaryPanel
          label="Health 하위"
          active={filters.trouble}
          onClick={() => onFilter({ trouble: !filters.trouble, status: "", overdue: false })}
          actionLabel="Health 하위 프로젝트만 보기"
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, minWidth: 0 }}>
            {/* 재 본 것 중 몇이 차질인가. **안 잰 것은 분모가 아니다** — 넣으면 아무것도
                안 잰 조직이 가장 건강해 보인다. */}
            <Gauge
              value={scored ? trouble.count : null}
              max={scored || 1}
              size="4.5rem"
              thickness={6}
              centerText={String(trouble.count || 0)}
              color={trouble.count > 0 ? "error" : "success"}
              emptyLabel="아직 안 쟀습니다"
              revealKey={trouble.count}
            />
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>
              {"Health 는 " + (health.unscored || 0) + "건을 아직 재지 않았습니다."}
            </Typography>
          </Box>
        </SummaryPanel>

        <SummaryPanel
          label="지연 마일스톤"
          active={filters.overdue}
          onClick={() => onFilter({ overdue: !filters.overdue, status: "", trouble: false })}
          actionLabel="지연 마일스톤이 있는 프로젝트만 보기"
        >
          <Typography sx={{ fontSize: FONT_SIZE.readout, fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.15 }}>
            {overdue.count || 0}
          </Typography>
          {/* 가장 오래 지난 것 셋. 「3건」만 말하면 그것을 본 사람이 할 수 있는 일이 없다 —
              어느 것이 얼마나 지났는지가 곧 할 일 목록이다.
              REAUDIT C7/RC6 — 0건이면 그림이 사라지고 큰 숫자 0만 남아 이웃 두 칸(둘 다
              숫자 아래에 사연을 까는 줄이 있다)보다 가벼워 보였다. 0도 「쟀고 없었다」는
              답이라 같은 자리에 문장을 채운다. */}
          {overdue.count ? (
            <OverdueBars items={overdue.items} today={d.today} />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              지연된 마일스톤이 없습니다.
            </Typography>
          )}
        </SummaryPanel>
      </Box>
    </Box>
  );
}

/* 표의 열. 사용자가 요구한 여섯 가지다(이름·상태·부서·기간·진행률·Health).
 *
 * `deptNames` 를 인자로 받는 이유: 부서 이름은 관리자군만 받아 올 수 있다
 * (project-queries.js::useDeptNames). 이름을 모르는 사람에게 UUID 를 그리면 그건 정보가
 * 아니라 소음이라 아예 안 그린다(§불변 6, project-format.js::deptLabel). */
function columns(deptNames) {
  return [
    {
      key: "name", label: "이름", type: "title", minWidth: "12rem", sortable: true,
      // 표의 어느 열이 '이 행이 무엇인가' 를 말하는지 알려 준다(kit.jsx::rowOpenLabel).
      rowName: (p) => p.name,
      render: (p) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
            {p.name || "이름 없음"}
          </Typography>
          {p.code ? (
            <Typography variant="caption" color="text.secondary">{p.code}</Typography>
          ) : null}
        </Box>
      ),
    },
    {
      key: "status", label: "상태", minWidth: "8rem",
      render: (p) => (
        <Stack direction="row" gap={0.5} sx={{ flexWrap: "wrap", alignItems: "center" }}>
          <Badge value={PROJECT_STATUS_KO[p.status] || p.status} />
          {p.archived_at ? <Badge value="보관됨" /> : null}
          {/* 여기 「이관 때 원본 없음」 배지가 있었다. 얼어붙은 이관 흔적 컬럼을 읽던
              것이라 사용자가 무엇을 고쳐도 안 사라졌다. 서버도 그 필드를 걷었다(S14). */}
        </Stack>
      ),
    },
    {
      key: "dept_id", label: "부서", minWidth: "7rem",
      render: (p) => deptLabel(p, deptNames) || "-",
    },
    {
      /* 기간은 **날짜**다. 타입을 안 주면 auto 배치가 남는 폭을 이 열의 max-content 비율만큼
         가져가는데, 그 문자열이 「2026-08-01 ~ 2026-12-31」이라 길다 — 실측에서 358px 를 42%만
         채운 채 「이름」이 100% 접혔다. 날짜는 자기 내용 폭만 쓰고 여유는 접히는 열이 갖는다. */
      key: "period", label: "기간", type: "date", minWidth: "11rem",
      render: (p) => periodText(p.starts_on, p.ends_on),
    },
    {
      key: "progress_pct", label: "진행률", type: "percent", minWidth: "6rem",
      // null 은 0% 가 아니다. 0 으로 그리면 "작업이 아직 안 붙은 프로젝트" 와 "붙었는데
      // 하나도 못 끝낸 프로젝트" 가 화면에서 똑같아진다(project-format.js 의 계약).
      render: (p) => percentText(p.progress_pct) || (
        <Typography component="span" variant="body2" color="text.secondary">
          {NO_PROGRESS_CACHE}
        </Typography>
      ),
    },
    {
      key: "health_score", label: "Health", type: "score", minWidth: "7rem",
      render: (p) => (p.health_score == null ? (
        <Typography component="span" variant="body2" color="text.secondary">
          {NO_HEALTH_CACHE}
        </Typography>
      ) : p.health_score + "점"),
    },
    {
      key: "created_at", label: "생성 일자", type: "date", minWidth: "8rem", sortable: true,
      render: (p) => <DateCell value={p.created_at} />,
    },
  ];
}

export function Projects() {
  const nav = useNavigate();
  useListMemory("/projects");
  const toast = useToast();
  const auth = useAuth();
  const [filters, setFilters] = useQueryState(PROJECT_SPEC);
  const [creating, setCreating] = React.useState(false);
  /* «조건 때문에 0건» 판정 (C1 · W5). `archived` 도 조건이다 — 보관 스위치를 켠 채 0건인
     화면에 「프로젝트가 없습니다」라고 말하면 그 스위치가 원인이라는 사실이 사라진다.
     기본값은 주소에 안 실리므로(`useQueryState`) 여기서 **기본값과 다른가**로 센다. */
  const hasProjectFilter = React.useMemo(
    () => Object.keys(PROJECT_SPEC).some(
      (k) => k !== "sort" && k !== "order" && filters[k] !== PROJECT_SPEC[k] && filters[k] !== "" && filters[k] != null
    ),
    [filters]
  );
  const clearProjectFilters = React.useCallback(
    () => setFilters({ archived: false, dept: "", sort: "name", order: "asc" }),
    [setFilters]
  );
  /* 결과 줄이 세는 것은 «지금 걸린 조건» 이다 — 기본값과 다른 축만 센다. */
  const activeProjectConditions = React.useMemo(
    () => Object.keys(PROJECT_SPEC).filter(
      (k) => k !== "sort" && k !== "order" && filters[k] !== PROJECT_SPEC[k] && filters[k] !== "" && filters[k] != null
    ),
    [filters]
  );
  /* 검색어 확정은 `SearchBox` 가 디바운스해서 부른다. **참조가 고정**돼야 한다 —
     매 렌더마다 새로 만들면 React.memo 가 깨져 글자마다 목록이 다시 그려진다. */
  const commitSearch = React.useCallback((next) => setFilters({ q: next }), [setFilters]);
  const qs = projectListQuery(filters).toString();
  const q = useProjectList(qs);
  const dashboard = useProjectDashboard(filters.dept);
  const deptNames = useDeptNames();
  const create = useCreateProject();

  const role = (auth.data && auth.data.role) || "";
  const canWrite = PROJECT_WRITE_ROLES.includes(role);

  const open = React.useCallback(
    (p) => nav("/projects/" + p.id, { state: { from: "/projects" } }),
    [nav],
  );

  /* 목록 밖의 값(부서 후보)은 첫 묶음 원본이 들고 온다 — 조건이 같으면 묶음마다 같다. */
  const data = q.first || {};
  const items = q.rows;
  /* 부서 이름은 **목록 응답이 함께 준다** (0060 §32).
   *
   * `useDeptNames` 는 `/api/admin/departments` 를 읽으므로 관리자에게만 값이 있다. 그런데
   * 이 열은 "이 프로젝트가 누구 것인가" 라 일반 사용자에게 더 필요하다 — 예전에는 그 사람
   * 화면에서만 전부 '-' 로 비어, 소속을 보여 주기로 한 결정이 정작 대상에게 안 보였다.
   *
   * 응답의 후보 목록은 **그 사람의 조회 범위 안**이라 이름이 새지 않는다. 관리자 쪽 맵을
   * 뒤에 겹쳐 두는 이유는 범위 밖 부서(전역 관리자가 보는 남의 조직)도 이름이 나와야 하기
   * 때문이다. */
  const deptNamesFromList = React.useMemo(() => {
    const out = {};
    for (const o of (data.departments && data.departments.options) || []) out[o.id] = o.name;
    return out;
  }, [data.departments]);
  const names = React.useMemo(
    () => ({ ...deptNamesFromList, ...deptNames }),
    [deptNamesFromList, deptNames],
  );
  const cols = React.useMemo(() => columns(names), [names]);

  async function submitCreate(body) {
    const created = await create.mutateAsync(body);
    setCreating(false);
    toast("프로젝트를 만들었습니다.", "success");
    // 방금 만든 것을 바로 열어 준다. 목록으로 돌려보내면 사용자가 22건 중에서 자기가 방금
    // 만든 것을 다시 찾아야 한다.
    const made = created && created.project;
    if (made && made.id) nav("/projects/" + made.id, { state: { from: "/projects" } });
  }

  return (
    <div className="c-screen">
      <PageHeader
        crumbRoot="팀 공간" area="프로젝트" title="프로젝트"
        actions={canWrite ? (
          <Button variant="primary" onClick={() => setCreating(true)}>새 프로젝트</Button>
        ) : null}
        description="내가 볼 수 있는 프로젝트가 지금 어디까지 왔는지 봅니다."
      />

      <Summary
        query={dashboard}
        filters={filters}
        onFilter={(patch) => setFilters(patch)}
      />

      {/* 탐색 줄은 **판이 아니다** (지시 80 · W5). 이 화면만 `c-toolbar-card` 를 달고 남아
          있었다 — 독립 검수 실측: 1920 에서 잉크 폭 비 0.355, 3840 에서 0.234 로, W5 가
          「없앴다」고 적은 `/policies` 판(0.43)보다 오히려 나빴다. 나머지 넷과 같은 부품을 쓴다:
          scope(부서)가 먼저, 보기 방식(보관 포함)은 흐름 끝, 건수는 필터와 목록 **사이**. */}
      <FilterSurface>
        {/* 탐색 줄의 구조가 티켓·게시판과 **같다** (지시 2 · 8): 위 줄이 「무엇을
            찾는가」(검색), 아래 줄이 「무엇으로 좁히는가」(부서·보관). 예전에는 이 화면만
            검색이 아예 없어서, 프로젝트가 스무 개를 넘으면 이름을 눈으로 훑어야 했다. */}
        <ToolbarRow>
          <SearchBox
            value={filters.q}
            onSearch={commitSearch}
            placeholder="프로젝트 이름, 코드 검색"
            ariaLabel="프로젝트 검색"
          />
        </ToolbarRow>
        <FilterRow>
          {/* 후보는 이 응답이 들고 온다 — 서버가 계산한 내 조회 범위다. */}
          <DepartmentFilter
            departments={data.departments}
            value={filters.dept}
            onChange={(v) => setFilters({ dept: v })}
          />
          <FormControlLabel
            sx={{ m: 0 }}
            control={
              <Switch
                size="small"
                checked={!!filters.archived}
                onChange={(e) => setFilters({ archived: e.target.checked })}
              />
            }
            label={<Typography variant="body2">보관한 프로젝트 포함</Typography>}
          />
          {hasProjectFilter ? (
            <FilterActions>
              <Button variant="ghost" size="sm" onClick={clearProjectFilters}>필터 지우기</Button>
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>
      <ResultLine total={data.total} conditions={activeProjectConditions} />

      {q.isLoading ? <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={cols} rows={[]} loading /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : items.length === 0 ? (
          <Card>
            {/* «정말 없다» 와 «조건 때문에 0건» 을 가른다 (C1 · W5).
                예전에는 `filters.archived` 로만 갈라져서, 부서나 검색어로 0건이 된 화면도
                「프로젝트가 없습니다」라고 말했다 — 게다가 그 조건을 그 자리에서 풀 수단이
                없었다. 조건이 하나라도 걸려 있으면 그 사실을 말하고 지울 길을 준다. */}
            <ListEmptyState
              filtered={hasProjectFilter}
              onClear={clearProjectFilters}
              filteredTitle="조건에 맞는 프로젝트가 없습니다"
              filteredHelp="지금 걸린 조건(검색어, 부서, 상태)에 맞는 프로젝트가 없습니다. 조건을 지우면 전체를 볼 수 있습니다."
              art="tickets"
              title="프로젝트가 없습니다"
              situation={filters.archived ? undefined : "지금 진행 중인 프로젝트가 없거나, 있는 프로젝트가 전부 보관돼 있습니다."}
              help={filters.archived
                ? "보관한 것까지 포함해도 볼 수 있는 프로젝트가 없습니다."
                : "보관한 프로젝트까지 보려면 위의 스위치를 켜세요."}
            />
          </Card>
        ) : (
          <>
            {/* `overflow: hidden` 을 손으로 박으면 `stickyHeader` 가 죽는다 — 그 판이
                스크롤 컨테이너가 되어 열 이름이 판 안에 붙박인다. 목록 판은 `ListCard` 다. */}
            <ListCard sx={{ p: 0 }}>
              <DataTable
                stickyHeader
                columns={cols} rows={items} rowKey={(p) => p.id} onRow={open}
                // HashRouter다 — 실제 `href` 는 `#` 이 붙어야 새 탭에서 이 라우트로 실제
                // 도착한다(순수 클릭은 `open`/`nav()` 가 처리해 이 값을 안 본다).
                rowHref={(p) => "#/projects/" + p.id}
                empty="표시할 프로젝트가 없습니다."
                sort={{ key: filters.sort, dir: filters.order }}
                onSort={(key) => {
                  const next = toggleSort({ key: filters.sort, dir: filters.order }, key, key === "created_at" ? "desc" : "asc");
                  setFilters({ sort: next.key, order: next.dir });
                }}
              />
            </ListCard>
            {/* 여기 「이관할 때 이 프로젝트에서 문제가 있었습니다」 배너가 있었다. 얼어붙은
                이관 흔적 컬럼을 읽던 것이라 관리자에게 문의해도 없앨 방법이 없었다.
                서버도 그 필드를 걷었다(S14). */}
            <ListFooter
              total={q.total} loaded={q.loaded}
              hasNext={q.hasNext} isFetchingNext={q.isFetchingNext} onMore={q.fetchNext}
              moreLabel="프로젝트 더 보기"
            />
          </>
        )}

      <FormModal
        open={creating}
        title="새 프로젝트"
        fields={PROJECT_FORM_FIELDS}
        initial={{ status: "active" }}
        submitLabel="추가"
        onSubmit={submitCreate}
        onClose={() => setCreating(false)}
      />
    </div>
  );
}
