/* 클로비 드로어가 **이동 대신 열리는가** (Q2).
 *
 * 예전에는 클로비를 누르는 세 자리가 전부 `navigate("/chat")` 이었다. 티켓을 보다가
 * 물어보려고 누르면 보던 화면이 사라졌다 — 물어볼 대상이 화면에 있는데 그 화면을
 * 떠나야 하는 구조였다.
 *
 * 여기서 고정하는 것은 **문맥 라벨의 계약**이다: 드로어가 "현재 문맥: X" 라고 말할 때
 * 그 X 가 사이드바 라벨과 같은 말이어야 한다. 다르면 같은 곳을 가리키는지 알 수 없다.
 * (드로어가 실제로 열리고 이동하지 않는 것은 브라우저로 확인했다 — URL 그대로, 폭 460px.) */

import { describe, expect, it } from "vitest";
import { routeContextLabel } from "./AssistantDrawer.jsx";
import { USER_NAV } from "./navConfig.js";

describe("현재 문맥 라벨", () => {
  it("주요 화면을 사이드바와 같은 말로 부른다", () => {
    expect(routeContextLabel("/")).toBe("홈");
    expect(routeContextLabel("/me")).toBe("홈");
    expect(routeContextLabel("/my-tickets")).toBe("내 티켓");
    expect(routeContextLabel("/team-tickets")).toBe("팀 티켓");
    expect(routeContextLabel("/sprint")).toBe("스프린트 회의");
    expect(routeContextLabel("/board")).toBe("자유게시판");
  });

  /* 이 파일 맨 위 주석이 스스로 세운 계약: "드로어가 '현재 문맥: X'라고 할 때 그 X는
   * 사이드바 라벨과 같은 말이어야 한다." 그런데 두 곳이 조용히 어긋나 있었다 —
   * USER_NAV는 "/me"를 "홈", "/team-docs/trash"를 "휴지통"이라 부르는데 드로어는 각각
   * "오늘의 업무", "문서 휴지통"이라는 다른 말을 썼다. 전용 라벨이 아직 없는 화면
   * (예: /chat, /notifications)은 대상에서 뺀다 — 그건 이 계약 위반이 아니라 "모르는
   * 경로는 일반 문구로 폴백한다"는 별도의, 의도된 동작이다(아래 마지막 테스트). */
  it("전용 문맥 라벨이 있는 화면은 사이드바와 실제로 같은 말을 쓴다", () => {
    const fallback = routeContextLabel("/이런-경로는-어디에도-없다");
    let checked = 0;
    for (const group of USER_NAV) {
      for (const item of group.items || []) {
        const label = routeContextLabel(item.to);
        if (label === fallback) continue;   // 전용 규칙이 아직 없는 화면 — 별도 결함이 아니다
        checked += 1;
        expect(label, `${item.to} — 드로어 문맥("${label}")과 사이드바 라벨("${item.label}")이 어긋난다`)
          .toBe(item.label);
      }
    }
    // 이 단언이 없으면 위 루프가 하나도 안 돌고도 통과할 수 있다.
    expect(checked, "실제로 대조한 화면이 없다 — 검사가 비어 있다").toBeGreaterThan(5);
  });

  it("상세 화면과 목록을 구분한다 — 순서가 중요하다", () => {
    // `/team-docs/trash` 가 `/team-docs` 규칙에 먼저 걸리면 '휴지통'이 '문서'가 된다.
    expect(routeContextLabel("/team-docs")).toBe("문서");
    expect(routeContextLabel("/team-docs/abc-123")).toBe("문서 상세");
    expect(routeContextLabel("/team-docs/trash")).toBe("휴지통");
    expect(routeContextLabel("/board")).toBe("자유게시판");
    expect(routeContextLabel("/board/abc-123")).toBe("게시글");
  });

  it("모르는 경로에서도 빈 문자열을 내지 않는다", () => {
    // 문맥 줄이 "현재 문맥: " 로 끝나면 고장 난 것처럼 보인다.
    expect(routeContextLabel("/무언가/새로운/화면")).toBeTruthy();
    expect(routeContextLabel("")).toBeTruthy();
    expect(routeContextLabel(undefined)).toBeTruthy();
  });
});
