import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { ContextBar } from "./ContextBar.jsx";
import { EntityCombobox, TeamSelect } from "./filters.jsx";
import { FilterToggle } from "./FilterBar.jsx";
import { Segmented } from "./kit.jsx";
import { createClovirTheme } from "./theme.js";

/* 문맥 · 보기 줄(`ui/ContextBar.jsx`, D-497) — 「어느 판을 보는가」와 「그 판을 어떻게 그리는가」.
 *
 * 지키는 것:
 *  1) 문맥 칸은 필터 바와 **같은 줄 칸**이다 — 칸 안 접두 이름 · 노치 라벨 없음 · wide 칸 표식.
 *  2) 보기 옵션 묶음은 `role="group"` 「보기 옵션」이고 보기 전환 뒤에 선다. 넘긴 순서 그대로다.
 *  3) 이 줄은 필터 바가 아니다 — 검색 칸 · 조건 줄 · 필터 면 표식 · 아래 실선이 없다.
 *  4) 브라우저가 받는 CSS — 줄이 wide 칸 계단의 이름 붙은 크기 컨테이너이고, 내용 폭으로 줄어드는 선언이 없다.
 * 실제 칸 폭 · 계단은 실브라우저 `composition_checks.py::filter_cell_anatomy` 가 `[data-context-bar]` 까지 잰다. */

const TEAM = {
  selected: "d-a",
  options: [
    { id: "d-a", name: "플랫폼개발팀", path: [{ id: "o", name: "플랫폼본부" }, { id: "d-a", name: "플랫폼개발팀" }] },
    { id: "d-b", name: "서비스운영팀", path: [{ id: "o", name: "플랫폼본부" }, { id: "d-b", name: "서비스운영팀" }] },
  ],
};
const SPRINTS = [{ value: "sp-1", label: "9-2 (진행 중)", secondary: "2026-09-15 ~ 2026-09-22" }];

function renderBar(props) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <ContextBar
        context={(
          <>
            <TeamSelect team={TEAM} value="d-a" onChange={() => {}} />
            <EntityCombobox size="wide" label="회차" value="sp-1" onChange={() => {}} options={SPRINTS} allLabel="전체" />
          </>
        )}
        {...props}
      />
    </ThemeProvider>,
  );
}

const VIEW = (
  <Segmented
    ariaLabel="보기 선택" value="board" onChange={() => {}}
    options={[{ value: "board", label: "칸반" }, { value: "backlog", label: "백로그" }]}
  />
);
const OPTIONS = (
  <>
    <FilterToggle pressed={false} onClick={() => {}}>내 티켓만</FilterToggle>
    <FilterToggle pressed onClick={() => {}}>보류 접기</FilterToggle>
    <FilterToggle pressed={false} onClick={() => {}}>완료와 취소 보기</FilterToggle>
  </>
);

