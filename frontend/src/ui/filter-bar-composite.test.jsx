import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FilterBar, FilterConditionLine, FilterToggle } from "./FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "./filters.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 필터 바 조합 부품 — 목록 화면 탐색 줄의 **한 벌** (UI 3차 · 조합 계약 C-1).
 *
 * 지난 회차까지 이 자리는 낱개 부품을 화면 열여섯 곳이 제각각 조립했다. 티켓 · 게시판은 칩 줄과 결과 줄을 필터 면
 * **밖**에 두 줄로 세웠고, 검색만 한 줄을 쓰고 필터를 다음 줄로 내린 화면이 다섯이었고, 「필터 지우기」는 줄 끝 동작
 * 묶음에서 화면마다 다른 크기로 섰다. 이 파일이 지키는 것은 조합이다:
 *
 *   1. 한 줄 = 검색 → 내용 칸 → `end` 묶음. 검색 · 칸 · 끝 묶음이 **같은 줄 요소**의 자식이고 그 순서다.
 *   2. 조건 칩이 있을 때만 같은 면 **안** 마지막 줄이 조건 줄이다. 면 밖에는 아무것도 그리지 않는다.
 *   3. 조건 수 = 칩 수. 화면이 조건 수를 따로 넘길 길이 없다.
 *   4. 지우기 · 덧붙는 글자 단추는 조건 줄 안 30 글자 단추다(테두리 상자가 아니다).
 *   5. 서랍 안 필터(`divider=false`)는 아래 실선이 없다.
 * 실제 기하(한 줄에 설 자리가 있는데 줄이 바뀌지 않는가 · 아래 실선 · 칩 높이)는 브라우저 검사
 * `composition_checks.py::filter_composition` 이 잰다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

const CHIPS = [
  { key: "q", label: "검색: 배포", onDelete: vi.fn() },
  { key: "status", label: "상태: 계획", onDelete: vi.fn() },
];

describe("FilterBar — 한 줄", () => {
  it("검색 · 내용 칸 · 끝 묶음이 한 줄 요소 안에서 그 순서로 선다", () => {
    const { container } = ui(
      <FilterBar
        search={<SearchBox value="" onSearch={() => {}} ariaLabel="티켓 검색" />}
        end={<FilterToggle pressed={false} onClick={() => {}}>내 티켓만</FilterToggle>}
      >
        <EntityCombobox label="프로젝트" value="" onChange={() => {}} options={[{ value: "p", label: "포털 개편" }]} />
        <FilterSelect label="상태" value="" onChange={() => {}} options={["계획"]} />
      </FilterBar>,
    );
    const surface = container.querySelector("[data-filter-surface][data-filter-bar]");
    expect(surface).not.toBeNull();
    const rows = surface.querySelectorAll("[data-filter-row]");
    expect(rows).toHaveLength(1);
    const row = rows[0];
    const kids = [...row.children];
    expect(kids[0].getAttribute("data-filter-kind")).toBe("search");
    expect(kids[1].getAttribute("data-filter-kind")).toBe("entity");
    expect(kids[2].getAttribute("data-filter-kind")).toBe("enum");
    expect(kids[kids.length - 1].contains(screen.getByRole("button", { name: "내 티켓만" }))).toBe(true);
    // 칸 안 이름 — 줄 칸 문맥이 깔린다(`FilterRowContext`).
    expect(row.querySelectorAll("[data-prefix-label]")).toHaveLength(2);
    // 조건이 없으면 둘째 줄이 없다.
    expect(surface.querySelector("[data-condition-line]")).toBeNull();
    expect(surface.children).toHaveLength(1);
  });

  it("검색이 없고 끝 묶음만 있어도 줄은 하나다", () => {
    const { container } = ui(<FilterBar end={<FilterToggle pressed onClick={() => {}}>보관된 계정 보기</FilterToggle>} />);
    const surface = container.querySelector("[data-filter-surface]");
    expect(surface.querySelectorAll("[data-filter-row]")).toHaveLength(1);
    expect(surface.querySelector("[data-filter-kind=search]")).toBeNull();
    expect(screen.getByRole("button", { name: "보관된 계정 보기" })).toHaveAttribute("aria-pressed", "true");
  });

  it("아래 실선은 목록 위 필터 바에만 긋고, 서랍 안(divider=false)은 긋지 않는다", () => {
    const { container, rerender } = ui(<FilterBar search={<SearchBox value="" onSearch={() => {}} ariaLabel="검색" />} />);
    expect(getComputedStyle(container.querySelector("[data-filter-surface]")).borderBottomWidth).toBe("1px");
    rerender(<ThemeModeProvider><FilterBar divider={false} search={<SearchBox value="" onSearch={() => {}} ariaLabel="검색" />} /></ThemeModeProvider>);
    expect(getComputedStyle(container.querySelector("[data-filter-surface]")).borderBottomWidth).not.toBe("1px");
  });
});

