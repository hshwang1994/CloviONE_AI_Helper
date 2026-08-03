import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Button, Callout, Card, ErrorState, PageHeader, Skeleton, StatCard } from "../ui/kit.jsx";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { LineSeries } from "../ui/charts/LineSeries.jsx";
import { ChartEmpty } from "../ui/charts/base.jsx";
import { ticketColumns, GroupedTickets, TicketEditModal, ticketConnState } from "./MyTickets.jsx";
import { groupByAssignee } from "./TeamTickets.jsx";
import { burndownSeries, wdBalanceItems } from "./sprint-charts.js";

/* 도우미 > 주간 스프린트 회의. 한 화면에서 (1) 그 주의 담당자별 티켓, (2) 계획 티켓을 본다.
 * 편집은 회의 중 바로 — 기존 티켓 API 재사용. 데이터는 조회 전용.
 *
 * 2026-08 재설계(docs/NEXT_SESSION_PLAN.md §B, 사용자와 합의된 계획):
 *   - '티켓 배분' 섹션을 없앴다. 미할당 티켓 화면과 완전히 같은 목록·같은 조작이라, 회의 중
 *     어느 쪽에서 배정했는지 헷갈리고 두 화면을 따로 고쳐야 했다. 여기서는 '거기로 가는 길'만 남긴다.
 *   - '완료 현황' 카운트 표(개발자 × 완료/진행/검증/계획 숫자)를 담당자별 '티켓 목록'으로 바꿨다.
 *     숫자 표는 "누가 몇 건" 까지만 말해 주고 정작 회의에서 필요한 "무엇을" 은 말해 주지 않아서,
 *     매번 팀 티켓 화면을 따로 열어 이름으로 필터해야 했다. 제목을 누르면 그 티켓 상세로 간다.
 *   - '계획 논의'는 그대로 둔다(다음 주 이야기라 성격이 다르다). */

function mondayOf(d) {
  const x = new Date(d);
  const back = (x.getDay() + 6) % 7; // 월요일 기준
  x.setDate(x.getDate() - back); x.setHours(0, 0, 0, 0);
  return x;
}
function isoDate(d) { const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

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
  const withId = (t, name) => {
    const id = t.id != null ? t.id : index.get(t.tid);
    return { ...t, id: id != null ? id : undefined, assignee_names: [name] };
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
    // [{name, tickets:[…]}] 또는 {이름: [티켓…]} 두 모양을 모두 받아들인다 — 백엔드가 어느 쪽으로
    // 확정하든 프런트를 다시 고치지 않게(계약이 정해지면 한쪽만 남긴다).
    const groups = Array.isArray(d.by_assignee)
      ? d.by_assignee.map((g) => [g && g.name, (g && g.tickets) || []])
      : Object.entries(d.by_assignee);
    return dedupe(groups.flatMap(([name, tickets]) =>
      (Array.isArray(tickets) ? tickets : []).map((t) => withId(t, name || "(미확인 담당자)"))));
  }

  const devs = Array.isArray(d.developers) ? d.developers : [];
  return dedupe(devs.flatMap((dev) =>
    (Array.isArray(dev.tickets) ? dev.tickets : []).map((t) => withId(t, dev.name))));
}

