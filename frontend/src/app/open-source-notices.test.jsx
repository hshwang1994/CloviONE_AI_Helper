import React from "react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

vi.mock("../lib/api.js", () => ({ api: vi.fn(), setCsrf: () => {} }));

import { UserMenu } from "./UserMenu.jsx";
import { NOTICES } from "./OpenSourceNotices.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* 오픈소스 고지 (D-579) — 사용자 메뉴의 한 항목이 고지 목록을 연다. 정본 문서(`docs/THIRD_PARTY_NOTICES.md`)의 `## ` 머리마다 화면에
 * 항목이 하나 있어야 한다 — 문서에 고지를 더하고 화면을 잊으면(또는 그 반대) 이 시험이 잡는다. */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOC = path.resolve(HERE, "../../../docs/THIRD_PARTY_NOTICES.md");

describe("사용자 메뉴 → 오픈소스 고지", () => {
  it("메뉴 항목이 고지 목록을 연다", () => {
    render(
      <MemoryRouter>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <UserMenu name="김운영" userId="u1" me={{ display_name: "김운영" }} />
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: "김운영 메뉴" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "오픈소스 고지" }));
    const dialog = screen.getByRole("dialog", { name: "오픈소스 고지" });
    for (const n of NOTICES) {
      expect(within(dialog).getByText(n.name)).toBeInTheDocument();
      expect(within(dialog).getByRole("link", { name: n.url })).toHaveAttribute("href", n.url);
    }
    expect(within(dialog).getByText(/「마블 룰렛」은 lazygyu 의 상표이고/)).toBeInTheDocument();
  });
});

describe("문서와 화면이 어긋나지 않는다", () => {
  it("문서의 `## ` 머리마다 화면 항목이 있고, 화면 항목마다 문서 머리가 있다", () => {
    const headings = fs.readFileSync(DOC, "utf-8").split(/\r?\n/).filter((l) => l.startsWith("## ")).map((l) => l.slice(3).trim());
    expect(headings.length).toBeGreaterThanOrEqual(4);
    for (const h of headings) {
      expect(NOTICES.some((n) => h.startsWith(n.doc)), `화면에 없는 고지: ${h}`).toBe(true);
    }
    for (const n of NOTICES) {
      expect(headings.some((h) => h.startsWith(n.doc)), `문서에 없는 고지: ${n.doc}`).toBe(true);
    }
  });
});
