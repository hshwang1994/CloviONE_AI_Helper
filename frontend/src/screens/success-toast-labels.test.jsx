/* qa-contract-change: 조직 관리 IA 재설계(P6)로 부서 추가의 입구가 페이지 머리에서 부서 판의 「하위 부서 추가」로, 삭제가 판 머리 단추에서 「더 보기」 메뉴 항목으로 옮겨 갔다 — 같은 세 문장(추가 · 저장 · 삭제)을 새 입구에서 계속 못박는다.
 *
 * qa-contract-change: 부서 화면이 registry/DataScreen 을 떠나 조직 콘솔의 상세 판과 자체 모달(screens/org/)이 됐다 — /departments 세 케이스를 그 경로(OrgConsole 렌더 + 헤더 부서 추가·상세 판 수정·삭제)로 옮겨 같은 세 문장을 계속 못박는다. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 성공 토스트 기본 문구 — 실제 소비 화면 회귀 (PA-RC-0025).
 *
 * 감사가 지목한 실측: 같은 화면(/departments)에서 추가 → "추가했습니다.", 수정 →
 * "저장했습니다."(둘 다 이미 문장형)인데 삭제만 "삭제 완료"(명사형, 마침표 없음)였다.
 * successMessages.test.js는 사전 함수 자체(순수 함수)만 보므로, 여기서는 **실제 화면을
 * 렌더링해 진짜 클릭 → 진짜 토스트**로 그 세 액션이 이제 전부 문장형인지 확인한다.
 *
 * /prompts의 '보관'도 같은 기본 경로를 타던 액션이라 함께 확인한다(요구된 대표 소비처).
 *
 * /users의 대량 활성화는 DataScreen이 아니라 UsersBulk.jsx의 완전히 별개인 자체 처리
 * 경로다(result()형 opt-out과 같은 취지지만 실제로는 그 필드조차 아니다) — 이 사전
 * 변경이 그 문구를 건드리지 않았다는 것을 음성 대조군으로 직접 확인한다(acceptance
 * criteria: "Do not let a generic dictionary override actions that already define their
 * own message via result()").
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { Users } from "./Users.jsx";
import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { clickAction, hasAction } from "../test-helpers/actions.js";

function renderWith(children) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>{children}</MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT_ORG = { timeout: 8000 };

function renderOrgConsoleAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/departments/:id" element={<OrgConsole />} />
                {/* 부서를 지우면 그 부서가 있던 조직으로 옮겨 간다 — 그 주소도 같은 화면이다. */}
                <Route path="/organizations" element={<OrgConsole />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});