export function Sprint() {
  const nav = useNavigate();
  const [offset, setOffset] = React.useState(0); // 0=이번 주, -1=지난 주 …
  const [editing, setEditing] = React.useState(null);

  const monday = addDays(mondayOf(new Date()), offset * 7);
  const start = isoDate(monday);
  const end = isoDate(addDays(monday, 7));
  const sunday = isoDate(addDays(monday, 6));

  const q = useQuery({
    queryKey: ["sprint", start, end],
    queryFn: () => api(`/api/sprint/summary?start=${start}&end=${end}`),
    retry: false,
  });

  const weekLabel = offset === 0 ? "이번 주" : offset === -1 ? "지난 주" : offset === 1 ? "다음 주" : `${start} ~ ${sunday}`;
  const nudge = (
    <Stack direction="row" gap={1} sx={{ flexWrap: "wrap" }}>
      <Button size="sm" onClick={() => setOffset((o) => o - 1)}>◀ 이전 주</Button>
      <Button size="sm" disabled={offset === 0} onClick={() => setOffset(0)}>이번 주</Button>
      <Button size="sm" onClick={() => setOffset((o) => o + 1)}>다음 주 ▶</Button>
    </Stack>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="도우미" area="스프린트 회의" title="스프린트 회의" spot="sprint" actions={nudge} />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch" }} aria-live="polite">
        {weekLabel} ({start} ~ {sunday}) 기준입니다. 담당자별로 무엇을 끝냈고 무엇을 하고 있는지 함께 보고, 다음 계획을 논의하세요. 회의 중 바로 수정할 수 있습니다.
      </Typography>

      {q.isLoading ? <Card><Skeleton lines={8} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const d = q.data || {};
          // 연동 미설정 안내는 다른 티켓 화면과 같은 함수를 쓴다(문구가 화면마다 갈라지지 않게).
          const conn = ticketConnState(d);
          if (conn) return conn;
          if (d.ok === false) return <Callout tone="danger">{d.error || "불러오지 못했습니다."}</Callout>;
          const team = d.team || {};
          const unassignedCount = (d.unassigned || []).length;
          const planned = d.planned || [];
          const rows = assigneeTicketRows(d);
          const people = groupByAssignee(rows).length;
          const onOpen = (t) => nav("/tickets/" + t.id);
          const cols = ticketColumns({ onEdit: setEditing, onOpen });
          return (
            <>
              <Box
                sx={{
                  display: "grid", gap: 2, mb: 2.5,
                  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "repeat(4, minmax(0,1fr))" },
                }}
              >
                <StatCard value={team.done || 0} label="완료(건)" />
                <StatCard value={team.in_progress || 0} label="진행 중(건)" />
                <StatCard value={team.est_done_total || 0} label="완료 업무량(인일)" />
                <StatCard value={team.overdue || 0} label="지연(건)" kind={team.overdue ? "warn" : undefined} />
              </Box>

              {/* 번다운 + WD 밸런스. 회의에서 먼저 묻는 두 가지가 "이 주가 계획대로 가고 있나"와
                  "누구에게 몰려 있나"다 — 목록을 읽기 전에 그 둘을 그림으로 한 번에 본다.
                  차트 라이브러리는 들이지 않는다(번들 예산). ui/charts 의 SVG 컴포넌트를 쓴다. */}
              <Box
                component="section" aria-labelledby="sprint-flow"
                sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0,1fr))" } }}
              >
                <Card>
                  <Typography component="h2" id="sprint-flow" variant="h6" sx={{ fontSize: "1.0625rem", mb: 0.5 }}>
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
                  <Typography component="h2" variant="h6" sx={{ fontSize: "1.0625rem", mb: 0.5 }}>
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

              {/* 예전의 '티켓 배분' 섹션 자리. 목록을 통째로 다시 그리지 않고 담당자를 지정할 수 있는
                  화면으로 보내기만 한다 — 같은 목록이 두 화면에 있으면 회의 중 어디서 무엇을 했는지
                  추적이 안 된다. 미할당이 0건이면 굳이 이 줄을 띄우지 않는다. */}
              {unassignedCount > 0 ? (
                <Box sx={{ mb: 2.5 }}>
                  <Callout tone="warn">
                    담당자가 없는 활성 티켓이 {unassignedCount}건 있습니다.{" "}
                    <Link component="button" type="button" underline="hover" sx={{ font: "inherit" }} onClick={() => nav("/unassigned")}>
                      ‘미할당 티켓’ 화면
                    </Link>
                    에서 담당자를 지정하세요.
                  </Callout>
                </Box>
              ) : null}

              {/* aria-labelledby로 두 섹션에 이름을 준다 — 이름 없는 <section>은 스크린리더에서
                  랜드마크로 잡히지 않아, 같은 모양의 표 두 개 사이를 건너뛸 방법이 없었다. */}
              <Box component="section" aria-labelledby="sprint-by-assignee" sx={{ mb: 4 }}>
                <Typography component="h2" id="sprint-by-assignee" variant="h6" sx={{ fontSize: "1.0625rem", mb: 1.5 }}>
                  담당자별 티켓 ({people}명)
                </Typography>
                <Card>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "70ch" }}>
                    이 주에 담당자별로 맡은 티켓입니다. 제목을 누르면 티켓 상세가 열리고, ‘편집’으로 상태·담당자·마감을 바로 바꿀 수 있습니다.
                  </Typography>
                  <GroupedTickets
                    rows={rows}
                    columns={cols}
                    groupBy={groupByAssignee}
                    empty="이 주에 담당자가 맡은 티켓이 없습니다." />
                </Card>
              </Box>

              <Box component="section" aria-labelledby="sprint-planned" sx={{ mb: 4 }}>
                <Typography component="h2" id="sprint-planned" variant="h6" sx={{ fontSize: "1.0625rem", mb: 1.5 }}>
                  계획 논의 (계획 {planned.length}건)
                </Typography>
                <Card>
                  <GroupedTickets
                    rows={planned}
                    columns={ticketColumns({ showAssignee: true, onEdit: setEditing, onOpen })}
                    empty="계획 상태 티켓이 없습니다." />
                </Card>
              </Box>

              <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
            </>
          );
        })()}
    </div>
  );
}
