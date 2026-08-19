import { describe, it, expect } from "vitest";

import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import { NAV, USER_NAV } from "./navConfig.js";

/* 관리자 사이드바 IA 계약 (지시 30 · 51 · 60).
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * 예전 판(PA-RC-0031 / 0060)은 5그룹 36항목 배치를 못박고 있었다 — "감사 그룹은 감사·통계만",
 * "백업과 복구 리허설이 이웃해 있다" 같은 식으로. 지시 30 이 그 배치 자체를 다시 짜라고 했고,
 * 결과가 6그룹 31항목이다(navConfig.js NAV 상단 주석에 판단 근거가 있다).
 *
 * **옛 단언 중 살아 있는 것은 전부 남겼다.** 짝을 이루던 화면들은 "같은 그룹에 이웃해 있다"
 * 보다 **강한** 상태가 됐다 — 같은 화면의 탭이다(AdminRoutes.jsx TAB_GROUPS). 그래서 그
 * 단언은 "사이드바에 형제로 있다"가 아니라 "사이드바 항목이 아니라 탭이다"로 바뀐다.
 * 약화가 아니라 더 강한 계약이다.
 *
 * 그대로 남는 불변식 셋: 라벨에 괄호 병기 금지, **모든 항목에 role 게이트**(팔레트 누수
 * 방지), 사용자 사이드바 4그룹.
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
const allPaths = () => NAV.flatMap((g) => g.items.map((i) => i.to));

describe("관리자 사이드바 — 그룹이 질문에 답한다 (지시 30)", () => {
  it("여섯 그룹이고, 이름이 곧 '어떤 일을 하려는가'다", () => {
    expect(NAV.map((g) => g.group)).toEqual([
      "운영", "설정", "사용자와 권한", "자동화와 연동", "AI", "감사",
    ]);
  });

  it("감사 그룹에는 감사만 남는다 — 사용 통계 리포트는 AI 로 갔다", () => {
    const audit = pathsOf(NAV, "감사");
    expect(new Set(audit)).toEqual(new Set(["/audit", "/dev-report"]));
    expect(audit).not.toContain("/policy-usage");
    expect(audit).not.toContain("/prompt-usage");
    expect(audit).not.toContain("/feature-flags");
    expect(audit).not.toContain("/announcements");
  });

  it("AI 재료가 한 자리에 모인다 — 예전엔 자동화·연동·감사 셋에 흩어져 있었다", () => {
    expect(pathsOf(NAV, "AI")).toEqual([
      "/prompts", "/policies", "/templates", "/ai-quotas", "/ai-usage",
    ]);
  });

  it("설정 성격 화면이 장애 대응 화면과 섞이지 않는다", () => {
    expect(pathsOf(NAV, "설정")).toEqual([
      "/settings", "/setup", "/feature-flags", "/announcements",
    ]);
    const ops = pathsOf(NAV, "운영");
    expect(ops).not.toContain("/settings");
    expect(ops).not.toContain("/feature-flags");
  });
});

describe("짝을 이루는 화면은 형제 항목이 아니라 한 화면의 탭이다 (지시 30 · 41)", () => {
  /* 옛 판은 "백업과 복구 리허설이 같은 그룹에 **이웃해** 있다"를 지켰다. 지금은 한 화면의
     탭이라 이웃할 필요조차 없다 — 사이드바 항목 자체가 하나다. 라우트는 그대로 살아 있고
     (AdminRoutes.jsx 가 옛 주소를 해당 탭으로 연다) 사이드바에서만 사라진다. */
  it.each([
    ["/restore-drills", "/backup"],
    ["/approval-delegations", "/approvals"],
    ["/audit-anomalies", "/audit"],
    ["/policy-usage", "/ai-usage"],
    ["/prompt-usage", "/ai-usage"],
    ["/scheduler-calendar", "/schedules"],
  ])("%s 는 사이드바 항목이 아니고, 대표 화면 %s 이 사이드바에 있다", (merged, host) => {
    expect(allPaths()).not.toContain(merged);
    expect(allPaths()).toContain(host);
  });

  it("합쳐서 36항목이 31항목이 됐다 — 기능은 하나도 안 없어졌다", () => {
    const total = NAV.reduce((sum, g) => sum + g.items.length, 0);
    expect(total).toBe(31);
  });
});

describe("관리자 사이드바 — 라벨 용어 규칙", () => {
  it("어느 라벨도 괄호 병기를 안 쓴다 — 한 벌로 통일", () => {
    const bracketed = NAV.flatMap((g) => g.items.map((i) => i.label))
      .filter((l) => l.includes("(") || l.includes(")"));
    expect(bracketed).toEqual([]);
  });
});

