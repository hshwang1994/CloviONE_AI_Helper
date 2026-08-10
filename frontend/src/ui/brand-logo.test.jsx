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

  it("부제 글자 크기가 4K에서도 12px 이상으로 남는 rem 값이다 — 6px대가 아니다", () => {
    renderLogo();
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });
    const fontSize = lastUnconditionalDeclaration(subtitle, "font-size");

    /* 값을 리터럴로 못박지 않는 이유: 부제 크기는 워드마크 폭과 맞물려 있다(BrandLogo 의
     * '락업 치수' 주석 — 부제의 진행폭 × 글자크기 = 워드마크 폭이라야 두 줄이 한 덩어리로
     * 보인다). 그 균형을 조정할 때마다 여기 적힌 숫자가 같이 틀리면 검사가 아니라 걸림돌이다.
     * 지킬 것은 숫자가 아니라 하한선이다: (1) px 고정이 아니라 rem 이라 4K 레버를 타야 하고,
     * (2) tiny_text 검사가 도는 2200px 이상(루트 18px)에서 12px 아래로 내려가면 안 된다. */
    expect(fontSize, "부제가 rem이 아니다 — 4K 루트 폰트사이즈 레버를 안 탄다").toMatch(/rem$/);
    const atFourK = Number.parseFloat(fontSize) * 18;
    expect(atFourK, `2200px 이상에서 ${atFourK}px — QA tiny_text 하한(12px) 미만`)
      .toBeGreaterThanOrEqual(12);
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
