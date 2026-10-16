/* 종 숫자의 구성 (r23 #32) — 숫자는 내 알림 · 관리 알림 · 시스템 알림을 더한 값이라 알림 화면(내 알림만)의 수와 다를 수 있다.
 * 둘 이상이 더해졌을 때만 툴팁과 접근 이름이 그 구성을 말한다(`badgeParts`). */
import { describe, expect, it } from "vitest";
import { badgeParts } from "./NotificationBell.jsx";

describe("badgeParts", () => {
  it("더해진 묶음을 이름과 건수로 말한다", () => {
    expect(badgeParts({ own: 6, ownAudience: "admin", other: 6, otherAudience: "user", sys: 1 }))
      .toEqual(["관리 알림 6건", "내 알림 6건", "시스템 알림 1건"]);
  });

  it("0건인 묶음과 상대 묶음이 없는 콘솔은 빼고, 하나뿐이면 하나만 돌려준다", () => {
    expect(badgeParts({ own: 3, ownAudience: "user", other: 0, otherAudience: null, sys: 0 })).toEqual(["내 알림 3건"]);
    expect(badgeParts({ own: 0, ownAudience: "user", other: 5, otherAudience: "admin", sys: 0 })).toEqual(["관리 알림 5건"]);
    expect(badgeParts({ own: 0, ownAudience: "user", other: 0, otherAudience: null, sys: 0 })).toEqual([]);
  });
});
