import { describe, it, expect } from "vitest";

import { REGISTRY } from "../registry.js";
import { actionKo } from "../../lib/format.js";

/* RG-05: 승인 큐는 서버 페이지네이션(paginated:true)인데 필터가 status 하나뿐이었다.
 * 서버(app/approvals/router.py)는 request_type/requested_by도 쿼리 파라미터로 받는데
 * 화면이 그 둘을 안 쓰고 있었다 — 5종 요청 유형이 섞인 큐를 종류·요청자로 좁힐 방법이
 * 없었다. clientFilter로는 "지금 페이지 안"까지만 걸러지므로 반드시 서버 필터여야 한다.
 */
describe("RG-05 — 승인 큐가 request_type/requested_by 서버 필터를 쓴다", () => {
  const filters = REGISTRY.approvals.filters;

  it("request_type 필터가 서버로 간다(clientFilter가 아니다)", () => {
    const f = filters.find((x) => x.key === "request_type");
    expect(f, "request_type 필터가 없다").toBeTruthy();
    expect(f.clientFilter, "clientFilter면 지금 페이지 안까지만 걸러져 부정확하다").toBeFalsy();
    expect(f.type).toBe("select");
  });

  it("request_type 옵션이 실제 등록된 5개 요청 유형과 일치하고, 목록 열과 같은 라벨(actionKo)을 쓴다", () => {
    const f = filters.find((x) => x.key === "request_type");
    const values = f.options.map((o) => o.value).sort();
    expect(values).toEqual(
      ["document.publish", "integration.change_config", "runner.change_config", "schedule.enable", "user.role_change"].sort(),
    );
    for (const o of f.options) {
      expect(o.label).toBe(actionKo(o.value));
    }
  });

  it("requested_by 필터가 서버로 가는 자유 텍스트 ID 필터다", () => {
    const f = filters.find((x) => x.key === "requested_by");
    expect(f, "requested_by 필터가 없다").toBeTruthy();
    expect(f.clientFilter).toBeFalsy();
    expect(f.type).toBe("text");
  });
});
