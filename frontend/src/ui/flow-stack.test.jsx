import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ActionFooter, Button, Callout, Card, FLOW_GAP, FlowStack } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 흐름 (D-528) — 덩어리 사이 간격은 상자가 아니라 **담는 쪽**이 준다. 예전에는 메시지 상자 74곳이 위아래 여백을 손으로
 * 적어 화면마다 간격이 달랐다. 흐름 그릇은 자식 사이 간격을 주고, 자식의 위아래 바깥 여백을 지운다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

/** 이 요소에 걸린 emotion 규칙 본문 전부(선택자 포함) — jsdom 은 `> *` 같은 자식 선택자를 계산값으로 다 풀지 못한다. */
function rulesText(el) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  return [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n")
    .split("}").filter((chunk) => classes.some((c) => chunk.includes("." + c))).join("}\n");
}

describe("FlowStack", () => {
  it("간격 토큰은 page 16 · card 14 · tight 8 이다", () => {
    expect(FLOW_GAP).toEqual({ page: "1rem", card: "0.875rem", tight: "0.5rem" });
  });

  it("세로 흐름이고 자식 사이 간격을 그릇이 준다", () => {
    const { container } = ui(<FlowStack gap="card"><div>가</div><div>나</div></FlowStack>);
    const flow = container.querySelector(".k-flow");
    const s = getComputedStyle(flow);
    expect(s.display).toBe("flex");
    expect(s.flexDirection).toBe("column");
    expect(s.rowGap).toBe("0.875rem");
    expect(flow).toHaveAttribute("data-flow", "card");
  });

  it("자식의 위아래 바깥 여백은 겹친 선택자(&&)로 지운다 — 자식 sx(0,1,0)보다 이긴다", () => {
    const { container } = ui(<FlowStack><Callout tone="info">안내</Callout></FlowStack>);
    const text = rulesText(container.querySelector(".k-flow"));
    expect(text).toMatch(/\.css-[\w-]+\.css-[\w-]+>\*\{[^}]*margin-block-start:0/);
    expect(text).toMatch(/margin-block-end:0/);
  });
});

describe("흐름 밖 메시지 상자의 형제 간격", () => {
  /* 블록 흐름에서는 상자가 형제와 12px 한 간격을 스스로 갖지만, gap 을 주는 flex · grid 그릇에서는 여백이 gap 에 더해진다
     (부품 갤러리 실측: 두 상자 사이 gap + 24). 그 그릇 안의 상자는 표지를 달고 여백을 갖지 않는다. */
  it("gap 을 주는 격자 안에서는 표지가 서고, 블록 흐름에서는 서지 않는다", () => {
    const { container } = ui(
      <>
        <div className="grid" style={{ display: "grid", rowGap: "8px" }}>
          <Callout tone="info">격자 안 하나</Callout>
          <Callout tone="warn">격자 안 둘</Callout>
        </div>
        <div className="block">
          <Callout tone="info">블록 안 하나</Callout>
          <p>문단</p>
        </div>
        <div className="flexless" style={{ display: "flex", flexDirection: "column" }}>
          <Callout tone="info">gap 없는 flex</Callout>
        </div>
      </>,
    );
    for (const box of container.querySelectorAll(".grid > .k-callout")) expect(box).toHaveAttribute("data-gap-parent");
    expect(container.querySelector(".block > .k-callout")).not.toHaveAttribute("data-gap-parent");
    // gap 이 없는 flex 는 간격을 주지 않는 그릇이다 — 상자가 제 여백을 지킨다.
    expect(container.querySelector(".flexless > .k-callout")).not.toHaveAttribute("data-gap-parent");
  });
});

describe("Card stack", () => {
  it("판이 자식 사이 간격(14)을 주고, 발이 있으면 본문 상자가 그 간격을 준다", () => {
    const { container } = ui(<Card stack><div>가</div><div>나</div></Card>);
    const card = container.querySelector('[data-surface="plate"]');
    expect(getComputedStyle(card).rowGap).toBe("0.875rem");
    expect(getComputedStyle(card).flexDirection).toBe("column");

    // 판 발이 마지막 줄이면 쌓기 간격은 본문 상자가 준다 - 발은 판 바닥에 서고 제 윗선으로 본문과 갈린다.
    const footed = ui(
      <Card stack className="footed">
        <div>가</div>
        <div>나</div>
        <ActionFooter placement="card"><Button>저장</Button></ActionFooter>
      </Card>,
    );
    const root = footed.container.querySelector(".footed");
    const body = root.querySelector("[data-card-body]");
    expect(getComputedStyle(body).rowGap).toBe("0.875rem");
    expect(getComputedStyle(root).rowGap).not.toBe("0.875rem");
  });
});
