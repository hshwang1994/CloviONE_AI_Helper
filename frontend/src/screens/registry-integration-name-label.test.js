import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* WF1 R2 재검증(admin_integration-detail) — name은 app/integrations/discovery.py의
 * idempotency 조회 키 겸 systemd 유닛 이름이라 슬러그 그대로 저장된다(예:
 * "claude-request-interpreter"). 이 값이 목록 열에도, 상세 드로어 제목(declaredRowName이
 * rowName을 그대로 쓴다)에도 그대로 샜다 — ops 화면(Diagnostics.jsx 등)이 이미 쓰는
 * opsHelpers.js::serviceLabel()로 알려진 4종은 사람이 읽는 이름으로, 그 밖은 kebab/snake
 * 자동 정리로 보여준다. 저장된 값 자체는 안 바꾼다(discovery.py 재실행 idempotency 등
 * 다른 로직이 참조한다) — 표시만 고친다.
 */
function findCol(key) {
  return REGISTRY.integrations.columns.find((c) => c.key === key);
}

describe("연동 목록 — '이름' 열이 슬러그 대신 사람이 읽는 이름을 보여준다 (WF1 R2)", () => {
  it("알려진 슬러그는 SERVICE_LABELS의 한국어 이름으로 보인다", () => {
    const col = findCol("name");
    expect(col.render({ name: "claude-request-interpreter" })).toBe("요청 해석기");
    expect(col.render({ name: "claude-ticket-runner" })).toBe("티켓 러너");
    expect(col.render({ name: "clovirone-work-assistant" })).toBe("업무 도우미");
    expect(col.render({ name: "n8n" })).toBe("n8n 엔진");
  });

  it("관리자가 자유 텍스트로 등록한 이름(알려진 4종 밖)은 그대로 보인다", () => {
    const col = findCol("name");
    expect(col.render({ name: "사내 결제 시스템" })).toBe("사내 결제 시스템");
  });

  it("알려진 4종 밖의 kebab-case 슬러그는 Title Case로 다듬어 보인다(원시 하이픈 노출 방지)", () => {
    const col = findCol("name");
    expect(col.render({ name: "custom-billing-service" })).toBe("Custom Billing Service");
  });

  it("상세 드로어 제목(rowName)도 같은 이름을 쓴다 — 슬러그가 모달 제목으로 새지 않는다", () => {
    const col = findCol("name");
    expect(col.rowName({ name: "claude-request-interpreter" })).toBe("요청 해석기");
  });
});
