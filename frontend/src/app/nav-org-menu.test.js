import { describe, it, expect } from "vitest";

import { NAV, SCREEN_ROLES } from "./navConfig.js";

/* 조직관리·부서관리·조직도가 사이드바에 별도 항목 3개로 남아 있던 버그(사용자 신고: "사이드바에
 * 3개 항목으로 남아있어서 3개 페이지처럼 보임").
 *
 * AdminRoutes.jsx 는 이미 /organizations, /departments, /org-tree 셋 다 같은 OrgConsole 로
 * 라우팅한다(병합 자체는 끝났다) — 그런데 사이드바 메뉴가 여전히 3개면, 클릭할 때마다
 * '다른 메뉴'가 활성화되며 OrgConsole 이 다시 마운트되어 트리 선택 상태가 리셋된다.
 *
 * 이 테스트는 사이드바(NAV)에 조직 관련 항목이 **하나만** 있어야 함을 못박는다.
 * 라우팅은 건드리지 않으므로 /departments, /org-tree 로의 직접 진입(북마크)은 여전히 유효하다
 * — 그건 org-console.test.jsx(AdminRoutes 딥링크 표)가 이미 지킨다.
 */
describe("사이드바 조직 메뉴 통합", () => {
  const ORG_PATHS = ["/organizations", "/departments", "/org-tree"];
  const userGroup = NAV.find((g) => g.group === "사용자");
  const orgItems = (userGroup.items || []).filter((i) => ORG_PATHS.includes(i.to));

  it("조직 관련 메뉴 항목은 하나뿐이다(예전에는 3개라 클릭할 때마다 메뉴가 바뀌었다)", () => {
    expect(orgItems.length).toBe(1);
  });

  it("대표 항목은 /organizations 를 가리키고 라벨·권한이 있다", () => {
    const item = orgItems[0];
    expect(item.to).toBe("/organizations");
    expect(item.label).toBeTruthy();
    expect(item.roles).toEqual(SCREEN_ROLES.organizations);
  });

  it("남은 URL(/departments, /org-tree)의 역할 게이트는 그대로 남아 있다(직접 진입용)", () => {
    // 메뉴는 하나로 줄이되, AdminRoutes.jsx 가 참조하는 SCREEN_ROLES 표는 셋 다 유지한다.
    expect(SCREEN_ROLES.departments).toEqual(["admin", "system_admin"]);
    expect(SCREEN_ROLES["org-tree"]).toEqual(["admin", "system_admin"]);
  });
});
