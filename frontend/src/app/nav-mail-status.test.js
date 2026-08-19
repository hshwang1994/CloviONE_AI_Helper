import { describe, it, expect } from "vitest";

import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";

import { NAV } from "./navConfig.js";

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

  /* 옛 판은 이 항목의 아이콘 **키**가 표에서 해석되는지 봤다("오타면 조용히 안 그려진다").
   * W3 «Icon System» 이후 자식 항목은 키를 갖지 않는다 — 글리프는 그룹 하나의 것이다.
   * 그래서 같은 위험("그려져야 할 그림이 조용히 사라진다")을 지금 실제로 그리는 자리에서
   * 잰다: 이 항목이 사는 그룹이 랜드마크 글리프를 들고 있는가, 그리고 자식 쪽에 키가
   * 되돌아오지 않았는가. 단언이 하나에서 둘로 늘었다. */
  it("이 항목이 사는 그룹이 랜드마크 글리프를 들고 있고, 항목 자신은 안 든다", () => {
    expect(group.icon, "'운영' 그룹이 글리프를 잃으면 사이드바 한 줄이 그림 없이 그려진다")
      .toBe(DashboardOutlinedIcon);
    expect(item.icon, "자식 아이콘 키가 되돌아왔다").toBeUndefined();
  });
});
