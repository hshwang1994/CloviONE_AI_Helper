import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { priorityKo } from "../lib/priority.js";
import {
  Callout, Card, DataTable, EmptyState, ErrorState, PageHeader, SectionTitle, Segmented, Skeleton,
} from "../ui/kit.jsx";
import { StatusSummaryCard } from "../ui/StatusKpi.jsx";
import { FONT_WEIGHT, NUMERIC } from "../ui/theme.js";
import { GRID_GAP } from "../ui/density.js";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { Donut } from "../ui/charts/Donut.jsx";
import { Gauge } from "../ui/charts/Gauge.jsx";

/* 내 업무량 · 완료 통계 (계획서 Phase 6 사용자).
 *
 * 숫자는 전부 서버가 만든다(GET /api/me/stats). 화면에서 다시 집계하지 않는 이유는
 * 두 곳에서 세면 언젠가 서로 다른 말을 하기 때문이다 — 홈의 '지연 3건'과 여기의 '지연 5건'이
 * 어긋나는 순간 사용자는 둘 다 안 믿는다.
 *
 * **'완료'는 마감일 기준이다.** 소스에 완료 시각이 없어서(app/profiles/stats.py 모듈
 * docstring) '6월 완료'는 '마감이 6월인 티켓 중 완료 상태'라는 뜻이다. 화면에도 그렇게 쓴다 —
 * 숨기면 6월에 끝낸 7월 마감 일이 왜 안 세지는지 아무도 모른다.
 *
 * MUI Grid 를 쓰지 않는다(MUI 7 에서 xs={12} 가 조용히 무시된다). px 폰트 크기도 쓰지 않는다.
 */


/* 판끼리의 간격은 `GRID_GAP`(24px) 하나다 — 가로 이음매를 그것으로 그리면서
   세로만 20px 로 두면 한 화면에서 두 값이 나란히 보인다. */
const BODY_GRID = {
  display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    lg: "minmax(0, 2fr) minmax(0, 1fr)",
    xxl: "minmax(0, 3fr) minmax(0, 1fr)",
  },
};

const MONTH_OPTIONS = [3, 6, 12];

// 티켓 미러 동기화 상태(app/tickets/models.py SYNC_IDLE/RUNNING/OK/ERROR) → 한국어.
// 매핑에 없는 값이 오면(새 상태 추가 등) 원시 영문 대신 '확인 필요'로 뭉뚱그린다(Home.jsx와 동일 원칙).

function pct(rate) {
  return rate == null ? "-" : Math.round(rate * 100) + "%";
}

/* SectionTitle(ui/kit.jsx)로 옮겨졌다(DS-07). */

/* 티켓 소스가 왜 비었는지 — 0건과 '못 읽었다'는 다른 말이다. */
function SourceNotice({ source }) {
  if (!source) return null;
  if (source.configured === false) {
    return (
      <Callout tone="warn">
        {source.message || "티켓 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요."}
      </Callout>
    );
  }
  if (source.ok === false) {
    return (
      <Callout tone="warn">
        {source.error || "티켓을 불러오지 못했습니다. 아래 숫자는 비어 있을 수 있습니다. 새로고침해 보세요."}
      </Callout>
    );
  }
  /* 여기 「내 계정이 Notion 사용자와 연결되어 있지 않습니다」 갈래가 있었다 (S15).
     그 상태는 없어졌다 — 사람마다 담당자로 가리킬 값이 언제나 있다(D-285). 그리고 그
     안내가 시키던 절차(관리자에게 연결 요청)는 아무도 수행할 수 없다. */
  return null;
}

