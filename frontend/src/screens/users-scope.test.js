/* 관리 범위 표시 (F2).
 *
 * 범위가 `dept`/`org` 인데 대상이 비어 있으면 **그 사람은 아무것도 못 본다.** 저장 경계에서
 * 막지만(app/users/service.py `_apply_admin_scope`), 예전 데이터나 CLI 로 들어온 값이 있을 수
 * 있다. 그 상태를 화면이 "소속 부서" 라고만 쓰면 관리자는 계정이 멀쩡하다고 믿고, 당사자는
 * "목록이 비어요" 라고 신고한다 — 원인을 찾을 단서가 없는 전형적인 조용한 실패다.
 */
import { describe, it, expect } from "vitest";
import { scopeLabel } from "./Users.jsx";

const DEPTS = { options: [{ value: "d1", label: "ClovirONE팀" }] };

describe("관리 범위 라벨", () => {
  it("개발자 말이 아니라 '무엇을 볼 수 있는가'로 쓴다", () => {
    expect(scopeLabel({ admin_scope: "global" }, DEPTS)).toBe("전체 포털");
  });

  it("부서 범위는 어느 부서인지 이름으로 말한다", () => {
    expect(scopeLabel({ admin_scope: "dept", scope_dept_id: "d1" }, DEPTS))
      .toBe("소속 부서(하위 포함): ClovirONE팀");
  });

  it("대상 없는 부서 범위를 조용히 넘기지 않는다", () => {
    const out = scopeLabel({ admin_scope: "dept", scope_dept_id: null }, DEPTS);
    expect(out).toMatch(/아무것도 보이지 않습니다/);
  });

  it("대상 없는 조직 범위도 마찬가지다", () => {
    expect(scopeLabel({ admin_scope: "org" }, DEPTS)).toMatch(/아무것도 보이지 않습니다/);
  });

  it("값이 없으면 전체 포털로 읽는다 — 모델 기본값과 같다", () => {
    expect(scopeLabel({}, DEPTS)).toBe("전체 포털");
  });

  it("이름을 못 찾으면 id 라도 보인다 — 빈 칸으로 두지 않는다", () => {
    expect(scopeLabel({ admin_scope: "dept", scope_dept_id: "사라진id" }, DEPTS))
      .toBe("소속 부서(하위 포함): 사라진id");
  });
});
