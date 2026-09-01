import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { COLUMN_TYPES } from "./columnTypes.js";

/* 🔴 **날짜와 시각을 그리는 열은 `datetime` 이다** (2026-09-01).
 *
 * `DateCell`(`ui/cells.jsx`)이 내는 값은 언제나 `2026-09-01 23:30` — 날짜가 아니라 날짜와
 * 시각이고, 폭이 실측 120px 다. 그런데 그 칸을 그리는 열들이 `type:"date"`(바닥 8.5rem =
 * 136px)나 더 좁은 명시 폭(`width:"8rem"`)으로 선언돼 있었다. 칸 안쪽 여백이 2rem 이므로
 * 필요한 폭은 **9.5rem** 이다 — 모자란 만큼이 그대로 넘쳤다.
 *
 * 모자란 폭이 조용히 잘리지 않는 이유는 `kit.jsx::colCellSx` 에 있다: `render` 가 있는
 * nowrap 열에는 `overflow:hidden` 을 안 건다(배지가 반쪽으로 잘리는 것을 막으려고).
 * 그래서 글자가 칸 밖으로, 그리고 **표 밖으로** 나갔다 — `/projects` 1920 실측에서 마지막
 * 열의 «2026-09-01 23:30» 이 표 오른쪽 테두리를 8px 넘어 그려졌다.
 *
 * 자리가 하나가 아니었다: 공용 `dateCol()`(관리 콘솔 전체가 쓴다)과 화면 여섯이 같은
 * 모양이었다. 그래서 판정을 소스로 옮긴다 — 다음에 `DateCell` 을 쓰는 열이 생기면 그때
 * 이 시험이 실패한다(`chart-question.test.js` 와 같은 방식).
 *
 * 상세 필드(`{ key, label, value: <DateCell/> }`)는 대상이 아니다 — 표의 열이 아니라
 * 라벨-값 한 줄이고 폭 경쟁을 하지 않는다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");

function walk(dir) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) { out.push(...walk(full)); continue; }
    if (!/\.jsx?$/.test(name) || /\.test\.jsx?$/.test(name)) continue;
    out.push(full);
  }
  return out;
}

/** `<DateCell` 이 나오는 줄 하나를 열 선언으로 읽는다. `type:` 과 `value:` 를 함께 본다. */
function dateCellLines() {
  const sites = [];
  for (const file of walk(SRC)) {
    if (file.endsWith(path.join("ui", "cells.jsx"))) continue;   // 부품 자신
    const text = fs.readFileSync(file, "utf8");
    text.split(/\r?\n/).forEach((line, i) => {
      if (!/<DateCell\b/.test(line)) return;
      sites.push({ where: path.relative(SRC, file) + ":" + (i + 1), line: line.trim() });
    });
  }
  return sites;
}

describe("DateCell 을 그리는 열의 폭 어휘", () => {
  const sites = dateCellLines();

  it("표본이 실재한다 — 0곳을 도는 검사는 실패를 만들 수 없다", () => {
    expect(sites.length).toBeGreaterThanOrEqual(8);
  });

  it("`datetime` 바닥은 이 값이 실제로 필요한 폭보다 넓다", () => {
    // 120px(글자) + 32px(칸 안쪽 여백) = 152px = 9.5rem.
    expect(Number.parseFloat(COLUMN_TYPES.datetime.minWidth)).toBeGreaterThanOrEqual(9.5);
  });

  it("🔴 열로 쓰이면 `type: \"datetime\"` 이다 — `date`(8.5rem)로는 폭이 모자란다", () => {
    const bad = sites
      .filter((s) => /\bkey\s*:/.test(s.line))          // 열/필드 선언인 줄만
      .filter((s) => !/\bvalue\s*:/.test(s.line))       // 상세 필드는 열이 아니다
      .filter((s) => !/type\s*:\s*"datetime"/.test(s.line))
      .map((s) => s.where + " → " + s.line.slice(0, 90));
    expect(bad, `날짜·시각 열인데 datetime 이 아니다:\n${bad.join("\n")}`).toEqual([]);
  });

  it("🔴 그 열에 `datetime` 바닥보다 좁은 폭을 손으로 적지 않는다", () => {
    const floor = Number.parseFloat(COLUMN_TYPES.datetime.minWidth);
    const bad = [];
    for (const s of sites) {
      const m = /\b(width|minWidth)\s*:\s*"([\d.]+)rem"/.exec(s.line);
      if (m && Number.parseFloat(m[2]) < floor) bad.push(s.where + " → " + m[0]);
    }
    expect(bad, `어휘의 바닥보다 좁게 적었다:\n${bad.join("\n")}`).toEqual([]);
  });
});
