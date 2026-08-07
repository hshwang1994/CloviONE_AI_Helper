/* 필터 줄 격자(ui/FilterBar.jsx)의 트랙 상한.
 *
 * 배경 — TicketFilterBar.jsx 와 DataScreen.jsx 가 각자 똑같은 그리드를 복제해 갖고 있었다:
 * `gridTemplateColumns: { sm: "repeat(auto-fit, minmax(11rem, 1fr))", xxl: "repeat(auto-fit,
 * minmax(13rem, 1fr))" }`. auto-fit + 상한 없는 `1fr` 트랙이라, 필터가 둘뿐이면 각 트랙이
 * 카드 폭의 절반씩을 차지해 쓸데없이 넓어졌다.
 *
 * jsdom 은 실제 레이아웃을 계산하지 않으므로(컨테이너 폭에 따라 몇 열이 되는지, 각 칸이
 * 몇 px 인지는 물어볼 수 없다) `new-ticket-layout.test.jsx` 와 같은 방법을 쓴다 — emotion 이
 * 실제로 `<style>` 에 내보낸 CSS 규칙을 그대로 읽어 트랙 정의 자체를 검사한다. `minmax(min,
 * 1fr)` 는 두 번째 값이 **컨테이너의 남는 폭에 비례해 늘어나는** 트랙이라 상한이 없다.
 * `minmax(min, 16rem)` 처럼 고정 rem 이면 아무리 컨테이너가 넓어도, 필터가 아무리 적어도
 * 그 값에서 멈춘다 — 이것이 "합리적 상한"의 뜻이다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { FilterBarGrid } from "./FilterBar.jsx";
import { createClovirTheme } from "./theme.js";
import { TicketFilterBar } from "../screens/TicketFilterBar.jsx";

/* emotion 이 `<style>` 에 넣은 규칙 중 이 요소의 클래스에 걸린 것만 (감싼 at-rule, 선언) 으로
 * 뽑는다. new-ticket-layout.test.jsx 와 같은 구현 — 공용 테스트 유틸이 없어 파일마다 복제하는
 * 것이 이 저장소의 기존 관례다. */
function rulesFor(el) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  const found = [];
  const scan = (text, cond) => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf("{", i);
      if (open === -1) break;
      const head = text.slice(i, open).trim();
      let depth = 1;
      let j = open + 1;
      while (j < text.length && depth > 0) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
        j += 1;
      }
      if (head.startsWith("@")) scan(text.slice(open + 1, j - 1), cond ? `${cond} && ${head}` : head);
      else if (head.split(",").some((s) => classes.includes(s.trim().replace(/^\./, "")))) {
        found.push({ cond, body: text.slice(open + 1, j - 1) });
      }
      i = j;
    }
  };
  scan(css, "");
  return found;
}

