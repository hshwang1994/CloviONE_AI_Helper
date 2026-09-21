import { describe, it, expect } from "vitest";
import { filterGroupsByQuery, NAV } from "./navConfig.js";

/* PA-RC-0017 acceptance_criteria 7: "레일 필터에 두 글자를 입력하면 목적지가 좁혀진다." */
describe("레일 내비 필터", () => {
  it("빈 질의는 원본 그대로 돌려준다", () => {
    expect(filterGroupsByQuery(NAV, "")).toBe(NAV);
    expect(filterGroupsByQuery(NAV, "   ")).toBe(NAV);
  });

  it("두 글자만 쳐도 라벨이 맞는 항목만 남는다", () => {
    // '감사' 그룹은 지시 30 재구성으로 감사 로그·개발자 월간 리포트 둘만 남았다
    // ('감사 이상 징후'는 감사 로그의 탭이 됐다) — 그룹 이름이 맞으면 그 그룹 전체가 남는다.
    const out = filterGroupsByQuery(NAV, "감사");
    const paths = out.flatMap((g) => g.items.map((i) => i.to));
    expect(paths).toContain("/audit");
    expect(paths).toContain("/dev-report");
    expect(paths).not.toContain("/dashboard");
  });

  it("대소문자를 가리지 않는다(영문 라벨 대비)", () => {
    const nav = [{ group: "테스트", items: [{ to: "/x", label: "AI 관리" }] }];
    expect(filterGroupsByQuery(nav, "ai").flatMap((g) => g.items)).toHaveLength(1);
    expect(filterGroupsByQuery(nav, "AI").flatMap((g) => g.items)).toHaveLength(1);
  });

  it("공백 · 대소문자 · 전각 표기가 달라도 같은 메뉴가 남는다 (검색 접기)", () => {
    const nav = [
      { group: "테스트", items: [{ to: "/x", label: "AI 관리" }, { to: "/y", label: "현황 제외 보고" }] },
    ];
    const hits = (q) => filterGroupsByQuery(nav, q).flatMap((g) => g.items.map((i) => i.to));
    for (const q of ["AI관리", "ai 관리", " AI  관리 ", "ＡＩ 관리", "ai\u{3000}관리"]) {
      expect(hits(q), q).toEqual(["/x"]);
    }
    // 대상 쪽 공백도 접는다 — 라벨의 「현황 제외」를 붙여 쳐도 찾는다.
    expect(hits("현황제외")).toEqual(["/y"]);
    expect(hits("현황 제외")).toEqual(["/y"]);
  });

  it("공백 · 제로폭 문자만 친 질의는 빈 질의다 — 원본 그대로 돌려준다", () => {
    expect(filterGroupsByQuery(NAV, "\u{3000}")).toBe(NAV);
    expect(filterGroupsByQuery(NAV, "\u{200B}")).toBe(NAV);
  });

  it("맞는 항목이 하나도 없는 그룹은 통째로 사라진다(빈 헤더로 안 남는다)", () => {
    const out = filterGroupsByQuery(NAV, "존재하지않는질의그것도아주긴");
    expect(out).toEqual([]);
  });

  it("그룹 이름 자체가 맞으면 그 그룹의 항목을 전부 남긴다", () => {
    const auditGroup = NAV.find((g) => g.group === "감사");
    const out = filterGroupsByQuery(NAV, "감사");
    const outGroup = out.find((g) => g.group === "감사");
    expect(outGroup.items.length).toBe(auditGroup.items.length);
  });

  it("원본 NAV 배열/그룹 객체를 변형하지 않는다", () => {
    const before = JSON.stringify(NAV);
    filterGroupsByQuery(NAV, "설정");
    expect(JSON.stringify(NAV)).toBe(before);
  });
});
