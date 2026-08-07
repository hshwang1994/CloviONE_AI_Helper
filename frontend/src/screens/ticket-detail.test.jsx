import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 티켓 상세 — 본문 편집 + 댓글 (계획 Phase 3 §E).
 *
 * 이 화면에서 조용히 틀리면 가장 비싼 것 두 가지를 고정한다.
 *
 * 1) **"저장은 됐지만 원본과 어긋남"을 성공으로 보고하지 않는다.**
 *    서버는 본문을 우리 DB에 먼저 쓰고 그다음 Notion에 민다. 그래서 Notion이 죽어도 사용자
 *    글은 살아남지만, 그 상태를 "저장했습니다"로만 알리면 사용자는 원본이 갱신된 줄 알고
 *    회의에 들어간다. 응답의 synced:false 가 화면에 보여야 한다.
 *
 * 2) **본문을 못 읽은 상태에서는 편집을 열지 않는다.** 빈 편집기로 저장하면 그게 곧 본문
 *    삭제다. 이건 되돌릴 수 없는 종류의 실수다.
 *
 * 그리고 댓글의 soft-delete가 화면에서 **툼스톤으로 보이는지** — 행이 조용히 사라지면
 * 사용자는 자기가 잘못 봤다고 생각한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Ticket } from "./Ticket.jsx";
import { lineCount, hasUnsupportedBlocks } from "./TicketBody.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TICKET = {
  id: "page-1", uid: "uid-1", tid: 42, title: "샘플 티켓", status: "진행",
  priority: "높음", difficulty: "3", est_wd: 2, due: "2026-09-01",
  project: "알파", assignee_names: ["나"], url: "https://notion.so/page-1",
};

const BLOCKS = [
  { kind: "heading_2", text: "배경" },
  { kind: "paragraph", text: "본문 한 줄." },
];

function detailPayload(over = {}) {
  return {
    configured: true, ok: true, ticket: TICKET, blocks: BLOCKS, blocks_error: null,
    body_markdown: "## 배경\n본문 한 줄.", body_is_local: true, body_sync_error: null, ...over,
  };
}

function route(path, handlers) {
  /* 티켓 상세는 상세·댓글·메타를 각각 부른다 — 경로별로 답을 고른다. */
  for (const [prefix, value] of handlers) {
    if (path.startsWith(prefix)) return typeof value === "function" ? value(path) : value;
  }
  throw new Error("unexpected api call: " + path);
}

function wrap(node = <Ticket />) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/tickets/page-1"]}>
              <Routes>
                <Route path="/tickets/:id" element={node} />
                <Route path="*" element={node} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

// ── 본문 편집 ────────────────────────────────────────────────────────────────