function declaration(rule, prop) {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`).exec(rule.body);
  return m ? m[1].trim() : null;
}

/** `repeat(auto-fit, minmax(MIN, MAX))` 에서 (min, max) 를 뽑는다. */
function minmaxParts(track) {
  const m = /^repeat\(auto-fit,\s*minmax\(([^,]+),\s*([^)]+)\)\)$/.exec(track || "");
  if (!m) throw new Error(`auto-fit/minmax 트랙이 아니다: ${track}`);
  return { min: m[1].trim(), max: m[2].trim() };
}

function renderGrid() {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <FilterBarGrid data-testid="grid">
        <div>필터 1</div>
        <div>필터 2</div>
      </FilterBarGrid>
    </ThemeProvider>,
  );
}

describe("FilterBarGrid — 트랙에 상한이 있다", () => {
  it("필터가 둘뿐이어도 sm 트랙의 최대 폭이 고정 rem 이지 컨테이너에 비례하는 1fr 이 아니다", () => {
    renderGrid();
    const grid = screen.getByTestId("grid");
    const rules = rulesFor(grid);

    const sm = rules.find((r) => r.cond === "@media (min-width:600px)");
    expect(sm, "sm 브레이크포인트 규칙을 못 찾았다").toBeTruthy();
    const track = declaration(sm, "grid-template-columns");
    const { min, max } = minmaxParts(track);

    expect(min).toBe("11rem");
    // 핵심 단정: 두 번째 값이 'fr' 이 아니라 고정 rem 이어야, 필터가 둘뿐일 때 두 트랙이
    // 카드 폭을 절반씩 나눠 갖는 일이 없다. 상한 없는 1fr 이면 여기서 실패한다.
    expect(max.endsWith("fr")).toBe(false);
    expect(max.endsWith("rem")).toBe(true);
    const maxRem = Number.parseFloat(max);
    // '합리적 상한' — 최소 폭(11rem)보다는 넓되, 무한정은 아니다.
    expect(maxRem).toBeGreaterThan(11);
    expect(maxRem).toBeLessThanOrEqual(20);
  });

  it("xxl 트랙도 같은 규칙(고정 rem 상한)을 따른다", () => {
    renderGrid();
    const grid = screen.getByTestId("grid");
    const rules = rulesFor(grid);

    const xxl = rules.find((r) => r.cond === "@media (min-width:2200px)");
    expect(xxl, "xxl 브레이크포인트 규칙을 못 찾았다").toBeTruthy();
    const track = declaration(xxl, "grid-template-columns");
    const { min, max } = minmaxParts(track);

    expect(min).toBe("13rem");
    expect(max.endsWith("fr")).toBe(false);
    expect(max.endsWith("rem")).toBe(true);
    expect(Number.parseFloat(max)).toBeLessThanOrEqual(24);
  });

  it("xs(좁은 화면)는 여전히 한 칸짜리 세로 쌓기다 — 회귀 없음", () => {
    renderGrid();
    const grid = screen.getByTestId("grid");
    const rules = rulesFor(grid);
    // MUI 는 xs(0px)도 다른 브레이크포인트와 같이 `@media (min-width:0px)` 로 내보낸다 —
    // display/gap/align-items 만 조건 없는 기본 규칙이고, 열 수는 xs 도 미디어 쿼리다.
    const xs = rules.find((r) => r.cond === "@media (min-width:0px)");
    expect(xs, "xs 브레이크포인트 규칙을 못 찾았다").toBeTruthy();
    expect(declaration(xs, "grid-template-columns")).toBe("1fr");
  });
});

/* TicketFilterBar.jsx 가 실제로 이 공유 격자를 쓰는지 — 화면 두 곳(TicketFilterBar,
 * DataScreen)이 각자 그리드를 복제하던 것을 하나로 모은 것이므로, 부품 자체 검사만으로는
 * "실제 화면이 그것을 쓴다"를 보장하지 못한다. 필터 두 개(상태·우선순위)만 켠 채로
 * 렌더해 그 DOM 요소에도 같은 트랙 상한이 걸려 있는지 확인한다. */
describe("TicketFilterBar — 필터 2개일 때도 공유 격자(상한 있음)를 쓴다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({ configured: true, ok: true, statuses: ["진행", "완료"], priorities: ["High", "Normal"], difficulties: [] });
  });

  it("상태·우선순위 두 필터의 부모 격자가 sm 에서 minmax(11rem, 16rem) 이하로 캡핑돼 있다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider theme={createClovirTheme()}>
          <TicketFilterBar
            fields={["status", "priority"]}
            value={{ status: "", priority: "" }}
            onChange={() => {}}
          />
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const status = await screen.findByRole("combobox", { name: "상태" });
    const grid = status.closest(".MuiFormControl-root").parentElement;
    const rules = rulesFor(grid);
    const sm = rules.find((r) => r.cond === "@media (min-width:600px)");
    expect(sm, "sm 브레이크포인트 규칙을 못 찾았다(격자를 못 찾았을 수 있다)").toBeTruthy();
    const { max } = minmaxParts(declaration(sm, "grid-template-columns"));
    expect(max).toBe("16rem");
  });
});
