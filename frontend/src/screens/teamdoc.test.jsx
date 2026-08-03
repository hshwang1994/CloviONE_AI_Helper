import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 문서 상세 계약 테스트.
 *
 * 이 화면의 핵심은 **장애 격리**다. 메타는 로컬 캐시, 본문 블록은 실시간 Notion이라 본문만
 * 따로 실패할 수 있다. 그때 화면 전체가 오류로 무너지거나, 반대로 아무 말 없이 빈 여백만
 * 남으면 사용자는 "문서가 삭제됐나?"라고 오해한다 — 제목·메타·원본 링크는 그대로 두고
 * 본문 자리에만 이유를 적어야 한다.
 *
 * DocBody/safeExternal은 티켓 상세(Ticket.jsx)도 함께 쓰는 공용 렌더러라 시그니처가 계약이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { TeamDoc, DocBody, safeExternal } from "./TeamDoc.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(node, path = "/team-docs/d1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/team-docs/:id" element={node} />
                <Route path="*" element={node} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const DOC = {
  id: "d1", title: "네트워크 설계서", document_type: "설계서", status: "활성",
  work_field: "인프라", tech_tags: ["Nginx"], projects: ["사내망 개편"],
  author_names: ["김운영"], owner: "플랫폼 운영팀", priority: "높음",
  last_edited: "2026-08-01T01:00:00", original_url: "https://notion.so/abc",
  is_favorite: false,
};

beforeEach(() => {
  apiMock.mockReset();
});

describe("본문이 없거나 실패해도 메타는 남는다", () => {
  it("blocks가 비어 있으면 제목·메타는 그대로 두고 본문 자리에만 안내를 넣는다", async () => {
    apiMock.mockResolvedValue({ document: DOC, blocks: [] });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText("본문 내용이 없습니다. 원본 문서를 확인해 주세요.")).toBeInTheDocument();
    // 메타 레일은 살아 있어야 한다 — 본문이 없다고 문서 정보까지 사라지면 안 된다.
    expect(screen.getByText("업무 분야")).toBeInTheDocument();
    expect(screen.getByText("인프라")).toBeInTheDocument();
    // 원본 링크(장애 시 유일한 탈출구)도 남는다.
    expect(screen.getByRole("button", { name: "원본 열기" })).toBeInTheDocument();
  });

  it("blocks가 아예 null이어도 렌더가 깨지지 않는다", async () => {
    apiMock.mockResolvedValue({ document: { ...DOC, original_url: null, url: null, source_url: null } });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText("본문 내용이 없습니다. 원본 문서를 확인해 주세요.")).toBeInTheDocument();
    // 안전하지 않은/없는 원본 URL이면 '원본 열기' 버튼 자체를 내지 않는다.
    expect(screen.queryByRole("button", { name: "원본 열기" })).toBeNull();
  });

  it("blocks_error가 오면 원인을 적어 주고 원본으로 유도한다", async () => {
    apiMock.mockResolvedValue({ document: DOC, blocks: null, blocks_error: "Notion 응답 시간 초과" });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText(/Notion 응답 시간 초과/)).toBeInTheDocument();
    // 본문만 실패했을 뿐이므로 메타 레일(소유자 등)은 계속 보인다.
    expect(screen.getByText("플랫폼 운영팀")).toBeInTheDocument();
  });
});

describe("DocBody 공용 렌더러(티켓 상세와 공유)", () => {
  it("연속한 글머리/번호는 하나의 목록으로 묶는다", () => {
    const { container } = render(
      <DocBody blocks={[
        { kind: "paragraph", text: "머리말" },
        { kind: "bulleted", text: "첫째" },
        { kind: "bulleted", text: "둘째" },
        { kind: "numbered", text: "하나" },
        { kind: "numbered", text: "둘" },
      ]} />
    );
    // bare <li>가 흩어지면 번호가 문서 전체 카운터를 공유해 잘못 매겨진다.
    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(container.querySelectorAll("ol > li")).toHaveLength(2);
  });
});

describe("safeExternal", () => {
  it("http(s)만 통과시킨다", () => {
    expect(safeExternal("https://notion.so/a")).toBe("https://notion.so/a");
    expect(safeExternal("http://intra/a")).toBe("http://intra/a");
    expect(safeExternal("javascript:alert(1)")).toBeNull();
    expect(safeExternal(null)).toBeNull();
    expect(safeExternal(123)).toBeNull();
  });
});
