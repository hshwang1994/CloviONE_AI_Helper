/* 조건 줄의 컨트롤을 **세로 폼**에 놓았을 때 — 치수가 따라오면 안 된다.
 *
 * ## 무엇이 깨졌었나
 *
 * `CONTROL_KIND.entity` 는 `flex: 1 1 18rem` 이다. 그 18rem 은 **가로로 흐르는 조건 줄**의
 * 폭이지만, 같은 컨트롤을 세로 `Stack`(flex-direction: column) 안에 놓으면 flex-basis 가
 * **주축 = 높이**가 된다. 새 문서 모달에서 실제로 그렇게 됐고, 「프로젝트」 칸 하나가
 * 324px 로 부풀어 「폴더」와의 사이에 손바닥만 한 빈칸이 생겼다. 모달 높이는 1,066px 였다.
 *
 * 정적 검사도 vitest 도 이것을 못 봤다 — 둘 다 **렌더된 높이**를 안 본다. 그래서 여기서는
 * 값을 만드는 함수(`kindSx`)의 결과를 직접 못박는다: 폼 자리로 선언하면 줄 치수가 **없다**.
 *
 * ## 그리고 UUID
 *
 * 후보 목록에서 못 찾은 값을 라벨로 그대로 쓰면 그 자리가 UUID 를 보여 준다. 운영에서
 * 정확히 그랬다. 값이 식별자 모양이면 사람이 읽을 문장으로 바꾼다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  CONTROL_KIND, EntityCombobox, FilterSelect, FORM_FIELD_SX, isOpaqueId, kindSx, unmatchedLabel,
} from "./filters.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

const UUID = "62134ac8-831e-4071-bb07-d7c3144d85eb";
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function withTheme(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("폼 자리의 치수 — 줄 치수를 물려받지 않는다", () => {
  it("`layout=\"form\"` 은 종류별 줄 치수를 **통째로** 대체한다", () => {
    const row = kindSx("entity", undefined);
    const form = kindSx("entity", undefined, "form");

    /* 줄 자리는 그대로다 — 이 시험이 조건 줄의 폭 규칙을 지키는 쪽도 함께 본다. */
    expect(row.flex).toBe(CONTROL_KIND.entity.flex);
    /* 폼 자리에는 **flex-basis 가 없다**. 이것이 높이로 새던 값이다. */
    expect(form.flex).toBe(FORM_FIELD_SX.flex);
    expect(String(form.flex)).not.toMatch(/rem/);
    expect(form.maxWidth).toBe("none");
    expect(form.width).toBe("100%");
  });

  it("호출부 `sx` 는 폼 자리에서도 여전히 이긴다", () => {
    const merged = kindSx("entity", { maxWidth: "20rem" }, "form");
    expect(merged.maxWidth).toBe("20rem");
    expect(merged.flex).toBe(FORM_FIELD_SX.flex);
  });

  it("줄 치수를 쓰는 종류 전부가 폼 자리에서 같은 규칙을 받는다", () => {
    for (const kind of Object.keys(CONTROL_KIND)) {
      const form = kindSx(kind, undefined, "form");
      expect(form.flex).toBe(FORM_FIELD_SX.flex);
    }
  });
});

describe("후보에 없는 값 — 식별자를 사용자에게 그리지 않는다", () => {
  it("UUID 모양만 가리고, 값이 곧 이름인 축은 그대로 둔다", () => {
    expect(isOpaqueId(UUID)).toBe(true);
    expect(isOpaqueId("진행 중")).toBe(false);
    expect(unmatchedLabel(UUID, false)).not.toMatch(UUID_RE);
    expect(unmatchedLabel("진행 중", false)).toBe("진행 중");
  });

  it("아직 받는 중과 못 찾음을 **다른 문장**으로 말한다", () => {
    expect(unmatchedLabel(UUID, true)).not.toBe(unmatchedLabel(UUID, false));
  });

  it("EntityCombobox 는 후보가 비어도 입력칸에 UUID 를 안 넣는다", () => {
    withTheme(
      <EntityCombobox label="프로젝트" value={UUID} onChange={() => {}} options={[]} />,
    );
    const input = screen.getByRole("combobox");
    expect(UUID_RE.test(input.value || "")).toBe(false);
    expect(UUID_RE.test(document.body.textContent || "")).toBe(false);
  });

  it("FilterSelect 도 같다 — 같은 함정이 두 부품에 있었다", () => {
    withTheme(
      <FilterSelect label="프로젝트" value={UUID} onChange={() => {}} options={[]} />,
    );
    expect(UUID_RE.test(document.body.textContent || "")).toBe(false);
  });

  it("후보에 있으면 당연히 이름을 그린다", () => {
    withTheme(
      <EntityCombobox
        label="프로젝트"
        value={UUID}
        onChange={() => {}}
        options={[{ value: UUID, label: "SK하이닉스 [용인 클러스터]" }]}
      />,
    );
    expect(screen.getByRole("combobox").value).toBe("SK하이닉스 [용인 클러스터]");
  });
});