describe("FilterBar — 조건 줄", () => {
  it("칩이 있으면 같은 면 안 마지막 줄에 「검색 결과 M건」 → 칩 → 지우기 → 덧붙는 단추 순서로 선다", () => {
    const onClear = vi.fn();
    const onAll = vi.fn();
    const { container } = ui(
      <FilterBar
        search={<SearchBox value="배포" onSearch={() => {}} ariaLabel="검색" />}
        conditions={{ chips: CHIPS, total: 1234, onClearAll: onClear, clearLabel: "필터 초기화", extraAction: { label: "전체 보기", onClick: onAll } }}
      >
        <FilterSelect label="상태" value="계획" onChange={() => {}} options={["계획"]} />
      </FilterBar>,
    );
    const surface = container.querySelector("[data-filter-surface]");
    const line = surface.querySelector("[data-condition-line]");
    expect(line).not.toBeNull();
    expect(surface.lastElementChild).toBe(line);
    const count = line.querySelector("[data-condition-count]");
    expect(count.textContent).toBe("검색 결과 1,234건");
    expect(count).toHaveAttribute("aria-live", "polite");
    const kids = [...line.children];
    expect(kids[0]).toBe(count);
    expect(kids.filter((k) => k.hasAttribute("data-condition-chip")).map((k) => k.textContent)).toEqual(["검색: 배포", "상태: 계획"]);
    const clear = within(line).getByRole("button", { name: "필터 초기화" });
    const all = within(line).getByRole("button", { name: "전체 보기" });
    expect(clear).toHaveAttribute("data-filter-clear");
    expect(clear.className).toContain("MuiButton-text");
    expect(clear.className).toContain("MuiButton-sizeSmall");
    expect(all.className).toContain("MuiButton-text");
    expect(kids.indexOf(clear)).toBeGreaterThan(kids.indexOf(kids.filter((k) => k.hasAttribute("data-condition-chip")).pop()));
    expect(kids.indexOf(all)).toBeGreaterThan(kids.indexOf(clear));
    // 면 밖에는 아무것도 없다.
    expect(container.querySelector("[data-result-line]")).toBeNull();
    expect(surface.parentElement.children).toHaveLength(1);
  });

  it("조건 수는 칩 수다 — 칩이 없는 조건을 셀 길이가 없다", () => {
    const { container, rerender } = ui(<FilterConditionLine total={5} chips={[CHIPS[0]]} conditions={["a", "b", "c"]} />);
    expect(container.querySelector("[data-condition-count]").textContent).toBe("검색 결과 5건");
    rerender(<ThemeModeProvider><FilterConditionLine total={5} chips={[]} /></ThemeModeProvider>);
    expect(container.querySelector("[data-condition-line]")).toBeNull();
    // 이름이 없는 칩은 칩이 아니다.
    rerender(<ThemeModeProvider><FilterConditionLine total={5} chips={[{ key: "x", label: "" }, CHIPS[1]]} /></ThemeModeProvider>);
    expect(container.querySelectorAll("[data-condition-chip]")).toHaveLength(1);
    expect(container.querySelector("[data-condition-count]").textContent).toBe("검색 결과 5건");
  });

  it("결과를 아직 모르면 수를 지어내지 않는다 · 단위를 바꿀 수 있다", () => {
    const { container, rerender } = ui(<FilterConditionLine total={null} chips={CHIPS} />);
    expect(container.querySelector("[data-condition-count]").textContent).toBe("세는 중…");
    rerender(<ThemeModeProvider><FilterConditionLine total={3} unit="명" chips={CHIPS} /></ThemeModeProvider>);
    expect(container.querySelector("[data-condition-count]").textContent).toBe("검색 결과 3명");
  });

  it("칩의 지우기 · 줄의 지우기 · 덧붙는 단추가 넘긴 동작을 부른다", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const onClear = vi.fn();
    const onAll = vi.fn();
    ui(
      <FilterConditionLine
        total={9}
        chips={[{ key: "status", label: "상태: 계획", onDelete }]}
        onClearAll={onClear}
        clearLabel="필터 초기화"
        extraAction={{ label: "전체 보기", onClick: onAll }}
      />,
    );
    const chip = screen.getByText("상태: 계획").closest("[data-condition-chip]");
    await user.click(chip.querySelector(".MuiChip-deleteIcon"));
    expect(onDelete).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "필터 초기화" }));
    expect(onClear).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "전체 보기" }));
    expect(onAll).toHaveBeenCalledTimes(1);
  });

  it("지우기를 안 넘기면 지우기 단추가 없다 — 아무 일도 안 하는 단추를 두지 않는다", () => {
    ui(<FilterConditionLine total={9} chips={CHIPS} />);
    expect(screen.queryByRole("button", { name: /지우기|초기화/ })).toBeNull();
    expect(document.querySelector("[data-filter-clear]")).toBeNull();
  });

  it("긴 조건값은 칩 안에서 말줄임되고 전체 값을 title 로 든다", () => {
    const long = "프로젝트: ClovirAssist 플랫폼 전환 및 자체 데이터 이관";
    ui(<FilterConditionLine total={1} chips={[{ key: "p", label: long, onDelete: () => {} }]} />);
    expect(screen.getByText(long).closest("[data-condition-chip]")).toHaveAttribute("title", long);
  });
});

