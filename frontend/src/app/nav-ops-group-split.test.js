import { describe, it, expect } from "vitest";

import { NAV } from "./navConfig.js";

/* 예전엔 "운영" 한 그룹에 14항목이 평평하게 섞여 있었다(IA-01) — 매일 훑는 화면(대시보드·
 * 알림·작업 큐·설정), 저빈도·고위험 시스템 인프라(백업·진단·시스템 설정 등), 규정 준수·통제
 * (감사·기능 플래그·공지)가 순서 없이 나열됐다. 최상위 그룹 셋으로 쪼갠다 — 사이드바 렌더러
 * (AppShell.jsx)와 명령 팔레트(CommandPalette.jsx) 둘 다 "배열 원소 하나 = 그룹 하나"로만
 * 다뤄 코드 수정 없이 안전하게 되는 안이다.
 */
describe("사이드바 '운영' 그룹 분리 (IA-01)", () => {
  it("'운영' 이름의 그룹은 더 이상 없다", () => {
    expect(NAV.find((g) => g.group === "운영")).toBeUndefined();
  });

  it("운영 현황·시스템 인프라·거버넌스 세 그룹이 있고, 원래 14개가 그대로 어딘가에 남아 있다", () => {
    const opsToday = NAV.find((g) => g.group === "운영 현황");
    const infra = NAV.find((g) => g.group === "시스템 인프라");
    const governance = NAV.find((g) => g.group === "거버넌스");
    expect(opsToday).toBeTruthy();
    expect(infra).toBeTruthy();
    expect(governance).toBeTruthy();
    // 14는 IA-01 분리 당시의 원래 항목 수다. 그 뒤 MEGA CYCLE I(FN-01)가 "시스템 인프라"에
    // "메일 발송"을 새로 추가해 총합이 하나 늘었다 — 늘어난 이유가 있는 숫자이지 유실이 아니다.
    const total = opsToday.items.length + infra.items.length + governance.items.length;
    expect(total).toBe(15);
  });

  it("각 항목의 라우트·역할·배지는 그대로다 — 어느 그룹에 속하는지만 바뀌었다", () => {
    const all = NAV.flatMap((g) => g.items || []);
    const byPath = Object.fromEntries(all.map((i) => [i.to, i]));
    expect(byPath["/jobs"].roles).toEqual(["operator", "admin", "system_admin"]);
    expect(byPath["/jobs"].badge).toBe("jobFailed");
    expect(byPath["/system"].roles).toEqual(["system_admin"]);
    expect(byPath["/audit"].roles).toEqual(["admin", "system_admin", "auditor"]);
    expect(byPath["/maintenance"].roles).toEqual(["operator", "admin", "system_admin", "auditor"]);
  });
});
