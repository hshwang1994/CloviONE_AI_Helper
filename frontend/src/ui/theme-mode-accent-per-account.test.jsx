import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider, useThemeMode, clearBootAccent } from "./ThemeModeProvider.jsx";
import { DEFAULT_ACCENT } from "./theme.js";

/* 강조색도 테마(밝게/어둡게)와 같은 이유로 계정별 localStorage 키를 쓴다(app/theme-store.js의
 * accountKey와 같은 모양). 공용/키오스크 PC에서 한 사람이 고른 색이 다음 로그인 사용자에게
 * 넘어가면 안 된다 — 이 파일이 그 계약을 지킨다.
 *
 * `ThemeModeProvider`는 `AuthProvider`보다 바깥(위)에 마운트돼 있어(main.jsx) userId를
 * prop으로 받을 수 없다 - 대신 계정을 아는 첫 지점(app/UserMenu.jsx)이
 * `identifyAccentUser(userId)`를 호출해 안에서 알려 준다. 이 테스트는 그 실제 호출
 * 패턴을 흉내 낸다(prop이 아니라 함수 호출로 계정을 알린다). */

function AccentProbe({ value, userId }) {
  const { accent, setAccent, identifyAccentUser } = useThemeMode();
  React.useEffect(() => {
    if (userId) identifyAccentUser(userId);
  }, [userId, identifyAccentUser]);
  return (
    <button onClick={() => setAccent(value)}>{`현재:${accent}`}</button>
  );
}

function renderFor(userId) {
  return render(
    <ThemeModeProvider>
      <AccentProbe value="#6B5BC7" userId={userId} />
    </ThemeModeProvider>
  );
}

describe("강조색의 계정별 저장", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("사용자 A가 강조색을 바꿔도 사용자 B의 저장된 색과 화면에는 영향이 없다", async () => {
    // B는 이미 자기 색을 골라 둔 상태(청록)로 시작한다.
    window.localStorage.setItem("clovirone_accent:userB", "#327C98");

    const user = userEvent.setup();
    const { unmount } = renderFor("userA");
    await user.click(screen.getByRole("button"));
    unmount();

    // A의 선택은 A 자신의 계정 키에만 쓰인다.
    expect(window.localStorage.getItem("clovirone_accent:userA")).toBe("#6B5BC7");
    // B의 계정 키는 그대로다 — A의 변경에 영향받지 않는다.
    expect(window.localStorage.getItem("clovirone_accent:userB")).toBe("#327C98");

    // B로 새로 마운트하면(다음 로그인) 자기 계정에 저장된 색이 보인다 — A의 색이 아니다.
    renderFor("userB");
    expect(screen.getByRole("button")).toHaveTextContent("현재:#327C98");
  });

  it("아무도 로그인하지 않았을 때(identifyAccentUser 호출 전)는 계정 무관 공용 키를 쓴다", () => {
    render(
      <ThemeModeProvider>
        <AccentProbe value="#6B5BC7" userId={null} />
      </ThemeModeProvider>
    );
    expect(screen.getByRole("button")).toHaveTextContent(`현재:${DEFAULT_ACCENT}`);
  });

  it("clearBootAccent는 계정 무관 키만 지우고 계정별 키는 남긴다", () => {
    window.localStorage.setItem("clovirone_accent", "#6B5BC7");
    window.localStorage.setItem("clovirone_accent:userA", "#327C98");

    clearBootAccent();

    expect(window.localStorage.getItem("clovirone_accent")).toBeNull();
    expect(window.localStorage.getItem("clovirone_accent:userA")).toBe("#327C98");
  });
});
