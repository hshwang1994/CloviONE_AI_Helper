import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { Disclosure } from "./Disclosure.jsx";
import { TechRows } from "./kit.jsx";
import { SettingRow, SettingRows } from "./adminKit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 접기 구획 · 기술 정보 줄 · 설정 줄 묶음 — 메일 · AI · 시스템 화면이 손으로 짜던 셋을 공통 부품으로 모은 계약.
 * 부품마다 「없던 때 무엇이 틀렸는가」를 단언한다. */

afterEach(cleanup);

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("Disclosure — 닫힌 구획 하나", () => {
  it("기본은 닫혀 있고 몸을 그리지 않는다 — 누르면 몸이 나오고 aria-controls 가 그 몸을 가리킨다", async () => {
    ui(<Disclosure title="문제 해결과 고급" summary="DNS · DKIM · SPF 진단">
      <input aria-label="안쪽 칸" />
    </Disclosure>);
    const toggle = screen.getByRole("button", { name: "문제 해결과 고급" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("안쪽 칸")).toBeNull();
    expect(screen.getByText("DNS · DKIM · SPF 진단")).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(toggle.getAttribute("aria-controls"));
    expect(panel).not.toBeNull();
    expect(panel).toContainElement(screen.getByLabelText("안쪽 칸"));
    await userEvent.click(toggle);
    expect(screen.queryByLabelText("안쪽 칸")).toBeNull();
  });

  it("단추의 접근 가능한 이름은 제목뿐이다 — 요약이 바뀌어도 같은 이름으로 찾는다", () => {
    ui(<Disclosure title="고급" summary="준비 13개 중 9개 통과">몸</Disclosure>);
    expect(screen.getByRole("button", { name: "고급" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /준비 13개/ })).toBeNull();
  });

  it("defaultOpen 은 열린 채 시작하고, 제어 모드는 onToggle 로 다음 값을 알린다", async () => {
    const onToggle = vi.fn();
    ui(<>
      <Disclosure id="adv" title="열림" defaultOpen>열린 몸</Disclosure>
      <Disclosure title="제어" open={false} onToggle={onToggle}>제어 몸</Disclosure>
    </>);
    expect(screen.getByText("열린 몸")).toBeInTheDocument();
    expect(document.getElementById("adv")).toContainElement(screen.getByText("열린 몸"));
    expect(screen.queryByText("제어 몸")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "제어" }));
    expect(onToggle).toHaveBeenCalledWith(true);
    // 제어 모드는 부모가 값을 바꾸기 전까지 닫혀 있다.
    expect(screen.queryByText("제어 몸")).toBeNull();
  });
});

describe("TechRows — 이름 · 값 두 열", () => {
  it("값이 빈 줄은 그리지 않고, 줄이 없으면 아무것도 그리지 않는다", () => {
    const { container } = ui(<TechRows rows={[["상태 코드", "ok"], ["실패 종류", null], { name: "연속 실패", value: "" }, ["프록시", false]]} />);
    expect(container.querySelectorAll("dt")).toHaveLength(1);
    expect(screen.getByText("상태 코드").tagName).toBe("DT");
    expect(screen.getByText("ok").tagName).toBe("DD");
    const empty = ui(<TechRows rows={[["a", null]]} />);
    expect(empty.container.querySelector("dl")).toBeNull();
  });

  it("라벨 폭은 자리마다 받는다(기본 10rem)", () => {
    const { container } = ui(<TechRows labelWidth="8rem" rows={[["메일 서버", "127.0.0.1:2525"]]} />);
    expect(container.querySelector("dl").style.gridTemplateColumns || getComputedStyle(container.querySelector("dl")).gridTemplateColumns).toContain("8rem");
  });
});

describe("SettingRows — 첫 줄의 위 선을 지운다", () => {
  it("그릇에 표지가 있고 안의 설정 줄들이 그대로 선다", () => {
    const { container } = ui(
      <SettingRows>
        <SettingRow compact label="AI 사용" description="끄면 답을 만들지 않습니다." />
        <SettingRow compact label="AI 도우미" description="끄면 대화 API 가 닫힙니다." />
      </SettingRows>,
    );
    expect(container.querySelector(".k-settingrows")).not.toBeNull();
    expect(container.querySelectorAll(".k-settingrow")).toHaveLength(2);
  });
});