/* 브라우저가 받는 CSS 에서 이 요소의 규칙을 찾는다(`filter-cell-anatomy.test.jsx` 와 같은 방식 — emotion 이 넣은 규칙을 읽는다). */
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
const declaration = (rule, prop) => {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`).exec(rule.body);
  return m ? m[1].trim() : null;
};

describe("문맥 · 보기 줄", () => {
  it("🔴 문맥 칸은 필터 바와 같은 줄 칸이다 — 칸 안 접두 이름, 노치 라벨 없음, 팀 · 회차는 wide 칸", () => {
    const { container } = renderBar({});
    const bar = container.querySelector("[data-context-bar]");
    expect(bar).not.toBeNull();
    const cells = [...bar.querySelectorAll("[data-filter-kind=entity]")];
    expect(cells).toHaveLength(2);
    expect([...bar.querySelectorAll("[data-prefix-label]")].map((el) => el.textContent)).toEqual(["팀", "회차"]);
    for (const cell of cells) {
      // 접두는 칸의 입력 상자 **안**이고, 두 축 다 값이 긴 축이라 wide 칸이다.
      expect(cell.querySelector("[data-prefix-label]").closest(".MuiInputBase-root")).not.toBeNull();
      expect(cell.getAttribute("data-filter-size")).toBe("wide");
    }
    expect(bar.querySelector("label.MuiInputLabel-root")).toBeNull();
    // 줄 칸의 빈 글자 — 팀 칸은 「고르세요」다(폼 자리의 「팀을 고르세요」가 아니다).
    expect(screen.getByRole("combobox", { name: "팀" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "회차" })).toBeInTheDocument();
  });

  it("🔴 보기 옵션 묶음은 이름 있는 묶음이고 보기 전환 뒤에서 넘긴 순서대로 선다", () => {
    const { container } = renderBar({ view: VIEW, options: OPTIONS });
    const bar = container.querySelector("[data-context-bar]");
    const group = screen.getByRole("group", { name: "보기 옵션" });
    expect(bar.contains(group)).toBe(true);
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["내 티켓만", "보류 접기", "완료와 취소 보기"]);
    // 켬/끔 단추다 — 눌린 상태를 말한다.
    expect(within(group).getByRole("button", { name: "보류 접기" })).toHaveAttribute("aria-pressed", "true");
    // 줄의 차례: 문맥 칸 → 보기 전환 → 보기 옵션.
    const order = [...bar.children].map((el) => (
      el.matches("[data-filter-kind]") ? el.getAttribute("data-filter-kind")
        : el.matches("[data-context-view]") ? "view"
          : el.matches("[data-context-options]") ? "options" : "?"
    ));
    expect(order).toEqual(["entity", "entity", "view", "options"]);
    expect(within(bar.querySelector("[data-context-view]")).getByRole("tablist", { name: "보기 선택" })).toBeInTheDocument();
    // 묶음 이름은 눈에 보이는 글자로도 서되, 낭독기는 묶음 이름으로 한 번만 읽는다.
    const caption = [...group.querySelectorAll("span")].find((el) => el.textContent === "보기 옵션");
    expect(caption).toBeTruthy();
    expect(caption).toHaveAttribute("aria-hidden", "true");
  });

  it("보기 옵션이 없으면 묶음을 세우지 않는다 — 스프린트 회의처럼 문맥만 있는 줄", () => {
    const { container } = renderBar({});
    expect(screen.queryByRole("group", { name: "보기 옵션" })).toBeNull();
    expect(container.querySelector("[data-context-view]")).toBeNull();
    expect(container.querySelector("[data-context-options]")).toBeNull();
  });

  it("🔴 이 줄은 필터 바가 아니다 — 검색 칸 · 조건 줄 · 필터 면 표식이 없다", () => {
    const { container } = renderBar({ view: VIEW, options: OPTIONS });
    const bar = container.querySelector("[data-context-bar]");
    expect(bar.matches("[data-filter-surface], [data-filter-bar]")).toBe(false);
    expect(bar.querySelector("[data-filter-surface], [data-filter-row], [data-condition-line], [data-filter-kind=search]")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("🔴 브라우저가 받는 CSS — 줄은 wide 계단의 이름 붙은 크기 컨테이너이고 부모 폭을 다 쓰는 블록이다", () => {
    const { container } = renderBar({ view: VIEW, options: OPTIONS });
    const bar = container.querySelector("[data-context-bar]");
    const rule = rulesFor(bar).find((r) => r.cond === "" && declaration(r, "container-type"));
    expect(rule, "문맥 줄이 크기 컨테이너를 열지 않는다 — wide 칸이 늘 13rem 에 머문다").toBeTruthy();
    expect(declaration(rule, "container-type")).toBe("inline-size");
    expect(declaration(rule, "container-name")).toBe("filter-surface");
    // 블록 수준 flex 다 — 내용 폭으로 줄어드는 선언(`inline-flex` · `fit-content` · 고정 폭)이 없다. 크기 컨테이너가 그런
    // 자리에 서면 폭이 0 이 된다. emotion 은 `display` 를 접두어 붙은 값 여럿으로 내므로 전부 모아 본다.
    const displays = [...rule.body.matchAll(/(?:^|;)\s*display\s*:\s*([^;]+)/g)].map((m) => m[1].trim());
    expect(displays).toContain("flex");
    expect(displays.some((v) => /inline/.test(v))).toBe(false);
    expect(declaration(rule, "width")).toBeNull();
    expect(rule.body).not.toMatch(/fit-content|max-content/);
    expect(declaration(rule, "flex-wrap")).toBe("wrap");
  });
});
