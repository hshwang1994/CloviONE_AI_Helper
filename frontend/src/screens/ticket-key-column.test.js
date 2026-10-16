/* 티켓 번호 열의 폭은 번호 길이가 정한다 (D-529 · r23 캡처 01).
 *
 * 그리는 함수(`render`)만 있는 열은 열 계획이 값을 재지 않는다(`ui/columnPlan.js::columnValueText` — 그리는 함수의 글은 화면 글이
 * 아닐 수 있어 재지 않는 것이 계약이고 `ui/plan-columns.test.js` 가 그것을 못박는다). 그래서 티켓 번호 열이 `value` 없이
 * `render` 만 가졌을 때는 바닥(6.5rem)에 머물러, 홈 지연 표에서 접두가 긴 번호가 「SXDNMW...」처럼 잘렸다. 열이 그리는 글을
 * `value` 로도 말하면 번호 길이가 폭을 정한다.
 */
import { describe, expect, it } from "vitest";
import { ticketColumns } from "./MyTickets.jsx";
import { columnSpec } from "../ui/columnPlan.js";

describe("티켓 번호 열", () => {
  it("그리는 번호를 value 로도 말하고, 긴 번호면 열 바닥이 그만큼 넓어진다", () => {
    const col = ticketColumns({ compact: true }).find((c) => c.key === "tid");
    expect(col.value({ key: "SXDNMWQ-12" })).toBe("SXDNMWQ-12");
    const short = columnSpec(col, { rows: [{ key: "AB-1" }] });
    const long = columnSpec(col, { rows: [{ key: "SXDNMWQXYZ-1234" }] });
    expect(long.min).toBeGreaterThan(short.min);
  });
});

describe("티켓 제목 칸", () => {
  it("제목이 티켓을 여는 표만 opensRow 를 말한다 — 숨긴 열 안내가 「행을 열면」을 고를 근거다(r23 #48)", () => {
    expect(ticketColumns({ onOpen: () => {} }).find((c) => c.key === "title").opensRow).toBe(true);
    expect(ticketColumns({}).find((c) => c.key === "title").opensRow).toBe(false);
  });
});
