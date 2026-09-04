import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigationType } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 휴지통의 조작기 — 탭 · 뒤로가기 · 선택 · 정렬 · 미리보기.
 *
 * 사용자가 화면을 보고 말했다: 「탭도 이상하고 뒤로가기도 안 되고 본문도 안 보이고 그리드도
 * 이상하고 정렬 안 돼 있고」. 다섯이 전부 실제 결함이었고 뿌리가 서로 달랐다.
 *
 *   탭       한 축(`?kind=`)을 둘이 나눠 쥐었고(판독 줄 + 드롭다운), 숫자를 **이미 걸러진**
 *            목록에서 세서 문서 탭에서 「티켓 0」이 떴다. 조건 결과가 0건이면 조작기가
 *            통째로 사라져 조건을 풀 자리도 없어졌다.
 *   뒤로가기  조건을 바꿀 때마다 히스토리를 **push** 했다. 세 번 누르면 화면을 벗어나는 데
 *            네 번 눌러야 했다.
 *   선택     조건을 바꿔도 안 비웠다. 화면에 없는 줄이 「선택 영구 삭제」로 사라졌다.
 *   정렬     조작기가 아예 없었다.
 *   본문     티켓과 옛 미러 문서는 제목 말고 볼 것이 없었다 — 영구 삭제는 되돌릴 수 없는데도.
 *
 * 각 시험에 반례를 붙인다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Trash } from "./Trash.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TICKET = {
  id: "t-1", item_type: "ticket", type_label: "티켓", source: "legacy",
  title: "로그인 오류", excerpt: "", space: "", deleted_by: "박세찬",
  deleted_at: "2026-08-25T02:00:00", purge_after: "2026-09-01T02:00:00", can_manage: true,
};
const DOC = {
  id: "doc:11111111-2222-3333-4444-555555555555", item_type: "document", type_label: "문서",
  source: "knowledge", title: "서버 인프라 현황", excerpt: "본문 첫 줄입니다",
  space: "프로젝트 미지정", deleted_by: "이성진",
  deleted_at: "2026-08-26T02:00:00", purge_after: "2026-09-02T02:00:00", can_manage: true,
};

const calls = [];
let here = null;
/* 마지막 이동이 push 였나 replace 였나. `location.key` 는 replace 에서도 새로 찍히므로
   push/replace 를 구별하지 못한다 — 라우터가 직접 말해 주는 값을 쓴다. */
let lastNav = null;

function Probe() {
  here = useLocation();
  lastNav = useNavigationType();
  return null;
}

function stub(rows, extra) {
  apiMock.mockImplementation((path, options) => {
    const p = String(path);
    calls.push(p);
    if (p.startsWith("/api/trash?")) {
      const url = new URL(p, "https://x");
      const kind = url.searchParams.get("kind");
      const items = kind ? rows.filter((r) => r.item_type === kind) : rows;
      return Promise.resolve({
        items, total: items.length, retention_days: 7,
        document_autopurge: true, document_retention_days: 7,
        sort: url.searchParams.get("sort") || "deleted_at",
        dir: url.searchParams.get("dir") || "desc",
        // 조건과 무관한 개수 — 서버가 좁히기 전에 센다.
        counts: {
          ticket: rows.filter((r) => r.item_type === "ticket").length,
          document: rows.filter((r) => r.item_type === "document").length,
          all: rows.length,
          urgent: (extra && extra.urgent) || 0,
        },
        ...(extra && extra.body),
      });
    }
    if (p.endsWith("/preview")) {
      return Promise.resolve({
        id: "t-1", item_type: "ticket", title: "로그인 오류",
        blocks: [{ kind: "paragraph", text: "지우기 전에 보는 본문" }], blocks_error: null,
      });
    }
    if (options && options.method === "POST") return Promise.resolve({ ok: true });
    return Promise.resolve({});
  });
}

function renderScreen(entry = "/team-docs/trash") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}><Probe /><Trash /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
  return qc;
}

beforeEach(() => {
  calls.length = 0;
  here = null;
  lastNav = null;
  apiMock.mockReset();
  stub([DOC, TICKET]);
});

// ── 탭 ──────────────────────────────────────────────────────────────────────

