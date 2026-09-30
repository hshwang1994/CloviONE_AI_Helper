import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn(), setCsrf: () => {} }));
import { api } from "../lib/api.js";
import { SecretField } from "./SecretField.jsx";

/* 비밀 값 칸 (계획 2.3). 값은 들어가기만 하고 돌아오지 않는다 - 칸이 저장된 값을 보여 주는
 * 길이 없어야 하고, 저장 뒤에는 입력칸이 비어야 한다(화면에 남은 값은 어깨 너머로 읽힌다). */

function renderField(props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SecretField slot="smtp.password" label="메일 비밀번호" {...props} />
    </QueryClientProvider>,
  );
}

function listing(stored) {
  return { items: [{ slot: "smtp.password", label: "메일(SMTP) 비밀번호", stored, updated_at: stored ? "2026-09-30T01:00:00" : null }] };
}

describe("SecretField", () => {
  beforeEach(() => { api.mockReset(); });

  it("저장된 값이 없으면 그렇게 말하고, 입력칸은 비밀번호 칸이다", async () => {
    api.mockResolvedValue(listing(false));
    renderField();
    expect(await screen.findByText(/저장된 값이 없습니다/)).toBeTruthy();
    const input = screen.getByLabelText("메일 비밀번호");
    expect(input.getAttribute("type")).toBe("password");
    expect(input.getAttribute("autocomplete")).toBe("new-password");
    expect(screen.queryByRole("button", { name: "삭제" })).toBeNull();
  });

  it("저장하면 PUT 을 보내고 입력칸을 비운다", async () => {
    api.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") return Promise.resolve({ stored: true, changed: true });
      return Promise.resolve(listing(false));
    });
    renderField();
    const input = await screen.findByLabelText("메일 비밀번호");
    fireEvent.change(input, { target: { value: "p@ss-word" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/admin/secrets/smtp.password", { method: "PUT", body: { value: "p@ss-word" } },
    ));
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("저장된 값은 보여 주지 않고 삭제를 제공한다", async () => {
    api.mockResolvedValue(listing(true));
    renderField();
    expect(await screen.findByText(/저장된 값이 있습니다/)).toBeTruthy();
    expect(screen.getByLabelText("메일 비밀번호").value).toBe("");
    expect(screen.getByRole("button", { name: "삭제" })).toBeTruthy();
  });

  it("빈 값으로는 저장할 수 없다", async () => {
    api.mockResolvedValue(listing(false));
    renderField();
    await screen.findByText(/저장된 값이 없습니다/);
    expect(screen.getByRole("button", { name: "저장" }).disabled).toBe(true);
  });

  it("서버가 거절하면 이유를 보여 준다", async () => {
    api.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") return Promise.reject(new Error("비밀 값을 저장할 도우미에 연결하지 못했습니다."));
      return Promise.resolve(listing(false));
    });
    renderField();
    const input = await screen.findByLabelText("메일 비밀번호");
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/도우미/);
  });
});
