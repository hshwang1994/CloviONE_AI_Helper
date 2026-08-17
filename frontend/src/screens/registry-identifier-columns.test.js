import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* PA-RC-0029/0036/0037 후속 — 배경 감사가 발견한 것: `identifier` 열 최소 폭 메커니즘
 * (kit.jsx::colMinWidth, D-128)은 만들어졌지만 세 화면(Users/Offboarding/SettingsMain)에만
 * 적용됐다. REGISTRY의 나머지 화면 대다수가 "행을 식별하는 열이 이름·이메일인데 폭 보호가
 * 없다"는 같은 근본 원인을 그대로 갖고 있었다 — 그중 일부(러너 10열, notion-mapping의 이메일
 * 열)는 원래 `/users`를 고치게 만들었던 사례보다 열 수·값 길이가 더 나쁘다.
 *
 * 이 시험은 두 가지를 고정한다:
 * (1) 아래 목록의 각 화면이 실제로 `identifier:true` 열을 하나 갖고 있다 — 조용히 빠지는 회귀 방지.
 * (2) `/audit`·`/jobs`에는 **의도적으로** 없다 — `PA-RC-0029` 원 조사가 두 화면을 실측해
 *     "잘림 0, 건드리지 않는다"로 확정한 화면이다(BACKLOG.md PA3-11). 실측 없이 그 판정을
 *     뒤집으면 안 되므로, 누군가 "그냥 다 붙이자"며 이 두 화면에 identifier를 넣으면 이
 *     시험이 깨져서 그 판단을 다시 하게 만든다.
 */
describe("REGISTRY 화면의 identifier 열 적용 범위 (PA-RC-0029 후속 롤아웃)", () => {
  function identifierKeys(config) {
    return (config.columns || []).filter((c) => c.identifier).map((c) => c.key);
  }

  const shouldHaveIdentifier = [
    "users", "offboarding", // 기존(D-128) — Users.jsx/Offboarding.jsx는 REGISTRY 밖 별도 컴포넌트라
    // 여기 목록엔 없다(REGISTRY는 registry/*.js로 조립된 화면만 담는다) — 이 둘은 참고용 주석.
    "integrations", "runners", "workflows",
    "schedules", "documents",
    "organizations", "departments", "job-titles", "notion-mapping", "org-tree",
    "prompts", "policies", "templates", "prompt-usage", "policy-usage",
    "approval-delegations", "impersonation", "approvals", "audit-anomalies",
    "notifications", "announcements", "feature-flags", "ai-quotas",
  ].filter((k) => REGISTRY[k]); // users/offboarding처럼 REGISTRY에 없는 키는 걸러낸다.

  it.each(shouldHaveIdentifier)("%s는 identifier:true 열을 적어도 하나 갖는다", (key) => {
    expect(identifierKeys(REGISTRY[key]).length, `${key}에 identifier:true 열이 없다`).toBeGreaterThan(0);
  });

  it("audit·jobs는 identifier를 안 쓴다 — PA-RC-0029가 실측으로 '잘림 0, 건드리지 않는다'로 확정한 화면이다", () => {
    expect(identifierKeys(REGISTRY.audit), "audit에 identifier가 생겼다 — 실측 없이 이 판정을 뒤집지 않는다").toEqual([]);
    expect(identifierKeys(REGISTRY.jobs), "jobs에 identifier가 생겼다 — 실측 없이 이 판정을 뒤집지 않는다").toEqual([]);
  });
});
