import React from "react";
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
 *             `risk`    그 위의 신호(0 이면 서지 않는다 · 글자 값이면 그 글자가 값이다)
 *             `measure` 구성에 들지 않는 측정값 — 카드 아래 정의 목록 한 줄(`notes`)
 *   strip   서로 다른 측정값 — KPI 타일 줄(기본). 둘 이하이면 속성 줄이다(아래)
 *   meta    속성 — 속성 줄(`MetaBar`). `kind` 가 있는 값은 값 옆 배지가 톤을 말한다.
 *
 * 그릇은 값이 있어야 선다(D-501). 측정값이 하나 둘뿐이면 그것만으로 판을 세우지 않는다 — 작업 큐의
 * 「평균 처리 시간」은 상태 카드 옆 반폭 판에 이름만 들고 섰고, AI 사용 상한의 두 판은 「0」 하나씩을
 * 800px 판에 담았다. 누를 수 있거나 경보인 값만 판(칩 · 타일)을 갖고, 나머지는 한 줄로 선다.
 *
 * 카드 정의(`cards(data, ctx)`)는 셋이 같다 — registry 의 숫자 계산과 시험은 그릇과 무관하게 남는다. */

/** 속성 줄로 설 수 있는 측정값의 최대 수. 그보다 많으면 타일 줄이 비교를 돕는다. */
export const STRIP_AS_META_MAX = 2;

function metaItems(cards) {
  return cards.map((c) => ({
    key: c.key,
    label: c.label,
    value: c.kind ? <Badge value={c.value} kind={c.kind} /> : c.value,
  }));
}

export function SummaryView({ summary, data, ctx, sx }) {
  const kind = summary.kind || "strip";
  const cards = ((summary.cards && summary.cards(data, ctx)) || []).filter(Boolean)
    .map((c, i) => ({ ...c, key: c.key || c.label || String(i) }));

  if (kind === "status") {
    const parts = cards.filter((c) => (c.role || "part") === "part");
    const risks = cards.filter((c) => c.role === "risk");
    /* 측정값은 카드 아래 정의 목록 한 줄이다 — 값이 없는 측정값은 줄에도 서지 않는다(「평균 처리 시간」이
       잴 이력이 없을 때). 이름과 값이 한 짝(dt · dd)이라 어느 숫자인지 다시 찾을 필요가 없다. */
    const notes = cards
      .filter((c) => c.role === "measure" && c.value != null && c.value !== "")
      .map((c) => ({ key: c.key, label: c.label, text: String(c.value) }));
    /* 여백은 카드 자신이 든다 — 카드가 설 값이 없어 안 서면(전체 0 · 누를 칩 없음) 여백도 함께 없다. */
    return (
      <StatusSummaryCard
        ariaLabel="요약"
        sx={sx}
        total={summary.total ? summary.total(data) : undefined}
        items={parts}
        risks={risks}
        notes={notes}
      />
    );
  }
  if (kind === "meta" || (kind === "strip" && cards.length <= STRIP_AS_META_MAX && !cards.some((c) => c.onClick))) {
    /* 누를 수 있는 측정값은 타일로 남긴다 — 속성 줄의 값은 단추가 아니라서, 옮기면 그 값으로 목록을 좁히던
       길이 사라진다. */
    return <MetaBar ariaLabel="요약" sx={sx} items={metaItems(cards)} />;
  }
  return <StatusKpiStrip ariaLabel="요약" sx={sx} items={cards} />;
}
