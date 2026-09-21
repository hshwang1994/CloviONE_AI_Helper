import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { SummaryView, STRIP_AS_META_MAX } from "./SummaryView.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 목록 화면 요약의 그릇 (D-501) — 요약은 누를 수 있거나 · 경보이거나 · 그 값의 유일한 자리일 때만 판을 갖는다.
 *
 * AI 사용 상한은 「0」 하나씩을 든 800px 판 둘이었고, 작업 큐는 상태 카드 옆에 「평균 처리 시간」 이름만 든 반폭 판과
 * 「가장 오래된 대기」 큰 글자 판을 한 줄 더 세웠다. 측정값 둘 이하는 속성 줄 한 줄이고, 상태 구성의 측정값은 카드 아래
 * 정의 목록 한 줄이다. */
function draw(summary, data = {}) {
  return render(<ThemeModeProvider><SummaryView summary={summary} data={data} ctx={{}} /></ThemeModeProvider>);
}

describe("strip — 측정값 둘 이하는 속성 줄이다", () => {
  it("값 둘은 판 둘이 아니라 속성 줄 한 줄이다(AI 사용 상한)", () => {
    const { container } = draw({
      cards: () => [
        { value: "0", label: "오늘 전체 AI 호출" },
        { value: "0", label: "이번 달 전체 AI 호출" },
      ],
    });
    expect(STRIP_AS_META_MAX).toBe(2);
    const bar = container.querySelector(".k-metabar");
    expect(bar).not.toBeNull();
    expect(within(bar).getByText("오늘 전체 AI 호출")).toBeInTheDocument();
    expect(container.querySelectorAll(".k-metacell")).toHaveLength(2);
  });

  it("반례 — 셋 이상이면 비교를 돕는 타일 줄이다", () => {
    const { container } = draw({
      cards: () => [{ value: "1", label: "가" }, { value: "2", label: "나" }, { value: "3", label: "다" }],
    });
    expect(container.querySelector(".k-metabar")).toBeNull();
    expect(screen.getByRole("group", { name: "요약" }).children).toHaveLength(3);
  });

  it("반례 — 누를 수 있는 측정값은 둘 이하여도 타일로 남는다(좁히는 길을 없애지 않는다)", () => {
    const { container } = draw({
      cards: () => [{ value: "3", label: "실패", onClick: () => {} }, { value: "1", label: "대기" }],
    });
    expect(container.querySelector(".k-metabar")).toBeNull();
    expect(screen.getByRole("button", { name: "실패 3" })).toBeInTheDocument();
  });
});

describe("status — 측정값은 카드 아래 한 줄이다", () => {
  const JOBS = {
    kind: "status",
    total: (s) => s.queued + s.failed,
    cards: (s) => [
      { value: s.queued, label: "대기", onClick: () => {} },
      { value: s.failed, label: "실패", onClick: () => {} },
      { value: s.age, label: "가장 오래된 대기", role: "risk", kind: "danger", onClick: () => {} },
      { value: s.avg, label: "평균 처리 시간(24h)", role: "measure" },
    ],
  };

  it("측정값은 두 번째 타일 줄이 아니라 카드의 정의 목록이다 — 판이 하나다", () => {
    const { container } = draw(JOBS, { queued: 7, failed: 3, age: "622시간 38분", avg: "12.3초" });
    expect(screen.getAllByRole("group", { name: /요약/ })).toHaveLength(1);
    const dl = container.querySelector("[data-summary-notes]");
    expect(within(dl).getByText("평균 처리 시간(24h)")).toBeInTheDocument();
    expect(within(dl).getByText("12.3초")).toBeInTheDocument();
    // 경보는 카드 머리의 칩이다 — 글자 값이어도 선다.
    expect(screen.getByRole("button", { name: "가장 오래된 대기 622시간 38분" })).toBeInTheDocument();
  });

  it("값이 없는 측정값은 그 줄에도 서지 않는다", () => {
    const { container } = draw(JOBS, { queued: 7, failed: 3, age: "5분", avg: null });
    expect(container.querySelector("[data-summary-notes]")).toBeNull();
    expect(screen.queryByText("평균 처리 시간(24h)")).toBeNull();
  });

  it("전체를 주면 비율 바가 선다 — 부분 둘이 한 전체를 나눈다", () => {
    const { container } = draw(JOBS, { queued: 7, failed: 3, age: "5분", avg: null });
    expect(container.querySelector("[data-ratio-bar]")).not.toBeNull();
    expect(container.querySelector("[data-summary-total]")).toHaveTextContent("10");
  });
});
