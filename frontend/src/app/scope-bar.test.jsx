/* 스코프 바 — 지금 보는 범위를 화면이 말한다 (S4 / A8 → 0060).
 *
 * 범위를 실제로 걸면 목록이 좁아지는데, **왜 좁아졌는지 화면이 말하지 않으면** 사용자는
 * "왜 이것만 보이지" 를 알 수 없고 그건 결함으로 신고된다.
 *
 * 0060 에서 두 가지가 바뀐다:
 *
 *  1. **축이 화면에 따라 다르다.** 관리 화면(`/users` 등)에서 목록을 좁히는 것은 *관리
 *     범위*이고, 그 밖의 범위 화면에서 좁히는 것은 *내 소속*이다. 한 문구로 뭉치면 부서
 *     관리자가 자기 소속을 관리 범위로 착각한다.
 *  2. **소속 미지정은 반드시 말한다.** 예전에는 그 상태가 곧 전역(전부 보임)이라 말할
 *     것이 없었지만, 이제는 아무것도 못 보는 상태다 — 증상이 "목록이 비어 있음" 이라
 *     이 안내가 없으면 원인을 찾을 방법이 없다.
 */
import { describe, it, expect } from "vitest";
import { scopeSummary } from "./ScopeBar.jsx";

const CLOVIR = [{ id: "d1", name: "브로드컴사업본부" }, { id: "d2", name: "ClovirONE팀" }];

describe("범위 요약 — 사용자 화면(조회 범위)", () => {
  it("일반 사용자는 자기 소속을 **경로로** 말한다", () => {
    // 이름 하나('ClovirONE팀')만으로는 어느 줄기인지 알 수 없고, 조직 개편으로 같은 이름이
    // 다른 자리에 생기면 구분이 아예 불가능해진다.
    expect(scopeSummary({ department_path: CLOVIR }, "/projects")).toEqual({
      label: "내 소속", detail: "브로드컴사업본부 › ClovirONE팀", tone: "info",
    });
  });

  it("소속 미지정이면 **경고한다** — 그 계정은 조직 데이터를 아무것도 못 본다", () => {
    const s = scopeSummary({ membership_kind: "unassigned", department_path: [] }, "/projects");
    expect(s.label).toBe("소속 미지정");
    expect(s.tone).toBe("warn");
  });

  it("조직 직속은 조직 이름을 말한다", () => {
    expect(scopeSummary({
      membership_kind: "organization", department_path: [],
      organization: { id: "o1", name: "굿모닝아이텍" },
    }, "/projects")).toEqual({ label: "소속", detail: "굿모닝아이텍", tone: "info" });
  });

  it("전체 범위 관리자에게는 띄우지 않는다 — 모든 화면 위의 '전체 포털'은 소음이다", () => {
    expect(scopeSummary({ management: { kind: "global" } }, "/projects")).toBeNull();
    expect(scopeSummary({ management: { kind: "global" } }, "/users")).toBeNull();
  });
});

describe("범위 요약 — 관리 화면(관리 범위)", () => {
  it("부서 관리자는 **배정받은 관리 범위**를 말한다 — 본인 소속 부서가 아니다", () => {
    // 관리자가 자기 부서와 다른 부서를 관리 범위로 배정받을 수 있다. 우연히 같은 문자열일
    // 때만 예전 코드가 맞아 보였다.
    expect(scopeSummary({
      department_path: [{ id: "x", name: "본인 소속 부서" }],
      management: { kind: "dept", path: CLOVIR },
    }, "/users")).toEqual({
      label: "관리 범위", detail: "브로드컴사업본부 › ClovirONE팀", tone: "info",
    });
  });

  it("같은 사람이 사용자 화면에서는 **내 소속**을 본다 — 두 축을 섞지 않는다", () => {
    expect(scopeSummary({
      department_path: [{ id: "x", name: "본인 소속 부서" }],
      management: { kind: "dept", path: CLOVIR },
    }, "/projects")).toEqual({
      label: "내 소속", detail: "본인 소속 부서", tone: "info",
    });
  });

  it("대상 부서가 없으면 그 사실을 말한다 — 그 계정은 아무것도 관리할 수 없다", () => {
    const s = scopeSummary({ management: { kind: "dept", path: [] } }, "/users");
    expect(s.detail).toBe("지정된 부서 없음");
    expect(s.tone).toBe("warn");
  });

  it("조직 관리자는 배정받은 조직 이름을 말한다", () => {
    expect(scopeSummary({
      management: { kind: "org", org: { id: "o1", name: "goodmit" } },
    }, "/users")).toEqual({ label: "관리 범위", detail: "goodmit", tone: "info" });
  });

  it("대상 조직이 없으면 그 사실을 말한다", () => {
    const s = scopeSummary({ management: { kind: "org", org: null } }, "/users");
    expect(s.detail).toBe("지정된 조직 없음");
    expect(s.tone).toBe("warn");
  });
});

/* 문구도 축을 따라간다 — 두 축은 좁히는 방향이 다르다.
 *
 * 관리 범위는 자기 ∪ 후손만이라(위로 안 간다), 관리 화면에서 "상위 부서와 하위 부서 밖"
 * 이라고 쓰면 부서 관리자가 상위 부서 사람도 관리할 수 있다고 읽는다. 목록에는 안 나오니
 * 화면이 거짓말을 한 셈이 된다. */
describe("범위 밖 안내 문구", () => {
  it("관리 화면에서는 위로 올라가지 않는다고 말한다", async () => {
    const { caveatFor } = await import("./ScopeBar.jsx");
    expect(caveatFor("/users")).toContain("이 부서와 하위 부서 밖");
    expect(caveatFor("/users")).not.toContain("상위 부서");
  });

  it("조회 화면에서는 상위 부서도 보인다고 말한다", async () => {
    const { caveatFor } = await import("./ScopeBar.jsx");
    expect(caveatFor("/projects")).toContain("상위 부서와 하위 부서 밖");
  });
});
