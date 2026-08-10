import { describe, it, expect } from "vitest";
import { canGo } from "./Dashboard.jsx";
import { fmtCertDays } from "./ops/opsHelpers.js";

describe("fmtCertDays", () => {
  it("returns em-dash for null/undefined", () => {
    expect(fmtCertDays(null)).toBe("-");
    expect(fmtCertDays(undefined)).toBe("-");
  });
  it("returns 만료됨 for negative days", () => {
    expect(fmtCertDays(-5)).toBe("만료됨");
  });
  it("returns 오늘 만료 for exactly 0 days", () => {
    expect(fmtCertDays(0)).toBe("오늘 만료");
  });
  it("returns D-N for positive days", () => {
    expect(fmtCertDays(10)).toBe("D-10");
    expect(fmtCertDays(1)).toBe("D-1");
  });
});

describe("canGo (NAV role gating)", () => {
  it("allows operator into /jobs but blocks auditor", () => {
    expect(canGo("/jobs", "operator")).toBe(true);
    expect(canGo("/jobs", "auditor")).toBe(false);
  });
  it("allows auditor into /audit", () => {
    expect(canGo("/audit", "auditor")).toBe(true);
  });
  it("restricts /diagnostics to admin/system_admin", () => {
    expect(canGo("/diagnostics", "admin")).toBe(true);
    expect(canGo("/diagnostics", "operator")).toBe(false);
  });
  it("treats an unlisted path as unrestricted", () => {
    expect(canGo("/anything", "user")).toBe(true);
  });
  it("blocks a null role on a gated path", () => {
    expect(canGo("/diagnostics", null)).toBe(false);
  });
  it("opens /backup and /integrations to read roles including auditor", () => {
    expect(canGo("/backup", "auditor")).toBe(true);
    expect(canGo("/integrations", "auditor")).toBe(true);
  });
});


/* 머리 지표 다섯 (6단계) — 맨 위 한 줄에서 끝나는 질문들.
 *
 * 예전에는 같은 값들이 여섯 구역에 흩어져 있어 "지금 괜찮은가" 를 알려면 끝까지 스크롤하며
 * 여섯 번 찾아야 했다. 운영 화면에서는 매일 반복되는 비용이다.
 */
import { headlineStats, serviceMix as _mix } from "./Dashboard.jsx";

const ARGS = {
  services: { web: "up", worker: "up", scheduler: "down", n8n: "unknown" },
  counts: { active_workflows: 3 },
  jobs: { success_rate_pct: 72, failed_open: 2 },
  disk: { used_pct: 91 },
  jobsNote: "",
  diagTo: "/diagnostics",
  diagNote: "",
};

describe("머리 지표", () => {
  it("도넛과 **같은 계산**을 써서 두 곳이 다른 말을 할 수 없다", () => {
    const mix = _mix(ARGS.services);
    const up = mix.find((m) => m.label === "정상").value;
    const total = mix.reduce((a, m) => a + m.value, 0);

    const services = headlineStats(ARGS).find((t) => t.key === "services");
    expect(services.value).toBe(`${up} / ${total}`);
  });

  it("중단이 있으면 위험으로 표시한다 — 요약이 '정상'처럼 보이면 요약이 아니다", () => {
    expect(headlineStats(ARGS).find((t) => t.key === "services").kind).toBe("danger");
    const allUp = { ...ARGS, services: { web: "up", worker: "up" } };
    expect(headlineStats(allUp).find((t) => t.key === "services").kind).toBe("ok");
  });

  it("성공률과 디스크는 값에 따라 심각도가 바뀐다", () => {
    const t = headlineStats(ARGS);
    expect(t.find((x) => x.key === "rate").kind).toBe("danger");   // 72%
    expect(t.find((x) => x.key === "disk").kind).toBe("danger");   // 91%
    const calm = { ...ARGS, jobs: { success_rate_pct: 99, failed_open: 0 }, disk: { used_pct: 40 } };
    const c = headlineStats(calm);
    expect(c.find((x) => x.key === "rate").kind).toBe("ok");
    expect(c.find((x) => x.key === "disk").kind).toBeUndefined();
  });

  it("값이 없으면 0이 아니라 '-' 다 — 없는 것과 0은 다르다", () => {
    const empty = headlineStats({ ...ARGS, services: {}, jobs: {}, disk: {}, counts: {} });
    expect(empty.find((x) => x.key === "services").value).toBe("-");
    expect(empty.find((x) => x.key === "rate").value).toBe("-");
    expect(empty.find((x) => x.key === "disk").value).toBe("-");
  });

  it("다섯 개 전부 어디로 갈지(또는 갈 곳 없음)를 분명히 정한다", () => {
    const t = headlineStats(ARGS);
    expect(t).toHaveLength(5);
    expect(t.map((x) => x.key)).toEqual(["services", "workflows", "rate", "failed", "disk"]);
    // 서비스 타일은 이 화면 자체가 상세라 이동 대상이 없다(막다른 클릭을 만들지 않는다).
    expect(t.find((x) => x.key === "services").to).toBeNull();
    expect(t.filter((x) => x.key !== "services").every((x) => !!x.to)).toBe(true);
  });
});
