import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 그림마다 «이 그림이 답하는 업무 질문» 이 있는가 (W6).
 *
 * 왜 소스를 직접 세는가: 부품이 런타임에 던지면 선언 하나가 빠진 것 때문에 화면이 통째로
 * 죽는다. 그렇다고 조용히 넘기면 그 선언은 있으나 마나다 — 실제로 W5 이전의
 * `CHART_SERIES` 가 «정의는 있는데 소비처가 0» 인 채로 여러 Wave 를 살아남았다.
 * 그래서 판정을 시험으로 옮긴다: **소스에 그려진 것**을 세고, 새 소비처가 생기면 그때
 * 실패한다(`registry-entity-fields.test.js` 가 Entity 선택기에 쓰는 것과 같은 방식).
 *
 * 「제목」은 이 질문이 아니다. «상태 구성» 은 무엇을 그렸는지를 말하지, 그것을 보고 무슨
 * 판단을 해야 하는지를 말하지 않는다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../..");
const COMPONENTS = ["LineSeries", "BarSeries", "Donut", "Sparkline"];

function walk(dir) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) { out.push(...walk(full)); continue; }
    if (!/\.jsx?$/.test(name) || /\.test\.jsx?$/.test(name)) continue;
    if (full.includes(path.join("ui", "charts"))) continue;      // 부품 자신은 소비처가 아니다
    out.push(full);
  }
  return out;
}

/** 소스에서 `<Component ... >` 여는 태그 하나를 통째로 잘라 낸다. */
function openingTags(text, component) {
  const out = [];
  const re = new RegExp("<" + component + "[\\s/>]", "g");
  let m;
  while ((m = re.exec(text)) !== null) {
    let depth = 0;
    for (let i = m.index; i < text.length; i++) {
      const ch = text[i];
      if (ch === "{") depth++;
      else if (ch === "}") depth--;
      else if (ch === ">" && depth === 0) { out.push(text.slice(m.index, i + 1)); break; }
    }
  }
  return out;
}

describe("차트 소비처는 «이 그림이 답하는 업무 질문» 을 갖는다", () => {
  const files = walk(SRC);
  const sites = [];
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    for (const c of COMPONENTS) {
      for (const tag of openingTags(text, c)) {
        sites.push({ where: path.relative(SRC, file) + " :: " + c, tag });
      }
    }
  }

  it("표본이 실재한다 — 0곳을 도는 검사는 실패를 만들 수 없다", () => {
    // 「검사가 위반을 못 찾았다」와 「검사가 아무것도 안 봤다」는 다른 사실이다.
    expect(sites.length).toBeGreaterThanOrEqual(10);
  });

  it("🔴 선언이 빠진 소비처가 없다", () => {
    const naked = sites.filter((s) => !/\bquestion\s*=/.test(s.tag)).map((s) => s.where);
    expect(naked).toEqual([]);
  });

  it("질문은 한 문장으로 끝난다 — 조각 문장을 두지 않는다", () => {
    const bad = [];
    for (const s of sites) {
      const m = /\bquestion="([^"]+)"/.exec(s.tag);
      if (!m) continue;
      const q = m[1];
      if (!/[.。]$|다\.$|니다\.$/.test(q)) bad.push(s.where + " → " + q);
      if (q.length > 120) bad.push(s.where + " (너무 길다: " + q.length + "자)");
    }
    expect(bad).toEqual([]);
  });
});
