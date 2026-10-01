/* 스위치 — 브라우저가 실제로 받는 CSS 와 조작 계약 (D-525).
 *
 * `theme-contract.test.js` 는 테마 객체의 값과 관계식을 잰다. 여기서는 그 값이 **emotion 이 낸 규칙으로 실제 요소에
 * 닿는지**를 본다 — MUI 의 같은 자리 규칙(켠 트랙 0.5 · 비활성 트랙 0.12 · 손잡이 둘레 halo · small 변형의 px 치수)이
 * 특이도로 이기면 객체는 맞고 화면은 틀린다. jsdom 은 `:hover` · `:active` · `:focus-visible` 를 계산하지 않으므로 그
 * 셋은 emotion 의 `<style>` 에서 규칙을 읽고, 실제 포인터 · 키보드 상태는 `scripts/ui_qa/switch_states.py` 가 잰다.
 *
 * 조작 계약: 실제 checkbox(role=switch)이고 상태는 네이티브 checked 로 나간다 · Space 가 바꾼다 · `SettingRow` 의 이름을
 * 누르면 바뀐다(`controlId`) · 비활성은 클릭 · Space · 이름 클릭 어느 것에도 바뀌지 않는다.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import Switch from "@mui/material/Switch";

import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { SettingRow } from "./adminKit.jsx";
import { createClovirTheme, remPx, SWITCH } from "./theme.js";

const rgb = (hex) => {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
};

/* 테마 모드는 `<html data-theme>` 가 정한다(`ThemeModeProvider`) — 렌더 전에 세우고 시험 뒤에 걷는다. */
function inMode(mode, node) {
  document.documentElement.setAttribute("data-theme", mode);
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}
afterEach(() => { document.documentElement.removeAttribute("data-theme"); });

function parts(name) {
  const input = screen.getByRole("switch", { name });
  const root = input.closest(".MuiSwitch-root");
  return {
    input,
    root,
    base: root.querySelector(".MuiSwitch-switchBase"),
    track: root.querySelector(".MuiSwitch-track"),
    thumb: root.querySelector(".MuiSwitch-thumb"),
  };
}

function Row({ initial = false, disabled = false, onToggle = () => {}, controlId = "t-switch" }) {
  const [on, setOn] = React.useState(initial);
  return (
    <SettingRow
      compact label="새 댓글 알림" description="내 티켓에 댓글이 달리면 알립니다."
      controlId={controlId}
      action={(
        <Switch
          id={controlId || undefined} checked={on} disabled={disabled}
          onChange={(e) => { setOn(e.target.checked); onToggle(e.target.checked); }}
          slotProps={{ input: { "aria-label": "새 댓글 알림 받기" } }}
        />
      )}
    />
  );
}

/* emotion 이 낸 스타일 전체. jsdom 의 계산값은 **특이도를 보지 않고 문서 순서로만** 겹치기 때문에(나중에 삽입된 손잡이 ·
   트랙 자신의 규칙이 이긴다) 상태 규칙(switchBase 에서 형제 · 자식으로 내려 쓰는 규칙)은 계산값으로 재지 못한다 — 그 승패는
   실브라우저 하네스가 재고(`switch_states` · `kit_measure` 의 `switch_geometry`), 여기서는 **그 규칙이 실제로 들어갔는지**를
   본다. 슬롯 이름(`track` · `thumb` · `switchBase` · `root`)을 하나라도 틀리게 적으면 MUI 가 그 덩어리를 통째로 버리는데,
   테마 객체만 재는 시험은 그것을 못 잡는다. */
const emotionCss = () => [...document.querySelectorAll("style")].map((el) => el.textContent || "").join("\n").toLowerCase();
/* `selectorTail{…}` 블록 가운데 하나가 선언들을 **모두** 갖는가. emotion 은 시험에서 접두사(-webkit- 등)를 앞에 붙이므로
   블록의 첫머리가 아니라 블록 안을 본다. */
const declares = (css, selectorTail, body) => {
  const wanted = body.toLowerCase().split(";").filter(Boolean).map((d) => d + ";");
  const head = `${selectorTail}{`;
  for (let at = css.indexOf(head); at !== -1; at = css.indexOf(head, at + 1)) {
    const block = css.slice(at + head.length, css.indexOf("}", at)) + ";";
    if (wanted.every((d) => block.includes(d))) return true;
  }
  return false;
};

