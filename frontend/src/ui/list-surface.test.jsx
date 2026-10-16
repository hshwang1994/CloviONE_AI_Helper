import React from "react";
import { describe, it, expect, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { DataTable, EmptyState, TitleCell } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 목록 판 — 표가 자기 자리를 안다 (UI 3차 · 조합 계약 C-3).
 *
 * 지난 회차까지 주 목록 스무 곳이 `Card`(여백 20)/`ListCard` 로 표를 감쌌다. 머리 줄은 판 가장자리에서 떨어졌고,
 * 받은 건수와 「더 보기」는 판 밖 가운데 상자(`ListFooter`), 숨긴 열 안내는 표 위, 일괄 동작은 화면 머리였다. 이 파일이
 * 고정하는 것은 **구조**다:
 *
 *   1. surface — 판이 곧 표 상자다. 첫 줄이 표 상자(머리 줄 포함), 마지막 줄이 발이다. 발은 표 상자 **밖**이다.
 *   2. 발 = 왼쪽 받은 건수 문장 · 덧붙는 한 토막, 오른쪽 선택 묶음 · 「더 보기」. 그릴 것이 없으면 발이 없다.
 *   3. 무한 스크롤 센티널은 **표 끝 흐름**이다 — sticky 발 안에 두면 늘 보이는 자리라 자동 로딩이 멈추지 않는다.
 *   4. 불러오는 중 · 빈 목록은 판 안(여백 20)이다. card 는 판 여백을 거슬러 가장자리까지, plain 은 판을 안 그린다.
 * 실제 기하(머리가 판 윗변에 붙는가 · 발 높이 44 · sticky 발이 행 초점을 가리는가)는 실브라우저
 * `composition_checks.py::list_surface` 와 keyboard 하네스가 잰다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

const cols = [
  { key: "title", label: "제목", type: "title", sortable: true },
  { key: "status", label: "상태", type: "status", sortable: true, filter: { kind: "enum", field: "status" } },
  { key: "due", label: "마감", type: "date" },
];
const rows = [
  { id: 1, title: "배포 점검", status: "계획", due: "2026-09-20" },
  { id: 2, title: "로그 정리", status: "진행 중", due: "2026-09-21" },
  { id: 3, title: "문서 이관", status: "완료", due: "2026-09-22" },
];
const intersect = async () => { await act(async () => { globalThis.__intersect(); }); };

describe("surface — 판이 곧 표 상자다", () => {
  it("표 상자가 판의 첫 줄이고 발이 마지막 줄이다 — 발은 표 상자 밖이다", () => {
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 40, loaded: 3, hasNext: true, onMore: () => {} }} />,
    );
    const plate = container.querySelector("[data-list-surface]");
    expect(plate).not.toBeNull();
    expect(plate.getAttribute("data-table-placement")).toBe("surface");
    expect(plate.hasAttribute("data-list-state")).toBe(false);
    const box = plate.querySelector(".MuiTableContainer-root");
    expect(plate.firstElementChild).toBe(box);
    expect(box.querySelector("thead tr")).not.toBeNull();
    const foot = plate.querySelector("[data-list-footer]");
    expect(plate.lastElementChild).toBe(foot);
    expect(box.contains(foot)).toBe(false);
    expect(container.querySelector("tfoot")).toBeNull();
    // 판 여백이 없다 — 머리가 판 가장자리에 붙는다. 판은 sticky 발이 서도록 넘침을 자르지 않는다.
    const cs = getComputedStyle(plate);
    expect(cs.paddingTop).toMatch(/^0(px|rem)?$/);
    expect(cs.paddingLeft).toMatch(/^0(px|rem)?$/);
    expect(cs.overflow).toBe("visible");
  });

  it("발은 긴 목록에서 화면 아래에 따라온다(sticky) — 판 안 목록만", () => {
    const { container, unmount } = ui(<DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} />);
    const foot = container.querySelector("[data-list-footer]");
    expect(getComputedStyle(foot).position).toBe("sticky");
    expect(getComputedStyle(foot).bottom).toMatch(/^0(px)?$/);
    expect(foot.hasAttribute("data-list-footer-sticky")).toBe(true);
    unmount();
    const card = ui(<DataTable placement="card" columns={cols} rows={rows} rowKey={(r) => r.id} />);
    const cardFoot = card.container.querySelector("[data-list-footer]");
    expect(getComputedStyle(cardFoot).position).not.toBe("sticky");
    expect(cardFoot.hasAttribute("data-list-footer-sticky")).toBe(false);
  });

  it("쪽을 나누지 않는 목록은 받은 행 수로 같은 문장을 쓰고, 두 줄 미만이면 발을 안 그린다", () => {
    const { container, rerender } = ui(<DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} />);
    expect(container.querySelector("[data-list-footer]").textContent).toBe("전체 3건 중 3건 표시");
    rerender(<ThemeModeProvider><DataTable placement="surface" columns={cols} rows={rows.slice(0, 1)} rowKey={(r) => r.id} /></ThemeModeProvider>);
    expect(container.querySelector("[data-list-footer]")).toBeNull();
    // 표 상자 모서리는 판 안쪽 반경으로 잘린다 — 발이 없으면 아래 모서리도 표 상자가 든다.
    expect(container.querySelector("[data-list-surface]").lastElementChild).toBe(container.querySelector(".MuiTableContainer-root"));
  });

  it("덧붙는 한 토막은 발 왼쪽 문장 뒤에 선다", () => {
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 12, loaded: 3, onMore: () => {} }} note="검색어로 좁혀 보세요." />,
    );
    const foot = container.querySelector("[data-list-footer]");
    const noteEl = foot.querySelector("[data-list-note]");
    expect(noteEl.textContent).toBe("검색어로 좁혀 보세요.");
    expect(within(foot).getByText("전체 12건 중 3건 표시").compareDocumentPosition(noteEl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("결과 문장을 스스로 가진 목록은 그 문장이 발 문장이다 — 받은 행 수 문장을 한 번 더 세우지 않는다", () => {
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} note="총 12건 가운데 첫 3건을 보여 줍니다." />,
    );
    const foot = container.querySelector("[data-list-footer]");
    expect(foot.textContent).toBe("총 12건 가운데 첫 3건을 보여 줍니다.");
    expect(within(foot).queryByText(/받았습니다/)).toBeNull();
  });
});

