import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/* 값을 그 자리에서 바꾸는 공통 계약 (C8 · R-89 · W6).
 *
 * 이 시험이 존재하는 이유: **계약만 있고 배선이 없는 코드**는 다음 회차에서 «있는 줄 알고»
 * 다시 만들어진다. 배선(티켓 Grid·상세 머리)은 티켓 도메인 회차의 몫이라, 여기서는 상태
 * 기계 전부를 렌더로 고정해 둔다 — 배선하는 사람이 무엇을 얻는지 이 파일이 답한다.
 *
 * C8 이 「전부 구현해야 완료」라고 적은 것 아홉을 그대로 훑는다:
 *   현재 값 · 권한 확인 · 변경 가능한 값 제시 · 선택 · Saving(중복 차단) · 성공 ·
 *   실패 · 실패 시 Rollback · 재조회로 실제 값 반영
 */

import { InlineEdit, canStartSave, inlineEditNext } from "./InlineEdit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

const OPTIONS = [
  { value: "계획", label: "계획" },
  { value: "진행", label: "진행" },
  { value: "완료", label: "완료" },
];

function draw(props) {
  return render(
    <ThemeModeProvider>
      <InlineEdit label="상태" rowName="업무 01" options={OPTIONS} canEdit {...props} />
    </ThemeModeProvider>,
  );
}

describe("상태 전이 — 순수 함수", () => {
  it("권한이 없으면 열리지 않는다", () => {
    expect(inlineEditNext("locked", "open")).toBe("locked");
  });

  it("저장 중에는 열리지도 닫히지도 않는다", () => {
    expect(inlineEditNext("saving", "open")).toBe("saving");
    expect(inlineEditNext("saving", "cancel")).toBe("saving");
  });

  it("🔴 저장 중의 선택은 새 저장을 띄우지 않는다", () => {
    expect(canStartSave("saving")).toBe(false);
    expect(canStartSave("open")).toBe(true);
  });

  it("성공·실패는 저장 중에서만 나온다", () => {
    expect(inlineEditNext("saving", "ok")).toBe("done");
    expect(inlineEditNext("saving", "fail")).toBe("error");
    expect(inlineEditNext("read", "ok")).toBe("read");
  });
});

describe("아홉 가지 상태가 화면에 실재한다", () => {
  it("① 평상시엔 값 그대로 읽힌다 — 컨트롤이 아니다", () => {
    draw({ value: "진행", onSave: vi.fn() });
    // 값이 그대로 보이고, 「바꿀 수 있다」는 것은 이름으로만 드러난다(select 상자가 아니다).
    expect(screen.getByText("진행")).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: "업무 01 상태 바꾸기" })).toBeTruthy();
  });

  it("② 권한이 없으면 **편집 진입 자체가 없다**", () => {
    draw({ value: "진행", canEdit: false, onSave: vi.fn(), deniedReason: "담당자만 바꿀 수 있습니다." });
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("진행").getAttribute("data-inline-edit")).toBe("locked");
  });

  it("③④ 열면 바꿀 수 있는 값이 나오고 고를 수 있다", async () => {
    const onSave = vi.fn().mockResolvedValue("완료");
    draw({ value: "진행", onSave });
    await userEvent.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    expect(screen.getByRole("listbox")).toBeTruthy();
    await userEvent.click(screen.getByRole("option", { name: "완료" }));
    expect(onSave).toHaveBeenCalledWith("완료");
  });

  it("⑤ 🔴 저장 중에는 같은 저장을 두 번 보내지 않는다", async () => {
    let release;
    const onSave = vi.fn(() => new Promise((r) => { release = r; }));
    draw({ value: "진행", onSave });
    await userEvent.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    await userEvent.click(screen.getByRole("option", { name: "완료" }));
    const trigger = screen.getByRole("button", { name: /상태 바꾸기/ });
    expect(trigger.getAttribute("data-inline-edit")).toBe("saving");
    expect(trigger).toBeDisabled();
    // 저장 중에 다시 눌러도 목록이 열리지 않고, 저장은 한 번뿐이다.
    await userEvent.click(trigger);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onSave).toHaveBeenCalledTimes(1);
    release("완료");
    await waitFor(() => expect(screen.getByText("완료")).toBeTruthy());
  });

  it("⑥⑨ 🔴 성공은 «서버가 돌려준 값»으로 그린다 — 넘긴 값이 아니다", async () => {
    // 상태를 '완료'로 옮겼는데 서버가 워크플로 규칙으로 '검증'에 두는 경우가 실재한다.
    const onSave = vi.fn().mockResolvedValue("검증");
    draw({ value: "진행", onSave });
    await userEvent.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    await userEvent.click(screen.getByRole("option", { name: "완료" }));
    await waitFor(() => expect(screen.getByText("검증")).toBeTruthy());
    expect(screen.queryByText("완료")).toBeNull();
  });

  it("⑦⑧ 🔴 실패하면 **이전 값으로 되돌아가고** 사유가 값 옆에 남는다", async () => {
    const onSave = vi.fn().mockRejectedValue(Object.assign(new Error("x"), { userMessage: "권한이 없습니다." }));
    draw({ value: "진행", onSave });
    await userEvent.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    await userEvent.click(screen.getByRole("option", { name: "완료" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("권한이 없습니다."));
    expect(screen.getByText("진행")).toBeTruthy();       // 롤백
    expect(screen.queryByText("완료")).toBeNull();
  });

  it("바깥에서 값이 바뀌면(목록 재조회) 그 값이 정본이다", async () => {
    const { rerender } = draw({ value: "진행", onSave: vi.fn() });
    rerender(
      <ThemeModeProvider>
        <InlineEdit label="상태" rowName="업무 01" options={OPTIONS} canEdit value="완료" onSave={vi.fn()} />
      </ThemeModeProvider>,
    );
    await waitFor(() => expect(screen.getByText("완료")).toBeTruthy());
  });

  it("바꿀 값이 하나도 없으면 열리지 않는다", () => {
    draw({ value: "진행", options: [], onSave: vi.fn() });
    expect(screen.getByRole("button", { name: /상태 바꾸기/ })).toBeDisabled();
  });
});
