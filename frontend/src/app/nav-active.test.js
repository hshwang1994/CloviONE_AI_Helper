import { describe, it, expect } from "vitest";

import { activeNavPath, bestNavMatch, ROUTE_OWNER, NAV, USER_NAV } from "./navConfig.js";

/* 상세 화면에서도 **선택된 메뉴가 남아 있다** (사용자 지적 #14).
 *
 * `bestNavMatch` 는 nav 항목 경로의 접두사만 본다. 그런데 상세는 목록과 **다른 접두사**를
 * 쓴다 — 목록은 `/my-tickets`·`/unassigned`·`/team-tickets` 인데 상세는 `/tickets/:id` 다.
 * 그래서 티켓을 여는 순간 어느 메뉴에도 안 걸려 **선택 표시가 통째로 사라졌다.**
 *
 * 두 단계로 고친다. 순서가 중요하다:
 *   1. 목록에서 들어왔으면 **그 목록**이 켜진다(`location.state.from`) — 사용자가 방금 누른 것
 *   2. 출처를 모르면(새로고침·딥링크·북마크) `ROUTE_OWNER` 의 기본 소속
 *
 * 2번만 두면 미할당에서 연 티켓인데 '내 티켓' 이 켜져 사용자가 자기 위치를 오해한다.
 * 1번만 두면 새로고침 한 번에 다시 사라진다.
 */

const PATHS = USER_NAV.flatMap((g) => g.items || []).map((i) => i.to);

describe("사이드바 선택 유지", () => {
  it("직접 맞는 항목이 있으면 그것이 이긴다", () => {
    expect(activeNavPath("/my-tickets", PATHS)).toBe("/my-tickets");
  });

  // PA-RC-0031: '휴지통'이 더 이상 자기 메뉴 항목을 안 갖는다(TeamDocs.jsx 화면 안 버튼으로
  // 옮겼다) — /tickets/:id 와 같은 부류(자기 항목 없는 상세 경로)가 됐다. 접두 매칭으로
  // 부모(문서, 지금은 '팀 공간' 그룹)가 대신 켜져야 한다 — 예전엔 자기 항목이 있어 이 경로
  // 자체가 정확히 켜졌었다(그때는 '접두 매칭으로 부모·자식이 동시에 켜지는' 버그 방지가
  // 목적이었다 — 이제 그 시나리오 자체가 없어져 이 테스트의 목적이 바뀌었다).
  it("자기 메뉴 항목이 없어진 /team-docs/trash는 접두 매칭으로 부모(문서)가 대신 켜진다", () => {
    expect(activeNavPath("/team-docs/trash", PATHS)).toBe("/team-docs");
  });

  it("티켓 상세는 예전에 아무 메뉴에도 안 걸렸다", () => {
    expect(bestNavMatch("/tickets/abc", PATHS), "이 값이 null 이라 표시가 사라졌다").toBeNull();
    expect(activeNavPath("/tickets/abc", PATHS)).toBe("/my-tickets");
  });

  it("어디서 왔는지가 있으면 그 메뉴가 켜진다", () => {
    expect(activeNavPath("/tickets/abc", PATHS, "/unassigned")).toBe("/unassigned");
    expect(activeNavPath("/tickets/abc", PATHS, "/sprint")).toBe("/sprint");
  });

  it("출처가 실제 메뉴가 아니면 무시한다", () => {
    /* 신뢰하지 않는 값이 그대로 켜지면 없는 메뉴가 활성으로 표시된다. */
    expect(activeNavPath("/tickets/abc", PATHS, "/nope")).toBe("/my-tickets");
  });

  it("검색은 소속이 있고, 자기 메뉴가 있는 화면은 자기 것이 이긴다", () => {
    expect(activeNavPath("/search", PATHS)).toBe("/me");
    // `/profile` 은 **자기 메뉴 항목이 있다** — ROUTE_OWNER 에 넣으면 홈이 켜져 버린다.
    expect(activeNavPath("/profile", PATHS)).toBe("/profile");
  });

  it("ROUTE_OWNER 의 목적지는 실제로 존재하는 메뉴다", () => {
    /* 오타 하나면 그 화면에서 영원히 표시가 안 켜지는데, 증상이 조용해서 안 보인다.
     * ROUTE_OWNER는 두 콘솔(관리자 NAV·사용자 USER_NAV)이 함께 쓰는 한 표라 — /departments·
     * /org-tree처럼 목적지가 관리자 전용 메뉴인 항목도 있다. PATHS(사용자 콘솔)만으로 검사하면
     * 그 항목들은 항상 "목적지가 메뉴에 없다"로 걸려 이 시험 자체가 못 미덥게 된다. */
    const ALL_PATHS = [...PATHS, ...NAV.flatMap((g) => g.items || []).map((i) => i.to)];
    for (const [from, to] of Object.entries(ROUTE_OWNER)) {
      expect(ALL_PATHS, `${from} → ${to} 의 목적지가 메뉴에 없다`).toContain(to);
    }
  });
});
