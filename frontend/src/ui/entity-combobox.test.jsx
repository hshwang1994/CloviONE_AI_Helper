import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";

import { EntityCombobox } from "./filters.jsx";
import { createClovirTheme } from "./theme.js";

/* Entity Selector — «데이터가 쌓이는 만큼 후보가 자라는» 축을 고르는 자리.
 *
 * PLAN 테스트 계획이 이 파일을 이름으로 지목한다(신규 `entity-combobox`). 지키는 것 다섯:
 *
 *  1. **검색 가능.** 입력하면 후보가 걸러진다. 이것이 없으면 프로젝트 200개가 스크롤 목록이
 *     되고, 사용자는 이름을 알면서도 그것을 눈으로 찾아야 한다. 제품 전체에 이런 자리가
 *     **0개**였다(`plain_dropdown_for_entity` pass 0 · fail 80).
 *  2. **키보드만으로 끝난다** (ARIA 1.2 combobox). 화살표로 옮기고 Enter 로 고른다.
 *  3. **되돌릴 길이 있다.** 목록 첫 줄의 「… 전체」 — 이 제품의 다른 필터와 같은 어휘다.
 *     되돌릴 수 없는 필터는 함정이다(C2).
 *  4. **주소에서 복원한 값이 사라지지 않는다.** 후보에 없는 값이면 그 값을 후보로 끼운다.
 *  5. **고른 값을 끝까지 알 수 있다.** 잘려도 `title` 로 전체 값이 나온다(C2 «값 식별성»).
 */

function renderBox(props) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <EntityCombobox
        label="프로젝트"
        value=""
        onChange={() => {}}
        options={[
          { value: "p1", label: "P. SK 하이닉스 [용인 클러스터 대비]", secondary: "인프라팀" },
          { value: "p2", label: "P. SK 하이닉스 [이천 증설]", secondary: "인프라팀" },
          { value: "p3", label: "D. 굿모닝아이텍 [ClovirONE 2.0]", secondary: "제품팀" },
        ]}
        {...props}
      />
    </ThemeProvider>,
  );
}

describe("EntityCombobox", () => {
  it("입력하면 후보가 걸러진다 — 이것이 «검색형» 의 전부다", async () => {
    const user = userEvent.setup();
    renderBox();
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    await user.click(input);
    // 열자마자 「전체」 + 후보 셋.
    expect(await screen.findAllByRole("option")).toHaveLength(4);
    // 값이 있는 상태에서 타이핑하면 갈아 끼운다(`selectOnFocus`) — 시험에서는 그 선택을
    // 명시적으로 만든다(jsdom 은 포인터 이벤트로 캐럿을 다시 잡는다).
    await user.clear(input);
    await user.type(input, "이천");
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0].textContent).toContain("이천 증설");
  });

  it("앞부분이 같은 후보는 보조 식별자로 갈린다 — 자르고 끝내면 둘이 같은 값이 된다", async () => {
    const user = userEvent.setup();
    renderBox();
    await user.click(screen.getByRole("combobox", { name: "프로젝트" }));
    await user.clear(screen.getByRole("combobox", { name: "프로젝트" }));
    await user.type(screen.getByRole("combobox", { name: "프로젝트" }), "하이닉스");
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(2);
    // 두 후보의 접근 가능한 이름이 서로 다르다(앞부분이 같아도).
    expect(options[0].textContent).not.toBe(options[1].textContent);
    for (const o of options) expect(o.textContent).toContain("인프라팀");
  });

  it("키보드만으로 고를 수 있다 (ARIA 1.2 combobox)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderBox({ onChange });
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    await user.click(input);
    expect(input.getAttribute("aria-autocomplete")).toBe("list");
    await user.clear(input);
    await user.type(input, "이천");
    // `autoHighlight` 가 첫 후보를 이미 짚고 있다 — Enter 하나로 끝난다.
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("p2");
  });

  it("되돌릴 길이 목록 안에 있다 — 다른 필터와 같은 어휘(「… 전체」)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderBox({ value: "p1", onChange });
    await user.click(screen.getByRole("combobox", { name: "프로젝트" }));
    const all = await screen.findByRole("option", { name: "프로젝트 전체" });
    await user.click(all);
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("후보에 없는 값도 그대로 보여 준다 — 주소에서 복원한 필터가 화면에서만 사라지지 않는다", () => {
    renderBox({ value: "p-사라진-것" });
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    expect(input.value).toBe("p-사라진-것");
  });

  it("고른 값이 잘려도 전체 값을 알 수 있다 (C2 «선택된 값 식별성»)", () => {
    renderBox({ value: "p1" });
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    expect(input.getAttribute("title")).toBe("P. SK 하이닉스 [용인 클러스터 대비]");
  });

  it("빈 값의 「… 전체」는 포커스해도 자리표시자로 남고, 입력 글자로 넣지 않는다", async () => {
    const user = userEvent.setup();
    const { container } = renderBox();
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    expect(input.getAttribute("placeholder")).toBe("프로젝트 전체");
    expect(input.value).toBe("");
    expect(container.querySelector(".MuiInputLabel-shrink"), "필터 노치 라벨은 유지된다").toBeTruthy();
    await user.click(input);
    expect(input.getAttribute("placeholder")).toBe("프로젝트 전체");
    expect(input.value).toBe("");
  });

  it("타이핑을 시작하면 「… 전체」 뒤에 글자가 붙지 않는다", async () => {
    const user = userEvent.setup();
    renderBox();
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    await user.click(input);
    await user.type(input, "D.");
    expect(input.value).toBe("D.");
    expect(input.value.includes("프로젝트 전체")).toBe(false);
  });

  it("후보가 없을 때 «없다» 고 말한다 — 빈 목록은 고장으로 읽힌다", async () => {
    const user = userEvent.setup();
    renderBox({ options: [], noOptionsText: "일치하는 프로젝트가 없습니다" });
    const input = screen.getByRole("combobox", { name: "프로젝트" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "없는것");
    expect(await screen.findByText("일치하는 프로젝트가 없습니다")).toBeTruthy();
  });
});