describe("본문 편집", () => {
  it("Notion 반영에 실패하면 '저장했습니다'로 끝내지 않고 어긋난 사실과 재시도를 보여준다", async () => {
    const user = userEvent.setup();
    let detail = detailPayload();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") {
        // 서버 계약: 본문은 저장됐으므로 200 + ok. 다만 원본과는 어긋났다.
        detail = detailPayload({ body_sync_error: "Notion 응답 오류: HTTP 500" });
        return Promise.resolve({ ok: true, synced: false, body_markdown: "새 본문",
                                 body_sync_error: "Notion 응답 오류: HTTP 500" });
      }
      return Promise.resolve(route(path, [
        ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
        ["/api/tickets/page-1", detail],
      ]));
    });

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    // 토스트가 실패를 말하고,
    expect(await screen.findByText(/원본\(Notion\) 반영에 실패/)).toBeInTheDocument();
    // 화면에 남는 배너로도 말한다(토스트는 8초 뒤 사라진다).
    expect(await screen.findByText(/원본\(Notion\)에 반영하지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "원본에 다시 반영" })).toBeInTheDocument();
  });

  it("성공하면 성공이라고만 말한다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "PUT") {
        return Promise.resolve({ ok: true, synced: true, body_markdown: "새 본문", body_sync_error: null });
      }
      return Promise.resolve(route(path, [
        ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
        ["/api/tickets/page-1", detailPayload()],
      ]));
    });

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("본문을 저장했습니다.")).toBeInTheDocument();
    expect(screen.queryByText(/반영하지 못했습니다/)).toBeNull();
  });

  it("본문을 못 읽었으면 편집을 막는다 — 빈 편집기로 저장하면 본문 삭제가 된다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload({
        blocks: null, blocks_error: "본문을 불러오지 못했습니다.", body_markdown: null,
      })],
    ])));

    wrap();

    expect(await screen.findByRole("button", { name: "본문 편집" })).toBeDisabled();
    expect(screen.getByText(/지금 저장하면 원본 본문을 지우게 되므로/)).toBeInTheDocument();
  });

  it("편집기는 서버가 준 마크다운으로 열린다 — 빈 칸으로 열면 저장이 곧 삭제다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload()],
    ])));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));

    /* 예전에는 `{ name: "" }` 으로 골랐다 — 편집기에 접근 이름이 **없다는 사실**을 검사가
       거꾸로 고정하고 있었다(접근성 감사 2). 지금은 위 heading 과 같은 이름을 가지므로
       그 이름으로 고른다. 이름으로 고를 수 있다는 것 자체가 스크린리더로 찾을 수 있다는 뜻이다. */
    expect(screen.getByRole("textbox", { name: "본문 편집" }).value)
      .toBe("## 배경\n본문 한 줄.");
  });

  /* 2026-08: 저장이 더 이상 이미지·표를 지우지 않는다(notion_write.replace_page_body 가
     편집기로 표현 가능한 블록만 지운다). 그래서 이 테스트의 원래 단언("사라집니다")은 이제
     **거짓을 고정하는 검사**가 됐다. 화면이 지키는 성질을 새 동작으로 바꿔 조준한다:
     그런 블록이 있다는 사실을 알리되, 지워지지 않는다고 말한다. */
  it("표현할 수 없는 블록이 있으면 '지워지지 않는다'고 알린다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload({
        blocks: [...BLOCKS, { kind: "unsupported", text: "[image] 원본에서 확인" }],
      })],
    ])));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));

    expect(screen.getByText(/그 블록은 지워지지 않습니다/)).toBeInTheDocument();
  });

  it("아직 우리 정본이 없으면 '서식이 평문이 된다'고 먼저 알린다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload({ body_is_local: false })],
    ])));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));

    expect(screen.getByText(/굵게, 링크 같은 인라인\s*서식은 사라지고/)).toBeInTheDocument();
  });

  it("정본이 생긴 뒤에는 저장이 무손실이라 경고하지 않는다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload({ body_is_local: true })],
    ])));

    wrap();
    await user.click(await screen.findByRole("button", { name: "본문 편집" }));

    expect(screen.queryByText(/서식은 사라지고/)).toBeNull();
  });
});

describe("TicketBody 헬퍼", () => {
  it("줄 수를 센다(상한 판정의 근거)", () => {
    expect(lineCount("")).toBe(1);
    expect(lineCount("a\nb\nc")).toBe(3);
    expect(lineCount(null)).toBe(1);
  });
  it("표현 불가 블록을 알아본다", () => {
    expect(hasUnsupportedBlocks([{ kind: "paragraph" }])).toBe(false);
    expect(hasUnsupportedBlocks([{ kind: "unsupported" }])).toBe(true);
    expect(hasUnsupportedBlocks(null)).toBe(false);
  });
});

// ── 댓글 ─────────────────────────────────────────────────────────────────────

