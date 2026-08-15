import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 문서 **편집** 계약 (사용자 지적 #9).
 *
 * 사용자 보고는 "문서 편집이 정상적으로 동작하지 않는다" 였고, 확인해 보니 편집 기능이 아예
 * 없었다. 여기서 고정하는 것은 티켓 본문 편집과 같은 세 가지다.
 *
 * 1) 편집 -> 저장 -> **새 지문을 받는다.** 저장 응답의 body_version 을 안 쓰면 다음 저장이
 *    반드시 409 로 막히고, 사용자는 자기 글을 두 번째부터 저장할 수 없다.
 * 2) "저장은 됐지만 원본과 어긋남"을 성공으로 보고하지 않는다. 서버는 그때도 200 을 준다
 *    (사용자 글은 안전하므로 오류로 던지면 오히려 그 글이 롤백된다).
 * 3) 본문을 못 읽은 상태에서는 편집을 열지 않는다. 빈 편집기로 저장하면 그게 곧 본문 삭제다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { TeamDoc } from "./TeamDoc.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOC = {
  id: "d1", title: "네트워크 설계서", document_type: "설계서", status: "활성",
  work_field: "인프라", tech_tags: ["Nginx"], projects: ["사내망 개편"],
  author_names: ["김운영"], owner: "플랫폼 운영팀", priority: "높음",
  last_edited: "2026-08-01T01:00:00", original_url: "https://notion.so/abc",
  is_favorite: false,
};

const BLOCKS = [
  { kind: "heading_2", text: "배경" },
  { kind: "paragraph", text: "본문 한 줄." },
];

function detailPayload(over = {}) {
  return {
    document: DOC, blocks: BLOCKS, blocks_error: null,
    body_markdown: "## 배경\n본문 한 줄.", body_version: "v1",
    body_is_local: true, body_sync_error: null, ...over,
  };
}

function wrap(node = <TeamDoc />) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/team-docs/d1"]}>
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

/* 문서 상세는 상세와 댓글을 각각 부른다 - 경로별로 답을 고른다. */
function route(path, detail) {
  if (path.startsWith("/api/team-docs/d1/comments")) return { ok: true, comments: [] };
  if (path.startsWith("/api/team-docs/d1")) return detail;
  throw new Error("unexpected api call: " + path);
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("문서 본문 편집", () => {
  it("편집을 열어 고치고 저장하면 저장 요청이 나가고 새 지문을 받아 다음 저장에 쓴다", async () => {
    const user = userEvent.setup();
    const saves = [];
    let detail = detailPayload();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") {
        saves.push({ path, body: opts.body });
        detail = detailPayload({ body_markdown: opts.body.body_markdown, body_version: "v2" });
        return Promise.resolve({
          ok: true, synced: true, body_markdown: opts.body.body_markdown,
          body_version: "v2", body_is_local: true, body_sync_error: null,
        });
      }
      return Promise.resolve(route(path, detail));
    });

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));

    const box = screen.getByPlaceholderText(/본문을 입력하세요/);
    await user.clear(box);
    await user.type(box, "고친 본문");
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("본문을 저장했습니다.")).toBeInTheDocument();
    expect(saves).toHaveLength(1);
    expect(saves[0].path).toBe("/api/team-docs/d1/body");
    expect(saves[0].body.body_markdown).toBe("고친 본문");
    // 편집을 시작할 때 받은 지문을 그대로 돌려보낸다 - 이게 없으면 앞사람 글을 덮어쓴다.
    expect(saves[0].body.base_version).toBe("v1");

    // 두 번째 저장은 **새 지문**으로 나가야 한다. 옛 지문을 쓰면 서버가 409 로 막는다.
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(saves).toHaveLength(2));
    expect(saves[1].body.base_version).toBe("v2");
  });

  it("원본 반영에 실패하면 '저장했습니다'로 끝내지 않고 어긋난 사실과 재시도를 보여준다", async () => {
    const user = userEvent.setup();
    let detail = detailPayload();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") {
        detail = detailPayload({ body_sync_error: "Notion 응답 오류: HTTP 500" });
        return Promise.resolve({
          ok: true, synced: false, body_markdown: "새 본문", body_version: "v2",
          body_is_local: true, body_sync_error: "Notion 응답 오류: HTTP 500",
        });
      }
      return Promise.resolve(route(path, detail));
    });

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText(/원본\(Notion\) 반영에 실패/)).toBeInTheDocument();
    // 토스트는 사라진다. 화면에 남는 배너로도 말해야 한다.
    expect(await screen.findByText(/원본\(Notion\)에 반영하지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "원본에 다시 반영" })).toBeInTheDocument();
  });

  it("충돌(409)은 조용히 지나가지 않고 사용자에게 그대로 보인다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") {
        return Promise.reject(new Error("다른 사람이 먼저 저장했습니다. 새로고침해 주세요."));
      }
      return Promise.resolve(route(path, detailPayload()));
    });

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText(/다른 사람이 먼저 저장했습니다/)).toBeInTheDocument();
  });

  it("본문을 못 읽었으면 편집을 막는다 - 빈 편집기로 저장하면 본문 삭제가 된다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, detailPayload({
      blocks: null, blocks_error: "본문을 불러오지 못했습니다.", body_markdown: null,
      body_is_local: false,
    }))));

    wrap();
    expect(await screen.findByRole("button", { name: "본문 수정" })).toBeDisabled();
  });

  it("원본에서 되읽은 근사치를 고칠 때만 서식 손실을 경고한다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(
      route(path, detailPayload({ body_is_local: false }))
    ));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));
    expect(screen.getByText(/인라인\s*서식은 사라지고/)).toBeInTheDocument();
  });

  it("정본이 생긴 뒤에는 경고하지 않는다 - 늘 경고하면 아무도 안 읽는다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(route(path, detailPayload())));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 수정" }));
    expect(screen.queryByText(/인라인\s*서식은 사라지고/)).toBeNull();
  });
});
