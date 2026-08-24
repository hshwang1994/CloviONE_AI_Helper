import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { TicketCard } from "./Chat.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* AI-41: 결과 카드에서 앱 내 티켓 상세로 가는 딥링크가 없었다(외부 원본 링크만).
 * AssistantPanel.jsx의 같은 카드는 이미 #/tickets/{id}로 간다 — TicketCard도 같은 패턴을 쓴다.
 *
 * 그 외부 링크는 지금 없다. 티켓 응답의 `url` 이 전 건 app.notion.com 을 가리켰고, 정본이
 * 이 서버로 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상 쓰지 않는 낡은 사본이라 서버가
 * 필드를 걷었다. 앱 안으로 가는 길만 남는다. */

function renderCard(t, extraProps = {}) {
  return render(
    <ThemeModeProvider>
      <TicketCard t={t} isTicket {...extraProps} />
    </ThemeModeProvider>
  );
}

describe("결과 카드의 앱 내 티켓 딥링크", () => {
  it("t.id가 있으면 #/tickets/{id}로 가는 '앱에서 보기' 링크가 보인다", () => {
    renderCard({ id: "t-123", title: "러너 상태 수집 타임아웃 분리" });
    const link = screen.getByRole("link", { name: "앱에서 보기" });
    expect(link).toHaveAttribute("href", "#/tickets/t-123");
  });

  it("t.id가 없으면 링크를 그리지 않는다(존재하지 않는 상세로 보내지 않는다)", () => {
    renderCard({ title: "id 없는 카드" });
    expect(screen.queryByRole("link", { name: "앱에서 보기" })).toBeNull();
  });

  it("티켓이 아닌 카드(프로젝트 등)에는 딥링크를 붙이지 않는다", () => {
    renderCard({ id: "p-1", title: "프로젝트 카드" }, { isTicket: false });
    expect(screen.queryByRole("link", { name: "앱에서 보기" })).toBeNull();
  });

  it("서버가 옛 url 을 다시 실어 보내도 외부 링크를 만들지 않는다", () => {
    /* 예전에는 이 시험이 반대를 단언했다: 외부 링크와 앱 딥링크가 둘 다 보인다.
       화면이 옛 필드를 보고 링크를 되살리면 사용자는 오늘 고친 내용이 없는 쪽으로 나간다. */
    renderCard({ id: "t-9", title: "둘 다", url: "https://www.notion.so/x" });
    expect(screen.getByRole("link", { name: "앱에서 보기" })).toHaveAttribute("href", "#/tickets/t-9");
    expect(screen.queryByText("Notion에서 열기")).toBeNull();
    expect(screen.queryByText("https://www.notion.so/x")).toBeNull();
  });
});
