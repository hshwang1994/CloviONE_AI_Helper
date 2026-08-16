import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { ToastProvider, useToast } from "./kit.jsx";

/* 토스트는 한 번만 낭독된다 (접근성 감사 4).
 *
 * 감사가 본 상태: aria-live 영역 **안에** role="alert" 가 들어 있어 같은 문장을 두 번 읽었다.
 * (MUI Alert 의 role 기본값이 'alert' 라 role={undefined} 로는 지워지지 않는다.)
 *
 * 낭독 담당은 바깥 라이브 영역 하나다. 정보·성공은 polite(읽던 것을 자르지 않는다),
 * 오류는 assertive - 오류만은 지금 하던 낭독을 끊고 알려야 한다.
 */

function Fire({ message, kind }) {
  const toast = useToast();
  return <button type="button" onClick={() => toast(message, kind)}>알림 띄우기</button>;
}

function liveRegionFor(node) {
  return node.closest("[aria-live]");
}

describe("토스트 낭독", () => {
  it("라이브 영역 안에 또 다른 alert 를 두지 않는다", async () => {
    render(<ToastProvider><Fire message="본문을 저장했습니다." kind="success" /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "알림 띄우기" }));
    const text = await screen.findByText("본문을 저장했습니다.");
    expect(liveRegionFor(text)).not.toBeNull();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
  });

  it("메시지는 라이브 영역에 한 번만 있다", async () => {
    render(<ToastProvider><Fire message="본문을 저장했습니다." kind="success" /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "알림 띄우기" }));
    await screen.findByText("본문을 저장했습니다.");
    expect(screen.getAllByText("본문을 저장했습니다.")).toHaveLength(1);
  });

  it("정보·성공은 polite, 오류는 assertive 로 낭독한다", async () => {
    const { unmount } = render(
      <ToastProvider><Fire message="저장했습니다." kind="success" /></ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "알림 띄우기" }));
    const ok = await screen.findByText("저장했습니다.");
    expect(liveRegionFor(ok)).toHaveAttribute("aria-live", "polite");
    unmount();

    render(<ToastProvider><Fire message="저장하지 못했습니다." kind="error" /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "알림 띄우기" }));
    const bad = await screen.findByText("저장하지 못했습니다.");
    expect(liveRegionFor(bad)).toHaveAttribute("aria-live", "assertive");
  });

  it("라이브 영역은 토스트가 없을 때에도 떠 있다", () => {
    // 내용과 영역이 같은 순간에 생기면 낭독을 놓치는 스크린리더가 있다.
    const { container } = render(
      <ToastProvider><Fire message="저장했습니다." kind="success" /></ToastProvider>,
    );
    expect(document.querySelectorAll("[aria-live]").length).toBeGreaterThan(0);
    expect(container).toBeTruthy();
  });

  // PA-RC-0025 — DataScreen.jsx/SubListDrawer.jsx의 기본 성공 토스트가 "라벨 완료"(명사형,
  // 마침표 없음)에서 사전 기반 문장형("삭제했습니다." 등)으로 바뀌었다. 문구를 바꾸면서
  // 이 파일이 위에서 이미 못박은 낭독 메커니즘(라이브 영역 하나, alert 중복 없음, 한 번만
  // 낭독)까지 함께 잃지 않았는지 그 새 문구로 직접 확인한다.
  it("PA-RC-0025 사전이 낸 문장형 문구('삭제했습니다.')도 같은 낭독 규약을 그대로 지킨다", async () => {
    render(<ToastProvider><Fire message="삭제했습니다." kind="success" /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "알림 띄우기" }));
    const text = await screen.findByText("삭제했습니다.");

    // 라이브 영역 안에 있고(낭독됨), 중복 alert가 없고(한 번만 낭독), success이므로 polite다
    // (오류가 아니므로 지금 하던 낭독을 끊지 않는다) — 위 세 시험과 동일한 세 가지 불변식.
    expect(liveRegionFor(text)).not.toBeNull();
    expect(liveRegionFor(text)).toHaveAttribute("aria-live", "polite");
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    expect(screen.getAllByText("삭제했습니다.")).toHaveLength(1);
  });
});
