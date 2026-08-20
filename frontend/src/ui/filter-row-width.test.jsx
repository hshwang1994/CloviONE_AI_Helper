/* qa-contract-replaced-by: frontend/src/ui/filter-bar-grid.test.jsx
 * qa-contract-change: 필터 줄의 폭 계약이 «격자 트랙 상한»에서 «컨트롤 종류별 폭»으로
 * 바뀌었다. 옛 시험이 지키던 불변식(필터가 적을 때 폭만 넓어지지 않는다)은 그대로 살아
 * 있고, 그것을 지키는 **기제**가 바뀐다: 예전에는 격자 상자를 `width: fit-content` 로
 * 줄여서 지켰는데, 바로 그 한 줄이 `isolated_control_row` 가 재는 «윗줄 여유» 를 구조적으로
 * 항상 0 으로 만들어 R-76 이 이름으로 지목한 결함 두 개를 게이트가 볼 수 없게 만들고 있었다.
 * 이제 줄은 폭 전체를 차지하고 컨트롤이 자기 종류만큼만 차지한다. 단언 수는 늘었다.
 *
 * ## 이 파일이 지키는 것
 *
 *  1. **컨트롤 폭은 종류가 정한다.** 검색은 늘어나고, Entity 는 넉넉하고, 닫힌 열거형은
 *     내용만큼이다. 값 길이와 무관하게 전부 같은 폭을 받는 상태로 돌아가지 않는다.
 *  2. **상한이 고정 rem 이다.** `1fr` 처럼 컨테이너에 비례하는 값이면 필터가 둘뿐일 때
 *     두 컨트롤이 페이지 폭을 절반씩 나눠 갖는다 — 옛 시험이 잡던 그 결함이다.
 *  3. **줄은 폭 전체를 차지한다.** 남는 폭이 실제로 남는 폭이어야 프로브가 그것을 잰다.
 *  4. **되돌리기는 조건 칸이 아니다.** `필터 지우기` 가 필터와 같은 폭의 상자가 되지 않는다.
 *  5. **실제 화면이 그 계약을 쓴다.** 부품만 맞고 화면이 자기 격자를 다시 만드는 상태를
 *     막는다(예전에 TicketFilterBar 와 DataScreen 이 각자 격자를 복제하고 있었다).
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { FilterRow, FilterSurface, filterGroupOf, FILTER_GROUP_ORDER } from "./FilterBar.jsx";
import { CONTROL_KIND, kindSx } from "./filters.jsx";
import { createClovirTheme } from "./theme.js";
import { TicketFilterBar } from "../screens/TicketFilterBar.jsx";

function renderRow(children) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <FilterSurface data-testid="surface">
        <FilterRow data-testid="row">{children}</FilterRow>
      </FilterSurface>
    </ThemeProvider>,
  );
}

describe("컨트롤 폭은 종류가 정한다 (C2 «폭 배분»)", () => {
  it("종류마다 서로 다른 폭 계약을 갖는다 — 값 길이와 무관한 균등 폭이 아니다", () => {
    const widths = Object.entries(CONTROL_KIND).map(([k, v]) => [k, v.flex]);
    // 일곱 종류가 전부 선언돼 있다. (`number` 는 W5 가 더했다 — 「동시 실행 수」의 값은
    // «1» 한 글자인데 균등 격자가 775px 를 줬다. 폭이 값에 대해 거짓말을 하면 사용자는
    // 그 칸에 무엇을 넣어야 하는지 잘못 짐작한다.)
    expect(Object.keys(CONTROL_KIND).sort()).toEqual(
      ["date", "entity", "enum", "number", "search", "text", "toggle"],
    );
    // 그리고 그 값들이 전부 같지 않다 — 같으면 그것이 곧 균등 폭이다.
    expect(new Set(widths.map(([, f]) => f)).size).toBeGreaterThan(1);
  });

  it("자라는 것은 검색과 Entity 뿐이고, 둘 다 상한이 있다 — 남는 폭을 나눠 갖지 않는다", () => {
    // 검색은 그 줄의 지배 컨트롤이다.
    expect(CONTROL_KIND.search.flex.startsWith("1 ")).toBe(true);
    // Entity 는 값이 길어 남는 폭을 쓸 자격이 있다 — 다만 자기 상한까지만이다.
    expect(CONTROL_KIND.entity.flex.startsWith("1 ")).toBe(true);
    expect(CONTROL_KIND.entity.maxWidth).toBeTruthy();
    // 나머지는 자라지 않는다 — 짧은 값이 긴 값과 같은 폭을 받는 상태로 돌아가지 않는다.
    for (const kind of ["enum", "date", "text", "toggle", "number"]) {
      expect(CONTROL_KIND[kind].flex.startsWith("0 "), kind).toBe(true);
    }
  });

  it("상한은 고정 rem 이다 — `fr` 이면 컨테이너 폭에 비례해 늘어난다(옛 결함)", () => {
    for (const [kind, spec] of Object.entries(CONTROL_KIND)) {
      if (!spec.maxWidth) continue;
      expect(String(spec.maxWidth).endsWith("fr"), kind).toBe(false);
      expect(String(spec.maxWidth).endsWith("rem"), kind).toBe(true);
    }
  });

  it("Entity 는 닫힌 열거형보다 넓다 — 프로젝트명이 상태 라벨과 같은 폭을 받지 않는다", () => {
    expect(Number.parseFloat(CONTROL_KIND.entity.minWidth))
      .toBeGreaterThan(Number.parseFloat(CONTROL_KIND.enum.minWidth));
    expect(Number.parseFloat(CONTROL_KIND.entity.maxWidth))
      .toBeGreaterThan(Number.parseFloat(CONTROL_KIND.enum.maxWidth));
  });

  it("호출부 sx 가 종류 기본값을 이긴다 — 예외가 필요한 자리는 여전히 예외를 쓸 수 있다", () => {
    const merged = kindSx("enum", { minWidth: "20rem" });
    expect(merged.minWidth).toBe("20rem");
    expect(merged.flex).toBe(CONTROL_KIND.enum.flex);
  });
});

describe("필터 줄은 폭 전체를 차지한다 (프로브가 남는 폭을 잴 수 있어야 한다)", () => {
  it("줄은 100% 폭이고 줄바꿈된다 — `fit-content` 로 상자를 줄이지 않는다", () => {
    renderRow(<div>필터 1</div>);
    const row = screen.getByTestId("row");
    const cs = getComputedStyle(row);
    expect(cs.display).toBe("flex");
    expect(cs.flexWrap).toBe("wrap");
    expect(cs.width).toBe("100%");
  });

  it("탐색 줄은 판이 아니다 — 배경도 테두리 상자도 없다(지시 80)", () => {
    renderRow(<div>필터 1</div>);
    const surface = screen.getByTestId("surface");
    const cs = getComputedStyle(surface);
    // 배경을 칠하지 않는다(칠하면 그것이 판이다).
    expect(cs.backgroundColor === "" || cs.backgroundColor === "rgba(0, 0, 0, 0)").toBe(true);
    // 아래 실선 하나로 목록과 갈린다 — 네 변을 두르지 않는다.
    expect(cs.borderBottomStyle).toBe("solid");
    expect(cs.borderTopStyle === "" || cs.borderTopStyle === "none").toBe(true);
  });
});

describe("필터 축의 그룹 순서는 한 곳에서 정한다 (C2 «그룹 순서 고정»)", () => {
  it("scope → entity → 분류 → 상태 → 기간 순이다", () => {
    expect(FILTER_GROUP_ORDER.slice(0, 5)).toEqual(
      ["scope", "entity", "category", "status", "period"],
    );
  });

  it("키 이름에서 그룹을 유도하고, 선언이 명시하면 그것이 이긴다", () => {
    expect(filterGroupOf({ key: "dept" })).toBe("scope");
    expect(filterGroupOf({ key: "assignee_user_id" })).toBe("entity");
    expect(filterGroupOf({ key: "status" })).toBe("status");
    expect(filterGroupOf({ key: "since" })).toBe("period");
    expect(filterGroupOf({ key: "whatever" })).toBe("other");
    // `kind: entity` 는 키 이름과 무관하게 entity 다.
    expect(filterGroupOf({ key: "whatever", kind: "entity" })).toBe("entity");
    // 명시 선언이 최우선.
    expect(filterGroupOf({ key: "status", group: "scope" })).toBe("scope");
  });
});

/* TicketFilterBar.jsx 가 실제로 이 공유 계약을 쓰는지 — 화면 두 곳(TicketFilterBar,
 * DataScreen)이 각자 격자를 복제하던 것을 하나로 모은 것이므로, 부품 자체 검사만으로는
 * "실제 화면이 그것을 쓴다"를 보장하지 못한다. */
