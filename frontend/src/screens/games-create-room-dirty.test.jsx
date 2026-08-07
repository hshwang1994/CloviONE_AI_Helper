import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 게임방 만들기 모달 — "닫기 전 확인"(E11, ui/kit.jsx Modal의 dirty prop 주석)이 실제로
 * 모든 닫기 경로 · 모든 입력을 지키는가.
 *
 * ui/kit.jsx의 그 주석이 밝히는 실패 사례: 퀴즈 문제(최대 20문항)를 다 쓰고 Esc나 바깥을
 * 한 번 누르면 확인 없이 전부 사라졌다 — 그래서 CreateRoomModal이 dirty를 계산해 Modal에
 * 넘긴다. 이 테스트는 그 방어가 새는 두 지점을 고정한다:
 *
 *   1) 하단 '취소' 버튼은 Modal의 dirty 검사(requestClose)를 거치지 않고 CreateRoomModal이
 *      받은 onClose를 곧장 부른다(ModalFooter onCancel={onClose}) — X 아이콘·Esc·바깥
 *      클릭은 확인을 받으면서 '취소' 버튼만 확인 없이 바로 닫힌다.
 *   2) dirty 계산 자체가 title/question/options/aiTopic/quizQs만 본다 — 당첨 인원처럼
 *      숫자/셀렉트로 바꾼 값은 어떤 닫기 경로를 쓰든 전혀 반영되지 않는다.
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

async function openModal() {
  renderGames();
  await userEvent.click(await screen.findByRole("button", { name: "게임방 만들기" }));
  await screen.findByRole("heading", { name: "게임방 만들기" });
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(route);
});

describe("게임방 만들기 — 닫기 전 확인이 새는 지점", () => {
  it("제목을 쓰고 '취소'를 눌러도 확인 없이 사라지지 않는다(하단 취소 버튼도 dirty 검사를 거쳐야 한다)", async () => {
    await openModal();
    await userEvent.type(screen.getByLabelText(/방 제목/), "테스트 방");

    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    // 확인 없이 바로 닫혔다면 이 문구가 뜨지 않고 모달이 곧장 사라진다.
    expect(await screen.findByText(/입력한 내용이 저장되지 않았습니다/)).toBeInTheDocument();
  });

  it("당첨 인원만 바꾸고 닫아도 확인 없이 사라지지 않는다(숫자/셀렉트 필드도 dirty여야 한다)", async () => {
    await openModal();
    const winners = screen.getByLabelText("당첨 인원");
    await userEvent.clear(winners);
    await userEvent.type(winners, "5");

    await userEvent.click(screen.getByRole("button", { name: "닫기" }));

    expect(await screen.findByText(/입력한 내용이 저장되지 않았습니다/)).toBeInTheDocument();
  });

  it("열자마자 아무것도 안 바꾸고 닫으면 확인 없이 바로 닫힌다(거짓 dirty 금지)", async () => {
    // 기본 게임(랜덤 추첨)은 제한 시간 필드가 아예 안 보인다 - 열자마자 닫는 건
    // 방장이 아무것도 고르지 않았다는 뜻이라 "저장 안 된 내용"이 있을 수 없다.
    // 열기 리셋 effect가 timer를 gameType 기본값(0)이 아니라 하드코딩된 15로 남겨두면
    // dirty가 거짓으로 true가 되어 여기서 안 나와야 할 확인 대화상자가 뜬다.
    await openModal();

    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByText(/입력한 내용이 저장되지 않았습니다/)).not.toBeInTheDocument();
  });
});
