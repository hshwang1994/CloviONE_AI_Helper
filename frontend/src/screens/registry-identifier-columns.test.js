import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { COLUMN_TYPES } from "../ui/columnTypes.js";

/* qa-contract-change: 관리자 표 규칙(D-501)으로 「제목」 · 「직책 이름」처럼 그 행의 이름인 열은 `identifier` 가 아니라 `type: "title"` 이다 — 제목 열은
   행을 식별하는 열(`COLUMN_TYPES.title.identifying`)이고 폭 보호도 더 세다(바닥 16rem, 남는 폭을 갖는다). 그래서 (1)이 세는 것을 「identifier:true 또는
   제목 열」로 넓힌다. 공지 배너 · 직책 관리가 그 이사를 했고, (2)의 두 화면 판정은 그대로다. */
/* qa-contract-change: 열 폭 배분(D-529)으로 짧은 이름 열(프롬프트 「사용처」 · AI 통계 「묶음」)이 제목이 아니라 이름 열이 됐다 — 이름 열도
   행을 식별하는 타입(`COLUMN_TYPES.name.identifying`)이라 (1)이 세는 것을 「identifier:true 또는 식별 타입(제목 · 이름 · 식별자 · 코드)」으로
   넓힌다. 세는 화면 목록과 (2)의 판정은 그대로다. */
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
  /* 행을 식별하는 열 — 옛 `identifier:true` 플래그이거나 제목 열(D-501). */
  function rowIdentifyingKeys(config) {
    return (config.columns || [])
      .filter((c) => c.identifier || (c.type && COLUMN_TYPES[c.type] && COLUMN_TYPES[c.type].identifying))
      .map((c) => c.key);
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

  it.each(shouldHaveIdentifier)("%s는 행을 식별하는 열(identifier:true 또는 제목 열)을 적어도 하나 갖는다", (key) => {
    expect(rowIdentifyingKeys(REGISTRY[key]).length, `${key}에 행을 식별하는 열이 없다`).toBeGreaterThan(0);
  });

  it("제목 열로 옮긴 화면은 그 열이 정말 제목 열이다 — 폭 보호를 잃지 않았다", () => {
    for (const key of ["announcements", "job-titles", "admin-notifications"]) {
      const titles = (REGISTRY[key].columns || []).filter((c) => c.type === "title");
      expect(titles.length, `${key}의 제목 열`).toBe(1);
    }
  });

  it("audit·jobs는 identifier를 안 쓴다 — PA-RC-0029가 실측으로 '잘림 0, 건드리지 않는다'로 확정한 화면이다", () => {
    expect(identifierKeys(REGISTRY.audit), "audit에 identifier가 생겼다 — 실측 없이 이 판정을 뒤집지 않는다").toEqual([]);
    expect(identifierKeys(REGISTRY.jobs), "jobs에 identifier가 생겼다 — 실측 없이 이 판정을 뒤집지 않는다").toEqual([]);
  });
});
