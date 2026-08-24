import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { MASCOT } from "../lib/assets.js";
import { MASCOT_BOUNDS, hfracOf } from "./mascotBounds.js";
import { MASCOT_PLACE, mascotBoxPx } from "./Mascot.jsx";

/* 클로비가 **보이는 크기**로 나오는가 (지시 71 · PLAN «Clovi 계약»).
 *
 * 이 시험이 막는 실패는 하나다: **호출부가 박스 픽셀을 손으로 적는 것.** 포즈 PNG 는 전부
 * 1024² 인데 캐릭터가 차지하는 세로 비율이 0.666~0.850 으로 벌어져서, 같은 `size={48}` 이
 * 자산에 따라 40px 짜리 캐릭터도 되고 32px 짜리도 된다. 그 차이는 박스를 재는 어떤 검사로도
 * 안 보인다 — 그래서 지시 71 이 "실제 브라우저에서 너무 작다" 고 말할 때까지 아무도 몰랐다.
 *
 * 판정 밴드의 정본은 QA 프로브(`scripts/ui_qa/mascot.py`)다. 여기서 그 숫자를 다시 적지
 * 않고 **소스에서 읽는다** — 두 벌로 적는 순간 한쪽만 고쳐지고, 그때 이 시험은 통과하는데
 * 캡처는 실패한다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");
const PROBE = path.resolve(HERE, "../../../scripts/ui_qa/mascot.py");
const BOUNDS_JSON = path.resolve(HERE, "../../../app/static/brand/mascot/mascot-bounds.json");

/** 프로브의 `MIN_VISIBLE_H` 를 소스에서 읽는다. */
function probeBands() {
  const text = fs.readFileSync(PROBE, "utf8");
  const block = text.match(/MIN_VISIBLE_H\s*=\s*\{([\s\S]*?)\}/);
  expect(block, "프로브에서 MIN_VISIBLE_H 를 못 찾았다").toBeTruthy();
  const bands = {};
  for (const m of block[1].matchAll(/"([a-z_]+)"\s*:\s*([0-9.]+)/g)) bands[m[1]] = Number(m[2]);
  return bands;
}

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

/** 소스에서 `<Component ... >` 여는 태그를 통째로 잘라 낸다(중첩 JSX 표현식을 센다). */
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

const CONSUMERS = walk(SRC).filter((f) => !f.endsWith(path.join("ui", "Mascot.jsx")));

describe("클로비 크기 계약", () => {
  it("모든 호출부가 박스가 아니라 **자리**를 말한다", () => {
    const offenders = [];
    for (const file of CONSUMERS) {
      const text = fs.readFileSync(file, "utf8");
      for (const component of ["MascotPose", "MascotMini"]) {
        for (const tag of openingTags(text, component)) {
          const rel = path.relative(SRC, file).split(path.sep).join("/");
          if (!/\bplace=/.test(tag)) offenders.push(`${rel}: <${component}> 에 place= 가 없다`);
          else if (/\bsize=/.test(tag)) offenders.push(`${rel}: <${component}> 가 place 와 size 를 함께 준다`);
        }
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("모든 자리가 프로브가 아는 밴드를 선언한다", () => {
    const bands = probeBands();
    const unknown = Object.entries(MASCOT_PLACE)
      .filter(([, spec]) => !(spec.context in bands))
      .map(([name, spec]) => `${name}: 프로브에 없는 context ${spec.context}`);
    expect(unknown, unknown.join("\n")).toEqual([]);
  });

  it("어떤 포즈를 넣어도 그 자리의 하한을 넘는다", () => {
    const bands = probeBands();
    const offenders = [];
    for (const [place, spec] of Object.entries(MASCOT_PLACE)) {
      const floor = bands[spec.context];
      for (const src of Object.values(MASCOT)) {
        const box = mascotBoxPx(place, src);
        const boxes = typeof box === "number" ? [box] : Object.values(box);
        for (const b of boxes) {
          const visible = b * hfracOf(src);
          if (visible < floor) {
            offenders.push(
              `${place} × ${src.split("/").pop()}: 보이는 높이 ${visible.toFixed(1)}px`
              + ` < 하한 ${floor}px (박스 ${b}px)`);
          }
        }
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("여백이 다른 자산이 같은 크기로 **보인다** — 박스는 서로 다르다", () => {
    /* 이 시험이 곧 이 계약의 존재 이유다. `clovi-idle-blink`(잉크 85%)와
       `clovi-wave`(72%)는 여백이 13%p 다르다 — 박스를 같게 주면 보이는 크기가 다르고,
       보이는 크기를 같게 주면 박스가 달라야 한다. */
    const a = MASCOT.blink, b = MASCOT.wave;
    expect(hfracOf(a)).not.toBe(hfracOf(b));
    const boxA = mascotBoxPx("assistantHero", a);
    const boxB = mascotBoxPx("assistantHero", b);
    expect(boxA).not.toBe(boxB);
    expect(boxA * hfracOf(a)).toBeCloseTo(boxB * hfracOf(b), 0);
    expect(boxA * hfracOf(a)).toBeCloseTo(MASCOT_PLACE.assistantHero.visible, 0);
  });

  it("잠금 파일과 생성된 사본이 같은 값을 말한다", () => {
    const lock = JSON.parse(fs.readFileSync(BOUNDS_JSON, "utf8"));
    const drift = [];
    for (const [file, entry] of Object.entries(lock.assets)) {
      const mirror = MASCOT_BOUNDS[file];
      if (!mirror) { drift.push(`${file}: 사본에 없다`); continue; }
      if (mirror.hfrac !== entry.hfrac) drift.push(`${file}: hfrac ${mirror.hfrac} ≠ ${entry.hfrac}`);
    }
    expect(drift, drift.join("\n")).toEqual([]);
    expect(Object.keys(MASCOT_BOUNDS).length).toBe(Object.keys(lock.assets).length);
  });

  it("모르는 자산은 여백이 없다고 본다 — 크기를 부풀리지 않는다", () => {
    /* 반례. 잠금에 없는 경로가 오면 `hfrac=1` 이라 박스가 «보이는 크기» 그대로다.
       이 값이 1 보다 작으면 모르는 자산이 조용히 커지고, 1 보다 크면 조용히 작아진다. */
    expect(hfracOf("/static/brand/mascot/없는-자산.png")).toBe(1);
    expect(mascotBoxPx("gameCelebrate", "/없는/경로.png")).toBe(MASCOT_PLACE.gameCelebrate.visible);
  });
});
