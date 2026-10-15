import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import TextField from "@mui/material/TextField";

import { Button, FIELD_ROWS, Field, FieldRow, FormSection } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { CONTROL_HEIGHT_VAR } from "./theme.js";

/* 폼 칸의 해부 (F1 · D-527). 칸 하나는 **라벨 20 · 컨트롤 34 · 도움말 auto** 의 고정 세로 트랙이고, 동작(단추)은 컨트롤과
 * 같은 둘째 줄의 오른쪽 칸에 선다. 도움말 · 오류는 셋째 줄 두 칸 전체에 서고, 오류가 있으면 도움말 자리를 대신한다.
 * 예전에는 공용 칸에 동작 자리가 없어 화면마다 단추를 `flex-end` · `flex-start` · `center` 로 따로 줄 세웠다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

function cell(el) {
  const s = getComputedStyle(el);
  return { row: s.gridRow || s.gridRowStart, column: s.gridColumn || s.gridColumnStart };
}

describe("Field — 세 줄 트랙과 동작 칸", () => {
  it("라벨 · 컨트롤 · 도움말이 고정 트랙에 서고, 동작은 컨트롤과 같은 줄의 오른쪽 칸이다", () => {
    const { container } = ui(
      <Field label="모델" htmlFor="m" help="연결하면 목록을 가져옵니다." helpId="m-help" action={<Button>다시 불러오기</Button>}>
        <TextField id="m" size="small" inputProps={{ "aria-describedby": "m-help" }} />
      </Field>,
    );
    const field = container.querySelector("[data-form-field]");
    const s = getComputedStyle(field);
    expect(s.display).toBe("grid");
    expect(s.gridTemplateRows).toBe(FIELD_ROWS);
    expect(s.gridTemplateColumns).toBe("minmax(0,1fr) auto");

    const label = screen.getByText("모델");
    expect(cell(label).row).toMatch(/^1/);
    const control = container.querySelector(".k-field-control");
    const action = container.querySelector(".k-field-action");
    expect(cell(control).row).toMatch(/^2/);
    expect(cell(action).row).toMatch(/^2/);
    // 동작은 위에 붙는다 — 도움말 줄까지 늘어나 가운데에 뜨지 않는다.
    expect(getComputedStyle(action).alignSelf).toBe("start");
    expect(getComputedStyle(action).alignItems).toBe("flex-start");

    const help = document.getElementById("m-help");
    expect(help).toHaveTextContent("연결하면 목록을 가져옵니다.");
    // 도움말은 두 칸 전체다 — 단추 밑으로도 이어진다.
    expect(getComputedStyle(help).gridColumn.replace(/\s/g, "")).toBe("1/-1");
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-describedby", "m-help");
  });

  it("동작이 없으면 동작 칸 자체가 없다 — 빈 트랙이 입력 폭을 먹지 않는다", () => {
    const { container } = ui(<Field label="이름" htmlFor="n"><TextField id="n" size="small" /></Field>);
    expect(getComputedStyle(container.querySelector("[data-form-field]")).gridTemplateColumns).toBe("minmax(0,1fr)");
    expect(container.querySelector(".k-field-action")).toBeNull();
  });

  it("오류는 도움말 자리를 대신한다 — 두 줄이 쌓여 칸 높이가 흔들리지 않는다", () => {
    ui(
      <Field label="주소" htmlFor="a" help="받는 사람이 보는 주소입니다." error="주소 형식이 아닙니다." helpId="a-help">
        <TextField id="a" size="small" />
      </Field>,
    );
    const help = document.getElementById("a-help");
    expect(help.querySelector('[role="alert"]')).toHaveTextContent("주소 형식이 아닙니다.");
    expect(help).not.toHaveTextContent("받는 사람이 보는 주소입니다.");
  });

  it("가리키는 자리(helpId)가 있으면 도움말이 없어도 셋째 줄이 남는다 — 나중의 오류가 같은 노드에 선다", () => {
    const { container, rerender } = ui(<Field label="제목" htmlFor="t" helpId="t-help"><TextField id="t" size="small" /></Field>);
    expect(document.getElementById("t-help")).toBeInTheDocument();
    rerender(<ThemeModeProvider><Field label="제목" htmlFor="t" helpId="t-help" error="제목을 입력하세요."><TextField id="t" size="small" /></Field></ThemeModeProvider>);
    expect(document.getElementById("t-help").querySelector('[role="alert"]')).toHaveTextContent("제목을 입력하세요.");
    // 가리키는 자리도 도움말도 없으면 빈 줄을 그리지 않는다.
    const bare = ui(<Field label="별칭" htmlFor="b"><TextField id="b" size="small" /></Field>);
    expect(bare.container.querySelector("[data-form-field]").children).toHaveLength(2);
    expect(container).toBeTruthy();
  });

  it("폭 토큰은 혼자 설 때의 상한이다(sm 10 · md 16 · lg 24 · xl 32rem)", () => {
    const { container } = ui(
      <>
        <Field label="포트" htmlFor="p" width="sm"><TextField id="p" size="small" /></Field>
        <Field label="서버" htmlFor="h" width="xl"><TextField id="h" size="small" /></Field>
      </>,
    );
    const [port, host] = container.querySelectorAll("[data-form-field]");
    expect(getComputedStyle(port).maxWidth).toBe("10rem");
    expect(getComputedStyle(host).maxWidth).toBe("32rem");
  });

  it("밀집 칸(density=dense)은 컨트롤 높이 변수를 30 으로 낮춘다", () => {
    const { container } = ui(<Field label="값" htmlFor="v" density="dense"><TextField id="v" size="small" /></Field>);
    const field = container.querySelector("[data-form-field]");
    expect(field.style.getPropertyValue(CONTROL_HEIGHT_VAR) || getComputedStyle(field).getPropertyValue(CONTROL_HEIGHT_VAR).trim())
      .toBe("1.875rem");
  });
});

describe("FieldRow — 한 줄의 칸들과 줄 단위 동작", () => {
  it("줄 동작은 라벨 줄을 비운 같은 트랙의 둘째 줄에 선다", () => {
    const { container } = ui(
      <FieldRow columns={["9.5rem", "9.5rem"]} action={<Button>시간 저장</Button>}>
        <Field label="시작" htmlFor="s"><TextField id="s" size="small" /></Field>
        <Field label="종료" htmlFor="e"><TextField id="e" size="small" /></Field>
      </FieldRow>,
    );
    const row = container.querySelector("[data-field-row]");
    expect(getComputedStyle(row).gridTemplateColumns).toBe("auto auto");
    expect(getComputedStyle(row).justifyContent).toBe("start");
    const action = container.querySelector(".k-field-row-action");
    expect(getComputedStyle(action).gridTemplateRows).toBe(FIELD_ROWS);
    expect(getComputedStyle(container.querySelector(".k-field-row-action-slot")).gridRow).toMatch(/^2/);
    // 값이 폭을 정하는 칸은 상한만 말한다 — 남는 폭을 나누지 않는다.
    const fields = row.firstElementChild;
    expect(getComputedStyle(fields).gridTemplateColumns).toBe("minmax(0, 9.5rem) minmax(0, 9.5rem)");
  });

  it("폭을 말하지 않은 줄은 12칸 컨테이너 격자이고 동작은 칸 묶음 오른쪽의 제 칸이다", () => {
    const { container } = ui(
      <FieldRow action={<Button>확인</Button>}>
        <Field label="서버" htmlFor="x" span={{ wide: 8, mid: 2 }}><TextField id="x" size="small" /></Field>
        <Field label="포트" htmlFor="y" span={{ wide: 4, mid: 1 }}><TextField id="y" size="small" /></Field>
      </FieldRow>,
    );
    const row = container.querySelector("[data-field-row]");
    expect(getComputedStyle(row).gridTemplateColumns).toBe("minmax(0, 1fr) auto");
    expect(getComputedStyle(row.firstElementChild).containerType).toBe("inline-size");
  });
});

describe("FieldRow — 좁은 화면 (P-136)", () => {
  /* jsdom 의 계산 스타일은 미디어 질의를 풀지 않는다 — 줄 뿌리 클래스에 걸린 규칙 자체를 읽는다. */
  const rulesOf = (el) => {
    const cls = [...el.classList].find((c) => c.startsWith("css-"));
    return [...document.styleSheets].flatMap((sh) => [...sh.cssRules].map((r) => r.cssText))
      .filter((t) => /^@media \(max-width:\s*599\.95px\)/.test(t) && t.includes(`.${cls}`));
  };

  it("줄 동작은 600px 아래에서 칸 묶음 아래로 내려가고, 빈 라벨 줄을 걷는다", () => {
    const { container } = ui(
      <FieldRow columns={["12rem", "12rem"]} action={<Button>저장</Button>}>
        <Field label="제한 시간(초)" htmlFor="t"><TextField id="t" size="small" /></Field>
        <Field label="동시 실행 수" htmlFor="c"><TextField id="c" size="small" /></Field>
      </FieldRow>,
    );
    const row = container.querySelector("[data-field-row]");
    expect(rulesOf(row).some((t) => /grid-template-columns:\s*minmax\(0,\s*1fr\)/.test(t)), "좁은 화면에서도 동작이 옆에 남았다").toBe(true);
    expect(rulesOf(container.querySelector(".k-field-row-action")).some((t) => /k-field-row-action-spacer/.test(t) && /display:\s*none/.test(t))).toBe(true);
    expect(rulesOf(container.querySelector(".k-field-row-action-slot")).some((t) => /grid-row:\s*1/.test(t))).toBe(true);
  });

  it("동작이 없는 줄에는 좁은 화면 규칙이 없다", () => {
    const { container } = ui(
      <FieldRow columns={["12rem"]}>
        <Field label="값" htmlFor="v"><TextField id="v" size="small" /></Field>
      </FieldRow>,
    );
    expect(rulesOf(container.querySelector("[data-field-row]"))).toEqual([]);
  });
});

describe("FormSection — 카드가 아닌 폼 구획", () => {
  it("머리 · 1px 선 · 칸 목록이고 판(테두리 · 면)을 두르지 않는다", () => {
    const { container } = ui(
      <FormSection title="보내는 사람" description="받는 사람이 보는 주소입니다.">
        <Field label="보내는 주소" htmlFor="f"><TextField id="f" size="small" /></Field>
      </FormSection>,
    );
    const section = container.querySelector("[data-form-section]");
    expect(section.tagName).toBe("SECTION");
    expect(section).toHaveClass("k-form-section");
    expect(section.querySelector("[data-surface]")).toBeNull();
    expect(section.closest("[data-surface]")).toBeNull();
    expect(screen.getByRole("heading", { name: "보내는 사람" })).toBeInTheDocument();
    expect(screen.getByText("받는 사람이 보는 주소입니다.")).toBeInTheDocument();
  });
});
