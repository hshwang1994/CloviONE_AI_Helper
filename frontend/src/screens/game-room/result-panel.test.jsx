import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";
import { ToastProvider } from "../../ui/kit.jsx";
import { ANNOUNCE_MS, ResultPanel } from "./ResultPanel.jsx";

/* 공통 결과 틀 (D-563) — 발표 전환 · 공개 순간의 `onReveal` 한 번 · 늦은 입장은 전환 없음 · 승자 없는 결과 · 당첨자 모양. */

function wrap(ui) {
  return render(<ThemeModeProvider><ToastProvider>{ui}</ToastProvider></ThemeModeProvider>);
}

const ONE = [{ id: "u2", name: "박개발", user_id: "u2" }];
const MANY = [{ id: "a", name: "가" }, { id: "b", name: "나" }, { id: "c", name: "다" }];

afterEach(() => { vi.useRealTimers(); });

describe("발표 전환과 onReveal", () => {
  it("새 열쇠는 「결과를 발표합니다」 뒤에 당첨자를 공개하고 그 순간 onReveal 을 한 번 부른다", () => {
    vi.useFakeTimers();
    const onReveal = vi.fn();
    const { rerender } = wrap(<ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" winners={ONE} revealKey="r1:5" onReveal={onReveal} />);
    expect(screen.getByText(/결과를 발표합니다/)).toBeInTheDocument();
    expect(screen.queryByText("박개발")).toBeNull();
    expect(onReveal).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS + 10); });
    expect(screen.getByText("박개발")).toBeInTheDocument();
    expect(screen.getByText("당첨")).toBeInTheDocument();
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(onReveal).toHaveBeenCalledWith("r1:5");
    // 같은 열쇠로 다시 그려도(폴링 · 창 크기 · 테마) 다시 돌지 않는다.
    rerender(<ThemeModeProvider><ToastProvider><ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" winners={ONE} revealKey="r1:5" onReveal={onReveal} /></ToastProvider></ThemeModeProvider>);
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS * 2); });
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-result-panel="revealed"]')).not.toBeNull();
    // 다음 결과(새 열쇠)에서는 다시 발표한다.
    rerender(<ThemeModeProvider><ToastProvider><ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" winners={ONE} revealKey="r1:9" onReveal={onReveal} /></ToastProvider></ThemeModeProvider>);
    expect(screen.getByText(/결과를 발표합니다/)).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS + 10); });
    expect(onReveal).toHaveBeenCalledTimes(2);
    expect(onReveal).toHaveBeenLastCalledWith("r1:9");
  });

  it("처음 본 열쇠(instant)는 전환 없이 바로 결과이고 onReveal 을 부르지 않는다 — 늦은 입장 · 새로고침", () => {
    vi.useFakeTimers();
    const onReveal = vi.fn();
    wrap(<ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" winners={ONE} revealKey="r1:5" instant onReveal={onReveal} />);
    expect(screen.queryByText(/결과를 발표합니다/)).toBeNull();
    expect(screen.getByText("박개발")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS * 2); });
    expect(onReveal).not.toHaveBeenCalled();
  });

  it("onReveal 이 던져도 결과는 그대로 보인다 — 축포는 표현이다", () => {
    vi.useFakeTimers();
    const onReveal = vi.fn(() => { throw new Error("confetti broke"); });
    wrap(<ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" winners={ONE} revealKey="r1:5" onReveal={onReveal} />);
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS + 10); });
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(screen.getByText("박개발")).toBeInTheDocument();
  });
});

describe("당첨자 모양", () => {
  it("승자가 없는 결과(calm)는 당첨자 자리 없이 게임별 결과만 — 1 · 2 · 3등을 만들지 않는다", () => {
    wrap(<ResultPanel game="랜덤 팀 나누기" headline="팀을 나눴습니다" mood="calm" revealKey="r1:3" instant detail={<div>1팀: 가, 나</div>} detailDefaultOpen />);
    expect(document.querySelector('[data-result-mood="calm"]')).not.toBeNull();
    expect(document.querySelector("[data-result-winners]")).toBeNull();
    expect(screen.queryByText("당첨")).toBeNull();
    expect(screen.getByText("1팀: 가, 나")).toBeInTheDocument();
  });

  it("여럿이면 같은 무게의 격자이고 전부 보인다, 순위가 있으면 1등부터 번호가 붙는다", () => {
    const { unmount } = wrap(<ResultPanel game="랜덤 추첨" headline="당첨자" winners={MANY} revealKey="r1:3" instant />);
    expect(document.querySelector('[data-result-winners="grid"]')).not.toBeNull();
    for (const w of MANY) expect(screen.getByTitle(w.name)).toBeInTheDocument();
    unmount();
    wrap(<ResultPanel game="구슬 레이스" headline="당첨자" winners={MANY} ranked revealKey="r1:3" instant />);
    expect(document.querySelector('[data-result-winners="ranked"]')).not.toBeNull();
    expect(screen.getByLabelText("1등")).toBeInTheDocument();
    expect(screen.getByLabelText("3등")).toBeInTheDocument();
  });

  it("전체 결과는 접혀 있다가 단추로 펼친다", () => {
    wrap(<ResultPanel game="실시간 퀴즈" headline="우승자" winners={ONE} revealKey="r1:3" instant detail={<div>점수표</div>} detailLabel="최종 순위" />);
    expect(document.querySelector('[data-result-detail="closed"]')).not.toBeNull();
    act(() => { screen.getByRole("button", { name: "최종 순위 보기" }).click(); });
    expect(document.querySelector('[data-result-detail="open"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "최종 순위 접기" })).toBeInTheDocument();
  });
});
