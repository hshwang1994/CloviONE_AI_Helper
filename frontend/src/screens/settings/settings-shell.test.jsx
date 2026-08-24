import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

/* PA-RC-0017: /settings의 탭 그릇(SettingsShell.jsx). 각 탭 내용(설정 표·시스템 설정·
 * AI 관리·유지보수)의 자체 동작은 이미 각자의 테스트(system-ops*.test.jsx,
 * llm-console.test.jsx, settings-*.test.jsx)가 지킨다 — 여기서 다시 확인하지 않는다.
 * 이 파일이 지키는 건 이 화면이 **새로 만든** 것만이다: 탭 가시성이 role을 따라가는가(가장
 * 큰 위험이라고 Handoff가 짚은 지점), 탭 전환이 실제로 다른 화면을 그리는가, 그리고 권한
 * 없는 role이 주소를 손으로 바꿔도 안 뚫리는가.
 *
 * qa-contract-replaced-by: frontend/src/screens/notion-console.test.jsx
 *
 * 그 파일은 Notion 관리 화면(NotionConsole.jsx)이 토큰과 데이터베이스 id 를 어떻게 보여
 * 주고 연결을 어떻게 시험하는지를 지켰다. 화면이 없어졌으므로 그 성질을 옮겨 담을 곳도
 * 없다 — **그 덮개는 되살아나지 않고, 그것이 맞다.** 티켓·문서·프로젝트가 이 서버의
 * 데이터베이스에서 나오게 된 뒤로 노션 토큰은 제품이 읽는 값이 아니고, 그 값을 고치는
 * 화면이 남아 있으면 없어진 쓰기 경로를 사람이 다시 열 수 있다고 말하는 셈이 된다.
 * 여기 남는 것은 그 화면이 걸려 있던 '연동' 탭이 **정말로 없다**는 단언 하나다.
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

// MemoryRouter(시험 전용)는 window.location.hash를 실제로 안 건드린다(users-url-state.test.jsx
// 등 기존 관용과 같은 이유) — 실제 매치된 주소를 보려면 같은 라우터 컨텍스트 안에서
// useLocation()을 읽는 프로브가 필요하다(admin-detail-routes.test.jsx와 같은 패턴).
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname + location.search}</div>;
}

function renderShell(initialPath = "/settings") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <LocationProbe />
              <SettingsShell />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
const currentPath = () => screen.getByTestId("location-probe").textContent;

describe("설정 탭 — role별 가시성", () => {
  it("system_admin은 세 탭을 전부 본다", () => {
    currentRole = "system_admin";
    renderShell();
    expect(screen.getByRole("tab", { name: "시스템 정책" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "OS와 서비스 동작" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "AI" })).toBeInTheDocument();
    // '연동' 탭은 안에 Notion 관리 화면 하나만 들고 있었고, 그 화면이 없어지면서 함께
    // 없어졌다. 빈 탭으로 남기면 사용자는 자기가 못 보는 내용이 있다고 읽는다.
    expect(screen.queryByRole("tab", { name: "연동" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab").length).toBe(3);
  });

  // Handoff required_tests: "역할 4종(user·operator·auditor·system_admin) × 신규 탭 전체
  // allow/deny". system_admin은 위에서 이미 확인했으니 나머지 셋을 여기서 명시적으로 돈다 —
  // 셋 다 결과가 같더라도(전부 system_admin 전용 게이트라) "왜 안 물어봤나"로 남지 않게
  // 이름을 하나씩 못박는다.
  //
  // PA-RC-0030 acceptance(4): 볼 수 있는 탭이 하나뿐인 역할에게는 전환할 게 없는 탭 스트립
  // 자체가 장식이다 — 예전엔(PA-RC-0017) 탭이 하나여도 버튼으로 그렸다. 이제 탭 목록
  // (role="tablist") 자체가 없다 — 시스템 정책 '내용'(설정 표)은 그대로 보인다.
  it.each(["user", "operator", "auditor"])(
    "%s는 탭 전환 UI 자체가 없다 — 시스템 정책 내용만 바로 보인다(탭이 하나뿐이라)",
    (role) => {
      currentRole = role;
      renderShell();
      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
      expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    },
  );

  // PA-RC-0030: 예전엔 주소만 ?tab=os로 남긴 채 조용히 시스템 정책으로 떨어졌다(거부 안내
  // 없음, 주소·화면 불일치) — 이제 라우트 게이트(RequireRole)와 같은 EmptyState로 명시하고
  // 주소는 요청한 그대로 둔다(PA-RC-0024 딥링크 계약).
  it.each(["user", "operator", "auditor"])(
    "%s가 주소를 손으로 ?tab=os/ai로 바꾸면 '권한이 없습니다'를 명시한다(조용히 시스템 정책으로 안 떨어진다)",
    async (role) => {
      currentRole = role;
      renderShell("/settings?tab=os");
      // SystemOps.jsx만 그리는 "시스템 정보" 카드 제목이 없어야 한다 — 있다면 role 게이트가
      // 뚫려 이 역할이 OS 특권 동작(서비스 재시작 등)에 닿은 것이다.
      expect(await screen.findByText("권한이 없습니다")).toBeInTheDocument();
      expect(screen.queryByText("시스템 정보")).not.toBeInTheDocument();
      // 설정 표(시스템 정책 탭의 내용)로 조용히 안 떨어졌다 — 거부 화면만 있다.
      expect(screen.queryByText("현재 상태")).not.toBeInTheDocument();
    },
  );

  it("역할 때문에 못 보는 탭을 요청해도 주소는 그대로 남는다(PA-RC-0024 딥링크 계약)", async () => {
    currentRole = "operator";
    renderShell("/settings?tab=os");
    await screen.findByText("권한이 없습니다");
    expect(currentPath()).toContain("tab=os");
  });

  it("모르는 tab 값(오타·삭제된 탭)은 주소를 정정하고 시스템 정책으로 떨어진다 — 역할 문제와 다르게 처리한다", async () => {
    currentRole = "operator";
    renderShell("/settings?tab=does-not-exist");
    await screen.findByText("현재 상태");
    expect(screen.queryByText("권한이 없습니다")).not.toBeInTheDocument();
    await waitFor(() => expect(currentPath()).not.toContain("tab=does-not-exist"));
  });
});

describe("설정 탭 — 전환하면 실제로 다른 화면을 그린다", () => {
  it("'OS와 서비스 동작' 탭을 누르면 SystemOps 고유 영역(서비스 카드)이 나타난다", async () => {
    currentRole = "system_admin";
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole("tab", { name: "OS와 서비스 동작" }));
    expect(await screen.findByText("서비스")).toBeInTheDocument();
  });

  it("'AI' 탭을 누르면 LlmConsole 고유 영역(지금 적용 중인 값)이 나타난다", async () => {
    currentRole = "system_admin";
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole("tab", { name: "AI" }));
    expect(await screen.findByText("지금 적용 중인 값")).toBeInTheDocument();
  });

  // 없어진 '연동' 탭의 옛 주소(#/settings?tab=integration)가 즐겨찾기에 남아 있을 수 있다.
  // 모르는 탭 키와 같은 갈래로 떨어져 주소가 정정되고 시스템 정책이 그려져야 한다 — 여기서
  // 'Notion 관리'가 다시 그려지면 화면이 되살아난 것이다.
  it("옛 '연동' 탭 주소로 들어와도 그 화면은 다시 안 그려진다", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=integration");
    await screen.findByText("현재 상태");
    expect(screen.queryByRole("tab", { name: "연동" })).not.toBeInTheDocument();
    expect(screen.queryByText("데이터베이스")).not.toBeInTheDocument();
    await waitFor(() => expect(currentPath()).not.toContain("tab=integration"));
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