describe("스위치가 받는 CSS", () => {
  it.each(["light", "dark"])("%s — 꺼짐은 계산값으로, 켜짐 · 비활성 · 손잡이 규칙은 실제로 들어간 규칙으로 잰다", (mode) => {
    const p = createClovirTheme(mode).palette;
    inMode(mode, <Switch checked={false} onChange={() => {}} slotProps={{ input: { "aria-label": "꺼짐" } }} />);
    // 꺼짐은 트랙 · 손잡이 **자신**의 규칙이라 계산값이 믿을 만하다.
    const off = parts("꺼짐");
    expect(getComputedStyle(off.track).backgroundColor).toBe("rgba(0, 0, 0, 0)");
    expect(getComputedStyle(off.track).borderTopColor).toBe(rgb(p.text.faint));
    expect(getComputedStyle(off.track).opacity).toBe("1");
    expect(getComputedStyle(off.thumb).backgroundColor).toBe(rgb(p.text.faint));
    expect(getComputedStyle(off.thumb).boxShadow).toBe("none");

    const css = emotionCss();
    const edge = mode === "light" ? p.primary.main : p.primary.dark;
    // MUI 는 켠 트랙에 opacity 0.5, 비활성 트랙에 0.12 를 깐다 — 우리 규칙에 opacity:1 이 함께 있어야 이긴다.
    expect(declares(css, ".mui-checked+.muiswitch-track", `opacity:1;background-color:${p.primary.main};border-color:${edge};`)).toBe(true);
    expect(declares(css, ".mui-checked .muiswitch-thumb", "background-color:#FFFFFF;")).toBe(true);
    expect(declares(css, ".mui-disabled+.muiswitch-track", `opacity:1;background-color:${p.background.inset};border-color:${p.divider};`)).toBe(true);
    expect(declares(css, ".mui-disabled .muiswitch-thumb", `background-color:${p.disabledControlInk};`)).toBe(true);
    expect(declares(css, ".mui-disabled.mui-checked+.muiswitch-track",
      `background-color:${p.disabledControlInk};border-color:${p.disabledControlInk};`)).toBe(true);
    expect(declares(css, ".mui-disabled.mui-checked .muiswitch-thumb", `background-color:${p.background.inset};`)).toBe(true);
  });

  it("치수는 rem 이고 트랙은 알약이며, `size=\"small\"` 도 같은 스위치다", () => {
    inMode("light", (
      <>
        <Switch checked onChange={() => {}} slotProps={{ input: { "aria-label": "보통" } }} />
        <Switch size="small" checked onChange={() => {}} slotProps={{ input: { "aria-label": "작게" } }} />
      </>
    ));
    for (const name of ["보통", "작게"]) {
      const { root, track } = parts(name);
      const rs = getComputedStyle(root);
      // 루트 자신의 규칙 — MUI 기본(58px)과 small 변형(40 x 24)이 같은 블록 안에서 먼저 서고 우리 값이 뒤에 선다.
      expect(rs.width, name).toBe(remPx(SWITCH.boxW));
      expect(rs.height, name).toBe(remPx(SWITCH.hit));
      expect(rs.overflow, name).toBe("hidden");
      expect(getComputedStyle(track).borderRadius, name).toBe("999px");
    }
    // 손잡이 크기와 켜짐 이동은 루트 아래 중첩 규칙이다 — 들어갔는지 본다(승패는 실브라우저가 잰다).
    const css = emotionCss();
    expect(declares(css, " .muiswitch-thumb", `width:${remPx(SWITCH.thumb)};height:${remPx(SWITCH.thumb)};`)).toBe(true);
    expect(declares(css, " .muiswitch-switchbase.mui-checked", `transform:translatex(${remPx(SWITCH.travel)});`)).toBe(true);
  });

  it("올림 · 누름 · 초점 규칙이 emotion 의 스타일에 실제로 들어간다", () => {
    const p = createClovirTheme("light").palette;
    inMode("light", <Switch checked={false} onChange={() => {}} slotProps={{ input: { "aria-label": "규칙" } }} />);
    const css = [...document.querySelectorAll("style")].map((el) => el.textContent || "").join(" ");
    const lower = (v) => v.toLowerCase();
    expect(css).toMatch(/@media \(hover: ?hover\)/);
    expect(lower(css)).toContain(`:has(.muiswitch-input:hover)+.muiswitch-track{background-color:${lower(p.background.inset)};border-color:${lower(p.text.secondary)}`);
    expect(lower(css)).toContain(`:has(.muiswitch-input:active)+.muiswitch-track{background-color:${lower(p.background.sunken)};border-color:${lower(p.text.secondary)}`);
    expect(css).toContain(".Mui-focusVisible+.MuiSwitch-track{outline:2px solid var(--clovir-focus-ring");
    expect(css).not.toMatch(/MuiSwitch[^}]*transition:[^};]*\b\d+ms[^,};]*\b\d+ms/);
  });
});

