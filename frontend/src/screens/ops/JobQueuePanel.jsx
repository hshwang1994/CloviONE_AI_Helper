import React from "react";
import Link from "@mui/material/Link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime, jobTypeKo } from "../../lib/format.js";
import { Card, StatCard } from "../../ui/kit.jsx";
import { Sparkline } from "../../ui/charts/Sparkline.jsx";
import { fmtNum, fmtProcessingTime, DashSection, Note, STAT_GRID } from "../Dashboard.jsx";
import { LogRow, LogList } from "./LogList.jsx";

/* 진단 화면의 "작업 지표 (최근 24시간)" + "최근 작업 오류" — 둘 다 작업 큐 관련 신호라 한 패널로
 * 묶는다. errorDist는 부모(Diagnostics)가 errorBuckets()로 미리 계산해 전달한다(순수 계산이라
 * 이 패널의 관심사가 아니다). */
export function JobQueuePanel({ jobs24, jobErrors, errorDist, nav }) {
  return (
    <>
      {Object.keys(jobs24).length ? (
        <DashSection title="작업 지표 (최근 24시간)">
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
            <StatCard value={fmtNum(jobs24.total)} label="처리 요청" />
            {/* Dashboard.jsx와 같은 지표, 분모는 24시간 내 종료된(성공, 실패, 취소) 작업만이며 아직
                끝나지 않은 대기/실행 중 작업은 제외된다(app/health/service.py finished_24h). 라벨을
                Dashboard.jsx와 동일하게 맞춰 같은 값이 화면마다 다른 의미로 읽히지 않게 한다. */}
            <StatCard value={jobs24.success_rate_pct != null ? jobs24.success_rate_pct + "%" : "-"} label="성공률(종료 작업 대비)"
              kind={jobs24.success_rate_pct == null ? undefined : jobs24.success_rate_pct >= 95 ? "ok" : jobs24.success_rate_pct >= 80 ? "warn" : "danger"} />
            {/* raw seconds 대신 Dashboard.jsx의 fmtProcessingTime()을 그대로 재사용한다, 큰 초 값이
                굵은 KPI 타일에서 스캔하기 어렵다는 이유로 Dashboard.jsx가 이미 고친 문제를 이
                화면만 다시 겪고 있었다(같은 필드 avg_processing_seconds). */}
            <StatCard value={fmtProcessingTime(jobs24.avg_processing_seconds)} label="평균 처리" />
            {/* queued/failed_open은 24시간 창이 아니라 시점 백로그 누계다(백엔드가 시간 필터 없이 계산).
                '24시간' 프레임과 섞여 오래된 백로그가 오늘 실패처럼 읽히던 문제, 라벨에 '(전체)'를 붙여 구분한다.
                Dashboard의 동일 타일처럼 /jobs로 드릴다운해, 문제를 보여주기만 하고 조치할 곳이 없던 막다른
                타일을 없앤다(이 화면은 admin/system_admin 전용이라 /jobs는 항상 도달 가능). */}
            <StatCard value={fmtNum(jobs24.queued != null ? jobs24.queued : 0)} label="대기 중(전체)"
              kind={jobs24.queued > 0 ? "warn" : undefined} onClick={() => nav("/jobs")} />
            <StatCard value={fmtNum(jobs24.failed_open != null ? jobs24.failed_open : 0)} label="미해결 실패(전체)"
              kind={jobs24.failed_open > 0 ? "danger" : undefined} onClick={() => nav("/jobs")} />
          </Box>
        </DashSection>
      ) : null}
      <DashSection title="최근 작업 오류"
        action={<Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/jobs")}>작업 큐에서 보기 →</Link>}>
        <Card>
          {jobErrors.length ? (
            <>
              {/* 20건이 한 시간에 몰렸는지 두 달에 흩어져 있는지는 목록만 훑어서는 안 보인다.
                  errorBuckets()가 3건 미만·같은 순간이면 null을 주므로, 없는 추세를 그리지 않는다. */}
              {errorDist ? (
                <Box sx={{ mb: 2.5 }}>
                  <Sparkline
                    points={errorDist.counts} color="error" height="3.5rem"
                    summary={"최근 실패 " + errorDist.n + "건의 발생 분포, "
                      + fmtDateTime(new Date(errorDist.from).toISOString()) + " ~ "
                      + fmtDateTime(new Date(errorDist.to).toISOString())
                      + " (전체 실패 추세가 아니라 이 목록에 담긴 건들의 분포입니다)"} />
                </Box>
              ) : null}
              <LogList>
                {/* 이 목록은 60초마다 자동 재수집돼 순서가 바뀔 수 있다 — '최근 주요 변경' 목록과 같은
                    이유로 index 대신 안정적인 합성 키를 쓴다(잡 id가 번들에 없어 시각+타입+인덱스로
                    최대한 안정화). */}
                {jobErrors.map((e, i) => (
                  <LogRow key={e.at + "|" + e.job_type + "|" + i} when={fmtDateTime(e.at)} what={e.error || "-"}>
                    {/* 원시 영어 enum(chat_message 등)이 한글 콘솔에 새지 않게 한국어로 변환(미매핑은 원값 폴백). */}
                    <Typography variant="body2" color="text.secondary">{jobTypeKo(e.job_type)}</Typography>
                  </LogRow>
                ))}
              </LogList>
            </>
          ) : <Note sx={{ mt: 0 }}>최근 실패한 작업이 없습니다.</Note>}
        </Card>
      </DashSection>
    </>
  );
}
