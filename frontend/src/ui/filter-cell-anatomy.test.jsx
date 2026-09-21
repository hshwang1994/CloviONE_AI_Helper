import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn(async () => ({ items: [{ name: "회의록", document_count: 3 }, { name: "배포", document_count: 1 }] }));
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import {
  CONTROL_KIND, DebouncedTextField, DepartmentFilter, EntityCombobox, FILTER_SURFACE_CONTAINER, FilterRowContext,
  FilterSelect, ROW_KIND, RowSummary, TeamSelect, kindSx, rowAllText,
} from "./filters.jsx";
import { TagPicker } from "./TagPicker.jsx";
import { FilterActions, FilterBar } from "./FilterBar.jsx";
import { CONTROL, createClovirTheme, remPx } from "./theme.js";

/* 필터 바 줄 칸의 해부는 **종류와 무관하게 하나다** (UI 3차 · 조합 계약 C-2).
 *
 * 지난 회차까지 한 줄 안에 해부가 둘이었다: 셀렉트 · 자유 입력은 접두 이름이 칸 안 14 · 값이 6 뒤에 섰고,
 * 자동완성(프로젝트 · 작성자 · 태그)은 접두가 6 · 값이 14 뒤에 섰다. 다중 선택은 칸 안에 칩을 그려 34 칸을
 * 94 까지 키웠다. jsdom 은 여백을 계산하지 못하므로 여기서는 **해부의 구조**를 고정한다 — 모든 종류가
 * 접두 표식(`data-prefix-label`)과 값 표식(`data-row-value`)을 같은 자리에 내고, 다중 선택은 칩 대신 한 줄
 * 요약을 그리며, 폭은 늘어나지 않는 줄 칸 표를 따른다. 실제 여백 · 세로 중심 · 굵기는 실브라우저
 * `composition_checks.py::filter_cell_anatomy` 가 잰다. */

const OPTIONS = [
  { value: "p1", label: "ClovirAssist 플랫폼 전환" },
  { value: "p2", label: "인프라 정비" },
  { value: "p3", label: "포털 개편" },
];

