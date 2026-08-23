import { describe, it, expect } from "vitest";
/* 링크 활성화 판정의 정본은 `app/navConfig.js` 한 곳이다 — 예전에는 Dashboard.jsx 가
   자기 표를 들고 있었고 그 표가 정본과 갈라져 있었다(아래 describe 참고, 지시 21). */
import { canReach as canGo } from "../app/navConfig.js";
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

/* 링크 활성화 판정 (지시 21).
 *
 * 이 화면은 예전에 `NAV_ROLES` 라는 **두 번째** 권한표를 갖고 있었고, 그 표가 정본
 * (`app/navConfig.js::SCREEN_ROLES`)과 갈라져 있었다 — `/diagnostics` 를
 * `["admin","system_admin"]` 으로 적었지만 정본도, SPA 라우트 게이트도
 * (`AdminRoutes.jsx`), 백엔드도(`app/health/router.py` 의 `CONSOLE_OPS_ROLES`) `operator` 를
 * 허용한다. 그래서 운영자는 볼 수 있는 화면인데 대시보드에서 갈 방법이 없었다.
 *
 * 🔴 아래 `/diagnostics` 단언은 **뒤집혔다**. 예전 검사가 그 불일치를 그대로 못박고 있었다 —
 * 검사가 옳고 구현이 틀린 경우가 아니라, 검사가 틀린 값을 지키고 있던 경우다. */
describe("canGo — 정본 한 표에서 읽는다", () => {
  it("allows operator into /jobs but blocks auditor", () => {
    expect(canGo("/jobs", "operator")).toBe(true);
    expect(canGo("/jobs", "auditor")).toBe(false);
  });
  it("allows auditor into /audit", () => {
    expect(canGo("/audit", "auditor")).toBe(true);
  });
  it("운영자도 /diagnostics 에 간다 — 라우트·백엔드와 같은 집합이다", () => {
    expect(canGo("/diagnostics", "admin")).toBe(true);
    expect(canGo("/diagnostics", "operator")).toBe(true);
    expect(canGo("/diagnostics", "auditor")).toBe(false);
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
  it("쿼리가 붙은 주소도 같은 화면으로 본다 (/settings?tab=policy)", () => {
    // 유지보수 경보가 가리키는 곳이다 — 탭 단위 게이트는 그 화면이 따로 건다.
    expect(canGo("/settings?tab=policy", "operator")).toBe(true);
    expect(canGo("/settings?tab=policy", "user")).toBe(false);
  });
});


/* 머리 지표 넷 (6단계) — 맨 위 한 줄에서 끝나는 질문들.
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

  /* VIS-107R — failed_open_oldest_at 이 나이를 덧붙인다. 절대 날짜를 박으면 작성 다음 날부터
   * 썩는다(바로 위 ops-service-status.test.jsx 의 RECENT_BACKUP_AT 주석과 같은 함정) — 기준일을
   * 지금으로부터 상대로 잰다. */
  it("failed_open_oldest_at이 있으면 라벨에 나이를 덧붙인다", () => {
    const oldAt = new Date(Date.now() - 21 * 86400000).toISOString().replace(/\.\d+Z$/, "");
    const withAge = { ...ARGS, jobs: { success_rate_pct: 72, failed_open: 2, failed_open_oldest_at: oldAt } };
    const label = headlineStats(withAge).find((x) => x.key === "failed").label;
    expect(label).toContain("21일 전");
  });

  it("failed_open_oldest_at이 없으면(서버가 아직 안 주는 옛 응답 포함) 나이를 안 붙인다", () => {
    const label = headlineStats(ARGS).find((x) => x.key === "failed").label;
    expect(label).toBe("미해결 실패 작업");
  });

  it("넷 전부 어디로 갈지(또는 갈 곳 없음)를 분명히 정한다", () => {
    const t = headlineStats(ARGS);
    // S11 이 '활성 워크플로' 타일을 걷어냈다 — 그 화면이 없어졌다.
    expect(t).toHaveLength(4);
    expect(t.map((x) => x.key)).toEqual(["services", "rate", "failed", "disk"]);
    // 서비스 타일은 이 화면 자체가 상세라 이동 대상이 없다(막다른 클릭을 만들지 않는다).
    expect(t.find((x) => x.key === "services").to).toBeNull();
    expect(t.filter((x) => x.key !== "services").every((x) => !!x.to)).toBe(true);
  });
});

