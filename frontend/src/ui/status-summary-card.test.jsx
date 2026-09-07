import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { StatusSummaryCard } from "./StatusKpi.jsx";

/* 상태 요약이 **카드 하나**가 됐다 (D-474).
 *
 * 예전에는 상태마다 카드 하나였고 작업 보드는 일곱 칸 중 다섯이 0건이었다 — 빈 카드
 * 다섯이 화면 폭을 먹고 무엇이 중요한지를 지웠다. 이 시험이 재는 것은 「합쳤다」가 아니라
 * 합치면서 **잃지 않았는가**다: 0건인 상태의 이름이 남는가, 누를 수 있던 칸이 여전히
 * 눌리는가, 지금 고른 것을 화면이 말하는가.
 */
function withTheme(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

const ITEMS = [
  { key: "plan", label: "계획", value: "151" },
  { key: "prog", label: "진행 중", value: "21" },
  { key: "done", label: "완료", value: "0" },
  { key: "hold", label: "보류", value: "0" },
  { key: "cancel", label: "취소", value: "0" },
];

describe("상태 요약 카드", () => {
  it("값이 있는 상태만 칩으로 서고 건수와 비율을 함께 말한다", () => {
    withTheme(<StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} />);
    const group = screen.getByRole("group", { name: "상태" });
    expect(within(group).getByText("151")).toBeInTheDocument();
    expect(within(group).getByText("88%")).toBeInTheDocument();
    expect(within(group).getByText("12%")).toBeInTheDocument();
  });

  it("0건인 상태는 **이름을 잃지 않고** 한 칸으로 접힌다", () => {
    withTheme(<StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} />);
    // 접기의 값어치는 자리를 아끼는 것이지 사실을 지우는 것이 아니다.
    expect(screen.getByText("완료, 보류, 취소 0건")).toBeInTheDocument();
    // 그 셋은 자기 칩을 따로 갖지 않는다.
    expect(screen.queryByRole("button", { name: /^완료/ })).toBeNull();
  });

  /* 접기의 값어치는 자리를 아끼는 것이지 **작동하던 조작기를 없애는 것**이 아니다. */
  it("0건이어도 누를 수 있으면 접지 않는다", () => {
    withTheme(<StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} onSelect={() => {}} />);
    // 다섯 다 눌러서 목록을 거를 수 있으므로 하나도 안 접힌다.
    expect(screen.queryByText(/0건$/)).toBeNull();
    expect(screen.getByRole("button", { name: "완료 0" })).toBeInTheDocument();
  });

  it("누를 수 있는 칩은 진짜 버튼이고 aria-pressed 로 고른 것을 말한다", async () => {
    const onSelect = vi.fn();
    withTheme(
      <StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} value="prog" onSelect={onSelect} />,
    );
    const chip = screen.getByRole("button", { name: "진행 중 21" });
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "계획 151" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(chip);
    expect(onSelect).toHaveBeenCalledWith("prog");
  });

  it("onSelect 가 없으면 칩은 버튼이 아니다 — 죽은 단추를 만들지 않는다", () => {
    withTheme(<StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("항목의 onClick 이 onSelect 보다 우선한다 — 화면이 데려갈 곳을 스스로 정한다", async () => {
    const own = vi.fn();
    const onSelect = vi.fn();
    withTheme(
      <StatusSummaryCard
        ariaLabel="상태" total="172" onSelect={onSelect}
        items={[{ key: "plan", label: "계획", value: "151", onClick: own }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "계획 151" }));
    expect(own).toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("신호는 머리 오른쪽에 서고 0건인 것은 안 선다", async () => {
    const onRiskSelect = vi.fn();
    withTheme(
      <StatusSummaryCard
        ariaLabel="상태" total="172" items={ITEMS}
        risks={[
          { key: "overdue", label: "지연", value: "16" },
          { key: "blocked", label: "차단됨", value: "0" },
        ]}
        riskValue="overdue"
        onRiskSelect={onRiskSelect}
      />,
    );
    const risk = screen.getByRole("button", { name: "지연 16" });
    expect(risk).toHaveAttribute("aria-pressed", "true");
    // 0 짜리 신호는 누를 것이 없는 단추다 — 아예 안 그린다.
    expect(screen.queryByText("차단됨")).toBeNull();
    await userEvent.click(risk);
    expect(onRiskSelect).toHaveBeenCalledWith("overdue");
  });

  it("색은 점이 나르고 숫자는 잉크색이다", () => {
    const { container } = withTheme(
      <StatusSummaryCard ariaLabel="상태" total="172" items={ITEMS} />,
    );
    // 값이 있는 상태 둘 + 스택 바가 아니라, 칩마다 점 하나.
    expect(container.querySelectorAll("[data-status-dot]")).toHaveLength(2);
    // 스택 바는 낭독기에게 같은 사실을 두 번 읽히지 않는다 — 아래 칩이 같은 숫자를 글자로 말한다.
    const bar = container.querySelector("[data-ratio-bar]");
    expect(bar).toBeInTheDocument();
    expect(bar).toHaveAttribute("aria-hidden", "true");
  });

  /* 전체를 준 카드와 안 준 카드는 **다른 것을 말한다.** 홈의 「오늘 마감」과 「지연」은
     한 티켓이 둘 다일 수 있어 합이 전체가 아니다 — 그 합으로 낸 비율은 거짓이다. */
  it("총계를 안 주면 비율도 스택 바도 안 그린다 — 겹칠 수 있는 축이기 때문이다", () => {
    const { container } = withTheme(
      <StatusSummaryCard
        ariaLabel="상태"
        items={[{ key: "a", label: "가", value: "3" }, { key: "b", label: "나", value: "1" }]}
      />,
    );
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("75%")).toBeNull();
    expect(container.querySelector("[data-ratio-bar]")).toBeNull();
  });

  it("값이 null 인 항목은 0 이 아니라 「모른다」다 — 0건으로 접지 않는다", () => {
    withTheme(
      <StatusSummaryCard
        ariaLabel="상태"
        items={[
          { key: "a", label: "오늘 마감", value: null },
          { key: "b", label: "지연", value: null },
          { key: "c", label: "진행 중", value: "0" },
        ]}
      />,
    );
    // 끊겨서 모르는 둘은 `-` 로 서고,
    expect(screen.getAllByText("-")).toHaveLength(2);
    // 진짜 0 인 하나만 접힌다 — 「모른다」와 「없다」를 한 칸에 섞지 않는다.
    expect(screen.getByText("진행 중 0건")).toBeInTheDocument();
  });
});