describe("발 — 「더 보기」와 자동 로딩", () => {
  it("「더 보기」는 30 보조 단추이고 누르면 다음 묶음을 부른다", async () => {
    const onMore = vi.fn();
    ui(<DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 40, loaded: 3, hasNext: true, onMore, moreLabel: "티켓 더 보기" }} />);
    const more = screen.getByRole("button", { name: "티켓 더 보기" });
    expect(more.className).toContain("MuiButton-sizeSmall");
    expect(more.className).not.toContain("MuiButton-contained");
    await userEvent.click(more);
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("🔴 센티널은 표 끝 흐름에 선다 — sticky 발 안에 없다", () => {
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 40, loaded: 3, hasNext: true, onMore: () => {} }} />,
    );
    const plate = container.querySelector("[data-list-surface]");
    const foot = plate.querySelector("[data-list-footer]");
    const sentinel = plate.querySelector("[data-list-sentinel]");
    expect(sentinel).not.toBeNull();
    expect(foot.contains(sentinel)).toBe(false);
    expect(sentinel.parentElement).toBe(plate);
    expect(sentinel.nextElementSibling).toBe(foot);
    expect(sentinel.getAttribute("aria-hidden")).toBe("true");
    // 자리를 안 먹는다 — MUI sx 의 1 이하 숫자는 백분율이다(`"1px"` 로 적는다).
    expect(getComputedStyle(sentinel).height).toBe("1px");
  });

  it("센티널이 보이면 다음 묶음을 부르고, 받는 중에는 다시 안 부른다", async () => {
    const onMore = vi.fn();
    const { rerender } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 40, loaded: 3, hasNext: true, onMore }} />,
    );
    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);
    rerender(
      <ThemeModeProvider>
        <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 40, loaded: 3, hasNext: true, isFetchingNext: true, onMore }} />
      </ThemeModeProvider>,
    );
    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("더 받을 것이 없으면 센티널도 「더 보기」도 없다", async () => {
    const onMore = vi.fn();
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 3, loaded: 3, hasNext: false, onMore }} />,
    );
    expect(container.querySelector("[data-list-sentinel]")).toBeNull();
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
  });

  it("autoMaxRows 를 넘으면 자동이 멎고 조건을 좁히라고 말한다 — 단추로는 계속 받는다", async () => {
    const onMore = vi.fn();
    ui(<DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 900, loaded: 3, hasNext: true, onMore, autoMaxRows: 3 }} />);
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
    expect(screen.getByText(/조건을 좁히면 더 빨리 찾을 수 있습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));
    expect(onMore).toHaveBeenCalledTimes(1);
  });
});