describe("TicketFilterBar — 공유 탐색 줄 계약을 실제로 쓴다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({ configured: true, ok: true, statuses: ["진행", "완료"], priorities: ["High", "Normal"], difficulties: [] });
  });

  function renderBar(fields, value) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <ThemeProvider theme={createClovirTheme()}>
          <TicketFilterBar
            fields={fields}
            value={value}
            onChange={() => {}}
            total={7}
          />
        </ThemeProvider>
      </QueryClientProvider>,
    );
  }

  it("필터가 든 줄이 판이 아니라 공유 탐색 줄이다", async () => {
    const { container } = renderBar(["status", "priority"], { status: "", priority: "" });
    await screen.findByRole("combobox", { name: "상태" });
    expect(container.querySelector("[data-filter-surface]")).toBeTruthy();
    expect(container.querySelector("[data-filter-row]")).toBeTruthy();
    // 예전에는 이 자리가 `<Card className="c-toolbar-card">` 였다.
    expect(container.querySelector(".c-toolbar-card")).toBeNull();
  });

  it("건수는 필터와 목록 사이의 결과 줄에 있고 조건 수를 함께 말한다", async () => {
    const { container } = renderBar(["status"], { status: "완료" });
    await screen.findByRole("combobox", { name: "상태" });
    const line = container.querySelector("[data-result-line]");
    expect(line).toBeTruthy();
    expect(line.textContent).toContain("조건 1개, 결과");
    expect(line.textContent).toContain("7건");
  });

  it("«필터 지우기» 는 조건 칸이 아니라 동작 묶음 안의 텍스트 버튼이다", async () => {
    const { container } = renderBar(["status"], { status: "완료" });
    const clear = await screen.findByRole("button", { name: "필터 지우기" });
    // 동작 묶음 안에 있다(필터와 같은 흐름 칸이 아니다).
    expect(clear.closest("[data-filter-actions]")).toBeTruthy();
    // 그리고 테두리 있는 상자가 아니다 — `/policies` 에서 지우려는 필터보다 넓은 255px
    // 테두리 상자였던 것이 지시 76 이 지목한 상태다.
    expect(clear.className).toContain("MuiButton-text");
    expect(container.querySelector("[data-filter-actions]")).toBeTruthy();
  });

  it("조건이 없으면 «필터 지우기» 자체가 없다 — 아무 일도 안 하는 버튼을 두지 않는다", async () => {
    renderBar(["status"], { status: "" });
    await screen.findByRole("combobox", { name: "상태" });
    expect(screen.queryByRole("button", { name: "필터 지우기" })).toBeNull();
  });
});
