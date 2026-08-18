import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import {
  Callout, Card, DataTable, EmptyState, ErrorState, MetricStrip, PageHeader, SectionTitle, Skeleton,
} from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { Donut } from "../ui/charts/Donut.jsx";
import { LineSeries } from "../ui/charts/LineSeries.jsx";

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


const BODY_GRID = {
  display: "grid", gap: 2.5, alignItems: "start",
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    lg: "minmax(0, 2fr) minmax(0, 1fr)",
    xxl: "minmax(0, 3fr) minmax(0, 1fr)",
  },
};

const MONTH_OPTIONS = [3, 6, 12];

// 티켓 미러 동기화 상태(app/tickets/models.py SYNC_IDLE/RUNNING/OK/ERROR) → 한국어.
// 매핑에 없는 값이 오면(새 상태 추가 등) 원시 영문 대신 '확인 필요'로 뭉뚱그린다(Home.jsx와 동일 원칙).
const SYNC_STATUS_KO = { idle: "대기", running: "동기화 중", ok: "정상", error: "오류" };

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
  if (source.mapped === false) {
    return (
      <Callout tone="warn">
        내 계정이 Notion 사용자와 연결되어 있지 않아 담당 티켓을 찾을 수 없습니다.
        관리자에게 계정 연결을 요청하세요.
      </Callout>
    );
  }
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
        spot="sprint"
        actions={
          <TextField
            select size="small" label="기간"
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: "8rem" }}
          >
            {MONTH_OPTIONS.map((m) => <MenuItem key={m} value={m}>{`최근 ${m}개월`}</MenuItem>)}
          </TextField>
        }
      />

      {q.isLoading ? (
        <Card><Skeleton lines={8} /></Card>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <SourceNotice source={data.source} />

          {/* 예전에는 흰 카드 여섯 장이 같은 무게로 깔려서 "남은 일 3"과 "완료 128"이 같은
              크기로 읽혔다. 한 줄에 모으고 핵심('남은 일')만 큰 글자로 둔다 (지시 2).
              둘로 가르는 안도 만들어 봤으나 뒷줄이 둘뿐이라 판 하나가 숫자 두 개를 위해
              화면 폭을 다 쓰게 돼서, 남은 일부터 완료까지 한 줄로 읽는 쪽을 골랐다. */}
          <MetricStrip
            ariaLabel="내 업무량"
            sx={{ mb: 2.5 }}
            items={[
              { key: "active", value: totals.active, label: "남은 일", primary: true },
              { key: "overdue", value: totals.overdue, label: "지연", kind: totals.overdue > 0 ? "danger" : undefined },
              { key: "due_today", value: totals.due_today, label: "오늘 마감", kind: totals.due_today > 0 ? "warn" : undefined },
              { key: "blocked", value: totals.blocked, label: "막힘(이슈)", kind: totals.blocked > 0 ? "danger" : undefined },
              { key: "done", value: totals.done, label: "완료", kind: "ok" },
              { key: "rate", value: pct(totals.completion_rate), label: "완료율(취소 제외)" },
            ]}
          />

          {/* PA-RC-0027: `totals.all`이 이제 소스를 못 읽었을 때 0이 아니라 undefined다
              (totals={}) — `=== 0`만 보면 이 경우 아래 차트 분기로 빠져 load.by_week 등
              없는 값에 접근해 죽는다. `!totals.all`은 "0건"과 "모른다"를 같은 EmptyState
              분기로 보내고, 그 안의 source.mapped 체크가 둘을 다시 정확히 갈라 말한다. */}
          {!totals.all ? (
            <Card>
              {/* WF1 R4 — 계정이 Notion과 안 연결된 사람은 위 SourceNotice("관리자에게 계정
                  연결을 요청하세요")와 여기 아래 EmptyState가 **서로 다른 원인**을 말했다
                  ("담당 티켓이 하나도 없어서") — 게다가 그 CTA("내 티켓으로")가 데려가는
                  /my-tickets도 같은 원인(연결 안 됨)으로 똑같이 비어 있어 막다른 길이었다.
                  진단이 이미 위 배너에 있으니 여기서 반복하거나 못 고치는 CTA를 주지 않는다. */}
              {source && source.mapped === false ? (
                <EmptyState
                  art="tickets"
                  title="아직 집계할 티켓이 없습니다"
                  situation="계정이 Notion 사용자와 아직 연결되지 않아 담당 티켓을 알 수 없습니다."
                  help="위 안내대로 관리자에게 계정 연결을 요청하세요. 연결되면 그때부터 여기에 업무량과 완료 추이가 쌓입니다."
                />
              ) : (
                <EmptyState
                  art="tickets"
                  title="아직 집계할 티켓이 없습니다"
                  situation="내가 담당인 티켓이 하나도 없어서 그릴 숫자가 없습니다."
                  help="티켓을 맡거나 새로 만들면 여기에 업무량과 완료 추이가 쌓입니다."
                  relatedLink={{ href: "#/my-tickets", label: "내 티켓으로" }}
                />
              )}
            </Card>
          ) : (
            <Box sx={BODY_GRID}>
              <Box sx={{ display: "grid", gap: 2.5, minWidth: 0 }}>
                <Card>
                  {/* SEM-02: MyStats는 단독 라우트(/my-stats)라 PageHeader가 h1이고, 이 화면의
                      SectionTitle 5개가 전부 그 h1 바로 아래다 — h2를 명시한다. */}
                  <SectionTitle
                    component="h2"
                    title="달별 완료 추이"
                    help="마감일이 그 달인 티켓 기준입니다. 완료율의 분모에서 취소는 뺍니다."
                  />
                  {/* 배정이 0건인 달의 완료율은 `null` 이다(0% 가 아니다). 선은 숫자만 그릴 수
                      있으므로 0으로 눕히되, 아래 표가 같은 달을 '-' 로 보여 준다 — 그림과 표가
                      함께 있어야 "일이 없었던 달"과 "하나도 못 끝낸 달"이 구분된다. */}
                  {/* 완료율 한 선만 그린다. 건수(0~10)와 백분율(0~100)은 단위가 달라
                      같은 눈금에 겹치면 건수 선이 바닥에 눌려 붙어 아무 정보도 주지 않는다.
                      건수는 바로 아래 표가 정확히 말한다. */}
                  <LineSeries
                    series={[{
                      label: "완료율(%)",
                      points: data.months.map((m) => (m.completion_rate == null ? 0 : Math.round(m.completion_rate * 100))),
                    }]}
                    labels={data.months.map((m) => m.month.slice(2))}
                    unit="%"
                    summary={`최근 ${data.months.length}개월, 배정이 없던 달은 0으로 눕습니다(표에서는 '-')`}
                    emptyLabel="집계할 달이 없습니다"
                  />
                  <Box sx={{ mt: 2, minWidth: 0 }}>
                    <DataTable
                      columns={[
                        { key: "month", label: "달" },
                        { key: "assigned", label: "배정", align: "right" },
                        { key: "doneCell", label: "완료", align: "right" },
                        { key: "cancelled", label: "취소", align: "right" },
                        { key: "openCell", label: "진행", align: "right" },
                        { key: "rate", label: "완료율", align: "right" },
                        { key: "wd", label: "예상/실제 WD", align: "right" },
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

              <Box sx={{ display: "grid", gap: 2.5, minWidth: 0 }}>
                <Card>
                  <SectionTitle component="h2" title="상태 구성" />
                  <Donut
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
                    items={load.by_priority.map((p) => ({ label: p.name, value: p.count }))}
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
                      <Box key={label} sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 0.75, borderBottom: 1, borderColor: "divider" }}>
                        <Typography variant="body2" color="text.secondary">{label}</Typography>
                        <Typography sx={{ fontWeight: FONT_WEIGHT.bold }}>{value} WD</Typography>
                      </Box>
                    ))}
                  </Box>
                </Card>
              </Box>
            </Box>
          )}

          {data.sync ? (
            /* 원시 ISO 문자열을 그대로 두면 '2026-08-03T12:01:32.434817' 이 나온다 —
               이 앱의 표시 규약은 Asia/Seoul 로 포맷한 시각이다(lib/format.js).
               상태값도 원시 영문(idle/running/ok/error, app/tickets/models.py SYNC_*)을 그대로
               내면 안 된다 — Home.jsx·TeamDocs.jsx가 이미 같은 sync.status를 한국어로 옮긴다. */
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2.5 }}>
              티켓 미러 상태: {SYNC_STATUS_KO[data.sync.status] || "확인 필요"}
              {data.sync.last_success_at ? `, 마지막 동기화 ${fmtDateTime(data.sync.last_success_at)}` : ""}
              {data.sync.truncated ? ", 일부만 동기화됨" : ""}
            </Typography>
          ) : null}
        </>
      )}
    </div>
  );
}

export default MyStats;
