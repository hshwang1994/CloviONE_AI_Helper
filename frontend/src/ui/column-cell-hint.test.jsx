import { describe, it, expect } from "vitest";

/* 잘린 칸의 hover 글자는 **칸에 그린 글자**다 — 행의 원래 값이 아니다.
 *
 * 🔴 이 파일이 생긴 이유(2026-09-21, 관리자 화면 회차 발견): `render` 가 있는 열은 hover 글자를 행의 원래 값에서 만들었다.
 * 역할 · 상태 배지는 값을 한국어 이름으로 바꿔 그리므로, 사용자 목록 역할 칸에 마우스를 올리면 「시스템 관리자」 배지 위로
 * `system_admin` 이 떴다. 그런 열은 `hint(row)` 로 그린 글자를 말한다. registry 의 배지 열(`badgeCol`) · 값 이름 열(`mapCol`)은
 * 도우미가 스스로 준다.
 */

import { columnCellHint, statusText } from "./kit.jsx";
import { badgeCol, mapCol } from "../screens/data-screen/columnHelpers.jsx";

const TRUNC = { truncate: true };

describe("잘린 칸의 hover 글자", () => {
  it("hint 가 있으면 그린 이름을 쓴다 — 원래 값으로 떨어지지 않는다", () => {
    const col = { key: "role", render: () => null, hint: (r) => (r.role === "system_admin" ? "시스템 관리자" : r.role) };
    const row = { role: "system_admin" };
    expect(columnCellHint(col, row, null, { ...TRUNC, plain: "system_admin" })).toBe("시스템 관리자");
  });

  it("🔴 배지 열은 상태 이름을 hover 로 준다", () => {
    const col = badgeCol("state", "상태");
    const row = { state: "running" };
    expect(columnCellHint(col, row, null, { ...TRUNC, plain: String(row.state) })).toBe(statusText("running"));
    expect(columnCellHint(col, row, null, { ...TRUNC, plain: String(row.state) })).not.toBe("running");
  });

  it("🔴 값 이름 열은 대응표의 이름을 hover 로 준다", () => {
    const col = mapCol("kind", "종류", { mail: "메일 발송" });
    expect(columnCellHint(col, { kind: "mail" }, null, { ...TRUNC, plain: "mail" })).toBe("메일 발송");
    // 대응표에 없는 값은 값 그대로다 — 그린 글자도 그 값이다.
    expect(columnCellHint(col, { kind: "etc" }, null, { ...TRUNC, plain: "etc" })).toBe("etc");
  });

  it("🔴 hint 없이 손으로 적은 상태 열도 배지 이름을 hover 로 준다 — 저장값 「검토중」이 아니라 「검토 중」(r23 #55)", () => {
    const col = { key: "status", label: "상태", type: "status", render: () => null };
    expect(columnCellHint(col, { status: "검토중" }, null, { ...TRUNC, plain: "검토중" })).toBe("검토 중");
    // 상태가 아닌 열은 원래 값 그대로다.
    expect(columnCellHint({ key: "x", type: "text" }, { x: "검토중" }, null, { ...TRUNC, plain: "검토중" })).toBe("검토중");
  });

  it("잘리지 않는 칸에는 hover 글자가 없다", () => {
    const col = badgeCol("state", "상태");
    expect(columnCellHint(col, { state: "running" }, null, { truncate: false })).toBeUndefined();
  });
});
