import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MetaBar } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 상세 상단 속성이 **위계**를 갖는가 (R-90 · R-75 · 지시 75).
 *
 * S16 이 칸의 폭을 고쳤다. 남은 문제는 **무게**다: 아홉 개 속성이 전부 같은 강도로 한 줄에
 * 늘어서면, 티켓을 열었을 때 먼저 봐야 하는 「상태·담당자·마감」과 지원 문의 때나 부르는
 * 「티켓 번호」가 구별되지 않는다. 4K 에서 그 줄은 2,880px 이고, 원하는 값을 찾으려면
 * 아홉 칸을 다 훑어야 한다.
 *
 * 이 시험이 지키는 것은 셋이다 — 선언이 없으면 안 바뀐다 · 선언하면 두 층이 된다 ·
 * 두 층의 순서가 «먼저 판단할 것» 부터다.
 */

const LONG = "ClovirAssist 플랫폼 전환 및 자체 데이터 이관 프로젝트";

function renderBar(items) {
  return render(
    <ThemeModeProvider><MetaBar ariaLabel="속성" items={items} /></ThemeModeProvider>,
  );
}

describe("상세 속성의 위계", () => {
  it("rank 를 아무도 선언 안 하면 예전 그대로 한 줄이다", () => {
    const { container } = renderBar([
      { key: "a", label: "상태", type: "status", value: "진행" },
      { key: "b", label: "프로젝트", type: "name", value: LONG },
    ]);
    expect(container.querySelector('[data-meta-ranked="true"]')).toBeNull();
    expect(container.querySelectorAll('[data-meta-rank]').length).toBe(0);
    expect(container.querySelectorAll(".k-metacell").length).toBe(2);
  });

  it("전부 primary 여도 한 줄이다 — 위계가 없는 것을 있는 척하지 않는다", () => {
    const { container } = renderBar([
      { key: "a", label: "상태", rank: "primary", value: "진행" },
      { key: "b", label: "담당자", rank: "primary", value: "황형섭" },
    ]);
    expect(container.querySelector('[data-meta-ranked="true"]')).toBeNull();
  });

  it("선언하면 두 층이 되고 «먼저 판단할 것» 이 위다", () => {
    const { container } = renderBar([
      { key: "tid", label: "티켓 번호", type: "identifier", value: "CLV-142" },
      { key: "status", label: "상태", type: "status", rank: "primary", value: "진행" },
      { key: "due", label: "마감", type: "date", rank: "primary", value: "2026-09-01" },
      { key: "est", label: "예상 WD", type: "number", value: 3 },
    ]);
    expect(container.querySelector('[data-meta-ranked="true"]')).not.toBeNull();

    const cells = [...container.querySelectorAll("[data-meta-rank]")];
    expect(cells.map((c) => c.getAttribute("data-meta-rank")))
      .toEqual(["primary", "primary", "secondary", "secondary"]);
    // DOM 순서가 곧 읽는 순서다 — 낭독과 키보드 이동도 같은 순서를 따른다.
    expect(cells[0].textContent).toContain("상태");
    expect(cells[2].textContent).toContain("티켓 번호");
  });

  it("보조 줄은 라벨과 값이 한 줄에 붙는다 — 상자를 만들지 않는다", () => {
    const { container } = renderBar([
      { key: "status", label: "상태", rank: "primary", value: "진행" },
      { key: "tid", label: "티켓 번호", value: "CLV-142" },
    ]);
    const secondary = container.querySelector('[data-meta-rank="secondary"]');
    expect(getComputedStyle(secondary).display).toBe("flex");
    // 판(테두리 있는 컨테이너)을 만들면 «무엇이 위인가» 가 다시 흐려진다.
    for (const el of container.querySelectorAll(".k-metacell")) {
      expect(getComputedStyle(el).borderTopStyle || "none").not.toBe("solid");
    }
  });

  it("긴 값이 있어도 칸이 화면 폭을 다 먹지 않는다", () => {
    const { container } = renderBar([
      { key: "project", label: "프로젝트", type: "name", rank: "primary", value: LONG },
      { key: "tid", label: "티켓 번호", type: "identifier", value: "CLV-142" },
    ]);
    const cell = container.querySelector('[data-meta-rank="primary"]');
    expect(getComputedStyle(cell).maxWidth).toBe("20rem");
    // 그리고 잘리지 않는다 — 한글은 어절 단위로 접힌다(root.css 의 keep-all).
    expect(screen.getByText(LONG)).toBeInTheDocument();
    expect(getComputedStyle(cell).overflow || "visible").not.toBe("hidden");
  });

  it("값이 비면 칸을 지우지 않고 `-` 를 적는다 — 자리가 사라지면 «모른다» 가 된다", () => {
    renderBar([
      { key: "status", label: "상태", rank: "primary", value: "진행" },
      { key: "due", label: "마감", value: null },
    ]);
    expect(screen.getByText("-")).toBeInTheDocument();
  });
});
