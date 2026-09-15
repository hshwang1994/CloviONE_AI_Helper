import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { DataTable, RowActions } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 행 동작 — 표 행 안의 단추 묶음 (핸드오프 RULES §5 · 조합 계약 C-4).
 *
 * 지난 회차까지 행 동작은 열 `render` 마다 손으로 그렸다. 미할당 「나에게 배정」 · 휴지통 「복원」 · 승인 「승인」이 행마다
 * **채움**이라 목록 한 화면에 채움이 스무 개 섰고, 화면의 할 일(머리의 채움 하나)이 어디인지 사라졌다. 동작이 셋인 행은
 * 칸 안에 단추 셋을 나란히 세웠다. 이 파일이 지키는 것:
 *
 *   1. 행 안 단추는 30(작은 단추)이고 채움이 없다 — 보조(default)와 파괴(danger) 둘뿐이다.
 *   2. 둘을 넘으면 「더 보기」 하나로 접는다. 파괴 항목은 메뉴에서도 파괴로 읽힌다.
 *   3. 아이콘 항목은 이름을 `aria-label` 로 든다.
 *   4. `data-row-actions` 표식이 실브라우저 `row_actions` 검사의 대상이다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("RowActions", () => {
  it("둘 이하면 30 단추로 서고, 채움으로 부탁해도 보조로 선다", async () => {
    const claim = vi.fn();
    const { container } = ui(
      <RowActions
        actions={[
          { key: "claim", label: "나에게 배정", onClick: claim, variant: "primary" },
          { key: "edit", label: "수정", onClick: () => {} },
        ]}
      />,
    );
    const group = container.querySelector("[data-row-actions]");
    expect(group).not.toBeNull();
    const buttons = within(group).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["나에게 배정", "수정"]);
    for (const b of buttons) {
      expect(b.className).toContain("MuiButton-sizeSmall");
      expect(b.className).not.toContain("MuiButton-containedPrimary");
    }
    await userEvent.click(buttons[0]);
    expect(claim).toHaveBeenCalledTimes(1);
  });

  it("파괴 동작은 파괴 모양이다", () => {
    ui(<RowActions actions={[{ key: "restore", label: "복원", onClick: () => {} }, { key: "purge", label: "영구 삭제", variant: "danger", onClick: () => {} }]} />);
    const restore = screen.getByRole("button", { name: "복원" });
    const purge = screen.getByRole("button", { name: "영구 삭제" });
    expect(purge.className).not.toBe(restore.className);
    expect(purge.className).not.toContain("MuiButton-contained");
  });

  it("셋 이상이면 「더 보기」 하나로 접고, 메뉴 안에서 항목을 부른다", async () => {
    const a = vi.fn();
    const c = vi.fn();
    const { container } = ui(
      <RowActions
        ariaLabel="프롬프트 작업 더 보기"
        actions={[
          { key: "a", label: "게시", onClick: a },
          { key: "b", label: "보관", onClick: () => {} },
          { key: "c", label: "삭제", onClick: c, variant: "danger" },
        ]}
      />,
    );
    const group = container.querySelector("[data-row-actions]");
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute("aria-label", "프롬프트 작업 더 보기");
    expect(buttons[0]).toHaveAttribute("aria-haspopup", "menu");
    expect(buttons[0].className).toContain("MuiIconButton-sizeSmall");
    await userEvent.click(buttons[0]);
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["게시", "보관", "삭제"]);
    await userEvent.click(within(menu).getByRole("menuitem", { name: "게시" }));
    expect(a).toHaveBeenCalledTimes(1);
    expect(c).not.toHaveBeenCalled();
  });

  it("아이콘 항목은 이름을 aria-label 로 든다", () => {
    ui(<RowActions actions={[{ key: "edit", label: "수정", ariaLabel: "수정: 배포 점검", icon: <span aria-hidden="true">✎</span>, onClick: () => {} }]} />);
    const b = screen.getByRole("button", { name: "수정: 배포 점검" });
    expect(b.className).toContain("MuiIconButton-sizeSmall");
  });

  it("동작이 없으면 아무것도 그리지 않는다", () => {
    const { container } = ui(<RowActions actions={[null, false]} />);
    expect(container.querySelector("[data-row-actions]")).toBeNull();
  });

  it("표 행 안에서 행 클릭(상세 열기)으로 번지지 않는다", async () => {
    const onRow = vi.fn();
    const onEdit = vi.fn();
    ui(
      <DataTable
        placement="surface"
        columns={[
          { key: "title", label: "제목", type: "title" },
          { key: "_actions", label: "작업", type: "actions", render: () => <RowActions actions={[{ key: "edit", label: "수정", onClick: onEdit }]} /> },
        ]}
        rows={[{ id: 1, title: "배포 점검" }]}
        rowKey={(r) => r.id}
        onRow={onRow}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "수정" }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onRow).not.toHaveBeenCalled();
  });
});
