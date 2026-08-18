import React from "react";
import { useQuery } from "@tanstack/react-query";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Button, Callout, Card, ErrorState, MetricStrip, PageHeader, Skeleton } from "../ui/kit.jsx";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { LineSeries } from "../ui/charts/LineSeries.jsx";
import { ChartEmpty } from "../ui/charts/base.jsx";
import { ticketColumns, GroupedTickets, TicketEditModal, ticketConnState } from "./MyTickets.jsx";
import { groupByAssignee } from "./TeamTickets.jsx";
import { burndownSeries, wdBalanceItems } from "./sprint-charts.js";
import { useQueryState } from "../lib/useQueryState.js";
import {
  SPRINT_FIELDS, SPRINT_REPORT_FIELDS, TicketEmptyState, TicketFilterBar, clearTicketFilters,
  hasTicketFilter, matchesTicketFilters, ticketFilterSpec,
} from "./TicketFilterBar.jsx";
import { BASELINE_TRACKS, TILE_GRID_GAP, TILE_PADDING } from "../ui/density.js";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";

/* 도우미 > 주간 스프린트 회의. 한 화면에서 (1) 그 주의 담당자별 티켓, (2) 계획 티켓을 본다.
 * 편집은 회의 중 바로 — 기존 티켓 API 재사용. 데이터는 조회 전용.
 *
 * 2026-08 재설계(docs/NEXT_SESSION_PLAN.md §B, 사용자와 합의된 계획):
 *   - '티켓 배분' 섹션을 없앴다. 미할당 티켓 화면과 완전히 같은 목록·같은 조작이라, 회의 중
 *     어느 쪽에서 배정했는지 헷갈리고 두 화면을 따로 고쳐야 했다. 여기서는 '거기로 가는 길'만 남긴다.
 *   - '완료 현황' 카운트 표(개발자 × 완료/진행/검증/계획 숫자)를 담당자별 '티켓 목록'으로 바꿨다.
 *     숫자 표는 "누가 몇 건" 까지만 말해 주고 정작 회의에서 필요한 "무엇을" 은 말해 주지 않아서,
 *     매번 팀 티켓 화면을 따로 열어 이름으로 필터해야 했다. 제목을 누르면 그 티켓 상세로 간다.
 *   - '계획 논의'는 그대로 둔다(다음 주 이야기라 성격이 다르다).
 *
 * 2026-08 두 번째 손질 — **회의 순서대로** 다시 배치했다. 팀·프로젝트가 늘면서 담당자별
 * 목록 하나만으로는 화면이 끝없이 길어져, 회의 중 "지금 누구 얘기 중이냐"를 스크롤로 찾고
 * 있었다. 지금 순서는 회의에서 실제로 말하는 순서다:
 *
 *   1) 요약 + 번다운  — "이 주가 계획대로 가고 있나"
 *   2) 담당자 카드 격자 — "누가 얼마나 지고 있나". 1인 1카드(건수·업무량·지연), 누르면 그
 *      사람 티켓만 남는다. 한 사람을 보는 데 스크롤이 필요 없다.
 *   3) 담당자별 티켓 목록 — 고른 사람(또는 전원)의 '무엇을'
 *   4) 미할당 패널     — "이건 누가 가져갈까"
 *   5) 계획 논의       — "다음 주엔 뭘 하나"
 *
 * 그리고 화면이 스스로 **'날짜 범위 기준'** 이라고 말한다. Notion 의 스프린트 데이터베이스는
 * 이 포털 연동에 공유돼 있지 않아 읽지 못한다(조회하면 404). 즉 여기의 '이번 주'와 팀이
 * Notion 에서 만든 스프린트는 **다른 것**이다. 화면이 말하지 않으면 두 사람이 서로 다른 것을
 * 같은 이름으로 부르며 회의를 한다 — 지금까지 아무 말도 없었다. */

