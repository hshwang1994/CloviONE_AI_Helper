import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* WF1 R5 — 문서 자동 생성 화면의 빈 상태에서 쓰기 역할(admin/system_admin)은 같은 문장
 * ("'+ 문서 생성'으로 워크플로와 기간을 지정하면...")을 세 번 읽었다: 상시 안내 배너(help,
 * 항상 보임) → emptyHelp → emptySteps[0](DataScreen.jsx가 canOnboard일 때만 situation/
 * prerequisite/steps/expected를 함께 보여준다 — 그 구조가 이미 "무엇을 할지"를 말한다).
 * 읽기 전용 역할(operator/auditor)은 그 4단 구조 자체가 안 보이므로 emptyHelp가 유일한
 * 안내라 그대로 남긴다.
 */
describe("문서 자동 생성 — 빈 상태 안내가 상시 배너·단계 목록과 반복되지 않는다", () => {
  const config = REGISTRY.documents;

  it("쓰기 역할에게는 emptyHelp를 따로 보여주지 않는다(situation/steps가 이미 안내한다)", () => {
    expect(config.emptyHelp("admin")).toBeFalsy();
    expect(config.emptyHelp("system_admin")).toBeFalsy();
  });

  it("읽기 전용 역할에게는 emptyHelp가 여전히 유일한 안내다", () => {
    expect(config.emptyHelp("operator")).toBe("문서 생성 권한이 있는 관리자가 생성하면 여기에 기록이 남습니다.");
    expect(config.emptyHelp("auditor")).toBe("문서 생성 권한이 있는 관리자가 생성하면 여기에 기록이 남습니다.");
  });

  it("상시 배너(help)와 빈 상태 첫 단계(emptySteps[0])는 여전히 '+ 문서 생성' 안내를 담고 있다", () => {
    // emptyHelp를 지워도 정보가 사라지지 않는다는 것을 함께 확인한다.
    expect(config.help).toContain("문서 생성");
    expect(config.emptySteps[0]).toContain("문서 생성");
  });
});

/* DGEN-02: "워크플로가 등록돼 있어야 한다"는 문구만으로는, 채팅용(AI 업무 도우미)이나
 * Notion 매핑용 워크플로가 이미 있는 설치의 관리자가 "워크플로는 있는데 왜 안 되지"로
 * 헤맬 수 있었다 — 문서 생성은 그 워크플로들과 무관한 별도 워크플로가 필요하다는 사실
 * 자체를 말하지 않았다. */
describe("문서 자동 생성 — 빈 상태가 '워크플로는 있는데 왜 안 되지'를 막는다 (DGEN-02)", () => {
  const config = REGISTRY.documents;

  it("emptyPrerequisite가 채팅·Notion 매핑용 워크플로와는 별개라고 명시한다", () => {
    expect(config.emptyPrerequisite).toContain("채팅");
    expect(config.emptyPrerequisite).toContain("Notion 매핑");
    expect(config.emptyPrerequisite).toContain("별개");
  });

  it("워크플로 목록으로 이동하는 링크가 여전히 있다(별개라는 사실을 안 뒤 바로 확인할 수 있게)", () => {
    expect(config.emptyRelatedLink).toEqual({ href: "#/workflows", label: "먼저: 워크플로 등록으로 이동" });
  });
});
