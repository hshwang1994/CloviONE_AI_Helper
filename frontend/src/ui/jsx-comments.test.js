/* JSX 주석이 제대로 닫혀 있는가.
 *
 * `{/* … *​/}` 에서 닫는 `}` 를 빠뜨리면 그 뒤의 JSX 가 통째로 JS 표현식으로 읽혀
 * `Expected identifier but found "!"` 같은 **엉뚱한 위치의 파싱 오류**가 난다.
 * 실제로 이 저장소에서 한 세션에 세 번 났고(AppShell 2회, kit 1회), 매번 오류가
 * 가리키는 줄과 진짜 원인이 20~60줄 떨어져 있어 찾는 데 시간이 걸렸다.
 *
 * vitest 는 파일을 변환할 때만 이걸 잡는다 — 그 파일을 import 하는 테스트가 없으면
 * 조용히 지나간다. 그래서 소스 전체를 직접 훑는 검사를 둔다. */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// jsdom 환경에서는 `import.meta.url` 이 file: 스킴이 아니라 fileURLToPath 가 던진다.
// vitest 는 `frontend/` 에서 도므로 cwd 기준이 안전하다.
const SRC = join(process.cwd(), "src");

function jsxFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...jsxFiles(full));
    else if (name.endsWith(".jsx")) out.push(full);
  }
  return out;
}

describe("JSX 주석", () => {
  it("`{/*` 로 연 주석은 전부 `*/}` 로 닫힌다", () => {
    const broken = [];
    for (const file of jsxFiles(SRC)) {
      const text = readFileSync(file, "utf8");
      const opener = /\{\/\*/g;
      let m;
      while ((m = opener.exec(text)) !== null) {
        const end = text.indexOf("*/", m.index + 3);
        if (end < 0 || text.slice(end, end + 3) !== "*/}") {
          const line = text.slice(0, m.index).split("\n").length;
          broken.push(`${file.replace(SRC, "src")}:${line}`);
        }
      }
    }
    expect(broken).toEqual([]);
  });
});
