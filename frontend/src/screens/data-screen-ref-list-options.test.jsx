import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* DGEN-01/USE-04/SCHD-02(2026-08-11 체크포인트 다음 후보): 문서 생성 모달의 워크플로/템플릿
 * ID, 스케줄의 대상 ID가 손으로 옮겨 적는 자유 텍스트였다 — 화면이 이미 아는 목록(워크플로
 * 화면·템플릿 화면)을 그대로 select로 보여주게 한다. config.refLists +
 * f.optionsFromRefList(DataScreen.jsx)가 그 배선이다.
 *
 * MUI Select의 내부 동작(열기/클릭)에 기대지 않는다(form-conditional.test.jsx와 같은 이유,
 * jsdom에서 불안정하다) — 이미 선택된 값으로 렌더해 표시 라벨을 확인한다: 옵션이 실제로
 * 연결됐다면 원시 UUID(wf-1)가 아니라 이름(매주 보고서)이 보인다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
  AuthProvider: ({ children }) => children,
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { REGISTRY } from "./registry.js";
import { DOC_GENERATE_FIELDS } from "./registry/actions.js";

const CONFIG = {
  key: "x-refs",
  title: "참조 목록 테스트",
  endpoint: "/api/admin/x-refs",
  refLists: [{ key: "workflows", endpoint: "/api/admin/workflows" }],
  columns: [{ key: "name", label: "이름" }],
  detailFields: [],
  create: {
    roles: ["system_admin"],
    fields: [
      // value로 미리 골라 둔다 — MUI Select의 팝업(포털)을 열지 않고도 "닫힌 상태에서 보이는
      // 라벨"만으로 옵션이 실제로 연결됐는지 확인한다(form-conditional.test.jsx와 같은 이유로
      // 열기/클릭 상호작용에는 기대지 않는다).
      { name: "workflow_id", label: "워크플로", type: "select", required: true, value: "wf-1", optionsFromRefList: "workflows" },
      { name: "target_ref", label: "대상", type: "select", required: true, value: "noop", optionsFromRefList: "workflows",
        extraOptions: [{ value: "noop", label: "시스템 (noop)" }] },
    ],
  },
};

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><DataScreen config={CONFIG} /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("config.refLists — 다른 화면의 리소스를 이름 붙은 select 옵션으로", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((url) => {
      if (String(url).startsWith("/api/admin/workflows")) {
        return Promise.resolve({ items: [{ id: "wf-1", name: "매주 보고서", enabled: true }] });
      }
      return Promise.resolve({ items: [], page: 1, page_size: 20, total: 0 });
    });
  });

  it("워크플로 ID 대신 워크플로 이름을 보여준다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    renderScreen(qc);

    await user.click(await screen.findByRole("button", { name: "추가" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/workflows"));

    // 필드 기본값이 "wf-1"이다 — 참조 목록이 실제로 연결됐다면 select가 닫힌 상태에서도
    // 그 옵션의 라벨("매주 보고서")이 보인다. 연결이 안 됐다면(옛 자유 텍스트이거나 옵션이
    // 비어 있으면) 원시 값 "wf-1"이 그대로 보이거나 빈칸이다.
    await waitFor(() => expect(screen.getByText("매주 보고서")).toBeInTheDocument());
    expect(screen.queryByText("wf-1")).toBeNull();
  });

  it("extraOptions로 덧붙인 고정 선택지(시스템 noop)도 함께 있다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    renderScreen(qc);

    await user.click(await screen.findByRole("button", { name: "추가" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/workflows"));
    // target_ref 필드 기본값이 "noop" — extraOptions로 덧붙인 고정 선택지가 실제로 옵션
    // 배열에 들어갔다면(그냥 무시되지 않았다면) 닫힌 select에 그 라벨이 보인다.
    await waitFor(() => expect(screen.getByText("시스템 (noop)")).toBeInTheDocument());
  });
});

describe("DGEN-01/USE-04/SCHD-02 계약 — 실제 화면 설정에 실제로 걸려 있다", () => {
  it("문서 생성 폼(DOC_GENERATE_FIELDS)의 워크플로/템플릿이 자유 텍스트가 아니라 select다", () => {
    const workflowField = DOC_GENERATE_FIELDS.find((f) => f.name === "workflow_id");
    expect(workflowField.type).toBe("select");
    expect(workflowField.optionsFromRefList).toBe("workflows");
    const templateField = DOC_GENERATE_FIELDS.find((f) => f.name === "template_id");
    expect(templateField.type).toBe("select");
    expect(templateField.optionsFromRefList).toBe("templates");
  });

  it("documents 화면이 workflows/templates refLists를 선언한다", () => {
    expect(REGISTRY.documents.refLists.map((r) => r.key).sort()).toEqual(["templates", "workflows"]);
  });

  it("schedules 생성/수정 폼의 대상 필드가 select이고 시스템(noop) 선택지를 포함한다", () => {
    for (const formKey of ["create", "edit"]) {
      const field = REGISTRY.schedules[formKey].fields.find((f) => f.name === "target_ref");
      expect(field.type, formKey + ".target_ref").toBe("select");
      expect(field.optionsFromRefList, formKey + ".target_ref").toBe("workflows");
      expect(field.extraOptions, formKey + ".target_ref").toEqual([{ value: "noop", label: "시스템 (noop)" }]);
    }
    expect(REGISTRY.schedules.refLists.map((r) => r.key)).toEqual(["workflows"]);
  });
});
