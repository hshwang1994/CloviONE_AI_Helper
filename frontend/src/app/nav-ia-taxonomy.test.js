import { describe, it, expect } from "vitest";

import { NAV, USER_NAV } from "./navConfig.js";

/* PA-RC-0031: 사이드바 그룹이 업무 기준이 아니라 어긋나 있었다 — 감사 그룹 6개 중 3개가
 * 감사가 아니고, 같은 명사가 두 그룹으로 쪼개지고(정책/정책 사용 통계), 구조가 같은 사용
 * 통계 화면 둘이 다른 그룹에, 백업과 그 복구 리허설이 다른 그룹에 있었다. 라우트·역할·배지는
 * 한 글자도 안 바꾸고 그룹 배정만 옮긴다(target_design, DECISIONS.md D-129) — 이 테스트는
 * 그 약속(수용 기준)을 고정한다.
 */

function group(nav, name) {
  return nav.find((g) => g.group === name);
}
function itemsOf(nav, name) {
  return (group(nav, name) || {}).items || [];
}
function pathsOf(nav, name) {
  return itemsOf(nav, name).map((i) => i.to);
}
function findItem(nav, to) {
  for (const g of nav) {
    const hit = (g.items || []).find((i) => i.to === to);
    if (hit) return { ...hit, group: g.group };
  }
  return null;
}

describe("관리자 사이드바 — 감사 그룹은 감사·통계만 남는다 (acceptance 1)", () => {
  it("기능 플래그·공지 배너·복구 리허설이 감사 그룹에 없다", () => {
    const auditPaths = pathsOf(NAV, "감사");
    expect(auditPaths).not.toContain("/feature-flags");
    expect(auditPaths).not.toContain("/announcements");
    expect(auditPaths).not.toContain("/restore-drills");
  });

  it("감사 그룹에 남은 항목은 감사 로그·이상 징후·사용 통계·초기 설정(사후 점검류)뿐이다", () => {
    const auditPaths = pathsOf(NAV, "감사");
    expect(new Set(auditPaths)).toEqual(new Set([
      "/audit", "/audit-anomalies", "/setup", "/policy-usage", "/prompt-usage",
    ]));
  });
});

describe("관리자 사이드바 — 같은 종류 화면이 같은 그룹에 모인다 (acceptance 2)", () => {
  it("정책 사용 통계와 프롬프트 사용 통계가 같은(감사) 그룹에 있다", () => {
    const policyUsage = findItem(NAV, "/policy-usage");
    const promptUsage = findItem(NAV, "/prompt-usage");
    expect(policyUsage.group).toBe("감사");
    expect(promptUsage.group).toBe(policyUsage.group);
  });
});

describe("관리자 사이드바 — 업무 인접성 (acceptance 3)", () => {
  it("백업과 복구 리허설이 같은 그룹에 바로 이웃해 있다", () => {
    const backup = findItem(NAV, "/backup");
    const drills = findItem(NAV, "/restore-drills");
    expect(backup.group).toBe("운영");
    expect(drills.group).toBe(backup.group);
    const opsPaths = pathsOf(NAV, "운영");
    const bi = opsPaths.indexOf("/backup");
    const di = opsPaths.indexOf("/restore-drills");
    expect(Math.abs(di - bi)).toBe(1);
  });
});

describe("관리자 사이드바 — 라벨 용어 규칙 (acceptance 4)", () => {
  it("34/35항목 중 어느 라벨도 괄호 병기를 안 쓴다 — 한 벌로 통일(3개만 쓰던 것을 없앴다)", () => {
    const allLabels = NAV.flatMap((g) => g.items.map((i) => i.label));
    const bracketed = allLabels.filter((l) => l.includes("(") || l.includes(")"));
    expect(bracketed).toEqual([]);
  });
});

describe("관리자 사이드바 — 이동한 항목의 role·배지·아이콘은 한 글자도 안 바뀐다 (acceptance 6)", () => {
  // 원본 값(git show HEAD 이전 navConfig.js에서 직접 확인, PA-RC-0031 착수 시점) — 그룹만
  // 옮기고 이 넷은 그대로다. 실수로 role을 새로 달거나 빠뜨리면 여기서 잡힌다.
  it("기능 플래그: roles 없음(운영 콘솔 4역할 전원, SCREEN_ROLES가 라우트 게이트를 맡는다)", () => {
    const item = findItem(NAV, "/feature-flags");
    expect(item.group).toBe("운영");
    expect(item.roles).toBeUndefined();
    expect(item.badge).toBeUndefined();
    expect(item.icon).toBe("flag");
  });

  it("복구 리허설: roles 없음", () => {
    const item = findItem(NAV, "/restore-drills");
    expect(item.group).toBe("운영");
    expect(item.roles).toBeUndefined();
    expect(item.badge).toBeUndefined();
    expect(item.icon).toBe("backup");
  });

  it("공지 배너: roles 없음", () => {
    const item = findItem(NAV, "/announcements");
    expect(item.group).toBe("자동화");
    expect(item.roles).toBeUndefined();
    expect(item.badge).toBeUndefined();
    expect(item.icon).toBe("announce");
  });

  it("프롬프트 사용 통계: roles 없음", () => {
    const item = findItem(NAV, "/prompt-usage");
    expect(item.group).toBe("감사");
    expect(item.roles).toBeUndefined();
    expect(item.badge).toBeUndefined();
    expect(item.icon).toBe("report");
  });
});

describe("사용자 사이드바 — 휴지통 메뉴 항목 제거, 4그룹으로 (acceptance 5)", () => {
  it("USER_NAV에 '휴지통' 항목이 없다 — /team-docs/trash로 가는 메뉴는 이제 없다", () => {
    const allPaths = USER_NAV.flatMap((g) => g.items.map((i) => i.to));
    expect(allPaths).not.toContain("/team-docs/trash");
  });

  it("'문서' 단독 그룹이 없다 — /team-docs가 팀 공간에 합쳐졌다", () => {
    const names = USER_NAV.map((g) => g.group);
    expect(names).not.toContain("문서");
    expect(names).toHaveLength(4);
    const teamSpace = findItem(USER_NAV, "/team-docs");
    expect(teamSpace.group).toBe("팀 공간");
  });
});
