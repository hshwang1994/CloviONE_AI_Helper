import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { paletteAt, TONE_ACCENT } from "./kit.jsx";
import { StatusKpiTile } from "./StatusKpi.jsx";
import { DiscussBucket } from "./DiscussBucket.jsx";
import { SIGNALS, SIGNAL_ORDER } from "../lib/ticketSignals.js";

/* 같은 신호는 **제품 전체에서 같은 말과 같은 색**이다 (D-349 · `docs/ui-redesign/PLAN.md` 묶음 A).
 *
 * 🔴 그렇지 않았다. 어휘 표는 `lib/ticketSignals.js` 하나인데 작업 보드와 회의 화면이 각자
 * 이름과 색을 **다시 적어** 뒀다. 결과로 한 화면 안에서 같은 티켓의 「이슈 있음」이 목록에서는
 * 보라, 위 KPI 타일에서는 주황이었고, 지연과 차단은 타일에서 둘 다 빨강이라 서로 구분되지도
 * 않았다. 어휘가 두 벌이면 한쪽만 고쳐지고, 그 어긋남은 아무 오류도 안 낸다.
 *
 * qa-contract-change: KPI 타일이 톤을 나르는 자리가 3px 위색 띠에서 라벨 앞의 7px 점으로 옮겨졌다(D-474). 재는 곳만 바꾸고 재는 것은 그대로다 — 같은 신호가 제품 전체에서 같은 색인가.
 * 띠를 걷은 이유는 칸마다 다른 색 띠 일곱 개가 나란히 서면 무엇이 중요한지가 사라지기
 * 때문이고, 그 판단은 색 어휘가 한 곳이라는 이 시험의 목적과 무관하다. 논의 갈래
 * 카드(`DiscussBucket`)는 띠를 그대로 쓰므로 그쪽 단언은 안 옮긴다.
 */

function withTheme(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

/** 위색 띠의 실제 색. 안 실리면 CSS 기본값 `currentColor` 로 떨어지므로 빈 문자열이다. */
function topBandColor(el) {
  return getComputedStyle(el).borderBlockStartColor || "";
}

describe("신호 어휘는 한 곳이다", () => {
  it("톤 표가 셋을 서로 다른 색으로 준다", () => {
    const tones = SIGNAL_ORDER.map((k) => SIGNALS[k].tone);
    expect(new Set(tones).size).toBe(SIGNAL_ORDER.length);
    for (const tone of tones) expect(TONE_ACCENT[tone]).toBeTruthy();
  });

  it("paletteAt 은 팔레트 경로가 아닌 값을 **그대로** 돌려준다", () => {
    // 🔴 예전에는 `theme.palette["var(--badge-purple-fg)"]` 를 찾아 undefined 를 돌려줬다.
    // undefined 를 border-color 에 주면 속성이 아예 안 실리고 글자색 띠가 그려진다.
    const theme = { palette: { brand: { core: "#5A4FCF" } } };
    expect(paletteAt(theme, "brand.core")).toBe("#5A4FCF");
    expect(paletteAt(theme, "var(--badge-purple-fg)")).toBe("var(--badge-purple-fg)");
  });

  it("KPI 타일이 보라 톤을 실제로 그린다", () => {
    const { container } = withTheme(
      <StatusKpiTile label={SIGNALS.issue.label} value="3" kind={SIGNALS.issue.tone} />,
    );
    const dot = container.querySelector("[data-status-dot]");
    expect(dot).toBeInTheDocument();
    expect(getComputedStyle(dot).backgroundColor).toContain("--badge-purple-fg");
    // 색은 점이 나르고 **띠는 없다** — 걷은 것이 실제로 걷혔는지 반대편에서도 확인한다.
    expect(topBandColor(container.firstChild)).not.toContain("--badge-purple-fg");
  });

  it("논의 갈래 카드가 같은 톤 표를 본다", () => {
    withTheme(
      <DiscussBucket label={SIGNALS.issue.label} count={2} tone={SIGNALS.issue.tone} selected={false} onClick={() => {}} />,
    );
    const tile = screen.getByRole("tab");
    expect(topBandColor(tile)).toContain("--badge-purple-fg");
  });

  it("어느 화면도 신호 이름을 따로 적지 않는다", async () => {
    // 소스에서 재는 이유: 렌더로는 「우연히 같은 글자」와 「같은 표를 본다」를 못 가른다.
    const files = import.meta.glob("../screens/*.jsx", { query: "?raw", import: "default", eager: true });
    const offenders = [];
    for (const [path, src] of Object.entries(files)) {
      if (path.includes(".test.")) continue;
      // 신호 이름을 문자열 리터럴로 적은 자리. 어휘 표는 `SIGNALS[...].label` 로 읽는다.
      if (/["'`]이슈 있음["'`]|["'`]차단됨["'`]/.test(src)) offenders.push(path);
    }
    expect(offenders).toEqual([]);
  });
});
