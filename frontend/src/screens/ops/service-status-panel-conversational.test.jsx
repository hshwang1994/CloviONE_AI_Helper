import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { ServiceStatusPanel } from "./ServiceStatusPanel.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";
import { ToastProvider } from "../../ui/kit.jsx";

/* D-118 — worker_conversational은 배치 워커와 또 다른 세 번째 systemd 유닛
 * (clovirone-web-worker-conversational.service)이다. 예전 이분법(web이 아니면
 * 무조건 clovirone-web-worker)을 그대로 두면, 대화형 레인이 죽었을 때도 배치 워커
 * 로그를 보라고 안내해 실제 장애 유닛과 다른 곳을 가리킨다 — 이 컴포넌트 자신의
 * 존재 이유("web만 죽었는데 워커 로그를 보라고 하면 엉뚱한 곳을 가리킨다")와
 * 정확히 같은 결함이 새 컴포넌트에도 재발하는 것을 막는다. */

function renderPanel(comps, nav = vi.fn()) {
  return {
    nav,
    ...render(
      <ThemeModeProvider>
        <ToastProvider>
          <ServiceStatusPanel disk={{}} mem={{}} certDaysRemaining={null} comps={comps} nav={nav} />
        </ToastProvider>
      </ThemeModeProvider>,
    ),
  };
}

describe("ServiceStatusPanel — worker_conversational 유닛 안내 (D-118)", () => {
  it("대화형 레인만 죽었을 때 journalctl 안내가 배치 워커가 아니라 대화형 유닛을 가리킨다", () => {
    renderPanel({ web: "up", worker: "up", scheduler: "up", worker_conversational: "down" });
    expect(screen.getByText(/clovirone-web-worker-conversational/)).toBeInTheDocument();
    expect(screen.queryByText(/journalctl -u clovirone-web-worker(?!-conversational)/)).toBeNull();
  });

  it("배치 워커만 죽었을 때는 여전히 배치 유닛을 가리킨다(회귀 방지)", () => {
    renderPanel({ web: "up", worker: "down", scheduler: "up" });
    expect(screen.getByText(/journalctl -u clovirone-web-worker\b/)).toBeInTheDocument();
  });

  it("대화형 레인 타일을 누르면 작업 큐(/jobs)로 이동한다(다른 레인 카드와 같은 동작)", async () => {
    const user = userEvent.setup();
    const nav = vi.fn();
    renderPanel({ web: "up", worker: "up", scheduler: "up", worker_conversational: "down" }, nav);
    await user.click(screen.getByRole("button", { name: /대화형 워커/ }));
    expect(nav).toHaveBeenCalledWith("/jobs");
  });

  it("대화형 레인을 켠 적 없는 설치(comps에 키 자체가 없음)에서는 타일이 안 보인다", () => {
    renderPanel({ web: "up", worker: "up", scheduler: "up" });
    expect(screen.queryByText("대화형 워커")).toBeNull();
  });
});