describe("발 — 선택 묶음", () => {
  it("선택이 없으면 오른쪽을 비우고, 있으면 「N개 선택」 · 일괄 동작 · 「해제」가 한 toolbar 로 선다", async () => {
    const onClear = vi.fn();
    const action = <button type="button">선택 삭제</button>;
    const { container, rerender } = ui(
      <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} selection={{ count: 0, onClear, actions: action }} />,
    );
    expect(screen.queryByRole("toolbar")).toBeNull();
    rerender(
      <ThemeModeProvider>
        <DataTable placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id} selection={{ count: 2, onClear, actions: action }} />
      </ThemeModeProvider>,
    );
    const toolbar = screen.getByRole("toolbar", { name: "일괄 작업" });
    expect(container.querySelector("[data-list-footer]").contains(toolbar)).toBe(true);
    expect(toolbar.hasAttribute("data-list-selection")).toBe(true);
    expect(toolbar).toHaveTextContent("2개 선택");
    expect(within(toolbar).getByRole("button", { name: "선택 삭제" })).toBeInTheDocument();
    await userEvent.click(within(toolbar).getByRole("button", { name: "선택 해제" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("한 줄짜리 목록도 고르면 발이 선다 — 할 일이 있으면 그릴 것이 있다", () => {
    const { container } = ui(
      <DataTable placement="surface" columns={cols} rows={rows.slice(0, 1)} rowKey={(r) => r.id} selection={{ count: 1, onClear: () => {}, actions: null }} />,
    );
    const foot = container.querySelector("[data-list-footer]");
    expect(foot).not.toBeNull();
    expect(within(foot).getByRole("toolbar", { name: "일괄 작업" })).toHaveTextContent("1개 선택");
  });
});

describe("불러오는 중 · 빈 목록 · card · plain", () => {
  it("불러오는 중과 빈 목록은 판 안 여백 20 에 선다 — 표가 없으니 판 여백이 있다", () => {
    const { container, rerender } = ui(<DataTable placement="surface" columns={cols} rows={[]} loading />);
    let plate = container.querySelector("[data-list-surface]");
    expect(plate.getAttribute("data-list-state")).toBe("loading");
    expect(plate.querySelector("table")).toBeNull();
    expect(getComputedStyle(plate).paddingTop).not.toMatch(/^0(px|rem)?$/);
    rerender(
      <ThemeModeProvider>
        <DataTable placement="surface" columns={cols} rows={[]} emptyState={<EmptyState layout="region" title="검색 조건에 맞는 항목이 없습니다" />} />
      </ThemeModeProvider>,
    );
    plate = container.querySelector("[data-list-surface]");
    expect(plate.getAttribute("data-list-state")).toBe("empty");
    expect(within(plate).getByText("검색 조건에 맞는 항목이 없습니다")).toBeInTheDocument();
    expect(plate.querySelector("[data-list-footer]")).toBeNull();
  });

  it("비었는데 서버에 더 있으면 「더 보기」는 판 안에 남는다", () => {
    ui(<DataTable placement="surface" columns={cols} rows={[]} list={{ total: 50, loaded: 20, hasNext: true, onMore: () => {} }} />);
    expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
  });

  it("card 는 판을 새로 그리지 않고 판 여백을 거슬러 편다 — 목록 판 표식이 없다", () => {
    const { container } = ui(<DataTable placement="card" columns={cols} rows={rows} rowKey={(r) => r.id} />);
    const band = container.querySelector("[data-table-placement='card']");
    expect(band).not.toBeNull();
    expect(container.querySelector("[data-list-surface]")).toBeNull();
    expect(band.querySelector("[data-list-footer]")).not.toBeNull();
    expect(getComputedStyle(band).marginLeft).toMatch(/^calc\(-/);
  });

  it("plain(기본)은 판도 발도 그리지 않는다 — 모달 · 서랍 · 보호 화면의 표는 그대로다", () => {
    const { container } = ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
    expect(container.querySelector("[data-table-placement='plain']")).not.toBeNull();
    expect(container.querySelector("[data-list-surface]")).toBeNull();
    expect(container.querySelector("[data-list-footer]")).toBeNull();
    expect(container.querySelector(".MuiCard-root")).toBeNull();
  });

  it("plain 도 `list` 를 주면 발을 그린다 — 따라오지는 않는다", () => {
    const { container } = ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} list={{ total: 9, loaded: 3, hasNext: true, onMore: () => {} }} />);
    const foot = container.querySelector("[data-list-footer]");
    expect(foot.textContent).toContain("전체 9건 중 3건 표시");
    expect(getComputedStyle(foot).position).not.toBe("sticky");
  });
});

describe("머리 줄 — 함몰면과 표지", () => {
  it("고정 머리도 함몰면이다 — 판 면(흰 줄)으로 덮지 않는다", () => {
    const { container } = ui(<DataTable placement="surface" stickyHeader columns={cols} rows={rows} rowKey={(r) => r.id} />);
    const th = container.querySelector("thead th");
    const plate = container.querySelector("[data-list-surface]");
    expect(getComputedStyle(th).backgroundColor).not.toBe(getComputedStyle(plate).backgroundColor);
    expect(getComputedStyle(th).backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  });

  it("정렬 표지는 이름 옆 글리프이고 활성 열은 방향 표지를 든다 · 필터 표지는 조건이 걸리는 열에만", () => {
    const { container } = ui(
      <DataTable
        placement="surface" columns={cols} rows={rows} rowKey={(r) => r.id}
        sort={{ key: "status", dir: "desc" }} onSort={() => {}} filters={{}} onFilter={() => {}}
      />,
    );
    const [titleTh, statusTh, dueTh] = container.querySelectorAll("thead th");
    // 정렬 표지는 정렬 단추 **안**, 이름 뒤다.
    const titleGlyph = titleTh.querySelector("[data-head-glyph='sort']");
    expect(titleGlyph.tagName.toLowerCase()).toBe("svg");
    expect(titleGlyph.closest("button")).toBe(within(titleTh).getByText("제목").closest("button"));
    expect(titleTh.getAttribute("aria-sort")).toBe("none");
    expect(statusTh.getAttribute("aria-sort")).toBe("descending");
    expect(statusTh.querySelector("[data-head-glyph='sort']")).not.toBeNull();
    // 필터 표지는 조건이 걸릴 수 있는 열(상태)에만 선다.
    expect(statusTh.querySelector("[data-head-glyph='filter']")).not.toBeNull();
    expect(titleTh.querySelector("[data-head-glyph='filter']")).toBeNull();
    expect(dueTh.querySelector("[data-head-glyph]")).toBeNull();
    // 필터 단추는 누르는 높이 30 을 유지하고 이름이 있다.
    expect(within(statusTh).getByRole("button", { name: "상태 필터" })).toBeInTheDocument();
    // 활성 열의 표지는 강조색, 아닌 열은 흐린 잉크다 — 둘이 같은 색이면 어느 축인지 안 보인다.
    expect(getComputedStyle(statusTh.querySelector("[data-head-glyph='sort']")).color)
      .not.toBe(getComputedStyle(titleGlyph).color);
  });
});

describe("TitleCell — 행을 여는 이름", () => {
  it("여는 동작이 있으면 진짜 단추이고 링크색 600 이다", async () => {
    const onOpen = vi.fn();
    ui(<TitleCell title="배포 점검" onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "배포 점검" });
    expect(button.getAttribute("data-title-cell")).toBe("button");
    expect(button.getAttribute("title")).toBe("배포 점검");
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("열리지 않는 이름은 링크처럼 칠하지 않는다 · 행에 링크가 걸린 표는 색만 링크다", () => {
    const { rerender } = ui(<TitleCell title="" />);
    const plainText = screen.getByText("제목 없음");
    expect(plainText.getAttribute("data-title-cell")).toBe("text");
    const inkColor = getComputedStyle(plainText).color;
    rerender(<ThemeModeProvider><TitleCell title="문서 이관" link /></ThemeModeProvider>);
    const linked = screen.getByText("문서 이관");
    expect(linked.getAttribute("data-title-cell")).toBe("link");
    expect(screen.queryByRole("button")).toBeNull();
    expect(getComputedStyle(linked).color).not.toBe(inkColor);
  });
});
