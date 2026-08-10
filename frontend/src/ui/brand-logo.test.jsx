import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import BrandLogo from "./BrandLogo.jsx";
import { createClovirTheme } from "./theme.js";

/* 상단바 워드마크 부제("SMART WORKSPACE ASSISTANT")가 SVG <text>로 남아 있지 않는지 본다.
 *
 * 왜 필요한가 — 이 컴포넌트는 viewBox 528x156을 CSS 폭 150~224px로 축소해 그리는 인라인
 * SVG다. SVG <text>의 fontSize 속성은 그 축소 배율을 그대로 먹어서, 마크업에 fontSize="20"
 * 이라 적어도 실제 렌더 크기는 20 * (170/528) ≈ 6.4px로 떨어진다 — charts/base.jsx가 같은
 * 이유로 이미 금지해 둔 패턴이다("<svg> 안에는 <text>를 쓰지 않는다. SVG 텍스트는 px 단위라
 * 루트 폰트사이즈 레버를 안 따르고, 4K에서 12px 미만으로 남아 QA의 tiny_text 검사에 걸린다").
 * QA의 tiny_text 검사(scripts/ui_qa/assertions.py)는 렌더된 크기가 아니라 마크업의 명목값을
 * 읽어 이 결함을 통과로 오판했다 — 그 검사를 고치는 것은 이 결함의 해법이 아니다. 실제 렌더를
 * 고쳐야 그 사각지대가 더는 문제가 안 된다.
 *
 * jsdom은 레이아웃을 계산하지 않으므로(density.test.jsx의 같은 이유) "몇 px로 그려졌나"는
 * 물을 수 없다. 대신 (1) 부제 글자가 <svg><text> 밖의 일반 HTML 요소인지, (2) emotion이
 * 실제로 낸 CSS에 6px대가 아니라 사이드바(AppShell.jsx)와 같은 읽을 수 있는 크기(0.75rem =
 * 12px)가 선언돼 있는지를 본다.
 */

function rulesFor(el) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  const found = [];
  const scan = (text, cond) => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf("{", i);
      if (open === -1) break;
      const head = text.slice(i, open).trim();
      let depth = 1;
      let j = open + 1;
      while (j < text.length && depth > 0) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
        j += 1;
      }
      if (head.startsWith("@")) scan(text.slice(open + 1, j - 1), cond ? `${cond} && ${head}` : head);
      else if (head.split(",").some((s) => classes.includes(s.trim().replace(/^\./, "")))) {
        found.push({ cond, body: text.slice(open + 1, j - 1) });
      }
      i = j;
    }
  };
  scan(css, "");
  return found;
}

// 같은 규칙 블록 안에 같은 속성이 여러 번 나올 수 있다(MUI 기본값 → sx 순서) — 뒤에 온
// 선언이 이긴다(density.test.jsx의 baseDecl과 같은 이유).
function lastUnconditionalDeclaration(el, prop) {
  let found = null;
  for (const rule of rulesFor(el).filter((r) => r.cond === "")) {
    const re = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, "g");
    let m;
    while ((m = re.exec(rule.body)) !== null) found = m[1].trim();
  }
  return found;
}

function renderLogo() {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <BrandLogo />
    </ThemeProvider>,
  );
}

describe("BrandLogo 부제 — SVG <text> 대신 HTML로 그린다", () => {
  it("부제 글자가 <svg><text> 안이 아니라 일반 HTML 요소다", () => {
    renderLogo();
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });
    expect(subtitle.tagName.toLowerCase()).not.toBe("text");
    expect(subtitle.closest("svg")).toBeNull();
  });

  it("부제 크기가 2200px 이상에서 12px 이상이고, 4K에서 무한정 커지지도 않는다", () => {
    renderLogo();
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });
    const root = document.querySelector("svg.wordmark").parentElement.parentElement;

    /* 부제는 자기 크기를 스스로 정하지 않는다 — 락업 바깥 상자의 BRAND_UNIT 을 그대로 받는다
     * (`1em`). 그 단위 하나에서 마크·간격·워드마크 폭까지 파생되므로, 크기를 물으려면
     * 바깥 상자를 봐야 한다. */
    expect(lastUnconditionalDeclaration(subtitle, "font-size")).toBe("1em");

    /* 값을 리터럴로 못박지 않는 이유: 이 단위는 워드마크 폭과 맞물려 있다(BrandLogo 의
     * '락업 치수' 주석). 균형을 조정할 때마다 여기 적힌 숫자가 같이 틀리면 검사가 아니라
     * 걸림돌이다. 지킬 것은 숫자가 아니라 양쪽 경계다:
     *   하한 — QA tiny_text 가 도는 2200px 이상(루트 18px)에서 12px 미만이면 안 된다.
     *   상한 — rem 만 쓰면 4K(루트 20px)에서 로고만 25% 커진다(사용자 지적). 상한이 있어야
     *          해상도·브라우저 배율이 바뀌어도 크기가 좁은 범위 안에서만 움직인다. */
    const unit = lastUnconditionalDeclaration(root, "font-size");
    const m = /^min\(\s*([\d.]+)rem\s*,\s*([\d.]+)px\s*\)$/.exec(unit || "");
    expect(m, `락업 단위가 min(<n>rem, <n>px) 꼴이 아니다: ${unit}`).not.toBeNull();

    const [, remPart, pxCap] = m.map(Number);
    const at = (rootPx) => Math.min(remPart * rootPx, pxCap);

    expect(at(18), `2200px 이상에서 ${at(18)}px — QA tiny_text 하한(12px) 미만`)
      .toBeGreaterThanOrEqual(12);
    // 루트 16px(≤2199) 대비 루트 20px(≥3000)에서의 증가폭. rem 만 쓰면 25%가 된다.
    const growth = at(20) / at(16);
    expect(growth, `4K에서 락업이 ${Math.round((growth - 1) * 100)}% 커진다 — 상한이 없다`)
      .toBeLessThan(1.2);
  });

  it("워드마크 SVG 안에는 'Clovir'/'Assist' <text> 두 개만 남는다(부제 <text>는 제거됐다)", () => {
    renderLogo();
    const svg = document.querySelector("svg.wordmark");
    const texts = [...svg.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts).toEqual(["Clovir", "Assist"]);
  });
});

