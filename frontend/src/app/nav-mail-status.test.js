import { describe, it, expect } from "vitest";

import { NAV } from "./navConfig.js";
import { NAV_ICONS } from "./navIcons.js";

/* FN-01: GET /api/admin/mail/status·POST /test는 처음부터 있었는데 사이드바 항목이 없었다.
 * 형제(백업·진단)와 같은 CONSOLE_READ_ROLES 집합으로 넣는다. PA-RC-0017로 "시스템 인프라"는
 * 없어지고 "운영" 그룹이 그 형제들을 이어받았다. */
describe("사이드바 운영 메뉴 — 메일 발송", () => {
  const group = NAV.find((g) => g.group === "운영");
  const item = (group.items || []).find((i) => i.to === "/mail");

  it("메일 발송 메뉴 항목이 존재하고 형제 항목(백업)과 같은 role 집합을 쓴다", () => {
    expect(item).toBeTruthy();
    expect(item.label).toBe("메일 발송");
    expect(item.roles).toEqual(["operator", "admin", "system_admin", "auditor"]);
  });

  it("아이콘 키가 실제 아이콘 컴포넌트로 해석된다(오타면 사이드바에서 조용히 안 그려진다)", () => {
    expect(NAV_ICONS[item.icon]).toBeTruthy();
  });
});
