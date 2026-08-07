import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 티켓 첨부 — 사용자가 "추가 버튼이 동작하지 않는다 / 두 개 고른 뒤 드래그하면 올라간다"고
 * 보고한 건을 고정한다. 재현해 보니 세 가지가 겹쳐 있었다.
 *
 * 1) **고른 파일이 서버로 안 갔다.** `pick` 이 살아 있는 `FileList` 를 그대로 mutation 에
 *    넘기고, 같은 줄에서 `input.value = ""` 로 입력을 비웠다. HTML 표준상 value 에 ""를
 *    넣으면 선택 파일 목록을 **그 자리에서** 비운다. mutationFn 은 마이크로태스크 뒤에 도는
 *    비동기라, 그때 그 목록은 이미 0개다 — 아무것도 안 올라가는데 "파일을 첨부했습니다"
 *    토스트만 떴다. 드래그는 `dataTransfer.files` 를 아무도 비우지 않아 멀쩡했다.
 *    같은 화면에서 버튼만 죽고 드래그만 사는 이유가 정확히 이것이다.
 *
 * 2) **드롭존이 첨부 0건일 때만 있었다.** 한 장 붙는 순간 드래그가 아무 데도 안 걸린다.
 *    "처음엔 되던 게 갑자기 안 된다"는 가장 나쁜 종류의 고장이다.
 *
 * 3) **canEdit=false 면 버튼도 입력도 통째로 사라졌다.** 이유 없이 없어진 버튼은 사용자에게
 *    권한 안내가 아니라 고장으로 읽힌다.
 *
 * jsdom 주의: `user-event` 와 RTL 은 `input.files` 를 얼려서(frozen) 덮어씌우기 때문에
 * 브라우저의 "value=''가 목록을 비운다"를 흉내내지 못한다 — 그래서 1)은 표준대로 동작하는
 * 살아 있는 FileList 를 직접 심어 재현한다(`pickFilesLikeBrowser`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { TicketAttachments } from "./TicketAttachments.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const IMG = { id: "a1", filename: "shot.png", is_image: true, url: "/api/x/a1", size_bytes: 2048 };
const PDF = { id: "a2", filename: "spec.pdf", is_image: false, url: "/api/x/a2", size_bytes: 4096 };

function wrap(props) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <TicketAttachments ticketId="page-1" onChanged={() => {}} {...props} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function fileInput(container) {
  return container.querySelector('input[type="file"]');
}

function makeFiles(names) {
  return names.map((n) => new File(["x"], n, { type: "image/png" }));
}

/** 브라우저와 같은 `<input type=file>` 을 흉내낸다.
 *
 * 표준(html.spec.whatwg.org #dom-input-value-filename): `value` 에 빈 문자열을 넣으면
 * **선택 파일 목록을 비운다**. 그 목록은 `files` 가 돌려준 바로 그 객체다 — 새 목록으로
 * 바뀌는 게 아니라 그 자리에서 비워진다. 이 성질이 결함의 전부라 테스트도 이대로 심는다.
 */
function pickFilesLikeBrowser(input, files) {
  const live = { length: files.length, item: (i) => live[i] || null };
  files.forEach((f, i) => { live[i] = f; });
  live[Symbol.iterator] = function* () { for (let i = 0; i < live.length; i++) yield live[i]; };
  Object.defineProperty(input, "files", { configurable: true, get: () => live });
  Object.defineProperty(input, "value", {
    configurable: true,
    get: () => (live.length ? "C:\\fakepath\\" + live[0].name : ""),
    set: (v) => {
      if (v !== "") throw new Error("파일 입력에는 빈 문자열만 넣을 수 있다");
      for (let i = 0; i < files.length; i++) delete live[i];
      live.length = 0;
    },
  });
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function dropFiles(node, files) {
  const ev = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(ev, "dataTransfer", { value: { files, items: [], types: ["Files"] } });
  node.dispatchEvent(ev);
}

function uploadCalls() {
  return apiMock.mock.calls.filter(
    ([path, opts]) => path === "/api/tickets/page-1/attachments" && opts && opts.method === "POST"
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ ok: true });
});

// ── 파일 추가 버튼 ────────────────────────────────────────────────────────────

