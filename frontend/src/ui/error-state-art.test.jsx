import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ErrorState } from "./kit.jsx";
import { ART } from "../lib/assets.js";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 「500」 팻말 그림은 서버가 정말 5xx 를 냈을 때만 선다 (더블클릭 조사, 2026-09-21).
 *
 * 사용자는 「같은 메뉴를 빠르게 두 번 누르면 500 오류 화면이 뜬다」고 했는데 서버 로그 14일치에
 * 그 경로의 5xx 는 한 건도 없었다. 화면의 「500」은 `ErrorState` 의 그림이었다 — 401 · 403 · 404 ·
 * 연결 끊김이 아닌 실패가 **전부** 이 그림이라, 화면 코드의 예외 · 요청 제한(429) · 프록시의 이상한
 * 응답까지 「서버 오류 500」으로 보였다. 그림이 거짓말을 하면 사용자는 고장 난 곳을 잘못 짚는다.
 */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

function artOf(container) {
  const img = container.querySelector("img");
  return img ? img.getAttribute("src") : null;
}

describe("오류 그림은 실패의 종류를 말한다", () => {
  it.each([500, 502, 503])("서버가 %s 을 냈을 때만 「500」 그림이다", (status) => {
    const { container } = ui(<ErrorState error={{ status, message: "서버에서 문제가 생겼습니다." }} onRetry={() => {}} />);
    expect(artOf(container)).toBe(ART.serverError);
  });

  it("요청 제한(429)은 「500」이 아니라 기다리는 그림이다", () => {
    const { container } = ui(<ErrorState error={{ status: 429, message: "요청이 너무 잦습니다." }} onRetry={() => {}} />);
    expect(artOf(container)).toBe(ART.wait);
    expect(artOf(container)).not.toBe(ART.serverError);
  });

  it("상태 코드가 없는 실패 · 이상한 응답은 「500」이 아니다", () => {
    const unknown = ui(<ErrorState error={{ message: "문제가 발생했습니다." }} onRetry={() => {}} />);
    expect(artOf(unknown.container)).toBe(ART.trouble);
    unknown.unmount();
    const invalid = ui(<ErrorState error={{ status: 200, kind: "invalid_response", message: "서버 응답을 해석하지 못했습니다." }} onRetry={() => {}} />);
    expect(artOf(invalid.container)).toBe(ART.trouble);
  });

  it("그 밖의 상태는 제 그림을 그대로 쓴다(404 · 403 · 연결 끊김)", () => {
    const gone = ui(<ErrorState error={{ status: 404 }} />);
    expect(artOf(gone.container)).toBe(ART.notFound);
    gone.unmount();
    const forbidden = ui(<ErrorState error={{ status: 403 }} />);
    expect(artOf(forbidden.container)).toBe(ART.noPermission);
    forbidden.unmount();
    const offline = ui(<ErrorState error={{ kind: "network", message: "서버에 연결할 수 없습니다." }} onRetry={() => {}} />);
    expect(artOf(offline.container)).toBe(ART.offline);
  });
});

describe("화면 실패 두 갈래 — 렌더 예외 · 새 버전 배포", () => {
  it("렌더 예외는 제 제목 · 다시 시도 · 보조 동작 · 옮겨 적을 기술 정보를 갖는다", () => {
    const retry = vi.fn();
    const { container } = ui(
      <ErrorState
        error={{ kind: "render", message: "다시 시도해도 같으면 새로고침해 주세요.", detail: "TypeError: x is undefined\n    at Board (WorkBoard.jsx:12)" }}
        onRetry={retry}
        secondaryAction={<button type="button">새로고침</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "화면을 표시하지 못했습니다" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "새로고침" })).toBeInTheDocument();
    const detail = container.querySelector("[data-error-detail]");
    expect(detail).not.toBeNull();
    expect(detail.textContent).toContain("WorkBoard.jsx:12");
    expect(artOf(container)).toBe(ART.trouble);
  });

  it("새 버전이 배포돼 화면 파일을 못 받은 것은 새로고침만 준다", () => {
    const reload = vi.fn();
    const { container } = ui(<ErrorState error={{ kind: "chunk", message: "x" }} onRetry={reload} />);
    expect(screen.getByRole("heading", { name: "새 버전이 배포됐습니다" })).toBeInTheDocument();
    expect(screen.getByText("새로고침하면 새 버전의 화면이 열립니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "새로고침" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
    expect(artOf(container)).not.toBe(ART.serverError);
  });
});
