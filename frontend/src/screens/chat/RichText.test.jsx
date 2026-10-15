import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { RichText } from "./RichText.jsx";

/* 머리글 줄의 URL도 목록·표·문단과 같이 링크가 된다(step 10 #2).
 *
 * parseBlocks가 만드는 네 블록(head·list·kv·para) 중 목록·표·문단 셋은 이미
 * linkifyText를 거치는데 머리글만 `{b.text}`를 그대로 그렸다 - "■ https://…" 처럼
 * 답변이 URL로 시작하는 줄(가장 흔한 트리거는 AI-33이지만, 그걸 고쳐도 이 경로 자체는
 * 남는다)에서 그 줄의 URL이 링크도 복사 버튼도 아닌 죽은 글자로 남았다.
 */

describe("RichText — 머리글 줄의 URL", () => {
  it("[제목] 형태 머리글 안의 URL이 복사 버튼이 된다", () => {
    const { container } = render(<RichText text="[참고] https://www.notion.so/abc 확인" />);
    const link = container.querySelector("a, button");
    expect(link).not.toBeNull();
    // 어떤 주소도 앵커가 아니다 - 죽은 글자로 남지 않게 복사 버튼으로만 낸다.
    expect(link.textContent).toContain("https://www.notion.so/abc");
    expect(container.querySelector("a")).toBeNull();
  });

  it("■ 불릿 머리글 안의 URL도 링크가 된다", () => {
    const { container } = render(<RichText text="■ https://www.notion.so/xyz" />);
    const link = container.querySelector("a, button");
    expect(link).not.toBeNull();
    expect(link.textContent).toContain("https://www.notion.so/xyz");
  });

  it("URL이 없는 평범한 머리글은 그대로 글자로 남는다(회귀 없음)", () => {
    const { getByText } = render(<RichText text="[요약] 이번 주 진행 상황" />);
    expect(getByText("요약", { exact: false })).toBeInTheDocument();
  });
});

// AI-34: 펜스 코드블록이 <pre><code>로 렌더되고, 원문이 linkifyText/블록 재분류를
// 거치지 않고 그대로 보존된다.
describe("RichText — 펜스 코드블록", () => {
  it("```로 감싼 내용이 <pre><code>에 원문 그대로 렌더된다(불릿/URL로 오분류되지 않는다)", () => {
    const { container } = render(
      <RichText text={"```\ndef f(x):\n- https://example.com 아님\n```"} />,
    );
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    const code = pre.querySelector("code");
    expect(code).not.toBeNull();
    expect(code.textContent).toBe("def f(x):\n- https://example.com 아님");
    // 코드 안의 URL은 링크화되지 않는다 - 코드는 코드 그대로다.
    expect(pre.querySelector("a")).toBeNull();
  });

  it("펜스 앞뒤의 일반 텍스트는 그대로 문단으로 렌더된다", () => {
    const { getByText, container } = render(
      <RichText text={"앞 문단\n```\ncode\n```\n뒤 문단"} />,
    );
    expect(getByText("앞 문단")).toBeInTheDocument();
    expect(getByText("뒤 문단")).toBeInTheDocument();
    expect(container.querySelector("pre code").textContent).toBe("code");
  });
});

/* A8(D-569) — 답 안의 「**굵게**」는 굵게, 「[제목](경로)」는 **그 답의 출처와 같은 경로일 때만** 앱 안 링크다.
 * 모델이 지어낸 경로는 앱 안 경로 모양이어도 링크가 되지 않고 원래 글자 그대로 남는다. 바깥 주소는 어느 경우에도 앵커가 아니다. */