function mondayOf(d) {
  const x = new Date(d);
  const back = (x.getDay() + 6) % 7; // 월요일 기준
  x.setDate(x.getDate() - back); x.setHours(0, 0, 0, 0);
  return x;
}
function isoDate(d) { const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

/* 이 화면이 주소에 두는 상태.
 *
 * `week` 는 그 주 **월요일 날짜**다. 예전에는 '이번 주에서 몇 주 떨어졌나'(offset)를 화면
 * 상태로만 들고 있었다. 두 가지가 문제였다: 화면을 떠나면 사라지고, 설령 주소에 실었더라도
 * '-1' 은 **언제 열었느냐에 따라 다른 주**를 가리켜서 회의 링크를 공유할 수가 없다.
 *
 * 페이지는 없다 — /api/sprint/summary 는 그 주치를 전량 준다. 그래서 조건도 화면이 직접
 * 거른다(`matchesTicketFilters`). 서버가 자르는 목록에서 같은 짓을 하면 안 된다. */
const SPRINT_SPEC = ticketFilterSpec(SPRINT_FIELDS, { week: "", dept: "" });

/** 주소의 `week`(없으면 오늘) → 그 주 월요일. 이상한 값이면 이번 주로 떨어진다. */
function weekMonday(week) {
  if (!week) return mondayOf(new Date());
  const parsed = new Date(`${week}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? mondayOf(new Date()) : mondayOf(parsed);
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/* 응답 안에서 '앱 티켓 id를 가진' 온전한 티켓 행을 모아 tid → id 색인을 만든다.
 * 왜 필요한가: 담당자별 티켓의 출처인 app/reports/service.py의 _ticket_detail()은 tid·제목·상태만
 * 담고 앱 id는 담지 않는다(월간 리포트는 링크가 필요 없었다). 그래서 그대로 쓰면 제목을 눌러도
 * 갈 곳이 없다. 같은 응답에 이미 들어 있는 온전한 행(planned·unassigned)에서 id를 찾아 붙인다. */
function ticketIdByTid(d) {
  const index = new Map();
  for (const list of [d.planned, d.unassigned, d.tickets]) {
    if (!Array.isArray(list)) continue;
    for (const t of list) {
      if (t && t.tid != null && t.id != null && !index.has(t.tid)) index.set(t.tid, t.id);
    }
  }
  return index;
}

/* 담당자별 티켓 행을 만든다 — GroupedTickets + groupByAssignee(팀 티켓과 같은 그룹 규칙)에 그대로 넘긴다.
 *
 * 우선순위:
 *   1) 서버가 by_assignee를 주면 그것을 쓴다. 담당자별 주(week) 범위 필터는 서버가 판단해야 한다
 *      (지금 여기서 하는 파생은 임시다 — app/sprints/service.py가 by_assignee를 돌려주기 시작하면
 *      아래 2)번 가지를 통째로 지운다).
 *   2) 아직 없으면 응답에 이미 들어 있는 developers[].tickets(= 그 주에 담당자가 맡은 티켓)로 만든다.
 *      데이터를 새로 지어내지 않는다 — 서버가 준 것을 모양만 바꾼다.
 *
 * 반환 행에는 assignee_names를 한 명만 넣는다. developers 버킷 자체가 이미 '이 사람의 티켓'이라
 * 다중 담당 티켓은 각 담당자 버킷에 한 번씩 들어 있고, groupByAssignee가 그대로 각자 그룹에 넣는다. */
export function assigneeTicketRows(data) {
  const d = data || {};
  const index = ticketIdByTid(d);
  /* `owner_user_id` 는 **이 행이 놓인 버킷의 주인**이다. 티켓 자신의 `assignee_user_ids`
     (담당자 전원)는 손대지 않는다 — 편집 모달이 그 값으로 담당자 칸을 채우므로, 여기서
     한 명으로 줄이면 담당자가 둘인 티켓을 회의 중 편집하는 순간 **다른 담당자가 지워진다**.
     둘은 다른 질문에 답한다: "이 티켓은 누구 것들인가" 와 "이 줄은 누구 칸에 있나". */
  const withId = (t, name, ownerId) => {
    const id = t.id != null ? t.id : index.get(t.tid);
    return {
      ...t,
      id: id != null ? id : undefined,
      assignee_names: [name],
      owner_user_id: ownerId != null ? ownerId : undefined,
    };
  };

  // 같은 담당자 밑에 같은 티켓이 두 번 들어가는 것을 막는다.
  // app/reports/service.py는 티켓의 담당자 id마다 버킷에 한 번씩 넣는데, 앱에 연결되지 않은 Notion
  // 계정은 전부 '(미확인 담당자)' 한 사람으로 해석된다 — 담당자가 둘인 티켓이 그 버킷에 두 번
  // 들어가 목록에 똑같은 줄이 나란히 두 개 보였다(예전 카운트 표에서는 숫자만 부풀어 안 보였다).
  const dedupe = (rows) => {
    const seen = new Set();
    return rows.filter((t) => {
      const key = (t.assignee_names && t.assignee_names[0]) + "|" + (t.id != null ? "id:" + t.id : "tid:" + t.tid);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };

  if (d.by_assignee != null) {
    // [{name, user_id, tickets:[…]}] 또는 {이름: [티켓…]} 두 모양을 모두 받아들인다 — 백엔드가
    // 어느 쪽으로 확정하든 프런트를 다시 고치지 않게(계약이 정해지면 한쪽만 남긴다).
    // 사전 모양에는 버킷 주인의 앱 user_id 가 담길 자리가 없다(그 모양에서는 담당자 조건을
    // 화면이 걸 수 없다는 뜻이고, 없는 것을 지어내지 않는다).
    const groups = Array.isArray(d.by_assignee)
      ? d.by_assignee.map((g) => [g && g.name, (g && g.tickets) || [], g && g.user_id])
      : Object.entries(d.by_assignee).map(([name, tickets]) => [name, tickets, undefined]);
    return dedupe(groups.flatMap(([name, tickets, ownerId]) =>
      (Array.isArray(tickets) ? tickets : []).map((t) => withId(t, name || "(미확인 담당자)", ownerId))));
  }

  const devs = Array.isArray(d.developers) ? d.developers : [];
  return dedupe(devs.flatMap((dev) =>
    (Array.isArray(dev.tickets) ? dev.tickets : []).map((t) => withId(t, dev.name, dev.user_id))));
}

/* 이 응답의 행이 실제로 싣는 조건만 내놓는다.
 *
 * `by_assignee` 는 목록 API 와 같은 티켓 dict 라 프로젝트·담당자 id 가 들어 있다. 옛 모양
 * (`developers[].tickets`)은 리포트 경로라 둘 다 없다 — 거기서 두 조건을 그리면 고르는 순간
 * 목록이 통째로 비고, 사용자는 그것을 "티켓이 없다"로 읽는다. */
function sprintFields(data) {
  return data && data.by_assignee != null ? SPRINT_FIELDS : SPRINT_REPORT_FIELDS;
}

/* 행 하나가 조건을 지나는가.
 *
 * 공용 판정이 먼저다 — 규칙이 서버와 갈라지면 안 된다. 그 위에 **한 겹만** 얹는다:
 * 담당자 조건이 걸리면 행의 **주인**(그 행이 놓인 담당자 칸)까지 본다.
 *
 * 왜 한 겹이 더 필요한가. 공용 규칙은 서버와 같게 "담당자 중 한 명이라도 맞으면 통과"다.
 * 그런데 이 화면의 행은 담당자 칸마다 한 벌씩 복제된 것이라, 그 규칙만 쓰면 담당자가 둘인
 * 티켓이 **상대방 그룹에도** 남는다. 카드를 눌러 "이 사람 것만" 을 보려던 사용자에게 남의
 * 이름이 붙은 그룹이 하나 더 나오는 것은, 필터가 안 걸린 것과 구분되지 않는다. */
function sprintRowMatches(row, filters, fields) {
  if (!matchesTicketFilters(row, filters, fields)) return false;
  const who = fields.includes("assignee_user_id") ? filters.assignee_user_id : "";
  return !who || row.owner_user_id === who;
}

/* 담당자 한 명 = 카드 한 장.
 *
 * 숫자는 **서버가 준 그 주 전체 값**이다. 필터를 걸어도 흔들리지 않는다 — 통계 카드·그래프와
 * 같은 규칙이고, 흔들리면 "이 사람이 이번 주에 몇 건을 맡았나"의 답이 화면 상태에 따라
 * 달라진다. 카드를 눌러 좁히는 것은 **아래 목록**이다.
 *
 * 앱 user_id 가 없는 사람(앱에 연결되지 않은 Notion 계정, 예: '(미확인 담당자)')은 누를 수
 * 없다. 담당자 조건은 앱 user_id 로만 걸 수 있어서다(스펙 §12.3 — 브라우저는 소스 user id 를
 * 주지도 받지도 않는다). 누를 수 있는 척 그려 놓고 아무 일도 안 일어나게 두지 않는다. */
/* 담당자 현황 카드 줄.
 *
 * 담는 정보는 이름 한 줄 + 숫자 셋이다. 기준선에서 이만한 정보를 담는 자리는
 * `.admin-health`(작은 상태 타일 한 줄, 5열 + 12px 간격 + 16px 패딩)다 — `.card.pad`(20px)
 * 급의 큰 카드가 아니다. 3열로 벌려 두면 한 장이 500px 를 넘어 이름 옆이 통째로 빈다
 * (사용자 지적: "담당자 현황 카드도 정보에 비해서 카드가 너무 큰 거 아니야?"). */
export const PEOPLE_GRID = {
  display: "grid", gap: TILE_GRID_GAP, alignItems: "stretch",
  gridTemplateColumns: {
    xs: "1fr",
    sm: "repeat(2, minmax(0,1fr))",
    md: "repeat(3, minmax(0,1fr))",
    xl: BASELINE_TRACKS.health,
  },
};

function PersonCard({ person, active, onPick }) {
  const cells = [
    { label: "건수", value: `${person.assigned || 0}건` },
    { label: "업무량", value: `${person.est_all || 0}인일` },
    { label: "지연", value: `${person.overdue || 0}건`, warn: !!person.overdue },
  ];
  return (
    <Paper
      variant="outlined"
      component={onPick ? "button" : "div"}
      type={onPick ? "button" : undefined}
      onClick={onPick}
      aria-pressed={onPick ? !!active : undefined}
      sx={{
        // 여백은 기준선 `.health-card`(16px)다 — 이 타일이 담는 것도 이름 한 줄과 숫자 셋이다.
        p: TILE_PADDING, textAlign: "left", width: "100%", minWidth: 0,
        // 카드 자신도 격자다 — 이름 줄을 위에, 숫자 줄을 바닥에 붙여 카드끼리 눈금이 맞는다.
        display: "grid", gap: 1.5, alignContent: "space-between",
        font: "inherit", color: "inherit", cursor: onPick ? "pointer" : "default",
        borderColor: active ? "primary.main" : "divider",
        borderWidth: active ? 2 : 1,
        "&:hover": onPick ? { borderColor: "primary.main" } : undefined,
      }}
    >
      <Typography component="div" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, overflowWrap: "anywhere" }}>
        {person.name}
      </Typography>
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
        {cells.map((c) => (
          <Box key={c.label} sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{c.label}</Typography>
            <Typography
              component="div"
              sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body }}
              color={c.warn ? "warning.main" : "text.primary"}
            >
              {c.value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

export function Sprint() {
  const nav = useNavigate();
  const [filters, setFilters] = useQueryState(SPRINT_SPEC);
  const [editing, setEditing] = React.useState(null);

  const monday = weekMonday(filters.week);
  const start = isoDate(monday);
  const end = isoDate(addDays(monday, 7));
  const sunday = isoDate(addDays(monday, 6));
  // 주 이동은 히스토리에 남긴다(push) — 회의 중 지난 주를 봤다가 뒤로가기로 돌아오는 것이
  // 자연스럽다. 필터는 replace 라 글자마다 히스토리가 쌓이지 않는다.
  const goWeek = (m) => setFilters({ week: isoDate(m) }, { push: true });
  const offset = Math.round((monday - mondayOf(new Date())) / WEEK_MS);

  // 부서는 **화면 Context** 다(0060 §18) — 스프린트는 목록이 아니라 회의라 "지금 어느 팀
  // 이야기인가" 가 분명해야 하고, 여러 팀 데이터가 암묵적으로 섞이면 회의가 정확해지지 않는다.
  // 주소에 남기므로 새로고침·뒤로가기에서도 선택이 유지된다.
  const dept = filters.dept || "";
  const q = useQuery({
    queryKey: ["sprint", start, end, dept],
    queryFn: () =>
      api(`/api/sprint/summary?start=${start}&end=${end}`
        + (dept ? `&department_id=${encodeURIComponent(dept)}` : "")),
    retry: false,
  });
  const deptCtx = (q.data && q.data.department) || { selected: null, options: [] };

  const weekLabel = offset === 0 ? "이번 주" : offset === -1 ? "지난 주" : offset === 1 ? "다음 주" : `${start} ~ ${sunday}`;
  const nudge = (
    <Stack direction="row" gap={1} sx={{ flexWrap: "wrap" }}>
      <Button size="sm" onClick={() => goWeek(addDays(monday, -7))}>◀ 이전 주</Button>
      <Button size="sm" disabled={offset === 0} onClick={() => setFilters({ week: "" }, { push: true })}>이번 주</Button>
      <Button size="sm" onClick={() => goWeek(addDays(monday, 7))}>다음 주 ▶</Button>
    </Stack>
  );
  // 필터를 지우는 버튼은 **주소에 남을 수 있는 조건 전부**를 지운다. 지금 응답 모양에서
  // 그리지 않는 조건이라도 주소에는 남아 있을 수 있다(다른 주에서 걸어 둔 링크).
  const clearFilters = () => setFilters(clearTicketFilters(SPRINT_FIELDS));

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="도우미" area="스프린트 회의" title="스프린트 회의" spot="sprint" actions={nudge} />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, maxWidth: "70ch" }} aria-live="polite">
        {weekLabel} ({start} ~ {sunday}) 기준입니다. 담당자별로 무엇을 끝냈고 무엇을 하고 있는지 함께 보고, 다음 계획을 논의하세요. 회의 중 바로 수정할 수 있습니다.
      </Typography>
      {/* 조회 부서 — **필터가 아니라 화면 Context** 다(0060 §18). 필터처럼 목록 위에 작게
          두지 않고 화면 머리에 크게 둔다: 회의 참석자 전원이 "지금 어느 팀 이야기인가" 를
          같은 자리에서 봐야 한다. 고를 수 있는 부서는 서버가 조회 범위에서 계산해 준다
          (프런트가 스스로 계산하면 서버 검증과 갈라진다). */}
      {deptCtx.options.length > 1 ? (
        <Box sx={{ mb: 2, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <Typography component="span" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>
            조회 부서
          </Typography>
          <TextField
            select size="small" sx={{ minWidth: "20rem" }}
            value={deptCtx.selected || ""}
            onChange={(e) => setFilters({ dept: e.target.value }, { push: true })}
            aria-label="스프린트를 볼 부서"
          >
            {deptCtx.options.map((o) => (
              <MenuItem key={o.id} value={o.id}>
                {o.path.map((n) => n.name).join(" › ")}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      ) : null}
      {/* 이 화면의 '주'가 무엇인지 못박는다. 아무 말이 없으면 회의에서 두 사람이 서로 다른
          것을 같은 이름으로 부른다 — 한 사람은 이 날짜 범위를, 다른 사람은 Notion 스프린트를
          떠올린다. 연동에 공유되지 않은 데이터베이스를 있는 것처럼 말하지도 않는다. */}
      <Box sx={{ mb: 2.5 }}>
        <Callout tone="info">
          이 화면은 <b>날짜 범위 기준</b>입니다. 위 기간에 마감이 잡힌 티켓을 모읍니다. Notion 의 스프린트
          데이터베이스는 이 포털 연동에 공유되어 있지 않아 읽지 못합니다. 그래서 팀이 Notion 에서 만든 스프린트와
          이 화면의 한 주는 서로 다를 수 있습니다.
        </Callout>
      </Box>

      {q.isLoading ? <Card><Skeleton lines={8} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const d = q.data || {};
          // 연동 미설정 안내는 다른 티켓 화면과 같은 함수를 쓴다(문구가 화면마다 갈라지지 않게).
          const conn = ticketConnState(d);
          if (conn) return conn;
          if (d.ok === false) return <Callout tone="danger">{d.error || "불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>;
          const team = d.team || {};
          const unassignedCount = (d.unassigned || []).length;
          const fields = sprintFields(d);
          const filtered = hasTicketFilter(filters, fields);
          /* 조건은 화면이 건다. 이 응답은 그 주치를 **전량** 주므로(페이지가 없다) 여기서
             거르는 것이 정직하다 — 서버가 자르는 목록에서 같은 짓을 하면 한 페이지 안에서만
             걸러져 총 건수와 어긋난다. 통계 카드와 그래프는 서버가 준 그대로 둔다: 그건
             '이 주 전체' 를 말하는 값이고, 필터에 따라 흔들리면 다른 뜻이 된다. */
          // 계획 논의 행은 팀 티켓 목록에서 온 **원본 한 벌**이라 담당자 칸 복제가 없다 —
          // 그쪽은 공용 판정만 쓴다(주인 좁히기를 얹으면 담당자 조건에서 통째로 사라진다).
          const planned = (d.planned || []).filter((t) => matchesTicketFilters(t, filters, fields));
          const rows = assigneeTicketRows(d).filter((t) => sprintRowMatches(t, filters, fields));
          const people = groupByAssignee(rows).length;
          const onOpen = (t) => nav("/tickets/" + t.id, { state: { from: "/sprint" } });
          const cols = ticketColumns({ onEdit: setEditing, onOpen });

          /* 담당자 카드. 이번 주 배정이 있는 사람만 카드가 된다 — 활성 사용자 전원이 0짜리
             카드로 늘어서면 실제 편중이 그 사이에 묻힌다(WD 밸런스 막대와 같은 규칙).
             빠진 사람은 숨기지 않고 카드 밑에서 **숫자로 말한다**. */
          const devs = Array.isArray(d.developers) ? d.developers : [];
          const busy = devs.filter((p) => p && (p.has_tickets || p.assigned > 0));
          const idle = devs.length - busy.length;
          const canPick = fields.includes("assignee_user_id");
          const pickPerson = (uid) => setFilters({ assignee_user_id: filters.assignee_user_id === uid ? "" : uid });
          return (
            <>
              {/* 건수 셋과 인일 하나가 한 줄에 있다 — 단위가 섞이므로 라벨에 단위를 적는다
                  (지시 9의 "Ticket Count 와 WD 를 의미 없이 혼합하지 않는다"). */}
              <MetricStrip
                ariaLabel="이번 주 팀 합계"
                items={[
                  { key: "done", value: team.done || 0, label: "완료(건)", primary: true },
                  { key: "in_progress", value: team.in_progress || 0, label: "진행 중(건)" },
                  { key: "est", value: team.est_done_total || 0, label: "완료 업무량(인일)" },
                  { key: "overdue", value: team.overdue || 0, label: "지연(건)", kind: team.overdue ? "warn" : undefined },
                ]}
                sx={{ mb: 2.5 }}
              />

              {/* 번다운 + WD 밸런스. 회의에서 먼저 묻는 두 가지가 "이 주가 계획대로 가고 있나"와
                  "누구에게 몰려 있나"다 — 목록을 읽기 전에 그 둘을 그림으로 한 번에 본다.
                  차트 라이브러리는 들이지 않는다(번들 예산). ui/charts 의 SVG 컴포넌트를 쓴다. */}
              <Box
                component="section" aria-labelledby="sprint-flow"
                sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0,1fr))" } }}
              >
                <Card>
                  <Typography component="h2" id="sprint-flow" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 0.5 }}>
                    번다운
                  </Typography>
                  {/* 그림이 무엇을 말하고 **무엇을 말하지 않는지**를 그림 옆에 쓴다. 완료 시각이
                      기록되지 않아 날짜별 실제 이력은 그릴 수 없다 — 그걸 숨기면 사람들은 이
                      그림을 실제 진행으로 읽는다. */}
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5, maxWidth: "60ch" }}>
                    두 선 모두 <b>마감일</b>이 축입니다. ‘계획’은 그날 이후로 마감이 남아 있는 업무량,
                    ‘아직 미완료’는 그중 끝나지 않은 것입니다. 두 선의 간격이 이미 끝낸 일입니다.
                    완료 시각은 원본에 기록이 없어 날짜별 실제 이력은 그리지 않습니다.
                  </Typography>
                  {(() => {
                    const bd = burndownSeries(d.burndown);
                    return bd
                      ? <LineSeries series={bd.series} labels={bd.labels} unit="인일" summary={bd.summary} />
                      : <ChartEmpty label="이 주에 마감인 업무량이 없습니다" height="9rem" />;
                  })()}
                </Card>
                <Card>
                  <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 0.5 }}>
                    담당자별 업무량(WD)
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5, maxWidth: "60ch" }}>
                    이 주에 마감인 티켓의 예상 업무량 합계입니다(취소 제외). 평균의 1.5배를 넘는 사람만 색으로 표시합니다.
                  </Typography>
                  {(() => {
                    const wd = wdBalanceItems(d.developers);
                    return wd ? (
                      <>
                        <BarSeries items={wd.items} max={wd.max} unit="인일" formatValue={(v) => String(v)} />
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                          {wd.summary}
                        </Typography>
                      </>
                    ) : <ChartEmpty label="이 주에 배정된 업무가 없습니다" height="9rem" />;
                  })()}
                </Card>
              </Box>

              {/* 담당자 현황 — 1인 1카드. 예전에는 이 자리에 담당자별 티켓이 통째로 늘어서서,
                  사람이 늘수록 "지금 누구 얘기 중이냐"를 스크롤로 찾아야 했다. 카드 격자는
                  한 화면에서 전원을 훑게 하고, 누르면 아래 목록이 그 사람만 남는다.
                  `alignItems: "stretch"` 다 — `start` 로 두면 카드마다 제 내용 높이를 가져
                  줄 바닥이 들쭉날쭉해진다(사용자가 지적한 Q5 "카드 크기가 제각각"). */}
              <Box component="section" aria-labelledby="sprint-people" sx={{ mb: 2.5 }}>
                <Typography component="h2" id="sprint-people" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 0.5 }}>
                  담당자 현황 ({busy.length}명)
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5, maxWidth: "70ch" }}>
                  이 주 전체 기준입니다(아래 조건을 걸어도 카드 숫자는 바뀌지 않습니다).
                  {canPick ? " 카드를 누르면 아래 목록이 그 사람 티켓만 남습니다." : ""}
                </Typography>
                {busy.length ? (
                  <Box sx={PEOPLE_GRID}>
                    {busy.map((p) => (
                      <PersonCard
                        key={p.user_id || p.name}
                        person={p}
                        active={!!p.user_id && filters.assignee_user_id === p.user_id}
                        onPick={canPick && p.user_id ? () => pickPerson(p.user_id) : undefined}
                      />
                    ))}
                  </Box>
                ) : (
                  <Card><Typography variant="body2" color="text.secondary">이 주에 배정된 티켓이 없습니다.</Typography></Card>
                )}
                {idle > 0 ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                    이번 주 배정이 없는 사람 {idle}명은 카드로 그리지 않습니다.
                  </Typography>
                ) : null}
              </Box>

              {/* 목록 두 개가 같은 조건을 쓴다 — 회의 중 "이 프로젝트만 보자" 를 한 번에 건다.
                  대분류와 기한은 여기 없다: 대분류는 리포트 경로 행에 없고, 기한 버킷은 '오늘'이
                  있어야 풀린다(TicketFilterBar 의 CLIENT_JUDGED 주석). */}
              <TicketFilterBar fields={fields} value={filters} onChange={setFilters} onClear={clearFilters} />

              {/* aria-labelledby로 두 섹션에 이름을 준다 — 이름 없는 <section>은 스크린리더에서
                  랜드마크로 잡히지 않아, 같은 모양의 표 두 개 사이를 건너뛸 방법이 없었다. */}
              <Box component="section" aria-labelledby="sprint-by-assignee" sx={{ mb: 4 }}>
                <Typography component="h2" id="sprint-by-assignee" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>
                  담당자별 티켓 ({people}명)
                </Typography>
                <Card>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "70ch" }}>
                    이 주에 담당자별로 맡은 티켓입니다. 제목을 누르면 티켓 상세가 열리고, ‘수정’으로 상태, 담당자, 마감을 바로 바꿀 수 있습니다.
                  </Typography>
                  <GroupedTickets
                    rows={rows}
                    columns={cols}
                    groupBy={groupByAssignee}
                    // VIS-64: 담당자가 몇 명만 넘어도 이 표가 11,000px를 넘어 페이지네이션 없이
                    // 한 화면에 다 들어갔다. 담당자 카드(위)를 눌러 한 사람만 볼 수도 있지만,
                    // 회의 초반엔 전원을 보며 한 사람씩 순서대로 넘어가는 쓰임도 있다 — 그때를
                    // 위해 그룹을 접어서 시작하고 펼쳐 가는 흐름을 준다.
                    collapsible
                    emptyState={
                      <TicketEmptyState
                        filtered={filtered} onClear={clearFilters}
                        title="이 주에 담당자가 맡은 티켓이 없습니다"
                        help="위의 주 이동으로 다른 주를 볼 수 있습니다."
                      />
                    } />
                </Card>
              </Box>

              {/* 미할당 = 배분 대상. 회의에서 "이건 누가 가져갈까"를 하는 자리라 담당자별 목록
                  **뒤, 다음 주 계획 앞**에 둔다(그게 말이 오가는 순서다).

                  예전에는 담당자별 목록 위에 안내 한 줄로 얹혀 있어서, 그 목록의 머리말처럼
                  읽혔다. 지금은 제 이름을 가진 패널이다 — 스크린리더에서도 건너뛸 수 있는
                  랜드마크가 된다.

                  목록은 여기서 다시 그리지 않는다. 같은 목록이 두 화면에 있으면 회의 중 어디서
                  무엇을 배정했는지 추적이 안 된다(이것이 '티켓 배분' 섹션을 지운 이유다).
                  대신 몇 건인지 말하고, 배정할 수 있는 화면으로 보낸다. */}
              <Box component="section" aria-labelledby="sprint-unassigned" sx={{ mb: 4 }}>
                <Typography component="h2" id="sprint-unassigned" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>
                  미할당 티켓 (배분 대상 {unassignedCount}건)
                </Typography>
                <Card>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "70ch" }}>
                    {unassignedCount > 0
                      ? `담당자가 없는 활성 티켓이 ${unassignedCount}건 있습니다. 회의에서 누가 가져갈지 정하고, 아래 화면에서 담당자를 지정하세요.`
                      : "담당자가 없는 활성 티켓이 없습니다. 배분할 것이 없습니다."}
                  </Typography>
                  <Button variant={unassignedCount > 0 ? "primary" : "default"} onClick={() => nav("/unassigned")}>
                    ‘미할당 티켓’ 화면 열기
                  </Button>
                </Card>
              </Box>

              <Box component="section" aria-labelledby="sprint-planned" sx={{ mb: 4 }}>
                <Typography component="h2" id="sprint-planned" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1.5 }}>
                  계획 논의 (계획 {planned.length}건)
                </Typography>
                <Card>
                  <GroupedTickets
                    rows={planned}
                    columns={ticketColumns({ showAssignee: true, onEdit: setEditing, onOpen })}
                    emptyState={
                      <TicketEmptyState
                        filtered={filtered} onClear={clearFilters}
                        title="계획 상태 티켓이 없습니다"
                        help="다음 주에 할 일을 계획 상태로 만들면 여기에 모입니다."
                      />
                    } />
                </Card>
              </Box>

              <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
            </>
          );
        })()}
    </div>
  );
}
