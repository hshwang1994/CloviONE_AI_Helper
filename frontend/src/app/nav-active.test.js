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

  // PA-RC-0031: '휴지통'이 자기 메뉴 항목을 안 갖는다(문서 화면 안 버튼으로 옮겼다) —
  // /tickets/:id 와 같은 부류(자기 항목 없는 경로)다.
  //
  // S14 · C2 로 '문서' 항목이 `/knowledge` 를 가리키게 되면서 접두 매칭이 이 경로를 못
  // 잡는다(`/team-docs/trash` 는 `/knowledge` 로 시작하지 않는다). 그래서 소속을
  // ROUTE_OWNER 에 적어 뒀고, 그 폴백이 실제로 문서 메뉴를 켜는지 여기서 본다 — 안 켜지면
  // 휴지통을 여는 순간 사이드바 선택 표시가 통째로 사라진다.
  it("자기 메뉴 항목이 없는 /team-docs/trash는 소속을 적어 둔 대로 문서 메뉴를 켠다", () => {
    expect(activeNavPath("/team-docs/trash", PATHS)).toBe("/knowledge");
  });

  it("티켓 상세는 예전에 아무 메뉴에도 안 걸렸다", () => {
    expect(bestNavMatch("/tickets/abc", PATHS), "이 값이 null 이라 표시가 사라졌다").toBeNull();
    expect(activeNavPath("/tickets/abc", PATHS)).toBe("/my-tickets");
  });

  it("어디서 왔는지가 있으면 그 메뉴가 켜진다", () => {
    expect(activeNavPath("/tickets/abc", PATHS, "/unassigned")).toBe("/unassigned");
    expect(activeNavPath("/tickets/abc", PATHS, "/sprint")).toBe("/sprint");
  });

  /* 🔴 **목록 둘이 나눠 쓰는 상세** (사용자 지적: "기능 개선 제안 게시물을 누르면
   * 자유게시판으로 넘어간다").
   *
   * 자유게시판과 기능 개선 제안은 목록만 갈라져 있고 상세는 `/board/:id` 한 라우트다.
   * 그래서 제안 글을 열면 접두 매칭이 **자유게시판**을 켜고, 빵부스러기는 「기능 개선
   * 제안」이라 해 같은 화면에서 두 신호가 어긋났다. 접두 매칭이 이기기 때문에 `from` 은
   * 한 번도 안 읽혔다 — ROUTE_OWNER 주석이 「목록에서 온 경우 from 이 이긴다」고 적어 둔
   * 것과 코드가 달랐다. */
  it("제안 목록에서 연 글은 제안 메뉴가 켜진 채로 있다", () => {
    expect(bestNavMatch("/board/abc", PATHS), "접두 매칭은 자유게시판을 준다").toBe("/board");
    expect(activeNavPath("/board/abc", PATHS, "/ideas")).toBe("/ideas");
  });

  it("자유게시판에서 연 글은 그대로 자유게시판이다", () => {
    expect(activeNavPath("/board/abc", PATHS, "/board")).toBe("/board");
    // 출처를 모르면(딥링크) 접두사 그대로 — 화면이 뜬 뒤 스스로 출처를 적는다
    // (BoardPost.jsx, board-post-kind-crumb.test.jsx).
    expect(activeNavPath("/board/abc", PATHS)).toBe("/board");
  });

  it("나눠 쓰지 않는 하위 화면에서는 출처가 접두 매칭을 못 이긴다", () => {
    /* `from` 을 무조건 이기게 고치면 이 줄이 빨개진다 — 홈에서 연 문서가 **홈**을 켠다.
       `/knowledge/<id>` 는 목록 둘이 나눠 쓰는 상세가 아니라 문서 하나의 하위 경로다.
       (`/team-docs/trash` 는 반례가 못 된다: 접두 매칭이 애초에 null 이라 그 자리에서
       `from` 이 이기는 것이 원래 계약이다 — 위 「어디서 왔는지가 있으면」 시험.) */
    expect(bestNavMatch("/knowledge/abc", PATHS), "접두 매칭이 있는 경로여야 반례가 된다").toBe("/knowledge");
    expect(activeNavPath("/knowledge/abc", PATHS, "/me")).toBe("/knowledge");
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
