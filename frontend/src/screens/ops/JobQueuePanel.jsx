import React from "react";
import Link from "@mui/material/Link";
import Box from "@mui/material/Box";
import { fmtDateTime, jobTypeKo } from "../../lib/format.js";
import { Badge, DataTable, EmptyState, MetaBar, Section } from "../../ui/kit.jsx";
import { StatusKpiStrip } from "../../ui/StatusKpi.jsx";
import { Sparkline } from "../../ui/charts/Sparkline.jsx";
import { STRIP_AS_META_MAX } from "../data-screen/SummaryView.jsx";
import { fmtNum, fmtProcessingTime } from "./opsHelpers.js";
import { DateCell } from "../../ui/cells.jsx";

/* 최근 24시간에 잰 측정값 셋 — 처리 요청 · 성공률 · 평균 처리. 잴 수 없는 값(종료된 작업이 없어 성공률이 없거나,
 * 처리 이력이 없어 평균이 없을 때)은 `null` 이라 서지 않는다(D-501 · `StatusKpi.jsx`). 「-」 한 글자를 든 판은 값이
 * 없는 그릇이었다.
 *
 * 성공률의 분모는 24시간 내 종료된(성공, 실패, 취소) 작업만이며 아직 끝나지 않은 대기/실행 중 작업은 제외된다
 * (app/health/service.py finished_24h). 라벨을 Dashboard.jsx와 동일하게 맞춰 같은 값이 화면마다 다른 의미로 읽히지
 * 않게 한다. 평균 처리는 raw seconds 대신 Dashboard.jsx의 fmtProcessingTime()을 그대로 쓴다. */
export function jobMeasures(jobs24) {
  const j = jobs24 || {};
  const rate = j.success_rate_pct;
  return [
    j.total != null ? { key: "total", value: fmtNum(j.total), label: "처리 요청", primary: true } : null,
    rate != null ? {
      key: "rate", value: rate + "%", label: "성공률(종료된 작업 기준)",
      kind: rate >= 95 ? "ok" : rate >= 80 ? "warn" : "danger",
    } : null,
    j.avg_processing_seconds != null
      ? { key: "avg", value: fmtProcessingTime(j.avg_processing_seconds), label: "평균 처리 시간" }
      : null,
  ].filter(Boolean);
}

/* 진단 화면의 "작업 지표 (최근 24시간)" + "최근 작업 오류" — 둘 다 작업 큐 관련 신호라 한 패널로
 * 묶는다. errorDist는 부모(Diagnostics)가 errorBuckets()로 미리 계산해 전달한다(순수 계산이라
 * 이 패널의 관심사가 아니다). */
export function JobQueuePanel({ jobs24, jobErrors, errorDist, nav }) {
  const measures = jobMeasures(jobs24);
  return (
    <>
      {measures.length ? (
        <Section titleAs="h2" title="작업 지표 (최근 24시간)">
          {/* 이 줄은 **24시간 창**의 측정만 든다. 여기 「대기 중(전체)」 · 「미해결 실패(전체)」 타일이 있었는데 둘은 24시간이
              아니라 시점 백로그 누계라(백엔드가 시간 필터 없이 센다) 제목의 창과 맞지 않았고, 같은 수가 맨 위 판정 목록에도
              섰다. 백로그는 그 판정 목록 한 곳이 말하고, 그 줄에서 상태로 거른 작업 큐로 간다(`opsHelpers.js::healthVerdict`).
              측정이 둘 이하이면 판 대신 속성 줄이다(D-501 · `SummaryView.jsx` 의 같은 규칙) — 한가한 설치의 「0 처리 요청」
              한 칸이 판 하나를 차지하지 않는다. */}
          {measures.length <= STRIP_AS_META_MAX ? (
            <MetaBar
              ariaLabel="작업 지표"
              items={measures.map((it) => ({
                key: it.key,
                label: it.label,
                value: it.kind ? <Badge value={it.value} kind={it.kind} /> : it.value,
              }))}
            />
          ) : (
            <StatusKpiStrip ariaLabel="작업 지표" items={measures} />
          )}
        </Section>
      ) : null}
      {/* 이력 목록은 판 없이 괘선 구획이다 — 대시보드의 「최근 주요 변경」·진단의 「설치처 설정」과
          같은 어휘. 예전에는 이 목록만 흰 판 안에 있어 같은 화면에서 표면이 하나 더 있었다. */}
      <Section titleAs="h2" title="최근 작업 오류" rule
        action={<Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/jobs")}>작업 큐에서 보기 →</Link>}>
          {jobErrors.length ? (
            <>
              {/* 20건이 한 시간에 몰렸는지 두 달에 흩어져 있는지는 목록만 훑어서는 안 보인다.
                  errorBuckets()가 3건 미만·같은 순간이면 null을 주므로, 없는 추세를 그리지 않는다. */}
              {errorDist ? (
                <Box sx={{ mb: 2.5 }}>
                  <Sparkline
                    question="실패가 한 순간에 몰렸는지 오래 흩어져 있는지 봅니다."
                    points={errorDist.counts} color="error" height="3.5rem"
                    summary={"최근 실패 " + errorDist.n + "건의 발생 분포, "
                      + fmtDateTime(new Date(errorDist.from).toISOString()) + " ~ "
                      + fmtDateTime(new Date(errorDist.to).toISOString())
                      + " (전체 실패 추세가 아니라 이 목록에 담긴 건들의 분포입니다)"} />
                </Box>
              ) : null}
              {/* 시각 · 내용 · 작업 종류 세 열은 표다 — 손으로 짠 줄 격자(`LogList`)가 열 정렬 · 머리 · 좁은
                  화면 접기를 따로 가졌다(계획 B-5). 이 목록은 60초마다 자동 재수집돼 순서가 바뀔 수 있어
                  index 대신 안정적인 합성 키를 쓴다(잡 id가 번들에 없어 시각+타입+인덱스로 최대한 안정화). */}
              {/* 목록 판 — 판이 곧 표 상자다(조합 계약 C-3). 최근 몇 건의 미리보기라 발에 건수를 세우지 않는다(「작업 큐에서
                  보기」가 전체로 넘긴다). */}
              <DataTable
                placement="surface"
                list={false}
                columns={[
                  { key: "at", label: "시각", type: "datetime", render: (e) => <DateCell value={e.at} /> },
                  { key: "error", label: "오류", type: "title", render: (e) => e.error || "-" },
                  /* 원시 영어 enum(chat_message 등)이 한글 콘솔에 새지 않게 한국어로 변환(미매핑은 원값 폴백). */
                  { key: "job_type", label: "작업", type: "enum", render: (e) => jobTypeKo(e.job_type) },
                ]}
                rows={jobErrors.map((e, i) => ({ ...e, rowId: e.at + "|" + e.job_type + "|" + i }))}
                rowKey={(e) => e.rowId}
              />
            </>
          ) : <EmptyState layout="inline" title="최근 실패한 작업이 없습니다." />}
      </Section>
    </>
  );
}
