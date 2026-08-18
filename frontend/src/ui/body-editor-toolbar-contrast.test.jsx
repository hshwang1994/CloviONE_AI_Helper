import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

/* 작성 도움 툴바(제목/글머리/번호/구분선 + 이모지) 버튼이 흰 Card 배경 위에서 경계가
 * 보이는가.
 *
 * 왜 emotion 이 낸 CSS 텍스트를 직접 읽나 — 이 저장소의 jsdom 은 실제 레이아웃을 계산하지
 * 않고, computed style 도 emotion 이 런타임에 넣는 동적 클래스(css-xxxx)의 선언을 안정적으로
 * 돌려주지 않는다(new-ticket-layout.test.jsx 의 같은 이유). 우리가 sx 로 준 배경 선언은
 * `.css-xxxx { ... }` 규칙으로 나가므로, 그 텍스트에서 직접 읽는다. MUI 가 기본으로 붙이는
 * 정적 클래스(.MuiButton-outlined 등)의 배경은 걸러진다 — 우리가 새로 추가한 배경만 본다.
 */

import { BodyEditor } from "./BodyEditor.jsx";
import { createClovirTheme } from "./theme.js";

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

/* MUI 의 styled() 체인은 같은 속성(background-color 등)을 한 규칙 블록 안에 여러 번
 * 적는다(기본값 → variant 기본값 → 우리 sx 순서). CSS 캐스케이드는 **같은 블록 안에서 뒤에
 * 온 선언이 이긴다** — 그래서 첫 매치가 아니라 마지막 매치를 읽어야 실제로 적용되는 값이
 * 나온다(new-ticket-layout.test.jsx 의 declaration은 grid-template-columns 처럼 한 규칙에
 * 한 번만 나오는 속성을 다뤄 이 문제를 겪지 않았다). */
function declaration(rule, prop) {
  const re = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, "g");
  let last = null;
  let m;
  while ((m = re.exec(rule.body)) !== null) last = m[1].trim();
  return last;
}

/* `var(--variant-outlinedBg)` 처럼 **폴백 없는 CSS 변수 참조**는 실제 배경을 확정하지
 * 않는다 — MUI 의 outlined 버튼은 기본 상태에서 이 변수를 아무도 정의하지 않아(호버에서만
 * 정의됨) 사실상 투명으로 그려진다. 우리가 준 배경인지 확인하려면 실제 색 리터럴
 * (16진수/rgb/hsl)이 있어야 한다. */
function isLiteralColor(value) {
  if (!value) return false;
  const v = value.trim();
  if (/^var\(/.test(v)) return false;
  return /^#|^rgba?\(|^hsla?\(/.test(v);
}

function hasOwnBackground(el) {
  return rulesFor(el).some((r) => {
    const bg = declaration(r, "background-color") || declaration(r, "background");
    return isLiteralColor(bg);
  });
}

function renderEditor() {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <BodyEditor id="desc" value="" onChange={() => {}} label="설명" />
    </ThemeProvider>,
  );
}

describe("작성 도움 툴바 — 버튼이 카드 배경과 구별되는 배경을 스스로 선언한다", () => {
  it("서식 버튼(제목)에 우리가 준 배경색이 선언돼 있다", () => {
    const { getByRole } = renderEditor();
    const btn = getByRole("button", { name: "제목" });
    expect(hasOwnBackground(btn)).toBe(true);
  });

  it("서식 버튼(글머리/번호/구분선)에도 배경색이 선언돼 있다", () => {
    const { getByRole } = renderEditor();
    for (const name of ["글머리", "번호", "구분선"]) {
      expect(hasOwnBackground(getByRole("button", { name }))).toBe(true);
    }
  });

  /* 이모지 버튼 여덟 개는 지시 28 로 없앴다(`body-editor-no-emoji.test.jsx`).
     이 파일이 지키는 것은 "도구 버튼이 카드 배경과 구별되는가"이고, 그 대상은 이제 남아
     있는 네 개다 — 없어진 버튼의 배경색을 계속 재면 초록불이 아무것도 증명하지 않는다. */
});
