import React from "react";
import Box from "@mui/material/Box";
import { Badge, MetaBar } from "../../ui/kit.jsx";
import { StatusKpiStrip, StatusSummaryCard } from "../../ui/StatusKpi.jsx";

/* 목록 화면 요약 — **데이터의 뜻이 그릇을 정한다** (계획 표 7 · 핸드오프 README §7 · RULES §10).
 *
 * 예전에는 registry 의 요약이 무엇이든 판독 줄(`MetricStrip`) 하나에 담겼다. 합이 전체인 상태 구성,
 * 서로 다른 측정값, 백업 일정 같은 속성이 같은 모양으로 서서 「무엇이 무엇의 부분인가」가 사라졌다.
 * registry 가 `summary.kind` 로 뜻을 말한다:
 *
 *   status  상태 구성 — 상태 요약 카드 하나. 카드마다 `role` 을 준다:
 *             `part`    전체를 나눈 부분(상태 칩)
 *             `risk`    그 위의 신호(0 이면 서지 않는다)
 *             `measure` 구성에 들지 않는 측정값(아래 KPI 타일 줄)
 *   strip   서로 다른 측정값 — KPI 타일 줄(기본)
 *   meta    속성 — 속성 줄(`MetaBar`). `kind` 가 있는 값은 값 옆 배지가 톤을 말한다.
 *
 * 카드 정의(`cards(data, ctx)`)는 셋이 같다 — registry 의 숫자 계산과 시험은 그릇과 무관하게 남는다. */
export function SummaryView({ summary, data, ctx, sx }) {
  const kind = summary.kind || "strip";
  const cards = ((summary.cards && summary.cards(data, ctx)) || []).filter(Boolean)
    .map((c, i) => ({ ...c, key: c.key || c.label || String(i) }));

  if (kind === "status") {
    const parts = cards.filter((c) => (c.role || "part") === "part");
    const risks = cards.filter((c) => c.role === "risk");
    const measures = cards.filter((c) => c.role === "measure");
    return (
      <Box sx={{ display: "grid", gap: 1.5, ...sx }}>
        <StatusSummaryCard
          ariaLabel="요약"
          total={summary.total ? summary.total(data) : undefined}
          items={parts}
          risks={risks}
        />
        {measures.length ? <StatusKpiStrip ariaLabel="요약 측정값" items={measures} /> : null}
      </Box>
    );
  }
  if (kind === "meta") {
    return (
      <MetaBar
        ariaLabel="요약"
        sx={sx}
        items={cards.map((c) => ({
          key: c.key,
          label: c.label,
          value: c.kind ? <Badge value={c.value} kind={c.kind} /> : c.value,
        }))}
      />
    );
  }
  return <StatusKpiStrip ariaLabel="요약" sx={sx} items={cards} />;
}
