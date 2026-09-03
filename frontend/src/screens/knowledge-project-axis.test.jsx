/* 문서 화면의 **프로젝트 축** — 후보가 실제로 오는가, 그리고 안 오면 무엇이 보이는가.
 *
 * ## 왜 이 파일이 따로 있는가
 *
 * 정적 전량과 vitest 2,855 시험이 전부 초록인 채로 운영에서 이것이 깨져 있었다:
 * 좌측 내비에 프로젝트가 **한 개도** 안 나오고, 새 문서 모달과 필터 줄은 프로젝트 이름
 * 대신 `62134ac8-831e-…` 를 보여 줬다.
 *
 * 원인은 한 줄이다 — 화면이 `/api/projects?page_size=200` 을 불렀고 서버 상한은 100 이라
 * (`app/core/pagination.py::MAX_PAGE_SIZE`) 그 질의는 **매번 422** 였다. 후보가 빈 배열이
 * 되고, 고르개는 고른 값의 이름을 못 찾아 값(UUID)을 그대로 라벨로 그렸다.
 *
 * 기존 시험이 이것을 못 잡은 이유도 한 줄이다: 대역이 **주소를 안 보고** 무조건 프로젝트
 * 두 건을 돌려줬다. 그래서 여기서 세우는 성질은 「무엇을 돌려주면 무엇이 보이는가」가
 * 아니라 **「무엇을 요청하는가」**, 그리고 **「요청이 실패하면 무엇이 보이는가」** 다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "u-1", display_name: "나", role: "user" } }),
}));

import { Knowledge } from "./Knowledge.jsx";
import { MAX_PAGE_SIZE } from "./project-queries.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const SPACE = "space-org";
const P1 = "62134ac8-831e-4071-bb07-d7c3144d85eb";
const P2 = "0a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d";
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const calls = [];
/* 후보 질의를 서버처럼 **검사한다**. 상한을 넘으면 422 를 흉내 내 거절한다 — 이 한 줄이
   이 파일의 존재 이유다. 대역이 주소를 안 보면 운영과 다른 세계를 시험하게 된다. */
let projectsRejected = false;

function projectsResponse(path) {
  const url = new URL(String(path), "https://x");
  const size = Number(url.searchParams.get("page_size") || 20);
  if (size > MAX_PAGE_SIZE) {
    projectsRejected = true;
    const err = new Error("입력값을 확인해 주세요.");
    err.status = 422;
    return Promise.reject(err);
  }
  return Promise.resolve({
    items: [
      { id: P1, name: "SK하이닉스 [용인 클러스터]", code: "AAAAAA" },
      { id: P2, name: "포스코DX", code: "BBBBBB" },
    ],
    total: 2,
    page: 1,
    page_size: size,
  });
}

function docs(total = 0) {
  return { items: [], authors: [], total, limit: 100, offset: 0 };
}

beforeEach(() => {
  calls.length = 0;
  projectsRejected = false;
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const text = String(path);
    calls.push(text);
    if (text.startsWith("/api/projects")) return projectsResponse(text);
    if (text.startsWith("/api/knowledge/spaces/")) {
      return Promise.resolve({ folders: [{ id: "f-1", name: "01. 회의록", depth: 0, children: [] }] });
    }
    if (text === "/api/knowledge/spaces") {
      /* 공간은 **조직 공간 하나뿐**이다 — 프로젝트 둘은 아직 문서가 없어 공간이 없다.
         운영이 정확히 이 모양이었다(프로젝트 22개, 공간 11개). */
      return Promise.resolve({ items: [{ id: SPACE, name: "팀 문서", owner_kind: "organization" }] });
    }
    if (text === "/api/knowledge/tags") return Promise.resolve({ items: [] });
    if (text === "/api/knowledge/categories") return Promise.resolve({ items: [] });
    if (text === "/api/knowledge/summary") {
      return Promise.resolve({ total: 112, recent: 0, favorites: 0, drafts: 0 });
    }
    if (text === "/api/knowledge/templates") {
      return Promise.resolve({ items: [{ id: "blank", name: "빈 문서", help: "빈 상태로 시작합니다.", empty: true }] });
    }
    if (text.startsWith("/api/knowledge/recent")) return Promise.resolve({ items: [] });
    return Promise.resolve(docs());
  });
});

function renderScreen(entry = "/knowledge") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Knowledge />
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function projectCalls() {
  return calls.filter((p) => p.startsWith("/api/projects"));
}

