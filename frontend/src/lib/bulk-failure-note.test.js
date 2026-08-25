/* 일괄 작업의 실패 사유를 **그대로** 말한다 (UA-25).
 *
 * qa-contract-replaced-by: frontend/src/screens/teamdocs-bulk-failure-reason.test.jsx
 *
 * 예전에는 화면마다 이 문구를 각자 만들었고, 전부 실제 사유와 무관하게 「권한이 없어
 * 건너뛰었습니다」였다 — Notion 장애일 때 관리자가 이 문구만 보고 더 높은 권한의 계정으로
 * 헛되이 재시도했다. 옛 문서 화면의 그 시험은 화면이 사라지며 함께 지웠고, 계약은 여기로
 * 내려왔다: 문구를 만드는 곳이 `lib/format.js::bulkFailureNote` 하나뿐이라 여기서 지키면
 * 그 함수를 쓰는 화면 전부에서 지켜진다.
 */
import { describe, it, expect } from "vitest";
import { bulkFailureNote } from "./format.js";

/* UA-25 — 일괄 실패 사유가 항상 "권한이 없어"로 뭉개져, Notion 장애로 실패해도
 * 권한 문제로 보여 관리자가 다른 계정으로 헛되이 재시도했다. 백엔드가 이미 건별로
 * 돌려주는 실제 사유(failed[].error)를 그대로 보여주는지 확인한다. */

describe("bulkFailureNote", () => {
  it("실패가 없으면 빈 문자열이다", () => {
    expect(bulkFailureNote([])).toBe("");
    expect(bulkFailureNote(null)).toBe("");
    expect(bulkFailureNote(undefined)).toBe("");
  });

  it("실제 사유를 그대로 보여준다 — 권한이 아니어도(Notion 실패) 권한 문구로 뭉개지 않는다", () => {
    const note = bulkFailureNote([{ id: "a", error: "원본을 보관처리하지 못했습니다. 잠시 후 다시 시도하세요." }]);
    expect(note).toContain("원본을 보관처리하지 못했습니다");
    // 서버가 더 이상 못 내는 문구다 — 화면이 옛 문자열을 어딘가에 박아 두지 않았는지 함께 본다.
    expect(note).not.toContain("노션");
    expect(note).not.toContain("권한이 없");
  });

  it("이미 처리된 항목도 실제 사유(권한 아님)를 보여준다", () => {
    const note = bulkFailureNote([{ id: "a", error: "이미 처리된 항목입니다." }]);
    expect(note).toContain("이미 처리된 항목입니다");
  });

  it("건수를 실제 실패 개수로 말한다", () => {
    const note = bulkFailureNote([
      { id: "a", error: "이미 처리된 항목입니다." },
      { id: "b", error: "이 항목을 복원하거나 지울 권한이 없습니다." },
    ]);
    expect(note).toContain("2건은 건너뛰었습니다");
  });

  it("사유가 섞이면 첫 번째만 보여준다(UsersBulk.jsx와 같은 관용)", () => {
    const note = bulkFailureNote([
      { id: "a", error: "첫 사유" },
      { id: "b", error: "두 번째 사유" },
    ]);
    expect(note).toContain("첫 사유");
    expect(note).not.toContain("두 번째 사유");
  });

  it("error 필드가 없으면 안전한 기본 문구로 대체한다", () => {
    const note = bulkFailureNote([{ id: "a" }]);
    expect(note).toContain("1건은 건너뛰었습니다");
  });
});
