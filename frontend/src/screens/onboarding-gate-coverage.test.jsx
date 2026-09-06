import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { canOnboardFor } from "./data-screen/screenHelp.jsx";

/* RG-06: DataScreen.jsx의 canOnboard 게이트("이 온보딩이 가리키는 버튼을 이 역할이 볼 수
 * 있는가")는 create/primary headerAction이 있는 화면을 전제로 짜여 있다. 온보딩 안내
 * 자체가 웹 버튼이 아니라 서버 CLI 단계를 설명하는 화면(복구 리허설)은 그 전제가 아예
 * 성립하지 않아 canOnboard가 항상 거짓이었고, 정성껏 쓴 situation/prerequisite/steps/
 * expected 4종이 어떤 역할에서도 렌더되지 않았다.
 *
 * 같은 함정이 다른 registry 화면에도 있는지 전수로 확인한다 — emptySituation을 선언한
 * 화면인데 create도 primary headerAction도 config.forceOnboarding도 없으면, 그 온보딩은
 * 죽은 텍스트다.
 */

describe("RG-06 — emptySituation을 쓴 화면은 실제로 렌더될 경로가 있다", () => {
  for (const [key, cfg] of Object.entries(REGISTRY)) {
    if (!cfg.emptySituation) continue;
    it(`${key}: create 또는 primary headerAction 또는 forceOnboarding 중 하나는 있다`, () => {
      const canCreate = !!cfg.create;
      const hasPrimaryHeaderAction = (cfg.headerActions || []).some((a) => a.primary);
      const forced = !!cfg.forceOnboarding;
      expect(
        canCreate || hasPrimaryHeaderAction || forced,
        `${key}: emptySituation이 있지만 canOnboard가 어떤 역할에서도 참이 될 수 없다 — ` +
          "온보딩 안내가 죽은 텍스트다. create를 추가하거나, headerActions에 primary:true를 " +
          "달거나, 안내가 웹 버튼을 가리키지 않으면 forceOnboarding:true를 명시하세요.",
      ).toBe(true);
    });
  }

  it("복구 리허설이 forceOnboarding으로 게이트를 우회한다(안내가 서버 CLI 단계라 웹 버튼이 없다)", () => {
    expect(REGISTRY["restore-drills"].forceOnboarding).toBe(true);
    expect(REGISTRY["restore-drills"].create).toBeFalsy();
    expect((REGISTRY["restore-drills"].headerActions || []).some((a) => a.primary)).toBe(false);
  });
});

/* P-88 — 주 머리 동작에 `when(ctx)` 가 걸려 있으면 게이트도 그 조건을 본다. 관리 알림의
 * 「모두 읽음」이 그 조합이다: 읽을 것이 없으면 단추가 없고, 그때 절차 안내도 없어야 한다. */
describe("canOnboardFor — primary + when 은 지금 보이는 단추만 센다", () => {
  const cfg = REGISTRY["admin-notifications"];
  const readAll = (cfg.headerActions || []).find((a) => a.label === "모두 읽음");

  it("관리 알림의 「모두 읽음」은 primary 이고 when 을 갖는다(이 시험의 전제)", () => {
    expect(readAll.primary).toBe(true);
    expect(typeof readAll.when).toBe("function");
    expect(cfg.create).toBeFalsy();
  });

  it("읽을 것이 있으면 참, 없으면 거짓 — 맥락을 모르면 거짓", () => {
    expect(canOnboardFor(cfg, "admin", { unreadCount: 3 })).toBe(true);
    expect(canOnboardFor(cfg, "admin", { unreadCount: 0 })).toBe(false);
    expect(canOnboardFor(cfg, "admin")).toBe(false);
  });

  it("반례: when 이 없는 primary(백업 실행)는 맥락 없이도 역할만으로 참이다", () => {
    expect(canOnboardFor(REGISTRY.backup, "system_admin")).toBe(true);
    expect(canOnboardFor(REGISTRY.backup, "operator")).toBe(false);
  });
});