describe("RichText — 굵게 · 출처 링크 · 마크다운 머리글", () => {
  it("「**글**」은 <strong> 으로 그린다", () => {
    const { container } = render(<RichText text="**중요한** 내용입니다." />);
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong.textContent).toBe("중요한");
    expect(container.textContent).toBe("중요한 내용입니다.");
  });

  it("출처에 있는 경로의 링크는 같은 창의 해시 링크다", () => {
    const { getByRole } = render(
      <RichText text="[연차 규정](/knowledge/d-1) 을 보세요." routeLinks={new Set(["/knowledge/d-1"])} />,
    );
    expect(getByRole("link", { name: "연차 규정" })).toHaveAttribute("href", "#/knowledge/d-1");
  });

  it("출처에 없는 경로는 앱 안 경로 모양이어도 링크가 아니라 원래 글자 그대로다", () => {
    const { container } = render(
      <RichText text="[지어낸 문서](/knowledge/d-9) 를 보세요." routeLinks={new Set(["/knowledge/d-1"])} />,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("[지어낸 문서](/knowledge/d-9)");
  });

  it("출처 경로가 없으면(routeLinks 없음) 어떤 마크다운 링크도 링크가 아니다", () => {
    const { container } = render(<RichText text="[연차 규정](/knowledge/d-1)" />);
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe("[연차 규정](/knowledge/d-1)");
  });

  it("문단 자리(?block=)만 다르면 같은 문서다 — 링크는 출처의 경로로 간다", () => {
    const { getByRole } = render(
      <RichText text="[연차 규정](/knowledge/d-1?block=b9)" routeLinks={new Set(["/knowledge/d-1?block=b2"])} />,
    );
    expect(getByRole("link", { name: "연차 규정" })).toHaveAttribute("href", "#/knowledge/d-1?block=b2");
  });

  it("「[글](https://…)」의 바깥 주소는 앵커가 되지 않는다(복사 단추로만 남는다)", () => {
    const { container } = render(
      <RichText text="[바깥](https://evil.example/a) 참고" routeLinks={new Set(["/knowledge/d-1", "https://evil.example/a"])} />,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("button").textContent).toBe("https://evil.example/a");
    expect(container.textContent).toContain("[바깥](");
  });

  it("굵게 안의 출처 링크도 링크다", () => {
    const { container } = render(
      <RichText text="**[연차 규정](/knowledge/d-1)**" routeLinks={new Set(["/knowledge/d-1"])} />,
    );
    const anchor = container.querySelector("strong a");
    expect(anchor).not.toBeNull();
    expect(anchor).toHaveAttribute("href", "#/knowledge/d-1");
  });

  it("목록 항목 · 키-값 값 · 머리글 안에서도 같은 규칙이다", () => {
    const routes = new Set(["/knowledge/d-1", "/tickets/t-1"]);
    const { getByRole, container } = render(
      <RichText
        text={"[요약] **두 건**\n- [연차 규정](/knowledge/d-1) 홍길동, 2026-10-01\n- [가짜](/tickets/zz)\n\n문서: [연차 규정](/knowledge/d-1)\n티켓: [결재 화면](/tickets/t-1)"}
        routeLinks={routes}
      />,
    );
    expect(container.querySelector("h4 strong").textContent).toBe("두 건");
    expect(container.querySelectorAll('a[href="#/knowledge/d-1"]')).toHaveLength(2);
    expect(getByRole("link", { name: "결재 화면" })).toHaveAttribute("href", "#/tickets/t-1");
    expect(container.textContent).toContain("[가짜](/tickets/zz)");
  });

  it("「# 제목」 · 「## 제목」은 머리글로 그린다(글자 그대로 남지 않는다)", () => {
    const { getByRole, container } = render(<RichText text={"# 요약\n본문입니다.\n## 세부 사항 ##"} />);
    expect(getByRole("heading", { name: "요약" })).toBeInTheDocument();
    expect(getByRole("heading", { name: "세부 사항" })).toBeInTheDocument();
    expect(container.textContent).not.toContain("#");
  });

  it("코드 블록 안의 굵게 · 링크는 해석하지 않는다", () => {
    const { container } = render(
      <RichText text={"```\n**not bold** [x](/knowledge/d-1)\n```"} routeLinks={new Set(["/knowledge/d-1"])} />,
    );
    const code = container.querySelector("pre code");
    expect(code.textContent).toBe("**not bold** [x](/knowledge/d-1)");
    expect(container.querySelector("strong")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
  });
});

/* AI 채팅 개선 회차 — 모델이 쓰는 마크다운 중 글자 그대로 남던 것들. 사용자 캡처에서
 * 「[[포스코DX] 부가서비스·NAS 빌링 화면 가이드](/knowledge/…)」가 글자로 보였다(라벨 안 대괄호를 못 읽었고, 줄 맨 앞이면
 * 머리글로 잘못 읽었다). 링크 규칙(그 답의 출처 경로나 화면 길잡이 경로만)은 그대로다. */
describe("RichText — 라벨 안 대괄호 · 인라인 코드 · 중첩 목록 · 인용 · 구분선 · 표", () => {
  const ROUTES = new Set(["/knowledge/d-9"]);

  it("라벨에 대괄호가 든 링크도 링크 하나다 — 줄 맨 앞이어도 머리글이 아니다", () => {
    const { getByRole, queryByRole, container } = render(
      <RichText text={"[[포스코DX] 부가서비스·NAS 빌링 화면 가이드](/knowledge/d-9) 를 먼저 보세요."} routeLinks={ROUTES} />,
    );
    expect(getByRole("link", { name: "[포스코DX] 부가서비스·NAS 빌링 화면 가이드" })).toHaveAttribute("href", "#/knowledge/d-9");
    expect(queryByRole("heading")).toBeNull();
    expect(container.textContent).not.toContain("](");
  });

  it("출처에 없는 경로면 대괄호 라벨이어도 원래 글자 그대로다", () => {
    const { queryByRole, container } = render(<RichText text={"[[가짜] 문서](/knowledge/zz) 입니다."} routeLinks={ROUTES} />);
    expect(queryByRole("link")).toBeNull();
    expect(container.textContent).toContain("[[가짜] 문서](/knowledge/zz)");
  });

  it("화면 길잡이 경로는 출처가 없어도 링크다 — 질의가 붙으면 아니다", () => {
    const { getByRole, getAllByRole } = render(<RichText text={"[사내 문서](/knowledge)에서 찾아보세요. [내 문서](/knowledge?author=u1)도 있습니다."} />);
    expect(getByRole("link", { name: "사내 문서" })).toHaveAttribute("href", "#/knowledge");
    expect(getAllByRole("link")).toHaveLength(1);
  });

  it("인라인 코드는 code 로 그리고 그 안은 해석하지 않는다", () => {
    const { container } = render(<RichText text={"명령은 `**git status**` 입니다."} />);
    const code = container.querySelector("code");
    expect(code).not.toBeNull();
    expect(code.closest("pre")).toBeNull();
    expect(code.textContent).toBe("**git status**");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("* · • 목록과 한 단 중첩 목록을 목록으로 그린다", () => {
    const { container } = render(<RichText text={"* 첫째\n  - 첫째의 하위\n• 둘째"} />);
    const top = container.querySelector("ul");
    expect(top).not.toBeNull();
    expect(top.querySelectorAll(":scope > li")).toHaveLength(2);
    const nested = top.querySelector("li ul");
    expect(nested).not.toBeNull();
    expect(nested.textContent).toContain("첫째의 하위");
    expect(container.textContent).not.toContain("* 첫째");
    expect(container.textContent).not.toContain("- 첫째의 하위");
  });

  it("「>」 인용 · 「---」 구분선 · 「####」 머리글을 글자 그대로 남기지 않는다", () => {
    const { container, getByRole } = render(<RichText text={"> 규정 원문을 따릅니다.\n---\n#### 세부 기준"} />);
    expect(container.querySelector("blockquote")).toHaveTextContent("규정 원문을 따릅니다.");
    expect(container.querySelector("hr")).not.toBeNull();
    expect(getByRole("heading", { name: "세부 기준" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/^>|---|####/m);
  });

  it("표는 표로 그린다 — 머리 줄과 칸, 칸 안의 출처 링크", () => {
    const { getByRole, getAllByRole } = render(
      <RichText text={"| 문서 | 수정일 |\n|---|---|\n| [빌링 가이드](/knowledge/d-9) | 2026-09-04 |"} routeLinks={ROUTES} />,
    );
    expect(getByRole("table")).toBeInTheDocument();
    expect(getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["문서", "수정일"]);
    expect(getByRole("link", { name: "빌링 가이드" })).toHaveAttribute("href", "#/knowledge/d-9");
    expect(getAllByRole("cell").map((c) => c.textContent)).toEqual(["빌링 가이드", "2026-09-04"]);
  });

  it("망가진 입력(닫히지 않은 괄호 · 펜스)은 글로 떨어지고 깨지지 않는다", () => {
    const { container } = render(<RichText text={"[닫히지 않은 링크(/knowledge/d-9\n```\n끝나지 않은 코드"} routeLinks={ROUTES} />);
    expect(container.textContent).toContain("[닫히지 않은 링크(/knowledge/d-9");
    expect(container.textContent).toContain("끝나지 않은 코드");
    expect(container.querySelector("a")).toBeNull();
  });
});