function inRow(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <FilterRowContext.Provider value>{node}</FilterRowContext.Provider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function outsideRow(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>{node}</ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("줄 칸 해부 — 종류가 달라도 접두 이름과 값의 자리가 같다", () => {
  it("셀렉트 · 자동완성 · 자유 입력 · 태그가 모두 칸 안 접두 표식을 낸다", () => {
    const { container } = inRow(
      <>
        <FilterSelect label="상태" value="" onChange={() => {}} options={["계획", "진행 중"]} />
        <EntityCombobox label="프로젝트" value="" onChange={() => {}} options={OPTIONS} />
        <DebouncedTextField label="대분류" value="" onCommit={() => {}} />
        <TagPicker value={[]} onChange={() => {}} />
      </>,
    );
    const cells = [...container.querySelectorAll("[data-filter-kind]")];
    expect(cells).toHaveLength(4);
    for (const cell of cells) {
      const prefix = cell.querySelector("[data-prefix-label]");
      expect(prefix, cell.getAttribute("data-filter-kind")).not.toBeNull();
      // 접두는 칸의 입력 상자 **안**이다(위에 쌓인 라벨이 아니다).
      expect(prefix.closest(".MuiInputBase-root")).not.toBeNull();
    }
    expect(container.querySelector("label.MuiInputLabel-root")).toBeNull();
    expect([...container.querySelectorAll("[data-prefix-label]")].map((el) => el.textContent))
      .toEqual(["상태", "프로젝트", "대분류", "태그"]);
  });

  it("셀렉트의 값은 값 표식 안에 서고, 전체 값을 title 로 든다", () => {
    const { container } = inRow(
      <FilterSelect label="상태" value="진행 중" onChange={() => {}} options={["계획", "진행 중"]} />,
    );
    const value = container.querySelector("[data-row-value]");
    expect(value).not.toBeNull();
    expect(value.textContent).toBe("진행 중");
    expect(value.getAttribute("title")).toBe("상태 진행 중");
  });

  it("자동완성 다중 선택은 줄 칸 안에 칩을 그리지 않고 고른 이름을 한 줄로 요약한다", () => {
    const { container } = inRow(
      <EntityCombobox multiple label="프로젝트" value={["p1", "p3"]} onChange={() => {}} options={OPTIONS} />,
    );
    expect(container.querySelector(".MuiChip-root")).toBeNull();
    const summary = container.querySelector("[data-row-value]");
    expect(summary).not.toBeNull();
    expect(summary.textContent).toBe("ClovirAssist 플랫폼 전환, 포털 개편");
    expect(summary.getAttribute("title")).toBe("ClovirAssist 플랫폼 전환, 포털 개편");
    // 요약은 접두 뒤, 같은 입력 상자 안에 선다.
    const root = container.querySelector(".MuiAutocomplete-inputRoot");
    expect(root.contains(summary)).toBe(true);
    expect(root.querySelector("[data-prefix-label]").compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // 고른 값이 있으면 「전체」 자리표시자를 겹쳐 세우지 않는다.
    expect(container.querySelector("input").getAttribute("placeholder")).toBeNull();
  });

  it("줄 칸 밖(폼 · 모달)의 다중 선택은 예전처럼 칩을 그린다", () => {
    const { container } = outsideRow(
      <EntityCombobox multiple label="프로젝트" value={["p1", "p2"]} onChange={() => {}} options={OPTIONS} />,
    );
    expect(container.querySelectorAll(".MuiChip-root")).toHaveLength(2);
    expect(container.querySelector("[data-row-value]")).toBeNull();
    // 칩이 서면 자리표시자(예시 글)를 칩 옆에 겹쳐 세우지 않는다 — 비었을 때만 선다.
    expect(container.querySelector("input").getAttribute("placeholder")).toBeNull();
    const empty = outsideRow(
      <EntityCombobox multiple label="담당자" value={[]} onChange={() => {}} options={OPTIONS} placeholder="예: 김하나" />,
    );
    expect(empty.container.querySelector("input").getAttribute("placeholder")).toBe("예: 김하나");
  });

  it("태그 고르개도 줄 칸에서는 칩 대신 요약이고, 빈 칸의 「검색 또는 입력」은 안내 표식을 단다", async () => {
    const { container, rerender } = inRow(<TagPicker value={[]} onChange={() => {}} />);
    const input = container.querySelector("input");
    expect(input.getAttribute("placeholder")).toBe("검색 또는 입력");
    expect(input.hasAttribute("data-row-hint")).toBe(true);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <ThemeProvider theme={createClovirTheme()}>
          <FilterRowContext.Provider value><TagPicker value={["회의록", "배포"]} onChange={() => {}} /></FilterRowContext.Provider>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(container.querySelector("[data-row-value]")).not.toBeNull());
    expect(container.querySelector(".MuiChip-root")).toBeNull();
    expect(container.querySelector("[data-row-value]").textContent).toBe("회의록, 배포");
  });

  it("빈 요약은 아무것도 그리지 않는다", () => {
    const { container } = outsideRow(<RowSummary names={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("rowAllText — 이름이 따로 선 낱말일 때만 뗀다", () => {
  const cases = [
    ["역할", "역할: 전체", "전체"],
    ["분류", "분류 전체", "전체"],
    ["프로젝트", "프로젝트 전체", "전체"],
    ["상태", "전체 상태", "전체"],
    ["팀", "팀을 고르세요", "팀을 고르세요"],
    ["부서", "내 범위 전체", "내 범위 전체"],
    ["상태", "종료 제외", "종료 제외"],
    ["기한", undefined, "전체"],
    ["상태", "상태", "상태"],
  ];
  it.each(cases)("%s + %s → %s", (label, allLabel, want) => {
    expect(rowAllText(label, allLabel)).toBe(want);
  });

  it("정규식 글자가 든 이름도 글자 그대로 비교한다", () => {
    expect(rowAllText("WD (예상)", "WD (예상) 전체")).toBe("전체");
    expect(rowAllText("a.b", "axb 전체")).toBe("axb 전체");
  });
});

describe("팀 고르개의 빈 글자", () => {
  const team = { options: [{ id: "t1", name: "플랫폼개발팀" }, { id: "t2", name: "서비스운영팀" }] };

  it("줄 칸에서는 이름이 접두로 서므로 「고르세요」만 말한다 — 「팀 · 을 고르세요」가 아니다", () => {
    const { container } = inRow(<TeamSelect team={team} value="" onChange={() => {}} />);
    expect(container.querySelector("[data-prefix-label]").textContent).toBe("팀");
    expect(container.querySelector("input").getAttribute("placeholder")).toBe("고르세요");
  });

  it("줄 칸 밖에서는 스스로 무엇을 고르는지 말한다", () => {
    const { container } = outsideRow(<TeamSelect team={team} value="" onChange={() => {}} />);
    expect(container.querySelector("input").getAttribute("placeholder")).toBe("팀을 고르세요");
  });
});

describe("줄 칸 폭 — 늘어나지 않는다", () => {
  it("줄 칸이면 종류 표(ROW_KIND)를 쓰고, 줄 밖이면 흐름 치수(CONTROL_KIND)를 그대로 쓴다", () => {
    expect(kindSx("entity", undefined, undefined, true)).toMatchObject({ flex: "0 0 13rem", width: "13rem" });
    expect(kindSx("text", undefined, undefined, true)).toMatchObject({ flex: "0 0 auto", minWidth: "11rem", maxWidth: "min(24rem, 100%)" });
    // 자유 입력의 값 자리는 6rem 이다 — 이름이 길어도 친 글자가 보인다.
    expect(kindSx("text", undefined, undefined, true)["& .MuiInputBase-input"]).toMatchObject({ width: "6rem" });
    expect(kindSx("date", undefined, undefined, true)).toMatchObject({ flex: "0 0 11rem", width: "11rem" });
    expect(kindSx("datetime", undefined, undefined, true)).toMatchObject({ flex: "0 0 18rem", width: "18rem" });
    expect(kindSx("enum", undefined, undefined, true)).toMatchObject({ flex: "0 0 auto", minWidth: "8rem", maxWidth: "13rem" });
    expect(kindSx("entity", undefined).flex).toBe(CONTROL_KIND.entity.flex);
    expect(kindSx("entity", undefined, "form").width).toBe("100%");
  });

  it("늘어나는 줄 칸 종류가 없다 — 검색 슬롯만 줄이 정한다", () => {
    for (const [kind, spec] of Object.entries(ROW_KIND)) {
      if (kind === "search") continue;
      expect(String(spec.flex || "0 0 auto").startsWith("0 "), kind).toBe(true);
      // 컨테이너 질의 안의 계단도 자라는 폭을 말하지 않는다 — 값 하나(`--filter-wide`)만 바꾼다.
      for (const [key, rule] of Object.entries(spec)) {
        if (!key.startsWith("@")) continue;
        expect(rule.flex, `${kind} ${key}`).toBeUndefined();
        expect(rule.width, `${kind} ${key}`).toBeUndefined();
      }
    }
  });

  it("호출부 폭이 이긴다(작업 보드 · 스프린트 회의)", () => {
    expect(kindSx("entity", { width: "16rem", flex: "0 0 16rem" }, undefined, true)).toMatchObject({ width: "16rem", flex: "0 0 16rem" });
  });
});

/* wide Entity 칸 — 값이 긴 축(프로젝트 · 부서와 팀의 경로 · 회차 · 문서 공간 · 연결된 스케줄)은 필터 면의 폭을 따라 계단으로 선다.
 * jsdom 은 컨테이너 질의를 평가하지 못하므로 여기서는 치수 표와 **브라우저가 받는 CSS 규칙**을 고정한다. 실제 폭이 면에 맞는
 * 계단인지는 실브라우저 `composition_checks.py::filter_cell_anatomy` 가 잰다. */
describe("wide Entity 칸 — 필터 면의 폭이 계단을 고른다", () => {
  const STEP = /^@container ([\w-]+) \(min-width: ([\d.]+)rem\)$/;
  const steps = (spec) => Object.entries(spec)
    .filter(([key]) => STEP.test(key))
    .map(([key, rule]) => {
      const [, name, min] = STEP.exec(key);
      return [name, Number(min), rule["--filter-wide"]];
    });

  it("바닥은 기본 칸과 같은 13rem 이고, 면이 76rem · 96rem 이상이면 16rem · 20rem 이다", () => {
    const wide = kindSx("entity", undefined, undefined, true, "wide");
    expect(wide).toMatchObject({ "--filter-wide": "13rem", flex: "0 0 var(--filter-wide)", width: "var(--filter-wide)", minWidth: 0, maxWidth: "100%" });
    expect(ROW_KIND.entityWide["--filter-wide"]).toBe(ROW_KIND.entity.width);
    // 넓은 계단이 뒤에 실린다 — 둘 다 맞는 넓은 면에서는 뒤의 규칙(20rem)이 이긴다.
    expect(steps(wide)).toEqual([
      [FILTER_SURFACE_CONTAINER.containerName, 76, "16rem"],
      [FILTER_SURFACE_CONTAINER.containerName, 96, "20rem"],
    ]);
    // 1366 의 필터 면(1,070px = 66.9rem)은 첫 계단에 못 미친다 — 그 폭의 줄바꿈은 예전과 같다.
    expect(1070 / 16).toBeLessThan(steps(wide)[0][1]);
    // 기본 칸에는 계단이 없다.
    expect(steps(kindSx("entity", undefined, undefined, true))).toEqual([]);
  });

  it("계단은 폭이 아니라 값 하나만 바꾼다 — 호출부가 폭을 말하면 wide 칸에서도 호출부가 이긴다", () => {
    const merged = kindSx("entity", { width: "16rem", flex: "0 0 16rem" }, undefined, true, "wide");
    expect(merged).toMatchObject({ width: "16rem", flex: "0 0 16rem" });
    for (const [, , value] of steps(merged)) expect(value).toMatch(/rem$/);
    for (const [key, rule] of Object.entries(merged)) {
      if (key.startsWith("@container")) expect(Object.keys(rule)).toEqual(["--filter-wide"]);
    }
  });

  it("크기는 줄 칸에서만 뜻이 있다 — 줄 밖 흐름 치수와 폼 치수는 wide 를 모른다", () => {
    expect(kindSx("entity", undefined, undefined, false, "wide").flex).toBe(CONTROL_KIND.entity.flex);
    expect(kindSx("entity", undefined, "form", true, "wide")).toMatchObject({ width: "100%", maxWidth: "none" });
    // wide 치수가 없는 종류는 크기를 무시하고 제 표를 쓴다.
    expect(kindSx("enum", undefined, undefined, true, "wide")).toMatchObject(ROW_KIND.enum);
  });

  it("size=wide 인 줄 칸은 뿌리에 data-filter-size 를 낸다 — 기본 칸과 줄 밖 칸은 안 낸다", () => {
    const { container } = inRow(
      <>
        <EntityCombobox size="wide" label="프로젝트" value="p1" onChange={() => {}} options={OPTIONS} />
        <EntityCombobox size="wide" multiple label="회차" value={["p1"]} onChange={() => {}} options={OPTIONS} />
        <EntityCombobox label="담당자" value="" onChange={() => {}} options={OPTIONS} />
      </>,
    );
    const cells = [...container.querySelectorAll("[data-filter-kind=entity]")];
    expect(cells.map((c) => c.getAttribute("data-filter-size"))).toEqual(["wide", "wide", null]);
    // 잘려도 전체 값은 title 이 든다 — 단일은 입력 상자, 다중은 한 줄 요약.
    expect(cells[0].querySelector("input").getAttribute("title")).toBe("ClovirAssist 플랫폼 전환");
    expect(cells[1].querySelector("[data-row-value]").getAttribute("title")).toBe("ClovirAssist 플랫폼 전환");
    const outside = outsideRow(<EntityCombobox size="wide" label="프로젝트" value="" onChange={() => {}} options={OPTIONS} />);
    expect(outside.container.querySelector("[data-filter-kind=entity]").hasAttribute("data-filter-size")).toBe(false);
  });

  it("부서 필터와 팀 고르개는 이름이 경로라 wide 가 기본이고, 호출부가 기본 칸으로 되돌릴 수 있다", () => {
    const departments = { options: [
      { id: "d1", name: "플랫폼개발팀", path: [{ name: "플랫폼본부" }, { name: "플랫폼개발팀" }] },
      { id: "d2", name: "서비스운영팀", path: [{ name: "플랫폼본부" }, { name: "서비스운영팀" }] },
    ] };
    const team = { options: departments.options };
    const { container } = inRow(
      <>
        <DepartmentFilter departments={departments} value="d1" onChange={() => {}} />
        <TeamSelect team={team} value="d2" onChange={() => {}} />
        <DepartmentFilter departments={departments} value="" onChange={() => {}} size="default" />
      </>,
    );
    const cells = [...container.querySelectorAll("[data-filter-kind=entity]")];
    expect(cells.map((c) => c.getAttribute("data-filter-size"))).toEqual(["wide", "wide", null]);
    expect(cells[0].querySelector("input").getAttribute("title")).toBe("플랫폼본부 › 플랫폼개발팀");
  });

  /* 테마 객체만 바꾸고 브라우저가 받는 CSS 에 안 넣는 실수를 막는다 — emotion 이 실제로 낸 규칙 글을 읽는다
     (`editable-body-edit-width.test.jsx` 와 같은 방법). */
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

  it("브라우저가 받는 CSS — 필터 면은 이름 붙은 크기 컨테이너이고, wide 칸의 계단만 그 이름으로 면의 폭을 묻는다", () => {
    const { container } = outsideRow(
      <FilterBar>
        <EntityCombobox size="wide" label="프로젝트" value="" onChange={() => {}} options={OPTIONS} />
        <EntityCombobox label="담당자" value="" onChange={() => {}} options={OPTIONS} />
      </FilterBar>,
    );
    const surface = container.querySelector("[data-filter-surface]");
    const surfaceRule = rulesFor(surface).find((r) => r.cond === "" && declaration(r, "container-type"));
    expect(surfaceRule, "필터 면이 크기 컨테이너를 열지 않는다").toBeTruthy();
    expect(declaration(surfaceRule, "container-type")).toBe("inline-size");
    expect(declaration(surfaceRule, "container-name")).toBe("filter-surface");
    // 면은 여전히 부모 폭을 다 쓰는 격자 블록이다 — 내용 폭으로 줄이는 선언이 없다.
    expect(declaration(surfaceRule, "display")).toBe("grid");
    expect(declaration(surfaceRule, "width")).toBeNull();

    const [wide, plain] = container.querySelectorAll("[data-filter-kind=entity]");
    expect(wide.getAttribute("data-filter-size")).toBe("wide");
    const wideRules = rulesFor(wide);
    const base = wideRules.find((r) => r.cond === "" && declaration(r, "--filter-wide"));
    expect(base, "wide 칸의 바닥 규칙이 없다").toBeTruthy();
    expect(declaration(base, "--filter-wide")).toBe("13rem");
    expect(declaration(base, "width")).toBe("var(--filter-wide)");
    expect(declaration(base, "flex")).toBe("0 0 var(--filter-wide)");
    const stepRules = wideRules.filter((r) => r.cond !== "" && declaration(r, "--filter-wide"));
    expect(stepRules.map((r) => [r.cond, declaration(r, "--filter-wide")])).toEqual([
      ["@container filter-surface (min-width: 76rem)", "16rem"],
      ["@container filter-surface (min-width: 96rem)", "20rem"],
    ]);
    // 폭을 바꾸는 규칙 가운데 뷰포트 매체 질의는 없다 — 기준은 면이다.
    expect(wideRules.filter((r) => r.cond.startsWith("@media") && declaration(r, "--filter-wide"))).toEqual([]);
    // 기본 칸은 13rem 고정이고 계단이 없다.
    expect(plain.hasAttribute("data-filter-size")).toBe(false);
    expect(rulesFor(plain).filter((r) => r.cond.startsWith("@container"))).toEqual([]);
    expect(rulesFor(plain).some((r) => r.cond === "" && declaration(r, "width") === "13rem")).toBe(true);
  });
});

describe("다중 선택 요약이 실제 선택과 같은 순서다", () => {
  it("고른 순서를 지킨다", () => {
    render(<RowSummary names={["나", "가", "다"]} />);
    expect(screen.getByText("나, 가, 다").getAttribute("title")).toBe("나, 가, 다");
  });
});

describe("줄 끝 동작 묶음의 띠 — 필터 칸과 같은 rem 34", () => {
  it("FilterActions 띠의 바닥 높이는 필터 칸(CONTROL.button)과 같은 rem 값이다 — px 36 이 아니다", () => {
    const { container } = outsideRow(<FilterActions><button type="button">필터 초기화</button></FilterActions>);
    const band = container.querySelector("[data-filter-actions]");
    const want = remPx(CONTROL.button);
    expect(want).toBe("2.125rem");
    expect(getComputedStyle(band).minHeight).toBe(want);
    // 칸 높이와 같은 토큰이다 — 칸 규칙(`filters.jsx` 줄 칸 34)과 따로 놀지 않는다.
    expect(getComputedStyle(band).minHeight).not.toBe(`${CONTROL.input}px`);
  });
});
