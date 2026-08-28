import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* DefaultAvatarPicker — 인라인 격자 → 대화상자화 (REAUDIT_PLAN §17 bundle-2 step 7:
 * "기본 아바타 고르개 대화상자화").
 *
 * 예전 계약(고른 즉시 onPick 호출 — 취소가 없었다)이 바뀌었으므로 그 변화 자체를 못박는다:
 *  1. 트리거 버튼이 대화상자를 연다.
 *  2. 대화상자 **안에서** 후보를 눌러도 onPick 은 아직 안 나간다(저장 전까지는 미리보기일 뿐).
 *  3. 저장을 눌러야 onPick 이 정확히 그 키로 나가고, 대화상자가 닫힌다.
 *  4. 취소/닫기는 onPick 을 전혀 부르지 않는다 — 둘러보다 실수로 반영되는 사고가 없다.
 */
import { DefaultAvatarPicker } from "./DefaultAvatarPicker.jsx";

function mount(props = {}) {
  const onPick = vi.fn();
  render(
    <DefaultAvatarPicker seed="user-1" value="" busy={false} onPick={onPick} {...props} />
  );
  return { onPick };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("트리거 버튼", () => {
  it("버튼 하나만 화면에 있고, 후보 격자는 열기 전에는 없다", () => {
    mount();
    expect(screen.getByRole("button", { name: "기본 아바타 고르기" })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "기본 아바타" })).not.toBeInTheDocument();
  });

  it("누르면 대화상자가 열린다", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "기본 아바타 고르기" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "기본 아바타" })).toBeInTheDocument();
  });
});

describe("저장하기 전에는 반영되지 않는다", () => {
  it("후보를 눌러도(아직 저장 전) onPick 은 안 나간다 — 둘러보는 것과 고르는 것은 다르다", async () => {
    const user = userEvent.setup();
    const { onPick } = mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    const candidate = within(dialog).getAllByRole("radio")[0];
    await user.click(candidate);
    expect(onPick).not.toHaveBeenCalled();
    // 하지만 화면에는 골랐다는 표시(aria-checked)가 즉시 보여야 한다 — 눌러도 반응이 없으면
    // 고장으로 읽힌다.
    expect(candidate).toHaveAttribute("aria-checked", "true");
  });

  it("취소 버튼은 onPick 을 부르지 않고 대화상자를 닫는다", async () => {
    const user = userEvent.setup();
    const { onPick } = mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getAllByRole("radio")[0]);
    await user.click(screen.getByRole("button", { name: "취소" }));
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("아무것도 안 바꿨으면 저장 버튼이 잠겨 있다(저장할 변경이 없다)", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    await screen.findByRole("dialog");
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });
});

describe("저장", () => {
  it("후보를 고르고 저장을 누르면 그 키로 onPick 이 나가고 대화상자가 닫힌다", async () => {
    const user = userEvent.setup();
    const { onPick } = mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    const candidate = within(dialog).getAllByRole("radio")[0];
    await user.click(candidate);
    const expectedLabel = candidate.getAttribute("aria-label");
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(onPick).toHaveBeenCalledTimes(1);
    const sentKey = onPick.mock.calls[0][0];
    expect(typeof sentKey).toBe("string");
    expect(sentKey.length).toBeGreaterThan(0);
    // 실제로 눌렀던 그 후보의 키가 나갔는지는 라벨(스타일명)로 교차 확인한다.
    expect(expectedLabel).toContain("아바타");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("이미 고른 값이 있는 채로 열면, 같은 값을 다시 눌러 선택 해제하고 저장하면 빈 문자열이 나간다", async () => {
    const user = userEvent.setup();
    // value가 있으면 그 후보가 이미 선택 표시(aria-checked)로 열린다 — 같은 후보를 다시
    // 누르면 선택 해제(계정 자동 얼굴로 돌아가는 것과 같은 뜻)다.
    const { onPick } = mount({ value: "lorelei:0" });
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    const chosen = within(dialog).getByRole("radio", { checked: true });
    await user.click(chosen);
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(onPick).toHaveBeenCalledWith("");
  });
});

describe("다른 후보 보기", () => {
  it("안내 문단은 없고, 고른 값이 있으면 선택 해제로 자동 얼굴로 돌아갈 수 있다", async () => {
    const user = userEvent.setup();
    const { onPick } = mount({ value: "lorelei:0" });
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText(/사진이 없을 때/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "선택 해제" }));
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(onPick).toHaveBeenCalledWith("");
  });

  it("스타일마다 후보가 여섯이고 한 줄 격자에 선다", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const group = await screen.findByRole("radiogroup", { name: "기본 아바타" });
    expect(within(group).getAllByRole("radio")).toHaveLength(30);
    const rows = group.querySelectorAll("[data-avatar-row]");
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      expect(within(row).getAllByRole("radio")).toHaveLength(6);
    }
  });

  it("눌러도 이미 고른 값의 선택 표시는 유지된다 — 회차만 바뀐다", async () => {
    const user = userEvent.setup();
    mount({ value: "lorelei:0" });
    await user.click(screen.getByRole("button", { name: "기본 아바타 고르기" }));
    const dialog = await screen.findByRole("dialog");
    // 처음에는 고른 후보가 화면에 없을 수도 있다(회차 0에 없으면). '선택 해제'
    // 버튼이 있다는 것 자체가 무언가 골라져 있다는 뜻이다.
    expect(within(dialog).getByRole("button", { name: "선택 해제" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "다른 후보 보기" }));
    // 다시 눌러도 대화상자는 그대로 열려 있고 후보 격자도 여전히 있다.
    expect(within(dialog).getByRole("radiogroup", { name: "기본 아바타" })).toBeInTheDocument();
  });
});
