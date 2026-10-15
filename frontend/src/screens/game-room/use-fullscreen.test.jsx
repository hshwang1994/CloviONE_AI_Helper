import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { useFullscreen } from "./useFullscreen.js";

/* 놀이방 전체 화면 (D-575) — 표준 API · 흉내(iPhone) · Esc · 정리.
 *
 * jsdom 에는 Fullscreen API 가 없다 — 표준 갈래는 요소의 `requestFullscreen` 과 문서의 `fullscreenElement` · `exitFullscreen` 을 흉내
 * 내 브라우저처럼 `fullscreenchange` 를 쏜다. 흉내 갈래는 API 가 없는 그대로를 잰다. */

function Harness({ resetKey = "a" }) {
  const ref = React.useRef(null);
  const fs = useFullscreen(ref, { resetKey });
  return (
    <div ref={ref} data-testid="root">
      <button type="button" onClick={fs.toggle}>{fs.active ? "전체 화면 종료" : "전체 화면"}</button>
      <span data-testid="state">{fs.active ? (fs.pseudo ? "pseudo" : "native") : "off"}</span>
    </div>
  );
}

function installNative() {
  let current = null;
  Object.defineProperty(document, "fullscreenElement", { configurable: true, get: () => current });
  const set = (el) => { current = el; document.dispatchEvent(new Event("fullscreenchange")); };
  HTMLElement.prototype.requestFullscreen = vi.fn(function request() { set(this); return Promise.resolve(); });
  document.exitFullscreen = vi.fn(() => { set(null); return Promise.resolve(); });
  return { browserExit: () => act(() => set(null)) };
}

afterEach(() => {
  delete HTMLElement.prototype.requestFullscreen;
  delete document.exitFullscreen;
  delete document.fullscreenElement;
  document.body.style.overflow = "";
});

describe("표준 API", () => {
  it("루트가 전체 화면 요소가 되고, 브라우저가 풀면(fullscreenchange) 따라 풀린다", async () => {
    const native = installNative();
    render(<Harness />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(HTMLElement.prototype.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(document.fullscreenElement).toBe(screen.getByTestId("root"));
    expect(screen.getByTestId("state")).toHaveTextContent("native");
    expect(screen.getByRole("button", { name: "전체 화면 종료" })).toBeInTheDocument();
    native.browserExit();
    expect(screen.getByTestId("state")).toHaveTextContent("off");
  });

  it("Esc 로 풀린다", async () => {
    installNative();
    render(<Harness />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    await act(async () => { fireEvent.keyDown(document, { key: "Escape" }); });
    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(screen.getByTestId("state")).toHaveTextContent("off");
  });

  it("화면을 떠나거나 방이 바뀌면 푼다", async () => {
    installNative();
    const { rerender, unmount } = render(<Harness resetKey="a" />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    rerender(<Harness resetKey="b" />);
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    unmount();
    expect(document.exitFullscreen).toHaveBeenCalledTimes(2);
  });
});

describe("흉내(API 없는 iPhone)", () => {
  it("API 가 없으면 흉내 모드 — 문서 굴림을 잠그고 Esc · 떠나기에 되돌린다", async () => {
    document.body.style.overflow = "scroll";
    const { unmount } = render(<Harness />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(screen.getByTestId("state")).toHaveTextContent("pseudo");
    expect(document.body.style.overflow).toBe("hidden");
    await act(async () => { fireEvent.keyDown(document, { key: "Escape" }); });
    expect(screen.getByTestId("state")).toHaveTextContent("off");
    expect(document.body.style.overflow).toBe("scroll");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("scroll");
  });

  it("브라우저가 거절하면 흉내로 내려간다", async () => {
    HTMLElement.prototype.requestFullscreen = vi.fn(() => Promise.reject(new Error("denied")));
    render(<Harness />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(screen.getByTestId("state")).toHaveTextContent("pseudo");
  });
});
