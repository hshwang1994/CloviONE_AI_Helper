import React from "react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 목록과 상세를 한 화면에 둔 곳은 **고를 때 다시 마운트되지 않는다** — 본문 경계의 키는 경로가 아니라 화면이다.
 *
 * 🔴 이 파일이 생긴 이유(2026-09-21): 조직 관리 · 사용자 관리 · 채팅방은 두 주소(`/departments` · `/departments/:id` 등)에
 * 같은 element 를 걸어 인스턴스를 지키도록 만들어졌는데(PA-RC-0024 · S1), 본문 경계의 키가 경로라서 처음부터 한 번도
 * 그렇게 돌지 않았다. 부서 하나를 고를 때마다 화면이 통째로 다시 마운트돼 조직도의 펼침 · 스크롤을 잃었고, 화면 이동
 * 알림이 초점을 본문 맨 앞으로 옮겨 방금 누른 자리도 잃었다.
 *
 * 여기서 못박는 것:
 *   · 묶음 안의 이동(부서 → 부서, 목록 → 사람)은 같은 인스턴스다. 다른 화면으로 가면 새로 마운트된다.
 *   · 같은 메뉴를 다시 누르는 새 진입(진입 번호)은 묶음 안에서도 새로 마운트한다.
 *   · 묶음 안의 이동은 초점을 옮기지도 낭독하지도 않는다. 다른 화면으로 가면 둘 다 한다.
 *   · 셸이 정말로 이 규칙을 쓴다(`App.jsx` 의 경계 키 · `AppShell.jsx` 의 알림).
 */

import { NavEntryProvider, screenKeyOf, useEntryNavigate, useNavEntry } from "./navEntry.jsx";
import { useRouteAnnounce } from "./routeAnnounce.js";

describe("screenKeyOf — 화면 한 벌이 그리는 경로 묶음", () => {
  it("조직 관리의 네 주소는 한 화면이다", () => {
    const key = screenKeyOf("/organizations");
    for (const p of ["/org-tree", "/departments", "/departments/d-1", "/departments/d-2"]) expect(screenKeyOf(p), p).toBe(key);
  });

  it("사용자 목록과 사람 한 명, 채팅방 목록과 방 하나는 각각 한 화면이다", () => {
    expect(screenKeyOf("/users/u-1")).toBe(screenKeyOf("/users"));
    expect(screenKeyOf("/chat-rooms/r-1")).toBe(screenKeyOf("/chat-rooms"));
    expect(screenKeyOf("/users")).not.toBe(screenKeyOf("/chat-rooms"));
  });

  it("AI 도우미의 초안과 대화 하나도 한 화면이다 — 대화를 바꿔도 입력 칸 · 목록 스크롤이 남는다", () => {
    expect(screenKeyOf("/chat/c-1")).toBe(screenKeyOf("/chat"));
    expect(screenKeyOf("/chat/c-2")).toBe(screenKeyOf("/chat/c-1"));
    expect(screenKeyOf("/chat")).not.toBe(screenKeyOf("/chat-rooms"));
    expect(screenKeyOf("/chat/c-1/extra")).toBe("/chat/c-1/extra");
  });

  it("묶음에 없는 경로는 경로가 곧 화면이다 — 상세마다 다른 화면인 곳을 합치지 않는다", () => {
    expect(screenKeyOf("/tickets/a")).toBe("/tickets/a");
    expect(screenKeyOf("/tickets/b")).not.toBe(screenKeyOf("/tickets/a"));
    expect(screenKeyOf("/users/u-1/sessions")).toBe("/users/u-1/sessions");
    expect(screenKeyOf("/departments-report")).toBe("/departments-report");
  });
});

let mounts = 0;

function Screen() {
  React.useEffect(() => { mounts += 1; }, []);
  const navigate = useNavigate();
  const enter = useEntryNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/departments/d-2")}>다른 부서</button>
      <button type="button" onClick={() => navigate("/tickets/t-1")}>다른 화면</button>
      <button type="button" onClick={() => enter("/departments/d-2")}>메뉴 다시 누르기</button>
    </>
  );
}

/* App.jsx 의 본문 경계와 같은 키 — `화면:진입 번호`. 알림도 AppShell 과 같은 방식으로 부른다. */
function Body() {
  const loc = useLocation();
  const entry = useNavEntry();
  const message = useRouteAnnounce(loc.pathname, screenKeyOf(loc.pathname));
  return (
    <main id="main-content" tabIndex={-1}>
      <div data-testid="where">{loc.pathname}</div>
      <div data-testid="announce">{message}</div>
      <div key={`${screenKeyOf(loc.pathname)}:${entry}`}><Screen /></div>
    </main>
  );
}

function renderAt(entry) {
  mounts = 0;
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <NavEntryProvider>
        <Body />
      </NavEntryProvider>
    </MemoryRouter>,
  );
}

describe("묶음 안의 이동은 같은 인스턴스다", () => {
  it("🔴 부서를 바꿔 골라도 화면이 다시 마운트되지 않는다", async () => {
    const user = userEvent.setup();
    renderAt("/departments/d-1");
    expect(mounts).toBe(1);
    await user.click(screen.getByRole("button", { name: "다른 부서" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/departments/d-2");
    expect(mounts).toBe(1);
  });

  it("다른 화면으로 가면 새로 마운트된다", async () => {
    const user = userEvent.setup();
    renderAt("/departments/d-1");
    await user.click(screen.getByRole("button", { name: "다른 화면" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/tickets/t-1");
    expect(mounts).toBe(2);
  });

  it("같은 메뉴를 다시 누르는 새 진입은 묶음 안에서도 새로 마운트한다", async () => {
    const user = userEvent.setup();
    renderAt("/departments/d-2");
    await user.click(screen.getByRole("button", { name: "메뉴 다시 누르기" }));
    expect(mounts).toBe(2);
  });
});

describe("묶음 안의 이동은 초점을 빼앗지 않는다", () => {
  it("🔴 부서를 바꿔 골라도 초점이 누른 자리에 남고 낭독도 없다", async () => {
    const user = userEvent.setup();
    renderAt("/departments/d-1");
    const pick = screen.getByRole("button", { name: "다른 부서" });
    await user.click(pick);
    expect(document.activeElement).toBe(pick);
    expect(screen.getByTestId("announce")).toHaveTextContent("");
  });

  it("다른 화면으로 가면 초점이 본문으로 가고 이동을 알린다", async () => {
    const user = userEvent.setup();
    renderAt("/departments/d-1");
    await user.click(screen.getByRole("button", { name: "다른 화면" }));
    await act(async () => {});
    expect(document.activeElement).toBe(document.getElementById("main-content"));
    expect(screen.getByTestId("announce").textContent).toMatch(/이동했습니다/);
  });
});

describe("셸이 이 규칙을 쓴다", () => {
  const HERE = path.dirname(fileURLToPath(import.meta.url));
  it("본문 경계의 키와 화면 이동 알림이 경로가 아니라 화면을 본다", () => {
    const app = fs.readFileSync(path.join(HERE, "App.jsx"), "utf8");
    expect(app).toMatch(/<ErrorBoundary key=\{`\$\{screenKeyOf\(loc\.pathname\)\}:\$\{entry\}`\}/);
    const shell = fs.readFileSync(path.join(HERE, "AppShell.jsx"), "utf8");
    expect(shell).toMatch(/useRouteAnnounce\(loc\.pathname, screenKeyOf\(loc\.pathname\)\)/);
  });
});