describe("댓글", () => {
  const COMMENTS = [
    { id: "c1", author_user_id: "u1", author_name: "김개발", body: "확인했습니다.",
      deleted: false, deleted_at: null, created_at: "2026-08-01T01:00:00",
      updated_at: "2026-08-01T01:00:00", can_edit: true, can_delete: true },
    { id: "c2", author_user_id: "u2", author_name: "이운영", body: "저도요.",
      deleted: false, deleted_at: null, created_at: "2026-08-01T02:00:00",
      updated_at: "2026-08-01T02:00:00", can_edit: false, can_delete: false },
  ];

  it("남의 댓글에는 수정·삭제 버튼을 그리지 않는다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: COMMENTS }],
      ["/api/tickets/page-1", detailPayload()],
    ])));

    wrap();

    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    // 댓글 영역 안에서만 센다 — 화면 머리에도 '삭제'(티켓 휴지통) 버튼이 따로 있다.
    const box = within(screen.getByRole("region", { name: "댓글" }));
    // 내 댓글 하나에만 버튼이 붙는다(총 2개 댓글, 버튼은 각 1쌍).
    expect(box.getAllByRole("button", { name: "수정" })).toHaveLength(1);
    expect(box.getAllByRole("button", { name: "삭제" })).toHaveLength(1);
  });

  it("삭제된 댓글은 사라지지 않고 툼스톤으로 남는다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [
        { ...COMMENTS[0], body: "", deleted: true, deleted_at: "2026-08-01T03:00:00",
          can_edit: false, can_delete: false },
        COMMENTS[1],
      ] }],
      ["/api/tickets/page-1", detailPayload()],
    ])));

    wrap();

    expect(await screen.findByText(/삭제된 댓글입니다/)).toBeInTheDocument();
    // 지운 내용이 다시 내려오지도, 그려지지도 않는다.
    expect(screen.queryByText("확인했습니다.")).toBeNull();
    // 살아 있는 댓글은 그대로.
    expect(screen.getByText("저도요.")).toBeInTheDocument();
  });

  it("등록하면 서버가 준 목록을 그대로 반영한다(클라가 목록을 기워 맞추지 않는다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") {
        return Promise.resolve({ ok: true, comment_id: "c9", comments: [
          ...COMMENTS,
          { id: "c9", author_user_id: "u1", author_name: "김개발", body: "새 댓글",
            deleted: false, deleted_at: null, created_at: "2026-08-01T04:00:00",
            updated_at: "2026-08-01T04:00:00", can_edit: true, can_delete: true },
        ] });
      }
      return Promise.resolve(route(path, [
        ["/api/tickets/page-1/comments", { ok: true, comments: COMMENTS }],
        ["/api/tickets/page-1", detailPayload()],
      ]));
    });

    wrap();
    await screen.findByText("확인했습니다.");
    await user.type(screen.getByLabelText("댓글 입력"), "새 댓글");
    await user.click(screen.getByRole("button", { name: "댓글 등록" }));

    expect(await screen.findByText("새 댓글")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("댓글 입력").value).toBe(""));
  });

  it("빈 댓글은 등록 버튼 자체가 눌리지 않는다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload()],
    ])));

    wrap();

    expect(await screen.findByRole("button", { name: "댓글 등록" })).toBeDisabled();
  });
});

// ── 레이아웃(댓글은 본문이 아니라 속성 레일) ──────────────────────────────────

describe("레이아웃 — 댓글은 속성 레일에", () => {
  it("댓글은 본문 열이 아니라 속성 레일(우측 컬럼)에 렌더된다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(route(path, [
      ["/api/tickets/page-1/comments", { ok: true, comments: [] }],
      ["/api/tickets/page-1", detailPayload()],
    ])));

    const { container } = wrap();
    await screen.findByRole("heading", { name: "속성" });

    const main = container.querySelector('[data-testid="ticket-detail-main"]');
    const rail = container.querySelector('[data-testid="ticket-detail-rail"]');
    expect(main).toBeInTheDocument();
    expect(rail).toBeInTheDocument();

    const commentsRegion = screen.getByRole("region", { name: "댓글" });
    // 댓글은 본문 열이 아니라 속성 레일 안에 있어야 한다.
    expect(main.contains(commentsRegion)).toBe(false);
    expect(rail.contains(commentsRegion)).toBe(true);

    // 레일 안에서도 속성이 댓글보다 먼저 나온다(속성을 먼저 보고 논의를 본다).
    const attrHeading = within(rail).getByRole("heading", { name: "속성" });
    expect(attrHeading.compareDocumentPosition(commentsRegion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // 좁은 화면에서 한 열로 접힐 때도 본문이 댓글보다 먼저 나와야 한다 — main 컬럼이
    // DOM에서 rail 컬럼보다 앞서면(둘 다 order override가 없으므로) 그 순서로 쌓인다.
    expect(main.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
