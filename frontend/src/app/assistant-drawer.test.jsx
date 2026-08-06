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

describe("현재 문맥 라벨", () => {
  it("주요 화면을 사이드바와 같은 말로 부른다", () => {
    expect(routeContextLabel("/")).toBe("오늘의 업무");
    expect(routeContextLabel("/me")).toBe("오늘의 업무");
    expect(routeContextLabel("/my-tickets")).toBe("내 티켓");
    expect(routeContextLabel("/team-tickets")).toBe("팀 티켓");
    expect(routeContextLabel("/sprint")).toBe("스프린트 회의");
    expect(routeContextLabel("/board")).toBe("자유게시판");
  });

  it("상세 화면과 목록을 구분한다 — 순서가 중요하다", () => {
    // `/team-docs/trash` 가 `/team-docs` 규칙에 먼저 걸리면 '문서 휴지통'이 '문서'가 된다.
    expect(routeContextLabel("/team-docs")).toBe("문서");
    expect(routeContextLabel("/team-docs/abc-123")).toBe("문서 상세");
    expect(routeContextLabel("/team-docs/trash")).toBe("문서 휴지통");
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
