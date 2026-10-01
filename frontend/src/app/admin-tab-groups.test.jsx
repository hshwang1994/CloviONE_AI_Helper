import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: AI 사용 통계 그릇의 짝을 「프롬프트 사용 탭」에서 「호출 기록 탭」으로 옮겼다 — 프롬프트 · 정책 사용 탭을 걷었다(D-543, 옛 주소는 그 목록 화면으로 넘긴다). 옛 주소가 살아 있다 · 탭 순서가 들어온 길과 무관하다 · 그릇과 탭의 역할이 같다는 성질은 그대로 잰다. */
/* 관리자 IA 재구성 — 짝을 이루던 화면이 한 화면의 탭이 됐다 (지시 30 · 41 · 51).
 *
 * 여기서 지키는 것은 "합쳤다"가 아니라 **합치면서 잃지 않았다**이다.
 *
 *  1. 옛 주소가 죽지 않는다 — `/restore-drills` 로 들어오면 그 탭이 열린다.
 *  2. 리다이렉트가 아니라 **그 자리에서** 연다 — 리다이렉트는 해시 쿼리를 버려서
 *     저장된 뷰 링크(`#/restore-drills?status=failed`)의 필터가 사라진다.
 *  3. 탭 안의 목록이 자기 필터를 주소에 써도 `?tab=` 이 살아남는다
 *     (datascreen-view.js 의 owned-key 규약).
 *  4. 권한은 그대로다 — 그릇의 역할 집합과 안쪽 탭의 역할 집합이 같아야 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));

let mockRole = "system_admin";
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: mockRole, id: "a1" }, isLoading: false, isError: false }),
}));

import AdminRoutes, { TAB_GROUPS } from "./AdminRoutes.jsx";
import { SCREEN_ROLES } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

beforeEach(() => {
  mockRole = "system_admin";
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  window.location.hash = "#/";
});

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes><Route path="*" element={<AdminRoutes />} /></Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/* 합쳐진 짝 — (옛 주소, 대표 주소, 옛 주소로 들어왔을 때 켜져 있어야 하는 탭 라벨) */
const MERGED = [
  ["/restore-drills", "/backup", "복구 리허설"],
  ["/approval-delegations", "/approvals", "승인 위임"],
  ["/audit-anomalies", "/audit", "이상 징후"],
  ["/ai-usage-records", "/ai-usage", "호출 기록"],
  ["/scheduler-calendar", "/schedules", "달력"],
];

