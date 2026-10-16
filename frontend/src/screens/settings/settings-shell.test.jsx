import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

/* PA-RC-0017: /settings의 탭 그릇(SettingsShell.jsx). 각 탭 내용(설정 표·시스템 설정·
 * AI 관리·유지보수)의 자체 동작은 이미 각자의 테스트(system-ops*.test.jsx,
 * settings/ai-settings.test.jsx, settings-*.test.jsx)가 지킨다 — 여기서 다시 확인하지 않는다.
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
 *
 * qa-contract-change: 「AI」 탭이 「AI 연결」 화면(`/ai-connection`, D-539)이 되어 그릇의 탭은 셋이다. AI 탭을 누르던 시험은
 * 옛 주소(`?tab=ai`)가 새 화면으로 넘어가는지로, AI 탭으로 h1 · 토글 반례를 재던 시험은 파일 저장소 탭으로 옮겼다.
 *
 * qa-contract-change: 「시스템 정책 탭이 그려졌다」를 잡던 표식이 유지보수 판의 「현재 상태」 줄에서 「유지보수 모드」 설정 줄로 옮긴다 —
 * 유지보수 판 둘이 한 판의 설정 줄 둘이 되면서(D-501) 「현재 상태」 낱말이 없어졌다. 판정(그 탭이 그려졌는가 · 권한 없는 역할에게는
 * 안 그려졌는가)은 그대로이고, 기술 정보 토글이 그릇 머리에 서는지 재는 시험 둘을 더한다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
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
    // 파일 저장소(S20) — S8 의 `/api/storage/*` 를 부르는 첫 화면이고 권한이 os·ai 와
    // 같은 집합이라(STORAGE_CONFIGURE = SYSTEM_ADMIN_ONLY) 이 그릇의 제약을 만족한다.
    expect(screen.getByRole("tab", { name: "파일 저장소" })).toBeInTheDocument();
    // AI 는 탭이 아니라 「AI 연결」 화면이다(D-539).
    expect(screen.queryByRole("tab", { name: "AI" })).not.toBeInTheDocument();
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
    "%s가 주소를 손으로 ?tab=os/ai로 바꾸면 '권한이 없습니다.'를 명시한다(조용히 시스템 정책으로 안 떨어진다)",
    async (role) => {
      currentRole = role;
      renderShell("/settings?tab=os");
      // SystemOps.jsx만 그리는 "시스템 정보" 카드 제목이 없어야 한다 — 있다면 role 게이트가
      // 뚫려 이 역할이 OS 특권 동작(서비스 재시작 등)에 닿은 것이다.
      expect(await screen.findByText("권한이 없습니다.")).toBeInTheDocument();
      expect(screen.queryByText("시스템 정보")).not.toBeInTheDocument();
      // 설정 표(시스템 정책 탭의 내용)로 조용히 안 떨어졌다 — 거부 화면만 있다.
      expect(screen.queryByText("유지보수 모드")).not.toBeInTheDocument();
    },
  );

  it("역할 때문에 못 보는 탭을 요청해도 주소는 그대로 남는다(PA-RC-0024 딥링크 계약)", async () => {
    currentRole = "operator";
    renderShell("/settings?tab=os");
    await screen.findByText("권한이 없습니다.");
    expect(currentPath()).toContain("tab=os");
  });

  it("모르는 tab 값(오타·삭제된 탭)은 주소를 정정하고 시스템 정책으로 떨어진다 — 역할 문제와 다르게 처리한다", async () => {
    currentRole = "operator";
    renderShell("/settings?tab=does-not-exist");
    await screen.findByText("유지보수 모드");
    expect(screen.queryByText("권한이 없습니다.")).not.toBeInTheDocument();
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

  it("옛 AI 탭 주소는 「AI 연결」 화면으로 넘어간다", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=ai");
    await waitFor(() => expect(screen.getByTestId("location-probe")).toHaveTextContent("/ai-connection"));
  });

  // 없어진 '연동' 탭의 옛 주소(#/settings?tab=integration)가 즐겨찾기에 남아 있을 수 있다.
  // 모르는 탭 키와 같은 갈래로 떨어져 주소가 정정되고 시스템 정책이 그려져야 한다 — 여기서
  // 'Notion 관리'가 다시 그려지면 화면이 되살아난 것이다.
  it("옛 '연동' 탭 주소로 들어와도 그 화면은 다시 안 그려진다", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=integration");
    await screen.findByText("유지보수 모드");
    expect(screen.queryByRole("tab", { name: "연동" })).not.toBeInTheDocument();
    expect(screen.queryByText("데이터베이스")).not.toBeInTheDocument();
    await waitFor(() => expect(currentPath()).not.toContain("tab=integration"));
  });

  it("기본 탭('시스템 정책')은 설정 표와 유지보수 카드를 함께 보여준다 — 유지보수는 더는 별도 화면이 아니다", async () => {
    currentRole = "system_admin";
    renderShell();
    expect(await screen.findByText("유지보수 모드")).toBeInTheDocument();
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

/* 그릇의 머리 — 제목은 고정이고(D-452) 탭별 설명은 제목 옆 `?` 다(D-453). 예전에는 탭
   라벨이 h1 이라 「AI」가 화면 제목이었고, 설명은 탭 본문 첫 줄의 문단이었다. */
