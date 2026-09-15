import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
// `fmtNum` 은 운영 화면 헬퍼에 있다(대시보드와 같은 출처를 쓴다 — 숫자 표기가
// 두 화면에서 달라지면 같은 값이 다르게 보인다).
import { fmtNum } from "./ops/opsHelpers.js";
import { StatusList, StatusTile } from "../ui/adminKit.jsx";
import { ErrorState, Skeleton, SubGroup, TechDetail } from "../ui/kit.jsx";
import { ProgressRows } from "../ui/charts/ProgressRows.jsx";
import { fmtDayKo } from "../lib/format.js";
import { FONT_WEIGHT, KO_WORD_BREAK, MOTION } from "../ui/theme.js";

/* 이번 주 업무 상태 — **사용자 홈 오른쪽 레일의 한 묶음** (0060 §3).
 *
 * 예전에는 이 컴포넌트가 관리자 대시보드 안에 있었고, 그 뒤에는 홈 아래쪽에서 전체 폭
 * 구역을 차지했다. 두 자리 모두 문제가 있었다.
 *
 * ## 같은 숫자를 두 번 말하고 있었다
 *
 * 판독 줄에 다섯 칸이 있었는데 그중 둘은 **바로 위 줄과 같은 값**이었다.
 * `mine.open` 은 홈 상단의 「진행 중」과 같은 함수가 센 값이고(app/home/work.py 의 주석이
 * 그렇게 적어 뒀다), `mine.overdue` 는 「지연」과 같은 값이다. 실측(2026-08-26)에서 한
 * 화면에 「지연 12」와 「지연 티켓 12」가 나란히 떠 있었다. 나머지 하나(`due_this_week`)도
 * 오른쪽 스프린트 도넛의 모수와 같은 수다.
 *
 * 그래서 **티켓 축의 숫자는 여기서 전부 뺐다.** 남는 것은 다른 축이다: 프로젝트와
 * 마일스톤, 그리고 주마다 끝낸 양의 흐름.
 *
 * ## 진단 문구를 화면에서 내렸다
 *
 * 「아직 Health 를 계산하지 않은 프로젝트」·「일부 지표만으로 계산된 프로젝트가 있어 점수의
 * 신뢰도가 낮을 수 있습니다」는 사실이지만, 그 문장을 읽고 사용자가 할 수 있는 일이 없다.
 * 한 줄 요약만 남기고 자세한 이유는 접어 둔다 — 지우지는 않는다(§불변 6: 없는 것을 있는
 * 척하지 않는다. 빠진 것이 있으면 빠졌다고 말해야 한다).
 *
 * ## 막대는 «그 주에 마감이던 일 가운데 얼마나 끝냈는가» 다
 *
 * 완료 1건짜리 주가 화면 폭을 가득 채운 막대로 그려지고 있었다. 가장 큰 값을 꽉 찬 막대로
 * 보는 상대 축소는 값들 사이의 크기 비교에는 맞지만, 「많이 했나 적게 했나」를 묻는 자리
 * 에서는 규모를 부풀린다.
 *
 * 다행히 이 자료에는 **제대로 된 분모가 있다.** `assigned` 는 그 주에 마감이던 내 티켓
 * 전부이고 `done` 은 그중 상태가 완료인 것이라, 둘은 같은 모집단이다
 * (`app/home/aggregate.py::sprint_progress` — 창 판정이 두 값에 똑같이 걸린다). 그래서
 * 막대를 **비율**로 읽을 수 있다: 마감 12건 중 3건을 끝낸 주는 4분의 1 만큼 찬다.
 *
 * 마감이 0건인 주는 0% 가 아니라 **분모가 없는 주**다. 0% 로 그리면 「아무것도 못 했다」로
 * 읽히는데 사실은 「할 것이 없었다」다 — 그 줄은 중립 트랙과 「마감 없음」이다.
 *
 * 줄 모양도 바꿨다. 예전에는 [이름 | 값 | 막대] 가 한 행이었고 부연이 **어떤 줄에만** 한
 * 줄을 더 만들어 행 높이가 들쭉날쭉했다(실측 1920: 넉 주 중 둘만 아래에 한 줄이 더 있었고
 * 막대는 110px 였다). 이제 모든 주가 「기간 + 사실」 한 줄과 「가득 폭 막대」 한 줄로
 * 똑같다(`ui/charts/ProgressRows.jsx`).
 *
 * **별도 파일로 둔 이유**는 번들이다. 사용자 콘솔은 관리자 화면 설정(registry.js)을 일부러
 * 안 들여온다(UserRoutes.jsx 헤더 주석). 이 묶음을 `Dashboard.jsx` 안에 두면 관리자 화면
 * 전체가 사용자 번들에 딸려 온다.
 */