describe("옛 주소가 죽지 않는다", () => {
  it.each(MERGED)("%s 로 들어오면 그 탭이 켜진 채 열린다", async (oldPath, hostPath, tabLabel) => {
    renderAt(oldPath);
    const tab = await screen.findByRole("tab", { name: tabLabel }, { timeout: 5000 });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it.each(MERGED)("대표 주소 %1$s 로 들어오면 첫 탭이 켜진다 (%0$s 는 두 번째)", async (oldPath, hostPath, tabLabel) => {
    renderAt(hostPath);
    const tab = await screen.findByRole("tab", { name: tabLabel }, { timeout: 5000 });
    expect(tab).toHaveAttribute("aria-selected", "false");
  });
});

/* 🔴 탭 순서는 들어온 주소와 무관하다 (D-501).
 *
 * 옛 주소로 들어오면 그 탭을 맨 앞으로 옮겨 기본 탭으로 삼던 때가 있었다 — `/restore-drills` 는 [복구 리허설|백업],
 * `/backup` 은 [백업|복구 리허설]이었다. 같은 그릇이 들어온 길에 따라 탭 자리가 바뀌면 사람은 탭을 자리로 기억할 수
 * 없다. 옛 주소가 바꾸는 것은 **켜질 탭** 하나뿐이다(위 「옛 주소가 죽지 않는다」가 그 절반을 지킨다). */
describe("탭 순서는 들어온 주소와 무관하다 (D-501)", () => {
  const tabOrder = async (path, anyLabel) => {
    await screen.findByRole("tab", { name: anyLabel }, { timeout: 5000 });
    // 그릇의 탭 줄만 센다 — 탭 안 화면의 세그먼티드(보기 기준 · 기간)도 탭 역할이라 페이지 전체를 세면 켜진 탭에 따라 수가 달라진다.
    return within(screen.getAllByRole("tablist")[0]).getAllByRole("tab").map((t) => t.textContent);
  };

  it.each(MERGED)("%s 와 %s 가 같은 순서로 탭을 세운다", async (oldPath, hostPath, tabLabel) => {
    const viaOld = renderAt(oldPath);
    const fromOld = await tabOrder(oldPath, tabLabel);
    viaOld.unmount();
    renderAt(hostPath);
    const fromHost = await tabOrder(hostPath, tabLabel);
    expect(fromOld).toEqual(fromHost);
    // 순서의 정본은 그릇 정의다 — 대표 탭이 언제나 맨 앞이다.
    const group = TAB_GROUPS.find((g) => g.path === hostPath);
    expect(fromHost).toEqual(group.tabs.map((t) => t.label));
  });
});

/* 형제 탭과 같은 곳으로 가는 머리 단추는 두지 않는다 (D-501).
 *
 * 탭 그릇 안의 목록 화면에 「이상 징후 보기」 · 「감사 로그 전체」 · 「백업 목록」 · 「정책 사용 통계」 · 「프롬프트
 * 사용 통계」 머리 단추가 있었다. 전부 바로 옆 탭이 이미 가는 곳이다 — 한 이동이 두 자리에 있으면 둘 중 무엇을
 * 눌러야 하는지를 사람이 따져야 한다. 그릇 정의(`TAB_GROUPS`)와 registry 를 맞대 보고, 새로 생겨도 여기서 멈춘다. */
describe("형제 탭을 가리키는 머리 단추가 없다 (D-501)", () => {
  it("탭 그릇 안 화면의 머리 이동이 형제 탭의 주소를 가리키지 않는다", () => {
    const bad = [];
    for (const g of TAB_GROUPS) {
      const siblingPaths = new Set([g.path, ...g.tabs.map((t) => "/" + t.key)]);
      for (const t of g.tabs) {
        const cfg = REGISTRY[t.key];
        for (const a of (cfg && cfg.headerActions) || []) {
          if (typeof a.navigate !== "function") continue;
          const target = String(a.navigate()).replace(/^#/, "").split("?")[0];
          if (siblingPaths.has(target)) bad.push(`${t.key}: 「${a.label}」 → ${target}`);
        }
      }
    }
    expect(bad, bad.join("\n")).toEqual([]);
  });

  it("반례 — 그릇 밖으로 가는 머리 이동(백업 일정 설정)은 그대로 선다", () => {
    const labels = (REGISTRY["restore-drills"].headerActions || []).map((a) => a.label);
    expect(labels).toEqual(["백업 일정 설정"]);
  });
});

describe("탭 안의 화면이 제목을 두 번 그리지 않는다", () => {
  it("그릇이 h1 하나만 그린다 — 안쪽 목록은 자기 PageHeader 를 안 그린다", async () => {
    renderAt("/backup");
    await screen.findByRole("tab", { name: "복구 리허설" }, { timeout: 5000 });
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent("백업");
  });
});

describe("권한이 그릇과 안쪽 탭에서 같다", () => {
  it.each([
    ["/backup", ["backup", "restore-drills"]],
    ["/approvals", ["approvals", "approval-delegations"]],
    ["/audit", ["audit", "audit-anomalies"]],
    ["/ai-usage", ["ai-usage", "ai-usage-stats", "ai-usage-records"]],
    ["/schedules", ["schedules", "scheduler-calendar"]],
  ])("%s 그릇의 역할 집합이 안쪽 탭들과 정확히 같다", (hostPath, keys) => {
    const sets = keys.map((k) => JSON.stringify([...(SCREEN_ROLES[k] || [])].sort()));
    // 그릇이 넓으면 못 보는 사람이 빈 화면을 보고, 좁으면 볼 수 있는 사람이 못 본다.
    expect(new Set(sets).size, `${hostPath}: ${keys.join(" vs ")} 의 역할 집합이 다르다`).toBe(1);
  });

  it("역할이 모자라면 그릇 자체가 권한 안내를 보여 준다", async () => {
    mockRole = "user";
    renderAt("/audit");
    expect(await screen.findByText("권한이 없습니다", {}, { timeout: 5000 })).toBeInTheDocument();
  });

  /* 🔴 **막다른 길에서 막다른 길로 보내지 않는다.**
   *
   * 이 안내의 단추는 `href="#/"` 였는데 두 라우트 표 어디에도 `path="/"` 가 없어서,
   * 권한 벽에서 유일한 단추를 누르면 「찾을 수 없습니다」로 갔다. 라벨이 「대시보드로
   * 이동」이면 대시보드로 가야 한다. */
  it("🔴 그 안내의 단추가 실제로 대시보드를 가리킨다", async () => {
    mockRole = "user";
    renderAt("/audit");
    await screen.findByText("권한이 없습니다", {}, { timeout: 5000 });
    const go = screen.getByRole("link", { name: "대시보드로 이동" });
    expect(go.getAttribute("href")).toBe("#/dashboard");
  });
});

/* 그릇의 머리 — 제목은 고정이고(D-452), 도움말은 제목 옆 `?` 이며(D-453), 탭 본문의 머리
   동작은 그릇 머리의 오른쪽에 선다(D-454). 예전에는 탭 라벨이 h1 이 됐고(「복구 리허설」),
   도움말은 탭 아래 오른쪽 정렬 줄의 안내 상자였고, 동작은 그 상자 옆에 붙어 있었다. */
import { REGISTRY } from "../screens/registry.js";

describe("그릇의 머리 — 제목·도움말·동작 (D-452 · D-453 · D-454)", () => {
  it("옛 주소 /restore-drills 로 들어와도 h1 은 그릇 제목 「백업」이다 — 탭 라벨이 아니다", async () => {
    renderAt("/restore-drills");
    await screen.findByRole("tab", { name: "복구 리허설" }, { timeout: 5000 });
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent("백업");
    expect(h1s[0]).not.toHaveTextContent("복구 리허설");
  });

  it("탭 본문의 머리 동작이 그릇 머리(.k-page-head) 안에 선다 — 탭 아래 별도 줄이 아니다", async () => {
    renderAt("/backup");
    // 목록이 비어 있으면 빈 상태도 같은 이름의 CTA 를 그린다 — 머리에 선 것을 골라 본다.
    // 머리 슬롯은 portal 이라 호스트가 붙기 전 한 틱은 본문 자리(fallback)에 그려진다 — 첫
    // 매치를 잡으면 그 틱을 재게 되므로(기계가 느릴 때 실제로 빨갛다) 머리에 설 때까지 기다린다.
    const inHeadNow = () =>
      screen.getAllByRole("button", { name: "백업 실행" }).filter((b) => b.closest(".k-page-head"));
    await waitFor(() => expect(inHeadNow()).toHaveLength(1), { timeout: 5000 });
    const inHead = inHeadNow();
    expect(inHead).toHaveLength(1);
    expect(inHead[0].closest('[role="tabpanel"]')).toBeNull();
  });

  it("도움말은 제목 옆 `?` 토글이다 — 누르면 registry 의 문장이 펼쳐진다", async () => {
    const user = userEvent.setup();
    renderAt("/backup");
    const toggle = await screen.findByRole("button", { name: "도움말 보기" }, { timeout: 5000 });
    expect(toggle.closest(".k-page-head")).not.toBeNull();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "도움말 닫기" })).toHaveAttribute("aria-expanded", "true");
    const text = typeof REGISTRY.backup.help === "function" ? REGISTRY.backup.help("system_admin") : REGISTRY.backup.help;
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});