/* PA-RC-0018 REBUILD — buildAlerts()/dashboardNav()는 DashboardBody 렌더 안에 있던 로직을
 * 값 자체만 대조할 수 있게 그대로 옮긴 것이다(acceptance criteria 8: 재구축 전후 계산이
 * 동일해야 한다). 임계값 하나하나는 원본 로직을 한 글자도 바꾸지 않았다 — 이 테스트는
 * "다시 짠 게 아니라 옮긴 것"을 값으로 증명한다. */
import { buildAlerts, dashboardNav } from "./Dashboard.jsx";

describe("dashboardNav — 역할별 이동 대상", () => {
  it("admin/system_admin은 진단·작업 큐 모두 간다", () => {
    const n = dashboardNav("admin");
    expect(n).toEqual({ diagTo: "/diagnostics", procTo: "/diagnostics", jobsTo: "/jobs", diagNote: "", jobsNote: "", procNote: "" });
  });
  it("operator도 진단·작업 큐 모두 간다 (지시 21 — 정본 표와 같은 집합)", () => {
    /* 🔴 뒤집힌 단언이다. 예전에는 이 화면만의 두 번째 권한표가 `/diagnostics` 를
       admin+ 로 좁혀 놨고, 검사가 그 불일치를 그대로 못박고 있었다. 정본
       (`SCREEN_ROLES.diagnostics`)·SPA 라우트 게이트(`AdminRoutes.jsx`)·백엔드
       (`app/health/router.py` 의 `CONSOLE_OPS_ROLES`) 셋 다 운영자를 허용한다 —
       장애 대응 중인 운영자가 볼 수 있는 화면인데 대시보드에서 갈 방법이 없었다. */
    const n = dashboardNav("operator");
    expect(n.diagTo).toBe("/diagnostics");
    expect(n.procTo).toBe("/diagnostics");
    expect(n.jobsTo).toBe("/jobs");
    expect(n.diagNote).toBe("");
    expect(n.jobsNote).toBe("");
  });
  it("auditor는 진단·작업 큐 둘 다 못 가 procTo도 undefined다", () => {
    const n = dashboardNav("auditor");
    expect(n.diagTo).toBeUndefined();
    expect(n.procTo).toBeUndefined();
    expect(n.jobsTo).toBeUndefined();
    expect(n.jobsNote).toBe(", 관리자 문의");
  });
});