/* 「추가 필터」(D-596) — 덜 쓰는 조건 칸을 접는다. 감사 로그가 첫 소비처다(대상 ID · 작업 · 문의 번호). */
describe("FilterBar — 추가 필터 접기", () => {
  function MoreBar({ active = 0 }) {
    return (
      <FilterBar
        search={<SearchBox value="" onSearch={() => {}} placeholder="검색" ariaLabel="검색" />}
        more={{ active, fields: [<FilterSelect key="r" label="문의 번호" value="" onChange={() => {}} options={["a"]} />] }}
      >
        <FilterSelect label="결과" value="" onChange={() => {}} options={["성공", "실패"]} />
      </FilterBar>
    );
  }

  it("접힌 채로 시작하고, 단추가 칸을 여닫는다 — 접힌 칸은 DOM 에 없다", async () => {
    ui(<MoreBar />);
    const toggle = screen.getByRole("button", { name: "추가 필터" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("문의 번호")).toBeNull();
    // 단추는 첫 줄에 선다 — 칸 흐름(검색 → 조건 칸) 뒤다.
    expect(toggle.closest("[data-filter-row]")).toBe(screen.getByLabelText("결과").closest("[data-filter-row]"));

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const field = screen.getByLabelText("문의 번호");
    const moreRow = field.closest("[data-filter-more]");
    expect(moreRow).not.toBeNull();
    expect(toggle).toHaveAttribute("aria-controls", moreRow.id);

    await userEvent.click(toggle);
    expect(screen.queryByLabelText("문의 번호")).toBeNull();
  });

  it("접힌 칸에 조건이 걸려 있으면 처음부터 펼치고, 단추 이름이 걸린 수를 말한다", () => {
    ui(<MoreBar active={1} />);
    const toggle = screen.getByRole("button", { name: "추가 필터 1" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("문의 번호")).toBeInTheDocument();
  });

  it("사람이 접은 것은 그대로 두되, 접힌 칸에 조건이 새로 걸리면 다시 펼친다(딥링크 · 저장된 뷰)", async () => {
    const { rerender } = ui(<MoreBar active={1} />);
    await userEvent.click(screen.getByRole("button", { name: "추가 필터 1" }));
    expect(screen.queryByLabelText("문의 번호")).toBeNull();
    rerender(<ThemeModeProvider><MoreBar active={1} /></ThemeModeProvider>);
    expect(screen.queryByLabelText("문의 번호")).toBeNull();
    rerender(<ThemeModeProvider><MoreBar active={2} /></ThemeModeProvider>);
    expect(screen.getByRole("button", { name: "추가 필터 2" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("문의 번호")).toBeInTheDocument();
  });

  it("`more` 를 안 주면 단추도 둘째 줄도 없다", () => {
    ui(<FilterBar><FilterSelect label="결과" value="" onChange={() => {}} options={["성공"]} /></FilterBar>);
    expect(screen.queryByRole("button", { name: /추가 필터/ })).toBeNull();
    expect(document.querySelector("[data-filter-more]")).toBeNull();
  });
});