/* 티켓 소스 장애 안내.
 *
 * **같은 화면에서 같은 문장을 두 번 말하지 않는다.** 바로 위 스프린트 도넛이 이미 "티켓
 * 소스를 읽지 못해 …" 를 말하는 자리다. 원인은 그쪽이 말하고, 여기서는 **이 묶음에만
 * 해당하는 사실**만 말한다. AssistantPanel 이 같은 이유로 짧게 참조만 한다. */
export const WORK_UNKNOWN = "같은 이유로 최근 완료 추이도 셀 수 없습니다. 프로젝트와 마일스톤은 다른 소스라 정상 집계됩니다.";

// 완료 추이의 기준. 소스에 '상태가 완료로 바뀐 시각'이 없다(app/projects/weekly.py 와
// app/sprints/burndown.py 가 같은 사정을 적어 뒀다). 없는 이력을 추정해 선을 그으면 그건
// 추이가 아니라 창작이라, 화면이 기준을 그대로 말한다.
//
// 다만 **본문에 상시로 두지 않는다.** 이 두 문장은 그림을 의심할 때만 필요하고, 평소에는
// 좁은 레일에서 넉 줄을 차지하며 그림보다 길었다. 「집계 기준」 도움말 안으로 내린다.
export const TREND_BASIS = "한 주는 월요일에 시작합니다. 완료 여부는 마감일이 그 주에 든 티켓만 셉니다.";
export const TREND_BASIS_LIMIT = "티켓에는 완료로 바꾼 시각이 없어서, 지난주에 끝낸 일도 마감일이 있는 주에 셉니다.";

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

/** 추이 한 줄 — 기간 이름과 그 주의 두 수.
 *
 * `total` 이 0 이면 **분모가 없는 주**다(그 주에 마감이 하나도 없었다). `ProgressRows` 가
 * 그 줄을 0% 가 아니라 중립 트랙으로 그린다. 여기서 0 을 1 로 바꾸거나 그 줄을 빼면
 * 「그 주가 없었다」가 되어 추이의 간격이 거짓말을 한다.
 *
 * 라벨에서 연도를 뺀다 — 넉 주짜리 그림에서 같은 해가 네 번 나오면 폭만 먹는다. */
export function trendRows(trend) {
  const rows = Array.isArray(trend) ? trend : [];
  return rows.map((w) => ({
    key: w.week_of,
    label: `${fmtDayKo(w.week_of)} 주간`,
    value: w.done || 0,
    total: w.assigned || 0,
  }));
}

/* 프로젝트 축 한 줄 — 이름과 값, 누르면 그 목록으로 간다.
 *
 * 판독 칸(지금은 걷힌 `MetricStrip`)을 쓰지 않았다. 이 자리는 좁은 레일이고, 값 둘을 40px 로 세우면
 * 「지금 급한 것」보다 커진다. 목록 줄이 맞는 모양이다 — 대시보드 · 진단의 상태 줄과 같은 부품
 * (`StatusList` · `StatusTile`)이다(계획 B-6). 예전에는 같은 줄을 이 파일이 손으로 그렸다. */
