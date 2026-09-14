import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Button, Callout, CountChip, DotLabel, Tag } from "./kit.jsx";
import { FilterSurface, ToolbarRow } from "./FilterBar.jsx";
import { FilterSelect } from "./filters.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 긴 데이터가 들어와도 **높이가 정해진 부품은 한 줄**, **글이 흐르는 부품은 자리 안에서 줄바꿈**
 * (핸드오프 계획 §0-3 줄바꿈 계약 · §0-5 긴 데이터).
 *
 * 실측으로만 드러나던 결함이다: 34px 버튼의 라벨이 두 줄로 접히면 그 줄의 버튼 높이가 전부
 * 갈리고, 태그 · 필터 값이 한 줄을 넘으면 칸이 부풀어 옆 칸과 윗선이 어긋난다. 반대로 메시지
 * 박스의 문장을 한 줄에 가두면 판 밖으로 넘친다. 여기서는 계산된 스타일로 그 정책을 단언하고,
 * 실제 폭에서의 결과는 `scripts/ui_qa/hostile_data.py` · `kit_measure.py` 가 잰다. */

const LONG = "사내 업무 자동화 플랫폼의 티켓 상태 전이 규칙을 부서 범위 관리자 권한과 함께 다시 검토하는 아주 긴 이름";
const URL = "https://internal.example.co.kr/very/deep/path/segment-without-any-break-opportunity";

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("높이가 정해진 부품 — 한 줄 · 말줄임 · 전체 값", () => {
  it("버튼 라벨은 줄바꿈하지 않고, 말줄임은 `truncate` 를 켠 자리에만 있다", () => {
    ui(<><Button>{LONG}</Button><Button truncate size="sm">{LONG}</Button></>);
    const [plain, cut] = screen.getAllByRole("button");
    expect(getComputedStyle(plain).whiteSpace).toBe("nowrap");
    expect(plain).not.toHaveAttribute("title");
    expect(getComputedStyle(plain.querySelector("span.MuiBox-root")).textOverflow).not.toBe("ellipsis");
    expect(cut).toHaveAttribute("title", LONG);
    expect(getComputedStyle(cut.querySelector("span.MuiBox-root")).textOverflow).toBe("ellipsis");
  });

  it("태그는 한 줄 말줄임이고 부모 폭을 넘지 않는다", () => {
    const { container } = ui(<Tag label={LONG} />);
    const st = getComputedStyle(container.querySelector(".k-tag"));
    expect(st.whiteSpace).toBe("nowrap");
    expect(st.textOverflow).toBe("ellipsis");
    expect(st.maxWidth).toBe("100%");
  });

  it("점과 낱말은 한 줄이고 전체 낱말을 title 로 든다", () => {
    const { container } = ui(<DotLabel label={LONG} tone="warn" />);
    const root = container.querySelector("[data-dot-label]");
    expect(getComputedStyle(root).whiteSpace).toBe("nowrap");
    expect(root).toHaveAttribute("title", LONG);
  });

  it("건수 칩은 숫자가 길어도 같은 높이이고 줄바꿈하지 않는다", () => {
    const { container } = ui(<><CountChip value={1} /><CountChip value="123,456,789건" /></>);
    const [a, b] = container.querySelectorAll("[data-count-chip]");
    expect(getComputedStyle(a).height).toBe(getComputedStyle(b).height);
    expect(getComputedStyle(b).whiteSpace).toBe("nowrap");
  });

  it("필터 칸의 긴 값은 한 줄 말줄임이고 이름과 값 전체를 title 로 든다", () => {
    const { container } = ui(
      <FilterSurface>
        <ToolbarRow>
          <FilterSelect label="분류" value="k" onChange={() => {}} options={[{ value: "k", label: LONG }]} />
        </ToolbarRow>
      </FilterSurface>,
    );
    const value = container.querySelector(`[title="분류 ${LONG}"]`);
    expect(value).not.toBeNull();
    const st = getComputedStyle(value);
    expect(st.whiteSpace).toBe("nowrap");
    expect(st.textOverflow).toBe("ellipsis");
  });
});

describe("글이 흐르는 부품 — 자리 안에서 줄바꿈", () => {
  it("메시지 박스 본문은 한 줄에 갇히지 않고 한글은 낱말 단위로 접힌다", () => {
    const { container } = ui(<Callout tone="danger">{`${LONG} ${URL}`}</Callout>);
    const box = container.querySelector(".k-callout");
    const st = getComputedStyle(box);
    expect(st.whiteSpace).not.toBe("nowrap");
    expect(st.wordBreak).toBe("keep-all");
    // 글 칸의 바닥이 0 이라 긴 URL 이 동작 칸이나 판 밖으로 밀어내지 않는다.
    expect(st.gridTemplateColumns).toContain("minmax(0,1fr)");
  });
});
