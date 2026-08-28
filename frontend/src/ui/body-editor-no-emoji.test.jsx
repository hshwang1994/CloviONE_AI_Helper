/* qa-contract-change: 본문 편집기의 이모지 계약이 「버튼을 아예 두지 않는다」에서 「툴바에 글자를 박지 않되 눌러서 여는 고르개를 준다」로 바뀌었다. 지시 28 이 걷은 것은 여덟 개를 툴바에 박아 놓고 권하던 자리이고 그 판단은 그대로 남는다. 서식 도구가 넷에서 아홉으로 늘어난 만큼 단언도 늘었다.
 *
 * 바꾼 단언은 하나다: 「이모지를 넣을 길이 아예 없다」 → 「고르개로 연다」. 「툴바 글자에
 * 이모지가 없다」는 그대로 남고, 새 도구 다섯(체크·인용·코드·링크·이모지)의 단언이 붙었다.
 *
 * 본문 편집기의 이모지 — **툴바가 권하지 않고, 필요한 사람이 연다.**
 *
 * 예전에는 서식 도구 옆에 ✅📌⚠️🔹👉🎯🎉💡 여덟 개가 나란히 있었다. 그 자리는 화면이
 * 장식 문자를 **스스로 권하는** 자리였다 — 없애는 것으로 끝나지 않고 넣으라고 버튼까지 줬다.
 * 지금은 툴바의 기본 얼굴에 글자 한 자도 없고, 고르개는 눌러야 열린다.
 *
 * 본문에 이모지를 못 쓰게 막지는 않는다. 사용자가 직접 치면 그대로 저장된다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { BodyEditor } from "./BodyEditor.jsx";

describe("본문 편집기 — 이모지를 툴바에 박지 않는다", () => {
  it("🔴 서식 도구의 글자에 이모지가 한 자도 없다", () => {
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    const toolbar = screen.getByRole("group", { name: /서식/ });
    for (const glyph of ["✅", "📌", "⚠️", "🔹", "👉", "🎯", "🎉", "💡"]) {
      expect(toolbar.textContent, `이모지 버튼이 남아 있다: ${glyph}`).not.toContain(glyph);
    }
    // 예전 버튼들의 접근 이름도 그대로 없다(숨겨 두고 남기지 않았다는 확인).
    expect(screen.queryByRole("button", { name: /표시 넣기$/ })).toBeNull();
  });

  it("필요한 사람은 눌러서 고른다 — 고르개가 열리고 이름표는 표준 명칭이다", async () => {
    const user = userEvent.setup();
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    const open = screen.getByRole("button", { name: "이모지" });
    expect(open).toHaveAttribute("aria-expanded", "false");
    await user.click(open);
    // 이모지 글자를 이름으로 두면 플랫폼·폰트에 따라 스크린리더가 아무것도 못 읽는다(VIS-86).
    expect(await screen.findByRole("button", { name: "엄지척" })).toBeInTheDocument();
  });

  it("고른 이모지가 본문에 들어간다", async () => {
    const user = userEvent.setup();
    let value = "회의 결과 ";
    const onChange = (next) => { value = next; };
    render(<BodyEditor id="b1" value={value} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "이모지" }));
    await user.click(await screen.findByRole("button", { name: "엄지척" }));
    expect(value).toContain("👍");
  });
});

describe("글의 구조를 만드는 도구", () => {
  it("🔴 렌더러가 실제로 그리는 열하나가 전부 있다", () => {
    /* 숫자를 늘리려고 렌더러가 모르는 버튼을 넣지 않는다(지시 10). 열하나 다
       `app/core/notion_blocks.py` 가 블록으로 만들고 `ui/DocBody.jsx` 가 그린다. 제목이
       셋인 이유는 REAUDIT §15.4 — `markdown_to_blocks` 는 처음부터 `#`·`##`·`###` 를 다
       읽고 있었는데 도구는 `##` 하나만 줬었다(문서 편집기 `BlockEditor.jsx` 와 기능 집합을
       맞추며 나머지 둘을 채웠다). */
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    for (const name of ["제목1", "제목2", "제목3", "글머리", "번호", "체크", "인용", "코드", "구분선", "링크", "이모지"]) {
      expect(screen.getByRole("button", { name }), `${name} 도구가 없다`).toBeInTheDocument();
    }
  });

  it("제목 도구 셋이 각자 다른 수준을 넣는다 — 하나가 다른 것의 별명이 아니다", async () => {
    const user = userEvent.setup();
    let value = "";
    const onChange = (next) => { value = next; };
    const { rerender } = render(<BodyEditor id="b1" value={value} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "제목1" }));
    expect(value).toBe("# ");

    value = "";
    rerender(<BodyEditor id="b1" value={value} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "제목2" }));
    expect(value).toBe("## ");

    value = "";
    rerender(<BodyEditor id="b1" value={value} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "제목3" }));
    expect(value).toBe("### ");
  });

  it("체크 도구가 넣는 것은 **체크 목록 표식**이다 — 그냥 글머리가 아니다", async () => {
    const user = userEvent.setup();
    let value = "";
    render(<BodyEditor id="b1" value={value} onChange={(next) => { value = next; }} />);
    await user.click(screen.getByRole("button", { name: "체크" }));
    expect(value).toBe("- [ ] ");
  });

  it("코드 도구는 **여는 줄과 닫는 줄을 함께** 넣는다", async () => {
    const user = userEvent.setup();
    let value = "";
    render(<BodyEditor id="b1" value={value} onChange={(next) => { value = next; }} />);
    await user.click(screen.getByRole("button", { name: "코드" }));
    // 한 줄만 넣으면 사용자가 닫는 울타리를 직접 쳐야 하고, 안 치면 아래 본문 전체가 코드가 된다.
    expect(value.match(/```/g)).toHaveLength(2);
  });

  it("사용자가 직접 친 이모지는 그대로 남는다 — 막는 것이 아니라 권하지 않는 것이다", () => {
    render(<BodyEditor id="b1" value="회의 결과 ✅ 완료" onChange={() => {}} />);
    expect(screen.getByDisplayValue("회의 결과 ✅ 완료")).toBeInTheDocument();
  });
});
