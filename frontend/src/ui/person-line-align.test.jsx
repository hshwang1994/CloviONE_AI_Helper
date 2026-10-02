import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { PersonLine } from "./UserAvatar.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 사람 줄이 글 줄 안(표 칸 · 문장)에서 세로 가운데에 서는가(랩 캡처의 조직 구성원 표).
 * 인라인 flex 의 기준선은 첫 항목인 아바타의 아래 변이라, `vertical-align` 이 기본값(baseline)이면 아바타 아래 변이 글 기준선에 앉아
 * 이름이 옆 칸 글보다 3 ~ 4px 위에 선다. jsdom 은 배치를 안 하므로 그 규칙이 실제로 걸렸는지를 잰다(실측은 랩 측정 스크립트). */

describe("사람 줄의 세로 정렬", () => {
  it("글 줄 안에서 가운데(middle)에 선다", () => {
    const { container } = render(
      <ThemeModeProvider>
        <table><tbody><tr><td><PersonLine person={{ user_id: "u1" }} name="명성" size="xs" /></td><td>smyeong@goodmit.co.kr</td></tr></tbody></table>
      </ThemeModeProvider>,
    );
    const line = container.querySelector(".k-avatar").parentElement;
    expect(getComputedStyle(line).display).toBe("inline-flex");
    expect(getComputedStyle(line).verticalAlign).toBe("middle");
  });

  it("반례 — 호출부의 sx 는 정렬을 덮을 수 있다(덮지 않으면 기본은 middle 이다)", () => {
    const { container } = render(
      <ThemeModeProvider>
        <PersonLine person={{ user_id: "u1" }} name="명성" sx={{ verticalAlign: "top" }} />
      </ThemeModeProvider>,
    );
    expect(getComputedStyle(container.querySelector(".k-avatar").parentElement).verticalAlign).toBe("top");
  });
});
