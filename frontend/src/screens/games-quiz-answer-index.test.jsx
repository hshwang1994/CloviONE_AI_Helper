import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 실시간 퀴즈 편집기(Games.jsx QuizEditor) — 정답은 보기 배열의 "인덱스"로 추적된다(보기에
 * 안정적 id가 없다 — Games.jsx의 `q.options.map((o, oi) => ...)` key가 배열 인덱스 oi 그 자체).
 * removeOpt가 보기를 지울 때 배열은 한 칸씩 당겨지는데, 정답 인덱스를 같이 당기지 않으면
 * "정답"이 가리키는 실제 내용이 방장 모르게 바뀐다.
 *
 * 재현: 방장이 보기 C(인덱스 2)를 정답으로 찍고, 그보다 앞의 보기 A(인덱스 0)를 지운다.
 * 배열은 [B, C, D] -> 인덱스는 [0, 1, 2]로 밀리는데, 정답 인덱스가 여전히 2를 가리키면
 * 서버는 D를 정답으로 채점한다 — 방장은 여전히 C가 정답이라고 믿는 채로 방을 만든다.
 * 아무 경고도 없다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Games } from "./Games.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function route(path) {
  if (path === "/api/games/rooms") return Promise.resolve({ items: [], game_ai_enabled: false });
  return Promise.resolve({});
}

function renderGames() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/games"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Games />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function openQuizEditor() {
  renderGames();
  await userEvent.click(await screen.findByRole("button", { name: "게임방 추가" }));
  await screen.findByRole("heading", { name: "게임방 추가" });
  await userEvent.click(screen.getByRole("combobox", { name: "게임" }));
  await userEvent.click(await screen.findByRole("option", { name: "실시간 퀴즈" }));
  await screen.findByText("문제 1");
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(route);
});

describe("실시간 퀴즈 — 보기 삭제가 정답 인덱스를 밀어내지 않는다", () => {
  it("정답(C)보다 앞의 보기(A)를 지워도 정답은 계속 C의 내용을 가리킨다", async () => {
    await openQuizEditor();

    // 기본 보기 2개 -> 4개(A, B, C, D)
    await userEvent.click(screen.getByRole("button", { name: "보기 추가" }));
    await userEvent.click(screen.getByRole("button", { name: "보기 추가" }));

    await userEvent.type(screen.getByLabelText("문제 1 보기 1"), "A");
    await userEvent.type(screen.getByLabelText("문제 1 보기 2"), "B");
    await userEvent.type(screen.getByLabelText("문제 1 보기 3"), "C");
    await userEvent.type(screen.getByLabelText("문제 1 보기 4"), "D");

    // C(인덱스 2)를 정답으로 표시
    await userEvent.click(screen.getAllByRole("radio")[2]);
    expect(screen.getAllByRole("radio")[2]).toBeChecked();

    // A(인덱스 0, 정답보다 앞)를 삭제
    await userEvent.click(screen.getAllByRole("button", { name: "삭제" })[0]);

    // 보기는 [B, C, D]로 줄었다. 정답 라디오가 가리키는 보기의 "내용"이 여전히 C여야 한다
    // (버그: 인덱스를 그대로 둬서 D를 가리키게 된다).
    const radios = screen.getAllByRole("radio");
    const checkedIndex = radios.findIndex((r) => r.checked);
    expect(checkedIndex).toBeGreaterThanOrEqual(0);
    const correctInput = screen.getByLabelText(`문제 1 보기 ${checkedIndex + 1}`);
    expect(correctInput).toHaveValue("C");
    expect(correctInput).not.toHaveValue("D");
  });

  it("정답으로 표시된 보기 자체를 지우면 다른 보기로 정답이 넘어가지 않고 미지정이 된다", async () => {
    await openQuizEditor();

    await userEvent.click(screen.getByRole("button", { name: "보기 추가" }));

    await userEvent.type(screen.getByLabelText("문제 1 보기 1"), "A");
    await userEvent.type(screen.getByLabelText("문제 1 보기 2"), "B");
    await userEvent.type(screen.getByLabelText("문제 1 보기 3"), "C");

    // C(인덱스 2)를 정답으로 표시하고 그 보기를 곧바로 삭제
    await userEvent.click(screen.getAllByRole("radio")[2]);
    await userEvent.click(screen.getAllByRole("button", { name: "삭제" })[2]);

    // 남은 보기 [A, B] 중 어느 쪽으로도 정답이 "추측"되어 넘어가면 안 된다.
    const radios = screen.getAllByRole("radio");
    expect(radios.every((r) => !r.checked)).toBe(true);
  });
});
