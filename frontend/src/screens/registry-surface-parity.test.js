/* W0: ROUTE_COVERAGE.json 이 REGISTRY·TAB_GROUPS·TAB_DEFS 를 실제로 전부 담고 있는가.
 *
 * ## 왜 Python Gate 가 아니라 여기인가
 *
 * `scripts/check_ui_renewal_coverage.py` 는 소스 진실 다섯 개로 커버리지를 검증하는데,
 * 그중 REGISTRY 키만은 Python 정규식으로 읽을 수 없다. 계획 세션에서 실제로 시도했다 —
 * 7개 도메인 파일을 정규식으로 훑자 28개 중 1개를 **조용히** 놓쳤다. 놓친 키는 커버리지에
 * 없어도 Gate 가 초록이 된다. 검사가 없는 것보다 나쁜 상태다.
 *
 * REGISTRY 는 JS 객체 조립(스프레드 · 계산된 키 · 조건부 병합)의 결과라서, 그걸 정확히
 * 아는 유일한 도구는 JS 자신이다. 그래서 이 대조만 Vitest 로 옮긴다 —
 * **JS 진실은 JS 가 증명한다.**
 *
 * ## 무엇을 고정하는가
 *
 *  ① REGISTRY 의 모든 키가 ROUTE_COVERAGE 의 어떤 Surface 로든 도달 가능하다
 *     (단일 Route `/key` 이거나, TAB_GROUPS 그릇 안의 탭이거나, OrgConsole 이 그린다)
 *  ② TAB_GROUPS 의 모든 그릇과 탭이 Surface 로 존재한다
 *  ③ SettingsShell 의 TAB_DEFS 세 탭이 Surface 로 존재한다
 *  ④ 반대로 ROUTE_COVERAGE 가 registry_key 를 주장하는 Surface 는 실제 REGISTRY 키다
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { REGISTRY } from "./registry.js";
import { NOTIFICATIONS_SCREEN } from "./registry/notifications.js";
import { TAB_GROUPS, ORG_CONSOLE_KEYS } from "../app/AdminRoutes.jsx";
import { SETTINGS_TAB_KEYS } from "./settings/SettingsShell.jsx";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COVERAGE = path.resolve(HERE, "../../../docs/ui-renewal/ROUTE_COVERAGE.json");

const coverage = JSON.parse(fs.readFileSync(COVERAGE, "utf-8"));
const surfaces = coverage.surfaces || [];

/** 쿼리를 뗀 경로. 탭 Surface 는 `/backup?tab=restore-drills` 로 등록된다. */
const base = (r) => String(r || "").split("?")[0];
const routes = new Set(surfaces.map((s) => base(s.route)));
const surfaceIds = new Set(surfaces.map((s) => s.id));

/** 이 registry 키를 그리는 Surface 가 커버리지에 있는가 (직접 Route 또는 탭). */
function reachable(key) {
  if (routes.has("/" + key)) return true;
  for (const g of TAB_GROUPS) {
    if (g.tabs.some((t) => t.key === key) && routes.has(g.path)) return true;
  }
  return false;
}

describe("ROUTE_COVERAGE ↔ JS 소스 대조", () => {
  it("REGISTRY 키가 전부 Surface 로 도달 가능하다", () => {
    const keys = Object.keys(REGISTRY);
    expect(keys.length).toBeGreaterThan(20); // 파싱 사고 감지 — 빈 객체로 통과하지 않게
    const orphan = keys.filter((k) => !ORG_CONSOLE_KEYS.includes(k) && !reachable(k));
    expect(orphan, `커버리지에 없는 REGISTRY 키: ${orphan.join(", ")}`).toEqual([]);
  });

  it("OrgConsole 이 그리는 키도 Surface 가 있다", () => {
    const orphan = ORG_CONSOLE_KEYS.filter((k) => !routes.has("/" + k));
    expect(orphan, `조직 콘솔 키가 커버리지에 없다: ${orphan.join(", ")}`).toEqual([]);
  });

  it("TAB_GROUPS 의 그릇과 탭이 전부 Surface 다", () => {
    expect(TAB_GROUPS.length).toBeGreaterThan(0);
    const missing = [];
    for (const g of TAB_GROUPS) {
      if (!routes.has(g.path)) missing.push(g.path);
      for (const t of g.tabs) {
        // 탭 본문 Surface 는 `<그릇>?tab=<키>` 로 등록한다.
        const want = `${g.path}?tab=${t.key}`;
        if (!surfaces.some((s) => s.route === want)) missing.push(want);
        // 옛 주소는 리다이렉트가 아니라 제자리 렌더라 그것도 Surface 다.
        if ("/" + t.key !== g.path && !routes.has("/" + t.key)) missing.push("/" + t.key);
      }
    }
    expect(missing, `커버리지에 없는 탭 그릇/탭: ${missing.join(", ")}`).toEqual([]);
  });

  it("설정 탭 세 개가 전부 Surface 다", () => {
    expect(SETTINGS_TAB_KEYS).toContain("policy");
    const missing = SETTINGS_TAB_KEYS.filter(
      (k) => !surfaces.some((s) => s.route === `/settings?tab=${k}`),
    );
    expect(missing, `커버리지에 없는 설정 탭: ${missing.join(", ")}`).toEqual([]);
  });

  it("커버리지가 주장하는 registry_key 는 실재하는 키다", () => {
    // 사용자 콘솔의 `notifications` 는 REGISTRY 에 **일부러** 없다 — 두 콘솔이 같은 화면
    // 키를 공유하면 라우트가 겹쳐서 0060 이 갈라놨다(registry.js 주석). config 자체는 있다.
    const known = { ...REGISTRY, ...NOTIFICATIONS_SCREEN };
    const bogus = surfaces
      .filter((s) => s.registry_key && !(s.registry_key in known))
      .map((s) => `${s.id}→${s.registry_key}`);
    expect(bogus, `없는 registry 키를 가리킨다: ${bogus.join(", ")}`).toEqual([]);
  });

  it("커버리지 Surface id 가 중복되지 않는다", () => {
    expect(surfaceIds.size).toBe(surfaces.length);
  });
});
