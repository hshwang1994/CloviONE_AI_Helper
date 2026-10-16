import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 메일 미리 보기의 테마 (D-571) — 라이트 · 다크 세그먼티드가 서버에 그 모양을 묻고, 틀의 바탕을 서버가 준 메일 바탕색으로 깐다.
 *   1) 처음은 라이트이고 주소에 테마를 싣지 않는다(서버 기본값).
 *   2) 다크를 고르면 `?scheme=dark` 로 다시 묻고 틀이 다크 HTML 과 그 바탕을 받는다. 라이트로 돌아오면 다시 기본 주소다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { MailPreview } from "./MailPreview.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const LIGHT = {
  kind: "ticket_assigned", scheme: "light", background: "#F5F6FB", subject: "[ClovirAssist] ABC-12 담당자로 지정",
  text: "평문 본문입니다.", html: "<!DOCTYPE html><p>라이트 본문</p>",
};
const DARK = { ...LIGHT, scheme: "dark", background: "#0A0C16", html: '<!DOCTYPE html><body data-ogsc=""><p>다크 본문</p></body>' };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p === "/api/admin/mail/templates") return Promise.resolve({ items: [{ key: "ticket_assigned", label: "티켓 배정" }] });
    if (p.endsWith("/preview?scheme=dark")) return Promise.resolve(DARK);
    if (p.endsWith("/preview")) return Promise.resolve(LIGHT);
    return Promise.resolve({});
  });
});

function renderPreview() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MailPreview />
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const previewCalls = () => apiMock.mock.calls.map((c) => String(c[0])).filter((p) => p.includes("/preview"));
const frame = () => screen.getByTestId("mail-preview-frame");

describe("메일 미리 보기 — 테마", () => {
  it("처음은 라이트이고 테마를 주소에 싣지 않는다", async () => {
    renderPreview();
    await screen.findByTestId("mail-preview-frame");
    expect(frame().getAttribute("srcdoc")).toContain("라이트 본문");
    expect(frame()).toHaveAttribute("data-scheme", "light");
    expect(frame()).toHaveStyle({ backgroundColor: "#F5F6FB" });
    expect(screen.getByRole("tablist", { name: "미리 보기 테마" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "라이트" })).toHaveAttribute("aria-selected", "true");
    expect(previewCalls()).toEqual(["/api/admin/mail/templates/ticket_assigned/preview"]);
  });

  it("다크를 고르면 서버에 다크를 묻고 틀이 다크 HTML 과 그 바탕을 받는다", async () => {
    const user = userEvent.setup();
    renderPreview();
    await screen.findByTestId("mail-preview-frame");
    await user.click(screen.getByRole("tab", { name: "다크" }));
    await waitFor(() => expect(frame().getAttribute("srcdoc")).toContain("다크 본문"));
    expect(frame()).toHaveAttribute("data-scheme", "dark");
    expect(frame()).toHaveStyle({ backgroundColor: "#0A0C16" });
    expect(frame().getAttribute("sandbox")).toBe("");
    expect(previewCalls()).toContain("/api/admin/mail/templates/ticket_assigned/preview?scheme=dark");
    await user.click(screen.getByRole("tab", { name: "라이트" }));
    await waitFor(() => expect(frame().getAttribute("srcdoc")).toContain("라이트 본문"));
    expect(frame()).toHaveStyle({ backgroundColor: "#F5F6FB" });
  });
});