describe("buildAlerts — 조치 대기 목록의 값(원본 로직 그대로)", () => {
  it("빈 payload·역할이면 경보가 없다", () => {
    expect(buildAlerts({}, "admin")).toEqual([]);
  });

  it("유지보수 모드는 danger, 설정의 정책 탭으로 보낸다", () => {
    /* 예전 목적지는 `/maintenance` 였다 — 지금은 `/settings?tab=policy` 로 접힌 옛 주소라
       (AdminRoutes.jsx) 링크가 한 번 튕겨 보내는 셈이었다. 실제 목적지를 가리킨다. */
    const a = buildAlerts({ maintenance: true }, "admin");
    expect(a).toEqual([{ src: "maintenance", label: "유지보수 모드", value: "활성", kind: "danger", to: "/settings?tab=policy" }]);
  });

  it("실패 작업은 danger, 대기 작업은 warn이다", () => {
    const a = buildAlerts({ jobs_24h: { failed_open: 5, queued: 2 } }, "admin");
    expect(a.find((x) => x.src === "job:failed")).toMatchObject({ value: "5", kind: "danger", to: "/jobs" });
    expect(a.find((x) => x.src === "job:queued")).toMatchObject({ value: "2", kind: "warn", to: "/jobs" });
  });

  it("성공률은 80/95% 경계로 danger/warn/무경보가 갈린다(끝난 작업이 있을 때만)", () => {
    const at = (pct) => buildAlerts({ jobs_24h: { success_rate_pct: pct, total: 10 } }, "admin").find((x) => x.src === "job:rate");
    expect(at(70).kind).toBe("danger");
    expect(at(85).kind).toBe("warn");
    expect(at(99)).toBeUndefined();
    // 끝난 작업이 0건이면(전부 대기/실행 중) 분모가 없어 경보를 만들지 않는다.
    expect(buildAlerts({ jobs_24h: { success_rate_pct: 10, total: 0 } }, "admin").find((x) => x.src === "job:rate")).toBeUndefined();
  });

  it("워커/스케줄러는 down이면 danger, unknown이면 warn이다", () => {
    const a = buildAlerts({ components: { worker: "down", scheduler: "unknown" } }, "admin");
    expect(a.find((x) => x.src === "comp:worker")).toMatchObject({ value: "중단", kind: "danger" });
    expect(a.find((x) => x.src === "comp:scheduler")).toMatchObject({ value: "응답 없음", kind: "warn" });
  });

  it("비활성화된 연동은 down이어도 경보를 만들지 않는다", () => {
    const a = buildAlerts({ integrations: { n8n: { enabled: false, last_health: "down" } } }, "admin");
    expect(a.find((x) => x.src === "integ:n8n")).toBeUndefined();
  });

  it("활성 연동이 down이면 danger, /integrations로 보낸다", () => {
    const a = buildAlerts({ integrations: { n8n: { enabled: true, last_health: "down" } } }, "admin");
    expect(a.find((x) => x.src === "integ:n8n")).toMatchObject({ label: expect.any(String), value: "중단", kind: "danger", to: "/integrations" });
  });

  it("마지막 백업 없음/오래됨은 system_admin에게만 뜬다(캔 액트 없는 경보를 상시 띄우지 않는다)", () => {
    expect(buildAlerts({}, "admin").find((x) => x.src === "backup")).toBeUndefined();
    expect(buildAlerts({}, "system_admin").find((x) => x.src === "backup")).toMatchObject({ value: "없음", kind: "danger", to: "/backup" });

    const staleAt = new Date(Date.now() - 10 * 86400000).toISOString(); // BACKUP_STALE_DAYS(7)보다 오래됨
    expect(buildAlerts({ last_backup_at: staleAt }, "admin").find((x) => x.src === "backup-stale")).toBeUndefined();
    const staleAlert = buildAlerts({ last_backup_at: staleAt }, "system_admin").find((x) => x.src === "backup-stale");
    expect(staleAlert).toMatchObject({ value: "10일 전", kind: "warn", to: "/backup" });
  });

  it("디스크는 85%부터 danger, 80%부터 warn — 메모리는 90%/80%다", () => {
    expect(buildAlerts({ disk: { used_pct: 85 } }, "admin").find((x) => x.src === "disk").kind).toBe("danger");
    expect(buildAlerts({ disk: { used_pct: 82 } }, "admin").find((x) => x.src === "disk").kind).toBe("warn");
    expect(buildAlerts({ disk: { used_pct: 79 } }, "admin").find((x) => x.src === "disk")).toBeUndefined();
    expect(buildAlerts({ memory: { used_pct: 90 } }, "admin").find((x) => x.src === "mem").kind).toBe("danger");
    expect(buildAlerts({ memory: { used_pct: 81 } }, "admin").find((x) => x.src === "mem").kind).toBe("warn");
  });

  it("여러 경보가 동시에 있으면 삽입 순서를 보존한다(정렬은 렌더 쪽 책임)", () => {
    const a = buildAlerts({
      maintenance: true,
      jobs_24h: { failed_open: 1, queued: 1 },
      disk: { used_pct: 90 },
    }, "admin");
    expect(a.map((x) => x.src)).toEqual(["maintenance", "job:failed", "job:queued", "disk"]);
  });
});
