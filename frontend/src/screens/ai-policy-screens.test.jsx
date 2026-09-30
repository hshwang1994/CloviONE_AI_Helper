import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 정책 화면과 AI 초안 결재(계획 3.9, D-519). 화면이 지키는 것:
 *
 *  1. 정책 폼은 JSON 대신 종류마다 정해진 칸을 보이고, 보내기 직전에 서버의 모양({kind, applies_to, content})으로
 *     모은다. 수정 폼은 서버가 준 행을 같은 칸으로 되돌린다.
 *  2. 옛 형식 정책은 발행하거나 새 버전을 만들 수 없다.
 *  3. 승인 화면과 결재함은 AI 문서 만들기 요청에 「초안 미리 보기」 · 「초안 보기」를 붙이고, 서버의 초안 본문을 연다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../ui/celebrate.js", () => ({ celebrateIfCleared: () => {}, celebrateIfCompleted: () => {} }));

import { REGISTRY } from "./registry.js";
import { MyApprovals } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const policies = REGISTRY.policies;
const actionsFor = (row) => policies.actions.filter((a) => !a.when || a.when(row, undefined)).map((a) => a.label);

describe("정책 폼", () => {
  it("쓰기 승인 칸을 서버의 모양으로 모은다", () => {
    const body = policies.toApiBody({
      name: "문서 승인", kind: "approval", target_write: "workspace.draft", purpose: "설명",
      write_requires_approval: true, auto_system_admin: true, auto_admin: false, auto_operator: true,
    });
    expect(body).toEqual({
      name: "문서 승인", purpose: "설명", kind: "approval", applies_to: "workspace.draft",
      content: { write_requires_approval: true, auto_approve_roles: ["system_admin", "operator"] },
    });
  });

  it("응답 제한의 빈 글자 수는 null 이고, 수정 폼은 종류를 칸으로 알아본다", () => {
    const created = policies.toApiBody({ name: "짧게", kind: "content", target: "*", max_output_chars: "", block_external_links: true });
    expect(created.content).toEqual({ max_output_chars: null, block_external_links: true });
    const edited = policies.toApiBody({ target: "chat.answer", max_output_chars: "300", block_external_links: false });
    expect(edited).toEqual({ applies_to: "chat.answer", content: { max_output_chars: 300, block_external_links: false } });
  });

  it("수정 폼은 서버가 준 행을 같은 칸으로 되돌린다", () => {
    const row = { kind: "data_protection", applies_to: ["chat.answer"], purpose: "p",
      content: { mask_emails: true, mask_phone_numbers: false, mask_resident_registration_numbers: true } };
    const values = policies.fromRow(row);
    expect(values).toMatchObject({ target: "chat.answer", mask_emails: true, mask_phone_numbers: false,
      mask_resident_registration_numbers: true, purpose: "p" });
    expect(policies.toApiBody(values).content).toEqual(row.content);
  });

  it("만들기 폼은 고른 종류의 칸만 보인다", () => {
    const shown = (kind) => policies.create.fields.filter((f) => !f.showIf || f.showIf({ kind })).map((f) => f.name);
    expect(shown("approval")).toContain("write_requires_approval");
    expect(shown("approval")).toContain("target_write");
    expect(shown("approval")).not.toContain("mask_emails");
    expect(shown("content")).toEqual(["name", "kind", "target", "max_output_chars", "block_external_links", "purpose"]);
  });

  it("옛 형식 정책은 발행하거나 새 버전을 만들 수 없다", () => {
    const legacy = { id: "p", kind: "legacy", status: "archived", name: "옛 정책" };
    expect(actionsFor(legacy)).not.toContain("발행");
    expect(actionsFor(legacy)).not.toContain("새 버전");
    expect(policies.editWhen({ ...legacy, status: "draft" })).toBe(false);
    expect(actionsFor({ id: "q", kind: "content", status: "draft", name: "새 정책" })).toContain("발행");
  });
});

describe("AI 초안 결재", () => {
  it("승인 화면의 「초안 미리 보기」가 서버의 초안 본문을 연다", () => {
    const preview = REGISTRY.approvals.actions.find((a) => a.label === "초안 미리 보기");
    expect(preview.when({ request_type: "ai.document_create" })).toBe(true);
    expect(preview.when({ request_type: "user.role_change" })).toBe(false);
    expect(preview.path({ object_id: "req-1" })).toBe("/api/approvals/ai-drafts/req-1");
    expect(preview.info({ item: { output_text: "초안 본문" } })).toBe("초안 본문");
  });

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/approvals/ai-drafts/")) {
        return Promise.resolve({ item: { title: "연차 안내 초안", output_text: "결재할 초안 본문입니다." } });
      }
      return Promise.resolve({
        items: [{ id: "A1", request_type: "ai.document_create", status: "pending", object_type: "ai_action_request",
          object_id: "req-9", requested_at: "2026-09-01T01:00:00", requester_name: "김민수",
          request_payload: { title: "연차 안내 초안", target_name: "연차 안내 초안", chars: 12 } }],
        total: 1, page: 1, page_size: 20, can_decide: true,
      });
    });
  });

  it("결재함의 「초안 보기」가 본문을 보여 준다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter initialEntries={["/my-approvals"]}>
            <Routes><Route path="/my-approvals" element={<MyApprovals />} /></Routes>
          </MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "초안 보기: 연차 안내 초안" }));
    expect(await screen.findByText("결재할 초안 본문입니다.")).toBeInTheDocument();
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/approvals/ai-drafts/req-9"));
  });
});