describe("스위치 조작 계약", () => {
  it("실제 switch 이고 상태는 네이티브 checked 로 나가며, 누르면 바뀐다", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    inMode("light", <Row onToggle={onToggle} />);
    const input = screen.getByRole("switch", { name: "새 댓글 알림 받기" });
    expect(input).toHaveAttribute("type", "checkbox");
    expect(input).not.toBeChecked();
    await user.click(input);
    expect(input).toBeChecked();
    expect(onToggle).toHaveBeenLastCalledWith(true);
  });

  it("Space 로 바뀌고 초점이 그대로 남는다", async () => {
    const user = userEvent.setup();
    inMode("light", <Row />);
    const input = screen.getByRole("switch", { name: "새 댓글 알림 받기" });
    await user.tab();
    expect(input).toHaveFocus();
    await user.keyboard(" ");
    expect(input).toBeChecked();
    expect(input).toHaveFocus();
    await user.keyboard(" ");
    expect(input).not.toBeChecked();
  });

  it("`controlId` 를 준 줄은 이름이 그 스위치의 라벨이라, 이름을 눌러도 바뀐다", async () => {
    const user = userEvent.setup();
    inMode("light", <Row />);
    const name = screen.getByText("새 댓글 알림");
    expect(name.tagName).toBe("LABEL");
    expect(name).toHaveAttribute("for", "t-switch");
    const input = screen.getByRole("switch", { name: "새 댓글 알림 받기" });
    expect(input).toHaveAttribute("id", "t-switch");
    await user.click(name);
    expect(input).toBeChecked();
    await user.click(name);
    expect(input).not.toBeChecked();
    // 접근 가능한 이름은 여전히 스위치의 aria-label 이다 — 시험과 QA 흐름이 그 이름으로 찾는다.
    expect(screen.getByRole("switch", { name: "새 댓글 알림 받기" })).toBe(input);
  });

  it("`controlId` 가 없으면 이름은 라벨이 아니다 — 단추 · 세그먼티드 줄의 이름이 컨트롤을 누르지 않게", () => {
    inMode("light", <Row controlId={null} />);
    expect(screen.getByText("새 댓글 알림").tagName).toBe("DIV");
  });

  it("비활성은 클릭 · Space · 이름 클릭 어느 것에도 바뀌지 않고 초점도 받지 않는다", async () => {
    /* 비활성 스위치는 `pointer-events: none` 이라 user-event 는 아예 누르기를 거부한다(브라우저와 같은 판단이다).
       그 검사를 끄고 클릭을 그대로 보내도 비활성 input 은 바뀌지 않아야 한다. */
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const onToggle = vi.fn();
    inMode("light", <Row initial disabled onToggle={onToggle} />);
    const input = screen.getByRole("switch", { name: "새 댓글 알림 받기" });
    expect(input).toBeDisabled();
    expect(input).toBeChecked();
    await user.click(input);
    await user.click(screen.getByText("새 댓글 알림"));
    await user.tab();
    expect(input).not.toHaveFocus();
    await user.keyboard(" ");
    expect(input).toBeChecked();
    expect(onToggle).not.toHaveBeenCalled();
  });
});