export function MyStats() {
  const [months, setMonths] = React.useState(6);
  const q = useQuery({
    queryKey: ["my-stats", months],
    queryFn: () => api(`/api/me/stats?months=${months}&weeks=4`),
    retry: false,
  });

  const data = q.data;
  // PA-RC-0027: 소스를 못 읽었거나 매핑이 없으면 백엔드가 totals/workload를 아예
  // 안 싣는다 — `{}`로 기본값을 줘야 아래 totals.active 등이 undefined로 안전하게
  // 평가된다(판독 칸이 이미 null/undefined 둘 다 '-'로 그린다).
  const totals = (data && data.totals) || {};
  const load = (data && data.workload) || {};
  const source = data && data.source;

  return (
    <div className="c-screen">
      <PageHeader
        area="내 정보"
        title="내 업무량, 완료 통계"
        crumbRoot=""

        /* 기간은 **세그먼티드**다(확정 규약 §2). 셋뿐이고 서로 배타적이라, 열어서 고르는
           셀렉트보다 세 값이 한눈에 보이는 편이 낫다 — 지금 무엇을 보고 있는지가 목록을
           열지 않아도 읽힌다. */
        actions={
          <Segmented
            ariaLabel="기간"
            value={months}
            onChange={setMonths}
            options={MONTH_OPTIONS.map((m) => ({ value: m, label: `최근 ${m}개월` }))}
          />
        }
      />

      {q.isLoading ? (
        <Card><Skeleton kind="chart" /></Card>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <SourceNotice source={data.source} />

          {/* 요약 카드 하나 — 예전에는 흰 카드 여섯 장이 같은 무게로 깔려서 「남은 일 3」과
              「완료 128」이 같은 크기로 읽혔고, 그 뒤 한 줄로 모았지만 여섯 칸이 여전히
              나란한 무게였다. 지금은 전체 하나가 크게 서고 나머지는 그 아래 칩이다.

              🔴 **무엇이 부분이고 무엇이 신호인가를 가른다.** 완료·남은 일·취소 셋은 전체
              티켓을 남김없이 나눈 부분이라 스택 바와 비율이 참이다. 지연·오늘 마감·막힌
              일은 그렇지 않다 — 남은 일의 **부분집합이면서 서로 겹친다**(한 티켓이 지연이면서
              막힌 일일 수 있다). 그 셋을 같은 바에 넣으면 합이 전체를 넘는다. 그래서 위험
              요약으로 카드 머리 오른쪽에 선다. */}
          <StatusSummaryCard
            ariaLabel="내 업무량"
            sx={{ mb: 2.5 }}
            total={totals.all}
            totalLabel={`최근 ${months}개월 내 티켓`}
            items={[
              { key: "done", value: totals.done, label: "완료", kind: "ok" },
              { key: "active", value: totals.active, label: "남은 일" },
              { key: "cancelled", value: totals.cancelled, label: "취소" },
            ]}
            risks={[
              { key: "overdue", value: totals.overdue, label: "지연", kind: "danger" },
              { key: "due_today", value: totals.due_today, label: "오늘 마감", kind: "warn" },
              // 「막힘(이슈)」였다. 괄호 안이 옛 티켓 **상태값**인데 `이슈` 는 더 이상 상태가
              // 아니고(D-349), 이 숫자는 「이슈 있음이거나 차단됨」을 센다. 홈 화면이 같은
              // 묶음을 이미 「막힌 일」로 부른다(`Home.jsx`) — 같은 수를 두 이름으로 부르지 않는다.
              { key: "blocked", value: totals.blocked, label: "막힌 일", kind: "danger" },
            ]}
            action={
              /* 완료율은 **취소를 뺀** 분모라 위 스택 바의 비율과 다른 수다. 그래서 바 옆이
                 아니라 자기 그림을 갖는다 — 같은 자리에 두면 98% 와 92% 가 왜 다른지 물을
                 자리가 없다. 이름을 링 아래에 그대로 붙여 그 차이를 말한다. */
              <Gauge
                value={totals.completion_rate == null ? null : Math.round(totals.completion_rate * 100)}
                size="4.5rem"
                thickness={12}
                color="ok"
                centerText={pct(totals.completion_rate)}
                label="완료율(취소 제외)"
                emptyLabel="아직 잴 수 없습니다"
              />
            }
          />

          {/* PA-RC-0027: `totals.all`이 티켓을 못 읽었을 때 0이 아니라 undefined다
              (totals={}) — `=== 0`만 보면 이 경우 아래 차트 분기로 빠져 load.by_week 등
              없는 값에 접근해 죽는다. `!totals.all`은 두 경우를 같은 EmptyState 로 보내고,
              「왜 모르는가」는 위 SourceNotice 배너가 말한다.
              0건의 이유는 이제 하나다 — 담당인 티켓이 없다. 「계정이 연결되지 않았다」는
              갈래는 그 상태 자체가 없어져 함께 걷었다(S15 · D-285). */}
          {!totals.all ? (
            <Card>
              <EmptyState
                art="tickets"
                title="아직 집계할 티켓이 없습니다"
                situation="내가 담당인 티켓이 하나도 없어서 그릴 숫자가 없습니다."
                help="티켓을 맡거나 새로 만들면 여기에 업무량과 완료 추이가 쌓입니다."
                relatedLink={{ href: "#/my-tickets", label: "내 티켓으로" }}
              />
            </Card>
          ) : (
            <Box sx={BODY_GRID}>
              <Box sx={{ display: "grid", gap: GRID_GAP, minWidth: 0 }}>
                <Card>
                  {/* SEM-02: MyStats는 단독 라우트(/my-stats)라 PageHeader가 h1이고, 이 화면의
                      SectionTitle 5개가 전부 그 h1 바로 아래다 — h2를 명시한다. */}
                  <SectionTitle
                    component="h2"
                    title="달별 완료 추이"
                    help="마감일이 그 달인 티켓 기준입니다. 완료율의 분모에서 취소는 뺍니다."
                  />
                  {/* 🔴 선이 아니라 **막대**다.
                      선은 점과 점 사이를 이어 「그 사이에도 값이 있었다」고 말한다. 그런데
                      배정이 0건인 달의 완료율은 `null` 이지 0% 가 아니고, 선은 숫자만 그릴 수
                      있어 그 달을 0 으로 눕혔다 — 「일이 없었던 달」이 「하나도 못 끝낸 달」로
                      보였고, 그 거짓을 아래 표의 '-' 가 뒤늦게 정정했다. 막대는 달마다 따로
                      서므로 그 달 하나만 「배정 없음」이라고 말하고 옆 달에 선을 긋지 않는다.
                      기준을 100 으로 못박아 「가장 큰 값이 꽉 찬 막대」가 되지 않게 한다 —
                      완료율은 서로 비교할 값이 아니라 그 자체가 절대값이다. */}
                  <BarSeries
                    question="달마다 완료율이 어떠했는지 봅니다. 배정이 없던 달은 값이 «-» 이고, 그 달의 정확한 건수는 아래 표가 답합니다."
                    items={data.months.map((m) => (m.completion_rate == null
                      ? { label: m.month.slice(2), value: 0, color: "neutral", valueText: "-" }
                      : { label: m.month.slice(2), value: Math.round(m.completion_rate * 100) }))}
                    max={100}
                    unit="%"
                    emptyLabel="집계할 달이 없습니다"
                  />
                  <Box sx={{ mt: 2, minWidth: 0 }}>
                    <DataTable
                      columns={[
                        /* 달은 이 표에서 **행을 가리키는 이름**이다 — 표당 하나뿐인
                           `title` 자리라 몸통에서 홀로 왼쪽에 선다(D-471). 폭은 값이
                           「26-08」로 고정 길이라 남는 폭을 먹지 않게 못박는다. */
                        { key: "month", label: "달", type: "title", width: "6.5rem" },
                        { key: "assigned", label: "배정", type: "count" },
                        { key: "doneCell", label: "완료", type: "count" },
                        { key: "cancelled", label: "취소", type: "count" },
                        { key: "openCell", label: "진행", type: "count" },
                        { key: "rate", label: "완료율", type: "percent" },
                        { key: "wd", label: "예상/실제 WD", type: "number" },
                      ]}
                      rows={data.months.map((m) => ({
                        ...m,
                        doneCell: m.done,
                        openCell: m.open,
                        rate: pct(m.completion_rate),
                        wd: `${m.est_wd} / ${m.act_wd}`,
                      }))}
                      rowKey={(r) => r.month}
                      empty="집계할 달이 없습니다"
                    />
                  </Box>
                </Card>

                <Card>
                  <SectionTitle
                    component="h2"
                    title="앞으로의 부하(주별)"
                    help="아직 끝나지 않은 티켓만 셉니다. 끝난 일은 부하가 아닙니다."
                  />
                  <BarSeries
                    question="다음 몇 주 가운데 어느 주에 일이 몰려 있는지 봅니다."
                    items={[
                      ...load.by_week.map((w) => ({
                        label: w.label, value: w.count, note: `${w.start}~`,
                      })),
                      { label: "그 이후", value: load.by_week_extra.later.count, color: "neutral" },
                      { label: "지난 마감", value: load.by_week_extra.overdue.count, color: "error" },
                      { label: "마감 없음", value: load.by_week_extra.no_due.count, color: "neutral" },
                    ]}
                    unit="건"
                    emptyLabel="남은 일이 없습니다"
                  />
                </Card>
              </Box>

              <Box sx={{ display: "grid", gap: GRID_GAP, minWidth: 0 }}>
                <Card>
                  <SectionTitle component="h2" title="상태 구성" />
                  <Donut
                    question="남은 일이 어느 상태에 걸려 있는지 봅니다."
                    segments={load.by_status.map((s) => ({
                      label: s.name,
                      value: s.count,
                      color: s.name === "완료" ? "success" : s.name === "이슈" ? "error" : undefined,
                    }))}
                    unit="건"
                    centerLabel="티켓"
                    emptyLabel="티켓이 없습니다"
                  />
                </Card>
                <Card>
                  <SectionTitle component="h2" title="남은 일의 우선순위" />
                  <BarSeries
                    question="먼저 손대야 할 일이 얼마나 쌓였는지 봅니다."
                    /* 이름을 **한국어로** 옮긴다. 서버가 주는 값은 원시 등급명(High·Normal)
                       이라 그대로 그리면 이 화면만 영문이 된다 — 티켓 목록과 상세는 이미
                       `priorityKo` 를 지난다. 같은 값이 화면마다 다른 낱말로 보이면 안 된다. */
                    items={load.by_priority.map((p) => ({ label: priorityKo(p.name), value: p.count }))}
                    unit="건"
                    emptyLabel="남은 일이 없습니다"
                  />
                </Card>
                <Card>
                  <SectionTitle component="h2" title="공수(WD)" help="예상 공수는 남은 일 기준, 실제 공수는 완료한 일 기준입니다." />
                  <Box sx={{ display: "grid", gap: 1 }}>
                    {[
                      ["남은 예상 공수", load.est_wd_active],
                      ["그중 지연분", load.est_wd_overdue],
                      ["완료한 일의 예상 공수", load.est_wd_done],
                      ["완료한 일의 실제 공수", load.act_wd_done],
                    ].map(([label, value]) => (
                      /* 판 **안쪽**을 나누는 실선은 판을 두르는 선보다 한 단 여리다(`rule`).
                         값은 자릿수를 고정해 네 줄이 세로로 맞선다. */
                      <Box
                        key={label}
                        sx={{
                          display: "flex", justifyContent: "space-between", gap: 2, py: 0.75,
                          borderBottom: 1,
                          borderColor: (t) => t.palette.rule,
                          "&:last-of-type": { borderBottom: 0 },
                        }}
                      >
                        <Typography variant="body2" color="text.secondary">{label}</Typography>
                        <Typography sx={{ fontWeight: FONT_WEIGHT.bold, ...NUMERIC }}>{value} WD</Typography>
                      </Box>
                    ))}
                  </Box>
                </Card>
              </Box>
            </Box>
          )}

          {/* 여기 미러 신선도 안내가 있었다. 서버가 `sync` 블록을 더 이상 안 싣는다 —
              티켓 표가 이 서버의 정본이라 낡을 것이 없다(S14). */}
        </>
      )}
    </div>
  );
}

export default MyStats;