describe("파일 추가 버튼", () => {
  it("버튼은 숨은 파일 입력을 연다", async () => {
    const user = userEvent.setup();
    const { container } = wrap({ attachments: [], canEdit: true });
    const spy = vi.spyOn(fileInput(container), "click");

    await user.click(screen.getByRole("button", { name: "파일 추가" }));

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("고른 파일이 실제로 서버로 간다 — 토스트만 성공하고 아무것도 안 올라가면 안 된다", async () => {
    const { container } = wrap({ attachments: [], canEdit: true });

    pickFilesLikeBrowser(fileInput(container), makeFiles(["one.png", "two.png"]));

    // 두 장을 골랐으면 POST 도 두 번이다(서버 개수 상한 때문에 순차로 올린다).
    await waitFor(() => expect(uploadCalls()).toHaveLength(2));
    const sent = uploadCalls().map(([, opts]) => opts.body.get("file").name);
    expect(sent).toEqual(["one.png", "two.png"]);
  });

  it("한 장도 못 올렸으면 '첨부했습니다'라고 말하지 않는다", async () => {
    const { container } = wrap({ attachments: [], canEdit: true });

    // 아무것도 안 고르고 취소한 경우(브라우저는 빈 목록으로 change 를 쏘기도 한다).
    pickFilesLikeBrowser(fileInput(container), []);

    await new Promise((r) => setTimeout(r, 30));
    expect(uploadCalls()).toHaveLength(0);
    expect(screen.queryByText(/파일을 첨부했습니다/)).toBeNull();
  });
});

// ── 드래그해서 놓기 ───────────────────────────────────────────────────────────

describe("드래그해서 놓기", () => {
  it("첨부가 이미 있어도 끌어다 놓을 자리가 있다", async () => {
    const { container } = wrap({ attachments: [IMG, PDF], canEdit: true });

    const zone = screen.getByTestId("attachment-dropzone");
    expect(zone).toBeInTheDocument();

    dropFiles(zone, makeFiles(["three.png"]));

    await waitFor(() => expect(uploadCalls()).toHaveLength(1));
    expect(container.textContent).toContain("끌어다 놓으세요");
  });

  it("첨부가 0건일 때도 같은 자리에서 같게 동작한다", async () => {
    wrap({ attachments: [], canEdit: true });

    dropFiles(screen.getByTestId("attachment-dropzone"), makeFiles(["one.png"]));

    await waitFor(() => expect(uploadCalls()).toHaveLength(1));
  });

  it("상한을 넘기면 조용히 무시하지 않고 이유를 말한다", async () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ ...PDF, id: "p" + i, filename: `f${i}.pdf` }));
    wrap({ attachments: many, canEdit: true });

    dropFiles(screen.getByTestId("attachment-dropzone"), makeFiles(["one.png"]));

    expect(await screen.findByText(/최대 10개까지/)).toBeInTheDocument();
    expect(uploadCalls()).toHaveLength(0);
  });

  /* mutationFn 은 한 번의 pick 안에서는 **순차로** 올려 서버의 개수 상한 검사가 서로를
   * 못 보고 통과하는 것을 막는다(위 upload 뮤테이션 주석). 그런데 그 보호는 "한 번의 pick
   * 안"에서만 유효하다 — 첫 배치가 아직 서버로 올라가는 도중(`upload.isPending`)에 드롭존을
   * 다시 눌러 두 번째 배치를 시작할 수 있다면, 두 배치가 **서로 다른 pick 호출**이라 각자
   * `list.length`(아직 갱신되지 않은 옛 값)만 보고 "지금 넣어도 상한 안 넘는다"고 판단한다.
   * 결과는 정확히 그 주석이 막으려던 것과 같다 — 개수 상한 검사가 서로를 못 본다. "파일 추가"
   * 버튼은 `disabled={upload.isPending || full}`로 이미 막아 뒀는데, 같은 문(pick)으로 들어가는
   * 드롭존에는 그 가드가 빠져 있었다. */
  it("첫 배치가 아직 올라가는 중이면 드롭존이 두 번째 배치를 겹쳐 보내지 않는다", async () => {
    // 8개 보유 + 2개씩 두 번 드롭 = 12개, 서버 상한(10개)을 넘긴다. 두 드롭 모두
    // list.length(8) 기준으로는 "8+2=10, 상한 안 넘음"이라 각자 통과해 버리는 것이 결함이다.
    const eight = Array.from({ length: 8 }, (_, i) => ({ ...PDF, id: "p" + i, filename: `f${i}.pdf` }));
    let resolveFirst;
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/tickets/page-1/attachments" && opts && opts.method === "POST") {
        // 첫 배치의 첫 파일 업로드가 응답을 받지 못한 채 걸려 있는 상태를 흉내낸다
        // (upload.isPending 이 true 인 동안).
        return new Promise((resolve) => { resolveFirst = resolve; });
      }
      return Promise.resolve({ ok: true });
    });

    wrap({ attachments: eight, canEdit: true });
    const zone = screen.getByTestId("attachment-dropzone");

    dropFiles(zone, makeFiles(["one.png", "two.png"]));
    await waitFor(() => expect(uploadCalls()).toHaveLength(1)); // 첫 배치의 첫 파일만 나가고 걸려 있다

    // 첫 배치가 아직 pending인 동안 같은 드롭존에 두 번째 배치를 놓는다.
    dropFiles(zone, makeFiles(["three.png", "four.png"]));
    await new Promise((r) => setTimeout(r, 30));

    // 두 번째 배치는 시작되면 안 된다 — POST 호출 수가 그대로여야 한다.
    expect(uploadCalls()).toHaveLength(1);

    resolveFirst({ ok: true });
  });
});

