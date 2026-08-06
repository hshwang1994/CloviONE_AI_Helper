/* 기능 플래그를 끄면 **메뉴도 사라진다** (X4).
 *
 * 예전에는 플래그가 서버만 껐다. 껐다고 믿은 메뉴가 사이드바에 그대로 남고, 눌리고,
 * 404 를 뱉었다 — 운영자는 "껐는데 왜 보이지", 사용자는 "눌렀는데 없다" 를 겪는다.
 * 화면에서 감추는 것은 편의일 뿐 통제가 아니다(라우터가 여전히 각자 막는다).
 */
import { describe, it, expect } from "vitest";
import { navWithFeatures, USER_NAV } from "./navConfig.js";

const paths = (nav) => nav.flatMap((g) => (g.items || []).map((i) => i.to));

describe("메뉴와 기능 플래그", () => {
  it("끈 기능의 메뉴가 사라진다", () => {
    const out = navWithFeatures(USER_NAV, { games_enabled: false, board_enabled: false });
    expect(paths(out)).not.toContain("/games");
    expect(paths(out)).not.toContain("/board");
    expect(paths(out)).toContain("/my-tickets");   // 플래그 없는 메뉴는 그대로
  });

  it("문서를 끄면 문서 휴지통도 같이 사라진다 — 한쪽만 남으면 막다른 길이다", () => {
    const out = navWithFeatures(USER_NAV, { team_docs_enabled: false });
    expect(paths(out)).not.toContain("/team-docs");
    expect(paths(out)).not.toContain("/team-docs/trash");
  });

  it("항목이 하나도 안 남은 묶음은 제목만 남지 않는다", () => {
    const out = navWithFeatures(USER_NAV, {
      team_docs_enabled: false, games_enabled: false, board_enabled: false,
      team_chat_enabled: false,
    });
    for (const g of out) {
      if (g.items) expect(g.items.length).toBeGreaterThan(0);
    }
  });

  it("값을 모를 때는 그대로 둔다 — 새로고침마다 메뉴가 깜빡이면 안 된다", () => {
    expect(paths(navWithFeatures(USER_NAV, null))).toEqual(paths(USER_NAV));
    expect(paths(navWithFeatures(USER_NAV, undefined))).toEqual(paths(USER_NAV));
  });

  it("켜져 있으면 그대로 보인다", () => {
    const out = navWithFeatures(USER_NAV, { games_enabled: true, board_enabled: true });
    expect(paths(out)).toContain("/games");
    expect(paths(out)).toContain("/board");
  });
});