describe("옮긴 항목의 role·배지는 한 글자도 안 바뀌고, 글리프는 그룹 하나가 갖는다", () => {
  /* 옛 판은 네 번째 칸에 **항목별 아이콘 키**를 못박고 있었다(`"flag"`·`"announce"`·`"ai"`…).
   * 그 상태 자체가 R-48 이 금지한 것이었다 — `ticket` 네 곳, `report` 네 곳, `docs` 세 곳처럼
   * 같은 그림이 여러 목적지에서 반복돼 훑을 때 서로 다른 화면이 한 덩어리로 보였고, 41개
   * 글리프가 라벨 시작선을 그룹 60px / 자식 64px 로 갈라 놓았다(F-W1R-18 픽셀 실측).
   *
   * W3 «Icon System» 의 규칙은 하나다: **그룹이 글리프를 가지면 자식은 갖지 않는다.**
   * 그래서 네 번째 칸이 **그 항목이 사는 그룹의 랜드마크 글리프 컴포넌트**로 바뀐다.
   * 고정 강도는 오히려 올라간다 — 문자열 키 비교가 컴포넌트 **동일성** 비교가 되고,
   * "자식에 키가 되돌아오지 않았다"는 단언이 하나 더 붙는다. 규칙이 되돌려지면 둘 중
   * 하나가 반드시 깨진다. */
  it.each([
    ["/feature-flags", "설정", ["operator", "admin", "system_admin", "auditor"], SettingsOutlinedIcon],
    ["/announcements", "설정", ["operator", "admin", "system_admin", "auditor"], SettingsOutlinedIcon],
    ["/prompts", "AI", ["operator", "admin", "system_admin", "auditor"], SmartToyOutlinedIcon],
    ["/approvals", "사용자와 권한", ["operator", "admin", "system_admin", "auditor"], ManageAccountsOutlinedIcon],
    ["/integrations", "자동화와 연동", ["operator", "admin", "system_admin", "auditor"], AutoAwesomeOutlinedIcon],
  ])("%s: %s 그룹, 역할 보존 · 글리프는 그룹의 것 하나", (to, expectedGroup, roles, GroupIcon) => {
    const item = findItem(NAV, to);
    expect(item.group).toBe(expectedGroup);
    expect(item.roles).toEqual(roles);
    expect(item.icon, `${to} 에 자식 아이콘 키가 되돌아왔다`).toBeUndefined();
    expect(group(NAV, expectedGroup).icon, `${expectedGroup} 그룹이 랜드마크 글리프를 잃었다`)
      .toBe(GroupIcon);
  });

  it("두 콘솔의 **모든** 자식 항목에 아이콘 키가 없다 — 규칙은 다섯 줄이 아니라 전수다", () => {
    const withIcon = [...NAV, ...USER_NAV]
      .flatMap((g) => g.items.map((it) => ({ group: g.group, to: it.to, icon: it.icon })))
      .filter((x) => x.icon !== undefined);
    expect(withIcon, "그룹이 글리프를 가지면 자식은 갖지 않는다 (PLAN «Icon System»)").toEqual([]);
  });

  it("모든 그룹이 글리프를 정확히 하나 갖고, 한 콘솔 안에서 그림이 반복되지 않는다", () => {
    for (const nav of [NAV, USER_NAV]) {
      const icons = nav.map((g) => g.icon);
      expect(icons.filter(Boolean), "글리프 없는 그룹이 있다").toHaveLength(nav.length);
      expect(new Set(icons).size, "같은 그림을 두 그룹이 쓴다").toBe(nav.length);
    }
  });

  it("배지를 들고 있던 항목은 그대로 들고 있다", () => {
    expect(findItem(NAV, "/jobs").badge).toBe("jobFailed");
    expect(findItem(NAV, "/backup").badge).toBe("backupFailed");
    expect(findItem(NAV, "/approvals").badge).toBe("approvalPending");
    expect(findItem(NAV, "/admin-notifications").badge).toBe("adminNotifUnread");
  });

  it("관리자 사이드바의 **모든** 항목에 role 게이트가 있다 (0060)", () => {
    // 이것이 팔레트 누수를 막는 실제 불변식이다 — 하나라도 비면 그 화면이 일반 사용자의
    // Ctrl+K 결과에 나타난다.
    const missing = NAV.flatMap((g) => g.items)
      .filter((i) => !Array.isArray(i.roles) || i.roles.length === 0)
      .map((i) => i.to);
    expect(missing).toEqual([]);
  });
});

describe("사용자 사이드바 — 휴지통 메뉴 항목 제거, 4그룹으로 (acceptance 5)", () => {
  it("USER_NAV에 '휴지통' 항목이 없다 — /team-docs/trash로 가는 메뉴는 이제 없다", () => {
    const paths = USER_NAV.flatMap((g) => g.items.map((i) => i.to));
    expect(paths).not.toContain("/team-docs/trash");
  });

  it("'문서' 단독 그룹이 없다 — /team-docs는 팀 업무 안에 있다", () => {
    const names = USER_NAV.map((g) => g.group);
    expect(names).not.toContain("문서");
    expect(names).toHaveLength(4);
    // 2026-08-19(D-166): 예전엔 '팀 공간' 하나에 여덟 항목이 있었다. 업무와 소통·놀이를
    // 갈랐으므로 문서는 '팀 업무' 쪽이다 — 문서를 찾는 사람은 일하러 온 사람이다.
    expect(findItem(USER_NAV, "/team-docs").group).toBe("팀 업무");
  });

  /* 지시 58 재검토 결과를 고정한다(D-166). 이 셋은 판정이지 취향이 아니다 — 되돌리려면
     같은 근거를 다시 세워야 한다. */
  it("'도우미' 그룹이 없다 — AI 도우미와 스프린트 회의는 같은 부류가 아니다", () => {
    const names = USER_NAV.map((g) => g.group);
    expect(names).not.toContain("도우미");
    expect(findItem(USER_NAV, "/chat").group).toBe("내 업무");
    expect(findItem(USER_NAV, "/sprint").group).toBe("팀 업무");
  });

  it("한 그룹이 여섯 항목을 넘지 않는다 — 넘으면 서랍이 아니라 목록이다", () => {
    for (const g of USER_NAV) {
      expect(g.items.length, `${g.group} 이 너무 크다`).toBeLessThanOrEqual(6);
    }
  });
});