// ── 권한 ──────────────────────────────────────────────────────────────────────

describe("편집 권한이 없을 때", () => {
  it("버튼이 그냥 사라지지 않고 이유를 말한다", () => {
    const { container } = wrap({ attachments: [IMG], canEdit: false });

    expect(screen.getByText(/담당자/)).toBeInTheDocument();
    // 이유를 말하되 누를 수 없는 것은 여전히 없다 — 눌러 봐야 거절당하는 버튼은 안 그린다.
    expect(screen.queryByRole("button", { name: "파일 추가" })).toBeNull();
    expect(fileInput(container)).toBeNull();
    expect(screen.queryByTestId("attachment-dropzone")).toBeNull();
  });

  it("첨부 자체는 그대로 보인다 — 권한이 없다고 목록을 감추지 않는다", () => {
    wrap({ attachments: [IMG, PDF], canEdit: false });

    expect(screen.getByAltText("shot.png")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "spec.pdf" })).toBeInTheDocument();
    // 뗄 수는 없다.
    expect(screen.queryByRole("button", { name: /떼기/ })).toBeNull();
  });
});

// ── 오탐 방지: 정상 경로는 그대로 ─────────────────────────────────────────────

describe("정상 경로는 여전히 된다", () => {
  it("이미지는 썸네일로, 파일은 링크로, 뗄 수 있는 상태로 그린다", () => {
    wrap({ attachments: [IMG, PDF], canEdit: true });

    expect(screen.getByAltText("shot.png")).toHaveAttribute("src", "/api/x/a1");
    expect(screen.getByRole("link", { name: "spec.pdf" })).toHaveAttribute("href", "/api/x/a2");
    expect(screen.getByText("4 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "shot.png 떼기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "spec.pdf 떼기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "파일 추가" })).toBeEnabled();
  });

  it("10MB 를 넘는 파일은 올리지 않고 이유를 말한다", async () => {
    wrap({ attachments: [], canEdit: true });
    const big = new File(["x"], "huge.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });

    dropFiles(screen.getByTestId("attachment-dropzone"), [big]);

    expect(await screen.findByText(/10MB를 넘습니다/)).toBeInTheDocument();
    expect(uploadCalls()).toHaveLength(0);
  });

  it("꽉 찼으면 버튼을 잠그고 그 사실을 말한다", () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ ...PDF, id: "p" + i, filename: `f${i}.pdf` }));
    wrap({ attachments: many, canEdit: true });

    expect(screen.getByRole("button", { name: "파일 추가" })).toBeDisabled();
    expect(screen.getByText(/꽉 찼습니다/)).toBeInTheDocument();
  });
});
