import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
// `fmtNum` 은 운영 화면 헬퍼에 있다(대시보드와 같은 출처를 쓴다 — 숫자 표기가
// 두 화면에서 달라지면 같은 값이 다르게 보인다).
import { fmtNum } from "./ops/opsHelpers.js";
import { Card, ErrorState, Skeleton, StatCard } from "../ui/kit.jsx";
import { DashSection, HEADLINE_GRID, Note } from "../ui/adminKit.jsx";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";

/* 내 업무 요약 — **사용자 홈의 구역** (0060 §3).
 *
 * 예전에는 이 컴포넌트가 `Dashboard.jsx`(관리자 대시보드) 안에 있었고 그 화면 하단 절반을
 * 차지했다. 그런데 여기 있는 숫자는 전부 개인 업무이거나 그 사람의 조회 범위 요약이고,
 * 카드를 누르면 전부 사용자 콘솔(`/my-tickets`·`/projects`·`/me`)로 나갔다 — 즉 관리자
 * 대시보드에서 한 번 누르면 탭이 바뀌었다.
 *
 * 관리자 콘솔은 Control Plane 이다: 운영·관리 정보만 둔다. 개인 업무는 사용자 홈에 둔다.
 *
 * **별도 파일로 뺀 이유**는 번들이다. 사용자 콘솔은 관리자 화면 설정(registry.js, gzip
 * 43KB)을 일부러 안 들여온다(UserRoutes.jsx 헤더 주석). `Dashboard.jsx` 에서 이 컴포넌트를
 * import 하면 그 노력이 통째로 무너진다 — 관리자 대시보드 전체가 사용자 번들에 딸려 온다.
 */

/* 티켓 소스 장애 안내.
 *
 * **같은 화면에서 같은 문장을 두 번 말하지 않는다.** 이 구역이 사용자 홈으로 옮겨오면서
 * 바로 위 스프린트 카드가 이미 "티켓 소스를 읽지 못해 …" 를 말하는 자리가 됐다 —
 * 원인을 두 번 설명하면 사용자는 서로 다른 두 문제로 읽는다. 원인은 그쪽이 말하고,
 * 여기서는 **이 구역에만 해당하는 사실**(무엇이 못 세어지고 무엇은 멀쩡한가)만 말한다.
 * AssistantPanel 이 같은 이유로 이미 "위 스프린트 카드와 같은 이유로" 라고 참조한다. */
export const WORK_UNKNOWN = "같은 이유로 내 미완료, 이번 주 마감, 지연 티켓은 셀 수 없습니다. 차질 프로젝트, 지연 마일스톤은 다른 소스라 정상 집계됩니다.";

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
      {/* FN-42: 점수가 있어도 5개 규칙 중 일부만 판정됐을 수 있다(예: 마일스톤이 없어 그
          규칙만 못 잼) — 감점이 없으면 그대로 만점처럼 보여 '다 재서 건강함'과 구별이
          안 된다. unscored(점수 자체 없음)와 다른 신호라 별도 문구로 말한다. */}
      {projects.low_confidence ? (
        <Note>일부 지표만으로 계산된 프로젝트 {fmtNum(projects.low_confidence)}건이 있어 점수의 신뢰도가 낮을 수 있습니다.</Note>
      ) : null}
      {projects.truncated ? (
        <Note>프로젝트가 많아 일부만 훑었습니다. 합계가 전체와 다를 수 있습니다.</Note>
      ) : null}

      {/* PA-RC-0018: 차질 프로젝트/지연 마일스톤 이름·사유 목록(WorkList, 2카드)이 여기 있었다.
          TEST SERVER 실측(2026-08-16)에서 대시보드 문서 높이가 1.5화면 예산(acceptance
          criteria 2)을 넘겨(1805px) 지웠다 — 위 StatCard 두 장이 이미 개수를 보여주고
          클릭하면 /projects로 간다, 이름·사유는 거기서 본다. 인벤토리·현재 큐 상태 구역을
          상세 화면으로 내린 것과 같은 판단이다(같은 값을 화면에 두 번, 이번엔 "개수"와
          "그 개수의 목록"으로 반복하지 않는다). 항목 3개 이하로 줄이는 것부터 먼저
          시도했으나(서버가 count와 별개로 items를 최대 5줄까지만 주므로) 실측 데이터가 이미
          3건 이하라 절감 효과가 없었다 — 카드 자체를 지워야 폭을 줄일 수 있었다. */}

      {trend ? (
        <Box sx={{ mt: 2 }}>
          <Card sx={{ p: 2.5 }}>
            <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1.5 }}>최근 완료 추이</Typography>
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

