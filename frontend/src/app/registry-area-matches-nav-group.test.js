import { describe, it, expect } from "vitest";

import { REGISTRY } from "../screens/registry.js";
import { NAV, groupForPath } from "./navConfig.js";

/* PA-RC-0031 후속 발견 — REGISTRY 화면의 `config.area`가 사이드바 그룹과 갈라질 수 있다.
 *
 * 관리자 콘솔은 `homeUser`가 항상 false라(`AppShell.jsx`) breadcrumb 뿌리가 `PA-RC-0039`의
 * `CrumbRootProvider`/`groupForPath` 유도를 안 타고 항상 리터럴 "관리자"다 — 그 다음 단계
 * (두 번째 breadcrumb 조각)는 `DataScreen.jsx`가 그리는 `config.area`, 즉 각 REGISTRY 화면
 * 설정에 손으로 적어 둔 값이다. `PA-RC-0031`이 사이드바 그룹만 옮기고(`navConfig.js`) 이
 * 손으로 적은 `area`는 안 건드린 화면이 4개 있었다(`복구 리허설`·`기능 플래그`·`공지 배너`·
 * `프롬프트 사용 통계`) — 사이드바는 새 그룹을 강조하는데 그 화면을 열면 breadcrumb는 옛
 * 그룹 이름을 계속 말했다. `nav-ia-taxonomy.test.js`/`crumb-root.test.jsx`는 둘 다
 * `navConfig.js`/합성 `PageHeader`만 검사해 이 어긋남을 못 잡았다 — 이 파일은 REGISTRY
 * 설정과 사이드바를 직접 교차 대조해 같은 종류의 드리프트가 다시 조용히 들어오지 못하게 한다.
 *
 * `groupForPath`는 사이드바 강조가 쓰는 바로 그 함수다(`activeNavPath` 재사용) — "지금 켜진
 * 메뉴"와 이 시험이 기대하는 답이 서로 다른 계산으로 갈라질 방법이 없다. */
describe("REGISTRY 화면의 area가 실제 사이드바 그룹과 일치한다 (PA-RC-0031 후속)", () => {
  const checked = [];
  for (const [key, config] of Object.entries(REGISTRY)) {
    if (!config.area) continue; // area 없는 설정(있다면)은 이 계약 밖 — 별도 문제.
    const group = groupForPath(NAV, "/" + key);
    if (group == null) continue; // 사이드바에 없는 화면(딥링크 전용 등)은 이 축으로 못 잰다.
    checked.push({ key, area: config.area, group });
  }

  it("이 시험 자체가 뭔가는 실제로 검사하고 있다(REGISTRY와 NAV 둘 다 비어 있지 않다)", () => {
    expect(Object.keys(REGISTRY).length).toBeGreaterThan(10);
    expect(checked.length).toBeGreaterThan(10);
  });

  it.each(checked.map((c) => [c.key, c.area, c.group]))(
    "%s: config.area(%s)가 사이드바 그룹(%s)과 같다",
    (key, area, group) => {
      expect(area, `${key}의 config.area("${area}")가 사이드바 그룹("${group}")과 다르다 — breadcrumb과 사이드바가 서로 다른 그룹을 말한다`).toBe(group);
    },
  );
});