function StatRow({ label, value, kind, onClick, ariaLabel }) {
  const tone = kind === "danger" ? "error.strong" : kind === "warn" ? "warning.strong" : "text.primary";
  return (
    <StatusTile name={label} onClick={onClick} ariaLabel={ariaLabel}>
      <Typography
        component="span"
        sx={{ fontWeight: FONT_WEIGHT.bold, color: tone, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}
      >
        {value}건
      </Typography>
    </StatusTile>
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
    return q.isError
      ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} size="compact" />
      : <Skeleton kind="chart" height="6rem" />;
  }

  const d = q.data;
  const projects = d.projects || {};
  const troubled = projects.troubled || { count: 0, items: [] };
  const overdueMs = (d.milestones || {}).overdue || { count: 0, items: [] };
  const trend = d.completion_trend;
  const rows = trendRows(trend);
  // 지문에 **값**이 들어가야 그림이 실제로 바뀔 때만 다시 그려진다(ui/motion.js).
  const trendKey = trend ? "home-trend:" + trend.map((w) => `${w.week_of}:${w.done}:${w.assigned}`).join(",") : null;
  const caveat = !!(projects.unscored || projects.low_confidence || projects.truncated);

  return (
    <>
      {/* `first` 를 준다 — 이 묶음 위에 스프린트 진척이 있는 것은 맞지만, 그 둘을 가르는
          실선은 이제 **굴리지 않는 상자**가 갖는다(Home.jsx 의 「이번 주」 판). 여기에
          두면 몇 줄만 굴려도 경계가 스크롤 밖으로 사라진다. */}
      <SubGroup title="프로젝트" first>
        <StatusList ariaLabel="프로젝트">
          <StatRow
            label="차질 프로젝트" value={fmtNum(troubled.count)}
            kind={troubled.count ? "danger" : undefined}
            onClick={() => nav("/projects")} ariaLabel="차질 프로젝트 목록 열기"
          />
          <StatRow
            label="지연 마일스톤" value={fmtNum(overdueMs.count)}
            kind={overdueMs.count ? "warn" : undefined}
            onClick={() => nav("/projects")} ariaLabel="지연 마일스톤이 있는 프로젝트 목록 열기"
          />
        </StatusList>
        {/* 빠진 것이 있으면 빠졌다고 말한다. 다만 그 이유를 화면 본문에 세 줄로 늘어놓지
            않는다 — 읽어도 사용자가 할 수 있는 일이 없는 문장이다. */}
        {caveat ? (
          <Box sx={{ mt: 1 }}>
            <TechDetail label="이 수에 안 들어간 프로젝트가 있습니다">
              {projects.unscored ? (
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
                  아직 상태를 계산하지 않은 프로젝트 {fmtNum(projects.unscored)}건은 이 판정에 들어가지 않았습니다.
                </Typography>
              ) : null}
              {projects.low_confidence ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
                  일부 항목만으로 계산한 프로젝트 {fmtNum(projects.low_confidence)}건이 있어 그만큼은 덜 정확합니다.
                </Typography>
              ) : null}
              {projects.truncated ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
                  프로젝트가 많아 일부만 훑었습니다. 합계가 전체와 다를 수 있습니다.
                </Typography>
              ) : null}
            </TechDetail>
          </Box>
        ) : null}
      </SubGroup>

      <SubGroup title="최근 완료 추이">
        {trend ? (
          <>
            <ProgressRows
              question="주마다 마감을 얼마나 지켰는지 봅니다."
              items={rows}
              revealKey={trendKey}
              emptyLabel="완료 추이를 만들 표본이 없습니다"
              emptyRowLabel="마감 없음"
              formatRow={(r) => `마감 ${fmtNum(r.total)}건 중 ${fmtNum(r.value)}건 완료`}
            />
            {/* 기준은 그림을 의심할 때만 필요하다 — 접어 둔다(지우지는 않는다). */}
            <Box sx={{ mt: 1.25 }}>
              <TechDetail label="집계 기준">
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{TREND_BASIS}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>{TREND_BASIS_LIMIT}</Typography>
              </TechDetail>
            </Box>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{WORK_UNKNOWN}</Typography>
        )}
      </SubGroup>
    </>
  );
}
