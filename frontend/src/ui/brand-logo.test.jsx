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

  it("부제 글자 크기가 사이드바와 같은 읽을 수 있는 값(0.75rem)이다 — 6px대가 아니다", () => {
    renderLogo();
    const subtitle = screen.getByText("SMART WORKSPACE ASSISTANT", { selector: "span" });
    const fontSize = lastUnconditionalDeclaration(subtitle, "font-size");
    expect(fontSize).toBe("0.75rem");
    expect(fontSize).not.toMatch(/^6(\.\d+)?px$/);
    expect(fontSize).not.toBe("20px");
  });

  it("워드마크 SVG 안에는 'Clovir'/'Assist' <text> 두 개만 남는다(부제 <text>는 제거됐다)", () => {
    renderLogo();
    const svg = document.querySelector("svg.wordmark");
    const texts = [...svg.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts).toEqual(["Clovir", "Assist"]);
  });
});