describe("종류 탭", () => {
  it("🔴 조건 결과가 0건이어도 탭 줄이 남고 조건을 풀 자리가 있다", async () => {
    // 티켓만 있는 휴지통에서 「문서」를 고른 상태. 예전에는 여기서 탭이 통째로 사라지고
    // 「휴지통이 비어 있습니다 / 아직 지운 티켓이나 문서가 없습니다」라는 거짓말이 떴다.
    stub([TICKET]);
    renderScreen("/team-docs/trash?kind=document");

    expect(await screen.findByText("이 종류에는 항목이 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /전체/ })).toBeInTheDocument();
    expect(screen.queryByText("아직 지운 티켓이나 문서가 없습니다")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "전체 보기" }));
    await screen.findByText("로그인 오류");
  });

  it("탭을 바꾸면 조건이 서버 질의에 실린다", async () => {
    renderScreen();
    await screen.findByText("로그인 오류");
    await userEvent.click(screen.getByRole("tab", { name: /티켓/ }));
    await waitFor(() => expect(calls.some((p) => p.includes("kind=ticket"))).toBe(true));
  });
});

// ── 뒤로가기 ────────────────────────────────────────────────────────────────

describe("뒤로가기", () => {
  it("🔴 탭을 눌러도 히스토리가 안 쌓인다 — 뒤로가기 한 번으로 화면을 벗어난다", async () => {
    renderScreen();
    await screen.findByText("로그인 오류");

    await userEvent.click(screen.getByRole("tab", { name: /티켓/ }));
    await waitFor(() => expect(here.search).toContain("kind=ticket"));
    expect(lastNav).toBe("REPLACE");

    await userEvent.click(screen.getByRole("tab", { name: /전체/ }));
    await waitFor(() => expect(here.search).not.toContain("kind="));
    expect(lastNav).toBe("REPLACE");
  });

  it("반례 — 조건은 그래도 주소에 남는다(북마크·목록 복귀가 그 값을 쓴다)", async () => {
    renderScreen();
    await screen.findByText("로그인 오류");
    await userEvent.click(screen.getByRole("tab", { name: /티켓/ }));
    await waitFor(() => expect(here.search).toContain("kind=ticket"));
  });

  it("주소에 있던 모르는 키는 안 지운다 — 알림 딥링크가 그 값을 싣는다", async () => {
    renderScreen("/team-docs/trash?from=notification");
    await screen.findByText("로그인 오류");
    await userEvent.click(screen.getByRole("tab", { name: /티켓/ }));
    await waitFor(() => expect(here.search).toContain("kind=ticket"));
    expect(here.search).toContain("from=notification");
  });
});

// ── 선택 ────────────────────────────────────────────────────────────────────

