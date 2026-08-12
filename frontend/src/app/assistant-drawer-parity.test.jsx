import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI-25/26/28/29: 드로어가 전체화면 Chat.jsx가 이미 가진 기능을 재사용하지 못해 생긴
 * 4가지 결함을 한 번에 고정한다 — 전부 "드로어가 useChat()이 이미 내주는 상태를 화면에
 * 안 그렸다"는 같은 뿌리(component-reuse debt)다.
 *
 *   AI-25: 어시스턴트 답이 평문(pre-wrap)으로만 그려져 카드·재시도·복사·시각을 버렸다.
 *   AI-26: '새 대화' 버튼이 없어 한 스레드에 영구히 갇혔다.
 *   AI-28: 붙여넣은 이미지가 안 보이고 안 지워지고, 이미지만 있으면 전송이 막혔다.
 *   AI-29: 429/503 잠금 안내·해제 버튼이 전체화면에만 있어 드로어는 새로고침 전엔 안 풀렸다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));
// downscaleImage는 실제 <canvas>/Image() 디코딩을 쓴다 — jsdom엔 진짜 이미지 코덱이 없어
// 테스트의 가짜 바이트(진짜 PNG가 아님)를 디코딩하다 실패한다(img.onerror). 이 함수만 가짜로
// 바꾸고 나머지 chat-helpers.js(크기 검사·b64Bytes 등)는 그대로 둔다 — pickFiles의 나머지
// 로직(첨부 개수·용량 상한, pending 갱신)은 실제 코드 그대로 검증한다.
vi.mock("../screens/chat-helpers.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, downscaleImage: async (file) => ({ media_type: file.type || "image/png", data: "ZmFrZQ==" }) };
});

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function renderShellAndOpenDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={["/chat-rooms"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openDrawer() {
  await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
  fireEvent.click(screen.getAllByLabelText("클로비 AI 도우미 열기")[0]);
  return screen.findByLabelText("클로비에게 질문");
}

const THREAD_MESSAGES = {
  items: [
    { id: "m1", role: "user", content: "로그인 실패 티켓 찾아줘", processing_status: "done", created_at: "2026-08-01T00:00:00Z" },
    {
      id: "m2", role: "assistant", content: "요청하신 티켓을 찾았습니다.", processing_status: "done",
      created_at: "2026-08-01T00:00:01Z",
      structured: { tickets: [{ title: "로그인 실패 조사", status: "진행", assignees: ["김운영"] }] },
    },
  ],
};

function commonApi(overrides) {
  return (path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ items: [], global: null, unread_total: 0 });
    if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0, badge: 0, by_type: {} });
    if (overrides) {
      const hit = overrides(path, opts, method);
      if (hit !== undefined) return hit;
    }
    if (path.startsWith("/api/conversations?") && method === "GET") return Promise.resolve({ items: [{ id: "c1", title: "기존 대화" }] });
    if (path === "/api/conversations/c1/messages" && method === "GET") return Promise.resolve(THREAD_MESSAGES);
    return Promise.resolve({});
  };
}

describe("AI-25 — 드로어도 전체화면과 같은 카드를 그린다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(commonApi());
    wideViewport();
  });

  it("구조화된 티켓 응답이 평문이 아니라 카드(제목·상태 배지·담당자)로 보인다", async () => {
    renderShellAndOpenDrawer();
    await openDrawer();

    expect(await screen.findByText("로그인 실패 조사")).toBeInTheDocument();
    expect(screen.getByText("상태")).toBeInTheDocument();
    expect(screen.getByText("진행")).toBeInTheDocument();
    expect(screen.getByText("담당자")).toBeInTheDocument();
  });

  it("복사·시각 같은 액션도 전체화면과 동일하게 뜬다", async () => {
    renderShellAndOpenDrawer();
    await openDrawer();

    await screen.findByText("로그인 실패 조사");
    expect(screen.getByRole("button", { name: /복사/ })).toBeInTheDocument();
  });
});

describe("AI-26 — '새 대화'로 스레드에서 빠져나올 수 있다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(commonApi());
    wideViewport();
  });

  it("대화가 있으면 '새 대화' 버튼이 있고, 누르면 빈 상태(제안 칩)로 돌아간다", async () => {
    renderShellAndOpenDrawer();
    await openDrawer();
    await screen.findByText("로그인 실패 조사");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "새 대화" }));

    expect(await screen.findByText("무엇을 도와드릴까요?")).toBeInTheDocument();
    expect(screen.getByText("현재 화면의 핵심 내용을 요약해 줘")).toBeInTheDocument();
    expect(screen.queryByText("로그인 실패 조사")).toBeNull();
  });
});

describe("AI-28 — 붙여넣은 이미지가 보이고, 이미지만으로도 보낼 수 있다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(commonApi((path, opts, method) => {
      if (path.startsWith("/api/conversations?") && method === "GET") return Promise.resolve({ items: [] });
    }));
    wideViewport();
  });

  function pasteImage() {
    const file = new File([new Uint8Array([1, 2, 3])], "shot.png", { type: "image/png" });
    const ev = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(ev, "clipboardData", { value: { files: [file] } });
    document.dispatchEvent(ev);
  }

  it("이미지를 붙이면 미리보기와 제거 버튼이 뜨고, 텍스트 없이도 전송 버튼이 눌린다", async () => {
    renderShellAndOpenDrawer();
    await openDrawer();

    pasteImage();

    expect(await screen.findByText("shot.png")).toBeInTheDocument();
    const removeBtn = screen.getByRole("button", { name: /첨부 제거: shot\.png/ });
    expect(removeBtn).toBeInTheDocument();

    // 텍스트를 하나도 안 쳤는데도(이미지만 있음) 전송 버튼이 잠겨 있지 않다.
    expect(screen.getByRole("button", { name: "질문 전송" })).toBeEnabled();

    await userEvent.setup().click(removeBtn);
    expect(screen.queryByText("shot.png")).toBeNull();
  });
});

describe("AI-29 — 429/503 잠금 안내와 해제 버튼이 드로어 안에 있다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(commonApi((path, opts, method) => {
      if (path.startsWith("/api/conversations?") && method === "GET") return Promise.resolve({ items: [] });
      if (path === "/api/conversations" && method === "POST") {
        const err = new Error("Too Many Requests");
        err.status = 429;
        return Promise.reject(err);
      }
    }));
    wideViewport();
  });

  it("429를 받으면 배너와 '닫기' 버튼이 드로어 안에 뜨고, 눌러야 다시 보낼 수 있다", async () => {
    renderShellAndOpenDrawer();
    const box = await openDrawer();

    fireEvent.change(box, { target: { value: "안녕" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });

    const dismiss = await screen.findByRole("button", { name: "닫기" });
    expect(screen.getByRole("button", { name: "질문 전송" })).toBeDisabled();

    await userEvent.setup().click(dismiss);
    expect(screen.queryByRole("button", { name: "닫기" })).toBeNull();
    expect(screen.getByRole("button", { name: "질문 전송" })).not.toBeDisabled();
  });
});
