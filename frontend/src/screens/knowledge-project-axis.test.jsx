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

  /* qa-contract-change: 아래 셋은 **좌측 내비**를 재고 있었다. 그 내비가 걷혔으므로
     (문서 개편 5번) 프로젝트 축의 유일한 입구 — 조건 줄의 고르개 — 에서 같은 사실을
     잰다. 「공통 문서가 프로젝트 갈래 밖에 선다」(D-415)는 그 갈래 제목 자체가
     없어졌으므로 「미지정이 늘 첫 후보로 선다」로 바꿔 잰다. */
  it("프로젝트 고르개가 **문서 0건 프로젝트까지** 이름으로 보여 준다", async () => {
    renderScreen();
    await userEvent.click(await screen.findByRole("combobox", { name: /프로젝트/ }));
    expect(await screen.findByRole("option", { name: "SK하이닉스 [용인 클러스터]" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "포스코DX" })).toBeTruthy();
  });

  it("「프로젝트 미지정」이 **첫 후보**로 선다 — 라벨이 내용에 대해 거짓말하지 않는다", async () => {
    renderScreen();
    await userEvent.click(await screen.findByRole("combobox", { name: /프로젝트/ }));
    const options = await screen.findAllByRole("option");
    const labels = options.map((o) => o.textContent);
    /* 후보의 비프로젝트 값을 「프로젝트 미지정」이라 부르므로 축 이름이 「프로젝트」로
       정직해졌다 — 「문서 범위」라는 우회 이름이 필요했던 이유가 없어졌다. */
    expect(screen.queryByText("문서 범위")).toBeNull();
    expect(labels).toContain("프로젝트 미지정");
    expect(labels.indexOf("프로젝트 미지정")).toBeLessThan(
      labels.indexOf("SK하이닉스 [용인 클러스터]"),
    );
  });

  it("자리가 여럿이면 진입하자마자 「프로젝트 미지정」으로 접히지 않는다", async () => {
    renderScreen("/knowledge");
    await screen.findByRole("combobox", { name: /프로젝트/ });

    /* 자동 선택은 **프로젝트가 하나일 때만**이다. 「미지정」이 늘 후보에 서게 된 뒤로
       후보 수로 재면 프로젝트가 없는 조직에서 매번 미지정으로 접힌다. */
    await waitFor(() => {
      expect(calls.some((p) => p.startsWith("/api/knowledge/documents"))).toBe(true);
    });
    const docCalls = calls.filter((p) => p.startsWith("/api/knowledge/documents"));
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
    /* qa-contract-change: 「전체」는 좌측 내비의 첫 줄이었다. 지금 기다릴 것은 조건
       줄의 프로젝트 고르개다. */
    await screen.findByRole("combobox", { name: /프로젝트/ });

    await waitFor(() => {
      for (const input of document.querySelectorAll("input")) {
        expect(UUID_RE.test(input.value || "")).toBe(false);
      }
      expect(UUID_RE.test(document.body.textContent || "")).toBe(false);
    });
  });
});

/* qa-contract-change: 「폴더 삭제 — 묻고 지운다」가 여기 있었다. 폴더 축이 화면에서
   걷히면서(문서 개편 1·5번) 폴더를 만들거나 지우는 입구가 아예 없다. 확인 창을 재던
   시험을 그대로 두면 없는 단추를 찾다 빨간불이 되므로, 재는 사실을 **입구가 없다**로
   바꾼다 — 그것이 이 회차가 실제로 만든 상태다. 서버의 폴더 엔드포인트 넷과 표·트리거는
   그대로 있으므로 되돌리기는 화면 파일 하나다. */
describe("폴더 축은 화면에 없다", () => {
  it("문서 화면에 폴더를 만들거나 지우는 입구가 없다", async () => {
    renderScreen("/knowledge?project=none");
    await screen.findByRole("combobox", { name: /프로젝트/ });

    expect(screen.queryByText("폴더")).toBeNull();
    expect(screen.queryByRole("button", { name: /폴더 추가/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /폴더 삭제/ })).toBeNull();
    /* 그리고 트리를 **묻지도 않는다** — 안 그리면서 묻는 질의는 순전한 낭비다. */
    expect(calls.some((p) => p.includes("/tree"))).toBe(false);
  });
});