/* 부제가 워드마크 **바로 아래**에 붙어 있는가 — 구조로 본다.
 *
 * 사용자 지적: "SMART WORKSPACE ASSISTANT 가 Header 하단에 따로 떨어져 보인다".
 * 원인은 여백이 아니라 구조였다. 마크·글자·빈 여백까지 다 든 528×156 SVG 한 장을 그려 놓고
 * 부제를 그 위에 절대위치(left 31% / top 74%)로 얹었는데, 그 상자는 글자 베이스라인 아래로
 * 45%가 빈 채여서 부제가 상단바 바닥까지 밀려 내려갔다. 좌표를 다른 숫자로 바꾸는 것은
 * 해법이 아니다 — 그래서 이 검사는 "부제가 워드마크의 형제로, 세로 흐름 안에 있는가"를 본다.
 * jsdom 은 레이아웃을 계산하지 않으므로 픽셀 위치는 물을 수 없다(density.test.jsx 와 같은 이유).
 */
describe("BrandLogo 락업 — 마크 + 2단 텍스트 블록", () => {
  it("부제가 워드마크와 같은 부모 안에 있고, 그 부모는 세로 배치다", () => {
    renderLogo();
    const wordmark = document.querySelector("svg.wordmark");
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });

    expect(subtitle.parentElement).toBe(wordmark.parentElement);
    const block = wordmark.parentElement;
    expect(lastUnconditionalDeclaration(block, "flex-direction")).toBe("column");
    // 워드마크가 먼저, 부제가 그 다음 — 2줄 순서 자체를 못박는다.
    expect([...block.children].indexOf(wordmark)).toBeLessThan(
      [...block.children].indexOf(subtitle),
    );
  });

  it("부제를 절대위치로 얹지 않는다 — 좌표로 미는 방식으로 되돌아가면 여기서 걸린다", () => {
    renderLogo();
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });

    expect(lastUnconditionalDeclaration(subtitle, "position")).not.toBe("absolute");
    for (const prop of ["top", "left", "bottom", "right", "margin-top"]) {
      expect(lastUnconditionalDeclaration(subtitle, prop), `부제에 ${prop} 보정이 있다`)
        .toBeNull();
    }
  });

  it("두 줄은 시작점이 아니라 가운데를 맞춘다", () => {
    /* 두 줄의 폭은 정확히 같지 않다(부제 15.83em vs 워드마크 15em, 그리고 폰트가 폴백으로
     * 떨어지면 부제가 더 좁아진다). 시작점만 맞추면 그 차이가 전부 오른쪽에 몰려 블록이
     * 왼쪽으로 쏠려 보인다 — 사용자 지적("중앙 정렬이 어색하다")이 그것이다.
     * letter-spacing 을 벌려 폭을 억지로 맞추는 대신 가운데를 맞춘다. */
    renderLogo();
    const wordmark = document.querySelector("svg.wordmark");
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });

    expect(lastUnconditionalDeclaration(wordmark.parentElement, "align-items")).toBe("center");
    expect(lastUnconditionalDeclaration(subtitle, "text-align")).toBe("center");
  });

  it("마크와 텍스트 블록은 가로로 나란히 놓인다", () => {
    renderLogo();
    const wordmark = document.querySelector("svg.wordmark");
    const root = wordmark.parentElement.parentElement;

    expect(lastUnconditionalDeclaration(root, "display")).toBe("inline-flex");
    expect(lastUnconditionalDeclaration(root, "align-items")).toBe("center");
    // 마크는 텍스트 블록의 형제다(예전처럼 워드마크 SVG 안에 그려 넣지 않는다).
    const mark = [...root.children].find((el) => el.tagName.toLowerCase() === "svg");
    expect(mark, "마크 SVG가 락업 루트의 자식이 아니다").toBeTruthy();
    expect(mark).not.toBe(wordmark);
  });
});