describe("프로젝트 후보 질의 — 서버가 받아 주는 요청인가", () => {
  it("후보를 **묻기는 하되** 서버 상한을 넘는 page_size 를 안 보낸다", async () => {
    renderScreen();
    await waitFor(() => expect(projectCalls().length).toBeGreaterThan(0));

    for (const path of projectCalls()) {
      const size = Number(new URL(path, "https://x").searchParams.get("page_size") || 20);
      expect(size).toBeLessThanOrEqual(MAX_PAGE_SIZE);
    }
    /* 대역이 실제로 거절한 적이 없어야 한다 — 「상한을 넘겼는가」의 반대편 증거다. */
    expect(projectsRejected).toBe(false);
  });

  it("좌측 내비가 **문서 0건 프로젝트까지** 이름으로 보여 준다", async () => {
    renderScreen();
    expect(await screen.findByText("SK하이닉스 [용인 클러스터]")).toBeTruthy();
    expect(await screen.findByText("포스코DX")).toBeTruthy();
  });

  it("공통 문서는 프로젝트 갈래 **밖**에 선다 — 제목이 내용에 대해 거짓말하지 않는다", async () => {
    renderScreen();
    const common = await screen.findByRole("button", { name: "공통 문서" });

    /* 절의 제목은 「프로젝트」가 아니다 — 그 아래에 공통 문서가 함께 서기 때문이다.
       좌측 내비와 위 필터 줄이 **같은 낱말**을 쓰므로 이름은 화면에 둘 이상 있다. */
    expect(screen.getAllByText("문서 범위").length).toBeGreaterThan(0);

    /* 그리고 순서가 뜻이다: 「공통 문서」 → 갈래 이름 「프로젝트」 → 프로젝트들.
       공통 문서가 프로젝트 줄들 **사이**에 끼면 다시 같은 오해가 생긴다. */
    const group = screen.getByText("프로젝트");
    const first = await screen.findByRole("button", { name: "SK하이닉스 [용인 클러스터]" });
    const before = (a, b) => Boolean(
      a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(before(common, group)).toBe(true);
    expect(before(group, first)).toBe(true);
  });

  it("자리가 여럿이면 진입하자마자 「공통 문서」로 접히지 않는다", async () => {
    renderScreen("/knowledge");
    await screen.findByText("포스코DX");

    /* 자동 선택은 **고를 것이 하나일 때만**이다. 공간이 하나(조직)라는 이유로 켜지면
       사용자는 프로젝트 문서가 통째로 빠진 목록을 첫 화면으로 받는다. */
    const docCalls = calls.filter((p) => p.startsWith("/api/knowledge/documents"));
    expect(docCalls.length).toBeGreaterThan(0);
    for (const path of docCalls) expect(path).not.toContain("project_id=none");
  });
});

describe("후보 질의가 실패해도 — 사용자에게 UUID 를 보여 주지 않는다", () => {
  beforeEach(() => {
    /* 서버가 어떤 이유로든 후보를 못 줄 때(권한·장애·계약 어긋남). 운영에서 실제로
       일어난 상태이고, 그때 화면이 무엇을 그리는가가 이 시험의 대상이다. */
    const inner = apiMock.getMockImplementation();
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/projects")) {
        const err = new Error("실패");
        err.status = 500;
        return Promise.reject(err);
      }
      return inner(path);
    });
  });

  it("고른 프로젝트의 이름을 몰라도 필터 줄에 식별자를 그리지 않는다", async () => {
    renderScreen(`/knowledge?project=${P1}`);
    await screen.findByRole("button", { name: "전체" });

    await waitFor(() => {
      for (const input of document.querySelectorAll("input")) {
        expect(UUID_RE.test(input.value || "")).toBe(false);
      }
      expect(UUID_RE.test(document.body.textContent || "")).toBe(false);
    });
  });
});

describe("폴더 삭제 — 묻고 지운다", () => {
  it("확인 창을 지나기 전에는 DELETE 를 안 보낸다", async () => {
    renderScreen("/knowledge?project=none");
    const nav = await screen.findByText("폴더");
    expect(nav).toBeTruthy();

    const del = await screen.findByRole("button", { name: "01. 회의록 폴더 삭제" });
    await userEvent.click(del);

    /* 확인 창이 떠 있고, 아직 아무것도 안 지웠다. */
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/문서는 지워지지 않고/)).toBeTruthy();
    expect(calls.some((p) => p.startsWith("/api/knowledge/folders/"))).toBe(false);
  });
});