describe("그릇의 머리 — 제목 고정·탭별 도움말 (D-452 · D-453)", () => {
  it("파일 저장소 탭을 열어도 h1 은 「설정」이다 — 탭 라벨이 제목이 되지 않는다", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=storage");
    await screen.findByRole("tab", { name: "파일 저장소" });
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent("설정");
    expect(h1s[0]).not.toHaveTextContent("파일 저장소");
  });

  it("OS 탭의 설명은 제목 옆 `?` 도움말이다 — 본문 첫 줄 문단이 아니다", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=os");
    const toggle = await screen.findByRole("button", { name: "도움말 보기" });
    expect(toggle.closest(".k-page-head")).not.toBeNull();
    expect(screen.getByText(/시스템 설정 도우미가 정해진 동작으로만 처리합니다/)).toBeInTheDocument();
  });

  it("시스템 정책 탭에는 도움말 문장이 없으므로 `?` 도 없다 — 반례", async () => {
    currentRole = "system_admin";
    renderShell("/settings?tab=policy");
    await screen.findByRole("tab", { name: "시스템 정책" });
    expect(screen.queryByRole("button", { name: "도움말 보기" })).toBeNull();
  });
});

/* 설정 표의 보기 토글은 그릇 머리의 동작 자리에 선다(D-454 · D-501). 예전에는 이 단추 하나가 표 위 전폭 필터 바를 혼자
   차지했다 — 검색도 조건 칸도 없는 1,600px 줄의 오른쪽 끝에 단추 하나였다. */
describe("기술 정보 토글 — 그릇 머리의 동작 자리 (D-454 · D-501)", () => {
  function withSettings() {
    apiMock.mockImplementation((path) => (path === "/api/admin/settings"
      ? Promise.resolve({
        settings: {
          conversation_retention_days: {
            value: 90, type: "int", description: "대화 보존 기간", restart_required: false, is_default: true,
          },
        },
      })
      : Promise.resolve({})));
  }

  it("시스템 정책 탭의 「기술 정보(설정 키) 보기」는 페이지 머리에 서고, 표 위에 필터 바 줄이 없다", async () => {
    currentRole = "system_admin";
    withSettings();
    renderShell();
    const toggle = await screen.findByRole("button", { name: "기술 정보(설정 키) 보기" });
    expect(toggle.closest(".k-page-head"), "토글이 머리 밖(본문 첫 줄)에 섰다").not.toBeNull();
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(document.querySelector("[data-filter-bar]"), "한 칸짜리 전폭 필터 바가 다시 섰다").toBeNull();
    // 머리에 올라가도 토글은 그대로 동작한다 — 키 열이 들어온다.
    const user = userEvent.setup();
    await user.click(toggle);
    expect(await screen.findByRole("columnheader", { name: "키" })).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("반례: 다른 탭으로 옮기면 그 토글도 머리에서 내려간다 — 키 열이 없는 탭에 켤 단추를 남기지 않는다", async () => {
    currentRole = "system_admin";
    withSettings();
    const user = userEvent.setup();
    renderShell();
    await screen.findByRole("button", { name: "기술 정보(설정 키) 보기" });
    await user.click(screen.getByRole("tab", { name: "OS와 서비스 동작" }));
    await screen.findByText("서비스");
    expect(screen.queryByRole("button", { name: "기술 정보(설정 키) 보기" })).toBeNull();
  });
});
