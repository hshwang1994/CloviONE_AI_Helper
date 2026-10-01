import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Button, Callout, HeadRow, SectionHeader, centerPad } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 머리 줄 (D-528) — 「앞 · 글 · 동작」을 **첫 줄 가운데선** 하나에 세운다. 메시지 상자 · 구획 머리 · 판 머리 · 스위치 줄이
 * 같은 모양이다. 예전 메시지 상자는 위 정렬이라 한 줄 글(24px) 옆 30px 단추가 3 ~ 5px 내려갔다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("centerPad", () => {
  it("두 높이 차이의 반을 rem 으로 돌려주고, 음수면 0 이다", () => {
    expect(centerPad(34, 24)).toBe("0.3125rem");
    expect(centerPad(30, 16)).toBe("0.4375rem");
    expect(centerPad(16, 30)).toBe("0rem");
  });
});

describe("HeadRow", () => {
  it("first-line 모드는 줄 높이 변수와 칸별 내림 여백으로 첫 줄을 동작의 가운데선에 맞춘다", () => {
    const { container } = ui(
      <HeadRow lead={<span>!</span>} lineHeightPx={24} leadPx={16} actionPx={30} action={<Button size="sm">목록 보기</Button>}>
        부서가 지정되지 않은 사람이 1명 있습니다.
      </HeadRow>,
    );
    const row = container.querySelector(".k-head-row");
    expect(row).toHaveAttribute("data-head-row", "first-line");
    const s = getComputedStyle(row);
    expect(s.gridTemplateColumns).toBe("auto minmax(0,1fr) auto");
    expect(s.alignItems).toBe("start");
    expect(s.getPropertyValue("--head-h").trim()).toBe("1.875rem");
    // H = max(30, 24) = 30 → 아이콘 (30-16)/2 = 7px, 글 (30-24)/2 = 3px, 동작 0.
    expect(getComputedStyle(container.querySelector(".k-head-lead")).paddingTop).toBe("0.4375rem");
    expect(getComputedStyle(container.querySelector(".k-head-text")).paddingTop).toBe("0.1875rem");
    expect(getComputedStyle(container.querySelector(".k-head-action")).paddingTop).toBe("0rem");
  });

  it("center 모드는 행 전체의 가운데를 맞추고 내림 여백을 두지 않는다", () => {
    const { container } = ui(<HeadRow mode="center" action={<Button size="sm">설정하기</Button>}>두 줄 행</HeadRow>);
    const row = container.querySelector(".k-head-row");
    expect(row).toHaveAttribute("data-head-row", "center");
    expect(getComputedStyle(row).alignItems).toBe("center");
    expect(getComputedStyle(container.querySelector(".k-head-text")).paddingTop).toBe("");
  });

  it("동작이 없으면 줄 높이는 글 한 줄이고 동작 칸이 없다", () => {
    const { container } = ui(<HeadRow lineHeightPx={24}>제목만</HeadRow>);
    const row = container.querySelector(".k-head-row");
    expect(getComputedStyle(row).gridTemplateColumns).toBe("minmax(0,1fr)");
    expect(getComputedStyle(row).getPropertyValue("--head-h").trim()).toBe("1.5rem");
    expect(container.querySelector(".k-head-action")).toBeNull();
  });
});

describe("머리 줄 위에 선 부품", () => {
  it("메시지 상자는 머리 줄이고 동작 단추는 30 으로 선다", () => {
    const { container } = ui(
      <Callout tone="warn" action={<Button>목록 보기</Button>}>부서가 지정되지 않은 사람이 1명 있습니다.</Callout>,
    );
    const row = container.querySelector(".k-callout > .k-head-row");
    expect(row).toBeTruthy();
    expect(row.querySelector(".k-head-action")).toContainElement(screen.getByRole("button", { name: "목록 보기" }));
  });

  it("구획 머리는 동작을 제목 줄에 세우고 도움말은 그 아래 전체 폭이다", () => {
    const { container } = ui(
      <SectionHeader title="최근 실패" help="최근 7일 안의 실패만 보입니다." action={<Button>모두 보기</Button>} count="3건" />,
    );
    const head = container.querySelector(".k-section-header");
    const titleRow = head.firstElementChild;
    expect(titleRow).toContainElement(screen.getByRole("heading", { name: "최근 실패" }));
    expect(titleRow).toContainElement(screen.getByRole("button", { name: "모두 보기" }));
    // 도움말은 제목 줄(동작 상자) 밖이다.
    expect(titleRow).not.toContainElement(screen.getByText("최근 7일 안의 실패만 보입니다."));
    expect(screen.getByText("3건")).toBeInTheDocument();
  });
});