describe("타일 트랙 — 마지막 줄이 반만 차지 않는다", () => {
  it("개수를 나누어떨어지게 하는 칸 수를 고른다", async () => {
    const { balancedTileTracks } = await import("./density.js");
    const eight = balancedTileTracks(8);
    expect(eight.xs).toBe("repeat(2, minmax(0, 1fr))");
    expect(eight.sm).toBe("repeat(4, minmax(0, 1fr))");
    expect(eight.xl).toBe("repeat(8, minmax(0, 1fr))");
    /* 여섯이면 2·3·6 — 어느 폭에서도 꽉 찬다. */
    const six = balancedTileTracks(6);
    expect(six.sm).toBe("repeat(3, minmax(0, 1fr))");
    expect(six.xl).toBe("repeat(6, minmax(0, 1fr))");
  });
});

/* jsdom 은 레이아웃이 없어 «324px 였다» 를 직접 못 잰다 — 그래서 위 시험들은 값이 만들어지는
   자리를 못박는다. 실제 높이는 실브라우저 검수가 확인했다(모달 1,066px → 471px). */

/* 폼 자리의 이름은 **칸 위**에 선다 — 핸드오프 RULES §7 · 계획 §0-11(노치 라벨 금지).
 * 줄 칸이 아닌 자리에서 `label` 을 받으면 MUI 라벨이 테두리 노치 대신 칸 위 흐름에 서고, 노치 틈은 접힌다. */
describe("폼 자리의 이름 — 노치가 아니라 칸 위", () => {
  it("FilterSelect 폼 자리의 라벨은 흐름 안(static)에 서고 노치 틈이 접힌다", () => {
    const { container } = withTheme(
      <FilterSelect layout="form" label="역할" value="" onChange={() => {}} options={["관리자", "사용자"]} />,
    );
    const label = container.querySelector(".MuiInputLabel-root");
    expect(label, "라벨이 없다").not.toBeNull();
    expect(getComputedStyle(label).position).toBe("static");
    expect(getComputedStyle(label).transform === "none" || getComputedStyle(label).transform === "").toBe(true);
    const legend = container.querySelector("fieldset legend");
    expect(getComputedStyle(legend).maxWidth).toBe("0.01px");
    // 접근 이름은 그대로 라벨 낱말이다.
    expect(screen.getByLabelText("역할")).toBeTruthy();
  });

  it("EntityCombobox 폼 자리도 같은 규칙이고, 줄 칸은 칸 안 접두 이름 그대로다", () => {
    const { container, unmount } = withTheme(
      <EntityCombobox layout="form" label="담당자" value="" onChange={() => {}} options={[{ value: "u1", label: "김하나" }]} />,
    );
    /* jsdom 의 계산 스타일은 선택자 우선순위를 다 따지지 않는다 — 칸 뿌리 클래스에 걸린 규칙 자체를 읽는다. */
    const root = container.querySelector(".MuiInputLabel-root").parentElement;
    const rootClass = [...root.classList].find((c) => c.startsWith("css-"));
    const rules = [...document.styleSheets].flatMap((sh) => [...sh.cssRules].map((r) => r.cssText));
    expect(
      rules.some((t) => t.startsWith(`.${rootClass} .MuiInputLabel-root`) && /position:\s*static/.test(t)),
      "칸 뿌리에 위 라벨 규칙이 없다",
    ).toBe(true);
    expect(rules.some((t) => t.includes(`.${rootClass} .MuiOutlinedInput-notchedOutline legend`) && t.includes("0.01px"))).toBe(true);
    unmount();
    const row = withTheme(
      <EntityCombobox layout="row" label="담당자" value="" onChange={() => {}} options={[{ value: "u1", label: "김하나" }]} />,
    );
    expect(row.container.querySelector(".MuiInputLabel-root"), "줄 칸에 노치 라벨이 생겼다").toBeNull();
  });
});