describe("선택", () => {
  async function selectFirstRow() {
    const row = (await screen.findByText("로그인 오류")).closest("tr");
    await userEvent.click(within(row).getByRole("checkbox"));
  }

  it("🔴 탭을 바꾸면 선택이 **비워진다** — 돌아와도 되살아나지 않는다", async () => {
    /* 두 겹이 걸려 있고 이 시험은 **안쪽**을 잰다.
     *   바깥: 일괄 동작은 지금 화면에 있는 줄과의 교집합만 보낸다.
     *   안쪽: 조건이 바뀌면 고른 것 자체를 비운다.
     * 바깥만 있으면 「티켓 → 문서 → 티켓」으로 돌아오는 순간 옛 선택이 되살아나, 사용자가
     * 고른 적 없는 줄이 다시 「선택 영구 삭제」의 대상이 된다. 그래서 **돌아와서** 잰다. */
    renderScreen();
    await selectFirstRow();
    expect(screen.getByText(/1개 선택/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /문서/ }));
    await waitFor(() => expect(screen.queryByText("로그인 오류")).toBeNull());
    expect(screen.queryByText(/1개 선택/)).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: /전체/ }));
    const row = (await screen.findByText("로그인 오류")).closest("tr");
    expect(within(row).getByRole("checkbox")).not.toBeChecked();
    expect(screen.queryByText(/1개 선택/)).toBeNull();
  });

  it("🔴 그리고 바깥 겹 — 화면에 없는 줄은 일괄 요청에 안 실린다", async () => {
    /* 조건을 안 바꿔도 목록은 변한다(15초 폴링·복원·남이 지운 것). 안쪽 겹이 안 도는
     * 그 경우에도 되돌릴 수 없는 요청에 화면 밖 id 가 실리면 안 된다. */
    renderScreen();
    await selectFirstRow();

    // 폴링이 그 줄을 걷어 간 상황을 만든다.
    stub([DOC]);
    await waitFor(() => expect(screen.queryByText("로그인 오류")).toBeNull(), { timeout: 20000 });
    expect(screen.queryByText(/1개 선택/)).toBeNull();
  }, 25000);

  it("반례 — 같은 탭 안에서는 선택이 유지된다(비우기를 아무 데나 걸면 못 고른다)", async () => {
    renderScreen();
    await selectFirstRow();
    expect(screen.getByText(/1개 선택/)).toBeInTheDocument();
    // 폴링이 한 번 돌아도 유지된다.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByText(/1개 선택/)).toBeInTheDocument();
  });

  it("🔴 확인 창이 무엇이 죽는지 **이름으로** 말한다 — 개수만으로는 알아챌 수 없다", async () => {
    renderScreen();
    await selectFirstRow();
    await userEvent.click(screen.getByRole("button", { name: "선택 영구 삭제" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/로그인 오류/)).toBeInTheDocument();
    expect(within(dialog).getByText(/되돌릴 수 없습니다/)).toBeInTheDocument();
  });

  it("단건 영구 삭제 확인도 그 줄의 이름을 말한다", async () => {
    renderScreen();
    const row = (await screen.findByText("로그인 오류")).closest("tr");
    await userEvent.click(within(row).getByRole("button", { name: "영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/‘로그인 오류’/)).toBeInTheDocument();
  });
});

// ── 정렬 ────────────────────────────────────────────────────────────────────

describe("정렬", () => {
  it("🔴 머리글을 누르면 축이 서버 질의에 실리고 주소에 남는다", async () => {
    renderScreen();
    await screen.findByText("로그인 오류");

    await userEvent.click(screen.getByRole("button", { name: /삭제 예정/ }));
    await waitFor(() => expect(calls.some((p) => p.includes("sort=purge_after"))).toBe(true));
    expect(here.search).toContain("sort=purge_after");
  });

  it("같은 머리글을 다시 누르면 방향이 뒤집힌다", async () => {
    renderScreen();
    await screen.findByText("로그인 오류");
    const header = screen.getByRole("button", { name: /삭제 예정/ });

    await userEvent.click(header);
    await waitFor(() => expect(here.search).toContain("dir=asc"));
    await userEvent.click(screen.getByRole("button", { name: /삭제 예정/ }));
    // 기본 방향(`desc`)은 주소에서 지워진다 — 아무 조건도 안 건 화면의 주소가 깨끗해야
    // 「지금 뭔가 걸려 있나」를 주소만 보고 알 수 있다. 실제로 나간 질의로 확인한다.
    await waitFor(() => expect(calls.some((p) => p.includes("sort=purge_after&dir=desc"))).toBe(true));
    expect(here.search).not.toContain("dir=asc");
  });

  it("지금 정렬 중인 열이 aria-sort 로 낭독된다 — 화살표만으로는 안 들린다", async () => {
    renderScreen("/team-docs/trash?sort=title&dir=asc");
    await screen.findByText("로그인 오류");
    const cells = screen.getAllByRole("columnheader");
    const title = cells.find((c) => c.textContent.includes("제목"));
    expect(title).toHaveAttribute("aria-sort", "ascending");
  });

  it("반례 — 주소의 모르는 축은 기본값으로 떨어진다(화살표가 거짓말하지 않는다)", async () => {
    renderScreen("/team-docs/trash?sort=nonsense&dir=sideways");
    await screen.findByText("로그인 오류");
    await waitFor(() => expect(calls.some((p) => p.includes("sort=deleted_at&dir=desc"))).toBe(true));
  });
});

// ── 본문 ────────────────────────────────────────────────────────────────────

describe("지우기 전에 본문 보기", () => {
  it("🔴 티켓 제목을 누르면 본문이 창으로 열린다 — 예전에는 볼 방법이 없었다", async () => {
    renderScreen();
    await userEvent.click(await screen.findByRole("button", { name: "로그인 오류" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("지우기 전에 보는 본문")).toBeInTheDocument();
    expect(calls.some((p) => p === "/api/trash/t-1/preview")).toBe(true);
  });

  it("반례 — 우리 문서는 창이 아니라 그 문서 화면으로 간다(거기 복원·이력이 있다)", async () => {
    renderScreen();
    const link = await screen.findByRole("link", { name: /서버 인프라 현황/ });
    expect(link.getAttribute("href")).toBe("#/knowledge/11111111-2222-3333-4444-555555555555");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("문서 줄은 본문 첫머리를 제목 아래에 보여 준다", async () => {
    renderScreen();
    expect(await screen.findByText("본문 첫 줄입니다")).toBeInTheDocument();
  });
});

// ── 「더 보기」의 상한 ──────────────────────────────────────────────────────

describe("더 보기", () => {
  it("🔴 상한(1000)을 넘겨 보내지 않는다 — 서버가 422 를 내고 화면이 통째로 죽는다", async () => {
    /* 이 회차가 문서 원천의 200건 벽을 없앴는데 **바깥 벽(1000)** 은 그대로였다.
       `limit` 이 이제 주소에 실리므로 한 번 넘기면 새로고침해도 안 낫는다. */
    stub([DOC, TICKET], { body: { total: 5000 } });
    renderScreen("/team-docs/trash?limit=980");
    await screen.findByText("로그인 오류");
    calls.length = 0;

    await userEvent.click(screen.getByRole("button", { name: /휴지통 더 보기/ }));
    await waitFor(() => expect(calls.some((p) => p.includes("limit=1000"))).toBe(true));
    const limits = calls
      .map((p) => Number((/[?&]limit=(\d+)/.exec(p) || [])[1]))
      .filter((n) => Number.isFinite(n) && n > 0);
    expect(Math.max(...limits), calls.join(" | ")).toBeLessThanOrEqual(1000);
  });

  it("주소로 들어온 큰 값도 상한에서 자른다", async () => {
    stub([DOC, TICKET], { body: { total: 5000 } });
    renderScreen("/team-docs/trash?limit=9999");
    await screen.findByText("로그인 오류");
    expect(calls.some((p) => p.includes("limit=1000"))).toBe(true);
    expect(calls.some((p) => p.includes("limit=9999"))).toBe(false);
  });

  it("상한에 닿으면 단추를 안 그린다 — 눌러도 같은 목록이 다시 올 뿐이다", async () => {
    stub([DOC, TICKET], { body: { total: 5000 } });
    renderScreen("/team-docs/trash?limit=1000");
    await screen.findByText("로그인 오류");
    expect(screen.queryByRole("button", { name: /휴지통 더 보기/ })).toBeNull();
  });

  it("반례 — 상한 아래에서는 그대로 늘어난다", async () => {
    stub([DOC, TICKET], { body: { total: 5000 } });
    renderScreen();
    await screen.findByText("로그인 오류");
    await userEvent.click(screen.getByRole("button", { name: /휴지통 더 보기/ }));
    await waitFor(() => expect(calls.some((p) => p.includes("limit=200"))).toBe(true));
  });
});

// ── 급한 건수 ───────────────────────────────────────────────────────────────

describe("24시간 내 영구 삭제", () => {
  it("서버가 센 값을 그리고, 누르면 임박한 순으로 세워 준다", async () => {
    stub([DOC, TICKET], { urgent: 3 });
    renderScreen();
    const chip = await screen.findByText("24시간 내 영구 삭제 3");
    await userEvent.click(chip);
    await waitFor(() => expect(here.search).toContain("sort=purge_after"));
    expect(here.search).toContain("dir=asc");
  });

  it("반례 — 0건이면 안 그린다(늘 서 있는 경고는 경고가 아니다)", async () => {
    stub([DOC, TICKET], { urgent: 0 });
    renderScreen();
    await screen.findByText("로그인 오류");
    expect(screen.queryByText(/24시간 내 영구 삭제/)).toBeNull();
  });
});
