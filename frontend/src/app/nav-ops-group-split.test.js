import { describe, it, expect } from "vitest";

import { NAV } from "./navConfig.js";

/* 예전엔 "운영" 한 그룹에 14항목이 평평하게 섞여 있었다(IA-01) — 매일 훑는 화면(대시보드·
 * 알림·작업 큐·설정), 저빈도·고위험 시스템 인프라(백업·진단·시스템 설정 등), 규정 준수·통제
 * (감사·기능 플래그·공지)가 순서 없이 나열됐다. 최상위 그룹 셋으로 쪼갰다(IA-01) — 그 뒤
 * MEGA CYCLE I(FN-01)가 메일 발송을 더해 15가 됐다.
 *
 * PA-RC-0017: 7그룹 39항목을 5그룹 35항목으로 다시 짰다(navConfig.js NAV 상단 주석 참조).
 * 사라진 4(시스템 설정·유지보수·Notion 관리·AI 관리)는 유실이 아니라 /settings의 탭이 됐다
 * (SettingsShell.jsx) — 그래서 이 테스트는 "항목이 어딘가에 다 있다"가 아니라 "5그룹·항목당
 * 7개 이하·총 35개·그리고 탭이 된 4개는 NAV에 없다"를 함께 지킨다.
 */
describe("사이드바 5그룹 재편 (PA-RC-0017)", () => {
  it("'운영' 단일 그룹도, IA-01 시절 3그룹 이름도 이제 없다", () => {
    const names = NAV.map((g) => g.group);
    expect(names).not.toContain("운영 현황");
    expect(names).not.toContain("시스템 인프라");
    expect(names).not.toContain("거버넌스");
    expect(names).not.toContain("콘텐츠");
  });

  it("정확히 5그룹(운영/사용자와 권한/자동화/연동/감사)이고 그룹당 7항목 이하다", () => {
    const names = NAV.map((g) => g.group);
    expect(names).toEqual(["운영", "사용자와 권한", "자동화", "연동", "감사"]);
    for (const g of NAV) expect(g.items.length).toBeLessThanOrEqual(7);
  });

  it("총 35항목 — 39에서 설정 탭이 된 4개(시스템 설정·유지보수·Notion 관리·AI 관리)를 뺀 수다", () => {
    const total = NAV.reduce((sum, g) => sum + g.items.length, 0);
    expect(total).toBe(35);
  });

  it("탭이 된 4개는 더 이상 NAV의 별도 항목이 아니다 — /settings 하나로 모인다", () => {
    const all = NAV.flatMap((g) => g.items || []);
    const paths = all.map((i) => i.to);
    expect(paths).not.toContain("/system");
    expect(paths).not.toContain("/maintenance");
    expect(paths).not.toContain("/notion-console");
    expect(paths).not.toContain("/llm-console");
    expect(paths).toContain("/settings");
  });

  it("남은 항목의 라우트·역할·배지는 그대로다 — 어느 그룹에 속하는지만 바뀌었다", () => {
    const all = NAV.flatMap((g) => g.items || []);
    const byPath = Object.fromEntries(all.map((i) => [i.to, i]));
    expect(byPath["/jobs"].roles).toEqual(["operator", "admin", "system_admin"]);
    expect(byPath["/jobs"].badge).toBe("jobFailed");
    expect(byPath["/audit"].roles).toEqual(["admin", "system_admin", "auditor"]);
    expect(byPath["/setup"].roles).toEqual(["system_admin"]);
  });
});