describe("부서 — 추가·수정·삭제가 전부 문장형이다 (조직 콘솔 경로)", () => {
  const AT2 = "2026-08-01T00:00:00";
  const TREE2 = [
    { id: "o1", kind: "organization", name: "조직A", depth: 0, path: "조직A",
      active: true, user_count: 0, child_count: 1, subtree_user_count: 0, created_at: AT2 },
    { id: "d1", kind: "department", name: "기존부서", depth: 1, path: "조직A › 기존부서",
      org_id: "o1", active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT2 },
  ];

  function mockDepartments() {
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      const u = String(path);
      if (u === "/api/admin/departments" && method === "POST") {
        return Promise.resolve({ id: "d-new", name: "새부서" });
      }
      if (u === "/api/admin/departments/d1" && method === "DELETE") {
        return Promise.resolve({ ok: true });
      }
      if (u === "/api/admin/departments/d1" && method === "PATCH") {
        return Promise.resolve({ department: { id: "d1", name: "고친이름" } });
      }
      if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE2 });
      if (u === "/api/admin/departments/d1") {
        return Promise.resolve({ department: {
          id: "d1", name: "기존부서", active: true, parent_id: null, org_id: "o1",
          org_name: "조직A", user_count: 0, child_department_count: 0, created_at: AT2,
          // 삭제 가능 여부는 이제 **서버가 판정해서 준다**(org-01) — 화면이 자기 계산으로
          // 「지금 삭제할 수 있습니다」라고 말한 뒤 409 를 받던 것을 그렇게 막았다.
          delete_precheck: { deletable: true, reason: null, dependents: [], detachables: [] },
        } });
      }
      if (u.startsWith("/api/admin/organizations")) {
        return Promise.resolve({ items: [{ id: "o1", name: "조직A", slug: "org-a",
          status: "active", department_count: 1, user_count: 0, created_at: AT2 }] });
      }
      if (u.startsWith("/api/admin/departments")) {
        return Promise.resolve({ items: [{ id: "d1", name: "기존부서", org_id: "o1",
          active: true, user_count: 0, created_at: AT2 }] });
      }
      if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve({ items: [] });
    });
  }

  it("추가 — 이미 문장형이었다('추가했습니다.')", async () => {
    mockDepartments();
    const user = userEvent.setup();
    renderOrgConsoleAt("/departments/d1");
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT_ORG);
    await user.click(await within(panel).findByRole("button", { name: "하위 부서 추가" }, WAIT_ORG));
    const dialog = await screen.findByRole("dialog", { name: "기존부서에 하위 부서 추가" });
    await user.type(within(dialog).getByLabelText(/부서 이름/), "새부서");
    await user.click(within(dialog).getByRole("button", { name: "추가" }));

    expect(await screen.findByText("추가했습니다.")).toBeInTheDocument();
  });

  it("수정 — 이미 문장형이었다('저장했습니다.')", async () => {
    mockDepartments();
    const user = userEvent.setup();
    renderOrgConsoleAt("/departments/d1");
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT_ORG);
    await user.click(await within(panel).findByRole("button", { name: "수정" }, WAIT_ORG));

    const editDialog = await screen.findByRole("dialog", { name: /수정/ });
    const nameInput = within(editDialog).getByLabelText(/부서 이름/);
    await user.clear(nameInput);
    await user.type(nameInput, "고친이름");
    await user.click(within(editDialog).getByRole("button", { name: "저장" }));

    expect(await screen.findByText("저장했습니다.")).toBeInTheDocument();
  });

  it("삭제 — 실측 버그 재현/수정 확인: 예전엔 '삭제 완료'(명사형, 마침표 없음), 이제 '삭제했습니다.'", async () => {
    mockDepartments();
    const user = userEvent.setup();
    renderOrgConsoleAt("/departments/d1");
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT_ORG);
    // 삭제는 파괴적 동작이라 「더 보기」 메뉴의 항목이다.
    await user.click(await within(panel).findByRole("button", { name: "기존부서 작업 더 보기" }, WAIT_ORG));
    const menu = await screen.findByRole("menu", {}, WAIT_ORG);
    await user.click(within(menu).getByRole("menuitem", { name: "삭제" }));

    const dialogs = await screen.findAllByRole("dialog", {}, WAIT_ORG);
    await user.click(within(dialogs[dialogs.length - 1]).getByRole("button", { name: "삭제" }));

    expect(await screen.findByText("삭제했습니다.")).toBeInTheDocument();
    // revert-to-verify 근거: 옛 패턴("삭제 완료")은 더 이상 어디에도 없어야 한다.
    expect(screen.queryByText("삭제 완료")).not.toBeInTheDocument();
  });
});

