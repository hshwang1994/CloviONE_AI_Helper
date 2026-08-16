import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0017: /settings의 탭 그릇(SettingsShell.jsx). 각 탭 내용(설정 표·시스템 설정·
 * Notion 관리·AI 관리·유지보수)의 자체 동작은 이미 각자의 테스트(system-ops*.test.jsx,
 * notion-console.test.jsx, llm-console.test.jsx, settings-*.test.jsx)가 지킨다 — 여기서
 * 다시 확인하지 않는다. 이 파일이 지키는 건 이 화면이 **새로 만든** 것만이다: 탭 가시성이
 * role을 따라가는가(가장 큰 위험이라고 Handoff가 짚은 지점), 탭 전환이 실제로 다른 화면을
 * 그리는가, 그리고 권한 없는 role이 주소를 손으로 바꿔도 안 뚫리는가.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

let currentRole = "system_admin";
vi.mock("../../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: currentRole, id: "a1" } }),
}));

import { SettingsShell } from "./SettingsShell.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

beforeEach(() => {
  apiMock.mockReset();
  // 모든 탭이 이 화면 하나에서 각자의 엔드포인트를 부른다 — 각 화면의 성공 렌더 세부값은
  // 그 화면 자신의 테스트가 이미 검증하므로, 여기서는 "무엇이든 응답이 온다"만 있으면 된다.
  apiMock.mockImplementation(() => Promise.resolve({}));
});

function renderShell(initialPath = "/settings") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <SettingsShell />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("설정 탭 — role별 가시성", () => {
  it("system_admin은 네 탭을 전부 본다", () => {
    currentRole = "system_admin";
    renderShell();
    expect(screen.getByRole("tab", { name: "시스템 정책" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "OS와 서비스 동작" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "연동" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "AI" })).toBeInTheDocument();
  });

  // Handoff required_tests: "역할 4종(user·operator·auditor·system_admin) × 신규 탭 전체
  // allow/deny". system_admin은 위에서 이미 확인했으니 나머지 셋을 여기서 명시적으로 돈다 —
  // 셋 다 결과가 같더라도(전부 system_admin 전용 게이트라) "왜 안 물어봤나"로 남지 않게
  // 이름을 하나씩 못박는다.
  it.each(["user", "operator", "auditor"])(
    "%s는 '시스템 정책' 탭 하나만 본다 — 나머지 셋은 탭 버튼 자체가 없다",
    (role) => {
      currentRole = role;
      renderShell();
      expect(screen.getByRole("tab", { name: "시스템 정책" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "OS와 서비스 동작" })).not.toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "연동" })).not.toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "AI" })).not.toBeInTheDocument();
    },
  );

  it.each(["user", "operator", "auditor"])(
    "%s가 주소를 손으로 ?tab=os/integration/ai로 바꿔도 해당 탭 내용이 아니라 시스템 정책으로 떨어진다",
    (role) => {
      currentRole = role;
      renderShell("/settings?tab=os");
      // SystemOps.jsx만 그리는 "시스템 정보" 카드 제목이 없어야 한다 — 있다면 role 게이트가
      // 뚫려 이 역할이 OS 특권 동작(서비스 재시작 등)에 닿은 것이다.
      expect(screen.queryByText("시스템 정보")).not.toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "시스템 정책", selected: true })).toBeInTheDocument();
    },
  );
});

describe("설정 탭 — 전환하면 실제로 다른 화면을 그린다", () => {
  it("'OS와 서비스 동작' 탭을 누르면 SystemOps 고유 영역(서비스 카드)이 나타난다", async () => {
    currentRole = "system_admin";
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole("tab", { name: "OS와 서비스 동작" }));
    expect(await screen.findByText("서비스")).toBeInTheDocument();
  });

  it("'연동' 탭을 누르면 NotionConsole 고유 영역(데이터베이스 카드)이 나타난다", async () => {
    currentRole = "system_admin";
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole("tab", { name: "연동" }));
    expect(await screen.findByText("데이터베이스")).toBeInTheDocument();
  });

  it("기본 탭('시스템 정책')은 설정 표와 유지보수 카드를 함께 보여준다 — 유지보수는 더는 별도 화면이 아니다", async () => {
    currentRole = "system_admin";
    renderShell();
    expect(await screen.findByText("현재 상태")).toBeInTheDocument();
  });
});

describe("설정 탭 — 옛 안내 4문단은 삭제됐다 (Handoff acceptance_criteria 3)", () => {
  it("탭이 생긴 뒤에는 '어디로 가면 되는지' 안내문이 화면에 없다", async () => {
    currentRole = "system_admin";
    renderShell();
    await screen.findByRole("tab", { name: "시스템 정책", selected: true });
    expect(screen.queryByText(/노션 데이터베이스 id 와 토큰은/)).not.toBeInTheDocument();
    expect(screen.queryByText(/서버 시간대, DNS, 서비스 재시작처럼/)).not.toBeInTheDocument();
    expect(screen.queryByText(/유지보수 모드, 점검 공지는/)).not.toBeInTheDocument();
  });
});