describe("/prompts — '보관'도 기본 경로를 타던 액션이다", () => {
  const PROMPT = {
    id: "p1", name: "주간 보고", purpose: "주간 보고서 생성", runner_id: null,
    version: 1, status: "published", created_by_name: "관리자",
    created_at: "2026-08-01T00:00:00", published_at: "2026-08-01T00:00:00",
    content: "지시문 내용",
  };

  it("보관 — '보관 완료'가 아니라 '보관했습니다.'", async () => {
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/prompts") && method === "GET") {
        return Promise.resolve({ items: [PROMPT], total: 1 });
      }
      if (path === "/api/admin/prompts/p1/transition" && method === "POST") {
        return Promise.resolve({ ...PROMPT, status: "archived" });
      }
      return Promise.resolve({ items: [] });
    });
    const user = userEvent.setup();
    renderWith(<DataScreen config={REGISTRY.prompts} />);
    const row = await screen.findByText("주간 보고");
    await user.click(row.closest("tr"));
    const drawer = await screen.findByRole("dialog");
    await clickAction(user, drawer, "보관");

    const confirmDialog = await screen.findByRole("dialog", { name: /보관할까요|확인/ });
    await user.click(within(confirmDialog).getByRole("button", { name: /확인|보관|계속/ }));

    expect(await screen.findByText("보관했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("보관 완료")).not.toBeInTheDocument();
  });

  // successMessages.test.js는 successMessageFor() 자체(순수 함수)만 본다 — DataScreen.jsx와
  // SubListDrawer.jsx가 **둘 다 실제로 그 함수를 불러 쓰는지**(배선 자체)는 각 파일의 실제
  // 호출부를 렌더링해서 봐야 한다. '버전 기록' 하위 드로어의 '이 버전으로 롤백'은
  // SubListDrawer.jsx의 act()가 직접 만드는 토스트라 DataScreen.jsx의 finishAction()을 거치지
  // 않는다 — 이 하나가 그 경로를 유일하게 증명한다.
  it("'버전 기록' 하위 드로어의 '이 버전으로 롤백'(SubListDrawer.jsx 자체 경로)도 문장형이다", async () => {
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/prompts?name=")) {
        return Promise.resolve({ items: [PROMPT], total: 1 });
      }
      if (path.startsWith("/api/admin/prompts") && method === "GET") {
        return Promise.resolve({ items: [PROMPT], total: 1 });
      }
      if (path === "/api/admin/prompts/rollback" && method === "POST") {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({ items: [] });
    });
    const user = userEvent.setup();
    renderWith(<DataScreen config={REGISTRY.prompts} />);
    const row = await screen.findByText("주간 보고");
    await user.click(row.closest("tr"));
    const drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("button", { name: "버전 기록" }));

    const subDrawer = await screen.findByRole("dialog", { name: "프롬프트 버전 기록" });
    await user.click(within(subDrawer).getByRole("button", { name: "이 버전으로 롤백" }));

    const confirmDialog = await screen.findByRole("dialog", { name: /롤백할까요|확인/ });
    await user.click(within(confirmDialog).getByRole("button", { name: /확인|롤백|계속/ }));

    expect(await screen.findByText("이 버전으로 롤백했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("이 버전으로 롤백 완료")).not.toBeInTheDocument();
  });
});

describe("/users 대량 활성화 — result()류 opt-out 경로는 이 사전 변경과 무관하다(음성 대조군)", () => {
  const mkUser = (n) => ({
    id: "u-" + n, email: `m${n}@goodmit.co.kr`, display_name: "사람" + n, role: "user",
    active: false, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
    department: null, department_id: null, title: null, title_id: null,
    last_login_at: null, created_at: "2026-07-01T00:00:00", archived_at: null,
  });
  const USERS = [mkUser(1), mkUser(2)];

  it("전원 적용 성공 시에도 기존 커스텀 문구('활성화: N명 적용(...)')가 그대로 뜬다", async () => {
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: USERS, total: 2, page_size: 20 });
      if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
      if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
      if (path === "/api/admin/settings") return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
      if (path === "/api/admin/users/bulk/apply" && method === "POST") {
        return Promise.resolve({
          action: "enable", action_label: "활성화", requested: 2,
          applied: [
            { id: "u-1", email: "m1@goodmit.co.kr", display_name: "사람1", changed: true },
            { id: "u-2", email: "m2@goodmit.co.kr", display_name: "사람2", changed: true },
          ],
          failed: [],
        });
      }
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderWith(<Users />);
    await screen.findByText("사람1");

    await user.click(await screen.findByRole("checkbox", { name: "전체 선택" }));
    await screen.findByText("2명 선택");
    await user.click(screen.getByRole("button", { name: "활성화" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /확인|활성화|계속/ }));

    // successMessages.js의 "활성화" → "활성화했습니다."는 여기 절대 안 쓰인다 — UsersBulk.jsx는
    // DataScreen.jsx의 finishAction()/announce()를 거치지 않고 자기 문자열을 직접 만든다.
    expect(await screen.findByText("활성화: 2명 적용(0명은 이미 그 상태)")).toBeInTheDocument();
    expect(screen.queryByText("활성화했습니다.")).not.toBeInTheDocument();
  });
});
